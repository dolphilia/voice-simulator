"""固定した /ɔ/ のLPC入力を12〜18次で解析し、公開ピークが変わる段を照合する。"""

import argparse
import json
from pathlib import Path
import re
import subprocess

import numpy as np
import scipy
from scipy.linalg import toeplitz

from measure_fan_crossing_allocations import run_manifest, verified_path
from measure_tsp_lpc_order_recordings import compare_raw_roots
import measure_tsp_lpc_pre_emphasis as upstream_probe
import measure_vowel_open_o_lpc_matched as matched
from measure_uniform_tube import record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/vowel-open-o-lpc-orders.json'
ROOT = WORKSPACE.parents[2]


def input_paths(study):
    ref = study['reference']
    run, manifest = run_manifest(ref['run'], ref['case'], study['upstream_revision'])
    manifest_path = run / 'manifest.json'
    if manifest['status'] != 'pass' or sha256(manifest_path) != ref['manifest_sha256']:
        raise ValueError('保存された照合実行が登録値と異なります')
    case, = (row for row in manifest['inputs'] if row['path'].endswith(f'/cases/{ref["case"]}.json'))
    path = run / manifest['source_snapshot'] / case['path']
    if sha256(path) != case['sha256']:
        raise ValueError('保存されたケース定義を照合できません')
    paths = {'manifest': manifest_path, 'definition': path}
    for name in ('summary.json', 'artifacts/analysis-windows.npz', 'artifacts/upstream-vowel-sequence.wav',
                 'artifacts/upstream-analysis.json'):
        paths[Path(name).name] = verified_path((run, manifest), name)
    return paths


def saved_window(study, paths):
    cfg = study['measurement']
    base = matched.read(paths['definition'])['measurement']
    waves = matched.read_wave(paths['upstream-vowel-sequence.wav'], base, cfg['wave'])
    expected = matched.read(paths['summary.json'])['conditions']
    endpoints = [next(row for row in expected if row['index'] == index) for index in cfg['endpoint_window_indices']]
    raw, window = matched.reconstruct_frame(
        waves, cfg['wave'], (cfg['source_start_frame_from_vowel'], cfg['source_frame_count'], cfg['analysis_rate_hz'],
                            cfg['decimator'], cfg['orders'][0]), base)
    if len(window) != cfg['analysis_frame_count'] or base['source_rate_hz'] != cfg['source_rate_hz'] or base['ipa'] != cfg['ipa']:
        raise ValueError('分析窓の長さ、レート、または母音が事前登録と異なります')
    with np.load(paths['analysis-windows.npz'], allow_pickle=False) as frames:
        for expected_order, row in zip((cfg['orders'][0], cfg['orders'][-1]), endpoints, strict=True):
            index = row['index']
            metadata = [row[key] for key in ('wave', 'start_frame', 'duration_frames', 'analysis_rate_hz', 'decimator', 'order')]
            expected_metadata = [cfg['wave'], cfg['source_start_frame_from_vowel'], cfg['source_frame_count'],
                                 cfg['analysis_rate_hz'], cfg['decimator'], expected_order]
            if metadata != expected_metadata or not np.array_equal(frames[f'raw_{index}'].view('<u8'), raw.view('<u8')) \
                    or not np.array_equal(frames[f'lpc_{index}'].view('<u8'), window.view('<u8')):
                raise ValueError(f'先行実行の分析窓とPCMからの再計算が一致しません ({index})')
    return window, endpoints


def envelope_grid(cfg):
    start, end, step = cfg['envelope_grid_hz']
    return np.arange(start, end + step, step)


def raw_poles(roots, rate, cfg):
    result = []
    for re_part, im_part in roots:
        if im_part <= cfg['real_axis_imag_tolerance']:
            continue
        root = complex(re_part, im_part)
        frequency = float(np.angle(root) * rate / (2 * np.pi))
        bandwidth = float(-np.log(abs(root)) * rate / np.pi)
        result.append([frequency, bandwidth])
    return sorted(result)


def selected(poles, rate, cfg, max_bandwidth):
    return [pole for pole in poles if cfg['min_freq_hz'] <= pole[0] < rate/2 - cfg['nyquist_guard_hz']
            and pole[1] <= max_bandwidth]


def pole_error(a, b):
    if len(a) != len(b):
        return None
    return float(np.max(abs(np.asarray(a) - np.asarray(b)))) if len(a) else 0.0


