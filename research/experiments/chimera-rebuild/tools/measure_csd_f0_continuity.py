"""歌唱F0の周期候補を残し、連続有声区間の経路を比較する。"""

import argparse
import csv
from itertools import groupby, product
import json
import math
from pathlib import Path
import subprocess
import sys

import numpy as np

from measure_csd_envelope_timing import waveforms
from measure_csd_f0_search_sensitivity import (Result, add_file, agree, period_window, published,
                                               run_inputs, score_cents, select_period)
from measure_csd_f0_third_harmonic import cut, normalized_difference, spectrum_and_lags
from measure_csd_long_notes import load_sources
from measure_csd_song_f0 import LABELS, NotePitch, midi_to_hz
from measure_csd_vibrato_aperiodicity import load_frames, median, vibrato
from measure_speech_timing import read
from measure_uniform_tube import record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE


CASE = WORKSPACE / 'cases/csd-f0-continuity.json'
MODES = ('wide', 'narrow', 'local', 'tracked')


def period_candidates(values, lower, rate, threshold, first):
    indices = np.arange(lower, len(values))
    # 両端では探索範囲の内側だけを比較する。
    minima = (values[lower:] < threshold) & np.r_[True, np.diff(values[lower:]) < 0]
    minima &= np.r_[np.diff(values[lower:]) >= 0, True]
    lags = sorted(set(indices[minima].tolist()) | {first.lag})
    return [select_period(values, lag, rate, threshold, False) for lag in lags]


def emissions(candidates, lag_weight):
    octaves = np.log2([item.hz for item in candidates])
    differences = np.asarray([item.aperiodicity for item in candidates])
    return octaves, differences + lag_weight * (octaves.max() - octaves)


def choose_path(lattice, lag_weight, transition_weight):
    bins, costs = zip(*(emissions(candidates, lag_weight) for candidates in lattice), strict=True)
    score = costs[0]
    back = []
    for previous, current, cost in zip(bins[:-1], bins[1:], costs[1:], strict=True):
        path_cost = score[:, None] + transition_weight * np.abs(previous[:, None] - current)
        origin = path_cost.argmin(axis=0)
        score = cost + path_cost[origin, np.arange(len(current))]
        back.append(origin)
    index = int(score.argmin())
    best_cost = float(score[index])
    indices = [index]
    for origin in reversed(back):
        indices.append(int(origin[indices[-1]]))
    return list(reversed(indices)), best_cost


def measure_track(estimator, centers, target, ratios, case, limits, *, independent_stride=1):
    thresholds = [max(2, int(estimator.rate / (target * ratio))) for ratio in ratios]
    rows = []
    for t in centers:
        power, values = period_window(estimator, t, target)
        if values is None:
            wide = narrow = Result('outside_wave', None, 1.0, None)
        else:
            wide, narrow = (select_period(values, k, estimator.rate, estimator.threshold, power < estimator.gate)
                            for k in thresholds)
        candidates = [] if wide.hz is None else period_candidates(
            values, thresholds[0], estimator.rate, estimator.threshold, wide)
        rows.append({'time': t, 'power': power, 'wide': wide, 'narrow': narrow, 'candidates': candidates,
                     'local': wide, 'tracked': wide})
    for voiced, segment in groupby(rows, key=lambda row: bool(row['candidates'])):
        if voiced:
            chunk = list(segment)
            lattice = [row['candidates'] for row in chunk]
            local, _ = choose_path(lattice, case['lag_cost_per_octave'], 0)
            tracked, _ = choose_path(lattice, case['lag_cost_per_octave'], case['transition_cost_per_octave'])
            for row, a, b in zip(chunk, local, tracked, strict=True):
                row.update(local=row['candidates'][a], tracked=row['candidates'][b])
    direct_ok = True
    for i, row in enumerate(rows):
        wide, narrow, local, tracked = (row[key] for key in MODES)
        if i % independent_stride and wide == narrow == local == tracked:
            continue
        for ratio, result in zip(ratios, (wide, narrow), strict=True):
            status, hz, energy, aper = estimator.at(row['time'], target, upper_ratio=ratio, include_gated_aperiodicity=True)
            direct_ok &= energy == row['power'] and agree(result, status, hz, aper, limits)
    return rows, direct_ok


