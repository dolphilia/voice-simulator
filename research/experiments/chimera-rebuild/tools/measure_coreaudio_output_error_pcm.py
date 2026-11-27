"""AudioUnitの戻り値が同じ減衰PCMの採取結果を変えるかを測る。"""

import argparse
from pathlib import Path
import subprocess
import sys
import time

import numpy as np

import smooth_tap_marker
from measure_coreaudio_output_render_status import SOURCE
from measure_fan_crossing_allocations import run_manifest, verified_path
from measure_safari_process_tap_calibration import read_json
from measure_uniform_tube import record_measurement
from measure_worklet_fixed import ROOT, UPSTREAM, WORKSPACE
from measure_worklet_live_song_process_tap import NATIVE, PLIST, app_command, await_file, inspect_tape, staged_app, stop_tap
from measure_worklet_safari_song_audio_client import write_json
from measure_worklet_safari_song_process_output import capture_times
from upstream_baseline import sha256


CASE = WORKSPACE / 'cases/coreaudio-output-error-pcm.json'


def capture(folder, binary, marker, spec, status, app, entry_mode, *, during_playback=None):
    ready = folder / 'ready'
    config = folder / 'pcm-settings.json'
    settings = {'markerPath': str(marker), 'pcmPath': str(folder / 'native.f32le'),
                'eventCallbacks': spec['event_callbacks']}
    if 'restart' in spec:
        settings['restart'] = spec['restart']
    if entry_mode:
        settings.update(entryMode=entry_mode, entryNeighbors=spec['observe_entry_neighbor_callbacks'],
                        entryLookback=spec['known_buffer_lookback_callbacks'])
    write_json(config, settings)
    parameters = [str(spec['event_callback']), '0', str(spec['sample_rate_hz']), str(spec['native_seconds']),
                  str(spec['event_callbacks'] if status else 0), str(ready), str(config)]
    report = {'native_command': [str(binary), *parameters], 'tap_started': False}
    attach_wait = spec.get('tap_attach_after_release_seconds')
    with (folder / 'native.json').open('wb') as output, (folder / 'native.log').open('wb') as log:
        with subprocess.Popen([str(binary), *parameters], stdin=subprocess.PIPE, stdout=output, stderr=log) as probe:
            try:
                if not await_file(ready, probe, time.monotonic() + 5):
                    raise ValueError('出力AudioUnitの準備が完了しません')
                with staged_app(app, folder) as (local, recording):
                    command = app_command(local, probe.pid, spec['tap_seconds'], recording)
                    report['tap_command'] = [arg.replace(str(local.parent), '$TAP_STAGE') for arg in command]
                    report['output_pid'] = probe.pid
                    if attach_wait is not None:
                        probe.stdin.write(b'\x01')
                        probe.stdin.flush()
                        release_time = time.monotonic()
                        time.sleep(attach_wait)
                        report['seconds_from_release_to_tap_launch'] = time.monotonic() - release_time
                    with (folder / 'tap-launch.log').open('wb') as tap_log, subprocess.Popen(
                            command, stdout=tap_log, stderr=subprocess.STDOUT) as tap:
                        try:
                            report['tap_started'] = await_file(recording / 'tap-ready', tap,
                                time.monotonic() + spec['tap_ready_timeout_seconds'])
                            if attach_wait is None:
                                if report['tap_started']:
                                    time.sleep(spec['tap_lead_seconds'])
                                probe.stdin.write(b'\x01')
                                probe.stdin.flush()
                            if during_playback is not None:
                                report['during_playback'] = during_playback()
                            report['output_exit_code'] = probe.wait(timeout=spec['native_seconds'] + 4)
                            report['tap_exit_code'] = tap.wait(timeout=spec['tap_seconds'] + 4)
                        finally:
                            if tap.poll() is None:
                                stop_tap(local, recording)
                                tap.terminate()
            finally:
                if probe.poll() is None:
                    probe.terminate()
                write_json(folder / 'capture.json', report)
    return report


