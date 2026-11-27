"""中国語辞書、歌詞の振り分け、歌唱とブラウザ再演を固定上流に照合する。"""

import argparse
from pathlib import Path
import re
import shutil
import subprocess

import numpy as np

import measure_bilabial_stop as voice
import measure_russian_lyrics as rendering
import measure_sibilant as frication
import measure_song_plan as song_plan
import measure_speech_timing as timing
import measure_uniform_tube as shared
import measure_velar_stops as browser_song
import measure_vowel_voice as vowels
import measure_wasm_fixed as wasm
from measure_worklet_fixed import ROOT, web_sources
from upstream_baseline import UPSTREAM, WORKSPACE, sha256

CASE = WORKSPACE / 'cases/mandarin-lyrics.json'
REVISED_CASE = WORKSPACE / 'cases/mandarin-lyrics-v2.json'
DICTIONARY = WORKSPACE / 'data/mandarin.txt.gz'
PROBE = WORKSPACE / 'tools/upstream_mandarin_probe.rs'


def score(variant, limits):
    return {'id': variant['id'], 'lyrics': variant['lyrics'],
            'notes': [{'midi': midi, 'beats': 1} for midi in variant['midi']],
            'bpm': limits['bpm'], 'start_seconds': limits['start_seconds']}


def representation(syllables):
    def annotated(segment):
        suffix = {True: 'ʰ', False: '˭', None: ''}[segment.get('aspirated')]
        return segment['ipa'] + suffix

    rows = [[*item['onset'], item['nucleus'], *item['coda']] for item in syllables]
    return {
        'count': len(syllables),
        'labels': [item['text'] for item in syllables],
        'ipa': [''.join(map(annotated, row)) for row in rows],
        'phrase_ends': [i for i, item in enumerate(syllables) if item['phraseEnd']],
        'word_ends': [i for i, item in enumerate(syllables) if item['wordEnd']],
        'nuclei': [item['nucleus']['ipa'] for item in syllables],
        'coda_lengths': [[part.get('dur') for part in s['coda']] for s in syllables],
        'nasal_leads': [s.get('nasalLead') for s in syllables],
        'closings': [s.get('closing') for s in syllables],
        'pitch_bends': [s.get('pitch', []) for s in syllables],
    }


def compare_lyrics(config, artifacts, execute):
    limits = config['measurement']
    entries = config['lyric_cases'] + [{**s, 'text': s['lyrics']} for s in config['song']]
    request = artifacts / 'lyric-inputs.json'
    timing.write(request, {'song_plan': {
        'lyric_cases': [{key: entry[key] for key in ('id', 'text')} for entry in entries],
        'mandarin_words': list(config['han_readings']),
        'scores': [score(entry, limits) for entry in (*config['song'], config['plan_only'])],
    }})
    candidate_path = artifacts / 'lyric-candidate.json'
    rendered = artifacts / 'lyric-render.json'
    execute([*song_plan.CLI, 'inspect', str(request)], stdout=candidate_path)
    execute([*song_plan.CLI, 'render', str(request), str(rendered)])
    candidate = timing.read(candidate_path)
    execute(['cargo', 'build', '--locked', '--release', '-p', 'chimera-cli'], cwd=UPSTREAM)
    upper_dir = artifacts / 'lyric-upstream'
    upper_dir.mkdir()
    upper_probe = shared.build_upstream_probe(PROBE, upper_dir, execute, extra_libraries=('serde_json',))
    reading_path = upper_dir / 'readings.json'
    execute([str(upper_probe), str(request)], cwd=UPSTREAM, stdout=reading_path)
    readings = candidate['mandarin_readings']
    checks = {'inspect_and_render': sha256(candidate_path) == sha256(rendered),
              'fixed_dictionary': sha256(DICTIONARY) == config['dictionary_sha256']
              == sha256(UPSTREAM / 'public/data/mandarin.txt.gz'),
              'registered_and_upstream_readings': readings == config['han_readings'] == timing.read(reading_path)}
    syllables = {row['id']: row['syllables'] for row in candidate['lyric_cases']}
    observations = {}
    for entry in entries:
        name = entry['id']
        upper_path = upper_dir / f'{name}.json'
        execute([str(UPSTREAM / 'target/release/chimera'), 'syllables', entry['text']], cwd=UPSTREAM, stdout=upper_path)
        difference, error = timing.compare(syllables[name], timing.read(upper_path), limits['gesture_abs_tolerance'])
        observed = representation(syllables[name])
        expected = {key: entry[key] for key in observed.keys() & entry.keys()}
        checks[f'{name}/upstream_syllables'] = difference is None
        checks[f'{name}/registered_syllables'] = all(observed[k] == v for k, v in expected.items())
        if 'count_min' in entry:
            checks[f'{name}/registered_syllables'] &= observed['count'] >= entry['count_min']
        observations[name] = {**observed, 'first_upstream_difference': difference, 'maximum_difference': error}
    diagnostic = next(entry for entry in candidate['scores'] if entry['id'] == config['plan_only']['id'])
    planned = diagnostic['plan']['unavailable_speech_symbols']
    checks['planned_unavailable'] = (planned == config['plan_only']['unavailable']
                                     and len(diagnostic['plan']['notes']) == len(diagnostic['syllables']))
    return checks, syllables, {'cases': observations, 'readings': readings,
                               'upstream_readings': timing.read(reading_path), 'unavailable': planned}


