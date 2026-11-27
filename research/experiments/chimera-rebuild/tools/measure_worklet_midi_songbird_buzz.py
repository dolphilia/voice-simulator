"""Finch buzzのWeb MIDI再発音と、呼気の初回・後続の間隔を照合する。"""

import math
from pathlib import Path

import numpy as np

from measure_worklet_midi_songbird import rms
from measure_worklet_midi_songbird_call import describe_intervals, main
from measure_worklet_songbird_buzz import predict_crossings, trace_differences
from measure_worklet_songbird_call import rising_frames
from upstream_baseline import WORKSPACE

CASE = WORKSPACE / 'cases/worklet-midi-songbird-buzz.json'
SOURCE = WORKSPACE / 'cases/songbird-calls.json'
CONTROLS = ('voices', 'drive', 'tension', 'interval_semitones', 'purity')
CONTROL_FIELDS = (*CONTROLS, *(f'target_{key}' for key in CONTROLS))


def compare_crossings(trace, declared, starts, end, rate, spec):
    stride = spec['control_frames']
    pulse = spec['pulse']
    threshold = pulse['gate_threshold']
    coordinates = trace['frame'][::stride].astype(int)
    target = rising_frames(coordinates, trace['gate_target'][::stride], threshold)
    smoothed = rising_frames(coordinates, trace['gate'][::stride], threshold)
    smoothed_reference = rising_frames(coordinates, declared['gate'][::stride], threshold)
    times, period = predict_crossings(pulse, 1)
    grid = [math.ceil(time * rate / stride) * stride for time in times]
    first_interval = float((times[1] - times[0]) * rate)
    steady_interval = float(period * rate)

    windows = []
    for press, stop in zip(starts, (starts[-1]['frame'], end or len(trace)), strict=True):
        start = press['frame']
        predicted = [start + frame for frame in grid if start + frame < stop]
        observed, filtered, reference = [
            values[(values >= start) & (values < stop)]
            for values in (target, smoothed, smoothed_reference)
        ]
        intervals = np.diff(observed)
        windows.append({
            'note': press['note'], 'window': [start, stop],
            'target_rises': observed.tolist(), 'analytic_rises': predicted,
            'measured_intervals_frames': intervals.tolist(),
            'observed_minus_analytic_frames': (observed - predicted).tolist()
                if len(observed) == len(predicted) else None,
            'smoothed_rises': filtered.tolist(), 'independent_smoothed_rises': reference.tolist(),
            'smoothed_lag_frames': (filtered - observed).tolist() if len(filtered) == len(observed) else None,
        })
    return windows, target, first_interval, steady_interval


