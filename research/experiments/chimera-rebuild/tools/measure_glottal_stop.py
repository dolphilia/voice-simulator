"""声門閉鎖音の時間、残留面積、発声復帰を固定上流に照合する。"""

import argparse
from pathlib import Path
import re
import shutil
import subprocess

import numpy as np
from scipy.io import wavfile
from scipy.signal import lfilter

import measure_alveolar_stop as cells
import measure_alveolopalatal_affricates as periods
import measure_alveolopalatal_fricatives as bodies
import measure_bilabial_stop as voice
import measure_glottal_frication as windows
import measure_postalveolar_affricate as traces
import measure_sibilant as frication
import measure_speech_timing as timing
import measure_uniform_tube as shared
import measure_velar_stops as browser_song
import measure_wasm_fixed as wasm
from measure_worklet_fixed import ROOT, web_sources
from upstream_baseline import UPSTREAM, WORKSPACE, sha256

CASE = WORKSPACE / 'cases/glottal-stop.json'


def compare_plan(config, variant, settings, upper):
    limits = config['measurement']
    tolerance = limits['gesture_abs_tolerance']
    score = settings.get('song')
    source = settings
    if score:
        source = {**settings, 'speech': {'utterances': [
            {'segments': p['timing']['segments']} for p in score['plan']['phrases']]}}
    parts, report = frication.compare_plans(source, upper, tolerance)
    found = [i for i, part in enumerate(parts) if part['ipa'] == 'ʔ']
    if len(found) != 1:
        raise ValueError('声門閉鎖音の区間が一件必要です')
    index, = found
    span = parts[index]
    a, b = (span[k] for k in ('t0', 't1'))
    rate = variant.get('rate', 1)
    duration = (limits['sung_duration_seconds'] if score else variant['duration_seconds']) / rate
    expected = [{'label': 'ʔ', 't0': a, 't1': b, 'rampIn': .012 / rate, 'rampOut': .015 / rate,
                 'strength': 8, 'targets': {'closure': 1.0}}]
    actual = [g for g in settings['gestures'] if g['label'] in ('ʔ', 'palatalized')]
    difference, error = timing.compare(actual, expected, tolerance)
    checks = {'upstream_plan': report['passed'], 'independent_closure_gesture': difference is None,
              'registered_duration': span['kind'] == 'glottal' and abs(b - a - duration) <= tolerance}
    report.update(span=span, first_registered_difference=difference, maximum_registered_error=error,
                  closure_gestures=actual)
    if score:
        notes, syllables = score['plan']['notes'], score['syllables']
        note_index = variant['target_note']
        note, syllable = notes[note_index], syllables[note_index]
        beat = limits['start_seconds'] + note_index * 60 / limits['bpm']
        following = parts[index + 1]
        pitch = 440 * 2 ** ((limits['midi'] - 69) / 12)
        checks.update(
            all_lyrics_and_notes=(len(notes) == len(syllables) == variant['notes']
                and ''.join(row['text'] for row in syllables) == variant['lyrics']
                and not score['plan']['unavailable_speech_symbols']),
            lexical_glottal_onset=([s['ipa'] for s in syllable['onset']] == ['ʔ']
                and syllable['text'] == '爱' and syllable['nucleus']['ipa'] == 'aɪ'),
            glottal_onset_hands_over_on_beat=(following['ipa'] == 'a'
                and all(abs(t - beat) <= tolerance for t in
                        (b, following['t0'], note['beat_seconds'], note['nucleus_start_seconds']))
                and abs(note['f0_hz'] - pitch) <= tolerance),
        )
        report.update(note=note, preceding=parts[index - 1] if index else None, first_vowel=following,
                      unavailable_speech_symbols=score['plan']['unavailable_speech_symbols'])
    return checks, report


def independent_closure(trace, settings, source, scale, limits):
    rate = limits['output_rate_hz']
    block = settings['control_block_internal_samples'] // settings['decimation_factor']
    clock = np.arange(0, len(trace), block) / rate
    gesture, = (g for g in settings['gestures'] if g['label'] == 'ʔ')
    a, b = (gesture[k] for k in ('t0', 't1'))
    attack = np.clip((clock - a + gesture['rampIn']) / gesture['rampIn'], 0, 1)
    release = np.clip((clock - b) / gesture['rampOut'], 0, 1)
    envelope = np.where(clock < a, np.sin(attack * np.pi / 2)**2,
                        np.where(clock < b + gesture['rampOut'], np.cos(release * np.pi / 2)**2, 0))
    command = np.repeat(np.minimum(1, .5 * gesture['strength'] * envelope), block)[:len(trace)]
    actual = trace['glottal_closure_command']
    error = float(abs(command - actual).max())
    pole = np.exp(-1 / (limits['closure_smoothing_seconds'] * rate))
    closure = lfilter([1 - pole], [1, -pole], actual)
    chink = (.008 + .03 * source['voice']['breathiness']) * scale**2
    static_gap = lfilter([1 - pole], [1, -pole], trace['abduction_cm2'] + chink)
    retained = 1 - (1 - limits['static_retained_fraction_closed']) * closure
    static_area = static_gap * retained
    silent_phase = trace['glottal_phase'] >= limits['static_sample_phase_threshold']
    count = int(silent_phase.sum())
    area_error = float(abs(static_area[silent_phase] - trace['glottal_area_cm2'][silent_phase]).max(initial=0))
    return closure, {
        'command_absolute_error': error, 'command_passed': error <= limits['independent_command_tolerance'],
        'static_area_absolute_error_cm2': area_error, 'static_sample_count': count,
        'static_area_passed': count >= limits['minimum_static_samples']
        and area_error <= limits['independent_static_area_tolerance_cm2'],
        'peak_smoothed_closure': float(closure.max()), 'minimum_static_retained_fraction': float(retained.min()),
    }


