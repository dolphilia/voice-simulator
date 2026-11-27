"""そり舌摩擦音と舌尖母音の歌唱を固定上流に照合する。"""

import argparse
from pathlib import Path
import re
import shutil
import subprocess

import numpy as np
from scipy.io import wavfile

import measure_alveolar_stop as cells
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

CASE = WORKSPACE / 'cases/retroflex-fricative.json'
CELL_REFERENCE = WORKSPACE / 'cases/alveolar-affricate.json'
CLI = ['cargo', 'run', '--locked', '--release', '-p', 'vocal-cli', '--']
SOURCES = ('constriction_noise', 'teeth_noise', 'glottis_noise')
TIP = ('tongue_tip_x_cm', 'tongue_tip_y_cm', 'tongue_tip_curl')


def expected_gestures(ipa, a, b, rate, height, palatalized):
    targets = {'tongue_tip_y_cm': height}
    if ipa == 'ʂ':
        targets.update(tongue_tip_x_cm=5.45, tip_curl=.9)
    else:
        targets.update(tongue_tip_x_cm=6.3, jaw_cm=.3)
    gestures = [{'label': ipa, 't0': a - .008, 't1': max(a + .01, b),
                 'rampIn': .030 / rate, 'rampOut': .018 / rate, 'strength': 40,
                 'releaseHold': .045 / rate, 'speed': 1.3, 'targets': targets}]
    if ipa == 's':
        gestures.append({'label': ipa, 't0': a, 't1': b, 'rampIn': .05 / rate,
                         'rampOut': .05 / rate, 'strength': 1.2,
                         'targets': {'tongue_body_x_cm': 3.2, 'tongue_body_y_cm': 7.4}})
    gestures.append({'label': 'voiceless', 't0': a - .015, 't1': b + .005, 'strength': 6,
                     'rampIn': .03 / rate, 'rampOut': .03 / rate, 'targets': {'abduction_cm2': .30}})
    if ipa == 'ʂ' and palatalized:
        gestures.append({'label': 'palatalized', 't0': a, 't1': b, 'strength': 3,
                         'rampIn': .04 / rate, 'rampOut': .04 / rate,
                         'targets': {'tongue_body_x_cm': 3.8, 'tongue_body_y_cm': 7.95}})
    return gestures


def compare_plan(config, variant, settings, upper):
    tolerance = config['measurement']['gesture_abs_tolerance']
    score = settings.get('song')
    source = settings
    if score:
        source = {**settings, 'speech': {'utterances': [
            {'segments': phrase['timing']['segments']} for phrase in score['plan']['phrases']]}}
    parts, report = frication.compare_plans(source, upper, tolerance)
    spans = [part for part in parts if part['ipa'] in variant['symbols']]
    if [part['ipa'] for part in spans] != variant['symbols']:
        raise ValueError('事前登録した摩擦音を計画から取得できません')
    rate = variant.get('rate', 1)
    duration = config['durations_seconds']['song' if score else 'speech']
    expected, lengths = [], []
    for part in spans:
        ipa, a, b = (part[key] for key in ('ipa', 't0', 't1'))
        height = bodies.body_value(variant['body'], config['tip_y_cm'][ipa])
        expected.extend(expected_gestures(ipa, a, b, rate, height, variant.get('palatalized')))
        lengths.append([b - a, duration[ipa] / rate])
    actual = [g for g in settings['gestures'] if g['label'] in (*variant['symbols'], 'voiceless', 'palatalized')]
    first, error = timing.compare(actual, expected, tolerance)
    flags = {'upstream_plan': report['passed'], 'registered_gestures': first is None,
             'registered_durations': all(abs(a - b) <= tolerance for a, b in lengths)}
    report.update(spans=spans, duration_actual_expected_seconds=lengths, gestures=actual,
                  first_registered_difference=first, maximum_registered_error=error)
    if score:
        syllables, notes = score['syllables'], score['plan']['notes']
        flags['registered_syllables'] = (
            [s['text'] for s in syllables] == variant['characters']
            and [[p['ipa'] for p in s['onset']] for s in syllables] == [[p] for p in variant['symbols']]
            and [s['nucleus']['ipa'] for s in syllables] == variant['nuclei']
            and all(not s['coda'] for s in syllables) and not score['plan']['unavailable_speech_symbols'])
        beat_length = 60 / variant['bpm'] * variant['beats_per_note']
        f0 = 440 * 2 ** ((variant['midi'] - 69) / 12)
        expected_beats = [variant['start_seconds'] + i * beat_length for i in range(len(spans))]
        flags['registered_beats_and_pitch'] = len(notes) == len(spans) and all(
            abs(part['t1'] - beat) <= tolerance and abs(note['beat_seconds'] - beat) <= tolerance
            and abs(note['f0_hz'] - f0) <= tolerance
            for part, note, beat in zip(spans, notes, expected_beats, strict=True))
        report['beats_seconds'] = expected_beats
    return flags, report