def inspect_order(order, rust, lags, windowed, emphasized, cfg, grid):
    rate = cfg['analysis_rate_hz']
    weighted = lags[:order+1] * np.exp(-0.5 * (2 * np.pi * cfg['lag_window_hz'] * np.arange(order+1) / rate)**2)
    matrix = toeplitz(weighted[:-1])
    matrix.flat[::order+1] = weighted[0] * (1+1e-9) + 1e-30
    coefficients = np.r_[1.0, np.linalg.solve(matrix, -weighted[1:])]
    prediction_error = matrix[0, 0] + coefficients[1:] @ weighted[1:]
    roots = np.roots(coefficients)
    hz_error, distance, axes = compare_raw_roots(rust['roots'], roots, rate)
    raw = raw_poles(rust['roots'], rate, cfg)
    independent = raw_poles(zip(roots.real, roots.imag), rate, cfg)
    public = [pole for pole in rust['poles'] if pole[0] < rate/2 - cfg['nyquist_guard_hz']]
    response = np.polynomial.polynomial.polyval(np.exp(-2j * np.pi * grid / rate), coefficients)
    envelope = 10*np.log10(prediction_error / (np.abs(response)**2 + 1e-30))
    err = lambda a, b: float(np.max(abs(np.asarray(a) - np.asarray(b))))
    errors = {'pre_emphasis': err(emphasized, rust['emphasized']), 'hamming': err(windowed, rust['shaped']),
              'autocorrelation': err(lags[:order+1], rust['autocorrelation']),
              'weighted_autocorrelation': err(weighted, rust['weighted_autocorrelation']),
              'coefficients': err(coefficients, rust['coefficients']),
              'prediction_error': abs(float(prediction_error) - rust['prediction_error']),
              'all_complex_roots': distance, 'all_roots_hz': hz_error,
              'envelope_db': err(envelope, rust['lpc_envelope_db']),
              'public_poles_hz': pole_error(selected(independent, rate, cfg, cfg['max_bandwidth_hz']), public),
              'cap_replay_hz': pole_error(selected(raw, rate, cfg, cfg['max_bandwidth_hz']), public)}
    limits = {key: cfg['absolute_sample_and_correlation_tolerance'] for key in
              ('pre_emphasis', 'hamming', 'autocorrelation', 'weighted_autocorrelation')}
    limits.update(coefficients=cfg['coefficient_tolerance'], prediction_error=cfg['coefficient_tolerance'],
                  all_complex_roots=cfg['complex_root_tolerance'], all_roots_hz=cfg['formant_tolerance_hz'],
                  envelope_db=cfg['envelope_tolerance_db'], public_poles_hz=cfg['formant_tolerance_hz'],
                  cap_replay_hz=cfg['formant_tolerance_hz'])
    relaxed = selected(raw, rate, cfg, cfg['diagnostic_max_bandwidth_hz'])
    unlimited = selected(raw, rate, cfg, float('inf'))
    by_band = {name: {'raw': [p for p in raw if low <= p[0] < high],
                      'public': [p for p in public if low <= p[0] < high],
                      'diagnostic': [p for p in relaxed if low <= p[0] < high]}
               for name, (low, high) in cfg['bands_hz'].items()}
    stats = {'order': order, 'raw_poles': raw, 'public_poles': public,
             'nyquist_excluded': [pole for pole in rust['poles'] if pole not in public],
             'real_axis_rounding_pairs': axes, 'public_with_diagnostic_cap': relaxed,
             'lowest_without_bandwidth_cap': unlimited[0] if unlimited else None, 'bands': by_band, 'errors': errors}
    return stats, all(errors[key] is not None and errors[key] <= limit for key, limit in limits.items())


def reflection_step(before, after):
    previous = np.array(before['coefficients'])
    current = np.array(after['coefficients'])
    order = len(previous)
    weighted = after['weighted_autocorrelation']
    acc = weighted[order] + np.dot(previous[1:], weighted[1:order][::-1])
    k = -acc / before['prediction_error']
    expected = np.r_[1.0, previous[1:] + k*previous[:0:-1], k]
    error = before['prediction_error'] * (1-k*k)
    shared = all(np.array_equal(after[field][:order], before[field]) for field in
                 ('autocorrelation', 'weighted_autocorrelation'))
    return {'from_order': order-1, 'to_order': order, 'reflection_coefficient': float(k), 'shared_lags_match': shared,
            'coefficient_update_error': float(abs(expected-current).max()),
            'prediction_error_update_error': abs(float(error) - after['prediction_error']),
            'largest_change_in_shared_predictor_coefficients': float(abs(current[1:-1] - previous[1:]).max())}


