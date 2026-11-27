"""CSDの録音注釈から通常の歌唱計画を作り、固定上流と照合する。"""

import argparse
import csv
from decimal import Decimal
import gzip
import math
import os
from pathlib import Path
import shutil
import subprocess
import wave

import numpy as np
from scipy.io import wavfile

from measure_song_plan import DICT, PROBE, segments
import measure_speech_timing as timing
import measure_uniform_tube as shared
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/csd-song-planning.json'
VOWELS = dict(zip('a ae ai ao au e ei eo er i ii oi oo ou u uu'.split(),
                  'ɑ æ aɪ ʌ aʊ ɛ eɪ ə ɝ ɪ i ɔɪ ɔ oʊ ʊ u'.split(), strict=True))
CONSONANTS = {ipa: ipa for ipa in 'b d f g h k l m n p s t v w z'.split()}
CONSONANTS.update(ch='tʃ', dh='ð', j='dʒ', ng='ŋ', r='ɹ', sh='ʃ', th='θ', y='j', zh='ʒ')
DIPHTHONGS = {'aɪ', 'aʊ', 'eɪ', 'ɔɪ', 'oʊ'}


def segment(ipa):
    return {'ipa': ipa}


def syllable(code):
    onset, coda = [], []
    nucleus = None
    for token in filter(None, code.split('_')):
        ipa = VOWELS.get(token, CONSONANTS.get(token))
        if ipa is None:
            raise ValueError(f'CSDに未対応の音素記号があります ({token}, {code})')
        if nucleus is not None:
            coda.append(segment(ipa))
        elif token in VOWELS:
            nucleus = segment(ipa)
        else:
            onset.append(segment(ipa))
    return {'text': code, 'onset': onset, 'nucleus': nucleus or segment('ə'), 'coda': coda, 'wordEnd': True}


def parse_notes(path, score):
    with path.open(newline='') as stream:
        reader = csv.reader(stream)
        next(reader)
        rows = [(Decimal(a.strip()), Decimal(b.strip()), Decimal(p.strip()), label.strip())
                for a, b, p, label in (row[:4] for row in reader if len(row) >= 4)]
    if not rows or any(not all(x.is_finite() for x in (a, b, p)) or not 0 <= a < b
                      for a, b, p, _ in rows):
        raise ValueError(f'CSDの音符に不正な時刻または音高があります ({path.name})')
    if any(a[0] >= b[0] for a, b in zip(rows, rows[1:])):
        raise ValueError(f'CSDの音符開始が昇順になっていません ({path.name})')
    notes = []
    for i, (start, end, midi, label) in enumerate(rows):
        syl = syllable(label)
        phase_end = i == len(rows) - 1 or float(rows[i + 1][0]) - float(end) > score['phrase_gap_seconds']
        phase_start = not i or notes[-1]['syllable']['phraseEnd']
        prev = notes[-1] if i else None
        if (prev is not None and not phase_start and not syl['onset'] and not syl['coda']
                and syl['nucleus'] == prev['syllable']['nucleus']
                and float(start) - float(prev['end']) < score['melisma_gap_seconds']):
            syl['melisma'] = True
        notes.append({'start': start, 'end': end, 'midi': midi, 'syllable': {**syl, 'phraseEnd': phase_end},
                      'phrase_start': phase_start})
    return notes


def phrase_inputs(uid, notes, score):
    phrases = []
    starts = [i for i, note in enumerate(notes) if note['phrase_start']] + [len(notes)]
    for i, (left, right) in enumerate(zip(starts, starts[1:])):
        rows = notes[left:right]
        nominal_end = [row['start'] for row in rows[1:]] + [rows[-1]['end']]
        beats = [float(end) - float(note['start']) for note, end in zip(rows, nominal_end, strict=True)]
        if not all(x > 0 for x in beats):
            raise ValueError(f'正の拍長でない音符があります ({uid})')
        payload = {'id': f'{uid}-{i+1:02d}', 'start_seconds': float(rows[0]['start']), 'bpm': score['bpm'],
                   'syllables': [row['syllable'] for row in rows],
                   'notes': [{'midi': float(row['midi']), 'beats': beat} for row, beat in zip(rows, beats, strict=True)]}
        phrases.append((payload, rows, nominal_end))
    return phrases


