"""Chirp cascadeのWeb MIDIを、キー順を変えた独立対照と照合する。"""

from fractions import Fraction
import math
from pathlib import Path

import numpy as np

from measure_songbird_flute import control_reference
from measure_wasm_fixed import compare_pcm, first_index
from measure_worklet_midi_songbird import rms
from measure_worklet_midi_songbird_call import describe_intervals, main, normalized_events
from measure_worklet_songbird_call import first_synthesis_differences
from measure_worklet_songbird_chirps import replay_targets
from upstream_baseline import WORKSPACE

CASE = WORKSPACE / 'cases/worklet-midi-songbird-chirps.json'
SOURCE = WORKSPACE / 'cases/songbird-calls.json'
LABIAL_CONTROLS = ('voices', 'drive', 'target_voices', 'target_drive')


def compare_order(trace, chronological, starts, end, rate, spec):
    stride = spec['control_frames']
    lo, hi = (Fraction(str(value)) for value in spec['overlap_window_seconds'])
    offset = stride * math.ceil(lo * rate / stride)
    tolerance = spec['order_control_absolute_tolerance']
    windows = []
    for start, stop in zip(starts, (starts[-1]['frame'], end or len(trace)), strict=True):
        first = start['frame']
        overlap = first + offset
        fields = {}
        for field in ('gate_target', 'target_pitch_hz'):
            delta = abs(trace[field][first:stop] - chronological[field][first:stop])
            fields[field] = {
                'first_relative_frame': first_index(delta > tolerance),
                'declared_at_overlap': float(trace[field][overlap]),
                'chronological_at_overlap': float(chronological[field][overlap]),
            }
        windows.append({'start_frame': first, 'stop_frame': stop, 'overlap_frame': overlap,
                        'overlap_in_window': lo <= Fraction(offset, rate) <= hi and overlap < stop,
                        'differences': fields})
    return windows


