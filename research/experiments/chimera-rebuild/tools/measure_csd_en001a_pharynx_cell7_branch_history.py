"""CSD咽頭セル7の圧力差を伝える枝の履歴を実測・交換する。"""

import argparse
import os
from pathlib import Path
import subprocess

import numpy as np

import measure_csd_en001a_pharynx_cell7_compliance_pulse as pulse
from tsp_fk61_lip_observation import insert_before


block, source, tsp, radiation = pulse.block, pulse.source, pulse.tsp, pulse.radiation
CASE = radiation.WORKSPACE / 'cases/csd-en001a-pharynx-cell7-branch-history.json'
MODES = pulse.MODES
CONDITIONS = ('native', 'compliance_only', 'left_history', 'right_history', 'both_branches', 'wall_history')
FILES = (*source.FILES, *(f'{name}_{condition}-block.csv' for name in MODES for condition in CONDITIONS))
RESET = 'CHIMERA_CSD_PHARYNX_HISTORY'
BRANCH_HISTORY = ('previous_flow', 'previous_momentum')
WALL_HISTORY = ('previous_velocity', 'previous_displacement')


def rust_value(value):
    return f'f64::from_bits(0x{np.float64(value).view(np.uint64):016x})'


def modify_history(root, fixed, measure, c0, rows):
    network = root / ('crates/chimera/src/airway/network.rs' if fixed else 'crates/vocal-core/src/airway/network.rs')
    reset_at, focus = (measure[name] for name in ('reset_before_sample', 'focus_node'))
    first = measure['reset_branch_left_nodes'][0]
    branch_values = rows['branches'][1:3]
    wall_values = rows['walls']
    if fixed:
        branch = '                let lp = l_prev[j];'
        is_series = 'b_kind[j] == KIND_SERIES && b == a + 1'
        branch_index = 'a'
        assignments = ('u_arr[j]', 'mom[j]')
        wall = '            let v = ((m * inv_t - 0.5 * r) * self.wall_v[k]'
        wall_index, velocity, displacement = 'k', 'self.wall_v[k]', 'self.wall_y[k]'
        pressure = '                self.p[k] += (t / c) * self.flow_sum[k];'
        node, compliance = 'k', 'c'
    else:
        branch = '            let flow = branch.step(self.dt, difference);'
        is_series = 'branch.port.is_none() && right == left + 1'
        branch_index = 'left'
        assignments = ('branch.flow',)
        wall = '                let flow = self.wall_motion[node].step(wall, self.dt, surface, self.pressure[node]);'
        wall_index = 'node'
        velocity, displacement = 'self.wall_motion[node].velocity_cm_s', 'self.wall_motion[node].displacement_cm'
        pressure = '                self.pressure[node] += self.dt / compliance * inflow;'
        node, compliance = 'node', 'compliance'
    insert_before(network, '        let probe_initial =', f'''        let probe_reset = if probe_cells.as_ref().is_some_and(|row| row.0 == {reset_at}) {{
            std::env::var("{RESET}").ok().and_then(|value| value.parse::<u8>().ok()).unwrap_or(0)
        }} else {{
            0
        }};
''')
    branches = []
    for i, row in enumerate(branch_values):
        values = ' '.join(f'{var} = {rust_value(row[key])};'
                          for var, key in zip(assignments, BRANCH_HISTORY[:len(assignments)], strict=True))
        branches.append(f'                    {first+i} if probe_reset & {1 << i} != 0 => {{ {values} }}\n')
    insert_before(network, branch, f'''            if probe_reset != 0 && {is_series} {{
                match {branch_index} {{
{''.join(branches)}                    _ => {{}}
                }}
            }}
''')
    walls = ''.join(
        f'                    {i} => {{ {velocity} = {rust_value(row["previous_velocity"])}; '
        f'{displacement} = {rust_value(row["previous_displacement"])}; }}\n'
        for i, row in zip(measure['reset_wall_nodes'], wall_values, strict=True))
    insert_before(network, wall, f'''            if probe_reset & 4 != 0 {{
                match {wall_index} {{
{walls}                    _ => {{}}
                }}
            }}
''')
    insert_before(network, pressure, f'''                let {compliance} = if {node} == {focus}
                    && probe_cells.as_ref().is_some_and(|row| row.0 == 0)
                    && std::env::var_os("{pulse.MASK}").as_deref() == Some(std::ffi::OsStr::new("1"))
                {{
                    {rust_value(c0)}
                }} else {{
                    {compliance}
                }};
''')


