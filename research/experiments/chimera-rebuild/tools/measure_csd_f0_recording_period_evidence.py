"""録音のF0候補を波形相関・倍音間隔・YINの対照で調べる。"""

import argparse
import csv
import gzip
import math
from pathlib import Path
import subprocess
import sys

import numpy as np
from scipy.signal import butter, find_peaks, sosfiltfilt

from measure_csd_envelope_timing import load_inputs, waveforms
from measure_csd_f0_continuity import MODES, describe_frame, measure_track
from measure_csd_f0_continuity_songs import matches_period
from measure_csd_f0_search_sensitivity import add_file, cmnd, published, run_inputs, select_period
from measure_csd_long_notes import load_sources
from measure_csd_song_f0 import NotePitch, measurement_windows, midi_to_hz
from measure_speech_timing import read
from measure_uniform_tube import record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/csd-f0-recording-period-evidence.json'
ROOT = WORKSPACE.parents[2]


def centered(pcm, rate, time, duration):
    count = round(duration * rate)
    start = int(time * rate) - count // 2
    if not 0 <= start <= len(pcm) - count:
        raise ValueError('評価窓がPCMの範囲外です')
    return pcm[start:start + count]


def peak_offset(a, b, c):
    curvature = a - 2 * b + c
    return (a - c) / (2 * curvature) if curvature < 0 else 0.0


def normalized_correlation(frame, rate, scan):
    lo, hi = math.ceil(rate / scan[1]), math.floor(rate / scan[0])
    lags = np.arange(lo, hi + 1)
    values = []
    for lag in lags:
        left, right = frame[:-lag], frame[lag:]
        a, b = left - left.mean(), right - right.mean()
        norm = np.linalg.norm(a) * np.linalg.norm(b)
        values.append(float(np.dot(a, b) / norm) if norm else 0.0)
    i = int(np.argmax(values))
    fine = peak_offset(*values[i - 1:i + 2]) if 0 < i < len(values) - 1 else 0.0
    hz = rate / (int(lags[i]) + fine)
    return {'estimate_hz': hz, 'lag_samples': int(lags[i]), 'correlation': values[i]}, dict(zip(lags.tolist(), values, strict=True))


def spectral_peaks(frame, rate, case):
    n = case['spectral_fft_size']
    power = np.abs(np.fft.rfft((frame - frame.mean()) * np.hanning(len(frame)), n=n))**2
    maximum = float(power.max())
    if maximum == 0:
        return []
    db = 10 * np.log10(np.maximum(power / maximum, 1e-30))
    peaks, _ = find_peaks(db, height=case['spectral_peak_floor_db'], prominence=case['spectral_prominence_db'])
    lower, upper = case['spectral_peak_bounds_hz']
    return [(float((k + peak_offset(*db[k - 1:k + 2])) * rate / n), float(db[k]))
            for k in peaks if lower <= k * rate / n <= upper]


def fit_harmonics(peaks, case, candidates):
    if not peaks:
        return {'estimate_hz': None, 'matched_harmonics': 0, 'candidates': {}}
    freqs = np.array([hz for hz, _ in peaks])
    low, high = case['pitch_scan_hz']
    grid = np.linspace(low, high, round((high - low) / case['pitch_grid_step_hz']) + 1)
    tolerance = case['harmonic_match_tolerance_hz']

    def measure(fundamentals):
        hz = np.asarray(fundamentals)[:, None]
        order = np.maximum(1, np.rint(freqs / hz))
        errors = freqs - order * hz
        losses = np.mean(np.minimum(errors**2, tolerance**2), axis=1)
        counts = np.sum(np.abs(errors) <= tolerance, axis=1)
        return losses, counts

    losses, counts = measure(grid)
    best = int(losses.argmin())
    matched = int(counts[best])
    result = {'estimate_hz': float(grid[best]) if matched >= case['minimum_matched_harmonics'] else None,
              'matched_harmonics': matched, 'total_peaks': len(peaks), 'candidates': {}}
    if candidates:
        scores, fits = measure(list(candidates.values()))
        result['candidates'] = {label: {'rms_clipped_error_hz': math.sqrt(loss), 'matched_harmonics': int(count)}
                                for label, loss, count in zip(candidates, scores, fits, strict=True)}
    return result


def evidence(pcm, rate, time, case, candidates):
    window = centered(pcm, rate, time, case['period_probe_seconds'])
    period, correlation = normalized_correlation(window, rate, case['pitch_scan_hz'])
    diagnostics, peak_lists = {}, {}
    for duration in case['spectral_window_seconds']:
        peaks = spectral_peaks(centered(pcm, rate, time, duration), rate, case)
        peak_lists[duration] = peaks
        diagnostics[duration] = fit_harmonics(peaks, case, candidates)
    return {'period': period, 'spectrum': diagnostics}, correlation, peak_lists


