"""ChugのWeb MIDI再発音、呼気パルス、声門周期を照合する。"""

from pathlib import Path

import numpy as np

from measure_seal_chug import cycle_checks
from measure_seal_trill import CALL_IDS, glottis_internal
from measure_wasm_fixed import read_json
from measure_worklet_midi_seal_call import CHUG, TRILL, intervals, main
from measure_worklet_midi_songbird import rms
from upstream_baseline import WORKSPACE

CASE = WORKSPACE / 'cases/worklet-midi-seal-chug.json'
PULSE_FIELDS = ('pulse_rate_hz', 'pulse_depth', 'duty', 'target_pulse_rate_hz', 'target_duty',
                'pressure_cm_h2o', 'target_pressure_cm_h2o', 'roughness', 'target_roughness')


def chug_spec(definition, case):
    spec = read_json(TRILL)['measurement'] | read_json(CHUG)['measurement']
    keys = spec['chug_keys']
    expected = [
        {'t': 0.0, 'v': {'gate': 1.0, 'pitch': keys['initial_pitch_hz'], 'pulseRate': keys['pulse_rate_hz'],
                        'pulse': keys['pulse_depth'], 'duty': keys['duty'], 'rough': keys['initial_roughness']}},
        {'t': keys['sweep_seconds'], 'v': {'gate': 1.0}},
        {'t': keys['release_seconds'], 'v': {'gate': 0.0, 'rough': keys['final_roughness']}},
    ]
    if (definition['id'] != case['input']['call_id'] or definition['pitchRef'] != keys['reference_pitch_hz']
            or definition['keys'] != expected or case['input']['pitch_range_hz'] != spec['pitch_limits_hz']
            or case['measurement']['control_frames'] != spec['control_frames']):
        raise ValueError('固定上流のChugと登録した制御点を確認してください')
    return spec


def phase_rate(phase, rate, wrap_threshold):
    wraps = np.flatnonzero(np.diff(phase) < wrap_threshold)
    periods = np.diff(wraps)
    return {'wraps': len(wraps), 'complete_cycles': len(periods),
            'frequency_hz': rate / float(np.mean(periods)) if periods.size else None}


