"""声門の周期境界と変動倍率を上流と独立計算に照合する。"""

import argparse
import json
from pathlib import Path
import re
import subprocess

import numpy as np
import scipy
from scipy.io import wavfile

import measure_glottal_coupling as glottal
import measure_junction as reference
import measure_pcm_output as pcm
import measure_uniform_tube as shared
import measure_turbulence as random_reference
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


NATIVE_TEST = ('lung_port', 'folds_held_apart_meet_for_less_of_the_cycle')
CREATURE_TEST = ('engine', 'the_creatures_hold_at_the_lighter_rate')
CASE_IDS = ('glottal-cycle-jitter', 'glottal-cycle-shimmer', 'glottal-cycle-voiced',
            'glottal-diplophonia-control', 'glottal-diplophonia-fixed', 'glottal-diplophonia-voiced',
            'glottal-chaos-fixed-point', 'glottal-chaos-period-2', 'glottal-chaos-period-4',
            'glottal-chaos-aperiodic', 'glottal-chaos-voiced')


def logistic_orbit(rate, cycles):
    """初回の折り返しから始まる状態列を独立に反復する。"""
    initial = 0.37
    state = initial
    states = np.empty(cycles)
    for i in range(cycles):
        next_state = (rate * state) * (1.0 - state)
        state = next_state if 0.0 < next_state < 1.0 else initial
        states[i] = state
    return states


def cycle_factors(params, cycles):
    """周回ごとに8個引く一様乱数を、周期長用・面積振幅用に分ける。"""
    draw = np.fromiter(random_reference.mulberry32(params['cycle_seed'], 8 * cycles),
                       dtype=float, count=8 * cycles).reshape(cycles, 2, 4)
    fluctuations = (draw.sum(axis=-1) - 2) * 1.7320508
    period = 1 + params['jitter'] * fluctuations[:, 0]
    amplitude = 1 + params['shimmer'] * fluctuations[:, 1]
    amount = params.get('diplophonia', 0.0)
    if amount:
        odd = np.arange(cycles) % 2 == 0
        period += np.where(odd, 0.08, -0.08) * amount
        amplitude[odd] -= 0.35 * amount
    chaos = params.get('chaos', 0.0)
    if chaos:
        deviations = logistic_orbit(2.9 + 1.1 * chaos, cycles) - 0.5
        period += 0.45 * chaos * deviations
        amplitude += 1.1 * chaos * deviations
    return np.r_[1.0, np.clip(period, 0.55, 1.8)], np.r_[1.0, np.maximum(0.12, amplitude)]


def measure_chaos(case, phase, boundaries, steady, artifacts):
    cfg, params = case['measurement']['chaos_map'], case['glottis']['params']
    chaos = params['chaos']
    rate = 2.9 + 1.1 * chaos
    nominal_increment = params['f0_hz'] / case['network']['sample_rate_hz']
    # 折り返しの次のサンプルから新周期の位相増分を取り、写像の状態を逆算する。
    start = boundaries[:-1]
    period_scale = nominal_increment / (phase[start + 1] - phase[start])
    base_scale, _ = cycle_factors({**params, 'chaos': 0.0}, len(start))
    measured_state = 0.5 + (period_scale - base_scale[1:]) / (0.45 * chaos)
    reference_state = logistic_orbit(rate, len(start))
    maximum_error = float(np.max(np.abs(measured_state - reference_state)))
    np.savetxt(artifacts / 'chaos-orbit.csv',
               np.column_stack((np.arange(1, len(start) + 1), start, period_scale, measured_state, reference_state)),
               delimiter=',', fmt=('%d', '%d', '%.17g', '%.17g', '%.17g'), comments='',
               header='cycle,start_sample,observed_period_scale,state_from_phase,independent_state')
    tail = measured_state[steady]
    if len(tail) <= max(map(int, cfg['lag_rms_intervals'])):
        raise ValueError('写像の周期性を測るための完全な周期が不足しています')
    lag_rms = {}
    lag_checks = {}
    for lag, (lo, hi) in cfg['lag_rms_intervals'].items():
        k = int(lag)
        lag_rms[lag] = float(np.sqrt(np.mean((tail[k:] - tail[:-k])**2)))
        lag_checks[f'chaos_lag_{lag}_rms'] = lo <= lag_rms[lag] <= hi
    slope = np.abs(rate * (1 - 2 * tail))
    lyapunov = float(np.mean(np.log(slope))) if np.all(slope > 0) else None
    lo, hi = cfg['lyapunov_mean_interval']
    checks = {
        'chaos_state_from_phase': maximum_error < cfg['state_max_absolute_error'],
        'chaos_lyapunov_mean': lyapunov is not None and lo <= lyapunov <= hi,
        **lag_checks,
    }
    result = {
        'rate': rate, 'first_state': float(measured_state[0]), 'max_state_error': maximum_error,
        'steady_state_min_max': [float(np.min(tail)), float(np.max(tail))],
        'steady_state_mean': float(np.mean(tail)), 'lag_rms': lag_rms, 'lyapunov_mean': lyapunov,
    }
    if 'steady_state_mean_interval' in cfg:
        lo, hi = cfg['steady_state_mean_interval']
        checks['chaos_steady_state_mean'] = lo <= result['steady_state_mean'] <= hi
    return checks, result


