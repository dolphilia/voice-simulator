"""/ð/ の調音・放射と、TSPの通常の英語発話入口を照合する。"""

import argparse
import csv
import os
from pathlib import Path
import re
import subprocess

import numpy as np
from scipy.io import wavfile

import measure_alveolar_stop as cells
import measure_bilabial_stop as voice
import measure_sibilant as frication
import measure_speech_timing as timing
from measure_uniform_tube import build_upstream_probe, candidate_sources, record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/dental-dh.json'


def registered_gestures(segments, actual, variant, tolerance):
    dh, = [segment for segment in segments if segment['ipa'] == 'ð']
    a, b = dh['t0'], dh['t1']
    rate = max(variant['rate'], 1)
    closed = variant['kind'] == 'stop'
    delay = min(variant.get('delay_seconds', 0), max(0, b - a - .03))
    aim = a + delay
    label = 'stop-like ð' if closed else 'voiced frication'
    expected = [
        {'label': 'ð', 't0': aim - (.031 if closed else .008),
         't1': max(aim + .01, b - (.02 if closed else 0)), 'rampIn': .03 / rate, 'rampOut': .018 / rate,
         'releaseHold': .045 / rate, 'speed': 1.55 if closed else 1.3, 'strength': 40.0,
         'targets': {'tongue_tip_x_cm': 6.85, 'tongue_tip_y_cm': variant['tip_y_cm']}},
        {'label': label, 't0': a - .015, 't1': b, 'rampIn': .03 / rate, 'rampOut': .03 / rate,
         'strength': 6.0 if closed else 3.0, 'targets': {'abduction_cm2': variant['opening_cm2']}},
    ]
    labels = {'ð', label}
    if variant.get('palatalized'):
        labels.add('palatalized')
        expected.append({'label': 'palatalized', 't0': a, 't1': b, 'rampIn': .04 / rate, 'rampOut': .04 / rate,
                         'strength': 3.0, 'targets': {'tongue_body_x_cm': 3.8, 'tongue_body_y_cm': 7.95}})
    observed = [gesture for gesture in actual if gesture['label'] in labels]
    first, error = timing.compare(observed, expected, tolerance)
    return first is None and dh['kind'] == variant['kind'], {
        'segment': dh, 'applied_closure_delay_seconds': delay, 'first_difference': first,
        'maximum_checked_difference': error, 'registered': expected, 'observed': observed,
    }


