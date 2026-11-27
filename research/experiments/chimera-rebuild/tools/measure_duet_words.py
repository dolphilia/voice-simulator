"""歌詞の拍境界を、固定上流・有理数の計算・実ブラウザに照合する。"""

import argparse
from fractions import Fraction
import json
from pathlib import Path
import re
import shutil
import subprocess

import numpy as np
from scipy.io import wavfile

from measure_fan_crossing_allocations import run_manifest, verified_path
import measure_uniform_tube as shared
from measure_wasm_fixed import read_json
from measure_worklet_fixed import ROOT, WEB, web_sources
from upstream_baseline import UPSTREAM, WORKSPACE, sha256

CASE = WORKSPACE / 'cases/duet-words.json'
TRANSPORT = WORKSPACE / 'cases/duet-transport.json'
TELEMETRY = WORKSPACE / 'cases/duet-telemetry.json'
CAPTURE = WEB / 'tools/capture-duet-words.mjs'
DEMO = WEB / 'public/shows/duet-clock'
NATIVE = ['cargo', 'run', '--locked', '--release', '-p', 'vocal-cli', '--']
UPPER = ['cargo', 'run', '--locked', '--release', '-p', 'chimera-cli', '--']


def rational(value):
    return Fraction(str(value))


def schedule(melody):
    time = rational(melody.get('t0', 0.3))
    beat = Fraction(60) / rational(melody['bpm'])
    for midi, length in melody['notes']:
        end = time + beat * rational(length)
        yield time, end, midi, length
        time = end


def oracle(voice, spell):
    notes = [(start, end) for start, end, midi, _ in schedule(voice['melody']) if midi > 0]
    spell = {key.lower(): value for key, value in spell.items()}
    lyrics = []
    word = None
    for i, ((start, end), syllable) in enumerate(zip(notes, voice['syllables'], strict=True)):
        if word is None or not syllable.get('melisma'):
            text = spell.get(syllable['text'].lower(), syllable['text'])
            word = {'key': i, 'text': text + ('' if syllable.get('wordEnd') else '-')}
        lyrics.append((start, end, word))
    return lyrics


def expected_word(lyrics, seconds):
    return next((word for start, end, word in lyrics if start <= seconds < end), None)


def voice_asset(melody, spelled):
    return {'melody': melody, 'syllables': melody['syllables'] if 'syllables' in melody else spelled[melody['lyrics']]}


def spelling_result(rows):
    return [(row['text'], bool(row.get('wordEnd')), bool(row.get('melisma'))) for row in rows]


def build_inputs(case, demo_show, stem_cases, artifacts, execute):
    demo_melodies = [read_json(DEMO / voice['melody']) for voice in demo_show['voices']]
    diagnostic = case['diagnostic']
    diagnostic_melodies = [voice['melody'] for voice in diagnostic['voices']]
    lyrics = sorted({m['lyrics'] for m in [*demo_melodies, *diagnostic_melodies] if 'syllables' not in m})
    lex_input, lex_output = (artifacts / name for name in ('syllable-case.json', 'syllables.json'))
    lex_input.write_text(json.dumps({'song_plan': {'lyric_cases': [{'id': text, 'text': text} for text in lyrics]}}, ensure_ascii=False))
    execute([*NATIVE, 'inspect', str(lex_input)], stdout=lex_output)
    spelled = {row['id']: row['syllables'] for row in read_json(lex_output)['lyric_cases']}
    upstream_match = True
    for i, text in enumerate(lyrics):
        upstream_output = artifacts / f'upper-syllables-{i}.json'
        execute([*UPPER, 'syllables', text], cwd=UPSTREAM, stdout=upstream_output)
        upstream_match &= spelling_result(read_json(upstream_output)) == spelling_result(spelled[text])
    demo = [voice_asset(melody, spelled) for melody in demo_melodies]
    consistent = []
    for i, (source, item) in enumerate(zip(stem_cases, demo, strict=True)):
        destination = artifacts / f'demo-native-plan-{i + 1}.json'
        execute([*NATIVE, 'inspect', str(source)], stdout=destination)
        song = read_json(destination)['song']
        notes = song['plan']['notes']
        consistent.append(song['syllables'] == item['syllables'] and len(notes) == len(item['melody']['notes']) and all(
            n['note'] == {'midi': midi, 'beats': beats} and abs(n['beat_seconds'] - float(start)) <= 1e-12
            and abs(n['beat_end_seconds'] - float(end)) <= 1e-12 for n, (start, end, midi, beats) in zip(
                notes, schedule(item['melody']), strict=True)))
    control = case['controls']['default_start_fractional_bpm']
    rate = case['sample_rate_hz']
    controls = sorted({0, *(int(edge * rate) + delta for start, end, _, _ in schedule(control)
                           for edge in (start, end) for delta in (-1, 0, 1, 2))})
    inputs = {
        'demo': {'voices': demo, 'samples': case['demo']['paused_samples'], 'spell': demo_show.get('spell', {})},
        'diagnostic': {'voices': [voice_asset(melody, spelled) for melody in diagnostic_melodies],
                       'samples': diagnostic['paused_samples'], 'spell': diagnostic['spell']},
        'fractional': {'voices': [voice_asset(control, spelled)], 'samples': controls, 'spell': {}},
    }
    return inputs, {'native_demo_melodies_match_prior_audio_plans': all(consistent),
                    'upper_and_native_plain_lyrics_match': upstream_match}


