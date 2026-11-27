"""Safariの歌唱準備と、Core Audioで採った先行信号を照合する。"""

import argparse
import json
from pathlib import Path
import shutil
from statistics import median
import subprocess
import sys
import time

import numpy as np
from scipy.io import wavfile
from scipy.signal import correlate

import smooth_tap_marker
from measure_fan_crossing_allocations import run_manifest, verified_path
from measure_safari_process_tap_calibration import INSPECTOR, read_json
from measure_uniform_tube import candidate_sources, record_measurement
from measure_worklet_fixed import ROOT, UPSTREAM, WEB, WORKSPACE, web_sources
from measure_worklet_live_song_process_tap import app_command, await_file, inspect_tape, staged_app, stop_tap
from measure_worklet_safari_song_audio_client import write_json
from measure_worklet_safari_song_prepared_pause import CAPTURE, WASM, analyze_trial
from measure_worklet_safari_song_prepared_shared_context import compare_marker
from measure_worklet_safari_song_split_score_preparation import compare_preparation, preparation_lengths
from upstream_baseline import sha256


CASE = WORKSPACE / 'cases/worklet-safari-song-process-output.json'


def bridge(app, folder, inspector, spec, command):
    def snapshot():
        return json.loads(subprocess.check_output([str(inspector), *spec['candidate_bundle_ids']],
                                                  timeout=4, text=True))

    def release(result):
        result['release_epoch_ns'] = time.time_ns()
        temp = folder / 'trace-release.tmp'
        write_json(temp, result)
        temp.rename(folder / 'trace-release.json')

    request = folder / 'trace-ready.json'
    result = {'before': snapshot(), 'tap_finished': False}
    with subprocess.Popen(command) as browser:
        try:
            if not await_file(request, browser, time.monotonic() + 18):
                raise ValueError('Safariから先行信号の開始通知を受け取れません')
            result['at_gate'] = snapshot()
            active = {item['pid'] for item in result['before'] if item['runningOutput']}
            fresh = [item for item in result['at_gate'] if item['runningOutput'] and item['pid'] not in active]
            if len(fresh) != 1:
                raise ValueError('試験音で出力が有効になったCore Audioプロセスを一意に特定できません')
            target = result['target'] = fresh[0]
            with staged_app(app, folder) as (local, capture):
                args = app_command(local, target['pid'], spec['tap_duration_seconds'], capture)
                result['tap_command'] = [arg.replace(str(local.parent), '$TAP_STAGE') for arg in args]
                with (folder / 'tap-launch.log').open('wb') as log, subprocess.Popen(
                        args, stdout=log, stderr=subprocess.STDOUT) as tap:
                    try:
                        ready = await_file(capture / 'tap-ready', tap, time.monotonic() + spec['tap_ready_timeout_seconds'])
                        if not ready:
                            raise ValueError('Core Audioタップの開始通知を受け取れません')
                        result['tap_ready_epoch_ns'] = time.time_ns()
                        time.sleep(spec['construction_delay_seconds'])
                        release(result)
                        code = tap.wait(timeout=spec['tap_duration_seconds'] + 4)
                        result['tap_finished'] = code == 0 and (capture / 'tap.json').is_file()
                        result['tap_exit_code'] = code
                    finally:
                        if tap.poll() is None:
                            stop_tap(local, capture)
                            tap.terminate()
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            result['error'] = str(error)
            if request.is_file() and 'release_epoch_ns' not in result:
                release(result)
        finally:
            write_json(folder / 'tap-bridge.json', result)
        try:
            return browser.wait(timeout=30)
        finally:
            if browser.poll() is None:
                browser.terminate()
                try:
                    browser.wait(timeout=4)
                except subprocess.TimeoutExpired:
                    browser.kill()
                    browser.wait()


