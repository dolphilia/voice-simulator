"""ボーカルフライの周期と面積パルスを固定上流と独立計算に照合する。"""

import argparse
import json
from pathlib import Path
import re
import subprocess

import numpy as np
import scipy
from scipy.signal import find_peaks

import measure_glottal_coupling as glottal
import measure_junction as reference
import measure_pcm_output as telemetry
import measure_uniform_tube as shared
from upstream_baseline import UPSTREAM, WORKSPACE


CASES = ('glottal-fry-control', 'glottal-fry-threshold', 'glottal-fry-strong',
         'glottal-fry-low-f0', 'glottal-fry-overlap')


def measure(case, artifacts, execute):
    cfg = case['measurement']
    count = cfg['sample_count']
    fs = case['network']['sample_rate_hz']
    upstream_path = reference.capture_upstream(case, artifacts, execute, glottal.NATIVE_TEST)
    columns, data = telemetry.read_columns(artifacts / 'trace.csv', count)
    upper_columns, upper = telemetry.read_columns(upstream_path, count, len(columns))
    if columns != upper_columns:
        raise ValueError('上流と候補の観測列が一致しません')
    comparisons = {col: shared.compare_series(data[col], upper[col], cfg['upstream_series_peak_relative_error_lt'])
                   for col in columns[1:]}

    phase = data['glottal_phase']
    expected_f0 = cfg['expected_f0_hz']
    expected_area, expected_gate, expected_phase = glottal.reconstruct_source(
        case, data['glottal_pressure_drop_dyn_cm2'])
    area_tol = cfg['independent_area_peak_relative_error_lt']
    area = data['glottal_area_cm2']
    area_check = shared.compare_series(area, expected_area, area_tol)
    voicing = data['glottal_voicing']
    gate_check = shared.compare_series(voicing, expected_gate, area_tol)
    f0_error = float(np.max(np.abs(data['glottal_f0_hz'] - expected_f0)))
    phase_error = float(np.max(np.abs(np.exp(2j * np.pi * (phase - expected_phase)) - 1)))

    lo, hi = cfg['analysis_window_samples']
    wraps = np.flatnonzero(np.diff(phase) < 0) + 1
    wraps = wraps[(lo <= wraps) & (wraps <= hi)]
    if wraps.size < 2:
        raise ValueError('測定区間で完全な声門周期を観測できません')
    lengths = np.diff(wraps)
    period_error = float(np.max(np.abs(lengths - fs / expected_f0)))
    stable_gate = float(np.min(voicing[wraps[0]:wraps[-1]]))
    pulse = area - case['glottis']['params']['chink_cm2']
    opened = pulse > cfg['area_open_threshold_cm2']
    open_fraction = float(np.mean(opened[wraps[0]:wraps[-1]]))
    expected_peaks = np.asarray(cfg['expected_peak_phases'])
    secondary_search_phase = cfg.get('secondary_opening_search_phase')

    peak_counts = []
    peak_phase_errors = []
    secondary_openings = []
    secondary_ratios = []
    for start, end in zip(wraps[:-1], wraps[1:], strict=True):
        peaks, _ = find_peaks(pulse[start:end], height=cfg['peak_min_above_chink_cm2'])
        peak_counts.append(peaks.size)
        if peaks.size == expected_peaks.size:
            peak_phase_errors.append(float(np.max(np.abs(phase[start + peaks] - expected_peaks))))
            if peaks.size == 2:
                secondary_ratios.append(float(pulse[start + peaks[1]] / pulse[start + peaks[0]]))
        if secondary_search_phase is not None:
            indices = np.flatnonzero(opened[start:end] & (phase[start:end] >= secondary_search_phase))
            if indices.size:
                secondary_openings.append(float(phase[start + indices[0]]))

    peak_error = max(peak_phase_errors, default=None)
    checks = {
        'upstream_time_series': all(item['status'] for item in comparisons.values()),
        'fry_f0': f0_error < cfg['f0_max_absolute_error_hz'],
        'independent_phase': phase_error < cfg['phase_turn_max_complex_error_lt'],
        'independent_area': area_check['status'],
        'independent_voicing': gate_check['status'] and stable_gate > cfg['minimum_voicing'],
        'enough_complete_cycles': len(lengths) >= cfg['minimum_complete_cycles'],
        'cycle_lengths_match_f0': period_error < cfg['cycle_period_max_absolute_error_samples'],
        'total_open_fraction': abs(open_fraction - cfg['expected_open_fraction']) < cfg['open_fraction_max_absolute_error'],
        'peaks_per_cycle': len(peak_phase_errors) == len(lengths),
        'peak_phases': peak_error is not None and peak_error < cfg['peak_phase_max_absolute_error'],
    }
    result = {
        'checks': checks, 'complete_cycles': len(lengths), 'minimum_voicing': stable_gate,
        'f0_hz': float(data['glottal_f0_hz'][0]), 'f0_max_absolute_error_hz': f0_error,
        'mean_period_samples': float(np.mean(lengths)), 'max_period_error_samples': period_error,
        'max_complex_phase_error': phase_error, 'total_open_fraction': open_fraction,
        'peak_counts_per_cycle': sorted(set(peak_counts)), 'max_peak_phase_error': peak_error,
        'upstream_time_series': comparisons, 'independent_area': area_check, 'independent_voicing': gate_check,
    }
    for key, values, bounds in (
        ('secondary_opening', secondary_openings, cfg.get('secondary_opening_interval_phase')),
        ('secondary_to_primary_peak_ratio', secondary_ratios, cfg.get('secondary_to_primary_peak_ratio_interval')),
    ):
        if bounds is not None:
            lower, upper_bound = bounds
            checks[key] = len(values) == len(lengths) and all(lower <= value <= upper_bound for value in values)
            result[f'{key}_min_max'] = [min(values), max(values)] if values else None
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('case', choices=CASES)
    args = parser.parse_args()
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]*', args.run_id):
        parser.error('実行IDは英数字で始め、英数字、ハイフン、アンダースコアで指定してください')
    case_path = WORKSPACE / 'cases' / f'{args.case}.json'
    case = json.loads(case_path.read_text())
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        raise ValueError('変更のない固定上流版が必要です')

    def measure_run(artifacts, execute):
        return measure(case, artifacts, execute)

    modules = (reference, glottal, shared, telemetry)
    sources = [reference.PROBE, Path(__file__).resolve(), *(Path(module.__file__) for module in modules),
               WORKSPACE / 'tools/upstream_baseline.py', *shared.candidate_sources()]
    details = {'upstream_revision': revision, 'case_id': case['id'], 'scipy_version': scipy.__version__}
    return shared.record_measurement(args.run_id, case_path, [case_path, *sources], details, measure_run)


if __name__ == '__main__':
    raise SystemExit(main())
