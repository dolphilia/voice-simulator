"""そり舌接近音の調音と中国語歌唱の頭子音・児化韻尾を固定上流に照合する。"""

import argparse
from pathlib import Path
import re
import shutil
import subprocess

import numpy as np
from scipy.io import wavfile
from scipy.signal import find_peaks

import measure_alveolar_stop as cells
import measure_bilabial_stop as voice
import measure_labial_velar as articulators
import measure_postalveolar_affricate as traces
import measure_retroflex_fricative as apical
import measure_sibilant as frication
import measure_speech_timing as timing
import measure_uniform_tube as shared
import measure_velar_stops as browser_song
import measure_wasm_fixed as wasm
from measure_worklet_fixed import ROOT, web_sources
from upstream_baseline import UPSTREAM, WORKSPACE, sha256

CASE = WORKSPACE / 'cases/retroflex-approximant.json'
CLI = ['cargo', 'run', '--locked', '--release', '-p', 'vocal-cli', '--']
TIP = ('tongue_tip_x_cm', 'tongue_tip_y_cm', 'tongue_tip_curl')


def compare_song_plan(variant, score, spans, parts, gestures, limits):
    tolerance = limits['gesture_abs_tolerance']
    notes = score['plan']['notes']
    syllables = score['syllables']
    symbols = [[row['text'], [p['ipa'] for p in row['onset']], row['nucleus']['ipa'],
                [p['ipa'] for p in row['coda']]] for row in syllables]
    flags = {'registered_syllables': symbols == variant['syllables']
             and [i for i, row in enumerate(syllables) if row.get('melisma')] == variant.get('melisma_notes', [])
             and not score['plan']['unavailable_speech_symbols']}
    beat = limits['start_seconds']
    expected_notes = []
    for midi, beats in zip(variant['midi'], variant['beats'], strict=True):
        end = beat + beats * 60 / limits['bpm']
        expected_notes.append([beat, end, beat, 440 * 2 ** ((midi - 69) / 12)])
        beat = end
    actual_notes = [[n[k] for k in ('beat_seconds', 'beat_end_seconds', 'nucleus_start_seconds', 'f0_hz')]
                    for n in notes]
    difference, _ = timing.compare(actual_notes, expected_notes, tolerance)
    flags['independent_beats_and_midi'] = difference is None
    flags['no_special_nasal_coda_gestures'] = (
        not any(g['label'] in ('nasal vowel', 'coda held', 'coda approach') for g in gestures)
        and all(row.get('nasalLead') is None for row in syllables if row['coda']))
    events = []
    for span, ref in zip(spans, variant['rhotic'], strict=True):
        i = ref['note']
        a, b = span['t0'], span['t1']
        start, end, _, hz = expected_notes[i]
        note = notes[i]
        if ref['role'] == 'onset':
            expected_end = start
            neighbor = parts[parts.index(span) + 1]
            boundary = neighbor['ipa'] == 'ʅ' and abs(neighbor['t0'] - b) <= tolerance
        else:
            if i + 1 < len(expected_notes):
                expected_end = expected_notes[i + 1][0] - ref['next_onset_seconds']
                next_phone = parts[parts.index(span) + 1]
                flags[f'{i}/next_onset'] = next_phone['ipa'] == 'm' and abs(next_phone['t0'] - b) <= tolerance
            else:
                expected_end = end - min(.05, .3 * (end - start))
            neighbor = parts[parts.index(span) - 1]
            boundary = (neighbor['ipa'] == 'a' and abs(neighbor['t1'] - a) <= tolerance
                        and abs(note['nucleus_end_seconds'] - a) <= tolerance)
        pitch = [g['targets']['f0_hz'] for g in gestures if g['label'] == 'pitch'
                 and abs(g['t0'] - a) <= tolerance and abs(g['t1'] - b) <= tolerance]
        flags[f'{i}/{ref["role"]}_boundaries_and_pitch'] = (
            boundary and abs(b - expected_end) <= tolerance
            and len(pitch) == 1 and abs(pitch[0] - hz) <= tolerance)
        events.append({**ref, 'span': span, 'beat_seconds': start,
                       'expected_end_seconds': expected_end, 'pitch_hz': pitch})
    return flags, {'syllables': symbols, 'events': events, 'notes': notes, 'beat_difference': difference}


