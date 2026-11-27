"""CSDの保存済みPCMでYINの閾値だけを変更する。"""

import argparse
from collections import Counter
import csv
import gzip
import io
import math
from pathlib import Path
import subprocess
import sys

import numpy as np

from measure_csd_envelope_timing import error, waveforms, within
from measure_csd_f0_continuity_songs import matches_period, optional_float
from measure_csd_f0_search_sensitivity import (Result, add_file, agree, compare_registered, load_all,
                                              period_window, run_inputs, score_cents, select_period, song_statistics)
from measure_csd_note_spectrum import Spectrum
from measure_csd_song_f0 import LABELS, NotePitch, measurement_windows, midi_to_hz
from measure_csd_vibrato_aperiodicity import check_independence, median, vibrato
from measure_speech_timing import read
from measure_uniform_tube import record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE


CASE = WORKSPACE / 'cases/csd-f0-yin-threshold.json'
ROOT = WORKSPACE.parents[2]
MODES = ('wide', 'lower_threshold')


def measure_window(estimator, t, target, thresholds):
    power, values = period_window(estimator, t, target)
    low = max(2, int(estimator.rate / (target * estimator.search_range)))
    if values is None:
        return power, low, values, (Result('outside_wave', None, 1.0, None),) * len(thresholds)
    if low >= len(values):
        raise ValueError('登録したYINの探索範囲にラグがありません')
    results = tuple(select_period(values, low, estimator.rate, threshold, power < estimator.gate)
                    for threshold in thresholds)
    return power, low, values, results