def closure_level(pcm, rate, dh, vowel, block):
    blocks = pcm[:len(pcm) // block * block].astype(float).reshape((-1, block))
    powers = np.mean(blocks**2, axis=1)
    ends = np.arange(1, len(blocks) + 1) * block / rate
    power = lambda a, b: np.mean(powers[(ends >= a) & (ends <= b)])
    closure = power(dh['t0'], (dh['t0'] + dh['t1']) / 2)
    reference = power(vowel['t0'], vowel['t1'])
    return float(10 * np.log10((closure + 1e-14) / (reference + 1e-14)))


def dental_observation(trace, span, rate, fractional_range):
    a, b = span['t0'], span['t1']
    lo, hi = [a + (b - a) * f for f in fractional_range]
    t = trace['frame'] / rate
    middle = trace[(t >= lo) & (t < hi)]
    names = ('tongue_tip_x_cm', 'tongue_tip_y_cm', 'oral_minimum_cm2', 'abduction_cm2', 'glottal_voicing')
    return {**{name: float(np.median(middle[name])) for name in names},
            'closed_frames': int(np.count_nonzero(middle['oral_minimum_cm2'] == 0)),
            'constriction_noise_rms_dyn_cm2': float(np.sqrt(np.mean(middle['constriction_noise_forward_pressure']**2))),
            'noise_registered_frames': int(np.count_nonzero(middle['constriction_noise_source'] >= 0)),
            'observed_frames': len(middle)}


def compare_variant(config, fixture, variant, directory, probe, execute):
    limits = config['measurement']
    directory.mkdir()
    source = {**fixture, 'body': variant['body'], 'input': {k: variant[k] for k in ('id', 'text', 'rate')},
              'voice': {**fixture['voice'], 'f0_hz': variant['f0_hz']}}
    # 音素の追加だけで自動乱流が起動することも、実際の出力列で確認する。
    source.pop('turbulence', None)
    english = variant.get('language') == 'english'
    if english:
        source['language'] = 'english'
    path = directory / 'case.json'
    timing.write(path, {'upstream_revision': config['upstream_revision'], 'speech_voice': source})
    settings, trace, partitions, upper_trace, upper_pcm, upper_plan = voice.capture(
        path, limits['host_block_frames'], directory, execute, (), probe=probe)
    reference = timing.read(upper_plan)
    adapted = settings
    if english:
        adapted = {**settings, 'speech': {'utterances': [
            {'segments': entry['timing']['segments']} for entry in settings['speech']['phrases']]}}
    segments, report = frication.compare_plans(adapted, reference, limits['gesture_abs_tolerance'])
    count = settings['output_frames']
    native, upper = [voice.load_trace(p, count) for p in (trace, upper_trace)]
    physical = [field for field in native.dtype.names if field != 'oral_minimum_cell']
    differences, errors = frication.source_comparison(native[physical], upper[physical], limits)
    minimum_cells = cells.compare_cell_minima(native, upper, {'closed_area_cm2': .0002,
                                                            'geometry_absolute_tolerance': limits['geometry_abs_tolerance']})
    rate, pcm = wavfile.read(partitions[0][0])
    upper_samples = np.fromfile(upper_pcm, dtype='<f4')
    if any(x.shape != (count,) or x.dtype != np.float32 or not np.isfinite(x).all() for x in (pcm, upper_samples)):
        raise ValueError('PCMの数、形式または有限性が条件外です')
    delta = np.abs(pcm.astype(float) - upper_samples)
    different = np.flatnonzero(pcm.view(np.uint32) != upper_samples.view(np.uint32))
    checks = {'upstream_plan': report['passed'], 'physical_trace': not differences and minimum_cells['passed'],
              'upstream_pcm': bool(delta.max() <= limits['pcm_abs_tolerance']),
              'sample_rates_and_frames': (count == reference['output_frames'] and rate == limits['output_rate_hz']
                                         and source['internal_sample_rate_hz'] == limits['internal_rate_hz']),
              'host_partition': all(sha256(wav) == sha256(partitions[0][0]) and sha256(csv_path) == sha256(partitions[0][1])
                                    for wav, csv_path in partitions)}
    result = {'checks': checks, 'plan_comparison': report, 'first_trace_differences': differences,
              'trace_errors': errors, 'oral_minimum_cells': minimum_cells, 'output_frames': count,
              'first_pcm_bit_difference': int(different[0]) if different.size else None,
              'maximum_pcm_absolute_difference': float(delta.max())}
    if english:
        result['dental_segments'] = [segment for segment in segments if segment['ipa'] == 'ð']
        checks['planned_dental'] = bool(result['dental_segments'])
        return result
    plan_ok, dental_plan = registered_gestures(segments, settings['gestures'], variant, limits['gesture_abs_tolerance'])
    result['registered_dental_plan'] = dental_plan
    result['center_observation'] = [dental_observation(track, dental_plan['segment'], rate, limits['center_fraction'])
                                   for track in (native, upper)]
    checks['registered_dental_plan'] = plan_ok
    if variant.get('quiet_closure'):
        vowel = next(part for part in segments if part.get('stress') == 1)
        before = [closure_level(samples, rate, dental_plan['segment'], vowel, limits['host_block_frames'][0])
                  for samples in (pcm, upper_samples)]
        checks['quiet_closure'] = all(db < limits['maximum_closure_db_relative_to_vowel'] for db in before)
        result['closure_db_relative_to_vowel'] = before
    return result


def english_inputs(config, previous, transcript_path, directory, execute):
    with transcript_path.open(newline='') as file:
        transcripts = {index: (speaker, text) for index, speaker, text in csv.reader(file, delimiter='\t')}
    directory.mkdir()
    results = {}
    for index in config['recording_ids']:
        speaker, text = transcripts[index]
        path = directory / f'{index}.json'
        execute([str(WORKSPACE / 'target/release/vocal-cli'), 'english', text], stdout=path)
        unavailable = timing.read(path)['unavailable_speech_symbols']
        earlier = previous['observations'][index]
        matches = re.search(r'\(([^()]*)\)$', earlier.get('error', ''))
        old = set(matches.group(1).split()) if matches else set()
        results[index] = {'before': sorted(old), 'after': unavailable,
                          'matches_prediction': old - {'ð'} == set(unavailable)}
    newly_renderable = [index for index, report in results.items() if report['before'] and not report['after']]
    checks = {'unavailable_only_changes_dh': all(row['matches_prediction'] for row in results.values()),
              'registered_newly_renderable': newly_renderable == config['newly_renderable']}
    variants = []
    for index in newly_renderable:
        speaker, text = transcripts[index]
        female = speaker.startswith('F')
        variants.append({'id': index, 'text': text, 'body': 'female' if female else 'male',
                         'f0_hz': 205 if female else 112, 'rate': 1, 'language': 'english'})
    return checks, results, variants


def measure(config, base, previous, transcripts, artifacts, execute):
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera', '--test', 'stop_spans'], cwd=UPSTREAM,
            stdout=artifacts / 'upstream-stop-spans.log')
    probe = build_upstream_probe(voice.PROBE, artifacts, execute, extra_libraries=('serde_json',))
    evidence = {variant['id']: compare_variant(config, base, variant, artifacts / variant['id'], probe, execute)
                for variant in config['speech']}
    checks, inputs, newly_renderable = english_inputs(config['english'], previous, transcripts,
                                                      artifacts / 'english-plans', execute)
    for variant in newly_renderable:
        evidence[variant['id']] = compare_variant(config, base, variant, artifacts / variant['id'], probe, execute)
    for label, row in evidence.items():
        checks.update({f'{label}:{name}': result for name, result in row['checks'].items()})
    return {'checks': checks, 'contexts': evidence, 'english_inputs': inputs}


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
    fixture = CASE.parent / config['base_case']
    previous = WORKSPACE / 'runs' / config['english']['preflight_run'] / 'summary.json'
    transcripts = UPSTREAM / config['english']['transcripts']
    inputs = [CASE, Path(__file__).resolve(), fixture, previous, transcripts, voice.PROBE, Path(voice.__file__),
              Path(cells.__file__), Path(frication.__file__), Path(timing.__file__), *candidate_sources()]
    base = timing.read(fixture)['speech_voice']
    return record_measurement(args.run_id, CASE, inputs,
                              {'case_id': config['id'], 'revision': config['revision'], 'upstream_revision': revision,
                               'invoked_from': str(Path.cwd())},
                              lambda out, execute: measure(config, base, timing.read(previous), transcripts, out, execute),
                              command=None, input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
