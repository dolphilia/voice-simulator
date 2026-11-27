"""ブラウザと同じ44.1 kHzの信号をネイティブcubebから出力して比較する。"""

import argparse
from pathlib import Path
import subprocess
import sys
import time

import numpy as np

from measure_csd_envelope_timing import verified_file
from measure_cubeb_output_process_tap import capture
from measure_firefox_headphone_drift_44100 import CASE as DRIFT, analyze_pcm
from measure_firefox_headphone_response_44100 import CASE as RESPONSE, OUTPUT_DEVICE, read_stereo
from measure_safari_process_tap_calibration import capture_on_output, output_snapshot
from measure_speech_timing import read
from measure_tsp_listening import hydrate_run
from measure_uniform_tube import record_measurement
from measure_worklet_fixed import ROOT
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/native-cubeb-headphone-drift-44100.json'


def measure(folder, execute, case, calibration, binary, app, reference, expected_period, prior):
    probe = folder / 'coreaudio-output-device'
    execute(['xcrun', 'swiftc', '-O', '-framework', 'CoreAudio', str(OUTPUT_DEVICE), '-o', str(probe)])
    marker = folder / 'fixture.f32le'
    marker.write_bytes(reference.tobytes())
    native = case['capture_native']
    capture_case = native | {'sample_rate_hz': case['sample_rate_hz']}
    captured = {}

    def device_during_playback():
        time.sleep(native['device_snapshot_seconds_after_release'])
        return output_snapshot(probe)

    def acquire():
        captured.update(capture(folder / 'native', binary, app, marker, capture_case, native['delay_us'],
                                during_playback=device_during_playback))

    route = capture_on_output(case, folder, probe, acquire)
    return inspect_native(folder, case, calibration, route, captured, reference, expected_period, prior)


