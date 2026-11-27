"""固定発声で肺ポートから気管末端までの最初の圧力差を追う。"""

import argparse
import json
from pathlib import Path
import subprocess
import sys

from measure_fixed_voice_glottal_branch import FIELDS as BRANCH_FIELDS, replay
from measure_fixed_voice_subglottal_balance import (
    NATIVE_PRESSURE, PROBE, REFERENCES, ROOT, UPPER_PRESSURE, capture_native, capture_upstream,
    compare_event, first_difference, pressure_update, read_rows, record_measurement, same,
    source_inputs, verified_artifact,
)
from measure_fixed_voice_tracheal_penultimate import (
    BASE_CASE, NATIVE_EDITS, NATIVE_LOOKUP, NODE_FIELDS, TRACE_TAG, UPPER_EDITS, UPPER_LOOKUP,
    flow_substitutions, pressure_row,
)
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/fixed-voice-tracheal-onset-48000.json'
PATH_TAG = '''        let trace_tag = |branch, glottis| {
            let earlier = match tracheal {
                Some((_, incoming, _)) if branch == incoming => Some("tracheal-in,"),
                Some((_, _, outgoing)) if branch == outgoing => Some("tracheal-out,"),
                _ if branch == glottis => Some(""),
                _ => None,
            };
            let along_path = path.as_ref().and_then(|nodes|
                nodes.iter().position(|&(incoming, _)| incoming == branch));
            (earlier.is_some() || along_path.is_some()).then_some((earlier, along_path))
        };
'''


def path_lookup(terminal, inlet, left, fixed, count):
    return f'''        let path = research.map(|(glottis, _)| {{
            let mut cell = {terminal};
            let mut cells = Vec::new();
            while !{fixed}[cell] {{
                assert!(cells.len() < {count});
                let mut inlets = {inlet};
                let incoming = inlets.next().unwrap();
                assert!(inlets.next().is_none());
                cells.push((incoming, cell));
                cell = {left};
            }}
            cells.reverse();
            cells
        }});
'''


def branch_report(indent):
    previous = '''print!("{tag}{sample}");
for value in values {
    print!(",{value}");
}
println!();'''
    recorded = '''for label in [tag.map(|tag| format!("{tag}{sample}")),
              path_index.map(|cell| format!("path-branch,{cell},{sample}"))].into_iter().flatten() {
    print!("{label}");
    for value in values {
        print!(",{value}");
    }
    println!();
}'''
    return tuple('\n'.join(' ' * indent + line for line in part.splitlines()) for part in (previous, recorded))


def node_report(anchor, node, values):
    return anchor, anchor + f'''
                if let (Some((glottis, sample)), Some(cells)) = (research, &path)
                    && let Some(cell) = cells.iter().position(|&(_, observed_node)| observed_node == {node})
                {{
                    let incoming = cells[cell].0;
                    let outgoing = cells.get(cell + 1).map_or(glottis, |&(branch, _)| branch);
                    let values = [{values}];
                    print!("path-node,{{cell}},{{sample}}");
                    for value in values {{ print!(",{{value:?}}"); }}
                    println!();
                }}'''


def native_edits(count):
    lookup = path_lookup('self.branches[glottis].nodes[0]',
                         'self.branches.iter().enumerate().filter_map(|(i, entry)|\n'
                         '                    (entry.nodes[1] == cell).then_some(i))',
                         'self.branches[incoming].nodes[0]', 'self.fixed_pressure', count)
    return (*NATIVE_EDITS, (NATIVE_LOOKUP, NATIVE_LOOKUP + lookup), (TRACE_TAG, PATH_TAG),
            ("f64, &'static str)>", "f64, (Option<&'static str>, Option<usize>))>"),
            ('if let Some((sample, left, right, noise, tag)) = trace',
             'if let Some((sample, left, right, noise, (tag, path_index))) = trace'), branch_report(12),
            node_report(NATIVE_PRESSURE, 'node', '''old_pressure, self.pressure[node],
                        self.branches[incoming].flow, self.branches[outgoing].flow,
                        self.wall_motion[node].flow_cm3_s, self.volume_source(node), inflow,
                        self.sections[node].volume(), compliance'''))


