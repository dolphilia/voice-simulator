"""英語 /ʃ/ の調音、歯の乱流、発話と歌唱の出力を固定上流に照合する。"""

import argparse
import os
from pathlib import Path
import re
import subprocess

import numpy as np
from scipy.io import wavfile
from scipy.signal import periodogram

import measure_alveolar_stop as cells
import measure_bilabial_stop as voice
import measure_english_rhotic as inputs_with_transcripts
import measure_sibilant as frication
import measure_speech_timing as timing
import measure_uniform_tube as shared
import measure_wasm_fixed as pcm_metrics
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/postalveolar-fricative-sh.json'


def blend(endpoints, body):
    if isinstance(body, str):
        return endpoints[body]
    female, child = body['female'], body['child']
    return ((1 - child) * ((1 - female) * endpoints['male'] + female * endpoints['female'])
            + child * endpoints['child'])


def within(section, a, b):
    return (section >= a) & (section < b)


def plan_check(settings, reference, variant, source, limits):
    if 'song' in settings:
        phrases = settings['song']['plan']['phrases']
    else:
        phrases = settings['speech'].get('phrases')
    adapted = settings if phrases is None else {**settings, 'speech': {'utterances': [
        {'segments': phrase['timing']['segments']} for phrase in phrases]}}
    tol = limits['gesture_abs_tolerance']
    segments, report = frication.compare_plans(adapted, reference, tol)
    ipa = variant.get('ipa', 'ʃ')
    spans = [segment for segment in segments if segment['ipa'] == ipa]
    gestures = settings['gestures']
    rate = max(source.get('input', {}).get('rate', 1), 1)
    targets = dict(tongue_tip_x_cm=5.7, tongue_tip_y_cm=blend(limits['tip_heights_cm'], source['body']),
                   jaw_cm=0.35, lip_protrusion_cm=0.75, lip_spread=0.2)
    flags = {'fixed_upstream_plan': report['passed'], 'registered_phone': bool(spans)}
    details = {**report, 'segments': spans}
    if ipa in ('ʃ', 'tʃ'):
        expected = []
        for span in spans:
            a, b = span['t0'], span['t1']
            start = a if ipa == 'ʃ' else max(a, a + .45 * (b - a) - .015)
            expected.append({'label': ipa, 't0': start - .008, 't1': max(b, start + .010),
                             'rampIn': .030 / rate, 'rampOut': .018 / rate, 'releaseHold': .045 / rate,
                             'speed': 1.3 if ipa == 'ʃ' else 1.4, 'strength': 40, 'targets': targets})
        observed = [g for g in gestures if g['label'] == ipa and
                    (ipa == 'ʃ' or g.get('speed') == 1.4)]
        difference, error = timing.compare(expected, observed, tol)
        flags['registered_oral_axes'] = difference is None
        details.update(first_registered_oral_difference=difference, registered_oral_error=error,
                       frication_gestures=observed)
    if ipa == 'ʃ':
        expected = [{'label': 'voiceless', 't0': s['t0'] - .015, 't1': s['t1'] + .005,
                     'rampIn': .03 / rate, 'rampOut': .03 / rate, 'strength': 6,
                     'targets': {'abduction_cm2': .30}} for s in spans]
        observed = [g for want in expected for g in gestures if g['label'] == 'voiceless'
                    and abs(g['t0'] - want['t0']) <= tol]
        difference, error = timing.compare(expected, observed, tol)
        flags['registered_folds'] = difference is None
        details.update(first_registered_folds_difference=difference, registered_folds_error=error)
    if variant.get('palatalized'):
        expected = [{'label': 'palatalized', 't0': s['t0'], 't1': s['t1'],
                     'rampIn': .04 / rate, 'rampOut': .04 / rate, 'strength': 3,
                     'targets': {'tongue_body_x_cm': 3.8, 'tongue_body_y_cm': 7.95}} for s in spans]
        observed = [g for g in gestures if g['label'] == 'palatalized']
        difference, _ = timing.compare(expected, observed, tol)
        flags['palatalization_on_free_axes'] = difference is None
        details['first_palatalization_difference'] = difference
    if variant.get('final'):
        exhale = next(g for g in gestures if g['label'] == 'exhale')
        delay = exhale['t0'] - spans[-1]['t1']
        flags['final_exhale'] = abs(delay - .015) <= tol
        details['exhale_delay_seconds'] = delay
    if variant['id'] == 'placed-closure':
        stop = next(s for s in segments if s['ipa'] == 't')
        delay = min(.025, max(0., stop['t1'] - stop['t0'] - .030))
        at = stop['t0'] + delay
        expected = [at - .031, max(at + .010, stop['t1'] - .020)]
        closure = next(g for g in gestures if g['label'] == 't' and 'tongue_tip_y_cm' in g['targets'])
        observed = [closure['t0'], closure['t1']]
        difference, _ = timing.compare(expected, observed, tol)
        flags['tip_placed_behind_lips'] = difference is None
        details['closure'] = {'delay_seconds': delay, 'expected': expected, 'observed': observed}
    if 'song' in settings:
        notes = settings['song']['plan']['notes']
        details['nuclei_seconds'] = [[n['nucleus_start_seconds'], n['nucleus_end_seconds']] for n in notes]
        flags['song_onset_and_coda'] = (len(spans) == len(notes) == 2
            and abs(spans[0]['t1'] - notes[0]['nucleus_start_seconds']) <= tol
            and abs(spans[-1]['t0'] - notes[-1]['nucleus_end_seconds']) <= tol)
    return flags, details


