"""プロセスタップと、逆相ステレオに載せたフレーム印を照合する。"""

import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
from tempfile import TemporaryDirectory
import time

import numpy as np
from scipy.io import wavfile

import measure_worklet_live_song_output_callback as callback


song = callback.song
CASE = song.WORKSPACE / 'cases/worklet-live-song-process-tap-probe.json'
NATIVE = Path(__file__).with_name('chimera_process_tap.swift').resolve()
PLIST = Path(__file__).with_name('chimera_process_tap_info.plist').resolve()
PLAYBACK_CASE = song.WORKSPACE / 'cases/worklet-live-song-process-tap.json'


def marker_pcm(count, marker):
    frames = np.arange(count, dtype=np.int64)
    values = (frames * marker['multiplier'] + marker['offset']) % marker['modulus']
    return ((values - marker['center']) / marker['scale']).astype('<f4')


def decode(stereo, marker, tolerance):
    # 歌唱を両チャンネルに同じ値で加え、フレーム印だけを逆相に置く。
    diff = (stereo[:, 0].astype(np.float64) - stereo[:, 1]) / 2
    positive = np.diff(diff)
    positive = positive[(positive > 0) & np.isfinite(positive)]
    if not positive.size:
        return None
    gain = float(np.median(positive)) * marker['scale'] / marker['multiplier']
    if not 0.05 <= gain <= 20:
        return None
    values = diff * (marker['scale'] / gain) + marker['center']
    rounded = np.rint(values)
    modulus = marker['modulus']
    valid = np.isfinite(values) & (np.abs(values - rounded) <= tolerance) & (rounded >= 0) & (rounded < modulus)
    # 1サンプルのゼロは印の一部になり得る。ゼロが連続する区間は有効な印から外す。
    zero = diff == 0
    repeated_zero = zero[:-1] & zero[1:]
    valid[:-1] &= ~repeated_zero
    valid[1:] &= ~repeated_zero
    phases = np.full(len(values), -1, dtype=np.int64)
    inverse = pow(marker['multiplier'], -1, modulus)
    phases[valid] = ((rounded[valid].astype(np.int64) - marker['offset']) * inverse) % modulus
    return diff, gain, phases, valid


def continuous_spans(phases, valid, modulus):
    linked = valid[:-1] & valid[1:] & (((phases[1:] - phases[:-1]) % modulus) == 1)
    cuts, = np.nonzero(~linked)
    starts = np.r_[0, cuts + 1]
    ends = np.r_[cuts + 1, len(phases)]
    return [(int(a), int(b)) for a, b in zip(starts, ends) if valid[a]]


