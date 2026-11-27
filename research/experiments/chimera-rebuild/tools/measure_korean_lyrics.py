"""韓国語歌詞の音節と両唇閉鎖音の歌唱を、上流・CLI・Workletで照合する。"""

import argparse
from pathlib import Path
import re
import shutil
import subprocess
import unicodedata

import numpy as np
from scipy.io import wavfile

import measure_bilabial_stop as speech
import measure_sibilant as sibilant
import measure_song_plan as song
import measure_speech_timing as timing
import measure_uniform_tube as shared
import measure_wasm_fixed as wasm
from measure_worklet_english_body import compare_observations
from measure_worklet_fixed import CAPTURE, ROOT, WEB, web_sources
from upstream_baseline import UPSTREAM, WORKSPACE, sha256

CASE = WORKSPACE / 'cases/korean-lyrics.json'
LIVE = WORKSPACE / 'cases/worklet-live-song.json'


def marked_ipa(syllables):
    def mark(segment):
        flag = segment.get('aspirated')
        tone = ''
        if flag is True:
            tone = 'ʰ' + (f"{segment['vot'] * 1000:.0f}" if 'vot' in segment else '')
        elif flag is False:
            tone = '˭'
        return segment['ipa'] + tone
    return '.'.join(''.join(map(mark, [*s['onset'], s['nucleus'], *s['coda']])) for s in syllables)


def compare_lyrics(case, artifacts, execute):
    entries = list(case['lyric_cases'])
    for entry in case['lyric_cases']:
        text = unicodedata.normalize('NFD', entry['text'])
        if text != entry['text'] and entry['id'] not in ('old-jamo', 'block-plus-final'):
            entries.append({'id': entry['id'] + '-nfd', 'text': text, 'canonical': entry['id']})
    request = artifacts / 'lyric-inputs.json'
    timing.write(request, {'song_plan': {'lyric_cases': [
        {field: entry[field] for field in ('id', 'text')} for entry in entries]}})
    candidate_path = artifacts / 'lyric-candidate.json'
    rendered = artifacts / 'lyric-render.json'
    execute([*song.CLI, 'inspect', str(request)], stdout=candidate_path)
    execute([*song.CLI, 'render', str(request), str(rendered)])
    candidate = {row['id']: row['syllables'] for row in timing.read(candidate_path)['lyric_cases']}
    execute(['cargo', 'build', '--locked', '--release', '-p', 'chimera-cli'], cwd=UPSTREAM)
    upper_directory = artifacts / 'lyric-upstream'
    upper_directory.mkdir()
    results = {}
    for entry in entries:
        name = entry['id']
        reference = upper_directory / f'{name}.json'
        execute([str(UPSTREAM / 'target/release/chimera'), 'syllables', entry['text']],
                cwd=UPSTREAM, stdout=reference)
        syllables = candidate[name]
        diff, _ = timing.compare(syllables, timing.read(reference), 0)
        actual_ipa = marked_ipa(syllables)
        labels = [[s[key] for key in ('text', 'wordEnd', 'phraseEnd')] for s in syllables]
        canonical = entry.get('canonical')
        results[name] = {
            'first_upstream_difference': diff, 'marked_ipa': actual_ipa, 'labels': labels,
            'matches_registered_ipa': actual_ipa == entry.get('marked_ipa', actual_ipa),
            'matches_registered_labels': labels == entry.get('labels', labels),
            'matches_canonical': canonical is None or syllables == candidate[canonical],
        }
    flags = {
        'lyrics_inspect_and_render': sha256(candidate_path) == sha256(rendered),
        'lyrics_match_upstream': all(item['first_upstream_difference'] is None for item in results.values()),
        'lyrics_match_registered_and_nfd': all(
            all(item[key] for key in ('matches_registered_ipa', 'matches_registered_labels', 'matches_canonical'))
            for item in results.values()),
    }
    return flags, results, candidate['sung']


def voice_case(case, source):
    return {**source, 'id': case['id'], 'hypothesis': case['hypothesis'],
            'song_voice': {**source['song_voice'], 'body': 'male', 'score': case['score']},
            'measurement': case['measurement']}


