"""U whistleのWeb MIDI入力、音高の谷、離鍵後の発声を照合する。"""

import math
from pathlib import Path

import numpy as np

from measure_wasm_fixed import read_json
from measure_worklet_midi_seal_call import CHUG, TRILL, intervals, main
from measure_worklet_midi_songbird import rms
from measure_worklet_seal_whistle import pitch_turn
from upstream_baseline import WORKSPACE

CASE = WORKSPACE / 'cases/worklet-midi-seal-whistle.json'
SOURCE = WORKSPACE / 'cases/seal-whistle.json'
PULSE_FIELDS = ('pulse_rate_hz', 'pulse_depth', 'duty', 'target_pulse_rate_hz', 'target_duty')


def whistle_spec(definition, case):
    spec = read_json(TRILL)['measurement'] | read_json(SOURCE)['measurement']
    keys = spec['whistle_keys']
    expected = [
        {'t': 0.0, 'v': {'gate': 1.0, 'pitch': keys['initial_pitch_hz'], 'pulse': keys['pulse_depth']}},
        {'t': keys['turn_seconds'], 'v': {'pitch': keys['turn_pitch_hz']}, 'curve': 'exp'},
        {'t': keys['sweep_seconds'], 'v': {'pitch': keys['final_pitch_hz']}, 'curve': 'exp'},
        {'t': keys['release_seconds'], 'v': {'gate': 0.0}},
    ]
    if (definition['id'] != case['input']['call_id'] or definition['pitchRef'] != keys['reference_pitch_hz']
            or definition['keys'] != expected or case['input']['pitch_range_hz'] != spec['pitch_limits_hz']
            or case['measurement']['control_frames'] != spec['control_frames']):
        raise ValueError('固定上流のU whistleと登録した制御点を確認してください')
    return spec | {'roughness_smoothing_seconds': read_json(CHUG)['measurement']['roughness_smoothing_seconds']}


def whistle_performance(trace, pcm, voice, events, pitches, config, spec):
    breath = voice['breath']
    rate = breath['sample_rate_hz']
    dt = spec['control_frames'] / rate
    keys = spec['whistle_keys']
    tol = config['independent_tolerances']
    begins, releases, ends = intervals(trace, pcm, events, rate, config)
    starts = [row['frame'] for row in begins]
    end = ends[0] if len(ends) == 1 else None
    gate_low, gate_high = config['retrigger_gate_before']
    target_low, target_high = config['pitch_valley_window_seconds']
    turn_checks, turns = {}, []
    points = trace['frame'].astype(int)
    for start, stop, pitch, release in zip(starts, (starts[-1], end or len(trace)), pitches, releases, strict=True):
        flags, turn = pitch_turn(points, trace, start, stop, pitch / keys['reference_pitch_hz'], rate, spec, config)
        turns.append(turn)
        command = turn['target_minimum']
        smooth = turn['smoothed_minimum']
        flags['valley_follows_release_in_registered_window'] = (
            release['frame'] < command['frame'] < smooth['frame']
            and all(target_low <= (point['frame'] - start) / rate <= target_high for point in (command, smooth))
            and command['pitch_hz'] < smooth['pitch_hz'])
        flags['valley_offsets_match_registered_prediction'] = (
            command['frame'] - start == config['expected_target_turn_offset_frames']
            and smooth['frame'] - start == config['expected_smoothed_turn_offset_frames'])
        turn_checks.update({f'press_{len(turns)}.{name}': value for name, value in flags.items()})
    hold = starts[-1] + math.ceil(keys['sweep_seconds'] / dt) * spec['control_frames']
    return_pitch = pitches[-1] * keys['final_pitch_hz'] / keys['reference_pitch_hz']
    tail = rms(pcm[-round(config['tail_window_seconds'] * rate):])
    checks = {
        'each_press_sets_keyed_pitch_and_envelope': all(
            abs(row['pitch_target_hz'] - pitch) <= tol['target_pitch_hz'] and row['gate_target'] == 1
            for row, pitch in zip(begins, pitches, strict=True)),
        'release_preserves_call_and_phonation': all(row['call_ids'] == [3]
            and row['gate_min'] >= config['minimum_release_gate'] and row['pcm_rms'] >= config['minimum_release_pcm_rms']
            and row['glottis_peak_cm2'] >= config['minimum_open_glottis_peak_cm2'] for row in releases),
        'retrigger_preserves_smoothed_pitch_and_gate': gate_low <= begins[-1]['preceding_gate'] <= gate_high
            and begins[-1]['preceding_gate'] < begins[-1]['actual_gate'] < 1
            and begins[-1]['preceding_pitch_hz'] < begins[-1]['actual_pitch_hz'] < begins[-1]['pitch_target_hz'],
        'call_holds_last_pitch_and_restores_performer': end is not None and hold < end
            and abs((end - starts[-1]) / rate - (keys['release_seconds'] + keys['ownership_tail_seconds']))
            <= dt + tol['control_clock_seconds'] and np.all(trace['gate_target'][end:] == 0)
            and np.all(abs(trace['target_pitch_hz'][hold:end] - return_pitch) <= tol['target_pitch_hz'])
            and np.all(trace['target_pitch_hz'][end:] == voice['shape']['pitch_hz'])
            and np.all(trace['target_pulse_depth'][end:] == breath['controls']['pulse_depth'])
            and tail <= config['maximum_tail_pcm_rms'],
        'performer_pulse_rate_and_duty_persist': all(np.all(trace['target_' + name] == breath['controls'][name])
            for name in ('pulse_rate_hz', 'duty')),
        'valley_pitch_scales_by_midi_ratio': all(abs(
            turns[1][name]['pitch_hz'] - turns[0][name]['pitch_hz'] * pitches[1] / pitches[0])
            <= config['log_filter_comparison_tolerance_hz'] for name in ('target_minimum', 'smoothed_minimum')),
    }
    return checks | turn_checks, {'start_windows': begins, 'release_windows': releases, 'pitch_turns': turns,
                                 'natural_end_frame': end, 'pitch_hold_frame': hold, 'final_target_pitch_hz': return_pitch,
                                 'tail_pcm_rms': tail}


if __name__ == '__main__':
    extras = (SOURCE, WORKSPACE / 'tools/measure_worklet_seal_whistle.py')
    raise SystemExit(main(CASE, performance=whistle_performance, prepare_spec=whistle_spec,
                          additional_state=PULSE_FIELDS, description=__doc__, driver=Path(__file__), extra_inputs=extras))
