"""同じ音符を体型別に歌わせ、調音、拍、音高、閉鎖、PCMを照合する。"""

import argparse
import math
from pathlib import Path
import re
import subprocess

import numpy as np

import measure_bilabial_stop as speech
import measure_body_calibrated_vowels as calibrated
import measure_body_ipa as ipa
import measure_song_voice as sung
import measure_speech_timing as timing
import measure_uniform_tube as shared
import measure_vowel_voice as vowel
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/human-body-song.json'
ANCHORS = ('male', 'female', 'child')
DURATION_SECONDS = {'p': 0.085, 's': 0.12, 'z': 0.09}


def independent_notes(settings, config):
    score, cfg = config['score'], config['measurement']
    step, start = 60 / score['bpm'], score['start_seconds']
    beats = [start]
    for note in score['notes']:
        beats.append(beats[-1] + note['beats'] * step)
    end = beats[-1] - 0.05
    onset = [0.8 * DURATION_SECONDS[syl['onset'][0]['ipa']] for syl in score['syllables']]
    stops = [beat - length for beat, length in zip(beats[:-1], onset, strict=True)]
    nuclei_end = [*stops[1:], end]
    frequencies = [440 * 2**((note['midi'] - 69) / 12) for note in score['notes']]
    notes = settings['song']['plan']['notes']
    pitch = sorted((g['t0'], g['t1'], g['targets']['f0_hz'])
                   for g in settings['gestures'] if g['label'] == 'pitch')
    phrase = settings['song']['plan']['phrases'][0]['timing']['segments']
    expected = {
        'beat_times_and_nuclei': [[a, b, a, v, hz] for a, b, v, hz in
                                  zip(beats[:-1], beats[1:], nuclei_end, frequencies, strict=True)],
        'pitch': [[a, b, hz] for stop, beat, vowel_end, hz in
                  zip(stops, beats[:-1], nuclei_end, frequencies, strict=True)
                  for a, b in ((stop, beat), (beat, vowel_end))],
        't0_t1': [(a, b) for stop, beat, vowel_end in zip(stops, beats[:-1], nuclei_end, strict=True)
                  for a, b in ((stop, beat), (beat, vowel_end))],
    }
    actual = {
        'beat_times_and_nuclei': [[n[key] for key in ('beat_seconds', 'beat_end_seconds',
                                                   'nucleus_start_seconds', 'nucleus_end_seconds', 'f0_hz')]
                                  for n in notes],
        'pitch': [list(g) for g in pitch],
        't0_t1': [[s['start_seconds'], s['end_seconds']] for s in phrase],
    }
    expected['t0_t1'] = [list(pair) for pair in expected['t0_t1']]
    difference, error = timing.compare(actual, expected, cfg['gesture_absolute_tolerance'])
    return {'difference': difference, 'maximum_absolute_error': error,
            'beat_seconds': beats[:-1], 'note_f0_hz': frequencies, 'head_consonant_start_seconds': stops}


def independent_shape(settings, variant, cfg, vowels, tips):
    gestures = settings['gestures']
    weights = variant['weights']
    expected = {'p': [-0.25], 'ɑ': [calibrated.expected_patch('ɑ', weights, vowels, set())] * 3}
    actual = {'p': [g['targets']['lip_aperture_cm'] for g in gestures if g['label'] == 'p'
                    and 'lip_aperture_cm' in g['targets']],
              'ɑ': [g['targets'] for g in gestures if g['label'] == 'ɑ']}
    for ipa in ('s', 'z'):
        expected[ipa] = [math.fsum(w * tips[name][ipa] for name, w in zip(ANCHORS, weights, strict=True))]
        actual[ipa] = [g['targets']['tongue_tip_y_cm'] for g in gestures if g['label'] == ipa
                       and 'tongue_tip_y_cm' in g['targets']]
    difference, error = timing.compare(actual, expected, cfg['gesture_absolute_tolerance'])
    return {'difference': difference, 'maximum_absolute_error': error, 'targets': actual}


def first_binary_difference(local_trace, upper_trace, count, files, upper_pcm):
    from scipy.io import wavfile
    selected = ('lip_minimum_cm2', 'noise_teeth_distance_cm', 'smoothed_f0_hz',
                'glottal_area_cm2', 'radiation_derivative_cm3_s2')

    def observations(path):
        return np.genfromtxt(path, delimiter=',', names=True, usecols=selected, max_rows=count)

    actual, upper = (observations(path) for path in (local_trace, upper_trace))
    series = {}
    for name in selected:
        samples = np.flatnonzero(actual[name] != upper[name])
        if samples.size:
            index = int(samples[0])
            series[name] = {'frame': index, 'candidate_minus_upstream': float(actual[name][index] - upper[name][index])}
    _, waveform = wavfile.read(files[0][0])
    reference = np.fromfile(upper_pcm, dtype='<f4')
    indices = np.flatnonzero(waveform.astype('<f4').view('<u4') != reference.view('<u4'))
    return {'series': series, 'first_pcm_bit_difference_frame': int(indices[0]) if indices.size else None}


