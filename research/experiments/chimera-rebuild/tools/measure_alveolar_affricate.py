"""歯茎・そり舌破擦音の閉鎖、乱流と中国語歌唱の有気対立を固定上流に照合する。"""

import argparse
from pathlib import Path
import re
import shutil
import subprocess

import numpy as np
from scipy.io import wavfile

import measure_alveolar_stop as cells
import measure_alveolopalatal_affricates as affricates
import measure_alveolopalatal_fricatives as bodies
import measure_bilabial_stop as voice
import measure_postalveolar_affricate as traces
import measure_sibilant as frication
import measure_speech_timing as timing
import measure_uniform_tube as shared
import measure_velar_fricative as constriction
import measure_velar_stops as browser_song
import measure_wasm_fixed as wasm
from measure_worklet_fixed import ROOT, web_sources
from upstream_baseline import UPSTREAM, WORKSPACE, sha256

CASE = WORKSPACE / 'cases/alveolar-affricate.json'
RETROFLEX_CASE = WORKSPACE / 'cases/retroflex-affricate.json'
CLI = ['cargo', 'run', '--locked', '--release', '-p', 'vocal-cli', '--']


def expected_gestures(span, tip, rate, pronunciation, palatalized):
    a, b = span['t0'], span['t1']
    duration = b - a
    split = a + .45 * duration
    release = max(a, split - .015)
    ipa = span['ipa']
    main = {'label': ipa, 'strength': 40, 'rampIn': .030 / rate,
            'rampOut': .018 / rate, 'releaseHold': .045 / rate}
    auxiliary = {'label': 'ts', 'strength': 1.2, 'rampIn': .05 / rate,
                 'rampOut': .05 / rate, 'targets': {'tongue_body_x_cm': 3.2, 'tongue_body_y_cm': 7.4}}
    if ipa == 'tʂ':
        close_target = {'tongue_tip_x_cm': 5.45, 'tongue_tip_y_cm': 10.05, 'tip_curl': .95}
        jet_target = {'tongue_tip_x_cm': 5.45, 'tongue_tip_y_cm': tip, 'tip_curl': .90}
    else:
        close_target = {'tongue_tip_x_cm': 6.25, 'tongue_tip_y_cm': 9.68}
        jet_target = {'tongue_tip_x_cm': 6.3, 'tongue_tip_y_cm': tip, 'jaw_cm': .3}
    gestures = [{**main, 't0': a - .031, 't1': max(a + .010, split - .020),
                 'speed': 2, 'targets': close_target}]
    if ipa == 'ts':
        gestures.append({**auxiliary, 't0': a, 't1': split})
    gestures.append({**main, 't0': release - .008, 't1': max(release + .010, b),
                     'speed': 1.4, 'targets': jet_target})
    if ipa == 'ts':
        gestures.append({**auxiliary, 't0': release, 't1': b})
    if pronunciation:
        start, end = a + .25 * duration, b + pronunciation['plateau_past_end_seconds']
        fall, opening = pronunciation['ramp_out_seconds'], pronunciation['abduction_cm2']
    else:
        start = a + .15 * duration
        end, fall, opening = max(start, b - .03), min(.03, b - start), .36
    gestures.append({'label': 'aspiration', 'strength': 6, 't0': start, 't1': end,
                     'rampIn': .035 / rate, 'rampOut': fall / rate, 'targets': {'abduction_cm2': opening}})
    if palatalized:
        gestures.append({'label': 'palatalized', 'strength': 3, 't0': a, 't1': end + fall,
                         'rampIn': .04 / rate, 'rampOut': .04 / rate,
                         'targets': {'tongue_body_x_cm': 3.8, 'tongue_body_y_cm': 7.95}})
    return gestures


