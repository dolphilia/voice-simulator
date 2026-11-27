"""固定発声で咽頭の次セルの圧力収支と前後の枝を観測する。"""

import argparse
from itertools import combinations
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

from scipy.io import wavfile

from measure_fixed_voice_glottal_branch import FIELDS as BRANCH_FIELDS, NATIVE_NET, PROBE, UPPER_NET, apply_edits, replay
from measure_fixed_voice_radiation_balance import WALL_FIELDS, wall_values
from measure_fixed_voice_subglottal_balance import (
    NATIVE_PRESSURE, ROOT, UPPER_PRESSURE, apply_patch, pressure_update, read_rows, record_measurement,
    same, source_inputs, stage_candidate, verified_artifact,
)
from measure_fixed_voice_tracheal_penultimate import flow_substitutions
from measure_uniform_tube import build_upstream_probe
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/fixed-voice-pharyngeal-second-cell-48000.json'
PRESSURE = 'pharynx_next_pressure_dyn_cm2'
NODE_FIELDS = ('internal_sample', 'node', 'old_pressure', 'new_pressure', 'incoming', 'outgoing',
               'wall_outflow', 'volume_source', 'net_flow', 'volume', 'compliance')
PRESSURE_TERMS = ('old_pressure', 'volume_source', 'incoming', 'outgoing', 'wall_outflow', 'compliance')


NATIVE_PATH = '''        let cell_path = research.map(|(glottis, _)| {
            let inlet = self.branches[glottis].nodes[1];
            let node = inlet + 1;
            let incoming = pharyngeal_branch.unwrap();
            let mut outlets = self.branches.iter().enumerate().filter(|(_, edge)| edge.nodes[0] == node);
            let (outgoing, edge) = outlets.next().unwrap();
            assert!(outlets.next().is_none() && edge.nodes == [node, node + 1] && edge.port.is_none());
            assert_eq!(self.neighbors[node].len(), 2);
            assert!(incoming < outgoing);
            assert!(self.radiators[node].is_none() && !self.fixed_pressure[node] && !self.sections[node].is_closed());
            (node, incoming, outgoing)
        });
'''
UPPER_PATH = '''        let cell_path = research.map(|(glottis, _)| {
            let node = self.b_b[glottis] + 1;
            let incoming = pharyngeal_branch.unwrap();
            let mut outlets = self.b_a.iter().enumerate().filter(|&(_, &left)| left == node);
            let (outgoing, _) = outlets.next().unwrap();
            assert!(outlets.next().is_none() && self.b_b[outgoing] == node + 1 && self.b_kind[outgoing] == KIND_SERIES);
            assert_eq!(self.nbr_start[node + 1] - self.nbr_start[node], 2);
            assert!(incoming < outgoing);
            assert!(self.rad_of[node] < 0 && !self.fixed[node] && !self.is_junction[node]);
            (node, incoming, outgoing)
        });
'''
NATIVE_WALL_STEP = '                let flow = self.wall_motion[node].step(wall, self.dt, surface, self.pressure[node]);'
UPPER_WALL_STEP = '            let v = ((m * inv_t - 0.5 * r) * self.wall_v[k]'
UPPER_BRANCH_IF = '                if let Some((_, sample)) = research.filter(|&(branch, _)| branch == j || pharyngeal_branch == Some(j)) {'
UPPER_BRANCH_TAG = '                    let tag = if pharyngeal_branch == Some(j) { "pharyngeal," } else { "" };'

