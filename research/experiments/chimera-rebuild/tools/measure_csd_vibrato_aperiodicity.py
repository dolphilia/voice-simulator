"""保存したCSDのF0とPCMでビブラート・非周期性を上流の報告に照合する。"""

import argparse
from collections import Counter, defaultdict
import csv
import math
import os
from pathlib import Path
import statistics
import subprocess
import sys
from typing import NamedTuple

import numpy as np

from measure_csd_envelope_timing import error, load_inputs, verified_file, waveforms, within
from measure_csd_song_f0 import LABELS, NotePitch, measurement_windows, midi_to_hz
from measure_speech_timing import read
from measure_uniform_tube import record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE


CASE = WORKSPACE / 'cases/csd-vibrato-aperiodicity.json'
# 固定上流の compare/score.rs の NoteRow 列番号。
SCORE_NOTE_COLUMNS = {'eligible': 6, 'depth_cents': 7, 'rate_hz': 8, 'voiced_share': 9, 'aperiodicity': 11}
REPORT_NOTE = {'depth_cents': 'vibDepth', 'rate_hz': 'vibRate', 'aperiodicity': 'aperiodicity', 'voiced_share': 'voiced'}
REPORT_SONG = {'depth_cents': 'vibratoDepthCents', 'rate_hz': 'vibratoRateHz', 'aperiodicity': 'aperiodicity',
               'voiced_share': 'voicedShare', 'vibrato_share': 'vibratoShare'}
SCORE_TERMS = {'depth_cents': 'vibrato depth', 'rate_hz': 'vibrato rate', 'aperiodicity': 'aperiodicity',
               'voiced_share': 'voiced share', 'vibrato_share': 'vibrato share'}
SIDES = {'recording': ('human', 'singer'), 'upstream': ('synth', 'synth')}


class PitchFrame(NamedTuple):
    time: float
    status: str
    hz: float | None
    power: float | None
    aper: float | None


def median(values):
    kept = [value for value in values if value is not None]
    return statistics.median(kept) if kept else None


def longest_run(contour):
    voiced = np.fromiter((x is not None for x in contour), dtype=bool, count=len(contour))
    boundaries = np.flatnonzero(np.diff(np.r_[False, voiced, False]))
    spans = list(zip(boundaries[::2], boundaries[1::2], strict=True))
    a, b = max(spans, key=lambda span: span[1] - span[0], default=(0, 0))
    return int(a), np.asarray(contour[a:b], dtype=float)


def detrend(values):
    pos = np.arange(len(values)) - (len(values)-1)/2
    centered = values - math.fsum(values)/len(values)
    slope = np.dot(pos, centered)/np.dot(pos, pos)
    return centered - slope*pos, float(slope)


def independent_fit(values, residual, ac, max_lag):
    x = np.arange(len(values)) - (len(values)-1)/2
    design = np.column_stack((np.ones(len(x)), x))
    model = design @ np.linalg.lstsq(design, values, rcond=None)[0]
    error_cents = float(np.max(np.abs((values - model) - residual)))
    if ac is None:
        return error_cents, None
    # 回帰を解き直し、全ラグの相関を一度に計算する。
    fitted_residual = values - model
    overlap = np.arange(len(x), len(x)-max_lag-1, -1)
    product_sums = np.correlate(fitted_residual, fitted_residual, mode='full')[len(x)-1:len(x)+max_lag]
    computed = (product_sums/overlap) / (product_sums[0]/len(x))
    return error_cents, float(np.max(np.abs(computed - ac)))


