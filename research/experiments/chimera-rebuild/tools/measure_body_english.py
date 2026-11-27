"""体型別の英語発話を、計画、抑揚、閉鎖、鼻端流量、PCMで照合する。"""

import argparse
import gzip
import math
from pathlib import Path
import re
import subprocess

import numpy as np
from scipy.io import wavfile

import measure_alveolar_stop as alveolar
import measure_bilabial_stop as speech
import measure_body_calibrated_vowels as calibrated
import measure_body_ipa as ipa
import measure_english_frontend as frontend
import measure_sibilant as fricative
import measure_speech_timing as timing
import measure_uniform_tube as shared
import measure_vowel_voice as vowel
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/human-body-english.json'
ANCHORS = ('male', 'female', 'child')
CLI = ['cargo', 'run', '--locked', '--release', '-p', 'vocal-cli', '--']


def capture_frontend(config, artifacts, execute):
    fixture = artifacts / 'frontend-input.json'
    timing.write(fixture, {'english_text': {'inputs': [config['input']]}})
    dictionary = artifacts / 'dictionary.tsv'
    dictionary.write_bytes(gzip.decompress((UPSTREAM / 'public/data/cmudict.txt.gz').read_bytes()))
    output = artifacts / 'frontend-upstream.json'
    probe = shared.build_upstream_probe(frontend.PROBE, artifacts, execute, extra_libraries=('serde_json',))
    execute([str(probe), str(fixture), str(dictionary)], cwd=UPSTREAM, stdout=output)
    return timing.read(output)['entries'][0]


def frontend_evidence(config, settings, upper_front, expected_f0):
    plan, expected = settings['speech'], config['expected']
    cfg = config['measurement']
    raw = ('segments', 'words', 'intonation', 'pause')
    phrases = []
    for phrase in plan['phrases']:
        source = phrase['segments']
        phrases.append({
            'words': phrase['words'], 'intonation': phrase['intonation'], 'pause': phrase['pause'],
            'ipa': [p['segment']['ipa'] for p in phrase['timing']['segments']],
            'primary_indices': [i for i, s in enumerate(source) if s.get('stress') == 1],
            'word_end_indices': [i for i, s in enumerate(source) if s.get('wordEnd')],
        })
    observed = {
        'shown': plan['shown'], 'phrases': phrases,
        'phrase_span_seconds': [[p['start_seconds'], p['end_seconds']] for p in plan['phrases']],
        'tail_seconds': plan['render_end_seconds'] - plan['end_seconds'],
        'output_frames': settings['output_frames'],
    }
    comparison = {key: expected[key] for key in observed}
    registered, _ = timing.compare(observed, comparison, cfg['gesture_absolute_tolerance'])
    lexical, _ = timing.compare([{k: p[k] for k in raw} for p in plan['phrases']],
                                [p['phrase'] for p in upper_front['phrases']],
                                cfg['gesture_absolute_tolerance'])
    pitches = [p['pitch'][-1]['targets']['f0_hz'] for p in plan['phrases']]
    expected_pitches = [expected_f0 * f for f in expected['last_pitch_multipliers']]
    prosody, error = timing.compare(pitches, expected_pitches, cfg['gesture_absolute_tolerance'])
    return {'registered_difference': registered, 'first_lexical_difference': lexical,
            'prosody_difference': prosody, 'last_pitch_max_error_hz': error,
            'last_pitch_targets_hz': pitches, **observed}


def independent_targets(variant, vowels, tips, gestures, tolerance):
    weights = variant['weights']
    expected = {'ɑ': [calibrated.expected_patch('ɑ', weights, vowels, set())] * 2}
    measured = {'ɑ': [g['targets'] for g in gestures if g['label'] == 'ɑ']}
    for phoneme in ('s', 'z'):
        expected[phoneme] = [
            math.fsum(w * tips[name][phoneme] for w, name in zip(weights, ANCHORS, strict=True))]
        measured[phoneme] = [g['targets']['tongue_tip_y_cm'] for g in gestures
                             if g['label'] == phoneme and 'tongue_tip_y_cm' in g['targets']]
    diff, error = timing.compare(measured, expected, tolerance)
    return {'difference': diff, 'maximum_checked_difference': error, 'targets': measured}