def buzz_performance(trace, pcm, voice, events, pitches, spec, definition, configs, *, declared, upstream_trace, **_context):
    rate = voice['sample_rate_hz']
    stride = spec['control_frames']
    dt = stride / rate
    tol = spec['independent_absolute_tolerances']
    starts, releases, end = describe_intervals(trace, pcm, events, spec, rate)
    windows, all_rises, first_interval, steady_interval = compare_crossings(
        trace, declared, starts, end, rate, spec)
    for release in releases:
        left, right = release['window']
        release['target_rises'] = all_rises[(all_rises >= left) & (all_rises < right)].tolist()

    restart = starts[-1]['frame']
    restart_fields = ('gate', 'gate_target', 'pitch_hz', 'target_pitch_hz', 'sac_pressure_dyn_cm2',
                      'left_opening', 'right_opening', 'left_port_flow_cm3_s', 'right_port_flow_cm3_s', *CONTROL_FIELDS)
    before, after = [{key: float(trace[key][frame]) for key in restart_fields} for frame in (restart - 1, restart)]
    expected_gate = before['gate'] * math.exp(-dt / configs['release_seconds'])
    weight = math.exp(-dt / configs['parameter_time_constants_seconds']['pitch_hz'])
    expected_pitch = math.exp(weight * math.log(before['pitch_hz']) + (1 - weight) * math.log(after['target_pitch_hz']))
    area_errors = {side: float(np.max(abs(trace[f'{side}_port_area_cm2']
                                         - spec['maximum_syrinx_port_area_cm2'] * trace[f'{side}_opening'])))
                   for side in ('left', 'right')}

    clock = trace['control_clock_seconds']
    elapsed = float(clock[end - 1] - clock[restart - 1]) if end is not None else None
    prior_elapsed = float(clock[end - stride - 1] - clock[restart - 1]) if end is not None else None
    duration = definition['keys'][-1]['t'] + 0.05
    tail = rms(pcm[-round(rate * spec['tail_window_seconds']):])
    pulse_tol = spec['pulse']['maximum_timing_error_frames']
    late = windows[-1]
    low, high = spec['smoothing_lag_frames']
    checks = {
        'buzz_starts_at_transposed_pitch_and_labial_targets': all(
            abs(row['target_hz'] - pitch) <= tol['target_pitch_hz'] and row['gate_goal'] == 0
            and trace['call_id'][row['frame']] == 4
            and all(trace['target_' + name][row['frame']] == value
                    for name, value in spec['labial_targets_at_onset'].items())
            for row, pitch in zip(starts, pitches, strict=True)),
        'buzz_handoff_retains_previous_smoothed_state': trace['call_id'][restart - 1] == 4 and before['gate'] > 0
            and abs(after['gate'] - expected_gate) <= tol['gate'] and abs(after['pitch_hz'] - expected_pitch) <= tol['pitch_hz'],
        'buzz_rises_match_linear_keys': len(late['target_rises']) == spec['pulse']['count'] and all(
            bool(row['observed_minus_analytic_frames']) and max(map(abs, row['observed_minus_analytic_frames'])) <= pulse_tol
            for row in windows),
        'first_interval_shorter_than_repeated_intervals': all(
            row['measured_intervals_frames']
            and abs(row['measured_intervals_frames'][0] - first_interval) <= pulse_tol
            and row['measured_intervals_frames'][0] < steady_interval - pulse_tol
            and all(abs(interval - steady_interval) <= pulse_tol for interval in row['measured_intervals_frames'][1:])
            for row in windows),
        'smoothed_gate_has_expected_crossings_and_lag': late['smoothed_lag_frames'] is not None
            and all(low <= lag <= high for lag in late['smoothed_lag_frames'])
            and all(row['smoothed_rises'] == row['independent_smoothed_rises'] for row in windows),
        'release_retains_pulses_and_both_syrinx_flows': all(
            row['call_ids'] == [4] and len(row['target_rises']) >= spec['minimum_release_pulse_count']
            and row['pcm_rms'] >= spec['minimum_post_release_pcm_rms']
            and min(row['flows_rms_cm3_s'].values()) >= spec['minimum_both_syrinx_rms_cm3_s'] for row in releases),
        'syrinx_port_area_matches_opening': max(area_errors.values()) <= spec['port_area_absolute_tolerance_cm2'],
        'natural_end_restores_performer_and_pcm_decays': end is not None and prior_elapsed <= duration < elapsed
            and abs((end - restart) / rate - duration) <= dt + 1e-10
            and np.all(trace['gate_target'][end:] == 0)
            and all(np.all(trace['target_' + name][end:] == voice['controls'][name])
                    for name in ('pitch_hz', *CONTROLS))
            and tail <= spec['maximum_tail_pcm_rms'],
    }
    return checks, {
        'starts': starts, 'pulses': windows, 'post_release': releases,
        'analytic_first_interval_frames': first_interval, 'analytic_repeat_interval_frames': steady_interval,
        'retrigger': {'frame': restart, 'before': before, 'after': after,
                      'independent_gate': expected_gate, 'independent_pitch_hz': expected_pitch},
        'automatic_end_frame': end, 'elapsed_at_end_seconds': elapsed, 'elapsed_one_tick_before_end_seconds': prior_elapsed,
        'port_area_errors_cm2': area_errors, 'tail_pcm_rms': tail,
        'comparison_to_upstream_by_stage': trace_differences(trace, upstream_trace, pcm, 4),
    }


if __name__ == '__main__':
    raise SystemExit(main(CASE, performance=buzz_performance, additional_state=CONTROL_FIELDS,
                          description=__doc__, driver=Path(__file__), extra_inputs=(
                              SOURCE, WORKSPACE / 'tools/measure_worklet_songbird_buzz.py',
                              WORKSPACE / 'tools/measure_worklet_songbird_call.py')))
