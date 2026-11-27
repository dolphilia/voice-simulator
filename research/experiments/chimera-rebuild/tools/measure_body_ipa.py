"""体型を変えたIPAのジェスチャー、閉鎖、歯への乱流、PCMを照合する。"""

import argparse
import math
from pathlib import Path
import re
import subprocess

import numpy as np
from scipy.io import wavfile

import measure_bilabial_stop as speech
import measure_body_calibrated_vowels as calibrated
import measure_pcm_output as pcm
import measure_sibilant as fricative
import measure_speech_timing as timing
import measure_uniform_tube as shared
import measure_vowel_voice as vowel
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/human-body-ipa.json'
BODY_TABLE = WORKSPACE / 'cases/human-body-geometry.json'
CONSONANTS = WORKSPACE / 'crates/vocal-core/src/phonetics/consonant-targets.generated.json'
UPPER_CONSONANTS = UPSTREAM / 'crates/chimera/src/phonetics/consonantTargets.generated.json'
CLI = ['cargo', 'run', '--locked', '--release', '-p', 'vocal-cli', '--']
ANCHORS = ('male', 'female', 'child')


def registered_plan(config, variant, table, gestures):
    def targets(ipa, field):
        return [g['targets'][field] for g in gestures if g.get('label') == ipa and field in g['targets']]

    anchors = config['expected_sibilant_tip_y_cm']
    weights = variant['weights']
    predictions = {}
    measurements = {}
    for ipa in ('s', 'z'):
        predictions[ipa] = [math.fsum(w * anchors[name][ipa] for name, w in zip(ANCHORS, weights, strict=True))]
        measurements[ipa] = targets(ipa, 'tongue_tip_y_cm')
    partial = calibrated.expected_patch('ɑ', weights, table, set())
    expected = {'tips': predictions, 'vowels': [partial] * 6, 'lip': [-0.25]}
    measured = {'tips': measurements, 'vowels': [g['targets'] for g in gestures if g.get('label') == 'ɑ'],
                'lip': targets('p', 'lip_aperture_cm')}
    diff, maximum = timing.compare(measured, expected, config['measurement']['gesture_abs_tolerance'])
    return dict(mismatch=diff, maximum_absolute_error=maximum, oral_targets=measured)


def frames_for_span(span, rate, count, fractions=(0.0, 1.0)):
    duration = span['t1'] - span['t0']
    start, stop = (math.ceil((span['t0'] + f * duration) * rate) for f in fractions)
    return slice(max(0, start), min(count, stop))


def stop_closure(clip, trace, stop, rate, cfg):
    t0, t1 = stop['t0'], stop['t1']
    start_low, start_high = cfg['closure_offset_seconds']
    end_low, end_high = cfg['release_offset_seconds']
    start = max(0, int((t0 + start_low) * rate))
    stop_at = min(len(clip), math.ceil((t1 + end_high) * rate))
    closed = np.flatnonzero(trace['lip_minimum_cm2'][start:stop_at] < cfg['closed_area_cm2']) + start
    if not closed.size:
        return {'passed': False, 'closed_frames': 0}
    onset, release = int(closed[0]), int(closed[-1] + 1)
    duration = round(cfg['release_window_seconds'] * rate)
    peak = float(np.max(abs(clip[release:release + duration]), initial=0.0))
    offsets = [onset / rate - t0, release / rate - t1]
    return {
        'passed': bool(start_low <= offsets[0] <= start_high and end_low <= offsets[1] <= end_high
                       and closed.size == release - onset and peak >= cfg['minimum_release_pcm']),
        'first_closed_frame': onset, 'first_reopened_frame': release,
        'closed_frames': int(closed.size), 'offset_seconds': offsets, 'release_pcm_peak': peak,
    }


