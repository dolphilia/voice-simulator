"""保存済み4曲で、F0探索上限だけが音響指標に与える影響を測る。"""

import argparse
import csv
import gzip
import io
import math
import os
from pathlib import Path
import statistics
import subprocess
import sys
from collections import Counter, defaultdict
from typing import NamedTuple

import numpy as np

from measure_csd_envelope_timing import error, load_inputs, verified_file, waveforms, within
from measure_csd_long_notes import load_sources
from measure_csd_note_spectrum import Spectrum
from measure_csd_song_f0 import LABELS, NotePitch, measurement_windows, midi_to_hz
from measure_csd_vibrato_aperiodicity import check_independence, median, vibrato
from measure_speech_timing import read
from measure_uniform_tube import record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE


CASE = WORKSPACE / 'cases/csd-f0-search-sensitivity.json'
CONDITIONS = ('wide', 'narrow')
VIB_FIELDS = ('status', 'eligible', 'run_first_frame', 'run_frames', 'depth_cents', 'rate_hz')
REFERENCE_SIDES = {'recording': ('human', 'singer'), 'upstream': ('synth', 'synth')}


class Result(NamedTuple):
    status: str
    hz: float | None
    aperiodicity: float
    lag: int | None


def cmnd(window, max_lag):
    count = len(window) - max_lag
    shifted = np.lib.stride_tricks.sliding_window_view(window, count)[1:max_lag+1]
    delta = shifted - window[:count]
    np.square(delta, out=delta)
    distances = np.sum(delta, axis=1)
    cumulative = np.cumsum(distances)
    values = np.ones(max_lag+1)
    np.divide(distances*np.arange(1, max_lag+1), cumulative, out=values[1:], where=cumulative>0)
    return values


def select_period(values, lower_lag, rate, threshold, below_gate):
    found = np.flatnonzero(values[lower_lag:] < threshold)
    if not len(found):
        lag = lower_lag+int(np.argmin(values[lower_lag:]))
        status = 'below_energy_gate' if below_gate else 'unvoiced_period'
        return Result(status, None, float(values[lag]), lag)
    lag = int(found[0]+lower_lag)
    while lag+1 < len(values) and values[lag+1] < values[lag]:
        lag += 1
    refined = float(lag)
    if 1 < lag < len(values)-1:
        a, b, c = values[lag-1:lag+2]
        curvature = a-2*b+c
        if abs(curvature) > 1e-12:
            refined += (a-c)/(2*curvature)
    status = 'below_energy_gate' if below_gate else 'voiced'
    hz = None if below_gate else float(rate/refined)
    return Result(status, hz, float(values[lag]), lag)