def acoustic_events(track, samples, plan, rate, cfg):
    time = (track['frame'] + 1) / rate
    first_phrase = plan['phrases'][0]
    first_mask = (time >= first_phrase['start_seconds']) & (time < first_phrase['end_seconds'])
    nasal_port = float(track['velum_port_area_cm2'][first_mask].max())
    nasal_flow = float(abs(track['nose_flow_cm3_s'][first_mask]).max())
    lip_closed = track['lip_minimum_cm2'] < cfg['closed_area_cm2']
    enters = np.flatnonzero(lip_closed & ~np.r_[False, lip_closed[:-1]])
    leaves = np.flatnonzero(~lip_closed & np.r_[False, lip_closed[:-1]])
    left, right = cfg['pop_lip_closure_window_seconds']
    matches = enters[(time[enters] >= left) & (time[enters] <= right)]
    opened = leaves[leaves > matches[0]] if matches.size else np.empty(0, dtype=int)
    reopened_at = float(time[opened[0]]) if opened.size else None
    lower, upper = cfg['pop_lip_release_window_seconds']
    quiet = []
    for before, after in zip(plan['phrases'], plan['phrases'][1:]):
        gap = after['start_seconds'] - before['end_seconds']
        a, b = [before['end_seconds'] + f * gap for f in cfg['quiet_window_fractions']]
        window = samples[round(a * rate):round(b * rate)]
        quiet.append({'span_seconds': [a, b], 'peak_pcm': float(abs(window).max())})
    quiet.append({'span_seconds': [len(samples) / rate - 0.02, len(samples) / rate],
                  'peak_pcm': float(abs(samples[-round(0.02 * rate):]).max())})
    median_f0 = []
    for phrase in plan['phrases']:
        last = next(s for s in reversed(phrase['timing']['segments']) if s['manner'] == 'vowel')
        a, b = last['start_seconds'], last['end_seconds']
        mask = (time >= a + 0.5 * (b - a)) & (time < b)
        median_f0.append(float(np.median(track['glottal_f0_hz'][mask])))
    checks = {
        'nasal_port_and_radiation': nasal_port >= cfg['minimum_nasal_port_cm2']
                                    and nasal_flow >= cfg['minimum_nose_flow_cm3_s'],
        'pop_lip_closure_and_release': reopened_at is not None and lower <= reopened_at <= upper,
        'quiet_between_phrases_and_at_tail': all(q['peak_pcm'] <= cfg['maximum_quiet_pcm_peak'] for q in quiet),
    }
    return checks, {'nasal_port_peak_cm2': nasal_port, 'nasal_flow_peak_cm3_s': nasal_flow,
                    'pop_closed_seconds': float(time[matches[0]]) if matches.size else None,
                    'pop_reopened_seconds': reopened_at, 'quiet': quiet, 'last_vowel_median_f0_hz': median_f0}


def measure_native_endpoint(variant, config, folder, frames, rate, execute):
    stem = folder / 'native-text'
    log = folder / 'native-text.log'
    execute(['cargo', 'run', '--locked', '--release', '-p', 'chimera-cli', '--', 'render', 'text',
             str(stem), config['input']['text'], variant['body'], '--float'], cwd=UPSTREAM, stdout=log)
    native_rate, wave = wavfile.read(stem.with_suffix('.wav'))
    displayed = log.read_text().splitlines()[0]
    return {'passed': native_rate == rate and wave.shape == (frames,) and displayed == config['expected']['shown'],
            'output_frames': len(wave), 'shown': displayed}