def inspect_native(folder, case, calibration, route, captured, reference, expected_period, prior,
                   *, snapshot_rate_validated=False):
    active = captured['during_playback']
    device, = [row for row in active['devices'] if row['id'] == active['defaultOutput']]
    settings = case['output_device']
    checks = {
        'probe_and_tap_completed': captured['tap_ready'] and captured['probe_exit_code'] == captured['tap_exit_code'] == 0,
        'registered_output_device_and_rate': (device['uid'], device['sampleRate']) ==
                                              (settings['uid'], settings['sample_rate_hz']),
        'original_output_restored': route['after']['defaultOutput'] == route['before']['defaultOutput'],
        'cubeb_coreaudio_backend': read(folder / 'native/probe.json')['backend'] == 'audiounit-rust',
    }
    results = analyze_pcm(folder / 'native', folder / 'native', case, calibration, expected_period, checks,
                          reference_pcm=reference, snapshot_rate_validated=snapshot_rate_validated)
    checks['tap_used_probe_pid'] = results['tap_pid'] == captured['pid']
    results.update(active_output_device=device, browser_hardware_width=settings['expected_frames'],
                   hardware_width_matches_browser=device['bufferFrames'] == settings['expected_frames'],
                   browser_comparison=prior, native_delay_us=captured['delay_us'])
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('probe', type=Path)
    parser.add_argument('app', type=Path)
    parser.add_argument('--case', type=Path, default=CASE)
    parser.add_argument('--output-run-id', help='保存済み収録の再解析に新しい出力IDを使う')
    args = parser.parse_args()
    spec, drift, response = (read(path) for path in (CASE, DRIFT, RESPONSE))
    if spec['base_case'] != DRIFT.name:
        parser.error('ネイティブ比較の基準ケースが一致しません')
    registered = args.case.resolve()
    review = None
    additional_inputs = []
    if registered != CASE:
        override = read(registered)
        if 'capture_reviews' in override:
            review = override
            snapshot_path = registered.with_name(review['base_case'])
            override = read(snapshot_path)
            additional_inputs.extend([registered, snapshot_path])
        if override['base_case'] != CASE.name or override['id'] != spec['id']:
            parser.error('ネイティブ比較の補足ケースが一致しません')
        spec |= override
    case = response | drift | spec
    for key in ('anchor', 'tone_probe', 'analysis'):
        case[key] = response[key] | drift[key]
    trials = [item['review_run'] for item in review['capture_reviews']] if review else spec['trial_ids']
    if args.run_id not in trials or (review and review['id'] != spec['id']) or (args.output_run_id and not review):
        parser.error('登録されたネイティブ比較の試行IDを指定してください')
    revision = case['upstream_revision']
    if (subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip() != revision
            or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True)):
        parser.error('変更のない固定上流が必要です')

    binary, app = args.probe.resolve(strict=True), args.app.resolve(strict=True)
    previous = hydrate_run(spec['native_probe_reference'], 'cubeb-output-callback-process-tap', revision)
    hashes = {'probe_binary_sha256': sha256(binary),
              'tap_binary_sha256': sha256(app / 'Contents/MacOS/chimera-process-tap'),
              'tap_info_sha256': sha256(app / 'Contents/Info.plist')}
    if snap := spec.get('snapshot_patch'):
        patch = WORKSPACE / 'tools' / snap
        checkout = binary.parents[3]
        original = Path(previous[1]['probe_binary']).parents[3] / 'cubeb-coreaudio-rs'
        # 収録条件以外のプローブ、バックエンド、依存の固定版が同じかを確認する。
        compared_paths = ('examples/chimera-paired-output-probe.rs', 'src/backend/mod.rs', 'Cargo.lock')
        if (subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=checkout, text=True).strip() != spec['cubeb_revision']
                or any(sha256(checkout / name) != sha256(original / name) for name in compared_paths)):
            parser.error('44.1 kHzの記録以外で、先行プローブのソースまたは版と一致しません')
        subprocess.run(['git', 'apply', '--reverse', '--check', str(patch)], cwd=checkout, check=True)
        hashes['native_snapshot_source_sha256'] = sha256(checkout / 'src/backend/chimera_output_snapshot.rs')
        additional_inputs.extend([registered, patch])
    elif previous[1].get('probe_binary_sha256') != hashes['probe_binary_sha256']:
        parser.error('既存の同時収録と同じネイティブcubebプローブを指定してください')
    if any(previous[1].get(key) != hashes[key] for key in ('tap_binary_sha256', 'tap_info_sha256')):
        parser.error('既存の同時収録と同じネイティブcubebプローブとタップを指定してください')
    subprocess.run(['/usr/bin/codesign', '--verify', str(app)], check=True)

    cal = hydrate_run(case['safari_calibration_run'], 'safari-process-tap-smooth-marker-44100', revision)
    calibration_file = verified_file(*cal, 'artifacts/effective-case.json')
    calibration = read(calibration_file)
    if calibration['sample_rate_hz'] != case['sample_rate_hz']:
        parser.error('登録したマーカーの校正レートが異なります')
    case['marker'] = calibration['marker']

    prior, sources = {}, []
    graph_path = None
    for run_id in spec['browser_comparison_runs']:
        browser = hydrate_run(run_id, drift['id'], revision)
        info = verified_file(*browser, 'summary.json')
        waveform = verified_file(*browser, 'artifacts/graph.f32le')
        if browser[1]['case_revision'] != drift['revision'] or not all(read(info)['checks'].values()):
            parser.error('ブラウザの合格した長い収録を指定してください')
        if run_id == spec['reference_browser_run']:
            graph_path = waveform
        prior[run_id] = {'events': {key: item['source_frame'] for key, item in read(info)['events'].items()},
                         'waveform_sha256': sha256(waveform)}
        sources.extend([browser[0] / 'manifest.json', info, waveform])
    if graph_path is None or {item['waveform_sha256'] for item in prior.values()} != {sha256(graph_path)}:
        parser.error('ブラウザ試行のPCMが共通であることを確認できません')
    reference = np.fromfile(graph_path, dtype='<f4')
    if len(reference) != drift['anchor']['last_exclusive']:
        parser.error('ブラウザのPCMは登録した採取範囲と一致しません')

    short = case['reference_waveform']
    short_folder = WORKSPACE / 'runs' / short['run']
    short_manifest = read(short_folder / 'manifest.json')
    short_pcm = verified_file(short_folder, short_manifest, 'artifacts/tap.f32le')
    calibration_review = hydrate_run(short['review'], response['id'], revision)
    reviewed = verified_file(*calibration_review, 'summary.json')
    baseline = read(reviewed)
    end_frame = short['start_frame'] + short['length_frames']
    if baseline['capture_run'] != short['run'] or not any(
            w['source_frames'] == [short['start_frame'], end_frame] and w['stationary'] for w in baseline['windows']):
        parser.error('位相の基準となる定常波形が一致しません')
    start = baseline['tap_anchor']['origin_in_pcm'] + short['start_frame']
    stereo = read_stereo(short_pcm)[start:start + short['length_frames']]
    expected = ((stereo[:, 0] - stereo[:, 1]) / 2).reshape(-1, short['period_frames']).mean(axis=0)

    sources.extend([CASE, *additional_inputs, DRIFT, RESPONSE, Path(__file__).resolve(), OUTPUT_DEVICE,
                    previous[0] / 'manifest.json', cal[0] / 'manifest.json', calibration_file,
                    short_folder / 'manifest.json', short_pcm, calibration_review[0] / 'manifest.json', reviewed,
                    *(WORKSPACE / 'tools' / name for name in (
                       'measure_cubeb_output_process_tap.py', 'measure_firefox_headphone_drift_44100.py',
                       'measure_firefox_headphone_response_44100.py', 'measure_worklet_live_song_process_tap.py',
                       'measure_safari_process_tap_calibration.py', 'measure_cubeb_output_callback.py',
                       'chimera-cubeb-output-probe.rs', 'chimera-cubeb-output-snapshot.patch', 'chimera_process_tap.swift',
                       'smooth_tap_marker.py'))])
    metadata = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision,
                'cubeb_revision': spec['cubeb_revision'], 'analysis_command': [sys.executable, *sys.argv], **hashes}
    if review:
        capture_run, = [item['capture_run'] for item in review['capture_reviews'] if item['review_run'] == args.run_id]
        saved_folder = WORKSPACE / 'runs' / capture_run
        manifest_path = saved_folder / 'manifest.json'
        saved = read(manifest_path)
        if (saved['run_id'] != capture_run or capture_run not in spec['trial_ids']
                or any(saved.get(key) != value for key, value in metadata.items() if key != 'analysis_command')):
            parser.error('元の収録のケースまたは記録ビルドと一致しません')
        summary = verified_file(saved_folder, saved, 'summary.json')
        paths = ['artifacts/fixture.f32le', 'artifacts/output-device.json', 'artifacts/native/capture.json',
                 'artifacts/native/probe.json', 'artifacts/native/tap.json', 'artifacts/native/tap.f32le']
        paths.extend(row['path'] for row in saved['outputs'] if row['path'].startswith('artifacts/native/cubeb-output-'))
        inputs = [verified_file(saved_folder, saved, name) for name in paths]
        if sha256(inputs[0]) != sha256(graph_path):
            parser.error('収録に使った試験信号と参照PCMが異なります')
        route, captured = read(inputs[1]), read(inputs[2])
        case['anchor'] |= review['anchor']

        def remeasure(out, execute):
            result = inspect_native(saved_folder / 'artifacts', case, calibration, route, captured,
                                    reference, expected, prior, snapshot_rate_validated=True)
            return {**result, 'registered_checks': read(summary)['checks'], 'capture_run': capture_run}

        metadata.update(case_revision=review['revision'], capture_run=capture_run)
        return record_measurement(args.output_run_id or args.run_id, registered,
                                  [*sources, manifest_path, summary, *inputs], metadata, remeasure,
                                  command=None, input_root=ROOT)
    return record_measurement(args.run_id, registered, sources, metadata, lambda out, execute:
                              measure(out, execute, case, calibration, binary, app, reference, expected, prior),
                              command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
