"""FK61_01の制御境界5632以降で口端流量差の入力を分ける。"""

import argparse
from pathlib import Path
import os
import subprocess

import numpy as np

import measure_tsp_fk61_oral_onset_inflow as oral


load, terminal, radiation, tsp = oral.load, oral.terminal, oral.radiation, oral.tsp
lip = load.lip
CASE = radiation.WORKSPACE / 'cases/tsp-fk61-control5632-mouth-flow.json'
MODES = ('upstream', 'trial')
GROUPS = ('initial_state', 'boundary_flow', 'volume_sources', 'coefficients')
BRANCH_COEFFICIENTS = ('inertance', 'resistance', 'forward_loss', 'reverse_loss')
WALL_COEFFICIENTS = ('mass', 'resistance', 'stiffness', 'surface')
TRAJECTORY_FIELDS = ('flow', 'pressure42', 'new_pressure', 'lip_flow')
RETAINED = ('prefix.npz', 'pcm-digests.json', *(f'{mode}-{name}' for mode in MODES for name in
             ('nodes.csv', 'lip.f64le', 'branch.csv', 'wall.csv', 'compliance.csv')))


def replaced_fields(row, reference, keys):
    return row | {key: reference[key] for key in keys}


def volume_data(events, path, measure):
    begin, stop = measure['comparison_internal_samples']
    first, end = measure['local_internal_samples']
    cells = {}
    for n in range(first - 1, end):
        for node, cell in zip(measure['nodes'][1:], events[n]['nodes'], strict=True):
            cells[n, node] = cell
    rows = lip.read_trace(path, stop - begin)
    return {'cells': cells, 'loads': {n: rows[n - begin] for n in range(first, end)}}


def volume_replay(data, measure, fixed):
    first, stop = measure['local_internal_samples']
    rate = measure['internal_sample_rate_hz']
    errors = []
    for n in range(first, stop):
        for node in measure['nodes'][1:]:
            cell = data['cells'][n, node]
            predicted = oral.volume_replay(data, n, node, rate, fixed)
            if (not cell['geometry_enabled'] or cell['minimum_cm2'] < data['loads'][n]['squeeze_threshold']
                    or any(value != cell[key] for key, value in predicted.items())):
                errors.append([n, node])
    return errors


def exchange_series(upper, trial, measure, groups=(), volume_control=None):
    first, stop = measure['local_internal_samples']
    events = {}
    for n in range(first, stop):
        original, ref = trial[n], upper[n]
        event = original.copy()
        if 'boundary_flow' in groups:
            event['boundary'] = replaced_fields(original['boundary'], ref['boundary'], ('flow',))
        if 'coefficients' in groups:
            event.update(series=replaced_fields(original['series'], ref['series'], BRANCH_COEFFICIENTS),
                         walls=[replaced_fields(a, b, WALL_COEFFICIENTS)
                                for a, b in zip(original['walls'], ref['walls'], strict=True)],
                         compliance=ref['compliance'],
                         load=replaced_fields(original['load'], ref['load'], load.LOAD_GEOMETRY))
        if 'volume_sources' in groups or volume_control is not None:
            if volume_control is None:
                selected_nodes = measure['nodes'][1:]
            else:
                start, end = volume_control['internal_samples']
                selected_nodes = (volume_control['node'],) if start <= n < end else ()
            event['nodes'] = [replaced_fields(a, b, ('initial_inflow_cm3_s',)) if j in selected_nodes else a
                              for j, a, b in zip(measure['nodes'][1:], original['nodes'], ref['nodes'], strict=True)]
        events[n] = event
    history = upper if 'initial_state' in groups else trial
    return terminal.model(events, measure, False, initial_event=history[first],
                          preceding_load=history[first - 1]['load'])


def native_differences(data, measure):
    samples = measure['comparison_samples']
    rows = {}
    upper, trial = (data[name] for name in MODES)
    for n in samples:
        event, original = upper[n], trial[n]
        cell, base_cell = event['nodes'][0], original['nodes'][0]
        rows[str(n)] = {'input42_cm3_s': cell['initial_inflow_cm3_s'] - base_cell['initial_inflow_cm3_s'],
                        'input43_cm3_s': event['nodes'][1]['initial_inflow_cm3_s'] - original['nodes'][1]['initial_inflow_cm3_s'],
                        'before_wall42_cm3_s': cell['before_wall_cm3_s'] - base_cell['before_wall_cm3_s'],
                        'pressure42_dyn_cm2': cell['old_pressure_dyn_cm2'] - base_cell['old_pressure_dyn_cm2'],
                        'boundary_cm3_s': event['boundary']['flow'] - original['boundary']['flow'],
                        'series_cm3_s': event['series']['flow'] - original['series']['flow'],
                        'mouth_cm3_s': event['load']['lip_flow'] - original['load']['lip_flow'],
                        'inflow43_cm3_s': event['load']['inflow'] - original['load']['inflow']}
    return rows