def check_entry_blocks(spec, mode, pcm, marks, start, stop, width):
    neighbors = spec['observe_entry_neighbor_callbacks']
    observed = [{'callback': i, **row['bufferEntry']} for i, row in enumerate(marks) if 'bufferEntry' in row]
    checks = {'native_entry_observation_span': [row['callback'] for row in observed] == list(
        range(start - neighbors, stop + neighbors))}
    for row in observed:
        i = row['callback']
        samples = pcm[i * width:(i + 1) * width]
        whole_zero = row['zeroSamples'] == width * 2
        previous = row.get('previousMarkerOffset')
        known = whole_zero or previous is not None
        valid_offset = previous is None or i * width - spec['known_buffer_lookback_callbacks'] * width <= previous < i * width
        expected_action = 'marker'
        if start <= i < stop:
            expected_action = 'explicit_zero' if mode == 'zero' else 'retain' if known else 'fallback_zero'
        checks[f'entry/{i}/metadata'] = (row['action'] == expected_action and valid_offset
                                        and 0 <= row['zeroSamples'] <= width * 2)
        if start <= i < stop:
            if expected_action == 'retain' and not whole_zero:
                expected = pcm[previous:previous + width]
                checks[f'entry/{i}/retained_pcm'] = np.array_equal(samples.view('<u4'), expected.view('<u4'))
            else:
                checks[f'entry/{i}/zero_pcm'] = not np.any(samples)
    return checks, observed


def compare_native(folder, spec, marker, status, entry_mode):
    report = read_json(folder / 'native.json')
    pcm = np.fromfile(folder / 'native.f32le', dtype='<f4').reshape(-1, 2)
    marks = report['frameMarks']
    event = spec['event_callback']
    stop = event + spec['event_callbacks']
    width = spec['expected_callback_frames']
    if len(marks) <= stop or len(pcm) != len(marks) * width:
        raise ValueError('対象区間とその前後を照合できる長さのPCMがありません')
    first, last = event * width, stop * width
    difference = (pcm[:, 0].astype(float) - pcm[:, 1]) / 2
    x = difference[first - 1]
    expected = smooth_tap_marker.marker_pcm(len(pcm), marker)
    outside = np.r_[np.arange(first), np.arange(last, len(pcm))]
    checks = {
        'native_format': report['invalidBuffers'] == 0 and report['sampleRate'] == spec['sample_rate_hz']
            and np.isfinite(pcm).all() and np.array_equal(pcm[:, 0], -pcm[:, 1]),
        'native_sizes_and_positions': all(row['frames'] == width and row['markerOffset'] == i * width
                                          for i, row in enumerate(marks)),
        'native_status_schedule': all(row['status'] == (status if event <= i < stop else 0)
                                      for i, row in enumerate(marks)),
        'native_clocks': all(row.get('sampleTime') is not None and row.get('hostTime') is not None for row in marks)
            and all(b['sampleTime'] - a['sampleTime'] == a['frames'] and b['hostTime'] > a['hostTime']
                    for a, b in zip(marks, marks[1:])),
        'native_marker': np.array_equal(pcm[outside, 0].view('<u4'), expected[outside].view('<u4')),
    }
    result = {'event_sample': first, 'event_frames': last - first, 'fade_frames': width,
              'last_marker_sample': float(x),
              'event_host_time': marks[event].get('hostTime'), 'output_pid': report['pid']}
    if entry_mode:
        entry_checks, result['buffer_entries'] = check_entry_blocks(spec, entry_mode, pcm, marks, event, stop, width)
        checks.update(entry_checks)
    else:
        ramp = x * (1 - np.arange(1, width + 1, dtype=float) / width)
        max_error = float(np.abs(difference[first:first + width] - ramp).max())
        checks['native_ramp'] = abs(x) >= spec['minimum_boundary_signal_amplitude'] and max_error <= spec['maximum_native_ramp_error']
        checks['native_zero_tail'] = not np.any(pcm[first + width:last])
        result['maximum_ramp_error'] = max_error
    return checks, result, pcm[first - width:last + width]


