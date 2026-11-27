"""固定発声で壁・開口の放射流量と時間微分の丸めを比較する。"""

import argparse
from itertools import combinations, islice
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

from measure_fixed_voice_glottal_branch import NATIVE_NET, PROBE, UPPER_NET, apply_edits, f64
from measure_fixed_voice_glottal_slit_prefix import CASE as PREFIX_CASE
from measure_fixed_voice_lung_port_momentum import CASE as LUNG_CASE
from measure_fixed_voice_subglottal_balance import apply_patch
from measure_fixed_voice_tracheal_momentum import (
    BALANCE_CASE, CASE as SINGLE_CASE, PATCH_ORDER, REFERENCES, ROOT, read_rows,
    record_measurement, same, source_inputs, stage_candidate, verified_artifact,
)
from measure_fixed_voice_tracheal_series_momentum import CASE as SERIES_CASE
from measure_uniform_tube import build_upstream_probe
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/fixed-voice-radiation-balance-48000.json'
OUTPUT_FIELDS = ('internal_sample', 'wall', 'lip', 'nose', 'total', 'previous_total', 'derivative')
WALL_FIELDS = ('internal_sample', 'node', 'pressure', 'area', 'length', 'surface', 'mass', 'resistance', 'stiffness',
               'previous_velocity', 'previous_displacement', 'velocity', 'displacement', 'flow', 'radiation_fraction')
NATIVE_WALL = '        let mut wall_radiation = 0.0;'
UPPER_WALL = '        let mut wall_rad_sum = 0.0;'
NATIVE_OUTPUT = '        self.previous_radiation_flow = radiation_flow;'
UPPER_OUTPUT = '        self.rad_prev_total = rad_total;'


def sample_selector(windows):
    allowed = ' || '.join(f'({start}..{end}).contains(sample)' for start, end in windows)
    return ('        let radiation_sample = self.research_glottis.and_then(|(_, next)| next.checked_sub(1))\n'
            f'            .filter(|sample| {allowed});\n')


def native_edits(windows):
    return ((NATIVE_WALL, sample_selector(windows) + NATIVE_WALL),
            ('                let flow = self.wall_motion[node].step(wall, self.dt, surface, self.pressure[node]);',
             '''                let previous = self.wall_motion[node];
                let flow = self.wall_motion[node].step(wall, self.dt, surface, self.pressure[node]);
                if let Some(sample) = radiation_sample && wall.radiation_fraction != 0.0 {
                    let current = self.wall_motion[node];
                    let values = [self.pressure[node], section.area_cm2, section.length_cm, surface,
                        wall.mass_g_cm2, wall.resistance_dyn_s_cm3, wall.stiffness_dyn_cm3,
                        previous.velocity_cm_s, previous.displacement_cm, current.velocity_cm_s,
                        current.displacement_cm, flow, wall.radiation_fraction];
                    print!("radiating-wall,{sample},{node}");
                    for value in values { print!(",{value:?}"); }
                    println!();
                }'''),
            (NATIVE_OUTPUT, '''        if let Some(sample) = radiation_sample {
            let mut apertures = self.radiators.iter().flatten();
            let lip = apertures.next().unwrap().flow;
            let nose = apertures.next().unwrap().flow;
            assert!(apertures.next().is_none());
            println!("radiation,{sample},{wall_radiation:?},{lip:?},{nose:?},{radiation_flow:?},{:?},{derivative:?}",
                self.previous_radiation_flow);
        }
''' + NATIVE_OUTPUT))


def upstream_edits(windows):
    return ((UPPER_WALL, sample_selector(windows) + UPPER_WALL),
            ('            let v = ((m * inv_t - 0.5 * r) * self.wall_v[k]',
             '''            let previous_v = self.wall_v[k];
            let previous_y = self.wall_y[k];
            let v = ((m * inv_t - 0.5 * r) * self.wall_v[k]'''),
            ('            wall_rad_sum += uw * self.wall_rad[k];',
             '''            wall_rad_sum += uw * self.wall_rad[k];
            if let Some(sample) = radiation_sample && self.wall_rad[k] != 0.0 {
                let surface = self.wall_perim[k] * sa * self.dx[k];
                let values = [self.p[k], self.area[k], self.dx[k], surface, m, r, self.wall_k[k],
                    previous_v, previous_y, v, self.wall_y[k], uw, self.wall_rad[k]];
                print!("radiating-wall,{sample},{k}");
                for value in values { print!(",{value:?}"); }
                println!();
            }'''),
            (UPPER_OUTPUT, '''        if let Some(sample) = radiation_sample {
            let mut apertures = self.rad_of.iter().filter_map(|&index| usize::try_from(index).ok());
            let lip = self.rad_u[apertures.next().unwrap()];
            let nose = self.rad_u[apertures.next().unwrap()];
            assert!(apertures.next().is_none());
            println!("radiation,{sample},{wall_rad_sum:?},{lip:?},{nose:?},{rad_total:?},{:?},{out:?}",
                self.rad_prev_total);
        }
''' + UPPER_OUTPUT))


