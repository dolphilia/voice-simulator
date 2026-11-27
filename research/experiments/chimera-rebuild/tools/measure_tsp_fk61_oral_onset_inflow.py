"""発声開始時に節点40から41へ伝わる流量と体積源を照合する。"""

import argparse
from fractions import Fraction
from functools import partial
import json
import os
from pathlib import Path
import subprocess

import numpy as np

import measure_tsp_fk61_branch_first_difference as first_diff
from measure_tsp_fk61_node42_volume_source import poles


drive, load, terminal = first_diff.drive, first_diff.load, first_diff.terminal
radiation, tsp, lip, pcm = first_diff.radiation, first_diff.tsp, first_diff.lip, first_diff.pcm
CASE = radiation.WORKSPACE / 'cases/tsp-fk61-oral-onset-inflow.json'
MODES, SAVED_FILES = first_diff.MODES, first_diff.SAVED_FILES
NODE_GROUPS = ('initial', 'incoming', 'outgoing', 'wall', 'compliance', 'old_pressure')
BRANCH = (40, 41)


def read_capture(out, mode, measure):
    first, stop = measure['comparison_internal_samples']
    nodes = tuple(measure['nodes'])
    pressure_nodes = measure['pressure_nodes']
    tags = {'branch': tuple(zip(nodes[:-1], nodes[1:], strict=True)),
            'wall': tuple((node,) for node in nodes[1:]),
            'compliance': tuple((node,) for node in pressure_nodes)}
    traces = {tag: terminal.read_records(out / f'{mode}-{tag}.csv', terminal.observer.FIELDS[tag],
                                         len(selection[0]) + 1,
                                         {(n, *edge) for n in range(first, stop) for edge in selection})
              for tag, selection in tags.items()}
    grid = radiation.read_nodes(out / f'{mode}-nodes.csv', first, stop, cell_indices=nodes)
    cells = {(n, node): {key: float(values[i, j]) for key, values in grid.items()}
             for i, n in enumerate(range(first, stop)) for j, node in enumerate(nodes)}
    loads = dict(zip(range(first, stop), lip.read_trace(out / f'{mode}-lip.f64le', stop - first), strict=True))
    return {'cells': cells, 'grid': grid, 'loads': loads, **traces}


def inputs_to_node(data, n, node):
    cell = data['cells'][n, node]
    return {
        'initial': cell['initial_inflow_cm3_s'], 'incoming': data['branch'][n, node - 1, node]['flow'],
        'outgoing': data['branch'][n, node, node + 1]['flow'], 'wall': data['wall'][n, node]['flow'],
        'compliance': data['compliance'][n, node]['value'], 'old_pressure': cell['old_pressure_dyn_cm2'],
    }


def predict_node(row, rate, *, incoming_last=False):
    if incoming_last:
        before_wall = (row['initial'] - row['outgoing']) + row['incoming']
    else:
        before_wall = (row['initial'] + row['incoming']) - row['outgoing']
    inflow = before_wall - row['wall']
    pressure = row['old_pressure'] + (1 / rate) / row['compliance'] * inflow
    return before_wall, inflow, pressure


def raw_from_volumes(cell, rate, fixed):
    difference = cell['old_volume_cm3'] - cell['volume_cm3']
    return difference * rate if fixed else difference / (1 / rate)


def volume_replay(data, n, node, rate, fixed, *, raw=None):
    previous, cell = (data['cells'][step, node] for step in (n - 1, n))
    parameters = data['loads'][n]
    new_volume = max(parameters['area_floor'], cell['area_cm2']) * cell['length_cm']
    unfiltered = raw_from_volumes(cell, rate, fixed) if raw is None else raw
    first, second = poles(previous['pole1_cm3_s'], previous['pole2_cm3_s'],
                          parameters['pole_coefficient'], unfiltered)
    return {'volume_cm3': new_volume, 'spill_cm3_s': unfiltered, 'pole1_cm3_s': first,
            'pole2_cm3_s': second, 'initial_inflow_cm3_s': second}


