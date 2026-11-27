"""唇歯摩擦音の下唇端、狭窄乱流、声門、ロシア語歌唱を固定上流と照合する。"""

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
import measure_alveolopalatal_fricatives as body
import measure_bilabial_stop as voice
import measure_sibilant as frication
import measure_speech_timing as timing
import measure_uniform_tube as shared
import measure_velar_stops as song
import measure_wasm_fixed as wasm
from measure_worklet_fixed import ROOT, web_sources
from upstream_baseline import UPSTREAM, WORKSPACE, sha256

CASE = WORKSPACE / 'cases/labiodental-fricatives.json'
REVISED_CASE = WORKSPACE / 'cases/labiodental-fricatives-v2.json'
SOURCE_NAMES = ('glottis_noise', 'constriction_noise', 'teeth_noise')


def compare_plan(config, variant, settings, upper, is_song):
    limits = config['measurement']
    data = settings
    if is_song:
        data = {**settings, 'speech': {'utterances': [
            {'segments': p['timing']['segments']} for p in settings['song']['plan']['phrases']]}}
    parts, compared = frication.compare_plans(data, upper, limits['gesture_abs_tolerance'])
    ipa = variant['ipa']
    matches = [segment for segment in parts if segment['ipa'] == ipa]
    if len(matches) != 1:
        raise ValueError(f'対象音素 /{ipa}/ の区間を一件取得できません')
    segment = matches[0]
    a, b = segment['t0'], segment['t1']
    rate = max(1.0, variant.get('rate', 1.0))
    aperture = body.body_value(variant['body'], config['lip_aperture_targets_cm'][ipa])
    voiced = ipa == 'v'
    label = 'voiced frication' if voiced else 'voiceless'
    expected = [
        {'label': ipa, 't0': a - .008, 't1': max(a + .010, b), 'rampIn': .030 / rate,
         'rampOut': .018 / rate, 'strength': 40, 'releaseHold': .045 / rate, 'speed': 1.3,
         'targets': {'labiodental': 1, 'lip_aperture_cm': aperture}},
        {'label': label, 't0': a - .015, 't1': b if voiced else b + .005,
         'rampIn': .03 / rate, 'rampOut': .03 / rate, 'strength': 3 if voiced else 6,
         'targets': {'abduction_cm2': .09 if voiced else .30}},
    ]
    chosen = [g for g in settings['gestures'] if g['label'] in (ipa, label)]
    first, error = timing.compare(chosen, expected, limits['gesture_abs_tolerance'])
    checks = {'upstream_plan': compared['passed'], 'registered_targets_and_timing': first is None}
    compared.update(registered_difference=first, registered_max_error=error,
                    segment=segment, aperture_target_cm=aperture, gestures=chosen)
    if is_song:
        syl = settings['song']['syllables']
        tokens = {'onsets': [[p['ipa'] for p in s['onset']] for s in syl],
                  'nuclei': [s['nucleus']['ipa'] for s in syl],
                  'codas': [[p['ipa'] for p in s['coda']] for s in syl]}
        checks['registered_syllables'] = tokens == {key: variant[key] for key in tokens}
        compared['syllables'] = tokens
    return checks, compared, parts[0], segment


def constrain_gain(trace, body_scale, tolerance):
    registered = trace['constriction_noise_source'] >= 0
    area = trace['noise_minimum_cm2'][registered] / body_scale**2
    if not area.size:
        return {'registered_frames': 0, 'passed': False}
    t = np.clip((area - .35) / (.9 - .35), 0, 1)
    expected = 1.364e-6 * (1 - (3 * t**2 - 2 * t**3))
    error = float(abs(trace['constriction_noise_gain'][registered] - expected).max())
    low = trace['constriction_noise_lowpass_hz'][registered]
    return {'registered_frames': int(registered.sum()), 'gain_maximum_absolute_error': error,
            'lowpass_hz': float(np.median(low)),
            'passed': error <= tolerance and bool(np.all(low == 2600))}