def period_window(estimator, timestamp, target_hz):
    first = int(timestamp*estimator.rate)-estimator.width//2
    stop = first+estimator.width
    if first < 0 or stop > len(estimator.pcm):
        return None, None
    window = estimator.pcm[first:stop]
    power = float(np.mean(window**2))
    # 上限を変えても最長の遅延と差分に使うサンプル数は変わらない。
    max_lag = min(estimator.width//2, int(estimator.rate/(target_hz/estimator.search_range)))
    return power, cmnd(window, max_lag)


def estimate_both(estimator, timestamp, target_hz, ratios):
    power, values = period_window(estimator, timestamp, target_hz)
    if values is None:
        outside = Result('outside_wave', None, 1.0, None)
        return None, (outside,) * len(ratios)
    max_lag = len(values) - 1
    lower_lags = [max(2, int(estimator.rate/(target_hz*ratio))) for ratio in ratios]
    if max(lower_lags) > max_lag:
        raise ValueError('遅延範囲が登録した音符を含みません')
    return power, tuple(select_period(values, k, estimator.rate, estimator.threshold, power < estimator.gate)
                        for k in lower_lags)


def read_saved_frames(path):
    tracks = defaultdict(list)
    with path.open(newline='') as stream:
        for row in csv.DictReader(stream):
            label = row['signal']
            tracks[int(row['note_index']), label].append(
                (float(row['seconds']), row['f0_status'], float(row['f0_hz']) if row['f0_hz'] else None,
                 float(row['mean_square']) if row['mean_square'] else None,
                 float(row['aperiodicity_in_upstream_report'])))
    return tracks


def agree(result, status, hz, aperiodicity, limits):
    return (result.status == status and within(error(result.hz, hz), limits['f0_replay_tolerance_hz'])
            and within(error(result.aperiodicity, aperiodicity), limits['aperiodicity_replay_tolerance']))


def score_cents(hz, target):
    return None if hz is None else 1200*math.log2(hz/target)


def note_track(key, centers, saved, target, estimator, spectrum, ratios, settings, periodicity, output, counts, firsts):
    contour = {k: [] for k in CONDITIONS}
    small_aper = {k: [] for k in CONDITIONS}
    h1h2 = {k: [] for k in CONDITIONS}
    old_counts = counts['frames']
    checks = {'replay': True, 'direct': True, 'no_new_voiced': True, 'fft': True}
    for position, (t, base_status, base_hz, base_power, base_aper) in enumerate(saved):
        power, measured = estimate_both(estimator, t, target, ratios)
        wide, narrow = measured
        checks['replay'] &= (power == base_power and
                              agree(wide, base_status, base_hz, base_aper, settings))
        checks['no_new_voiced'] &= not (wide.hz is None and narrow.hz is not None)
        if wide != narrow or old_counts % settings['independent_sample_stride'] == 0:
            for ratio, observed in zip(ratios, measured, strict=True):
                status, hz, energy, aper = estimator.at(t, target, upper_ratio=ratio, include_gated_aperiodicity=True)
                checks['direct'] &= energy == power and agree(observed, status, hz, aper, settings)
            counts['independently_checked_frames'] += 1
        old_counts += 1
        cents = [score_cents(r.hz, target) for r in measured]
        harmonics = [None, None]
        if position % 2 == 0:
            sample = spectrum.start(t)
            if sample is not None and any(r.hz is not None for r in measured):
                fourier, parseval = spectrum.power(sample)
                checks['fft'] &= parseval <= spectrum.config['parseval_relative_tolerance']
                harmonics = [spectrum.h1h2(fourier, r.hz)[0] if r.hz is not None else None for r in measured]
        for k, r, c, h in zip(CONDITIONS, measured, cents, harmonics, strict=True):
            contour[k].append(c)
            small_aper[k].append(r.aperiodicity)
            if h is not None:
                h1h2[k].append(h)
            counts[f'{k}_{r.status}'] += 1
            counts[f'{k}_high_f0'] += c is not None and c >= settings['high_error_cents']
        change = {'note_index': key[0], 'seconds': t, 'wide_hz': wide.hz, 'narrow_hz': narrow.hz,
                  'wide_lag': wide.lag, 'narrow_lag': narrow.lag, 'wide_status': wide.status, 'narrow_status': narrow.status,
                  'wide_aperiodicity': wide.aperiodicity, 'narrow_aperiodicity': narrow.aperiodicity, 'mean_square': power}
        if wide != narrow:
            counts['changed_yin_frames'] += 1
            firsts.setdefault('first_yin_change', change)
        if wide.hz != narrow.hz:
            counts['changed_f0_frames'] += 1
            firsts.setdefault('first_f0_change', change)
        if wide.hz is not None and narrow.hz is None:
            counts['voiced_frames_lost'] += 1
            firsts.setdefault('first_voiced_frame_lost', change)
        if harmonics[0] != harmonics[1]:
            counts['changed_h1h2_frames'] += 1
        output.writerow((*key, t, power, wide.status, narrow.status, wide.hz, narrow.hz, *cents,
                         wide.lag, narrow.lag, wide.aperiodicity, narrow.aperiodicity, *harmonics))
    counts['frames'] = old_counts
    tracks = {}
    for k in CONDITIONS:
        values = contour[k]
        detail = vibrato(values, periodicity)
        voiced = sum(value is not None for value in values)
        tracks[k] = {**detail, 'f0_cents_median': median(values), 'voiced_share': voiced/len(centers),
                     'aperiodicity': median(small_aper[k]), 'h1h2_db': median(h1h2[k]), 'h1h2_frames': len(h1h2[k])}
    return tracks, checks


def compare_registered(rows, official, saved_period, short_spectrum, score, settings):
    per_note = []
    raw = []
    saved = []
    for i, row in enumerate(rows):
        for label in LABELS:
            wide = row['signals'][label]['wide']
            archived = saved_period['notes'][i]['signals'][label]
            saved.extend(error(wide[name], archived[name]) for name in (*VIB_FIELDS, 'aperiodicity', 'voiced_share')
                         if name != 'status')
            saved.append(0 if wide['status'] == archived['status'] else None)
            if short_spectrum is not None:
                saved.append(error(wide['h1h2_db'], short_spectrum['notes'][i]['signals'][label]['h1h2_db']))
            if label in REFERENCE_SIDES:
                side, score_key = REFERENCE_SIDES[label]
                per_note.append(error(wide['h1h2_db'], official['notes'][i][side]['h1h2']))
                if score is not None:
                    raw.append(error(wide['h1h2_db'], score[score_key][i][5]))
    return {'archived_metrics': all(within(x, settings['metric_replay_tolerance']) for x in saved),
            'published_h1h2': all(within(x, settings['published_rounding_tolerance']) for x in per_note),
            'raw_score_h1h2_if_available': all(within(x, settings['metric_replay_tolerance']) for x in raw)}


def song_statistics(rows, label, conditions=CONDITIONS):
    aligned = [row['signals'][label] for row in rows if row['aligned']]
    results = {}
    for key in conditions:
        group = [row[key] for row in aligned]
        eligible = [x for x in group if x['eligible']]
        detected = [x for x in eligible if x['status'] == 'detected']
        results[key] = {
            'eligible': len(eligible), 'detected': len(detected),
            'vibrato_share': len(detected)/len(eligible) if eligible else None,
            'vibrato_statuses': dict(Counter(t['status'] for t in group)),
            'depth_cents': median(x['depth_cents'] for x in detected), 'rate_hz': median(x['rate_hz'] for x in detected),
            'h1h2_db': median(x['h1h2_db'] for x in group),
            'notes_missing_h1h2': sum(x['h1h2_db'] is None for x in group),
            'notes_missing_f0': sum(x['f0_cents_median'] is None for x in group),
            'aperiodicity': median(x['aperiodicity'] for x in group),
            'voiced_share': statistics.mean(x['voiced_share'] for x in group),
        }
    return results


def check_previous_control(rows, saved_control, tolerance):
    items = rows[saved_control['note_index']]['signals']
    for label, result in saved_control['measurements'].items():
        for name, key in (('wide', 'wide'), ('narrow', 'limited')):
            a, b = items[label][name], result[key]
            if a['status'] != b['status'] or not all(within(error(a[k], b[k]), tolerance)
                                                    for k in VIB_FIELDS if k != 'status'):
                return False
    return True


def write_song(song, wave_paths, render, pitch_cfg, registered, spectrum_cfg, periodicity_cfg, settings, out):
    official = registered['official']
    source = official['notes']
    saved = read_saved_frames(registered['frames'])
    configuration = waveforms(wave_paths, render)
    minimum = min(n['midi'] for n in source)
    estimators = {k: NotePitch(pcm, rate, minimum, pitch_cfg) for k, (pcm, rate) in configuration.items()}
    spectra = {k: Spectrum(pcm, rate, spectrum_cfg) for k, (pcm, rate) in configuration.items()}
    if settings['upper_semitones'][0] != pitch_cfg['search_half_width_semitones']:
        raise ValueError('通常の上限が過去の登録と一致しません')
    ratios = [math.exp2(x/12) for x in settings['upper_semitones']]
    rows = []
    counts = {k: Counter() for k in LABELS}
    firsts = {k: {} for k in LABELS}
    frame_checks = Counter()
    with (out / f"{song['id']}-frames.csv.gz").open('wb') as binary, \
            gzip.GzipFile(fileobj=binary, filename='', mode='wb', compresslevel=4, mtime=0) as compressed, \
            io.TextIOWrapper(compressed, encoding='utf-8', newline='') as stream:
        writer = csv.writer(stream, lineterminator='\n')
        writer.writerow(('note_index', 'signal', 'seconds', 'mean_square', 'wide_status', 'narrow_status',
                         'wide_hz', 'narrow_hz', 'wide_cents', 'narrow_cents', 'wide_lag', 'narrow_lag',
                         'wide_aperiodicity', 'narrow_aperiodicity', 'wide_h1h2_db', 'narrow_h1h2_db'))
        for index, n in enumerate(source):
            _, centers = measurement_windows(n, pitch_cfg)
            tracks = {}
            for label in LABELS:
                baseline = saved[index, label]
                if [r[0] for r in baseline] != centers or not centers:
                    raise ValueError(f"音符の5 ms格子が通常条件と一致しません ({song['id']}, {index})")
                values, checked = note_track((index, label), centers, baseline, midi_to_hz(n['midi']), estimators[label],
                                              spectra[label], ratios, settings, periodicity_cfg, writer,
                                              counts[label], firsts[label])
                tracks[label] = values
                frame_checks.update({k: not v for k, v in checked.items()})
            rows.append({'note_index': index, 'ipa': n['ipa'], 'aligned': n['aligned'], 'signals': tracks})
    control = registered['control']
    checks = {k: not bad for k, bad in frame_checks.items()}
    checks['all_registered_windows'] = (len(rows) == song['notes'] and len(saved) == len(rows)*len(LABELS)
        and all(r['frames'] == song['frames_per_signal'] for r in counts.values()))
    checks.update(compare_registered(rows, official, registered['periodicity'], registered.get('spectrum'),
                                      registered.get('raw_score'), settings))
    if control is not None:
        checks['previous_single_note_experiment'] = check_previous_control(rows, control, settings['metric_replay_tolerance'])
    regression = check_independence([e for n in rows for label in LABELS for e in n['signals'][label].values()],
                                    periodicity_cfg)
    checks['independent_vibrato_regression'] = regression['matches']
    return {'checks': checks, 'split': song['split'], 'notes': rows, 'frames': counts, 'first_changes': firsts,
            'independent_vibrato': regression,
            'metrics': {k: song_statistics(rows, k) for k in LABELS}}


def run_inputs(name, revision, inputs):
    root = WORKSPACE / 'runs' / name
    manifest = root / 'manifest.json'
    meta = read(manifest)
    if meta['status'] != 'pass' or meta['upstream_revision'] != revision:
        raise ValueError(f'固定上流で検証済みの実行が必要です ({name})')
    inputs.append(manifest)
    return root, meta


def add_file(run, relative, inputs):
    path = verified_file(*run, relative)
    inputs.append(path)
    return path


def published(run, prefix, inputs):
    report = read(add_file(run, f'artifacts/{prefix}/report.json', inputs))
    score = read(add_file(run, f'artifacts/{prefix}/score.json', inputs))
    return ({song['summary']['id']: song for song in report['songs']}, score['train']['notes'])


def load_all(case, inputs):
    revision = case['upstream_revision']
    short_reference = run_inputs(case['short_source_run'], revision, inputs)
    short_spectrum = run_inputs(case['short_spectrum_run'], revision, inputs)
    short_periodicity = run_inputs(case['short_periodicity_run'], revision, inputs)
    long_ref = run_inputs(case['long_run'], revision, inputs)
    ctl = run_inputs(case['long_control_run'], revision, inputs)
    spectrum = read(add_file(short_spectrum, 'summary.json', inputs))['songs']
    period_short = read(add_file(short_periodicity, 'summary.json', inputs))['songs']
    period_long = read(add_file(long_ref, 'summary.json', inputs))['songs']
    control = read(add_file(ctl, 'summary.json', inputs))
    result = {}
    short_report, short_score = published(short_reference, 'csd', inputs)
    long_report, long_score = published(long_ref, 'upstream', inputs)
    long_case_path = CASE.parent / case['long_case']
    long_case = read(long_case_path)
    pitch_path = CASE.parent / long_case['pitch_case']
    pitch_cfg = read(pitch_path)['measurement']
    inputs.extend((long_case_path, pitch_path))
    long_waves = load_sources(long_case, long_ref[1]['selection_run'], long_ref[1]['recording_run'], inputs)
    long_waves = {ranked['id']: (recording, details) for _, ranked, _, recording, details in long_waves}
    for song in case['songs']:
        k = song['id']
        if 'wave_case' in song:
            record, paths, wave = load_inputs(case, *short_reference, song, inputs)
            render = wave['render']
            config = wave['measurement']
            comparisons = {'official': short_report[k], 'periodicity': period_short[k], 'spectrum': spectrum[k],
                           'raw_score': short_score.get(k),
                           'frames': add_file(short_periodicity, f'artifacts/{k}-pitch-periodicity-frames.csv', inputs)}
        else:
            recording, record = long_waves[k]
            paths = (recording, add_file(long_ref, f'artifacts/upstream/{k}-synth.wav', inputs),
                     add_file(long_ref, f'artifacts/{k}/candidate.wav', inputs))
            render = period_long[k]['wave_frames']
            config = pitch_cfg
            comparisons = {'official': long_report[k], 'periodicity': period_long[k], 'raw_score': long_score.get(k),
                           'frames': add_file(long_ref, f'artifacts/{k}/{k}-pitch-periodicity-frames.csv', inputs)}
        comparisons['control'] = control if k == control['song'] else None
        result[k] = (paths, render, config, comparisons, record)
    return result


def measurement(case, inputs, spectrum, periodicity, out, execute):
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera-cli', 'compare::'],
            cwd=UPSTREAM, stdout=out / 'fixed-compare-tests.log')
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera', '--test', 'golden_analysis'],
            cwd=UPSTREAM, stdout=out / 'fixed-analysis-tests.log')
    songs = {}
    checks = {}
    for song in case['songs']:
        name = song['id']
        paths, render, pitch, registered, _ = inputs[name]
        measured = write_song(song, paths, render, pitch, registered, spectrum, periodicity, case['measurement'], out)
        songs[name] = measured
        checks.update({f'{name}_{k}': value for k, value in measured['checks'].items()})
    return {'checks': checks, 'songs': songs}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    if os.environ.get('CHIMERA_RUN_STORAGE') != 'rtl9210b':
        parser.error('時系列は作業用ディスクを指定してください')
    case = read(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('差分のない固定上流版を用意してください')
    spec, periodic = (CASE.parent / case[k] for k in ('spectrum_case', 'periodicity_case'))
    artifacts = [CASE, spec, periodic, Path(__file__).resolve(),
                 *(WORKSPACE / 'tools' / name for name in ('measure_csd_note_spectrum.py', 'measure_csd_vibrato_aperiodicity.py',
                   'measure_csd_long_notes.py', 'select_csd_long_notes.py', 'measure_csd_song_f0.py',
                   'measure_vowel_voice.py', 'measure_csd_envelope_timing.py', 'measure_csd_continuous_song.py',
                   'measure_speech_timing.py', 'measure_uniform_tube.py', 'upstream_baseline.py'))]
    inputs = load_all(case, artifacts)
    details = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision,
               'driver': [sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]],
               'recordings': {k: row[-1] for k, row in inputs.items()}}
    return record_measurement(args.run_id, CASE, artifacts, details,
        lambda out, run: measurement(case, inputs, read(spec)['spectrum'], read(periodic)['measurement'], out, run),
        command=None, input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
