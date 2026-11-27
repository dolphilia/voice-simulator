"""固定 /i/ の中心線の2か所の演算順を通常の幾何と描画で比較する。"""

import argparse
from difflib import unified_diff
from itertools import combinations
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

import numpy as np
from scipy.io import wavfile

import measure_fixed_voice_centerline as centerline
import measure_fixed_voice_pharynx_onset as pressure
from measure_songbird_chirps_volume_rate_propagation_44100 import stage_candidate
from measure_uniform_tube import candidate_sources, record_measurement
from measure_wasm_fixed import compare_pcm
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


ROOT = WORKSPACE.parents[2]
CASE = WORKSPACE / 'cases/fixed-voice-centerline-render-48000.json'
ANATOMY = Path('crates/vocal-core/src/anatomy.rs')
VARIANTS = {
    'standard': (),
    'epiglottis': ('epiglottis',),
    'posterior': ('posterior',),
    'combined': ('epiglottis', 'posterior'),
}
ARTIFACTS = {
    'geometry': ('candidate-contours.csv', 'candidate-area.csv', 'upstream-contours.csv', 'upstream-area.csv'),
    'pressure': ('candidate-pharynx-balance.csv', 'upstream-pharynx-balance.csv', 'prefix-case.json'),
    'pcm': ('block-128.wav', 'upstream-voice.f32', 'replay-case.json'),
}
EPIGLOTTIS = ('            body.point(0.3, 2.4) + Point::new(0.0, larynx),',
              '''            // 喉頭蓋基部のYだけ上流の体型変換と同じ順序で計算する。
            Point::new(0.3 * k, (7.0 - (7.0 - 2.4) * body.pharynx) * k) + Point::new(0.0, larynx),''')
POSTERIOR = (('        let pharynx = template_spline(', '        let pharynx = posterior_wall_spline('),
             ('fn template_spline<const N: usize>(', '''// CHIMERA の Catmull–Rom の演算順を用いる (Jameson Hodge, MIT, LICENSE-CHIMERA)。
fn posterior_wall_spline<const N: usize>(
    body: BodyParameters,
    template: [[f64; 2]; N],
    samples_per_segment: usize,
) -> Vec<Point> {
    let points = template.map(|[x, y]| body.point(x, y));
    let mut curve = Vec::with_capacity((N - 1) * samples_per_segment + 1);
    for i in 0..N - 1 {
        let p0 = points[i.saturating_sub(1)];
        let p1 = points[i];
        let p2 = points[i + 1];
        let p3 = points[(i + 2).min(N - 1)];
        for j in 0..samples_per_segment {
            let t = j as f64 / samples_per_segment as f64;
            let t2 = t * t;
            let t3 = t2 * t;
            let coordinate = |a: f64, b: f64, c: f64, d: f64| {
                0.5 * (2.0 * b + (-a + c) * t
                    + (2.0 * a - 5.0 * b + 4.0 * c - d) * t2
                    + (-a + 3.0 * b - 3.0 * c + d) * t3)
            };
            curve.push(Point::new(coordinate(p0.x, p1.x, p2.x, p3.x),
                                  coordinate(p0.y, p1.y, p2.y, p3.y)));
        }
    }
    curve.push(points[N - 1]);
    curve
}

fn template_spline<const N: usize>('''))


def edit_source(text, edits):
    for old, new in edits:
        if text.count(old) != 1:
            raise ValueError('実験用差分の位置を固定ソースの1箇所に特定できません')
        text = text.replace(old, new, 1)
    return text


