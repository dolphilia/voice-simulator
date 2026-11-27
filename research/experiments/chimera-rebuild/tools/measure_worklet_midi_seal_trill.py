"""Descending trillの下降、再発音とパルス位相を照合する。"""

import math
from pathlib import Path

import numpy as np

from measure_wasm_fixed import read_json
from measure_worklet_midi_seal_call import CHUG, TRILL, intervals, main
from measure_worklet_midi_songbird import rms
from upstream_baseline import WORKSPACE

CASE = WORKSPACE / 'cases/worklet-midi-seal-trill.json'
PULSE_FIELDS = ('pulse_rate_hz', 'pulse_depth', 'duty', 'pressure_cm_h2o',
                'target_pulse_rate_hz', 'target_duty', 'target_pressure_cm_h2o')


def trill_spec(definition, case):
    spec = read_json(TRILL)['measurement']
    keys = spec['keys']
    expected = [
        {'t': 0.0, 'v': {'gate': 1.0, 'pitch': keys['initial_pitch_hz'], 'pulseRate': keys['initial_pulse_rate_hz'],
                        'pulse': keys['pulse_depth'], 'duty': keys['duty']}},
        {'t': keys['sweep_seconds'], 'v': {'gate': 1.0, 'pitch': keys['final_pitch_hz'],
                                        'pulseRate': keys['final_pulse_rate_hz']}, 'curve': 'exp'},
        {'t': keys['release_seconds'], 'v': {'gate': 0.0}},
    ]
    if (definition['id'] != case['input']['call_id'] or definition['pitchRef'] != keys['reference_pitch_hz']
            or definition['keys'] != expected or case['input']['pitch_range_hz'] != spec['pitch_limits_hz']
            or case['measurement']['control_frames'] != spec['control_frames']):
        raise ValueError('固定上流のDescending trillと登録した制御点を確認してください')
    return spec | {'roughness_smoothing_seconds': read_json(CHUG)['measurement']['roughness_smoothing_seconds']}


def pressure_at_retrigger(first, second, dt, conversion):
    step = second['pulse_rate_hz'] * dt
    phase = (first['pulse_phase'] + step) % 1.0
    reset_phase = step % 1.0
    duty, depth = second['duty'], second['pulse_depth']
    pressure_scale = second['pressure_cm_h2o'] * conversion * second['gate']

    def pressure(value):
        sine = math.sin(math.pi * value / duty) if value < duty else 0.0
        return pressure_scale * (1 - depth + depth * sine)

    return {'expected_phase': phase, 'reset_phase': reset_phase, 'continued_pressure_dyn_cm2': pressure(phase),
            'reset_pressure_dyn_cm2': pressure(reset_phase)}


