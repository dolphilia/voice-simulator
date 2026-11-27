"""長い連続音の定常区間で、位相の進み遅れをホスト時計の速度差と照合する。"""

import argparse
from itertools import groupby
from pathlib import Path
import sys

import numpy as np

from measure_csd_envelope_timing import verified_file
from measure_cubeb_output_callback import load_blocks
from measure_speech_timing import read
from measure_tsp_listening import hydrate_run
from measure_uniform_tube import record_measurement
from measure_worklet_fixed import ROOT
from upstream_baseline import WORKSPACE


CASE = WORKSPACE / 'cases/firefox-process-tap-headphone-drift-44100-clock-plateaus.json'


def category(row, spec):
    level, = [f['amplitude_ratio'] for f in row['frequencies'] if f['hz'] == spec['band_tone_hz']]
    slope = row['pilot_slope_from_previous_ppm']
    if slope is None or abs(slope) < spec['minimum_abs_pilot_slope_ppm']:
        return None
    if level < spec['reduced_band_upper_limit']:
        band = 'reduced'
    elif level >= spec['wide_band_lower_limit']:
        band = 'wide'
    else:
        return None
    return band, (1 if slope > 0 else -1)


def slope_fit(x, y):
    offsets = np.asarray(x, dtype=float) - x[0]
    measured = np.asarray([v - y[0] for v in y], dtype=float)
    matrix = np.column_stack((offsets, np.ones(len(offsets))))
    coef, _, rank, _ = np.linalg.lstsq(matrix, measured, rcond=None)
    if rank != 2:
        raise ValueError('区間に直線の傾きを求める点がありません')
    return float(coef[0]), float(np.sqrt(np.mean((matrix @ coef - measured)**2)))


def estimate_clock(series, start, stop, tick, nominal_ns):
    positions, ticks = zip(*[(n, t) for n, t in series if start <= n <= stop], strict=True)
    slope, residual = slope_fit(list(positions), list(ticks))
    return {'block_starts': len(positions), 'ns_per_frame': slope * tick,
            'relative_to_nominal_ppm': (slope * tick / nominal_ns - 1) * 1e6,
            'host_fit_rms_ns': residual * tick}


