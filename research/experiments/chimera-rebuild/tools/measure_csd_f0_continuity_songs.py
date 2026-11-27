"""固定したF0候補選択と追跡をCSD全曲の保存PCMへ適用する。"""

import argparse
from collections import Counter
import csv
import gzip
import io
import json
import math
from pathlib import Path
import subprocess
import sys

import numpy as np

from measure_csd_envelope_timing import error, waveforms, within
from measure_csd_f0_continuity import MODES, describe_frame, measure_track
from measure_csd_f0_search_sensitivity import (add_file, compare_registered, load_all, read_saved_frames,
                                               run_inputs, score_cents, song_statistics)
from measure_csd_note_spectrum import Spectrum, direct_power
from measure_csd_song_f0 import LABELS, NotePitch, measurement_windows, midi_to_hz
from measure_csd_vibrato_aperiodicity import check_independence, median, vibrato
from measure_speech_timing import read
from measure_uniform_tube import record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/csd-f0-continuity-songs.json'
ROOT = WORKSPACE.parents[2]
COMPARISONS = (('wide', 'local'), ('local', 'tracked'), ('wide', 'tracked'))


def optional_float(value):
    return float(value) if value else None


def matches_period(result, status, hz, aperiodicity, lag, limits):
    return (result.status == status and result.lag == (int(lag) if lag else None)
            and within(error(result.hz, optional_float(hz)), limits['f0_replay_tolerance_hz'])
            and within(error(result.aperiodicity, optional_float(aperiodicity)), limits['aperiodicity_replay_tolerance']))


def matches_legacy_frame(row, original, harmonics, limits):
    return row['power'] == optional_float(original['mean_square']) and all(
        matches_period(row[k], original[f'{k}_status'], original[f'{k}_hz'],
                       original[f'{k}_aperiodicity'], original[f'{k}_lag'], limits)
        and within(error(harmonics[k][0], optional_float(original[f'{k}_h1h2_db'])), limits['metric_replay_tolerance'])
        for k in MODES[:2])


def matches_single_note(rows, reference, limits):
    return len(rows) == len(reference) and all(
        row['time'] == float(saved['seconds']) and all(matches_period(
            row[k], saved[f'{k}_status'], saved[f'{k}_f0_hz'], saved[f'{k}_cmnd'], saved[f'{k}_lag_samples'], limits)
            for k in MODES)
        for row, saved in zip(rows, reference, strict=True))


def summarize_track(rows, target, harmonics, periodicity, large_step):
    result = {}
    for mode in MODES:
        track = [score_cents(row[mode].hz, target) for row in rows]
        steps = [abs(b - a) for a, b in zip(track, track[1:]) if a is not None and b is not None]
        h1h2 = [item[mode][0] for item in harmonics]
        result[mode] = {**vibrato(track, periodicity), 'f0_cents_median': median(track),
                        'voiced_share': sum(x is not None for x in track) / len(rows),
                        'aperiodicity': median(row[mode].aperiodicity for row in rows),
                        'h1h2_db': median(h1h2), 'h1h2_frames': sum(x is not None for x in h1h2),
                        'large_steps': sum(x >= large_step for x in steps), 'total_step_cents': math.fsum(steps)}
    return result


def frame_annotations(row, target, note, index):
    return describe_frame(row, target) | {'note_index': index, 'ipa': note['ipa'],
        'note_start_seconds': note['start'], 'note_end_seconds': note['end'],
        'aligned': note['aligned']}


def direct_harmonics(spectrum, start, row, harmonics):
    independent_power = direct_power(spectrum, start)
    independent = {k: spectrum.h1h2(independent_power, row[k].hz) if row[k].hz is not None else (None, (None, None))
                   for k in MODES}
    differences = {k: error(harmonics[k][0], independent[k][0]) for k in MODES}
    tolerance = spectrum.config['independent_feature_tolerance']
    return {'h1h2_difference_db': differences, 'matches': all(
        independent[k][1] == harmonics[k][1] and within(differences[k], tolerance) for k in MODES)}