def observe_frication(trace, time, span, limits, registration):
    a, b = span['t0'], span['t1']
    lo, hi = (a + (b - a) * fraction for fraction in limits['center_fraction'])
    window = (time >= lo) & (time < hi)
    selected = window & (trace['noise_cell'] >= 0)
    def median(field, mask=window):
        return float(np.median(trace[field][mask])) if mask.any() else None

    return {
        **{key: median(key) for key in (*TIP, 'oral_minimum_cm2', 'abduction_cm2')},
        'noise_teeth_distance_cm': median('noise_teeth_distance_cm', selected),
        'noise_minimum_cm2': median('noise_minimum_cm2', selected),
        'registration_reason_fraction': {key: float(mask[window].mean()) for key, mask in registration.items()},
        'sources': {key: {
            'registered_fraction': float(np.mean(trace[f'{key}_source'][window] != -1)),
            'active_fraction': float(np.mean(trace[f'{key}_level'][window] > 0)),
            'forward_pressure_rms_dyn_cm2': float(np.sqrt(np.mean(trace[f'{key}_forward_pressure'][window]**2))),
        } for key in SOURCES},
    }


def periodicity(pcm, beat, rate, limits):
    start, end = (round((beat + offset) * rate) for offset in limits['periodicity_window_seconds'])
    size, hop = (round(rate * limits[f'periodicity_{key}_seconds']) for key in ('frame', 'hop'))
    low, high = (round(rate * lag) for lag in limits['periodicity_lag_seconds'])
    peaks = []
    for first in range(start, end - size + 1, hop):
        samples = pcm[first:first + size].astype('float64')
        centered = samples - samples.mean()
        corr = np.correlate(centered, centered, mode='full')[size - 1:]
        peaks.append(float(corr[low:high].max() / (corr[0] + 1e-12)))
    return float(np.mean(peaks))


def apical_vowels(trace, time, pcm, beats, limits):
    rows = []
    for beat in beats:
        frames = [int(np.searchsorted(time, beat + offset)) for offset in limits['apical_sample_offsets_seconds']]
        samples = {key: trace[key][frames].tolist() for key in (*TIP, 'lip_aperture_cm', 'lip_protrusion_cm')}
        drift = {key: abs(samples[key][1] - samples[key][0]) for key in TIP}
        rows.append({'samples': samples, 'drift': drift, 'frames': frames,
                     'periodicity': periodicity(pcm, beat, limits['output_rate_hz'], limits)})
    return rows