def compare_plan(config, variant, settings, upper):
    limits = config['measurement']
    tolerance = limits['gesture_abs_tolerance']
    score = settings.get('song')
    source = settings
    if score:
        source = {**settings, 'speech': {'utterances': [
            {'segments': phrase['timing']['segments']} for phrase in score['plan']['phrases']]}}
    parts, report = frication.compare_plans(source, upper, tolerance)
    ipa = config.get('phoneme', 'ts')
    positions = [index for index, part in enumerate(parts) if part['ipa'] == ipa]
    lyrics = variant.get('syllables', [None])
    if len(positions) != len(lyrics):
        raise ValueError(f'登録した数の /{ipa}/ 区間がありません')
    rate = variant.get('rate', 1)
    tip = bodies.body_value(variant.get('body', 'male'), config['release_tip_cm'])
    expected, spans, note_checks = [], {}, []
    lengths = []
    for note, (character, position) in enumerate(zip(lyrics, positions, strict=True)):
        part = parts[position]
        entry = config['syllables'].get(character)
        span = part['t1'] - part['t0']
        duration = variant.get('onset_duration_seconds', (entry or variant)['duration_seconds'])
        lengths.append([span, duration / rate])
        gestures = expected_gestures(part, tip, rate, entry, variant.get('palatalized'))
        expected.extend(gestures)
        spans[character or 'ipa'] = part
        if score:
            syllable = score['syllables'][note]
            onset = syllable['onset']
            written = score['plan']['notes'][note]
            beat = limits['start_seconds'] + note * 60 / limits['bpm'] * limits['beats_per_note']
            hz = 440 * 2 ** ((limits['midi'] - 69) / 12)
            note_checks.append(
                syllable['text'] == character and len(onset) == 1 and onset[0]['ipa'] == ipa
                and onset[0].get('aspirated') == entry['aspirated']
                and onset[0].get('vot') == entry['vot_seconds']
                and onset[0].get('dur') == variant.get('onset_duration_seconds', entry['explicit_duration_seconds'])
                and syllable['nucleus']['ipa'] == parts[position + 1]['ipa'] == entry['nucleus']
                and all(abs(value - beat) <= tolerance for value in
                        (part['t1'], parts[position + 1]['t0'], written['beat_seconds']))
                and abs(written['f0_hz'] - hz) <= tolerance)
    actual = [g for g in settings['gestures'] if g['label'] in (ipa, 'aspiration', 'palatalized')]
    first, error = timing.compare(actual, expected, tolerance)
    checks = {'upstream_plan': report['passed'], 'registered_gestures': first is None,
              'registered_durations': all(abs(a - b) <= tolerance for a, b in lengths)}
    if score:
        checks['syllable_features_and_beat'] = (all(note_checks)
            and len(score['syllables']) == len(score['plan']['notes']) == len(lyrics)
            and not score['plan']['unavailable_speech_symbols'])
    report.update(spans=spans, release_tip_y_cm=tip, duration_actual_expected_seconds=lengths,
                  gestures=actual, first_registered_difference=first, maximum_registered_error=error)
    return checks, report


def sung_events(trace, span, closed, limits):
    rate = limits['output_rate_hz']
    time = (trace['frame'] + 1) / rate
    a, b = span['t0'], span['t1']
    split = np.searchsorted(time, a + .45 * (b - a))
    start = max(split, closed.get('release_frame', 0))
    pulse, period = affricates.periodic_onset(
        trace, time, start, b + limits['voicing_search_padding_seconds'], limits)
    noise_source = limits.get('release_noise_source', 'teeth_noise')
    jet = np.flatnonzero((trace['frame'] >= start) & (time < b + limits['release_window_padding_seconds'])
                         & (trace[f'{noise_source}_level'] > 0))
    window = (a <= time) & (time < b + limits['voicing_search_padding_seconds'])
    return {'start_frame': int(start), 'pulse_onset_frame': pulse, 'pulse_period_frames': period,
            'pulse_from_planned_end_ms': None if pulse is None else float((time[pulse] - b) * 1e3),
            'first_jet_frame': int(jet[0]) if jet.size else None, 'jet_frames': int(jet.size),
            'peak_abduction_cm2': float(trace['abduction_cm2'][window].max())}