def vibrato(contour, config):
    start, values = longest_run(contour)
    hop = config['hop_seconds']
    n = len(values)
    eligible = n * hop >= config['minimum_run_seconds']
    result = {'run_first_frame': start if n else None, 'run_frames': n, 'run_seconds': n*hop,
              'eligible': eligible, 'status': 'too_short', 'depth_cents': None, 'rate_hz': None,
              'first_peak_lag_frames': None, 'first_peak_correlation': None, 'first_peak_rate_hz': None,
              'residual_rms_cents': None, 'trend_cents_per_frame': None, 'independent_residual_error_cents': None,
              'independent_correlation_error': None}
    if not eligible:
        return result
    residual, slope = detrend(values)
    energy = float(np.dot(residual, residual)/n)
    result.update(trend_cents_per_frame=slope, residual_rms_cents=math.sqrt(energy))
    low, high = config['allowed_rate_hz']
    max_lag = min(n-1, math.ceil(1/(low*hop))+1)
    if energy <= 0:
        result['independent_residual_error_cents'], _ = independent_fit(values, residual, None, max_lag)
        result['status'] = 'zero_residual'
        return result
    ac = [1.0] + [float(np.dot(residual[:-j], residual[j:])/(n-j)/energy) for j in range(1, max_lag+1)]
    residual_error, ac_error = independent_fit(values, residual, ac, max_lag)
    result.update(independent_residual_error_cents=residual_error, independent_correlation_error=ac_error)
    peak = next((j for j in range(config['lag_min_frames'], max_lag)
                 if ac[j] >= max(config['minimum_peak_correlation'], ac[j-1], ac[j+1])), None)
    if peak is None:
        result['status'] = 'no_correlation_peak'
        return result
    a, b, c = ac[peak-1:peak+2]
    curve = a-2*b+c
    correction = .5*(a-c)/curve if curve < 0 else 0
    frequency = 1/((peak+correction)*hop)
    result.update(first_peak_lag_frames=peak, first_peak_correlation=b, first_peak_rate_hz=frequency)
    if not low <= frequency <= high:
        result['status'] = 'rate_out_of_range'
        return result
    result.update(status='detected', rate_hz=frequency, depth_cents=math.sqrt(energy)*math.sqrt(2))
    return result


def modulation_controls(config, setup):
    indices = np.arange(setup['contour_frames'])

    def sine(rate):
        return (setup['peak_cents'] * np.sin(2*np.pi*rate*indices*config['hop_seconds'])).tolist()

    periodic = {str(hz): vibrato(sine(hz), config) for hz in setup['rates_hz']}
    fast = {str(hz): vibrato(sine(hz), config) for hz in setup['fast_rates_hz']}
    base = sine(setup['rates_hz'][1])
    trend = setup['trend_offset_cents'] + setup['trend_slope_cents_per_frame'] * indices
    inclined = vibrato((np.asarray(base)+trend).tolist(), config)
    original = periodic[str(setup['rates_hz'][1])]
    depth_shift = error(original['depth_cents'], inclined['depth_cents'])
    rate_shift = error(original['rate_hz'], inclined['rate_hz'])
    minimum = setup['min_frames']
    before_minimum = vibrato([0.0]*(minimum-1), config)
    exact_minimum = vibrato([0.0]*minimum, config)
    linear = vibrato(trend.tolist(), config)
    merged = vibrato(base[:2*minimum-1], config)
    separate = base[:2*minimum-1]
    separate[minimum-1] = None
    split = vibrato(separate, config)
    tie = vibrato(([0.0]*minimum)+[None]+base[:minimum], config)
    independent = check_independence([*periodic.values(), *fast.values(), inclined, linear, merged, tie], config)
    return {'checks': {
        'periodic_rate_and_depth': all(within(error(res['rate_hz'], float(hz)), setup['rate_tolerance_hz'])
            and within(error(res['depth_cents'], setup['peak_cents']), setup['depth_tolerance_cents'])
            for hz, res in periodic.items()),
        'fast_first_peak_rejected': all(r['status'] == 'rate_out_of_range'
            and within(error(r['first_peak_rate_hz'], float(hz)), setup['rate_tolerance_hz']) for hz, r in fast.items()),
        'trend_independence': within(depth_shift, config['independent_residual_tolerance_cents'])
            and within(rate_shift, config['independent_correlation_tolerance']) and linear['status'] == 'zero_residual',
        'minimum_run_and_first_tie': before_minimum['status'] == 'too_short' and exact_minimum['status'] == 'zero_residual'
            and tie['run_first_frame'] == 0 and tie['run_frames'] == minimum,
        'missing_center_splits_voiced_run': merged['status'] == 'detected'
            and split['status'] == 'too_short' and split['run_first_frame'] == 0 and split['run_frames'] == minimum-1,
        'independent_regression_and_correlation': independent['matches'],
    }, 'periodic': periodic, 'fast': fast, 'trend': inclined, 'pure_trend': linear, 'minimum': exact_minimum,
        'below_minimum': before_minimum, 'joined': merged, 'split': split, 'tied': tie, 'independent': independent}


