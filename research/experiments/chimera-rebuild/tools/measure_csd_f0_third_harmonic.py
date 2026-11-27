"""CSDの一部でYINが選んだ短い遅延を、探索上限だけ変えて調べる。"""

import argparse
import math
import os
from pathlib import Path
import wave

import numpy as np

from measure_csd_continuous_song import samples
from measure_csd_song_f0 import CASE as ORIGINAL, LABELS, NotePitch, measurement_windows
from measure_speech_timing import read
from measure_uniform_tube import record_measurement
from measure_vowel_voice import independent_yin
from upstream_baseline import WORKSPACE, sha256


CASE = WORKSPACE / 'cases/csd-f0-third-harmonic-en001a.json'


def cut(estimator, time):
    i = int(time * estimator.rate) - estimator.width // 2
    return estimator.pcm[i:i+estimator.width]


def narrow(estimator, time, target, upper_ratio):
    _, wide, power, _ = estimator.at(time, target)
    if power is None or power < estimator.gate:
        return wide, None
    hz, _ = independent_yin(cut(estimator, time), estimator.rate, {
        'pitch_min_hz': target / estimator.search_range, 'pitch_max_hz': target * upper_ratio,
        'yin_threshold': estimator.threshold,
    })
    return wide, hz


def normalized_difference(frame, lag, max_lag):
    width = len(frame) - max_lag
    base = frame[:width]
    terms = [float(np.sum((base-frame[k:k+width])**2)) for k in range(1, lag+1)]
    return terms[-1] * lag / sum(terms)