def measure_variant(config, variant, posture, endpoints, vowels, tips, artifacts, probe, execute):
    cfg = config['measurement']
    case = {
        'id': f"{config['id']}-{variant['id']}", 'upstream_revision': config['upstream_revision'],
        'hypothesis': config['hypothesis'],
        'song_voice': {**{key: config[key] for key in ('score', 'voice', 'internal_sample_rate_hz', 'vibrato_cents')},
                       'body': variant['body'], 'posture': posture, 'turbulence': {'scale': 1.0}},
        'measurement': cfg,
    }
    path = artifacts / 'case.json'
    timing.write(path, case)
    captured = speech.capture(path, cfg['host_block_frames'], artifacts, execute, sung.SUITES, probe=probe)
    settings, local_trace, files, upper_trace, upper_pcm, _ = captured
    scale = math.fsum(w * endpoints[name]['scale'] for name, w in zip(ANCHORS, variant['weights'], strict=True))
    report = sung.compare_outputs(case, *captured, body_scale=scale)
    note = independent_notes(settings, config)
    shape = independent_shape(settings, variant, cfg, vowels, tips)
    report['independent_notes'] = note
    report['independent_oral_targets'] = shape
    report['body_scale'] = scale

    count = settings['output_frames']
    rate = config['voice']['output_sample_rate_hz']
    frication = {}
    source_columns = ('teeth_noise_source', 'teeth_noise_level', 'noise_minimum_cm2',
                      'glottal_voicing', 'teeth_noise_forward_pressure')
    trace = np.genfromtxt(local_trace, delimiter=',', names=True, usecols=source_columns, max_rows=count)
    for span in report['plan']['segments']:
        if span['ipa'] in ('s', 'z'):
            limits = {**cfg, 'center_fraction': cfg['fricative_center_fraction']}
            frication[span['ipa']] = ipa.sibilant_activity(trace, span, rate, scale, limits)
    report['frication'] = frication
    report['first_numerical_differences'] = first_binary_difference(local_trace, upper_trace, count, files, upper_pcm)
    report['checks'].update({
        'beat_timing_and_pitch_goals_from_midi': note['difference'] is None,
        'independent_body_specific_targets': shape['difference'] is None,
        's_and_z_frication_during_heads': all(v['passed'] for v in frication.values()) and len(frication) == 2,
    })
    return report


def measure(config, posture, endpoints, vowels, tips, artifacts, execute):
    suites = (*sung.SUITES, 'body_mix')
    args = [word for suite in suites for word in ('--test', suite)]
    execute(['cargo', 'test', '--locked', '-p', 'chimera', *args], cwd=UPSTREAM,
            stdout=artifacts / 'upstream-tests.log')
    probe = shared.build_upstream_probe(speech.PROBE, artifacts, execute, extra_libraries=('serde_json',))
    results, checks = {}, {}
    for variant in config['variants']:
        label = variant['id']
        folder = artifacts / label
        folder.mkdir()
        record = measure_variant(config, variant, posture, endpoints, vowels, tips, folder, probe, execute)
        results[label] = record
        checks.update({f'{label}/{key}': bool(value) for key, value in record['checks'].items()})
    first_plan = results['male']['plan']
    checks['note_and_segment_timing_invariant_across_bodies'] = all(
        r['plan']['notes'] == first_plan['notes'] and r['plan']['segments'] == first_plan['segments'] for r in results.values())
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
    endpoints = timing.read(ipa.BODY_TABLE)['measurement']['reference_endpoints']
    vowels = timing.read(vowel.TABLE)
    tips = timing.read(ipa.CASE)['expected_sibilant_tip_y_cm']
    upper_paths = ('crates/chimera-cli/src/render.rs', 'crates/chimera/src/phonetics/sing.rs',
                   'crates/chimera/src/phonetics/planner.rs', 'crates/chimera/src/phonetics/inventory.rs',
                   'crates/chimera/src/phonetics/vowelTargets.generated.json',
                   'crates/chimera/src/phonetics/consonantTargets.generated.json',
                   'crates/chimera/src/voice/human_voice.rs', 'crates/chimera/tests/sing_fast.rs',
                   'crates/chimera/tests/sung_release.rs')
    details = {'case_id': config['id'], 'upstream_revision': revision,
               'upper_source_sha256': {name: sha256(UPSTREAM / name) for name in upper_paths}}
    modules = (speech, calibrated, ipa, sung, timing, shared, vowel, sung.alveolar, sung.speech)
    sources = [CASE, neutral, ipa.CASE, ipa.BODY_TABLE, Path(__file__).resolve(), speech.PROBE,
               *shared.candidate_sources(), *(Path(module.__file__) for module in modules),
               WORKSPACE / 'tools/upstream_baseline.py']
    return shared.record_measurement(run_id, CASE, sources, details,
                                     lambda artifacts, execute: measure(config, posture, endpoints, vowels, tips,
                                                                        artifacts, execute), command=None)


if __name__ == '__main__':
    raise SystemExit(main())
