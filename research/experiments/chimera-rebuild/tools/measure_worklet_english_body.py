"""英語発話の体型選択と、ブラウザで保存したケースのCLI再現を検証する。"""

import argparse
import gzip
import hashlib
import math
from pathlib import Path
import re
import shutil
import subprocess

import numpy as np
from scipy.io import wavfile

import measure_bilabial_stop as speech
import measure_body_english as english
import measure_sibilant as fricative
import measure_speech_timing as timing
import measure_uniform_tube as shared
import measure_wasm_fixed as wasm
from measure_worklet_fixed import CAPTURE, ROOT, WEB, web_sources
from upstream_baseline import UPSTREAM, WORKSPACE, sha256

CASE = WORKSPACE / 'cases/worklet-english-body.json'


def reference_artifacts(config, source, pcm_filename='upstream-pcm.f32'):
    run = WORKSPACE / 'runs' / config['reference_run']
    manifest = timing.read(run / 'manifest.json')
    case_input = next(item for item in manifest['inputs'] if item['path'] == str(source.relative_to(WORKSPACE)))
    if (manifest['status'] != 'pass' or manifest['upstream_revision'] != config['upstream_revision']
            or case_input['sha256'] != sha256(source)):
        raise ValueError('固定上流の参照データと登録ケースが一致しません')
    names = {variant['id']: run / 'artifacts' / variant['id'] for variant in timing.read(source)['variants']}
    files = [folder / name for folder in names.values()
             for name in ('case.json', 'upstream-plan.json', pcm_filename, 'upstream-voicing.csv')]
    recorded = {item['path']: item['sha256'] for item in manifest['outputs']}
    for path in files:
        if recorded.get(str(path.relative_to(run))) != sha256(path):
            raise ValueError(f'固定上流の保存データとハッシュが一致しません（{path}）')
    return names, [run / 'manifest.json', *files]


def compare_observations(report, native, upper, limits, frames, *, live=False):
    names = report['columns']
    fields = limits['observed_fields']
    stride = limits['observation_stride_frames']
    points = np.minimum(np.arange(stride, frames + stride, stride), frames) - 1
    rows = np.asarray(report['observations'], dtype=float)
    if (names[:2] != ['output_frame' if live else 'context_frame', 'frames_rendered']
            or any(field not in names for field in fields)
            or rows.shape != (len(points), len(names)) or not np.isfinite(rows).all()):
        raise ValueError('ブラウザの観測列、長さ、有限性が登録条件と一致しません')
    observed = np.empty(len(points), dtype=[('frame', int), *((f, float) for f in fields)])
    observed['frame'] = points
    for field in fields:
        observed[field] = rows[:, names.index(field)]
    cli_states = wasm.compare_states(
        np.column_stack([observed[f] for f in fields]),
        np.column_stack([native[f][points] for f in fields]),
        fields, points, limits['candidate_trace_peak_relative_tolerance'])
    difference, upper_states = speech.compare_traces(
        observed, upper[['frame', *fields]][points],
        {**limits, 'audio_state_peak_relative_tolerance': limits['upper_state_peak_relative_tolerance']})
    if difference is not None:
        difference['frame'] = int(points[difference['frame']])
    first_upper_differences = []
    for field in fields:
        delta = observed[field] - upper[field][points]
        first = wasm.first_index(delta != 0)
        if first is not None:
            first_upper_differences.append(
                {'frame': int(points[first]), 'field': field, 'browser_minus_upstream': float(delta[first])})
    first_upper_differences.sort(key=lambda item: item['frame'])
    checks = {
        'observation_clock': bool(np.array_equal(rows[:, 0], points) and np.array_equal(rows[:, 1], points + 1)),
        'cli_observed_states': all(value['status'] for value in cli_states.values()),
        'upstream_observed_states': difference is None and all(
            upper_states[field]['absolute'] <= limits['geometry_absolute_tolerance']
            for field in ('velum_port_area_cm2', 'noise_minimum_cm2') if field in upper_states),
    }
    return observed, checks, {'points': len(points), 'cli_states': cli_states, 'upstream_states': upper_states,
                              'first_upper_difference_by_field': first_upper_differences,
                              'first_upper_state_over_tolerance': difference}