def observe(trace, pcm, rate, span, limits):
    a, b = span['t0'], span['t1']
    lo, hi = [a + (b - a) * f for f in limits['center_fraction']]
    times = (trace['frame'] + 1) / rate
    mask = within(times, lo, hi)
    first_half = within(times, a, (a + b) / 2)
    center = trace[mask]
    if len(center) < 2:
        raise ValueError('摩擦の中央区間に測定用のサンプルがありません')
    freqs, density = periodogram(pcm[mask].astype(float), fs=rate, window='hann')
    low, high = limits['high_band_hz']
    src = center['teeth_noise_source'] >= 0
    teeth = center[src]
    keys = ('lip_protrusion_cm', 'lip_spread', 'jaw_cm', 'oral_minimum_cm2', 'glottal_voicing')
    return {
        'center_seconds': [lo, hi],
        'median': {key: float(np.median(center[key])) for key in keys},
        'closed_frames_in_first_half': int(np.count_nonzero(
            trace['oral_minimum_cm2'][first_half] <= limits['closed_area_cm2'])),
        'minimum_center_area_cm2': float(center['oral_minimum_cm2'].min()),
        'median_subglottal_pressure_cm_h2o': float(np.median(center['pressure_sub_dyn_cm2']) / 980.665),
        'teeth_active_fraction': float(np.mean(center['teeth_noise_level'] > 0)),
        'teeth_forward_pressure_rms_dyn_cm2': float(np.sqrt(np.mean(center['teeth_noise_forward_pressure']**2))),
        'teeth_distance_median_cm': float(np.median(teeth['noise_teeth_distance_cm'])) if len(teeth) else None,
        'teeth_cutoff_median_hz': float(np.median(teeth['teeth_noise_lowpass_hz'])) if len(teeth) else None,
        'pcm_high_band_power': float(density[(freqs >= low) & (freqs <= high)].sum() * (freqs[1] - freqs[0])),
    }


def compare_variant(config, variant, source, folder, probe, execute):
    limits = config['measurement']
    folder.mkdir()
    key = 'song_voice' if 'score' in source else 'speech_voice'
    if 'noise_scale' in variant:
        source = {**source, 'turbulence': {'scale': variant['noise_scale']}}
    path = folder / 'case.json'
    timing.write(path, {'id': variant['id'], 'upstream_revision': config['upstream_revision'], key: source})
    settings, track, files, upstream_track, upstream_pcm, upstream_plan = voice.capture(
        path, limits['host_block_frames'], folder, execute, (), probe=probe)
    reference = timing.read(upstream_plan)
    flags, plan = plan_check(settings, reference, variant, source, limits)
    n = settings['output_frames']
    native, upper = [voice.load_trace(p, n) for p in (track, upstream_track)]
    fields = [field for field in native.dtype.names if field != 'oral_minimum_cell']
    mismatches, errors = frication.source_comparison(native[fields], upper[fields], limits)
    minima = cells.compare_cell_minima(native, upper, {**limits,
                                                      'geometry_absolute_tolerance': limits['geometry_abs_tolerance']})
    rate, pcm = wavfile.read(files[0][0])
    upper_pcm = np.fromfile(upstream_pcm, dtype='<f4')
    if any(x.shape != (n,) or x.dtype != np.float32 or not np.isfinite(x).all() for x in (pcm, upper_pcm)):
        raise ValueError('PCMのフレーム数、型または有限性が条件外です')
    compared = pcm_metrics.compare_pcm(pcm, upper_pcm, limits['pcm_abs_tolerance'])
    band = [frication.independent_band(t, limits['selection_abs_tolerance'],
                                     body_scale=blend(limits['length_scales'], source['body']))
            for t in (native, upper)]
    center = [[observe(t, x, rate, s, limits) for s in plan['segments']]
              for t, x in ((native, pcm), (upper, upper_pcm))]
    flags.update(upstream_physical_trace=not mismatches and minima['passed'],
                 upstream_pcm=compared['first_frame_over_tolerance'] is None,
                 sample_rates_and_frames=(rate == limits['output_rate_hz'] and n == reference['output_frames']
                                          and source['internal_sample_rate_hz'] == limits['internal_rate_hz']),
                 host_partition=all(sha256(wav) == sha256(files[0][0]) and sha256(csv) == sha256(files[0][1])
                                    for wav, csv in files),
                 independent_teeth_band=all(result['passed'] for result in band))
    observations = [row for side in center for row in side]
    if variant.get('check_pressure'):
        flags['subglottal_pressure'] = all(row['median_subglottal_pressure_cm_h2o']
                                          > limits['minimum_adult_subglottal_pressure_cm_h2o'] for row in observations)
    if variant.get('check_center'):
        low, high = limits['open_narrowing_cm2']
        flags['open_narrowing_and_teeth_noise'] = all(
            row['minimum_center_area_cm2'] > limits['closed_area_cm2']
            and low <= row['median']['oral_minimum_cm2'] <= high
            and row['median']['glottal_voicing'] <= limits['maximum_center_voicing']
            and row['teeth_active_fraction'] >= limits['minimum_teeth_active_fraction'] for row in observations)
    if variant.get('noise_scale') == 0:
        noise_fields = [f for f in fields if f.endswith(('_noise_level', '_forward_pressure', '_reverse_pressure'))]
        flags['mute_removes_noise_injection'] = bool(noise_fields) and all(
            not t[f].any() for t in (native, upper) for f in noise_fields)
    first = {}
    for field in ('tongue_tip_y_cm', 'lip_protrusion_cm', 'oral_minimum_cm2', 'teeth_noise_lowpass_hz',
                  'teeth_noise_forward_pressure', 'radiation_derivative_cm3_s2'):
        hits = np.flatnonzero(native[field] != upper[field])
        first[field] = None if not hits.size else {'frame': int(hits[0]),
            'difference': float(native[field][hits[0]] - upper[field][hits[0]])}
    return flags, {'plan': plan, 'center': center, 'noise_band': band, 'pcm': compared,
                   'output_frames': n, 'first_numeric_difference': first, 'first_trace_differences': mismatches,
                   'trace_errors': errors, 'oral_minimum_cells': minima}


