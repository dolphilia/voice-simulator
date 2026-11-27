"""/dʒ/ の閉鎖中の有声性と解放を /tʃ/ および固定上流と照合する。"""

import argparse
import math
import os
from pathlib import Path
import subprocess

import numpy as np
from scipy.io import wavfile
from scipy.signal import lfilter

import measure_alveolar_stop as cells
import measure_alveolopalatal_affricates as events
import measure_bilabial_stop as voice
import measure_english_rhotic as fixtures
import measure_postalveolar_affricate as tsh
import measure_postalveolar_fricative as sh
import measure_sibilant as frication
import measure_speech_timing as timing
import measure_uniform_tube as shared
import measure_wasm_fixed as pcm_metrics
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/postalveolar-affricate-dzh.json'


def registered_gestures(span, following, variant, rate, tip):
    ipa = span['ipa']
    a, b = span['t0'], span['t1']
    split = a + .45 * (b - a)
    release = max(a, split - .015)
    opening = split if ipa == 'dʒ' else a + .15 * (b - a)
    lip = {'lip_protrusion_cm': .75, 'lip_spread': .2}
    oral = {'label': ipa, 'strength': 40, 'rampIn': .030 / rate,
            'rampOut': .018 / rate, 'releaseHold': .045 / rate}
    expected = [
        {**oral, 't0': a - .031, 't1': max(a + .010, split - .020), 'speed': 2,
         'targets': {**lip, 'tongue_tip_x_cm': 5.75, 'tongue_tip_y_cm': 10}},
        {**oral, 't0': release - .008, 't1': max(release + .010, b), 'speed': 1.4,
         'targets': {**lip, 'tongue_tip_x_cm': 5.7, 'tongue_tip_y_cm': tip, 'jaw_cm': .35}},
        {'label': 'voiced affricate' if ipa == 'dʒ' else 'aspiration',
         't0': opening, 't1': max(opening, b - .030), 'strength': 6, 'rampIn': .035 / rate,
         'rampOut': min(.03, b - opening) / rate, 'targets': {'abduction_cm2': .36}},
    ]
    if variant.get('breathy'):
        expected.append({'label': 'breathy', 't0': b - .02, 't1': min(b + .08, following['t1']),
                         'strength': 5, 'rampIn': .03 / rate, 'rampOut': .03 / rate,
                         'targets': {'abduction_cm2': .10}})
    if variant.get('palatalized'):
        expected.append({'label': 'palatalized', 't0': a, 't1': b,
                         'strength': 3, 'rampIn': .04 / rate, 'rampOut': .04 / rate,
                         'targets': {'tongue_body_x_cm': 3.8, 'tongue_body_y_cm': 7.95}})
    return expected