def aperiodicity_controls(setup, pitch_config):
    rate = setup['pcm_rate_hz']
    hz = setup['pcm_tone_hz']
    time = np.arange(rate*2)/rate
    gain = np.select((time < 1, time < 1.5), (setup['pcm_loud_amplitude'], setup['pcm_quiet_amplitude']), 0)
    pcm = gain * np.sin(2*np.pi*hz*time)
    midi = 69 + 12*math.log2(hz/440)
    estimator = NotePitch(pcm, rate, midi, pitch_config)
    rows = {label: estimator.at(t, hz, include_gated_aperiodicity=True)
            for label, t in (('loud', .5), ('quiet', 1.25), ('silence', 1.75), ('outside', 0))}
    loud, quiet, silence, outside = (rows[key] for key in ('loud', 'quiet', 'silence', 'outside'))
    old_quiet = estimator.at(1.25, hz)
    floor = setup['maximum_periodic_aperiodicity']
    return {'checks': {
        'gate_masks_f0_with_periodicity_retained': loud[0] == 'voiced' and loud[1] is not None
            and quiet[0] == 'below_energy_gate' and quiet[1] is None
            and loud[2] >= estimator.gate > quiet[2]
            and within(loud[3], floor) and within(quiet[3], floor)
            and old_quiet[:3] == quiet[:3] and old_quiet[3] is None,
        'silence_and_outside_wave': silence == ('below_energy_gate', None, 0.0, 1.0)
            and outside == ('outside_wave', None, None, 1.0) and estimator.at(0, hz)[3] is None,
    }, 'gate': estimator.gate, 'status_f0_power_aperiodicity': rows}


def load_frames(path):
    frames = defaultdict(list)

    def number(text):
        return float(text) if text else None

    with path.open(newline='') as stream:
        for row in csv.DictReader(stream):
            frame = PitchFrame(float(row['time_seconds']), row['status'], number(row['f0_hz']),
                               number(row['mean_square']), number(row['aperiodicity']))
            if (frame.hz is not None) != (frame.status == 'voiced'):
                raise ValueError('保存したF0の有声判定と値が一致しません')
            frames[int(row['note_index']), row['signal']].append(frame)
    return frames


def note_track(rows, source, target, estimator, config, writer):
    contour = []
    aperiodicity = []
    recovered = Counter()
    examples = {}
    for f in rows:
        cents = None if f.hz is None else 1200 * math.log2(f.hz / target)
        contour.append(cents)
        aper = f.aper
        if aper is None:
            state, hz, power, aper = estimator.at(f.time, target, include_gated_aperiodicity=True)
            if (state, hz, power) != (f.status, f.hz, f.power) or state not in ('outside_wave', 'below_energy_gate'):
                raise ValueError(f'非周期性を補完する窓が先行実行と一致しません ({source}, {f.time})')
            recovered[state] += 1
            examples.setdefault(state, {'seconds': f.time, 'mean_square': power, 'aperiodicity': aper,
                                        'gate_mean_square': estimator.gate})
        if aper is None or not math.isfinite(aper):
            raise ValueError(f'非周期性の値が得られません ({source}, {f.time})')
        aperiodicity.append(aper)
        writer.writerow((*source, f.time, f.status, f.hz, cents, f.power, f.aper, aper))
    measured = vibrato(contour, config)
    begin = measured['run_first_frame']
    if begin is not None:
        measured['run_center_seconds'] = [rows[begin].time, rows[begin+measured['run_frames']-1].time]
    measured['voiced_share'] = sum(value is not None for value in contour)/len(rows) if rows else None
    measured['aperiodicity'] = median(aperiodicity)
    measured['visible_only_aperiodicity'] = median(f.aper for f in rows)
    measured['recovered_frames'] = dict(recovered)
    measured['first_recovered_frames'] = examples
    return measured, contour, aperiodicity


def check_independence(notes, config):
    residual = [n['independent_residual_error_cents'] for n in notes if n['eligible']]
    correlation = [n['independent_correlation_error'] for n in notes if n['residual_rms_cents']]
    return {'matches': all(within(x, config['independent_residual_tolerance_cents']) for x in residual)
        and all(within(x, config['independent_correlation_tolerance']) for x in correlation),
        'compared_trends': len(residual), 'compared_correlations': len(correlation),
        'maximum_residual_error_cents': max(residual, default=None), 'maximum_correlation_error': max(correlation, default=None)}


