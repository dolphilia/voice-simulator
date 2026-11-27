"""舌背の渡り音の調音、短時間スペクトル、韓国語歌唱を固定上流と照合する。"""

import argparse
from pathlib import Path
import re
import shutil
import subprocess

import numpy as np
from scipy.io import wavfile

import measure_alveolar_stop as cells
import measure_bilabial_stop as voice
import measure_labial_velar as analysis
import measure_sibilant as speech
import measure_speech_timing as timing
import measure_uniform_tube as shared
import measure_velar_stops as velar
import measure_wasm_fixed as wasm
from measure_worklet_fixed import ROOT, web_sources
from upstream_baseline import UPSTREAM, WORKSPACE, sha256

CASE = WORKSPACE / 'cases/tongue-glides.json'
TONGUE_AXES = ('tongue_body_x_cm', 'tongue_body_y_cm')


def compare_plan(settings, baseline, variant, score, tol):
    song = settings.get('song')
    source = settings
    if song is not None:
        source = {**settings, 'speech': {'utterances': [
            {'segments': p['timing']['segments']} for p in song['plan']['phrases']]}}
    parts, evidence = speech.compare_plans(source, baseline, tol)
    ipa = variant['ipa']
    selected = [part for part in parts if part['ipa'] == ipa]
    if len(selected) != 1:
        raise ValueError(f'対象音素 /{ipa}/ の区間を一件取得できません')
    interval = selected[0]
    a, b = (interval[k] for k in ('t0', 't1'))
    rate = max(1.0, variant.get('rate', 1.0))
    axes = (3.8, 7.95) if ipa == 'j' else (2.35, 7.45)
    planned = [{'label': ipa, 't0': a - .008, 't1': max(a + .01, b), 'rampIn': .03 / rate,
                'rampOut': .03 / rate, 'releaseHold': .045 / rate, 'speed': 1.105,
                'strength': 40, 'targets': dict(zip(TONGUE_AXES, axes, strict=True))}]
    if ipa == 'j':
        planned.append({'label': ipa, 't0': a, 't1': b, 'rampIn': .05 / rate, 'rampOut': .05 / rate,
                        'strength': 2.2, 'targets': {'jaw_cm': .25}})
    gestures = [g for g in settings['gestures'] if g['label'] == ipa]
    difference, num = timing.compare(gestures, planned, tol)
    flags = {'upstream_plan': evidence['passed'], 'independent_gestures': difference is None}
    summary = {'upstream': evidence, 'first_registered_difference': difference, 'numeric_error': num,
               'segment': interval, 'gestures': gestures}
    if song is not None:
        syl = song['syllables']
        actual = {'onsets': [[p['ipa'] for p in s['onset']] for s in syl],
                  'nuclei': [s['nucleus']['ipa'] for s in syl],
                  'codas': [[p['ipa'] for p in s['coda']] for s in syl],
                  'melisma': [s.get('melisma', False) for s in syl]}
        flags['registered_syllables'] = actual == {k: variant[k] for k in actual}
        index = variant['note_index']
        beats = [score['start_seconds'] + i * 60 / score['bpm'] for i in range(len(score['notes']))]
        notes = song['plan']['notes']
        actual_notes = [[n['beat_seconds'], n['nucleus_start_seconds']] for n in notes]
        expected_notes = [[t, t] for t in beats]
        beat_diff, _ = timing.compare(actual_notes, expected_notes, tol)
        hz = 440 * 2 ** ((variant['midi'][index] - 69) / 12)
        pitch = [g['targets']['f0_hz'] for g in settings['gestures'] if g['label'] == 'pitch'
                 and abs(g['t0'] - a) <= tol and abs(g['t1'] - b) <= tol]
        flags['glide_ends_at_beat'] = (beat_diff is None and abs(b - beats[index]) <= tol
            and abs(b - a - .8 * (.055 if ipa == 'j' else .06)) <= tol)
        flags['glide_at_note_pitch'] = len(pitch) == 1 and abs(pitch[0] - hz) <= tol
        summary.update(syllables=actual, beat_and_nucleus_seconds=actual_notes, pitch_hz=pitch)
    return flags, summary