def compare_tap(folder, spec, marker_case, native, entry_mode, native_pcm):
    tape = read_json(folder / 'tap.json')
    report = inspect_tape(folder, marker_case, observe_marker=smooth_tap_marker.observe)
    marker = report['smooth_marker']
    checks = {f'tap_{key}': value for key, value in report['checks'].items() if key != 'known_marker_continuous'}
    stamps = [row.get('hostTime') for row in tape['blocks']]
    checks['tap_target_and_host_clock'] = (tape['pid'] == native['output_pid'] and len(stamps) >= 2 and None not in stamps
                                          and all(a < b for a, b in zip(stamps, stamps[1:])))
    if not all(checks.values()):
        return checks, report
    pcm = np.fromfile(folder / 'tap.f32le', dtype='<f4').reshape(-1, 2)
    scale = tape['timebaseNumer'] / tape['timebaseDenom'] / 1e6
    origin = tape['anchorEpochMs'] + (native['event_host_time'] - tape['anchorHostTime']) * scale
    times, step_error = capture_times(tape, origin, len(pcm))
    per_ms = spec['sample_rate_hz'] / 1000
    width = marker_case['window_frames']
    period = marker_case['marker']['chips'] * marker_case['marker']['frames_per_chip']
    event_frame = native['event_sample']

    def anchor(row):
        i = row['start']
        phase = row['marker_position_frames']
        nearest = event_frame + times[i] * per_ms
        resolved = phase + period * round((nearest - phase) / period)
        point = i + event_frame - resolved
        delay = times[i] + (point - i) / per_ms
        return row | {'event_tap_frame': point, 'path_delay_ms': float(delay),
                      'time_ms': float(times[i])}

    before = [anchor(row) for row in marker['windows'] if row['accepted'] and
              -400 <= times[row['start']] and times[row['start'] + width] <= -35]
    after = [anchor(row) for row in marker['windows'] if row['accepted'] and
             120 <= times[row['start']] <= 420]
    checks['tap_anchors_before_and_after'] = bool(before and after)
    if not before or not after:
        return checks, report
    pre, post = before[-1], after[0]
    change = post['event_tap_frame'] - pre['event_tap_frame']
    checks['tap_anchor_path_delay'] = all(abs(row['path_delay_ms']) <= spec['maximum_absolute_path_delay_ms']
                                          for row in (pre, post))
    checks['tap_alignment_change'] = abs(change) <= spec['maximum_pre_post_delay_change_frames']
    report.update(pre_anchor=pre, post_anchor=post, phase_change_frames=change, maximum_host_step_error_ms=step_error)
    q = native['fade_frames']
    location = pre['event_tap_frame']
    if entry_mode:
        local, details = compare_tap_entry(pcm, native_pcm, spec, location, pre['gain'], q)
        checks.update(local)
        report['event_blocks'] = details
        return checks, report
    left = int(np.ceil(location + q/4))
    right = int(np.floor(location + 3*q/4))
    zero_left = int(np.ceil(location + q + q/4))
    zero_right = int(np.floor(location + native['event_frames'] - q/4))
    checks['tap_contains_event'] = 0 <= left < right < zero_left < zero_right <= len(pcm)
    if not checks['tap_contains_event']:
        return checks, report
    difference = (pcm[:, 0].astype(float) - pcm[:, 1]) / 2
    reference = pre['gain'] * native['last_marker_sample'] * (1 - (np.arange(left, right) - location + 1) / q)
    measured = difference[left:right]
    norm = np.linalg.norm(reference)
    ratio = float(np.linalg.norm(measured) / norm)
    error = float(np.linalg.norm(measured - reference) / norm)
    tail_peak = float(np.abs(difference[zero_left:zero_right]).max())
    checks['tap_comparison_finite'] = np.isfinite([ratio, error, tail_peak]).all()
    report.update(ramp_tap_range=[left, right], zero_tail_tap_range=[zero_left, zero_right],
                  ramp_relative_amplitude=ratio, ramp_relative_error=error, zero_tail_peak=tail_peak)
    return checks, report