def compare_plan(settings, upper, variant, body, config):
    limits = config['measurement']
    tol = limits['gesture_abs_tolerance']
    song = settings.get('song')
    phrases = song['plan']['phrases'] if song else settings['speech'].get('phrases')
    adapted = settings if phrases is None else {**settings, 'speech': {'utterances': [
        {'segments': phrase['timing']['segments']} for phrase in phrases]}}
    segments, report = frication.compare_plans(adapted, upper, tol)
    ipa = variant.get('ipa', 'dʒ')
    span, = [part for part in segments if part['ipa'] == ipa]
    a, b = span['t0'], span['t1']
    rate = max(1, variant.get('rate', 1))
    tip = sh.blend(config['release_tip_cm'][ipa], body)
    following = next((s for s in segments if s['t0'] >= b), {'t1': b + .08})
    expected = registered_gestures(span, following, variant, rate, tip)
    labels = {g['label'] for g in expected}
    observed = [g for g in settings['gestures'] if g['label'] in labels]
    difference, error = timing.compare(observed, expected, tol)
    checks = {'fixed_upstream_plan': report['passed'], 'registered_articulation': difference is None}
    report.update(span=span, tip_y_cm=tip, first_registered_difference=difference,
                  maximum_registered_difference=error, gestures=observed)
    if variant.get('canonical'):
        minimum, inherent = (limits[label][ipa] for label in ('minimums_ms', 'inherent_ms'))
        d = (minimum + (inherent - minimum) * .85) / 1000
        checks['registered_duration'] = abs(b - a - d) <= tol
    if variant['id'] == 'placed-closure':
        stop = next(part for part in segments if part['ipa'] == 't')
        delay = min(.025, max(0, stop['t1'] - stop['t0'] - .030))
        at = stop['t0'] + delay
        closure = next(g for g in settings['gestures'] if g['label'] == 't' and 'tongue_tip_y_cm' in g['targets'])
        checked = [closure['t0'], closure['t1']]
        estimate = [at - .031, max(at + .010, stop['t1'] - .020)]
        difference, _ = timing.compare(checked, estimate, tol)
        checks['prepositioned_tip'] = difference is None
        report['following_closure'] = {'delay_seconds': delay, 'predicted': estimate, 'observed': checked}
    if song:
        folds = next(g for g in observed if g['label'] == 'voiced affricate')
        release = next(g for g in observed if g.get('speed') == 1.4)
        beat = song['plan']['notes'][1]['nucleus_start_seconds']
        checks['short_sung_folds_and_release'] = (abs(b - a - .0125) <= tol
            and abs(b - beat) <= tol and abs(folds['t0'] - folds['t1']) <= tol
            and abs(folds['t1'] + folds['rampOut'] - b) <= tol and release['t0'] >= a - .008 - tol)
        report['nucleus_beat_seconds'] = beat
    return checks, report


def closing_low_band_db(pcm, start, limits):
    rate = limits['output_rate_hz']
    width = round(rate * limits['spectral_frame_seconds'])
    left, right = (int(t * rate / width) * width for t in (start - .01, start + .03))
    # ヌル状態から閉鎖の終端まで処理し、閉鎖窓の系列だけ比較する。
    alpha = -math.expm1(-2 * math.pi * limits['spectral_lowpass_hz'] / rate)
    full = pcm[:right].astype(float)
    low = lfilter([alpha], [1, alpha - 1], lfilter([alpha], [1, alpha - 1], full))
    power = [(x[left:right].reshape(-1, width)**2).sum(axis=1) + 1e-20 for x in (full, low)]
    return float(np.min(10 * np.log10(power[1] / power[0])))


def narrow_open_passage(trace, span, limits):
    rate = limits['output_rate_hz']
    time = (trace['frame'] + 1) / rate
    a, b = span['t0'], span['t1']
    window = (time >= a - limits['closure_window_padding_seconds']) & (time < b)
    area = trace['oral_minimum_cm2']
    threshold = limits['male_narrow_open_area_cm2']
    narrow = np.flatnonzero(window & (area < threshold))
    if not narrow.size:
        return {'passed': False, 'minimum_cm2': float(area[window].min())}
    narrowed = max(np.split(narrow, np.flatnonzero(np.diff(narrow) != 1) + 1), key=len)
    minimum = int(narrowed[np.argmin(area[narrowed])])
    cell = int(trace['oral_minimum_cell'][minimum])
    branches = [f'oral_branch_{branch}_flow_cm3_s' for branch in (cell - 1, cell)]
    reopening = int(narrowed[-1]) + 1
    if reopening >= len(trace) or not all(branch in trace.dtype.names for branch in branches):
        return {'passed': False, 'minimum_frame': minimum, 'minimum_cell': cell, 'reopening_frame': reopening}
    flow = [float(trace[branch][minimum]) for branch in branches]
    jets = np.flatnonzero((trace['frame'] >= reopening) & (time < b + limits['release_window_padding_seconds'])
                          & (trace['teeth_noise_level'] > 0))
    pulse, period = events.periodic_onset(trace, time, reopening, b + limits['voicing_search_padding_seconds'], limits)
    fully_closed = int(np.count_nonzero(window & (area < limits['closed_area_cm2'])))
    return {'passed': bool(fully_closed == 0 and len(narrowed) >= limits['minimum_closed_frames']
                           and trace['lip_minimum_cm2'][minimum] >= limits['open_lip_minimum_cm2']
                           and min(flow) > 0 and area[reopening] >= threshold
                           and jets.size >= limits['minimum_teeth_active_frames_after_release']
                           and pulse is not None and jets[0] < pulse),
            'minimum_cm2': float(area[minimum]), 'minimum_frame': minimum, 'minimum_cell': cell,
            'narrow_frames': len(narrowed), 'fully_closed_frames': fully_closed, 'flow_cm3_s': flow,
            'reopening_frame': reopening, 'first_jet_after_reopening_frame': int(jets[0]) if jets.size else None,
            'periodic_return_frame': pulse, 'pulse_period_frames': period}