def sibilant_activity(trace, span, rate, scale, cfg):
    midpoint = frames_for_span(span, rate, len(trace), cfg['center_fraction'])
    teeth = trace['teeth_noise_source'][midpoint] >= 0
    if not teeth.size or not teeth.any():
        return {'passed': False, 'teeth_frames': 0, 'center_frames': int(teeth.size)}
    active = float(np.mean(trace['teeth_noise_level'][midpoint] > 0))
    area = trace['noise_minimum_cm2'][midpoint][teeth]
    normalized = float(np.median(area) / scale**2)
    lower, upper = cfg['central_normalized_narrowing_interval_cm2']
    return {
        'passed': bool(active >= cfg['minimum_teeth_active_fraction'] and lower <= normalized <= upper),
        'teeth_active_fraction': active,
        'teeth_frames': int(teeth.sum()),
        'physical_narrowing_median_cm2': float(np.median(area)),
        'normalized_narrowing_median_cm2': normalized,
        'voicing_median': float(np.median(trace['glottal_voicing'][midpoint])),
        'teeth_forward_pressure_rms_dyn_cm2': float(np.sqrt(np.mean(trace['teeth_noise_forward_pressure'][midpoint]**2))),
    }


def measure_variant(config, variant, table, endpoints, posture, folder, probe, execute):
    cfg = config['measurement']
    internal, rate = (cfg[k] for k in ('internal_rate_hz', 'output_rate_hz'))
    case = {
        'id': f"{config['id']}-{variant['id']}", 'upstream_revision': config['upstream_revision'],
        'hypothesis': config['hypothesis'],
        'speech_voice': {
            'body': variant['body'], 'input': config['input'], 'posture': posture,
            'internal_sample_rate_hz': internal,
            'voice': {**config['voice'], 'output_sample_rate_hz': rate},
            'turbulence': {'scale': 1.0},
        },
    }
    path = folder / 'case.json'
    timing.write(path, case)
    execute([*CLI, 'inspect', str(path)], stdout=folder / 'settings.json')
    trace = folder / 'voicing.csv'
    execute([*CLI, 'render', str(path), str(trace)])
    blocks = pcm.render_blocks(path, cfg, folder, execute)
    wave_path, csv_path = next(iter(blocks.values()))
    upper_files = tuple(folder / name for name in ('upstream-voicing.csv', 'upstream.f32', 'upstream-plan.json'))
    execute([str(probe), str(path), *map(str, upper_files)], cwd=UPSTREAM)
    settings = timing.read(folder / 'settings.json')
    plan = timing.read(upper_files[2])
    frames = settings['output_frames']
    segments, plan_comparison = fricative.compare_plans(settings, plan, cfg['gesture_abs_tolerance'])
    prediction = registered_plan(config, variant, table, settings['gestures'])
    actual, upper = (speech.load_trace(p, frames) for p in (trace, upper_files[0]))
    mismatches, errors = fricative.source_comparison(actual, upper, cfg)
    scale = math.fsum(w * endpoints[name]['scale'] for w, name in zip(variant['weights'], ANCHORS, strict=True))
    band = fricative.independent_band(actual, cfg['selection_abs_tolerance'], body_scale=scale)
    observed_rate, wave = wavfile.read(wave_path)
    upper_wave = np.fromfile(upper_files[1], dtype='<f4')
    if (wave.shape != (frames,) or wave.dtype != np.float32 or wave.shape != upper_wave.shape
            or not np.isfinite(wave).all() or not np.isfinite(upper_wave).all()):
        raise ValueError('候補と上流のPCMに同じ長さの有限な単精度サンプルが必要です')
    delta = abs(wave.astype(float) - upper_wave)
    outside = np.flatnonzero(delta > cfg['pcm_abs_tolerance'])
    stop = stop_closure(wave, actual, next(s for s in segments if s['ipa'] == 'p'), rate, cfg)
    activity = {s['ipa']: sibilant_activity(actual, s, rate, scale, cfg)
                for s in segments if s['ipa'] in ('s', 'z')}
    initial_f0 = 110.0 * (variant['f0_hz'] / 110.0)**(-math.expm1(-64 / rate / 0.06))
    f0_error = abs(initial_f0 - float(actual['glottal_f0_hz'][0]))
    checks = {
        'sample_rate_and_frames': observed_rate == rate and frames == plan['output_frames'],
        'upstream_gesture_and_segment_agreement': plan_comparison['passed'],
        'independent_registered_oral_targets': prediction['mismatch'] is None,
        'first_glottal_f0_matches_body_glide': f0_error < cfg['probe_first_f0_abs_tolerance_hz'],
        'upstream_trace_including_selected_noise_sources': not mismatches,
        'independent_teeth_noise_band_and_gain': band['passed'],
        'pcm_agreement': not outside.size,
        'block_partition_preserves_wave_and_pcm_trace': all(sha256(wav) == sha256(wave_path) and sha256(csv) == sha256(csv_path)
                                                           for wav, csv in blocks.values()),
        'lip_stop_closure_and_release': stop['passed'],
        's_teeth_noise_in_center_window': activity['s']['passed'],
        'z_teeth_noise_in_center_window': activity['z']['passed'],
    }
    return checks, {
        'plan': plan_comparison, 'independent_targets': prediction, 'segments': segments,
        'scale': scale, 'first_f0_hz': float(actual['glottal_f0_hz'][0]), 'first_f0_error_hz': f0_error,
        'stop': stop, 'sibilants': activity, 'independent_teeth_band': band,
        'absolute_pcm_error': float(delta.max()),
        'first_pcm_outside_tolerance': int(outside[0]) if outside.size else None,
        'trace_first_mismatches_by_field': mismatches, 'trace_errors': errors,
    }