def capture_times(tape, origin, frames):
    blocks = tape['blocks']
    rate = tape['sampleRate']
    scale = tape['timebaseNumer'] / tape['timebaseDenom'] / 1e6
    times = [tape['anchorEpochMs'] - origin + (b['hostTime'] - tape['anchorHostTime']) * scale for b in blocks]
    sample_time = [b['offset'] for b in blocks]
    sample_time.append(frames)
    times.append(times[-1] + blocks[-1]['frames'] * 1000 / rate)
    maximum_step_error = float(np.abs(np.diff(times) - np.diff(sample_time) * 1000 / rate).max())
    return np.interp(np.arange(frames + 1), sample_time, times), maximum_step_error


def quiet_runs(mask, times, interval):
    lo, hi = map(int, np.searchsorted(times[:-1], interval))
    edges = np.flatnonzero(np.diff(np.r_[False, mask[lo:hi], False])) + lo
    longest = max((int(b - a) for a, b in edges.reshape(-1, 2)), default=0)
    return {'longest_frames': longest, 'frames': int(mask[lo:hi].sum()),
            'spans': [{'range': [int(a), int(b)], 'ms_from_preparation': [float(times[a]), float(times[b])]}
                      for a, b in edges.reshape(-1, 2) if b - a >= 128]}


def graph_anchor(row, graph, spec, period, begin):
    phase = row['marker_position_frames']
    quantum = spec['quantum_frames']
    delay = spec['windows']
    wall = np.asarray(graph['callbackEpochMs'], dtype=float) - begin
    delta_ms = 1000 / spec['sample_rate_hz']
    candidates = []
    for relative in phase + np.arange(0, wall.size * quantum, period):
        block, inside = divmod(relative, quantum)
        if block >= wall.size:
            break
        estimate = wall[int(block)] + inside * delta_ms
        observed = row['times_ms'][0] - estimate
        if delay['minimum_pre_anchor_graph_delay_ms'] <= observed <= delay['maximum_pre_anchor_graph_delay_ms']:
            candidates.append({'context_frame': graph['startFrame'] + relative, 'delay_ms': observed})
    return candidates


def window_energy(samples, frames):
    sums = np.r_[0, np.cumsum(samples * samples)]
    return sums[frames:] - sums[:-frames]


def compare_song_onset(pcm, times, song, first_graph_ms, rate, spec):
    width = spec['rms_window_frames']
    threshold = spec['rms_threshold'] ** 2 * width
    source = song.astype(float)
    crossing = np.flatnonzero(window_energy(source, width) > threshold)
    if not crossing.size:
        return False, {'reason': '加工前の歌唱に指定振幅を超える位置がありません'}
    first = int(crossing[0])
    expected_at = first_graph_ms + 1000 * first / rate
    lower, upper = map(int, np.searchsorted(times[:-1], [expected_at - spec['search_before_ms'],
                                                        expected_at + spec['search_after_ms']]))
    common = pcm.astype(float).mean(axis=1)
    template_size = spec['template_frames']
    template = source[first:first + template_size]
    if len(template) != template_size or upper <= lower or upper + template_size - 1 > len(common):
        return False, {'reason': '歌唱立ち上がりの比較窓が採取範囲に収まりません'}
    region = common[lower:upper + template_size - 1]
    template = template - template.mean()
    running_sum = np.r_[0, np.cumsum(region)]
    mean_per_window = (running_sum[template_size:] - running_sum[:-template_size]) / template_size
    variance = window_energy(region, template_size) - template_size * mean_per_window**2
    normalization = np.sqrt(np.maximum(variance, 0)) * np.linalg.norm(template)
    scores = correlate(region, template, mode='valid', method='fft')
    scores = np.divide(scores, normalization, out=np.zeros_like(scores), where=normalization > 0)
    offset = int(np.argmax(scores))
    correlation_position = lower + offset
    above = np.flatnonzero(window_energy(common, width)[:upper] > threshold)
    onset = int(above[0]) if above.size else None
    separation = abs(onset - correlation_position) if onset is not None else None
    correlation = float(np.clip(scores[offset], -1, 1))
    passed = (onset is not None and lower <= onset < upper and correlation >= spec['minimum_correlation']
              and separation <= spec['maximum_threshold_anchor_error_frames'])
    return passed, {'reference_onset_frame': first, 'tap_onset_frame': onset, 'template_match_frame': correlation_position,
                    'correlation': correlation, 'threshold_anchor_error_frames': separation,
                    'onset_ms_from_preparation': float(times[onset]) if onset is not None else None,
                    'search_ms_from_preparation': [float(times[lower]), float(times[upper])],
                    'relative_to_graph_onset_ms': float(times[onset] - expected_at) if onset is not None else None}


