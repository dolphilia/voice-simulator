"""低速のピッチ変動を上流の時系列と独立したIIR計算に照合する。"""

import argparse
import json
from pathlib import Path
import re
import subprocess

import numpy as np
import scipy
from scipy.io import wavfile
from scipy.signal import lfilter

import measure_glottal_coupling as glottal
import measure_glottal_cycle as cycle
import measure_junction as reference
import measure_pcm_output as pcm
import measure_turbulence as random_reference
import measure_uniform_tube as shared
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE_IDS = ('glottal-pitch-drift', 'glottal-pitch-vibrato', 'glottal-pitch-voiced')


def independent_pitch(cfg, params, fs):
    """三つの低域フィルタを別々に計算し、ピッチ更新間の値を保持する。"""
    count, interval = (cfg[key] for key in ('sample_count', 'update_interval_samples'))
    ticks = len(range(0, count, interval))
    draws = np.fromiter(random_reference.mulberry32(cfg['drift_seed'], ticks * 12),
                        dtype=float, count=ticks * 12).reshape(ticks, 3, 4)
    excitation = (draws.sum(axis=-1) - 2) * 1.7320508
    poles = np.exp(-2 * np.pi * (0.3 * np.array([1, 3, 9])) / (fs / interval))
    streams = [lfilter([np.sqrt(1 - pole**2)], [1, -pole], values)
               for pole, values in zip(poles, excitation.T, strict=True)]
    drift = np.array([1, 0.5, 1 / 3]) @ streams / 1.4
    advance = params['vibrato_rate_hz'] * interval / fs * (1 + 0.04 * drift)
    phase = np.mod(np.cumsum(advance), 1)
    cents = params['vibrato_depth_cents'] * np.sin(2 * np.pi * phase) + params['drift_cents'] * drift
    frequency = params['f0_hz'] * np.exp(cents * np.log(2) / 1200)
    return np.repeat(frequency, interval)[:count]