def compare_variant(variant, source, limits, upper_path, browser, artifacts, execute):
    label = variant['id']
    frames = limits['output_frames']
    rate = limits['output_rate_hz']
    quantum = limits['expected_render_quantum_frames']
    case_path = artifacts / f'{label}-case.json'
    report = timing.read(artifacts / f'{label}.json')
    settings_file = artifacts / f'{label}-cli-settings.json'
    trace_file = artifacts / f'{label}-cli-trace.csv'
    pcm_file = artifacts / f'{label}-cli.wav'
    execute([*english.CLI, 'inspect', str(case_path)], stdout=settings_file)
    execute([*english.CLI, 'render', str(case_path), str(trace_file)])
    execute([*english.CLI, 'render-pcm', str(case_path), str(pcm_file),
             str(artifacts / f'{label}-cli-pcm.csv'), str(quantum)])
    cli = timing.read(settings_file)
    upper_plan = timing.read(upper_path / 'upstream-plan.json')
    browser_rate, wave = wavfile.read(artifacts / f'{label}.wav')
    native_rate, native = wavfile.read(pcm_file)
    upper = np.fromfile(upper_path / 'upstream-pcm.f32', dtype='<f4')
    if any(samples.shape != (frames,) or samples.dtype != np.float32 for samples in (wave, native, upper)):
        raise ValueError('PCMの長さまたは型が登録値と一致しません')
    cli_pcm = wasm.compare_pcm(wave, native, 0)
    upper_pcm = wasm.compare_pcm(wave, upper, limits['upper_pcm_absolute_tolerance'])
    tolerance = limits['plan_numeric_tolerance']
    plan_diff, plan_max = timing.compare(report['speech'], cli['speech'], tolerance)
    gesture_diff, gesture_max = timing.compare(report['gestures'], cli['gestures'], tolerance)
    phrases = report['speech']['phrases']
    adapted = {'speech': {'utterances': [p['timing'] for p in phrases]}, 'gestures': report['gestures']}
    _, upper_check = fricative.compare_plans(adapted, upper_plan, tolerance)
    native_states, upper_states = (speech.load_trace(p, frames) for p in (trace_file, upper_path / 'upstream-voicing.csv'))
    observed, trace_checks, trace = compare_observations(report, native_states, upper_states, limits, frames)
    event_checks, events = english.acoustic_events(observed, wave, report['speech'], rate, source['measurement'])
    base = variant.get('f0_hz')
    if base is None:
        endpoints = source['text_f0_endpoints_hz']
        base = (endpoints[variant['body']] if isinstance(variant['body'], str) else math.exp(math.fsum(
            weight * math.log(endpoints[name]) for name, weight in zip(english.ANCHORS, variant['weights'], strict=True))))
    targets = [p['pitch'][-1]['targets']['f0_hz'] for p in phrases]
    expected = [base * factor for factor in source['expected']['last_pitch_multipliers']]
    replay = timing.read(case_path)
    replay_voice = replay['speech_voice']
    original_voice = timing.read(upper_path / 'case.json')['speech_voice']
    counts = report['tract']['counts']
    checks = {
        'downloaded_case_matches_registered_input': (
            replay['upstream_revision'] == source['upstream_revision']
            and browser['replayFilename'] == 'worklet-english-case.json'
            and replay_voice['input']['text'] == source['input']['text']
            and replay_voice['input']['rate'] == source['input']['rate']
            and replay_voice['input']['start_seconds'] == source['expected']['phrase_span_seconds'][0][0]
            and all(replay_voice.get(key) == value for key, value in original_voice.items() if key != 'input')),
        'format_and_rate': (report['sampleRate'] == report['workletSampleRate'] == browser_rate == native_rate == rate
            and report['outputFrames'] == report['framesRendered'] == cli['output_frames'] == upper_plan['output_frames'] == frames
            and report['outputChannels'] == 1 and cli['decimation_factor'] * rate == limits['internal_rate_hz']),
        'browser_case_and_transcription': (report['body'] == variant['body'] and report['input'] == source['input']['text']
            and report['speech']['shown'] == browser['shown'] == source['expected']['shown']
            and not browser['errors'] and browser['recovered']),
        'worklet_clock': (report['shortestQuantum'] == report['longestQuantum'] == quantum
            and report['firstContextFrame'] == report['discontinuities'] == 0
            and report['callbacks'] == (frames + quantum - 1) // quantum),
        'tract_cell_counts': counts == limits['expected_cells'][label],
        'registered_base_f0_and_phrase_targets': (abs(report['basePitchHz'] - base) <= tolerance
            and timing.compare(targets, expected, tolerance)[0] is None),
        'cli_plan_and_gestures': plan_diff is None and gesture_diff is None,
        'upstream_plan_and_gestures': upper_check['passed'],
        'cli_pcm_bit_equality': cli_pcm['first_bit_difference_frame'] is None,
        'upstream_pcm': upper_pcm['first_frame_over_tolerance'] is None,
        **trace_checks, **event_checks,
    }
    return checks, {'base_f0_hz': report['basePitchHz'], 'last_pitch_targets_hz': targets, 'tract_cells': counts,
                    'browser_events': events, 'cli_pcm': cli_pcm, 'upstream_pcm': upper_pcm,
                    'plan_first_difference': plan_diff, 'maximum_plan_checked_error': plan_max,
                    'gesture_first_difference': gesture_diff, 'maximum_gesture_checked_error': gesture_max,
                    'upstream_plan': upper_check, **trace}


def measure(config, source_path, references, geometry_path, artifacts, execute, bun):
    source = timing.read(source_path)
    limits = config['measurement']
    execute([*bun, 'run', 'build'], cwd=WEB, stdout=artifacts / 'browser-build.log')
    execute(['cargo', 'test', '--locked', '-p', 'chimera', '--test', 'body_mix', '--test', 'engine'],
            cwd=UPSTREAM, stdout=artifacts / 'upstream-tests.log')
    binary = artifacts / 'vocal_wasm.wasm'
    shutil.copyfile(WORKSPACE / wasm.WASM, binary)
    execute(['node', str(CAPTURE), str(artifacts), str(CASE), str(source_path)])
    browser = timing.read(artifacts / 'browser-run.json')
    dictionary = english.frontend.DICT
    compressed, binary_hash = sha256(dictionary), sha256(binary)
    expanded = hashlib.sha256(gzip.decompress(dictionary.read_bytes())).hexdigest()
    geometry = timing.read(geometry_path)['cases']
    checks = {'registered_cell_counts_match_geometry_reference': all(
        counts == [tube['cells'] for tube in geometry[label.removesuffix('-explicit-180')]['geometry']['tubes']
                   if tube['name'] in ('pharynx', 'oral')] for label, counts in limits['expected_cells'].items())}
    cases = {}
    for variant in source['variants']:
        label = variant['id']
        site = browser[label]
        flags, cases[label] = compare_variant(variant, source, limits, references[label], site, artifacts, execute)
        flags['browser_assets'] = (site['servedWasmSha256'] == binary_hash
            and compressed == sha256(UPSTREAM / 'public/data/cmudict.txt.gz')
            and site['dictionaryResponseSha256'] == (compressed if site['dictionaryResponseIsGzip'] else expanded))
        checks.update({f'{label}/{name}': bool(value) for name, value in flags.items()})
    return {'checks': checks, 'cases': cases, 'browser': browser}


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
    source = WORKSPACE / 'cases' / config['native_case']
    references, files = reference_artifacts(config, source)
    geometry = WORKSPACE / 'runs' / config['geometry_reference_run'] / 'summary.json'
    bun = ['bun'] if shutil.which('bun') else ['npx', '--yes', '--package=bun@1.4.4', '--', 'bun']
    inputs = [CASE, source, geometry, *files, Path(__file__).resolve(), *shared.candidate_sources(), *web_sources(),
              *(Path(module.__file__) for module in (speech, english, fricative, timing, shared, wasm)),
              *(WORKSPACE / 'tools' / name for name in ('upstream_baseline.py', 'measure_worklet_fixed.py',
                'measure_body_calibrated_vowels.py', 'measure_body_ipa.py', 'measure_english_frontend.py',
                'measure_alveolar_stop.py', 'measure_pcm_output.py', 'measure_vowel_voice.py'))]
    metadata = {'case_id': config['id'], 'upstream_revision': revision, 'reference_run': config['reference_run'],
                'input_root': '$REPOSITORY', 'node': subprocess.check_output(['node', '--version'], text=True).strip(),
                'bun': subprocess.check_output([*bun, '--version'], text=True).strip()}
    return shared.record_measurement(run_id, CASE, inputs, metadata,
                                     lambda out, run: measure(config, source, references, geometry, out, run, bun),
                                     command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