def compare_frame(row, original, context, limits, counts, firsts, writer):
    note, index, label, target, spectrum, position = context
    harmonics = dict.fromkeys(MODES, (None, (None, None)))
    start = spectrum.start(row['time']) if position % 2 == 0 and row['wide'].hz is not None else None
    parseval_ok = True
    if start is not None:
        power, parseval = spectrum.power(start)
        parseval_ok = parseval <= spectrum.config['parseval_relative_tolerance']
        harmonics.update({k: spectrum.h1h2(power, row[k].hz) if row[k].hz is not None else (None, (None, None))
                          for k in MODES})

    if (original is None or int(original['note_index']) != index or original['signal'] != label
            or float(original['seconds']) != row['time']):
        raise ValueError(f'従来の保存窓と音符・波形・時刻が一致しません ({index}, {label}, {row["time"]})')
    legacy_ok = matches_legacy_frame(row, original, harmonics, limits)
    for mode in MODES:
        counts[f'{mode}_{row[mode].status}'] += 1
        cents = score_cents(row[mode].hz, target)
        counts[f'{mode}_high'] += cents is not None and cents >= limits['high_error_cents']
        counts[f'{mode}_low'] += cents is not None and cents <= -limits['high_error_cents']
        counts[f'{mode}_available_h1h2'] += harmonics[mode][0] is not None

    dft_ok = True
    direct = None
    for a, b in COMPARISONS:
        name = f'{a}_to_{b}'
        if row[a].hz != row[b].hz:
            counts[f'{name}_f0_windows'] += 1
            if f'{name}_first_f0' not in firsts:
                firsts[f'{name}_first_f0'] = frame_annotations(row, target, note, index)
        if harmonics[a][0] != harmonics[b][0]:
            counts[f'{name}_h1h2_windows'] += 1
            if f'{name}_first_h1h2' not in firsts:
                if direct is None:
                    direct = direct_harmonics(spectrum, start, row, harmonics)
                dft_ok &= direct['matches']
                firsts[f'{name}_first_h1h2'] = frame_annotations(row, target, note, index) | {
                    'fft_start_sample': start, 'fft_spacing_hz': spectrum.spacing,
                    'h1h2_by_condition': {k: {'db': value, 'peak_bins': bins} for k, (value, bins) in harmonics.items()},
                    'direct_dft': direct}
    counts['windows'] += 1

    voiced_ok = row['wide'].status == row['local'].status == row['tracked'].status
    membership_ok = (all(row[k] in row['candidates'] for k in ('local', 'tracked')) if row['wide'].hz is not None
                     else not row['candidates'])
    fields = [value for k in MODES for value in (*row[k], harmonics[k][0])]
    writer.writerow((index, label, row['time'], target, row['power'], *fields,
                     json.dumps([item._asdict() for item in row['candidates']], separators=(',', ':'))))
    return harmonics, {'legacy_windows': legacy_ok, 'parseval': parseval_ok, 'direct_dft': dft_ok,
                       'same_voicing_and_valid_candidates': voiced_ok and membership_ok}


