"""歯茎硬口蓋摩擦音の調音、歯の乱流、韓国語歌唱を固定上流と照合する。"""

import argparse
import math
from pathlib import Path
import re
import shutil
import subprocess

import numpy as np
from scipy.io import wavfile

import measure_alveolar_stop as cells
import measure_bilabial_stop as voice
import measure_sibilant as frication
import measure_speech_timing as timing
import measure_uniform_tube as shared
import measure_velar_stops as song
import measure_wasm_fixed as wasm
from measure_worklet_fixed import ROOT, web_sources
from upstream_baseline import UPSTREAM, WORKSPACE, sha256

CASE = WORKSPACE / 'cases/alveolopalatal-fricatives.json'
BODY_SCALES = {'male': 1.0, 'female': 0.90, 'child': 0.74}


def body_value(body, values):
    if isinstance(body, str):
        return values[body]
    female, child = body['female'], body['child']
    weights = ((1 - child) * (1 - female), (1 - child) * female, child)
    return math.fsum(weight * values[anchor] for weight, anchor in zip(weights, BODY_SCALES, strict=True))


def compare_plan(config, variant, settings, upper, is_song):
    tol = config['measurement']['gesture_abs_tolerance']
    source = settings
    if is_song:
        source = {**settings, 'speech': {'utterances': [
            {'segments': p['timing']['segments']} for p in settings['song']['plan']['phrases']]}}
    parts, report = frication.compare_plans(source, upper, tol)
    ipa = variant['ipa']
    matching = [part for part in parts if part['ipa'] == ipa]
    if len(matching) != 1:
        raise ValueError(f'対象音素 /{ipa}/ の区間を一件取得できません')
    segment = matching[0]
    a, b = segment['t0'], segment['t1']
    rate = max(1.0, variant.get('rate', 1.0))
    tip = body_value(variant['body'], config['calibrated_tip_cm'][ipa])
    voiceless = ipa == 'ɕ'
    label = 'voiceless' if voiceless else 'voiced frication'
    expected = [
        {'label': ipa, 't0': a - .008, 't1': max(a + .01, b), 'rampIn': .03 / rate,
         'rampOut': .018 / rate, 'strength': 40, 'releaseHold': .045 / rate, 'speed': 1.3,
         'targets': {'tongue_tip_x_cm': 5.85, 'tongue_tip_y_cm': tip, 'tongue_body_x_cm': 3.6,
                     'tongue_body_y_cm': 7.75, 'jaw_cm': .3, 'lip_protrusion_cm': 0, 'lip_spread': .7}},
        {'label': label, 't0': a - .015, 't1': b + .005 if voiceless else b,
         'rampIn': .03 / rate, 'rampOut': .03 / rate, 'strength': 6 if voiceless else 3,
         'targets': {'abduction_cm2': .30 if voiceless else .09}},
    ]
    actual = [gesture for gesture in settings['gestures'] if gesture['label'] in (ipa, label)]
    mismatch, error = timing.compare(actual, expected, tol)
    flags = {'upstream_plan': report['passed'], 'independent_gestures': mismatch is None}
    report.update(segment=segment, first_registered_difference=mismatch,
                  maximum_registered_difference=error, target_tip_y_cm=tip, gestures=actual)
    if is_song:
        syllables = settings['song']['syllables']
        tokens = {
            'onsets': [[p['ipa'] for p in s['onset']] for s in syllables],
            'nuclei': [s['nucleus']['ipa'] for s in syllables],
            'codas': [[p['ipa'] for p in s['coda']] for s in syllables],
        }
        report['syllables'] = tokens
        flags['registered_syllables'] = tokens == {key: variant[key] for key in tokens}
    return flags, report, parts[0], segment


def observe(trace, pcm, rate, vowel, segment, limits, scale, is_song):
    a, b = segment['t0'], segment['t1']
    t = trace['frame'] / rate
    fa, fb = limits['center_fraction']
    center = (t >= a + fa * (b - a)) & (t < a + fb * (b - a))
    if is_song:
        section = (t >= a) & (t < b)
        pressure = trace['teeth_noise_forward_pressure'][section]
        report = {'passed': bool(np.any(pressure)),
                  'teeth_forward_pressure_rms_dyn_cm2': float(np.sqrt(np.mean(pressure**2)))}
    else:
        report = frication.event_metrics(trace, pcm, rate, vowel, segment, limits, scale)
    report['median_abduction_cm2'] = float(np.median(trace['abduction_cm2'][center]))
    report['median_noise_minimum_cm2'] = float(np.median(trace['noise_minimum_cm2'][center]))
    return report


