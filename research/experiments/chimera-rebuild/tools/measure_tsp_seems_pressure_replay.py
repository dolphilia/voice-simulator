"""同じ発話から声帯の圧差入力を取り出し、ドリフト停止条件で再入力する。"""

import argparse
import math
from pathlib import Path
import subprocess

import numpy as np
from scipy.signal import lfilter

import measure_tsp_seems_drift_only as drift
import measure_tsp_stressed_vowel_formants as tsp
from measure_tsp_f2_bandwidth_held_out import saved_case
from measure_tsp_fine_variation import FIELDS, first_difference
from measure_tsp_seems_spectrum_stages import compare_spectra
from measure_uniform_tube import record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE


CASE = WORKSPACE / 'cases/tsp-seems-pressure-replay.json'
PATCH = WORKSPACE / 'tools/patches/upstream-tsp-pressure-replay.patch'
COMPARE = ('drift_zero', 'pressure_replay')
PRESSURE_FIELD = 'pressure_drop_dyn_cm2'


def pressure_filter(settings, rate, values):
    pole = math.exp(-math.tau * settings['smoothing_hz'] / rate)
    return lfilter([1 - pole], [1, -pole], values)


def gate_limits(settings):
    threshold = settings['threshold_cmh2o'] * settings['dyn_cm2_per_cmh2o']
    return [threshold * factor for factor in settings['gate_threshold_multipliers']]


def pressure_comparison(case, base, signals, pressure, verification, interval, out):
    settings = case['pressure']
    lo, hi = gate_limits(settings)
    start, stop = interval
    trace_count = len(signals['drift_zero'][0][PRESSURE_FIELD])
    errors, gate, traces, input_first = {}, {}, {}, {}
    for name, signal in signals.items():
        physical = signal[0][PRESSURE_FIELD]
        applied, smoothed = pressure[name].T
        estimate = pressure_filter(settings, base['internal_sample_rate_hz'], applied)
        errors[name] = float(np.max(abs(estimate - smoothed)))
        current = smoothed[start:stop]
        gate[name] = {'smoothed_min_dyn_cm2': float(np.min(current)), 'smoothed_max_dyn_cm2': float(np.max(current)),
                      'samples_at_upper_limit': int(np.count_nonzero(current >= hi))}
        traces.update({f'{name}_physical': physical, f'{name}_applied': applied[:trace_count],
                       f'{name}_smoothed': smoothed[:trace_count]})
        input_first[name] = first_difference(applied[:trace_count] - physical)
    np.savez_compressed(out / 'pressure-traces.npz', **traces)
    zero, self_replay = (signals[name] for name in ('drift_zero', 'pressure_self'))
    native = pressure['drift_zero']
    checks = {
        'native_pressure_and_plans': all(input_first[name] is None for name in ('upstream', 'drift_zero'))
            and all(verification[key] for key in ('default_matches_ordinary_pcm', 'ordinary_matches_archived_wav', 'same_plan')),
        'self_pressure_replay_preserves_state_and_full_pcm': verification['drift_zero'] == verification['pressure_self']
            and np.array_equal(native.view('<u8'), pressure['pressure_self'].view('<u8'))
            and all(np.array_equal(zero[0][field].view('<u8'), self_replay[0][field].view('<u8')) for field in FIELDS)
            and np.array_equal(zero[1].view('<u8'), self_replay[1].view('<u8')),
        'replayed_pressure_matches_donor_full_length': np.array_equal(
            pressure['upstream'][:, 0].view('<u8'), pressure['pressure_replay'][:, 0].view('<u8'))
            and input_first['pressure_replay'] is not None,
        'pressure_smoothing_matches_independent': max(errors.values()) <= case['limits']['filter_absolute_dyn_cm2'],
    }
    return checks, {'smoothed_pressure_error_dyn_cm2': errors, 'pressure_gate_limits_dyn_cm2': [lo, hi],
                    'window_pressure': gate, 'first_applied_vs_physical_sample': input_first,
                    'full_pressure_samples': len(native), 'trace_pressure_samples': trace_count}


