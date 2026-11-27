"""鳴禽のコール切り替えを実時間ブラウザと切り替えを省いた対照で照合する。"""

import json
import math
from pathlib import Path

import numpy as np

from measure_songbird_calls import CASE as SOURCE
from measure_songbird_flute import CALL_FIELDS, trace
from measure_songbird_sustain_pcm import FIELDS
from measure_songbird_syrinx import CLI
from measure_wasm_fixed import compare_pcm
from measure_worklet_songbird import read_wave
from measure_worklet_songbird_call import AREA_FLOW, first_synthesis_differences, run
from upstream_baseline import WORKSPACE

CASE = WORKSPACE / 'cases/worklet-songbird-switch.json'


def render_held_call(source, frame, quantum, artifacts, execute):
    kept = [event for event in source['events'] if event['frame'] != frame]
    if len(kept) != len(source['events']) - 1:
        raise ValueError('切り替えを省く対照の入力が不正です')
    case, wave, trace_path = (artifacts / f'held-buzz.{ext}' for ext in ('json', 'wav', 'csv'))
    config = {'songbird_voice': source | {'events': kept, 'observe_call_id': True, 'observe_syrinx': True}}
    case.write_text(json.dumps(config, ensure_ascii=False, indent=2) + '\n')
    execute([*CLI, 'render-pcm', str(case), str(wave), str(trace_path), str(quantum)])
    rate, frames = (source[key] for key in ('sample_rate_hz', 'frames'))
    return read_wave(wave, rate, frames), trace(trace_path, frames, (*FIELDS, *CALL_FIELDS, 'gate_target', 'call_id', *AREA_FLOW))


