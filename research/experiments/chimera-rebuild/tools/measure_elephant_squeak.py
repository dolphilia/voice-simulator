"""ゾウの squeak の制御・開始状態と公式デモ全体を照合する。"""

from pathlib import Path

import numpy as np

import measure_elephant_fixed_voice as fixed
from measure_elephant_trumpet import measure_call, run_call_measurement
from measure_elephant_valve import compare_state
from measure_songbird_syrinx import read
from upstream_baseline import WORKSPACE


CASE = WORKSPACE / 'cases/elephant-squeak.json'
OWNED = ('mode', 'lip_pitch_hz', 'pressure_cm_h2o')
FREE = ('pitch_hz', 'trunk', 'chaos')


def replacement_checks(trace, case, request, stop):
    earlier, manual = [e for e in case['events'] if 'params' in e]
    changed = manual['frame']
    chaos = trace['target_chaos']
    return {
        'replaces_trumpet': bool(trace['call_id'][request - 1] == 2),
        'trumpet_chaos_returns_at_replacement': bool(chaos[request - 1] != earlier['params']['chaos']
                                                    and chaos[request] == earlier['params']['chaos']),
        'free_targets_change_while_active': all(trace['target_' + name][changed] == manual['params'][name] for name in FREE),
        'owned_targets_wait': all(trace['target_' + name][changed - 1] == trace['target_' + name][changed]
                                  and trace['target_' + name][changed] != manual['params'][name] for name in OWNED),
        'manual_targets_return_at_stop': all(trace['target_' + name][stop] == manual['params'][name]
                                             for name in OWNED),
        'smoothed_values_wait_after_stop': all(trace[name][stop] == trace[name][stop - 1] for name in OWNED),
    }


def observe(trace, case, variant, spec):
    launch, = [e for e in case['events'] if e.get('play_call', {}).get('id') == 'squeak']
    request, start = launch['frame'], variant['first_control']
    end = variant['end_frame']
    stop = case['frames'] if end is None else end
    selected = trace['call_id'] == 3
    gate = trace['gate_goal']
    allowed = launch['play_call'].get('amplitude', 1.0)
    tolerance = spec['tolerances']['control']
    checks = {
        'ownership_period': np.array_equal(np.flatnonzero(selected), np.arange(request, stop)),
        'first_control_takes_call_targets': all(
            trace['target_' + k][start] == spec['squeak_keys'][k][0][1] for k in OWNED),
        'gate_envelope_scaled': bool(0.99 * allowed < np.max(gate[start:stop]) <= allowed + tolerance),
    }
    if variant.get('replacement_and_stop'):
        checks.update(replacement_checks(trace, case, request, stop))
    elif end is not None:
        checks['natural_release'] = bool(gate[end] == 0 and 0 < trace['gate'][end] < trace['gate'][end - 1])
    reed = compare_state(trace, case, spec)
    checks.update({f'reed_reference.{key}': diff['passed'] for key, diff in reed.items()})
    mode = trace['mode']
    opening = trace['reed_opening_cm2']
    driven = selected & (mode > spec['threshold_mode'])
    bypass = spec['trunk_valve_area_cm2'] * (1 - mode)
    windows = []
    rate = case['sample_rate_hz']
    for seconds in variant['windows_seconds']:
        first, last = (start + round(rate * t) for t in seconds)
        window = slice(first, last)
        windows.append({'seconds': seconds, 'lip_pitch_mean_hz': float(np.mean(trace['lip_pitch_hz'][window])),
                        'reed_peak_to_peak_cm2': float(np.ptp(opening[window])),
                        'nasal_ac_rms_cm3_s': float(np.std(trace['nasal_cm3_s'][window])),
                        'pcm_rms': fixed.rms(trace['pcm_f32'][window])})
    checks['nasal_radiation_measured'] = all(w['nasal_ac_rms_cm3_s'] > 0.0 and w['pcm_rms'] > 0.0 for w in windows)
    columns = ('call_id', 'control_clock_seconds', 'gate_goal', 'gate', 'lung_pressure_dyn_cm2',
               'trunk_valve_area_cm2', 'reed_opening_cm2', *OWNED, *FREE,
               *('target_' + k for k in (*OWNED, *FREE)))
    return checks, {
        'request_frame': request, 'first_control_frame': start, 'end_frame': end,
        'driven_frames': int(np.count_nonzero(driven)),
        'free_opening_controls_frames': int(np.count_nonzero(driven & (opening > bypass))),
        'minimum_bypass_minus_opening_cm2': float(np.min((bypass - opening)[driven])),
        'peak_smoothed_mode': float(np.max(mode[selected])),
        'windows': windows, 'reed_reference': reed,
        'frames': {str(i): {key: float(trace[key][i]) for key in columns} for i in variant['curve_frames']},
    }


def compare_initial_modes(artifacts, spec, variants):
    match = spec['matched_initial_mode']
    block = spec['host_block_frames'][0]
    folders = [artifacts / match[name] for name in ('standard', 'initial_one')]
    baseline, initial_one = [read(folder / 'case.json')['elephant_voice'] for folder in folders]
    rate = baseline['sample_rate_hz']
    first = variants[match['standard']]['observations']['first_control_frame']
    samples = match['comparison_frames']
    fields = ('mode', 'reed_opening_cm2', 'trunk_valve_area_cm2')
    traces = [np.genfromtxt(folder / f'pcm-{block}.csv', delimiter=',', names=True,
                            usecols=fields, max_rows=samples) for folder in folders]
    early = slice(*(first + round(rate * sec) for sec in match['early_window_seconds']))
    audio = slice(*(first + round(rate * sec) for sec in match['audio_window_seconds']))
    area = [float(trace['trunk_valve_area_cm2'][first]) for trace in traces]
    dominance = [int(np.count_nonzero((trace['mode'][early] > spec['threshold_mode']) &
                 (trace['reed_opening_cm2'][early] > spec['trunk_valve_area_cm2'] * (1 - trace['mode'][early]))))
                 for trace in traces]
    raw = [fixed.waveform(folder / f'pcm-{block}.wav', baseline)[audio].astype(float) for folder in folders]
    difference = float(np.max(np.abs(raw[1] - raw[0])))
    checks = {
        'matched_conditions': len(traces[0]) == len(traces[1]) == samples
        and baseline['shape']['mode'] == 0 and initial_one['shape']['mode'] == 1
        and (baseline | {'frames': samples, 'shape': baseline['shape'] | {'mode': 1}}) == initial_one,
        'initial_one_restricts_port': area[1] < area[0],
        'early_reed_influence': dominance[1] > dominance[0],
        'pcm_changes': difference > 0,
    }
    return checks, {'first_control_frame': first, 'first_area_cm2': area, 'early_free_opening_frames': dominance,
                    'max_pcm_difference': difference, 'early_window_seconds': match['early_window_seconds'],
                    'audio_window_seconds': match['audio_window_seconds']}


def measure(config, spec, artifacts, execute):
    checks, variants = measure_call(config, spec, artifacts, execute, 'squeak', observe)
    official = variants['official-full-48000']['observations']
    checks['official_full_length'] = official['official_full_frames'] == spec['official_frames'] == config['elephant_voice']['frames']
    pair, comparison = compare_initial_modes(artifacts, spec, variants)
    checks.update({f'initial_mode.{key}': value for key, value in pair.items()})
    return {'checks': checks, 'variants': variants, 'initial_mode_comparison': comparison}


if __name__ == '__main__':
    raise SystemExit(run_call_measurement(CASE, 'elephant-trumpet-before-squeak-1', measure, Path(__file__).resolve(), __doc__))