def sounding_phrases(voice):
    notes, syllables = [], []
    lyrics = iter(voice['syllables'])
    start = None
    for at, _, midi, beats in schedule(voice['melody']):
        if midi > 0:
            if not notes:
                start = at
            notes.append({'midi': midi, 'beats': beats})
            syllables.append(next(lyrics))
        elif notes:
            yield start, notes, syllables
            notes, syllables = [], []
    if notes:
        yield start, notes, syllables


def diagnostic_audio(case, voices, source, artifacts, execute):
    spec = case['diagnostic']
    path = artifacts / 'diagnostic'
    path.mkdir()
    rate, frames = case['sample_rate_hz'], spec['frames']
    audio = np.zeros(frames)
    assets = []
    for i, (voice, setting) in enumerate(zip(voices, spec['voices'], strict=True), 1):
        mel = f'melody-{i}.json'
        (path / mel).write_text(json.dumps(voice['melody'], ensure_ascii=False, indent=2) + '\n')
        assets.append({'name': setting['name'], 'melody': mel})
        stem = np.zeros(frames)
        for j, (start, notes, syllables) in enumerate(sounding_phrases(voice), 1):
            name = f'voice-{i}-phrase-{j}'
            settings, wave, trace = (path / f'{name}.{ext}' for ext in ('json', 'wav', 'csv'))
            document = read_json(source)
            document['song_voice'].update(body=setting['body'], score={
                'id': name, 'start_seconds': float(start), 'bpm': voice['melody']['bpm'], 'notes': notes, 'syllables': syllables,
            })
            settings.write_text(json.dumps(document, ensure_ascii=False, indent=2) + '\n')
            if i == 1 and j == 2:
                execute([*NATIVE, 'inspect', str(settings)], stdout=path / 'voice-1-phrase-2-plan.json')
            execute([*NATIVE, 'render-pcm', str(settings), str(wave), str(trace), '128'])
            rendered_rate, pcm = wavfile.read(wave)
            if rendered_rate != rate or pcm.ndim != 1 or not (0 < len(pcm) <= frames and np.isfinite(pcm).all()):
                raise ValueError('対照音源の長さまたは形式が事前登録と異なります')
            stem[:len(pcm)] += pcm
        wavfile.write(path / f'voice-{i}.wav', rate, stem.astype(np.float32))
        audio += stem * 0.35
    wave = path / 'mix.wav'
    peak = float(np.max(np.abs(audio)))
    if not 0 < peak < 32767 / 32768:
        raise ValueError('対照の混合WAVが振幅範囲を超えています')
    wavfile.write(wave, rate, np.rint(audio * 32768).astype('<i2'))
    (path / 'show.json').write_text(json.dumps({'title': 'デュエット歌詞の対照', 'audio': wave.name,
        'sample_rate_hz': rate, 'frames': frames, 'voices': assets, 'spell': spec['spell']}, ensure_ascii=False, indent=2) + '\n')
    _, first = wavfile.read(path / 'voice-1.wav')
    def rms(window):
        lo, hi = spec[window]
        return float(np.sqrt(np.mean(first[lo:hi].astype(float) ** 2)))

    return {'frames': frames, 'peak_mix': peak, 'first_voice_quiet_rms': rms('first_voice_quiet_window'),
            'first_voice_preparation_rms': rms('first_voice_next_phrase_preparation_window')}