def write_rows(writer, label, target, rows, truth=None):
    known = [None] * len(rows) if truth is None else truth
    for row, hz in zip(rows, known, strict=True):
        fields = [field for mode in MODES for field in row[mode]]
        writer.writerow((label, row['time'], target, hz, row['power'], *fields,
                         json.dumps([c._asdict() for c in row['candidates']], ensure_ascii=False)))


def maximum_error(rows, truth, interval, mode, *, cents=False):
    errors = []
    for row, expected in zip(rows, truth, strict=True):
        if interval[0] <= row['time'] <= interval[1]:
            hz = row[mode].hz
            if hz is None:
                return None
            errors.append(abs(score_cents(hz, expected)) if cents else abs(hz - expected))
    return max(errors, default=None)


def weak_fundamental(case, tone, pitch, ratios, limits, centers, writer):
    spec = case['fundamental_dip']
    rate = tone['sample_rate_hz']
    t = np.arange(round(tone['duration_seconds'] * rate)) / rate
    hz = spec['known_hz']
    time_marks = [*spec['transition_in_seconds'], *spec['transition_out_seconds']]
    level = spec['fundamental_relative_amplitude_at_dip']
    envelope = np.interp(t, time_marks, [1, level, level, 1])
    phase = 2 * np.pi * hz * t
    pcm = tone['relative_amplitude'] * (envelope * np.sin(phase) + spec['second_harmonic_relative_amplitude'] * np.sin(2 * phase))
    target = midi_to_hz(tone['midi'])
    rows, direct = measure_track(NotePitch(pcm, rate, tone['midi'], pitch), centers, target, ratios, case, limits)
    truth = [hz] * len(rows)
    write_rows(writer, 'weak-fundamental', target, rows, truth)
    octave_windows = {mode: sum(row[mode].hz is not None and abs(row[mode].hz - 2 * hz) <= spec['octave_error_tolerance_hz']
                                for row in rows) for mode in MODES}
    error = {mode: maximum_error(rows, truth, case['constant_interval_seconds'], mode) for mode in MODES}
    first = next((row for row in rows if row['local'] != row['tracked']), None)
    return direct, {'octave_windows': octave_windows, 'maximum_error_hz': error,
                    'first_local_to_tracked_change': describe_frame(first, target) if first else None}


