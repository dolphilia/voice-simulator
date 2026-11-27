"""確認用の全音符にYINの探索上限だけを変更し、通常の推定と照合する。"""

import argparse
from collections import Counter, defaultdict
import csv
import math
import os
from pathlib import Path
import wave

import numpy as np

from measure_csd_continuous_song import samples
from measure_csd_f0_third_harmonic import spectrum_and_lags
from measure_csd_song_f0 import LABELS, NotePitch
from measure_speech_timing import read
from measure_uniform_tube import record_measurement
from upstream_baseline import WORKSPACE, sha256


CASE = WORKSPACE / 'cases/csd-f0-upper-bound-en005a.json'
SYNTHS = ('upstream', 'candidate')


def cents(hz, target):
    return None if hz is None else 1200 * math.log2(hz / target)


def median_voiced(values):
    finite = [x for x in values if x is not None]
    return float(np.median(finite)) if finite else None


def load_centers(path):
    groups = defaultdict(list)
    with path.open(newline='') as stream:
        for row in csv.DictReader(stream):
            key = int(row['note_index']), row['signal']
            hz = float(row['f0_hz']) if row['f0_hz'] else None
            power = float(row['mean_square']) if row['mean_square'] else None
            groups[key].append((float(row['time_seconds']), row['status'], hz, power))
    return groups


