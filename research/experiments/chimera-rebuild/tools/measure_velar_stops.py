"""舌背閉鎖の計画、断面、波形、韓国語の音符への割り当てを照合する。"""

import argparse
from pathlib import Path
import re
import shutil
import subprocess

import numpy as np
from scipy.io import wavfile

import measure_alveolar_stop as alveolar
import measure_bilabial_stop as voice
import measure_sibilant as speech
import measure_song_plan as song
import measure_speech_timing as timing
import measure_uniform_tube as shared
import measure_wasm_fixed as wasm
from measure_worklet_english_body import compare_observations
from measure_worklet_fixed import CAPTURE, ROOT, WEB, web_sources
from upstream_baseline import UPSTREAM, WORKSPACE, sha256

CASE = WORKSPACE / 'cases/velar-stops.json'
KOREAN = WORKSPACE / 'cases/korean-lyrics.json'
LIVE = WORKSPACE / 'cases/worklet-live-song.json'


def compare_plan(settings, reference, variant, limits):
    is_song = 'song' in settings
    if is_song:
        plan = settings['song']['plan']
        settings = {**settings, 'speech': {'utterances': [
            {'segments': phrase['timing']['segments']} for phrase in plan['phrases']]}}
    tolerance = limits['gesture_absolute_tolerance']
    parts, upstream = speech.compare_plans(settings, reference, tolerance)
    stops = [part for part in parts if part['ipa'] == variant['stop']]
    gestures = settings['gestures']
    actual = [g for g in gestures if g['label'] in (variant['stop'], 'aspiration', 'palatalized')]
    rate = max(1, variant.get('rate', 1))
    expected = []
    for part in stops:
        start, end = part['t0'], part['t1']
        duration = end - start
        aim = start + min(variant['aim_delay_seconds'], max(0, duration - 0.03))

        def gesture(label, a, b, rise, fall, strength, key, value, **extra):
            return {'label': label, 't0': a, 't1': b, 'rampIn': rise / rate, 'rampOut': fall / rate,
                    'strength': strength, 'targets': {key: value}, **extra}

        ipa = variant['stop']
        expected.extend([
            gesture(ipa, aim - 0.024, max(aim + 0.01, end - 0.034), .03, .03, 40, 'tongue_body_y_cm',
                    8.35, speed=1.1925, releaseHold=.045 / rate),
            gesture(ipa, aim, end, .05, .05, 2.2, 'jaw_cm', .7),
            gesture(ipa, aim, end, .05, .05, .25, 'tongue_body_x_cm', 2.3),
        ])
        voiced_again = end
        if variant['aspiration'] is not None:
            opening, past, release = variant['aspiration']
            # 既定の帯気の保持は話速で縮む。無帯気の保持は一定。
            past = past / rate if opening == .36 else past
            expected.append(gesture('aspiration', start + duration * .25, end + past, .035, release,
                                    6, 'abduction_cm2', opening))
            voiced_again = end + past + release
        if variant.get('palatalized'):
            expected.append(gesture('palatalized', start, voiced_again, .04, .04, 3, 'tongue_body_x_cm', 3.8))
    difference, numeric = timing.compare(actual, expected, tolerance)
    checks = {'fixed_upstream_plan': upstream['passed'], 'registered_gestures': bool(stops) and difference is None}
    result = {'upstream': upstream, 'first_registered_difference': difference, 'registered_numeric_error': numeric,
              'stops': stops, 'gestures': actual}
    if is_song:
        syllables = settings['song']['syllables']
        labels = {key: [s[key] if key == 'wordEnd' else [p['ipa'] for p in s[key]] for s in syllables]
                  for key in ('wordEnd', 'onset', 'coda')}
        first, _ = timing.compare(labels, {'wordEnd': variant['word_end'], 'onset': variant['onsets'],
                                          'coda': variant['codas']}, 0)
        pitches = [g['targets']['f0_hz'] for g in gestures
                   if g['label'] == 'pitch' and any(abs(g['t0'] - s['t0']) <= tolerance
                                                   and abs(g['t1'] - s['t1']) <= tolerance for s in stops)]
        note = variant['stop_note_index']
        midi = settings['case']['song_voice']['score']['notes'][note]['midi']
        hz = 440 * 2 ** ((midi - 69) / 12)
        checks['word_boundary_and_note_pitch'] = first is None and len(pitches) == 1 and abs(pitches[0] - hz) <= tolerance
        result['syllables'] = labels
        result['stop_note_index_and_f0_hz'] = [note, pitches]
    return checks, result, parts


