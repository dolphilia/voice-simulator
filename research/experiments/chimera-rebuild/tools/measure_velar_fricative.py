"""軟口蓋摩擦音の舌背、乱流、ロシア語歌唱を固定上流と照合する。"""

import argparse
from pathlib import Path
import re
import shutil
import subprocess

import numpy as np
from scipy.io import wavfile

import measure_alveolar_stop as cells
import measure_alveolopalatal_fricatives as body
import measure_bilabial_stop as voice
import measure_labiodental_fricatives as noise
import measure_sibilant as frication
import measure_speech_timing as timing
import measure_uniform_tube as shared
import measure_velar_stops as song
import measure_wasm_fixed as wasm
from measure_worklet_fixed import ROOT, web_sources
from upstream_baseline import UPSTREAM, WORKSPACE, sha256

CASE = WORKSPACE / 'cases/velar-fricative.json'
REVISED_CASE = WORKSPACE / 'cases/velar-fricative-v2.json'
SOURCES = ('constriction_noise', 'teeth_noise', 'glottis_noise')


def compare_plan(config, variant, settings, upper, is_song):
    limits = config['measurement']
    tolerance = limits['gesture_abs_tolerance']
    if is_song:
        score = settings['song']
        settings = {**settings, 'speech': {'utterances': [
            {'segments': phrase['timing']['segments']} for phrase in score['plan']['phrases']]}}
    parts, report = frication.compare_plans(settings, upper, tolerance)
    spans = [part for part in parts if part['ipa'] == 'x']
    if len(spans) != 1:
        raise ValueError('対象音素 /x/ の区間を一件取得できません')
    span = spans[0]
    a, b = span['t0'], span['t1']
    rate = variant.get('rate', 1.0)
    height = body.body_value(variant['body'], config['calibrated_body_height_cm'])
    expected = [
        {'label': 'x', 't0': a - .008, 't1': max(a + .010, b), 'rampIn': .030 / rate,
         'rampOut': .030 / rate, 'strength': 40, 'releaseHold': .045 / rate, 'speed': 1.105,
         'targets': {'tongue_body_y_cm': height}},
        {'label': 'x', 't0': a, 't1': b, 'rampIn': .05 / rate, 'rampOut': .05 / rate,
         'strength': .25, 'targets': {'tongue_body_x_cm': 2.3}},
        {'label': 'voiceless', 't0': a - .015, 't1': b + .005, 'rampIn': .03 / rate,
         'rampOut': .03 / rate, 'strength': 6, 'targets': {'abduction_cm2': .30}},
    ]
    if variant.get('palatalized'):
        expected.append({'label': 'palatalized', 't0': a, 't1': b, 'rampIn': .04 / rate,
                         'rampOut': .04 / rate, 'strength': 3, 'targets': {'tongue_body_x_cm': 3.8}})
    gestures = [g for g in settings['gestures'] if g['label'] in ('x', 'voiceless', 'palatalized')]
    difference, error = timing.compare(gestures, expected, tolerance)
    base = limits['base_duration_seconds']
    expected_duration = base / rate
    if not is_song and config['revision'] >= 2:
        minimum = base * limits['klatt_minimum_fraction']
        expected_duration = (minimum + (base - minimum) * limits['klatt_word_medial_factor']) / rate
    flags = {'upstream_plan': report['passed'], 'registered_targets_and_timing': difference is None}
    if is_song:
        syllables = score['syllables']
        tokens = {'onsets': [[p['ipa'] for p in s['onset']] for s in syllables],
                  'nuclei': [s['nucleus']['ipa'] for s in syllables],
                  'codas': [[p['ipa'] for p in s['coda']] for s in syllables]}
        expected_duration *= limits['sung_duration_factor']
        beat = score['plan']['notes'][1]['beat_seconds']
        flags['registered_syllables'] = tokens == {key: variant[key] for key in tokens}
        flags['lands_on_beat'] = abs(b - beat) <= tolerance
        report.update(syllables=tokens, second_beat_seconds=beat)
    flags['registered_duration'] = abs(b - a - expected_duration) <= tolerance
    report.update(segment=span, target_height_cm=height, gestures=gestures, expected_seconds=expected_duration,
                  first_registered_difference=difference, maximum_registered_difference=error)
    preceding = parts[parts.index(span) - 1]
    return flags, report, preceding, span


