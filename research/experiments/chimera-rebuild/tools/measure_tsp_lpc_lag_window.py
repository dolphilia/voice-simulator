"""同じLPC入力窓で自己相関のラグ窓だけを変え、F2と行列を照合する。"""

import argparse
from difflib import unified_diff
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

import numpy as np
from scipy.linalg import toeplitz
from scipy.optimize import linear_sum_assignment

import measure_tsp_f2_bandwidth_envelope as envelope
import measure_tsp_f2_bandwidth_held_out as held_out
import measure_tsp_f2_known_poles as known
import measure_tsp_stressed_vowel_formants as tsp
from measure_uniform_tube import build_upstream_probe, record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE


CASE = WORKSPACE / 'cases/tsp-lpc-lag-window.json'
PROBE = WORKSPACE / 'tools/upstream_tsp_lpc_lag_probe.rs'
LPC = Path('crates/chimera/src/analysis/lpc.rs')


def previous_window(case, model, summary, wave, references):
    target = case['input']
    fs, order = target['sample_rate_hz'], target['lpc_order']
    matches = [(i, row) for i, row in enumerate(summary['windows'])
               if all(row[k] == target[v] for k, v in
                      (('variant', 'variant'), ('center', 'center'), ('order', 'lpc_order')))]
    design = summary['model_poles_hz'][target['variant']][1]
    if (len(matches) != 1 or fs != model['signal']['sample_rate_hz']
            or design != [target['known_f2_hz'], target['known_f2_bandwidth_hz']]):
        raise ValueError('先行計測から同じ波形と設計F2を特定できません')
    index, row = matches[0]
    if row['start_sample'] != target['first_sample']:
        raise ValueError('切り出し開始標本が先行実行と一致しません')
    samples = np.load(wave, allow_pickle=False)
    start = row['start_sample']
    frame = samples[start:start + target['frame_samples']]
    if samples.dtype != np.float64 or frame.shape != (target['frame_samples'],) or not np.isfinite(frame).all():
        raise ValueError('先行実行の波形は所定の長さの有限なfloat64が必要です')
    return fs, order, frame, row['fixed'], references[index]


def run_probe(case, frame, fs, order, grid, artifacts, execute):
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera', '--test', 'golden_analysis'],
            cwd=UPSTREAM, stdout=artifacts / 'upstream-golden-analysis.log')
    with TemporaryDirectory(prefix='lag-window-', dir=artifacts) as directory:
        scratch = Path(directory)
        original_path = scratch / 'upstream_lpc.rs'
        execute(['git', 'show', f"{case['upstream_revision']}:{LPC.as_posix()}"], cwd=UPSTREAM, stdout=original_path)
        original = original_path.read_text()
        if original_path.read_bytes() != (UPSTREAM / LPC).read_bytes():
            raise ValueError('作業ツリーのLPC実装が固定コミットと一致しません')
        before = '2.0 * PI * 40.0 * k as f64'
        if original.count(before) != 1:
            raise ValueError('上流のラグ窓の定数を一箇所に特定できません')
        changed = original.replace(before, '2.0 * PI * 0.0 * k as f64')
        (scratch / 'lpc_zero_window.rs').write_text(changed)
        (artifacts / 'zero-lag-window.patch').write_text(''.join(unified_diff(
            original.splitlines(keepends=True), changed.splitlines(keepends=True), 'upstream/lpc.rs', 'trial/lpc.rs')))
        source = scratch / PROBE.name
        source.write_bytes(PROBE.read_bytes())
        binary = build_upstream_probe(source, scratch, execute, extra_libraries=('serde_json',), cargo_args=('--offline',))
        request = scratch / 'window.json'
        request.write_text(json.dumps([fs, order, frame.tolist(), grid.tolist()]))
        result = artifacts / 'upstream-lag-comparison.json'
        execute([str(binary), str(request)], stdout=result)
    return tsp.read(result)