def measure(case, base, cfg, original, reference_wav, default_window, drift_window, prior, out, execute):
    signals, verification, pressure, _ = drift.capture(base, original, reference_wav, out, execute, pressure_patch=PATCH)
    analysis_signals = {name: signal for name, signal in signals.items() if name != 'pressure_self'}
    checks, result = drift.analyze(base, cfg, analysis_signals, default_window, out, execute)
    checks['radiation_and_output_stages_agree'] = checks.pop('both_radiation_and_output_stages_agree')
    pressure_checks, pressure_result = pressure_comparison(
        case, base, signals, pressure, verification, result['internal_sample_interval'], out)
    checks.update(pressure_checks)
    with np.load(drift_window, allow_pickle=False) as before, np.load(out / 'drift-windows.npz', allow_pickle=False) as after:
        checks['archived_drift_conditions_match'] = all(verification[name] == prior['pcm_verification'][name]
            and all(np.array_equal(before[f'{name}_{field}'], after[f'{name}_{field}']) for field in (*FIELDS, 'lpc_pcm'))
            for name in drift.UPSTREAM_CONDITIONS)
    zero, replaced = (signals[name] for name in COMPARE)
    first = {field: first_difference(replaced[0][field] - zero[0][field]) for field in FIELDS}
    first_pcm = first_difference(replaced[2] - zero[2])
    with np.load(out / 'drift-spectra.npz', allow_pickle=False) as data:
        distance = compare_spectra(base['spectra'], data['frequency_hz'], *(data[name] for name in COMPARE))
    poles = result['lpc_high_poles_hz']
    lpc_change = toward_candidate = None
    if all(poles.values()):
        lpc_change = poles['pressure_replay'][0] - poles['drift_zero'][0]
        toward_candidate = (abs(poles['candidate'][0] - poles['drift_zero'][0])
                            - abs(poles['candidate'][0] - poles['pressure_replay'][0]))
    start, stop = result['internal_sample_interval']
    gate_saturated = all(pressure_result['window_pressure'][name]['samples_at_upper_limit'] == stop - start for name in COMPARE)
    limits = case['limits']
    predictions = {
        'pressure_gate_saturated_in_window': gate_saturated and first['f0_hz'] is None and first['phase'] is None,
        'small_effect_on_glottal_spectrum_and_lpc': distance is not None and lpc_change is not None
            and distance['total_variation_high_band'] < limits['meaningful_glottal_spectral_distance']
            and abs(lpc_change) < limits['meaningful_lpc_shift_hz'],
    }
    return {'checks': checks, 'predictions': predictions, **result, **pressure_result, 'pcm_verification': verification,
            'first_different_internal_sample': first, 'first_different_pcm_frame': first_pcm,
            'glottal_change_from_pressure_replay': distance, 'lpc_change_from_pressure_replay_hz': lpc_change,
            'lpc_gap_reduction_to_candidate_hz': toward_candidate}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    case = tsp.read(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    prior = tsp.open_run(case['reference'], revision)
    drift_case, drift_path = saved_case(prior, drift.CASE)
    base, cfg, original, reference_wav, default_window, paths = drift.reference_inputs(drift_case['reference'], revision)
    drift_window = tsp.verified_path(prior, 'artifacts/drift-windows.npz')
    prior_summary = tsp.verified_path(prior, 'summary.json')
    inputs = [CASE, Path(__file__).resolve(), PATCH, drift_path, drift_window, prior_summary, prior[0] / 'manifest.json',
              UPSTREAM / 'crates/chimera/tests/lung_port.rs', UPSTREAM / 'crates/chimera/src/airway/network.rs', *paths]
    details = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision}
    return record_measurement(args.run_id, CASE, inputs, details, lambda out, execute: measure(
        case, base, cfg, original, reference_wav, default_window, drift_window, tsp.read(prior_summary), out, execute),
        command=None, input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
