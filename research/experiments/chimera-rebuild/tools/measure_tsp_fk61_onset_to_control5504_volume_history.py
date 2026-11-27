"""発声初期から5503までの体積源を、標本と制御ブロックごとに切り分ける。"""

import argparse
import math
from pathlib import Path

import numpy as np

import measure_tsp_fk61_control5504_oral_history as history


geometry, inlet, oral, six, load, tsp = history.geometry, history.inlet, history.oral, history.six, history.load, history.tsp
CASE = geometry.radiation.WORKSPACE / 'cases/tsp-fk61-onset-to-control5504-volume-history.json'
PRIOR_FILES = history.SAVED_FILES[:-1]
SAVED_FILES = (*PRIOR_FILES, 'trajectories.npz')
POLES = ('pole1_cm3_s', 'pole2_cm3_s')


def cell_values(data, start, stop, nodes, fields):
    return np.asarray([[[data['cells'][n, j][key] for key in fields] for j in nodes]
                       for n in range(start, stop)])


def replay_poles(seed, inputs, alpha):
    result = np.empty((*inputs.shape, 2))
    pole1, pole2 = seed.T
    for i, raw in enumerate(inputs):
        pole1 = pole1 + alpha * (raw - pole1)
        pole2 = pole2 + alpha * (pole1 - pole2)
        result[i, :, 0] = pole1
        result[i, :, 1] = pole2
    return result


def sum_samples(values):
    return np.asarray([[math.fsum(values[:, node, pole]) for pole in range(values.shape[2])]
                       for node in range(values.shape[1])])


def fields(values):
    return {'first_pole_l2_cm3_s': math.hypot(*values[:, 0]),
            'second_pole_l2_cm3_s': math.hypot(*values[:, 1]),
            'signed_poles_cm3_s': values.tolist()}


def geometry_inputs(data, start, stop, nodes, rate):
    local = {}
    volume_errors = {}
    for mode, capture in data.items():
        local[mode] = np.asarray([[oral.raw_from_volumes(capture['cells'][n, j], rate, mode == 'upstream')
                                  for j in nodes] for n in range(start, stop)])
        errors = []
        for n in range(start, stop):
            area_floor = capture['loads'][n]['area_floor']
            for j in nodes:
                row = capture['cells'][n, j]
                volume = max(area_floor, row['area_cm2']) * row['length_cm']
                if volume != row['volume_cm3'] or row['old_volume_cm3'] != capture['cells'][n - 1, j]['volume_cm3']:
                    errors.append((n, j))
        volume_errors[mode] = errors
    upper, trial = (data[key] for key in ('upstream', 'trial'))
    physical = np.asarray([[float(oral.exact_raw(upper, n, j, rate) - oral.exact_raw(trial, n, j, rate))
                            for j in nodes] for n in range(start, stop)])
    return local, physical, volume_errors


def shared_capture(out, prior, native, measure):
    earlier = tsp.read(geometry.radiation.WORKSPACE / 'cases/tsp-fk61-control5504-oral-history.json')['measurement']
    first, stop = earlier['comparison_internal_samples']
    shared = {}
    for mode, capture in native.items():
        old_data = oral.read_capture(prior, mode, earlier)
        old_steps = (prior / f'{mode}-ramp-step.csv').read_text().splitlines()
        new_steps = (out / f'{mode}-ramp-step.csv').read_text().splitlines()
        aligned = [row for row in new_steps[1:] if first <= int(row.split(',', 1)[0]) < stop]
        shared[mode] = all(inlet.shared_capture(capture, old_data).values()) and old_steps == [new_steps[0], *aligned]
        shared[mode] &= all(tsp.sha256(out / f'{mode}-{tag}.csv') == tsp.sha256(prior / f'{mode}-{tag}.csv')
                            for tag in ('centerline', 'ramp-target'))
    return shared


