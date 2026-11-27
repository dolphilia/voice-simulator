"""CSD音符の帯域電力、H1−H2、メルケプストラム距離を照合する。"""

import argparse
from collections import defaultdict
import csv
from functools import lru_cache
import math
import os
from pathlib import Path
import statistics
import subprocess
import sys

import numpy as np
import scipy
from scipy.fft import dct

from measure_csd_envelope_timing import PAIRS, error, load_inputs, verified_file, waveforms, within
from measure_csd_song_f0 import LABELS, measurement_windows
from measure_speech_timing import read
from measure_uniform_tube import record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE


CASE = WORKSPACE / 'cases/csd-note-spectrum.json'
SCORE_H1H2_COLUMN = 5  # 固定上流の compare/score.rs::H1H2


def mel(hz):
    return 2595 * np.log10(1 + np.asarray(hz) / 700)


def mcd(left, right):
    if left is None or right is None:
        return None
    return 10 / math.log(10) * math.sqrt(2) * math.dist(left, right)


def finite_stat(values, stat):
    available = [value for value in values if value is not None]
    return stat(available) if available else None


class Spectrum:
    def __init__(self, pcm, rate, config):
        self.pcm = pcm
        self.rate = rate
        self.config = config
        self.width = 1 << (math.ceil(rate * config['minimum_frame_seconds']) - 1).bit_length()
        self.spacing = rate / self.width
        self.freq = np.arange(self.width // 2 + 1) * self.spacing
        self.hann = np.hanning(self.width)
        edges = config['bands_hz']
        self.bands = np.stack([(self.freq >= lo) & (self.freq < hi) for lo, hi in zip(edges, edges[1:])])
        n = config['mel_bands']
        lo, hi = mel(config['mel_edges_hz'])
        self.edges = 700 * (np.power(10, np.linspace(lo, hi, n + 2) / 2595) - 1)
        a, b, c = (self.edges[offset:offset+n, None] for offset in range(3))
        self.mel_weights = np.maximum(0, np.minimum((self.freq-a)/(b-a), (c-self.freq)/(c-b)))
        q = np.arange(1, config['cepstral_coefficients'] + 1)
        self.cosine = np.cos(np.pi * q[:, None] * (np.arange(n) + .5) / n) / n

    def start(self, t):
        first = int(t * self.rate) - self.width // 2
        return first if 0 <= first and first + self.width <= len(self.pcm) else None

    def frame(self, first):
        return self.pcm[first:first+self.width].astype(float, copy=False)

    def power(self, first):
        window = self.frame(first) * self.hann
        coeff = np.fft.rfft(window)
        power = coeff.real**2 + coeff.imag**2
        from_time = float(np.dot(window, window))
        from_freq = float((2 * power[1:-1].sum() + power[0] + power[-1]) / self.width)
        return power, abs(from_time - from_freq) / max(1e-30, from_time)

    def features(self, power):
        floor = self.config['band_epsilon']
        band_power = self.bands @ power
        total = float(power[self.freq < self.config['bands_hz'][-1]].sum())
        bands = 10 * np.log10((band_power + floor) / (total + floor))
        mel_power = self.mel_weights @ power
        cepstrum = self.cosine @ np.log(mel_power + self.config['mel_epsilon'])
        return bands.tolist(), cepstrum.tolist(), total

    def independent_features(self, power):
        floor = self.config['band_epsilon']
        edges = self.config['bands_hz']
        bins = list(zip(self.freq, power, strict=True))
        total = math.fsum(float(p) for f, p in bins if edges[0] <= f < edges[-1])
        bands = [10 * math.log10((math.fsum(float(p) for f, p in bins if lo <= f < hi) + floor) /
                                 (total + floor)) for lo, hi in zip(edges, edges[1:])]
        mel_power = [float(np.dot(power, np.interp(self.freq, self.edges[i:i+3], (0, 1, 0), left=0, right=0)))
                     for i in range(self.config['mel_bands'])]
        coeff = dct(np.log(np.asarray(mel_power) + self.config['mel_epsilon']), type=2)
        cepstrum = coeff[1:1+self.config['cepstral_coefficients']] / (2 * len(mel_power))
        return bands, cepstrum, total

    def harmonic(self, power, hz):
        bin_index = hz / self.spacing
        margin = max(self.config['harmonic_fraction'] * bin_index, self.config['harmonic_minimum_bins'])
        lo = max(1, math.floor(bin_index - margin))
        hi = math.ceil(bin_index + margin)
        if hi + 1 >= len(power):
            return None, None
        # 等しい電力ではRustのmax_byと同じく後のビンを選ぶ。
        peak = hi - int(np.argmax(power[lo:hi+1][::-1]))
        a, b, c = 10 * np.log10(power[peak-1:peak+2] + self.config['band_epsilon'])
        curvature = a - 2*b + c
        level = b - .125 * (a-c)**2 / curvature if curvature < 0 else b
        return float(level), peak

    def h1h2(self, power, f0):
        h1, b1 = self.harmonic(power, f0)
        h2, b2 = self.harmonic(power, 2*f0)
        return (None if h1 is None or h2 is None else h1-h2), (b1, b2)


@lru_cache(maxsize=1)
def dft_matrix(size):
    bins = np.arange(size // 2 + 1)
    return np.exp(-2j * np.pi / size * np.outer(bins, np.arange(size)))


def direct_power(analyzer, first):
    n = analyzer.width
    win = .5 - .5 * np.cos(2 * np.pi * np.arange(n) / (n - 1))
    return np.abs(dft_matrix(n) @ (analyzer.frame(first) * win))**2


def spectrum_starts(analyzer, bounds, hop):
    t, end = bounds
    while t <= end:
        yield t, analyzer.start(t)
        t += hop


def note_features(analyzer, bounds, f0_rows, pitch_centers, pilot, writer=None, key=None):
    if [t for t, _, _ in f0_rows] != pitch_centers:
        raise ValueError('F0の保存時刻と音符の安定区間が一致しません')
    configs = analyzer.config
    cached_power = {}

    def power_at(first):
        if first not in cached_power:
            cached_power[first] = analyzer.power(first)
        return cached_power[first][0]

    acc = np.zeros(analyzer.width // 2 + 1)
    valid, skipped = [], 0
    for t, first in spectrum_starts(analyzer, bounds, configs['hop_seconds']):
        if first is None:
            skipped += 1
        else:
            acc += power_at(first)
            valid.append((t, first))

    harmonic_results = []
    harmonic_skipped = defaultdict(int)
    for t, f0, status in f0_rows[::2]:
        first = analyzer.start(t)
        if f0 is None:
            value, peaks, reason = None, (None, None), status
        elif first is None:
            value, peaks, reason = None, (None, None), 'spectrum_outside_wave'
        else:
            value, peaks = analyzer.h1h2(power_at(first), f0)
            reason = 'harmonic_outside_spectrum' if value is None else None
        if value is not None:
            harmonic_results.append(value)
        else:
            harmonic_skipped[reason] += 1
        if writer is not None:
            writer.writerow((*key, t, first, f0, *peaks, value, reason))

    bands = cepstrum = total = feature_error = dft_error = peak_hz = None
    if valid:
        bands, cepstrum, total = analyzer.features(acc)
        other_bands, other_cepstrum, _ = analyzer.independent_features(acc)
        feature_error = max(float(np.max(np.abs(np.asarray(a) - b))) for a, b in
                            ((bands, other_bands), (cepstrum, other_cepstrum)))
        peak_hz = float(analyzer.freq[int(np.argmax(acc))])
        if pilot:
            _, first = valid[0]
            direct = direct_power(analyzer, first)
            dft_error = float(np.max(np.abs(power_at(first) - direct)) / max(1e-30, float(direct.max())))

    first_window = None if not valid else {'seconds': valid[0][0], 'start_sample': valid[0][1]}
    return {
        'bands_db': bands, 'cepstrum': cepstrum, 'h1h2_db': finite_stat(harmonic_results, statistics.median),
        'spectrum_frames': len(valid), 'outside_wave_frames': skipped, 'available_h1h2_frames': len(harmonic_results),
        'missing_h1h2_frames_by_reason': dict(harmonic_skipped), 'first_window': first_window,
        'spectral_peak_hz': peak_hz, 'sum_0_to_8khz': total,
        'spectrum_status': 'no_complete_window' if not valid else ('zero_power' if not np.any(acc) else 'measured'),
        'max_parseval_error': max((value[1] for value in cached_power.values()), default=None),
        'independent_feature_error': feature_error, 'first_window_direct_dft_error': dft_error,
    }


def controls(config, setup):
    result = {}
    for rate in (44100, 48000):
        analyzer = Spectrum(np.array([]), rate, config)
        samples = np.arange(analyzer.width * 2)
        k = setup['fundamental_bin']
        base, second = setup['amplitudes']
        phase = 2 * np.pi * k * samples / analyzer.width
        analyzer.pcm = base*np.sin(phase) + second*np.sin(2*phase)
        power, parseval = analyzer.power(0)
        bands, _, _ = analyzer.features(power)
        h1h2, peaks = analyzer.h1h2(power, k * analyzer.spacing)
        expected_h1h2 = 20 * math.log10(base / second)
        predicted_fractions = np.asarray(setup['expected_power_fractions'])
        fraction_error = float(np.max(np.abs(np.power(10, np.asarray(bands)/10) - predicted_fractions)))
        analyzer.pcm = np.random.default_rng(setup['noise_seed']).normal(0, .05, analyzer.width * 2)
        noise = analyzer.features(analyzer.power(0)[0])
        analyzer.pcm *= setup['gain_factor']
        louder = analyzer.features(analyzer.power(0)[0])
        gain_distance = mcd(noise[1], louder[1])
        gain_bands = float(np.max(np.abs(np.asarray(noise[0]) - louder[0])))
        analyzer.pcm[:] = 0
        center = analyzer.width / rate
        silence = note_features(analyzer, (center, center), [], [], False)
        outside = note_features(analyzer, (0, 0), [], [], False)
        tol = config['independent_feature_tolerance']
        result[str(rate)] = {
            'checks': {
                'tone_band_power': fraction_error <= setup['band_power_fraction_tolerance'],
                'tone_harmonic_ratio': peaks == (k, 2*k) and within(error(h1h2, expected_h1h2),
                                                                   setup['harmonic_db_tolerance']),
                'parseval': parseval <= config['parseval_relative_tolerance'],
                'gain_relative_spectrum': gain_distance <= tol and gain_bands <= tol,
                'silence_and_outside_wave': silence['bands_db'] == [0.0] * len(bands)
                    and silence['spectrum_status'] == 'zero_power' and silence['h1h2_db'] is None
                    and outside['spectrum_status'] == 'no_complete_window' and outside['bands_db'] is None
                    and mcd(noise[1], outside['cepstrum']) is None,
            },
            'h1h2_db': h1h2, 'expected_h1h2_db': expected_h1h2, 'peak_bins': peaks,
            'band_db': bands, 'max_band_power_fraction_error': fraction_error, 'relative_parseval_error': parseval,
            'gain_mcd': gain_distance, 'gain_max_band_difference_db': gain_bands,
            'silent_bands_db': silence['bands_db'], 'outside_wave_status': outside['spectrum_status'],
        }
    return result


def load_f0(path):
    out = defaultdict(list)
    with path.open(newline='') as stream:
        for row in csv.DictReader(stream):
            hz = float(row['f0_hz']) if row['f0_hz'] else None
            if (hz is not None) != (row['status'] == 'voiced'):
                raise ValueError('保存したF0の有声判定と値が一致しません')
            out[int(row['note_index']), row['signal']].append((float(row['time_seconds']), hz, row['status']))
    return out


def band_errors(values, targets):
    return [error(a, b) for a, b in zip(values, targets, strict=True)]


def pair_features(a, b):
    distance = mcd(a['cepstrum'], b['cepstrum'])
    band_diff = [None if x is None or y is None else y-x for x, y in
                 zip(a['bands_db'] or [None]*5, b['bands_db'] or [None]*5, strict=True)]
    h1h2 = None if a['h1h2_db'] is None or b['h1h2_db'] is None else b['h1h2_db'] - a['h1h2_db']
    return {'mcd_db': distance, 'band_diff_db': band_diff, 'h1h2_diff_db': h1h2}


def compare_note(rows, published):
    differences = {}
    for label, side in (('recording', 'human'), ('upstream', 'synth')):
        measured = rows['signals'][label]
        differences[label] = band_errors(measured['bands_db'] or [None]*5, published[side]['bandsDb']) + [
            error(measured['h1h2_db'], published[side]['h1h2'])]
    pair = rows['pairs']['recording_vs_upstream']
    differences['pair'] = band_errors(pair['band_diff_db'], published['bandDiffDb']) + [
        error(pair['mcd_db'], published['mcd'])]
    return differences


def first_synth_difference(notes, analyzers):
    record = next((n for n in notes if n['signals']['upstream']['first_window'] is not None), None)
    if record is None:
        return None
    first = record['signals']['upstream']['first_window']
    a, b = (analyzers[key] for key in LABELS[1:])
    sample = first['start_sample']
    da = b.frame(sample) - a.frame(sample)
    bins = b.power(sample)[0] - a.power(sample)[0]
    samples = np.flatnonzero(da)
    windowed = np.flatnonzero(da*a.hann)
    return {'note_index': record['note_index'], 'window': first,
            'first_pcm_delta_sample': None if not len(samples) else sample + int(samples[0]),
            'first_windowed_delta_sample': None if not len(windowed) else sample + int(windowed[0]),
            'pcm_max_abs_difference': float(np.max(np.abs(da))), 'max_bin_power_difference': float(np.max(np.abs(bins)))}


def pitch_control(config, analyzers, f0_rows, alias):
    index, t = config['note_index'], config['center_seconds']
    rows = {}
    for label, analyzer in analyzers.items():
        pitch = [f for f in f0_rows[index, label] if abs(f[0]-t) < 1e-12]
        estimates = alias['selected_notes'][str(index)][label]['centers_with_f0_hz']
        compared = [(wide, narrow) for ts, wide, narrow in estimates if abs(ts-t) < 1e-12]
        if len(pitch) != 1 or len(compared) != 1 or pitch[0][1] != compared[0][0] or compared[0][1] is None:
            raise ValueError('倍音対照のF0と通常F0が固定した窓で一致しません')
        old, new = compared[0]
        power, _ = analyzer.power(analyzer.start(t))
        wide_h, wide_bins = analyzer.h1h2(power, old)
        narrow_h, narrow_bins = analyzer.h1h2(power, new)
        rows[label] = {'wide_f0_hz': old, 'narrow_f0_hz': new, 'wide_h1h2_db': wide_h,
                       'narrow_h1h2_db': narrow_h, 'wide_peak_bins': wide_bins, 'narrow_peak_bins': narrow_bins,
                       'absolute_change_db': abs(narrow_h-wide_h), 'shared_band_db': analyzer.features(power)[0]}
    return {'note_index': index, 'seconds': t, 'signals': rows,
            'predicted_change_in_both_synths': all(rows[key]['absolute_change_db'] >=
                                                   config['minimum_predicted_h1h2_change_db'] for key in LABELS[1:])}


def aggregates(rows, names):
    aligned = [row for row in rows if row['aligned']]
    measures = {}
    for a, b in PAIRS:
        pair = f'{a}_vs_{b}'
        all_values = [row['pairs'][pair] for row in aligned]
        measures[pair] = {
            'mean_mcd_db': finite_stat((x['mcd_db'] for x in all_values), statistics.mean),
            'median_mcd_db': finite_stat((x['mcd_db'] for x in all_values), statistics.median),
            'mean_band_diff_db': {name: finite_stat((x['band_diff_db'][i] for x in all_values), statistics.mean)
                                  for i, name in enumerate(names)},
        }
    h1h2 = {k: finite_stat((row['signals'][k]['h1h2_db'] for row in aligned), statistics.median) for k in LABELS}
    return measures, h1h2


def compare_summary(rows, published, score, config, name):
    names = config['band_names']
    measures, h1h2 = aggregates(rows, names)
    since_recording = measures['recording_vs_upstream']
    errors = {k: error(h1h2[k], published['h1h2Db'][side]) for k, side in
              (('recording', 'human'), ('upstream', 'synth'))}
    errors['mcd'] = error(since_recording['mean_mcd_db'], published['noteMcdDb'])
    errors['bands'] = max(error(since_recording['mean_band_diff_db'][k], published['bandDiffDb'][k]) for k in names)
    raw = score.get('notes', {}).get(name)
    check = {
        'published_song_measures': all(within(v, config['published_db_tolerance']) for v in errors.values()),
        'score_guard_mcd': score['songs'] == [name] and within(
            error(since_recording['mean_mcd_db'], score['guards']['noteMcdDb']), config['score_guard_tolerance']),
    }
    raw_errors = None
    if raw is not None:
        raw_errors = [error(since_recording['mean_mcd_db'], raw['mcd'])]
        for row in rows:
            for k, field in (('recording', 'singer'), ('upstream', 'synth')):
                values = row['signals'][k]
                saved = raw[field][row['note_index']]
                raw_errors.extend(band_errors(values['bands_db'] or [None]*5, saved[:5]))
                raw_errors.append(error(values['h1h2_db'], saved[SCORE_H1H2_COLUMN]))
        check['score_raw_spectral_measures'] = all(within(v, config['score_raw_db_tolerance']) for v in raw_errors)
    return {'checks': check, 'pairs': measures, 'median_h1h2_db': h1h2, 'published_errors_db': errors,
            'max_raw_score_error_db': None if raw_errors is None or None in raw_errors else max(raw_errors)}


def measure_song(case, song, wave_case, paths, f0_path, report, score, alias, out, pilot):
    name, config = song['id'], case['spectrum']
    signals = waveforms(paths, wave_case['render'])
    analyzers = {key: Spectrum(pcm, rate, config) for key, (pcm, rate) in signals.items()}
    f0_rows = load_f0(f0_path)
    if len(report['notes']) != song['notes'] or len(f0_rows) != song['notes'] * len(LABELS):
        raise ValueError(f'音符またはF0の件数が登録と一致しません ({name})')
    selected = song['pilot_indices'] if pilot else range(song['notes'])
    notes = []
    with (out / f'{name}-h1h2-frames.csv').open('w', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(('note_index', 'signal', 'seconds', 'start_sample', 'f0_hz', 'h1_bin', 'h2_bin',
                         'h1_minus_h2_db', 'missing_reason'))
        for i in selected:
            annotation = report['notes'][i]
            bounds, centers = measurement_windows(annotation, wave_case['measurement'])
            track_notes = {k: note_features(a, bounds, f0_rows[i, k], centers, i in song['pilot_indices'],
                                            writer, (i, k)) for k, a in analyzers.items()}
            pairs = {f'{a}_vs_{b}': pair_features(track_notes[a], track_notes[b]) for a, b in PAIRS}
            row = {'note_index': i, 'ipa': annotation['ipa'], 'aligned': annotation['aligned'], 'midi': annotation['midi'],
                   'bounds_seconds': bounds, 'signals': track_notes, 'pairs': pairs}
            row['published_errors_db'] = compare_note(row, annotation)
            notes.append(row)
    spectra = [value for row in notes for value in row['signals'].values()]
    errors = [e for row in notes for series in row['published_errors_db'].values() for e in series]
    dft = [s['first_window_direct_dft_error'] for s in spectra if s['first_window_direct_dft_error'] is not None]
    check = {
        'complete_registered_spectra': len(notes) == len(selected) and all(s['spectrum_frames'] > 0 for s in spectra),
        'parseval_and_features': all(within(s['max_parseval_error'], config['parseval_relative_tolerance'])
            and within(s['independent_feature_error'], config['independent_feature_tolerance']) for s in spectra),
        'published_note_measures': all(within(e, config['published_db_tolerance']) for e in errors),
    }
    if song['pilot_indices']:
        check['pilot_direct_dft'] = len(dft) == len(LABELS) * len(song['pilot_indices']) and all(
            v <= config['power_relpeak_tolerance'] for v in dft)
    controls_here = (pitch_control(case['f0_control'], analyzers, f0_rows, alias)
                     if song['split'] == 'calibration' else None)
    summary = {} if pilot else compare_summary(notes, report['summary'], score, config, name)
    check.update(summary.pop('checks', {}))
    return {'checks': check, 'split': song['split'], 'notes': notes, 'sample_rates': {k: a.rate for k, a in analyzers.items()},
            'max_published_note_error_db': None if None in errors else max(errors),
            'max_pilot_dft_relative_error': max(dft, default=None), 'pitch_control': controls_here,
            'first_synth_difference': first_synth_difference(notes, analyzers), **summary}


def measurement(case, sources, reports, scores, alias, out, run, pilot):
    run(['cargo', 'test', '--locked', '--offline', '-p', 'chimera-cli', 'compare::'],
        cwd=UPSTREAM, stdout=out / 'fixed-compare-tests.log')
    run(['cargo', 'test', '--locked', '--offline', '-p', 'chimera', '--test', 'golden_analysis'],
        cwd=UPSTREAM, stdout=out / 'fixed-analysis-tests.log')
    test = controls(case['spectrum'], case['controls'])
    results = {}
    for song, (_, waves, wave_case, f0) in zip(case['songs'], sources, strict=True):
        if pilot and not song['pilot_indices']:
            continue
        key = song['id']
        results[key] = measure_song(case, song, wave_case, waves, f0, reports[key], scores[song['split']],
                                    alias, out, pilot)
    checks = {'controls': all(all(r['checks'].values()) for r in test.values())}
    for key, result in results.items():
        checks.update({f'{key}_{check}': value for check, value in result['checks'].items()})
    return {'checks': checks, 'pilot': pilot, 'controls': test, 'songs': results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('--pilot', action='store_true', help='登録した調整用の5音符を先に計測する')
    parser.add_argument('--after-pilot', help='全音符の計測前に通過した少数音符の実行ID')
    args = parser.parse_args()
    if os.environ.get('CHIMERA_RUN_STORAGE') != 'rtl9210b':
        parser.error('計測は作業用ディスクを指定してください')
    case = read(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('差分のない固定上流版を用意してください')
    source = WORKSPACE / 'runs' / case['source_run']
    source_path = source / 'manifest.json'
    source_manifest = read(source_path)
    if source_manifest['status'] != 'pass' or source_manifest['upstream_revision'] != revision:
        parser.error('固定上流の通常報告と一致しません')
    report = verified_file(source, source_manifest, 'artifacts/csd/report.json')
    score = verified_file(source, source_manifest, 'artifacts/csd/score.json')
    reports = {song['summary']['id']: song for song in read(report)['songs']}
    score_data = read(score)
    scores = {'calibration': score_data['train'], 'held_out': score_data['heldout']}
    alias_root = WORKSPACE / 'runs' / case['f0_control']['run']
    alias_manifest = alias_root / 'manifest.json'
    alias_info = read(alias_manifest)
    if alias_info['status'] != 'pass':
        parser.error('固定した倍音の対照が合格していません')
    alias_path = verified_file(alias_root, alias_info, 'summary.json')
    tools = WORKSPACE / 'tools'
    inputs = [CASE, source_path, report, score, alias_manifest, alias_path, Path(__file__).resolve(),
              *(tools / name for name in ('measure_csd_envelope_timing.py', 'measure_csd_song_f0.py',
                                           'measure_csd_continuous_song.py', 'measure_speech_timing.py',
                                           'measure_uniform_tube.py', 'upstream_baseline.py'))]
    if not args.pilot:
        if args.after_pilot is None:
            parser.error('全音符の計測には --after-pilot と通過した実行IDが必要です')
        pilot_run = WORKSPACE / 'runs' / args.after_pilot
        pilot_path = pilot_run / 'manifest.json'
        pilot_info = read(pilot_path)
        pilot_summary = verified_file(pilot_run, pilot_info, 'summary.json')
        if (pilot_info['status'] != 'pass' or pilot_info['case_id'] != case['id']
                or pilot_info['case_revision'] != case['revision'] or not read(pilot_summary)['pilot']):
            parser.error('同じケースで通過した少数音符の実行が必要です')
        inputs.extend((pilot_path, pilot_summary))
    sources = []
    for song in case['songs']:
        recording, paths, wave_case = load_inputs(case, source, source_manifest, song, inputs)
        original = WORKSPACE / 'runs' / song['wave_run']
        f0 = verified_file(original, read(original / 'manifest.json'), 'artifacts/note-f0-frames.csv')
        sources.append((recording, paths, wave_case, f0))
        inputs.append(f0)
    details = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision,
               'driver': [sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]],
               'scipy': scipy.__version__, 'pilot_run_id': args.after_pilot,
               'recordings': {s['id']: entry[0] for s, entry in zip(case['songs'], sources, strict=True)}}
    return record_measurement(args.run_id, CASE, inputs, details,
        lambda out, run: measurement(case, sources, reports, scores, read(alias_path), out, run, args.pilot),
        command=None, input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
