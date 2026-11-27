"""口腔6節点を連成し、枝41→42の流量差を上流へさかのぼる。"""

import argparse
import os
from pathlib import Path
import subprocess

import numpy as np

import measure_tsp_fk61_control5632_mouth_flow as two_cell


oral, load, terminal, radiation, tsp = two_cell.oral, two_cell.load, two_cell.terminal, two_cell.radiation, two_cell.tsp
lip, pcm, drive = oral.lip, oral.pcm, oral.drive
CASE = radiation.WORKSPACE / 'cases/tsp-fk61-control5632-upstream-drive.json'
MODES, SAVED_FILES = oral.MODES, oral.SAVED_FILES
GROUPS = ('initial_state', 'upstream_boundary', 'inner_volume', 'terminal_volume', 'coefficients')
BRANCH_COEFFICIENTS = (*two_cell.BRANCH_COEFFICIENTS, 'noise_pressure')
TRAJECTORY_FIELDS = ('flow40_41', 'flow41_42', 'flow42_43', 'pressure40', 'pressure41', 'pressure42', 'lip_flow')


def replay(data, measure, fixed, *, reference=None, groups=(), volume_nodes=(), imposed_edge=None):
    first, stop = measure['local_internal_samples']
    rate = measure['internal_sample_rate_hz']
    nodes = measure['nodes'][1:]
    late_incoming = measure.get('late_incoming_nodes', ())
    edges = list(zip(measure['nodes'][:-1], nodes, strict=True))
    outside = edges[0]
    reference = data if reference is None else reference
    history = reference if 'initial_state' in groups else data
    passive = reference if 'coefficients' in groups else data
    boundary = reference if 'upstream_boundary' in groups else data
    exchanged_sources = set(volume_nodes)
    if 'inner_volume' in groups:
        exchanged_sources.update(measure['inner_nodes'])
    if 'terminal_volume' in groups:
        exchanged_sources.update(measure['terminal_nodes'])
    pressure = {node: history['cells'][first, node]['old_pressure_dyn_cm2'] for node in nodes}
    wall_history = {
        node: {key: history['wall'][first, node][f'previous_{key}'] for key in ('velocity', 'displacement')}
        for node in nodes
    }
    branch_history = {
        edge: {key: history['branch'][first, *edge][key] for key in ('previous_inertance', *drive.PRIOR)}
        for edge in edges[1:]
    }
    old_load = history['loads'][first - 1]
    lip_u, lip_l = old_load['new_inertance_flow_cm3_s'], old_load['inertance_g_cm4']
    results = {}
    for n in range(first, stop):
        flow = {outside: boundary['branch'][n, *outside]['flow']}
        for edge in edges[1:]:
            a, b = edge
            row = data['branch'][n, a, b] | branch_history[edge]
            row = two_cell.replaced_fields(row, passive['branch'][n, a, b], BRANCH_COEFFICIENTS)
            row.update(left_pressure=pressure[a], right_pressure=pressure[b])
            u = (reference['branch'][n, a, b]['flow'] if edge == imposed_edge
                 else terminal.branch_flow(row, rate, fixed))
            flow[edge] = u
            l = row['inertance']
            branch_history[edge] = {'previous_inertance': l, 'previous_flow': u, 'previous_momentum': l * u}
        walls, pressures, net = {}, {}, {}
        for node in nodes:
            row = passive['wall'][n, node] | {'pressure': pressure[node]}
            row.update({f'previous_{key}': value for key, value in wall_history[node].items()})
            walls[node] = terminal.step_wall(row, rate, fixed)
            wall_history[node] = {key: walls[node][key] for key in ('velocity', 'displacement')}
            source = (reference if node in exchanged_sources else data)['cells'][n, node]['initial_inflow_cm3_s']
            if node == nodes[-1]:
                net[node] = (source + flow[node - 1, node]) - walls[node]['flow']
            else:
                # 管の接続枝を後から登録した節点では、左からの流入も後で加える。
                parts = {'initial': source, 'incoming': flow[node - 1, node], 'outgoing': flow[node, node + 1],
                         'wall': walls[node]['flow'], 'compliance': passive['compliance'][n, node]['value'],
                         'old_pressure': pressure[node]}
                _, net[node], pressures[node] = oral.predict_node(parts, rate, incoming_last=node in late_incoming)
        mouth = nodes[-1]
        load_row = lip.load_inputs(passive['loads'][n])
        l = load_row['inertance']
        if 0 < lip_l < l:
            lip_u *= lip_l / l
        lip_l = l
        load_row.update(old_pressure=pressure[mouth], old_inertance_flow=lip_u, inflow=net[mouth])
        solved = radiation.solve_lip(load_row, rate, fixed)
        lip_u, pressures[mouth] = solved['new_inertance_flow'], solved['new_pressure']
        pressure = pressures
        results[n] = {'flow': flow, 'pressure': pressures, 'walls': walls, 'net': net,
                      'lip_flow': solved['lip_flow'], 'lip_inertance_flow': lip_u}
    return results