def chug_performance(trace, pcm, voice, events, pitches, config, spec):
    breath = voice['breath']
    rate = breath['sample_rate_hz']
    factor = 2 if rate <= 60000 else 1
    internal_rate = rate * factor
    keys = spec['chug_keys']
    dt = spec['control_frames'] / rate
    tol = config['independent_tolerances']
    glottal_phase = glottis_internal(trace, 'glottis_phase', factor)
    begins, releases, ends = intervals(trace, pcm, events, rate, config)
    starts = [row['frame'] for row in begins]
    restart = starts[-1]
    end = ends[0] if len(ends) == 1 else None
    cycle_flags, cycle = cycle_checks(trace, rate, restart, spec)
    threshold = spec['glottal_cycle']['phase_jump_for_wrap']
    cycle_rates = []
    for start, pitch in zip(starts, pitches, strict=True):
        a, b = (start + round(rate * sec) for sec in config['cycle_rate_window_seconds'])
        cycle_rates.append({'frames': [a, b], 'target_pitch_hz': pitch,
                            'breath': phase_rate(trace['pulse_phase'][a:b], rate, threshold),
                            'glottis': phase_rate(glottal_phase[a * factor:b * factor], internal_rate, threshold)})

    for row in releases:
        a, b = row['frames']
        active = trace[a:b]['pulse_phase'] < trace[a:b]['duty']
        pressure = trace[a:b]['lung_pressure_dyn_cm2']
        row['pulse_on_frames'] = int(active.sum())
        row['pulse_off_frames'] = int((~active).sum())
        row['pulse_on_peak_dyn_cm2'] = float(pressure[active].max()) if active.any() else None
        row['pulse_off_peak_dyn_cm2'] = float(pressure[~active].max()) if (~active).any() else None

    names = ('gate', 'target_pitch_hz', 'pitch_hz', 'target_roughness', 'roughness',
             'pulse_phase', 'pulse_rate_hz', 'lung_pressure_dyn_cm2')
    before, after = [{name: float(trace[name][i]) for name in names} for i in (restart - 1, restart)]
    expected_phase = (before['pulse_phase'] + after['pulse_rate_hz'] * dt) % 1.0
    phase_error = abs((after['pulse_phase'] - expected_phase + .5) % 1.0 - .5)
    sample = restart * factor
    glottal_step = (glottal_phase[sample] - glottal_phase[sample - 1]) % 1.0
    scale = float(trace['glottis_f0_hz_0'][restart] / internal_rate / glottal_step) if glottal_step > 0 else None
    scale_low, scale_high = config['glottal_period_scale_bounds']
    rough_low, rough_high = config['retrigger_roughness_target_before']
    tail = rms(pcm[-round(rate * config['tail_window_seconds']):])
    pulse_parameters = ('pulse_rate_hz', 'pulse_depth', 'duty')
    checks = {
        'chug_keyed_pitch_and_same_breath_targets': all(
            abs(row['pitch_target_hz'] - pitch) <= tol['target_pitch_hz'] and row['gate_target'] == 1
            and all(trace['target_' + key][row['frame']] == keys[key] for key in pulse_parameters)
            and trace['target_roughness'][row['frame']] == keys['initial_roughness']
            for row, pitch in zip(begins, pitches, strict=True)),
        'chug_release_keeps_gate_and_phonation': all(row['call_ids'] == [CALL_IDS['chug']]
            and row['gate_min'] >= config['minimum_release_gate'] and row['pcm_rms'] >= config['minimum_release_pcm_rms']
            and row['glottis_peak_cm2'] >= config['minimum_open_glottis_peak_cm2'] for row in releases),
        'release_keeps_pulsed_lung_pressure': all(row['pulse_on_peak_dyn_cm2'] is not None
            and row['pulse_on_peak_dyn_cm2'] >= config['minimum_pulse_on_pressure_dyn_cm2']
            and row['pulse_off_peak_dyn_cm2'] is not None
            and row['pulse_off_peak_dyn_cm2'] <= config['maximum_pulse_off_pressure_dyn_cm2'] for row in releases),
        'chug_retrigger_carries_breath_and_glottal_phase': rough_low <= before['target_roughness'] <= rough_high
            and before['roughness'] < after['roughness'] < after['target_roughness']
            and before['pitch_hz'] < after['pitch_hz'] < after['target_pitch_hz']
            and abs(after['gate'] - before['gate']) <= tol['gate'] and phase_error <= tol['pulse_phase']
            and scale is not None and scale_low <= scale <= scale_high,
        'pulse_and_glottis_cycles_follow_their_targets': all(row['breath']['frequency_hz'] is not None
            and abs(row['breath']['frequency_hz'] - keys['pulse_rate_hz']) <= config['breath_rate_absolute_tolerance_hz']
            and row['glottis']['frequency_hz'] is not None
            and abs(row['glottis']['frequency_hz'] - row['target_pitch_hz'])
            <= row['target_pitch_hz'] * config['glottal_rate_relative_tolerance'] for row in cycle_rates)
            and cycle_rates[0]['frames'][1] <= restart
            and cycle_rates[0]['glottis']['frequency_hz'] < cycle_rates[1]['glottis']['frequency_hz'],
        'chug_natural_end_restores_performer': end is not None
            and abs((end - restart) / rate - (keys['release_seconds'] + keys['ownership_tail_seconds']))
            <= dt + tol['control_clock_seconds'] and np.all(trace['gate_target'][end:] == 0)
            and all(np.all(trace['target_' + key][end:] == value) for key, value in (
                breath['controls'] | {name: voice['shape'][name] for name in ('pitch_hz', 'roughness')}).items())
            and tail <= config['maximum_tail_pcm_rms'],
    }
    retrigger = {'frame': restart, 'before': before, 'after': after,
                 'independent_pulse_phase': expected_phase, 'pulse_phase_error_cycles': phase_error,
                 'glottal_phase_step': glottal_step, 'glottal_period_scale_at_retrigger': scale}
    return checks | cycle_flags, {'start_windows': begins, 'release_windows': releases, 'cycle_rates': cycle_rates,
                                  'retrigger': retrigger, 'glottal_cycle': cycle, 'natural_end_frame': end,
                                  'tail_pcm_rms': tail}


if __name__ == '__main__':
    extras = tuple(WORKSPACE / 'tools' / name for name in
                   ('measure_seal_chug.py', 'measure_glottal_cycle.py', 'measure_glottal_coupling.py',
                    'measure_turbulence.py', 'measure_junction.py', 'measure_pcm_output.py'))
    raise SystemExit(main(CASE, performance=chug_performance, prepare_spec=chug_spec,
                          additional_state=PULSE_FIELDS, description=__doc__, driver=Path(__file__), extra_inputs=extras))