def compare_plan(config, variant, settings, upper):
    limits = config['measurement']
    tolerance = limits['gesture_abs_tolerance']
    song = settings.get('song')
    source = settings
    if song is not None:
        source = {**settings, 'speech': {'utterances': [
            {'segments': phrase['timing']['segments']} for phrase in song['plan']['phrases']]}}
    parts, report = frication.compare_plans(source, upper, tolerance)
    spans = [part for part in parts if part['ipa'] == 'ɻ']
    count = len(variant['rhotic']) if song is not None else 1
    if len(spans) != count:
        raise ValueError('事前登録した数の /ɻ/ 区間を計画から取得できません')
    rate = variant.get('rate', 1)
    duration = (limits['sung_rhotic_seconds'] if song else variant['duration_seconds']) / rate
    expected = []
    for span in spans:
        a, b = span['t0'], span['t1']
        expected.append({'label': 'ɻ', 't0': a - .008, 't1': max(a + .01, b), 'rampIn': .030 / rate,
                         'rampOut': .018 / rate, 'releaseHold': .045 / rate, 'speed': 1.3, 'strength': 40,
                         'targets': {'tongue_tip_x_cm': 5.4, 'tongue_tip_y_cm': 9.55, 'tip_curl': 1.0}})
        if variant.get('palatalized'):
            expected.append({'label': 'palatalized', 't0': a, 't1': b, 'rampIn': .04 / rate,
                             'rampOut': .04 / rate, 'strength': 3,
                             'targets': {'tongue_body_x_cm': 3.8, 'tongue_body_y_cm': 7.95}})
    gestures = settings['gestures']
    observed = [g for g in gestures if g['label'] in ('ɻ', 'palatalized')]
    first, error = timing.compare(observed, expected, tolerance)
    flags = {'upstream_plan': report['passed'], 'independent_gestures': first is None,
             'registered_duration': all(abs(p['t1'] - p['t0'] - duration) <= tolerance for p in spans)}
    report.update(spans=spans, parts=parts, first_registered_difference=first,
                  maximum_registered_error=error, actual_gestures=observed)
    if song is not None:
        more, report['song'] = compare_song_plan(variant, song, spans, parts, gestures, limits)
        flags.update(more)
    elif variant.get('final'):
        release = next(g for g in gestures if g['label'] == 'exhale')
        delay = release['t0'] - spans[0]['t1']
        flags['sonorant_exhale_delay'] = abs(delay - .045) <= tolerance
        report['exhale_delay_seconds'] = delay
    return flags, report


def cycle_across_boundary(trace, time, boundary, limits):
    padding = limits['boundary_period_search_seconds']
    start, end = np.searchsorted(time, [boundary - padding, boundary + padding])
    peaks = start + find_peaks(trace['glottal_area_cm2'][start:end],
                               prominence=limits['minimum_glottal_area_peak_prominence_cm2'])[0]
    for left, right in zip(peaks[:-1], peaks[1:], strict=True):
        if time[left] < boundary <= time[right]:
            interval = float(time[right] - time[left])
            ratio = interval * float(np.mean(trace['glottal_f0_hz'][[left, right]]))
            voicing = float(np.min(trace['glottal_voicing'][left:right + 1]))
            lo, hi = limits['period_to_f0_ratio']
            return {'frames': [int(left), int(right)], 'milliseconds': 1e3 * interval,
                    'period_to_f0_ratio': ratio, 'minimum_voicing': voicing,
                    'passed': lo <= ratio <= hi and voicing >= limits['minimum_center_voicing']}
    return {'passed': False, 'reason': '境界をまたぐ2連続の声門面積ピークがありません'}


