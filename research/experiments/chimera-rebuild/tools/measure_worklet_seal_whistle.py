"""アザラシの whistle と音高の折り返しを実時間ブラウザで照合する。"""

from math import exp, log1p
from pathlib import Path

import numpy as np
from scipy.signal import lfilter

import measure_wasm_fixed as wasm
from measure_seal_trill import CASE as TRILL, CALL_IDS, OUTPUT_CASE
from measure_seal_whistle import CASE as SOURCE, boundary_checks
from measure_seal_zap import CASE as ZAP
from measure_worklet_seal_sustain import compare_at, run
from measure_worklet_seal_trill import compare_variant
from upstream_baseline import WORKSPACE


CASE = WORKSPACE / 'cases/worklet-seal-whistle.json'


def pitch_turn(points, observed, start, end, pitch_ratio, rate, spec, config):
    stride = spec['control_frames']
    keep = (points >= start) & (points < end) & (points % stride == 0)
    ticks = points[keep]
    prev = np.flatnonzero(points == start - 1)
    if not np.array_equal(ticks, np.arange(start, end, stride)) or prev.size != 1:
        raise ValueError('谷の測定には開始制御直前と各制御境界の観測が必要です')

    keys = spec['whistle_keys']
    curve_names = ('initial_pitch_hz', 'turn_pitch_hz', 'final_pitch_hz')
    log_pitch = np.log([keys[key] for key in curve_names])
    turn, hold = keys['turn_seconds'], keys['sweep_seconds']
    relative = (ticks - start) / rate
    command = np.interp(relative, [0.0, turn, hold], log_pitch) + np.log(pitch_ratio)
    command = np.clip(command, *np.log(spec['pitch_limits_hz']))
    dt, tau = stride / rate, spec['smoothing_seconds']['pitch_hz']
    retain = exp(-dt / tau)
    # 初期状態から対数音高に対する一次の加重和を計算する。
    initial = retain * np.log(observed['pitch_hz'][prev[0]])
    smoothed, _ = lfilter([1.0 - retain], [1.0, -retain], command, zi=[initial])
    references = {'target_pitch_hz': np.exp(command), 'pitch_hz': np.exp(smoothed)}
    differences, minima = {}, {}
    for key, reference in references.items():
        actual = observed[key][keep]
        differences[key] = compare_at(actual, reference, config['log_filter_comparison_tolerance_hz'], ticks)
        index = int(np.argmin(actual))
        minima[key] = {'frame': int(ticks[index]), 'pitch_hz': float(actual[index]),
                       'reference_frame': int(ticks[np.argmin(reference)])}

    fall_rate = (log_pitch[0] - log_pitch[1]) / turn
    rise_rate = (log_pitch[2] - log_pitch[1]) / (hold - turn)
    continuous_delay = tau * log1p(fall_rate / rise_rate)
    from_key = (minima['pitch_hz']['frame'] - start) / rate - turn
    continuous_error_steps = abs(from_key - continuous_delay) / dt
    checks = {
        'log_pitch_filter_matches': all(result['passed'] for result in differences.values()),
        'discrete_minima_match': all(item['frame'] == item['reference_frame'] for item in minima.values()),
        'continuous_lag_within_control_step': continuous_error_steps
                                              <= config['maximum_continuous_delay_error_control_steps'],
    }
    return checks, {
        'target_minimum': minima['target_pitch_hz'], 'smoothed_minimum': minima['pitch_hz'],
        'minimum_delay_seconds': (minima['pitch_hz']['frame'] - minima['target_pitch_hz']['frame']) / rate,
        'ideal_turn_output_frame': start + turn * rate,
        'smoothed_delay_from_key_seconds': from_key,
        'continuous_delay_seconds': continuous_delay,
        'continuous_delay_error_control_steps': continuous_error_steps,
        'log_filter_comparison': differences,
    }


