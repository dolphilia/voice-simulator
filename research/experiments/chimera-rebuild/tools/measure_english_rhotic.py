"""英語 /ɹ/ の時間配分、調音、通常の合成経路を固定上流と照合する。"""

import argparse
import csv
import os
from pathlib import Path
import subprocess

import numpy as np
from scipy.io import wavfile

import measure_alveolar_stop as cells
import measure_bilabial_stop as voice
import measure_labial_velar as articulation
import measure_postalveolar_affricate as traces
import measure_sibilant as frication
import measure_speech_timing as timing
import measure_uniform_tube as shared
from measure_wasm_fixed import compare_pcm
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/english-rhotic.json'
CENTER_FIELDS = ('tongue_tip_x_cm', 'tongue_tip_y_cm', 'tongue_tip_curl', 'tongue_body_x_cm',
                 'tongue_body_y_cm', 'lip_protrusion_cm', 'lip_spread', 'glottal_voicing')


def check_timing(config, folder, execute):
    folder.mkdir()
    examples = [{'id': name, 'segments': segments} for name, segments in config['timing'].items()]
    case_path = folder / 'timing.json'
    timing.write(case_path, {**config, 'speech_timing': {'inputs': examples}})
    candidate = folder / 'candidate.json'
    upstream = folder / 'upstream.json'
    execute([*timing.CLI, 'render', str(case_path), str(candidate)])
    probe = shared.build_upstream_probe(timing.PROBE, folder, execute, extra_libraries=('serde_json',))
    execute([str(probe), str(case_path)], cwd=UPSTREAM, stdout=upstream)
    actual, reference = timing.read(candidate)['entries'], timing.read(upstream)['entries']
    limits = config['measurement']
    tol = limits['gesture_abs_tolerance']
    mismatch, error = timing.compare([timing.upper_view(row) for row in actual], reference, tol)
    durations = {row['id']: row['utterances'][0]['durations_seconds'] for row in actual}
    coda, lateral, linked, onset, onset_l, explicit = (durations[name] for name in
        ('coda-r', 'coda-l', 'linked-r', 'onset-r', 'onset-l', 'explicit-r'))
    same = lambda x, y: abs(x - y) <= tol
    # 句末の共鳴音、語頭以外、隣接する /k/ の3係数は両子音で共通。
    factor = 1.4 * 0.85 * 0.7
    predicted = [(minimum + (80.0 - minimum) * factor) / 1000 for minimum in (30.0, 40.0)]
    checks = {
        'klatt_upstream': mismatch is None,
        'coda_shares_nucleus': same(coda[1] + coda[2], lateral[1]),
        'separate_consonant_minima': same(coda[2], predicted[0]) and same(lateral[2], predicted[1]),
        'word_boundary_keeps_coda': sum(linked[1:3]) < limits['coda_linked_to_onset_max_ratio'] * sum(onset[1:3]),
        'same_word_onset_keeps_vowel': same(onset[1], onset_l[1]),
        'explicit_duration_unchanged': explicit[1:3] == [0.12, 0.09],
    }
    return checks, {'first_upstream_difference': mismatch, 'maximum_checked_error': error,
                    'durations_seconds': durations, 'predicted_coda_r_and_l_seconds': predicted}


def expected_gestures(spans, variant):
    symbol = variant.get('symbol', 'ɹ')
    rate = max(variant.get('rate', 1), 1)
    primary = (dict(tongue_tip_x_cm=5.35, tongue_tip_y_cm=9.35, tip_curl=0.85, lip_protrusion_cm=0.5,
                    lip_spread=0.3, tongue_root_cm=-0.6) if symbol == 'ɹ'
               else dict(tongue_tip_x_cm=5.4, tongue_tip_y_cm=9.55, tip_curl=1.0))
    expected = []
    for part in spans:
        a, b = part['t0'], part['t1']
        expected.append({'label': symbol, 't0': a - .008, 't1': max(a + .01, b), 'rampIn': .03 / rate,
                         'rampOut': .018 / rate, 'releaseHold': .045 / rate, 'strength': 40.0, 'speed': 1.3,
                         'targets': primary})
        if symbol == 'ɹ':
            expected.append({'label': symbol, 't0': a, 't1': b, 'rampIn': .05 / rate, 'rampOut': .05 / rate,
                             'strength': 2.2, 'targets': dict(tongue_body_x_cm=2.3, tongue_body_y_cm=7.1)})
        if variant.get('palatalized'):
            expected.append({'label': 'palatalized', 't0': a, 't1': b, 'rampIn': .04 / rate, 'rampOut': .04 / rate,
                             'strength': 3.0, 'targets': dict(tongue_body_x_cm=3.8, tongue_body_y_cm=7.95)})
    return expected