def observe(trace, pcm, span, limits):
    time = (trace['frame'] + 1) / limits['output_rate_hz']
    a, b = span['t0'], span['t1']
    lo, hi = (a + fraction * (b - a) for fraction in limits['center_fraction'])
    window = (time >= lo) & (time < hi)
    fields = (*TIP, 'glottal_voicing', 'abduction_cm2', 'glottal_f0_hz')
    center = {field: float(np.median(trace[field][window])) for field in fields}
    area = {field: float(trace[field][window].min()) for field in
            ('oral_minimum_cm2', 'pharynx_minimum_cm2', 'lip_minimum_cm2')}
    return {'center': center, 'minimum_area_cm2': area,
            'velum_port_median_cm2': float(np.median(trace['velum_port_area_cm2'][window]))
            if 'velum_port_area_cm2' in trace.dtype.names else None,
            'center_pcm_rms': float(np.sqrt(np.mean(pcm[window].astype(float)**2))),
            'passed': min(area.values()) > limits['closed_area_cm2']
            and center['tongue_tip_curl'] >= limits['minimum_center_curl']
            and center['glottal_voicing'] >= limits['minimum_center_voicing']}


def compare_variant(config, variant, source, out, probe, execute):
    limits = config['measurement']
    out.mkdir()
    is_song = 'score' in source
    path = out / 'case.json'
    key = 'song_voice' if is_song else 'speech_voice'
    timing.write(path, {'id': variant['id'], 'upstream_revision': config['upstream_revision'], key: source})
    settings, trace, files, upper_trace, raw, upper_plan = voice.capture(
        path, limits['host_block_frames'], out, execute, (), probe=probe)
    reference = timing.read(upper_plan)
    flags, plan = compare_plan(config, variant, settings, reference)
    if is_song:
        lexical = out / 'upstream-syllables.json'
        execute(['cargo', 'run', '--locked', '--release', '-p', 'chimera-cli', '--', 'syllables', variant['lyrics']],
                cwd=UPSTREAM, stdout=lexical)
        diff, error = timing.compare(settings['song']['syllables'], timing.read(lexical), limits['gesture_abs_tolerance'])
        plan.update(first_syllable_difference=diff, maximum_syllable_error=error)
        flags['upstream_lexical_syllables'] = diff is None
    frames = settings['output_frames']
    native, upper = (traces.load_trace(p, frames) for p in (trace, upper_trace))
    fields = [name for name in native.dtype.names if name != 'oral_minimum_cell']
    mismatch, errors = frication.source_comparison(native[fields], upper[fields], limits)
    cell_diff = cells.compare_cell_minima(native, upper, {
        **limits, 'geometry_absolute_tolerance': limits['geometry_abs_tolerance']})
    rate, pcm = wavfile.read(files[0][0])
    upper_pcm = np.fromfile(raw, dtype='<f4')
    if any(wave.shape != (frames,) or wave.dtype != np.float32 or not np.isfinite(wave).all()
           for wave in (pcm, upper_pcm)):
        raise ValueError('PCMの長さ・型・有限性が登録条件と異なります')
    pcm_diff = wasm.compare_pcm(pcm, upper_pcm, limits['pcm_abs_tolerance'])
    flags.update(
        trace=not mismatch and cell_diff['passed'], pcm=pcm_diff['first_frame_over_tolerance'] is None,
        sample_rates_and_frames=(rate == limits['output_rate_hz'] and frames == reference['output_frames']
                                 and source['internal_sample_rate_hz'] == limits['internal_rate_hz']),
        host_blocks=all(sha256(wave) == sha256(files[0][0]) and sha256(csv) == sha256(files[0][1])
                        for wave, csv in files),
    )
    report = {'plan': plan, 'first_trace_differences': mismatch, 'trace_errors': errors,
              'oral_minimum_cells': cell_diff, 'pcm': pcm_diff, 'frames': frames}
    if plan['spans']:
        observations, spring = [], []
        for data, wave in ((native, pcm), (upper, upper_pcm)):
            curl = np.empty(frames, dtype=[('tip_curl', 'f8')])
            curl['tip_curl'] = data['tongue_tip_curl']
            spring.append(articulators.articulator_spring(
                curl, settings, {'tip_curl': source['posture']['tip_curl']}, rate,
                limits['curl_spring_frequency_hz'], limits['curl_spring_abs_tolerance']))
            rows = [observe(data, wave, span, limits) for span in plan['spans']]
            observations.append(rows)
            if is_song:
                time = (data['frame'] + 1) / rate
                for event, row in zip(plan['song']['events'], rows, strict=True):
                    span = event['span']
                    if event['role'] == 'coda':
                        row['boundary_cycle'] = cycle_across_boundary(data, time, span['t0'], limits)
                    if event.get('apical'):
                        row['apical'], = apical.apical_vowels(data, time, wave, [event['beat_seconds']], limits)
        flags['independent_curl_dynamics'] = all(row['passed'] for row in spring)
        if variant.get('check_center'):
            flags['open_and_voiced_center'] = all(row[0]['passed'] for row in observations)
        for i, event in enumerate(variant.get('rhotic', [])):
            if event.get('check_continuity'):
                flags['open_and_voiced_coda'] = all(row[i]['passed'] for row in observations)
                flags['pulse_spans_vowel_coda_boundary'] = all(row[i]['boundary_cycle']['passed'] for row in observations)
            if event.get('apical'):
                pairs = [row[i]['apical'] for row in observations]
                flags['apical_continuity'] = all(
                    all(value <= limits['apical_max_drift'][axis] for axis, value in obs['drift'].items())
                    and obs['periodicity'] >= limits['minimum_apical_periodicity'] for obs in pairs)
        report.update(observations=observations, independent_curl_dynamics=spring)
    return flags, report, (source, settings, native, upper, pcm)