def constriction_registration(trace, body_scale, tolerance):
    """断面とセルの位置から狭窄音源の登録を予測する。"""
    cell = trace['noise_cell'].astype(int)
    pharynx = trace['pharynx_cells'].astype(int)
    oral = trace['oral_cells'].astype(int)
    dx = np.where(cell < pharynx, trace['pharynx_anatomical_length_cm'] / pharynx,
                  trace['oral_anatomical_length_cm'] / oral)
    offset = np.maximum(1, np.floor(.9 * body_scale / dx + .5)).astype(int)
    last = pharynx + oral - 2
    branches = (np.minimum(cell, last), np.minimum(cell + offset, last), np.maximum(0, cell - offset))
    crosses_gap = np.logical_or.reduce([branch == pharynx for branch in branches])
    area = trace['noise_minimum_cm2'] / body_scale**2
    u = np.clip((area - .35) / (.90 - .35), 0, 1)
    gain = 1.364e-6 * (1 - u**2 * (3 - 2 * u))
    too_wide = (cell >= 0) & (gain <= 0)
    blocked = (cell >= 0) & (gain > 0) & crosses_gap
    expected = (cell >= 0) & (gain > 0) & ~crosses_gap
    registered = trace['constriction_noise_source'] >= 0
    gain_delta = abs(np.where(expected, gain, 0) - trace['constriction_noise_gain'])
    disagreement = np.flatnonzero(expected != registered)
    report = {
        'registered_frames': int(registered.sum()),
        'expected_frames': int(expected.sum()),
        'first_registration_difference_frame': int(disagreement[0]) if disagreement.size else None,
        'gain_maximum_absolute_error': float(gain_delta.max()),
        'passed': not disagreement.size and bool(gain_delta.max() <= tolerance)
        and bool(np.all(trace['constriction_noise_lowpass_hz'][expected] == 2600)),
    }
    return report, {'branch_gap': blocked, 'area_ceiling': too_wide, 'registered': expected, 'no_open_cell': cell < 0}


def observe(trace, rate, preceding, span, limits, body_scale, variant, registration):
    a, b = span['t0'], span['t1']
    time = trace['frame'] / rate
    fa, fb = limits['center_fraction']
    center = (a + fa * (b - a) <= time) & (time < a + fb * (b - a))
    prior = (preceding['t0'] + .03 <= time) & (time < preceding['t1'] - .03)
    full = (a <= time) & (time < b)
    registered = trace['constriction_noise_source'][center] >= 0
    active = trace['constriction_noise_level'][center] > 0
    distance = trace['noise_teeth_distance_cm'][center] / body_scale
    distant = (trace['noise_cell'][center] >= 0) & (distance >= limits['teeth_distance_limit_normalized_cm'])
    teeth = trace['teeth_noise_source'][center] >= 0
    flags = {'no_teeth_source_at_distant_constriction': not np.any(distant & teeth)}
    if variant.get('turbulence_scale', 1) == 0:
        fields = [key for key in trace.dtype.names
                  if key.endswith(('_level', '_forward_pressure', '_reverse_pressure'))]
        flags['zero_noise_injection'] = all(not np.any(trace[key]) for key in fields)
    elif registration is None:
        flags['constriction_noise_over_segment'] = bool(np.any(trace['constriction_noise_level'][full] > 0))
    else:
        glottal = trace['glottis_noise_level'][center] > 0
        flags['central_glottal_noise'] = glottal.mean() >= limits['minimum_central_glottal_active_fraction']
    if registration is None and variant['id'] in ('male-back', 'male-front'):
        flags['central_constriction_active'] = active.mean() >= limits['minimum_central_active_fraction_male_contexts']
    reasons = {key: float(values[center].mean()) for key, values in registration.items()} if registration else {}
    blocker = {'male-back': 'branch_gap', 'male-front': 'area_ceiling'}.get(variant['id'])
    if reasons and blocker:
        flags['dominant_registration_blocker'] = reasons[blocker] >= limits['minimum_dominant_blocker_fraction']
    sources = {key: {
        'registered_fraction': float(np.mean(trace[f'{key}_source'][center] != -1)),
        'active_fraction': float(np.mean(trace[f'{key}_level'][center] > 0)),
        'active_fraction_full_segment': float(np.mean(trace[f'{key}_level'][full] > 0)),
        'forward_pressure_rms_dyn_cm2': float(np.sqrt(np.mean(trace[f'{key}_forward_pressure'][center]**2))),
    } for key in SOURCES}
    fields = ('tongue_body_x_cm', 'tongue_body_y_cm', 'pharynx_minimum_cm2', 'oral_minimum_cm2',
              'noise_minimum_cm2', 'abduction_cm2', 'glottal_voicing')
    medians = {name: [float(np.median(trace[name][window])) if np.any(window) else None
                      for window in (prior, center)] for name in fields}
    indices, counts = np.unique(trace['noise_cell'][center], return_counts=True)
    return flags, {
        'preceding_vowel_and_center_medians': medians,
        'central_sources': sources,
        'distant_selected_fraction': float(distant.mean()),
        'distant_registered_fraction': float((registered & distant).mean()),
        'central_candidate_registration': reasons,
        'normalized_teeth_distance_cm_min_max': [float(distance.min()), float(distance.max())],
        'selected_cells_and_frame_counts': {int(index): int(count) for index, count in zip(indices, counts, strict=True)},
    }


