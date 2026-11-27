"""気管の最後から2番目の節点と、その前後の直列枝の圧力・流量を照合する。"""

import argparse
from itertools import combinations
import json
from pathlib import Path
import subprocess
import sys

from measure_fixed_voice_glottal_branch import FIELDS as BRANCH_FIELDS, f64, replay, solve
from measure_fixed_voice_subglottal_balance import (
    NATIVE_PRESSURE, NATIVE_WALL, PROBE, REFERENCES, ROOT, UPPER_PRESSURE, UPPER_WALL,
    capture_native, capture_upstream, compare_event, first_difference, pressure_update, read_rows,
    record_measurement, same, source_inputs, verified_artifact,
)
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/fixed-voice-tracheal-penultimate-48000.json'
BASE_CASE = WORKSPACE / 'cases/fixed-voice-subglottal-balance-48000.json'
NODE_FIELDS = ('internal_sample', 'old_pressure', 'new_pressure', 'trachea_inflow', 'trachea_outflow',
               'wall_outflow', 'volume_source', 'net_flow', 'volume', 'compliance')
TAGS = {'penultimate': NODE_FIELDS, 'tracheal-in': BRANCH_FIELDS, 'tracheal-out': BRANCH_FIELDS}

NATIVE_LOOKUP = '''        let tracheal = research.map(|(glottis, _)| {
            let terminal = self.branches[glottis].nodes[0];
            let series_into = |node| self.branches.iter().position(|branch|
                branch.nodes[1] == node && branch.port.is_none()).unwrap();
            let outgoing = series_into(terminal);
            let middle = self.branches[outgoing].nodes[0];
            assert_eq!(self.neighbors[middle].len(), 2);
            (middle, series_into(middle), outgoing)
        });
'''
UPPER_LOOKUP = '''        let tracheal = research.map(|(glottis, _)| {
            let series_into = |node| self.b_b.iter().zip(&self.b_kind)
                .position(|(&right, &kind)| right == node && kind == KIND_SERIES).unwrap();
            let outgoing = series_into(self.b_a[glottis]);
            let middle = self.b_a[outgoing];
            assert_eq!(self.nbr_start[middle + 1] - self.nbr_start[middle], 2);
            (middle, series_into(middle), outgoing)
        });
'''
TRACE_TAG = '''        let trace_tag = |branch, glottis| match tracheal {
            Some((_, incoming, _)) if branch == incoming => Some("tracheal-in,"),
            Some((_, _, outgoing)) if branch == outgoing => Some("tracheal-out,"),
            _ if branch == glottis => Some(""),
            _ => None,
        };
'''
NATIVE_NODE = NATIVE_PRESSURE + '''
                if let (Some((middle, _, _)), Some((_, sample, incoming, outgoing))) = (tracheal, penultimate)
                    && middle == node
                {
                    let values = [old_pressure, self.pressure[node], incoming, outgoing,
                        self.wall_motion[node].flow_cm3_s, self.volume_source(node), inflow,
                        self.sections[node].volume(), compliance];
                    print!("penultimate,{sample}");
                    for value in values { print!(",{value:?}"); }
                    println!();
                }'''
UPPER_NODE = UPPER_PRESSURE + '''
                if let (Some((middle, _, _)), Some((_, sample, incoming, outgoing))) = (tracheal, penultimate)
                    && middle == k
                {
                    let values = [old_pressure, self.p[k], incoming, outgoing, self.wall_u[k],
                        self.vol_src2[k], self.flow_sum[k], self.vol[k], c];
                    print!("penultimate,{sample}");
                    for value in values { print!(",{value:?}"); }
                    println!();
                }'''