def events(trace, pcm, closure, span, limits):
    rate = limits['output_rate_hz']
    time = (trace['frame'] + 1) / rate
    a, b = (span[k] for k in ('t0', 't1'))
    mid = windows.window(trace, rate, span, limits['center_fraction'])
    earlier = (time >= a + limits['prior_window_seconds'][0]) & (time < a + limits['prior_window_seconds'][1])
    high = np.flatnonzero(closure >= limits['closed_force_threshold'])
    last = int(high[-1]) if high.size else None
    start = max(int(np.searchsorted(time, b)), last + 1 if last is not None else 0)
    pulse, period = periods.periodic_onset(trace, time, start, b + limits['voicing_search_padding_seconds'], limits)
    flow = trace['glottal_flow_cm3_s']
    mid_rms = float(np.sqrt(np.mean(flow[mid]**2)))
    before_rms = float(np.sqrt(np.mean(flow[earlier]**2)))
    return {
        'central_minimum_oral_cm2': float(trace['oral_minimum_cm2'][mid].min()),
        'central_minimum_lip_cm2': float(trace['lip_minimum_cm2'][mid].min()),
        'central_voicing_median': float(np.median(trace['glottal_voicing'][mid])),
        'prior_voicing_median': float(np.median(trace['glottal_voicing'][earlier])),
        'central_peak_glottal_area_cm2': float(trace['glottal_area_cm2'][mid].max()),
        'central_minimum_glottal_area_cm2': float(trace['glottal_area_cm2'][mid].min()),
        'central_flow_rms_cm3_s': mid_rms, 'prior_flow_rms_cm3_s': before_rms,
        'central_to_prior_flow_ratio': mid_rms / before_rms if before_rms > 0 else None,
        'central_pcm_rms': float(np.sqrt(np.mean(pcm[mid].astype(float)**2))),
        'high_closure_frames': int(high.size),
        'first_and_last_high_closure_frame': [int(high[0]), last] if high.size else None,
        'first_recovered_pulse_frame': pulse, 'recovered_period_frames': period,
        'recovery_after_planned_end_ms': None if pulse is None else float((time[pulse] - b) * 1e3),
    }


