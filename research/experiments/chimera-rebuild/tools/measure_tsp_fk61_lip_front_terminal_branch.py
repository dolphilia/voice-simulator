"""FK61_01の節点42から口端放射までを実測と局所再計算で比較する。"""

import argparse
import csv
from itertools import combinations
import json
import math
import os
from pathlib import Path
import subprocess

import numpy as np

import measure_tsp_fk61_lip_front_radiation as radiation
import tsp_fk61_terminal_branch_observation as observer
from measure_fixed_voice_glottal_branch import replay as solve_branch
from measure_fixed_voice_radiation_balance import wall_values


lip, pcm, tsp = radiation.lip, radiation.pcm, radiation.tsp
CASE = radiation.WORKSPACE / 'cases/tsp-fk61-lip-front-terminal-branch.json'
MODES = radiation.MODES
BRANCH_INPUTS = ('inertance', 'resistance', 'forward_loss', 'reverse_loss', 'noise_pressure')
WALL_STATES = ('velocity', 'displacement', 'flow')
LIP_STATE = ('new_pressure', 'new_inertance_flow', 'lip_flow')
BULK_MODULUS = 1.14e-3 * 35000.0 * 35000.0
RETAINED = ('prefix.npz', *(f'{mode}-{name}' for mode in MODES for name in ('nodes.csv', 'lip.f64le')))


def split_capture(out, mode):
    path = out / f'{mode}-nodes.csv'
    records = {'nodes': [], **{name: [] for name in observer.FIELDS}}
    for line in path.read_text().splitlines(keepends=True):
        tag, _, data = line.partition(',')
        if tag in observer.FIELDS:
            records[tag].append(data)
        else:
            records['nodes'].append(line)
    path.write_text(''.join(records['nodes']))
    for tag, fields in observer.FIELDS.items():
        (out / f'{mode}-{tag}.csv').write_text(','.join(fields) + '\n' + ''.join(records[tag]))


def read_records(path, fields, indices, expected, *, sample_window=None):
    values = {}
    with path.open(newline='') as file:
        reader = csv.reader(file)
        if tuple(next(reader)) != fields:
            raise ValueError(f'観測列が登録と異なります ({path.name})')
        for line in reader:
            key = tuple(map(int, line[:indices]))
            if sample_window is not None and not sample_window[0] <= key[0] < sample_window[1]:
                continue
            row = dict(zip(fields[indices:], map(float, line[indices:]), strict=True))
            if key in values or not all(math.isfinite(value) for value in row.values()):
                raise ValueError(f'観測値が非有限か重複しています ({path.name}, {key})')
            values[key] = row
    if values.keys() != expected:
        raise ValueError(f'観測番号に欠測があります ({path.name}, {sorted(expected - values.keys())})')
    return values


def read_mode(out, mode, measure, *, cell_indices=None):
    first, stop = measure['comparison_internal_samples']
    a, b, mouth = measure['nodes']
    series = ((a, b), (b, mouth))
    expected = {'branch': series, 'wall': ((b,), (mouth,)), 'compliance': ((b,),)}
    traces = {name: read_records(out / f'{mode}-{name}.csv', fields, len(expected[name][0]) + 1,
                                  {(n, *nodes) for n in range(first, stop) for nodes in expected[name]})
              for name, fields in observer.FIELDS.items()}
    cells = radiation.read_nodes(out / f'{mode}-nodes.csv', first, stop, cell_indices=cell_indices)
    sampled_nodes = (b, mouth) if cell_indices is None else tuple(cell_indices.index(node) for node in (b, mouth))
    loads = [lip.load_inputs(row) for row in lip.read_trace(out / f'{mode}-lip.f64le', stop - first)]
    events = {}
    for i, n in enumerate(range(first, stop)):
        events[n] = {
            'boundary': traces['branch'][n, a, b],
            'series': traces['branch'][n, b, mouth],
            'compliance': traces['compliance'][n, b]['value'],
            'nodes': [{key: float(rows[i, index]) for key, rows in cells.items()} for index in sampled_nodes],
            'walls': [traces['wall'][n, node] for node in (b, mouth)],
            'load': loads[i],
        }
    return events