def full_precision_notes(upper, input_rows):
    vowels = iter(row for row in upper['segments'] if row['kind'] == 'vowel')
    extracted = []
    for i, note in enumerate(input_rows):
        carry = i + 1 < len(input_rows) and input_rows[i + 1]['syllable'].get('melisma', False)
        count = 2 if note['syllable']['nucleus']['ipa'] in DIPHTHONGS and not carry else 1
        parts = [next(vowels, None) for _ in range(count)]
        if None in parts:
            raise ValueError('上流計画で母音の区間が不足しています')
        extracted.append([parts[0]['t0'], parts[-1]['t1']])
    if next(vowels, None) is not None:
        raise ValueError('上流計画で母音の区間が余っています')
    return extracted


def report_song(case, phrases, report, candidate, upstream, recording_path, generated_path):
    song_id = report['summary']['id']
    limits, score = case['measurement'], case['score']
    cutoff = limits['alignment_tolerance_seconds']
    tol = limits['upstream_plan_tolerance_seconds']
    all_rows, details = [], []
    for payload, notes, ends in phrases:
        uid = payload['id']
        native = candidate[uid]['plan']
        upper = upstream[uid]
        parts, part_error = timing.compare(segments(native), upper['segments'], tol)
        pitch = [{**g, 'targets': {'f0': g['targets']['f0_hz']}}
                 for phrase in native['phrases'] for g in phrase['pitch']]
        pitch_diff, pitch_error = timing.compare(pitch, upper['pitch'], limits['independent_pitch_tolerance_hz'])
        upper_vowels = full_precision_notes(upper, notes)
        details.append({'id': uid, 'first_segment_difference': parts, 'segment_max_difference_seconds': part_error,
                        'first_pitch_gesture_difference': pitch_diff, 'pitch_gesture_max_numeric_difference': pitch_error,
                        'unsupported': native['unavailable_speech_symbols']})
        for row, end, n, uv in zip(notes, ends, native['notes'], upper_vowels, strict=True):
            target = score['a4_hz'] * math.exp2((float(row['midi']) - 69) / 12)
            offset = n['nucleus_start_seconds'] - float(row['start'])
            upper_offset = uv[0] - float(row['start'])
            syl = row['syllable']
            all_rows.append({'id': len(all_rows), 'phrase_id': uid, 'start': float(row['start']), 'end': float(row['end']),
                             'midi': float(row['midi']), 'csd': syl['text'],
                             'ipa': ''.join(part['ipa'] for part in [*syl['onset'], syl['nucleus'], *syl['coda']]),
                             'melisma': syl.get('melisma', False), 'phraseStart': row['phrase_start'],
                             'beat_end_seconds_independent': float(end),
                             'beat_error_seconds': max(abs(n['beat_seconds'] - float(row['start'])),
                                                       abs(n['beat_end_seconds'] - float(end))),
                             'target_hz_independent': target, 'target_hz': n['f0_hz'],
                             'candidate_nucleus_seconds': [n['nucleus_start_seconds'], n['nucleus_end_seconds']],
                             'upstream_nucleus_seconds': uv, 'candidate_offset_ms': 1000 * offset,
                             'candidate_aligned': abs(offset) <= cutoff, 'probe_aligned': abs(upper_offset) <= cutoff})
    keys = ('start', 'end', 'midi', 'csd', 'ipa', 'melisma', 'phraseStart')
    for row, official in zip(all_rows, report['notes'], strict=True):
        row['upstream_report_aligned'] = official['aligned']
        row['upstream_report_rounded_start_seconds'] = official['plannedVowelStart']
        row['singer_cents_vs_score'] = official['human']['cents']
        row['fixed_synth_cents_vs_score'] = official['synth']['cents']
        row['annotation_matches_upstream_report'] = all(row[k] == official[k] for k in keys)
    with wave.open(str(recording_path), 'rb') as recording:
        record_rate = recording.getframerate()
        record_frames = recording.getnframes()
        record_channels = recording.getnchannels()
        record_width = recording.getsampwidth()
    synth_rate, synthetic = wavfile.read(generated_path)
    factor = int(limits['output_rate_hz'])
    rounded, rest = divmod(record_frames * factor, record_rate)
    wanted_samples = rounded + int(rest * 2 >= record_rate)
    first_nucleus_difference = next((row for row in all_rows
        if any(abs(a - b) > tol for a, b in zip(row['candidate_nucleus_seconds'], row['upstream_nucleus_seconds'], strict=True))), None)
    dropped = report['summary']['notesMisaligned']
    checks = {
        'same_annotations_phrase_and_melisma': all(row['annotation_matches_upstream_report'] for row in all_rows),
        'independent_beats': all(row['beat_error_seconds'] <= limits['independent_beat_tolerance_seconds'] for row in all_rows),
        'independent_midi_pitch': all(abs(row['target_hz'] - row['target_hz_independent']) <= limits['independent_pitch_tolerance_hz'] for row in all_rows),
        'same_segments_and_pitch_gestures': all(d['first_segment_difference'] is None and d['first_pitch_gesture_difference'] is None
                                               and not d['unsupported'] for d in details),
        'same_nucleus_times': first_nucleus_difference is None,
        'probe_matches_official_rounded_report': all(row['probe_aligned'] == row['upstream_report_aligned']
            and abs(row['upstream_nucleus_seconds'][0] - row['upstream_report_rounded_start_seconds'])
                <= limits['rounded_reference_tolerance_seconds'] for row in all_rows),
        'same_alignment_mask': all(row['candidate_aligned'] == row['upstream_report_aligned'] for row in all_rows)
                               and sum(not row['candidate_aligned'] for row in all_rows) == dropped,
        'reference_wave_and_duration': record_rate == case['dataset']['recording_rate_hz'] and synth_rate == factor
                                       and synthetic.shape == (wanted_samples,) and synthetic.dtype == np.float32
                                       and bool(np.isfinite(synthetic).all()),
    }
    return {'checks': checks, 'notes': all_rows, 'phrases': details, 'first_nucleus_difference': first_nucleus_difference,
            'recording_frames': record_frames, 'synth_frames': len(synthetic), 'singer_rate_hz': record_rate,
            'recording_channels': record_channels, 'recording_bits_per_sample': record_width * 8,
            'candidate_misaligned': sum(not row['candidate_aligned'] for row in all_rows), 'upstream_summary': report['summary'],
            'melismas': sum(row['melisma'] for row in all_rows),
            'maximum_nucleus_start_difference_ms': max(1000 * abs(row['candidate_nucleus_seconds'][0] - row['upstream_nucleus_seconds'][0])
                                                       for row in all_rows)}