def evaluate_whistle(points, observed, native_trace, source, variant, spec, *, measurement, audio, upper_pcm,
                     **_capture):
    checks, native_results = boundary_checks(native_trace, source, variant, spec)
    request = native_results['request_frame']
    start, end = (variant[key] for key in ('expected_start_control', 'expected_end'))
    rate = source['breath']['sample_rate_hz']
    active = observed['call_id'] == CALL_IDS['whistle']
    transitions = np.diff(active.astype(int), prepend=0)
    launch = next(event['play_call'] for event in source['events'] if event['frame'] == request)
    keys = spec['whistle_keys']
    played = launch.get('pitch_hz') or keys['reference_pitch_hz']
    first_keys = points[active & (np.abs(observed['target_pitch_hz'] - played)
                                 <= spec['independent_control_absolute_tolerance'])]
    turn_checks, turn = pitch_turn(points, observed, start, end, played / keys['reference_pitch_hz'],
                                    rate, spec, measurement['turnaround'])
    window_start, window_end = spec['smoothed_turn_window_seconds']
    elapsed = (turn['smoothed_minimum']['frame'] - start) / rate
    checks.update({
        'browser_whistle_start_and_end': points[transitions == 1].tolist() == [request]
                                        and points[transitions == -1].tolist() == [end],
        'browser_whistle_first_control': bool(first_keys.size and first_keys[0] == start),
        'browser_target_turn_frame': turn['target_minimum']['frame'] == variant['expected_turn'],
        'browser_smoothed_turn_lag': turn['minimum_delay_seconds'] > 0 and window_start <= elapsed <= window_end,
        **turn_checks,
    })

    marks = {request - 1, request, start - 1, start, end - 1, end,
             turn['target_minimum']['frame'], turn['smoothed_minimum']['frame']}
    marks.update(variant[key] for key in ('fall_sample', 'rise_sample', 'pitch_hold_sample', 'gate_zero_sample'))
    if variant['id'] == 'half-pitch-44100':
        at, update, floor = (variant[key] for key in ('manual_edit_sample', 'manual_control_sample', 'manual_gate_sample'))
        marks.update((at - 1, at, update - 1, update, floor))
    checks['browser_boundary_points_present'] = marks.issubset(set(points))
    snapshots = {
        str(frame): {key: float(observed[key][i]) for key in
                     ('call_id', 'target_pitch_hz', 'pitch_hz', 'target_pulse_rate_hz', 'pulse_rate_hz',
                      'target_duty', 'target_pressure_cm_h2o', 'target_pulse_depth', 'pulse_depth', 'gate_target',
                      'lung_pressure_dyn_cm2')}
        for i, frame in enumerate(points) if frame in marks
    }
    result = {'request_frame': request, 'first_control_frame': int(first_keys[0]) if first_keys.size else None,
              'end_frame': end, 'pitch_turn': turn, 'snapshots': snapshots}
    if variant['id'] == 'official-prefix-48000':
        actual, upper = audio[request:], upper_pcm[request:]
        pcm = wasm.compare_pcm(actual, upper, spec['pcm_absolute_tolerance'])
        offset = pcm['first_bit_difference_frame']
        checks['official_whistle_segment'] = pcm['first_frame_over_tolerance'] is None
        result['official_whistle_segment_pcm'] = {
            **pcm, 'frames': len(actual), 'start_frame': request,
            'first_bit_difference_output_frame': None if offset is None else request + offset,
            'different_bits': int(np.count_nonzero(actual.view('u4') != upper.view('u4'))),
        }
    return checks, result


def compare_whistle(label, baseline, config, source, artifacts, execute, browser, module):
    spec = wasm.read_json(TRILL)['measurement'] | wasm.read_json(ZAP)['measurement'] | source['measurement']
    return compare_variant(label, baseline, config, source | {'measurement': spec}, artifacts, execute,
                           browser, module, evaluate=evaluate_whistle)


if __name__ == '__main__':
    extra_sources = (Path(__file__).resolve(), TRILL, ZAP, OUTPUT_CASE, *(WORKSPACE / 'tools' / name for name in
                     ('measure_seal_trill.py', 'measure_seal_zap.py', 'measure_seal_whistle.py',
                      'measure_worklet_seal_trill.py')))
    raise SystemExit(run(CASE, SOURCE, compare_whistle, 'seal_whistle_render_does_not_allocate', (44100,), __doc__,
                         extra_sources=extra_sources))