def native_mismatches(data, trajectory):
    failures = []
    for n, row in trajectory.items():
        if any(value != data['branch'][n, *edge]['flow'] for edge, value in row['flow'].items()):
            failures.append([n, 'branch'])
        if any(value != data['cells'][n, node]['new_pressure_dyn_cm2'] for node, value in row['pressure'].items()):
            failures.append([n, 'pressure'])
        if any(value != data['cells'][n, node]['inflow_cm3_s'] for node, value in row['net'].items()):
            failures.append([n, 'inflow'])
        if any(any(value != data['wall'][n, node][key] for key, value in state.items())
               for node, state in row['walls'].items()):
            failures.append([n, 'wall'])
        load_row = data['loads'][n]
        if (row['lip_flow'] != load_row['lip_flow_cm3_s']
                or row['lip_inertance_flow'] != load_row['new_inertance_flow_cm3_s']):
            failures.append([n, 'mouth'])
    return failures


def summary_and_array(trajectory, native, measure, prefix, config, gain, coefficients):
    start, stop = measure['witness_interval']
    lip_flow = {n: row['lip_flow'] for n, row in trajectory.items()}
    checkpoints = {}
    for n in measure['comparison_samples']:
        row, trial = trajectory[n], native[n]
        checkpoints[str(n)] = {
            'branch40_shift_cm3_s': row['flow'][40, 41] - trial['flow'][40, 41],
            'branch41_shift_cm3_s': row['flow'][41, 42] - trial['flow'][41, 42],
            'pressure41_shift_dyn_cm2': row['pressure'][41] - trial['pressure'][41],
            'mouth_shift_cm3_s': row['lip_flow'] - trial['lip_flow'],
        }
    result = {
        'checkpoints': checkpoints,
        'pcm_two_samples': load.output_replay(prefix, {n: lip_flow[n] for n in range(start, stop)},
                                              measure, config, gain, coefficients),
        'pcm_full_interval': load.output_replay(prefix, lip_flow, measure, config, gain, coefficients),
    }
    array = np.asarray([(row['flow'][40, 41], row['flow'][41, 42], row['flow'][42, 43],
                         row['pressure'][40], row['pressure'][41], row['pressure'][42], row['lip_flow'])
                        for row in trajectory.values()])
    return result, array


def measured_checkpoints(data, measure):
    upper, trial = (data[mode] for mode in ('upstream', 'trial'))
    points = {}
    for n in measure['comparison_samples']:
        points[str(n)] = {
            'branches_cm3_s': {f'{node}->{node+1}': upper['branch'][n, node, node+1]['flow']
                               - trial['branch'][n, node, node+1]['flow'] for node in measure['nodes'][:-1]},
            'volume_sources_cm3_s': {str(j): upper['cells'][n, j]['initial_inflow_cm3_s']
                                     - trial['cells'][n, j]['initial_inflow_cm3_s'] for j in measure['nodes'][1:]},
            'prior_pressure_dyn_cm2': {str(j): upper['cells'][n, j]['old_pressure_dyn_cm2']
                                       - trial['cells'][n, j]['old_pressure_dyn_cm2'] for j in measure['nodes'][1:]},
        }
    return points