NATIVE_LOOP = '        for (index, (branch, &noise)) in self'
UPPER_LOOP = '        let enable_energy_safe = self.energy_safe;'
NATIVE_EDITS = (
    ('trace: Option<(usize, f64, f64, f64)>', "trace: Option<(usize, f64, f64, f64, &'static str)>"),
    ('if let Some((sample, left, right, noise)) = trace', 'if let Some((sample, left, right, noise, tag)) = trace'),
    ('            print!("{sample}");', '            print!("{tag}{sample}");'),
    (NATIVE_LOOP, NATIVE_LOOKUP + TRACE_TAG + NATIVE_LOOP),
    ('''            let observation = research.filter(|&(watched, _)| watched == index)
                .map(|(_, sample)| (sample, self.pressure[left], self.pressure[right], noise));''',
     '''            let observation = research.and_then(|(watched, sample)| trace_tag(index, watched)
                .map(|tag| (sample, self.pressure[left], self.pressure[right], noise, tag)));'''),
    (NATIVE_WALL, '''        let penultimate = research.zip(tracheal).map(|((_, sample), (middle, incoming, outgoing))|
            (middle, sample, self.branches[incoming].flow, self.branches[outgoing].flow));
''' + NATIVE_WALL),
    (NATIVE_PRESSURE, NATIVE_NODE),
)
UPPER_EDITS = (
    (UPPER_LOOP, UPPER_LOOKUP + TRACE_TAG + UPPER_LOOP),
    ('                if let Some((_, sample)) = research.filter(|&(branch, _)| branch == j) {',
     '''                if let Some((watched, sample)) = research && let Some(tag) = trace_tag(j, watched) {'''),
    ('                    print!("{sample}");', '                    print!("{tag}{sample}");'),
    (UPPER_WALL, '''        let penultimate = research.zip(tracheal).map(|((_, sample), (middle, incoming, outgoing))|
            (middle, sample, self.u[incoming], self.u[outgoing]));
''' + UPPER_WALL),
    (UPPER_PRESSURE, UPPER_NODE),
)


def read_observations(out, side, samples):
    raw = (out / f'{side}-raw.txt').read_text().splitlines(keepends=True)
    tags = {key + ',': fields for key, fields in TAGS.items()}
    original = ''.join(line for line in raw if not line.startswith(tuple(tags)))
    (out / f'{side}-original.txt').write_text(original)
    rows = []
    for prefix, fields in tags.items():
        csv = out / f'{side}-{prefix[:-1]}.csv'
        csv.write_text(','.join(fields) + '\n' + ''.join(
            line.removeprefix(prefix) for line in raw if line.startswith(prefix)))
        data = read_rows(csv)
        if [row['internal_sample'] for row in data] != samples:
            raise ValueError(f'内部点の連続性を確認できません ({csv.name})')
        rows.append(data)
    return rows


def pressure_row(row):
    return {**row, 'glottal_outflow': row['trachea_outflow']}


def same_clock(nodes, incoming, outgoing, terminal):
    return all(same(node['old_pressure'], in_edge['right_pressure'])
               and same(node['old_pressure'], out_edge['left_pressure'])
               and same(node['old_pressure'], last['inlet_old_pressure'])
               and same(node['trachea_inflow'], in_edge['flow'])
               and same(node['trachea_outflow'], out_edge['flow'])
               and same(node['trachea_outflow'], last['trachea_inflow'])
               and (index == 0 or same(node['old_pressure'], nodes[index - 1]['new_pressure']))
               for index, (node, in_edge, out_edge, last) in enumerate(zip(nodes, incoming, outgoing, terminal, strict=True)))


def flow_substitutions(candidate, reference, fs):
    def flow(row):
        pressure = f64(f64(f64(row['left_pressure']) - f64(row['right_pressure'])) + f64(row['noise_pressure']))
        drive = f64(pressure + f64(row['history_pressure']))
        linear = f64(f64(row['inertance_per_step']) + f64(row['resistance']))
        loss = row['forward_loss'] if drive >= 0 else row['reverse_loss']
        return float(solve(linear, drive, f64(loss))['flow'])

    inputs = ('left_pressure', 'right_pressure', 'noise_pressure', 'history_pressure',
              'inertance_per_step', 'resistance', 'forward_loss', 'reverse_loss')
    changed = [key for key in inputs if not same(candidate[key], reference[key])]
    matched = []
    if not same(flow(candidate), candidate['flow']) or not same(flow(reference), reference['flow']):
        raise ValueError('置換前の枝流量を再計算できません')
    for size in range(1, len(changed) + 1):
        for keys in combinations(changed, size):
            if same(flow({**candidate, **{key: reference[key] for key in keys}}), reference['flow']):
                matched.append(keys)
        if matched:
            break
    return {'candidate': candidate, 'upstream': reference, 'different_inputs': changed,
            'minimum_upstream_substitutions': matched,
            'flow_with_upstream_left_pressure': flow({**candidate, 'left_pressure': reference['left_pressure']}),
            'flow_with_upstream_history': flow({**candidate, 'history_pressure': reference['history_pressure']}),
            'flow_with_upstream_step_inertance': flow({**candidate, 'inertance_per_step': reference['inertance_per_step']}),
            'internal_rate_hz': fs}


def differences(left, right, start):
    result = {}
    for key in left[0]:
        position = first_difference([row[key] for row in left], [row[key] for row in right])
        result[key] = None if position is None else start + position
    return result