def local_replay(data, measure, fixed, *, raw_overrides=None):
    rate = measure['internal_sample_rate_hz']
    begin, stop = measure['comparison_internal_samples']
    nodes = measure['pressure_nodes']
    errors = {'branch': [], 'wall': [], 'node': [], 'volume': [], 'mouth': []}
    for key, row in data['branch'].items():
        if terminal.branch_flow(row, rate, fixed) != row['flow']:
            errors['branch'].append(key)
    for key, row in data['wall'].items():
        if terminal.step_wall(row, rate, fixed) != {field: row[field] for field in terminal.WALL_STATES}:
            errors['wall'].append(key)
    for n in range(begin, stop):
        load_row = data['loads'][n]
        if not lip.solve_matches(load_row, rate, fixed):
            errors['mouth'].append(n)
        for node in nodes:
            cell = data['cells'][n, node]
            row = inputs_to_node(data, n, node)
            fields = ('before_wall_cm3_s', 'inflow_cm3_s', 'new_pressure_dyn_cm2')
            if (row['compliance'] != cell['volume_cm3'] / terminal.BULK_MODULUS
                    or predict_node(row, rate, incoming_last=node in measure.get('late_incoming_nodes', ()))
                    != tuple(cell[key] for key in fields)):
                errors['node'].append((n, node))
            if n > begin:
                raw = None if raw_overrides is None else raw_overrides.get((n, node))
                expected = volume_replay(data, n, node, rate, fixed, raw=raw)
                if (not cell['geometry_enabled'] or cell['minimum_cm2'] < load_row['squeeze_threshold']
                        or any(value != cell[key] for key, value in expected.items())):
                    errors['volume'].append((n, node))
    return errors


def prior_overlap(out, mode, measure, data):
    first, stop = measure['comparison_internal_samples']
    previous = radiation.read_nodes(out / f'{mode}-nodes.csv', 0, 5880, cell_indices=(41, 42, 43))
    subset = [measure['nodes'].index(node) for node in (41, 42, 43)]
    equals = {'cells': all(load.same_bits(data['grid'][field][:, subset], values[first:stop])
                           for field, values in previous.items())}
    tags = {'branch': ((41, 42), (42, 43)), 'wall': ((42,), (43,)), 'compliance': ((42,),)}
    for tag, selection in tags.items():
        expected = {(n, *edge) for n in range(first, stop) for edge in selection}
        earlier = terminal.read_records(out / f'{mode}-{tag}.csv', terminal.observer.FIELDS[tag],
                                        len(selection[0]) + 1, expected, sample_window=(first, stop))
        equals[tag] = all(json.dumps(data[tag][key]) == json.dumps(row) for key, row in earlier.items())
    previous_loads = lip.read_trace(out / f'{mode}-lip.f64le', 5880)
    equals['mouth'] = all(json.dumps(data['loads'][n]) == json.dumps(previous_loads[n]) for n in range(first, stop))
    return equals


def node_exchanges(upper, trial, rate):
    observed = predict_node(upper, rate)[2]
    baseline = predict_node(trial, rate)[2]
    results = []
    for group in load.subsets(NODE_GROUPS):
        mixed = trial | {key: upper[key] for key in group}
        before_wall, inflow, pressure = predict_node(mixed, rate)
        results.append({'groups': list(group), 'before_wall_cm3_s': before_wall, 'net_inflow_cm3_s': inflow,
                        'new_pressure_dyn_cm2': pressure, 'shift_from_trial_dyn_cm2': pressure - baseline,
                        'residual_vs_upstream_dyn_cm2': pressure - observed})
    return results


def exact_raw(data, n, node, rate):
    parameters = data['loads'][n]
    before, after = (data['cells'][step, node] for step in (n - 1, n))
    volumes = [Fraction(max(parameters['area_floor'], row['area_cm2'])) * Fraction(row['length_cm'])
               for row in (before, after)]
    return (volumes[0] - volumes[1]) * rate


