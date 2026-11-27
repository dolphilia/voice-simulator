"""鳴禽buzzの初回と定常時の呼気パルスを実時間ブラウザで照合する。"""

from fractions import Fraction
import math
from pathlib import Path

import numpy as np

from measure_songbird_calls import CASE as SOURCE
from measure_songbird_sustain_pcm import internal
from measure_wasm_fixed import first_index
from measure_worklet_songbird_call import rising_frames, run
from upstream_baseline import WORKSPACE

CASE = WORKSPACE / 'cases/worklet-songbird-buzz.json'


def predict_crossings(limits, amplitude):
    level = Fraction(str(limits['gate_threshold'])) / Fraction(str(amplitude))
    high = Fraction(str(limits['rise_end_gate']))

    def crossing(seconds, low):
        begin, end = (Fraction(str(value)) for value in seconds)
        low = Fraction(str(low))
        return begin + (end - begin) * (level - low) / (high - low)

    first = crossing(limits['first_rise_seconds'], limits['first_rise_start_gate'])
    second = crossing(limits['second_rise_seconds'], limits['second_rise_start_gate'])
    period = Fraction(str(limits['period_seconds']))
    return [first, *(second + i * period for i in range(limits['count'] - 1))], period


def trace_differences(native, upper, audio, factor):
    fields = ('pitch_hz', 'gate', 'sac_pressure_dyn_cm2', 'left_opening', 'right_opening',
              'decimated', 'dc_removed')
    differences = {key: first_index(native[key] != upper[key]) for key in fields}
    native_radiation, upper_radiation = (internal(trace, factor) for trace in (native, upper))
    internal_sample = first_index(native_radiation != upper_radiation)
    first_output = internal_sample // factor if internal_sample is not None else None
    upper_pcm = upper['pcm_f32'].astype(np.float32)
    return {
        'first_differences_output_frames': differences,
        'first_radiation_difference_internal_sample': internal_sample,
        'first_radiation_difference_output_frame': first_output,
        'first_radiation_difference_values': (
            [float(native_radiation[internal_sample]), float(upper_radiation[internal_sample])]
            if internal_sample is not None else None),
        'first_positive_gate_target_frame': first_index(native['gate_target'] > 0),
        'first_radiation_difference_native_gate': float(native['gate'][first_output]) if first_output is not None else None,
        'first_radiation_difference_native_sac_pressure_dyn_cm2': (
            float(native['sac_pressure_dyn_cm2'][first_output]) if first_output is not None else None),
        'different_upstream_pcm_bit_patterns': int(np.count_nonzero(audio.view('u4') != upper_pcm.view('u4'))),
    }