def events(parts, stops, trace, pcm, limits):
    if not stops:
        return {'stops': [], 'intervening_vowel_peaks_cm2': [], 'passed': False}
    rate = limits['rate_hz']
    time = (trace['frame'] + 1) / rate
    area = np.minimum(trace['oral_minimum_cm2'], trace['pharynx_minimum_cm2'])
    lip = trace['lip_minimum_cm2']
    padding = limits['closure_window_padding_seconds']
    centers = [(p['t0'] + p['t1']) * .5 for p in stops]
    hits = []
    for n, p in enumerate(stops):
        left, right = p['t0'] - padding, p['t1'] + padding
        if n:
            left = max(left, (centers[n - 1] + centers[n]) * .5)
        if n + 1 < len(stops):
            right = min(right, (centers[n] + centers[n + 1]) * .5)
        eligible = np.flatnonzero((time >= left) & (time < right) & (area < limits['closed_area_cm2'])
                                  & (lip >= limits['open_lip_minimum_cm2']))
        if not eligible.size:
            window = area[(time >= left) & (time < right)]
            hits.append({'closed_frames': 0, 'minimum_cm2': float(window.min()), 'passed': False})
            continue
        runs = np.split(eligible, np.flatnonzero(np.diff(eligible) != 1) + 1)
        sealed = max(runs, key=len)
        first, opened = int(sealed[0]), int(sealed[-1]) + 1
        middle = (first + opened) // 2
        size = round(rate * limits['release_peak_window_seconds'])
        burst = pcm[opened:opened + round(rate * .005)]
        peak = float(abs(pcm[opened:opened + size]).max(initial=0))
        hits.append({'first_closed_frame': first, 'first_open_frame': opened, 'closed_frames': len(sealed),
                     'closure_offset_ms': (time[first] - p['t0']) * 1000,
                     'opening_offset_ms': ((opened + 1) / rate - p['t1']) * 1000,
                     'peak_frame_first_5_ms': opened + int(np.argmax(abs(burst))) if burst.size else None,
                     'center_oral_cm2': float(trace['oral_minimum_cm2'][middle]),
                     'center_pharynx_cm2': float(trace['pharynx_minimum_cm2'][middle]),
                     'center_lip_cm2': float(lip[middle]), 'center_tongue_body_x_cm': float(trace['tongue_body_x_cm'][middle]),
                     'release_pcm_peak': peak,
                     'passed': opened < len(area) and area[opened] >= limits['closed_area_cm2']
                     and len(sealed) >= limits['minimum_closed_frames'] and peak >= limits['minimum_release_peak']})
        hits[-1]['passed'] = bool(hits[-1]['passed'])
    between = [part for part in parts if part['kind'] == 'vowel'
               and stops[0]['t1'] <= part['t0'] and part['t1'] <= stops[-1]['t0']]
    vowel_areas = [float(area[(time >= p['t0']) & (time < p['t1'])].max()) for p in between]
    return {'stops': hits, 'intervening_vowel_peaks_cm2': vowel_areas,
            'passed': bool(hits) and all(item['passed'] for item in hits)}


