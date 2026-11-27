"""咽頭の最初の直列枝で流量差を生じさせる項を調べる。"""

import argparse
from itertools import islice
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

from scipy.io import wavfile

from measure_fixed_voice_glottal_branch import FIELDS, NATIVE_NET, PROBE, UPPER_NET, apply_edits, replay
from measure_fixed_voice_lung_port_momentum import CASE as LUNG_CASE
from measure_fixed_voice_pharyngeal_wall_surface import CASE as WALL_CASE
from measure_fixed_voice_pharynx_onset import PRESSURE, pressure_terms, restore_pressure
from measure_fixed_voice_radiation_balance import CASE as RADIATION_CASE
from measure_fixed_voice_radiation_derivative import CASE as DERIVATIVE_CASE
from measure_fixed_voice_subglottal_balance import apply_patch
from measure_fixed_voice_tracheal_momentum import (
    BALANCE_CASE, CASE as SINGLE_CASE, PATCH_ORDER, REFERENCES, ROOT, read_rows,
    record_measurement, same, source_inputs, stage_candidate, verified_artifact,
)
from measure_fixed_voice_tracheal_penultimate import flow_substitutions
from measure_fixed_voice_tracheal_series_momentum import CASE as SERIES_CASE
from measure_uniform_tube import build_upstream_probe
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/fixed-voice-pharyngeal-entry-branch-48000.json'
GEOMETRY = ('internal_sample', 'left_node', 'right_node', 'left_area', 'right_area', 'left_minimum', 'right_minimum',
            'left_length', 'right_length', 'left_perimeter', 'right_perimeter', 'left_viscous', 'right_viscous')
NATIVE_ANCHOR = '        let trace_tag = |branch, glottis| {'
NATIVE_LOOKUP = '''        let pharyngeal_branch = research.map(|(glottis, _)| {
            let inlet = self.branches[glottis].nodes[1];
            self.branches.iter().position(|edge| edge.nodes == [inlet, inlet + 1] && edge.port.is_none()).unwrap()
        });
'''
UPPER_ANCHOR = '        let enable_energy_safe = self.energy_safe;'
UPPER_LOOKUP = '''        let pharyngeal_branch = research.map(|(glottis, _)| {
            let inlet = self.b_b[glottis];
            self.b_a.iter().zip(&self.b_b).zip(&self.b_kind)
                .position(|((&a, &b), &kind)| a == inlet && b == inlet + 1 && kind == KIND_SERIES).unwrap()
        });
'''
NATIVE_PRINT = '            let observation = research.and_then(|(watched, sample)| trace_tag(index, watched)'
NATIVE_GEOMETRY = '''            if let Some((_, sample)) = research && pharyngeal_branch == Some(index) {
                let [a, b] = branch.nodes.map(|node| self.sections[node]);
                let geometry = [a.area_cm2, b.area_cm2, a.minimum_area_cm2, b.minimum_area_cm2,
                    a.length_cm, b.length_cm, a.perimeter_factor, b.perimeter_factor, a.viscous_factor, b.viscous_factor];
                print!("pharyngeal-geometry,{sample},{left},{right}");
                for value in geometry { print!(",{value:?}"); }
                println!();
            }
'''
UPPER_PRINT = '                if let Some((_, sample)) = research.filter(|&(branch, _)| branch == j) {'
UPPER_GEOMETRY = '''                if let Some((_, sample)) = research && pharyngeal_branch == Some(j) {
                    let geometry = [area[a], area[b], amin[a], amin[b], self.dx[a], self.dx[b],
                        self.wall_perim[a], self.wall_perim[b], self.visc_f[a], self.visc_f[b]];
                    print!("pharyngeal-geometry,{sample},{a},{b}");
                    for value in geometry { print!(",{value:?}"); }
                    println!();
                }
                if let Some((_, sample)) = research.filter(|&(branch, _)| branch == j || pharyngeal_branch == Some(j)) {
                    let tag = if pharyngeal_branch == Some(j) { "pharyngeal," } else { "" };'''
NATIVE_EDITS = (
    (NATIVE_ANCHOR, NATIVE_LOOKUP + NATIVE_ANCHOR),
    ('            let earlier = match tracheal {',
     '            let earlier = match tracheal {\n'
     '                _ if pharyngeal_branch == Some(branch) => Some("pharyngeal,"),'),
    (NATIVE_PRINT, NATIVE_GEOMETRY + NATIVE_PRINT),
)
UPPER_EDITS = (
    (UPPER_ANCHOR, UPPER_LOOKUP + UPPER_ANCHOR),
    (UPPER_PRINT, UPPER_GEOMETRY),
    ('                    print!("{sample}");', '                    print!("{tag}{sample}");'),
)


