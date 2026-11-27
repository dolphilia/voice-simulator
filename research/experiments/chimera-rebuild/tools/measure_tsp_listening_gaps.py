"""TSP試聴対の低エネルギー時間を保存したMFAの語・音素へ対応付ける。"""

import argparse
from bisect import bisect_right
from collections import Counter
from pathlib import Path
import sys

import numpy as np

from measure_csd_envelope_timing import verified_file
from measure_speech_timing import read, write
from measure_tsp_listening import IDENTIFIER, ROOT, hydrate_run, snapshot_case
from measure_uniform_tube import record_measurement
from upstream_baseline import WORKSPACE, sha256


CASE = WORKSPACE / 'cases/tsp-phone-boundaries-listening-07.json'
SOURCES = ('recording', 'upstream', 'candidate')
CATEGORIES = ('word_phone', 'word_without_phone', 'between_words', 'outside_word_sequence')


def frame_tiers(tiers, rate):
    result = {}
    for kind, entries in tiers.items():
        rows = [(round(start * rate), round(stop * rate), label) for start, stop, label in entries]
        if not rows or any(a < 0 or b <= a for a, b, _ in rows) or any(
                a[1] > b[0] for a, b in zip(rows, rows[1:])):
            raise ValueError(f'{kind} のフレーム区間が順序または範囲を満たしません')
        result[kind] = rows
    return result


def distribute(quiet, tiers):
    words, phones = (tiers[name] for name in ('words', 'phones'))
    word_starts, phone_starts = ([row[0] for row in rows] for rows in (words, phones))
    boundaries = sorted({endpoint for rows in (words, phones) for a, b, _ in rows for endpoint in (a, b)})
    pieces = []
    for first, stop in quiet:
        cuts = [first, *(p for p in boundaries if first < p < stop), stop]
        for a, b in zip(cuts, cuts[1:]):
            word_index = bisect_right(word_starts, a) - 1
            phone_index = bisect_right(phone_starts, a) - 1
            in_word = word_index >= 0 and a < words[word_index][1]
            in_phone = phone_index >= 0 and a < phones[phone_index][1]
            gap = None
            if in_word:
                category = 'word_phone' if in_phone else 'word_without_phone'
            elif 0 <= word_index < len(words) - 1:
                category = 'between_words'
                gap = [words[word_index][2], words[word_index + 1][2]]
            else:
                category = 'outside_word_sequence'
            pieces.append({'frames': [a, b], 'category': category,
                           'word': words[word_index][2] if in_word else None,
                           'phone': phones[phone_index][2] if in_phone else None, 'gap': gap})
    return pieces


def direct_counts(quiet, tiers, frame_count):
    # 各標本のマスクを先に付け、境界の分割を使わずに合計する。
    flags = {}
    for name in ('words', 'phones'):
        flags[name] = np.zeros(frame_count, dtype=bool)
        for start, stop, _ in tiers[name]:
            flags[name][start:stop] = True
    word_sequence = np.zeros(frame_count, dtype=bool)
    word_sequence[tiers['words'][0][0]:tiers['words'][-1][1]] = True
    low = np.zeros(frame_count, dtype=bool)
    for start, stop in quiet:
        low[start:stop] = True
    word, phone = flags['words'], flags['phones']
    return {'word_phone': int(np.count_nonzero(low & word & phone)),
            'word_without_phone': int(np.count_nonzero(low & word & ~phone)),
            'between_words': int(np.count_nonzero(low & word_sequence & ~word)),
            'outside_word_sequence': int(np.count_nonzero(low & ~word_sequence))}