def measure(config, table, endpoints, posture, artifacts, execute):
    execute(['cargo', 'test', '--locked', '-p', 'chimera', '--test', 'stop_spans',
             '--test', 'voiced_fricatives', '--test', 'body_mix'], cwd=UPSTREAM,
            stdout=artifacts / 'upstream-tests.log')
    probe = shared.build_upstream_probe(speech.PROBE, artifacts, execute, extra_libraries=('serde_json',))
    checks = {'embedded_consonant_calibration_matches_upstream': sha256(CONSONANTS) == sha256(UPPER_CONSONANTS)}
    results = {}
    for variant in config['variants']:
        label = variant['id']
        folder = artifacts / label
        folder.mkdir()
        passed, results[label] = measure_variant(config, variant, table, endpoints, posture, folder, probe, execute)
        checks.update({f'{label}/{key}': bool(value) for key, value in passed.items()})
    first = results['male']['segments']
    checks['timing_unchanged_across_bodies'] = all(r['segments'] == first for r in results.values())
    return {'checks': checks, 'cases': results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    run_id = parser.parse_args().run_id
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', run_id):
        parser.error('実行IDは英数字で始めてください')
    config = timing.read(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != config['upstream_revision'] or subprocess.check_output(
            ['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True):
        raise SystemExit('変更のない固定上流版が必要です')
    neutral = WORKSPACE / 'cases' / config['neutral_case']
    posture = timing.read(neutral)['posture']
    endpoints = timing.read(BODY_TABLE)['measurement']['reference_endpoints']
    table = timing.read(vowel.TABLE)
    upper_paths = ('src/phonetics/consonantTargets.generated.json', 'src/phonetics/vowelTargets.generated.json',
                   'src/phonetics/inventory.rs', 'src/phonetics/planner.rs', 'src/engine.rs',
                   'src/voice/human_airway.rs', 'src/voice/human_voice.rs', 'tests/body_mix.rs',
                   'tests/stop_spans.rs', 'tests/voiced_fricatives.rs')
    details = {'case_id': config['id'], 'upstream_revision': revision,
               'upstream_source_sha256': {name: sha256(UPSTREAM / 'crates/chimera' / name) for name in upper_paths}}
    modules = (speech, calibrated, pcm, fricative, timing, shared, vowel)
    sources = [CASE, BODY_TABLE, neutral, Path(__file__).resolve(), speech.PROBE, *shared.candidate_sources(),
               *(Path(module.__file__) for module in modules), WORKSPACE / 'tools/upstream_baseline.py']
    return shared.record_measurement(run_id, CASE, sources, details,
                                     lambda artifacts, execute: measure(config, table, endpoints, posture, artifacts, execute),
                                     command=None)


if __name__ == '__main__':
    raise SystemExit(main())
