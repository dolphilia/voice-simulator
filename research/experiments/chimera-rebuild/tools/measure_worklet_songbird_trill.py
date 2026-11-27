"""鳴禽trillのパルス周期と自然終了を実時間ブラウザで照合する。"""

import math
from fractions import Fraction
from pathlib import Path

import numpy as np

from measure_songbird_calls import CASE as SOURCE
from measure_worklet_songbird_call import rising_frames, run
from upstream_baseline import WORKSPACE

CASE = WORKSPACE / 'cases/worklet-songbird-trill.json'


def evaluate(points, states, audio, source, measurement, **_context):
    limits = measurement['trill']
    block = limits['control_interval_frames']
    rate = source['sample_rate_hz']
    request = next(event['frame'] for event in source['events'] if 'play_call' in event)
    first = math.ceil(request / block) * block
    period = 1 / Fraction(str(limits['rate_hz']))
    count = limits['count']
    threshold = limits['gate_threshold']
    period_frames = period * rate
    crosses_after_cycle = period * Fraction(str(limits['attack_key_fraction_of_period'])) * Fraction(str(threshold))
    nominal = [(i * period + crosses_after_cycle) * rate for i in range(count)]
    predicted = np.array([first + block * math.ceil(frame / block) for frame in nominal])
    ending_time = ((count - 1 + Fraction(str(limits['off_key_fraction_of_period']))) * period
                   + Fraction(str(limits['natural_end_hold_seconds'])))
    end = first + block * (math.floor(ending_time * rate / block) + 1)

    on_grid = points % block == 0
    control_points = points[on_grid]
    observed = rising_frames(control_points, states['gate_target'][on_grid], threshold)
    smoothed = rising_frames(control_points, states['gate'][on_grid], threshold)
    intervals = np.diff(observed)
    difference = (observed - predicted).tolist() if observed.size == predicted.size else None
    ids = states['call_id']
    changes = np.flatnonzero(ids != np.r_[0, ids[:-1]])
    transitions = [[int(points[i]), int(ids[i])] for i in changes]
    before_key, first_key = (int(np.searchsorted(points, p)) for p in (first - 1, first))
    pitch = float(states['target_pitch_hz'][first_key])
    peak = float(np.max(abs(audio)))
    allowed = limits['maximum_crossing_delay_error_frames']
    checks = {
        'measures_every_control_boundary': np.array_equal(control_points, np.arange(0, source['frames'], block)),
        'pulse_count': len(observed) == count,
        'pulse_period': len(intervals) == count - 1 and bool(np.all(abs(intervals - float(period_frames)) <= allowed)),
        'crossings_from_analytic_clock': difference is not None and max(map(abs, difference)) <= allowed,
        'call_started_and_naturally_ended': transitions == [[request, limits['call_id']], [end, 0]],
        'first_pitch_key': bool(
            points[before_key] == first - 1 and points[first_key] == first
            and states['target_pitch_hz'][before_key] == source['controls']['pitch_hz']
            and abs(pitch - limits['first_pitch_target_hz']) <= measurement['independent_control_absolute_tolerance']),
        'pcm_has_a_signal': peak >= limits['minimum_pcm_peak'],
    }
    clock = states['control_clock_seconds']
    start_clock = clock[np.searchsorted(points, request)]
    boundary_crossings = []
    for pulse, (ideal, frame) in enumerate(zip(nominal, predicted, strict=True), start=1):
        if ideal % block:
            continue
        # このフレームのキー評価は、直前の制御更新後の時計で始まる。
        at = int(np.searchsorted(points, frame))
        elapsed = clock[np.searchsorted(points, frame - block)] - start_clock
        boundary_crossings.append({
            'pulse': pulse, 'output_frame': int(frame),
            'elapsed_clock_error_seconds': float(Fraction.from_float(float(elapsed)) - ideal / rate),
            'gate_target': float(states['gate_target'][at]),
        })
    return checks, {
        'events': {'call_transitions': transitions, 'first_control_frame': first, 'natural_end_frame': end,
                   'first_pitch_target_hz': pitch, 'pulse_rises': observed.tolist(), 'pulse_intervals': intervals.tolist(),
                   'ideal_period_frames': float(period_frames), 'analytic_pulse_rises': predicted.tolist(),
                   'observed_minus_analytic_rise_frames': difference, 'smoothed_pulse_rises': smoothed.tolist(),
                   'smoothed_minus_target_rise_frames': (smoothed - observed).tolist() if smoothed.size == observed.size else None,
                   'analytic_crossings_on_control_boundary': boundary_crossings},
        'peak_pcm': peak,
    }


if __name__ == '__main__':
    raise SystemExit(run(CASE, SOURCE, 'definitions.json', evaluate, Path(__file__).resolve(), __doc__))