def compare_preparation_segments(study, preparation, prefix_count, graph, begin, delay_ms, times, quiet):
    spec = study['block_comparison']['segment_analysis']
    quantum = study['quantum_frames']
    first, last = preparation['firstContextFrame'], preparation['lastContextFrame']
    first_tail = first + prefix_count * quantum
    graph_times = dict(zip(graph['frames'], graph['callbackEpochMs'], strict=True))
    boundary = graph_times[first_tail] - begin + delay_ms
    margin = spec['boundary_margin_ms']
    tail_from = boundary + margin
    tail_to = preparation['finishedAtEpochMs'] - begin + delay_ms
    windows = {
        'startup': [graph_times[first] - begin + delay_ms - study['windows']['quiet_margin_before_ms'], boundary - margin],
        'boundary': [boundary - margin, tail_from],
        'early_tail': [tail_from, tail_from + spec['tail_comparison_ms']],
        'full_tail': [tail_from, tail_to],
    }
    covered = (windows['early_tail'][1] <= tail_to
               and all(times[0] <= low < high <= times[-1] for low, high in windows.values()))
    rows = {name: {'window_ms': interval} for name, interval in windows.items()}
    if covered:
        for name, interval in windows.items():
            rows[name].update(quiet_runs(quiet, times, interval))
    gaps = [graph_times[frame + quantum] - graph_times[frame] for frame in range(first - quantum, last + quantum, quantum)]
    return covered, {'first_tail_context_frame': first_tail, 'first_tail_graph_ms': graph_times[first_tail] - begin,
                     'preparation_graph_to_tap_estimate_ms': delay_ms, 'estimated_cut_ms': boundary,
                     'startup_max_graph_gap_ms': max(gaps[:prefix_count + 1]),
                     'tail_max_graph_gap_ms': max(gaps[prefix_count + 1:]), 'quiet': rows}


