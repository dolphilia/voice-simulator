"""実ブラウザの鍵盤歌唱を、固定上流とネイティブ再実行へ照合する。"""

import argparse
from pathlib import Path
import re
import shutil
import subprocess

import numpy as np
from scipy.io import wavfile

import measure_uniform_tube as shared
from measure_worklet_fixed import ROOT, WEB, web_sources
from measure_vowel_voice import independent_yin
from upstream_baseline import UPSTREAM, WORKSPACE, sha256
from measure_wasm_fixed import read_json

CASE = WORKSPACE / 'cases/worklet-midi-song.json'
CAPTURE = WEB / 'tools/capture-midi-song.mjs'
SUSTAINED = (('la', 0, .26, .43, 45), ('ma', 1, .25, .43, 48),
             ('continue', 3, .25, .44, 52), ('fallback', 4, .22, .36, 48))


def select(clock, data, start, end):
    result = data[(clock >= start) & (clock < end)]
    if not len(result):
        raise ValueError(f'{start:.4f}〜{end:.4f}秒の観測がありません')
    return result


def observations(clock, pitch, voicing, lip, rms, events, settings):
    on_a, on_b, old_off, carry, fallback, stop = events
    pitches = {}
    for label, event, start, end, note in SUSTAINED:
        onset = events[event]
        hz = float(np.median(select(clock, pitch, onset + start, onset + end)))
        target = 440 * 2 ** ((note - 69) / 12)
        pitches[label] = {'hz': hz, 'cents': float(1200 * np.log2(hz / target)),
                          'minimum_voicing': float(select(clock, voicing, onset + start, onset + end).min())}
    active = select(clock, rms, on_a + .25, stop - .04)
    silence = select(clock, rms, stop + settings['release_check_offset_seconds'], stop + .54)
    return {
        'pitches': pitches,
        'ma_minimum_lip_area': float(select(clock, lip, on_b, on_b + .18).min()),
        'ma_reopened_lip_area': float(select(clock, lip, on_b + .22, on_b + .45).min()),
        'continued_minimum_lip_area': float(select(clock, lip, carry, stop - .01).min()),
        'old_release_minimum_voicing': float(select(clock, voicing, old_off - .024, old_off + .12).min()),
        'release_rms_ratio': float(silence.max() / active.max()),
    }


def acoustic_checks(side, metrics, settings):
    minimum = settings['minimum_held_voicing']
    opened = settings['open_lip_area_cm2']
    return {
        f'{side}_notes_and_voicing': all(abs(item['cents']) < settings['maximum_pitch_difference_cents']
            and item['minimum_voicing'] > minimum for item in metrics['pitches'].values()),
        f'{side}_ma_closes_and_reopens': metrics['ma_minimum_lip_area'] < settings['closed_lip_area_cm2']
            and metrics['ma_reopened_lip_area'] > opened,
        f'{side}_carry_without_new_closure': metrics['continued_minimum_lip_area'] > opened,
        f'{side}_releasing_old_note_keeps_voice': metrics['old_release_minimum_voicing'] > minimum,
        f'{side}_release_to_silence': metrics['release_rms_ratio'] < settings['maximum_release_ratio'],
    }


