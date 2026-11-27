"""固定cubebの出力要求とプロセスタップを同じ試行で照合する。"""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import numpy as np

import inspect_firefox_cubeb_output as paired
import measure_cubeb_output_callback as cubeb
import measure_worklet_live_song_process_tap as tap
import smooth_tap_marker


WORKSPACE, ROOT = tap.song.WORKSPACE, tap.song.ROOT
CASE = WORKSPACE / 'cases/cubeb-output-callback-process-tap.json'


def read(path):
    return json.loads(path.read_text())


def capture(folder, binary, app, marker, case, delay_us, *, during_playback=None):
    folder.mkdir()
    ready = folder / 'probe-ready'
    command = [str(binary), str(case['sample_rate_hz']), str(case['requested_frames']),
               str(case['overrun_callback_index']), str(delay_us), str(case['observation_callbacks'] + 2),
               str(marker), str(ready)]
    env = os.environ | {'CHIMERA_CUBEB_OUTPUT_DIR': str(folder),
                        'CHIMERA_CUBEB_OUTPUT_BLOCKS': str(case['observation_callbacks'])}
    report = {'probe_command': command, 'tap_ready': False, 'delay_us': delay_us}
    try:
        with (folder / 'probe.json').open('wb') as output, (folder / 'probe.log').open('wb') as log:
            with subprocess.Popen(command, env=env, stdin=subprocess.PIPE, stdout=output, stderr=log) as probe:
                try:
                    if not tap.await_file(ready, probe, time.monotonic() + 5):
                        raise ValueError('cubebの準備が完了しません')
                    report['pid'] = probe.pid
                    with tap.staged_app(app, folder) as (local, recording):
                        command = tap.app_command(local, probe.pid, case['tap_seconds'], recording)
                        report['tap_command'] = [arg.replace(str(local.parent), '$TAP_STAGE') for arg in command]
                        with (folder / 'tap-launch.log').open('wb') as tap_log, subprocess.Popen(
                                command, stdout=tap_log, stderr=subprocess.STDOUT) as recorder:
                            try:
                                deadline = time.monotonic() + case['tap_ready_timeout_seconds']
                                report['tap_ready'] = tap.await_file(recording / 'tap-ready', recorder, deadline)
                                if not report['tap_ready']:
                                    raise ValueError('タップ開始の通知を受け取れません')
                                time.sleep(case['tap_lead_seconds'])
                                probe.stdin.write(b'\x01')
                                probe.stdin.flush()
                                if during_playback is not None:
                                    report['during_playback'] = during_playback()
                                report['probe_exit_code'] = probe.wait(timeout=7)
                                report['tap_exit_code'] = recorder.wait(timeout=case['tap_seconds'] + 3)
                            finally:
                                if recorder.poll() is None:
                                    tap.stop_tap(local, recording)
                                    recorder.terminate()
                finally:
                    if probe.poll() is None:
                        probe.terminate()
    finally:
        (folder / 'capture.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    return report


def locate_gap(difference, alignment, first, center, width, marker):
    length = len(difference) - width
    frames = first + np.arange(length)
    chips = smooth_tap_marker.chip_values(marker)
    left, right = alignment['anchors']
    before, after = (smooth_tap_marker.waveform(chips, marker, frames + anchor['fraction']) * anchor['gain']
                     for anchor in (left, right))
    norm = np.linalg.norm(difference)
    gap = np.zeros(width)
    candidates = range(center - width, center + width + 1)
    residual, position = min((float(np.linalg.norm(difference - np.r_[before[:i], gap, after[i:]]) / norm), i)
                             for i in candidates)
    return {'start_frame_in_window': position, 'relative_residual': residual, 'searched_frames': len(candidates)}


def inspect(folder, case, reference, run):
    marker = case['smooth_alignment']['marker']
    streams = sorted(folder.glob('cubeb-output-*'))
    checks = {'subprocesses_finished': run['probe_exit_code'] == run['tap_exit_code'] == 0,
              'one_stream': len(streams) == 1}
    result = {'checks': checks}
    if not all(checks.values()):
        return result
    stream, = streams
    metadata = read(folder / 'probe.json')
    native = result['cubeb'] = cubeb.inspect(stream, metadata, case, reference_pcm=reference)
    checks.update(native['checks'])
    if not all(checks.values()):
        return result
    rows = cubeb.load_blocks(stream)
    center = case['overrun_callback_index']
    radius = case['window_radius_callbacks']
    width = case['requested_frames']
    first = rows[center - radius]['pcm_byte_offset'] // 8
    last = first + native['matched_pcm_frames']
    if last <= first:
        raise ValueError('cubebのPCMを照合できません')
    core = {'valid': True, 'graph_marker_window': [first, last], 'matched_streams': [stream.name],
            'host_tick_ms': metadata['timebase_numer'] / metadata['timebase_denom'] / 1e6,
            'streams': {stream.name: {'pcm': {'tap_window': [first, last], 'anchors': [{'fraction': 0.0}] * 2}}}}
    observed = result['paired'] = paired.inspect_pair(folder, core, marker, case)
    checks['paired_window'] = observed['valid']
    if not observed['valid']:
        return result
    checks['matched_pid'] = read(folder / 'tap.json')['pid'] == run['pid']

    pcm = observed['pcm']
    lo, hi = pcm['tap_window']
    stereo = np.fromfile(folder / 'tap.f32le', dtype='<f4').reshape(-1, 2)[lo:hi]
    zeros = np.all(stereo == 0, axis=1)
    edges = np.flatnonzero(np.diff(np.r_[False, zeros, False])).reshape(-1, 2).tolist()
    result.update(cubeb_pcm_window=[first, last], tap_zero_spans=edges)
    late = run['delay_us'] > 0
    expected_gap = width if late else 0
    predictions = result['predictions'] = {
        'target_clock_gap': native['target']['device_sample_gap_frames'] == expected_gap,
        'other_cubeb_clocks_continuous': all(row['device_sample_gap_frames'] == 0 for row in native['intervals']
                                            if row['offset'] != 0),
        'tap_clock_continuous': not observed['tap_sample_clock_jumps'],
        'tap_window_length': pcm['captured_frames'] - pcm['expected_frames'] == expected_gap,
        'endpoint_offset_change': abs(observed['host_time_offset_change_ms']) <= case['maximum_endpoint_offset_change_ms'],
        'tap_zero_span': edges == ([[radius * width + case['expected_leading_edge_frames'],
                                    radius * width + case['expected_leading_edge_frames'] + case['expected_tap_zero_frames']]]
                                  if late else []),
    }
    if late and predictions['tap_window_length']:
        difference = (stereo[:, 0].astype(float) - stereo[:, 1]) / 2
        fit = result['inserted_zero_model'] = locate_gap(difference, pcm, first, radius * width, width, marker)
        predictions['zero_model_location_and_fit'] = (fit['start_frame_in_window'] == radius * width
            and fit['relative_residual'] <= case['maximum_inserted_zero_model_residual'])
    return result


def measure(case, binary, app, artifacts):
    marker = case['smooth_alignment']['marker']
    period = marker['chips'] * marker['frames_per_chip']
    mono = smooth_tap_marker.marker_pcm(period, marker)
    fixture = artifacts / 'marker.f32le'
    fixture.write_bytes(mono.tobytes())
    count = case['observation_callbacks'] * case['requested_frames']
    reference = mono[np.arange(count) % period]
    stereo = np.column_stack((reference, -reference)).tobytes()
    checks, trials = {}, {}
    for i, order in enumerate(case['condition_order'], 1):
        for condition in order:
            label = f'{i}-{condition}'
            folder = artifacts / label
            delay = round(case['delay_ms'] * 1000) if condition == 'overrun' else 0
            try:
                run = capture(folder, binary, app, fixture, case, delay)
                result = inspect(folder, case, stereo, run)
            except (OSError, KeyError, ValueError, subprocess.SubprocessError) as error:
                result = {'checks': {'capture_and_comparison_completed': False}, 'error': str(error)}
            trials[label] = result
            checks.update({f'{label}/{name}': passed for name, passed in result['checks'].items()})
    return {'checks': checks, 'trials': trials}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('probe', type=Path)
    parser.add_argument('app', type=Path)
    parser.add_argument('calibration_run')
    args = parser.parse_args()
    binary, app = (p.resolve(strict=True) for p in (args.probe, args.app))
    study = read(CASE)
    case = read(cubeb.CASE) | study
    calibration_path = CASE.parent / study['calibration_case']
    smooth = read(calibration_path)
    calibration_base = CASE.parent / smooth['base_case']
    smooth = read(calibration_base) | smooth
    revision = case['upstream_revision']
    if (study['base_case'] != cubeb.CASE.name or smooth['upstream_revision'] != revision
            or case['sample_rate_hz'] != smooth['sample_rate_hz'] or smooth['marker']['shape'] != 'smooth-binary'
            or subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=tap.song.UPSTREAM, text=True).strip() != revision
            or subprocess.check_output(['git', 'status', '--porcelain'], cwd=tap.song.UPSTREAM, text=True)):
        parser.error('固定上流と同時採取の較正条件が一致しません')
    calibration = tap.song.run_manifest(args.calibration_run, smooth['id'], revision)
    effective = tap.song.verified_path(calibration, 'artifacts/effective-case.json')
    summary = tap.song.verified_path(calibration, 'summary.json')
    calibration_files = [tap.song.verified_path(calibration, f'artifacts/{name}') for name in ('tap.json', 'tap.f32le')]
    subprocess.run(['/usr/bin/codesign', '--verify', str(app)], check=True)
    binary_sha = tap.song.sha256(app / 'Contents/MacOS/chimera-process-tap')
    info_sha = tap.song.sha256(app / 'Contents/Info.plist')
    tape_checks = read(summary)['tape']['checks']
    if (calibration[1]['status'] != 'pass' or read(effective) != smooth or not all(tape_checks.values())
            or binary_sha != calibration[1]['tap_binary_sha256'] or info_sha != calibration[1]['tap_info_sha256']):
        parser.error('同じ採取器で同じ試験信号を照合した校正が必要です')
    case['smooth_alignment'] = smooth
    inputs = [CASE, cubeb.CASE, calibration_path, calibration_base, calibration[0] / 'manifest.json', effective,
              summary, *calibration_files, Path(__file__).resolve(), tap.NATIVE, tap.PLIST,
              *(Path(tool.__file__) for tool in (tap, cubeb, paired, smooth_tap_marker)),
              cubeb.TOOLS / 'chimera-cubeb-output-probe.rs', cubeb.TOOLS / 'chimera-cubeb-output-snapshot.patch']
    details = {'case_id': study['id'], 'upstream_revision': revision, 'analysis_directory': str(Path.cwd()),
               'analysis_command': [sys.executable, *sys.argv], 'cubeb_coreaudio_revision': case['cubeb_coreaudio_revision'],
               'probe_binary': str(binary), 'probe_binary_sha256': tap.song.sha256(binary),
               'tap_binary_sha256': binary_sha, 'tap_info_sha256': info_sha, 'calibration_run': args.calibration_run}
    return tap.song.shared.record_measurement(args.run_id, CASE, inputs, details,
        lambda artifacts, _execute: measure(case, binary, app, artifacts), command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