NATIVE_EDITS = (
    ('        let trace_tag = |branch, glottis| {', NATIVE_PATH + '        let trace_tag = |branch, glottis| {'),
    ('                _ if pharyngeal_branch == Some(branch) => Some("pharyngeal,"),',
     '                _ if cell_path.is_some_and(|(_, _, outgoing)| outgoing == branch) => Some("cell-outgoing,"),\n'
     '                _ if pharyngeal_branch == Some(branch) => Some("pharyngeal,"),'),
    (NATIVE_WALL_STEP, NATIVE_WALL_STEP + '''
                if let (Some((_, sample)), Some((target, _, _))) = (research, cell_path) && target == node {
                    let current = self.wall_motion[node];
                    let values = [self.pressure[node], section.area_cm2, section.length_cm, surface,
                        wall.mass_g_cm2, wall.resistance_dyn_s_cm3, wall.stiffness_dyn_cm3,
                        previous.velocity_cm_s, previous.displacement_cm, current.velocity_cm_s,
                        current.displacement_cm, flow, wall.radiation_fraction];
                    print!("cell-wall,{sample},{node}");
                    for value in values { print!(",{value:?}"); }
                    println!();
                }'''),
    (NATIVE_PRESSURE, NATIVE_PRESSURE + '''
                if let (Some((_, sample)), Some((target, incoming, outgoing))) = (research, cell_path) && target == node {
                    let values = [old_pressure, self.pressure[node], self.branches[incoming].flow,
                        self.branches[outgoing].flow, self.wall_motion[node].flow_cm3_s, self.volume_source(node),
                        inflow, self.sections[node].volume(), compliance];
                    print!("cell-node,{sample},{node}");
                    for value in values { print!(",{value:?}"); }
                    println!();
                }'''),
)
UPPER_EDITS = (
    ('        let enable_energy_safe = self.energy_safe;', UPPER_PATH + '        let enable_energy_safe = self.energy_safe;'),
    (UPPER_BRANCH_IF, UPPER_BRANCH_IF.replace('pharyngeal_branch == Some(j)', 'pharyngeal_branch == Some(j)\n'
                                            '                    || cell_path.is_some_and(|(_, _, outgoing)| outgoing == j)')),
    (UPPER_BRANCH_TAG, '''                    let tag = if cell_path.is_some_and(|(_, _, outgoing)| outgoing == j) {
                        "cell-outgoing,"
                    } else if pharyngeal_branch == Some(j) { "pharyngeal," } else { "" };'''),
    (UPPER_WALL_STEP, '            let previous_v = self.wall_v[k];\n'
                      '            let previous_y = self.wall_y[k];\n' + UPPER_WALL_STEP),
    ('            wall_rad_sum += uw * self.wall_rad[k];', '''            wall_rad_sum += uw * self.wall_rad[k];
            if let (Some((_, sample)), Some((target, _, _))) = (research, cell_path) && target == k {
                let surface = self.wall_perim[k] * sa * self.dx[k];
                let values = [self.p[k], self.area[k], self.dx[k], surface, m, r, self.wall_k[k],
                    previous_v, previous_y, v, self.wall_y[k], uw, self.wall_rad[k]];
                print!("cell-wall,{sample},{k}");
                for value in values { print!(",{value:?}"); }
                println!();
            }'''),
    (UPPER_PRESSURE, '''                let old_pressure = self.p[k];
''' + UPPER_PRESSURE + '''
                if let (Some((_, sample)), Some((target, incoming, outgoing))) = (research, cell_path) && target == k {
                    let values = [old_pressure, self.p[k], self.u[incoming], self.u[outgoing],
                        self.wall_u[k], self.vol_src2[k], self.flow_sum[k], self.vol[k], c];
                    print!("cell-node,{sample},{k}");
                    for value in values { print!(",{value:?}"); }
                    println!();
                }'''),
)


def listed_input(manifest, name):
    entries = json.loads(manifest.read_text())['inputs']
    entry, = [entry for entry in entries if entry['path'].endswith('/' + name)]
    path = ROOT / entry['path']
    if sha256(path) != entry['sha256']:
        raise ValueError(f'先行実行の入力が保存ハッシュと一致しません ({path.name})')
    return path


def candidate_patches(manifest):
    previous = json.loads(manifest.read_text())
    patches = []
    for command in previous['commands']:
        argv = command['argv']
        if len(argv) == 3 and argv[:2] == ['git', 'apply']:
            prefix = '$WORKSPACE/'
            if not argv[2].startswith(prefix) or command['exit_code'] != 0:
                raise ValueError('先行実行の適用差分を再構成できません')
            patches.append(listed_input(manifest, argv[2].removeprefix(prefix)))
    if not patches:
        raise ValueError('先行実行に適用差分の記録がありません')
    return patches


