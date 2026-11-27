"""実時間のɑpɑをブラウザ間で比較し、Firefoxでは別にネイティブな時刻を採る。"""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

import numpy as np
from scipy.io import wavfile

import measure_worklet_firefox_native_clock as mozilla
import measure_worklet_ipa as ipa
import measure_worklet_release_alignment as release


CASE = ipa.WORKSPACE / 'cases/worklet-live-ipa-cross-browser.json'


def write_case(path, original, engine, profiled=False):
    options = {**original['measurement'], 'browser_engine': engine}
    if profiled:
        options['profiler_capture_only'] = True
    path.write_text(json.dumps({**original, 'measurement': options}, ensure_ascii=False, indent=2) + '\n')


def fingerprints(report, audio):
    obs = np.asarray(report['observations'], dtype='<f8')
    other = {name: report[name] for name in ('columns', 'speech', 'gestures', 'tract', 'glottal')}
    return {'pcm_sha256': hashlib.sha256(audio.astype('<f4', copy=False)).hexdigest(),
            'observations_sha256': hashlib.sha256(obs).hexdigest(),
            'score_and_sampled_tracks_sha256': hashlib.sha256(
                json.dumps(other, sort_keys=True, separators=(',', ':')).encode()).hexdigest()}


def gap_spacing(gaps, threshold):
    boundaries = np.flatnonzero(gaps >= threshold)
    periods, counts = np.unique(np.diff(boundaries), return_counts=True)
    return {'large_gap_threshold_ms': threshold, 'maximum_callback_gap_ms': float(gaps.max()),
            'large_gap_spacing_quanta': [[int(p), int(n)] for p, n in zip(periods, counts, strict=True)]}


def callback_cadence(report, warm):
    live = report['realtime']
    table = np.asarray(live['blocks'], dtype=float)
    gaps = np.diff(table[:, 4])
    budget = 1000 * table[0, 1] / report['sampleRate']
    return {'clock': live['timingClock'], **gap_spacing(gaps, max(3, float(gaps.max()) * .6)),
            'after_warmup': gap_spacing(gaps[warm:], budget)}