def solve_independently(frame, fs, order, cfg, width, grid, raw, rust):
    lag = np.arange(order + 1)
    weight = np.exp(-0.5 * (2 * np.pi * width * lag / fs)**2)
    correlations = raw * weight
    matrix = toeplitz(correlations[:order])
    matrix.flat[::order + 1] = correlations[0] * (1 + 1e-9) + 1e-30
    rhs = -correlations[1:]
    coefficients = np.r_[1.0, np.linalg.solve(matrix, rhs)]
    residual = matrix[0, 0] + np.dot(coefficients[1:], correlations[1:])
    eigenvalues = np.linalg.eigvalsh(matrix)
    roots = np.roots(coefficients)
    got = np.array([complex(re, im) for re, im in rust['roots']])
    distance = abs(roots[:, None] - got)
    i, j = linear_sum_assignment(distance)
    poles, axial = tsp.independent_poles(frame, fs, order, {**cfg, 'lag_window_hz': width})
    raw_error, pole_error, nyquist_matches = tsp.compare_poles(
        {'poles': poles, 'negative_real_roots': axial}, rust, cfg)
    response = np.polynomial.polynomial.polyval(np.exp(-2j * np.pi * grid / fs), coefficients)
    curve = 10 * np.log10(residual / (abs(response)**2 + 1e-30))
    picked = envelope.select(rust['poles'], cfg)
    return {
        'lag_window_hz': width, 'lag_weights': weight.tolist(), 'coefficients': coefficients.tolist(),
        'weighted_autocorrelation': correlations.tolist(), 'fixed_selection': picked,
        'prediction_error': float(residual), 'minimum_eigenvalue': float(eigenvalues[0]),
        'condition_number_2': float(eigenvalues[-1] / eigenvalues[0]),
        'raw_pole_delta_hz': raw_error, 'nyquist_axis_matches': nyquist_matches,
        'errors': {
            'weighted_autocorrelation': tsp.max_error(correlations, rust['weighted_autocorrelation']),
            'coefficients': tsp.max_error(coefficients, rust['coefficients']),
            'prediction_error': float(abs(residual - rust['prediction_error'])),
            'complex_roots': float(distance[i, j].max()),
            'eligible_poles_hz': pole_error,
            'selection_hz': held_out.selection_error(picked, envelope.select(poles, cfg)),
            'lpc_envelope_db': tsp.max_error(curve, rust['lpc_envelope_db']),
        },
    }


