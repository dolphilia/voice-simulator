"""Safariの既知ステレオ信号でCore Audioのプロセスタップを較正する。"""

import argparse
from collections import Counter
from datetime import datetime, timedelta
import json
from pathlib import Path
from statistics import median
import subprocess
import sys
import time

import numpy as np

import measure_worklet_live_song_process_tap as tap
import smooth_tap_marker
from measure_fan_crossing_allocations import run_manifest, verified_path
from measure_uniform_tube import record_measurement
from measure_worklet_fixed import ROOT, WEB, UPSTREAM, WORKSPACE
from upstream_baseline import sha256


CASE = WORKSPACE / 'cases/safari-process-tap-calibration.json'
INSPECTOR = WORKSPACE / 'tools/chimera_coreaudio_output_processes.swift'
OUTPUT_DEVICE = WORKSPACE / 'tools/chimera_coreaudio_output_device.swift'
SAFARI = WEB / 'tools/capture-safari-process-tap.mjs'


def read_json(path):
    return json.loads(path.read_text())


def inspect_graph(folder, name, spec):
    observation = read_json(folder / f'{name}.json')
    pcm = np.fromfile(folder / f'{name}.f32le', dtype='<f4')
    quantum, quanta = spec['quantum_frames'], spec['graph_capture_quanta']
    clocks = np.asarray(observation['callbackEpochMs'])
    generate = smooth_tap_marker.marker_pcm if spec['marker'].get('shape') == 'smooth-binary' else tap.marker_pcm
    expected = generate(quantum * quanta, spec['marker'])
    checks = {'sample_rate': observation['rate'] == spec['sample_rate_hz'],
              'graph_frames_continuous': bool(np.array_equal(observation['frames'], observation['startFrame'] + quantum * np.arange(quanta))
                   and np.array_equal(observation['inputFrames'], np.full(quanta, quantum))),
              'graph_time_nondecreasing': bool(clocks.size == quanta and np.isfinite(clocks).all() and (np.diff(clocks) >= 0).all())}
    diagnostics = None
    if 'maximum_graph_zero_error' in spec and pcm.shape == expected.shape:
        zero = expected == 0
        differences = pcm.view('<u4') != expected.view('<u4')
        error = float(np.max(np.abs(pcm[zero]), initial=0))
        diagnostics = {'bit_differences': int(differences.sum()), 'nonzero_reference_bit_differences': int(differences[~zero].sum()),
                       'maximum_zero_error': error}
        checks['graph_pcm_with_zero_tolerance'] = not differences[~zero].any() and error <= spec['maximum_graph_zero_error']
    else:
        checks['graph_pcm_bitwise'] = np.array_equal(pcm.view('<u4'), expected.view('<u4'))
    return checks, pcm, diagnostics


def injected_controls(pcm, spec):
    stereo = np.column_stack((pcm, -pcm))
    middle = len(pcm) // 2
    count = spec['control_discontinuity_frames']
    zero = np.zeros((count, 2), dtype='<f4')
    examples = [('continuous', stereo, (0, 0, 0, 0), None),
                ('missing', np.concatenate((stereo[:middle], stereo[middle+count:])), (count, 0, 0, 0), middle),
                ('repeated', np.concatenate((stereo[:middle], stereo[middle-count:])), (0, count, 0, 0), middle),
                ('silent', np.concatenate((stereo[:middle], zero, stereo[middle+count:])), (0, 0, count, count), middle + count)]
    keys = ('missing_marker_frames', 'repeated_marker_frames', 'undecoded_frames', 'silent_frames')
    checks, results = {}, {}
    for label, signal, expected, position in examples:
        result = tap.resolve_marker_window(signal, spec['marker'], spec, 0, len(pcm) - 1)
        transitions = result.get('transitions', [])
        positions = [transition['first_following_frame'] for transition in transitions]
        checks[f'injected/{label}'] = (result['valid'] and tuple(result[k] for k in keys) == expected
                                       and positions == ([] if position is None else [position]))
        results[label] = result
    return checks, results


def identified_process(capture):
    target = capture.get('confirmedTarget')
    if not target or capture.get('target', {}).get('pid') != target['pid']:
        return False
    # 開始前と停止後は選んだPIDに出力がなく、2回の開始で同じPIDが出力する。
    states = {row['phase']: any(p['pid'] == target['pid'] and p['bundleID'] == target['bundleID'] and p['runningOutput']
                                for p in row['processes']) for row in capture['snapshots']}
    return [states.get(phase) for phase in ('before', 'pilot', 'stopped', 'restarted')] == [False, True, False, True]