def capture_native(refs, copies, snapshot, out, execute):
    with TemporaryDirectory(prefix='pharynx-branch-candidate-', dir=out.parent) as temp:
        root = Path(temp)
        source, target = root / 'source', root / 'target'
        stage_candidate(snapshot, copies, source)
        for name in (*PATCH_ORDER, 'single.patch', 'series.patch', 'lung.patch', 'slit.patch', 'trace.patch',
                     'wall.patch', 'derivative.patch'):
            apply_patch(source, refs[name], execute)
        apply_edits(source, {NATIVE_NET: NATIVE_EDITS}, out / 'candidate-pharyngeal-entry.patch')
        execute(['cargo', 'build', '--release', '--locked', '--offline', '-p', 'vocal-cli',
                 '--manifest-path', str(source / 'Cargo.toml'), '--target-dir', str(target)])
        cli = target / 'release/vocal-cli'
        prefix = str(refs['extended-prefix-case.json'])
        execute([str(cli), 'render', prefix, str(out / 'candidate-internal.csv')], stdout=out / 'candidate-raw.txt')
        execute([str(cli), 'render-pcm', prefix, str(out / 'candidate.wav'), '--no-trace', '128'],
                stdout=out / 'candidate-pcm-probe.txt')
        return sha256(cli)


def capture_upstream(case, refs, out, execute):
    with TemporaryDirectory(prefix='pharynx-branch-upstream-', dir=out.parent) as temp:
        source = Path(temp)
        tar = source / 'source.tar'
        execute(['git', 'archive', case['upstream_revision']], cwd=UPSTREAM, stdout=tar)
        execute(['tar', '-xf', str(tar), '-C', str(source)])
        apply_patch(source, refs['upstream-observation.patch'], execute)
        apply_edits(source, {UPPER_NET: UPPER_EDITS}, out / 'upstream-pharyngeal-entry.patch')
        probe = build_upstream_probe(PROBE, out, execute, upstream=source, cargo_args=('--offline',))
    prefix = json.loads(refs['extended-prefix-case.json'].read_text())
    fs = prefix['fixed_airway']['sample_rate_hz']
    rate = prefix['voice']['output_sample_rate_hz']
    frames = prefix['fixed_airway']['sample_count'] * rate // fs
    voice = prefix['voice']
    args = ['i', fs, rate, frames, *(voice[key] for key in ('pressure_cm_h2o', 'gate', 'breathiness', 'tension', 'output_gain'))]
    execute([str(probe), 'render', *map(str, args), str(out), str(refs['gate-events.txt'])],
            cwd=UPSTREAM, stdout=out / 'upstream-raw.txt')
    return sha256(probe), frames, fs


def read_capture(out, side, samples, nodes):
    raw = (out / f'{side}-raw.txt').read_text().splitlines(keepends=True)
    tables = []
    for tag, fields in (('pharyngeal', FIELDS), ('pharyngeal-geometry', GEOMETRY)):
        prefix = tag + ','
        path = out / f'{side}-{tag}.csv'
        path.write_text(','.join(fields) + '\n' + ''.join(line.removeprefix(prefix) for line in raw if line.startswith(prefix)))
        table = read_rows(path)
        if [row['internal_sample'] for row in table] != samples:
            raise ValueError(f'咽頭枝の観測区間を確認できません ({path.name})')
        tables.append(table)
    if any([row['left_node'], row['right_node']] != nodes for row in tables[1]):
        raise ValueError(f'咽頭枝の両端の番号が一致しません ({side})')
    return tables


def verify_clock(table, native, fs, upper, *, multiply_history=False):
    return all(same(branch['flow'], native[i]['pharynx_outflow_cm3_s'])
               and same(branch['left_pressure'], native[i - 1][PRESSURE])
               and same(branch['right_pressure'], native[i - 1]['pharynx_next_pressure_dyn_cm2'])
               and same(restore_pressure(pressure_terms(native[i - 1], native[i]), fs), native[i][PRESSURE])
               and all(same(float(value), branch[key]) for key, value in replay(
                   branch, fs, upper, multiply_history=multiply_history).items())
               for branch in table for i in (int(branch['internal_sample']),))