def study_inputs(study):
    rev = study['upstream_revision']
    parent = tsp.open_run(study['pulse'], rev)
    pulse_case, motivation = radiation.saved_case(parent, pulse.CASE)
    baseline = tsp.open_run(pulse_case['block'], rev)
    block_case, definition = radiation.saved_case(baseline, block.CASE)
    centerline, render = (tsp.open_run(block_case[key], rev) for key in ('centerline', 'render'))
    paths = {'spec': tsp.verified_path(render, 'artifacts/candidate-short-128.json'),
             'pulse_case': motivation, 'block_case': definition,
             'pulse_summary': tsp.verified_path(parent, 'summary.json'),
             **{name: tsp.verified_path(parent, f'artifacts/{name}') for name in
                ('pcm-digests.json', 'observations.json', 'network.npz', 'pcm.npz')},
             **{f'{label}_manifest': run[0] / 'manifest.json' for label, run in
                (('pulse', parent), ('block', baseline), ('centerline', centerline), ('render', render))},
             **{name: tsp.verified_path(baseline, f'artifacts/{name}_native-block.csv') for name in MODES}}
    return block_case, centerline, paths


def capture(study, out, execute, block_case, centerline, paths):
    m = study['measurement']
    prior = tsp.read(paths['pulse_summary'])
    config = block_case['measurement'] | {'conditions': dict.fromkeys(CONDITIONS, 0)}
    donors = {name: block.read_events(paths[name], block_case['measurement'], name == 'upstream')[0][m['reset_before_sample']]
              for name in MODES}

    def instrument(root, fixed):
        name = 'upstream' if fixed else 'candidate'
        c0 = prior['sides'][name]['sample_zero']['compliance_only']['used_c']
        return block.patch_block(root, fixed, m, nodes=m['observed_nodes'], modify=lambda root, fixed:
                                 modify_history(root, fixed, m, c0, donors[name]))

    def command(argv, name, condition):
        enable = int(condition != 'native')
        mask = m['reset_masks'][condition]
        return [argv[0], f'{pulse.MASK}={enable}', f'{RESET}={mask}', *argv[1:]], out / f'{name}_{condition}-block.csv'

    source.capture(block_case | {'measurement': config}, paths['spec'], centerline, out, execute,
                   block_observer=instrument, render_observer=command)


def compare_inputs(control, trial, observed, mask):
    branch_keys = tuple(key for key in trial['branches'][0] if key != 'flow')
    wall_keys = tuple(key for key in trial['walls'][0] if key not in ('velocity', 'displacement', 'flow'))
    cell_keys = ('area_cm2', 'volume_cm3', 'raw_cm3_s', 'spill_cm3_s', 'pole2_cm3_s',
                 'initial_inflow_cm3_s', 'old_pressure_dyn_cm2')
    for i, (normal, pulse_row, actual) in enumerate(zip(control['branches'], trial['branches'],
                                                        observed['branches'], strict=True)):
        sources = {key: normal[key] for key in BRANCH_HISTORY} if i in (1, 2) and mask & (1 << (i - 1)) else {}
        expected = pulse_row | sources
        if any(actual[key] != expected[key] for key in branch_keys):
            return False
    for i, (normal, pulse_row, actual) in enumerate(zip(control['walls'], trial['walls'], observed['walls'], strict=True)):
        sources = {key: normal[key] for key in WALL_HISTORY} if i < 3 and mask & 4 else {}
        expected = pulse_row | sources
        if any(actual[key] != expected[key] for key in wall_keys):
            return False
    return observed['compliance'] == trial['compliance'] and all(
        all(actual[key] == expected[key] for key in cell_keys)
        for actual, expected in zip(observed['cells'], trial['cells'], strict=True))


def compare_pressures(a, b, n):
    changed = np.not_equal(a, b)
    hits = np.flatnonzero(np.any(changed, axis=1))
    return {'first': int(hits[0]) if hits.size else None,
            'nodes_by_sample': [np.flatnonzero(row).tolist() for row in changed],
            'at_reset_dyn_cm2': {str(i): float(b[n, i] - a[n, i]) for i in np.flatnonzero(changed[n])}}


