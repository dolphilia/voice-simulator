"""同じTSP研究用窓で、プリエンファシスだけを変えてLPCのF2を照合する。"""

import argparse
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

import numpy as np
from scipy.signal import freqz

import measure_tsp_f2_bandwidth_envelope as envelope
import measure_tsp_f2_bandwidth_held_out as held_out
import measure_tsp_f2_known_poles as known
import measure_tsp_lpc_lag_window as lag
import measure_tsp_stressed_vowel_formants as tsp
from measure_uniform_tube import build_upstream_probe, record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE


CASE = WORKSPACE / 'cases/tsp-lpc-pre-emphasis.json'
PROBE = WORKSPACE / 'tools/upstream_tsp_lpc_pre_emphasis_probe.rs'


def run_probe(frame, fs, order, grid, artifacts, execute, *, coefficients=None):
    result, = run_probes([(frame, order)], fs, grid, artifacts, execute, coefficients=coefficients)
    return result


def run_probes(windows, fs, grid, artifacts, execute, *, coefficients=None, formant_limits=None):
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera', '--test', 'golden_analysis'],
            cwd=UPSTREAM, stdout=artifacts / 'upstream-golden-analysis.log')
    results = []
    with TemporaryDirectory(prefix='pre-emphasis-', dir=artifacts) as directory:
        scratch = Path(directory)
        binary = build_upstream_probe(PROBE, scratch, execute, extra_libraries=('serde_json',), cargo_args=('--offline',))
        options = [json.dumps(coefficients)] if coefficients is not None else []
        if formant_limits is not None:
            options = [json.dumps(coefficients if coefficients is not None else [None, 0.0]),
                       json.dumps(formant_limits)]
        for i, (frame, order) in enumerate(windows):
            suffix = '' if len(windows) == 1 else f'-{i:02d}'
            request = scratch / f'window{suffix}.json'
            request.write_text(json.dumps([fs, order, frame.tolist(), grid.tolist()]))
            result = artifacts / f'upstream-pre-emphasis{suffix}.json'
            execute([str(binary), str(request), *options], stdout=result)
            results.append(tsp.read(result))
    return results


def inspect_variant(frame, previous_sample, fs, order, grid, cfg, settings, pilot, rust):
    pre = rust['pre_emphasis_coefficient']
    emphasized = frame - pre * previous_sample
    shaped = emphasized * np.hamming(len(frame))
    raw = np.correlate(shaped, shaped, 'full')[len(shaped) - 1:len(shaped) + order]
    result = lag.solve_independently(frame, fs, order, {**cfg, 'pre_emphasis': pre},
                                    settings['lag_window_hz'], grid, raw, rust)
    periodogram, dft_error = envelope.spectrum_db(shaped, fs, grid, pilot['gaussian_sigma_hz'])
    selected = np.asarray(settings['spectral_balance_frequencies_hz'])
    by_formula = 1 - pre * np.exp(-2j * np.pi * selected / fs)
    _, by_freqz = freqz([1, -pre], worN=selected, fs=fs)
    gains = 20 * np.log10(abs(by_formula))
    levels = periodogram[(selected / settings['spectrum_grid_hz']).astype(int)]
    result.update(pre_emphasis_coefficient=pre, pre_emphasis_option=rust['pre_emphasis_option'],
                  analytical_fir_gains_db=gains.tolist(), analytical_fir_balance_db=float(np.diff(gains)[0]),
                  periodogram_levels_db=levels.tolist(), periodogram_balance_db=float(np.diff(levels)[0]))
    result['errors'].update({
        'emphasized_samples': tsp.max_error(emphasized, rust['emphasized']),
        'windowed_samples': tsp.max_error(shaped, rust['shaped']),
        'autocorrelation': tsp.max_error(raw, rust['autocorrelation']),
        'periodogram_db': dft_error,
        'analytic_fir_response': float(np.max(abs(by_formula - by_freqz))),
    })
    return result, periodogram.tolist()


def first_difference(first, second, tolerance):
    return next((i for i, (a, b) in enumerate(zip(first, second, strict=True)) if abs(a-b) > tolerance), None)