def summarize_run(predicted, native, measure, prefix, config, gain, coefficients):
    start, stop = measure['witness_interval']
    mouth = {n: row['lip_flow'] for n, row in predicted.items()}
    return {
        'checkpoints': {str(n): {
            'mouth_cm3_s': mouth[n],
            'shift_from_trial_cm3_s': mouth[n] - native[n]['load']['lip_flow'],
            'branch_cm3_s': predicted[n]['flow'],
        } for n in measure['comparison_samples']},
        'pcm_two_samples': load.output_replay(prefix, {n: mouth[n] for n in range(start, stop)},
                                              measure, config, gain, coefficients),
        'pcm_full_interval': load.output_replay(prefix, mouth, measure, config, gain, coefficients),
    }


def boundary_volume(volume, measure):
    n = measure['local_internal_samples'][0]
    node = measure['nodes'][1]
    rate = measure['internal_sample_rate_hz']
    upper, trial = (volume[mode] for mode in MODES)
    observed = {mode: volume[mode]['cells'][n, node] for mode in MODES}
    exact = {mode: oral.exact_raw(volume[mode], n, node, rate) for mode in MODES}
    rounded = {mode: oral.raw_from_volumes(observed[mode], rate, mode == 'upstream') for mode in MODES}
    return {
        'raw_observed_cm3_s': rounded,
        'raw_exact_cm3_s': {mode: float(value) for mode, value in exact.items()},
        'rounded_delta_cm3_s': rounded['upstream'] - rounded['trial'],
        'exact_delta_cm3_s': float(exact['upstream'] - exact['trial']),
        'geometry_before': {mode: {key: volume[mode]['cells'][n-1, node][key] for key in
                                   ('area_cm2', 'length_cm', 'volume_cm3')} for mode in MODES},
        'geometry_after': {mode: {key: observed[mode][key] for key in
                                  ('area_cm2', 'length_cm', 'volume_cm3')} for mode in MODES},
        'pole2_delta_cm3_s': upper['cells'][n, node]['pole2_cm3_s'] - trial['cells'][n, node]['pole2_cm3_s'],
    }