def compare_tap_entry(pcm, native_pcm, spec, event_tap_frame, gain, q):
    results, checks = [], {}
    for number in range(spec['event_callbacks']):
        start = event_tap_frame + number * q
        left = int(np.ceil(start + q/4))
        right = int(np.floor(start + 3*q/4))
        checks[f'tap_event_{number}_covered'] = 0 <= left < right <= len(pcm)
        if not checks[f'tap_event_{number}_covered']:
            continue
        actual = pcm[left:right].astype(float)
        expected_pcm = native_pcm[(number + 1)*q:(number + 2)*q].astype(float)
        positions = np.arange(left, right) - start
        expected = gain * np.column_stack(
            [np.interp(positions, np.arange(q), expected_pcm[:, channel]) for channel in (0, 1)])
        norm = np.linalg.norm(expected)
        error = float(np.linalg.norm(actual - expected) / norm) if norm else None
        peak = float(np.abs(actual).max())
        agrees = (peak <= spec['maximum_tap_quiet_amplitude'] if error is None
                  else error <= spec['maximum_tap_known_relative_error'])
        checks[f'tap_event_{number}_finite'] = np.isfinite(actual).all() and (error is None or np.isfinite(error))
        results.append({'callback': spec['event_callback'] + number, 'tap_range': [left, right],
                        'peak': peak, 'exact_zero_frames': int(np.count_nonzero(np.all(actual == 0, axis=1))),
                        'written_pcm_relative_error': error, 'matches_written_pcm': bool(agrees)})
    return checks, results