def measure(config, bases, artifacts, execute, bun, browser):
    execute(['cargo', 'test', '--locked', '-p', 'chimera', '--test', 'mandarin',
             '--test', 'apical', '--test', 'sounds'], cwd=UPSTREAM, stdout=artifacts / 'upstream-tests.log')
    probe = shared.build_upstream_probe(voice.PROBE, artifacts, execute, extra_libraries=('serde_json',))
    limits = config['measurement']
    checks, variants, rendered = {}, {}, {}
    for variant in [*config['speech'], *config['song']]:
        name = variant['id']
        if 'lyrics' in variant:
            source = {**timing.read(bases['song'])['song_voice'], 'body': 'male'}
            source['score'] = {**source['score'], 'id': name, 'lyrics': variant['lyrics'],
                               'bpm': limits['bpm'], 'start_seconds': limits['start_seconds'],
                               'notes': [{'midi': midi, 'beats': beats} for midi, beats in
                                         zip(variant['midi'], variant['beats'], strict=True)]}
        else:
            source = {**timing.read(bases['speech'])['speech_voice'], 'body': variant['body']}
            source['input'] = {key: variant[key] for key in ('id', 'text', 'rate')}
            source['voice'] = {**source['voice'], 'f0_hz': variant['f0_hz']}
            source.pop('turbulence', None)
        flags, variants[name], replay = compare_variant(config, variant, source, artifacts / name, probe, execute)
        checks.update({f'{name}/{key}': bool(value) for key, value in flags.items()})
        if variant.get('browser'):
            rendered[name] = replay
    rhotic, control = (variants[name]['plan'] for name in ('nar-followed', 'na-followed'))
    vowel_shortening = (control['song']['notes'][0]['nucleus_end_seconds']
                        - rhotic['song']['notes'][0]['nucleus_end_seconds'])
    next_onsets = [next(p['t0'] for p in row['parts'] if p['ipa'] == 'm') for row in (rhotic, control)]
    tol = limits['gesture_abs_tolerance']
    checks['erhua_replaces_end_of_vowel'] = (abs(vowel_shortening - limits['sung_rhotic_seconds']) <= tol
                                            and abs(next_onsets[0] - next_onsets[1]) <= tol)
    diagnostic = config['remaining_symbols']
    request = artifacts / 'remaining-symbols.json'
    timing.write(request, {'song_plan': {'scores': [{'lyrics': diagnostic['lyrics'], 'id': 'remaining',
        'bpm': limits['bpm'], 'start_seconds': limits['start_seconds'],
        'notes': [{'midi': 57, 'beats': 1} for _ in range(diagnostic['syllables'])]}]}})
    planned = artifacts / 'remaining-symbols-plan.json'
    execute([*CLI, 'inspect', str(request)], stdout=planned)
    remaining = timing.read(planned)['scores'][0]['plan']['unavailable_speech_symbols']
    checks['remaining_symbols'] = remaining == diagnostic['expected']
    report = {'checks': checks, 'variants': variants, 'vowel_shortening_seconds': vowel_shortening,
              'compared_next_onsets_seconds': next_onsets, 'unavailable_speech_symbols': remaining}
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
    bases = {kind: WORKSPACE / 'cases' / config[f'{kind}_case'] for kind in ('song', 'speech')}
    modules = (apical, articulators, cells, frication, timing, traces, shared, voice, wasm, browser_song)
    sources = [CASE, *bases.values(), voice.PROBE, Path(__file__).resolve(), *shared.candidate_sources(),
               *(Path(module.__file__) for module in modules), WORKSPACE / 'tools/upstream_baseline.py',
               WORKSPACE / 'tools/measure_alveolopalatal_affricates.py',
               WORKSPACE / 'tools/measure_alveolopalatal_fricatives.py',
               WORKSPACE / 'tools/measure_velar_fricative.py', WORKSPACE / 'tools/measure_vowel_voice.py',
               WORKSPACE / 'tools/measure_song_plan.py', WORKSPACE / 'data/mandarin.txt.gz', WORKSPACE / 'data/cmudict.txt.gz']
    upstream_paths = ('crates/chimera-cli/src/render.rs', 'public/data/mandarin.txt.gz',
        *('crates/chimera/' + path for path in ('src/phonetics/ipa.rs', 'src/phonetics/planner.rs',
          'src/phonetics/mandarin.rs', 'src/phonetics/sing.rs', 'src/phonetics/durations.rs',
          'src/phonetics/inventory.rs', 'src/control/articulators.rs', 'src/anatomy/human.rs',
          'src/voice/human_airway.rs', 'src/voice/human_voice.rs', 'tests/mandarin.rs', 'tests/apical.rs',
          'tests/sounds.rs')))
    metadata = {'case_id': config['id'], 'revision': config['revision'], 'upstream_revision': revision,
                'upper_source_sha256': {path: sha256(UPSTREAM / path) for path in upstream_paths}}
    bun = ['bun'] if shutil.which('bun') else ['npx', '--yes', '--package=bun@1.4.4', '--', 'bun']
    if not args.native_only:
        sources += [browser_song.KOREAN, browser_song.LIVE, *web_sources(),
                    WORKSPACE / 'tools/measure_worklet_english_body.py']
        metadata.update(node=subprocess.check_output(['node', '--version'], text=True).strip(),
                        bun=subprocess.check_output([*bun, '--version'], text=True).strip())
    return shared.record_measurement(args.run_id, CASE, sources, metadata,
        lambda out, run: measure(config, bases, out, run, bun, not args.native_only), command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