def measure_variant(config, variant, posture, vowels, tips, upper_front, folder, probe, execute):
    cfg = config['measurement']
    rates = config['voice']
    rate = rates['output_sample_rate_hz']
    case = {
        'id': f"{config['id']}-{variant['id']}", 'upstream_revision': config['upstream_revision'],
        'hypothesis': config['hypothesis'],
        'speech_voice': {
            'input': config['input'], 'language': 'english', 'body': variant['body'], 'posture': posture,
            'internal_sample_rate_hz': config['internal_sample_rate_hz'], 'voice': dict(rates),
            'turbulence': {'scale': 1.0},
        },
    }
    if 'f0_hz' in variant:
        case['speech_voice']['voice']['f0_hz'] = variant['f0_hz']
    path = folder / 'case.json'
    timing.write(path, case)
    settings, local, outputs, upper, upper_pcm, upper_plan = speech.capture(
        path, cfg['host_block_frames'], folder, execute, (), probe=probe)
    meta = settings['speech']
    frames = settings['output_frames']
    adapted = {**settings, 'speech': {'utterances': [{'segments': ph['timing']['segments']} for ph in meta['phrases']]}}
    segments, plan_diff = fricative.compare_plans(adapted, timing.read(upper_plan), cfg['gesture_absolute_tolerance'])
    f0 = variant.get('f0_hz')
    if f0 is None:
        endpoints = config['text_f0_endpoints_hz']
        f0 = endpoints[variant['body']] if isinstance(variant['body'], str) else math.exp(
            math.fsum(w * math.log(endpoints[name]) for name, w in zip(ANCHORS, variant['weights'], strict=True)))
    lexicon = frontend_evidence(config, settings, upper_front, f0)
    joints = independent_targets(variant, vowels, tips, settings['gestures'], cfg['gesture_absolute_tolerance'])
    actual, reference = (speech.load_trace(p, frames) for p in (local, upper))
    if actual.dtype.names != reference.dtype.names:
        raise ValueError('候補と上流の観測列が一致しません')
    physical_fields = [name for name in actual.dtype.names if name != 'oral_minimum_cell']
    mismatch, errors = speech.compare_traces(actual[physical_fields], reference[physical_fields], cfg)
    minima = alveolar.compare_cell_minima(actual, reference, cfg)
    wave_path, csv_path = outputs[0]
    wave_rate, wave = wavfile.read(wave_path)
    target_wave = np.fromfile(upper_pcm, dtype='<f4')
    if (wave.shape != target_wave.shape or wave.shape != (frames,) or wave.dtype != np.float32
            or not np.isfinite(wave).all() or not np.isfinite(target_wave).all()):
        raise ValueError('PCMの長さまたは有限性が基準と異なります')
    error = np.abs(wave.astype(float) - target_wave)
    outside = np.flatnonzero(error > cfg['pcm_absolute_tolerance'])
    bits = np.flatnonzero(wave.astype('<f4').view('<u4') != target_wave.view('<u4'))
    scan = ('lip_aperture_cm', 'lip_minimum_cm2', 'noise_teeth_distance_cm', 'glottal_f0_hz',
            'glottal_area_cm2', 'radiation_derivative_cm3_s2')
    first = {}
    for name in scan:
        indices = np.flatnonzero(actual[name] != reference[name])
        if indices.size:
            i = int(indices[0])
            first[name] = {'frame': i, 'candidate_minus_upstream': float(actual[name][i] - reference[name][i])}
    expected_initial_pitch = 110.0 * (f0 / 110.0)**(-math.expm1(-64 / rate / 0.06))
    f0_error = abs(actual['glottal_f0_hz'][0] - expected_initial_pitch)
    event_checks, events = acoustic_events(actual, wave, meta, rate, cfg)
    checks = {
        'upstream_plan_and_score': plan_diff['passed'],
        'registered_lexicon_pause_stress_and_symbols': lexicon['registered_difference'] is None,
        'upstream_word_end_and_lexical_stress': lexicon['first_lexical_difference'] is None,
        'independent_statement_and_question_targets': lexicon['prosody_difference'] is None,
        'independent_body_targets': joints['difference'] is None,
        'initial_f0_glide': f0_error < cfg['initial_f0_absolute_tolerance_hz'],
        'same_output_rate_and_frames': wave_rate == rate == rates['output_sample_rate_hz']
                                       and frames == timing.read(upper_plan)['output_frames'],
        'upstream_observed_states': mismatch is None and minima['passed'],
        'upstream_pcm': not outside.size,
        'host_partition_invariance': all(sha256(w) == sha256(wave_path) and sha256(c) == sha256(csv_path) for w, c in outputs),
        **event_checks,
    }
    native = None
    if isinstance(variant['body'], str):
        native = measure_native_endpoint(variant, config, folder, frames, rate, execute)
        checks['native_upstream_text_cli'] = native['passed']
    report = {'segments': segments, 'lexical_and_prosody': lexicon, 'independent_targets': joints,
              'plan': plan_diff, 'expected_base_f0_hz': f0, 'initial_f0_error_hz': float(f0_error),
              'events': events, 'trace_first_over_tolerance': mismatch, 'trace_errors': errors,
              'oral_minimum_cells': minima,
              'trace_first_exact_difference': first, 'pcm_max_absolute_error': float(error.max()),
              'pcm_first_over_tolerance': int(outside[0]) if outside.size else None,
              'pcm_first_bit_difference_frame': int(bits[0]) if bits.size else None,
              'native_cli': native}
    return checks, report, settings['gestures']