def compare_variant(config, variant, source, out, probe, execute):
    out.mkdir()
    limits = config['measurement']
    key = 'song_voice' if 'lyrics' in variant else 'speech_voice'
    path = out / 'case.json'
    timing.write(path, {'id': variant['id'], 'upstream_revision': config['upstream_revision'], key: source})
    settings, trace, files, upper_trace, upstream_pcm, upper_plan = voice.capture(
        path, limits['host_block_frames'], out, execute, (), probe=probe)
    reference = timing.read(upper_plan)
    checks, plan = compare_plan(config, variant, settings, reference)
    if 'lyrics' in variant:
        lexical = out / 'upstream-syllables.json'
        execute(['cargo', 'run', '--locked', '--release', '-p', 'chimera-cli', '--', 'syllables', variant['lyrics']],
                cwd=UPSTREAM, stdout=lexical)
        difference, error = timing.compare(settings['song']['syllables'], timing.read(lexical),
                                           limits['gesture_abs_tolerance'])
        plan.update(first_syllable_difference=difference, maximum_syllable_error=error)
        checks['upstream_lexical_syllables'] = difference is None
    frames = settings['output_frames']
    native, upper = (traces.load_trace(p, frames) for p in (trace, upper_trace))
    fields = [name for name in native.dtype.names if name != 'oral_minimum_cell']
    mismatch, errors = frication.source_comparison(native[fields], upper[fields], limits)
    cell_diff = cells.compare_cell_minima(native, upper,
        {**limits, 'geometry_absolute_tolerance': limits['geometry_abs_tolerance']})
    rate, pcm = wavfile.read(files[0][0])
    upper_pcm = np.fromfile(upstream_pcm, dtype='<f4')
    if any(wave.shape != (frames,) or wave.dtype != np.float32 or not np.isfinite(wave).all()
           for wave in (pcm, upper_pcm)):
        raise ValueError('PCMの長さ・型・有限性が登録条件と異なります')
    pcm_diff = wasm.compare_pcm(pcm, upper_pcm, limits['pcm_abs_tolerance'])
    scale = bodies.body_value(source['body'], bodies.BODY_SCALES)
    independent, observed = [], []
    for data, wave in ((native, pcm), (upper, upper_pcm)):
        closure, comparison = independent_closure(data, settings, source, scale, limits)
        independent.append(comparison)
        observed.append(events(data, wave, closure, plan['span'], limits))
    checks.update(
        trace=not mismatch and cell_diff['passed'], pcm=pcm_diff['first_frame_over_tolerance'] is None,
        sample_rates_and_frames=(rate == limits['output_rate_hz'] and frames == reference['output_frames']
                                 and frames == variant.get('output_frames', frames)
                                 and source['internal_sample_rate_hz'] == limits['internal_rate_hz']),
        host_blocks=all(sha256(wave) == sha256(files[0][0]) and sha256(csv) == sha256(files[0][1])
                        for wave, csv in files),
        independent_command=all(x['command_passed'] for x in independent),
        independent_static_area=all(x['static_area_passed'] for x in independent),
        periodicity_returns=all(x['first_recovered_pulse_frame'] is not None for x in observed),
    )
    if variant.get('check_vcv'):
        checks['open_mouth_during_glottal_closure'] = all(
            min(e['central_minimum_oral_cm2'], e['central_minimum_lip_cm2']) > limits['open_oral_minimum_cm2']
            and e['high_closure_frames'] > 0 for e in observed)
        checks['glottal_flow_and_voicing_drop'] = all(
            e['prior_voicing_median'] >= limits['minimum_prior_voicing']
            and e['central_voicing_median'] <= limits['maximum_center_voicing']
            and e['central_to_prior_flow_ratio'] is not None
            and e['central_to_prior_flow_ratio'] <= limits['maximum_center_flow_ratio'] for e in observed)
    result = {'plan': plan, 'first_trace_differences': mismatch, 'trace_errors': errors, 'oral_minimum_cells': cell_diff,
              'pcm': pcm_diff, 'frames': frames, 'independent_closure': independent, 'events': observed}
    return checks, result, (source, settings, native, upper, pcm)


def measure(config, bases, artifacts, execute, bun, browser):
    execute(['cargo', 'test', '--locked', '-p', 'chimera', '--test', 'mandarin', '--test', 'sound_marks',
             '--test', 'er', '--test', 'lung_port'], cwd=UPSTREAM, stdout=artifacts / 'upstream-tests.log')
    probe = shared.build_upstream_probe(voice.PROBE, artifacts, execute, extra_libraries=('serde_json',))
    limits = config['measurement']
    checks, variants, rendered = {}, {}, {}
    for variant in [*config['speech'], *config['song']]:
        name = variant['id']
        if 'lyrics' in variant:
            source = {**timing.read(bases['song'])['song_voice'], 'body': 'male'}
            source['score'] = {**source['score'], 'id': name, 'lyrics': variant['lyrics'],
                               'bpm': limits['bpm'], 'start_seconds': limits['start_seconds'],
                               'notes': [{'midi': limits['midi'], 'beats': 1} for _ in range(variant['notes'])]}
        else:
            source = {**timing.read(bases['speech'])['speech_voice'], 'body': variant['body']}
            source['input'] = {key: variant[key] for key in ('id', 'text', 'segments', 'rate') if key in variant}
            source['voice'] = {**source['voice'], 'f0_hz': variant['f0_hz']}
            source.pop('turbulence', None)
        flags, variants[name], replay = compare_variant(config, variant, source, artifacts / name, probe, execute)
        checks.update({f'{name}/{key}': bool(value) for key, value in flags.items()})
        if variant.get('browser'):
            rendered[name] = replay
    report = {'checks': checks, 'variants': variants}
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
    modules = (bodies, cells, frication, periods, timing, traces, shared, voice, wasm, windows, browser_song)
    sources = [CASE, *bases.values(), voice.PROBE, Path(__file__).resolve(), *shared.candidate_sources(),
               *(Path(module.__file__) for module in modules), WORKSPACE / 'tools/upstream_baseline.py',
               WORKSPACE / 'tools/measure_vowel_voice.py', WORKSPACE / 'tools/measure_song_plan.py',
               WORKSPACE / 'data/mandarin.txt.gz', WORKSPACE / 'data/cmudict.txt.gz']
    upstream_paths = ('crates/chimera-cli/src/render.rs', 'public/data/mandarin.txt.gz',
        *('crates/chimera/' + path for path in ('src/phonetics/ipa.rs', 'src/phonetics/planner.rs',
          'src/phonetics/mandarin.rs', 'src/phonetics/sing.rs', 'src/phonetics/durations.rs',
          'src/phonetics/inventory.rs', 'src/control/score.rs', 'src/sources/glottis.rs', 'src/airway/network.rs',
          'src/voice/human_voice.rs', 'tests/mandarin.rs', 'tests/sound_marks.rs', 'tests/er.rs', 'tests/lung_port.rs')))
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