def measure(spec, marker_case, order, app, artifacts, execute):
    binary = artifacts / 'chimera-output-deadline'
    execute(['xcrun', 'swiftc', '-O', '-framework', 'AudioToolbox', str(SOURCE), '-o', str(binary)])
    marker = marker_case['marker']
    reference = artifacts / 'marker.f32le'
    smooth_tap_marker.marker_pcm(marker['chips'] * marker['frames_per_chip'], marker).tofile(reference)
    checks, results, native_waves = {}, {}, {}
    for name in order:
        folder = artifacts / name
        folder.mkdir()
        status = spec['conditions'][name]
        entry_mode = name if 'observe_entry_neighbor_callbacks' in spec else None
        result = results[name] = {}
        local = {}
        try:
            result['capture'] = captured = capture(folder, binary, reference, spec, status, app, entry_mode)
            local['native_completed'] = captured.get('output_exit_code') == 0
            local['tap_completed'] = captured['tap_started'] and captured.get('tap_exit_code') == 0 and (folder / 'tap.json').is_file()
            if local['native_completed']:
                native_checks, result['native'], native_waves[name] = compare_native(folder, spec, marker, status, entry_mode)
                local.update(native_checks)
            if local['tap_completed'] and local.get('native_clocks'):
                tap_checks, result['tap'] = compare_tap(folder, spec, marker_case, result['native'], entry_mode, native_waves[name])
                local.update(tap_checks)
        except (OSError, TypeError, KeyError, ValueError, subprocess.SubprocessError) as error:
            result['error'] = str(error)
            local['complete'] = False
        checks.update({f'{name}/{key}': bool(value) for key, value in local.items()})
    predictions = {}
    if 'observe_entry_neighbor_callbacks' in spec:
        if all(checks.values()):
            for name in order:
                native, tap = (results[name][k] for k in ('native', 'tap'))
                entries = native['buffer_entries'][spec['observe_entry_neighbor_callbacks']:][:spec['event_callbacks']]
                zero_entry = all(row['zeroSamples'] == spec['expected_callback_frames'] * 2 for row in entries)
                fallback = sum(row['action'] == 'fallback_zero' for row in entries)
                predictions[name] = {'event_entries_all_zero': zero_entry, 'fallback_requests': fallback,
                                     'admissible_tap_matches': all(r['matches_written_pcm'] for r in tap['event_blocks']),
                                     'event_tap_is_quiet': all(r['peak'] <= spec['maximum_tap_quiet_amplitude']
                                                               for r in tap['event_blocks'])}
    else:
        checks['identical_native_event_pcm'] = (len(native_waves) == 2 and np.array_equal(
            native_waves['success'].view('<u4'), native_waves['error'].view('<u4')))
        if all(checks.values()):
            success, error = (results[name]['tap'] for name in ('success', 'error'))
            predictions = {'success_passes_ramp': success['ramp_relative_error'] <= spec['maximum_passed_ramp_relative_error'],
                           'error_mutes_ramp': error['ramp_relative_amplitude'] <= spec['maximum_muted_ramp_relative_amplitude'],
                           'error_passes_ramp': error['ramp_relative_error'] <= spec['maximum_passed_ramp_relative_error'],
                           'tails_are_quiet': all(r['zero_tail_peak'] <= spec['maximum_tap_zero_tail_amplitude']
                                                  for r in (success, error))}
    return {'checks': checks, 'predictions': predictions, 'trials': results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('app', type=Path)
    parser.add_argument('--reverse', action='store_true')
    parser.add_argument('--case', type=Path, default=CASE)
    args = parser.parse_args()
    case_path = args.case.resolve(strict=True)
    spec = read_json(case_path)
    case_inputs = [case_path]
    if 'base_case' in spec:
        if spec['base_case'] != CASE.name:
            parser.error('指定された基準ケースに対応していません')
        case_inputs.append(CASE)
        spec = read_json(CASE) | spec
    revision = spec['upstream_revision']
    if (subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip() != revision
            or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True)):
        parser.error('変更のない固定上流が必要です')
    marker_path = CASE.parent / spec['marker_case']
    marker_case = read_json(marker_path)
    base_marker_path = CASE.parent / marker_case['base_case']
    calibration = run_manifest(spec['calibration_run'], marker_case['id'], revision)
    marker_case = read_json(base_marker_path) | marker_case
    reference_path = CASE.parent / spec['reference_case']
    reference = run_manifest(spec['reference_run'], read_json(reference_path)['id'], revision)
    files = [*case_inputs, marker_path, base_marker_path, reference_path, Path(__file__).resolve(), SOURCE, NATIVE, PLIST]
    for run in (reference, calibration):
        if run[1]['status'] != 'pass':
            parser.error(f'{run[0].name} の保存済み結果が必要です')
        files.extend((run[0] / 'manifest.json', verified_path(run, 'summary.json')))
    files.extend(WORKSPACE / 'tools' / name for name in (
        'smooth_tap_marker.py', 'measure_worklet_safari_song_process_output.py', 'measure_worklet_live_song_process_tap.py',
        'measure_uniform_tube.py', 'measure_worklet_safari_song_audio_client.py', 'measure_coreaudio_output_render_status.py'))
    app = args.app.resolve(strict=True)
    subprocess.run(['/usr/bin/codesign', '--verify', str(app)], check=True)
    tap_hash = sha256(app / 'Contents/MacOS/chimera-process-tap')
    plist_hash = sha256(app / 'Contents/Info.plist')
    if tap_hash != calibration[1]['tap_binary_sha256'] or plist_hash != calibration[1]['tap_info_sha256']:
        parser.error('較正済みの採取アプリと一致しません')
    order = list(spec['conditions'])
    if args.reverse:
        order.reverse()
    details = {'case_id': spec['id'], 'upstream_revision': revision, 'order': order,
               'analysis_command': [sys.executable, *sys.argv], 'analysis_directory': str(Path.cwd()),
               'swift': subprocess.check_output(['xcrun', 'swiftc', '--version'], text=True).strip(),
               'tap_app': str(app), 'tap_binary_sha256': tap_hash, 'tap_info_sha256': plist_hash}
    return record_measurement(args.run_id, case_path, files, details,
        lambda artifacts, execute: measure(spec, marker_case, order, app, artifacts, execute),
        command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