def comparison(case, inputs, selection, browser):
    rate = case['sample_rate_hz']
    unexpected = {'candidate': [], 'upstream': []}
    checks = {'both_reject_wrong_syllable_count': all(selection['wrongCount'])}
    comparisons = 0
    for scene, data in inputs.items():
        for index, (voice, comparison) in enumerate(zip(data['voices'], selection['engines'][scene], strict=True)):
            reference = oracle(voice, data['spell'])
            for side in unexpected:
                checks[f'{scene}_{index + 1}_{side}_intervals'] = len(comparison[side]) == len(reference) and all(
                    abs(got['start'] - float(start)) <= 1e-12 and abs(got['end'] - float(end)) <= 1e-12 and got['word'] == word
                    for got, (start, end, word) in zip(comparison[side], reference, strict=True))
            for row in comparison['samples']:
                comparisons += 1
                expected = expected_word(reference, Fraction(row['sample'], rate))
                for side in unexpected:
                    if row[side] != expected:
                        unexpected[side].append({'scene': scene, 'voice': index + 1, 'sample': row['sample'],
                                                 'word': row[side], 'expected': expected})
    def exact_decimals(differences):
        return all(item['scene'] == 'demo' and item['voice'] == 2 for item in differences) and (
            [item['sample'] for item in differences] == case['expected_upper_decimal_difference_samples'])

    checks['upstream_has_only_registered_decimal_differences'] = exact_decimals(unexpected['upstream'])
    correction = case['candidate_decimal_policy'] != 'upstream'
    checks['candidate_integer_sample_oracle'] = not unexpected['candidate'] if correction else exact_decimals(unexpected['candidate'])
    for scene in ('demo', 'diagnostic'):
        captured = browser[scene]
        expected_frames = inputs[scene]['samples']
        expected = [[comparison['samples'][i]['candidate'] for comparison in selection['engines'][scene]]
                    for i in range(len(expected_frames))]
        checks[f'{scene}_browser_paused_samples'] = [record['frame'] for record in captured['paused']] == expected_frames and all(
            not record['playing'] and record['epoch'] == i and record['words'] == expected[i]
            for i, record in enumerate(captured['paused']))
        checks[f'{scene}_browser_lyric_frontend'] = all(any(entry['status'] == 200 and token in entry['path']
            for entry in captured['assets']) for token in ('melody-1.json', 'melody-2.json', '.wasm', 'cmudict'))
    diagnostic = browser['diagnostic']
    tracks = [oracle(voice, inputs['diagnostic']['spell']) for voice in inputs['diagnostic']['voices']]
    checks['browser_live_forward_backward_seek'] = len(diagnostic['live']) == 3 and (
        diagnostic['live'][0]['frame'] < diagnostic['live'][1]['frame'] and diagnostic['live'][1]['frame'] > diagnostic['live'][2]['frame']) and all(
        record['playing'] and record['epoch'] == len(inputs['diagnostic']['samples']) + i
        and record['words'] == [expected_word(track, rational(record['seconds'])) for track in tracks]
        for i, record in enumerate(diagnostic['live']))
    checks['browser_pause_holds_words'] = len(diagnostic['held']) == 2 and diagnostic['held'][0] == diagnostic['held'][1] and not diagnostic['held'][0]['playing']
    checks['browser_wrong_syllable_count_keeps_other_voice'] = '音節数' in browser['invalidMelody'] and browser['invalidPlayback']['playing'] and (
        browser['invalidPlayback']['words'] == [None, {'key': 0, 'text': 'Pop'}])
    checks['browser_no_uncaught_errors'] = not browser['errors']
    return checks, {'comparisons': comparisons, 'decimal_differences': unexpected, 'browser': browser['version']}


def compare_roundoff_baseline(case, before, after):
    changes = []
    for scene, voices in after['engines'].items():
        for voice, (old, new) in enumerate(zip(before['engines'][scene], voices, strict=True), 1):
            for left, right in zip(old['samples'], new['samples'], strict=True):
                if left['sample'] != right['sample'] or left['upstream'] != right['upstream']:
                    raise ValueError('丸め補正の前後でサンプル一覧または上流結果が変わりました')
                if left['candidate'] != right['candidate']:
                    changes.append({'scene': scene, 'voice': voice, 'sample': right['sample'],
                                    'before': left['candidate'], 'after': right['candidate']})
    valid = [(change['scene'], change['voice'], change['sample']) for change in changes] == [
        ('demo', 2, sample) for sample in case['expected_upper_decimal_difference_samples']]
    return valid, changes