def compare_variant(config, variant, source, out, probe, execute):
    out.mkdir()
    limits = config['measurement']
    is_song = 'score' in source
    request = out / 'case.json'
    key = 'song_voice' if is_song else 'speech_voice'
    timing.write(request, {'id': variant['id'], 'upstream_revision': config['upstream_revision'], key: source})
    settings, trace, files, upper_trace, upper_raw, upper_plan = voice.capture(
        request, limits['host_block_frames'], out, execute, (), probe=probe)
    reference = timing.read(upper_plan)
    checks, plan = compare_plan(config, variant, settings, reference)
    if is_song and 'lyrics' in source['score']:
        lyrics = out / 'upstream-syllables.json'
        execute(['cargo', 'run', '--locked', '--release', '-p', 'chimera-cli', '--',
                 'syllables', variant['lyrics']], cwd=UPSTREAM, stdout=lyrics)
        difference, error = timing.compare(settings['song']['syllables'], timing.read(lyrics),
                                           limits['gesture_abs_tolerance'])
        plan.update(first_syllable_difference=difference, maximum_syllable_error=error)
        checks['upstream_lexical_syllables'] = difference is None
    frames = settings['output_frames']
    native, upper = (traces.load_trace(path, frames) for path in (trace, upper_trace))
    fields = [name for name in native.dtype.names if name != 'oral_minimum_cell']
    mismatches, errors = frication.source_comparison(native[fields], upper[fields], limits)
    cell_diff = cells.compare_cell_minima(native, upper, {
        **limits, 'geometry_absolute_tolerance': limits['geometry_abs_tolerance']})
    rate, pcm = wavfile.read(files[0][0])
    upstream_pcm = np.fromfile(upper_raw, dtype='<f4')
    if any(wave.shape != (frames,) or wave.dtype != np.float32 or not np.isfinite(wave).all()
           for wave in (pcm, upstream_pcm)):
        raise ValueError('PCMの長さ・型・有限性が登録条件と異なります')
    pcm_diff = wasm.compare_pcm(pcm, upstream_pcm, limits['pcm_abs_tolerance'])
    events = {}
    for key, span in plan['spans'].items():
        rows = []
        for data, wave in ((native, pcm), (upper, upstream_pcm)):
            row = affricates.observe(data, wave, span, limits)
            if 'tongue_tip_curl' in data.dtype.names and row.get('release_frame') is not None:
                time = (data['frame'] + 1) / rate
                closure = slice(row['closure_frame'], row['release_frame'])
                released = ((data['frame'] >= row['release_frame'])
                            & (time < span['t1'] + limits['release_window_padding_seconds']))
                row['median_closed_curl'] = float(np.median(data['tongue_tip_curl'][closure]))
                row['median_release_curl'] = float(np.median(data['tongue_tip_curl'][released])) if released.any() else None
                row['teeth_jet_frames'] = int(np.count_nonzero(data['teeth_noise_level'][released] > 0))
            if is_song:
                row['singing'] = sung_events(data, span, row, limits)
            rows.append(row)
        events[key] = rows
    checks.update(
        trace=not mismatches and cell_diff['passed'], pcm=pcm_diff['first_frame_over_tolerance'] is None,
        sample_rates_and_frames=(rate == limits['output_rate_hz'] and frames == reference['output_frames']
                                 and source['internal_sample_rate_hz'] == limits['internal_rate_hz']),
        host_blocks=all(sha256(wave) == sha256(files[0][0]) and sha256(csv) == sha256(files[0][1])
                        for wave, csv in files),
    )
    report = {'plan': plan, 'trace_errors': errors, 'earliest_trace_differences': mismatches,
              'oral_minimum_cells': cell_diff, 'frames': frames, 'events': events, 'pcm': pcm_diff}
    retroflex = config.get('phoneme') == 'tʂ'
    if variant.get('check_events'):
        checks['closure_then_jet_then_pulse'] = all(x['passed'] for x in events['ipa'])
    if retroflex or variant.get('check_events'):
        scale = bodies.body_value(variant.get('body', 'male'), bodies.BODY_SCALES)
        bands = [frication.independent_band(row, limits['independent_band_tolerance'], body_scale=scale)
                 for row in (native, upper)]
        checks['independent_teeth_band'] = all(row['passed'] or (retroflex and row['registered_frames'] == 0)
                                              for row in bands)
        report['teeth_band'] = bands
    if retroflex:
        registrations = [constriction.constriction_registration(row, scale, limits['gain_abs_tolerance'])[0]
                         for row in (native, upper)]
        checks['independent_constriction_registration'] = all(row['passed'] for row in registrations)
        report['constriction_registration'] = registrations
    return checks, report, (source, settings, native, upper, pcm)


