"""ロシア語の音節と、同じ歌詞を使った歌唱の計画・波形を固定上流と照合する。"""

import argparse
from pathlib import Path
import re
import shutil
import subprocess

import numpy as np
from scipy.io import wavfile

import measure_bilabial_stop as voice
import measure_sibilant as frication
import measure_song_plan as song_plan
import measure_speech_timing as timing
import measure_uniform_tube as shared
import measure_velar_stops as browser_song
import measure_wasm_fixed as wasm
from measure_worklet_fixed import ROOT, web_sources
from upstream_baseline import UPSTREAM, WORKSPACE, sha256

CASE = WORKSPACE / 'cases/russian-lyrics.json'


def representation(syllables):
    segments = [[*item['onset'], item['nucleus'], *item['coda']] for item in syllables]
    return {
        'count': len(syllables),
        'labels': [item['text'] for item in syllables],
        'tokens': [[s['ipa'] for s in row] for row in segments],
        'stress': [item['nucleus'].get('stress') for item in syllables],
        'nuclei': [item['nucleus']['ipa'] for item in syllables],
        'timed': [[[s['ipa'], s['dur']] for s in row if 'dur' in s] for row in segments],
        'word_ends': [item['wordEnd'] for item in syllables],
        'phrase_ends': [item['phraseEnd'] for item in syllables],
        'melisma': [item.get('melisma', False) for item in syllables],
    }


def compare_lyrics(config, artifacts, execute):
    entries = config['lyric_cases'] + [{**item, 'text': item['lyrics']} for item in config['song']]
    demo = next(item for item in entries if item['id'] == 'demo')
    demo_score = config['demo_score']
    request = artifacts / 'lyric-inputs.json'
    timing.write(request, {'song_plan': {
        'lyric_cases': [{key: entry[key] for key in ('id', 'text')} for entry in entries],
        'scores': [{'id': 'demo', 'lyrics': demo['text'], 'start_seconds': .5, 'bpm': demo_score['bpm'],
                    'notes': [{'midi': midi, 'beats': beats} for midi, beats in demo_score['midi_beats']]}],
    }})
    inspect = artifacts / 'lyric-candidate.json'
    render = artifacts / 'lyric-render.json'
    execute([*song_plan.CLI, 'inspect', str(request)], stdout=inspect)
    execute([*song_plan.CLI, 'render', str(request), str(render)])
    candidate = timing.read(inspect)
    syllables = {item['id']: item['syllables'] for item in candidate['lyric_cases']}
    execute(['cargo', 'build', '--locked', '--release', '-p', 'chimera-cli'], cwd=UPSTREAM)
    upper_dir = artifacts / 'lyric-upstream'
    upper_dir.mkdir()
    tol = config['measurement']['lexical_duration_tolerance']
    flags = {'lyrics_inspect_and_render': sha256(inspect) == sha256(render)}
    reports = {}
    for entry in entries:
        name = entry['id']
        upper = upper_dir / f'{name}.json'
        execute([str(UPSTREAM / 'target/release/chimera'), 'syllables', entry['text']], cwd=UPSTREAM, stdout=upper)
        result = syllables[name]
        first, error = timing.compare(result, timing.read(upper), tol)
        observed = representation(result)
        expected = {key: entry[key] for key in observed.keys() & entry.keys()}
        registered, _ = timing.compare({key: observed[key] for key in expected}, expected, tol)
        flags[f'{name}/upstream_lyrics'] = first is None
        flags[f'{name}/registered_lyrics'] = registered is None
        reports[name] = {**observed, 'first_upstream_difference': first, 'upstream_numeric_error': error,
                         'first_registered_difference': registered}
    demo_plan = candidate['scores'][0]
    unavailable = demo_plan['plan']['unavailable_speech_symbols']
    flags['demo_plan_and_inventory'] = (demo_plan['syllables'] == syllables['demo']
        and len(demo_score['midi_beats']) == len(demo_plan['syllables'])
        and unavailable == config['measurement']['demo_unavailable'])
    return flags, reports, syllables, unavailable