def analyze(study, captured, prior, proof):
    measure = study['measurement']
    rate = measure['internal_sample_rate_hz']
    n = measure['focus_sample']
    onset, follow = measure['volume_sample'], measure['followup_sample']
    data = {mode: read_capture(captured, mode, measure) for mode in MODES}
    with np.load(captured / 'prefix.npz', allow_pickle=False) as current, np.load(prior / 'prefix.npz', allow_pickle=False) as previous:
        same_prefix = current.files == previous.files and all(load.same_bits(current[key], previous[key])
                                                               for key in current.files)
    overlap = {mode: prior_overlap(prior, mode, measure, data[mode]) for mode in MODES}
    errors = {mode: local_replay(row, measure, mode == 'upstream') for mode, row in data.items()}
    # 節点40の体積源を出発点にして、節点41に届くまでの更新を観測する。
    upper, trial = (data[mode] for mode in ('upstream', 'trial'))
    cells = {f'{step}:{node}': {mode: data[mode]['cells'][step, node] for mode in ('upstream','trial')}
             for step in (onset, n, follow) for node in measure['pressure_nodes']}
    edge40 = {mode: data[mode]['branch'][n, *BRANCH] for mode in ('upstream', 'trial')}
    edges = drive.point_exchanges(edge40['upstream'], edge40['trial'], rate)
    pressure_tables = {f'{step}:{node}': node_exchanges(inputs_to_node(upper, step, node),
                                                       inputs_to_node(trial, step, node), rate)
                       for step, node in ((onset, 40), (n, 41), (follow, 42))}
    raw = {mode: raw_from_volumes(data[mode]['cells'][onset, 40], rate, mode == 'upstream')
           for mode in ('upstream', 'trial')}
    exact = {mode: exact_raw(data[mode], onset, 40, rate) for mode in ('upstream','trial')}
    flow_delta = {key: inputs_to_node(upper, n, 41)[key] - inputs_to_node(trial, n, 41)[key]
                  for key in NODE_GROUPS}
    effects = {tuple(row['groups']): abs(row['shift_from_trial_cm3_s']) for row in edges}
    origin = {tuple(row['groups']): abs(row['shift_from_trial_dyn_cm2']) for row in pressure_tables[f'{onset}:40']}
    hypotheses = {
        'incoming_branch_dominates_node41_net_at_focus': abs(flow_delta['incoming']) > max(
            abs(flow_delta[key]) for key in ('initial', 'outgoing', 'wall')),
        'pressure_dominates_edge40_flow_at_focus': effects['pressure',] > effects['inertance','losses'],
        'node40_volume_source_dominates_pressure_at_onset': origin['initial',] > origin['compliance',],
        'rounded_product_dominates_node40_raw_flow_difference': (
            abs(float(exact['upstream'] - exact['trial'])) < abs(raw['upstream'] - raw['trial'])),
    }
    previous_proof = tsp.read(prior / 'pcm-digests.json')
    checks = {
        'ordinary_cli_probe_and_saved_pcm_match': proof == previous_proof and all(
            row['bit_equal'] and row['ordinary']['frames'] == measure['frames']
            and row['ordinary'] == row['probe'] == row['archived'] for row in proof.values()),
        'prefix_and_shared_onset_capture_match': same_prefix and all(all(values.values()) for values in overlap.values()),
        'branches_walls_interior_pressure_and_mouth_replayed': not any(
            rows[stage] for rows in errors.values() for stage in ('branch', 'wall', 'node', 'mouth')),
        'volume_sources_and_two_filter_poles_replayed': not any(rows['volume'] for rows in errors.values()),
        'interventions_include_native_controls': (
            len(edges) == 2 ** len(drive.POINT_GROUPS) and edges[0]['flow_cm3_s'] == edge40['trial']['flow']
            and all(len(table) == 2 ** len(NODE_GROUPS) and table[0]['new_pressure_dyn_cm2']
                    == cells[name]['trial']['new_pressure_dyn_cm2'] for name, table in pressure_tables.items())),
    }
    return {'checks': checks, 'hypotheses': hypotheses, 'errors': errors, 'overlap': overlap,
            'cells': cells, 'branch40_at_focus': edge40, 'branch40_swaps': edges,
            'node_pressure_swaps': pressure_tables, 'node41_input_deltas': flow_delta,
            'node40_volume_source': {'rounded_cm3_s': raw, 'exact_cm3_s': {key: float(value) for key, value in exact.items()},
                                     'exact_delta_cm3_s': float(exact['upstream'] - exact['trial'])}}