def permission_observation(artifacts, since_epoch_ms=None):
    pid_file = artifacts / 'tap-pid'
    if not pid_file.is_file():
        return None
    pid = int(pid_file.read_text())
    predicate = ('subsystem == "com.apple.TCC" AND eventMessage CONTAINS "org.voice-simulator.chimera.process-tap" '
                 f'AND eventMessage CONTAINS "pid={pid}," AND eventMessage CONTAINS "kTCCServiceAudioCapture"')
    window = ['--last', '3m']
    if since_epoch_ms is not None:
        start = datetime.fromtimestamp(since_epoch_ms / 1000) - timedelta(seconds=1)
        end = start + timedelta(minutes=2)
        window = ['--start', start.strftime('%Y-%m-%d %H:%M:%S'), '--end', end.strftime('%Y-%m-%d %H:%M:%S')]
    try:
        log = subprocess.run(['/usr/bin/log', 'show', *window, '--style', 'json', '--predicate', predicate],
                             capture_output=True, text=True, timeout=8, check=True)
        events = json.loads(log.stdout)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        return {'diagnostic': str(error)}
    return {'process_pid': pid, 'window': window, 'service': 'kTCCServiceAudioCapture', 'matching_events': len(events),
            'prompt_events': [row['timestamp'] for row in events if 'AUTHREQ_PROMPTING' in row['eventMessage']]}


def output_snapshot(probe, *args):
    return json.loads(subprocess.check_output([str(probe), *map(str, args)], text=True, timeout=5))


def select_output(probe, current, expected):
    result = output_snapshot(probe, 'select', current, expected)
    until = time.monotonic() + 3
    while result['defaultOutput'] != expected and time.monotonic() < until:
        time.sleep(0.05)
        result = output_snapshot(probe)
    if result['defaultOutput'] != expected:
        raise ValueError('既定の出力機器が切り替わりませんでした')
    return result


def capture_on_output(spec, artifacts, probe, run):
    before = output_snapshot(probe)
    report = {'before': before}
    original = before['defaultOutput']
    options = spec['output_device']
    devices = [row for row in before['devices'] if row['uid'] == options['uid']
               and row['name'] == options['name'] and row['sampleRate'] == options['sample_rate_hz']]
    if len(devices) != 1:
        raise ValueError('登録した名前・UID・公称レートの出力機器を一意に確認できません')
    wanted = devices[0]['id']
    try:
        report['selected'] = select_output(probe, original, wanted) if original != wanted else before
        run()
        return report
    finally:
        try:
            after = output_snapshot(probe)
            if original != wanted and after['defaultOutput'] == wanted:
                after = select_output(probe, wanted, original)
            report['after'] = after
        finally:
            (artifacts / 'output-device.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')


def compare_output_device(spec, browser, tape, route, checks):
    options = spec['output_device']
    active = browser.get('tap', {}).get('outputDevice') or {}
    current = active.get('defaultOutput')
    device = next((row for row in active.get('devices', []) if row['id'] == current), {})
    blocks = tape['blocks']
    rate = spec['sample_rate_hz']
    ns = tape['timebaseNumer'] / tape['timebaseDenom']
    errors = [abs((right['hostTime'] - left['hostTime']) * ns / 1000 - left['frames'] * 1e6 / rate)
              for left, right in zip(blocks, blocks[1:]) if 'hostTime' in left and 'hostTime' in right]
    median_error = median(errors) if errors else None
    widths = dict(sorted(Counter(block['frames'] for block in blocks).items()))
    checks['active_device_matches_case'] = (device.get('uid'), device.get('sampleRate')) == (options['uid'], rate)
    checks['original_output_restored'] = route.get('after', {}).get('defaultOutput') == route['before']['defaultOutput']
    checks['tap_host_period_matches_rate'] = (median_error is not None
                                              and median_error <= spec['maximum_median_host_period_error_us'])
    return {'device': device, 'tap_block_frame_counts': widths, 'median_absolute_host_period_error_us': median_error,
            'maximum_absolute_host_period_error_us': max(errors, default=None),
            'predictions': {'device_and_tap_width': device.get('bufferFrames') == options['expected_frames']
                            and list(widths) == [options['expected_frames']],
                            'tap_width_matches_device': list(widths) == [device.get('bufferFrames')]}}