def synthetic(case, tone, baseline, pitch, ratios, limits, writer):
    sample_rate = tone['sample_rate_hz']
    target = midi_to_hz(tone['midi'])
    hop = pitch['hop_seconds']
    interval = case['constant_interval_seconds']
    centers = np.arange(round(interval[0] / hop), round(interval[1] / hop) + 1) * hop
    controls, original, independent = [], True, True
    tones = product(tone['cents_offsets'], tone['harmonic_amplitudes'])
    for (offset, amplitudes), old in zip(tones, baseline['observations'], strict=True):
        original &= offset == old['input_offset_cents'] and amplitudes == old['relative_amplitudes']
        expected = target * math.exp2(offset / 1200)
        time = np.arange(round(tone['duration_seconds'] * sample_rate)) / sample_rate
        x = tone['relative_amplitude'] * sum(a * np.sin(2 * np.pi * expected * time * k)
                                            for k, a in enumerate(amplitudes, 1))
        estimator = NotePitch(x, sample_rate, tone['midi'], pitch)
        rows, direct = measure_track(estimator, centers, target, ratios, case, limits)
        independent &= direct
        center = rows[round((tone['center_seconds'] - centers[0]) / hop)]
        for mode, saved in zip(MODES[:2], old['results'], strict=True):
            original &= agree(center[mode], saved['status'], saved['hz'], saved['aperiodicity'], limits)
            original &= center[mode].lag == saved['lag']
        label = f'known-{offset}-{len(amplitudes)}-harmonics'
        truth = [expected] * len(rows)
        write_rows(writer, label, target, rows, truth)
        controls.append({'name': label, 'known_hz': expected, 'center_hz': {name: center[name].hz for name in MODES},
                         'maximum_error_hz': {name: maximum_error(rows, truth, interval, name) for name in MODES}})

    independent_dip, dip = weak_fundamental(case, tone, pitch, ratios, limits, centers, writer)
    independent &= independent_dip

    spec = case['glide']
    a, b = spec['transition_seconds']
    high = target * math.exp2(max(tone['cents_offsets']) / 1200)
    time = np.arange(round(spec['duration_seconds'] * sample_rate)) / sample_rate
    centers = np.arange(round(.05 / hop), round((spec['duration_seconds'] - .05) / hop) + 1) * hop
    ramp_time = np.clip(time - a, 0, b - a)
    phase_cycles = target * time + (high - target) * (ramp_time**2 / (2 * (b - a)) + np.maximum(time - b, 0))
    base = tone['relative_amplitude'] * sum(h * np.sin(2 * np.pi * k * phase_cycles)
                                           for k, h in enumerate(tone['harmonic_amplitudes'][-1], 1))
    truth = np.interp(centers, [0, a, b, spec['duration_seconds']], [target, target, high, high])
    glide = {}
    for label in ('glide', 'separated'):
        x = base.copy()
        if label == 'separated':
            start, stop = spec['silence_seconds']
            x[(time >= start) & (time < stop)] = 0
        rows, direct = measure_track(NotePitch(x, sample_rate, tone['midi'], pitch), centers, target, ratios, case, limits)
        independent &= direct
        write_rows(writer, label, target, rows, truth if label == 'glide' else [
            None if start <= t < stop else hz for t, hz in zip(centers, truth, strict=True)])
        glide[label] = {'early_maximum_error_hz': maximum_error(rows, truth, spec['early_plateau_seconds'], 'tracked'),
                        'late_maximum_error_hz': maximum_error(rows, truth, spec['late_plateau_seconds'], 'tracked')}
        if label == 'glide':
            glide[label]['transition_maximum_error_cents'] = maximum_error(
                rows, truth, spec['transition_seconds'], 'tracked', cents=True)
        else:
            start, stop = spec['silence_interior_seconds']
            silent = [row for row in rows if start <= row['time'] <= stop]
            glide[label]['silence_windows'] = len(silent)
            glide[label]['silence_has_no_candidates'] = bool(silent) and all(
                row['tracked'].status == 'below_energy_gate' and not row['candidates'] for row in silent)
    checks = {'saved_detuned_tone_replayed': original, 'independent_known_tone_reference': independent}
    limit = case['known_tone_tolerance_hz']
    predictions = {'known_tones_within_hz_tolerance': all(within_limit(r['maximum_error_hz']['tracked'], limit)
                                                        for r in controls),
                   'glide_and_separated_plateaus': all(within_limit(r[k], limit) for r in glide.values()
                                                     for k in ('early_maximum_error_hz', 'late_maximum_error_hz')),
                   'glide_transition': within_limit(glide['glide']['transition_maximum_error_cents'],
                                                   spec['maximum_transition_error_cents']),
                   'silent_gap_separates_paths': glide['separated']['silence_has_no_candidates'],
                   'short_octave_error_without_transition_cost': (dip['octave_windows']['local']
                        >= case['fundamental_dip']['minimum_local_octave_windows']),
                   'transition_cost_follows_weak_fundamental': within_limit(
                       dip['maximum_error_hz']['tracked'], case['fundamental_dip']['maximum_tracked_error_hz'])}
    return checks, predictions, {'constant_tones': controls, **glide, 'weak_fundamental': dip}


def within_limit(value, maximum):
    return value is not None and abs(value) <= maximum


def describe_frame(row, target):
    return {'time_seconds': row['time'], 'wide': row['wide']._asdict(), 'local': row['local']._asdict(),
            'tracked': row['tracked']._asdict(), 'target_hz': target,
            'period_candidates': [item._asdict() for item in row['candidates']]}