def compare_tap(folder, study, marker_case, begin, end, native, *, song_reference=None, segments=None):
    tape = read_json(folder / 'tap.json')
    report = inspect_tape(folder, marker_case, observe_marker=smooth_tap_marker.observe)
    smooth = report['smooth_marker']
    checks = {f'tap_{k}': v for k, v in report['checks'].items() if k != 'known_marker_continuous'}
    blocks = tape['blocks']
    checks['tap_target_and_host_clock'] = (tape['pid'] == native['target']['pid'] and len(blocks) >= 2
                                         and all(a['hostTime'] < b['hostTime'] for a, b in zip(blocks, blocks[1:])))
    if not all(checks.values()):
        return checks, report
    pcm = np.fromfile(folder / 'tap.f32le', dtype='<f4').reshape(-1, 2)
    times, clock_error = capture_times(tape, begin, len(pcm))
    width = marker_case['window_frames']
    windows = study['windows']
    for row in smooth['windows']:
        start = row['start']
        row['times_ms'] = [float(times[start]), float(times[start + width])]
    accepted = [row for row in smooth['windows'] if row['accepted']]
    baseline = [row for row in accepted if -windows['baseline_from_ms'] <= row['times_ms'][0]
                and row['times_ms'][1] <= -windows['baseline_to_ms']]
    post = [row for row in accepted if end - begin + windows['post_from_ms'] <= row['times_ms'][0]
            and row['times_ms'][1] <= end - begin + windows['post_to_ms']]
    window_starts_with_jump = {jump['start'] for jump in smooth['phase_jumps']}
    longest = streak = 0
    previous = None
    for row in baseline:
        start = row['start']
        if previous is not None and start == previous + width and start not in window_starts_with_jump:
            streak += 1
        else:
            streak = 1
        previous = start
        longest = max(longest, streak)
    checks['tap_baseline_continuity'] = longest >= windows['minimum_baseline_consecutive_windows']
    checks['tap_post_anchor'] = bool(post)
    graph = read_json(folder / 'marker.json')
    marker = marker_case['marker']
    period = marker['chips'] * marker['frames_per_chip']
    anchors = graph_anchor(baseline[-1], graph, study, period, begin) if baseline else []
    checks['tap_pre_anchor_graph_match'] = len(anchors) == 1
    displacement = None
    if baseline and post:
        a, b = baseline[-1], post[0]
        raw = b['marker_position_frames'] - a['marker_position_frames'] - (b['start'] - a['start'])
        displacement = (raw + period / 2) % period - period / 2
    interval = [-windows['quiet_margin_before_ms'], end - begin + windows['quiet_margin_after_ms']]
    differential = (pcm[:, 0].astype(float) - pcm[:, 1]) / 2
    quiet = np.abs(differential) <= study['quiet_marker_amplitude']
    report.update(baseline_consecutive_windows=longest, pre_graph_anchors=anchors, pre_window=baseline[-1] if baseline else None,
                  post_window=post[0] if post else None, phase_displacement_frames=displacement,
                  maximum_host_step_error_ms=clock_error, preparation_ms=end - begin, quiet_window_ms=interval,
                  quiet=quiet_runs(quiet, times, interval),
                  exact_stereo_zero=quiet_runs(np.all(pcm == 0, axis=1), times, interval))
    checks['tap_spans_quiet_window'] = bool(times[0] <= interval[0] <= interval[1] <= times[-1])
    if song_reference is not None:
        reference, first_graph = song_reference
        checks['tap_song_onset'], report['song_onset'] = compare_song_onset(
            pcm, times, reference, first_graph - begin, study['sample_rate_hz'], study['song_onset'])
    if segments is not None:
        checks['tap_segment_windows'] = False
        if len(anchors) == 1:
            preparation, prefix_count = segments
            checks['tap_segment_windows'], report['preparation_segments'] = compare_preparation_segments(
                study, preparation, prefix_count, graph, begin, anchors[0]['delay_ms'], times, quiet)
    return checks, report