def observe(trace, pcm, rate, vowel, span, config, variant, is_song):
    limits = config['measurement']
    a, b = span['t0'], span['t1']
    t = trace['frame'] / rate
    fa, fb = limits['center_fraction']
    center = (t >= a + fa * (b - a)) & (t < a + fb * (b - a))
    area = float(np.median(trace['noise_minimum_cm2'][center]))
    lab = float(np.median(trace['labiodental'][center]))
    sources = {name: {
        'registered_fraction': float(np.mean(trace[name + '_source'][center] != -1)),
        'active_fraction': float(np.mean(trace[name + '_level'][center] > 0)),
        'forward_pressure_rms_dyn_cm2': float(np.sqrt(np.mean(trace[name + '_forward_pressure'][center]**2))),
    } for name in SOURCE_NAMES}
    distance = trace['noise_teeth_distance_cm'][center]
    scale = body.body_value(variant['body'], body.BODY_SCALES)
    at_lips = distance / scale <= 1
    registered = trace['constriction_noise_source'][center] >= 0
    labial_source = at_lips & registered
    active = trace['constriction_noise_level'][center] > 0
    sound = {'minimum_area_cm2_median': area, 'labiodental_median': lab, 'sources': sources,
             'teeth_distance_cm_min_max': [float(distance.min()), float(distance.max())],
             'lip_region_fraction': float(np.mean(at_lips)),
             'lip_region_source_fraction': float(np.mean(labial_source)),
             'lip_region_active_fraction_given_source': float(np.mean(active[labial_source]))
             if np.any(labial_source) else None,
             'abduction_cm2_median': float(np.median(trace['abduction_cm2'][center])),
             'voicing_median': float(np.median(trace['glottal_voicing'][center]))}
    checks = {}
    if is_song:
        full = (t >= a) & (t < b)
        checks['sung_constriction_noise'] = bool(np.any(trace['constriction_noise_level'][full] > 0))
        return checks, sound

    vowel_window = (t >= vowel['t0'] + .03) & (t < vowel['t1'] - .03)
    fields = ('lower_lip_edge_x_cm', 'lower_lip_edge_y_cm')
    lip = [float(np.median(trace[key][center])) for key in fields]
    prior_lip = [float(np.median(trace[key][vowel_window])) for key in fields]
    cutoff = limits['low_band_cutoff_hz']
    alpha = 1 - math.exp(-2 * math.pi * cutoff / rate)
    low = lfilter([alpha], [1, alpha - 1], lfilter([alpha], [1, alpha - 1], pcm.astype(float)))
    ratio = 10 * math.log10((1e-20 + float(np.mean(low[center]**2))) /
                            (1e-20 + float(np.mean(low[vowel_window]**2))))
    lo, hi = limits['narrowing_interval_cm2']
    checks['lip_moves_back_and_up'] = lip[0] < prior_lip[0] and lip[1] > prior_lip[1]
    oral_areas = [float(np.median(trace['oral_minimum_cm2'][window])) for window in (vowel_window, center)]
    if config['revision'] == 1:
        checks['narrowing_and_labiodental'] = lo <= area <= hi and lab >= limits['minimum_labiodental']
        checks['source_at_constriction_without_teeth_obstacle'] = (sources['teeth_noise']['registered_fraction'] == 0
            and sources['constriction_noise']['registered_fraction'] >= limits['minimum_constriction_active_fraction'])
    else:
        checks['oral_narrowing_and_labiodental'] = (lo <= oral_areas[1] < oral_areas[0]
            and lab >= limits['minimum_labiodental'])
        checks['lip_region_source_without_teeth_obstacle'] = (bool(np.any(labial_source))
            and not np.any(trace['teeth_noise_source'][center][at_lips] >= 0))
    if variant.get('turbulence_scale', 1) == 0:
        checks['zero_noise_injection'] = all(not trace[name].any() for name in trace.dtype.names
                                            if name.endswith(('_level', '_forward_pressure', '_reverse_pressure')))
    else:
        fraction = (sources['constriction_noise']['active_fraction'] if config['revision'] == 1
                    else sound['lip_region_active_fraction_given_source'])
        checks['active_constriction_noise'] = (
            fraction is not None and fraction >= limits['minimum_constriction_active_fraction'])
    if variant['id'] in ('male-v', 'female-v'):
        checks['voiced_low_band_weaker_than_vowel'] = ratio <= limits['maximum_voiced_low_band_db_relative_to_vowel']
    sound.update(vowel_lip_xy_cm=prior_lip, central_lip_xy_cm=lip, vowel_relative_low_band_db=ratio,
                 oral_minimum_cm2_vowel_and_fricative=oral_areas)
    return checks, sound