def solo_comparison(variants, limits, names=('zi-solo', 'ci-solo')):
    event_pairs = [next(iter(variants[name]['events'].values())) for name in names]
    source = limits.get('release_noise_source', 'teeth_noise').removesuffix('_noise')
    minimum_noise_frames = limits.get('minimum_release_noise_frames',
                                     limits.get('minimum_teeth_active_frames_after_release'))
    frame_key = f'{source}_jet_frames'
    rows = []
    for plain, aspirated in zip(*event_pairs, strict=True):
        left, right = plain['singing'], aspirated['singing']
        a, b = (row['pulse_from_planned_end_ms'] for row in (left, right))
        rows.append({'pulse_delay_from_planned_end_ms': None if a is None or b is None else b - a,
                     'effective_abduction_increase_cm2': right['peak_abduction_cm2'] - left['peak_abduction_cm2'],
                     frame_key: [left['jet_frames'], right['jet_frames']]})
    commands = []
    for name in names:
        plan = variants[name]['plan']
        aspiration = next(g for g in plan['gestures'] if g['label'] == 'aspiration')
        span = next(iter(plan['spans'].values()))
        commands.append(1e3 * (aspiration['t1'] + aspiration['rampOut'] - span['t1']))
    difference = commands[1] - commands[0]
    return {'aspiration_command_difference': abs(difference - limits['expected_command_release_difference_ms']) < 1e-9,
            'later_periodicity': all(row['pulse_delay_from_planned_end_ms'] is not None
                and row['pulse_delay_from_planned_end_ms'] >= limits['minimum_aspirated_pulse_delay_ms'] for row in rows),
            f'larger_opening_and_{source}_jet': all(row['effective_abduction_increase_cm2'] > 0
                and min(row[frame_key]) >= minimum_noise_frames for row in rows)
            }, {'command_past_end_ms': commands, 'command_difference_ms': difference, 'measured': rows}