def measure(study, shared, pause, marker_case, refs, fields, app, order, artifacts, execute):
    execute(['npm', 'exec', '--offline', '--yes', '--package=bun@1.4.4', '--', 'bun', 'run', 'build'],
            cwd=WEB, stdout=artifacts / 'browser-build.log')
    binary = artifacts / 'vocal_wasm.wasm'
    shutil.copyfile(WASM, binary)
    binary_hash = sha256(binary)
    inspector = artifacts / 'coreaudio-output-processes'
    execute(['xcrun', 'swiftc', '-O', '-framework', 'CoreAudio', str(INSPECTOR), '-o', str(inspector)])
    marker_spec = shared['marker'] | {'moduleName': 'fixed-processor-entry', 'waitForSystemTrace': True,
        'capture_quanta': study['marker_capture_quanta'], 'smooth_marker': marker_case['marker'], 'stereo_difference': True}
    shared = shared | {'marker': marker_spec}
    expected = smooth_tap_marker.marker_pcm(marker_spec['capture_quanta'] * marker_spec['quantum'], marker_case['marker'])
    checks, results = {}, {}
    block = study.get('block_comparison')
    if block:
        trials = [(f'pair-{pair}-{condition}', condition, pair) for pair, sequence in enumerate(order, 1) for condition in sequence]
        split_settings = block['split_settings']
    else:
        trials = [(condition, condition, None) for condition in order]
        split_settings = {'split': {'block_frames': study['split_block_frames'], 'initial_blocks': study['split_initial_blocks']}}
    for label, condition, pair in trials:
        folder = artifacts / label
        folder.mkdir()
        item = results[label] = {'condition': condition, 'pair': pair} if block else {}
        warm = 0 if condition == 'zero' else study['warm_up_frames']
        source, wav, meta = refs['zero' if warm == 0 else 'prepared']
        options = folder / 'capture-case.json'
        config = {'song_preset': 'prepared', 'startup_timeout_seconds': study['startup_timeout_seconds'],
                  'mid_song_pause': pause['pause'] | {'perform_pause': False}, 'shared_context_marker': marker_spec,
                  'audio_client_trace': study['capture'] | {'candidate_bundle_ids': marker_case['candidate_bundle_ids']}}
        lengths = None
        if condition in split_settings:
            settings = split_settings[condition]
            config.update(score_preparation_block_frames=settings['block_frames'],
                          score_preparation_initial_blocks=settings['initial_blocks'])
            lengths = preparation_lengths(warm, settings['block_frames'], settings['initial_blocks'])
        write_json(options, config)
        local = {}
        try:
            execute([sys.executable, str(Path(__file__).resolve()), '--bridge', str(app), str(folder), str(inspector),
                     str(options), 'node', str(CAPTURE), str(folder), str(source), str(options)],
                    cwd=WEB, stdout=folder / 'browser-command.log')
            reference_pcm = wavfile.read(wav)[1]
            trial = {'warm_up_frames': warm, 'mode': 'continuous', 'route': 'direct'}
            local, item['song'], _ = analyze_trial(label, trial, pause, read_json(source), binary_hash,
                                                  reference_pcm, read_json(meta), fields, folder, reference_live=True)
            report = read_json(folder / 'browser.json')
            prep_checks, end, preparation = compare_preparation(report, warm, marker_spec['quantum'], lengths)
            local.update(prep_checks)
            begin = report['scoreConstruction']['startedAtEpochMs']
            mark_checks, item['marker'] = compare_marker(folder, report, shared, preparation_end=end,
                expected_pcm=expected, maximum_zero_error=marker_case['maximum_graph_zero_error'])
            local.update(mark_checks)
            native = item['tap_bridge'] = read_json(folder / 'tap-bridge.json')
            local['tap_finished'] = native['tap_finished']
            if native['tap_finished']:
                release = read_json(folder / 'browser-trace-gate.json')['releaseEpochMs']
                local['construction_after_tap_gate'] = (native['tap_ready_epoch_ns'] <= native['release_epoch_ns']
                    and native['release_epoch_ns'] // 1_000_000 <= release <= begin)
                first_graph = report['realtime']['firstOutputEpochMs']
                song_reference = (reference_pcm, first_graph) if block else None
                segments = None
                if block and 'segment_analysis' in block:
                    segments = (preparation, len(settings['initial_blocks']))
                tap_checks, item['tap'] = compare_tap(folder, study, marker_case, begin, end, native,
                                                      song_reference=song_reference, segments=segments)
                local.update(tap_checks)
                if block:
                    onset = item['tap'].get('song_onset', {}).get('onset_ms_from_preparation')
                    item['timing'] = {'preparation_callbacks': preparation['callbacks'],
                                      'first_block_to_end_ms': end - preparation['startedAtEpochMs'],
                                      'release_to_graph_output_ms': first_graph - release,
                                      'release_to_tap_onset_ms': begin - release + onset if onset is not None else None}
        except (OSError, TypeError, KeyError, ValueError, subprocess.SubprocessError) as error:
            item['error'] = str(error)
            local['capture_and_analysis_complete'] = False
        checks.update({f'{label}/{key}': bool(value) for key, value in local.items()})
    if block:
        return compare_block_sizes(study, order, checks, results)
    bulk, split = results['bulk'], results['split']
    predictions = {'bulk_graph_gap': None, 'bulk_quiet_span': None, 'split_reduces_quiet_span': None}
    if all('marker' in r for r in (bulk, split)):
        predictions['bulk_graph_gap'] = (bulk['marker']['preparation_window_max_gap_ms']
            - split['marker']['preparation_window_max_gap_ms'] >= study['minimum_split_graph_gap_reduction_ms'])
    if all(checks.values()):
        a, b = (r['tap']['quiet']['longest_frames'] for r in (bulk, split))
        predictions['bulk_quiet_span'] = a >= study['minimum_bulk_quiet_frames']
        predictions['split_reduces_quiet_span'] = a - b >= study['minimum_split_quiet_reduction_frames']
    return {'checks': checks, 'predictions': predictions, 'trials': results}


def compare_block_sizes(study, order, checks, trials):
    spec = study['block_comparison']
    segments = spec.get('segment_analysis')
    pairs = []
    for i in range(1, len(order) + 1):
        baseline, candidate = (f'pair-{i}-{spec[name]}' for name in ('baseline', 'candidate'))
        pair = {'pair': i, 'baseline': baseline, 'candidate': candidate}
        pairs.append(pair)
        if not all(value for name, value in checks.items() if name.startswith((baseline + '/', candidate + '/'))):
            continue
        a, b = trials[baseline], trials[candidate]
        timing_a, timing_b = a['timing'], b['timing']
        pair['differences'] = {
            'preparation_reduction_ms': timing_a['first_block_to_end_ms'] - timing_b['first_block_to_end_ms'],
            'graph_startup_reduction_ms': timing_a['release_to_graph_output_ms'] - timing_b['release_to_graph_output_ms'],
            'tap_onset_reduction_ms': timing_a['release_to_tap_onset_ms'] - timing_b['release_to_tap_onset_ms'],
            'quiet_increase_frames': b['tap']['quiet']['longest_frames'] - a['tap']['quiet']['longest_frames'],
            'exact_zero_increase_frames': b['tap']['exact_stereo_zero']['longest_frames'] - a['tap']['exact_stereo_zero']['longest_frames'],
            'phase_magnitude_increase_frames': abs(b['tap']['phase_displacement_frames']) - abs(a['tap']['phase_displacement_frames']),
        }
        if segments:
            baseline_quiet, candidate_quiet = (trial['tap']['preparation_segments']['quiet'] for trial in (a, b))
            pair['differences'].update({
                f'{name}_quiet_increase_frames': candidate_quiet[name]['longest_frames'] - baseline_quiet[name]['longest_frames']
                for name in ('startup', 'boundary', 'early_tail', 'full_tail')
            })
    matched = [row['differences'] for row in pairs if 'differences' in row]
    medians = {name: median(pair[name] for pair in matched) for name in matched[0]} if matched else {}
    quantities = []
    for label in ('baseline', 'candidate'):
        settings = spec['split_settings'][spec[label]]
        quantities.append(len(preparation_lengths(study['warm_up_frames'], settings['block_frames'], settings['initial_blocks'])))
    nominal = (quantities[0] - quantities[1]) * study['quantum_frames'] * 1000 / study['sample_rate_hz']
    predictions = {}
    if len(matched) == len(pairs):
        predictions = {
            'nominal_preparation_reduction': abs(medians['preparation_reduction_ms'] - nominal) <= spec['preparation_reduction_tolerance_ms'],
            'graph_starts_earlier': medians['graph_startup_reduction_ms'] >= spec['minimum_median_startup_reduction_ms'],
            'tap_song_starts_earlier': medians['tap_onset_reduction_ms'] >= spec['minimum_median_startup_reduction_ms'],
            'quiet_increase_at_most_one_quantum': medians['quiet_increase_frames'] <= spec['maximum_median_quiet_increase_frames'],
            'phase_increase_at_most_one_quantum': medians['phase_magnitude_increase_frames'] <= spec['maximum_median_phase_magnitude_increase_frames'],
        }
        if segments:
            predictions.update(
                startup_quiet_difference_at_most_one_quantum=(abs(medians['startup_quiet_increase_frames'])
                    <= segments['maximum_median_startup_quiet_difference_frames']),
                early_tail_quiet_increase_at_most_one_quantum=(medians['early_tail_quiet_increase_frames']
                    <= segments['maximum_median_tail_quiet_increase_frames']),
            )
    return {'checks': checks, 'predictions': predictions, 'trials': trials, 'pairs': pairs,
            'nominal_preparation_reduction_ms': nominal, 'median_differences': medians}


def main():
    if sys.argv[1:2] == ['--bridge']:
        app, folder, inspector, options = map(Path, sys.argv[2:6])
        return bridge(app, folder, inspector, read_json(options)['audio_client_trace'], sys.argv[6:])
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('app', type=Path)
    parser.add_argument('--reverse', action='store_true')
    parser.add_argument('--case', type=Path, default=CASE)
    args = parser.parse_args()
    case_path = args.case.resolve(strict=True)
    study = read_json(case_path)
    case_inputs = [case_path]
    if 'base_case' in study:
        if study['base_case'] != CASE.name:
            parser.error('指定された基準ケースに対応していません')
        case_inputs.append(CASE)
        study = read_json(CASE) | study
    revision = study['upstream_revision']
    if (subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip() != revision
            or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True)):
        parser.error('変更のない固定上流が必要です')
    calibration = CASE.parent / study['calibration_case']
    smooth_spec = read_json(calibration)
    base_calibration = CASE.parent / smooth_spec['base_case']
    marker_case = read_json(base_calibration) | smooth_spec
    calibrated = run_manifest(study['calibration_run'], smooth_spec['id'], revision)
    calibration_summary = verified_path(calibrated, 'summary.json')
    shared_path = CASE.parent / study['shared_context_case']
    shared = read_json(shared_path)
    pause_path = CASE.parent / shared['reference']['case']
    pause = read_json(pause_path)
    files = [*case_inputs, calibration, base_calibration, calibrated[0] / 'manifest.json', calibration_summary,
             shared_path, pause_path, Path(__file__).resolve(), INSPECTOR, CAPTURE, CAPTURE.with_name('safari-webdriver.mjs'),
             *web_sources(), *candidate_sources()]
    files.extend(WORKSPACE / 'tools' / name for name in (
        'smooth_tap_marker.py', 'chimera_process_tap.swift', 'chimera_process_tap_info.plist', 'measure_uniform_tube.py',
        'measure_worklet_live_song_process_tap.py', 'measure_safari_process_tap_calibration.py',
        'measure_worklet_safari_song_audio_client.py', 'measure_worklet_safari_song_prepared_pause.py',
        'measure_worklet_safari_song_prepared_shared_context.py', 'measure_worklet_safari_song_split_score_preparation.py'))
    refs = {}
    for label, spec in study['references'].items():
        case_file = CASE.parent / spec['case']
        run = run_manifest(spec['run'], read_json(case_file)['id'], revision)
        if run[1]['status'] != 'pass':
            parser.error(f'{label} の保存済み比較基準が必要です')
        refs[label] = tuple(verified_path(run, f'artifacts/{spec["trial"]}/{name}')
                            for name in ('browser-case.json', 'browser.wav', 'browser.json'))
        files.extend((case_file, run[0] / 'manifest.json', *refs[label]))
    if (calibrated[1]['status'] != 'pass' or not read_json(calibration_summary)['tape']['checks']['known_marker_continuous']):
        parser.error('同じ試験信号の較正結果が必要です')
    app = args.app.resolve(strict=True)
    subprocess.run(['/usr/bin/codesign', '--verify', str(app)], check=True)
    digest = sha256(app / 'Contents/MacOS/chimera-process-tap')
    plist_digest = sha256(app / 'Contents/Info.plist')
    if digest != calibrated[1]['tap_binary_sha256'] or plist_digest != calibrated[1]['tap_info_sha256']:
        parser.error('較正済みの採取器と実行ファイルまたは設定が異なります')
    order = study['condition_order']
    if args.reverse:
        order = [pair[::-1] for pair in order] if 'block_comparison' in study else order[::-1]
    fields = list(read_json(CASE.parent / 'worklet-song-prepared-source.json')['measurement']['state_tolerance'])
    details = {'case_id': study['id'], 'upstream_revision': revision, 'analysis_directory': str(Path.cwd()),
               'analysis_command': [sys.executable, *sys.argv], 'condition_order': order,
               'tap_app': str(app), 'tap_binary_sha256': digest, 'tap_info_sha256': plist_digest}
    return record_measurement(args.run_id, case_path, files, details,
                              lambda artifacts, execute: measure(study, shared, pause, marker_case, refs, fields,
                                                                 app, order, artifacts, execute),
                              command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