def check_schedule(report, limits, spec):
    live = report['realtime']
    block = np.asarray(live['blocks'], dtype=float)
    q, f = limits['expected_render_quantum_frames'], limits['output_frames']
    timeline = np.arange((f + q - 1) // q) * q
    start = live['scheduledContextFrame']
    return bool(report['sampleRate'] == report['workletSampleRate'] == limits['output_rate_hz']
                and start == live['armedContextFrame'] + spec['lead_frames'] == report['firstContextFrame']
                and live['leadCallbacks'] == spec['lead_frames'] // q
                and np.array_equal(block[:, 0], start + timeline)
                and np.all(block[:, 1] == q) and np.array_equal(block[:, 2], np.minimum(timeline + q, f)))


def native_timing(profile, marker, report, warm):
    live = report['realtime']
    observed = np.asarray(live['blocks'], dtype=float)
    before = live['startupCallbacks'] + live['leadCallbacks']
    expected = before + len(observed)
    found = []
    marker_counts = {}
    for thread in mozilla.threads(profile):
        spans, _ = mozilla.thread_intervals(thread, marker)
        if not spans:
            continue
        name = f"{thread['name']}/{thread['pid']}"
        calls, _ = mozilla.thread_intervals(thread, 'AudioWorkletNodeEngine::CallProcess')
        marker_counts[name] = {'engine': len(spans), 'javascript_call': len(calls)}
        if len(calls) != expected or len(spans) < expected:
            continue
        engine, author = np.asarray(spans), np.asarray(calls)
        if not (np.isfinite(engine).all() and np.isfinite(author).all() and
                (engine[:, 1] >= engine[:, 0]).all() and (engine[:-1, 1] <= engine[1:, 0]).all() and
                (author[:, 1] >= author[:, 0]).all()):
            continue
        parents = np.searchsorted(engine[:, 1], author[:, 1])
        if np.array_equal(parents, np.arange(expected)) and (author[:, 0] >= engine[parents, 0]).all():
            found.append((name, engine[before:expected], author[before:], engine[expected:]))
    result = {'expected_intervals': expected, 'marker_counts': marker_counts}
    if len(found) != 1:
        return result
    name, v, author, tail = found[0]
    budget = 1000 * observed[0, 1] / report['sampleRate']
    durations = v[:, 1] - v[:, 0]
    native_gaps, date_gaps = np.diff(v[:, 0]), np.diff(observed[:, 4])
    result.update({'thread': name, 'budget_ms': budget,
                   'native_outer_tail_without_javascript_ms': (tail[:, 1] - tail[:, 0]).tolist(),
                   'native_first_and_last_ms': [float(durations[0]), float(durations[-1])],
                   'native_over_budget_output_frames': (np.flatnonzero(durations > budget) * int(observed[0, 1])).tolist(),
                   'native_all': ipa.realtime.timing_summary(durations, budget),
                   'native_after_warmup': ipa.realtime.timing_summary(durations[warm:], budget),
                   'native_javascript_after_warmup': ipa.realtime.timing_summary(author[warm:, 1] - author[warm:, 0], budget),
                   'date_all': ipa.realtime.timing_summary(observed[:, 3], budget),
                   'date_after_warmup': ipa.realtime.timing_summary(observed[warm:, 3], budget),
                   'date_over_but_native_within_budget': int(np.count_nonzero((observed[:, 3] > budget) & (durations <= budget))),
                   'native_callback_cadence_after_warmup': gap_spacing(native_gaps[warm:], budget),
                   'callback_gap_mean_absolute_error_ms': float(abs(date_gaps - native_gaps).mean()),
                   'callback_gap_error_when_shifted_one_quantum_ms': [
                       float(abs(date_gaps[1:] - native_gaps[:-1]).mean()),
                       float(abs(date_gaps[:-1] - native_gaps[1:]).mean())]})
    return result


def profiler_command(cmd, folder, profiler):
    return ['env', 'MOZ_PROFILER_STARTUP=1', 'MOZ_PROFILER_STARTUP_ENTRIES=16777216',
            'MOZ_PROFILER_STARTUP_FEATURES=' + ','.join(profiler['profiler_features']),
            'MOZ_PROFILER_STARTUP_FILTERS=' + ','.join(profiler['thread_filters']),
            'MOZ_PROFILER_SHUTDOWN=' + str(folder / 'firefox-profile.json'), *cmd]


def capture_trial(folder, engine, trial_case, execute, *, profiler=None):
    folder.mkdir()
    runtime = folder / 'capture-case.json'
    write_case(runtime, trial_case, engine, profiled=profiler is not None)
    cmd = ['node', str(ipa.CAPTURE), str(folder), str(ipa.CASE), str(runtime)]
    if profiler is not None:
        cmd = profiler_command(cmd, folder, profiler)
    execute(cmd, stdout=folder / 'browser-command.log')
    run = ipa.wasm.read_json(folder / 'browser-run.json')
    report = ipa.wasm.read_json(folder / 'browser.json')
    rate, audio = wavfile.read(folder / 'browser.wav')
    return run, report, rate, audio


def compress_outputs(folder):
    for name in ('browser.wav', 'browser.json', 'offline.wav', 'offline.json', 'firefox-profile.json'):
        path = folder / name
        if path.exists():
            release.stored.compress(path)


def measure(study, fixed, live, source, baseline, profile, artifacts, execute, bun):
    spec = study['measurement']
    limits = fixed['measurement']
    warm = live['measurement']['timing_exclude_first_blocks']
    execute([*bun, 'run', 'build'], cwd=ipa.WEB, stdout=artifacts / 'browser-build.log')
    binary = artifacts / 'vocal_wasm.wasm'
    shutil.copyfile(ipa.WORKSPACE / ipa.wasm.WASM, binary)
    reference = artifacts / 'reference'
    reference.mkdir()
    settings = ipa.wasm.read_json(source)
    replay = ipa.stop.capture(source, settings['measurement']['host_block_frames'],
                              reference, execute, ('aspiration', 'fast_speech', 'engine'))
    allocations = reference / 'native-allocations.log'
    execute(['cargo', 'test', '--locked', '-p', 'vocal-wasm', 'ipa_render_allocation_profile', '--', '--nocapture'],
            stdout=allocations)
    _, old_audio = wavfile.read(baseline['artifacts/browser.wav'])
    old_report = ipa.wasm.read_json(baseline['artifacts/browser.json'])
    old_digests = fingerprints(old_report, old_audio)
    _, cli_trace, cli_paths, upper_trace, _, _ = replay
    _, cli_audio = wavfile.read(cli_paths[0][0])
    checks, results, native_results = {}, [], []
    for round_number, order in enumerate(spec['browser_order'], 1):
        for engine in order:
            name = f'{round_number}-{engine}'
            folder = artifacts / name
            result = {'trial': name, 'engine': engine}
            try:
                run, report, _, audio = capture_trial(folder, engine, live, execute)
                result.update(ipa.compare_capture(source, fixed, folder, execute, bun, ipa.LIVE_CASE,
                                                  binary=binary, references=replay, allocation_log=allocations))
                result.update({'hashes': fingerprints(report, audio), 'callback_cadence': callback_cadence(report, warm),
                               'archived_chromium_pcm': ipa.wasm.compare_pcm(audio, old_audio, 0)})
                local = {**result['checks'], 'requested_engine': run.get('engine') == engine}
            except (OSError, ValueError, subprocess.CalledProcessError) as error:
                result['error'] = str(error)
                local = {'capture_and_comparison_completed': False}
            results.append(result)
            checks.update({f'{name}/{k}': v for k, v in local.items()})
            compress_outputs(folder)
    exact = ['pcm_sha256', 'observations_sha256', 'score_and_sampled_tracks_sha256']
    for key in exact:
        values = {item.get('hashes', {}).get(key) for item in results}
        checks[f'all_current_{key}_equal'] = len(values) == 1 and None not in values
    validated = next((item['hashes'] for item in results if item.get('hashes') and item['checks']['cli_pcm']), None)
    for number in range(1, spec['native_firefox_trials'] + 1):
        name = f'native-firefox-{number}'
        folder = artifacts / name
        result = {'trial': name}
        try:
            run, report, rate, audio = capture_trial(folder, 'firefox', live, execute, profiler=profile['measurement'])
            result.update({'browser': run['version'], 'hashes': fingerprints(report, audio)})
            profile_path = folder / 'firefox-profile.json'
            if profile_path.is_file():
                result.update(native_timing(ipa.wasm.read_json(profile_path), spec['native_marker'], report, warm))
            local = {'production_audio_and_schedule': run['engine'] == 'firefox' and
                     run['servedWasmSha256'] == ipa.sha256(binary) and not run['errors'] and run['recovered']
                     and rate == limits['output_rate_hz'] and check_schedule(report, limits, live['measurement'])
                     and ipa.wasm.compare_pcm(audio, cli_audio, 0)['first_bit_difference_frame'] is None,
                     'state_matches_ordinary_trials': result['hashes'] == validated,
                     'native_intervals_aligned': 'native_after_warmup' in result}
        except (OSError, ValueError, subprocess.CalledProcessError) as error:
            result['error'] = str(error)
            local = {'capture_and_comparison_completed': False}
        checks.update({f'{name}/{k}': v for k, v in local.items()})
        native_results.append(result)
        compress_outputs(folder)
    for path in (cli_trace, upper_trace, *(pair[1] for pair in cli_paths)):
        release.stored.compress(path)
    return {'checks': checks, 'trials': results, 'native_firefox': native_results,
            'archive': {'run': study['archived_chromium_run'], 'hashes': old_digests,
                        'same_wasm_as_current': ipa.sha256(baseline['artifacts/vocal_wasm.wasm']) == ipa.sha256(binary)}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    study = ipa.wasm.read_json(CASE)
    live_path = ipa.WORKSPACE / 'cases' / study['live_case']
    profile_path = ipa.WORKSPACE / 'cases' / study['firefox_profile_case']
    fixed, live, profile = (ipa.wasm.read_json(path) for path in (ipa.CASE, live_path, profile_path))
    source = ipa.WORKSPACE / 'cases' / fixed['speech_voice_case']
    revision = study['upstream_revision']
    if (live_path != ipa.LIVE_CASE or live['ipa_case'] != ipa.CASE.name
            or any(case['upstream_revision'] != revision for case in (fixed, live, profile))
            or subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ipa.UPSTREAM, text=True).strip() != revision
            or subprocess.check_output(['git', 'status', '--porcelain'], cwd=ipa.UPSTREAM, text=True)):
        parser.error('固定上流と発話の事前登録を照合できません')
    baseline, manifest = release.saved.load_saved_run(
        study['archived_chromium_run'], live['id'], revision,
        ['summary.json', 'artifacts/browser.wav', 'artifacts/browser.json', 'artifacts/vocal_wasm.wasm'])
    old = ipa.wasm.read_json(manifest)
    if old['status'] != 'pass' or not all(ipa.wasm.read_json(baseline['summary.json'])['checks'].values()):
        parser.error('保存Chromiumの基準実行を照合できません')
    for path in (ipa.CASE, live_path, source):
        inputs = [row['sha256'] for row in old['inputs'] if row['path'].endswith('/' + path.name)]
        if inputs != [ipa.sha256(path)]:
            parser.error(f'保存Chromiumについて {path.name} の入力が一致しません')
    if any(sorted(order) != ['chromium', 'firefox'] for order in study['measurement']['browser_order']):
        parser.error('各ラウンドにはChromiumとFirefoxを一度ずつ含めてください')
    bun = ['bun'] if shutil.which('bun') else ['npx', '--offline', '--yes', '--package=bun@1.4.4', '--', 'bun']
    inputs = [CASE, ipa.CASE, live_path, profile_path, source, manifest, *baseline.values(), ipa.stop.PROBE,
              *ipa.web_sources(), *ipa.shared.candidate_sources(), *(Path(mod.__file__) for mod in
                (ipa, mozilla, ipa.stop, ipa.timing, ipa.shared, ipa.wasm, ipa.realtime, ipa.live_ipa,
                 release.saved, release.stored)), Path(__file__).resolve()]
    metadata = {'case_id': study['id'], 'upstream_revision': revision,
                'node': subprocess.check_output(['node', '--version'], text=True).strip(),
                'bun': subprocess.check_output([*bun, '--version'], text=True).strip()}
    return ipa.shared.record_measurement(args.run_id, CASE, inputs, metadata,
        lambda a, run: measure(study, fixed, live, source, baseline, profile, a, run, bun),
        command=None, input_root=ipa.ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