def measure(case, demo_show, stem_cases, references, baseline, bun, artifacts, execute):
    execute([*bun, 'test', 'tests/words.test.ts', 'tests/tele.test.ts'], cwd=UPSTREAM, stdout=artifacts / 'upper-tests.log')
    inputs, preferred = build_inputs(case, demo_show, stem_cases, artifacts, execute)
    sound = diagnostic_audio(case, inputs['diagnostic']['voices'], stem_cases[0], artifacts, execute)
    (artifacts / 'word-inputs.json').write_text(json.dumps(inputs, ensure_ascii=False, indent=2) + '\n')
    execute([*bun, 'run', 'build'], cwd=WEB, stdout=artifacts / 'build.log')
    execute(['node', str(CAPTURE), str(CASE), str(UPSTREAM), str(artifacts)])
    selection = read_json(artifacts / 'word-selection.json')
    checks, result = comparison(case, inputs, selection, read_json(artifacts / 'browser-words.json'))
    checks['boundary_correction_changes_only_two_samples'], result['roundoff_changes'] = compare_roundoff_baseline(
        case, read_json(baseline[0]), selection)
    checks['boundary_correction_keeps_diagnostic_wav'] = sha256(baseline[1]) == sha256(artifacts / 'diagnostic/mix.wav')
    prep_at = Fraction(case['diagnostic']['first_voice_next_phrase_preparation_window'][0], case['sample_rate_hz'])
    return {**result, 'diagnostic_audio': sound, 'checks': {
        **checks, **preferred,
        'diagnostic_voice_1_rest_pcm': sound['first_voice_quiet_rms'] <= case['diagnostic']['first_voice_maximum_quiet_rms'],
        'diagnostic_voice_1_audible_preparation_during_lyric_gap': (
            sound['first_voice_preparation_rms'] >= case['diagnostic']['first_voice_minimum_preparation_rms']
            and expected_word(oracle(inputs['diagnostic']['voices'][0], inputs['diagnostic']['spell']), prep_at) is None),
        'demo_wav_and_telemetry_unchanged': all(sha256(DEMO / path.name) == sha256(path) for path in references),
    }}


def prior(name, case, revision, manifest_sha):
    entry = run_manifest(name, case, revision)
    if entry[1]['status'] != 'pass' or sha256(entry[0] / 'manifest.json') != manifest_sha:
        raise ValueError('登録した比較基準を照合できません')
    return entry


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', args.run_id):
        parser.error('英数字で始まる実行IDが必要です')
    case = read_json(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True):
        parser.error('変更のない固定上流版が必要です')
    ref_cfg = case['reference']
    tele_cfg = read_json(TELEMETRY)['reference']
    telemetry = prior(ref_cfg['telemetry_run'], 'duet-telemetry', revision, ref_cfg['telemetry_manifest_sha256'])
    transport = prior(tele_cfg['run'], 'duet-transport', revision, tele_cfg['manifest_sha256'])
    baseline_cfg = case['roundoff_reference']
    baseline_run = prior(baseline_cfg['run'], 'duet-words', revision, baseline_cfg['manifest_sha256'])
    baseline = [verified_path(baseline_run, output) for output in ('artifacts/word-selection.json', 'artifacts/diagnostic/mix.wav')]
    stem_cases = [verified_path(transport, f'artifacts/voice-{i}.json') for i in (1, 2)]
    references = [verified_path(transport, 'artifacts/mix.wav'), *(verified_path(telemetry, f'artifacts/voice-{i}.tele') for i in (1, 2))]
    demo_show = read_json(DEMO / 'show.json')
    demo_assets = [DEMO / name for name in ['show.json', demo_show['audio'], *(v[key] for v in demo_show['voices'] for key in ('melody', 'tele'))]]
    bun = ['bun'] if shutil.which('bun') else ['npx', '--yes', '--package=bun@1.4.4', '--', 'bun']
    upper_paths = ['src/show/words.ts', 'src/ui/components/DuetPage.tsx', 'src/ui/mouthWords.ts', 'src/wasm/engine.ts',
                   'crates/chimera-cli/src/render.rs', 'tests/words.test.ts', 'tests/tele.test.ts']
    details = {'case_id': case['id'], 'upstream_revision': revision,
        'upstream_source_sha256': {name: sha256(UPSTREAM / name) for name in upper_paths},
        'node': subprocess.check_output(['node', '--version'], text=True).strip(),
        'bun': subprocess.check_output([*bun, '--version'], text=True).strip()}
    inputs = [CASE, TRANSPORT, TELEMETRY, CAPTURE, Path(__file__), Path(shared.__file__),
              telemetry[0] / 'manifest.json', transport[0] / 'manifest.json', baseline_run[0] / 'manifest.json',
              *baseline, *stem_cases, *references, *demo_assets,
              *web_sources(), *shared.candidate_sources()]
    return shared.record_measurement(args.run_id, CASE, inputs, details, lambda artifacts, execute:
        measure(case, demo_show, stem_cases, references, baseline, bun, artifacts, execute), command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