def capture_candidate(case, refs, copies, snapshot, out, execute):
    with TemporaryDirectory(prefix='radiation-candidate-', dir=out.parent) as temp:
        root = Path(temp)
        source, target = root / 'source', root / 'target'
        stage_candidate(snapshot, copies, source)
        for name in (*PATCH_ORDER, 'single.patch', 'series.patch', 'lung.patch', 'slit.patch'):
            apply_patch(source, refs[name], execute)
        apply_edits(source, {NATIVE_NET: native_edits(case['windows'])}, out / 'candidate-radiation.patch')
        execute(['cargo', 'build', '--release', '--locked', '--offline', '-p', 'vocal-cli',
                 '--manifest-path', str(source / 'Cargo.toml'), '--target-dir', str(target)])
        cli = target / 'release/vocal-cli'
        prefix = str(refs['extended-prefix-case.json'])
        execute([str(cli), 'render', prefix, str(out / 'candidate-internal.csv')], stdout=out / 'candidate-raw.txt')
        execute([str(cli), 'render-pcm', prefix, str(out / 'candidate.wav'), '--no-trace', '128'],
                stdout=out / 'candidate-pcm-probe.txt')
        return sha256(cli)


def capture_upstream(case, refs, out, execute):
    with TemporaryDirectory(prefix='radiation-upstream-', dir=out.parent) as temp:
        source = Path(temp)
        tar = source / 'source.tar'
        execute(['git', 'archive', case['upstream_revision']], cwd=UPSTREAM, stdout=tar)
        execute(['tar', '-xf', str(tar), '-C', str(source)])
        apply_patch(source, refs['upstream-observation.patch'], execute)
        apply_edits(source, {UPPER_NET: upstream_edits(case['windows'])}, out / 'upstream-radiation.patch')
        probe = build_upstream_probe(PROBE, out, execute, upstream=source, cargo_args=('--offline',))
    voice = json.loads(refs['extended-prefix-case.json'].read_text())['voice']
    args = ['i', case['internal_rate_hz'], case['output_rate_hz'], case['prefix_frames']]
    args.extend(voice[key] for key in ('pressure_cm_h2o', 'gate', 'breathiness', 'tension', 'output_gain'))
    execute([str(probe), 'render', *map(str, args), str(out), str(refs['gate-events.txt'])],
            cwd=UPSTREAM, stdout=out / 'upstream-raw.txt')
    return sha256(probe)


def read_measurements(out, name, samples):
    raw = (out / f'{name}-raw.txt').read_text().splitlines(keepends=True)
    outputs = []
    for tag, fields in (('radiation', OUTPUT_FIELDS), ('radiating-wall', WALL_FIELDS)):
        path = out / f'{name}-{tag}.csv'
        prefix = tag + ','
        path.write_text(','.join(fields) + '\n' + ''.join(
            line.removeprefix(prefix) for line in raw if line.startswith(prefix)))
        outputs.append(read_rows(path))
    terms, walls = outputs
    expected_wall_nodes = {row['node'] for row in walls}
    pairs = {(row['internal_sample'], row['node']) for row in walls}
    if ([row['internal_sample'] for row in terms] != samples or len(pairs) != len(walls)
            or pairs != {(sample, node) for sample in samples for node in expected_wall_nodes}):
        raise ValueError(f'放射の観測番号に欠測または重複があります ({name})')
    return terms, walls


def time_step(rate):
    return f64(f64(1) / rate)


def derivative(total, previous, fs, upstream):
    delta = f64(f64(total) - f64(previous))
    return float(f64(delta * fs if upstream else delta / time_step(fs)))


def sum_flow(row):
    return f64(f64(f64(row['wall']) + f64(row['lip'])) + f64(row['nose']))