def measure_alternation(case, data, phase, boundaries, steady, peaks):
    cfg = case['measurement']['alternation']
    params = case['glottis']['params']
    odd = np.arange(1, len(boundaries))[steady] % 2 == 1
    lengths = np.diff(boundaries)[steady]
    magnitudes = peaks - params['chink_cm2']
    if not np.any(odd) or np.all(odd) or np.mean(magnitudes[~odd]) <= 0:
        raise ValueError('偶数周期と奇数周期の面積ピークを確認できません')
    period_odd, period_even = float(np.mean(lengths[odd])), float(np.mean(lengths[~odd]))
    peak_ratio = float(np.mean(magnitudes[odd]) / np.mean(magnitudes[~odd]))
    period_difference = period_odd - period_even
    f0 = params['f0_hz']
    f0_error = float(np.max(np.abs(data['glottal_f0_hz'] - f0)))
    first = int(boundaries[0])
    wrap_lo, wrap_hi = cfg['first_wrap_sample_interval']
    peak_lo, peak_hi = cfg['peak_ratio_interval']
    checks = {
        'initial_wrap_uses_nominal_period': wrap_lo <= first <= wrap_hi,
        'f0_reports_nominal_frequency': f0_error < cfg['nominal_f0_max_absolute_error_hz'],
        'odd_even_period_difference': abs(period_difference - cfg['expected_odd_minus_even_period_samples']) <
        cfg['period_difference_max_error_samples'],
        'odd_even_peak_ratio': peak_lo <= peak_ratio <= peak_hi,
    }
    result = {
        'odd_mean_period_samples': period_odd, 'even_mean_period_samples': period_even,
        'odd_minus_even_period_samples': period_difference, 'odd_to_even_area_peak_ratio': peak_ratio,
        'nominal_f0_max_absolute_error_hz': f0_error,
    }
    if 'subharmonic_to_f0_ratio_interval' in cfg:
        lo, hi = case['measurement']['analysis_window_samples']
        area = data['glottal_area_cm2'][lo:hi]
        time = np.arange(len(area)) / case['network']['sample_rate_hz']
        freqs = f0 * np.array([0.5, 1.0])
        windowed = (area - np.mean(area)) * np.hanning(len(area))
        magnitudes = np.abs(np.exp(-2j * np.pi * freqs[:, None] * time) @ windowed)
        ratio = float(magnitudes[0] / magnitudes[1]) if magnitudes[1] > 0 else None
        low, high = cfg['subharmonic_to_f0_ratio_interval']
        checks['subharmonic_to_f0_ratio'] = ratio is not None and low <= ratio <= high
        result['subharmonic_to_f0_ratio'] = ratio
    if 'first_wrap_area_difference_if_delayed_gt_cm2' in cfg:
        delayed, _, _ = glottal.reconstruct_source(
            case, data['glottal_pressure_drop_dyn_cm2'][:first + 1], phase=phase[:first + 1])
        difference = float(abs(data['glottal_area_cm2'][first] - delayed[-1]))
        checks['first_wrap_uses_new_amplitude'] = difference > cfg['first_wrap_area_difference_if_delayed_gt_cm2']
        result['first_wrap_area_difference_if_delayed_cm2'] = difference
    return checks, result