def band_difference(frame, lag, width, rate, edges):
    delta = frame[:width] - frame[lag:lag + width]
    energy = float(np.dot(delta, delta))
    power = 2 * np.abs(np.fft.rfft(delta))**2 / width
    power[0] /= 2
    if width % 2 == 0:
        power[-1] /= 2
    bins = np.fft.rfftfreq(width, 1 / rate)
    band_energies = [float(power[(lo <= bins) & (bins < hi)].sum()) for lo, hi in zip(edges, (*edges[1:], math.inf), strict=True)]
    return {'energy': energy, 'band_energies': band_energies,
            'relative_parseval_error': abs(energy - math.fsum(band_energies)) / max(1e-30, energy)}


def known_controls(rate, case):
    t = np.arange(rate) / rate
    results = []
    for hz in case['known_hz']:
        pcm = sum(a * np.sin(2 * np.pi * hz * t * k) for k, a in enumerate(case['known_harmonic_amplitudes'], 1))
        measured, _, _ = evidence(pcm, rate, 0.5, case, {})
        sections = [measured['period'], *measured['spectrum'].values()]
        measured['known_hz'] = hz
        measured['matches'] = all(row['estimate_hz'] is not None and abs(row['estimate_hz'] - hz) <= case['known_tolerance_hz']
                                  for row in sections)
        results.append(measured)
    return results


def probe_frames(case, rows, focus, estimator, low_lag, max_lag, target, out, *, first_note_window=0):
    rate = estimator.rate
    indexes = [focus + i for i in case['probe_offsets_windows']]
    if any(not 0 <= i < len(rows) for i in indexes):
        raise ValueError('現象の前後を登録した窓数で採れません')
    margin = round(case['filter_margin_seconds'] * rate) + estimator.width
    first = int(rows[indexes[0]]['time'] * rate) - margin
    last = int(rows[indexes[-1]]['time'] * rate) + margin
    if not 0 <= first < last <= len(estimator.pcm):
        raise ValueError('低域通過の解析に必要な前後の余裕がありません')
    sos = butter(case['lowpass_order'], case['lowpass_hz'], btype='lowpass', fs=rate, output='sos')
    filtered = sosfiltfilt(sos, estimator.pcm[first:last])

    diagnostics = []
    focal_lags = None
    with (out / 'normalized-correlation.csv').open('w', newline='') as ac, \
            (out / 'spectral-peaks.csv').open('w', newline='') as fft:
        ac_csv, fft_csv = csv.writer(ac), csv.writer(fft)
        ac_csv.writerow(['note_window', 'seconds', 'lag_samples', 'f0_hz', 'normalized_correlation'])
        fft_csv.writerow(['note_window', 'seconds', 'window_seconds', 'peak_hz', 'relative_db'])
        for i in indexes:
            row = rows[i]
            t = row['time']
            note_window = i + first_note_window
            candidates = {k: row[k].hz for k in ('wide', 'tracked') if row[k].hz is not None}
            measured, correlation, peaks = evidence(estimator.pcm, rate, t, case, candidates)
            ac_csv.writerows((note_window, t, lag, rate / lag, value) for lag, value in correlation.items())
            fft_csv.writerows((note_window, t, width, hz, db) for width, lines in peaks.items() for hz, db in lines)
            start = int(t * rate) - estimator.width // 2
            raw = estimator.pcm[start:start + estimator.width]
            filtered_frame = filtered[start - first:start - first + estimator.width]
            original_cmnd = cmnd(raw, max_lag)
            gated = row['wide'].status == 'below_energy_gate'
            after_filter = select_period(cmnd(filtered_frame, max_lag), low_lag, rate, estimator.threshold, gated)
            after_threshold = select_period(original_cmnd, low_lag, rate, case['lower_yin_threshold'], gated)
            supported = measured['spectrum'][max(case['spectral_window_seconds'])]['estimate_hz']
            is_split = all(k in candidates for k in ('wide', 'tracked')) and candidates['wide'] != candidates['tracked']
            diagnostic = (describe_frame(row, target) | measured | {'note_window': note_window, 'window_start_sample': start,
                           'lowpass': after_filter._asdict(), 'lower_yin_threshold': after_threshold._asdict(),
                           'correlation_at_candidate_lags': {k: correlation.get(row[k].lag) for k in candidates}})
            if is_split:
                diagnostic['independent_hz_errors'] = {
                    k: {'correlation': abs(measured['period']['estimate_hz'] - hz),
                        'spectrum': abs(supported - hz) if supported is not None else None} for k, hz in candidates.items()}
            diagnostics.append(diagnostic)
            if i == focus:
                lag = row['wide'].lag
                tested = sorted({lag - 1, lag, lag + 1, row['tracked'].lag})
                focal_lags = [{'lag_samples': tau, 'cmnd': float(original_cmnd[tau]),
                               **band_difference(raw, tau, estimator.width - max_lag, rate, case['difference_band_edges_hz'])}
                              for tau in tested]
    return diagnostics, focal_lags