def branch_flow(row, rate, fixed):
    return float(solve_branch(row, rate, fixed)['flow'])


def step_wall(row, rate, fixed):
    return dict(zip(WALL_STATES, map(float, wall_values(row, rate, fixed)), strict=True))


def node_state(rate, fixed, injection, flow, boundary, compliance, walls, pressure, load):
    first, mouth = injection
    first = ((first + boundary) - flow) - walls[0]['flow']
    mouth = (mouth + flow) - walls[1]['flow']
    pressure42 = pressure[0] + (1 / rate) / compliance * first
    load = load | {'old_pressure': pressure[1], 'inflow': mouth}
    return {'net': [first, mouth], 'pressure42': pressure42,
            **radiation.solve_lip(load, rate, fixed)}


def volume_injection(event):
    return [cell['initial_inflow_cm3_s'] for cell in event['nodes']]


def model(events, measure, fixed, reference=None, swaps=(), *, initial_event=None, preceding_load=None):
    start, stop = measure['local_internal_samples']
    rate = measure['internal_sample_rate_hz']
    begin = events[start] if initial_event is None else initial_event
    pressure = [cell['old_pressure_dyn_cm2'] for cell in begin['nodes']]
    walls = [dict(velocity=row['previous_velocity'], displacement=row['previous_displacement'])
             for row in begin['walls']]
    branch_l, branch_u, branch_m = (begin['series'][key] for key in
                                    ('previous_inertance', 'previous_flow', 'previous_momentum'))
    if preceding_load is None:
        load_u, load_l = begin['load']['old_inertance_flow'], begin['load']['inertance']
    else:
        # 直前の保存状態から始め、交換する最初の慣性に対しても通常どおり補正する。
        load_u, load_l = preceding_load['new_inertance_flow'], preceding_load['inertance']
    predicted = {}
    for n in range(start, stop):
        event = events[n]
        ref = event if reference is None else reference[n]
        branch = event['series'].copy()
        if 'branch_coefficients' in swaps:
            branch.update({key: ref['series'][key] for key in BRANCH_INPUTS})
        branch.update(left_pressure=pressure[0], right_pressure=pressure[1],
                      previous_inertance=branch_l, previous_flow=branch_u, previous_momentum=branch_m)
        branch_u = branch_flow(branch, rate, fixed)
        branch_l = branch['inertance']
        branch_m = branch_l * branch_u
        compliance = (ref if 'compliance' in swaps else event)['compliance']
        boundary = (ref if 'boundary' in swaps else event)['boundary']['flow']
        injection = volume_injection(event)
        if 'volume_injection' in swaps or ('volume_injection_onset_plus_one' in swaps
                                           and n == measure['onset_sample'] + 1):
            injection[0] = ref['nodes'][0]['initial_inflow_cm3_s']
        walls = [step_wall(row | {'pressure': p, 'previous_velocity': past['velocity'],
                                  'previous_displacement': past['displacement']}, rate, fixed)
                 for row, p, past in zip(event['walls'], pressure, walls, strict=True)]
        load = event['load']
        if 0 < load_l < load['inertance']:
            load_u *= load_l / load['inertance']
        load_l = load['inertance']
        state = node_state(rate, fixed, injection, branch_u, boundary, compliance, walls,
                           pressure, load | {'old_inertance_flow': load_u})
        pressure = [state['pressure42'], state['new_pressure']]
        load_u = state['new_inertance_flow']
        predicted[n] = {'flow': branch_u, 'walls': walls, **state}
    return predicted