def measure(case, artifacts, execute, bun):
    execute([*bun, 'test', 'tests/singing-live.test.ts', '-t', 'each key sings the next syllable'], cwd=UPSTREAM)
    execute([*bun, 'run', 'build'], cwd=WEB, stdout=artifacts / 'browser-build.log')
    execute(['node', str(CAPTURE), str(artifacts), str(CASE), str(UPSTREAM)], cwd=WEB)
    browser = read_json(artifacts / 'midi-song-browser.json')
    replay = artifacts / 'midi-song-case.json'
    report = read_json(artifacts / 'midi-song.json')
    command = ['cargo', 'run', '--locked', '--release', '-p', 'vocal-cli', '--']
    execute([*command, 'inspect', str(replay)], stdout=artifacts / 'cli-inspect.json')
    execute([*command, 'render', str(replay), str(artifacts / 'cli-voice.csv')])
    execute([*command, 'render-pcm', str(replay), str(artifacts / 'cli.wav'), str(artifacts / 'cli-pcm.csv'), '113'])
    inspect = read_json(artifacts / 'cli-inspect.json')
    voice = read_json(replay)['live_song_voice']
    trace = np.genfromtxt(artifacts / 'cli-voice.csv', delimiter=',', names=True)
    rate, pcm = wavfile.read(artifacts / 'midi-song.wav')
    raw = np.asarray(report['observations'])
    columns = {name: index for index, name in enumerate(report['columns'])}
    indexes = raw[:, columns['frames_rendered']].astype(int) - 1
    fields = {'gate': 'gate', 'lip_aperture_cm': 'lip_aperture_cm', 'lip_minimum_cm2': 'lip_minimum_cm2',
              'glottal_f0_hz': 'f0_hz', 'smoothed_f0_hz': 'smoothed_f0_hz', 'glottal_voicing': 'voicing'}
    difference = {field: float(np.max(np.abs(raw[:, columns[field]] - trace[dest][indexes])))
                  for field, dest in fields.items()}
    settings = case['measurement']
    selected = [event['frame'] / rate for event in voice['events']]
    block = int(raw[0, columns['quantum_frames']])
    rms = np.sqrt(np.mean(pcm.astype(float).reshape(-1, block) ** 2, axis=1))
    observed = observations(indexes / rate, raw[:, columns['glottal_f0_hz']], raw[:, columns['glottal_voicing']],
                            raw[:, columns['lip_minimum_cm2']], rms, selected, settings)
    pitches = {}
    for label, index, start, end, midi in SUSTAINED:
        left, right = [round(rate * (selected[index] + t)) for t in (start, end)]
        hz, score = independent_yin(pcm[left:right].astype(float), rate,
                                    {'pitch_min_hz': 70, 'pitch_max_hz': 320, 'yin_threshold': .15})
        target = 440 * 2 ** ((midi - 69) / 12)
        pitches[label] = {'hz': hz, 'yin_score': score,
                          'cents': float(1200 * np.log2(hz / target)) if hz else None}
    source = browser['upstream']
    telemetry = source['telemetry']
    clock, f0, voicing, area, env = (np.asarray([row[key] for row in telemetry])
                                    for key in ('clock', 'f0', 'voicing', 'lipArea', 'rms'))
    upper = observations(clock, f0, voicing, area, env, [e['clock'] for e in source['events']], settings)
    transitions = [row['transition'] for row in inspect['transitions']]
    expected = case['input']['events']
    state = [(row['next_syllable'], row['sounding_note'], row['sounding_syllable']) for row in transitions]
    upper_state = [(row['next'], row['pitch'], row['text']) for row in source['events']]
    errors = [((time - selected[0]) - (event['seconds'] - expected[0]['seconds']))
              for time, event in zip(selected, expected, strict=True)]
    checks = {
        'browser_uses_midi_path': all(browser[name]['requests'] == [{'sysex': False}] and not browser[name]['errors']
                                     for name in ('candidate', 'upstream')),
        'applied_keys_match_registration': [row['frame'] for row in inspect['transitions']] == [e['frame'] for e in voice['events']]
            and [row['key'] for row in inspect['transitions']] == [{k: v for k, v in e.items() if k != 'seconds'} for e in expected]
            and all(abs(error) <= .05 for error in errors) and report['songKeys'] == voice['events'],
        'normal_clock_and_pcm_replay': rate == report['sampleRate'] == case['input']['output_rate_hz']
            and block == 128 and np.array_equal(indexes, np.arange(block - 1, len(pcm), block))
            and bool((np.diff(raw[:, columns['context_frame']]) == block).all())
            and (artifacts / 'midi-song.wav').read_bytes() == (artifacts / 'cli.wav').read_bytes(),
        'cli_observation_matches_worklet': all(delta <= 1e-11 for delta in difference.values()),
        'candidate_pcm_pitch': all(item['cents'] is not None
                                   and abs(item['cents']) < settings['maximum_pitch_difference_cents']
                                   for item in pitches.values()),
        'upper_same_syllable_and_held_pitch': state == upper_state
            and [t['action'] for t in transitions] == ['syllable', 'syllable', 'ignored', 'melisma', 'fallback', 'release'],
        **acoustic_checks('candidate', observed, settings), **acoustic_checks('upstream', upper, settings),
    }
    return {'checks': checks, 'browser': browser['chromium'], 'candidate': observed, 'upstream': upper,
            'trace_maximum_difference': difference, 'relative_event_errors_seconds': errors,
            'cli_states': state, 'upstream_states': upper_state, 'syllables': voice['syllables'],
            'audio_frames': len(pcm), 'independent_pcm_pitch': pitches,
            'event_quantum_process_ms': [float(raw[event['frame'] // block, columns['process_ms']]) for event in voice['events']]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', args.run_id):
        parser.error('実行IDは英数字で始めてください')
    case = read_json(CASE)
    rev = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if rev != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True):
        parser.error('固定上流の取得状態を確認してください')
    ref = case['reference']
    baseline = WORKSPACE / 'runs' / ref['manual_midi_run'] / 'manifest.json'
    if sha256(baseline) != ref['manifest_sha256']:
        parser.error('手動MIDIの基準マニフェストが一致しません')
    bun = ['bun'] if shutil.which('bun') else ['npx', '--yes', '--package=bun@1.4.4', '--', 'bun']
    upstream = [UPSTREAM / name for name in ('src/ui/singing.ts', 'src/ui/store.ts', 'src/ui/midi.ts',
        'src/audio/AudioEngine.ts', 'crates/chimera/src/phonetics/sing.rs', 'tests/singing-live.test.ts')]
    inputs = [CASE, CAPTURE, baseline, Path(__file__), Path(__file__).with_name('measure_vowel_voice.py'),
              *web_sources(), *shared.candidate_sources(), *upstream]
    return shared.record_measurement(args.run_id, CASE, inputs, {'case_id': case['id'], 'upstream_revision': rev},
        lambda out, execute: measure(case, out, execute, bun), command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