def measure(config, case_path, base, artifacts, execute, bun, browser):
    execute(['cargo', 'test', '--locked', '-p', 'chimera', '--test', 'mandarin', '--test', 'mandarin_rhymes',
             '--test', 'mandarin_u', '--test', 'mandarin_ong', '--test', 'syllables'],
            cwd=UPSTREAM, stdout=artifacts / 'upstream-tests.log')
    checks, syllables, lyrics = compare_lyrics(config, artifacts, execute)
    probe = shared.build_upstream_probe(voice.PROBE, artifacts, execute, extra_libraries=('serde_json',))
    limits = config['measurement']
    variants, rendered = {}, {}
    for variant in config['song']:
        name = variant['id']
        flags, details, replay = rendering.measure_song(config, variant, syllables[name], base,
                                                        artifacts / name, probe, execute)
        _, settings, *_ = replay
        notes = settings['song']['syllables']
        flags.update(registered_nuclei=[s['nucleus']['ipa'] for s in notes] == variant['nuclei'],
                     no_lexical_pitch_bends=not any(s.get('pitch') for s in notes))
        if 'onset_vot' in variant:
            vot = [s['onset'][0].get('vot') for s in notes]
            gestures = [g for g in settings['gestures'] if g['label'] == 'aspiration']
            flags['aspiration_changes_folds'] = (vot == variant['onset_vot'] and len(gestures) == 2
                and [g['targets']['abduction_cm2'] for g in gestures] == [.22, .36])
            details.update(vot_seconds=vot, abduction_gestures=gestures)
        if 'offglide_seconds' in variant:
            spans = [segment for phrase in settings['song']['plan']['phrases']
                     for segment in phrase['timing']['segments']]
            glide = [s for s in spans if s['segment']['ipa'] == variant['offglide_ipa']]
            expected = variant['offglide_seconds']
            tolerance = limits['gesture_abs_tolerance']
            flags['independent_glide_duration'] = (len(glide) == 1
                and abs(glide[0]['end_seconds'] - glide[0]['start_seconds'] - expected) <= tolerance
                and abs(glide[0]['segment']['glide'] - expected) <= tolerance)
            details['offglide'] = glide
        checks.update({f'{name}/{key}': bool(value) for key, value in flags.items()})
        variants[name] = details
        rendered[name] = replay
    first, second = (rendered[name] for name in ('character-tones', 'typed-tones'))
    same_pcm = np.array_equal(first[4].view('u4'), second[4].view('u4'))
    checks['different_spellings_same_score_and_pcm'] = same_pcm and first[1]['gestures'] == second[1]['gestures']
    report = {'checks': checks, 'lyrics': lyrics, 'variants': variants}
    if browser:
        flags, report['browser'] = browser_song.browser_measure(
            config, {name: rendered[name] for name in limits['browser_cases']}, artifacts, execute, bun, case_path=case_path)
        checks.update(flags)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('--native-only', action='store_true', help='CLIと固定上流を計測する')
    parser.add_argument('--revision', type=int, choices=(1, 2), default=2, help='ケース定義の版')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', args.run_id):
        parser.error('実行IDは英数字で始めてください')
    case_path = CASE if args.revision == 1 else REVISED_CASE
    config = timing.read(case_path)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != config['upstream_revision'] or subprocess.check_output(
            ['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True):
        raise SystemExit('変更のない固定上流版が必要です')
    base = WORKSPACE / 'cases' / config['parent_song_case']
    modules = (voice, rendering, frication, song_plan, timing, shared, browser_song, wasm, vowels)
    sources = [case_path, base, voice.PROBE, PROBE, DICTIONARY, DICTIONARY.with_name('MANDARIN-PINYIN-LICENSE.txt'),
               Path(__file__).resolve(), *shared.candidate_sources(),
               *(Path(module.__file__) for module in modules), WORKSPACE / 'tools/upstream_baseline.py']
    upstream_paths = ('crates/chimera/src/phonetics/mandarin.rs', 'crates/chimera/src/phonetics/syllables.rs',
                      'crates/chimera/src/phonetics/sing.rs', 'crates/chimera/tests/mandarin.rs',
                      'crates/chimera/tests/mandarin_rhymes.rs', 'crates/chimera/tests/mandarin_u.rs',
                      'crates/chimera/tests/mandarin_ong.rs', 'crates/chimera/tests/syllables.rs',
                      'crates/chimera-cli/src/render.rs', 'tools/build-mandarin.ts',
                      'public/data/mandarin.txt.gz', 'public/data/MANDARIN-PINYIN-LICENSE.txt')
    metadata = {'case_id': config['id'], 'revision': config['revision'], 'upstream_revision': revision,
                'upper_source_sha256': {name: sha256(UPSTREAM / name) for name in upstream_paths}}
    bun = ['bun'] if shutil.which('bun') else ['npx', '--yes', '--package=bun@1.4.4', '--', 'bun']
    if args.native_only:
        sources += [WORKSPACE / 'data/cmudict.txt.gz', WORKSPACE / 'data/CMUDICT-LICENSE.txt']
    else:
        sources += [browser_song.KOREAN, browser_song.LIVE, *web_sources(),
                    WORKSPACE / 'tools/measure_worklet_english_body.py']
        metadata.update(node=subprocess.check_output(['node', '--version'], text=True).strip(),
                        bun=subprocess.check_output([*bun, '--version'], text=True).strip())
    return shared.record_measurement(
        args.run_id, case_path, sources, metadata,
        lambda out, run: measure(config, case_path, base, out, run, bun, not args.native_only), command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
