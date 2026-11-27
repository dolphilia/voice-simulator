"""保存済みTSP比較を畳み込みで再測定し、従来の結果との一致を確認する。"""

import argparse
import io
import json
from pathlib import Path
import warnings
from zipfile import ZipFile

import numpy as np
from scipy.io import wavfile
from scipy.signal import convolve

from upstream_baseline import WORKSPACE, sha256


def load(path):
    return json.loads(path.read_text())


def interval(power, threshold, hop, width):
    hit = power >= power.max() * 10 ** (threshold / 10)
    changes = np.flatnonzero(np.diff(np.r_[False, hit, False]))
    starts, ends = changes[::2], changes[1::2]
    long_enough = (ends - starts) >= 3
    if not long_enough.any():
        raise ValueError('しきい値以上の窓が連続する区間がありません')
    return [int(starts[long_enough][0]) * hop, (int(ends[long_enough][-1]) - 1) * hop + width]


def independently_measure(directory, signals, row, rate, width, hop, thresholds):
    ranges = {}
    for kind, source in signals.items():
        if kind == 'recording':
            # TSPの録音用メタデータチャンクはPCMの解析対象に含めない。
            with warnings.catch_warnings():
                warnings.simplefilter('ignore', wavfile.WavFileWarning)
                actual_rate, raw = wavfile.read(io.BytesIO(source))
            if raw.dtype != np.int16:
                raise ValueError('録音のPCM16形式を確認できません')
            samples = raw.astype(float) / 32768
        else:
            actual_rate, raw = wavfile.read(directory / source)
            if raw.dtype != np.float32:
                raise ValueError('合成のfloat32形式を確認できません')
            samples = raw.astype(float)
        registered = row['windows'][kind]
        if (actual_rate != rate or samples.ndim != 1 or samples.size != registered['pcm_frames']
                or not np.isfinite(samples).all()):
            raise ValueError('PCMのレート、フレーム数または有限性が一致しません')
        # 互いに重なる窓の二乗和は、矩形カーネルとの畳み込みでも求められる。
        power = convolve(samples ** 2, np.ones(width), mode='valid', method='direct')[::hop] / width
        for threshold in thresholds:
            bounds = interval(power, threshold, hop, width)
            expected = registered['thresholds'][str(threshold)]
            ranges[f'{kind}:{threshold}'] = {
                'observed': bounds, 'expected': [expected['start_frame'], expected['end_frame_exclusive']],
            }
    return ranges


def original_registration(reference, groups, intervals, thresholds, rate):
    registered = {split: reference[f'{split}_ids'] for split in groups}
    missing = {split: [recording for recording in ids if recording not in groups[split]]
               for split, ids in registered.items()}
    rows = {split: {} for split in groups}
    for split, ids in registered.items():
        for recording in ids:
            if recording in missing[split]:
                continue
            thresholds_ms = {}
            for db in thresholds:
                durations = {}
                for source in ('recording', 'upstream', 'candidate'):
                    start, end = intervals[recording][f'{source}:{db}']['observed']
                    durations[source] = (end - start) * 1000 / rate
                thresholds_ms[str(db)] = {
                    'duration_ms': durations,
                    'candidate_minus_recording_ms': durations['candidate'] - durations['recording'],
                    'candidate_minus_upstream_ms': durations['candidate'] - durations['upstream'],
                }
            rows[split][recording] = thresholds_ms
    return {'splits': rows, 'missing_or_misclassified_ids': missing}


def evidence(case_path, run, *, require_original_registration=False):
    case = load(case_path)
    base = load(case_path.parent / case['base_case'])
    prior = WORKSPACE / 'runs' / case['comparison_run']
    old = load(prior / 'summary.json')
    current = load(run / 'summary.json')
    manifest = load(run / 'manifest.json')
    prior_manifest = load(prior / 'manifest.json')
    prior_hashes = {entry['path']: entry['sha256'] for entry in prior_manifest['outputs']}
    rate = base['synthesis']['sample_rate_hz']
    metric = base['measurement']
    width = round(rate * metric['window_ms'] / 1000)
    hop = round(rate * metric['hop_ms'] / 1000)
    thresholds = [metric['threshold_db_relative_to_maximum_window_rms'], metric['sensitivity_threshold_db']]
    reference = base['reference']
    archive_path = Path(reference['archive_path'])
    if sha256(archive_path) != reference['sha256']:
        raise ValueError('録音アーカイブのSHA-256が一致しません')
    groups = {name: case[f'{name}_ids'] for name in ('calibration', 'held_out')}
    checks = {
        'exact_partition': list(current['splits']) == list(groups)
        and all(list(current['splits'][name]) == ids for name, ids in groups.items()),
        'speakers_are_disjoint': not ({id[:2] for id in groups['calibration']}
                                      & {id[:2] for id in groups['held_out']}),
        'measurement_passed': manifest['status'] == 'pass',
    }
    intervals = {}
    old_rows = {}
    with ZipFile(archive_path) as archive:
        for split, ids in groups.items():
            for record_id in ids:
                row = current['splits'][split][record_id]
                folder = run / 'artifacts' / record_id
                signals = {'recording': archive.read(row['recording_archive_member']), 'upstream': 'upstream.wav',
                           'candidate': 'candidate.wav'}
                intervals[record_id] = independently_measure(folder, signals, row, rate, width, hop, thresholds)
            for record_id, prior_row in old['splits'][split].items():
                current_row = current['splits'][split][record_id]
                numeric = {key: value for key, value in prior_row.items() if key != 'listening_pair'}
                expected_wavs = [f'artifacts/{record_id}/{name}.wav' for name in ('upstream', 'candidate')]
                old_rows[record_id] = {
                    'same_measurement': all(current_row[key] == value for key, value in numeric.items()),
                    'same_wave_hashes': all(sha256(run / path) == sha256(prior / path) == prior_hashes[path]
                                            for path in expected_wavs),
                }
    mismatches = {rid: [key for key, bounds in ranges.items() if bounds['observed'] != bounds['expected']]
                  for rid, ranges in intervals.items()}
    checks.update(independent_boundaries=not any(mismatches.values()),
                  saved_measurements_and_waves=all(all(row.values()) for row in old_rows.values()))
    result = {'checks': checks, 'independent_boundaries': sum(map(len, intervals.values())),
              'first_mismatched_keys_per_recording': {rid: keys for rid, keys in mismatches.items() if keys},
              'prior': old_rows, 'intervals': intervals}
    if require_original_registration:
        original = original_registration(reference, groups, intervals, thresholds, rate)
        checks['original_registration_complete'] = not any(original['missing_or_misclassified_ids'].values())
        primary = str(thresholds[0])
        checks['original_independent_primary_tolerance'] = checks['original_registration_complete'] and all(
            abs(row[primary]['candidate_minus_upstream_ms']) <= metric['synthetic_pair_duration_tolerance_ms']
            for split in original['splits'].values() for row in split.values())
        result['original_registration'] = original
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('case', type=Path)
    parser.add_argument('run', type=Path)
    parser.add_argument('--require-original-registration', action='store_true',
                        help='元の調整用と確認用の全件を確認し、独立した集計を出す')
    args = parser.parse_args()
    result = evidence(args.case, args.run, require_original_registration=args.require_original_registration)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return int(not all(result['checks'].values()))


if __name__ == '__main__':
    raise SystemExit(main())