def aggregate(rows, key):
    tracks = [n['signals'][key] for n in rows if n['aligned']]
    eligible = [x for x in tracks if x['eligible']]
    detected = [x for x in eligible if x['status'] == 'detected']
    voiced = [x['voiced_share'] for x in tracks if x['voiced_share'] is not None]
    filled = Counter()
    for row in tracks:
        filled.update(row['recovered_frames'])
    changed = sum(x['visible_only_aperiodicity'] != x['aperiodicity'] for x in tracks)
    return {'eligible': len(eligible), 'detected': len(detected), 'statuses': dict(Counter(n['status'] for n in tracks)),
            'depth_cents': median(x['depth_cents'] for x in tracks), 'rate_hz': median(x['rate_hz'] for x in tracks),
            'aperiodicity': median(x['aperiodicity'] for x in tracks),
            'visible_only_aperiodicity': median(x['visible_only_aperiodicity'] for x in tracks),
            'aperiodicity_medians_changed_by_including_gated_frames': changed, 'recovered_frames': dict(filled),
            'voiced_share': statistics.mean(voiced) if voiced else None,
            'vibrato_share': len(detected)/len(eligible) if eligible else None}


def comparison(notes, report, score, name, config):
    by_signal = {k: aggregate(notes, k) for k in LABELS}
    terms = {item['name']: item for item in score['terms']}
    raw = score.get('notes', {}).get(name)
    raw_errors, note_errors = [], []
    song_errors, term_errors = {}, {}
    for key, (label, score_label) in SIDES.items():
        result = by_signal[key]
        song_errors[key] = {v: error(result[k], report['summary'][v][label]) for k, v in REPORT_SONG.items()}
        term_errors[key] = {}
        for field, term in SCORE_TERMS.items():
            other = 'recording' if key == 'upstream' else 'upstream'
            value = result[field] if by_signal[other][field] is not None else None
            term_errors[key][term] = error(value, terms[term][score_label])
        for note, original in zip(notes, report['notes'], strict=True):
            measured = note['signals'][key]
            note_errors.extend(error(measured[k], original[label][v]) for k, v in REPORT_NOTE.items())
            if raw is not None:
                reference = raw[score_label][note['note_index']]
                raw_errors.extend(error(measured[k], reference[i]) for k, i in SCORE_NOTE_COLUMNS.items())

    tol = config['published_tolerance']
    check = {
        'published_note_values': all(within(x, tol) for x in note_errors),
        'published_song_values': all(within(x, tol) for per_side in song_errors.values() for x in per_side.values()),
        'score_terms': score['songs'] == [name] and all(within(x, config['published_score_term_tolerance'])
             for per_side in term_errors.values() for x in per_side.values()),
    }
    if raw is not None:
        check['unrounded_score_notes'] = all(within(x, config['raw_score_tolerance']) for x in raw_errors)
    return {'checks': check, 'signals': by_signal, 'published_song_errors': song_errors, 'score_term_errors': term_errors,
            'maximum_note_report_error': None if None in note_errors else max(note_errors),
            'maximum_unrounded_score_error': None if not raw_errors or None in raw_errors else max(raw_errors)}


def first_frame_difference(records, rows, notes, key, tolerance):
    for index, note in enumerate(notes):
        a, b = (records[index, signal][key] for signal in LABELS[1:])
        for j, (left, right) in enumerate(zip(a, b, strict=True)):
            discrepancy = error(left, right)
            if discrepancy is None or discrepancy > tolerance:
                return {'note_index': index, 'ipa': note['ipa'], 'frame': j, 'seconds': rows[index, 'upstream'][j].time,
                        'upstream': left, 'candidate': right}
    return None


def first_note_difference(notes, key):
    for n in notes:
        a, b = (n['signals'][label] for label in LABELS[1:])
        if a[key] != b[key]:
            return {'note_index': n['note_index'], 'ipa': n['ipa'], 'upstream': a, 'candidate': b}
    return None