def compare_variant(config, variant, source, out, probe, execute):
    out.mkdir()
    limits = config['measurement']
    is_song = 'lyrics' in variant
    request = out / 'case.json'
    key = 'song_voice' if is_song else 'speech_voice'
    timing.write(request, {'id': variant['id'], 'upstream_revision': config['upstream_revision'], key: source})
    settings, trace, files, upper_trace, upper_raw, upper_plan = voice.capture(
        request, limits['host_block_frames'], out, execute, (), probe=probe)
    reference = timing.read(upper_plan)
    flags, plan = compare_plan(config, variant, settings, reference)
    if is_song:
        syllables = out / 'upstream-syllables.json'
        execute(['cargo', 'run', '--locked', '--release', '-p', 'chimera-cli', '--', 'syllables', variant['lyrics']],
                cwd=UPSTREAM, stdout=syllables)
        difference, error = timing.compare(settings['song']['syllables'], timing.read(syllables),
                                           limits['gesture_abs_tolerance'])
        plan.update(first_syllable_difference=difference, maximum_syllable_error=error)
        flags['upstream_lexical_syllables'] = difference is None
    frames = settings['output_frames']
    native, upper = (traces.load_trace(path, frames) for path in (trace, upper_trace))
    fields = [name for name in native.dtype.names if name != 'oral_minimum_cell']
    mismatch, errors = frication.source_comparison(native[fields], upper[fields], limits)
    cell_diff = cells.compare_cell_minima(native, upper, {
        'geometry_absolute_tolerance': limits['geometry_abs_tolerance'],
        'closed_area_cm2': timing.read(CELL_REFERENCE)['measurement']['closed_area_cm2'],
    })
    rate, pcm = wavfile.read(files[0][0])
    upper_pcm = np.fromfile(upper_raw, dtype='<f4')
    if any(wave.shape != (frames,) or wave.dtype != np.float32 or not np.isfinite(wave).all()
           for wave in (pcm, upper_pcm)):
        raise ValueError('PCMの長さ・型・有限性が登録条件と異なります')
    pcm_diff = wasm.compare_pcm(pcm, upper_pcm, limits['pcm_abs_tolerance'])
    time = (native['frame'] + 1) / rate
    body_scale = bodies.body_value(variant['body'], bodies.BODY_SCALES)
    events, registrations, bands, vowels = [], [], [], []
    for data, wave in ((native, pcm), (upper, upper_pcm)):
        registration, reasons = constriction.constriction_registration(data, body_scale, limits['gain_abs_tolerance'])
        registrations.append(registration)
        bands.append(frication.independent_band(data, limits['independent_band_tolerance'], body_scale=body_scale))
        events.append({p['ipa']: observe_frication(data, time, p, limits, reasons) for p in plan['spans']})
        if is_song:
            vowels.append(apical_vowels(data, time, wave, plan['beats_seconds'], limits))
    flags.update(
        trace=not mismatch and cell_diff['passed'],
        pcm=pcm_diff['first_frame_over_tolerance'] is None,
        sample_rates_and_frames=(rate == limits['output_rate_hz'] and frames == reference['output_frames']
                                 and source['internal_sample_rate_hz'] == limits['internal_rate_hz']),
        host_blocks=all(sha256(wave) == sha256(files[0][0]) and sha256(csv) == sha256(files[0][1])
                        for wave, csv in files),
        independent_constriction_registration=all(r['passed'] for r in registrations),
        independent_teeth_band=all(r['registered_frames'] == 0 or r['passed'] for r in bands),
    )
    if is_song:
        flags['apical_targets_and_periodicity'] = all(
            all(drift <= limits['apical_max_drift'][name] for name, drift in row['drift'].items())
            and row['periodicity'] >= limits['minimum_vowel_periodicity']
            for series in vowels for row in series)
    report = {'plan': plan, 'first_trace_differences': mismatch, 'trace_errors': errors,
              'oral_minimum_cells': cell_diff, 'pcm': pcm_diff, 'frames': frames,
              'events': events, 'constriction_registration': registrations, 'teeth_band': bands}
    if vowels:
        report['vowels'] = vowels
    return flags, report, (source, settings, native, upper, pcm)


def compare_controls(replays, variants, limits):
    comparisons, muted = [], []
    columns = (*TIP, 'oral_minimum_cm2', 'noise_cell', 'noise_minimum_cm2', 'noise_teeth_distance_cm',
               'teeth_noise_source', 'constriction_noise_source')
    for active, off, events in zip(replays['male-paired'][2:4], replays['male-muted'][2:4],
                                   variants['male-paired']['events'], strict=True):
        s, retro = events['s'], events['ʂ']
        left, right = (row['noise_teeth_distance_cm'] for row in (s, retro))
        comparisons.append({
            'tongue_tip_retreat_cm': s['tongue_tip_x_cm'] - retro['tongue_tip_x_cm'],
            'retroflex_curl': retro['tongue_tip_curl'],
            'noise_teeth_distance_increase_cm': None if left is None or right is None else right - left,
            'retroflex_constriction_active_fraction': retro['sources']['constriction_noise']['active_fraction'],
        })
        muted.append({
            'same_geometry_and_registration': all(np.array_equal(active[key], off[key]) for key in columns),
            'zero_pressure_injection': all(not np.any(off[f'{key}_{direction}_pressure'])
                                           for key in SOURCES for direction in ('forward', 'reverse')),
        })
    flags = {
        'retroflex_posterior_and_curled': all(
            r['tongue_tip_retreat_cm'] >= limits['minimum_posterior_position_difference_cm']
            and r['retroflex_curl'] >= limits['minimum_retroflex_curl'] for r in comparisons),
        'retroflex_narrowest_section_farther_from_teeth': all(
            r['noise_teeth_distance_increase_cm'] is not None
            and r['noise_teeth_distance_increase_cm'] >= limits['minimum_distance_from_teeth_increase_cm']
            for r in comparisons),
        'retroflex_constriction_activity': all(
            r['retroflex_constriction_active_fraction'] >= limits['minimum_constriction_noise_active_fraction']
            for r in comparisons),
        'muted_keeps_geometry_and_registration': all(row['same_geometry_and_registration'] for row in muted),
        'muted_zero_pressure_injection': all(row['zero_pressure_injection'] for row in muted),
    }
    return flags, {'paired': comparisons, 'muted': muted}