def measure_song(config, variant, syllables, base, out, probe, execute):
    out.mkdir()
    limits = config['measurement']
    source = {**timing.read(base)['song_voice'], 'body': 'male'}
    score = {**source['score'], 'id': variant['id'], 'lyrics': variant['lyrics'],
             'notes': [{'midi': note, 'beats': 1} for note in variant['midi']]}
    source['score'] = score
    path = out / 'case.json'
    timing.write(path, {'id': variant['id'], 'upstream_revision': config['upstream_revision'], 'song_voice': source})
    settings, trace, files, upper_trace, upper_raw, upper_plan = voice.capture(
        path, limits['host_block_frames'], out, execute, (), probe=probe)
    upper = timing.read(upper_plan)
    plan = settings['song']['plan']
    adapted = {**settings, 'speech': {'utterances': [
        {'segments': phrase['timing']['segments']} for phrase in plan['phrases']]}}
    tol = limits['gesture_abs_tolerance']
    parts, comparison = frication.compare_plans(adapted, upper, tol)
    flags = {'upstream_plan': comparison['passed'],
             'sung_syllables_match_entry': settings['song']['syllables'] == syllables
             and not plan['unavailable_speech_symbols']}

    calculated = []
    for i, midi in enumerate(variant['midi']):
        beat = score['start_seconds'] + i * 60 / score['bpm']
        calculated.append([i, beat, beat, 440 * 2 ** ((midi - 69) / 12)])
    observed = [[note[key] for key in ('lyric_index', 'beat_seconds', 'nucleus_start_seconds', 'f0_hz')]
                for note in plan['notes']]
    first_beat, _ = timing.compare(observed, calculated, tol)
    flags['independent_beat_and_frequency'] = first_beat is None
    detail = {'plan': comparison, 'observed_beat_frequencies': observed, 'first_beat_difference': first_beat}
    if 'soft_glide_duration_seconds' in variant:
        glides = [s for s in parts if s['ipa'] == 'j']
        target = variant['soft_glide_duration_seconds']
        flags['softness_glide_ends_at_second_beat'] = (len(glides) == 1
            and abs(glides[0]['t1'] - glides[0]['t0'] - target) <= tol
            and abs(glides[0]['t1'] - calculated[1][1]) <= tol)
        detail['soft_glides'] = glides

    frames = settings['output_frames']
    rate, pcm = wavfile.read(files[0][0])
    reference_pcm = np.fromfile(upper_raw, dtype='<f4')
    if any(w.shape != (frames,) or w.dtype != np.float32 for w in (pcm, reference_pcm)):
        raise ValueError('歌唱PCMの長さか型を確認できません')
    pcm_diff = wasm.compare_pcm(pcm, reference_pcm, limits['pcm_abs_tolerance'])
    native, reference = [voice.load_trace(p, frames) for p in (trace, upper_trace)]
    # 最小断面が同率のセル番号は補助情報として保存し、連続値を照合する。
    fields = [name for name in native.dtype.names if name != 'oral_minimum_cell']
    state, errors = voice.compare_traces(native[fields], reference[fields], limits)
    flags.update(
        sample_rates_and_frames=rate == limits['output_rate_hz'] and frames == upper['output_frames']
        and limits['internal_rate_hz'] == source['internal_sample_rate_hz'],
        cli_pcm=pcm_diff['first_frame_over_tolerance'] is None,
        cli_states=state is None,
        same_host_blocks=all(sha256(w) == sha256(files[0][0]) and sha256(t) == sha256(files[0][1])
                             for w, t in files),
    )
    detail.update(pcm=pcm_diff, frames=frames, first_state_over_tolerance=state, state_errors=errors)
    return flags, detail, (source, settings, native, reference, pcm)


def measure(config, base, artifacts, execute, bun, browser):
    execute(['cargo', 'test', '--locked', '-p', 'chimera', '--test', 'russian', '--test', 'syllables'],
            cwd=UPSTREAM, stdout=artifacts / 'upstream-tests.log')
    checks, lyrics, syllables, unavailable = compare_lyrics(config, artifacts, execute)
    probe = shared.build_upstream_probe(voice.PROBE, artifacts, execute, extra_libraries=('serde_json',))
    variants, rendered = {}, {}
    for variant in config['song']:
        name = variant['id']
        flags, variants[name], rendered[name] = measure_song(
            config, variant, syllables[name], base, artifacts / name, probe, execute)
        checks.update({f'{name}/{key}': bool(value) for key, value in flags.items()})
    report = {'checks': checks, 'lyrics': lyrics, 'variants': variants, 'demo_unavailable': unavailable}
    if browser:
        flags, report['browser'] = browser_song.browser_measure(config, rendered, artifacts, execute, bun, case_path=CASE)
        checks.update(flags)
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
    base = WORKSPACE / 'cases' / config['voice_case']
    modules = (voice, frication, song_plan, timing, shared, browser_song, wasm)
    sources = [CASE, base, voice.PROBE, Path(__file__).resolve(), *shared.candidate_sources(),
               *(Path(module.__file__) for module in modules), WORKSPACE / 'tools/upstream_baseline.py',
               WORKSPACE / 'tools/measure_vowel_voice.py']
    upstream_paths = ('crates/chimera/src/phonetics/russian.rs', 'crates/chimera/src/phonetics/syllables.rs',
                      'crates/chimera/src/phonetics/sing.rs', 'crates/chimera/src/phonetics/songs.rs',
                      'crates/chimera/tests/russian.rs', 'crates/chimera/tests/syllables.rs',
                      'crates/chimera-cli/src/main.rs', 'crates/chimera-cli/src/render.rs')
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
        args.run_id, CASE, sources, metadata,
        lambda out, run: measure(config, base, out, run, bun, not args.native_only), command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