def trill_performance(trace, pcm, voice, events, pitches, config, spec):
    breath = voice['breath']
    rate = breath['sample_rate_hz']
    keys = spec['keys']
    stride = config['control_frames']
    dt = stride / rate
    tol = config['independent_tolerances']
    begins, releases, ends = intervals(trace, pcm, events, rate, config)
    starts = [row['frame'] for row in begins]
    restart = starts[-1]
    end = ends[0] if len(ends) == 1 else None
    fields = ('target_pitch_hz', 'pitch_hz', 'target_pulse_rate_hz', 'gate', 'gate_target', 'pulse_rate_hz',
              'pulse_depth', 'duty', 'pressure_cm_h2o', 'pulse_phase', 'lung_pressure_dyn_cm2')
    snapshots = [{name: float(trace[name][i]) for name in fields} for i in (restart - 1, restart)]
    before, after = snapshots
    contrast = pressure_at_retrigger(before, after, dt, spec['cm_h2o_to_dyn_cm2'])
    phase_error = abs((after['pulse_phase'] - contrast['expected_phase'] + .5) % 1.0 - .5)
    pressure_error = abs(after['lung_pressure_dyn_cm2'] - contrast['continued_pressure_dyn_cm2'])
    reset_error = abs(after['lung_pressure_dyn_cm2'] - contrast['reset_pressure_dyn_cm2'])
    tail = rms(pcm[-round(config['tail_window_seconds'] * rate):])

    paired = []
    for seconds in config['paired_curve_seconds']:
        offset = round(seconds / dt) * stride
        frames = [start + offset for start in starts]
        paired.append({'elapsed_seconds': offset / rate, 'frames': frames,
                       'pitch_targets_hz': trace['target_pitch_hz'][frames].tolist(),
                       'pulse_rate_targets_hz': trace['target_pulse_rate_hz'][frames].tolist()})
    first_pitch, second_pitch = pitches
    lower = spec['pitch_limits_hz'][0]
    expected_crossing = keys['sweep_seconds'] * math.log(lower / second_pitch) / math.log(
        keys['final_pitch_hz'] / keys['initial_pitch_hz'])
    matches = np.flatnonzero(trace['target_pitch_hz'][restart:end] == lower)
    clamp_frame = restart + int(matches[0]) if matches.size else None
    sweep = restart + math.ceil(keys['sweep_seconds'] / dt) * stride
    pulse_at_clamp = float(trace['target_pulse_rate_hz'][clamp_frame]) if clamp_frame is not None else None
    pulse_at_sweep = float(trace['target_pulse_rate_hz'][sweep])
    checks = {
        'trill_starts_set_keyed_pitch_and_pulse': all(
            abs(row['pitch_target_hz'] - pitch) <= tol['target_pitch_hz'] and row['gate_target'] == 1.0
            and abs(trace['target_pulse_rate_hz'][row['frame']] - keys['initial_pulse_rate_hz'])
            <= tol['target_pulse_rate_hz'] for row, pitch in zip(begins, pitches, strict=True)),
        'trill_midi_scales_pitch_only': all(row['frames'][0] < restart
            and abs(row['pitch_targets_hz'][1] - row['pitch_targets_hz'][0] * second_pitch / first_pitch)
            <= tol['target_pitch_hz'] and abs(row['pulse_rate_targets_hz'][1] - row['pulse_rate_targets_hz'][0])
            <= tol['target_pulse_rate_hz'] for row in paired),
        'trill_retrigger_preserves_pulse_phase_and_explains_pressure': before['gate_target'] == after['gate_target'] == 1.0
            and min(before['gate'], after['gate']) >= config['minimum_restart_gate']
            and before['pulse_rate_hz'] < after['pulse_rate_hz'] < after['target_pulse_rate_hz']
            and before['pitch_hz'] < after['pitch_hz'] < after['target_pitch_hz']
            and phase_error <= tol['pulse_phase'] and pressure_error <= tol['lung_pressure_dyn_cm2']
            and reset_error >= config['minimum_reset_pressure_difference_dyn_cm2'],
        'trill_pitch_clamps_while_pulse_slows': clamp_frame is not None and end is not None
            and abs((clamp_frame - restart) / rate - expected_crossing) <= dt + tol['control_clock_seconds']
            and np.all(trace['target_pitch_hz'][clamp_frame:end] == lower)
            and pulse_at_clamp > pulse_at_sweep
            and abs(pulse_at_sweep - keys['final_pulse_rate_hz']) <= tol['target_pulse_rate_hz'],
        'release_preserves_call_and_phonation': all(row['call_ids'] == [1]
            and row['gate_min'] >= config['minimum_release_gate'] and row['pcm_rms'] >= config['minimum_release_pcm_rms']
            and row['glottis_peak_cm2'] >= config['minimum_open_glottis_peak_cm2'] for row in releases),
        'automatic_end_restores_performer': end is not None
            and abs((end - restart) / rate - (keys['release_seconds'] + keys['ownership_tail_seconds']))
            <= dt + tol['control_clock_seconds'] and np.all(trace['gate_target'][end:] == 0)
            and all(np.all(trace['target_' + name][end:] == value)
                    for name, value in (breath['controls'] | {'pitch_hz': voice['shape']['pitch_hz']}).items())
            and tail <= config['maximum_tail_pcm_rms'],
    }
    return checks, {'start_windows': begins, 'release_windows': releases, 'natural_end_frame': end,
                    'paired_curve_samples': paired, 'tail_pcm_rms': tail,
                    'retrigger': {'frame': restart, 'before': before, 'after': after, **contrast,
                                  'phase_error_cycles': phase_error, 'pressure_error_dyn_cm2': pressure_error,
                                  'reset_pressure_error_dyn_cm2': reset_error},
                    'pitch_floor': {'frame': clamp_frame, 'expected_elapsed_seconds': expected_crossing,
                                    'target_hz': lower, 'pulse_rate_at_clamp_hz': pulse_at_clamp,
                                    'sweep_end_frame': sweep, 'pulse_rate_at_sweep_end_hz': pulse_at_sweep}}


if __name__ == '__main__':
    raise SystemExit(main(CASE, performance=trill_performance, prepare_spec=trill_spec, additional_state=PULSE_FIELDS,
                          description=__doc__, driver=Path(__file__)))