def direct_window(estimator, t, target, thresholds):
    start = int(t * estimator.rate) - estimator.width // 2
    end = start + estimator.width
    if start < 0 or end > len(estimator.pcm):
        return (Result('outside_wave', None, 1.0, None),) * len(thresholds), [None] * len(thresholds), None
    window = estimator.pcm[start:end]
    high = min(len(window) // 2, int(estimator.rate / (target / estimator.search_range)))
    low = max(2, int(estimator.rate / (target * estimator.search_range)))
    count = len(window) - high
    gated = np.dot(window, window) / len(window) < estimator.gate
    accum, cmnd = 0.0, [1.0]
    for lag in range(1, high + 1):
        delta = window[:count] - window[lag:lag + count]
        distance = float(np.dot(delta, delta))
        accum += distance
        cmnd.append(lag * distance / accum if accum else 1.0)
    minimum = min(range(low, high + 1), key=cmnd.__getitem__)
    results, crossings = [], []
    for threshold in thresholds:
        first = next((lag for lag in range(low, high + 1) if cmnd[lag] < threshold), None)
        crossings.append(first)
        lag = minimum if first is None else first
        hz = None
        if first is not None:
            while lag < high and cmnd[lag + 1] < cmnd[lag]:
                lag += 1
            adjusted = float(lag)
            if 1 < lag < high:
                left, mid, right = cmnd[lag - 1:lag + 2]
                curvature = left - 2 * mid + right
                if abs(curvature) > 1e-12:
                    adjusted += (left - right) / (2 * curvature)
            hz = estimator.rate / adjusted
        status = 'below_energy_gate' if gated else ('unvoiced_period' if hz is None else 'voiced')
        results.append(Result(status, None if gated else hz, cmnd[lag], lag))
    return results, crossings, {'lag_samples': minimum, 'cmnd': cmnd[minimum]}


def agrees_pair(measured, comparison, limits):
    return all(r.lag == ref.lag and agree(r, ref.status, ref.hz, ref.aperiodicity, limits)
               for r, ref in zip(measured, comparison, strict=True))


def gzip_csv(path):
    return io.TextIOWrapper(gzip.GzipFile(filename=str(path), mode='wb', compresslevel=4, mtime=0),
                            encoding='utf-8', newline='')


def measure_note(estimator, spectrum, centers, original, note, key, thresholds, limits, periodicity,
                 writer, counts, examples, checks):
    index, label = key
    target = midi_to_hz(note['midi'])
    tracks = {mode: {'cents': [], 'aper': [], 'harmonics': []} for mode in MODES}
    for position, t in enumerate(centers):
        saved = next(original, None)
        if saved is None or (int(saved['note_index']), saved['signal'], float(saved['seconds']),
                             float(saved['target_hz'])) != (index, label, t, target):
            raise ValueError(f'保存済みの音符、波形、窓中心または譜面音高が一致しません ({key}, {t})')
        power, low, values, pair = measure_window(estimator, t, target, thresholds)
        wide, lower = pair
        checks['baseline_windows'] += not (power == optional_float(saved['mean_square']) and matches_period(
            wide, saved['wide_status'], saved['wide_hz'], saved['wide_cmnd'], saved['wide_lag_samples'], limits))
        changed = wide != lower
        loss = wide.hz is not None and lower.hz is None
        shift = wide.hz is not None and lower.hz is not None and wide.lag != lower.lag
        checks['voicing_and_lag_order'] += (wide.hz is None and lower.hz is not None) or (
            shift and lower.lag < wide.lag) or ((wide.status == 'below_energy_gate') != (lower.status == 'below_energy_gate'))
        if changed or counts['windows'] % limits['independent_sample_stride'] == 0:
            direct, crossings, minimum = direct_window(estimator, t, target, thresholds)
            counts['independent_windows'] += 1
            checks['independent_windows'] += not agrees_pair(pair, direct, limits)
            flags = {'yin_change': changed, 'voiced_to_missing': loss, 'voiced_to_longer_lag': shift}
            for name, present in flags.items():
                if present and name not in examples:
                    examples[name] = {'note_index': index, 'ipa': note['ipa'], 'seconds': t,
                                      'window_in_note': position, 'target_hz': target, 'mean_square': power,
                                      'energy_gate': estimator.gate, 'first_crossings': crossings,
                                      'minimum': minimum, **{m: r._asdict() for m, r in zip(MODES, pair, strict=True)}}
        counts.update({'windows': 1, 'changed_yin': changed, 'voiced_to_missing': loss,
                       'voiced_to_longer_lag': shift, 'gate_masked_yin_change': changed and wide.status == 'below_energy_gate'})

        sample = spectrum.start(t) if position % 2 == 0 and wide.hz is not None else None
        harmonics = [None, None]
        if sample is not None:
            fft, parseval = spectrum.power(sample)
            checks['fft_parseval'] += parseval > spectrum.config['parseval_relative_tolerance']
            harmonics = [spectrum.h1h2(fft, r.hz)[0] if r.hz is not None else None for r in pair]
        checks['baseline_h1h2'] += not within(error(harmonics[0], optional_float(saved['wide_h1h2_db'])),
                                              limits['metric_replay_tolerance'])
        counts['changed_h1h2'] += harmonics[0] != harmonics[1]
        for mode, measured, h1h2 in zip(MODES, pair, harmonics, strict=True):
            cents = score_cents(measured.hz, target)
            tracks[mode]['cents'].append(cents)
            tracks[mode]['aper'].append(measured.aperiodicity)
            tracks[mode]['harmonics'].append(h1h2)
            counts[f'{mode}_{measured.status}'] += 1
            counts[f'{mode}_high'] += cents is not None and cents >= limits['high_error_cents']

        minimum = float(np.min(values[low:])) if values is not None else None
        writer.writerow((*key, position, t, target, power, minimum,
                         *(v for measured, h in zip(pair, harmonics, strict=True) for v in (*measured, h))))
    result = {}
    for mode, track in tracks.items():
        cents = track['cents']
        result[mode] = {**vibrato(cents, periodicity), 'f0_cents_median': median(cents),
                        'voiced_share': sum(v is not None for v in cents) / len(cents),
                        'aperiodicity': median(track['aper']), 'h1h2_db': median(track['harmonics'])}
    counts['changed_note_h1h2'] += result[MODES[0]]['h1h2_db'] != result[MODES[1]]['h1h2_db']
    counts['changed_note_vibrato_status'] += result[MODES[0]]['status'] != result[MODES[1]]['status']
    return result


def verify_recording_controls(registrations, estimator, thresholds, limits):
    controls = []
    for song, archive, indices in registrations:
        for saved in (row for row in archive['probes'] if row['note_window'] in indices):
            t, target = saved['time_seconds'], saved['target_hz']
            _, _, _, measured = measure_window(estimator, t, target, thresholds)
            direct, crossings, minimum = direct_window(estimator, t, target, thresholds)
            reference = [Result(**saved[name]) for name in ('wide', 'lower_yin_threshold')]
            controls.append({'song': song, 'note_index': archive['note_index'], 'note_window': saved['note_window'],
                             'seconds': t, 'matches': agrees_pair(measured, reference, limits)
                             and agrees_pair(measured, direct, limits), 'first_crossings': crossings, 'minimum': minimum,
                             **{mode: r._asdict() for mode, r in zip(MODES, measured, strict=True)}})
    return controls


def compare_song(song, configuration, archive, registered, thresholds, spectrum_cfg, periodicity, limits, out):
    paths, render, pitch, references, _ = configuration
    official = references['official']
    notes = official['notes']
    minimum = min(n['midi'] for n in notes)
    pcm = waveforms(paths, render)
    if pitch['yin_threshold'] != thresholds[0] or pitch['search_half_width_semitones'] != limits['upper_semitones'][0]:
        raise ValueError('通常の閾値または探索範囲が保存基準と一致しません')
    estimators = {k: NotePitch(x, rate, minimum, pitch) for k, (x, rate) in pcm.items()}
    spectra = {k: Spectrum(x, rate, spectrum_cfg) for k, (x, rate) in pcm.items()}
    counts = {k: Counter() for k in LABELS}
    examples = {k: {} for k in LABELS}
    checks, rows = Counter(), []
    with gzip.open(archive, 'rt', newline='') as prior, gzip_csv(out / f"{song['id']}-yin-threshold.csv.gz") as stream:
        original = csv.DictReader(prior)
        writer = csv.writer(stream, lineterminator='\n')
        fields = ('status', 'hz', 'cmnd', 'lag_samples', 'h1h2_db')
        writer.writerow(('note_index', 'signal', 'window_in_note', 'seconds', 'target_hz', 'mean_square', 'minimum_cmnd',
                         *(f'{mode}_{field}' for mode in MODES for field in fields)))
        for index, note in enumerate(notes):
            _, centers = measurement_windows(note, pitch)
            signals = {label: measure_note(estimators[label], spectra[label], centers, original, note,
                                           (index, label), thresholds, limits, periodicity, writer, counts[label],
                                           examples[label], checks) for label in LABELS}
            rows.append({'note_index': index, 'aligned': note['aligned'], 'signals': signals})
        checks['all_saved_windows_consumed'] += next(original, None) is not None
    results = {key: count == 0 for key, count in checks.items()}
    results.update(compare_registered(rows, official, references['periodicity'], references.get('spectrum'),
                                      references.get('raw_score'), limits))
    results['counts'] = len(notes) == song['notes'] and all(c['windows'] == song['frames_per_signal'] for c in counts.values())
    results['finite_pcm'] = all(np.isfinite(x).all() for x, _ in pcm.values())
    direct = check_independence([mode for row in rows for track in row['signals'].values() for mode in track.values()], periodicity)
    results['direct_vibrato'] = direct['matches']
    aggregates = {label: song_statistics(rows, label, MODES) for label in LABELS}
    return {'split': song['split'], 'checks': results, 'failed_windows': {k: n for k, n in checks.items() if n},
            'windows': counts, 'first_changes': examples, 'note_metrics': aggregates, 'direct_vibrato': direct,
            'recording_controls': verify_recording_controls(registered, estimators['recording'], thresholds, limits)}


def known_controls(tracker, tone, pitch, thresholds, limits, out):
    rate = tone['sample_rate_hz']
    target = midi_to_hz(tone['midi'])
    time = np.arange(round(tone['duration_seconds'] * rate)) / rate
    offset = max(tone['cents_offsets'])
    high = target * math.exp2(offset / 1200)
    phase = 2 * np.pi * high * time
    high_wave = tone['relative_amplitude'] * sum(a * np.sin(k * phase)
        for k, a in enumerate(tone['harmonic_amplitudes'][-1], 1))
    dip = tracker['fundamental_dip']
    level = dip['fundamental_relative_amplitude_at_dip']
    envelope = np.interp(time, [*dip['transition_in_seconds'], *dip['transition_out_seconds']], [1, level, level, 1])
    phase = 2 * np.pi * dip['known_hz'] * time
    dip_wave = tone['relative_amplitude'] * (
        envelope * np.sin(phase) + dip['second_harmonic_relative_amplitude'] * np.sin(2 * phase))
    hop = pitch['hop_seconds']
    a, b = [round(t / hop) for t in tracker['constant_interval_seconds']]
    output, agrees = {}, True
    with (out / 'known-tone-threshold.csv').open('w', newline='') as stream:
        writer = csv.writer(stream, lineterminator='\n')
        writer.writerow(('control', 'known_hz', 'seconds', 'threshold', 'status', 'hz', 'cmnd', 'lag_samples'))
        for label, wave, known in (('detuned_with_harmonics', high_wave, high), ('weak_fundamental', dip_wave, dip['known_hz'])):
            estimator = NotePitch(wave, rate, tone['midi'], pitch)
            errors = {mode: [] for mode in MODES}
            octaves = Counter(dict.fromkeys(MODES, 0))
            for frame in range(a, b + 1):
                t = frame * hop
                _, _, _, pair = measure_window(estimator, t, target, thresholds)
                reference, _, _ = direct_window(estimator, t, target, thresholds)
                agrees &= agrees_pair(pair, reference, limits)
                for mode, threshold, result in zip(MODES, thresholds, pair, strict=True):
                    errors[mode].append(abs(result.hz - known) if result.hz is not None else None)
                    octaves[mode] += result.hz is not None and abs(result.hz - 2 * known) <= dip['octave_error_tolerance_hz']
                    writer.writerow((label, known, t, threshold, *result))
            output[label] = {'known_hz': known, 'octave_windows': octaves,
                             'maximum_error_hz': {m: max(v) if all(e is not None for e in v) else None
                                                  for m, v in errors.items()}}
    return output, agrees


def measure(case, corpus, configurations, previous, controls, tracker, tone, pitch, spectrum, periodicity, out, execute):
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera-cli', 'compare::'],
            cwd=UPSTREAM, stdout=out / 'fixed-compare-tests.log')
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera', '--test', 'golden_analysis'],
            cwd=UPSTREAM, stdout=out / 'fixed-analysis-tests.log')
    thresholds = case['thresholds']
    limits = corpus['measurement']
    songs = {s['id']: compare_song(s, configurations[s['id']], previous[s['id']], controls.get(s['id'], []),
                                  thresholds, spectrum, periodicity, limits, out) for s in corpus['songs']}
    known, direct = known_controls(tracker, tone, pitch, thresholds, limits, out)
    checks = {f'{name}_{key}': v for name, song in songs.items() for key, v in song['checks'].items()}
    totals = Counter()
    for song in songs.values():
        for counts in song['windows'].values():
            totals.update(counts)
    recordings = [r for song in songs.values() for r in song['recording_controls']]
    checks.update(frame_counts=totals['windows'] == case['frame_count'] and totals['wide_voiced'] == case['baseline_voiced_frames']
                  and sum(s['notes'] for s in corpus['songs']) == case['note_count'],
                  known_direct=direct, prior_control_replay=len(recordings) == sum(len(c['windows']) for c in case['recording_controls'])
                  and all(r['matches'] for r in recordings))
    predictions = {'corpus_voiced_to_longer_lag': totals['voiced_to_longer_lag'] > 0,
                   'corpus_voiced_to_missing': totals['voiced_to_missing'] > 0,
                   'detuned_retained': all(within(v, tracker['known_tone_tolerance_hz'])
                                          for v in known['detuned_with_harmonics']['maximum_error_hz'].values()),
                   'weak_fundamental_octave_remains': known['weak_fundamental']['octave_windows']['lower_threshold'] > 0,
                   'previous_focuses_change_and_early_window_remains': bool(recordings) and all(
                       r['lower_threshold']['lag'] > r['wide']['lag'] if r['note_window'] >= 0 else r['lower_threshold'] == r['wide']
                       for r in recordings)}
    return {'checks': checks, 'predictions': predictions, 'thresholds': thresholds, 'totals': totals,
            'known_controls': known, 'songs': songs}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    case = read(CASE)
    revision = case['upstream_revision']
    if (subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip() != revision
            or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True)):
        parser.error('変更のない固定上流版が必要です')
    if len(case['thresholds']) != 2 or not 0 < case['thresholds'][1] < case['thresholds'][0] < 1:
        parser.error('通常値より小さい閾値を指定してください')
    corpus_path, tracker_path = (CASE.parent / case[k] for k in ('corpus_case', 'known_wave_case'))
    corpus, tracker = read(corpus_path), read(tracker_path)
    spectrum_path, periodicity_path = (CASE.parent / corpus[k] for k in ('spectrum_case', 'periodicity_case'))
    tone_path = CASE.parent / tracker['detuned_case']
    tone = read(tone_path)
    pitch_path = CASE.parent / tone['pitch_case']
    inputs = [CASE, corpus_path, tracker_path, spectrum_path, periodicity_path, tone_path, pitch_path, Path(__file__).resolve(),
              *(WORKSPACE / 'tools' / name for name in (
                  'measure_csd_f0_search_sensitivity.py', 'measure_csd_f0_continuity_songs.py', 'measure_csd_f0_continuity.py',
                  'measure_csd_note_spectrum.py', 'measure_csd_vibrato_aperiodicity.py', 'measure_csd_long_notes.py',
                  'select_csd_long_notes.py', 'measure_csd_song_f0.py', 'measure_vowel_voice.py', 'measure_csd_envelope_timing.py',
                  'measure_csd_continuous_song.py', 'measure_speech_timing.py', 'measure_uniform_tube.py', 'upstream_baseline.py'))]
    prior = run_inputs(case['corpus_reference_run'], revision, inputs)
    previous = {s['id']: add_file(prior, f"artifacts/{s['id']}-continuity-frames.csv.gz", inputs) for s in corpus['songs']}
    configurations = load_all(corpus, inputs)
    recordings = {k: row[-1] for k, row in configurations.items()}
    if any(info['sha256'] != prior[1]['recordings'][name]['sha256'] for name, info in recordings.items()):
        parser.error('保存済みの全曲比較と録音が一致しません')
    controls = {}
    for spec in case['recording_controls']:
        run = run_inputs(spec['run'], revision, inputs)
        name = spec['song']
        if recordings[name]['sha256'] != run[1]['recording']['sha256']:
            parser.error(f'独立周期の評価と録音が一致しません ({name})')
        controls.setdefault(name, []).append((name, read(add_file(run, 'summary.json', inputs)), spec['windows']))
    details = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision,
               'baseline_run': case['corpus_reference_run'], 'recordings': recordings,
               'analysis_directory': str(Path.cwd()), 'analysis_command': [sys.executable, *sys.argv]}
    return record_measurement(args.run_id, CASE, inputs, details,
        lambda out, execute: measure(case, corpus, configurations, previous, controls, tracker, tone,
                                     read(pitch_path)['measurement'], read(spectrum_path)['spectrum'],
                                     read(periodicity_path)['measurement'], out, execute), command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