def compare_variant(config, variant, out, paths, probe, execute, is_song):
    out.mkdir()
    limits = config['measurement']
    key = 'song_voice' if is_song else 'speech_voice'
    source = timing.read(paths[key])[key]
    if is_song:
        score = {**source['score'], 'id': variant['id'], 'lyrics': variant['lyrics'], 'notes': config['notes']}
        source = {**source, 'body': 'male', 'score': score}
    else:
        source = {**source, 'input': {k: variant[k] for k in ('id', 'text', 'rate')}}
    case_path = out / 'case.json'
    timing.write(case_path, {'id': variant['id'], 'upstream_revision': config['upstream_revision'], key: source})
    settings, track, files, upper_track, upper_raw, discussion = voice.capture(
        case_path, limits['host_block_frames'], out, execute, (), probe=probe)
    reference = timing.read(discussion)
    plan_checks, plan, parts = compare_plan(settings, reference, variant, limits)
    frames = settings['output_frames']
    native, upper = [voice.load_trace(path, frames) for path in (track, upper_track)]
    fields = [name for name in native.dtype.names if name != 'oral_minimum_cell']
    first, errors = voice.compare_traces(native[fields], upper[fields], limits)
    cells = alveolar.compare_cell_minima(native, upper, limits)
    rate, pcm = wavfile.read(files[0][0])
    ref = np.fromfile(upper_raw, dtype='<f4')
    if any(x.shape != (frames,) or x.dtype != np.float32 or not np.isfinite(x).all() for x in (pcm, ref)):
        raise ValueError('PCMのフレーム数、型または有限性が一致しません')
    pcm_diff = wasm.compare_pcm(pcm, ref, limits['pcm_absolute_tolerance'])
    a, b = [events(parts, plan['stops'], t, p, limits) for t, p in ((native, pcm), (upper, ref))]
    checks = {**plan_checks, 'finite_frames_and_format': frames == reference['output_frames'] and rate == limits['rate_hz'],
              'geometry_and_acoustics': first is None and cells['passed'],
              'pcm_upper': pcm_diff['first_frame_over_tolerance'] is None,
              'physical_closure_and_release': a['passed'] and b['passed'],
              'same_event_frames': all(
                  all(x.get(k) == y.get(k) for k in ('first_closed_frame', 'first_open_frame', 'peak_frame_first_5_ms'))
                  for x, y in zip(a['stops'], b['stops'], strict=True)),
              'same_pcm_blocks': all(sha256(w) == sha256(files[0][0]) and sha256(t) == sha256(files[0][1])
                                     for w, t in files)}
    result = {'plan': plan, 'earliest_state_over_tolerance': first, 'states': errors, 'cell_selection': cells,
              'pcm': pcm_diff, 'candidate_events': a, 'upstream_events': b}
    if is_song:
        return checks, result, (source, settings, native, upper, pcm)
    return checks, result, None


def browser_measure(config, rendered, artifacts, execute, bun, *, case_path=CASE):
    execute([*bun, 'run', 'build'], cwd=WEB, stdout=artifacts / 'browser-build.log')
    wasm_path = artifacts / 'vocal_wasm.wasm'
    shutil.copyfile(WORKSPACE / wasm.WASM, wasm_path)
    sources = [{'id': name, 'score': {**values[0]['score'], 'vibrato_cents': values[0]['vibrato_cents']}}
               for name, values in rendered.items()]
    inputs = artifacts / 'browser-inputs.json'
    timing.write(inputs, {'scores': sources, 'live': timing.read(LIVE)['measurement']})
    browser = artifacts / 'browser'
    browser.mkdir()
    execute(['node', str(CAPTURE), str(browser), str(case_path), str(inputs)])
    detail = timing.read(browser / 'browser-run.json')
    common = timing.read(KOREAN)['measurement']
    limits = {**common, 'upper_state_peak_relative_tolerance': config['measurement']['audio_state_peak_relative_tolerance']}
    if 'browser_observed_fields' in config['measurement']:
        limits['observed_fields'] = config['measurement']['browser_observed_fields']
    checks, results = {}, {}
    for name, (source, settings, native, upper, pcm) in rendered.items():
        report = timing.read(browser / f'{name}.json')
        case = browser / f'{name}-case.json'
        saved = timing.read(case)['song_voice']
        rate, real = wavfile.read(browser / f'{name}.wav')
        if real.shape != pcm.shape or not np.isfinite(real).all():
            raise ValueError(f'{name} のWorklet出力長か有限性が不正です')
        _, flags, observations = compare_observations(report, native, upper, limits, len(pcm), live=True)
        candidate = wasm.compare_pcm(real, pcm, 0)
        wave = browser / f'{name}-replay.wav'
        execute([*song.CLI, 'render-pcm', str(case), str(wave),
                 str(wave.with_suffix('.csv')), str(common['expected_render_quantum_frames'])])
        replay_rate, replay = wavfile.read(wave)
        difference, _ = timing.compare(report['gestures'], settings['gestures'], limits['plan_absolute_tolerance'])
        flags.update({
            'pcm': candidate['first_bit_difference_frame'] is None,
            'same_script_and_replay_pcm': saved['score']['lyrics'] == source['score']['lyrics']
                and replay_rate == rate == source['voice']['output_sample_rate_hz']
                and np.array_equal(real.view(np.uint32), replay.view(np.uint32)),
            'plan_and_wasm': report['song']['syllables'] == settings['song']['syllables'] and difference is None
                and detail[name]['servedWasmSha256'] == sha256(wasm_path) and not detail[name]['errors'],
        })
        checks.update({f'{name}/browser/{flag}': bool(passed) for flag, passed in flags.items()})
        results[name] = {'observations': observations, 'first_gesture_difference': difference, 'pcm': candidate,
                         'browser': detail[name]}
    return checks, results


