"""録音2語の基準窓でプリエンファシスだけを切り替え、F2候補を照合する。"""

import argparse
import gzip
import json
from pathlib import Path
import subprocess

import numpy as np
import scipy

import measure_tsp_f2_bandwidth_envelope as envelope
import measure_tsp_f2_bandwidth_held_out as held_out
import measure_tsp_lpc_lag_window as lag
import measure_tsp_lpc_pre_emphasis as pre
import measure_tsp_stressed_vowel_formants as tsp
from measure_uniform_tube import record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/tsp-lpc-pre-emphasis-recordings.json'


def prepare(case, cfg, alignment, intervals, duration, summary, fixed):
    rate = cfg['sample_rate_hz'] / cfg['decimation']
    length = int(rate * cfg['frame_seconds'])
    wavs, windows, medians = [], [], {}
    for planned in case['tokens']:
        uid, index, word = (planned[k] for k in ('utterance', 'phone_index', 'word'))
        path = tsp.verified_path(alignment, f'artifacts/corpus/recording/{uid}/{uid}.wav')
        if sha256(path) != duration['splits']['held_out'][uid]['recording_sha256']:
            raise ValueError(f'録音が最初の比較と一致しません ({uid})')
        wave = tsp.filtered_wave(path, 'recording', cfg)
        wavs.append(path)
        token, = (row['recording'] for row in summary['tokens'][uid] if row['indexes']['recording'] == index)
        reference, = (row for row in fixed[uid]['sources']['recording'] if row['index'] == index)
        interval = intervals[uid]['phones'][index]
        if token['word'] != word or token['interval'] != interval or interval[2] != planned['arpabet']:
            raise ValueError(f'録音の語またはMFA境界が登録内容と一致しません ({uid}/{word})')
        medians[uid] = reference['baseline_hz']
        order = cfg['order'][uid[0]]
        for center in case['centers']:
            prior, = (i for i, row in enumerate(token['windows']) if row['center'] == center)
            measured = tsp.window(wave, interval, center, order, cfg)
            start = measured['start_sample']
            old_rust = reference['windows'][prior]
            frame = wave[start:start + length]
            if (len(frame) != length or measured['outside_phone_ms'] > 1e-9
                    or start != token['windows'][prior]['start_sample'] or start != old_rust['start_sample']):
                raise ValueError(f'基準窓の標本位置が一致しません ({uid}/{word}/{center})')
            windows.append(({**planned, 'center': center, 'order': order, 'interval_seconds': interval[:2],
                             'start_sample': start, 'frame_samples': length}, frame, old_rust))
    return rate, windows, medians, wavs


def examine(case, meta, frame, old_rust, rust, rate, grid, cfg, settings, smoothing):
    fixed, zero = rust
    if [v['pre_emphasis_option'] for v in rust] != [None, 0] or [
            v['pre_emphasis_coefficient'] for v in rust] != settings['pre_emphasis_coefficients']:
        raise ValueError('固定の既定値と明示的な0が登録した条件と一致しません')
    delay = np.r_[0, frame[:-1]]
    window_settings = {**settings, 'spectral_balance_frequencies_hz': meta['spectral_balance_frequencies_hz']}
    observed = [pre.inspect_variant(frame, delay, rate, meta['order'], grid, cfg, window_settings, smoothing, v)
                for v in rust]
    variants, curves = zip(*observed, strict=True)
    width = case['measurement']['peak_half_width_hz']
    for variant, raw, spectrum in zip(variants, rust, curves, strict=True):
        selected = variant['fixed_selection']['f2']
        variant.update(poles=raw['poles'], peaks_near_f2={
            'own_periodogram': held_out.near_peak(spectrum, grid, selected, width),
            'unemphasized_periodogram': held_out.near_peak(curves[1], grid, selected, width),
            'own_lpc': held_out.near_peak(raw['lpc_envelope_db'], grid, selected, width),
        })
    baseline = variants[0]['fixed_selection']
    alternative = variants[1]['fixed_selection']
    selected_freqs = held_out.pair(baseline)
    default_error = {
        'poles_hz': tsp.max_error(fixed['poles'], old_rust['poles']),
        'pair_hz': tsp.max_error(selected_freqs, old_rust['f1_f2_hz']),
        'missing_reason_matches': baseline['reason'] == old_rust['reason'],
    }
    tolerance = settings['preprocessing_and_correlation_tolerance']
    expected = settings['pre_emphasis_coefficients'][0] * delay
    actual = np.array(zero['emphasized']) - np.array(fixed['emphasized'])
    post_window_difference = np.array(zero['shaped']) - np.array(fixed['shaped'])
    first = {name: pre.first_difference(fixed[name], zero[name], tolerance)
             for name in ('emphasized', 'shaped', 'autocorrelation')}
    first['coefficients'] = pre.first_difference(fixed['coefficients'], zero['coefficients'],
                                                 settings['coefficient_and_residual_tolerance'])
    delay_errors = {'samples': tsp.max_error(actual, expected),
                    'windowed_samples': tsp.max_error(post_window_difference, expected * np.hamming(len(frame)))}
    predictable_starts = {
        'emphasized': pre.first_difference(np.zeros(len(frame)), expected, tolerance),
        'shaped': pre.first_difference(np.zeros(len(frame)), expected * np.hamming(len(frame)), tolerance),
    }
    f2_delta = (alternative['f2'][0] - baseline['f2'][0]) if baseline['f2'] and alternative['f2'] else None
    data = {**meta, 'variants': variants, 'f2_delta_hz': f2_delta, 'first_differences': first,
            'discrete_delay_agreement': delay_errors, 'predicted_sample_positions': predictable_starts,
            'default_error': default_error}
    return data, {'utterance': meta['utterance'], 'center': meta['center'], 'periodogram_db': curves,
                  'lpc_db': [v['lpc_envelope_db'] for v in rust]}