def compare_variant(config, variant, base, is_song, out, probe, execute):
    out.mkdir()
    limits = config['measurement']
    key = 'song_voice' if is_song else 'speech_voice'
    source = {**timing.read(base)[key], 'body': variant['body']}
    if is_song:
        source['score'] = {**source['score'], 'id': variant['id'], 'lyrics': variant['lyrics'],
                           'notes': [{'midi': midi, 'beats': 1} for midi in variant['midi']]}
    else:
        source['input'] = {key: variant[key] for key in ('id', 'text', 'rate')}
        source['voice'] = {**source['voice'], 'f0_hz': variant['f0_hz']}
        source.pop('turbulence', None)
        if 'turbulence_scale' in variant:
            source['turbulence'] = {'scale': variant['turbulence_scale']}
    path = out / 'case.json'
    timing.write(path, {'id': variant['id'], 'upstream_revision': config['upstream_revision'], key: source})
    settings, trace, files, upper_trace, upper_raw, upper_plan = voice.capture(
        path, limits['host_block_frames'], out, execute, (), probe=probe)
    upper = timing.read(upper_plan)
    flags, plan, preceding, span = compare_plan(config, variant, settings, upper, is_song)
    frames = settings['output_frames']
    native, reference = [voice.load_trace(p, frames) for p in (trace, upper_trace)]
    exclusions = ['oral_minimum_cell']
    native_fields = [field for field in native.dtype.names if field not in exclusions]
    upper_fields = [field for field in reference.dtype.names if field not in exclusions]
    mismatches, errors = frication.source_comparison(native[native_fields], reference[upper_fields], limits)
    cell_diff = cells.compare_cell_minima(native, reference, {
        **limits, 'geometry_absolute_tolerance': limits['geometry_abs_tolerance']})
    rate, pcm = wavfile.read(files[0][0])
    upper_pcm = np.fromfile(upper_raw, dtype='<f4')
    if any(samples.shape != (frames,) or samples.dtype != np.float32 or not np.isfinite(samples).all()
           for samples in (pcm, upper_pcm)):
        raise ValueError('PCMの長さ、型または有限性が登録条件と異なります')
    pcm_diff = wasm.compare_pcm(pcm, upper_pcm, limits['pcm_abs_tolerance'])
    body_scale = body.body_value(variant['body'], body.BODY_SCALES)
    if config['revision'] >= 2:
        gains, registration = zip(*(constriction_registration(data, body_scale, limits['gain_abs_tolerance'])
                                    for data in (native, reference)), strict=True)
    else:
        gains = [noise.constrain_gain(data, body_scale, limits['gain_abs_tolerance']) for data in (native, reference)]
        registration = (None, None)
    native_flags, native_event = observe(native, rate, preceding, span, limits, body_scale, variant, registration[0])
    upper_flags, upper_event = observe(reference, rate, preceding, span, limits, body_scale, variant, registration[1])
    flags.update({key: native_flags[key] and upper_flags[key] for key in native_flags})
    flags.update(
        trace=not mismatches and cell_diff['passed'],
        pcm=pcm_diff['first_frame_over_tolerance'] is None,
        sample_rates_and_frames=rate == limits['output_rate_hz'] and frames == upper['output_frames']
        and source['internal_sample_rate_hz'] == limits['internal_rate_hz'],
        same_host_blocks=all(sha256(w) == sha256(files[0][0]) and sha256(c) == sha256(files[0][1]) for w, c in files),
        independent_constriction_gain=all(gain['passed'] for gain in gains),
    )
    return flags, {
        'plan': plan, 'first_trace_differences': mismatches, 'trace_errors': errors, 'oral_minimum_cells': cell_diff,
        'pcm': pcm_diff, 'constriction_gains': gains, 'events': [native_event, upper_event], 'frames': frames,
    }, (source, settings, native, reference, pcm)