def evaluate(points, states, audio, source, measurement, *, native_trace, upstream_trace, **_context):
    limits = measurement['buzz']
    block = limits['control_interval_frames']
    rate, frames = (source[key] for key in ('sample_rate_hz', 'frames'))
    event = next(e for e in source['events'] if 'play_call' in e)
    request = event['frame']
    first = math.ceil(request / block) * block
    crossings, period = predict_crossings(limits, event['play_call'].get('amplitude', 1))
    predicted = [first + math.ceil(seconds * rate / block) * block for seconds in crossings]
    predicted_first_interval = float((crossings[1] - crossings[0]) * rate)
    steady_interval = float(period * rate)

    on_grid = points % block == 0
    control_points = points[on_grid]
    gate_target = states['gate_target'][on_grid]
    threshold = limits['gate_threshold']
    rising = rising_frames(control_points, gate_target, threshold)
    smoothed = rising_frames(control_points, states['gate'][on_grid], threshold)
    intervals = np.diff(rising)
    rise_errors = (rising - predicted).tolist() if rising.size == len(predicted) else None
    measured_first_interval = int(intervals[0]) if intervals.size else None

    ids = states['call_id']
    transitions = [[int(points[i]), int(ids[i])] for i in np.flatnonzero(ids != np.r_[0, ids[:-1]])]
    end_time = Fraction(str(limits['last_key_seconds'])) + Fraction(str(limits['natural_end_hold_seconds']))
    ideal_end = first + (math.floor(end_time * rate / block) + 1) * block
    start_clock = states['control_clock_seconds'][np.searchsorted(points, request)]
    # 観測に記録される時計は更新後。キー評価に使う時計は一つ前の更新後の値。
    elapsed = np.r_[0.0, states['control_clock_seconds'][on_grid][:-1]] - start_clock
    end_crossing = first_index((control_points >= first) & (elapsed > float(end_time)))
    observed_clock_end = int(control_points[end_crossing]) if end_crossing is not None else None
    elapsed_at_end = float(elapsed[end_crossing]) if end_crossing is not None else None
    clock_error_at_end = (
        float(Fraction.from_float(elapsed_at_end) - Fraction(observed_clock_end - first, rate))
        if end_crossing is not None else None)

    timing_tol = limits['maximum_timing_error_frames']
    control_tol = measurement['independent_control_absolute_tolerance']
    before_key, first_key = (int(np.searchsorted(points, frame)) for frame in (first - 1, first))
    pitch = float(states['target_pitch_hz'][first_key])
    peak_gate = float(np.max(gate_target))
    peak = float(np.max(abs(audio)))
    checks = {
        'measures_every_control_boundary': np.array_equal(control_points, np.arange(0, frames, block)),
        'first_key_on_registered_boundary': bool(
            first == limits['expected_first_control_frame']
            and points[before_key] == first - 1 and points[first_key] == first
            and states['target_pitch_hz'][before_key] == source['controls']['pitch_hz']
            and abs(pitch - limits['first_pitch_target_hz']) <= control_tol),
        'gate_peak_matches_amplitude': abs(peak_gate - limits['expected_peak_gate_target']) <= control_tol,
        'pulse_count': len(rising) == limits['count'],
        'crossings_from_linear_keys': rise_errors is not None and max(map(abs, rise_errors)) <= timing_tol,
        'initial_interval_from_startup_ramp': (
            measured_first_interval is not None
            and abs(measured_first_interval - predicted_first_interval) <= timing_tol
            and measured_first_interval < steady_interval - timing_tol),
        'repeat_intervals_from_period': (len(intervals) == limits['count'] - 1
                                         and bool(np.all(abs(intervals[1:] - steady_interval) <= timing_tol))),
        'call_started_and_naturally_ended': (observed_clock_end is not None
                                             and abs(observed_clock_end - ideal_end) <= timing_tol
                                             and transitions == [[request, limits['call_id']], [observed_clock_end, 0]]),
        'pcm_has_a_signal': peak >= limits['minimum_pcm_peak'],
    }
    return checks, {
        'events': {
            'call_transitions': transitions, 'first_control_frame': first, 'first_pitch_target_hz': pitch,
            'gate_target_peak': peak_gate,
            'pulse_rises': rising.tolist(), 'pulse_intervals': intervals.tolist(),
            'analytic_crossings_frame_grid': predicted, 'observed_minus_analytic_rise_frames': rise_errors,
            'first_interval_prediction_frames': predicted_first_interval, 'steady_interval_prediction_frames': steady_interval,
            'smoothed_pulse_rises': smoothed.tolist(),
            'natural_end_frame_from_rational_clock': ideal_end, 'natural_end_frame_from_measured_clock': observed_clock_end,
            'elapsed_seconds_at_natural_end': elapsed_at_end, 'clock_error_at_natural_end_seconds': clock_error_at_end,
        },
        'peak_pcm': peak,
        'comparison_to_upstream_by_stage': trace_differences(native_trace, upstream_trace, audio, 2 if rate > 60000 else 4),
    }


if __name__ == '__main__':
    raise SystemExit(run(CASE, SOURCE, 'definitions.json', evaluate, Path(__file__).resolve(), __doc__))