def measure(config, bases, artifacts, execute, bun, browser, case_path):
    suites = ('mandarin', 'affricates', 'consonant_artifacts')
    if case_path == RETROFLEX_CASE:
        suites += ('sounds', 'apical')
    execute(['cargo', 'test', '--locked', '-p', 'chimera',
             *(argument for suite in suites for argument in ('--test', suite))],
            cwd=UPSTREAM, stdout=artifacts / 'upstream-tests.log')
    probe = shared.build_upstream_probe(voice.PROBE, artifacts, execute, extra_libraries=('serde_json',))
    limits = config['measurement']
    checks, variants, browser_inputs = {}, {}, {}
    for variant in [*config['speech'], *config['song']]:
        name = variant['id']
        if 'syllables' in variant:
            source = {**timing.read(bases['song'])['song_voice'], 'body': 'male'}
            source['score'] = {**source['score'], 'id': name,
                               'bpm': limits['bpm'], 'start_seconds': limits['start_seconds'],
                               'notes': [{'midi': limits['midi'], 'beats': limits['beats_per_note']}
                                         for _ in variant['syllables']]}
            if 'lyrics' in variant:
                source['score']['lyrics'] = variant['lyrics']
            else:
                character, = variant['syllables']
                pronunciation = config['syllables'][character]
                onset = {'ipa': config['phoneme'], 'dur': variant['onset_duration_seconds'],
                         'aspirated': pronunciation['aspirated']}
                if pronunciation['vot_seconds'] is not None:
                    onset['vot'] = pronunciation['vot_seconds']
                del source['score']['lyrics']
                source['score']['syllables'] = [{
                    'text': character, 'onset': [onset], 'nucleus': {'ipa': pronunciation['nucleus']},
                    'coda': [], 'wordEnd': True,
                }]
        else:
            source = {**timing.read(bases['speech'])['speech_voice'], 'body': variant['body']}
            source['input'] = {key: variant[key] for key in ('id', 'text', 'segments', 'rate') if key in variant}
            source['voice'] = {**source['voice'], 'f0_hz': variant['f0_hz']}
            source.pop('turbulence', None)
        flags, variants[name], rendered = compare_variant(config, variant, source, artifacts / name, probe, execute)
        checks.update({f'{name}/{key}': bool(value) for key, value in flags.items()})
        if variant.get('browser'):
            browser_inputs[name] = rendered
    pairs = {}
    for condition, names in config.get('solo_pairs', {'solo': ['zi-solo', 'ci-solo']}).items():
        flags, pairs[condition] = solo_comparison(variants, limits, names)
        checks.update({f'{condition}/{key}': bool(value) for key, value in flags.items()})
    if 'equal_duration' in pairs:
        plans = [variants[name]['plan'] for name in config['solo_pairs']['equal_duration']]
        spans = [next(iter(plan['spans'].values())) for plan in plans]
        targets = [[g for g in plan['gestures'] if g['label'] != 'aspiration'] for plan in plans]
        checks['equal_duration/same_oral_plan_and_boundaries'] = spans[0] == spans[1] and targets[0] == targets[1]
    diagnostic = config['remaining_symbols']
    request = artifacts / 'remaining-symbols.json'
    timing.write(request, {'song_plan': {'scores': [{'lyrics': diagnostic['lyrics'], 'id': 'remaining',
        'bpm': limits['bpm'], 'start_seconds': limits['start_seconds'], 'notes': [
            {'midi': limits['midi'], 'beats': limits['beats_per_note']} for _ in range(diagnostic['syllables'])]}]}})
    planned = artifacts / 'remaining-symbols-plan.json'
    execute([*CLI, 'inspect', str(request)], stdout=planned)
    remaining = timing.read(planned)['scores'][0]['plan']['unavailable_speech_symbols']
    checks['remaining_symbols'] = remaining == diagnostic['expected']
    report = {'checks': checks, 'variants': variants, 'solo_comparison': pairs.get('solo', pairs),
              'unavailable_speech_symbols': remaining}
    if browser:
        flags, report['browser'] = browser_song.browser_measure(
            config, browser_inputs, artifacts, execute, bun, case_path=case_path)
        checks.update(flags)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('--native-only', action='store_true', help='CLIと固定上流だけを計測する')
    parser.add_argument('--retroflex', action='store_true', help='そり舌破擦音 /tʂ/ のケースを使う')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', args.run_id):
        parser.error('実行IDは英数字で始めてください')
    case_path = RETROFLEX_CASE if args.retroflex else CASE
    config = timing.read(case_path)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != config['upstream_revision'] or subprocess.check_output(
            ['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True):
        raise SystemExit('変更のない固定上流版が必要です')
    bases = {kind: WORKSPACE / 'cases' / config[f'{kind}_case'] for kind in ('song', 'speech')}
    modules = (affricates, bodies, cells, constriction, frication, timing, traces, shared, voice, wasm, browser_song)
    sources = [case_path, *bases.values(), voice.PROBE, Path(__file__).resolve(), *shared.candidate_sources(),
               *(Path(module.__file__) for module in modules), WORKSPACE / 'tools/upstream_baseline.py',
               WORKSPACE / 'tools/measure_vowel_voice.py', WORKSPACE / 'tools/measure_song_plan.py',
               WORKSPACE / 'data/mandarin.txt.gz', WORKSPACE / 'data/cmudict.txt.gz']
    upstream_paths = ('crates/chimera-cli/src/render.rs', 'public/data/mandarin.txt.gz',
        *('crates/chimera/' + path for path in ('src/phonetics/ipa.rs', 'src/phonetics/planner.rs',
          'src/phonetics/mandarin.rs', 'src/phonetics/sing.rs', 'src/phonetics/inventory.rs',
          'src/phonetics/syllables.rs', 'src/phonetics/durations.rs', 'src/phonetics/consonantTargets.generated.json',
          'src/voice/human_airway.rs', 'src/voice/human_voice.rs', 'src/airway/network.rs',
          'tests/mandarin.rs', 'tests/affricates.rs', 'tests/consonant_artifacts.rs')))
    if args.retroflex:
        upstream_paths += ('crates/chimera/src/anatomy/human.rs', 'crates/chimera/tests/sounds.rs',
                           'crates/chimera/tests/apical.rs')
    metadata = {'case_id': config['id'], 'revision': config['revision'], 'upstream_revision': revision,
                'upper_source_sha256': {path: sha256(UPSTREAM / path) for path in upstream_paths}}
    bun = ['bun'] if shutil.which('bun') else ['npx', '--yes', '--package=bun@1.4.4', '--', 'bun']
    if not args.native_only:
        sources += [browser_song.KOREAN, browser_song.LIVE, *web_sources(),
                    WORKSPACE / 'tools/measure_worklet_english_body.py']
        metadata.update(node=subprocess.check_output(['node', '--version'], text=True).strip(),
                        bun=subprocess.check_output([*bun, '--version'], text=True).strip())
    return shared.record_measurement(args.run_id, case_path, sources, metadata,
        lambda out, run: measure(config, bases, out, run, bun, not args.native_only, case_path),
        command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