def analyze(study, captured, previous, earlier_expansion, config, gain, coefficients, proof):
    measure = study['measurement']
    first, stop = measure['local_internal_samples']
    a, b = measure['witness_interval']
    events = {mode: terminal.read_mode(captured, mode, measure, cell_indices=tuple(measure['nodes']))
              for mode in MODES}
    upper, trial = (events[mode] for mode in MODES)
    with np.load(captured / 'prefix.npz', allow_pickle=False) as original:
        prefix = dict(original)
    volume = {mode: volume_data(events[mode], captured / f'{mode}-lip.f64le', measure) for mode in MODES}
    volumes = {mode: volume_replay(data, measure, mode == 'upstream') for mode, data in volume.items()}
    boundary = boundary_volume(volume, measure)
    native_errors, predicted = {}, {}
    for mode, data in events.items():
        fixed = mode == 'upstream'
        predicted[mode] = terminal.model(data, measure, fixed, preceding_load=data[first-1]['load'])
        window = {n: data[n] for n in range(first, stop)}
        mismatch = terminal.disagreements(window, predicted[mode], measure, fixed)
        native_errors[mode] = {str(n): row for n, row in mismatch.items()}
    comparisons = native_differences(events, measure)
    trajectory = {f'native_{mode}': np.asarray([[row[key] for key in TRAJECTORY_FIELDS] for row in values.values()])
                  for mode, values in predicted.items()}
    conditions, selective = [], {}
    for subset in load.subsets(GROUPS):
        replay = exchange_series(upper, trial, measure, subset)
        key = '+'.join(subset) or 'baseline'
        conditions.append({'groups': list(subset), **summarize_run(replay, trial, measure, prefix, config, gain, coefficients)})
        trajectory[key] = np.asarray([[row[field] for field in TRAJECTORY_FIELDS] for row in replay.values()])
    for control in measure['volume_controls']:
        replay = exchange_series(upper, trial, measure, volume_control=control)
        selective[control['id']] = summarize_run(replay, trial, measure, prefix, config, gain, coefficients)
        trajectory[control['id']] = np.asarray([[row[field] for field in TRAJECTORY_FIELDS] for row in replay.values()])
    direct = load.output_replay(prefix, {n: upper[n]['load']['lip_flow'] for n in range(a, b)},
                                measure, config, gain, coefficients)
    baseline = conditions[0]['pcm_two_samples']
    by_group = {tuple(row['groups']): row for row in conditions}
    matched = {name: [entry['groups'] for entry in conditions
                      if entry[name]['first_difference_through_focus'] is None]
               for name in ('pcm_two_samples', 'pcm_full_interval')}
    effects = {group: abs(by_group[group,]['checkpoints'][str(a)]['shift_from_trial_cm3_s']) for group in GROUPS}
    pcm_fields = ('pcm', 'precast', 'first_difference_through_focus')
    checks = {
        'source_cli_and_probes_agree_with_archives': all(proof[mode]['bit_equal']
            and proof[mode]['ordinary'] == proof[mode]['probe'] == proof[mode]['archived'] for mode in MODES),
        'volume_sources_and_two_node_dynamics_match_native': not any(volumes.values()) and not any(native_errors.values()),
        'baseline_and_direct_lip_controls_replay_previous_pcm': (
            all(baseline[key] == previous['controls']['none'][key] for key in pcm_fields)
            and all(direct[key] == previous['controls']['first_shortest'][key] for key in pcm_fields)
            and previous['controls']['first_shortest']['interval'] == [a, b]
            and conditions[0]['pcm_full_interval'] == baseline
            and load.same_bits(trajectory['baseline'], trajectory['native_trial'])),
        'all_registered_groups_and_volume_controls_evaluated': (
            len(conditions) == 2 ** len(GROUPS) and set(selective) == {row['id'] for row in measure['volume_controls']}),
        'early_expansion_pcm_focus_matches_baseline': (
            earlier_expansion['pcm']['baseline_vs_upstream']['first_unequal_sample'] == measure['focus_frame']
            and earlier_expansion['pcm']['expanded_vs_upstream']['first_unequal_sample'] == measure['focus_frame']),
    }
    hypotheses = {
        'length_difference_explains_node42_raw_source_at_control_boundary': (
            abs(boundary['exact_delta_cm3_s']) > 0.5 * abs(boundary['rounded_delta_cm3_s'])),
        'post_boundary_source_outweighs_inherited_state': effects['volume_sources'] > effects['initial_state'],
        'boundary_branch_is_largest_single_group': effects['boundary_flow'] > max(
            value for key, value in effects.items() if key != 'boundary_flow'),
        'a_post_boundary_forcing_exchange_recovers_pcm': any('initial_state' not in group for group in matched['pcm_two_samples']),
    }
    report = {'checks': checks, 'hypotheses': hypotheses, 'boundary_volume42': boundary,
              'native_checkpoints': comparisons, 'volume_errors': volumes, 'native_differences': native_errors,
              'conditions': conditions, 'selective_volume': selective, 'direct_witness': direct,
              'matching_groups': matched}
    return report, trajectory | {'internal_sample': np.arange(first, stop), 'columns': np.asarray(TRAJECTORY_FIELDS)}


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
        parser.error('計測にCHIMERA_RUN_STORAGE=rtl9210bを指定してください')
    matched, output, source, previous, early = (tsp.open_run(study[key], revision) for key in
                                                ('matched', 'output', 'branch_first', 'previous_focus', 'early_expansion'))
    uid = study['measurement']['recording_id']
    spec = tsp.verified_path(matched, f'artifacts/{uid}/matched-case.json')
    config, config_path = radiation.saved_case(matched, lip.CONFIG)
    coefficients = tsp.verified_path(output, 'artifacts/coefficients.json')
    old_result = tsp.verified_path(previous, 'summary.json')
    early_result = tsp.verified_path(early, 'summary.json')
    captured = {name: tsp.verified_path(source, f'artifacts/{name}') for name in RETAINED}
    inputs = [CASE, Path(__file__).resolve(), Path(oral.__file__), Path(load.__file__), Path(terminal.__file__),
              Path(radiation.__file__), config_path, spec, coefficients, old_result, early_result, *captured.values(),
              *(run[0] / 'manifest.json' for run in (matched, output, source, previous, early)),
              *(ws / name for name in ('tools/measure_fixed_voice_glottal_branch.py',
                 'tools/measure_fixed_voice_radiation_balance.py', 'tools/measure_fixed_voice_release_lip_load.py',
                 'tools/measure_tsp_fk61_node42_volume_source.py', 'tools/measure_tsp_fk61_pcm_first_difference.py',
                 'tools/measure_tsp_fk61_lip_onset.py', 'tools/tsp_fk61_terminal_branch_observation.py',
                 'crates/vocal-core/src/airway/network.rs', 'crates/vocal-core/src/airway/network/geometry.rs',
                 'crates/vocal-core/src/voice.rs', 'crates/vocal-core/tests/geometry_ramp.rs')),
              *(upper / name for name in ('crates/chimera/src/airway/network.rs',
                 'crates/chimera/src/voice/human_voice.rs', 'crates/chimera/tests/airway_adversarial.rs'))]

    def measure(out, execute):
        gain = tsp.read(spec)['speech_voice']['voice']['output_gain']
        report, arrays = analyze(study, source[0] / 'artifacts', tsp.read(old_result), tsp.read(early_result), config,
                                 gain, tsp.read(coefficients), tsp.read(captured['pcm-digests.json']))
        np.savez_compressed(out / 'trajectories.npz', **arrays)
        return report

    details = {'case_id': study['id'], 'case_revision': study['revision'], 'upstream_revision': revision}
    return radiation.record_measurement(args.run_id, CASE, inputs, details, measure, command=None, input_root=ws.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