def capture_candidate(patches, prefix, copies, snapshot, out, execute):
    with TemporaryDirectory(prefix='pharynx-cell-candidate-', dir=out.parent) as temp:
        root = Path(temp)
        source = root / 'source'
        stage_candidate(snapshot, copies, source)
        for patch in patches:
            apply_patch(source, patch, execute)
        apply_edits(source, {NATIVE_NET: NATIVE_EDITS}, out / 'candidate-second-cell.patch')
        target = root / 'target'
        execute(['cargo', 'build', '--release', '--locked', '--offline', '-p', 'vocal-cli',
                 '--manifest-path', str(source / 'Cargo.toml'), '--target-dir', str(target)])
        cli = target / 'release/vocal-cli'
        execute([str(cli), 'render', str(prefix), str(out / 'candidate-internal.csv')], stdout=out / 'candidate-raw.txt')
        execute([str(cli), 'render-pcm', str(prefix), str(out / 'candidate.wav'), '--no-trace', '128'],
                stdout=out / 'candidate-pcm-probe.txt')
        return sha256(cli)


def capture_upstream(case, prefix, saved, out, execute):
    with TemporaryDirectory(prefix='pharynx-cell-upstream-', dir=out.parent) as temp:
        source = Path(temp)
        tar = source / 'source.tar'
        execute(['git', 'archive', case['upstream_revision']], cwd=UPSTREAM, stdout=tar)
        execute(['tar', '-xf', str(tar), '-C', str(source)])
        for name in ('upstream-observation.patch', 'upstream-pharyngeal-entry.patch'):
            apply_patch(source, saved[name], execute)
        apply_edits(source, {UPPER_NET: UPPER_EDITS}, out / 'upstream-second-cell.patch')
        probe = build_upstream_probe(PROBE, out, execute, upstream=source, cargo_args=('--offline',))
    voice = json.loads(prefix.read_text())['voice']
    args = ['i', *(case[key] for key in ('internal_rate_hz', 'output_rate_hz', 'prefix_output_frames'))]
    args.extend(voice[key] for key in ('pressure_cm_h2o', 'gate', 'breathiness', 'tension', 'output_gain'))
    execute([str(probe), 'render', *map(str, args), str(out), str(saved['gate-events.txt'])],
            cwd=UPSTREAM, stdout=out / 'upstream-raw.txt')
    return sha256(probe)


def read_observations(out, side, samples, node):
    raw = (out / f'{side}-raw.txt').read_text().splitlines(keepends=True)
    outputs = {}
    for tag, fields in (('cell-node', NODE_FIELDS), ('cell-wall', WALL_FIELDS),
                        ('pharyngeal', BRANCH_FIELDS), ('cell-outgoing', BRANCH_FIELDS)):
        prefix = tag + ','
        path = out / f'{side}-{tag}.csv'
        path.write_text(','.join(fields) + '\n' + ''.join(line.removeprefix(prefix) for line in raw if line.startswith(prefix)))
        rows = read_rows(path)
        if [row['internal_sample'] for row in rows] != samples or any(row.get('node', node) != node for row in rows):
            raise ValueError(f'節点または内部番号の欠測・重複があります ({path.name})')
        outputs[tag] = {int(row['internal_sample']): row for row in rows}
    return outputs


def pressure(row, fs):
    # 既存の直列二枝の収支と同じ加算順で検算する。
    return pressure_update({**row, 'trachea_inflow': row['incoming'], 'glottal_outflow': row['outgoing']}, fs)