def measure(config, posture, vowels, tips, artifacts, execute):
    execute(['cargo', 'test', '--locked', '-p', 'chimera', '--test', 'english', '--test', 'golden_phonetics_text',
             '--test', 'body_mix'], cwd=UPSTREAM, stdout=artifacts / 'upstream-tests.log')
    upper_front = capture_frontend(config, artifacts, execute)
    probe = shared.build_upstream_probe(speech.PROBE, artifacts, execute, extra_libraries=('serde_json',))
    checks, results, gestures = {}, {}, {}
    for variant in config['variants']:
        label = variant['id']
        folder = artifacts / label
        folder.mkdir()
        flags, results[label], gestures[label] = measure_variant(config, variant, posture, vowels, tips, upper_front,
                                                                 folder, probe, execute)
        checks.update({f'{label}/{key}': bool(value) for key, value in flags.items()})
    first = results['male']
    checks['identical_segment_timing_and_phrase_structure'] = all(
        r['segments'] == first['segments']
        and r['lexical_and_prosody']['phrases'] == first['lexical_and_prosody']['phrases'] for r in results.values())

    def without_pitch_value(events):
        return [{**g, 'targets': {k: v for k, v in g['targets'].items() if k != 'f0_hz'}} for g in events]

    checks['explicit_f0_changes_pitch_only_in_same_mix'] = (
        without_pitch_value(gestures['three-way']) == without_pitch_value(gestures['three-way-explicit-180'])
        and results['three-way']['lexical_and_prosody']['last_pitch_targets_hz']
        != results['three-way-explicit-180']['lexical_and_prosody']['last_pitch_targets_hz'])
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
    vowels = timing.read(vowel.TABLE)
    tips = timing.read(ipa.CASE)['expected_sibilant_tip_y_cm']
    upper_paths = ('crates/chimera-cli/src/render.rs', 'crates/chimera/src/phonetics/english.rs',
                   'crates/chimera/src/phonetics/planner.rs', 'crates/chimera/src/phonetics/vowelTargets.generated.json',
                   'crates/chimera/src/phonetics/consonantTargets.generated.json', 'crates/chimera/src/engine.rs',
                   'crates/chimera/src/voice/human_voice.rs', 'public/data/cmudict.txt.gz')
    details = {'case_id': config['id'], 'measurement_revision': config['measurement']['revision'],
               'upstream_revision': revision,
               'upper_source_sha256': {name: sha256(UPSTREAM / name) for name in upper_paths}}
    modules = (alveolar, speech, calibrated, ipa, frontend, fricative, timing, shared, vowel)
    sources = [CASE, neutral, ipa.CASE, Path(__file__).resolve(), speech.PROBE, frontend.PROBE,
               frontend.DICT, frontend.DICT_LICENSE, *shared.candidate_sources(),
               *(Path(module.__file__) for module in modules), WORKSPACE / 'tools/upstream_baseline.py']
    return shared.record_measurement(run_id, CASE, sources, details,
                                     lambda artifacts, execute: measure(config, posture, vowels, tips,
                                                                        artifacts, execute), command=None)


if __name__ == '__main__':
    raise SystemExit(main())