def compare_variant(config, variant, base, is_song, out, probe, execute):
    out.mkdir()
    limits = config['measurement']
    key = 'song_voice' if is_song else 'speech_voice'
    source = {**timing.read(base)[key], 'body': variant['body']}
    if is_song:
        source['score'] = {**source['score'], 'id': variant['id'], 'lyrics': variant['lyrics'],
                           'notes': [{'midi': note, 'beats': 1} for note in variant['midi']]}
    else:
        source['input'] = {k: variant[k] for k in ('id', 'text', 'rate')}
        source['voice'] = {**source['voice'], 'f0_hz': variant['f0_hz']}
        source.pop('turbulence', None)
        if 'turbulence_scale' in variant:
            source['turbulence'] = {'scale': variant['turbulence_scale']}
    path = out / 'case.json'
    timing.write(path, {'id': variant['id'], 'upstream_revision': config['upstream_revision'], key: source})
    settings, trace, files, upper_trace, upper_raw, upper_plan = voice.capture(
        path, limits['host_block_frames'], out, execute, (), probe=probe)
    upper = timing.read(upper_plan)
    checks, plan, vowel, span = compare_plan(config, variant, settings, upper, is_song)
    count = settings['output_frames']
    native, reference = [voice.load_trace(p, count) for p in (trace, upper_trace)]
    fields = [name for name in native.dtype.names if name != 'oral_minimum_cell']
    mismatches, errors = frication.source_comparison(native[fields], reference[fields], limits)
    cell_diff = cells.compare_cell_minima(native, reference, {
        **limits, 'geometry_absolute_tolerance': limits['geometry_abs_tolerance']})
    rate, pcm = wavfile.read(files[0][0])
    upper_pcm = np.fromfile(upper_raw, dtype='<f4')
    if any(x.shape != (count,) or x.dtype != np.float32 for x in (pcm, upper_pcm)):
        raise ValueError('PCMの長さか型が登録条件と異なります')
    pcm_diff = wasm.compare_pcm(pcm, upper_pcm, limits['pcm_abs_tolerance'])
    body_scale = body.body_value(variant['body'], body.BODY_SCALES)
    bands = [constrain_gain(t, body_scale, limits['selection_abs_tolerance']) for t in (native, reference)]
    first, second = [observe(t, p, rate, vowel, span, config, variant, is_song)
                     for t, p in ((native, pcm), (reference, upper_pcm))]
    checks.update({key: first[0][key] and second[0][key] for key in first[0]})
    if not is_song and config['revision'] >= 2:
        initial = limits['expected_initial_f0_hz']
        exponent = -math.expm1(-64 / rate / limits['pitch_smoothing_seconds'])
        expected = initial * (variant['f0_hz'] / initial) ** exponent
        measured = [float(t['glottal_f0_hz'][0]) for t in (native, reference)]
        checks['initial_pitch_glide'] = all(abs(hz - expected) <= limits['geometry_abs_tolerance'] for hz in measured)
        plan['first_f0_expected_and_measured_hz'] = [expected, *measured]
    checks.update(
        trace=not mismatches and cell_diff['passed'],
        pcm=pcm_diff['first_frame_over_tolerance'] is None,
        sample_rates_and_frames=rate == limits['output_rate_hz'] and count == upper['output_frames']
        and source['internal_sample_rate_hz'] == limits['internal_rate_hz'],
        same_host_blocks=all(sha256(w) == sha256(files[0][0]) and sha256(c) == sha256(files[0][1]) for w, c in files),
        independent_constriction_gain=all(band['passed'] for band in bands),
    )
    return checks, {'plan': plan, 'first_trace_differences': mismatches, 'trace_errors': errors,
                    'oral_minimum_cells': cell_diff, 'pcm': pcm_diff, 'bands': bands,
                    'events': [first[1], second[1]], 'frames': count}, (source, settings, native, reference, pcm)


