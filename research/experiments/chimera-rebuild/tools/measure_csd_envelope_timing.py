"""固定上流のCSDの音量包絡、全曲の時間差、句の有声開始を照合する。"""

import argparse
from collections import Counter
import csv
import math
import os
from pathlib import Path
import random
import statistics
import subprocess
import sys
import wave

import numpy as np

from measure_csd_continuous_song import samples
from measure_csd_song_f0 import LABELS, NotePitch, midi_to_hz
from measure_speech_timing import read
from measure_uniform_tube import record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/csd-envelope-timing.json'
PAIRS = (('recording', 'upstream'), ('recording', 'candidate'), ('upstream', 'candidate'))
ENVELOPE_FIELDS = ('starts', 'sizes', 'power', 'unfloored', 'db')
VOWELS = set('a ae ai ao au e ei eo er i ii oi oo ou u uu'.split())
VOICELESS = set('p t k f th s sh h ch'.split())
ONSET_KEYS = {'vowel': 'vowelOnsetSec', 'voiceless': 'voicelessOnsetSec', 'voiced': 'voicedOnsetSec'}
SCORE_ONSET_COLUMN = 10  # 固定上流の compare/score.rs::ONSET


def envelope(pcm, rate, settings):
    width = math.floor(rate * settings['frame_seconds'] + .5)
    starts = np.arange(0, len(pcm), width)
    sizes = np.diff(starts, append=len(pcm))
    power = np.add.reduceat(pcm.astype(float, copy=False)**2, starts) / sizes
    db = 10 * np.log10(power + settings['power_epsilon'])
    return {'starts': starts, 'sizes': sizes, 'power': power, 'unfloored': db,
            'db': np.maximum(db, settings['floor_db'])}


def direct_envelope(pcm, rate, settings):
    # 全窓のスカラー集計で、配列の添字と最終部分窓を独立に確認する。
    width = math.floor(rate * settings['frame_seconds'] + .5)
    result = []
    for start in range(0, len(pcm), width):
        chunk = pcm[start:start+width].astype(float, copy=False)
        energy = math.fsum(float(sample)**2 for sample in chunk) / len(chunk)
        result.append(max(settings['floor_db'], 10 * math.log10(energy + settings['power_epsilon'])))
    return result


def correlations(reference, shifted, radius):
    n = min(len(reference), len(shifted))
    rows = []
    for lag in range(-radius, radius + 1):
        start, end = max(0, -lag), min(n, n-lag)
        r = None
        if end - start >= 2:
            a, b = reference[start:end], shifted[start+lag:end+lag]
            if np.ptp(a) > 0 and np.ptp(b) > 0:
                ac, bc = a - a.mean(), b - b.mean()
                r = float(np.dot(ac, bc) / math.sqrt(np.dot(ac, ac) * np.dot(bc, bc)))
        rows.append((lag, max(0, end-start), r))
    return rows


def direct_correlations(reference, shifted, radius):
    # 中心化した配列を作らず、積和と各区間の一次・二次の和から算出する。
    n = min(len(reference), len(shifted))
    rows = []
    for lag in range(-radius, radius + 1):
        pairs = [(float(reference[i]), float(shifted[i+lag])) for i in range(n) if 0 <= i+lag < n]
        count = len(pairs)
        r = None
        if count >= 2:
            a, b = zip(*pairs)
            u, v = math.fsum(a), math.fsum(b)
            xx = count * math.fsum(x*x for x in a) - u*u
            yy = count * math.fsum(y*y for y in b) - v*v
            if min(a) != max(a) and min(b) != max(b):
                r = (count * math.fsum(x*y for x, y in pairs) - u*v) / math.sqrt(xx*yy)
        rows.append((lag, count, r))
    return rows


def best(rows, frame_seconds):
    finite = (row for row in rows if row[2] is not None)
    lag, count, r = max(finite, key=lambda row: row[2], default=(None, 0, None))
    seconds = None if lag is None else lag * frame_seconds
    return {'lag_frames': lag, 'lag_seconds': seconds, 'overlapping_frames': count, 'correlation': r}


def error(value, reference):
    if value is None or reference is None:
        return 0.0 if value is reference else None
    return abs(value - reference)


def within(value, tolerance):
    return value is not None and value <= tolerance