def measure(case, case_path, artifacts, execute):
    cfg, params = case['measurement'], case['glottis']['params']
    fs, count, interval = case['network']['sample_rate_hz'], cfg['sample_count'], cfg['update_interval_samples']
    upstream_path = reference.capture_upstream(case, artifacts, execute, pcm.NATIVE_TEST)
    header, data = pcm.read_columns(artifacts / 'trace.csv', count)
    upper_header, upper = pcm.read_columns(upstream_path, count, len(header))
    if header != upper_header:
        raise ValueError('上流と候補の観測列が一致しません')
    comparisons = {key: shared.compare_series(data[key], upper[key], cfg['upstream_series_peak_relative_error_lt'])
                   for key in header[1:]}
    frequency = data['glottal_f0_hz']
    expected_frequency = independent_pitch(cfg, params, fs)
    f0_check = shared.compare_series(frequency, expected_frequency, cfg['independent_f0_relative_error_lt'])
    changes = np.flatnonzero(np.diff(frequency)) + 1
    expected_changes = np.arange(interval, count, interval)

    phase = data['glottal_phase']
    raw_delta = np.diff(phase, prepend=0.0)
    wrapped = raw_delta < 0
    wraps = int(np.count_nonzero(wrapped))
    index = np.cumsum(wrapped)
    period_scale, amplitude_scale = cycle.cycle_factors(params, wraps)
    before = np.r_[0, index[:-1]]
    expected_delta = (expected_frequency / fs) / period_scale[before]
    phase_error = float(np.max(np.abs(raw_delta + wrapped - expected_delta)))
    expected_area, expected_voicing, _ = glottal.reconstruct_source(
        case, data['glottal_pressure_drop_dyn_cm2'], data.get('breath_effort'),
        phase=phase, amplitude_scale=amplitude_scale[index])
    area = shared.compare_series(data['glottal_area_cm2'], expected_area, cfg['independent_area_peak_relative_error_lt'])
    voicing = shared.compare_series(data['glottal_voicing'], expected_voicing,
                                    cfg['independent_area_peak_relative_error_lt'])
    checks = {
        'upstream_time_series': all(value['status'] for value in comparisons.values()),
        'independent_f0': f0_check['status'],
        'f0_updates_exactly_on_control_ticks': np.array_equal(changes, expected_changes),
        'phase_increment_uses_modulated_f0': phase_error < cfg['phase_increment_max_absolute_error_lt'],
        'enough_wraps': wraps >= cfg['minimum_wraps'],
        'independent_area': area['status'],
        'independent_voicing': voicing['status'],
    }
    lo, hi = cfg['analysis_window_samples']
    cents = 1200 * np.log2(frequency[lo:hi] / params['f0_hz'])
    result = {
        'checks': checks, 'control_updates': int(changes.size) + 1,
        'first_f0_hz': float(frequency[0]), 'wraps': wraps,
        'pitch_std_cents': float(np.std(cents)), 'pitch_peak_to_peak_cents': float(np.ptp(cents)),
        'max_phase_increment_absolute_error': phase_error,
        'upstream_time_series': comparisons, 'independent_f0': f0_check,
        'independent_area': area, 'independent_voicing': voicing,
    }
    if params['vibrato_depth_cents'] == 0:
        checks['drift_is_observable'] = result['pitch_std_cents'] > cfg['minimum_drift_std_cents']
    if params['vibrato_depth_cents'] > 0 and params['drift_cents'] == 0:
        crossings = np.flatnonzero((cents[1:] >= 0) & (cents[:-1] < 0)) + 1
        rate = float(fs / np.mean(np.diff(crossings))) if crossings.size >= 2 else None
        regular_phase = (np.arange(lo, hi) // interval + 1) * interval / fs * params['vibrato_rate_hz']
        regular = params['vibrato_depth_cents'] * np.sin(2 * np.pi * regular_phase)
        residual = float(np.sqrt(np.mean((cents - regular)**2)))
        rate_lo, rate_hi = cfg['vibrato_rate_interval_hz']
        checks.update(
            vibrato_depth_is_observable=result['pitch_peak_to_peak_cents'] > cfg['minimum_vibrato_peak_to_peak_cents'],
            vibrato_rate=rate is not None and rate_lo < rate < rate_hi,
            vibrato_phase_wanders=residual > cfg['minimum_error_from_regular_vibrato_rms_cents'],
        )
        result.update(vibrato_rate_hz=rate, error_from_regular_vibrato_rms_cents=residual)
    if 'pcm' in case:
        rendered = pcm.render_blocks(case_path, cfg, artifacts, execute)
        hashes = {str(block): [sha256(path) for path in paths] for block, paths in rendered.items()}
        checks['pcm_is_block_invariant'] = all(value == next(iter(hashes.values())) for value in hashes.values())
        wav, _ = next(iter(rendered.values()))
        rate, signal = wavfile.read(wav)
        expected_frames = count * case['pcm']['sample_rate_hz'] // fs
        peak = float(np.max(np.abs(signal)))
        checks['pcm_is_finite_nonzero_f32'] = (
            rate == case['pcm']['sample_rate_hz'] and signal.shape == (expected_frames,) and
            signal.dtype == np.float32 and bool(np.isfinite(signal).all()) and peak > 0)
        result.update(pcm_block_hashes=hashes, pcm_peak=peak, pcm_frames=expected_frames)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('case', choices=CASE_IDS)
    args = parser.parse_args()
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]*', args.run_id):
        parser.error('実行IDは英数字で始め、英数字、ハイフン、アンダースコアで指定してください')
    case_path = WORKSPACE / 'cases' / f'{args.case}.json'
    case = json.loads(case_path.read_text())
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        raise ValueError('変更のない固定上流版が必要です')

    def measure_run(artifacts, execute):
        return measure(case, case_path, artifacts, execute)

    modules = (reference, shared, glottal, cycle, random_reference, pcm)
    sources = [reference.PROBE, Path(__file__).resolve(), *(Path(module.__file__) for module in modules),
               WORKSPACE / 'tools/upstream_baseline.py', *shared.candidate_sources()]
    details = {'upstream_revision': revision, 'case_id': case['id'], 'scipy_version': scipy.__version__}
    return shared.record_measurement(args.run_id, case_path, [case_path, *sources], details, measure_run)


if __name__ == '__main__':
    raise SystemExit(main())