def measure(case, cfg, frame, fs, order, old_selection, old_rust, pilot, artifacts, execute):
    settings = case['measurement']
    step = settings['spectrum_grid_hz']
    grid = np.arange(0, fs / 2 + step, step)
    current = run_probe(case, frame, fs, order, grid, artifacts, execute)
    shaped = np.r_[frame[0], frame[1:] - cfg['pre_emphasis'] * frame[:-1]] * np.hamming(len(frame))
    raw = np.correlate(shaped, shaped, mode='full')[len(shaped) - 1:len(shaped) + order]
    periodogram, dft_error = envelope.spectrum_db(shaped, fs, grid, pilot['gaussian_sigma_hz'])
    variants = []
    for width, rust in zip(settings['lag_window_hz'], current['variants'], strict=True):
        if width != rust['lag_window_hz']:
            raise ValueError('ラグ窓の対照条件が登録順と一致しません')
        variants.append(solve_independently(frame, fs, order, cfg, width, grid, raw, rust))
    fixed, zero = variants
    ref_fixed, ref_zero = current['variants']
    old_agreement = {
        'coefficients': tsp.max_error(old_rust['coefficients'], ref_fixed['coefficients']),
        'prediction_error': abs(old_rust['prediction_error'] - ref_fixed['prediction_error']),
        'poles_hz': tsp.max_error(old_rust['poles'], ref_fixed['poles']),
        'fixed_selection_hz': held_out.selection_error(fixed['fixed_selection'], old_selection),
        'envelope_db': tsp.max_error(old_rust['lpc_envelope_db'], ref_fixed['lpc_envelope_db']),
    }
    pre_tolerance = settings['preprocessing_and_correlation_tolerance']
    fit_tolerance = settings['coefficient_and_residual_tolerance']
    pole_tolerance = cfg['frequency_bandwidth_agreement_hz']
    env_tolerance = settings['envelope_tolerance_db']
    trace_errors = {'windowed_samples': tsp.max_error(shaped, current['shaped']),
                    'raw_autocorrelation': tsp.max_error(raw, current['autocorrelation']),
                    'periodogram_db': dft_error}
    trace_limits = {'weighted_autocorrelation': pre_tolerance,
                    'coefficients': fit_tolerance, 'prediction_error': fit_tolerance,
                    'complex_roots': settings['complex_root_tolerance'],
                    'eligible_poles_hz': pole_tolerance, 'selection_hz': pole_tolerance,
                    'lpc_envelope_db': env_tolerance}
    difference = np.array(ref_zero['weighted_autocorrelation']) - np.array(ref_fixed['weighted_autocorrelation'])
    first = next((i for i, d in enumerate(difference) if abs(d) > pre_tolerance), None)
    first_coefficient = next((i for i, (a, b) in enumerate(zip(ref_fixed['coefficients'],
                                  ref_zero['coefficients'], strict=True)) if abs(a-b) > fit_tolerance), None)
    known_f2 = case['input']['known_f2_hz']
    errors = [v['fixed_selection']['f2'][0] - known_f2 if v['fixed_selection']['f2'] else None for v in variants]
    reduction = abs(errors[0]) - abs(errors[1]) if None not in errors else None
    checks = {
        'same_frame_and_preprocessing': all(len(current[k]) == len(a) for k, a in [('shaped', shaped), ('autocorrelation', raw)])
         and max(trace_errors['windowed_samples'], trace_errors['raw_autocorrelation']) <= pre_tolerance,
        'matches_saved_upstream': all(value is not None and value <= limit for value, limit in
            [(old_agreement['coefficients'], fit_tolerance), (old_agreement['prediction_error'], fit_tolerance),
             (old_agreement['poles_hz'], pole_tolerance), (old_agreement['fixed_selection_hz'], pole_tolerance),
             (old_agreement['envelope_db'], env_tolerance)]),
        'lag_zero_and_first_separation': first == 1 and difference[0] == 0.0 and first_coefficient == 1,
        'independent_fit_and_poles': all(value is not None and value <= trace_limits[key]
                                         for v in variants for key, value in v['errors'].items()),
        'independent_periodogram': dft_error <= settings['periodogram_tolerance_db'],
    }
    predictions = {
        'bias_reduces': reduction is not None and reduction >= settings['predicted_minimum_bias_reduction_hz'],
        'condition_number_rises': zero['condition_number_2'] > fixed['condition_number_2'],
    }
    (artifacts / 'spectra.json').write_text(json.dumps({'frequency_hz': grid.tolist(),
        'periodogram_db': periodogram.tolist(), 'lpc_db': [v['lpc_envelope_db'] for v in current['variants']]},
        separators=(',', ':')) + '\n')
    return {'checks': checks, 'hypotheses': predictions, 'comparison_to_saved': old_agreement,
            'trace_errors': trace_errors, 'first_weighted_lag_difference': first,
            'first_coefficient_difference': first_coefficient, 'weighted_lag_difference': difference.tolist(),
            'signed_f2_errors_hz': errors, 'absolute_bias_reduction_hz': reduction,
            'variants': variants, 'scipy': envelope.scipy.__version__}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    case = tsp.read(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True):
        raise ValueError('上流の作業ツリーが登録済みの固定版と一致しません')
    prior = tsp.open_run(case['baseline'], revision)
    design, design_file = held_out.saved_case(prior, known.CASE)
    held = tsp.open_run(design['held_out'], revision)
    registry, registry_file = held_out.saved_case(held, held_out.CASE)
    baseline, pilot = (tsp.open_run(registry[key], revision) for key in ('baseline', 'pilot'))
    cfg_payload, cfg_path = held_out.saved_case(baseline, tsp.CASE)
    pilot_payload, pilot_path = held_out.saved_case(pilot, envelope.CASE)
    cfg, pilot_settings = cfg_payload['measurement'], pilot_payload['measurement']
    wave = tsp.verified_path(prior, f"artifacts/{case['input']['variant']}.npy")
    summary = tsp.verified_path(prior, 'summary.json')
    observations = tsp.verified_path(prior, 'artifacts/upstream-envelopes.json')
    fs, order, frame, previous_f2, previous_rust = previous_window(
        case, design, tsp.read(summary), wave, tsp.read(observations))
    if (case['measurement']['lag_window_hz'] != [cfg['lag_window_hz'], 0]
            or fs != cfg['sample_rate_hz'] / cfg['decimation']
            or len(frame) != int(fs * cfg['frame_seconds'])):
        raise ValueError('先行のTSP計測と窓またはラグの設定が一致しません')
    inputs = [CASE, Path(__file__).resolve(), PROBE, design_file, registry_file, cfg_path, pilot_path,
              wave, summary, observations, Path(tsp.__file__), Path(envelope.__file__),
              Path(held_out.__file__), Path(known.__file__), UPSTREAM / LPC, UPSTREAM / tsp.TSP_SOURCE,
              UPSTREAM / 'crates/chimera/tests/golden_analysis.rs', UPSTREAM / 'Cargo.lock',
              WORKSPACE / 'tools/measure_uniform_tube.py', WORKSPACE / 'tools/measure_fan_crossing_allocations.py',
              WORKSPACE / 'tools/upstream_baseline.py']
    inputs.extend(root / 'manifest.json' for root, _ in (prior, held, baseline, pilot))
    return record_measurement(args.run_id, CASE, inputs, {
        'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision,
        'known_pole_reference': prior[0].name,
    }, lambda artifacts, execute: measure(case, cfg, frame, fs, order, previous_f2, previous_rust,
                                         pilot_settings, artifacts, execute),
        command=None, input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