def upstream_edits(count):
    lookup = path_lookup('self.b_a[glottis]',
                         'self.b_b.iter().enumerate().filter_map(|(i, &right)| (right == cell).then_some(i))',
                         'self.b_a[incoming]', 'self.fixed', count)
    return (*UPPER_EDITS, (UPPER_LOOKUP, UPPER_LOOKUP + lookup), (TRACE_TAG, PATH_TAG),
            ('let Some(tag) = trace_tag(j, watched)', 'let Some((tag, path_index)) = trace_tag(j, watched)'),
            branch_report(20), node_report(UPPER_PRESSURE, 'k', '''old_pressure, self.p[k],
                        self.u[incoming], self.u[outgoing], self.wall_u[k], self.vol_src2[k],
                        self.flow_sum[k], self.vol[k], c'''))


def read_path(out, side, count, samples):
    raw = (out / f'{side}-raw.txt').read_text().splitlines(keepends=True)
    kept = ''.join(line for line in raw if not line.startswith(('path-node,', 'path-branch,')))
    (out / f'{side}-without-path.txt').write_text(kept)
    tables = []
    for tag, fields in (('node', NODE_FIELDS), ('branch', BRANCH_FIELDS)):
        prefix = f'path-{tag},'
        path = out / f'{side}-path-{tag}.csv'
        path.write_text('cell,' + ','.join(fields) + '\n' + ''.join(
            row.removeprefix(prefix) for row in raw if row.startswith(prefix)))
        observed = read_rows(path)
        rows = {(row['cell'], row['internal_sample']): row for row in observed}
        if len(rows) != len(observed) or rows.keys() != {(cell, sample) for cell in range(count) for sample in samples}:
            raise ValueError(f'気管全域のセル番号または内部サンプルに欠測があります ({path.name})')
        tables.append(rows)
    return tables


def clock_matches(path, last, samples, count):
    nodes, branches = path
    for i, sample in enumerate(samples):
        for cell in range(count):
            row = nodes[cell, sample]
            incoming = branches[cell, sample]
            if cell + 1 < count:
                outlet_pressure = branches[cell + 1, sample]['left_pressure']
                outlet_flow = branches[cell + 1, sample]['flow']
            else:
                outlet_pressure, outlet_flow = (last[i][key] for key in ('old_pressure', 'glottal_outflow'))
                if not same(row['new_pressure'], last[i]['new_pressure']):
                    return False
            if not (same(row['old_pressure'], incoming['right_pressure'])
                    and same(row['old_pressure'], outlet_pressure)
                    and same(row['trachea_inflow'], incoming['flow'])
                    and same(row['trachea_outflow'], outlet_flow)):
                return False
            if i and not (same(row['old_pressure'], nodes[cell, sample - 1]['new_pressure'])
                          and same(incoming['previous_flow'], branches[cell, sample - 1]['flow'])):
                return False
    return True


def first_by_cell(a, b, count, samples, column):
    events = []
    for cell in range(count):
        index = first_difference([a[cell, sample][column] for sample in samples],
                                 [b[cell, sample][column] for sample in samples])
        events.append(None if index is None else samples[index])
    return events


def first_events(event_clock, a, b, compare, fs):
    point = min((value for value in event_clock if value is not None), default=None)
    return [{'cell': cell, 'sample': sample, **compare(a[cell, sample], b[cell, sample], fs)}
            for cell, sample in enumerate(event_clock) if sample is not None and sample == point]