def observe(trace, segment, rate, limits):
    time = (trace['frame'] + 1) / rate
    a, b = segment['t0'], segment['t1']
    left, right = (a + p * (b - a) for p in limits['center_fraction'])
    selected = (time >= left) & (time < right)
    if not selected.any():
        raise ValueError('渡り音の中央の観測区間が空です')
    values = {key: float(np.median(trace[key][selected]))
              for key in (*TONGUE_AXES, 'jaw_cm', 'glottal_voicing')}
    values['minimum_area_cm2'] = {key: float(trace[key][selected].min()) for key in
                                  ('oral_minimum_cm2', 'pharynx_minimum_cm2', 'lip_minimum_cm2')}
    return values


def sample_spectrum(pcm, upper, segment, rate, limits):
    samples = [analysis.spectrum(wave, segment, rate, limits) for wave in (pcm, upper)]
    poles = [entry['poles_hz'] for entry in samples]
    second = [row[1][0] if len(row) > 1 else None for row in poles]
    difference = abs(second[0] - second[1]) if all(f is not None for f in second) else None
    return {'candidate_and_upstream': samples, 'second_pole_hz': second, 'frequency_error_hz': difference,
            'passed': difference is not None and difference <= limits['formant_match_hz']}


def compare_variant(config, source, variant, is_song, out, probe, execute):
    out.mkdir()
    limits = config['measurement']
    key = 'song_voice' if is_song else 'speech_voice'
    input = {**timing.read(source)[key], 'body': variant['body']}
    if is_song:
        score = {**input['score'], 'id': variant['id'], 'lyrics': variant['lyrics'],
                 'notes': [{'midi': midi, 'beats': 1} for midi in variant['midi']]}
        input['score'] = score
    else:
        score = None
        input['input'] = {key: variant[key] for key in ('id', 'text', 'rate')}
    path = out / 'case.json'
    timing.write(path, {'id': variant['id'], 'upstream_revision': config['upstream_revision'], key: input})
    settings, trace, files, upper_trace, upper_raw, upper_plan = voice.capture(
        path, limits['host_block_frames'], out, execute, (), probe=probe)
    baseline = timing.read(upper_plan)
    flags, plan = compare_plan(settings, baseline, variant, score, limits['gesture_absolute_tolerance'])
    count = settings['output_frames']
    native, reference = [voice.load_trace(p, count) for p in (trace, upper_trace)]
    fields = [name for name in native.dtype.names if name != 'oral_minimum_cell']
    first, errors = voice.compare_traces(native[fields], reference[fields], limits)
    cell_diff = cells.compare_cell_minima(native, reference, limits)
    rate, pcm = wavfile.read(files[0][0])
    upper = np.fromfile(upper_raw, dtype='<f4')
    if any(x.shape != (count,) or x.dtype != np.float32 or not np.isfinite(x).all() for x in (pcm, upper)):
        raise ValueError('PCM長、型、有限性を確認できません')
    pcm_diff = wasm.compare_pcm(pcm, upper, limits['pcm_absolute_tolerance'])
    jaw = analysis.articulator_spring(native, settings, {'jaw_cm': input['posture']['jaw_cm']}, rate, 10,
                                     limits['independent_jaw_tolerance_cm'])
    observed = [observe(t, plan['segment'], rate, limits) for t in (native, reference)]
    flags.update({
        'trace_and_cells': first is None and cell_diff['passed'],
        'independent_jaw': jaw['passed'],
        'pcm_and_rate': pcm_diff['first_frame_over_tolerance'] is None
            and rate == limits['output_rate_hz'] and count == baseline['output_frames'],
        'same_host_blocks': all(sha256(w) == sha256(files[0][0]) and sha256(t) == sha256(files[0][1])
                                for w, t in files),
    })
    if not is_song:
        flags['remains_open'] = all(min(x['minimum_area_cm2'].values()) > limits['closed_area_cm2'] for x in observed)
    result = {'plan': plan, 'first_trace_over_tolerance': first, 'trace_errors': errors, 'cells': cell_diff,
              'independent_jaw': jaw, 'center_observations': observed, 'pcm': pcm_diff}
    if variant['id'] in ('palatal', 'velar'):
        result['spectrum'] = sample_spectrum(pcm, upper, plan['segment'], rate, limits)
        flags['same_second_pole'] = result['spectrum']['passed']
    return flags, result, (input, settings, native, reference, pcm) if is_song else None