def capture(study, spec, config, archived, out, execute):
    nodes = study['measurement']['nodes']
    prepare = partial(terminal.observer.prepare, cell_indices=nodes, branch_left_indices=nodes[:-1],
                      wall_indices=nodes[1:], compliance_indices=study['measurement']['pressure_nodes'])
    _, proof = lip.capture(study, spec, config, archived, out, execute, trial_patch=load.patch_trial,
                           prepare=prepare, retain_prefix=True)
    (out / 'pcm-digests.json').write_text(json.dumps(proof, indent=2) + '\n')
    for mode in MODES:
        terminal.split_capture(out, mode)
    return proof


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
    matched, bernstein, prior = (tsp.open_run(study[key], revision) for key in ('matched', 'bernstein', 'branch_first'))
    uid = study['measurement']['recording_id']
    spec = tsp.verified_path(matched, f'artifacts/{uid}/matched-case.json')
    config, config_path = radiation.saved_case(matched, lip.CONFIG)
    reference_pcm = tsp.verified_path(matched, 'artifacts/matched-pcm.npz')
    trial_pcm = tsp.verified_path(bernstein, 'artifacts/render.npz')
    retained = [tsp.verified_path(prior, f'artifacts/{name}') for name in SAVED_FILES]
    inputs = [CASE, Path(__file__).resolve(), Path(first_diff.__file__), Path(drive.__file__), Path(load.__file__),
              Path(terminal.__file__), Path(terminal.observer.__file__), Path(radiation.__file__),
              config_path, spec, reference_pcm, trial_pcm, *retained,
              *(run[0] / 'manifest.json' for run in (matched, bernstein, prior)),
              *radiation.candidate_sources(), lip.EMBEDDED_DICTIONARY, lip.DICT, lip.LOCAL, lip.PROBE,
              lip.TRACE_TOOL, lip.OUTPUT_PATCH, lip.SOURCE_PATCH, lip.observer.LOCAL_PATCH, lip.observer.UPPER_PATCH,
              ws / 'data/cmudict.txt.gz', ws / 'crates/vocal-core/tests/geometry_ramp.rs',
              *(ws / 'tools' / name for name in ('tsp_fk61_lip_front_observation.py', 'tsp_fk61_lip_observation.py',
                 'tsp_fk61_lip_front_radiation_observation.py', 'tsp_fk61_ray43_observation.py',
                 'tsp_fk61_node_volume_observation.py', 'tsp_fk61_lower_lip_bernstein_observation.py',
                 'measure_tsp_fk61_lip_onset.py', 'measure_tsp_fk61_node42_volume_source.py',
                 'measure_fixed_voice_glottal_branch.py', 'measure_fixed_voice_radiation_balance.py',
                 'measure_fixed_voice_release_lip_load.py', 'measure_tsp_fine_variation.py', 'measure_uniform_tube.py')),
              *(upper / name for name in ('Cargo.lock', 'crates/chimera/src/airway/network.rs',
                 'crates/chimera/src/voice/human_voice.rs', 'crates/chimera/tests/airway.rs',
                 'crates/chimera/tests/airway_adversarial.rs'))]

    def measure(out, execute):
        archived = pcm.archived_pcm(reference_pcm, uid)
        with np.load(trial_pcm, allow_pickle=False) as source:
            archived['trial'] = source['pcm']
        proof = capture(study, spec, config, archived, out, execute)
        return analyze(study, out, prior[0] / 'artifacts', proof)

    details = {'case_id': study['id'], 'case_revision': study['revision'], 'upstream_revision': revision}
    return radiation.record_measurement(args.run_id, CASE, inputs, details, measure, command=None, input_root=ws.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
