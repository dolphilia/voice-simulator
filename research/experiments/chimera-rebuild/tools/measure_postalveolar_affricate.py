"""後部歯茎破擦音とロシア語デモ歌唱を固定上流と照合する。"""

import argparse
import math
from pathlib import Path
import re
import shutil
import subprocess

import numpy as np
from scipy.io import wavfile
from scipy.signal import lfilter

import measure_alveolar_stop as cells
import measure_alveolopalatal_affricates as affricates
import measure_alveolopalatal_fricatives as body
import measure_bilabial_stop as voice
import measure_sibilant as frication
import measure_speech_timing as timing
import measure_uniform_tube as shared
import measure_velar_stops as song
import measure_wasm_fixed as wasm
from measure_worklet_fixed import ROOT, web_sources
from upstream_baseline import UPSTREAM, WORKSPACE, sha256

CASE = WORKSPACE / 'cases/postalveolar-affricate.json'


def compare_plan(config, variant, settings, upper, is_song):
    limits = config['measurement']
    tolerance = limits['gesture_abs_tolerance']
    source = settings
    if is_song:
        score = settings['song']
        source = {**settings, 'speech': {'utterances': [
            {'segments': phrase['timing']['segments']} for phrase in score['plan']['phrases']]}}
    parts, report = frication.compare_plans(source, upper, tolerance)
    positions = [i for i, part in enumerate(parts) if part['ipa'] == 'tʃ']
    if len(positions) != 1:
        raise ValueError('対象の /tʃ/ を一件取得できません')
    index, = positions
    span = parts[index]
    a, b = span['t0'], span['t1']
    duration = b - a
    rate = variant.get('rate', 1)
    split = a + .45 * duration
    opening = a + .15 * duration
    release = max(a, split - .015)
    lip = {'lip_protrusion_cm': .75, 'lip_spread': .2}
    tip = body.body_value(variant['body'], config['release_tip_cm'])
    oral = {'label': 'tʃ', 'strength': 40, 'rampIn': .030 / rate,
            'rampOut': .018 / rate, 'releaseHold': .045 / rate}
    expected = [
        {**oral, 't0': a - .031, 't1': max(a + .010, split - .020), 'speed': 2,
         'targets': {**lip, 'tongue_tip_x_cm': 5.75, 'tongue_tip_y_cm': 10}},
        {**oral, 't0': release - .008, 't1': max(release + .010, b), 'speed': 1.4,
         'targets': {**lip, 'tongue_tip_x_cm': 5.7, 'tongue_tip_y_cm': tip, 'jaw_cm': .35}},
        {'label': 'aspiration', 't0': opening, 't1': max(opening, b - .030),
         'strength': 6, 'rampIn': .035 / rate, 'rampOut': min(.030, b - opening) / rate,
         'targets': {'abduction_cm2': .36}},
    ]
    if variant.get('palatalized'):
        expected.append({'label': 'palatalized', 't0': a, 't1': b,
                         'strength': 3, 'rampIn': .04 / rate, 'rampOut': .04 / rate,
                         'targets': {'tongue_body_x_cm': 3.8, 'tongue_body_y_cm': 7.95}})
    actual = [g for g in settings['gestures'] if g['label'] == 'tʃ'
              or (g['label'] in ('aspiration', 'palatalized') and a <= g['t0'] < b)]
    first, error = timing.compare(actual, expected, tolerance)
    flags = {'upstream_plan': report['passed'], 'registered_gestures': first is None}
    report.update(span=span, planned_split_seconds=split, first_registered_difference=first,
                  maximum_registered_difference=error, release_tip_y_cm=tip, gestures=actual)
    if is_song:
        note = variant['target_lyric_index']
        syllable = score['syllables'][note]
        plan = score['plan']
        beat = plan['notes'][note]['beat_seconds']
        following = parts[index + 1:index + 4]
        durations = [part['t1'] - part['t0'] for part in following[:2]]
        flags.update(
            full_sung_score=(len(plan['notes']) == len(score['syllables']) == variant['syllable_count']
                             and len(plan['phrases']) == variant['phrase_count']
                             and not plan['unavailable_speech_symbols']),
            registered_syllable=(syllable['text'] == variant['target_text']
                                 and [s['ipa'] for s in syllable['onset']] == variant['target_onset']
                                 and syllable['nucleus']['ipa'] == variant['target_nucleus']),
            glides_to_second_beat=([part['ipa'] for part in following] == ['j', 'j', variant['target_nucleus']]
                                   and abs(following[-1]['t0'] - beat) <= tolerance
                                   and all(abs(x - y) <= tolerance for x, y in zip(
                                       durations, variant['glide_durations_seconds'], strict=True))),
        )
        target_duration = variant['target_midi_duration_seconds']
        report.update(lyric=syllable, following_segments=following, nucleus_beat_seconds=beat,
                      syllable_count=len(score['syllables']), phrase_count=len(plan['phrases']),
                      unavailable=plan['unavailable_speech_symbols'])
    elif variant.get('short_control'):
        target_duration = next(segment['dur'] for segment in variant['segments'] if segment['ipa'] == 'tʃ') / rate
        flags['short_opening_has_no_hold'] = any(
            g['label'] == 'aspiration' and abs(g['t0'] - g['t1']) <= tolerance for g in actual)
    else:
        inherent = limits['speech_inherent_duration_seconds']
        minimum = limits['speech_minimum_duration_seconds']
        target_duration = (minimum + (inherent - minimum) * limits['word_medial_factor']) / rate
    flags['registered_duration'] = abs(duration - target_duration) <= tolerance
    return flags, report, span