def compare_song(case, settings, upstream_plan, wave, plan_syllables):
    m = case['measurement']
    song_report = settings['song']
    score = song_report['plan']
    detail = {'utterances': [{'segments': p['timing']['segments']} for p in score['phrases']]}
    parts, plan = sibilant.compare_plans({**settings, 'speech': detail}, upstream_plan, m['plan_absolute_tolerance'])
    stops = [p for p in parts if p['ipa'] == 'p']
    pulses = [g for g in settings['gestures'] if g['label'] == 'aspiration']
    hold = [g['t1'] - p['t1'] for g, p in zip(pulses, stops, strict=True)]
    target = [g['targets']['abduction_cm2'] for g in pulses]
    ramp = [g['rampOut'] for g in pulses]
    aspiration, error = timing.compare(
        [hold, target, ramp], [m['upstream_head_aspiration_past_release_seconds'],
                               m['head_aspiration_abduction_cm2'], m['head_aspiration_ramp_out_seconds']],
        m['plan_absolute_tolerance'])
    divisor = 60 / case['score']['bpm']
    music = case['score']['notes']
    times = [case['score']['start_seconds'] + divisor * sum(n['beats'] for n in music[:i])
             for i in range(len(music))]
    expected = [[i, beat, beat, 440 * 2 ** ((n['midi'] - 69) / 12)]
                for i, (beat, n) in enumerate(zip(times, music, strict=True))]
    actual = [[n[k] for k in ('lyric_index', 'beat_seconds', 'nucleus_start_seconds', 'f0_hz')]
              for n in score['notes']]
    beats, _ = timing.compare(actual, expected, m['plan_absolute_tolerance'])
    centers = []
    rate = m['output_rate_hz']
    for part in (p for p in parts if p['ipa'] == 'u'):
        span = part['t1'] - part['t0']
        a, b = (round(rate * (part['t0'] + fraction * span)) for fraction in (.1, .9))
        centers.append(float(abs(wave[a:b]).max()))
    checks = {
        'upstream_song_plan': plan['passed'],
        'song_syllables_and_inventory': song_report['syllables'] == plan_syllables
            and not score['unavailable_speech_symbols'],
        'registered_aspiration': aspiration is None,
        'independent_beat_and_midi': beats is None,
        'vowels_sound': len(centers) == len(music) and min(centers) >= m['minimum_vowel_center_pcm_peak'],
    }
    return checks, {'plan': plan, 'segments': parts, 'beat_and_frequency': actual, 'first_beat_difference': beats,
                    'first_aspiration_difference': aspiration, 'maximum_aspiration_difference': error,
                    'hold_past_release_seconds': hold, 'abduction_cm2': target, 'ramp_out_seconds': ramp,
                    'vowel_pcm_peaks': centers}


def compare_browser(case, source, native, reference, settings, native_pcm, upper_pcm, artifacts, execute, bun):
    m = case['measurement']
    execute([*bun, 'run', 'build'], cwd=WEB, stdout=artifacts / 'browser-build.log')
    binary = artifacts / 'vocal_wasm.wasm'
    shutil.copyfile(WORKSPACE / wasm.WASM, binary)
    binary_hash = sha256(binary)
    score = {**case['score'], 'vibrato_cents': source['vibrato_cents']}
    jamo = {**score, 'lyrics': unicodedata.normalize('NFD', score['lyrics'])}
    variants = {'blocks-offline': score, 'jamo-offline': jamo, 'jamo-live': jamo}
    path = artifacts / 'browser-inputs.json'
    timing.write(path, {'scores': [{'id': name, 'score': score} for name, score in variants.items()],
                        'live': timing.read(LIVE)['measurement']})
    execute(['node', str(CAPTURE), str(artifacts), str(CASE), str(path)])
    sites = timing.read(artifacts / 'browser-run.json')
    limits = {**m, 'upper_state_peak_relative_tolerance': m['audio_state_peak_relative_tolerance']}
    checks, results = {}, {}
    frames = m['output_frames']
    for label, score in variants.items():
        live = label == 'jamo-live'
        report = timing.read(artifacts / f'{label}.json')
        saved_path = artifacts / f'{label}-case.json'
        saved = timing.read(saved_path)['song_voice']
        site = sites[label]
        rate, pcm = wavfile.read(artifacts / f'{label}.wav')
        if pcm.shape != (frames,) or pcm.dtype != np.float32 or not np.isfinite(pcm).all():
            raise ValueError(f'{label} のPCM長・型・観測値が登録条件と一致しません')
        _, flags, states = compare_observations(report, native, reference, limits, frames, live=live)
        candidate_diff = wasm.compare_pcm(pcm, native_pcm, 0)
        upper_diff = wasm.compare_pcm(pcm, upper_pcm, m['pcm_absolute_tolerance'])
        first_plan_diff, _ = timing.compare(report['song']['plan'], settings['song']['plan'],
                                            m['plan_absolute_tolerance'])
        first_gesture_diff, _ = timing.compare(report['gestures'], settings['gestures'],
                                               m['plan_absolute_tolerance'])
        quantum = m['expected_render_quantum_frames']
        config_match = all(saved.get(k) == source[k] for k in
                           ('body', 'posture', 'voice', 'internal_sample_rate_hz', 'vibrato_cents'))
        run_checks = {
            **flags,
            'case_keeps_input': config_match and all(saved['score'][k] == score[k] for k in
                                                     ('lyrics', 'notes', 'bpm', 'start_seconds')),
            'plan_and_gestures': report['song']['syllables'] == settings['song']['syllables']
                and first_plan_diff is None and first_gesture_diff is None,
            'wav_and_clock': rate == report['sampleRate'] == report['workletSampleRate'] == m['output_rate_hz']
                and report['framesRendered'] == frames and report['shortestQuantum'] == report['longestQuantum'] == quantum
                and report['discontinuities'] == 0,
            'same_wasm_and_no_errors': site['servedWasmSha256'] == binary_hash and not site['errors'],
            'pcm_cli_bit_exact': candidate_diff['first_bit_difference_frame'] is None,
            'pcm_upstream': upper_diff['first_frame_over_tolerance'] is None,
        }
        checks.update({f'{label}/{key}': bool(value) for key, value in run_checks.items()})
        results[label] = {'site': site, 'first_plan_difference': first_plan_diff,
                          'first_gesture_difference': first_gesture_diff, 'pcm_cli': candidate_diff,
                          'pcm_upstream': upper_diff, **states}
        if live:
            replay = artifacts / 'jamo-replay.wav'
            execute([*song.CLI, 'render-pcm', str(saved_path), str(replay),
                     str(artifacts / 'jamo-replay.csv'), str(quantum)])
            replay_rate, replay_pcm = wavfile.read(replay)
            checks['jamo-live/saved_case_replay'] = replay_rate == rate and np.array_equal(
                replay_pcm.view(np.uint32), pcm.view(np.uint32))
    return checks, results