def check_plan(settings, reference, variant, limits):
    if 'song' in settings:
        speech = {'utterances': [{'segments': row['timing']['segments']}
                                 for row in settings['song']['plan']['phrases']]}
    elif 'phrases' in settings['speech']:
        speech = {'utterances': [{'segments': row['timing']['segments']} for row in settings['speech']['phrases']]}
    else:
        speech = settings['speech']
    tol = limits['gesture_abs_tolerance']
    parts, report = frication.compare_plans({**settings, 'speech': speech}, reference, tol)
    symbol = variant.get('symbol', 'ɹ')
    spans = [part for part in parts if part['ipa'] == symbol]
    labels = {symbol, 'palatalized'} if variant.get('palatalized') else {symbol}
    observed = [gesture for gesture in settings['gestures'] if gesture['label'] in labels]
    first, error = timing.compare(observed, expected_gestures(spans, variant), tol)
    checks = {'upstream_plan': report['passed'], 'independent_rhotic_gestures': bool(spans) and first is None}
    report.update(spans=spans, first_registered_difference=first, maximum_registered_error=error)
    if variant.get('final'):
        exhale = next(gesture for gesture in settings['gestures'] if gesture['label'] == 'exhale')
        delay = exhale['t0'] - spans[-1]['t1']
        checks['sonorant_exhale_delay'] = abs(delay - .045) <= tol
        report['exhale_delay_seconds'] = delay
    if stop := variant.get('closure'):
        a, b = next((part['t0'], part['t1']) for part in parts if part['ipa'] == stop)
        delay = min(.025, max(0., b - a - .03))
        axis, lead, release = ('tongue_tip_y_cm', .031, .02) if stop == 't' else ('tongue_body_y_cm', .024, .034)
        gesture = next(g for g in settings['gestures'] if g['label'] == stop and axis in g['targets'])
        predicted = [a + delay - lead, max(a + delay + .01, b - release)]
        checked = [gesture['t0'], gesture['t1']]
        checks['prepositioned_closure'] = all(abs(l - r) <= tol for l, r in zip(checked, predicted, strict=True))
        report['closure'] = {'delay_seconds': delay, 'predicted': predicted, 'observed': checked}
    if 'song' in settings:
        notes = settings['song']['plan']['notes']
        checks['sung_onset_and_coda'] = (len(spans) == len(notes) == 2
            and abs(spans[0]['t1'] - notes[0]['nucleus_start_seconds']) <= tol
            and abs(spans[1]['t0'] - notes[1]['nucleus_end_seconds']) <= tol)
        report['note_nuclei'] = [[note['nucleus_start_seconds'], note['nucleus_end_seconds']] for note in notes]
    return checks, report


def observe(track, spans, limits):
    time = (track['frame'] + 1) / limits['output_rate_hz']
    observations = []
    for span in spans:
        a, b = span['t0'], span['t1']
        lo, hi = (a + f * (b - a) for f in limits['center_fraction'])
        mask = (time >= lo) & (time < hi)
        rows = track[mask]
        fields = [*CENTER_FIELDS, 'tongue_root_cm'] if 'tongue_root_cm' in rows.dtype.names else CENTER_FIELDS
        median = {key: float(np.median(rows[key])) for key in fields}
        minimum = {name: float(np.min(rows[f'{name}_minimum_cm2'])) for name in ('lip', 'oral', 'pharynx')}
        observations.append({'median': median, 'minimum_area_cm2': minimum,
                             'open_and_voiced': min(minimum.values()) > limits['closed_area_cm2']
                             and median['glottal_voicing'] >= limits['minimum_center_voicing']})
    return observations


def compare_variant(config, variant, source, folder, probe, execute):
    limits = config['measurement']
    folder.mkdir()
    key = 'song_voice' if 'score' in source else 'speech_voice'
    path = folder / 'case.json'
    timing.write(path, {'id': variant['id'], 'upstream_revision': config['upstream_revision'], key: source})
    settings, trace, files, upper_trace, upper_raw, upper_plan = voice.capture(
        path, limits['host_block_frames'], folder, execute, (), probe=probe)
    reference = timing.read(upper_plan)
    checks, plan = check_plan(settings, reference, variant, limits)
    n = settings['output_frames']
    native, upper = [traces.load_trace(p, n) for p in (trace, upper_trace)]
    fields = [field for field in native.dtype.names if field != 'oral_minimum_cell']
    mismatch, errors = frication.source_comparison(native[fields], upper[fields], limits)
    minima = cells.compare_cell_minima(native, upper, {**limits,
                                                      'geometry_absolute_tolerance': limits['geometry_abs_tolerance']})
    rate, pcm = wavfile.read(files[0][0])
    reference_pcm = np.fromfile(upper_raw, dtype='<f4')
    if any(wave.dtype != np.float32 or wave.shape != (n,) or not np.isfinite(wave).all() for wave in (pcm, reference_pcm)):
        raise ValueError('PCMのフレーム数、形式または有限性が登録条件外です')
    pcm_report = compare_pcm(pcm, reference_pcm, limits['pcm_abs_tolerance'])
    centers = [observe(track, plan['spans'], limits) for track in (native, upper)]
    axes = {'tip_curl': source['posture']['tip_curl']}
    if 'tongue_root_cm' in fields:
        axes['tongue_root_cm'] = source['posture']['tongue_root_cm']
    springs = []
    first_numeric_difference = {}
    for field in ('tongue_tip_curl', 'tongue_root_cm', 'oral_minimum_cm2', 'radiation_derivative_cm3_s2'):
        if field in fields:
            hits = np.flatnonzero(native[field] != upper[field])
            first_numeric_difference[field] = None if not hits.size else {
                'frame': int(hits[0]), 'signed_difference': float(native[field][hits[0]] - upper[field][hits[0]]),
            }
    for track in (native, upper):
        view = {'tip_curl': track['tongue_tip_curl']}
        if 'tongue_root_cm' in axes:
            view['tongue_root_cm'] = track['tongue_root_cm']
        springs.append(articulation.articulator_spring(
            view_as_trace(view, n), settings, axes, rate, limits['spring_frequency_hz'], limits['spring_abs_tolerance']))
    checks.update(physical_trace=not mismatch and minima['passed'],
                  pcm=pcm_report['first_frame_over_tolerance'] is None,
                  sample_rates_and_frames=(rate == limits['output_rate_hz'] and n == reference['output_frames']
                                           and source['internal_sample_rate_hz'] == limits['internal_rate_hz']),
                  host_partition=all(sha256(wav) == sha256(files[0][0]) and sha256(track) == sha256(files[0][1])
                                     for wav, track in files),
                  independent_tip_and_root_springs=all(result['passed'] for result in springs))
    if variant.get('check_center'):
        checks['open_and_voiced_center'] = all(all(row['open_and_voiced'] for row in side) for side in centers)
    return checks, {'plan': plan, 'center': centers, 'spring': springs, 'pcm': pcm_report, 'output_frames': n,
                    'first_trace_differences': mismatch, 'first_numeric_difference': first_numeric_difference,
                    'trace_errors': errors, 'oral_minimum_cells': minima}