def compare_variant(config, variant, source, output, probe, execute):
    limits = config['measurement']
    output.mkdir()
    path = output / 'case.json'
    key = 'song_voice' if 'score' in source else 'speech_voice'
    timing.write(path, {'id': variant['id'], 'upstream_revision': config['upstream_revision'], key: source})
    settings, trace, files, upper_trace, raw, plan_path = voice.capture(
        path, limits['host_block_frames'], output, execute, (), probe=probe)
    upper = timing.read(plan_path)
    body = source['body']
    checks, plan = compare_plan(settings, upper, variant, body, config)
    span = plan['span']
    count = settings['output_frames']
    native, reference = [tsh.load_trace(path, count) for path in (trace, upper_trace)]
    names = [[field for field in t.dtype.names if field != 'oral_minimum_cell'] for t in (native, reference)]
    mismatches, errors = frication.source_comparison(native[names[0]], reference[names[1]], limits)
    minima = cells.compare_cell_minima(native, reference, {**limits,
                                                      'geometry_absolute_tolerance': limits['geometry_abs_tolerance']})
    rate, pcm = wavfile.read(files[0][0])
    upstream_pcm = np.fromfile(raw, dtype='<f4')
    if any(x.shape != (count,) or x.dtype != np.float32 or not np.isfinite(x).all() for x in (pcm, upstream_pcm)):
        raise ValueError('PCMのフレーム数、型または有限性が条件外です')
    pcm_diff = pcm_metrics.compare_pcm(pcm, upstream_pcm, limits['pcm_abs_tolerance'])
    checks.update(physical_trace=not mismatches and minima['passed'],
                  pcm=pcm_diff['first_frame_over_tolerance'] is None,
                  sample_rates_and_frames=rate == limits['output_rate_hz'] and count == upper['output_frames']
                  and source['internal_sample_rate_hz'] == limits['internal_rate_hz'],
                  host_partitions=all(sha256(w) == sha256(files[0][0]) and sha256(t) == sha256(files[0][1])
                                      for w, t in files))
    waves = (pcm, upstream_pcm)
    acoustic = [events.observe(data, x, span, limits) for data, x in zip((native, reference), waves, strict=True)]
    band = [frication.independent_band(data, limits['selection_abs_tolerance'],
                                     body_scale=sh.blend(limits['length_scales'], body))
            for data in (native, reference)]
    if variant.get('canonical'):
        settings_spectral = {**limits, 'spectral_minimum_frication_ms': limits['spectral_minimum_frication_ms'][span['ipa']]}
        spectral = [tsh.spectral_events(x, span, settings_spectral) for x in waves]
        checks.update(acoustic_frication_into_vowel=all(row['passed'] for row in spectral),
                      independent_teeth_band=all(row['passed'] for row in band))
        if variant['id'] == 'male' and 'male_narrow_open_area_cm2' in limits:
            passages = [narrow_open_passage(data, span, limits) for data in (native, reference)]
            checks['narrow_passage_teeth_and_periodic_return'] = all(row['passed'] for row in passages)
            for acoustic_row, opening in zip(acoustic, passages, strict=True):
                acoustic_row['narrow_passage'] = opening
        else:
            checks['closure_teeth_and_periodic_return'] = all(row['passed'] for row in acoustic)
        for detail, x in zip(spectral, waves, strict=True):
            detail['lowest_closing_low_band_db'] = closing_low_band_db(x, span['t0'], limits)
    else:
        spectral = None
    first_numeric = {}
    for field in ('tongue_tip_y_cm', 'oral_minimum_cm2', 'abduction_cm2', 'glottal_area_cm2',
                  'teeth_noise_forward_pressure', 'radiation_derivative_cm3_s2'):
        hits = np.flatnonzero(native[field] != reference[field])
        first_numeric[field] = None if not hits.size else {'frame': int(hits[0]),
            'difference': float(native[field][hits[0]] - reference[field][hits[0]])}
    return checks, {'plan': plan, 'events': acoustic, 'spectral': spectral, 'noise_band': band,
                    'output_frames': count, 'pcm': pcm_diff, 'first_numeric_difference': first_numeric,
                    'trace_errors': errors, 'first_trace_differences': mismatches, 'oral_minimum_cells': minima}