def measure(case, base, refs, archived, copies, snapshot, out, execute):
    config = base['measurement']
    hashes = {
        'candidate': capture_native(refs, copies, snapshot, out, execute, extra_observations=NATIVE_EDITS),
        'upstream': capture_upstream(base, config, refs, out, execute, extra_observations=UPPER_EDITS),
    }
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera', '--test', 'airway_adversarial',
             '--test', 'engine'], cwd=UPSTREAM, stdout=out / 'upstream-tests.log')
    start, end = (config[key] for key in ('first_internal_sample', 'end_internal_sample_exclusive'))
    samples = list(range(start, end))
    fs = config['internal_rate_hz']
    native, upstream = (read_observations(out, side, samples) for side in ('candidate', 'upstream'))
    labels = list(TAGS)
    observed = {name: differences(left, right, start) for name, left, right in zip(labels, native, upstream, strict=True)}
    node_at = observed['penultimate']['new_pressure']
    outgoing_at = observed['tracheal-out']['flow']
    node_event = None if node_at is None else compare_event(
        pressure_row(native[0][node_at - start]), pressure_row(upstream[0][node_at - start]), fs)
    branch_events = {}
    for name, left, right in zip(labels[1:], native[1:], upstream[1:], strict=True):
        sample = observed[name]['flow']
        if sample is not None:
            branch_events[name] = flow_substitutions(left[sample - start], right[sample - start], fs)
    checks = {
        'saved_observations_unchanged': all(sha256(out / source) == sha256(archived[target]) for source, target in (
            ('candidate-original.txt', 'candidate-raw.txt'), ('upstream-original.txt', 'upstream-raw.txt'),
            ('candidate-internal.csv', 'candidate-internal.csv'), ('upstream-trace.csv', 'upstream-trace.csv'),
            ('upstream-voice.f32', 'upstream-voice.f32'))),
        'candidate_clock': same_clock(*native, read_rows(archived['candidate-balance.csv'])),
        'upstream_clock': same_clock(*upstream, read_rows(archived['upstream-balance.csv'])),
        'independent_pressure_balance': all(
            same(net, row['net_flow']) and same(pressure, row['new_pressure'])
            for row in (*native[0], *upstream[0]) for net, _, pressure in (pressure_update(pressure_row(row), fs),)),
        'independent_branch_equations': all(
            all(same(float(value), row[key]) for key, value in replay(row, fs, upper).items())
            for upper, side in ((False, native), (True, upstream)) for edge in side[1:] for row in edge),
        'pressure_first_diff_at_registered_sample': node_at == case['expected_pressure_sample'],
        'outgoing_flow_first_diff_at_registered_sample': outgoing_at == case['expected_outgoing_sample'],
        'pressure_and_flow_reconstructed': bool(node_event and node_event['minimum_upstream_substitutions']
                                                and all(e['minimum_upstream_substitutions'] for e in branch_events.values())),
    }
    return {'checks': checks, 'build_sha256': hashes, 'first_difference_by_field': observed,
            'pressure_event': node_event, 'first_branch_flow_differences': branch_events}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    case = json.loads(CASE.read_text())
    base = json.loads(BASE_CASE.read_text())
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    refs, manifests = {}, {}
    for group, files in REFERENCES.items():
        refs[group] = {}
        for name in files:
            manifests[group], refs[group][name] = verified_artifact(*base['references'][group], f'artifacts/{name}')
    previous = {}
    for name in ('candidate-raw.txt', 'upstream-raw.txt', 'candidate-internal.csv', 'upstream-trace.csv',
                 'upstream-voice.f32', 'candidate-balance.csv', 'upstream-balance.csv'):
        manifests['balance'], previous[name] = verified_artifact(*case['balance_run'], f'artifacts/{name}')
    copies, archived, snapshot = source_inputs(manifests['scaled'])
    # 実行時に読み込んだ研究用モジュールを保存する。
    loaded = (Path(file).resolve() for module in tuple(sys.modules.values())
              if (file := getattr(module, '__file__', None)))
    tools = sorted({path for path in loaded if path.parent == WORKSPACE / 'tools' and path.suffix == '.py'})
    inputs = [CASE, BASE_CASE, PROBE, WORKSPACE / 'LICENSE-CHIMERA', *tools, *archived, *manifests.values(),
              *previous.values(), *(path for group in refs.values() for path in group.values())]
    details = {'case_id': case['id'], 'upstream_revision': revision}
    return record_measurement(args.run_id, CASE, inputs, details,
                              lambda out, run: measure(case, base, refs, previous, copies, snapshot, out, run),
                              command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