def compare_song(song, configurations, archive, tracker, case, limits, spectrum_config, periodicity, out, reference):
    paths, render, pitch, registered, _ = configurations
    official = registered['official']
    notes = official['notes']
    archived_times = read_saved_frames(registered['frames'])
    pcms = waveforms(paths, render)
    minimum = min(n['midi'] for n in notes)
    estimators = {k: NotePitch(pcm, rate, minimum, pitch) for k, (pcm, rate) in pcms.items()}
    spectra = {k: Spectrum(pcm, rate, spectrum_config) for k, (pcm, rate) in pcms.items()}
    if pitch['search_half_width_semitones'] != limits['upper_semitones'][0]:
        raise ValueError('通常条件の探索範囲が音符の登録と一致しません')
    ratios = tuple(math.exp2(value / 12) for value in limits['upper_semitones'])
    counts = {k: Counter() for k in LABELS}
    firsts = {k: {} for k in LABELS}
    checks, rows = Counter(), []
    with gzip.open(archive, 'rt', newline='') as old, \
            (out / f"{song['id']}-continuity-frames.csv.gz").open('wb') as binary, \
            gzip.GzipFile(fileobj=binary, filename='', mode='wb', compresslevel=4, mtime=0) as compressed, \
            io.TextIOWrapper(compressed, encoding='utf-8', newline='') as stream:
        original = csv.DictReader(old)
        writer = csv.writer(stream, lineterminator='\n')
        fields = ('status', 'hz', 'cmnd', 'lag_samples', 'h1h2_db')
        writer.writerow(('note_index', 'signal', 'seconds', 'target_hz', 'mean_square',
                         *(f'{mode}_{field}' for mode in MODES for field in fields), 'candidates'))
        for i, note in enumerate(notes):
            _, centers = measurement_windows(note, pitch)
            target = midi_to_hz(note['midi'])
            signals = {}
            for label in LABELS:
                if not centers or centers != [row[0] for row in archived_times[i, label]]:
                    raise ValueError(f"保存された5 ms格子と一致しません ({song['id']}, {i}, {label})")
                track, verified = measure_track(estimators[label], centers, target, ratios, tracker, limits,
                                               independent_stride=limits['independent_sample_stride'])
                checks['direct_pitch'] += not verified
                if reference is not None and i == reference['index']:
                    checks['previous_tracked_note'] += not matches_single_note(track, reference['rows'][label], limits)
                harmonic_rows = []
                for j, row in enumerate(track):
                    context = note, i, label, target, spectra[label], j
                    h1h2, tested = compare_frame(row, next(original, None), context, limits,
                                                   counts[label], firsts[label], writer)
                    harmonic_rows.append(h1h2)
                    checks.update({name: not passed for name, passed in tested.items()})

                metrics = summarize_track(track, target, harmonic_rows, periodicity, case['large_step_cents'])
                signals[label] = metrics
                permissible = metrics['local']['total_step_cents'] + case['variation_tolerance_cents']
                checks['tracked_variation_not_greater'] += metrics['tracked']['total_step_cents'] > permissible
                for a, b in COMPARISONS:
                    name = f'{a}_to_{b}'
                    counts[label][f'{name}_h1h2_note_medians'] += metrics[a]['h1h2_db'] != metrics[b]['h1h2_db']
                    counts[label][f'{name}_vibrato_statuses'] += metrics[a]['status'] != metrics[b]['status']
            rows.append({'note_index': i, 'ipa': note['ipa'], 'aligned': note['aligned'], 'signals': signals})

        checks['all_legacy_rows_consumed'] += next(original, None) is not None

    passed = {k: failures == 0 for k, failures in checks.items()}
    passed['finite_pcm'] = all(np.isfinite(pcm).all() for pcm, _ in pcms.values())
    passed['registered_counts'] = (len(notes) == song['notes'] and len(archived_times) == len(notes) * len(LABELS)
                                   and all(c['windows'] == song['frames_per_signal'] for c in counts.values()))
    passed.update(compare_registered(rows, official, registered['periodicity'], registered.get('spectrum'),
                                     registered.get('raw_score'), limits))
    independent = check_independence([m for row in rows for modes in row['signals'].values() for m in modes.values()], periodicity)
    passed['direct_vibrato'] = independent['matches']
    aggregates = {}
    for label in LABELS:
        by_mode = song_statistics(rows, label, MODES)
        for mode, stats in by_mode.items():
            aligned = [row['signals'][label][mode] for row in rows if row['aligned']]
            stats.update(f0_median_cents=median(m['f0_cents_median'] for m in aligned),
                         large_steps=sum(m['large_steps'] for m in aligned),
                         total_step_cents=math.fsum(m['total_step_cents'] for m in aligned))
        aggregates[label] = by_mode
    return {'checks': passed, 'failed_windows_or_notes': {k: n for k, n in checks.items() if n},
            'split': song['split'], 'note_metrics': rows, 'frames': counts, 'first_changes': firsts,
            'metrics': aggregates, 'independent_vibrato': independent}