def track(clock, summary, spec):
    rows = summary['windows']
    reference = spec.get('clock_reference', 'cubeb')
    nominal_ns = 1e9 / spec['sample_rate_hz']
    trim = spec['discard_end_windows']
    result = []
    for status, group in groupby(rows, key=lambda row: category(row, spec)):
        seq = list(group)
        if status is None or len(seq) < spec['minimum_consecutive_windows']:
            continue
        within = seq[trim:len(seq) - trim]
        centers = [sum(row['source_frames']) // 2 for row in within]
        lag = [row['pilot_offset_frames'] for row in within]
        phase_slope, phase_residual = slope_fit(centers, lag)
        clocks = {key: estimate_clock(clock[key], centers[0], centers[-1], clock['tick'], nominal_ns)
                  for key in (reference, 'tap')}
        host_ppm = (clocks['tap']['ns_per_frame'] - clocks[reference]['ns_per_frame']) / nominal_ns * 1e6
        band, sign = status
        result.append({'band': band, 'categorization_slope_sign': sign, 'total_windows': len(seq),
                       'fitted_windows': len(within), 'source_window_centers': [centers[0], centers[-1]],
                       'pilot_slope_ppm': phase_slope * 1e6, 'pilot_fit_rms_frames': phase_residual,
                       'host_difference_ppm': host_ppm, 'error_ppm': phase_slope * 1e6 - host_ppm,
                       'median_band_amplitude_ratio': float(np.median([
                           f['amplitude_ratio'] for row in within for f in row['frequencies']
                           if f['hz'] == spec['band_tone_hz']])), 'clocks': clocks})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('--case', type=Path, default=CASE)
    args = parser.parse_args()
    spec = read(CASE)
    registered = args.case.resolve()
    if registered != CASE:
        override = read(registered)
        if override['base_case'] != CASE.name:
            parser.error('時計比較の基準ケースを指定してください')
        spec |= override
    source_path = registered.with_name(spec['source_case'])
    case = read(source_path)
    revision = spec['upstream_revision']
    if (case['id'], case['revision']) != (spec['source_case_id'], spec['source_case_revision']):
        parser.error('帯域と位相を収録したケースの版が異なります')
    captures = {}
    inputs = [CASE, registered, source_path, Path(__file__).resolve(), WORKSPACE/'tools/measure_cubeb_output_callback.py']
    for ident in spec.get('source_runs') or case['trial_ids']:
        folder, manifest = hydrate_run(ident, case['id'], revision)
        if manifest['case_revision'] != case['revision']:
            parser.error('収録のケースの版が異なります')
        path = verified_file(folder, manifest, 'summary.json')
        summary = read(path)
        reference = spec.get('clock_reference', 'cubeb')
        tap_dir = spec.get('capture_directory', 'artifacts')
        raw_folder, raw_manifest = folder, manifest
        if reference == 'direct':
            capture_run = summary['original_capture']
            allowed = [case['trials'][ident]]
        else:
            capture_run = summary.get('capture_run')
            allowed = [item['capture_run'] for item in case['capture_reviews']] if capture_run else []
        if capture_run:
            if capture_run not in allowed:
                parser.error('元の収録は補足ケースで登録されていません')
            raw_folder = WORKSPACE / 'runs' / capture_run
            raw_manifest = read(raw_folder / 'manifest.json')
            if raw_manifest['run_id'] != capture_run or raw_manifest['upstream_revision'] != revision:
                parser.error('元の収録の実行または上流版が異なります')
            inputs.append(raw_folder / 'manifest.json')
        start = summary[reference + '_anchor']['origin_in_pcm']
        if reference == 'direct':
            clock_source = verified_file(raw_folder, raw_manifest, tap_dir + '/native.json')
            marks = read(clock_source)['frameMarks']
            series = [(r['markerOffset'] - start, r['hostTime']) for r in marks if 'hostTime' in r]
        else:
            cubeb_dir = spec.get('capture_directory', 'artifacts/cubeb')
            clock_source = verified_file(raw_folder, raw_manifest, cubeb_dir + '/' + summary['cubeb_stream'] + '/blocks.csv')
            series = [(r['pcm_byte_offset'] // 8 - start, r['host_time']) for r in load_blocks(clock_source.parent)]
        tap = verified_file(raw_folder, raw_manifest, tap_dir + '/tap.json')
        tape = read(tap)
        t_orig = summary['tap_anchor']['origin_in_pcm']
        clock = {reference: series,
                 'tap': [(r['offset'] - t_orig, r['hostTime']) for r in tape['blocks']],
                 'tick': tape['timebaseNumer'] / tape['timebaseDenom']}
        inputs.extend((folder / 'manifest.json', path, clock_source, tap))
        captures[ident] = (clock, summary)

    def measure(out, execute):
        trials = {ident: track(clock, summary, spec) for ident, (clock, summary) in captures.items()}
        intervals = [r for rows in trials.values() for r in rows]
        checks = {'each_trial_has_wide_and_reduced': all({r['band'] for r in rows} == {'wide', 'reduced'}
                                                        for rows in trials.values()),
                  'phase_slope_matches_host_clocks': bool(intervals) and all(
                      abs(r['error_ppm']) <= spec['maximum_slope_error_ppm'] for r in intervals),
                  'reduced_band_matches_positive_drift': bool(intervals) and all(
                      (r['pilot_slope_ppm'] > 0) == (r['band'] == 'reduced') for r in intervals)}
        return {'checks': checks, 'trials': trials, 'plateau_count': len(intervals)}

    details = {'case_id': spec['id'], 'case_revision': spec['revision'], 'upstream_revision': revision,
               'analysis_command': [sys.executable, *sys.argv]}
    return record_measurement(args.run_id, registered, inputs, details, measure, command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