def analyze(study, out, prior, previous, config, gain, coefficients, proof):
    measure = study['measurement']
    start, stop = measure['attribution_internal_samples']
    handoff, handoff_stop = measure['handoff_internal_samples']
    nodes = measure['inner_nodes']
    rate = measure['internal_sample_rate_hz']
    block = measure['control_internal_samples']
    native = {mode: oral.read_capture(out, mode, measure) for mode in geometry.MODES}
    upper, trial = (native[mode] for mode in ('upstream', 'trial'))
    alpha = trial['loads'][start]['pole_coefficient']
    if any(capture['loads'][n]['pole_coefficient'] != alpha
           for capture in native.values() for n in range(start, handoff_stop)):
        raise ValueError('二段平滑の寄与を分離するには、採取した平滑係数が一定かつ共通である必要があります')
    seeds = {mode: cell_values(data, start - 1, start, nodes, POLES)[0] for mode, data in native.items()}
    raw = {mode: cell_values(data, start, handoff_stop, nodes, ('spill_cm3_s',))[:, :, 0]
           for mode, data in native.items()}
    observed = {mode: cell_values(data, start, handoff_stop, nodes, POLES) for mode, data in native.items()}
    native_replay = {mode: replay_poles(seeds[mode], raw[mode], alpha) for mode in native}
    handoff_index = handoff - start
    before, after = (seeds[mode] for mode in ('trial', 'upstream'))
    first_filter_delta = after - before
    decay = (1 - alpha) ** handoff_index
    seed_contribution = decay * np.column_stack(
        (first_filter_delta[:, 0], first_filter_delta[:, 1] + handoff_index * alpha * first_filter_delta[:, 0]))
    local, physical, volume_errors = geometry_inputs(native, start, stop, nodes, rate)
    measured_delta = raw['upstream'][:handoff_index] - raw['trial'][:handoff_index]
    rounded_delta = local['upstream'] - local['trial']
    routing_delta = ((raw['upstream'][:handoff_index] - local['upstream'])
                     - (raw['trial'][:handoff_index] - local['trial']))
    lag = np.arange(handoff_index - 1, -1, -1)
    weights = (1 - alpha) ** lag[:, None] * np.column_stack(
        (np.full(len(lag), alpha), alpha**2 * (lag + 1)))
    parts = {key: values[:, :, None] * weights[:, None, :]
             for key, values in {'measured': measured_delta, 'exact_geometry': physical,
                                 'roundoff': rounded_delta - physical, 'routing': routing_delta}.items()}
    sums = {key: sum_samples(values) for key, values in parts.items()}
    end_delta = observed['upstream'][handoff_index - 1] - observed['trial'][handoff_index - 1]
    residual = end_delta - (sums['measured'] + seed_contribution)
    decomposition_error = float(np.max(np.abs(sums['measured'] - sums['exact_geometry'] - sums['roundoff'] - sums['routing'])))
    windows = [(n, min(n + block, stop)) for n in range(start, stop, block)]
    contributions = {}
    for left, right in windows:
        contributions[str(left)] = {'end': right - 1, **{
            key: fields(sum_samples(array[left - start:right - start])) for key, array in parts.items()}}
    strongest = max(windows, key=lambda pair: contributions[str(pair[0])]['measured']['second_pole_l2_cm3_s'])
    peak_sample = start + int(np.argmax(np.linalg.norm(parts['measured'][:, :, 1], axis=1)))
    with np.load(prior / 'prefix.npz', allow_pickle=False) as archive:
        prefix = dict(archive)
    combined_after = raw['upstream'][handoff_index:]
    baseline = six.replay(trial, measure, False)
    controls = {'unchanged': (False, ()), 'seed_only': (True, ()), 'all_inputs': (False, ((start, stop),)),
                'seed_and_all_inputs': (True, ((start, stop),))}
    controls.update({f'block_{i}': (False, ((i, j),)) for i, j in windows})
    controls.update({f'suffix_{i}': (False, ((i, stop),)) for i, _ in windows[1:]})
    controls[f'omit_block_{strongest[0]}'] = (False, ((start, strongest[0]), (strongest[1], stop)))
    conditions, arrays = {}, {}
    for label, (switch_seed, ranges) in controls.items():
        inputs = raw['trial'][:handoff_index].copy()
        for left, right in ranges:
            inputs[left - start:right - start] = raw['upstream'][left - start:right - start]
        before_handoff = replay_poles(after if switch_seed else before, inputs, alpha)
        after_handoff = replay_poles(before_handoff[-1], combined_after, alpha)
        states = {(handoff_stop - 1, node): after_handoff[-1, i] for i, node in enumerate(nodes)}
        row, arrays[label] = history.pcm_from_history(
            states, upper, trial, measure | {'history_internal_samples': [handoff, handoff_stop]},
            prefix, config, gain, coefficients, baseline)
        conditions[label] = {
            'exchanged_seed': switch_seed, 'exchanged_intervals': [list(pair) for pair in ranges],
            'poles5503': before_handoff[-1].tolist(), 'poles5631': after_handoff[-1].tolist(),
            **fields(before_handoff[-1] - observed['trial'][handoff_index - 1]), **row,
        }
    reference_pcm = previous['conditions']['filter_seed+area']['pcm_full_interval']
    baseline_pcm = previous['conditions']['area']['pcm_full_interval']
    matched = [label for label, row in conditions.items() if row['pcm_full_interval']['first_difference_through_focus'] is None]
    tolerance = measure['linear_filter_tolerance_cm3_s']
    shared = shared_capture(out, prior, native, measure)
    compare_end = handoff_index - 1
    hypotheses = {
        'input_effect_exceeds_initial_state': fields(sums['measured'])['second_pole_l2_cm3_s']
            > fields(seed_contribution)['second_pole_l2_cm3_s'],
        'strongest_block_near_peak_filter_weight': strongest[0] in measure['focus_block_candidates'],
        'strongest_block_alone_leaves_pcm_difference': f'block_{strongest[0]}' not in matched,
        'native_history_recovers_previous_pcm': 'seed_and_all_inputs' in matched,
    }
    checks = {
        'ordinary_cli_and_shared_observations_match': proof == tsp.read(prior / 'pcm-digests.json')
            and all(row['bit_equal'] for row in proof.values()) and all(shared.values())
            and tsp.sha256(out / 'prefix.npz') == tsp.sha256(prior / 'prefix.npz'),
        'captured_volumes_and_filtered_poles_replayed': not any(volume_errors.values())
            and all(load.same_bits(native_replay[mode], observed[mode]) for mode in native),
        'signed_input_contributions_and_seed_recover_both_poles': float(np.max(np.abs(residual))) <= tolerance
            and decomposition_error <= tolerance,
        'full_exchange_and_prior_pcm_controls_replayed': np.array_equal(conditions['unchanged']['poles5503'],
            observed['trial'][compare_end]) and np.array_equal(conditions['seed_and_all_inputs']['poles5503'],
            observed['upstream'][compare_end]) and conditions['unchanged']['pcm_full_interval'] == baseline_pcm
            and conditions['seed_and_all_inputs']['pcm_full_interval'] == reference_pcm,
    }
    report = {'checks': checks, 'hypotheses': hypotheses, 'matched': matched, 'strongest_block': list(strongest),
              'peak_sample': peak_sample, 'filter_weight_peak_sample': start + int(np.argmax(weights[:, 1])),
              'analytic_residual_cm3_s': float(np.max(np.abs(residual))),
              'source_decomposition_residual_cm3_s': decomposition_error,
              'contributions': {key: fields(value) for key, value in {'observed': end_delta, 'seed': seed_contribution, **sums}.items()},
              'blocks': contributions, 'conditions': conditions}
    arrays.update({f'contribution_{key}': value for key, value in parts.items()})
    arrays.update({f'spill_{mode}': rows for mode, rows in raw.items()})
    arrays.update({'seed_contribution': seed_contribution, 'contribution_internal_sample': np.arange(start, stop),
                   'contribution_nodes': np.asarray(nodes), 'contribution_columns': np.asarray(POLES),
                   'pcm_internal_sample': np.arange(measure['local_internal_samples'][0], measure['local_internal_samples'][1]),
                   'pcm_columns': np.asarray((*six.TRAJECTORY_FIELDS, 'flow27_28', 'flow37_38'))})
    return report, arrays


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    return geometry.run_registered(parser.parse_args().run_id, CASE, analyze_run=analyze, prepare_run=history.prepare,
                                   split_run=history.split_observations, retained_files=PRIOR_FILES,
                                   extra_inputs=(Path(__file__).resolve(), Path(history.__file__)))


if __name__ == '__main__':
    raise SystemExit(main())