def measure(case, tracker, settings, source, wave_case, official, saved, out, execute):
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera-cli', 'compare::'],
            cwd=UPSTREAM, stdout=out / 'fixed-compare-tests.log')
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera', '--test', 'golden_analysis'],
            cwd=UPSTREAM, stdout=out / 'fixed-analysis-tests.log')
    index = case['note_index']
    note = official['notes'][index]
    target = midi_to_hz(note['midi'])
    pitch = wave_case['measurement']
    pcm, rate = waveforms(source, wave_case['render'])['recording']
    estimator = NotePitch(pcm, rate, min(n['midi'] for n in official['notes']), pitch)
    _, centers = measurement_windows(note, pitch)
    ratios = tuple(math.exp2(x / 12) for x in settings['upper_semitones'])
    rows, direct = measure_track(estimator, centers, target, ratios, tracker, settings)
    matches = len(rows) == len(saved) == case['reference_windows'] and all(
        row['time'] == float(old['seconds']) and row['power'] == float(old['mean_square']) and all(
            matches_period(row[k], old[f'{k}_status'], old[f'{k}_hz'], old[f'{k}_cmnd'],
                           old[f'{k}_lag_samples'], settings) for k in MODES)
        for row, old in zip(rows, saved, strict=True))
    change = [(i, abs(1200 * math.log2(row['tracked'].hz / row['wide'].hz))) for i, row in enumerate(rows)
              if row['wide'].hz is not None and row['tracked'].hz is not None and row['tracked'].hz != row['wide'].hz]
    if not change:
        raise ValueError('登録した音符に比較できるF0の差がありません')
    first_change, _ = change[0]
    focus, maximum = max(change, key=lambda item: item[1])
    if not math.isclose(rows[focus]['time'], case['focus_seconds'], rel_tol=0, abs_tol=1e-9):
        raise ValueError('最大差が出た窓が事前登録と一致しません')
    low_lag = max(2, int(rate / (target * estimator.search_range)))
    max_lag = min(estimator.width // 2, int(rate / (target / estimator.search_range)))
    prefix_count = max(0, -focus - min(case['probe_offsets_windows']))
    prefix = []
    if prefix_count and case.get('extend_probe_before_grid'):
        prior_times = [centers[0] + i * pitch['hop_seconds'] for i in range(-prefix_count, 0)]
        if prior_times[0] < note['start']:
            raise ValueError('補助窓の中心が対象音符より前にあります')
        # 補助窓の候補選択は、保存済み格子の追跡とは独立に行う。
        prefix, prefix_direct = measure_track(estimator, prior_times, target, ratios, tracker, settings)
        direct &= prefix_direct
    diagnostics, focal_lags = probe_frames(case, prefix + rows, len(prefix) + focus, estimator, low_lag,
                                            max_lag, target, out, first_note_window=-len(prefix))
    selected = next(item for item in diagnostics if item['note_window'] == focus)
    errors = selected['independent_hz_errors']
    source_hz = selected['tracked']['hz']

    def supports_longer(method):
        short, long = (errors[k][method] for k in ('wide', 'tracked'))
        return long is not None and short is not None and long < short and long <= case['independent_agreement_hz']

    def near_tracked(result):
        return result['hz'] is not None and abs(result['hz'] - source_hz) <= case['filtered_f0_tolerance_hz']

    controls = known_controls(rate, case)
    predictions = {'correlation_supports_longer_lag': supports_longer('correlation'),
                   'spectrum_supports_longer_lag': supports_longer('spectrum'),
                   'lower_threshold_selects_longer_period': near_tracked(selected['lower_yin_threshold']),
                   'lowpass_selects_longer_period': near_tracked(selected['lowpass'])}
    checks = {'prior_note_replayed': matches, 'independent_yin_replay': direct,
              'known_periods': all(row['matches'] for row in controls), 'band_parseval': all(
                  item['relative_parseval_error'] <= case['relative_parseval_tolerance'] for item in focal_lags),
              'probe_windows_measured': len(diagnostics) == len(case['probe_offsets_windows']),
              'original_voicing_carries_through_probe': all(r['wide']['status'] == 'voiced'
                                                           for r in diagnostics if r['note_window'] >= 0)}
    return {'checks': checks, 'predictions': predictions, 'note_index': index, 'ipa': note['ipa'], 'rate_hz': rate,
            'yin_window_samples': estimator.width, 'yin_minimum_lag_samples': low_lag, 'yin_maximum_lag_samples': max_lag,
            'first_note_difference': describe_frame(rows[first_change], target), 'maximum_difference_cents': maximum,
            'focus': selected, 'focus_difference_energies': focal_lags, 'probes': diagnostics, 'controls': controls}


def load_song(case, corpus, song, inputs):
    name = song['id']
    revision = case['upstream_revision']
    if 'wave_case' in song:
        run = run_inputs(corpus['short_source_run'], revision, inputs)
        recording, paths, wave_case = load_inputs(case, *run, song, inputs)
        reports, _ = published(run, 'csd', inputs)
        return recording, paths, wave_case, reports[name]

    run = run_inputs(corpus['long_run'], revision, inputs)
    long_case_path = CASE.parent / corpus['long_case']
    long_case = read(long_case_path)
    pitch_path = CASE.parent / long_case['pitch_case']
    inputs.extend([long_case_path, pitch_path])
    recordings = load_sources(long_case, run[1]['selection_run'], run[1]['recording_run'], inputs)
    (recording, details), = [(wave, info) for split, row, _, wave, info in recordings
                             if row['id'] == name and split == song['split']]
    synth = add_file(run, f'artifacts/upstream/{name}-synth.wav', inputs)
    candidate = add_file(run, f'artifacts/{name}/candidate.wav', inputs)
    frames = read(add_file(run, 'summary.json', inputs))['songs'][name]['wave_frames']
    wave_case = {'render': frames, 'measurement': read(pitch_path)['measurement']}
    reports, _ = published(run, 'upstream', inputs)
    return (details | {'resolved_path': str(recording)}, (recording, synth, candidate), wave_case, reports[name])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('--case', type=Path, default=CASE)
    args = parser.parse_args()
    case_path = args.case.resolve(strict=True)
    case = read(case_path)
    case_inputs = [case_path]
    if 'base_case' in case:
        if case['base_case'] != CASE.name:
            parser.error('指定された録音用の基準ケースに対応していません')
        case = read(CASE) | case
        case_inputs.append(CASE)
    revision = case['upstream_revision']
    if (subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip() != revision
            or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True)):
        parser.error('変更のない固定上流版が必要です')
    corpus_file = CASE.parent / case['corpus_case']
    corpus = read(corpus_file)
    song, = [row for row in corpus['songs'] if row['id'] == case['song']]
    inputs = [*case_inputs, corpus_file, Path(__file__).resolve(), *(WORKSPACE / 'tools' / name for name in (
        'measure_csd_f0_continuity.py', 'measure_csd_f0_continuity_songs.py', 'measure_csd_f0_search_sensitivity.py',
        'measure_csd_envelope_timing.py', 'measure_csd_song_f0.py', 'measure_csd_continuous_song.py', 'measure_vowel_voice.py',
        'measure_csd_vibrato_aperiodicity.py', 'measure_csd_f0_third_harmonic.py', 'measure_csd_note_spectrum.py',
        'measure_speech_timing.py', 'measure_uniform_tube.py', 'upstream_baseline.py'))]
    baseline = run_inputs(case['comparison_run'], revision, inputs)
    tracker_relative = (WORKSPACE / 'cases/csd-f0-continuity.json').relative_to(ROOT)
    tracker_path = baseline[0] / baseline[1]['source_snapshot'] / tracker_relative
    tracker_hashes = [row['sha256'] for row in baseline[1]['inputs'] if row['path'] == str(tracker_relative)]
    if tracker_hashes != [sha256(tracker_path)]:
        parser.error('前回の追跡条件を検証できません')
    tracker = read(tracker_path)
    inputs.append(tracker_path)
    if 'wave_case' not in song:
        inputs.extend(WORKSPACE / 'tools' / name for name in ('measure_csd_long_notes.py', 'select_csd_long_notes.py'))
    recording, waves, wave_case, report = load_song(case, corpus, song, inputs)
    if recording['sha256'] != baseline[1]['recordings'][song['id']]['sha256']:
        parser.error('全曲比較と録音が一致しません')
    archive = add_file(baseline, f"artifacts/{song['id']}-continuity-frames.csv.gz", inputs)
    with gzip.open(archive, 'rt', newline='') as f:
        saved = [row for row in csv.DictReader(f)
                 if row['signal'] == 'recording' and int(row['note_index']) == case['note_index']]
    details = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision,
               'recording': recording, 'baseline_run': case['comparison_run'], 'analysis_directory': str(Path.cwd()),
               'analysis_command': [sys.executable, *sys.argv]}
    return record_measurement(args.run_id, case_path, inputs, details,
        lambda out, execute: measure(case, tracker, corpus['measurement'], waves, wave_case,
                                     report, saved, out, execute), command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