def controls(case, rates):
    settings = case['envelope']
    config = case['controls']
    rng = random.Random(24)
    levels = [rng.uniform(.03, .29) for _ in range(120)]
    step = settings['frame_seconds']
    radius = settings['max_lag_frames']
    results = {}
    for rate in rates:
        width = math.floor(step * rate + .5)
        pcm = np.repeat(levels, width)
        db = envelope(pcm, rate, settings)['db']
        shifted = {}
        for name in ('negative_shift_frames', 'positive_shift_frames'):
            target = config[name]
            offset = abs(target) * width
            padding = np.zeros(offset)
            track = np.concatenate((padding, pcm[:-offset]) if target > 0 else (pcm[offset:], padding))
            shifted[name] = best(correlations(db, envelope(track, rate, settings)['db'], radius), step)
        louder = envelope(pcm * config['gain_factor'], rate, settings)['db']
        gain = best(correlations(db, louder, radius), step)
        tail = config['tail_samples']
        short_pcm = np.r_[np.zeros(width), np.full(tail, .125)]
        short = envelope(short_pcm, rate, settings)
        silence = np.full(len(db), settings['floor_db'], dtype=float)
        missing = best(correlations(silence, silence, radius), step)
        tol = settings['independent_correlation_tolerance']
        results[str(rate)] = {
            'checks': {
                'known_shifts': all(row['lag_frames'] == config[name] and within(error(row['correlation'], 1), tol)
                                    for name, row in shifted.items()),
                'constant_gain': gain['lag_frames'] == 0 and within(error(gain['correlation'], 1), tol),
                'silence_floor_and_partial_frame': (short['sizes'].tolist() == [width, tail]
                    and short['db'][0] == settings['floor_db']
                    and within(error(float(short['db'][1]), 20 * math.log10(.125)),
                               settings['independent_db_tolerance'])),
                'silence_has_no_lag': missing['lag_frames'] is None and missing['correlation'] is None,
            },
            'known_shifts': shifted, 'constant_gain': gain, 'silence': missing,
            'short_case_db': short['db'].tolist(), 'short_case_samples': short['sizes'].tolist(),
        }
    return results


def first_difference(tracks, left, right, field, tolerance, step):
    ix = np.flatnonzero(np.abs(tracks[left][field] - tracks[right][field]) > tolerance)
    if not len(ix):
        return None
    i = int(ix[0])
    return {'window': i, 'seconds': i*step,
            'signals': {label: {key: tracks[label][key][i].item() for key in ENVELOPE_FIELDS}
                        for label in (left, right)}}