def wall_values(row, fs, upstream):
    mass, resistance, stiffness = (f64(row[key]) for key in ('mass', 'resistance', 'stiffness'))
    m = f64(mass * fs if upstream else mass / time_step(fs))
    half_r = f64(resistance / 2)
    old_v, old_y, pressure = (f64(row[key]) for key in ('previous_velocity', 'previous_displacement', 'pressure'))
    applied = f64(f64(f64(m - half_r) * old_v) + pressure)
    damping = f64(stiffness * old_y)
    velocity = f64(f64(applied - damping) / f64(m + half_r))
    displacement = f64(old_y + f64(time_step(fs) * velocity))
    flow = f64(f64(row['surface']) * velocity)
    return velocity, displacement, flow


def validate(terms, walls, trace, fs, upstream, *, multiply_rate=None):
    if multiply_rate is None:
        multiply_rate = upstream
    wall_sums = {}
    for row in walls:
        values = wall_values(row, fs, upstream)
        if not all(same(float(value), row[key]) for key, value in zip(('velocity', 'displacement', 'flow'), values, strict=True)):
            return False
        sample = row['internal_sample']
        contribution = f64(f64(row['flow']) * f64(row['radiation_fraction']))
        wall_sums[sample] = f64(wall_sums.get(sample, 0) + contribution)
    for i, row in enumerate(terms):
        sample = row['internal_sample']
        if not (same(float(wall_sums[sample]), row['wall']) and same(float(sum_flow(row)), row['total'])
                and same(derivative(row['total'], row['previous_total'], fs, multiply_rate), row['derivative'])):
            return False
        if i > 0 and terms[i-1]['internal_sample'] + 1 == sample and not same(row['previous_total'], terms[i-1]['total']):
            return False
        if sample in trace and not all(same(row[key], trace[sample][column]) for key, column in (
            ('lip', 'lip_flow_cm3_s'), ('nose', 'nose_flow_cm3_s'), ('derivative', 'radiation_derivative_cm3_s2'))):
            return False
    return True


def compare_terms(a, b, fs, *, multiply_rate=False):
    keys = [key for key in ('wall', 'lip', 'nose', 'previous_total') if not same(a[key], b[key])]
    alternatives = keys if multiply_rate else [*keys, 'time_conversion']
    options = []
    for size in range(1, len(alternatives) + 1):
        for terms in combinations(alternatives, size):
            row = {**a, **{key: b[key] for key in terms if key != 'time_conversion'}}
            estimate = derivative(float(sum_flow(row)), row['previous_total'], fs, multiply_rate or 'time_conversion' in terms)
            options.append({'terms': terms, 'estimate': estimate, 'equal_upstream': same(estimate, b['derivative'])})
    successful = [entry['terms'] for entry in options if entry['equal_upstream']]
    minimum = min(map(len, successful), default=0)
    return {'candidate': a, 'upstream': b, 'substitutions': options,
            'minimum_upstream_substitutions': [keys for keys in successful if len(keys) == minimum]}


def wall_events(candidate, upstream, samples):
    sides = [{(row['internal_sample'], row['node']): row for row in rows} for rows in (candidate, upstream)]
    left, right = sides
    if left.keys() != right.keys():
        raise ValueError('放射する壁の節点番号を対応づけられません')
    hits = {}
    for key in ('pressure', 'area', 'length', 'surface', 'velocity', 'flow'):
        first = next(((sample, node) for sample in samples for _, node in sorted(k for k in left if k[0] == sample)
                      if not same(left[sample, node][key], right[sample, node][key])), None)
        hits[key] = (None if first is None else {'sample': first[0], 'node': first[1],
                      'candidate': left[first][key], 'upstream': right[first][key]})
    return hits