def spectral_events(pcm, span, limits):
    """上流の10 ms検出器を、独立したフィルタとフレーム集計で計算する。"""
    rate = limits['output_rate_hz']
    frames = round(limits['spectral_frame_seconds'] * rate)
    alpha = -math.expm1(-2 * math.pi * limits['spectral_lowpass_hz'] / rate)
    full = pcm[:pcm.size // frames * frames].astype(float)
    low = lfilter([alpha], [1, alpha - 1], lfilter([alpha], [1, alpha - 1], full))
    power = ((full**2).reshape(-1, frames)).sum(axis=1) + 1e-20
    low_power = ((low**2).reshape(-1, frames)).sum(axis=1) + 1e-20
    level = 10 * np.log10(power / frames)
    ratio = 10 * np.log10(low_power / power)

    def frame(seconds):
        return int(seconds * rate / frames)

    a, b = span['t0'], span['t1']
    search = np.arange(len(level))
    vowel_level = float(level[frame(b + .10):frame(b + .14)].max())
    split_db = limits['spectral_frication_ratio_max_db']
    fric = np.flatnonzero((search >= frame(a)) & (search < frame(b + .10)) & (ratio < split_db)
                          & (level > vowel_level + limits['spectral_frication_level_from_vowel_db']))
    if not fric.size:
        return {'passed': False, 'reason': 'スペクトル条件を満たす摩擦窓がありません'}
    voiced = np.flatnonzero((search > fric[-1]) & (ratio >= split_db)
                            & (level > vowel_level + limits['spectral_voiced_level_from_vowel_db']))
    if not voiced.size:
        return {'passed': False, 'reason': '摩擦後に母音のスペクトル条件を満たす窓がありません'}
    ms = limits['spectral_frame_seconds'] * 1000
    length_ms = (int(fric[-1]) - int(fric[0]) + 1) * ms
    gap_ms = (int(voiced[0]) - int(fric[-1]) - 1) * ms
    return {'passed': length_ms >= limits['spectral_minimum_frication_ms']
                      and gap_ms <= limits['spectral_maximum_gap_ms'],
            'frication_ms': length_ms, 'gap_to_vowel_ms': gap_ms,
            'first_frication_window': int(fric[0]), 'last_frication_window': int(fric[-1]),
            'first_vowel_window': int(voiced[0]), 'vowel_reference_db': vowel_level}


def load_trace(path, frames):
    # 長い譜例でも全行をPythonオブジェクトに展開せず、各系列を検査する。
    with path.open() as stream:
        names = stream.readline().strip().split(',')
        trace = np.loadtxt(stream, delimiter=',', dtype=[(name, 'f8') for name in names])
    if trace.shape != (frames,) or not np.array_equal(trace['frame'], np.arange(frames)):
        raise ValueError('観測された出力フレーム数または連番が一致しません')
    if not all(np.isfinite(trace[name]).all() for name in names):
        raise ValueError('観測系列に非有限値があります')
    return trace


def compare_variant(config, variant, source, is_song, out, probe, execute):
    out.mkdir()
    limits = config['measurement']
    key = 'song_voice' if is_song else 'speech_voice'
    path = out / 'case.json'
    timing.write(path, {'id': variant['id'], 'upstream_revision': config['upstream_revision'], key: source})
    settings, trace, files, upper_trace, upper_raw, upper_plan = voice.capture(
        path, limits['host_block_frames'], out, execute, (), probe=probe)
    upper = timing.read(upper_plan)
    checks, plan, span = compare_plan(config, variant, settings, upper, is_song)
    if is_song:
        upper_lyrics = out / 'upstream-syllables.json'
        execute(['cargo', 'run', '--locked', '--release', '-p', 'chimera-cli', '--',
                 'syllables', source['score']['lyrics']], cwd=UPSTREAM, stdout=upper_lyrics)
        difference, error = timing.compare(
            settings['song']['syllables'], timing.read(upper_lyrics), limits['gesture_abs_tolerance'])
        checks['lexical_syllables'] = difference is None
        plan.update(first_syllable_difference=difference, maximum_syllable_difference=error)
    frames = settings['output_frames']
    native, reference = [load_trace(p, frames) for p in (trace, upper_trace)]
    exclusions = {'oral_minimum_cell'}
    left = [field for field in native.dtype.names if field not in exclusions]
    right = [field for field in reference.dtype.names if field not in exclusions]
    mismatches, errors = frication.source_comparison(native[left], reference[right], limits)
    cell_diff = cells.compare_cell_minima(native, reference, {
        **limits, 'geometry_absolute_tolerance': limits['geometry_abs_tolerance']})
    rate, pcm = wavfile.read(files[0][0])
    upper_pcm = np.fromfile(upper_raw, dtype='<f4')
    if any(samples.shape != (frames,) or samples.dtype != np.float32 for samples in (pcm, upper_pcm)):
        raise ValueError('PCMの長さまたは型が登録条件と異なります')
    pcm_diff = wasm.compare_pcm(pcm, upper_pcm, limits['pcm_abs_tolerance'])
    events = [affricates.observe(data, wave, span, limits)
              for data, wave in ((native, pcm), (reference, upper_pcm))]
    checks.update(
        trace=not mismatches and cell_diff['passed'],
        pcm=pcm_diff['first_frame_over_tolerance'] is None,
        sample_rates_and_frames=rate == limits['output_rate_hz'] and frames == upper['output_frames']
        and source['internal_sample_rate_hz'] == limits['internal_rate_hz'],
        same_host_blocks=all(sha256(w) == sha256(files[0][0]) and sha256(csv) == sha256(files[0][1])
                             for w, csv in files),
    )
    report = {'plan': plan, 'trace_errors': errors, 'oral_minimum_cells': cell_diff, 'frames': frames,
              'first_trace_differences': mismatches, 'events': events, 'pcm': pcm_diff}
    if is_song or variant.get('canonical_vcv'):
        checks['closed_then_teeth_noise_then_periodic'] = all(event['passed'] for event in events)
    if variant.get('canonical_vcv'):
        report['spectral_events'] = [spectral_events(wave, span, limits) for wave in (pcm, upper_pcm)]
        checks['spectral_frication_into_vowel'] = all(row['passed'] for row in report['spectral_events'])
    return checks, report, (source, settings, native, reference, pcm)


def measure(config, bases, artifacts, execute, bun, browser):
    suites = ('affricates', 'consonant_artifacts', 'russian')
    execute(['cargo', 'test', '--locked', '-p', 'chimera',
             *(arg for suite in suites for arg in ('--test', suite))],
            cwd=UPSTREAM, stdout=artifacts / 'upstream-tests.log')
    probe = shared.build_upstream_probe(voice.PROBE, artifacts, execute, extra_libraries=('serde_json',))
    checks, variants, rendered = {}, {}, {}
    for variant in config['speech']:
        name = variant['id']
        source = {**timing.read(bases['speech'])['speech_voice'], 'body': variant['body']}
        source['input'] = {key: variant[key] for key in ('id', 'text', 'segments', 'rate') if key in variant}
        source['voice'] = {**source['voice'], 'f0_hz': variant['f0_hz']}
        source.pop('turbulence', None)
        flags, variants[name], _ = compare_variant(config, variant, source, False, artifacts / name, probe, execute)
        checks.update({f'{name}/{key}': bool(value) for key, value in flags.items()})
    demo = timing.read(bases['russian_demo'])
    variant = config['song']
    name = variant['id']
    lyrics = next(entry['text'] for entry in demo['lyric_cases'] if entry['id'] == 'demo')
    source = {**timing.read(bases['song'])['song_voice'], 'body': variant['body']}
    source['score'] = {**source['score'], 'id': name, 'lyrics': lyrics, 'bpm': demo['demo_score']['bpm'],
                       'start_seconds': variant['start_seconds'],
                       'notes': [{'midi': midi + variant['midi_octave_shift'], 'beats': beats}
                                 for midi, beats in demo['demo_score']['midi_beats']]}
    flags, variants[name], rendered[name] = compare_variant(
        config, variant, source, True, artifacts / name, probe, execute)
    checks.update({f'{name}/{key}': bool(value) for key, value in flags.items()})
    report = {'checks': checks, 'variants': variants}
    if browser:
        flags, report['browser'] = song.browser_measure(config, rendered, artifacts, execute, bun, case_path=CASE)
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
    bases = {kind: WORKSPACE / 'cases' / config[f'{kind}_case'] for kind in ('speech', 'song', 'russian_demo')}
    modules = (affricates, body, cells, frication, shared, song, timing, voice, wasm)
    sources = [CASE, *bases.values(), voice.PROBE, Path(__file__).resolve(), *shared.candidate_sources(),
               *(Path(module.__file__) for module in modules), WORKSPACE / 'tools/upstream_baseline.py',
               WORKSPACE / 'tools/measure_vowel_voice.py', WORKSPACE / 'tools/measure_song_plan.py']
    upstream_paths = ('src/phonetics/ipa.rs', 'src/phonetics/inventory.rs', 'src/phonetics/planner.rs',
                      'src/phonetics/durations.rs', 'src/phonetics/russian.rs', 'src/phonetics/sing.rs',
                      'src/phonetics/songs.rs', 'src/phonetics/consonantTargets.generated.json',
                      'src/voice/human_airway.rs', 'src/airway/network.rs', 'src/control/score.rs',
                      'tests/affricates.rs', 'tests/consonant_artifacts.rs', 'tests/russian.rs')
    metadata = {'case_id': config['id'], 'revision': config['revision'], 'upstream_revision': revision,
                'upper_source_sha256': {p: sha256(UPSTREAM / 'crates/chimera' / p) for p in upstream_paths}}
    bun = ['bun'] if shutil.which('bun') else ['npx', '--yes', '--package=bun@1.4.4', '--', 'bun']
    if args.native_only:
        sources += [WORKSPACE / 'data/cmudict.txt.gz', WORKSPACE / 'data/CMUDICT-LICENSE.txt']
    else:
        sources += [song.KOREAN, song.LIVE, *web_sources(), WORKSPACE / 'tools/measure_worklet_english_body.py']
        metadata.update(node=subprocess.check_output(['node', '--version'], text=True).strip(),
                        bun=subprocess.check_output([*bun, '--version'], text=True).strip())
    return shared.record_measurement(
        args.run_id, CASE, sources, metadata,
        lambda out, run: measure(config, bases, out, run, bun, not args.native_only), command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