def disagreements(events, predictions, measure, fixed):
    rate = measure['internal_sample_rate_hz']
    mismatches = {}
    for n, event in events.items():
        state = predictions.get(n)
        cells, walls, load = (event[key] for key in ('nodes', 'walls', 'load'))
        actual = {edge: event[edge]['flow'] for edge in ('boundary', 'series')}
        expected = {edge: branch_flow(event[edge], rate, fixed) for edge in actual}
        for i, (cell, wall) in enumerate(zip(cells, walls, strict=True)):
            actual.update({f'wall_{i}_{key}': wall[key] for key in WALL_STATES})
            expected.update({f'wall_{i}_{key}': value for key, value in step_wall(wall, rate, fixed).items()})
            actual[f'wall_{i}_node_flow'] = cell['wall_cm3_s']
            expected[f'wall_{i}_node_flow'] = wall['flow']
        balance = node_state(rate, fixed, volume_injection(event), actual['series'], actual['boundary'],
                             event['compliance'], walls, [row['old_pressure_dyn_cm2'] for row in cells], load)
        actual.update(pressure42=cells[0]['new_pressure_dyn_cm2'], **{key: load[key] for key in LIP_STATE})
        expected.update({key: balance[key] for key in ('pressure42', *LIP_STATE)})
        actual.update(compliance42=event['compliance'], compliance43=load['compliance'],
                      mouth_pressure=cells[1]['new_pressure_dyn_cm2'])
        expected.update(compliance42=cells[0]['volume_cm3'] / BULK_MODULUS,
                        compliance43=cells[1]['volume_cm3'] / BULK_MODULUS,
                        mouth_pressure=load['new_pressure'])
        for i, cell in enumerate(cells):
            actual[f'net_{i}'] = cell['inflow_cm3_s']
            expected[f'net_{i}'] = balance['net'][i]
        static = {key: [actual[key], target] for key, target in expected.items() if actual[key] != target}
        dynamic = {}
        if state is not None:
            dynamic = {key: [actual[key], state[key]] for key in ('pressure42', *LIP_STATE)
                       if actual[key] != state[key]}
            if actual['series'] != state['flow']:
                dynamic['series'] = [actual['series'], state['flow']]
            for i, wall in enumerate(state['walls']):
                dynamic.update({f'wall_{i}_{key}': [actual[f'wall_{i}_{key}'], target]
                                for key, target in wall.items() if actual[f'wall_{i}_{key}'] != target})
        if static or dynamic:
            mismatches[n] = {'static': static, 'dynamic': dynamic}
    return mismatches


def output_swaps(events, config, measure, prefix, gain, coefficients, terms):
    upstream, trial = events['upstream'], events['trial']
    start, stop = measure['local_internal_samples']
    frame = measure['trial_first_pcm_frame']
    witness = measure['mouth_witness_sample']
    clock = measure['internal_sample_rate_hz']
    components = dict(zip(radiation.FIELDS, prefix['trial_source'].T, strict=True))
    baseline = prefix['upstream_pcm'][:frame + 1]
    results = []
    for exchange in terms:
        states = model(trial, measure, False, upstream, exchange)
        lip_flow = components['lip_cm3_s'].copy()
        lip_flow[start:stop] = [value['lip_flow'] for value in states.values()]
        _, input_signal = radiation.radiation_from_components(components | {'lip_cm3_s': lip_flow}, clock, False)
        output, samples = pcm.replay(input_signal, coefficients['candidate'], gain, config)
        first = radiation.signal_difference(baseline, samples[:len(baseline)])['first_unequal_sample']
        results.append({'terms': list(exchange), 'mouth_at_witness_cm3_s': float(lip_flow[witness]),
                        'witness_mouth_delta_cm3_s': float(lip_flow[witness] - upstream[witness]['load']['lip_flow']),
                        'first_pcm_difference_through_frame': first,
                        'dc_removed_at_frame': float(output[frame, 2]), 'pcm_at_frame': float(samples[frame])})
    return results