def measure(config, paths, artifacts, execute, bun, browser):
    execute(['cargo', 'test', '--locked', '-p', 'chimera', '--test', 'aspiration', '--test', 'fast_speech',
             '--test', 'syllables'], cwd=UPSTREAM, stdout=artifacts / 'upstream-tests.log')
    probe = shared.build_upstream_probe(voice.PROBE, artifacts, execute, extra_libraries=('serde_json',))
    checks, results, rendered = {}, {}, {}
    for kind in ('speech', 'song'):
        for variant in config[kind]:
            label = variant['id']
            local, results[label], audio = compare_variant(
                config, variant, artifacts / label, paths, probe, execute, kind == 'song')
            checks.update({f'{label}/{name}': bool(value) for name, value in local.items()})
            if audio is not None:
                rendered[label] = audio
    fast, slow = [results[label]['candidate_events']['intervening_vowel_peaks_cm2'] for label in ('fast', 'repeated')]
    ratio = [a / b for a, b in zip(fast, slow, strict=True)]
    checks['fast_vowels_open'] = len(ratio) == 2 and min(ratio) > config['measurement']['fast_to_slow_minimum_open_area_ratio']
    front, back = [results[name]['candidate_events']['stops'][0].get('center_tongue_body_x_cm')
                   for name in ('front-k', 'back-k')]
    position_delta = front - back if front is not None and back is not None else None
    checks['front_vowel_moves_closure_forward'] = (
        position_delta is not None and position_delta >= config['measurement']['minimum_front_back_difference_cm'])
    summary = {'checks': checks, 'variants': results, 'fast_slow_area_ratio': ratio, 'front_back_x_difference_cm': position_delta}
    if browser:
        flags, details = browser_measure(config, rendered, artifacts, execute, bun)
        checks.update(flags)
        summary['browser'] = details
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('--native-only', action='store_true', help='CLIと固定上流を計測する')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', args.run_id):
        parser.error('実行IDは英数字で始めてください')
    config = timing.read(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != config['upstream_revision'] or subprocess.check_output(
            ['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True):
        raise SystemExit('変更のない固定上流版が必要です')
    paths = {kind + '_voice': WORKSPACE / 'cases' / config[kind + '_case'] for kind in ('speech', 'song')}
    modules = (alveolar, voice, speech, song, timing, shared, wasm)
    inputs = [CASE, *paths.values(), voice.PROBE, Path(__file__).resolve(), *shared.candidate_sources(),
              *(Path(module.__file__) for module in modules), WORKSPACE / 'tools/upstream_baseline.py']
    sources = [f'src/phonetics/{name}.rs' for name in ('inventory', 'planner', 'sing', 'korean', 'syllables')]
    sources += ['src/phonetics/consonantTargets.generated.json', 'tests/aspiration.rs', 'tests/fast_speech.rs']
    meta = {'case_id': config['id'], 'case_revision': config['revision'], 'upstream_revision': revision,
            'upper_source_sha256': {p: sha256(UPSTREAM / 'crates/chimera' / p) for p in sources}}
    bun = ['bun'] if shutil.which('bun') else ['npx', '--yes', '--package=bun@1.4.4', '--', 'bun']
    if not args.native_only:
        inputs += [KOREAN, *web_sources(), WORKSPACE / 'tools/measure_worklet_english_body.py']
        meta.update(node=subprocess.check_output(['node', '--version'], text=True).strip(),
                    bun=subprocess.check_output([*bun, '--version'], text=True).strip())
    return shared.record_measurement(args.run_id, CASE, inputs, meta,
        lambda out, run: measure(config, paths, out, run, bun, not args.native_only), command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