def measure(case, corpus, configurations, archives, tracker, spectrum, periodicity, previous, out, execute):
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera-cli', 'compare::'],
            cwd=UPSTREAM, stdout=out / 'fixed-compare-tests.log')
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera', '--test', 'golden_analysis'],
            cwd=UPSTREAM, stdout=out / 'fixed-analysis-tests.log')
    songs = {}
    checks = {}
    for song in corpus['songs']:
        name = song['id']
        reference = previous if name == previous['song'] else None
        result = compare_song(song, configurations[name], archives[name], tracker, case, corpus['measurement'],
                              spectrum, periodicity, out, reference)
        songs[name] = result
        checks.update({f'{name}/{k}': v for k, v in result['checks'].items()})
    windows = sum(count['windows'] for row in songs.values() for count in row['frames'].values())
    checks['all_registered_windows'] = windows == case['conventional_window_count']
    predictions = {f'{k}/fewer_high_windows_in_corpus': sum(s['frames'][k]['tracked_high'] for s in songs.values())
                   < sum(s['frames'][k]['wide_high'] for s in songs.values()) for k in ('upstream', 'candidate')}
    for name, result in songs.items():
        measured = result['metrics']['recording']
        predictions[f'{name}/recording_median_change'] = within(
            error(measured['tracked']['f0_median_cents'], measured['wide']['f0_median_cents']),
            case['maximum_recording_median_change_cents'])
    return {'checks': checks, 'predictions': predictions, 'windows': windows, 'songs': songs}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    case = read(CASE)
    revision = case['upstream_revision']
    if (subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip() != revision
            or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True)):
        parser.error('変更のない固定上流版が必要です')
    corpus_path, tracker_path = (CASE.parent / case[k] for k in ('corpus_case', 'tracker_case'))
    corpus, tracker = read(corpus_path), read(tracker_path)
    if any(config['upstream_revision'] != revision for config in (corpus, tracker)):
        parser.error('曲の基準または追跡の登録と固定上流が一致しません')
    spectrum, periodicity = (CASE.parent / corpus[k] for k in ('spectrum_case', 'periodicity_case'))
    inputs = [CASE, corpus_path, tracker_path, spectrum, periodicity, Path(__file__).resolve(),
              *(WORKSPACE / 'tools' / name for name in (
                  'measure_csd_f0_continuity.py', 'measure_csd_f0_search_sensitivity.py', 'measure_csd_note_spectrum.py',
                  'measure_csd_vibrato_aperiodicity.py', 'measure_csd_long_notes.py', 'select_csd_long_notes.py',
                  'measure_csd_song_f0.py', 'measure_vowel_voice.py', 'measure_csd_envelope_timing.py',
                  'measure_csd_continuous_song.py', 'measure_speech_timing.py', 'measure_uniform_tube.py', 'upstream_baseline.py'))]
    legacy = run_inputs(case['corpus_reference_run'], revision, inputs)
    archive = {s['id']: add_file(legacy, f"artifacts/{s['id']}-frames.csv.gz", inputs) for s in corpus['songs']}
    validated = run_inputs(case['single_note_reference_run'], revision, inputs)
    prior_tracker = validated[0] / validated[1]['source_snapshot'] / tracker_path.relative_to(ROOT)
    if sha256(prior_tracker) != sha256(tracker_path):
        parser.error('追跡の事前登録は1音符の検証時と同じファイルを指定してください')
    control_file = CASE.parent / tracker['held_out_control_case']
    inputs.extend([prior_tracker, control_file])
    control = read(control_file)
    one_note = add_file(validated, 'artifacts/pitch-tracks.csv', inputs)
    known = {k: [] for k in LABELS}
    with one_note.open(newline='') as file:
        for row in csv.DictReader(file):
            if row['signal'] in known:
                known[row['signal']].append(row)
    previous = {'song': control['song'], 'index': control['note_index'], 'rows': known}
    configurations = load_all(corpus, inputs)
    details = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision,
               'analysis_directory': str(Path.cwd()), 'analysis_command': [sys.executable, *sys.argv],
               'recordings': {k: row[-1] for k, row in configurations.items()}}
    return record_measurement(args.run_id, CASE, inputs, details,
        lambda out, execute: measure(case, corpus, configurations, archive, tracker, read(spectrum)['spectrum'],
                                     read(periodicity)['measurement'], previous, out, execute),
        command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