def evaluate(points, states, audio, source, measurement, *, control, artifacts, execute, native_trace, **_context):
    limits = measurement['switch']
    block = limits['control_interval_frames']
    rate, frames = (source[key] for key in ('sample_rate_hz', 'frames'))
    manual_frame, manual_control = (limits[key] for key in ('manual_frame', 'manual_control_frame'))
    switch_frame, switch_control = (limits[key] for key in ('switch_frame', 'switch_control_frame'))
    stop_frame, stop_control = (limits[key] for key in ('stop_frame', 'stop_control_frame'))
    manual = next(event for event in source['events'] if event['frame'] == manual_frame)
    index = {int(frame): i for i, frame in enumerate(points)}
    tolerance = measurement['independent_control_absolute_tolerance']
    times = control['parameter_time_constants_seconds']
    dt = block / rate

    def at(field, frame):
        return float(states[field][index[frame]])

    def linear(field, previous, goal):
        return goal + (previous - goal) * math.exp(-dt / times[field])

    ids = states['call_id']
    transitions = [[int(points[i]), int(ids[i])] for i in np.flatnonzero(ids != np.r_[0, ids[:-1]])]
    old_goal_interval = (points >= manual_frame) & (points < switch_frame)
    switch_hold = (points >= switch_frame) & (points < switch_control)
    restored = {}
    for field, old_target in limits['released_parameters'].items():
        goal = manual['controls'][field]
        previous = at(field, switch_frame - 1)
        expected = linear(field, previous, goal)
        target_name = f'target_{field}'
        restored[field] = {
            'target_before': at(target_name, switch_frame - 1),
            'target_on_switch': at(target_name, switch_frame),
            'smoothed_before': previous,
            'smoothed_on_switch': at(field, switch_frame),
            'smoothed_after_control': at(field, switch_control),
            'analytic_after_control': expected,
            'abs_error_after_control': abs(at(field, switch_control) - expected),
            'owned_during_buzz': bool(np.all(states[target_name][old_goal_interval] == old_target)),
            'restored_after_switch': bool(np.all(states[target_name][points >= switch_frame] == goal)),
            'smoothed_held_until_control': bool(np.all(states[field][switch_hold] == previous)),
        }

    pressure_before = at('pressure_kpa', manual_frame - 1)
    pressure_goal = manual['controls']['pressure_kpa']
    previous_gate = at('gate', switch_frame - 1)
    manual_gate = manual['gate']
    release_tau = control['release_seconds']
    release_goal = manual_gate + (previous_gate - manual_gate) * math.exp(-dt / release_tau)
    previous_pitch = at('pitch_hz', switch_frame - 1)
    pitch_goal = limits['new_call_first_pitch_hz']
    a = 1 - math.exp(-dt / times['pitch_hz'])
    log_pitch = math.exp((1 - a) * math.log(previous_pitch) + a * math.log(pitch_goal))
    manual_hold = (points >= manual_frame) & (points < manual_control)
    stop_hold = (points >= stop_frame) & (points < stop_control)
    stop_gate = at('gate', stop_frame - 1)
    stop_expected = stop_gate * math.exp(-dt / release_tau)
    first_pitch = at('target_pitch_hz', switch_control)

    held, held_trace = render_held_call(source, switch_frame, measurement['expected_render_quantum_frames'], artifacts, execute)
    difference = compare_pcm(audio, held, limits['counterfactual_pcm_difference_threshold'])
    first_bit = difference['first_bit_difference_frame']
    onset = difference['first_frame_over_tolerance']
    delay = onset - switch_control if onset is not None else None

    checks = {
        'observes_every_control_boundary': np.array_equal(points[points % block == 0], np.arange(0, frames, block)),
        'call_ids_at_registered_frames': transitions == limits['expected_transitions'],
        'unowned_pressure_target_updates_immediately': (
            at('target_pressure_kpa', manual_frame - 1) != pressure_goal
            and at('target_pressure_kpa', manual_frame) == pressure_goal
            and bool(np.all(states['pressure_kpa'][manual_hold] == pressure_before))
            and abs(at('pressure_kpa', manual_control) - linear('pressure_kpa', pressure_before, pressure_goal)) <= tolerance),
        'owned_targets_survive_manual_update': all(item['owned_during_buzz'] for item in restored.values()),
        'released_targets_restore_manual_values_at_switch': all(item['restored_after_switch'] for item in restored.values()),
        'released_values_update_on_control_boundary': all(
            item['smoothed_held_until_control'] and item['abs_error_after_control'] <= tolerance
            for item in restored.values()),
        'manual_gate_effective_at_switch': (
            at('gate_target', switch_frame - 1) > manual_gate and at('gate_target', switch_frame) == manual_gate
            and bool(np.all(states['gate'][switch_hold] == previous_gate))
            and abs(at('gate', switch_control) - release_goal) <= tolerance),
        'new_pitch_key_at_next_control': (
            at('target_pitch_hz', switch_frame - 1) != manual['controls']['pitch_hz']
            and bool(np.all(states['target_pitch_hz'][switch_hold] == manual['controls']['pitch_hz']))
            and bool(np.all(states['pitch_hz'][switch_hold] == previous_pitch))
            and abs(first_pitch - pitch_goal) <= tolerance
            and abs(at('pitch_hz', switch_control) - log_pitch) <= tolerance),
        'combined_stop_and_gate_release': (
            at('gate_target', stop_frame - 1) > 0.0 and at('gate_target', stop_frame) == 0.0
            and at('target_pitch_hz', stop_frame) == manual['controls']['pitch_hz']
            and bool(np.all(states['gate'][stop_hold] == stop_gate))
            and abs(at('gate', stop_control) - stop_expected) <= tolerance),
        'counterfactual_pcm_unchanged_before_control': first_bit is not None and first_bit >= switch_control,
        'counterfactual_pcm_changes_after_control': (
            delay is not None and 0 <= delay <= limits['maximum_pcm_difference_delay_frames']
            and difference['maximum_absolute_error'] >= limits['minimum_counterfactual_pcm_peak_difference']),
    }
    return checks, {
        'events': {'call_transitions': transitions, 'manual_frame': manual_frame, 'manual_control_frame': manual_control,
                   'switch_frame': switch_frame, 'switch_control_frame': switch_control,
                   'stop_frame': stop_frame, 'stop_control_frame': stop_control, 'restored': restored},
        'pressure_kpa': {'target_on_manual_frame': at('target_pressure_kpa', manual_frame),
                         'smoothed_on_manual_frame': at('pressure_kpa', manual_frame),
                         'smoothed_after_control': at('pressure_kpa', manual_control)},
        'gate': {'target_before_switch': at('gate_target', switch_frame - 1),
                 'target_on_switch': at('gate_target', switch_frame),
                 'smoothed_on_switch': at('gate', switch_frame), 'smoothed_after_control': at('gate', switch_control),
                 'smoothed_on_stop': at('gate', stop_frame), 'smoothed_after_stop_control': at('gate', stop_control)},
        'pitch_hz': {'target_on_switch': at('target_pitch_hz', switch_frame), 'new_call_first_target': first_pitch,
                     'smoothed_after_control': at('pitch_hz', switch_control), 'analytic_after_control': log_pitch},
        'counterfactual_pcm': difference, 'counterfactual_pcm_delay_frames': delay,
        'first_synthesis_differences': first_synthesis_differences(
            held_trace, native_trace, 4 if rate <= 60000 else 2, extra_fields=('gate_target', 'call_id', *AREA_FLOW)),
    }


if __name__ == '__main__':
    raise SystemExit(run(CASE, SOURCE, 'definitions.json', evaluate, Path(__file__).resolve(), __doc__))