def compare_note(case, note, recorded, estimators, output):
    index, target = note['note_index'], note['target_hz']
    groups = {k: recorded[index, k] for k in LABELS}
    times = [t for t, *_ in groups['recording']]
    if len(times) != note['frame_count'] or any(times != [t for t, *_ in rows] for rows in groups.values()):
        raise ValueError(f'3波形の窓の中心が一致しません ({index})')
    ratio = math.exp2(case['search_upper_semitones'] / 12)
    results = {}
    observed = {}
    for label, rows in groups.items():
        before, after = [], []
        counts_before, counts_after = Counter(), Counter()
        checked = True
        values = []
        for t, old_status, old_hz, old_power in rows:
            status, hz, power, aper = estimators[label].at(t, target, upper_ratio=ratio)
            old_cents = cents(old_hz, target)
            new_cents = cents(hz, target)
            before.append(old_cents)
            after.append(new_cents)
            counts_before[old_status] += 1
            counts_after[status] += 1
            checked &= old_power == power and (old_status == 'outside_wave') == (status == 'outside_wave')
            checked &= (old_status == 'below_energy_gate') == (status == 'below_energy_gate')
            values.append((old_hz, hz))
            output.writerow((index, label, t, old_status, status, old_hz, hz, aper))
        observed[label] = values
        results[label] = {
            'wide_median_cents': median_voiced(before), 'narrow_median_cents': median_voiced(after),
            'frames_wide': dict(sorted(counts_before.items())), 'frames_narrow': dict(sorted(counts_after.items())),
            'changed_f0_frames': sum(a != b for a, b in values),
            'new_voiced_frames': sum(a is None and b is not None for a, b in values),
            'registered_gate_and_power': checked,
            'wide_report_reproduced': median_voiced(before) == note['signals'][label]['median_cents_vs_score']
                                      and dict(counts_before) == note['signals'][label]['frames_by_status'],
        }
    cutoff = case['minimum_initial_cents']
    shared = [i for i, pair in enumerate(zip(*(observed[k] for k in SYNTHS), strict=True))
              if all(a is not None and cents(a, target) >= cutoff for a, _ in pair)]
    spectrum = {}
    if shared:
        center = shared[len(shared)//2]
        for label in SYNTHS:
            wide, narrow = observed[label][center]
            spectrum[label] = {'wide_hz': wide, 'narrow_hz': narrow}
            if narrow is not None:
                spectrum[label] = spectrum_and_lags({**case, 'spectrum_center_seconds': times[center]},
                                                    estimators[label], target, ratio)
        supported = all(r.get('third_harmonic_observed') and r.get('longer_lag_has_lower_normalized_difference')
                        and abs(cents(r['narrow_hz'], target)) <= case['maximum_abs_cents_near_score']
                        for r in spectrum.values())
        spectrum = {'center_seconds': times[center], 'agrees_with_third_harmonic_hypothesis': bool(supported),
                    'signals': spectrum}
    return {'note_index': index, 'midi': note['midi'], 'ipa': note['ipa'], 'target_hz': target,
            'common_high_frames': len(shared), 'signals': results, 'representative_frame': spectrum}


def summary(notes, cutoff):
    totals = {}
    for label in LABELS:
        rows = [n['signals'][label] for n in notes]
        totals[label] = {
            'changed_note_medians': [n['note_index'] for n in notes
                                     if n['signals'][label]['wide_median_cents'] != n['signals'][label]['narrow_median_cents']],
            'wide_notes_with_f0': sum(r['wide_median_cents'] is not None for r in rows),
            'narrow_notes_with_f0': sum(r['narrow_median_cents'] is not None for r in rows),
            'wide_voiced_frames': sum(r['frames_wide'].get('voiced', 0) for r in rows),
            'narrow_voiced_frames': sum(r['frames_narrow'].get('voiced', 0) for r in rows),
            'changed_f0_frames': sum(r['changed_f0_frames'] for r in rows),
        }
    return {**totals, 'shared_high_notes_by_median': [n['note_index'] for n in notes if all(
        n['signals'][k]['wide_median_cents'] is not None and n['signals'][k]['wide_median_cents'] >= cutoff for k in SYNTHS)],
        'notes_with_shared_high_frames': [n['note_index'] for n in notes if n['common_high_frames']],
        'shared_high_frames': sum(n['common_high_frames'] for n in notes),
        'representative_frames_supporting_hypothesis': [n['note_index'] for n in notes
            if n['representative_frame'].get('agrees_with_third_harmonic_hypothesis')]}


def measurement(case, normal, baseline, frames, paths, output):
    with wave.open(str(paths['recording']), 'rb') as audio:
        record_rate = audio.getframerate()
        if (audio.getnchannels(), audio.getsampwidth()) != (2, 2):
            raise ValueError('録音の2チャンネル・PCM16条件が一致しません')
        data = np.frombuffer(audio.readframes(audio.getnframes()), dtype='<i2')
    mono = data.reshape(-1, 2).astype(float).mean(axis=1) / 32768
    rate = normal['render']['sample_rate_hz']
    count = normal['render']['output_frames']
    upper, native = (samples(paths[key], rate, count) for key in SYNTHS)
    config = normal['measurement']
    low = min(x['midi'] for x in baseline['notes'])
    tracks = {label: NotePitch(pcm, fs, low, config) for label, pcm, fs in
              zip(LABELS, (mono, upper, native), (record_rate, rate, rate), strict=True)}
    with (output / 'upper-bound-frames.csv').open('w', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(('note_index', 'signal', 'time_seconds', 'wide_status', 'narrow_status', 'wide_hz',
                         'narrow_hz', 'narrow_aperiodicity'))
        notes = [compare_note(case, n, frames, tracks, writer) for n in baseline['notes']]
    rows = [r for n in notes for r in n['signals'].values()]
    return {'checks': {
                'same_measurement_windows_and_all_notes': len(notes) == normal['render']['notes']
                    and len(frames) == len(notes) * len(LABELS),
                'same_gate_and_window_power': all(r['registered_gate_and_power'] for r in rows),
                'same_registered_baseline_values': all(r['wide_report_reproduced'] for r in rows),
                'narrow_search_cannot_restore_missing_frames': all(not r['new_voiced_frames'] for r in rows),
            },
            'song': case['song'], 'split': case['split'], 'statistics': summary(notes, case['minimum_initial_cents']),
            'notes': notes}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    if os.environ.get('CHIMERA_RUN_STORAGE') != 'rtl9210b':
        parser.error('計測は作業用ディスクを指定してください')
    case = read(CASE)
    normal_path = CASE.parent / case['reference_case']
    calibration_path = CASE.parent / case['calibration']
    normal, calibration = read(normal_path), read(calibration_path)
    if normal['song'] != case['song'] or normal['split'] != 'held_out':
        parser.error('確認用として固定した通常条件と一致しません')
    checked_fields = ('minimum_initial_cents', 'search_upper_semitones', 'spectrum_window_seconds',
                      'spectrum_fft_size', 'third_harmonic_tolerance_hz')
    if any(calibration[k] != case[k] for k in checked_fields) or (
            calibration['maximum_median_abs_cents_from_score'] != case['maximum_abs_cents_near_score']):
        parser.error('倍音対照の条件が調整用の登録と一致しません')
    base, source = (WORKSPACE / 'runs' / case[key] for key in ('reference_run', 'source_run'))
    original = base / 'summary.json'
    frames = base / 'artifacts/note-f0-frames.csv'
    base_manifest, source_manifest = (run / 'manifest.json' for run in (base, source))
    base_info = read(base_manifest)
    rec = base_info['recording']
    if base_info['status'] != 'pass' or base_info['case_id'] != normal['id']:
        parser.error('通常条件の計測が合格した実行と一致しません')
    paths = {'recording': Path(rec['path']), 'candidate': base / 'artifacts/candidate.wav',
             'upstream': source / 'artifacts/csd' / f"{case['song']}-synth.wav"}
    if sha256(paths['recording']) != rec['sha256']:
        parser.error('録音が通常条件の入力と一致しません')
    for root, manifest, files in ((base, base_info, (original, frames, paths['candidate'])),
                                   (source, read(source_manifest), (paths['upstream'],))):
        hashes = {r['path']: r['sha256'] for r in manifest['outputs']}
        if any(sha256(path) != hashes.get(path.relative_to(root).as_posix()) for path in files):
            parser.error(f'基準のWAVまたは計測表が一致しません ({root.name})')
    tools = WORKSPACE / 'tools'
    inputs = [CASE, normal_path, calibration_path, Path(__file__).resolve(), base_manifest, source_manifest,
              original, frames, *(paths[k] for k in SYNTHS), tools / 'measure_csd_continuous_song.py',
              tools / 'measure_csd_song_f0.py', tools / 'measure_csd_f0_third_harmonic.py', tools / 'measure_vowel_voice.py']
    return record_measurement(args.run_id, CASE, inputs, {'case_id': case['id'], 'recording': rec},
        lambda out, _execute: measurement(case, normal, read(original), load_centers(frames), paths, out),
        command=None, input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