def measure(config, case_path, bases, artifacts, execute, bun, browser):
    suites = ('russian', 'voiced_fricatives', 'airway_adversarial')
    execute(['cargo', 'test', '--locked', '-p', 'chimera',
             *(arg for name in suites for arg in ('--test', name))],
            cwd=UPSTREAM, stdout=artifacts / 'upstream-tests.log')
    probe = shared.build_upstream_probe(voice.PROBE, artifacts, execute, extra_libraries=('serde_json',))
    checks, variants, rendered, controls = {}, {}, {}, {}
    for kind in ('speech', 'song'):
        for variant in config[kind]:
            name = variant['id']
            flags, variants[name], replay = compare_variant(
                config, variant, bases[kind], kind == 'song', artifacts / name, probe, execute)
            checks.update({f'{name}/{key}': bool(value) for key, value in flags.items()})
            if kind == 'song':
                rendered[name] = replay
            elif name in ('male-back', 'muted-back'):
                controls[name] = replay[2:4]

    limits = config['measurement']
    def central_x(event):
        return event['preceding_vowel_and_center_medians']['tongue_body_x_cm'][1]

    fronting = {}
    for context, key in (('front', 'vowel'), ('palatalized', 'palatalized')):
        changes = [central_x(front) - central_x(back) for front, back in zip(
            variants[f'male-{context}']['events'], variants['male-back']['events'], strict=True)]
        fronting[key] = changes
        checks[f'{key}_fronting'] = min(changes) >= limits[f'minimum_{key}_fronting_cm']
    geometry = ('tongue_body_x_cm', 'tongue_body_y_cm', 'noise_minimum_cm2', 'noise_cell',
                'pharynx_minimum_cm2', 'oral_minimum_cm2', 'noise_teeth_distance_cm',
                'constriction_noise_source', 'constriction_noise_forward', 'constriction_noise_reverse',
                'teeth_noise_source', 'pharynx_anatomical_length_cm', 'oral_anatomical_length_cm')
    checks['muted_same_geometric_registration'] = all(
        np.array_equal(normal[field], muted[field])
        for normal, muted in zip(controls['male-back'], controls['muted-back'], strict=True) for field in geometry)
    report = {'checks': checks, 'variants': variants, 'fronting_cm_candidate_and_upstream': fronting}
    if browser:
        flags, report['browser'] = song.browser_measure(config, rendered, artifacts, execute, bun, case_path=case_path)
        checks.update(flags)
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
    bases = {kind: WORKSPACE / 'cases' / config[f'{kind}_case'] for kind in ('speech', 'song')}
    modules = (cells, body, voice, noise, frication, timing, shared, song, wasm)
    sources = [case_path, *bases.values(), voice.PROBE, Path(__file__).resolve(), *shared.candidate_sources(),
               *(Path(module.__file__) for module in modules), WORKSPACE / 'tools/upstream_baseline.py',
               WORKSPACE / 'tools/measure_vowel_voice.py', WORKSPACE / 'tools/measure_song_plan.py']
    upstream_paths = ('src/phonetics/inventory.rs', 'src/phonetics/planner.rs', 'src/phonetics/russian.rs',
                      'src/phonetics/durations.rs',
                      'src/phonetics/sing.rs', 'src/phonetics/consonantTargets.generated.json',
                      'src/anatomy/human.rs', 'src/voice/human_airway.rs', 'src/airway/network.rs',
                      'src/physics.rs', 'tests/russian.rs', 'tests/voiced_fricatives.rs', 'tests/airway_adversarial.rs')
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