def measure(config, speech, song, published_support, transcripts, artifacts, execute):
    suites = ('sound_marks', 'lung_port', 'consonant_artifacts', 'affricates')
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera',
             *(arg for suite in suites for arg in ('--test', suite))], cwd=UPSTREAM,
            stdout=artifacts / 'upstream-tests.log')
    probe = shared.build_upstream_probe(voice.PROBE, artifacts, execute, extra_libraries=('serde_json',))
    contexts = {}
    checks = {}
    for variant, source in inputs_with_transcripts.choose_inputs(config, speech, song, transcripts):
        name = variant['id']
        flags, contexts[name] = compare_variant(config, variant, source, artifacts / name, probe, execute)
        checks.update({f'{name}:{check}': passed for check, passed in flags.items()})
    original = config['english']['newly_renderable_ids']
    checks['prior_blocker_only_sh'] = all(
        re.search(r'\(ʃ\)$', published_support['observations'][name].get('error', '')) is not None
        and contexts[name]['plan']['segments'] for name in original)
    normal, mute, palatal, stop = [contexts[name]['center'][0][0] for name in
                                  ('male', 'muted', 'alveolopalatal', 'affricate')]
    delta_db = float(10 * np.log10(normal['pcm_high_band_power'] / mute['pcm_high_band_power']))
    checks.update(mute_high_band_reduction=delta_db >= config['measurement']['minimum_mute_high_band_reduction_db'],
                  lip_protrusion_vs_alveolopalatal=normal['median']['lip_protrusion_cm'] > palatal['median']['lip_protrusion_cm'],
                  closure_in_affricate_control=stop['closed_frames_in_first_half'] > 0
                  and normal['closed_frames_in_first_half'] == 0)
    return {'checks': checks, 'contexts': contexts, 'male_high_band_without_mute_minus_mute_db': delta_db}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    if os.environ.get('CHIMERA_RUN_STORAGE') != 'rtl9210b':
        parser.error('観測CSVは CHIMERA_RUN_STORAGE=rtl9210b で作業用ディスクに出力してください')
    config = timing.read(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != config['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('差分のない固定上流版を用意してください')
    speech_path, song_path = (CASE.parent / config[name] for name in ('speech_base', 'song_base'))
    transcripts = UPSTREAM / config['english']['transcripts']
    prior = WORKSPACE / 'runs' / config['english']['prior_support_run']
    inputs = [CASE, speech_path, song_path, transcripts, prior / 'summary.json', prior / 'manifest.json',
              Path(__file__).resolve(), voice.PROBE,
              *(Path(m.__file__) for m in (cells, voice, frication, timing, pcm_metrics, inputs_with_transcripts)),
              *shared.candidate_sources()]
    speech = timing.read(speech_path)['speech_voice']
    speech.pop('turbulence', None)
    song = timing.read(song_path)['song_voice']
    return shared.record_measurement(args.run_id, CASE, inputs,
        {'case_id': config['id'], 'upstream_revision': revision, 'invoked_from': str(Path.cwd())},
        lambda out, execute: measure(config, speech, song, timing.read(prior / 'summary.json'), transcripts, out, execute),
        command=None, input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