def measure(config, inputs, artifacts, execute, bun, browser):
    execute(['cargo', 'test', '--locked', '-p', 'chimera', '--test', 'rising', '--test', 'syllables'],
            cwd=UPSTREAM, stdout=artifacts / 'upstream-tests.log')
    probe = shared.build_upstream_probe(voice.PROBE, artifacts, execute, extra_libraries=('serde_json',))
    checks, variants, rendered = {}, {}, {}
    for kind in ('speech', 'song'):
        for variant in config[kind]:
            label = variant['id']
            flags, variants[label], replay = compare_variant(config, inputs[kind], variant, kind == 'song',
                                                             artifacts / label, probe, execute)
            checks.update({f'{label}/{key}': bool(value) for key, value in flags.items()})
            if replay is not None:
                rendered[label] = replay
    limits = config['measurement']
    palatal, dorsal = (variants[k] for k in ('palatal', 'velar'))
    x_delta = palatal['center_observations'][0]['tongue_body_x_cm'] - dorsal['center_observations'][0]['tongue_body_x_cm']
    f2_delta = [j - g if j is not None and g is not None else None
                for j, g in zip(palatal['spectrum']['second_pole_hz'], dorsal['spectrum']['second_pole_hz'], strict=True)]
    checks['palatal_tongue_more_forward'] = x_delta >= limits['minimum_front_back_difference_cm']
    checks['palatal_second_pole_higher'] = all(f is not None and f >= limits['minimum_f2_difference_hz'] for f in f2_delta)
    report = {'checks': checks, 'variants': variants, 'tongue_x_difference_cm': x_delta,
              'palatal_minus_velar_second_pole_hz': f2_delta}
    if browser:
        flags, reports = velar.browser_measure(config, rendered, artifacts, execute, bun, case_path=CASE)
        checks.update(flags)
        report['browser'] = reports
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('--native-only', action='store_true', help='CLIと固定上流だけを計測する')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', args.run_id):
        parser.error('実行IDは英数字で始めてください')
    config = timing.read(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != config['upstream_revision'] or subprocess.check_output(
            ['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True):
        raise SystemExit('変更のない固定上流版が必要です')
    paths = {kind: WORKSPACE / 'cases' / config[kind + '_case'] for kind in ('speech', 'song')}
    modules = (analysis, cells, voice, speech, timing, shared, velar, wasm)
    sources = [CASE, *paths.values(), voice.PROBE, Path(__file__).resolve(), *shared.candidate_sources(),
               *(Path(m.__file__) for m in modules), WORKSPACE / 'tools/upstream_baseline.py',
               WORKSPACE / 'tools/measure_vowel_voice.py', WORKSPACE / 'tools/measure_song_plan.py']
    upper = ('src/phonetics/inventory.rs', 'src/phonetics/planner.rs', 'src/phonetics/korean.rs',
             'src/phonetics/sing.rs', 'src/phonetics/consonantTargets.generated.json',
             'src/control/articulators.rs', 'tests/rising.rs', 'tests/syllables.rs')
    meta = {'case_id': config['id'], 'revision': config['revision'], 'upstream_revision': revision,
            'upper_source_sha256': {p: sha256(UPSTREAM / 'crates/chimera' / p) for p in upper}}
    bun = ['bun'] if shutil.which('bun') else ['npx', '--yes', '--package=bun@1.4.4', '--', 'bun']
    if args.native_only:
        sources += [WORKSPACE / 'data/cmudict.txt.gz', WORKSPACE / 'data/CMUDICT-LICENSE.txt']
    else:
        sources += [velar.KOREAN, *web_sources(), WORKSPACE / 'tools/measure_worklet_english_body.py']
        meta.update(node=subprocess.check_output(['node', '--version'], text=True).strip(),
                    bun=subprocess.check_output([*bun, '--version'], text=True).strip())
    return shared.record_measurement(args.run_id, CASE, sources, meta,
        lambda out, run: measure(config, paths, out, run, bun, not args.native_only), command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