def measure(config, bases, artifacts, execute, bun, browser):
    execute(['cargo', 'test', '--locked', '-p', 'chimera', '--test', 'mandarin',
             '--test', 'apical', '--test', 'sounds', '--test', 'consonant_artifacts'],
            cwd=UPSTREAM, stdout=artifacts / 'upstream-tests.log')
    probe = shared.build_upstream_probe(voice.PROBE, artifacts, execute, extra_libraries=('serde_json',))
    checks, variants, replays = {}, {}, {}
    song = config['song']
    for variant in [*config['speech'], song]:
        name = variant['id']
        if 'lyrics' in variant:
            source = {**timing.read(bases['song'])['song_voice'], 'body': song['body']}
            source['score'] = {**source['score'], 'id': name, 'lyrics': song['lyrics'], 'bpm': song['bpm'],
                               'start_seconds': song['start_seconds'], 'notes': [
                                   {'midi': song['midi'], 'beats': song['beats_per_note']} for _ in song['characters']]}
        else:
            source = {**timing.read(bases['speech'])['speech_voice'], 'body': variant['body']}
            source['input'] = {key: variant[key] for key in ('id', 'text', 'rate')}
            source['voice'] = {**source['voice'], 'f0_hz': variant['f0_hz']}
            source.pop('turbulence', None)
            if 'turbulence_scale' in variant:
                source['turbulence'] = {'scale': variant['turbulence_scale']}
        flags, variants[name], replay = compare_variant(config, variant, source, artifacts / name, probe, execute)
        checks.update({f'{name}/{key}': bool(value) for key, value in flags.items()})
        if name in ('male-paired', 'male-muted', song['id']):
            replays[name] = replay
    flags, controls = compare_controls(replays, variants, config['measurement'])
    checks.update(flags)
    diagnostic = config['remaining_symbols']
    request = artifacts / 'remaining-symbols.json'
    timing.write(request, {'song_plan': {'scores': [{'lyrics': diagnostic['lyrics'], 'id': 'remaining',
        'bpm': song['bpm'], 'start_seconds': song['start_seconds'], 'notes': [
            {'midi': song['midi'], 'beats': song['beats_per_note']} for _ in range(diagnostic['syllables'])]}]}})
    planned = artifacts / 'remaining-symbols-plan.json'
    execute([*CLI, 'inspect', str(request)], stdout=planned)
    remaining = timing.read(planned)['scores'][0]['plan']['unavailable_speech_symbols']
    checks['remaining_symbols'] = remaining == diagnostic['expected']
    report = {'checks': checks, 'variants': variants, 'controls': controls, 'unavailable_speech_symbols': remaining}
    if browser:
        flags, report['browser'] = browser_song.browser_measure(
            config, {song['id']: replays[song['id']]}, artifacts, execute, bun, case_path=CASE)
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
    modules = (bodies, cells, constriction, frication, timing, traces, shared, voice, wasm, browser_song)
    sources = [CASE, CELL_REFERENCE, *bases.values(), voice.PROBE, Path(__file__).resolve(), *shared.candidate_sources(),
               *(Path(module.__file__) for module in modules), WORKSPACE / 'tools/upstream_baseline.py',
               WORKSPACE / 'tools/measure_alveolopalatal_affricates.py',
               WORKSPACE / 'tools/measure_vowel_voice.py', WORKSPACE / 'tools/measure_song_plan.py',
               WORKSPACE / 'data/mandarin.txt.gz', WORKSPACE / 'data/cmudict.txt.gz']
    upstream_paths = ('crates/chimera-cli/src/render.rs', 'public/data/mandarin.txt.gz',
        *('crates/chimera/' + path for path in ('src/phonetics/inventory.rs', 'src/phonetics/planner.rs',
          'src/phonetics/mandarin.rs', 'src/phonetics/sing.rs', 'src/phonetics/durations.rs',
          'src/phonetics/consonantTargets.generated.json', 'src/anatomy/human.rs', 'src/voice/human_airway.rs',
          'src/voice/human_voice.rs', 'src/airway/network.rs', 'tests/mandarin.rs', 'tests/apical.rs',
          'tests/sounds.rs', 'tests/consonant_artifacts.rs')))
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