def analyze(study, out, earlier, previous, config, gain, coefficients, proof):
    m = study['measurement']
    first, stop = m['local_internal_samples']
    rate = m['internal_sample_rate_hz']
    witness = str(m['witness_interval'][0])
    data = {mode: oral.read_capture(out, mode, m) for mode in MODES}
    upper, trial = (data[mode] for mode in ('upstream','trial'))
    with np.load(out / 'prefix.npz', allow_pickle=False) as current, np.load(earlier / 'prefix.npz', allow_pickle=False) as prior:
        prefix_equal = current.files == prior.files and all(load.same_bits(current[key], prior[key]) for key in current.files)
        prefix = dict(prior)
    overlap = {mode: oral.prior_overlap(earlier, mode, m, data[mode]) for mode in MODES}
    local = {mode: oral.local_replay(data[mode], m, mode == 'upstream') for mode in MODES}
    native = {mode: replay(data[mode], m, mode == 'upstream') for mode in ('upstream','trial')}
    discrepancies = {mode: native_mismatches(data[mode], trajectory) for mode, trajectory in native.items()}
    trajectories, conditions, separate_sources = {}, [], {}
    for group in load.subsets(GROUPS):
        trajectory = replay(trial, m, False, reference=upper, groups=group)
        report, array = summary_and_array(trajectory, native['trial'], m, prefix, config, gain, coefficients)
        trajectories['+'.join(group) or 'baseline'] = array
        conditions.append({'groups': list(group), **report})
    for node in m['nodes'][1:]:
        trajectory = replay(trial, m, False, reference=upper, volume_nodes=(node,))
        report, array = summary_and_array(trajectory, native['trial'], m, prefix, config, gain, coefficients)
        separate_sources[str(node)] = report
        trajectories[f'volume_{node}'] = array
    forced = replay(trial, m, False, reference=upper, imposed_edge=(41,42))
    forced_report, forced_array = summary_and_array(forced, native['trial'], m, prefix, config, gain, coefficients)
    trajectories['direct_branch41'] = forced_array
    matches = {name: [row['groups'] for row in conditions if row[name]['first_difference_through_focus'] is None]
               for name in ('pcm_two_samples', 'pcm_full_interval')}
    effects = {row['groups'][0]: abs(row['checkpoints'][witness]['branch41_shift_cm3_s'])
               for row in conditions if len(row['groups']) == 1}
    forcing = next(row for row in previous['conditions'] if row['groups'] == ['boundary_flow'])
    controls = {
        'old_two_node_baseline': all(conditions[0][name] == previous['conditions'][0][name]
                                     for name in ('pcm_two_samples', 'pcm_full_interval')),
        'old_two_node_with_branch41': all(forced_report[name] == forcing[name]
                                         for name in ('pcm_two_samples', 'pcm_full_interval')),
    }
    hypotheses = {
        'inner_volume_sources_exceed_terminal_sources_for_edge41': effects['inner_volume'] > effects['terminal_volume'],
        'upstream_boundary_is_largest_single_group': effects['upstream_boundary'] > max(
            value for key, value in effects.items() if key != 'upstream_boundary'),
        'initial_state_is_smaller_than_later_forcing': effects['initial_state'] < max(
            value for key, value in effects.items() if key != 'initial_state'),
        'post_boundary_inputs_recover_pcm': any(group and 'initial_state' not in group for group in matches['pcm_two_samples']),
    }
    point_checks = {str(n): {f'{j}->{j+1}': drive.point_exchanges(
        upper['branch'][n,j,j+1], trial['branch'][n,j,j+1], rate)
        for j in (40,41)} for n in m['point_samples']}
    checks = {
        'ordinary_cli_observation_and_archive_match': proof == tsp.read(earlier / 'pcm-digests.json')
            and all(row['bit_equal'] and row['ordinary']['frames'] == m['frames'] for row in proof.values()),
        'prefix_and_shared_probes_match': prefix_equal and all(all(values.values()) for values in overlap.values()),
        'native_volume_branches_walls_and_coupled_nodes_replayed': (
            not any(any(row.values()) for row in local.values()) and not any(discrepancies.values())),
        'old_two_node_counterfactual_controls_replayed': all(controls.values()),
        'registered_combinations_and_native_baseline_replayed': (
            len(conditions) == 2 ** len(GROUPS) and len(separate_sources) == len(m['nodes']) - 1
            and conditions[0]['checkpoints'][witness]['branch41_shift_cm3_s'] == 0.0
            and all(len(table) == 2 ** len(drive.POINT_GROUPS) for sample in point_checks.values() for table in sample.values())),
    }
    return {'checks': checks, 'hypotheses': hypotheses,
            'local_errors': local, 'native_mismatches': discrepancies, 'overlap': overlap, 'controls': controls,
            'native_checkpoints': measured_checkpoints(data, m), 'conditions': conditions,
            'separate_sources': separate_sources, 'point_exchanges': point_checks,
            'direct_branch41': forced_report, 'matching_groups': matches}, (
            trajectories | {'internal_sample': np.arange(first, stop), 'columns': np.asarray(TRAJECTORY_FIELDS)})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    ws, upper = radiation.WORKSPACE, radiation.UPSTREAM
    study = tsp.read(CASE)
    revision = subprocess.check_output(['git','rev-parse','HEAD'], cwd=upper, text=True).strip()
    if revision != study['upstream_revision'] or subprocess.check_output(['git','status','--porcelain'], cwd=upper):
        parser.error('変更のない固定上流版が必要です')
    if os.environ.get('CHIMERA_RUN_STORAGE') != 'rtl9210b':
        parser.error('試験ビルドにCHIMERA_RUN_STORAGE=rtl9210bを指定してください')
    matched, bernstein, earlier, output, previous = (tsp.open_run(study[key], revision) for key in
                                                     ('matched','bernstein','branch_first','coefficients','previous_focus'))
    uid = study['measurement']['recording_id']
    spec = tsp.verified_path(matched, f'artifacts/{uid}/matched-case.json')
    config, config_path = radiation.saved_case(matched, lip.CONFIG)
    reference_pcm = tsp.verified_path(matched, 'artifacts/matched-pcm.npz')
    trial_pcm = tsp.verified_path(bernstein, 'artifacts/render.npz')
    coefficients = tsp.verified_path(output, 'artifacts/coefficients.json')
    prior = tsp.verified_path(previous, 'summary.json')
    retained = [tsp.verified_path(earlier, f'artifacts/{name}') for name in SAVED_FILES]
    inputs = [CASE, Path(__file__).resolve(), Path(two_cell.__file__), Path(oral.__file__), Path(drive.__file__),
              Path(load.__file__), Path(terminal.__file__), Path(terminal.observer.__file__), Path(radiation.__file__),
              config_path, spec, reference_pcm, trial_pcm, coefficients, prior, *retained,
              *(row[0] / 'manifest.json' for row in (matched, bernstein, earlier, output, previous)),
              *radiation.candidate_sources(), lip.EMBEDDED_DICTIONARY, lip.DICT, lip.LOCAL, lip.PROBE,
              lip.TRACE_TOOL, lip.OUTPUT_PATCH, lip.SOURCE_PATCH, lip.observer.LOCAL_PATCH, lip.observer.UPPER_PATCH,
              ws / 'data/cmudict.txt.gz', ws / 'crates/vocal-core/tests/geometry_ramp.rs',
              *(ws / 'tools' / name for name in ('tsp_fk61_lip_front_observation.py','tsp_fk61_lip_observation.py',
                 'tsp_fk61_lip_front_radiation_observation.py','tsp_fk61_ray43_observation.py',
                 'tsp_fk61_node_volume_observation.py','tsp_fk61_lower_lip_bernstein_observation.py',
                 'measure_tsp_fk61_lip_onset.py','measure_tsp_fk61_node42_volume_source.py',
                 'measure_tsp_fk61_pcm_first_difference.py','measure_fixed_voice_glottal_branch.py',
                 'measure_fixed_voice_radiation_balance.py','measure_fixed_voice_release_lip_load.py',
                 'measure_tsp_fine_variation.py','measure_uniform_tube.py')),
              *(upper / name for name in ('Cargo.lock','crates/chimera/src/airway/network.rs',
                 'crates/chimera/src/voice/human_voice.rs','crates/chimera/tests/airway.rs',
                 'crates/chimera/tests/airway_adversarial.rs'))]

    def measure(out, execute):
        archive = pcm.archived_pcm(reference_pcm, uid)
        with np.load(trial_pcm, allow_pickle=False) as source:
            archive['trial'] = source['pcm']
        proof = oral.capture(study, spec, config, archive, out, execute)
        gain = tsp.read(spec)['speech_voice']['voice']['output_gain']
        report, arrays = analyze(study, out, earlier[0] / 'artifacts', tsp.read(prior), config, gain,
                                 tsp.read(coefficients), proof)
        np.savez_compressed(out / 'trajectories.npz', **arrays)
        return report

    details = {'case_id': study['id'], 'case_revision': study['revision'], 'upstream_revision': revision}
    return radiation.record_measurement(args.run_id, CASE, inputs, details, measure, command=None, input_root=ws.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