def measure(case, refs, copies, snapshot, out, execute):
    builds = {'candidate': capture_candidate(case, refs, copies, snapshot, out, execute),
              'upstream': capture_upstream(case, refs, out, execute)}
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera', '--test', 'airway', '--test', 'airway_adversarial'],
            cwd=UPSTREAM, stdout=out / 'upstream-tests.log')
    fs = case['internal_rate_hz']
    samples = sorted({sample for start, end in case['windows'] for sample in range(start, end)})
    candidate, candidate_walls = read_measurements(out, 'candidate', samples)
    upstream, upstream_walls = read_measurements(out, 'upstream', samples)
    native_trace, upper_trace = ({row['internal_sample']: row for row in read_rows(out / name)} for name in (
        'candidate-internal.csv', 'upstream-trace.csv'))
    with refs['upstream-trace.csv'].open('rb') as stream:
        upstream_prefix = b''.join(islice(stream, case['prefix_frames'] + 1))
    matches = [sample for sample, a, b in zip(samples, candidate, upstream, strict=True)
               if same(a['derivative'], b['derivative'])]
    first_any = next((sample for sample in samples if sample not in matches), None)
    first_frame = next((sample for sample in samples if sample in upper_trace and sample not in matches), None)
    targets = (first_any, first_frame, case['pcm_probe_internal_sample'])
    events = {str(sample): compare_terms(candidate[samples.index(sample)], upstream[samples.index(sample)], fs)
              for sample in targets if sample in samples and sample not in matches}
    checks = {
        'candidate_saved_trace_and_pcm': (sha256(out / 'candidate-internal.csv') == sha256(refs['candidate-internal.csv'])
                                          and sha256(out / 'candidate.wav') == sha256(refs['block-128.wav'])),
        'upstream_saved_trace_and_pcm': ((out / 'upstream-trace.csv').read_bytes() == upstream_prefix
                                         and (out / 'upstream-voice.f32').read_bytes() == refs['upstream-voice.f32'].read_bytes()[:case['prefix_frames'] * 4]),
        'candidate_wall_and_radiation_equations': validate(candidate, candidate_walls, native_trace, fs, False),
        'upstream_wall_and_radiation_equations': validate(upstream, upstream_walls, upper_trace, fs, True),
        'registered_frame_difference': first_frame == case['expected_first_frame_sample'],
        'event_reconstructed_with_upstream_inputs': bool(events and all(event['minimum_upstream_substitutions'] for event in events.values())),
    }
    return {'checks': checks, 'build_sha256': builds, 'first_internal_difference': first_any,
            'first_frame_end_difference': first_frame, 'events': events,
            'first_wall_differences': wall_events(candidate_walls, upstream_walls, samples),
            'sample_count_each': len(samples), 'wall_rows_each': len(candidate_walls)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    case, prefix, common, base, series, lung = (json.loads(path.read_text()) for path in (
        CASE, PREFIX_CASE, SINGLE_CASE, BALANCE_CASE, SERIES_CASE, LUNG_CASE))
    slit_case = WORKSPACE / 'cases/fixed-voice-glottal-slit-48000.json'
    slit = json.loads(slit_case.read_text())
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    if case['prefix_frames'] != prefix['prefix_frames']:
        parser.error('保存済みの延長レンダーとフレーム数が一致しません')
    groups = {**base['references'], 'onset': common['onset_run'], 'pcm': common['pcm_input_run'],
              'prefix-run': case['prefix_run']}
    filenames = {group: [name for name in names if name in PATCH_ORDER] for group, names in REFERENCES.items()}
    filenames['scaled'].append('upstream-observation.patch')
    filenames['pressure'] = ['gate-events.txt']
    filenames['pcm'] = ['upstream-trace.csv', 'upstream-voice.f32']
    filenames['prefix-run'] = ['extended-prefix-case.json', 'reordered/candidate-internal.csv', 'reordered/block-128.wav']
    refs, manifests = {}, {}
    for group, names in filenames.items():
        for name in names:
            manifests[group], refs[Path(name).name] = verified_artifact(*groups[group], f'artifacts/{name}')
    for group, run in (('single', series['single_branch_run']), ('series', lung['series_run']),
                       ('lung', slit['lung_run']), ('slit', case['slit_run'])):
        manifests[group], refs[f'{group}.patch'] = verified_artifact(*run, 'artifacts/candidate-tracheal-history.patch')
    copies, archived, snapshot = source_inputs(manifests['scaled'])
    loaded = (Path(file).resolve() for module in tuple(sys.modules.values())
              if (file := getattr(module, '__file__', None)))
    tools = sorted({path for path in loaded if path.parent == WORKSPACE / 'tools' and path.suffix == '.py'})
    inputs = [CASE, PREFIX_CASE, SINGLE_CASE, BALANCE_CASE, SERIES_CASE, LUNG_CASE, slit_case, PROBE,
              WORKSPACE / 'LICENSE-CHIMERA', *archived, *tools, *manifests.values(), *refs.values()]
    return record_measurement(args.run_id, CASE, inputs, {'case_id': case['id'], 'upstream_revision': revision},
                              lambda out, run: measure(case, refs, copies, snapshot, out, run),
                              command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
