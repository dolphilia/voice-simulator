"""鳴禽fluteの開始・途中停止を実時間ブラウザ、CLI、固定上流で照合する。"""

from pathlib import Path

import numpy as np

from measure_songbird_flute import CASE as SOURCE
from measure_worklet_songbird import rms
from measure_worklet_songbird_call import run
from upstream_baseline import WORKSPACE

CASE = WORKSPACE / 'cases/worklet-songbird-flute.json'


def transition_checks(observations, measurement):
    t = measurement['expected_transitions']
    start, first = (t[key] for key in ('start_command', 'first_key'))
    manual, manual_update = (t[key] for key in ('manual_change', 'manual_next_control'))
    stop, stop_update = (t[key] for key in ('stop_command', 'stop_next_control'))
    release, release_update = (t[key] for key in ('breath_release', 'breath_release_next_control'))
    pre_start, at_start, before_key, first_key = (observations[k] for k in (start - 1, start, first - 1, first))
    pre_manual, at_manual, manual_goal = (observations[k] for k in (manual - 1, manual, manual_update))
    pre_stop, at_stop, late_stop, after_stop = (observations[k] for k in (stop - 1, stop, stop_update - 1, stop_update))
    pre_release, at_release, after_release = (observations[k] for k in (release - 1, release, release_update))
    pitch_goal = t['restored_pitch_hz']
    tol = measurement['independent_control_absolute_tolerance']
    checks = {
        'call_id_changes_on_request': pre_start['call_id'] == 0 and at_start['call_id'] == t['call_id'],
        'first_key_on_control_boundary': (at_start['target_voices'] == before_key['target_voices'] == pre_start['target_voices']
                                          and first_key['target_voices'] != before_key['target_voices']
                                          and abs(first_key['target_pitch_hz'] - t['first_pitch_target_hz']) <= tol),
        'manual_pressure_immediate_goal': (pre_manual['target_pressure_kpa'] != t['manual_pressure_kpa']
                                           and at_manual['target_pressure_kpa'] == t['manual_pressure_kpa']
                                           and pre_manual['pressure_kpa'] == at_manual['pressure_kpa']
                                           and manual_goal['pressure_kpa'] > at_manual['pressure_kpa']),
        'call_stop_immediately_restores_manual_goal': (pre_stop['call_id'] == t['call_id'] and at_stop['call_id'] == 0
                                                      and pre_stop['target_pitch_hz'] != pitch_goal
                                                      and at_stop['target_pitch_hz'] == pitch_goal
                                                      and at_stop['gate_target'] == t['retained_gate_target']),
        'pitch_updates_at_next_control': (pre_stop['pitch_hz'] == at_stop['pitch_hz'] == late_stop['pitch_hz']
                                          and abs(after_stop['pitch_hz'] - pitch_goal) < abs(at_stop['pitch_hz'] - pitch_goal)),
        'breath_release_updates_at_next_control': (pre_release['gate_target'] == t['retained_gate_target']
                                                  and at_release['gate_target'] == 0.0
                                                  and pre_release['gate'] == at_release['gate']
                                                  and after_release['gate'] < at_release['gate']),
    }
    return checks, {
        'first_key': {'frame': first, 'pitch_target_hz': first_key['target_pitch_hz']},
        'manual': {'event_frame': manual, 'next_control': manual_update,
                   'pressure_target_kpa': at_manual['target_pressure_kpa']},
        'stop': {'event_frame': stop, 'next_control': stop_update, 'before': pre_stop, 'at_stop': at_stop,
                 'after_control': after_stop},
        'breath_release': {'event_frame': release, 'next_control': release_update, 'before': pre_release,
                           'at_release': at_release, 'after_control': after_release},
    }


def evaluate(points, states, audio, source, measurement, **_context):
    indexed = {int(frame): {key: float(state[i]) for key, state in states.items()}
               for i, frame in enumerate(points) if frame in measurement['extra_output_frames']}
    checks, events = transition_checks(indexed, measurement)
    rate, frames = (source[key] for key in ('sample_rate_hz', 'frames'))
    window = round(measurement['tail_window_seconds'] * rate)
    cropped = audio[:frames // window * window].astype(float).reshape(-1, window)
    peak_window_rms = float(np.sqrt(np.mean(np.square(cropped), axis=1).max()))
    relative_tail = rms(audio[-window:]) / max(peak_window_rms, np.finfo(float).tiny)
    first = measurement['expected_transitions']['first_key']
    lo, hi = (first + round(seconds * rate) for seconds in measurement['active_window_relative_seconds'])
    active_pcm_rms = rms(audio[lo:hi])
    checks['active_pcm_and_release_tail'] = (active_pcm_rms >= measurement['minimum_active_pcm_rms']
                                            and relative_tail <= measurement['maximum_tail_to_peak_rms_ratio'])
    return checks, {'events': events, 'active_pcm_rms': active_pcm_rms, 'tail_to_peak_rms': relative_tail}


if __name__ == '__main__':
    raise SystemExit(run(CASE, SOURCE, 'flute-definition.json', evaluate, Path(__file__).resolve(), __doc__))