def song_envelope(song, official, signals, settings, out):
    tracks = {label: envelope(pcm, rate, settings) for label, (pcm, rate) in signals.items()}
    size = song['envelope_frames']
    if not all(len(track['db']) == size for track in tracks.values()):
        raise ValueError(f"{song['id']} の包絡の窓数が登録と一致しません")
    robust = {label: direct_envelope(pcm, rate, settings) for label, (pcm, rate) in signals.items()}
    db_error = {label: float(np.max(np.abs(tracks[label]['db'] - robust[label]))) for label in LABELS}
    step, radius = settings['frame_seconds'], settings['max_lag_frames']
    peaks = {}
    with (out / f"{song['id']}-envelope.csv").open('w', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(('signal', 'window', 'start_seconds', 'start_sample', 'samples', 'mean_square',
                         'unfloored_db', 'level_db'))
        for label, track in tracks.items():
            for i, row in enumerate(zip(*(track[k] for k in ENVELOPE_FIELDS), strict=True)):
                writer.writerow((label, i, i*step, *row))
    with (out / f"{song['id']}-correlations.csv").open('w', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(('reference', 'shifted', 'lag_frames', 'lag_seconds', 'overlap', 'correlation',
                         'independent_correlation'))
        for a, b in PAIRS:
            rows = correlations(tracks[a]['db'], tracks[b]['db'], radius)
            direct = direct_correlations(robust[a], robust[b], radius)
            differences = [error(x[2], y[2]) for x, y in zip(rows, direct, strict=True)]
            agree = all(x[:2] == y[:2] for x, y in zip(rows, direct, strict=True)) and all(
                within(d, settings['independent_correlation_tolerance']) for d in differences)
            for (lag, k, r), (_, _, independent_r) in zip(rows, direct, strict=True):
                writer.writerow((a, b, lag, lag*step, k, r, independent_r))
            peaks[f'{a}_vs_{b}'] = {
                **best(rows, step), 'independent_best': best(direct, step),
                'same_lag_grid_and_correlations': agree,
                'max_independent_correlation_error': None if None in differences else max(differences),
                'first_unfloored_difference': first_difference(tracks, a, b, 'unfloored',
                                                               settings['first_difference_db'], step),
                'first_floored_difference': first_difference(tracks, a, b, 'db', settings['first_difference_db'], step),
            }
    reference = peaks['recording_vs_upstream']
    published = official['summary']
    lag_error = error(reference['lag_seconds'], published['envelopeLagSec'])
    corr_error = error(reference['correlation'], published['envelopeCorr'])
    pair_r = [x['correlation'] for x in peaks.values()]
    return {
        'checks': {
            'independent_envelope': all(within(e, settings['independent_db_tolerance']) for e in db_error.values()),
            'independent_correlations': all(x['same_lag_grid_and_correlations']
                and x['lag_frames'] == x['independent_best']['lag_frames'] for x in peaks.values()),
            'published_envelope': within(lag_error, settings['published_lag_tolerance_seconds'])
                and within(corr_error, settings['published_correlation_tolerance']),
        },
        'frames': size, 'samples_in_final_window': {k: int(v['sizes'][-1]) for k, v in tracks.items()},
        'floor_windows': {k: int(np.count_nonzero(v['unfloored'] < settings['floor_db'])) for k, v in tracks.items()},
        'maximum_independent_db_errors': db_error, 'pairs': peaks,
        'published': {'lag_seconds': published['envelopeLagSec'], 'correlation': published['envelopeCorr'],
                      'lag_error_seconds': lag_error, 'correlation_error': corr_error},
        'synth_pair_has_strongest_correlation': None not in pair_r and pair_r[2] > max(pair_r[:2]),
    }


def onset_scan(analysis, target, first, last, hop):
    t = first
    reject = Counter()
    while t < last:
        status, hz, power, aper = analysis.at(t, target)
        if hz is not None:
            return {'seconds': t, 'f0_hz': hz, 'mean_square': power, 'aperiodicity': aper,
                    'earlier_frames_by_status': dict(reject), 'missing_reason': None}
        reject[status] += 1
        t += hop
    return {'seconds': None, 'earlier_frames_by_status': dict(reject),
            'missing_reason': 'no_voiced_frame' if reject else 'empty_search'}


def onset_group(token):
    if token in VOWELS:
        return 'vowel'
    return 'voiceless' if token in VOICELESS else 'voiced'


def onset_differences(rows, analyses, annotations):
    pairs = {}
    for a, b in PAIRS:
        values = []
        for row in rows:
            left = row['signals'][a]['seconds']
            right = row['signals'][b]['seconds']
            if left is not None and right is not None:
                values.append((row, left, right))
        different = [(row, left, right) for row, left, right in values if left != right]
        first = None
        if different:
            row, left, right = different[0]
            index, t = row['note_index'], min(left, right)
            target = midi_to_hz(annotations[index]['midi'])
            states = {}
            for label in (a, b):
                analysis = analyses[label]
                status, hz, power, aper = analysis.at(t, target)
                states[label] = {'status': status, 'f0_hz': hz, 'mean_square': power, 'aperiodicity': aper,
                                 'gate_mean_square': analysis.gate, 'window_samples': analysis.width}
            first = {'note_index': index, 'ipa': row['ipa'], 'seconds': t, 'channels': states}
        maximum = max(values, key=lambda item: abs(item[2] - item[1]), default=None)
        pairs[f'{a}_vs_{b}'] = {
            'jointly_measured_phrases': len(values), 'different_phrases': len(different),
            'median_absolute_seconds': statistics.median(abs(t2 - t1) for _, t1, t2 in values) if values else None,
            'maximum': None if maximum is None else {'note_index': maximum[0]['note_index'],
                                                     'offset_seconds': maximum[2] - maximum[1]},
            'first_different_frame': first,
        }
    return pairs


def song_onsets(song, report, signals, settings, pitch_config, out):
    low = min(note['midi'] for note in report['notes'])
    analyses = {label: NotePitch(pcm, rate, low, pitch_config) for label, (pcm, rate) in signals.items()}
    rows = []
    note_errors = {label: [] for label in LABELS[:2]}
    boundaries_agree = True
    previous_end = -math.inf
    for i, note in enumerate(report['notes']):
        start, end = note['start'], note['end']
        phrase_start = start - previous_end > settings['phrase_gap_seconds']
        boundaries_agree &= phrase_start == note['phraseStart']
        if phrase_start:
            first = max(start - settings['lookback_seconds'], previous_end + settings['previous_note_margin_seconds'])
            last = start + min(settings['max_lookahead_seconds'], settings['note_lookahead_fraction'] * (end - start))
            group = onset_group(note['csd'].split('_', 1)[0])
            target = midi_to_hz(note['midi'])
            row = {'note_index': i, 'ipa': note['ipa'], 'start_kind': group, 'annotated_seconds': start,
                   'aligned': note['aligned'], 'search_seconds': [first, last], 'signals': {}}
            for label, analysis in analyses.items():
                measured = onset_scan(analysis, target, first, last, settings['hop_seconds'])
                offset = None if measured['seconds'] is None else measured['seconds'] - start
                row['signals'][label] = {**measured, 'offset_seconds': offset}
                if label != 'candidate':
                    field = 'human' if label == 'recording' else 'synth'
                    note_errors[label].append(error(offset, note[field]['onset']))
            rows.append(row)
        previous_end = end

    groups = {}
    for group, field in ONSET_KEYS.items():
        selected = [row for row in rows if row['start_kind'] == group and row['aligned']]
        group_result = {}
        for label in LABELS:
            offsets = [row['signals'][label]['offset_seconds'] for row in selected]
            finite = [v for v in offsets if v is not None]
            median = statistics.median(finite) if finite else None
            group_result[label] = {'available': len(finite), 'missing': len(offsets) - len(finite),
                                   'median_offset_seconds': median}
            if label != 'candidate':
                official = report['summary'][field]['human' if label == 'recording' else 'synth']
                group_result[label].update(published=official, error_seconds=error(median, official))
        groups[group] = group_result
    with (out / f"{song['id']}-phrase-onsets.csv").open('w', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(('note_index', 'ipa', 'start_kind', 'signal', 'annotated_seconds', 'first_seconds',
                         'stop_seconds', 'first_voiced_seconds', 'offset_seconds', 'missing_reason'))
        for row in rows:
            for label, v in row['signals'].items():
                writer.writerow((row['note_index'], row['ipa'], row['start_kind'], label, row['annotated_seconds'],
                                 *row['search_seconds'], v['seconds'], v['offset_seconds'], v['missing_reason']))
    return {
        'checks': {
            'registered_phrase_boundaries': boundaries_agree and len(rows) == song['phrases'],
            'published_note_onsets': all(within(d, settings['published_note_tolerance_seconds'])
                for deltas in note_errors.values() for d in deltas),
            'published_group_onsets': all(within(v[k]['error_seconds'], settings['published_group_tolerance_seconds'])
                for v in groups.values() for k in LABELS[:2]),
        },
        'groups': groups, 'phrases': rows, 'pairs': onset_differences(rows, analyses, report['notes']),
        'maximum_published_note_errors_seconds': {k: None if None in v else max(v) for k, v in note_errors.items()},
    }


def crosscheck_score(song, envelope_result, onset_result, published, config):
    r = envelope_result['pairs']['recording_vs_upstream']['correlation']
    guard = published['guards']['envelopeCorr']
    check = {'score_guard': published['songs'] == [song] and within(
        error(r, guard), config['guard_correlation_tolerance'])}
    result = {'guard_correlation': guard, 'guard_correlation_error': error(r, guard)}
    if song in published.get('notes', {}):
        raw = published['notes'][song]
        corr_error = error(r, raw['envCorr'])
        onset_errors = {}
        for label, field in (('recording', 'singer'), ('upstream', 'synth')):
            values = [error(row['signals'][label]['offset_seconds'],
                            raw[field][row['note_index']][SCORE_ONSET_COLUMN])
                      for row in onset_result['phrases']]
            onset_errors[label] = None if None in values else max(values)
        check.update(score_raw_correlation=within(corr_error, config['raw_correlation_tolerance']),
                     score_raw_onsets=all(within(d, config['raw_onset_tolerance_seconds'])
                                          for d in onset_errors.values()))
        result.update(raw_correlation=raw['envCorr'], raw_correlation_error=corr_error,
                      maximum_raw_onset_error_seconds=onset_errors)
    else:
        result['raw_values_available'] = False
    return {'checks': check, **result}


def verified_file(run, manifest, relative):
    path = run / relative
    matches = [row for row in manifest['outputs'] if row['path'] == relative]
    if len(matches) != 1 or path.stat().st_size != matches[0]['bytes'] or sha256(path) != matches[0]['sha256']:
        raise ValueError(f'先行実行と同じ成果物を確認できません ({path})')
    return path


def load_inputs(case, source, source_manifest, song, inputs):
    run = WORKSPACE / 'runs' / song['wave_run']
    manifest_path, wave_case_path = run / 'manifest.json', CASE.parent / song['wave_case']
    manifest, wave_case = read(manifest_path), read(wave_case_path)
    if (manifest['status'] != 'pass' or manifest['upstream_revision'] != case['upstream_revision']
            or manifest['case_id'] != wave_case['id'] or (wave_case['song'], wave_case['split']) != (song['id'], song['split'])):
        raise ValueError(f"検証済みの先行実行と曲の登録が一致しません ({song['id']})")
    recording = manifest['recording']
    record_path = Path(recording['path'])
    name = f"CSD/english/wav/{song['id']}.wav"
    if sha256(record_path) != recording['sha256'] or recording['sha256'] != source_manifest['dataset']['files'][name]['sha256']:
        raise ValueError(f'先行実行と同じ録音を確認できません ({name})')
    upstream = verified_file(source, source_manifest, f"artifacts/csd/{song['id']}-synth.wav")
    candidate = verified_file(run, manifest, 'artifacts/candidate.wav')
    inputs.extend((manifest_path, wave_case_path, upstream, candidate))
    return recording, (record_path, upstream, candidate), wave_case


def waveforms(paths, config):
    with wave.open(str(paths[0]), 'rb') as audio:
        rate, frames = audio.getframerate(), audio.getnframes()
        if (audio.getnchannels(), audio.getsampwidth(), rate, frames) != (
                2, 2, config['recording_rate_hz'], config['recording_frames']):
            raise ValueError('録音のチャンネル、サンプル形式、レートまたは長さが登録と一致しません')
        stereo = np.frombuffer(audio.readframes(frames), dtype='<i2').reshape(-1, 2)
    if stereo.shape[0] != frames:
        raise ValueError('録音のPCMデータがヘッダに記録された長さを満たしていません')
    mono = stereo.astype(float).mean(axis=1) / 32768
    fs, count = config['sample_rate_hz'], config['output_frames']
    upper, candidate = (samples(path, fs, count) for path in paths[1:])
    return {'recording': (mono, rate), 'upstream': (upper, fs), 'candidate': (candidate, fs)}


def measurement(case, sources, reports, scores, out, execute):
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera-cli', 'compare::'],
            cwd=UPSTREAM, stdout=out / 'fixed-compare-tests.log')
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera', '--test', 'golden_analysis'],
            cwd=UPSTREAM, stdout=out / 'fixed-analysis-tests.log')
    control = controls(case, (44100, 48000))
    results = {}
    for song, (_, paths, config) in zip(case['songs'], sources, strict=True):
        key = song['id']
        signals = waveforms(paths, config['render'])
        report = reports[key]
        envelope_result = song_envelope(song, report, signals, case['envelope'], out)
        onset_result = song_onsets(song, report, signals, case['onset'], config['measurement'], out)
        split = song['split']
        score = crosscheck_score(key, envelope_result, onset_result, scores[split], case['score_crosscheck'])
        results[key] = {'split': split, 'envelope': envelope_result, 'onset': onset_result, 'score': score}
    checks = {'controls': all(all(r['checks'].values()) for r in control.values())}
    for key, data in results.items():
        for section in ('envelope', 'onset', 'score'):
            checks.update({f'{key}_{field}': state for field, state in data[section]['checks'].items()})
    return {'checks': checks, 'controls': control, 'songs': results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
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
    reports = {song['summary']['id']: song for song in read(report)['songs']}
    score = verified_file(source, source_manifest, 'artifacts/csd/score.json')
    score_data = read(score)
    scores = {'calibration': score_data['train'], 'held_out': score_data['heldout']}
    tool_dir = WORKSPACE / 'tools'
    inputs = [CASE, source_path, report, score, Path(__file__).resolve(),
              *(tool_dir / name for name in ('measure_csd_song_f0.py', 'measure_csd_continuous_song.py',
                                             'measure_vowel_voice.py', 'measure_speech_timing.py',
                                             'measure_uniform_tube.py', 'upstream_baseline.py'))]
    sources = [load_inputs(case, source, source_manifest, song, inputs) for song in case['songs']]
    a, b = (source[2]['measurement'] | {'minimum_candidate_notes_with_f0': 0} for source in sources)
    if a != b:
        parser.error('2曲のF0計測条件が一致しません')
    details = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision,
               'driver': [sys.executable, str(Path(__file__).resolve()), args.run_id],
               'previous_run_id': case['score_crosscheck']['previous_run'],
               'recordings': {s['id']: item[0] for s, item in zip(case['songs'], sources, strict=True)}}
    return record_measurement(args.run_id, CASE, inputs, details,
        lambda out, execute: measurement(case, sources, reports, scores, out, execute),
        command=None, input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