def song_measure(case, refs, pitch, periodicity, ratios, limits, writer):
    control, song, published_song, files, frames, narrow_ref = refs
    index = control['note_index']
    target = midi_to_hz(published_song['notes'][index]['midi'])
    minimum = min(note['midi'] for note in published_song['notes'])
    high = control['high_error_cents']
    results, checks, predictions = {}, {}, {}
    for label, (pcm, rate) in waveforms(files, song['wave_frames']).items():
        track = frames[index, label]
        estimator = NotePitch(pcm, rate, minimum, pitch)
        rows, direct = measure_track(estimator, [row.time for row in track], target, ratios, case, limits)
        write_rows(writer, label, target, rows)
        contours = {mode: [score_cents(row[mode].hz, target) for row in rows] for mode in MODES}
        result = {mode: {**vibrato(values, periodicity), 'high_windows': sum(c is not None and c >= high for c in values),
                         'voiced_windows': sum(c is not None for c in values), 'median_cents': median(values)}
                  for mode, values in contours.items()}
        results[label] = result
        for a, b in [('wide', 'local'), ('local', 'tracked'), ('wide', 'tracked')]:
            changes = [row for row in rows if row[a] != row[b]]
            result[f'{a}_to_{b}_changed_windows'] = len(changes)
            result[f'first_{a}_to_{b}_change'] = describe_frame(changes[0], target) if changes else None
        initial_high = next((row for row in rows if row['wide'].hz and score_cents(row['wide'].hz, target) >= high), None)
        if initial_high:
            params = control | {'spectrum_center_seconds': initial_high['time']}
            result['first_high_spectrum'] = spectrum_and_lags(params, estimator, target, ratios[1])
        ref = narrow_ref[label]
        metrics = ('status', 'eligible', 'run_first_frame', 'run_frames')
        legacy = all(result[a][k] == ref[b][k] for a, b in [('wide', 'wide'), ('narrow', 'limited')] for k in metrics)
        for a, b in [('wide', 'wide'), ('narrow', 'limited')]:
            for key in ('depth_cents', 'rate_hz'):
                current, baseline = result[a][key], ref[b][key]
                legacy &= (current is baseline if current is None or baseline is None
                           else within_limit(current - baseline, limits['metric_replay_tolerance']))
        independent_differences = []
        max_lag = min(estimator.width // 2, int(rate / (target / estimator.search_range)))
        for row in rows:
            if row['wide'] != row['tracked']:
                frame = cut(estimator, row['time'])
                independent_differences.extend(abs(c.aperiodicity - normalized_difference(frame, c.lag, max_lag))
                                               for c in row['candidates'])
        result['maximum_independent_cmnd_difference'] = max(independent_differences, default=0)
        checks.update({
            f'{label}/saved_original_windows': len(rows) == control['expected_grid_frames'] == len(track) and all(
                row['power'] == saved.power and agree(row['wide'], saved.status, saved.hz, saved.aper, limits)
                for row, saved in zip(rows, track, strict=True)),
            f'{label}/legacy_metrics': legacy,
            f'{label}/independent_estimates': direct,
            f'{label}/changed_candidates_independently_verified': (
                result['maximum_independent_cmnd_difference'] <= limits['aperiodicity_replay_tolerance']),
            f'{label}/voicing_and_candidates': all(
                row['wide'].status == row['tracked'].status and
                (row['tracked'] in row['candidates'] if row['wide'].hz is not None else not row['candidates']) for row in rows),
        })
        settings = case['held_out']
        if label == 'recording':
            original, tracked = result['wide']['median_cents'], result['tracked']['median_cents']
            predictions['recording_median_preserved'] = (original is not None and tracked is not None
                and within_limit(tracked - original, settings['maximum_recording_median_change_cents']))
        else:
            checks[f'{label}/saved_high_count'] = (
                result['wide']['high_windows'] == settings['expected_original_high_windows_per_synthesis'])
            predictions[f'{label}/high_windows_reduced'] = (
                result['tracked']['high_windows'] <= settings['maximum_tracked_high_windows_per_synthesis'])
            vib = result['tracked']
            predictions[f'{label}/vibrato_in_registered_range'] = (
                vib['depth_cents'] is not None and vib['rate_hz'] is not None
                and settings['vibrato_depth_cents'][0] <= vib['depth_cents'] <= settings['vibrato_depth_cents'][1]
                and settings['vibrato_rate_hz'][0] <= vib['rate_hz'] <= settings['vibrato_rate_hz'][1])
    return checks, predictions, results


def verify_lattice(case):
    frequencies = [220.0, 440.0]
    scores = [[.01, .18], [.01, .15], [.14, .005], [.01, .16], [.01, .18]]
    lattice = [[Result('voiced', hz, cmnd, None) for hz, cmnd in zip(frequencies, row, strict=True)] for row in scores]
    weight, cost_per_octave = case['lag_cost_per_octave'], case['transition_cost_per_octave']

    def total(path):
        chosen = [row[i] for row, i in zip(lattice, path, strict=True)]
        cost = sum(pick.aperiodicity + weight * math.log2(max(frequencies) / pick.hz) for pick in chosen)
        changes = sum(abs(math.log2(b.hz / a.hz)) for a, b in zip(chosen, chosen[1:]))
        return cost + cost_per_octave * changes

    expected = min((total(path), path) for path in product(range(2), repeat=len(lattice)))
    observed, cost = choose_path(lattice, weight, cost_per_octave)
    local, _ = choose_path(lattice, weight, 0)
    return observed == list(expected[1]) and math.isclose(cost, expected[0], abs_tol=1e-12), {
        'all_paths': 2 ** len(lattice), 'local_indices': local, 'tracked_indices': observed, 'cost': cost}


def measure(case, tone, tone_ref, refs, pitch, periodicity, limits, out, execute):
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera-cli', 'compare::'],
            cwd=UPSTREAM, stdout=out / 'fixed-compare-tests.log')
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera', '--test', 'golden_analysis', 'analysis_matches_typescript'],
            cwd=UPSTREAM, stdout=out / 'fixed-yin-tests.log')
    ratios = [math.exp2(value / 12) for value in limits['upper_semitones']]
    gates = ('status', 'f0_hz', 'cmnd', 'lag_samples')
    with (out / 'pitch-tracks.csv').open('w', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(('signal', 'seconds', 'score_hz', 'known_hz', 'mean_square',
                         *(f'{mode}_{field}' for mode in MODES for field in gates), 'candidates'))
        test_checks, test_predictions, controls = synthetic(case, tone, tone_ref, pitch, ratios, limits, writer)
        song_checks, song_predictions, song = song_measure(case, refs, pitch, periodicity, ratios, limits, writer)
    lattice_check, lattice = verify_lattice(case)
    return {'checks': test_checks | song_checks | {'independent_path_enumeration': lattice_check},
            'predictions': test_predictions | song_predictions, 'known_inputs': controls,
            'synthetic_lattice': lattice, 'held_out_note': song}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    case = read(CASE)
    revision = case['upstream_revision']
    if (subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip() != revision
            or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True)):
        parser.error('変更のない固定上流版が必要です')

    sensitivity_file, detuned_file, control_file = (CASE.parent / case[k] for k in
        ('sensitivity_case', 'detuned_case', 'held_out_control_case'))
    sensitivity, tone, control = (read(file) for file in (sensitivity_file, detuned_file, control_file))
    pitch_file, periodicity_file, base_file = (CASE.parent / control[k] for k in ('pitch_case', 'periodicity_case', 'base_case'))
    inputs = [CASE, sensitivity_file, detuned_file, control_file, pitch_file, periodicity_file, base_file,
              Path(__file__).resolve(), *(WORKSPACE / 'tools' / name for name in (
                  'measure_csd_f0_search_sensitivity.py', 'measure_csd_envelope_timing.py', 'measure_csd_long_notes.py',
                  'select_csd_long_notes.py', 'measure_csd_song_f0.py', 'measure_csd_f0_third_harmonic.py',
                  'measure_csd_vibrato_aperiodicity.py', 'measure_vowel_voice.py', 'measure_speech_timing.py'))]
    tone_ref = read(add_file(run_inputs(case['detuned_run'], revision, inputs), 'summary.json', inputs))
    song_run = run_inputs(control['baseline_run'], revision, inputs)
    control_run = run_inputs(case['held_out_control_run'], revision, inputs)
    historical = read(add_file(control_run, 'summary.json', inputs))
    song_id = control['song']
    reports, _ = published(song_run, 'upstream', inputs)
    song = read(add_file(song_run, 'summary.json', inputs))['songs'][song_id]
    fixed, candidate, frames = (add_file(song_run, path, inputs) for path in (
        f'artifacts/upstream/{song_id}-synth.wav', f'artifacts/{song_id}/candidate.wav',
        f'artifacts/{song_id}/note-f0-frames.csv'))
    recordings = load_sources(read(base_file), song_run[1]['selection_run'], song_run[1]['recording_run'], inputs)
    recording, = [item[3] for item in recordings if item[1]['id'] == song_id]
    refs = control, song, reports[song_id], (recording, fixed, candidate), load_frames(frames), historical['measurements']
    details = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision,
               'baseline_run': control['baseline_run'], 'analysis_directory': str(Path.cwd()),
               'analysis_command': [sys.executable, *sys.argv]}
    return record_measurement(args.run_id, CASE, inputs, details,
        lambda out, execute: measure(case, tone, tone_ref, refs, read(pitch_file)['measurement'],
                                    read(periodicity_file)['measurement'], sensitivity['measurement'], out, execute),
        command=None, input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