def measure(config, case_path, bases, artifacts, run, bun, browser):
    run(['cargo', 'test', '--locked', '-p', 'chimera', '--test', 'voiced_fricatives',
         '--test', 'geometry_continuity', '--test', 'consonant_artifacts'],
        cwd=UPSTREAM, stdout=artifacts / 'upstream-tests.log')
    probe = shared.build_upstream_probe(voice.PROBE, artifacts, run, extra_libraries=('serde_json',))
    checks, variants, rendered, ablation = {}, {}, {}, {}
    for kind in ('speech', 'song'):
        for variant in config[kind]:
            label = variant['id']
            flags, variants[label], replay = compare_variant(
                config, variant, bases[kind], kind == 'song', artifacts / label, probe, run)
            checks.update({f'{label}/{key}': bool(flag) for key, flag in flags.items()})
            if kind == 'song':
                rendered[label] = replay
            elif label in ('male-v', 'muted-v'):
                ablation[label] = replay[2:4]
    f, v = [variants[label]['events'] for label in ('male-f', 'male-v')]
    checks['voiced_lower_abduction_and_higher_voicing'] = all(
        a['abduction_cm2_median'] > b['abduction_cm2_median'] and a['voicing_median'] < b['voicing_median']
        for a, b in zip(f, v, strict=True))
    geometric = ('noise_minimum_cm2', 'noise_teeth_distance_cm', 'noise_cell',
                 'constriction_noise_source', 'teeth_noise_source', 'lower_lip_edge_x_cm', 'lower_lip_edge_y_cm')
    checks['ablation_keeps_geometry_and_sources'] = all(np.array_equal(a[key], b[key])
        for a, b in zip(ablation['male-v'], ablation['muted-v'], strict=True) for key in geometric)
    if config['revision'] >= 2:
        slow, fast = (variants[name]['events'] for name in ('mixed-v-slow', 'mixed-v'))
        checks['faster_mixed_v_spends_less_time_in_lip_region'] = all(
            a['lip_region_source_fraction'] > b['lip_region_source_fraction']
            for a, b in zip(slow, fast, strict=True))
    report = {'checks': checks, 'variants': variants}
    if browser:
        browser_checks, report['browser'] = song.browser_measure(config, rendered, artifacts, run, bun, case_path=case_path)
        checks.update(browser_checks)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('--native-only', action='store_true', help='CLIと固定上流だけを計測する')
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
    bases = {kind: WORKSPACE / 'cases' / config[kind + '_case'] for kind in ('speech', 'song')}
    modules = (cells, body, voice, frication, timing, shared, song, wasm)
    sources = [case_path, *bases.values(), voice.PROBE, Path(__file__).resolve(), *shared.candidate_sources(),
               *(Path(module.__file__) for module in modules), WORKSPACE / 'tools/upstream_baseline.py',
               WORKSPACE / 'tools/measure_vowel_voice.py', WORKSPACE / 'tools/measure_song_plan.py']
    upstream_paths = ('src/phonetics/inventory.rs', 'src/phonetics/planner.rs', 'src/phonetics/consonantTargets.generated.json',
                      'src/anatomy/human.rs', 'src/voice/human_airway.rs', 'src/airway/network.rs',
                      'tests/voiced_fricatives.rs', 'tests/geometry_continuity.rs', 'tests/consonant_artifacts.rs')
    metadata = {'case_id': config['id'], 'revision': config['revision'], 'upstream_revision': revision,
                'upper_source_sha256': {path: sha256(UPSTREAM / 'crates/chimera' / path) for path in upstream_paths}}
    bun = ['bun'] if shutil.which('bun') else ['npx', '--yes', '--package=bun@1.4.4', '--', 'bun']
    if args.native_only:
        sources += [WORKSPACE / 'data/cmudict.txt.gz', WORKSPACE / 'data/CMUDICT-LICENSE.txt']
    else:
        sources += [song.KOREAN, song.LIVE, *web_sources(), WORKSPACE / 'tools/measure_worklet_english_body.py']
        metadata.update(node=subprocess.check_output(['node', '--version'], text=True).strip(),
                        bun=subprocess.check_output([*bun, '--version'], text=True).strip())
    return shared.record_measurement(
        args.run_id, case_path, sources, metadata,
        lambda out, run: measure(config, case_path, bases, out, run, bun, not args.native_only), command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