def substitutions(candidate, upstream, names, evaluate, target):
    changed = [name for name in names if not same(candidate[name], upstream[name])]
    minimum = []
    for size in range(1, len(changed) + 1):
        for terms in combinations(changed, size):
            restored = evaluate({**candidate, **{term: upstream[term] for term in terms}})
            if same(float(restored), target):
                minimum.append(list(terms))
        if minimum:
            break
    return {'differing_terms': changed, 'minimum_upstream_substitutions': minimum}


def validate(data, trace, samples, fs, upper, *, scale_outgoing=False, multiply_outgoing_history=False):
    for index in samples:
        node, wall, inlet, outlet = (data[tag][index] for tag in ('cell-node', 'cell-wall', 'pharyngeal', 'cell-outgoing'))
        net, _, updated = pressure(node, fs)
        pairs = ((node['old_pressure'], trace[index - 1][PRESSURE]), (node['new_pressure'], trace[index][PRESSURE]),
                 (node['old_pressure'], inlet['right_pressure']), (node['old_pressure'], outlet['left_pressure']),
                 (node['old_pressure'], wall['pressure']), (node['incoming'], inlet['flow']), (node['outgoing'], outlet['flow']),
                 (node['wall_outflow'], wall['flow']), (net, node['net_flow']), (updated, node['new_pressure']))
        if not all(same(a, b) for a, b in pairs):
            return False
        for row, history in ((inlet, True), (outlet, False)):
            expected = replay(row, fs, upper, multiply_history=history or multiply_outgoing_history,
                              scale_inertance=scale_outgoing and not history)
            if any(not same(float(value), row[name]) for name, value in expected.items()):
                return False
        if any(not same(float(value), wall[name]) for name, value in zip(
                ('velocity', 'displacement', 'flow'), wall_values(wall, fs, upper), strict=True)):
            return False
    return True


def event(candidate, upstream, sample, fs):
    a, b = candidate['cell-node'][sample], upstream['cell-node'][sample]
    wall_a, wall_b = candidate['cell-wall'][sample], upstream['cell-wall'][sample]
    return {
        'candidate': a, 'upstream': b,
        **substitutions(a, b, PRESSURE_TERMS, lambda row: pressure(row, fs)[2], b['new_pressure']),
        'wall': {'candidate': wall_a, 'upstream': wall_b, **substitutions(
            wall_a, wall_b, ('surface', 'mass', 'resistance', 'stiffness', 'previous_velocity', 'previous_displacement', 'pressure'),
            lambda row: wall_values(row, fs, False)[2], wall_b['flow'])},
        'outgoing_branch': flow_substitutions(candidate['cell-outgoing'][sample], upstream['cell-outgoing'][sample], fs),
    }