def view_as_trace(view, frames):
    data = np.empty(frames, dtype=[(name, 'f8') for name in view])
    for key, values in view.items():
        data[key] = values
    return data


def choose_inputs(config, speech, song, transcript_path):
    for row in config['speech']:
        yield row, {**speech, 'body': row['body'], 'input': {k: row[k] for k in ('text', 'rate', 'id')},
                    'voice': {**speech['voice'], 'f0_hz': row['f0_hz']}}
    row = config['song']
    score = {name: row[name] for name in ('id', 'lyrics', 'bpm', 'start_seconds', 'notes')}
    yield row, {**song, 'body': row['body'], 'score': score}
    ids = config['english']['newly_renderable_ids']
    with transcript_path.open(newline='') as file:
        lines = {rid: (speaker, text) for rid, speaker, text in csv.reader(file, delimiter='\t') if rid in ids}
    for rid in ids:
        speaker, text = lines[rid]
        female = speaker.startswith('F')
        yield {'id': rid}, {**speech, 'language': 'english', 'body': 'female' if female else 'male',
                            'input': {'text': text, 'id': rid, 'rate': 1},
                            'voice': {**speech['voice'], 'f0_hz': 205 if female else 112}}


def measure(config, speech, song, transcript_path, artifacts, execute):
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera', '--test', 'nasal_spans', '--test', 'sing_fast',
             '--test', 'sound_marks'], cwd=UPSTREAM, stdout=artifacts / 'upstream-tests.log')
    probe = shared.build_upstream_probe(voice.PROBE, artifacts, execute, extra_libraries=('serde_json',))
    checks, duration = check_timing(config, artifacts / 'timing', execute)
    contexts = {}
    for variant, source in choose_inputs(config, speech, song, transcript_path):
        name = variant['id']
        flags, contexts[name] = compare_variant(config, variant, source, artifacts / name, probe, execute)
        checks.update({f'{name}:{check}': value for check, value in flags.items()})
    english, retroflex = [contexts[name]['center'][0][0]['median'] for name in ('between-vowels', 'retroflex-control')]
    checks['rhotic_posture_differs_from_retroflex'] = (english['tongue_root_cm'] < 0
        and english['lip_protrusion_cm'] > retroflex['lip_protrusion_cm']
        and english['lip_spread'] < retroflex['lip_spread'])
    return {'checks': checks, 'durations': duration, 'contexts': contexts}


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
    transcript_path = UPSTREAM / config['english']['transcripts']
    prior = WORKSPACE / 'runs' / config['english']['prior_support_run']
    modules = (cells, voice, articulation, traces, frication, timing)
    inputs = [CASE, speech_path, song_path, transcript_path, prior / 'summary.json', prior / 'manifest.json',
              Path(__file__).resolve(), voice.PROBE, timing.PROBE, *(Path(m.__file__) for m in modules),
              *shared.candidate_sources()]
    speech = timing.read(speech_path)['speech_voice']
    speech.pop('turbulence', None)
    song = timing.read(song_path)['song_voice']
    return shared.record_measurement(args.run_id, CASE, inputs,
        {'case_id': config['id'], 'revision': config['revision'], 'upstream_revision': revision, 'invoked_from': str(Path.cwd())},
        lambda out, execute: measure(config, speech, song, transcript_path, out, execute),
        command=None, input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