def analyze(study, paths, out):
    cfg = study['measurement']
    window, endpoints = saved_window(study, paths)
    grid = envelope_grid(cfg)
    emphasized = np.r_[window[0], window[1:] - cfg['pre_emphasis']*window[:-1]]
    windowed = emphasized * np.hamming(len(window))
    center = len(windowed)-1
    lags = np.correlate(windowed, windowed, 'full')[center:center+cfg['orders'][-1]+1]
    fixed = []
    for name in upstream_outputs(study):
        observation, = matched.read(out / name)
        fixed.append(observation)
    observations, checked = zip(*(inspect_order(order, obs, lags, windowed, emphasized, cfg, grid)
                                  for order, obs in zip(cfg['orders'], fixed, strict=True)), strict=True)
    steps = [reflection_step(a, b) for a, b in zip(fixed[:-1], fixed[1:], strict=True)]
    old = matched.read(paths['upstream-analysis.json'])
    endpoint_root_error = [
        compare_raw_roots(obs['roots'], np.array([complex(re, im) for re, im in old[str(row['index'])]['roots']]),
                          cfg['analysis_rate_hz'])[1]
        for obs, row in zip((fixed[0], fixed[-1]), endpoints, strict=True)]
    endpoint_pole_error = [pole_error(obs['public_poles'], row['upstream_formants_hz_and_bw_hz'])
                           for obs, row in zip((observations[0], observations[-1]), endpoints, strict=True)]
    same_input = bool(np.array_equal(np.load(out / 'lpc-window.npy', allow_pickle=False).view('<u8'), window.view('<u8')))
    lag_prefixes = all(step['shared_lags_match'] for step in steps)
    lowest12, lowest18 = (row['public_poles'][0][0] for row in (observations[0], observations[-1]))
    no_cap12, no_cap18 = (row['lowest_without_bandwidth_cap'][0] for row in (observations[0], observations[-1]))
    first_all = next((row['order'] for row in observations if all(band['public'] for band in row['bands'].values())), None)
    third12, third18 = (row['bands']['third'] for row in (observations[0], observations[-1]))
    checks = {
        'identical_saved_input_reconstructed': same_input,
        'every_order_matches_independent_lpc': all(checked) and len(observations) == len(cfg['orders']),
        'adjacent_prediction_updates_match': lag_prefixes and all(
            step['coefficient_update_error'] < cfg['coefficient_tolerance']
            and step['prediction_error_update_error'] < cfg['coefficient_tolerance'] for step in steps),
        'archived_endpoints_reproduced': all(x < cfg['complex_root_tolerance'] for x in endpoint_root_error)
        and all(x is not None and x < cfg['formant_tolerance_hz'] for x in endpoint_pole_error),
    }
    hypotheses = {
        'shared_lags_stay_equal': lag_prefixes and all(step['largest_change_in_shared_predictor_coefficients'] > 0 for step in steps),
        'lowest_root_moves_with_or_without_bandwidth_cap': min(abs(lowest18-lowest12), abs(no_cap18-no_cap12)) >= cfg['large_shift_hz'],
        'mid_band_wide_root_at_low_order_is_excluded_by_bandwidth': bool(
            third12['raw'] and not third12['public'] and third12['diagnostic'] and third18['public']),
        'intermediate_order_can_recover_all_three_bands': any(
            all(band['public'] for band in row['bands'].values()) for row in observations[1:-1]),
    }
    return {'checks': checks, 'hypotheses': hypotheses, 'orders': list(observations), 'adjacent_steps': steps,
            'first_order_with_all_three_bands': first_all,
            'endpoints_lowest_shift_hz': lowest18-lowest12, 'endpoints_no_cap_lowest_shift_hz': no_cap18-no_cap12,
            'endpoint_max_complex_root_errors': endpoint_root_error, 'endpoint_max_public_errors_hz': endpoint_pole_error}


def upstream_outputs(study):
    return [f'upstream-pre-emphasis-{i:02d}.json' for i, _ in enumerate(study['measurement']['orders'])]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', args.run_id):
        parser.error('英数字で始まる実行IDを指定してください')
    study = matched.read(CASE)
    cfg = study['measurement']
    rev = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if rev != study['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    paths = input_paths(study)

    def measure(out, execute):
        frame, _ = saved_window(study, paths)
        np.save(out / 'lpc-window.npy', frame, allow_pickle=False)
        upstream_probe.run_probes([(frame, order) for order in cfg['orders']], cfg['analysis_rate_hz'],
                                  envelope_grid(cfg), out, execute, coefficients=[cfg['pre_emphasis']],
                                  formant_limits=(cfg['min_freq_hz'], cfg['max_bandwidth_hz']))
        return analyze(study, paths, out)

    inputs = [CASE, *paths.values(), Path(__file__), Path(upstream_probe.__file__), upstream_probe.PROBE,
              Path(matched.__file__), Path(matched.vowel.__file__), Path(matched.vowel.shared.__file__),
              WORKSPACE / 'tools/measure_tsp_lpc_order_recordings.py',
              UPSTREAM / 'crates/chimera-cli/src/render.rs', UPSTREAM / 'crates/chimera/src/analysis/lpc.rs',
              UPSTREAM / 'crates/chimera/tests/golden_analysis.rs']
    details = {'case_id': study['id'], 'case_revision': study['revision'], 'upstream_revision': rev,
               'scipy_version': scipy.__version__}
    return record_measurement(args.run_id, CASE, inputs, details, measure, command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