def analyze(study, out, paths):
    m = study['measurement']
    rate, n, nodes = (m[key] for key in ('internal_sample_rate_hz', 'reset_before_sample', 'observed_nodes'))
    window = m['comparison_internal_samples'][1]
    proof, snapshots = (tsp.read(out / key) for key in ('pcm-digests.json', 'observations.json'))
    previous, shape, summary = (tsp.read(paths[key]) for key in ('pcm-digests.json', 'observations.json', 'pulse_summary'))
    checks, report = {}, {}
    with (np.load(out / 'pcm.npz', allow_pickle=False) as pcm,
          np.load(paths['pcm.npz'], allow_pickle=False) as archived_pcm,
          np.load(paths['network.npz'], allow_pickle=False) as archived_network):
        for name in MODES:
            fixed = name == 'upstream'
            saved = summary['sides'][name]['sample_zero']
            rows, pressures = {}, {}
            for condition in CONDITIONS:
                key = f'{name}_{condition}'
                path = out / f'{key}-block.csv'
                events, geom = block.read_events(path, m, fixed, nodes=nodes)
                rows[condition] = events
                pressure = pulse.read_pressures(path, window)
                pressures[condition] = pressure
                reset_mask = m['reset_masks'][condition]
                model = (block.simulate(events[:n], rate, fixed) + block.simulate(events[n:], rate, fixed)
                         if reset_mask else block.simulate(events, rate, fixed))
                overrides = {(0, nodes.index(m['focus_node'])): saved['compliance_only']['used_c']}
                checks[f'{key}_geometry_and_local_replay'] = all(geom.values()) and block.validate_replay(
                    events, model, rate, fixed, compliance_overrides=None if condition == 'native' else overrides)
                checks[f'{key}_pcm_and_plan'] = (
                    proof[name][condition]['plan'] == previous[name]['native']['plan']
                    and proof[name][condition]['pcm'] == source.lip.pcm_digest(pcm[key]) and len(pcm[key]) == m['frames'])
                if condition in ('native', 'compliance_only'):
                    checks[f'{key}_prior_observations_match'] = (
                        snapshots[name][condition] == shape[name][condition]
                        and proof[name][condition] == previous[name][condition]
                        and source.lip.bit_equal(pcm[key], archived_pcm[key])
                        and pulse.output.prefix.load.same_bits(pressure, archived_network[f'{key}_pressure'][:window]))
                else:
                    checks[f'{key}_prefix_and_only_selected_histories_replaced'] = (
                        snapshots[name][condition]['0'] == shape[name]['compliance_only']['0']
                        and rows[condition][:n] == rows['compliance_only'][:n]
                        and np.array_equal(pressure[:n], pressures['compliance_only'][:n])
                        and compare_inputs(rows['native'][n], rows['compliance_only'][n], events[n], reset_mask))
            a, b = (rows[condition][n - 1]['branches'][1:3] for condition in ('native', 'compliance_only'))
            pressure2_equal = bool(np.array_equal(pressures['native'][n-1], pressures['compliance_only'][n-1]))
            flows = [trial['flow'] - normal['flow'] for normal, trial in zip(a, b, strict=True)]
            comparisons = {key: {
                'pressure': compare_pressures(pressures['native'], pressures[key], n),
                'pcm': pulse.differences(pcm[f'{name}_native'], pcm[f'{name}_{key}']),
                'pcm_bits_equal': bool(source.lip.bit_equal(pcm[f'{name}_native'], pcm[f'{name}_{key}'])),
            } for key in CONDITIONS[1:]}
            at_reset = {condition: {str(node): comparisons[condition]['pressure']['at_reset_dyn_cm2'].get(str(node), 0.0)
                                    for node in nodes} for condition in CONDITIONS[1:]}
            selected = tuple(map(str, m['reset_wall_nodes']))
            both_restore = all(at_reset['both_branches'][node] == 0.0 for node in selected)
            wall_restore = all(at_reset['wall_history'][node] == 0.0 for node in selected)
            report[name] = {
                'same_pressure_before_reset': pressure2_equal, 'pulse_branch_flows_before_reset_cm3_s': flows,
                'pressure_at_reset_dyn_cm2': at_reset, 'comparisons': comparisons,
                'hypotheses': {
                    'expected_flows_measured': pressure2_equal and flows == m['expected_branch_flow_difference_cm3_s'][name],
                    'both_histories_remove_local_pressure_return': both_restore,
                    'wall_history_removes_local_pressure_return': wall_restore,
                    'both_histories_reduce_pcm_difference': (
                        comparisons['both_branches']['pcm']['unequal'] < comparisons['compliance_only']['pcm']['unequal']),
                }}
    return {'checks': checks, 'sides': report}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    ws, upper = radiation.WORKSPACE, radiation.UPSTREAM
    study = tsp.read(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=upper, text=True).strip()
    if revision != study['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=upper):
        parser.error('変更のない固定上流版が必要です')
    if os.environ.get('CHIMERA_RUN_STORAGE') != 'rtl9210b':
        parser.error('試験ビルドにCHIMERA_RUN_STORAGE=rtl9210bを指定してください')
    block_case, centerline, paths = study_inputs(study)
    inputs = [CASE, Path(__file__).resolve(), *paths.values(),
              *(ws.parents[2] / item['path'] for item in tsp.read(paths['block_manifest'])['inputs']),
              Path(pulse.__file__), Path(pulse.output.full.__file__)]

    def measure(out, execute):
        capture(study, out, execute, block_case, centerline, paths)
        return analyze(study, out, paths)

    details = {'case_id': study['id'], 'case_revision': study['revision'], 'upstream_revision': revision}
    return radiation.record_measurement(args.run_id, CASE, list(dict.fromkeys(inputs)), details, measure,
                                        command=None, input_root=ws.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
