"""体型別のIPA発話を実ブラウザで実行し、保存ケース、固定上流、CLIに照合する。"""

import argparse
import math
from pathlib import Path
import re
import shutil
import subprocess

import numpy as np
from scipy.io import wavfile

import measure_bilabial_stop as speech
import measure_body_ipa as ipa
import measure_sibilant as fricative
import measure_speech_timing as timing
import measure_uniform_tube as shared
import measure_wasm_fixed as wasm
from measure_worklet_english_body import compare_observations, reference_artifacts
from measure_worklet_fixed import CAPTURE, ROOT, WEB, web_sources
from upstream_baseline import UPSTREAM, WORKSPACE, sha256

CASE = WORKSPACE / 'cases/worklet-ipa-body.json'


def consonants(observed, spans, native_stop, measure, rate, scale, limits):
    points = observed['frame']
    stop = next(span for span in spans if span['ipa'] == 'p')
    t0 = math.floor((stop['t0'] + limits['closure_offset_seconds'][0]) * rate)
    t1 = math.ceil((stop['t1'] + limits['release_offset_seconds'][1]) * rate)
    closed = (observed['lip_minimum_cm2'] < limits['closed_area_cm2']) & (points >= t0) & (points < t1)
    rise = wasm.first_index(closed)
    fall = wasm.first_index(~closed & np.r_[False, closed[:-1]])
    events = [int(points[index]) for index in (rise, fall)] if rise is not None and fall is not None else []
    expected = [native_stop.get(key) for key in ('first_closed_frame', 'first_reopened_frame')]
    delay = [event - saved for event, saved in zip(events, expected)] if native_stop['passed'] else []
    checks = {'stop_closure_release': len(delay) == 2 and all(
        0 <= value <= measure['maximum_sampled_event_delay_frames'] for value in delay)}
    noise = {}
    for span in spans:
        key = span['ipa']
        if key not in ('s', 'z'):
            continue
        window = ipa.frames_for_span(span, rate, int(points[-1] + 1), limits['center_fraction'])
        center = observed[(points >= window.start) & (points < window.stop)]
        excited = center['teeth_noise_source'] >= 0
        active = float(np.mean(center['teeth_noise_level'] > 0))
        low, high = limits['central_normalized_narrowing_interval_cm2']
        median = float(np.median(center['noise_minimum_cm2'][excited])) if excited.any() else None
        pressure = float(np.sqrt(np.mean(center['teeth_noise_forward_pressure'] ** 2)))
        checks[f'{key}_teeth_excitation'] = (median is not None and low <= median / scale**2 <= high
            and pressure > 0.0 and active >= limits['minimum_teeth_active_fraction'])
        noise[key] = {'points': len(center), 'active_fraction': active, 'minimum_median_cm2': median,
                      'teeth_forward_pressure_rms_dyn_cm2': pressure}
    return checks, {'stop_event_frames': events, 'event_delay_frames': delay, 'teeth': noise}