def coverage(case, rows, old_medians):
    summary = {}
    for token in case['tokens']:
        uid = token['utterance']
        matching = [row for row in rows if row['utterance'] == uid]
        entry = {}
        for i, label in enumerate(('fixed', 'zero')):
            variants = [row['variants'][i] for row in matching]
            matches = [pair for row in variants if (pair := held_out.pair(row['fixed_selection'])) is not None]
            entry[label] = {
                'valid_windows': len(matches),
                'missing_reasons': [row['fixed_selection']['reason'] for row in variants if row['fixed_selection']['reason']],
                'median_frequencies_hz': np.median(matches, axis=0).tolist() if matches else None,
                'median_condition_number': float(np.median([v['condition_number_2'] for v in variants])),
            }
        expected = old_medians[uid]
        entry['reference_median_error_hz'] = tsp.max_error(
            entry['fixed']['median_frequencies_hz'], expected if expected != [None, None] else None)
        summary[uid] = entry
    return summary


def measure(case, cfg, settings, smoothing, rate, windows, old_medians, artifacts, execute):
    step = settings['spectrum_grid_hz']
    grid = np.arange(0, rate / 2 + step, step)
    reference = pre.run_probes([(frame, meta['order']) for meta, frame, _ in windows], rate, grid, artifacts, execute)
    measured = [examine(case, meta, frame, old_rust, rust, rate, grid, cfg, settings, smoothing)
                for (meta, frame, old_rust), rust in zip(windows, reference, strict=True)]
    rows, curves = zip(*measured, strict=True)
    packed = json.dumps({'frequency_hz': grid.tolist(), 'windows': curves}, separators=(',', ':')).encode()
    (artifacts / 'spectra.json.gz').write_bytes(gzip.compress(packed, mtime=0))
    subjects = coverage(case, rows, old_medians)
    tolerance = cfg['frequency_bandwidth_agreement_hz']
    sample_tolerance = settings['preprocessing_and_correlation_tolerance']
    limits = pre.trace_limits(settings, cfg)
    checks = {
        'six_registered_windows': len(rows) == len(case['tokens']) * len(case['centers']) == 6,
        'default_upper_poles_and_f2': all(r['default_error']['missing_reason_matches']
                                            and all(v is not None and v <= tolerance for k, v in r['default_error'].items()
                                                    if k.endswith('_hz')) for r in rows),
        'default_medians': all(r['reference_median_error_hz'] is not None and r['reference_median_error_hz'] <= tolerance
                               for r in subjects.values()),
        'analytic_pre_emphasis_difference': all(max(r['discrete_delay_agreement'].values()) <= sample_tolerance and
            all(predicted == r['first_differences'][name] for name, predicted in r['predicted_sample_positions'].items())
            for r in rows),
        'independent_fits_and_spectra': all(value is not None and value <= limits[k] for row in rows
                                           for variant in row['variants'] for k, value in variant['errors'].items()),
    }
    threshold = case['measurement']['large_f2_shift_hz']
    large = [i for i, row in enumerate(rows) if row['f2_delta_hz'] is not None and abs(row['f2_delta_hz']) >= threshold]
    new_missing = [i for i, row in enumerate(rows) if not row['variants'][0]['fixed_selection']['reason']
                   and row['variants'][1]['fixed_selection']['reason']]
    predictions = {
        'median_condition_number_rises_in_both_words': all(
             r['zero']['median_condition_number'] > r['fixed']['median_condition_number'] for r in subjects.values()),
        'relative_high_band_level_drops_in_all_windows': all(
             r['variants'][1]['periodogram_balance_db'] < r['variants'][0]['periodogram_balance_db'] for r in rows),
        'large_f2_effect_or_missing': bool(large or new_missing),
    }
    return {'checks': checks, 'hypotheses': predictions, 'coverage': subjects, 'large_change_indexes': large,
            'new_missing_indexes': new_missing, 'windows': rows, 'scipy': scipy.__version__}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    case = tsp.read(CASE)
    rev = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if rev != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True):
        raise ValueError('上流の作業ツリーが登録済みの固定版と一致しません')
    baseline, synthetic = (tsp.open_run(case[k], rev) for k in ('baseline', 'synthetic_control'))
    config, cfg_file = held_out.saved_case(baseline, tsp.CASE)
    control, control_file = held_out.saved_case(synthetic, pre.CASE)
    cfg, settings = config['measurement'], control['measurement']
    if (case['centers'] != cfg['reference_centers'] or
            case['measurement']['pre_emphasis_coefficients'] != settings['pre_emphasis_coefficients'] or
            settings['pre_emphasis_coefficients'] != [cfg['pre_emphasis'], 0] or
            case['measurement']['lag_window_hz'] != settings['lag_window_hz'] or cfg['lag_window_hz'] != settings['lag_window_hz']):
        raise ValueError('既定の測定条件が先行ケースと一致しません')
    alignment, duration = (tsp.open_run(config[k], rev) for k in ('alignment', 'render'))
    pilot_run = tsp.open_run(case['spectral_protocol'], rev)
    pilot, pilot_file = held_out.saved_case(pilot_run, envelope.CASE)
    duration_summary = tsp.verified_path(duration, 'summary.json')
    alignment_summary = tsp.verified_path(alignment, 'summary.json')
    saved = tsp.verified_path(baseline, 'summary.json')
    fixed = tsp.verified_path(baseline, 'artifacts/upstream-formants.json')
    rate, windows, old_medians, wavs = prepare(
        case, cfg, alignment, tsp.read(alignment_summary)['intervals'],
        tsp.read(duration_summary), tsp.read(saved), tsp.read(fixed))
    inputs = [CASE, Path(__file__).resolve(), pre.PROBE, cfg_file, control_file, pilot_file, duration_summary,
              alignment_summary, saved, fixed, *wavs, Path(tsp.__file__), Path(held_out.__file__),
              Path(pre.__file__), Path(lag.__file__), Path(envelope.__file__), UPSTREAM / lag.LPC,
              UPSTREAM / tsp.TSP_SOURCE, UPSTREAM / 'crates/chimera/tests/golden_analysis.rs', UPSTREAM / 'Cargo.lock',
              WORKSPACE / 'tools/measure_uniform_tube.py', WORKSPACE / 'tools/measure_fan_crossing_allocations.py',
              WORKSPACE / 'tools/upstream_baseline.py']
    inputs.extend(run[0] / 'manifest.json' for run in (baseline, synthetic, alignment, duration, pilot_run))
    return record_measurement(args.run_id, CASE, inputs, {
        'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': rev,
        'recording_reference': baseline[0].name, 'synthetic_control': synthetic[0].name,
    }, lambda artifacts, execute: measure(case, cfg, settings, pilot['measurement'], rate, windows, old_medians,
                                         artifacts, execute),
        command=None, input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