def resolve_marker_window(stereo, marker, case, first, last):
    decoded = decode(stereo, marker, case['maximum_error_marker_units'])
    if decoded is None:
        return {'valid': False, 'reason': 'marker_gain_not_recovered'}
    _, gain, phases, valid = decoded
    modulus = marker['modulus']
    span = case['minimum_contiguous_anchor_frames']
    left, right = [], []
    for a, b in continuous_spans(phases, valid, modulus):
        if b - a < span:
            continue
        first_position = a + (first - int(phases[a])) % modulus
        suffix_start = a + span - 1
        last_position = suffix_start + (last - int(phases[suffix_start])) % modulus
        left.extend(range(first_position, b - span + 1, modulus))
        right.extend(range(last_position, b, modulus))
    length = last - first + 1
    allowance = case['maximum_anchor_displacement_frames']
    candidates = [(a, b) for a in left for b in right if b >= a and abs(b - a + 1 - length) <= allowance]
    if len(candidates) != 1:
        return {'valid': False, 'reason': 'marker_anchors_not_unique', 'anchor_candidates': len(candidates)}

    start, end = candidates[0]
    observed = np.flatnonzero(valid[start:end + 1]) + start
    jumps = []
    source_frame = first
    for a, b in zip(observed[:-1], observed[1:]):
        # 位相の差から、間に実際に出力されたフレーム数を引く。
        offset = (int(phases[b] - phases[a] - (b - a)) + modulus // 2) % modulus - modulus // 2
        previous_source_frame = source_frame
        source_frame += int(b - a) + offset
        if offset or b - a > 1:
            jumps.append({'first_following_frame': int(b), 'marker_displacement': int(offset),
                          'undecoded_frames': int(b - a - 1),
                          'source_frames_around_transition': [previous_source_frame, source_frame]})
    if source_frame != last:
        return {'valid': False, 'reason': 'marker_period_ambiguous'}
    observed_pcm = stereo[start:end + 1]
    decoded_window = valid[start:end + 1]
    silent = ((observed_pcm == 0).all(axis=1) & ~decoded_window)
    return {'valid': True, 'tap_window': [start, end + 1], 'expected_frames': length,
            'captured_frames': end - start + 1, 'marker_gain': gain,
            'missing_marker_frames': sum(max(0, x['marker_displacement']) for x in jumps),
            'repeated_marker_frames': sum(max(0, -x['marker_displacement']) for x in jumps),
            'undecoded_frames': int(np.count_nonzero(~decoded_window)),
            'silent_frames': int(np.count_nonzero(silent)), 'transitions': jumps}


def inspect_tape(folder, case, *, observe_marker=None):
    tape = song.wasm.read_json(folder / 'tap.json')
    pcm = np.fromfile(folder / 'tap.f32le', dtype='<f4').reshape(-1, 2)
    blocks = tape['blocks']
    peak = float(np.max(np.abs(pcm), initial=0))
    complete = (len(pcm) == tape['frames'] == sum(block['frames'] for block in blocks)
                and all(b['offset'] == a['offset'] + a['frames'] for a, b in zip(blocks, blocks[1:])))
    timed = all(b.get('sampleTime') is not None and b.get('hostTime') is not None for b in blocks)
    clock_jumps = ([b['sampleTime'] - a['sampleTime'] - a['frames'] for a, b in zip(blocks, blocks[1:])]
                   if timed else [])
    checks = {'sample_rate': tape['sampleRate'] == case['sample_rate_hz'],
              'buffers_complete': complete and not tape['overflow'] and tape['formatErrors'] == 0,
              'block_times_recorded': bool(blocks) and timed,
              'block_times_contiguous': bool(clock_jumps) and all(n == 0 for n in clock_jumps),
              'pcm_finite_and_nonzero': bool(np.isfinite(pcm).all()) and peak > 0}
    report = {'checks': checks, 'sample_rate_hz': tape['sampleRate'], 'frames': len(pcm), 'pcm_peak': peak,
              'maximum_block_clock_jump_frames': max(map(abs, clock_jumps), default=None)}
    if observe_marker is not None:
        marker = observe_marker(pcm, case)
        checks['known_marker_continuous'] = marker['known_marker_continuous']
        report.update(smooth_marker=marker, stereo_common_mode_peak=float(np.max(
            np.abs(pcm.astype(np.float64).mean(axis=1)), initial=0)))
        return report
    report.update(matching_frames=0, longest_matching_span=None)
    checks['known_marker_continuous'] = False
    decoded = decode(pcm, case['marker'], case['maximum_error_marker_units']) if len(pcm) and peak > 0 else None
    if decoded is not None:
        diff, gain, phases, valid = decoded
        spans = continuous_spans(phases, valid, case['marker']['modulus'])
        report.update(matching_frames=int(np.count_nonzero(valid)), marker_gain=gain,
                      stereo_common_mode_peak=float(np.max(np.abs(pcm.astype(np.float64).sum(axis=1) / 2))))
        if spans:
            a, b = max(spans, key=lambda span: span[1] - span[0])
            report['longest_matching_span'] = {
                'start': a, 'frames': b - a, 'marker_phase': int(phases[a]),
                'maximum_error_marker_units': float(np.max(np.abs(
                    diff[a:b] / gain - marker_pcm(case['marker']['modulus'], case['marker'])[phases[a:b]]
                ))) * case['marker']['scale'],
            }
            checks['known_marker_continuous'] = b - a >= case['minimum_contiguous_frames']
    return report


def inspect_playback_window(folder, trial, shared_case, case, frame_spec, outer_marker):
    profile = callback.read_json(folder / 'firefox-profile.json.gz')
    marker = callback.read_json(folder / 'marker.json')
    checks, graph = callback.reconcile(profile, trial['timing'], marker['frames'], frame_spec, outer_marker)
    expected_frames = case['expected_request_frames']
    if (not all(checks.values()) or len(graph['rows']) != 2 * case['window_radius_requests'] + 1
            or any(row['requested_frames'] != expected_frames or row['graph_advance_frames'] != expected_frames
                   for row in graph['rows'])):
        return {'valid': False, 'reason': 'graph_window_unverified'}
    first = graph['rows'][0]['reference_frame_starts'][0] - marker['startFrame']
    last = graph['rows'][-1]['reference_frame_starts'][-1] - marker['startFrame'] + frame_spec['worklet_quantum_frames'] - 1
    if first < 0 or last >= len(marker['frames']) * frame_spec['worklet_quantum_frames']:
        return {'valid': False, 'reason': 'outside_saved_marker'}
    spec = case | {'marker': shared_case['measurement']['marker'], 'minimum_contiguous_frames': case['minimum_contiguous_anchor_frames']}
    calibration = inspect_tape(folder, spec)
    if not all(calibration['checks'].values()):
        return {'valid': False, 'reason': 'tap_calibration_failed', 'calibration': calibration}
    stereo = np.fromfile(folder / 'tap.f32le', dtype='<f4').reshape(-1, 2)
    result = resolve_marker_window(stereo, spec['marker'], spec, first, last)
    result['graph_marker_window'] = [first, last + 1]
    result['center_graph_marker_frame'] = (graph['rows'][case['window_radius_requests']]['reference_frame_starts'][0]
                                          - marker['startFrame'])
    result['client_next_callback_delay_ms'] = graph['next_callback_delay_ms']
    result['calibration'] = calibration
    return result


def playback_analysis(run_id, capture_id):
    case = callback.read_json(PLAYBACK_CASE)
    capture = song.run_manifest(capture_id, case['id'], case['upstream_revision'])
    capture_summary_path = song.verified_path(capture, 'summary.json')
    capture_summary = callback.read_json(capture_summary_path)
    shared_case_path = callback.shared.CASE
    frames_path = PLAYBACK_CASE.parent / case['frame_validation_case']
    phase_path = callback.phases.CASE
    shared_case = callback.read_json(shared_case_path)
    frames = callback.read_json(frames_path)['measurement']
    phase = callback.read_json(phase_path)['measurement']
    inputs = [Path(__file__).resolve(), PLAYBACK_CASE, shared_case_path, frames_path, phase_path,
              Path(callback.__file__).resolve(), capture[0] / 'manifest.json', capture_summary_path]
    for trial in capture_summary['trials']:
        for name in ('firefox-profile.json.gz', 'marker.json', 'tap.f32le', 'tap.json'):
            path = f"artifacts/{trial['trial']}/{name}"
            if (capture[0] / path).is_file():
                inputs.append(song.verified_path(capture, path))

    def analyze(_artifacts, _execute):
        checks, trials = {}, []
        for trial in capture_summary['trials']:
            label = trial['trial']
            folder = capture[0] / 'artifacts' / label
            local = [ok for name, ok in capture_summary['checks'].items() if name.startswith(f'{label}/')]
            try:
                if not (folder / 'tap.json').is_file():
                    result = {'valid': False, 'reason': 'tap_not_recorded'}
                elif not local or not all(local) or not trial.get('timing_checks_passed'):
                    result = {'valid': False, 'reason': 'capture_checks_unverified'}
                else:
                    result = inspect_playback_window(folder, trial, shared_case, case, frames, phase['engine_marker'])
            except (OSError, EOFError, KeyError, TypeError, ValueError) as error:
                result = {'valid': False, 'reason': 'saved_evidence_incomplete', 'error': str(error)}
            trials.append({'trial': label, **result})
            checks[label] = result['valid']
        return {'checks': checks, 'trials': trials}

    details = {'case_id': case['id'], 'upstream_revision': case['upstream_revision'], 'capture_run': capture_id,
               'analysis_command': [sys.executable, *sys.argv], 'analysis_directory': str(Path.cwd())}
    return song.shared.record_measurement(run_id, PLAYBACK_CASE, inputs, details, analyze, command=None, input_root=song.ROOT)


def app_command(app, pid, seconds, folder):
    return ['/usr/bin/open', '-nW', '--stderr', str(folder / 'tap-command.log'), str(app),
            '--args', str(pid), str(seconds), str(folder)]


@contextmanager
def staged_app(app, artifacts):
    # LaunchServicesの起動とstderrの受け渡しは内蔵の一時領域に置く。
    # 保存用の計測成果だけを実行先へ移す。アプリの署名と許可設定はそのまま使う。
    with TemporaryDirectory(prefix='chimera-process-tap-', dir='/tmp') as tmp:
        stage = Path(tmp).resolve()
        local_app = stage / app.name
        subprocess.run(['/usr/bin/ditto', str(app), str(local_app)], check=True)
        record = stage / 'capture'
        record.mkdir()
        (record / 'tap-command.log').touch()
        try:
            yield local_app, record
        finally:
            for file in record.iterdir():
                shutil.copyfile(file, artifacts / file.name)


def stop_tap(app, folder):
    pidfile = folder / 'tap-pid'
    if pidfile.is_file():
        pid = int(pidfile.read_text())
        check = subprocess.run(['/bin/ps', '-p', str(pid), '-o', 'comm='], capture_output=True, text=True)
        if check.stdout.strip() == str(app.resolve() / 'Contents/MacOS/chimera-process-tap'):
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass


def await_file(path, owner, deadline):
    while not path.is_file():
        if owner.poll() is not None or time.monotonic() >= deadline:
            return False
        time.sleep(0.01)
    return True


def firefox_child(browser):
    listing = subprocess.check_output(['/bin/ps', '-axo', 'pid=,ppid=,comm='], text=True)
    children = []
    for line in listing.splitlines():
        pid, parent, command = line.split(None, 2)
        if int(parent) == browser.pid and Path(command).name in ('firefox', 'firefox-bin'):
            children.append(pid)
    if len(children) != 1:
        raise ValueError('計測用のFirefox親プロセスを一意に特定できません')
    return int(children[0])


def publish_trace_target(artifacts, pid):
    pending = artifacts / 'trace-target.tmp'
    pending.write_text(json.dumps({'firefox_pid': pid}) + '\n')
    pending.replace(artifacts / 'trace-target.json')


def browser_bridge(app, artifacts, case, command):
    spec = case['capture']
    gate = artifacts / 'trace-release.json'
    wait_for_trace = spec.get('wait_for_trace_before_release', False)
    tap_before_trace = app is not None and spec.get('trace_before_playback') and wait_for_trace
    with subprocess.Popen(command) as browser:
        try:
            if not await_file(artifacts / 'trace-ready.json', browser, time.monotonic() + 30):
                raise ValueError('Firefoxから先行音の準備通知を受け取れません')
            pid = firefox_child(browser) if app is not None or spec.get('publish_trace_target') else None
            if spec.get('publish_trace_target') and not tap_before_trace:
                publish_trace_target(artifacts, pid)
            if app is None:
                if spec.get('trace_before_playback') and not await_file(
                        artifacts / 'system-trace-ready.json', browser, time.monotonic() + 15):
                    raise ValueError('再生前にシステムトレースの開始を確認できません')
                time.sleep(spec['construction_delay_seconds'])
                release = {'tap_requested': False, 'tap_ready': False, 'release_epoch_ns': time.time_ns()}
                if spec.get('observe_start_signals'):
                    release['release_monotonic_ns'] = time.monotonic_ns()
                gate.write_text(json.dumps(release) + '\n')
                return browser.wait(timeout=45)
            with staged_app(app, artifacts) as (local_app, record):
                with (artifacts / 'tap-launch.log').open('wb') as log, subprocess.Popen(
                        app_command(local_app, pid, spec['tap_duration_seconds'], record),
                        stdout=log, stderr=subprocess.STDOUT) as tap:
                    try:
                        ready = await_file(record / 'tap-ready', tap, time.monotonic() + spec['tap_ready_timeout_seconds'])
                        prepared_at = time.monotonic_ns() if ready else None
                        if tap_before_trace:
                            if not ready:
                                raise ValueError('再生前にFirefoxのプロセスタップを準備できません')
                            publish_trace_target(artifacts, pid)
                        if wait_for_trace:
                            (artifacts / 'trace-tap-ready.json').write_text(json.dumps({'tap_ready': ready}) + '\n')
                            if not await_file(artifacts / 'system-trace-ready.json', browser, time.monotonic() + 15):
                                raise ValueError('タップ準備後にシステムトレースの開始を確認できません')
                        if ready or wait_for_trace:
                            time.sleep(spec['construction_delay_seconds'])
                        release = {'tap_requested': True, 'tap_ready': ready, 'release_epoch_ns': time.time_ns()}
                        if spec.get('observe_start_signals'):
                            release.update(tap_ready_monotonic_ns=prepared_at, release_monotonic_ns=time.monotonic_ns())
                        gate.write_text(json.dumps(release) + '\n')
                        tap.wait(timeout=spec.get('tap_wait_timeout_seconds', 5))
                    except subprocess.TimeoutExpired:
                        stop_tap(local_app, record)
                        tap.terminate()
                    except BaseException:
                        stop_tap(local_app, record)
                        tap.terminate()
                        raise
            return browser.wait(timeout=45)
        finally:
            if browser.poll() is None:
                browser.terminate()


def bridge_main(argv):
    parser = argparse.ArgumentParser(description='準備済みのFirefoxの出力を採取する')
    parser.add_argument('app', type=Path)
    parser.add_argument('artifacts', type=Path)
    parser.add_argument('case', type=Path)
    parser.add_argument('--no-tap', action='store_true', help='採取アプリを起動せずにゲートを解放する')
    separator = argv.index('--')
    args = parser.parse_args(argv[:separator])
    case = song.wasm.read_json(args.case)
    if 'base_case' in case:
        case = song.wasm.read_json(args.case.with_name(case['base_case'])) | case
    return browser_bridge(None if args.no_tap else args.app, args.artifacts, case, argv[separator+1:])


def probe(case, app, artifacts):
    expected = marker_pcm(case['sample_rate_hz'] * case['fixture_duration_seconds'], case['marker'])
    fixture = artifacts / 'fixture.wav'
    wavfile.write(fixture, case['sample_rate_hz'], np.column_stack((expected, -expected)))
    with (artifacts / 'afplay.log').open('wb') as log, subprocess.Popen(
            ['/usr/bin/afplay', str(fixture)], stdout=log, stderr=subprocess.STDOUT) as player:
        try:
            time.sleep(0.7)
            # 許可の確認を含むAPI側の待機に上限を設ける。
            with staged_app(app, artifacts) as (local_app, record):
                command = app_command(local_app, player.pid, case['capture_duration_seconds'], record)
                (artifacts / 'tap-command.json').write_text(json.dumps(command, ensure_ascii=False) + '\n')
                try:
                    with (artifacts / 'tap-launch.log').open('wb') as output:
                        tap = subprocess.run(command, stdout=output, stderr=subprocess.STDOUT, timeout=35)
                except subprocess.TimeoutExpired:
                    stop_tap(local_app, record)
                    return {'checks': {'tap_started_and_stopped': False}, 'tap_wait_timeout_seconds': 35}
            if tap.returncode != 0 or not (artifacts / 'tap.json').is_file():
                return {'checks': {'tap_started_and_stopped': False}, 'tap_exit_code': tap.returncode}
            return inspect_tape(artifacts, case)
        finally:
            if player.poll() is None:
                player.terminate()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('app', type=Path)
    args = parser.parse_args()
    case = song.wasm.read_json(CASE)
    app = args.app.resolve(strict=True)
    binary = app / 'Contents/MacOS/chimera-process-tap'
    inputs = [CASE, NATIVE, PLIST, Path(__file__).resolve()]
    details = {'case_id': case['id'], 'upstream_revision': case['upstream_revision'],
               'tap_binary': str(binary), 'tap_binary_sha256': song.sha256(binary)}
    return song.shared.record_measurement(args.run_id, CASE, inputs, details,
        lambda artifacts, _execute: probe(case, app, artifacts), command=None, input_root=song.ROOT)


if __name__ == '__main__':
    if sys.argv[1:2] == ['--browser-bridge']:
        raise SystemExit(bridge_main(sys.argv[2:]))
    if sys.argv[1:2] == ['--playback-analysis']:
        parser = argparse.ArgumentParser(description='保存したFirefoxの出力PCMを照合する')
        parser.add_argument('run_id')
        parser.add_argument('capture_id')
        args = parser.parse_args(sys.argv[2:])
        raise SystemExit(playback_analysis(args.run_id, args.capture_id))
    raise SystemExit(main())