def measure(config, speech, song, earlier, transcripts, artifacts, execute):
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera', '--test', 'affricates',
             '--test', 'sing_fast', '--test', 'consonant_artifacts', '--', '--nocapture'], cwd=UPSTREAM,
            stdout=artifacts / 'upstream-tests.log')
    probe = shared.build_upstream_probe(voice.PROBE, artifacts, execute, extra_libraries=('serde_json',))
    checks = {}
    contexts = {}
    for variant, source in fixtures.choose_inputs(config, speech, song, transcripts):
        name = variant['id']
        flags, contexts[name] = compare_variant(config, variant, source, artifacts / name, probe, execute)
        checks.update({f'{name}:{key}': value for key, value in flags.items()})
    checks['prior_only_dzh'] = all(earlier['observations'][name].get('error', '').endswith('(dʒ)')
                                   and contexts[name]['plan']['span']['ipa'] == 'dʒ'
                                   for name in config['english']['newly_renderable_ids'])
    advantage = {}
    for body in ('male', 'female'):
        voiced, voiceless = (contexts[name]['spectral'] for name in (body, body + '-tsh'))
        advantage[body] = [a['lowest_closing_low_band_db'] - b['lowest_closing_low_band_db']
                           for a, b in zip(voiced, voiceless, strict=True)]
    threshold = config['measurement']['spectral_minimum_voiced_closure_advantage_db']
    checks['voiced_closure_low_band_advantage'] = all(min(pair) > threshold for pair in advantage.values())
    return {'checks': checks, 'contexts': contexts, 'voiced_closure_low_band_advantage_db': advantage}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    if os.environ.get('CHIMERA_RUN_STORAGE') != 'rtl9210b':
        parser.error('観測CSVは CHIMERA_RUN_STORAGE=rtl9210b で作業用ディスクに出力してください')
    config = timing.read(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != config['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('差分のない固定上流版を用意してください')
    speech_path, song_path = (CASE.parent / config[name] for name in ('speech_base', 'song_base'))
    transcripts = UPSTREAM / config['english']['transcripts']
    prior = WORKSPACE / 'runs' / config['english']['prior_support_run']
    sources = (cells, events, voice, fixtures, tsh, sh, frication, timing, pcm_metrics)
    inputs = [CASE, speech_path, song_path, transcripts, prior / 'summary.json', prior / 'manifest.json',
              Path(__file__).resolve(), voice.PROBE, *(Path(module.__file__) for module in sources),
              *shared.candidate_sources()]
    speech = timing.read(speech_path)['speech_voice']
    speech.pop('turbulence', None)
    song = timing.read(song_path)['song_voice']
    return shared.record_measurement(args.run_id, CASE, inputs,
        {'case_id': config['id'], 'revision': config['revision'], 'upstream_revision': revision},
        lambda out, execute: measure(config, speech, song, timing.read(prior / 'summary.json'), transcripts, out, execute),
        command=None, input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