def analyze(case, source, aligned, pair, out):
    config = case['attribution']
    uid, = case['transcripts'][0]['recording_ids']
    if pair['recording_id'] != uid or pair['split'] != case['split']:
        raise ValueError('試聴対と整列した録音の区分・IDが一致しません')
    rate = case['measurement']['sample_rate_hz']
    annotated = {name: frame_tiers(aligned['intervals'][uid if name == 'recording' else f'{uid}-{name}'], rate)
                 for name in SOURCES}
    result = {}
    for threshold in config['thresholds_db']:
        comparison = {}
        for name, series in pair['thresholds'][str(threshold)]['signals'].items():
            tiers = annotated[name]
            count = source['splits'][case['split']][uid]['windows'][name]['pcm_frames']
            quiet = series['quiet_intervals']
            if (any(not 0 <= a < b <= count for a, b in quiet)
                    or any(rows[-1][1] > count for rows in tiers.values())):
                raise ValueError('保存した区間が元のPCM長を越えています')
            pieces = distribute(quiet, tiers)
            labels = Counter(dict.fromkeys(CATEGORIES, 0))
            gap_frames = 0
            for piece in pieces:
                a, b = piece['frames']
                labels[piece['category']] += b - a
                if piece['gap'] == config['predicted_gap']:
                    gap_frames += b - a
            if sum(labels.values()) != series['quiet_frames'] or labels != direct_counts(quiet, tiers, count):
                raise ValueError(f'区間の分割と独立したフレーム計数が一致しません ({name}, {threshold} dB)')
            comparison[name] = {
                'total_frames': series['quiet_frames'], 'frames_by_category': dict(labels),
                'predicted_gap_frames': gap_frames,
                'pieces': pieces,
            }
        result[str(threshold)] = comparison
    write(out / 'attribution.json', {'recording_id': uid, 'sample_rate_hz': rate, 'tiers_frames': annotated,
                                    'thresholds': result})
    primary = result[str(config['thresholds_db'][0])]
    recorded, candidate = (primary[name] for name in ('recording', 'candidate'))
    delta = recorded['total_frames'] - candidate['total_frames']
    gap_delta = recorded['predicted_gap_frames'] - candidate['predicted_gap_frames']
    return {
        'checks': {'source_intervals_and_labels': True, 'every_frame_attributed': True,
                   'direct_pcm_grid_counts_agree': True},
        'sample_rate_hz': rate, 'recording_id': uid, 'primary_recording_minus_candidate_frames': delta,
        'predicted_gap': config['predicted_gap'], 'primary_gap_recording_minus_candidate_frames': gap_delta,
        'predicted_gap_explains_majority': delta > 0 and gap_delta * 2 > delta,
        'counts': {db: {name: row['frames_by_category'] for name, row in rows.items()} for db, rows in result.items()},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('alignment_run')
    args = parser.parse_args()
    if not IDENTIFIER.fullmatch(args.alignment_run):
        parser.error('整列の実行IDが不正です')
    case = read(CASE)
    rev = case['upstream_revision']
    config = case['attribution']
    aligned = hydrate_run(args.alignment_run, case['id'], rev)
    timing = hydrate_run(config['timing_run'], config['timing_case'], rev)
    baseline = hydrate_run(case['baseline_run'], case['baseline_scope'], rev)
    aligned_case = snapshot_case(aligned, case['id'])
    if sha256(aligned_case) != sha256(CASE):
        parser.error('整列時と比較時のケースが一致しません')
    manifest = baseline[0] / 'manifest.json'
    baseline_entry = {'path': manifest.relative_to(ROOT).as_posix(), 'bytes': manifest.stat().st_size,
                      'sha256': sha256(manifest)}
    if any(baseline_entry not in manifest_data['inputs'] for _, manifest_data in (timing, aligned)):
        parser.error('発話区間と語・音素の整列が同じ波形の実行を参照していません')
    summary = verified_file(*aligned, 'summary.json')
    measures = verified_file(*timing, 'artifacts/pair-measurements.json')
    timing_summary = verified_file(*timing, 'summary.json')
    original = verified_file(*baseline, 'summary.json')
    if read(timing_summary)['sample_rate_hz'] != case['measurement']['sample_rate_hz']:
        parser.error('区間長計測と整列のサンプルレートが一致しません')
    inputs = [CASE, Path(__file__).resolve(), WORKSPACE / 'tools/measure_tsp_listening.py',
              WORKSPACE / 'tools/measure_uniform_tube.py', WORKSPACE / 'tools/upstream_baseline.py',
              WORKSPACE / 'tools/measure_csd_envelope_timing.py', WORKSPACE / 'tools/measure_speech_timing.py',
              aligned_case, summary, measures, timing_summary, original, manifest,
              aligned[0] / 'manifest.json', timing[0] / 'manifest.json']
    details = {'case_id': case['id'], 'upstream_revision': rev, 'case_revision': case['revision'],
               'alignment_run': args.alignment_run, 'timing_run': config['timing_run'], 'arguments': sys.argv[1:]}
    return record_measurement(
        args.run_id, CASE, inputs, details,
        lambda out, _: analyze(case, read(original), read(summary), read(measures)[config['pair']], out),
        command=None, input_root=ROOT,
    )


if __name__ == '__main__':
    raise SystemExit(main())