def render_variants(case, refs, copies, snapshot, out, execute):
    block_sizes = case['measurement']['pcm_block_sizes']
    prefix, full = (refs[ref][name] for ref, name in (('pressure', 'prefix-case.json'), ('pcm', 'replay-case.json')))
    products, build = {}, {}
    with TemporaryDirectory(prefix='fixed-voice-centerline-', dir=out.parent) as scratch:
        root = Path(scratch)
        workspace = root / 'candidate'
        target = root / 'target'
        known = stage_candidate(snapshot, copies, workspace)
        source_file = workspace / ANATOMY
        source = source_file.read_text()
        cli = target / 'release/vocal-cli'
        for label, actions in VARIANTS.items():
            text = source
            for action in actions:
                text = edit_source(text, (EPIGLOTTIS,) if action == 'epiglottis' else POSTERIOR)
            if actions:
                source_file.write_text(text)
                difference = ''.join(unified_diff(source.splitlines(keepends=True), text.splitlines(keepends=True),
                                                 fromfile=f'a/{ANATOMY}', tofile=f'b/{ANATOMY}'))
                (out / f'{label}.patch').write_text(difference)
            changed = [name.as_posix() for name, digest in known.items() if sha256(workspace / name) != digest]
            execute(['cargo', 'build', '--release', '--locked', '--offline', '-p', 'vocal-cli',
                     '--manifest-path', str(workspace / 'Cargo.toml'), '--target-dir', str(target)])
            build[label] = {'cli_sha256': sha256(cli), 'changed_sources': changed}
            folder = out / label
            folder.mkdir()
            execute([str(cli), 'geometry', str(prefix), str(folder / 'contours.csv')])
            execute([str(cli), 'area', str(prefix), str(folder / 'area.csv')])
            execute([str(cli), 'inspect', str(prefix)], stdout=folder / 'inspect.json')
            execute([str(cli), 'render', str(prefix), str(folder / 'internal.csv')])
            for block in block_sizes:
                execute([str(cli), 'render-pcm', str(full), str(folder / f'block-{block}.wav'), '--no-trace', str(block)])
            products[label] = folder
        execute(['cargo', 'test', '--release', '--locked', '--offline', '-p', 'vocal-core',
                 '--manifest-path', str(workspace / 'Cargo.toml'), '--target-dir', str(target),
                 '--lib', 'anatomy::'], stdout=out / 'combined-geometry-tests.log')
    return products, build


def preceding_terms(actual, upper, index, rate):
    if index is None:
        return None
    local = pressure.pressure_terms(actual[index-1], actual[index])
    reference = pressure.pressure_terms(upper[index-1], upper[index])
    changed = {key: (value, reference[key]) for key, value in local.items()
               if not centerline.same(value, reference[key])}
    matches = []
    for count in range(1, len(changed) + 1):
        matches = [keys for keys in combinations(changed, count)
                   if centerline.same(pressure.restore_pressure({**local, **{key: reference[key] for key in keys}}, rate),
                                      upper[index][pressure.PRESSURE])]
        if matches:
            break
    return {'differing_terms_at_first_pressure_difference': changed, 'minimum_upstream_substitutions': matches}


def contour_vertices(path, m):
    rows = {(row['part'], int(row['index'])): float(row['y_cm']) for row in centerline.csv_rows(path)}
    return {'epiglottis': rows[('epiglottis', m['epiglottis_base_vertex'])],
            'posterior': rows[('outer', m['posterior_wall_vertex'])]}