def compare_mode(label, variant, live, observed_site, source, limits, cli, native_trace, upper_trace, audio,
                 spans, native_stop, upper_plan, scale, binary_hash, artifacts):
    prefix = f'{label}-{"live" if live else "offline"}'
    report = timing.read(artifacts / f'{prefix}.json')
    rate = source['measurement']['output_rate_hz']
    frames = limits['output_frames']
    fs, wave = wavfile.read(artifacts / f'{prefix}.wav')
    if wave.shape != (frames,) or wave.dtype != np.float32:
        raise ValueError('ブラウザのPCMの型と長さが登録条件と一致しません')
    cli_pcm = wasm.compare_pcm(wave, audio[0], 0)
    upper_pcm = wasm.compare_pcm(wave, audio[1], limits['upper_pcm_absolute_tolerance'])
    plan = report['speech']
    tol = limits['plan_numeric_tolerance']
    keys = ('utterances', 'rate', 'render_end_seconds')
    plan_delta, plan_error = timing.compare(plan, {key: cli['speech'][key] for key in keys}, tol)
    score_delta, score_error = timing.compare(report['gestures'], cli['gestures'], tol)
    _, upper = fricative.compare_plans({'speech': plan, 'gestures': report['gestures']}, upper_plan, tol)
    observed, observation_flags, evidence = compare_observations(
        report, native_trace, upper_trace, limits, frames, live=live)
    flags, events = consonants(observed, spans, native_stop, limits, rate, scale, source['measurement'])
    indices = observed['frame']
    quantum = limits['expected_render_quantum_frames']
    body_f0 = variant['f0_hz']
    initial = 110.0 * (body_f0 / 110.0)**(-math.expm1(-64 / rate / 0.06))
    first_error = abs(float(observed['glottal_f0_hz'][0]) - initial)
    checks = {
        'browser_input_assets_and_format': (
            report['body'] == variant['body'] and report['input'] == source['input']['text']
            and observed_site['servedWasmSha256'] == binary_hash and not observed_site['errors']
            and observed_site['recovered'] and fs == rate == report['sampleRate'] == report['workletSampleRate']
            and report['outputFrames'] == report['framesRendered'] == frames and report['outputChannels'] == 1),
        'plan_and_score': plan_delta is None and score_delta is None and upper['passed'],
        'body_f0_and_first_control_step': abs(report['basePitchHz'] - body_f0) <= tol
            and first_error <= source['measurement']['probe_first_f0_abs_tolerance_hz'],
        'tract_counts': report['tract']['counts'] == limits['expected_cells'][label],
        'cli_pcm_bit_equal': cli_pcm['first_bit_difference_frame'] is None,
        'upstream_pcm': upper_pcm['first_frame_over_tolerance'] is None,
        'excitation_source_indices': bool(np.array_equal(observed['teeth_noise_source'], upper_trace['teeth_noise_source'][indices])),
        'worklet_quantum': (report['shortestQuantum'] == report['longestQuantum'] == quantum
            and report['callbacks'] == (frames + quantum - 1) // quantum and report['discontinuities'] == 0),
        **observation_flags, **flags,
    }
    if live:
        clock = report['realtime']
        checks['start_and_cancel'] = (
            report['firstContextFrame'] == clock['scheduledContextFrame']
            and clock['scheduledContextFrame'] - clock['armedContextFrame'] == limits['expected_live_schedule_lead_frames']
            and observed_site['stopped'])
    else:
        checks['start_at_zero'] = report['firstContextFrame'] == 0
    return checks, {'observed_f0_hz': report['basePitchHz'], 'first_f0_error_hz': first_error,
                    'cells': report['tract']['counts'], 'cli_pcm': cli_pcm, 'upstream_pcm': upper_pcm,
                    'plan_first_difference': plan_delta, 'plan_max_error': plan_error,
                    'gesture_first_difference': score_delta, 'gesture_max_error': score_error,
                    'upper_plan': upper, 'events': events, **evidence}


def compare_variant(variant, source, limits, reference, sites, binary_hash, table, bodies, artifacts, execute):
    label = variant['id']
    saved = artifacts / f'{label}-offline-case.json'
    live = artifacts / f'{label}-live-case.json'
    report = artifacts / f'{label}-cli-plan.json'
    trace = artifacts / f'{label}-cli-trace.csv'
    pcm = artifacts / f'{label}-cli.wav'
    execute([*ipa.CLI, 'inspect', str(saved)], stdout=report)
    execute([*ipa.CLI, 'render', str(saved), str(trace)])
    execute([*ipa.CLI, 'render-pcm', str(saved), str(pcm),
             str(artifacts / f'{label}-cli-pcm.csv'), str(limits['expected_render_quantum_frames'])])
    cli = timing.read(report)
    frames = limits['output_frames']
    rate = source['measurement']['output_rate_hz']
    upper_plan = timing.read(reference / 'upstream-plan.json')
    spans, _ = fricative.compare_plans(cli, upper_plan, limits['plan_numeric_tolerance'])
    native_rate, wave = wavfile.read(pcm)
    compared = (wave, np.fromfile(reference / 'upstream.f32', dtype='<f4'))
    if any(samples.shape != (frames,) or samples.dtype != np.float32 for samples in compared):
        raise ValueError('CLIまたは上流のPCMの型と長さが登録条件と一致しません')
    native, upstream = (speech.load_trace(p, frames) for p in (trace, reference / 'upstream-voicing.csv'))
    native_stop = ipa.stop_closure(wave, native, next(span for span in spans if span['ipa'] == 'p'),
                                  rate, source['measurement'])
    targets = ipa.registered_plan(source, variant, table, cli['gestures'])
    scale = math.fsum(weight * bodies[name]['scale'] for name, weight in zip(ipa.ANCHORS, variant['weights'], strict=True))
    export = timing.read(saved)
    voice = export['speech_voice']
    original = timing.read(reference / 'case.json')['speech_voice']
    checks = {
        'same_saved_case_both_modes': (sha256(saved) == sha256(live)
            and sites['offline']['replayFilename'] == 'worklet-ipa-case.json'
            and sites['live']['replayFilename'] == 'worklet-live-ipa-case.json'),
        'saved_case_matches_parameters': (
            export['upstream_revision'] == source['upstream_revision'] and voice['language'] == 'ipa'
            and voice['input']['start_seconds'] == 0.05
            and all(voice['input'][k] == source['input'][k] for k in ('text', 'rate'))
            and all(voice.get(k) == v for k, v in original.items() if k != 'input')),
        'cli_rate_and_frame_count': (native_rate == rate and frames == cli['output_frames'] == upper_plan['output_frames']
            and cli['decimation_factor'] * rate == source['measurement']['internal_rate_hz']),
        'independent_calibrated_targets': targets['mismatch'] is None,
    }
    result = {'native_stop': native_stop, 'independent_targets': targets}
    for mode in ('offline', 'live'):
        flags, result[mode] = compare_mode(
            label, variant, mode == 'live', sites[mode], source, limits, cli, native, upstream, compared,
            spans, native_stop, upper_plan, scale, binary_hash, artifacts)
        checks.update({f'{mode}/{key}': ok for key, ok in flags.items()})
    return checks, result


def measure(config, source_path, references, artifacts, execute, bun):
    source = timing.read(source_path)
    execute([*bun, 'run', 'build'], cwd=WEB, stdout=artifacts / 'browser-build.log')
    execute(['cargo', 'test', '--locked', '-p', 'chimera', '--test', 'stop_spans',
             '--test', 'voiced_fricatives', '--test', 'body_mix'], cwd=UPSTREAM, stdout=artifacts / 'upstream-tests.log')
    binary = artifacts / 'vocal_wasm.wasm'
    shutil.copyfile(WORKSPACE / wasm.WASM, binary)
    execute(['node', str(CAPTURE), str(artifacts), str(CASE), str(source_path)])
    browser = timing.read(artifacts / 'browser-run.json')
    table = timing.read(ipa.vowel.TABLE)
    bodies = timing.read(ipa.BODY_TABLE)['measurement']['reference_endpoints']
    checks, cases = {}, {}
    binary_hash = sha256(binary)
    for variant in source['variants']:
        label = variant['id']
        flags, cases[label] = compare_variant(variant, source, config['measurement'], references[label], browser[label],
                                               binary_hash, table, bodies, artifacts, execute)
        checks.update({f'{label}/{name}': bool(flag) for name, flag in flags.items()})
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
    references, files = reference_artifacts(config, source, 'upstream.f32')
    bun = ['bun'] if shutil.which('bun') else ['npx', '--yes', '--package=bun@1.4.4', '--', 'bun']
    inputs = [CASE, source, ipa.BODY_TABLE, *files, Path(__file__).resolve(), *shared.candidate_sources(), *web_sources(),
              *(Path(module.__file__) for module in (speech, ipa, fricative, shared, timing, wasm, ipa.calibrated, ipa.vowel)),
              *(WORKSPACE / 'tools' / name for name in ('upstream_baseline.py', 'measure_worklet_fixed.py',
                                                       'measure_worklet_english_body.py', 'measure_body_english.py',
                                                       'measure_pcm_output.py'))]
    meta = {'case_id': config['id'], 'upstream_revision': revision, 'reference_run': config['reference_run'],
            'node': subprocess.check_output(['node', '--version'], text=True).strip(),
            'bun': subprocess.check_output([*bun, '--version'], text=True).strip(), 'input_root': '$REPOSITORY'}
    return shared.record_measurement(run_id, CASE, inputs, meta,
                                     lambda out, run: measure(config, source, references, out, run, bun),
                                     command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