def measure(spec, case_path, app, artifacts, execute, graph_control):
    inspector = artifacts / 'coreaudio-output-processes'
    execute(['xcrun', 'swiftc', '-O', '-framework', 'CoreAudio', str(INSPECTOR), '-o', str(inspector)])
    browser_case = case_path
    if 'base_case' in spec:
        browser_case = artifacts / 'effective-case.json'
        browser_case.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + '\n')
    command = ['node', str(SAFARI), str(browser_case), str(artifacts), str(inspector)]
    log = artifacts / 'browser-command.log'
    route = None
    if graph_control:
        execute([*command, '', '', 'graph-control'], cwd=WEB, stdout=log)
    else:
        with tap.staged_app(app, artifacts) as (local_app, recording):
            try:
                command += [str(local_app), str(recording)]
                if 'output_device' in spec:
                    probe = artifacts / 'coreaudio-output-device'
                    execute(['xcrun', 'swiftc', '-O', '-framework', 'CoreAudio', str(OUTPUT_DEVICE), '-o', str(probe)])
                    route = capture_on_output(spec, artifacts, probe, lambda: execute(
                        [*command, '', str(probe)], cwd=WEB, stdout=log))
                else:
                    execute(command, cwd=WEB, stdout=log)
            finally:
                tap.stop_tap(local_app, recording)

    browser = read_json(artifacts / 'capture.json')
    result = {'phase': browser['phase'], 'browser_error': browser.get('error'), 'target': browser.get('confirmedTarget'),
              'tap_launch': browser.get('tap'), 'permission_observation': permission_observation(artifacts)}
    checks = {'safari_session': browser.get('capabilities', {}).get('browserName') == 'Safari',
              'target_reconfirmed': identified_process(browser)}
    if graph_control:
        checks['graph_control_completed'] = browser['phase'] == 'graph_control_complete'
    else:
        checks['tap_started_and_stopped'] = browser['phase'] == 'complete'
    smooth = spec['marker'].get('shape') == 'smooth-binary'
    for label, trusted in (('pilot-marker', 'pilotTrusted'), ('capture-marker', 'restartedTrusted')):
        checks[f'{label}/trusted_play_and_graph'] = bool(browser.get(trusted) and (artifacts / f'{label}.json').is_file())
        if checks[f'{label}/trusted_play_and_graph']:
            graph, pcm, diagnostics = inspect_graph(artifacts, label, spec)
            if diagnostics is not None:
                result[f'{label}_pcm'] = diagnostics
            checks.update({f'{label}/{key}': bool(value) for key, value in graph.items()})
            if label == 'pilot-marker' and all(graph.values()):
                local, result['injected'] = (smooth_tap_marker.injected_controls(spec) if smooth
                                             else injected_controls(pcm, spec))
                checks.update(local)
    native = artifacts / 'tap.json'
    if route is not None:
        result['output_route'] = route
        checks['active_device_matches_case'] = False
        checks['original_output_restored'] = route.get('after', {}).get('defaultOutput') == route['before']['defaultOutput']
    if native.is_file() and (artifacts / 'tap.f32le').is_file():
        tape = read_json(native)
        observer = smooth_tap_marker.observe if smooth else None
        inspected = tap.inspect_tape(artifacts, spec, observe_marker=observer)
        result['tape'] = inspected
        checks.update({f'tap/{key}': value for key, value in inspected['checks'].items()})
        times = [block.get('hostTime') for block in tape['blocks']]
        checks['tap/host_time_monotonic'] = (len(times) >= 2 and None not in times
                                            and all(b > a for a, b in zip(times, times[1:])))
        checks['tap/matched_target_pid'] = result['target'] is not None and tape['pid'] == result['target']['pid']
        checks['tap/reverse_polarity'] = (inspected.get('stereo_common_mode_peak', np.inf)
                                          <= spec['maximum_stereo_common_mode_ratio'] * inspected['pcm_peak'])
        if route is not None:
            result['output_measurement'] = compare_output_device(spec, browser, tape, route, checks)
    transcript = artifacts / 'tap-command.log'
    if transcript.is_file():
        result['tap_program_log'] = transcript.read_text(errors='replace').strip()
    return result | {'checks': checks}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('app', type=Path, nargs='?')
    parser.add_argument('--case', type=Path, default=CASE)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--inspect-permission', metavar='CAPTURE_RUN', help='保存済み試行の採取アプリの許可要求をOSログで照合する')
    modes.add_argument('--graph-control', action='store_true', help='Safariの試験音とCore Audioのプロセスの対応までを確認する')
    args = parser.parse_args()
    case_path = args.case.resolve(strict=True)
    spec = read_json(case_path)
    case_inputs = [case_path]
    if 'base_case' in spec:
        if spec['base_case'] != CASE.name:
            parser.error('指定された較正の基準ケースに対応していません')
        case_inputs.append(CASE)
        spec = read_json(CASE) | spec
    revision = spec['upstream_revision']
    if (subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip() != revision
            or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True)):
        parser.error('変更のない固定上流が必要です')
    if args.inspect_permission:
        if args.app:
            parser.error('許可要求の照合に採取アプリの指定は不要です')
        previous = run_manifest(args.inspect_permission, spec['id'], revision)
        capture = verified_path(previous, 'artifacts/capture.json')
        pid_file = verified_path(previous, 'artifacts/tap-pid')
        inputs = [*case_inputs, Path(__file__).resolve(), previous[0] / 'manifest.json', capture, pid_file]
        details = {'case_id': spec['id'], 'upstream_revision': revision, 'capture_run': args.inspect_permission,
                   'analysis_command': [sys.executable, *sys.argv], 'analysis_directory': str(Path.cwd())}

        def inspect(_artifacts, _execute):
            run = read_json(capture)
            recorded = permission_observation(pid_file.parent, run['snapshots'][0]['atEpochMs'])
            return {'capture_phase': run['phase'], 'permission_observation': recorded,
                    'checks': {'audio_capture_prompt_observed': bool(recorded and recorded.get('prompt_events'))}}

        return record_measurement(args.run_id, case_path, inputs, details, inspect, command=None, input_root=ROOT)
    if not args.app and not args.graph_control:
        parser.error('較正には採取アプリを指定してください')
    if args.app and args.graph_control:
        parser.error('グラフの対照に採取アプリの指定は不要です')
    app = args.app.resolve(strict=True) if args.app else None
    tool_sources = [*case_inputs, INSPECTOR, Path(__file__).resolve(), SAFARI, SAFARI.with_name('safari-webdriver.mjs'),
                    SAFARI.with_name('shared-context-marker-worklet.js'), SAFARI.with_name('shared-context-marker.mjs'), tap.NATIVE, tap.PLIST,
                    Path(tap.__file__), Path(smooth_tap_marker.__file__), WORKSPACE / 'tools/measure_uniform_tube.py',
                    WORKSPACE / 'tools/upstream_baseline.py', WORKSPACE / 'tools/measure_worklet_fixed.py']
    metadata = {'case_id': spec['id'], 'upstream_revision': revision, 'graph_control': args.graph_control,
                'analysis_directory': str(Path.cwd()), 'analysis_command': [sys.executable, *sys.argv],
                'safaridriver': subprocess.check_output(['/usr/bin/safaridriver', '--version'], text=True).strip(),
                'swift': subprocess.check_output(['xcrun', 'swiftc', '--version'], text=True).strip(),
                'node': subprocess.check_output(['node', '--version'], text=True).strip()}
    if app:
        subprocess.run(['/usr/bin/codesign', '--verify', str(app)], check=True)
        metadata.update(tap_app=str(app), tap_binary_sha256=sha256(app / 'Contents/MacOS/chimera-process-tap'),
                        tap_info_sha256=sha256(app / 'Contents/Info.plist'))
    if 'output_device' in spec:
        if not app:
            parser.error('出力機器を選ぶ校正には採取アプリを指定してください')
        tool_sources.append(OUTPUT_DEVICE)
    if 'comparison_run' in spec:
        reference = run_manifest(spec['comparison_run'], spec['comparison_case'], revision)
        prior_case = verified_path(reference, 'artifacts/effective-case.json')
        prior_summary = verified_path(reference, 'summary.json')
        old = read_json(prior_case)
        if (reference[1]['status'] != 'pass' or read_json(prior_summary)['tape']['sample_rate_hz'] == spec['sample_rate_hz']
                or any(old[key] != spec[key] for key in ('marker', 'quantum_frames', 'window_frames',
                    'minimum_correlation', 'minimum_distinct_peak_margin', 'maximum_relative_residual'))
                or any(reference[1][key] != metadata[key] for key in ('tap_binary_sha256', 'tap_info_sha256'))):
            parser.error('比較用の校正実行と試験信号・採取器の条件が一致しません')
        metadata['comparison_run'] = spec['comparison_run']
        tool_sources.extend((reference[0] / 'manifest.json', prior_case, prior_summary))
    return record_measurement(args.run_id, case_path, tool_sources, metadata,
                              lambda artifacts, execute: measure(spec, case_path, app, artifacts, execute, args.graph_control),
                              command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