def compare_variant(folder, label, m, geometry, vertices, upper, upper_pcm, base_pcm):
    first_ray, split = (m[k] for k in ('accumulation_ray', 'pharynx_boundary_ray'))
    open_sample = m['first_baseline_pressure_difference']
    start, end, fs = (m[k] for k in ('trace_first_sample', 'trace_end_sample_exclusive', 'internal_rate_hz'))
    shape = centerline.read_area(folder / 'area.csv')
    upper_shape, base_shape = geometry
    if len(shape) != len(upper_shape) or len(shape) <= split:
        raise ValueError(f'断面測定線の点数が一致しません ({label})')
    own_vertices = contour_vertices(folder / 'contours.csv', m)
    upper_vertices, base_vertices = vertices
    settings = json.loads((folder / 'inspect.json').read_text())['fixed_airway']
    pharynx = next(tube for tube in settings['tubes'] if tube['name'] == 'pharynx')
    cell = shape[split]['s_cm'] / m['pharynx_cells']
    actual = pressure.read_rows(folder / 'internal.csv')
    if len(actual) != len(upper) or len(actual) != m['prefix_output_frames'] * fs // m['output_rate_hz']:
        raise ValueError(f'内部サンプル数が登録と一致しません ({label})')
    internal_samples = range(start, end)
    firsts = {key: centerline.first_difference([row[key] for row in actual], [row[key] for row in upper])
              for key in upper[0] if key != 'internal_sample'}
    index = firsts[pressure.PRESSURE]
    rate_a, audio_a = wavfile.read(folder / f'block-{m["pcm_block_sizes"][0]}.wav')
    rate_b, audio_b = wavfile.read(folder / f'block-{m["pcm_block_sizes"][1]}.wav')
    limit = m['pcm_upstream_absolute_tolerance']
    if (rate_a != rate_b or rate_a != m['output_rate_hz'] or audio_a.shape != (m['full_output_frames'],)
            or audio_b.shape != audio_a.shape or audio_a.dtype != np.float32 or audio_b.dtype != np.float32):
        raise ValueError(f'WAVのレート・長さ・型が登録と異なります ({label})')
    pcm_upstream, pcm_standard = compare_pcm(audio_a, upper_pcm, limit), compare_pcm(audio_a, base_pcm, 0)
    checks = {
        'registered_contour_vertices': all(centerline.same(
            value, (upper_vertices if key in VARIANTS[label] else base_vertices)[key])
            for key, value in own_vertices.items()),
        'measurement_grid_layout': [row['region'] for row in shape] == [row['region'] for row in upper_shape],
        'fixed_airway_uses_observed_geometry': (
            pharynx['cells'] == m['pharynx_cells']
            and shape[split]['s_cm'] == pharynx['anatomical_length_cm'] == pharynx['simulation_length_cm']
            and all(centerline.same(cell, actual[i]['pharynx_length_cm']) for i in internal_samples)),
        'independent_pressure_balance': all(
            centerline.same(pressure.restore_pressure(pressure.pressure_terms(actual[i-1], actual[i]), fs),
                            actual[i][pressure.PRESSURE]) for i in internal_samples),
        'same_block_partition_pcm': audio_a.tobytes() == audio_b.tobytes(),
        'pcm_within_upstream_tolerance': pcm_upstream['first_frame_over_tolerance'] is None,
    }
    prediction = upper_shape if label == 'combined' else base_shape
    checks['registered_initial_accumulation_and_split'] = all(
        centerline.same(shape[i]['s_cm'], prediction[i]['s_cm']) for i in (first_ray, split))
    if label == 'combined':
        checks['registered_pressure_difference_removed_at_8205'] = (
            index != open_sample and centerline.same(actual[open_sample][pressure.PRESSURE],
                                                    upper[open_sample][pressure.PRESSURE]))
    evidence = {'accumulated_at_ray_cm': shape[first_ray]['s_cm'], 'pharynx_length_cm': shape[split]['s_cm'],
                'pharynx_cell_length_cm': cell,
                'contour_vertex_y_cm': own_vertices,
                'pressure_at_baseline_first_difference': actual[open_sample][pressure.PRESSURE],
                'first_difference_against_upstream': firsts,
                'first_pressure_difference_terms': preceding_terms(actual, upper, index, fs),
                'pcm_upstream': pcm_upstream, 'pcm_standard': pcm_standard}
    return checks, evidence