def analyze(study, config, gain, coefficients, out, previous, proof):
    measure = study['measurement']
    rate, onset = (measure[key] for key in ('internal_sample_rate_hz', 'onset_sample'))
    traces = {mode: read_mode(out, mode, measure) for mode in MODES}
    errors = {}
    local = {}
    for mode, events in traces.items():
        fixed = mode == 'upstream'
        local[mode] = model(events, measure, fixed)
        errors[mode] = disagreements(events, local[mode], measure, fixed)
    upstream, trial = traces['upstream'], traces['trial']
    ref, probe = upstream[onset], trial[onset]
    shifted = {'old_pressure': probe['nodes'][0]['old_pressure_dyn_cm2'],
               'net': probe['nodes'][0]['inflow_cm3_s']}
    with_compliance = shifted['old_pressure'] + (1 / rate) / ref['compliance'] * shifted['net']
    old_flow = upstream[onset + 1]['series']
    new_flow = trial[onset + 1]['series']
    with_left = branch_flow(new_flow | {'left_pressure': old_flow['left_pressure']}, rate, False)
    with_coefficients = branch_flow(new_flow | {k: old_flow[k] for k in BRANCH_INPUTS}, rate, False)
    with_both = branch_flow(new_flow | {k: old_flow[k] for k in (*BRANCH_INPUTS, 'left_pressure')}, rate, False)
    with_order = branch_flow(new_flow | {k: old_flow[k] for k in (*BRANCH_INPUTS, 'left_pressure')}, rate, True)
    with np.load(out / 'prefix.npz', allow_pickle=False) as prefix, np.load(previous['prefix.npz'], allow_pickle=False) as prior:
        matches = (set(prefix.files) == set(prior.files)
                   and all(prefix[key].dtype == prior[key].dtype and prefix[key].shape == prior[key].shape
                           and prefix[key].tobytes() == prior[key].tobytes() for key in prior.files))
        terms = ('compliance', 'boundary', 'branch_coefficients')
        subsets = [exchange for size in range(len(terms) + 1) for exchange in combinations(terms, size)]
        swaps = output_swaps(traces, config, measure, prefix, gain, coefficients, subsets)
        exploratory = output_swaps(traces, config, measure, prefix, gain, coefficients,
                                   study['exploratory_interventions']['terms'])
    earlier = all((out / key).read_bytes() == path.read_bytes() for key, path in previous.items() if key != 'prefix.npz')
    return {
        'checks': {
            'ordinary_probe_and_saved_pcm_unchanged': all(
                row['bit_equal'] and row['ordinary'] == row['probe'] == row['archived'] for row in proof.values()),
            'retained_network_lip_and_output_match': earlier and matches,
            'independent_branch_wall_and_volume_steps_match': not any(
                event['static'] for mode in errors.values() for event in mode.values()),
            'local_replay_matches_both_pressures_branch_wall_and_radiated_flow': not any(
                event['dynamic'] for mode in errors.values() for event in mode.values()),
            'interventions_run_and_reference_pcm_difference_reproduced': len(swaps) == 8 and
                swaps[0]['first_pcm_difference_through_frame'] == measure['trial_first_pcm_frame'],
        },
        'predictions': {
            'onset_pressure_from_compliance': ref['nodes'][0]['inflow_cm3_s'] == shifted['net']
                and with_compliance == ref['nodes'][0]['new_pressure_dyn_cm2'],
            'next_branch_flow_from_left_pressure_alone': with_left == old_flow['flow'],
            'compliance_only_recovers_pcm': swaps[1]['first_pcm_difference_through_frame'] is None,
        },
        'mismatches': {mode: {str(sample): event for sample, event in rows.items()} for mode, rows in errors.items()},
        'local_samples': measure['local_internal_samples'],
        'trial_minus_upstream_flow': [
            {'sample': n, 'boundary': trial[n]['boundary']['flow'] - upstream[n]['boundary']['flow'],
             'series': trial[n]['series']['flow'] - upstream[n]['series']['flow'],
             'injection42': volume_injection(trial[n])[0] - volume_injection(upstream[n])[0],
             'injection43': volume_injection(trial[n])[1] - volume_injection(upstream[n])[1]}
            for n in range(*measure['local_internal_samples'])],
        'onset_pressure42': {'upstream_compliance': ref['compliance'], 'trial_compliance': probe['compliance'],
                             'net_inflow': shifted['net'], 'upstream': ref['nodes'][0]['new_pressure_dyn_cm2'],
                             'trial': probe['nodes'][0]['new_pressure_dyn_cm2'], 'with_upstream_compliance': with_compliance},
        'next_series_flow': {'upstream': old_flow, 'trial': new_flow, 'with_left_pressure': with_left,
                             'with_coefficients': with_coefficients, 'with_both': with_both, 'with_all_and_order': with_order},
        'upstream_local': {str(sample): event for sample, event in local['upstream'].items()},
        'trial_local': {str(sample): event for sample, event in local['trial'].items()},
        'output_interventions': swaps,
        'exploratory_interventions': exploratory,
    }


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
    front, output, matched, prior = (tsp.open_run(study[key], revision) for key in ('front', 'output', 'matched', 'radiation'))
    config, config_path = radiation.saved_case(matched, lip.CONFIG)
    uid = study['measurement']['recording_id']
    spec = tsp.verified_path(matched, f'artifacts/{uid}/matched-case.json')
    pcm_input = tsp.verified_path(matched, 'artifacts/matched-pcm.npz')
    trial_pcm = tsp.verified_path(front, 'artifacts/trial-pcm.npz')
    coefficients = tsp.verified_path(output, 'artifacts/coefficients.json')
    previous = {name: tsp.verified_path(prior, f'artifacts/{name}') for name in RETAINED}
    inputs = [CASE, Path(__file__).resolve(), Path(observer.__file__), Path(radiation.__file__),
              config_path, spec, pcm_input, trial_pcm, coefficients, *previous.values(),
              *(run[0] / 'manifest.json' for run in (front, output, matched, prior)), *radiation.candidate_sources(),
              lip.EMBEDDED_DICTIONARY, lip.DICT, lip.LOCAL, lip.PROBE, lip.TRACE_TOOL, lip.OUTPUT_PATCH, lip.SOURCE_PATCH,
              lip.observer.LOCAL_PATCH, lip.observer.UPPER_PATCH, ws / 'data/cmudict.txt.gz',
              ws / 'crates/vocal-core/tests/geometry_ramp.rs',
              *(ws / 'tools' / name for name in ('tsp_fk61_lip_front_observation.py', 'tsp_fk61_lip_observation.py',
                 'tsp_fk61_lip_front_radiation_observation.py', 'measure_tsp_fk61_lip_onset.py',
                 'measure_fixed_voice_glottal_branch.py', 'measure_fixed_voice_radiation_balance.py',
                 'measure_fixed_voice_release_lip_load.py', 'measure_tsp_fk61_pcm_first_difference.py',
                 'measure_tsp_fine_variation.py', 'measure_uniform_tube.py')),
              *(upper / name for name in ('Cargo.lock', 'crates/chimera/src/airway/network.rs',
                 'crates/chimera/src/voice/human_voice.rs', 'crates/chimera/tests/airway.rs',
                 'crates/chimera/tests/airway_adversarial.rs'))]

    def measure(out, execute):
        arch = pcm.archived_pcm(pcm_input, uid) | {'trial': radiation.read_trial(trial_pcm)}
        _, proof = lip.capture(study, spec, config, arch, out, execute, trial_patch=radiation.apply_trial,
                               prepare=observer.prepare, retain_prefix=True)
        (out / 'pcm-digests.json').write_text(json.dumps(proof, indent=2) + '\n')
        for mode in MODES:
            split_capture(out, mode)
        gain = tsp.read(spec)['speech_voice']['voice']['output_gain']
        return analyze(study, config, gain, tsp.read(coefficients), out, previous, proof)

    info = {'case_id': study['id'], 'case_revision': study['revision'], 'upstream_revision': revision}
    return radiation.record_measurement(args.run_id, CASE, inputs, info, measure, command=None, input_root=ws.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