def spectrum_and_lags(case, estimator, target, ratio):
    t = case['spectrum_center_seconds']
    frame = cut(estimator, t)
    wide, narrow_hz = narrow(estimator, t, target, ratio)
    if wide is None or narrow_hz is None:
        raise ValueError('登録した観測時刻の倍音を比較できません')
    rate = estimator.rate
    size = case['spectrum_fft_size']
    width = round(case['spectrum_window_seconds'] * rate)
    left = round(t * rate) - width // 2
    signal = estimator.pcm[left:left+width]
    magnitude = abs(np.fft.rfft(signal * np.hanning(len(signal)), n=size))
    peak_bin = int(np.argmax(magnitude))
    peak = peak_bin * rate / size
    max_lag = min(len(frame)//2, int(rate / (target / estimator.search_range)))
    wide_lag, narrow_lag = (round(rate / hz) for hz in (wide, narrow_hz))
    upper_aper, true_aper = [normalized_difference(frame, lag, max_lag) for lag in (wide_lag, narrow_lag)]
    return {'wide_hz': wide, 'narrow_hz': narrow_hz, 'peak_hz': peak, 'wide_lag_samples': wide_lag,
            'narrow_lag_samples': narrow_lag, 'wide_cmnd': upper_aper, 'narrow_cmnd': true_aper,
            'third_harmonic_observed': abs(peak - 3 * target) <= case['third_harmonic_tolerance_hz'],
            'longer_lag_has_lower_normalized_difference': true_aper < upper_aper < estimator.threshold}


def note_result(baseline, estimators, config, ratio):
    target = baseline['target_hz']
    a, b = baseline['annotation_seconds']
    _, times = measurement_windows({'start': a, 'end': b, 'melisma': False}, config)
    result = {}
    for label, estimator in estimators.items():
        observations = [narrow(estimator, t, target, ratio) for t in times]
        voiced = [[hz for hz in values if hz is not None] for values in zip(*observations, strict=True)]
        cents = [float(np.median([1200 * math.log2(hz / target) for hz in group])) if group else None for group in voiced]
        previous = baseline['signals'][label]
        result[label] = {
            'wide_median_cents': cents[0], 'narrow_median_cents': cents[1],
            'wide_voiced_frames': len(voiced[0]), 'narrow_voiced_frames': len(voiced[1]),
            'baseline_reproduced': (cents[0] == previous['median_cents_vs_score']
                                    and len(voiced[0]) == previous['frames_by_status']['voiced']),
            'centers_with_f0_hz': [[t, a, b] for t, (a, b) in zip(times, observations, strict=True)],
        }
    return result


def measurement(case, config, baseline, candidate, upstream, recording, render):
    with wave.open(str(recording), 'rb') as clip:
        record_rate = clip.getframerate()
        raw = np.frombuffer(clip.readframes(clip.getnframes()), dtype='<i2')
    mono = raw.reshape(-1, 2).astype(float).mean(axis=1) / 32768
    rate, count = render['sample_rate_hz'], render['output_frames']
    upper, native = (samples(path, rate, count) for path in (upstream, candidate))
    minimum = min(note['midi'] for note in baseline['notes'])
    estimators = {k: NotePitch(x, fs, minimum, config) for k, x, fs in
                  zip(LABELS, (mono, upper, native), (record_rate, rate, rate), strict=True)}
    ratio = math.exp2(case['search_upper_semitones']/12)
    cutoff = case['minimum_initial_cents']
    notes = {n['note_index']: n for n in baseline['notes']}
    chosen = [i for i, note in notes.items() if all(note['signals'][k]['median_cents_vs_score'] is not None
            and note['signals'][k]['median_cents_vs_score'] >= cutoff for k in ('upstream', 'candidate'))]
    narrowed = {i: note_result(notes[i], estimators, config, ratio) for i in case['notes']}
    target = notes[case['spectrum_note']]['target_hz']
    spectrum = {k: spectrum_and_lags(case, estimators[k], target, ratio) for k in ('upstream', 'candidate')}
    t = np.arange(rate) / rate
    control = sum(a * np.sin(2*np.pi*target*i*t) for i, a in enumerate(case['synthetic_harmonic_amplitudes'], 1))
    test = NotePitch(control, rate, minimum, config)
    wide, corrected = narrow(test, .5, target, ratio)
    max_error = case['maximum_median_abs_cents_from_score']
    return {'checks': {
                'same_outlier_selection': chosen == case['notes'],
                'reproduces_wide_search': all(result['baseline_reproduced'] for row in narrowed.values()
                                              for result in row.values()),
                'upper_bound_alone_recovers_score_neighborhood': all(row[k]['narrow_median_cents'] is not None
                    and abs(row[k]['narrow_median_cents']) <= max_error for row in narrowed.values() for k in ('upstream', 'candidate')),
                'third_harmonic_and_competing_lags': all(row['third_harmonic_observed']
                    and row['longer_lag_has_lower_normalized_difference'] for row in spectrum.values()),
                'known_harmonic_control': wide is not None and corrected is not None
                    and 1200 * math.log2(wide/target) >= cutoff
                    and abs(1200 * math.log2(corrected/target)) <= max_error,
            },
            'selected_notes': narrowed, 'spectrum_and_lags': spectrum,
            'known_harmonic_control': {'wide_hz': wide, 'narrow_hz': corrected, 'true_hz': target}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    if os.environ.get('CHIMERA_RUN_STORAGE') != 'rtl9210b':
        parser.error('計測は作業用ディスクを指定してください')
    case, original = read(CASE), read(ORIGINAL)
    baseline_run, source_run = (WORKSPACE / 'runs' / case[key] for key in ('reference_run', 'source_run'))
    baseline, candidate = (baseline_run / x for x in ('summary.json', 'artifacts/candidate.wav'))
    upstream = source_run / 'artifacts/csd/en001a-synth.wav'
    base_manifest, source_manifest = (root / 'manifest.json' for root in (baseline_run, source_run))
    recorded = read(base_manifest)['recording']
    recording = Path(recorded['path'])
    if sha256(recording) != recorded['sha256']:
        parser.error('録音が固定した入力と一致しません')
    for run, manifest, paths in ((baseline_run, base_manifest, (baseline, candidate)),
                                  (source_run, source_manifest, (upstream,))):
        hashes = {x['path']: x['sha256'] for x in read(manifest)['outputs']}
        if any(sha256(path) != hashes.get(path.relative_to(run).as_posix()) for path in paths):
            parser.error(f'保存した基準波形または計測結果が一致しません ({run.name})')
    tools = WORKSPACE / 'tools'
    inputs = [CASE, ORIGINAL, Path(__file__).resolve(), baseline, candidate, upstream, base_manifest, source_manifest,
              tools/'measure_csd_song_f0.py', tools/'measure_csd_continuous_song.py', tools/'measure_vowel_voice.py']
    return record_measurement(args.run_id, CASE, inputs, {'case_id': case['id'], 'recording': recorded},
        lambda _out, _execute: measurement(case, original['measurement'], read(baseline), candidate, upstream,
                                           recording, original['render']),
        command=None, input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