def chirps_performance(trace, pcm, voice, events, pitches, spec, definition, configs, *, declared, artifacts, execute, **_context):
    rate = voice['sample_rate_hz']
    stride = spec['control_frames']
    dt = stride / rate
    tol = spec['independent_absolute_tolerances']
    starts, releases, end = describe_intervals(trace, pcm, events, spec, rate)
    restart = starts[-1]['frame']
    source = voice | {'events': normalized_events(events, pitches)}
    sorted_definition = definition | {'keys': sorted(definition['keys'], key=lambda key: key['t'])}
    chronological = control_reference(source, {'chirps': sorted_definition}, configs)
    order = compare_order(trace, chronological, starts, end, rate, spec)
    differences = [row['differences'] for row in order]

    declared_pcm, declared_trace = replay_targets(
        'declared-targets', source, declared, stride, spec['quantum_frames'], artifacts, execute)
    chronological_pcm, chronological_trace = replay_targets(
        'chronological-targets', source, chronological, stride, spec['quantum_frames'], artifacts, execute)
    replay_pcm = compare_pcm(pcm, declared_pcm, spec['declared_replay_pcm_tolerance'])
    order_pcm = compare_pcm(chronological_pcm, declared_pcm, spec['order_replay_pcm_difference_threshold'])
    stages = first_synthesis_differences(declared_trace, chronological_trace, 4)
    first = starts[0]['frame']
    gate_delta = first + spec['first_gate_order_delta_frames']
    pcm_first = order_pcm['first_frame_over_tolerance']
    delay = pcm_first - gate_delta if pcm_first is not None else None

    fields = ('gate', 'gate_target', 'pitch_hz', 'target_pitch_hz', 'sac_pressure_dyn_cm2',
              'left_opening', 'right_opening', 'left_port_flow_cm3_s', 'right_port_flow_cm3_s')
    before, after = [{key: float(trace[key][frame]) for key in fields} for frame in (restart - 1, restart)]
    expected_gate = before['gate'] * math.exp(-dt / configs['release_seconds'])
    weight = math.exp(-dt / configs['parameter_time_constants_seconds']['pitch_hz'])
    expected_pitch = math.exp(weight * math.log(before['pitch_hz']) + (1 - weight) * math.log(after['target_pitch_hz']))
    area_errors = {side: float(np.max(abs(trace[f'{side}_port_area_cm2']
                                         - spec['maximum_syrinx_port_area_cm2'] * trace[f'{side}_opening'])))
                   for side in ('left', 'right')}
    tail = rms(pcm[-round(rate * spec['tail_window_seconds']):])
    checks = {
        'chirps_both_presses_transpose_first_key': all(
            abs(row['target_hz'] - spec['first_pitch_key_hz'] * pitch / spec['pitch_reference_hz'])
            <= tol['target_pitch_hz'] and row['gate_goal'] == 0 and trace['call_id'][row['frame']] == 3
            for row, pitch in zip(starts, pitches, strict=True)),
        'chirps_retrigger_starts_call_over_and_preserves_smoothed_state': trace['call_id'][restart - 1] == 3
            and before['gate'] > 0
            and abs(after['gate'] - expected_gate) <= tol['gate']
            and abs(after['pitch_hz'] - expected_pitch) <= tol['pitch_hz']
            and before['target_pitch_hz'] != after['target_pitch_hz'],
        'release_retains_both_syrinx_flows': all(
            row['call_ids'] == [3] and row['pcm_rms'] >= spec['minimum_post_release_pcm_rms']
            and min(row['flows_rms_cm3_s'].values()) >= spec['minimum_both_syrinx_rms_cm3_s'] for row in releases),
        'first_order_difference_in_gate_then_pitch_at_both_notes': all(
            row['gate_target']['first_relative_frame'] == spec['first_gate_order_delta_frames']
            and row['target_pitch_hz']['first_relative_frame'] in spec['first_pitch_order_delta_frames']
            for row in differences),
        'same_elapsed_overlap_has_declared_plateau_and_sorted_rise':
            all(row['overlap_in_window'] for row in order) and all(
                abs(row['gate_target']['declared_at_overlap'] - spec['declared_overlap_gate']) <= tol['gate_target']
                and abs(row['gate_target']['chronological_at_overlap'] - spec['chronological_overlap_gate']) <= tol['gate_target']
                and row['target_pitch_hz']['chronological_at_overlap'] - row['target_pitch_hz']['declared_at_overlap']
                    >= spec['minimum_order_effect_on_pitch_hz'] for row in differences),
        'declared_targets_replay_browser_pcm': replay_pcm['first_frame_over_tolerance'] is None,
        'ordering_changes_sac_and_pcm_before_pitch_target_diverges':
            delay is not None and 0 <= delay <= spec['maximum_order_pcm_delay_frames']
            and order_pcm['maximum_absolute_error'] >= spec['minimum_order_pcm_peak_difference']
            and stages['output_frames']['sac_pressure_dyn_cm2'] == gate_delta
            and pcm_first < first + min(spec['first_pitch_order_delta_frames']),
        'syrinx_port_area_matches_opening': max(area_errors.values()) <= spec['port_area_absolute_tolerance_cm2'],
        'natural_end_restores_performer_and_pcm_decays': end is not None
            and abs((end - restart) / rate - (definition['keys'][-1]['t'] + 0.05)) <= dt + 1e-10
            and np.all(trace['gate_target'][end:] == 0)
            and all(np.all(trace['target_' + name][end:] == voice['controls'][name])
                    for name in ('pitch_hz', 'voices', 'drive'))
            and tail <= spec['maximum_tail_pcm_rms'],
    }
    return checks, {
        'starts': starts, 'post_release': releases, 'automatic_end_frame': end, 'tail_pcm_rms': tail,
        'retrigger': {'frame': restart, 'before': before, 'after': after,
                      'independent_gate': expected_gate, 'independent_pitch_hz': expected_pitch},
        'port_area_errors_cm2': area_errors, 'key_order': order,
        'declared_targets_replay_pcm': replay_pcm, 'target_order_pcm': order_pcm,
        'target_order_pcm_delay_frames': delay, 'target_order_first_synthesis_differences': stages,
    }


if __name__ == '__main__':
    raise SystemExit(main(CASE, performance=chirps_performance, additional_state=LABIAL_CONTROLS,
                          description=__doc__, driver=Path(__file__), extra_inputs=(
                              SOURCE, WORKSPACE / 'tools/measure_worklet_songbird_chirps.py',
                              WORKSPACE / 'tools/measure_worklet_songbird_call.py',
                              WORKSPACE / 'tools/measure_worklet_songbird.py',
                              WORKSPACE / 'tools/measure_songbird_syrinx.py',
                              WORKSPACE / 'tools/measure_wasm_fixed.py')))