def inspect(case, base, refs, archived, copies, snapshot, out, execute):
    cfg = base['measurement']
    count = case['observation']['tracheal_cells']
    hashes = {'candidate': capture_native(refs, copies, snapshot, out, execute, extra_observations=native_edits(count)),
              'upstream': capture_upstream(base, cfg, refs, out, execute, extra_observations=upstream_edits(count))}
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera', '--test', 'lung_port',
             '--test', 'airway_adversarial'], cwd=UPSTREAM, stdout=out / 'upstream-tests.log')
    samples = list(range(cfg['first_internal_sample'], cfg['end_internal_sample_exclusive']))
    fs = cfg['internal_rate_hz']
    native, upper = (read_path(out, label, count, samples) for label in ('candidate', 'upstream'))
    n, u = native[0], upper[0]
    b, v = native[1], upper[1]
    pressure_clock = first_by_cell(n, u, count, samples, 'new_pressure')
    flow_clock = first_by_cell(b, v, count, samples, 'flow')
    boundary_clock = first_by_cell(b, v, 1, samples, 'left_pressure')[0]

    def compare_nodes(left, right, rate):
        return compare_event(pressure_row(left), pressure_row(right), rate)

    pressure_events = first_events(pressure_clock, n, u, compare_nodes, fs)
    flow_events = first_events(flow_clock, b, v, flow_substitutions, fs)
    before_gate = [sample for sample in samples if sample < cfg['gate_open_frame'] * fs // cfg['output_rate_hz']]
    checks = {
        'prior_probes_and_render_reproduced': all(sha256(out / current) == sha256(archived[name]) for current, name in (
            ('candidate-without-path.txt', 'candidate-raw.txt'), ('upstream-without-path.txt', 'upstream-raw.txt'),
            ('candidate-internal.csv', 'candidate-internal.csv'), ('upstream-trace.csv', 'upstream-trace.csv'),
            ('upstream-voice.f32', 'upstream-voice.f32'))),
        'candidate_clock': clock_matches(native, read_rows(archived['candidate-balance.csv']), samples, count),
        'upstream_clock': clock_matches(upper, read_rows(archived['upstream-balance.csv']), samples, count),
        'silence_before_gate': bool(before_gate) and all(
            table[cell, sample][key] == 0.0 for table, key in (
                (n, 'new_pressure'), (u, 'new_pressure'), (b, 'flow'), (v, 'flow'), (b, 'left_pressure'), (v, 'left_pressure'))
            for cell in range(count) for sample in before_gate),
        'independent_pressure_equations': all(
            same(net, row['net_flow']) and same(pressure, row['new_pressure'])
            for row in (*n.values(), *u.values()) for net, _, pressure in (pressure_update(pressure_row(row), fs),)),
        'independent_branch_equations': all(
            all(same(float(value), row[key]) for key, value in replay(row, fs, fixed).items())
            for fixed, table in ((False, b), (True, v)) for row in table.values()),
        'known_distal_pressure_events': pressure_clock[-2:] == [8213, 8216],
        'first_pressure_and_flow_reconstructed': bool(pressure_events and flow_events and all(
            event['minimum_upstream_substitutions'] for event in (*pressure_events, *flow_events))),
    }
    return {'checks': checks, 'build_sha256': hashes, 'first_lung_boundary_pressure_difference': boundary_clock,
            'first_pressure_difference_by_cell': pressure_clock, 'first_inflow_difference_by_cell': flow_clock,
            'earliest_pressure_events': pressure_events, 'earliest_flow_events': flow_events}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    case = json.loads(CASE.read_text())
    base = json.loads(BASE_CASE.read_text())
    if any(base['measurement'][key] != value for section in ('input', 'observation')
           for key, value in case[section].items() if key != 'tracheal_cells'):
        parser.error('先行比較の入力または測定区間が一致しません')
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    refs, manifests, previous = {}, {}, {}
    for group, files in REFERENCES.items():
        refs[group] = {}
        for name in files:
            manifests[group], refs[group][name] = verified_artifact(*base['references'][group], f'artifacts/{name}')
    for name in ('candidate-raw.txt', 'upstream-raw.txt', 'candidate-internal.csv', 'upstream-trace.csv', 'upstream-voice.f32'):
        manifests['penultimate'], previous[name] = verified_artifact(*case['penultimate_run'], f'artifacts/{name}')
    penultimate = WORKSPACE / 'cases/fixed-voice-tracheal-penultimate-48000.json'
    for name in ('candidate-balance.csv', 'upstream-balance.csv'):
        registered = json.loads(penultimate.read_text())['balance_run']
        manifests['balance'], previous[name] = verified_artifact(*registered, f'artifacts/{name}')
    copies, saved, snapshot = source_inputs(manifests['scaled'])
    loaded = (Path(file).resolve() for module in tuple(sys.modules.values())
              if (file := getattr(module, '__file__', None)))
    tools = sorted({path for path in loaded if path.parent == WORKSPACE / 'tools' and path.suffix == '.py'})
    inputs = [CASE, BASE_CASE, penultimate, PROBE, WORKSPACE / 'LICENSE-CHIMERA', *tools, *saved,
              *manifests.values(), *previous.values(), *(path for group in refs.values() for path in group.values())]
    return record_measurement(args.run_id, CASE, inputs, {'case_id': case['id'], 'upstream_revision': revision},
                              lambda out, run: inspect(case, base, refs, previous, copies, snapshot, out, run),
                              command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