def measure(case, patches, saved, copies, snapshot, out, execute):
    prefix = saved['extended-prefix-case.json']
    build = {'candidate': capture_candidate(patches, prefix, copies, snapshot, out, execute),
             'upstream': capture_upstream(case, prefix, saved, out, execute)}
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera', '--test', 'airway', '--test', 'airway_adversarial'],
            cwd=UPSTREAM, stdout=out / 'upstream-tests.log')
    fs = case['internal_rate_hz']
    samples = list(range(case['first_internal_sample'], case['end_internal_sample_exclusive']))
    candidate, upstream = (read_observations(out, side, samples, case['nodes'][1]) for side in ('candidate', 'upstream'))
    a, b = ({int(row['internal_sample']): row for row in read_rows(path)} for path in (
        out / 'candidate-internal.csv', saved['upstream-pharynx-balance.csv']))
    rate, pcm = wavfile.read(out / 'candidate.wav')
    prior_rate, prior_pcm = wavfile.read(saved['block-128.wav'])
    first = {tag: {field: next((sample for sample in samples if not same(candidate[tag][sample][field], upstream[tag][sample][field])), None)
                   for field in fields} for tag, fields in (
        ('cell-node', NODE_FIELDS[2:]), ('cell-wall', ('pressure', 'surface', 'velocity', 'displacement', 'flow')),
        ('pharyngeal', ('flow',)), ('cell-outgoing', ('flow', 'history_pressure', 'left_pressure', 'right_pressure')))}
    sample = case['expected_first_pressure_difference']
    events = {str(i): event(candidate, upstream, i, fs) for i in (sample - 1, sample)}
    later = case['later_incoming_flow_difference']
    residual = flow_substitutions(candidate['pharyngeal'][later], upstream['pharyngeal'][later], fs)
    first_outgoing = first['cell-outgoing']['flow']
    outgoing_event = None if first_outgoing is None else flow_substitutions(
        candidate['cell-outgoing'][first_outgoing], upstream['cell-outgoing'][first_outgoing], fs)
    checks = {
        'candidate_previous_trace_and_branch': sha256(out / 'candidate-internal.csv') == sha256(saved['candidate-internal.csv'])
            and sha256(out / 'candidate-pharyngeal.csv') == sha256(saved['candidate-pharyngeal.csv']),
        'candidate_previous_pcm': prior_rate == rate == case['output_rate_hz'] and len(pcm) == case['prefix_output_frames']
            and pcm.tobytes() == prior_pcm[:len(pcm)].tobytes(),
        'fixed_upstream_previous_trace_pcm_and_branch': all(sha256(out / name) == sha256(saved[name])
            for name in ('upstream-trace.csv', 'upstream-voice.f32', 'upstream-pharyngeal.csv')),
        'candidate_equations_and_timing': validate(candidate, a, samples, fs, False),
        'upstream_equations_and_timing': validate(upstream, b, samples, fs, True),
        'registered_pressure_difference_and_equal_inputs': first['cell-node']['new_pressure'] == sample
            and all(same(candidate['cell-node'][sample][field], upstream['cell-node'][sample][field])
                    for field in ('old_pressure', 'incoming')),
        'first_difference_explained_by_pressure_inputs': bool(events[str(sample)]['minimum_upstream_substitutions']),
        'later_incoming_difference_from_right_pressure': first['pharyngeal']['flow'] == later
            and ('right_pressure',) in residual['minimum_upstream_substitutions'],
    }
    return {'checks': checks, 'build_sha256': build, 'first_differences': first, 'pressure_events': events,
            'first_outgoing_event': outgoing_event, 'later_incoming_event': residual}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    case = json.loads(CASE.read_text())
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    saved, manifests = {}, {}
    for run, names in (
        ('candidate_run', ('reordered/candidate-internal.csv', 'reordered/candidate-pharyngeal.csv',
                           'reordered/block-128.wav', 'candidate-tracheal-history.patch')),
        ('upstream_run', ('upstream-pharyngeal-entry.patch', 'upstream-trace.csv', 'upstream-voice.f32', 'upstream-pharyngeal.csv')),
        ('upstream_balance_run', ('upstream-pharynx-balance.csv',)),
    ):
        for name in names:
            manifests[run], saved[Path(name).name] = verified_artifact(*case[run], 'artifacts/' + name)
    for name in ('upstream-observation.patch', 'gate-events.txt', 'extended-prefix-case.json'):
        saved[name] = listed_input(manifests['upstream_run'], name)
    patches = [*candidate_patches(manifests['candidate_run']), saved['candidate-tracheal-history.patch']]
    source_run = saved['upstream-observation.patch'].parents[1].name
    manifests['source'] = listed_input(manifests['candidate_run'], f'{source_run}/manifest.json')
    copies, archived, snapshot = source_inputs(manifests['source'])
    loaded = (Path(file).resolve() for module in tuple(sys.modules.values()) if (file := getattr(module, '__file__', None)))
    tools = sorted({path for path in loaded if path.parent == WORKSPACE / 'tools' and path.suffix == '.py'})
    inputs = [CASE, PROBE, WORKSPACE / 'LICENSE-CHIMERA', *archived, *tools, *manifests.values(), *saved.values(), *patches]
    return record_measurement(args.run_id, CASE, inputs, {'case_id': case['id'], 'upstream_revision': revision},
                              lambda out, run: measure(case, patches, saved, copies, snapshot, out, run),
                              command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