def trace_limits(settings, cfg):
    limits = {name: settings['preprocessing_and_correlation_tolerance'] for name in
              ('emphasized_samples', 'windowed_samples', 'autocorrelation', 'weighted_autocorrelation', 'analytic_fir_response')}
    return {**limits, 'coefficients': settings['coefficient_and_residual_tolerance'],
            'prediction_error': settings['coefficient_and_residual_tolerance'],
            'complex_roots': settings['complex_root_tolerance'],
            'eligible_poles_hz': cfg['frequency_bandwidth_agreement_hz'],
            'selection_hz': cfg['frequency_bandwidth_agreement_hz'], 'lpc_envelope_db': settings['envelope_tolerance_db'],
            'periodogram_db': settings['periodogram_tolerance_db']}


def measure(case, cfg, frame, fs, order, old_selected, old_rust, old_raw, pilot, artifacts, execute):
    settings = case['measurement']
    step = settings['spectrum_grid_hz']
    grid = np.arange(0, fs / 2 + step, step)
    fixed, zero = run_probe(frame, fs, order, grid, artifacts, execute)
    if [fixed['pre_emphasis_option'], zero['pre_emphasis_option']] != [None, 0] or [
            fixed['pre_emphasis_coefficient'], zero['pre_emphasis_coefficient']] != settings['pre_emphasis_coefficients']:
        raise ValueError('固定の既定値と明示的な0が登録したプリエンファシス条件と一致しません')
    previous_sample = np.r_[0, frame[:-1]]
    checked = [inspect_variant(frame, previous_sample, fs, order, grid, cfg, settings, pilot, v) for v in (fixed, zero)]
    variants, spectra = zip(*checked, strict=True)
    samples = ('emphasized', 'shaped', 'autocorrelation', 'weighted_autocorrelation')
    pre_limit = settings['preprocessing_and_correlation_tolerance']
    fit_limit = settings['coefficient_and_residual_tolerance']
    pole_limit = cfg['frequency_bandwidth_agreement_hz']
    first = {name: first_difference(fixed[name], zero[name], pre_limit) for name in samples}
    first['coefficients'] = first_difference(fixed['coefficients'], zero['coefficients'], fit_limit)
    first['eligible_poles'] = first_difference(
        [freq for freq, _ in fixed['poles']], [freq for freq, _ in zero['poles']], pole_limit
    ) if len(fixed['poles']) == len(zero['poles']) else None
    observed_delta = np.array(zero['emphasized']) - np.array(fixed['emphasized'])
    expected_delta = settings['pre_emphasis_coefficients'][0] * previous_sample
    unwindowed_delta_error = tsp.max_error(expected_delta, observed_delta)
    windowed_delta_error = tsp.max_error(expected_delta * np.hamming(len(frame)),
                                         np.array(zero['shaped']) - np.array(fixed['shaped']))
    baseline_errors = {
        'windowed_samples': tsp.max_error(old_raw['shaped'], fixed['shaped']),
        'autocorrelation': tsp.max_error(old_raw['autocorrelation'], fixed['autocorrelation']),
        'weighted_autocorrelation': tsp.max_error(old_rust['weighted_autocorrelation'], fixed['weighted_autocorrelation']),
        'coefficients': tsp.max_error(old_rust['coefficients'], fixed['coefficients']),
        'prediction_error': abs(old_rust['prediction_error'] - fixed['prediction_error']),
        'eligible_poles_hz': tsp.max_error(old_rust['poles'], fixed['poles']),
        'selection_hz': held_out.selection_error(old_selected, variants[0]['fixed_selection']),
        'lpc_envelope_db': tsp.max_error(old_rust['lpc_envelope_db'], fixed['lpc_envelope_db']),
    }
    limits = trace_limits(settings, cfg)
    checks = {
        'matches_saved_lag_run': all(v is not None and v <= limits[k] for k, v in baseline_errors.items()),
        'first_difference_in_pre_emphasis': first['emphasized'] == first['shaped'] == 1
           and first['autocorrelation'] == first['weighted_autocorrelation'] == 0,
        'analytic_delay_difference': max(unwindowed_delta_error, windowed_delta_error) <= pre_limit,
        'independent_trace_and_poles': all(error is not None and error <= limits[key]
                                           for v in variants for key, error in v['errors'].items()),
    }
    errors = [v['fixed_selection']['f2'][0] - case['input']['known_f2_hz'] if v['fixed_selection']['f2'] else None
              for v in variants]
    reduction = abs(errors[0]) - abs(errors[1]) if None not in errors else None
    predictions = {
        'bias_reduces': reduction is not None and reduction >= settings['predicted_minimum_bias_reduction_hz'],
        'relative_f2_band_level_drops': variants[1]['periodogram_balance_db'] < variants[0]['periodogram_balance_db'],
    }
    (artifacts / 'spectra.json').write_text(json.dumps({'frequency_hz': grid.tolist(), 'periodogram_db': spectra,
        'lpc_db': [v['lpc_envelope_db'] for v in (fixed, zero)]}, separators=(',', ':')) + '\n')
    return {'checks': checks, 'hypotheses': predictions, 'comparison_to_saved': baseline_errors,
            'first_differences': first, 'pole_counts': [len(v['poles']) for v in (fixed, zero)],
            'first_pre_emphasis_delta': float(observed_delta[1]), 'max_pre_emphasis_delta_error': unwindowed_delta_error,
            'max_windowed_delta_error': windowed_delta_error, 'signed_f2_errors_hz': errors,
            'absolute_bias_reduction_hz': reduction, 'variants': variants, 'scipy': envelope.scipy.__version__}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    case = tsp.read(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True):
        raise ValueError('上流の作業ツリーが登録済みの固定版と一致しません')
    old_run = tsp.open_run(case['baseline'], revision)
    old_case, old_case_file = held_out.saved_case(old_run, lag.CASE)
    model_run = tsp.open_run(old_case['baseline'], revision)
    design, design_file = held_out.saved_case(model_run, known.CASE)
    held = tsp.open_run(design['held_out'], revision)
    registry, registry_file = held_out.saved_case(held, held_out.CASE)
    baseline, pilot = (tsp.open_run(registry[key], revision) for key in ('baseline', 'pilot'))
    cfg_payload, cfg_file = held_out.saved_case(baseline, tsp.CASE)
    pilot_payload, pilot_file = held_out.saved_case(pilot, envelope.CASE)
    cfg, pilot_settings = cfg_payload['measurement'], pilot_payload['measurement']
    wave = tsp.verified_path(model_run, f"artifacts/{case['input']['variant']}.npy")
    summary = tsp.verified_path(model_run, 'summary.json')
    observations = tsp.verified_path(model_run, 'artifacts/upstream-envelopes.json')
    old_trace = tsp.verified_path(old_run, 'artifacts/upstream-lag-comparison.json')
    fs, order, frame, previous_f2, _ = lag.previous_window(case, design, tsp.read(summary), wave, tsp.read(observations))
    settings = case['measurement']
    raw = tsp.read(old_trace)
    archived, = (r for r in raw['variants'] if r['lag_window_hz'] == settings['lag_window_hz'])
    if (old_case['input'] != case['input'] or settings['pre_emphasis_coefficients'] != [cfg['pre_emphasis'], 0]
            or settings['lag_window_hz'] != cfg['lag_window_hz']
            or settings['spectrum_grid_hz'] != old_case['measurement']['spectrum_grid_hz']):
        raise ValueError('先行計測と窓や固定した分析条件が一致しません')
    inputs = [CASE, Path(__file__).resolve(), PROBE, old_case_file, design_file, registry_file, cfg_file, pilot_file,
              wave, summary, observations, old_trace, Path(tsp.__file__), Path(lag.__file__), Path(envelope.__file__),
              Path(held_out.__file__), Path(known.__file__), UPSTREAM / lag.LPC, UPSTREAM / tsp.TSP_SOURCE,
              UPSTREAM / 'crates/chimera/tests/golden_analysis.rs', UPSTREAM / 'Cargo.lock',
              WORKSPACE / 'tools/measure_uniform_tube.py', WORKSPACE / 'tools/measure_fan_crossing_allocations.py',
              WORKSPACE / 'tools/upstream_baseline.py']
    inputs.extend(root / 'manifest.json' for root, _ in (old_run, model_run, held, baseline, pilot))
    return record_measurement(args.run_id, CASE, inputs, {
        'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision,
        'lag_window_reference': old_run[0].name,
    }, lambda artifacts, execute: measure(case, cfg, frame, fs, order, previous_f2, archived, raw,
                                         pilot_settings, artifacts, execute),
        command=None, input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