def measure(case, case_path, artifacts, execute):
    cfg = case['measurement']
    count = cfg['sample_count']
    params = case['glottis']['params']
    nominal_period = case['network']['sample_rate_hz'] / params['f0_hz']
    upstream_path = reference.capture_upstream(case, artifacts, execute,
                                               CREATURE_TEST if 'chaos_map' in cfg else NATIVE_TEST)
    header, data = pcm.read_columns(artifacts / 'trace.csv', count)
    upper_header, upper = pcm.read_columns(upstream_path, count, len(header))
    if header != upper_header:
        raise ValueError('上流と候補の観測列が一致しません')
    comparisons = {key: shared.compare_series(data[key], upper[key], cfg['upstream_series_peak_relative_error_lt'])
                   for key in header[1:]}

    phase = data['glottal_phase']
    raw_delta = np.diff(phase, prepend=0.0)
    wrapped = raw_delta < 0
    boundaries = np.flatnonzero(wrapped)
    if boundaries.size < 2:
        raise ValueError('声門の周期境界を二つ以上観測できません')
    index = np.cumsum(wrapped)
    reference_length, reference_amplitude = cycle_factors(params, len(boundaries))
    before = np.r_[0, index[:-1]]
    expected_delta = 1 / (nominal_period * reference_length[before])
    absolute_error = np.abs(raw_delta + wrapped - expected_delta)
    phase_window = slice(*cfg['phase_window_samples'])
    phase_increment_error = float(np.max(absolute_error[phase_window]))

    starts, ends = boundaries[:-1], boundaries[1:]
    length = ends - starts
    predicted = nominal_period * reference_length[1:len(boundaries)]
    phase_lo, phase_hi = cfg['phase_window_samples']
    measured_periods = (starts >= phase_lo) & (ends <= phase_hi)
    if not np.any(measured_periods):
        raise ValueError('位相の測定窓に完全な周期がありません')
    period_error = float(np.max(np.abs(length[measured_periods] - predicted[measured_periods])))
    area = data['glottal_area_cm2']
    area_expected, voicing_expected, _ = glottal.reconstruct_source(
        case, data['glottal_pressure_drop_dyn_cm2'], data.get('breath_effort'),
        phase=phase, amplitude_scale=reference_amplitude[index])
    area_check = shared.compare_series(area, area_expected, cfg['independent_area_peak_relative_error_lt'])
    voicing_check = shared.compare_series(data['glottal_voicing'], voicing_expected,
                                          cfg['independent_area_peak_relative_error_lt'])
    lower, upper_bound = cfg['analysis_window_samples']
    steady = (starts >= lower) & (ends <= upper_bound)
    if not np.any(steady):
        raise ValueError('安定発声の測定窓に完全な周期がありません')
    period_std = float(np.std(length[steady]))
    peaks = np.array([np.max(area[a:b]) for a, b in zip(starts[steady], ends[steady], strict=True)])
    if np.mean(peaks) <= 0:
        raise ValueError('面積パルスのピークを確認できません')
    relative_std = float(np.std(peaks) / np.mean(peaks))
    voicing_mean = float(np.mean(data['glottal_voicing'][lower:upper_bound]))

    checks = {
        'upstream_time_series': all(value['status'] for value in comparisons.values()),
        'seeded_phase_increment': phase_increment_error < cfg['phase_increment_max_absolute_error_lt'],
        'cycles_match_expected_lengths': period_error < cfg['cycle_lengths_max_absolute_error_samples'],
        'seeded_area_pulse': area_check['status'],
        'pressure_driven_voicing': voicing_check['status'] and voicing_mean > cfg['minimum_analysis_voicing'],
        'enough_complete_cycles': int(np.count_nonzero(steady)) >= cfg['minimum_complete_cycles'],
    }
    result = {
        'checks': checks, 'seed': params['cycle_seed'], 'first_wrap_sample': int(boundaries[0]),
        'complete_cycles_measured': int(np.count_nonzero(steady)), 'mean_voicing': voicing_mean,
        'period_std_samples': period_std, 'peak_area_relative_std': relative_std,
        'max_phase_increment_absolute_error': phase_increment_error,
        'max_period_absolute_error_samples': period_error,
        'upstream_time_series': comparisons, 'independent_area': area_check, 'independent_voicing': voicing_check,
    }
    if 'chaos_map' in cfg:
        additional_checks, result['chaos_map'] = measure_chaos(case, phase, boundaries, steady, artifacts)
        checks.update(additional_checks)
    elif 'alternation' in cfg:
        additional_checks, result['alternation'] = measure_alternation(case, data, phase, boundaries, steady, peaks)
        checks.update(additional_checks)
    else:
        checks.update(
            period_effect=(period_std > cfg['jitter_period_std_min_samples'] if params['jitter'] else
                           period_std < cfg['constant_period_std_max_samples']),
            amplitude_effect=(relative_std > cfg['shimmer_area_peak_relative_std_min'] if params['shimmer'] else
                              relative_std < cfg['steady_area_peak_relative_std_max']),
        )
    if 'pcm' in case:
        rendered = pcm.render_blocks(case_path, cfg, artifacts, execute)
        hashes = {str(block): [sha256(path) for path in paths] for block, paths in rendered.items()}
        checks['pcm_is_block_invariant'] = all(value == next(iter(hashes.values())) for value in hashes.values())
        wav, _ = next(iter(rendered.values()))
        rate, signal = wavfile.read(wav)
        expected_frames = count * case['pcm']['sample_rate_hz'] // case['network']['sample_rate_hz']
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

    sources = [reference.PROBE, Path(__file__).resolve(), Path(reference.__file__), Path(shared.__file__),
               Path(glottal.__file__), Path(random_reference.__file__), Path(pcm.__file__),
               WORKSPACE / 'tools/upstream_baseline.py', *shared.candidate_sources()]
    details = {'upstream_revision': revision, 'case_id': case['id'], 'scipy_version': scipy.__version__}
    return shared.record_measurement(args.run_id, case_path, [case_path, *sources], details, measure_run)


if __name__ == '__main__':
    raise SystemExit(main())