def measure(case, source_path, artifacts, execute, bun, browser):
    lyric_flags, lyrics, syllables = compare_lyrics(case, artifacts, execute)
    config = voice_case(case, timing.read(source_path))
    case_path = artifacts / 'voice-input.json'
    timing.write(case_path, config)
    m = case['measurement']
    settings, trace, files, upper_trace, upper_raw, upper_plan = speech.capture(
        case_path, m['host_block_frames'], artifacts, execute, ('syllables', 'sung_release', 'aspiration'))
    frames = m['output_frames']
    rate, pcm = wavfile.read(files[0][0])
    upper_pcm = np.fromfile(upper_raw, dtype='<f4')
    if any(x.shape != (frames,) or x.dtype != np.float32 or not np.isfinite(x).all() for x in (pcm, upper_pcm)):
        raise ValueError('CLIまたは固定上流のPCMの長さ・型・有限性が登録条件と一致しません')
    native, reference = (speech.load_trace(path, frames) for path in (trace, upper_trace))
    selected = ['frame', *m['observed_fields']]
    first_state, state_errors = speech.compare_traces(native[selected], reference[selected], m)
    pcm_error = wasm.compare_pcm(pcm, upper_pcm, m['pcm_absolute_tolerance'])
    song_flags, physical = compare_song(case, settings, timing.read(upper_plan), pcm, syllables)
    checks = {
        **lyric_flags, **song_flags,
        'cli_wav_format': rate == m['output_rate_hz'] and settings['output_frames'] == frames,
        'cli_output_is_block_invariant': all(sha256(w) == sha256(files[0][0])
                                              and sha256(t) == sha256(files[0][1]) for w, t in files),
        'cli_states_against_upper': first_state is None,
        'cli_pcm_against_upper': pcm_error['first_frame_over_tolerance'] is None,
    }
    report = {'checks': checks, 'lyrics': lyrics, 'song': physical, 'cli_pcm_upstream': pcm_error,
              'first_state_over_tolerance': first_state, 'state_errors': state_errors}
    if browser:
        worklet_checks, worklet = compare_browser(case, config['song_voice'], native, reference, settings,
                                                  pcm, upper_pcm, artifacts, execute, bun)
        checks.update(worklet_checks)
        report['browser'] = worklet
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('--native-only', action='store_true', help='CLIと固定上流の比較を実行する')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', args.run_id):
        parser.error('実行IDは英数字で始めてください')
    case = timing.read(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(
            ['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True):
        raise SystemExit('変更のない固定上流版が必要です')
    source = WORKSPACE / 'cases' / case['voice_case']
    modules = (speech, sibilant, song, timing, shared, wasm)
    inputs = [CASE, source, speech.PROBE, song.DICT, LIVE, Path(__file__).resolve(),
              *shared.candidate_sources(), *(Path(m.__file__) for m in modules),
              WORKSPACE / 'tools/upstream_baseline.py']
    bun = ['bun'] if shutil.which('bun') else ['npx', '--yes', '--package=bun@1.4.4', '--', 'bun']
    paths = ('crates/chimera/src/phonetics/korean.rs', 'crates/chimera/src/phonetics/syllables.rs',
             'crates/chimera/src/phonetics/sing.rs', 'crates/chimera/src/phonetics/planner.rs',
             'crates/chimera/tests/syllables.rs', 'crates/chimera-cli/src/main.rs', 'crates/chimera-cli/src/render.rs')
    metadata = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision,
                'unicode_version': unicodedata.unidata_version,
                'upper_source_sha256': {name: sha256(UPSTREAM / name) for name in paths}}
    if not args.native_only:
        inputs.extend([*web_sources(), WORKSPACE / 'tools/measure_worklet_english_body.py'])
        metadata.update(node=subprocess.check_output(['node', '--version'], text=True).strip(),
                        bun=subprocess.check_output([*bun, '--version'], text=True).strip())
    return shared.record_measurement(args.run_id, CASE, inputs, metadata,
        lambda out, execute: measure(case, source, out, execute, bun, not args.native_only),
        command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