def measure(case, refs, copies, snapshot, out, execute):
    m = case['measurement']
    full = json.loads(refs['pcm']['replay-case.json'].read_text())
    prefix = json.loads(refs['pressure']['prefix-case.json'].read_text())
    limits = (m['full_output_frames'], m['prefix_output_frames'])
    for source, frames in zip((full, prefix), limits, strict=True):
        if (source['fixed_airway']['sample_rate_hz'] != m['internal_rate_hz']
                or source['voice']['output_sample_rate_hz'] != m['output_rate_hz']
                or source['fixed_airway']['sample_count'] != frames * m['internal_rate_hz'] // m['output_rate_hz']
                or [event['frame'] for event in source['gate_events']] != [g for g in m['gate_frames'] if g < frames]):
            raise ValueError('保存済み入力の描画長・レート・操作時刻が登録条件外です')
    if full['posture'] != prefix['posture'] or full['voice'] != prefix['voice']:
        raise ValueError('全区間と内部観測の姿勢・発声入力が異なります')
    products, build = render_variants(case, refs, copies, snapshot, out, execute)
    upper_area, base_area = [centerline.read_area(refs['geometry'][f'{name}-area.csv']) for name in ('upstream', 'candidate')]
    vertices = [contour_vertices(refs['geometry'][f'{name}-contours.csv'], m) for name in ('upstream', 'candidate')]
    upper_pressure = pressure.read_rows(refs['pressure']['upstream-pharynx-balance.csv'])
    upper_pcm = np.fromfile(refs['pcm']['upstream-voice.f32'], dtype='<f4')
    base_rate, base_pcm = wavfile.read(refs['pcm']['block-128.wav'])
    if base_rate != m['output_rate_hz'] or base_pcm.dtype != np.float32 or upper_pcm.shape != base_pcm.shape:
        raise ValueError('保存済みPCMのレート・型・長さが登録条件外です')
    checks = {
        'only_registered_source_changed': all(value['changed_sources'] == ([ANATOMY.as_posix()] if VARIANTS[label] else [])
                                              for label, value in build.items()),
        'distinct_variant_binaries': len({value['cli_sha256'] for value in build.values()}) == len(VARIANTS),
        'standard_geometry_bytes_match_archive': all(sha256(products['standard'] / f'{name}.csv')
            == sha256(refs['geometry'][f'candidate-{name}.csv']) for name in ('area', 'contours')),
        'standard_pressure_bytes_match_archive': sha256(products['standard'] / 'internal.csv')
        == sha256(refs['pressure']['candidate-pharynx-balance.csv']),
        'standard_pcm_bytes_match_archive': sha256(products['standard'] / 'block-128.wav')
        == sha256(refs['pcm']['block-128.wav']),
    }
    arms = {}
    for label, folder in products.items():
        local, arms[label] = compare_variant(folder, label, m, (upper_area, base_area), vertices,
                                            upper_pressure, upper_pcm, base_pcm)
        checks.update({f'{label}/{key}': value for key, value in local.items()})
    standard = arms['standard']
    checks['baseline_first_differences_reproduced'] = (
        standard['first_difference_against_upstream'][pressure.PRESSURE] == m['first_baseline_pressure_difference']
        and standard['pcm_upstream']['first_bit_difference_frame'] == m['first_baseline_pcm_difference'])
    return {'checks': checks, 'variants': arms, 'build': build, 'pcm_frames': m['full_output_frames']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    case = json.loads(CASE.read_text())
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    refs = {}
    inputs = [CASE, Path(__file__), WORKSPACE / 'LICENSE-CHIMERA']
    for label, names in ARTIFACTS.items():
        refs[label] = {}
        for name in names:
            manifest, artifact = centerline.verified_artifact(*case['references'][label], f'artifacts/{name}')
            refs[label][name] = artifact
            inputs.extend((manifest, artifact))
    copies = [*candidate_sources(),
              *(WORKSPACE / 'data' / name for name in (
                  'cmudict.txt.gz', 'CMUDICT-LICENSE.txt', 'mandarin.txt.gz', 'MANDARIN-PINYIN-LICENSE.txt')),
              WORKSPACE / 'cases/contour-buffer-reuse.json', WORKSPACE / 'cases/bilabial-p.json']
    tools = [Path(module.__file__) for module in (centerline, pressure)]
    tools.extend(WORKSPACE / 'tools' / name for name in
                 ('measure_uniform_tube.py', 'measure_songbird_chirps_volume_rate_propagation_44100.py',
                  'measure_wasm_fixed.py', 'upstream_baseline.py'))
    details = {'case_id': case['id'], 'upstream_revision': revision, 'isolated_source': str(ANATOMY)}
    snapshot = WORKSPACE / 'runs' / args.run_id / 'artifacts/source'
    return record_measurement(args.run_id, CASE, [*inputs, *tools, *copies], details,
                              lambda out, run: measure(case, refs, copies, snapshot, out, run),
                              command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