def measurement(case, data, out, execute):
    for name in ('zenodo-4916302.json', 'selected-inputs.json'):
        shutil.copyfile(data.parent / name, out / name)
    choices = case['songs']
    songs = {}
    for row in choices:
        uid = row['id']
        notes = parse_notes(data / 'english/csv' / f'{uid}.csv', case['score'])
        songs[uid] = phrase_inputs(uid, notes, case['score'])
    input_path = out / 'song-inputs.json'
    timing.write(input_path, {'song_plan': {'scores': [p for groups in songs.values() for p, _, _ in groups],
                                          'lyric_cases': [], 'spelling_cases': [], 'syllable_words': []}})
    cli = ['cargo', 'run', '--locked', '--offline', '--release', '-p', 'vocal-cli', '--']
    inspect = out / 'candidate-inspect.json'
    render = out / 'candidate-render.json'
    execute([*cli, 'inspect', str(input_path)], stdout=inspect)
    execute([*cli, 'render', str(input_path), str(render)])

    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera', '--test', 'sing_fast', '--test', 'rising'],
            cwd=UPSTREAM, stdout=out / 'fixed-singing-tests.log')
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera-cli', 'compare::'], cwd=UPSTREAM,
            stdout=out / 'fixed-comparison-tests.log')
    ref = out / 'csd'
    execute(['cargo', 'run', '--locked', '--offline', '--release', '-p', 'chimera-cli', '--',
             'compare', 'csd', str(data), str(ref), '--songs', ','.join(songs),
             '--body', case['score']['body'], '--jobs', '1', '--float'], cwd=UPSTREAM, stdout=out / 'upstream-csd.log')
    official = timing.read(ref / 'report.json')
    got = {x['summary']['id']: x for x in official['songs']}
    if set(got) != songs.keys() or official['errors']:
        raise ValueError(f"CSDの通常比較で曲の欠測がありました ({official['errors']})")

    expanded = out.parent / 'tmp' / 'cmudict.tsv'
    expanded.write_bytes(gzip.decompress(DICT.read_bytes()))
    probe = shared.build_upstream_probe(PROBE, out, execute, extra_libraries=('serde_json',))
    reference = out / 'upstream-full-precision.json'
    execute([str(probe), str(input_path), str(expanded), case['score']['body']], stdout=reference)
    native, upper = ({x['id']: x for x in timing.read(p)['scores']} for p in (render, reference))
    reports = {}
    for row in choices:
        uid = row['id']
        result = report_song(case, songs[uid], got[uid], native, upper,
                             data / 'english/wav' / f'{uid}.wav', ref / f'{uid}-synth.wav')
        reports[uid] = {'split': row['split'], **result}
    checks = {'same_candidate_inspect_and_render': sha256(inspect) == sha256(render)}
    checks.update({f'{uid}/{name}': ok for uid, row in reports.items() for name, ok in row['checks'].items()})
    return {'checks': checks, 'songs': reports}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    if os.environ.get('CHIMERA_RUN_STORAGE') != 'rtl9210b':
        parser.error('CSD資料と計測の保存先は作業用ディスクを指定してください')
    case = timing.read(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('差分のない固定上流版を用意してください')
    root = Path(case['dataset']['work_root'])
    metadata = root / 'selected-inputs.json'
    source = timing.read(metadata)
    official = root / 'zenodo-4916302.json'
    if sha256(official) != source['metadata_sha256'] or source['record_doi'] != case['dataset']['doi']:
        parser.error('CSDの配布情報が登録版と一致しません')
    if {song['split'] for song in case['songs']} != {'held_out', 'calibration'}:
        parser.error('調整用と確認用を別の曲で登録してください')
    inputs = [CASE, Path(__file__).resolve(), PROBE, DICT, Path(shared.__file__), Path(timing.__file__).resolve(),
              WORKSPACE / 'tools/measure_song_plan.py', WORKSPACE / 'tools/fetch_csd_inputs.py',
              UPSTREAM / 'crates/chimera-cli/src/compare.rs', UPSTREAM / 'crates/chimera-cli/src/compare/score.rs',
              *shared.candidate_sources()]
    for song in case['songs']:
        uid = song['id']
        if (int(uid[2:-1]) % 5 == 0) != (song['split'] == 'held_out'):
            parser.error('上流の曲の分割と登録先が一致しません')
        for kind in ('csv', 'wav'):
            name = f'CSD/english/{kind}/{uid}.{kind}'
            path, saved = root / name, source['files'][name]
            if path.stat().st_size != saved['bytes'] or sha256(path) != saved['sha256']:
                parser.error('録音または注釈が照合した版と一致しません')
    return shared.record_measurement(args.run_id, CASE, inputs,
        {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision, 'dataset': source},
        lambda out, execute: measurement(case, root / 'CSD', out, execute),
        command=None, input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