def compare_variant(config, variant, base, is_song, out, probe, execute):
    out.mkdir()
    key = 'song_voice' if is_song else 'speech_voice'
    limits = config['measurement']
    source = {**timing.read(base)[key], 'body': variant['body']}
    scale = variant.get('turbulence_scale', 1)
    if is_song:
        source['score'] = {**source['score'], 'id': variant['id'], 'lyrics': variant['lyrics'],
                           'notes': [{'midi': midi, 'beats': 1} for midi in variant['midi']]}
    else:
        source['input'] = {k: variant[k] for k in ('id', 'text', 'rate')}
        source.pop('turbulence', None)
        if 'turbulence_scale' in variant:
            source['turbulence'] = {'scale': scale}
    path = out / 'case.json'
    timing.write(path, {'id': variant['id'], 'upstream_revision': config['upstream_revision'], key: source})
    settings, trace, files, upper_trace, upper_raw, upper_plan = voice.capture(
        path, limits['host_block_frames'], out, execute, (), probe=probe)
    upper = timing.read(upper_plan)
    flags, plan, vowel, segment = compare_plan(config, variant, settings, upper, is_song)
    frames = settings['output_frames']
    native, reference = [voice.load_trace(p, frames) for p in (trace, upper_trace)]
    exclusions = ['oral_minimum_cell']
    native_fields = [name for name in native.dtype.names if name not in exclusions]
    upper_fields = [name for name in reference.dtype.names if name not in exclusions]
    mismatches, errors = frication.source_comparison(native[native_fields], reference[upper_fields], limits)
    cell_diff = cells.compare_cell_minima(
        native, reference, {**limits, 'geometry_absolute_tolerance': limits['geometry_abs_tolerance']})
    rate, pcm = wavfile.read(files[0][0])
    upper_pcm = np.fromfile(upper_raw, dtype='<f4')
    if any(samples.shape != (frames,) or samples.dtype != np.float32 for samples in (pcm, upper_pcm)):
        raise ValueError('PCMの長さか型が登録条件と異なります')
    pcm_diff = wasm.compare_pcm(pcm, upper_pcm, limits['pcm_abs_tolerance'])
    body_scale = body_value(variant['body'], BODY_SCALES)
    bands = [frication.independent_band(t, limits['selection_abs_tolerance'], body_scale=body_scale)
             for t in (native, reference)]
    events = [observe(t, p, rate, vowel, segment, limits, scale, is_song)
              for t, p in ((native, pcm), (reference, upper_pcm))]
    flags.update(
        trace=not mismatches and cell_diff['passed'],
        pcm=pcm_diff['first_frame_over_tolerance'] is None,
        sample_rates_and_frames=rate == limits['output_rate_hz'] and frames == upper['output_frames']
        and source['internal_sample_rate_hz'] == limits['internal_rate_hz'],
        same_host_blocks=all(sha256(w) == sha256(files[0][0]) and sha256(c) == sha256(files[0][1])
                             for w, c in files),
        independent_teeth_band=all(band['passed'] for band in bands),
        observed_frication=all(event['passed'] for event in events),
    )
    return flags, {
        'plan': plan, 'first_trace_differences': mismatches, 'trace_errors': errors, 'oral_minimum_cells': cell_diff,
        'pcm': pcm_diff, 'bands': bands, 'events': events, 'frames': frames,
    }, (source, settings, native, reference, pcm)


def measure(config, bases, artifacts, execute, bun, browser):
    execute(['cargo', 'test', '--locked', '-p', 'chimera', '--test', 'voiced_fricatives', '--test', 'affricates',
             '--test', 'syllables'], cwd=UPSTREAM, stdout=artifacts / 'upstream-tests.log')
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
            elif name in ('male-sh', 'male-sh-muted'):
                controls[name] = replay[2:4]
    limits = config['measurement']
    male = [variants[name]['events'] for name in ('male-sh', 'male-zh', 'male-sh-muted')]
    abduction = [a['median_abduction_cm2'] - b['median_abduction_cm2'] for a, b in zip(*male[:2], strict=True)]
    checks['voiceless_wider_abduction'] = min(abduction) >= limits['minimum_male_abduction_difference_cm2']
    geometry = ('noise_cell', 'noise_minimum_cm2', 'noise_teeth_distance_cm', 'teeth_noise_source')
    checks['muted_same_geometric_registration'] = all(
        np.array_equal(a[key], b[key])
        for a, b in zip(controls['male-sh'], controls['male-sh-muted'], strict=True) for key in geometry)
    report = {'checks': checks, 'variants': variants, 'male_voiceless_minus_voiced_abduction_cm2': abduction}
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
    bases = {kind: WORKSPACE / 'cases' / config[kind + '_case'] for kind in ('speech', 'song')}
    modules = (cells, voice, frication, timing, shared, song, wasm)
    sources = [CASE, *bases.values(), voice.PROBE, Path(__file__).resolve(), *shared.candidate_sources(),
               *(Path(module.__file__) for module in modules), WORKSPACE / 'tools/upstream_baseline.py',
               WORKSPACE / 'tools/measure_vowel_voice.py', WORKSPACE / 'tools/measure_song_plan.py']
    upstream_paths = ('src/phonetics/inventory.rs', 'src/phonetics/planner.rs', 'src/phonetics/korean.rs',
                      'src/phonetics/sing.rs', 'src/phonetics/consonantTargets.generated.json',
                      'src/anatomy/human.rs', 'src/voice/human_airway.rs', 'src/airway/network.rs',
                      'tests/voiced_fricatives.rs', 'tests/affricates.rs', 'tests/syllables.rs')
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