def measure_song(case, song, report, score, saved_pitch, wave_case, files, out):
    song_id, config = song['id'], case['measurement']
    annotations = report['notes']
    pitch_config = wave_case['measurement']
    if pitch_config['hop_seconds'] != config['hop_seconds'] or len(annotations) != song['notes']:
        raise ValueError(f'{song_id} の音符数またはフレーム間隔が登録と一致しません')
    frames = load_frames(saved_pitch)
    if len(frames) != song['notes']*len(LABELS) or any(sum(len(frames[i, key]) for i in range(len(annotations)))
            != song['centers_per_signal'] for key in LABELS):
        raise ValueError(f'{song_id} のF0の窓数が登録と一致しません')
    low_midi = min(n['midi'] for n in annotations)
    estimators = {key: NotePitch(pcm, rate, low_midi, pitch_config)
                  for key, (pcm, rate) in waveforms(files, wave_case['render']).items()}
    notes = []
    series = {}
    with (out / f'{song_id}-pitch-periodicity-frames.csv').open('w', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(('note_index','signal','seconds','f0_status','f0_hz','cents','mean_square',
                         'aperiodicity_in_pitch_run','aperiodicity_in_upstream_report'))
        for i, note in enumerate(annotations):
            bounds, centers = measurement_windows(note, pitch_config)
            target = midi_to_hz(note['midi'])
            result = {'note_index': i, 'ipa': note['ipa'], 'aligned': note['aligned'], 'stable_seconds': bounds,
                      'signals': {}}
            for key, estimator in estimators.items():
                rows = frames[i, key]
                if [r.time for r in rows] != centers:
                    raise ValueError(f'{song_id} の音符 {i} の保存済みF0時刻が一致しません')
                measured, contour, aperiodicity = note_track(rows, (i, key), target, estimator, config, writer)
                result['signals'][key] = measured
                series[i, key] = {'cents': contour, 'aperiodicity': aperiodicity}
            notes.append(result)
    stats = comparison(notes, report, score, song_id, config)
    independence = check_independence([x for note in notes for x in note['signals'].values()], config)
    stats['checks']['independent_regression_and_correlation'] = independence['matches']
    return {'split': song['split'], 'notes': notes, **stats, 'independent': independence,
            'first_cents_difference': first_frame_difference(series, frames, notes, 'cents', config['first_cents_difference']),
            'first_aperiodicity_difference': first_frame_difference(series, frames, notes, 'aperiodicity',
                                                                   config['first_aperiodicity_difference']),
            'first_different_run_eligibility': first_note_difference(notes, 'eligible'),
            'first_different_detection_status': first_note_difference(notes, 'status')}


def measurement(case, sources, reports, scores, out, run):
    run(['cargo', 'test', '--locked', '--offline', '-p', 'chimera-cli', 'compare::'],
        cwd=UPSTREAM, stdout=out / 'fixed-compare-tests.log')
    run(['cargo', 'test', '--locked', '--offline', '-p', 'chimera', '--test', 'golden_analysis'],
        cwd=UPSTREAM, stdout=out / 'fixed-analysis-tests.log')
    traces = modulation_controls(case['measurement'], case['controls'])
    pcm_control = aperiodicity_controls(case['controls'], sources[0][2]['measurement'])
    checks = {**traces['checks'], **pcm_control['checks']}
    songs = {}
    for song, (_, files, wave_case, f0) in zip(case['songs'], sources, strict=True):
        key = song['id']
        result = measure_song(case, song, reports[key], scores[song['split']], f0, wave_case, files, out)
        songs[key] = result
        checks.update({f'{key}_{k}': v for k, v in result['checks'].items()})
    return {'checks': checks, 'contour_controls': traces, 'wave_controls': pcm_control, 'songs': songs}


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
    source_manifest_path = source / 'manifest.json'
    source_manifest = read(source_manifest_path)
    if source_manifest['status'] != 'pass' or source_manifest['upstream_revision'] != revision:
        parser.error('固定上流の通常報告と一致しません')
    report = verified_file(source, source_manifest, 'artifacts/csd/report.json')
    score = verified_file(source, source_manifest, 'artifacts/csd/score.json')
    reports = {song['summary']['id']: song for song in read(report)['songs']}
    score_data = read(score)
    scores = {'calibration': score_data['train'], 'held_out': score_data['heldout']}
    inputs = [CASE, source_manifest_path, report, score, Path(__file__).resolve(),
              *(WORKSPACE / 'tools' / name for name in ('measure_csd_envelope_timing.py', 'measure_csd_song_f0.py',
                'measure_csd_continuous_song.py', 'measure_vowel_voice.py', 'measure_speech_timing.py',
                'measure_uniform_tube.py', 'upstream_baseline.py'))]
    sources = []
    for song in case['songs']:
        recording, paths, wave_case = load_inputs(case, source, source_manifest, song, inputs)
        original = WORKSPACE / 'runs' / song['wave_run']
        f0 = verified_file(original, read(original / 'manifest.json'), 'artifacts/note-f0-frames.csv')
        sources.append((recording, paths, wave_case, f0))
        inputs.append(f0)
    details = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision,
               'driver': [sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]],
               'recordings': {s['id']: x[0] for s, x in zip(case['songs'], sources, strict=True)}}
    return record_measurement(args.run_id, CASE, inputs, details,
        lambda out, run: measurement(case, sources, reports, scores, out, run), command=None, input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