def measure(case, refs, copies, snapshot, out, execute):
    candidate_hash = capture_native(refs, copies, snapshot, out, execute)
    upper_hash, frames, fs = capture_upstream(case, refs, out, execute)
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera', '--test', 'airway', '--test', 'airway_adversarial'],
            cwd=UPSTREAM, stdout=out / 'upstream-tests.log')
    start, end = (case[key] for key in ('first_internal_sample', 'end_internal_sample_exclusive'))
    samples = list(range(start, end))
    nodes = case['first_ordered_branch_nodes']
    candidate, candidate_geom = read_capture(out, 'candidate', samples, nodes)
    upstream, upper_geom = read_capture(out, 'upstream', samples, nodes)
    native_trace = {row['internal_sample']: row for row in read_rows(out / 'candidate-internal.csv')}
    upper_trace = {row['internal_sample']: row for row in read_rows(refs['upstream-pharynx-balance.csv'])}
    rate, audio = wavfile.read(out / 'candidate.wav')
    prior_rate, prior_audio = wavfile.read(refs['block-128.wav'])
    with refs['upstream-trace.csv'].open('rb') as stream:
        upper_prefix = b''.join(islice(stream, frames + 1))
    first = next((i for i, a, b in zip(samples, candidate, upstream, strict=True) if not same(a['flow'], b['flow'])), None)
    first_pressure = next((i for i in samples if not same(native_trace[i][PRESSURE], upper_trace[i][PRESSURE])), None)
    targets = sorted({i for i in (first, case['known_flow_difference'], case['known_pressure_difference']) if i is not None})
    details = {str(i): {**flow_substitutions(candidate[i - start], upstream[i - start], fs),
                       'candidate_geometry': candidate_geom[i - start], 'upstream_geometry': upper_geom[i - start]}
               for i in targets if not same(candidate[i - start]['flow'], upstream[i - start]['flow'])}
    i = case['known_pressure_difference']
    pressure_inputs = pressure_terms(native_trace[i - 1], native_trace[i])
    pressure_inputs['pharynx_outflow_cm3_s'] = upstream[i - start]['flow']
    restored = restore_pressure(pressure_inputs, fs)
    checks = {
        'candidate_internal_trace_reproduced': sha256(out / 'candidate-internal.csv') == sha256(refs['candidate-internal.csv']),
        'candidate_pcm_prefix_reproduced': rate == prior_rate and len(audio) == frames and audio.tobytes() == prior_audio[:frames].tobytes(),
        'fixed_upstream_prefix_reproduced': ((out / 'upstream-trace.csv').read_bytes() == upper_prefix
            and (out / 'upstream-voice.f32').read_bytes() == refs['upstream-voice.f32'].read_bytes()[:frames * 4]),
        'candidate_branch_clock_and_equation': verify_clock(candidate, native_trace, fs, False),
        'upstream_branch_clock_and_equation': verify_clock(upstream, upper_trace, fs, True),
        'known_differences_reproduced': first_pressure == i and str(case['known_flow_difference']) in details
            and str(i) in details,
        'pressure_reconstructed_by_outflow_substitution': same(restored, upper_trace[i][PRESSURE]),
        'branch_flow_reconstructed_at_reported_events': bool(details) and all(
            event['minimum_upstream_substitutions'] for event in details.values()),
    }
    return {'checks': checks, 'build_sha256': {'candidate': candidate_hash, 'upstream': upper_hash},
            'first_branch_flow_difference': first, 'first_pharyngeal_pressure_difference': first_pressure,
            'branch_events': details, 'restored_pressure': {'sample': i, 'pressure': restored}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    slit_path = WORKSPACE / 'cases/fixed-voice-glottal-slit-48000.json'
    paths = (CASE, DERIVATIVE_CASE, WALL_CASE, RADIATION_CASE, SINGLE_CASE, BALANCE_CASE, SERIES_CASE, LUNG_CASE, slit_path)
    case, derivative, wall, radiation, common, base, series, lung, slit = (json.loads(path.read_text()) for path in paths)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    groups = {**base['references'], 'onset': common['onset_run'], 'pcm': common['pcm_input_run']}
    names = {group: [name for name in filenames if name in PATCH_ORDER] for group, filenames in REFERENCES.items()}
    names['scaled'].append('upstream-observation.patch')
    names['pressure'].append('gate-events.txt')
    names['pcm'] = ['upstream-voice.f32', 'upstream-trace.csv']
    refs, manifests = {}, {}
    for group, files in names.items():
        for name in files:
            manifests[group], refs[name] = verified_artifact(*groups[group], f'artifacts/{name}')
    for group, run in (('single', series['single_branch_run']), ('series', lung['series_run']), ('lung', slit['lung_run']),
                       ('slit', radiation['slit_run']), ('wall', derivative['wall_run']), ('derivative', case['derivative_run'])):
        manifests[group], refs[f'{group}.patch'] = verified_artifact(*run, 'artifacts/candidate-tracheal-history.patch')
    manifests['radiation'], refs['trace.patch'] = verified_artifact(*wall['radiation_run'], 'artifacts/candidate-radiation.patch')
    manifests['prefix'], refs['extended-prefix-case.json'] = verified_artifact(*radiation['prefix_run'], 'artifacts/extended-prefix-case.json')
    manifests['pressure-balance'], refs['upstream-pharynx-balance.csv'] = verified_artifact(
        *case['upstream_pressure_run'], 'artifacts/upstream-pharynx-balance.csv')
    for name in ('candidate-internal.csv', 'block-128.wav'):
        _, refs[name] = verified_artifact(*case['derivative_run'], f'artifacts/reordered/{name}')
    copies, archived, snapshot = source_inputs(manifests['scaled'])
    loaded = (Path(file).resolve() for module in tuple(sys.modules.values())
              if (file := getattr(module, '__file__', None)))
    tools = sorted({path for path in loaded if path.parent == WORKSPACE / 'tools' and path.suffix == '.py'})
    inputs = [*paths, PROBE, WORKSPACE / 'LICENSE-CHIMERA', *archived, *tools, *manifests.values(), *refs.values()]
    return record_measurement(args.run_id, CASE, inputs, {'case_id': case['id'], 'upstream_revision': revision},
                              lambda out, run: measure(case, refs, copies, snapshot, out, run),
                              command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
