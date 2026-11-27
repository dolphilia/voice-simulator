"""同じ診断PCMのCore Audio直接出力とプロセスタップを比較する。"""

import argparse
from pathlib import Path
import subprocess
import sys
import time

import numpy as np

from inspect_firefox_cubeb_output import host_tick_ms
from measure_coreaudio_output_error_pcm import capture, SOURCE
from measure_csd_envelope_timing import verified_file
from measure_firefox_headphone_drift_44100 import CASE as DRIFT, compare, first_sustained
from measure_firefox_headphone_response_44100 import (
    CASE as RESPONSE, OUTPUT_DEVICE, anchors, continuous_blocks, read_stereo,
)
from measure_safari_process_tap_calibration import capture_on_output, output_snapshot
from measure_speech_timing import read
from measure_tsp_listening import hydrate_run
from measure_uniform_tube import record_measurement
from measure_worklet_fixed import ROOT, UPSTREAM, WORKSPACE
from upstream_baseline import sha256


CASE = WORKSPACE / 'cases/coreaudio-headphone-drift-44100.json'
REVIEW = WORKSPACE / 'cases/coreaudio-headphone-drift-44100-raw-review.json'
NATIVE = 'native-cubeb-headphone-drift-44100'


def inspect(folder, case, calibration, route, recorded, reference, period):
    original, tape = (read(folder / name) for name in ('native.json', 'tap.json'))
    pcm, tap = (read_stereo(folder / name) for name in ('native.f32le', 'tap.f32le'))
    active = recorded['during_playback']
    device, = [row for row in active['devices'] if row['id'] == active['defaultOutput']]
    output = case['output_device']
    capture_spec, analysis = case['capture_direct'], case['analysis']
    compare_tap_start = case.get('compare_tap_start', False)
    leading = case.get('leading_frames', 0)
    first, last = (case['anchor'][key] for key in ('first', 'last_exclusive'))
    direct_marks = [{'pcm_frame': mark['markerOffset'], 'sample_time': mark.get('sampleTime'),
                     'host_time': mark.get('hostTime'), 'frames': mark['frames']}
                    for mark in original['frameMarks']]
    direct_first = 0 if 'leading_frames' in case else first
    direct_last = last + leading
    widths = sorted({row['frames'] for row in direct_marks if row['pcm_frame'] < direct_last
                     and row['pcm_frame'] + row['frames'] > direct_first})
    direct_rows = continuous_blocks(direct_marks, 'pcm_frame', 'sample_time', direct_first, direct_last,
                                    widths[0], len(pcm)) if len(widths) == 1 else None
    signal = np.pad(reference, (leading, 0))
    expected = np.column_stack((signal, -signal)).astype('<f4').tobytes()
    with (folder / 'native.f32le').open('rb') as stream:
        captured = stream.read(len(expected))
    checks = {
        'capture_completed': recorded['tap_started'] and recorded['output_exit_code'] == recorded['tap_exit_code'] == 0,
        'same_output_and_rate': (device['uid'], device['sampleRate']) == (output['uid'], case['sample_rate_hz']),
        'original_output_restored': route['after']['defaultOutput'] == route['before']['defaultOutput'],
        'tap_used_direct_pid': recorded['output_pid'] == original['pid'] == tape['pid'],
        'direct_is_unmodified_control': (original['delayMs'] == 0 and not original['invalidBuffers']
            and len(direct_marks) <= capture_spec['event_callback']
            and all(mark.get('status') == 0 for mark in original['frameMarks'])),
        'direct_pcm_matches_browser': captured == expected,
        'direct_format': original['sampleRate'] == case['sample_rate_hz'],
    }
    result = {'checks': checks, 'active_output_device': device, 'direct_callback_widths': widths}
    result['width_prediction_met'] = widths == [capture_spec['observed_output_expected_frames']]
    if 'leading_frames' in case:
        checks['registered_output_width'] = (
            device['bufferFrames'] == output['expected_frames'] and result['width_prediction_met'])
        result['leading_frames'] = leading
    search = case['trailing_anchor_search_frames']
    da, ta = (anchors(samples, calibration, case['anchor'], trailing_search_frames=search)
              for samples in (pcm, tap))
    result.update(direct_anchor=da, tap_anchor=ta)
    checks['direct_front_and_trailing_anchors'] = bool(
        da and da['origin_in_pcm'] == leading and da['integer_advance'] == 0)
    checks['tap_front_and_trailing_anchors'] = ta is not None
    tap_rows = None
    if ta is not None:
        origin = ta['origin_in_pcm']
        tap_rows = continuous_blocks(tape['blocks'], 'offset', 'sampleTime', origin + first, origin + last,
                                    analysis['tap_expected_frames'], len(tap))
    checks['tap_format'] = (tape['sampleRate'] == case['sample_rate_hz'] and tape['frames'] == len(tap)
                            and not tape['overflow'] and not tape['formatErrors'])
    for label, rows, evidence, key in (('direct', direct_rows, original, 'host_time'),
                                       ('tap', tap_rows, tape, 'hostTime')):
        checks[f'{label}_clock'] = bool(rows and all(row.get(key) is not None for row in rows)
            and all(b[key] > a[key] for a, b in zip(rows, rows[1:]))
            and np.isclose(evidence['timebaseNumer'] / evidence['timebaseDenom'] / 1e6,
                           host_tick_ms(), rtol=1e-12, atol=0))
        result[f'{label}_blocks_in_window'] = len(rows) if rows else 0
    if compare_tap_start:
        tap_start = tape['blocks'][0].get('hostTime') if tape['blocks'] else None
        direct_start = direct_marks[0]['host_time'] if direct_marks else None
        result['tap_lead_seconds'] = capture_spec['tap_lead_seconds']
        checks['valid_start_host_timestamps'] = (
            tap_start is not None and direct_start is not None and tap_start < direct_start)
        if checks['valid_start_host_timestamps']:
            result['first_host_ticks'] = {'tap': tap_start, 'direct': direct_start}
            result['start_host_gap_ms'] = (direct_start - tap_start) * host_tick_ms()
    if not all(checks.values()):
        return result
    direct_side = (pcm[:, 0] - pcm[:, 1]) / 2
    tap_side = (tap[:, 0] - tap[:, 1]) / 2
    clock = {'cubeb': direct_marks, 'tap': tape['blocks'], 'cb_origin': leading, 'tb_origin': origin}
    data = compare(direct_side[leading:], tap_side[origin:], period, case, clock)
    verification = data.pop('checks')
    checks['direct_tone_fits'] = verification['cubeb_tone_fits']
    data['predictions']['initial_band_matches_prior'] = verification['initial_band_matches_prior']
    for event in data['events'].values():
        event['direct'] = event.pop('cubeb')
        if 'leading_frames' in case:
            source_frame = event['source_frame']
            event['output_frame'] = source_frame + leading if source_frame is not None else None
            direct_event = event['direct']
            event['ms_from_first_output_timestamp'] = (
                direct_event['event_host_ns_from_block'] / 1e6 - direct_marks[0]['host_time'] * host_tick_ms()
                if direct_event else None)
        if compare_tap_start:
            observed = event['tap']
            event['ms_from_first_tap_timestamp'] = (
                (observed['containing']['host_ticks'] - tap_start) * host_tick_ms()
                + observed['frames_after_block_start'] * 1e3 / case['sample_rate_hz'] if observed else None)
    for window in data['windows']:
        window['direct_residual'] = window.pop('cubeb_residual')
    slopes = [row['pilot_slope_from_previous_ppm'] for row in data['windows'][1:]]
    positive = first_sustained(np.asarray(slopes) > analysis['phase_slope_threshold_ppm'],
                              analysis['minimum_consecutive_windows'])
    center = (sum(data['windows'][positive + 1]['source_frames']) // 2 if positive is not None else None)
    drop = data['events']['band_drop']['source_frame']
    data['predictions'].update(positive_pilot_first_center=center, positive_change_within_tap_block=(
        abs(drop - center) <= analysis['tap_expected_frames'] if drop is not None and center is not None else None))
    return {**result, **data}


def measure(folder, execute, case, calibration, app, fixture, reference, period, prior):
    binary, device = (folder / name for name in ('direct-output', 'coreaudio-output-device'))
    execute(['xcrun', 'swiftc', '-O', '-framework', 'AudioToolbox', str(SOURCE), '-o', str(binary)])
    execute(['xcrun', 'swiftc', '-O', '-framework', 'CoreAudio', str(OUTPUT_DEVICE), '-o', str(device)])
    local_fixture = folder / 'fixture.f32le'
    attach = case.get('attach_comparison')
    analyze = inspect
    if attach:
        from measure_coreaudio_headphone_late_attach_44100 import extended_fixture, inspect_attach

        reference = extended_fixture(reference, attach, calibration, case.get('silence_comparison'))
        local_fixture.write_bytes(reference.tobytes())
        analyze = inspect_attach
        if 'restart_comparison' in case:
            from measure_coreaudio_headphone_restart_44100 import inspect_restart

            analyze = inspect_restart
    else:
        local_fixture.write_bytes(bytes(4 * case.get('leading_frames', 0)) + fixture.read_bytes())
    path = folder / 'native'
    path.mkdir()
    capture_spec = case['capture_direct'] | {'sample_rate_hz': case['sample_rate_hz']}
    recorded = {}

    def snapshot():
        time.sleep(capture_spec['device_snapshot_seconds_after_release'])
        return output_snapshot(device)

    def acquire():
        recorded.update(capture(path, binary, local_fixture, capture_spec, False, app, None,
                                during_playback=snapshot))

    route = capture_on_output(case, folder, device, acquire)
    return {**analyze(path, case, calibration, route, recorded, reference, period),
            'native_cubeb_comparisons': prior, 'direct_audio_unit': capture_spec['audio_unit_subtype']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('app', type=Path, nargs='?')
    parser.add_argument('--case', type=Path, default=CASE, help='直接出力の条件を比較する収録ケース')
    parser.add_argument('--review', action='store_true', help='登録済みの生PCMを再解析する')
    args = parser.parse_args()
    spec, drift, response = (read(path) for path in (CASE, DRIFT, RESPONSE))
    registered = args.case.resolve()
    variant = read(registered) if registered != CASE else None
    review_spec = read(REVIEW) if args.review else None
    trial_ids = review_spec['trials'] if args.review else spec['trial_ids']
    if variant is not None:
        matches = [trial for trial in variant['trials'] if trial['run_id'] == args.run_id]
        if args.review or variant['capture_base'] != CASE.name or len(matches) != 1:
            parser.error('基準ケースに対応する比較の登録済み試行を指定してください')
        trial = matches[0]
        leading = trial['leading_frames']
        capture_spec = spec['capture_direct']
        available_frames = capture_spec['native_seconds'] * response['sample_rate_hz'] - drift['anchor']['last_exclusive']
        if type(leading) is not int or not 0 <= leading < available_frames:
            parser.error('試験信号全体が採取時間に収まる無音長を指定してください')
        if 'tap_lead_seconds' in trial:
            wait = trial['tap_lead_seconds']
            available_seconds = capture_spec['tap_seconds'] - capture_spec['native_seconds']
            if type(wait) not in (int, float) or not 0 <= wait < available_seconds:
                parser.error('試験信号全体がタップ採取時間に収まる待機を指定してください')
    if (variant is None and args.run_id not in trial_ids) or spec['base_case'] != DRIFT.name:
        parser.error('登録した直接出力の試行IDを指定してください')
    if args.review and (args.app or review_spec['base_case'] != CASE.name or review_spec['id'] != spec['id']):
        parser.error('登録済み収録の再解析には採取アプリを指定できません')
    if not args.review and args.app is None:
        parser.error('採取アプリを指定してください')
    case = response | drift | spec
    attach_reference = None
    silence_reference = None
    for key in ('anchor', 'analysis', 'tone_probe'):
        case[key] = response[key] | drift[key] | spec.get(key, {})
    if variant is not None:
        case.update(id=variant['id'], revision=variant['revision'], leading_frames=leading)
        if 'tap_lead_seconds' in trial:
            case.update(compare_tap_start=True, capture_direct=capture_spec | {'tap_lead_seconds': wait})
        attachment = variant
        if 'attach_reference_case' in variant:
            attach_reference = registered.with_name(variant['attach_reference_case'])
            attachment = read(attach_reference)
            if attachment['capture_base'] != CASE.name or 'attach_comparison' not in attachment:
                parser.error('後付けタップの基準ケースが一致しません')
        if 'attach_comparison' in attachment:
            attach = attachment['attach_comparison']
            duration = attach['native_seconds']
            delay = trial.get('tap_attach_after_release_seconds')
            limit = 12 if 'recurrence' in attachment else 3
            tap_duration = attach.get('tap_seconds', case['capture_direct']['tap_seconds'])
            if (not 0.5 <= duration <= limit or not duration < tap_duration <= 30 or leading
                    or (delay is not None and not 0 < delay < duration)):
                parser.error('後から接続するタップの待機または出力時間が不正です')
            options = case['capture_direct'] | {'native_seconds': duration, 'tap_seconds': tap_duration}
            if delay is not None:
                options['tap_attach_after_release_seconds'] = delay
            case.update(attach_comparison=attach, capture_direct=options)
            silence = variant.get('silence_comparison')
            apply_silence = trial.get('apply_silence')
            restart_case = variant.get('restart_comparison')
            if restart_case is not None:
                silence_reference = registered.with_name(variant['silence_reference_case'])
                registered_silence = read(silence_reference)
                if registered_silence['attach_reference_case'] != attach_reference.name:
                    parser.error('途中停止と無音対照の基準ケースが一致しません')
                silence = registered_silence['silence_comparison']
                apply_silence = True
                stop_frame, resume_frame, pause_frames = (restart_case[key] for key in
                    ('stop_after_source_frame', 'resume_source_frame', 'pause_frames_at_nominal_rate'))
                if (stop_frame, resume_frame, pause_frames) != (
                        silence['start_frame'], silence['end_frame'], silence['end_frame'] - silence['start_frame']):
                    parser.error('途中停止の位置または待機時間が無音の対照条件と一致しません')
                options['restart'] = {'stopAfterFrame': stop_frame, 'resumeSourceFrame': resume_frame,
                                      'pauseSeconds': pause_frames / case['sample_rate_hz']}
                case['restart_comparison'] = restart_case
            if silence is not None:
                begin, end, ramp = (silence[key] for key in ('start_frame', 'end_frame', 'ramp_frames'))
                if (type(apply_silence) is not bool or delay is not None
                        or not 2 <= ramp < silence['quiet_margin_frames'] < (end - begin) / 2
                        or not 0 < silence['pre_last_exclusive'] < begin < end < silence['post_first_frame']
                        < attach['analysis_end_frame'] - drift['analysis']['window_frames']):
                    parser.error('無音区間と前後の観測条件が不正です')
                case['silence_comparison'] = silence | {'enabled': apply_silence}
    revision = case['upstream_revision']
    if (subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip() != revision
            or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True)):
        parser.error('変更のない固定上流が必要です')
    browser = hydrate_run(spec['reference_browser_run'], drift['id'], revision)
    fixture = verified_file(*browser, 'artifacts/graph.f32le')
    if sha256(fixture) != spec['reference_pcm_sha256'] or fixture.stat().st_size != 4 * drift['anchor']['last_exclusive']:
        parser.error('登録したPCMの長さまたはハッシュが異なります')
    reference = np.fromfile(fixture, dtype='<f4')
    cal = hydrate_run(case['safari_calibration_run'], 'safari-process-tap-smooth-marker-44100', revision)
    cal_file = verified_file(*cal, 'artifacts/effective-case.json')
    calibration = read(cal_file)
    if calibration['sample_rate_hz'] != case['sample_rate_hz']:
        parser.error('マーカーの校正と直接出力のレートが異なります')
    short = case['reference_waveform']
    short_path = WORKSPACE / 'runs' / short['run']
    short_manifest = short_path / 'manifest.json'
    short_pcm = verified_file(short_path, read(short_manifest), 'artifacts/tap.f32le')
    review = hydrate_run(short['review'], response['id'], revision)
    review_file = verified_file(*review, 'summary.json')
    reviewed = read(review_file)
    if reviewed['capture_run'] != short['run']:
        parser.error('40標本周期に使うPCMが校正結果と一致しません')
    start = reviewed['tap_anchor']['origin_in_pcm'] + short['start_frame']
    stereo = read_stereo(short_pcm)[start:start + short['length_frames']]
    period = ((stereo[:, 0] - stereo[:, 1]) / 2).reshape(-1, short['period_frames']).mean(axis=0)

    tap_build = hydrate_run('cubeb-output-callback-process-tap-20261122-repeat',
                            'cubeb-output-callback-process-tap', revision)
    hashes = {key: tap_build[1][key] for key in ('tap_binary_sha256', 'tap_info_sha256')}

    sources = [CASE, DRIFT, RESPONSE, SOURCE, OUTPUT_DEVICE, Path(__file__).resolve(),
               browser[0] / 'manifest.json', fixture, cal[0] / 'manifest.json', cal_file,
               short_manifest, short_pcm, review[0] / 'manifest.json', review_file, tap_build[0] / 'manifest.json']
    if variant is not None:
        sources.append(registered)
    if attach_reference is not None:
        sources.append(attach_reference)
    if silence_reference is not None:
        sources.append(silence_reference)
        sources.append(Path(__file__).with_name('measure_coreaudio_headphone_restart_44100.py'))
    if 'attach_comparison' in case:
        sources.append(Path(__file__).with_name('measure_coreaudio_headphone_late_attach_44100.py'))
    sources.extend(Path(__file__).with_name(name) for name in ('measure_coreaudio_output_error_pcm.py',
        'measure_firefox_headphone_drift_44100.py', 'measure_firefox_headphone_response_44100.py',
        'measure_safari_process_tap_calibration.py', 'measure_worklet_live_song_process_tap.py',
        'chimera_process_tap.swift', 'smooth_tap_marker.py'))
    prior = {}
    for name in spec['native_comparison_runs']:
        native = hydrate_run(name, NATIVE, revision)
        summary = verified_file(*native, 'summary.json')
        result = read(summary)
        prior[name] = {key: item['source_frame'] for key, item in result['events'].items()}
        sources.extend([native[0] / 'manifest.json', summary])
    metadata = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision,
                'analysis_command': [sys.executable, *sys.argv], **hashes}
    if args.review:
        original = review_spec['trials'][args.run_id]
        saved = WORKSPACE / 'runs' / original
        saved_manifest = saved / 'manifest.json'
        manifest = read(saved_manifest)
        if (original not in spec['trial_ids'] or manifest['run_id'] != original or any(
                manifest[key] != value for key, value in metadata.items() if key != 'analysis_command')):
            parser.error('登録した元の収録と一致しません')
        summary, route, capture_report, saved_fixture, *raw = [
            verified_file(saved, manifest, name) for name in ('summary.json', 'artifacts/output-device.json',
                'artifacts/native/capture.json', 'artifacts/fixture.f32le', 'artifacts/native/native.json',
                'artifacts/native/native.f32le', 'artifacts/native/tap.json', 'artifacts/native/tap.f32le')]
        if sha256(saved_fixture) != sha256(fixture):
            parser.error('保存した試験信号と参照PCMが異なります')

        def remeasure(folder, execute):
            return {**inspect(raw[0].parent, case, calibration, read(route), read(capture_report), reference, period),
                    'native_cubeb_comparisons': prior, 'direct_audio_unit': case['capture_direct']['audio_unit_subtype'],
                    'original_capture': original, 'original_checks': read(summary)['checks']}

        metadata.update(case_revision=review_spec['revision'], original_capture=original, swift=manifest['swift'])
        return record_measurement(args.run_id, REVIEW, [*sources, REVIEW, saved_manifest, summary, route,
            capture_report, saved_fixture, *raw], metadata, remeasure, command=None, input_root=ROOT)
    app = args.app.resolve(strict=True)
    if (sha256(app / 'Contents/MacOS/chimera-process-tap') != hashes['tap_binary_sha256']
            or sha256(app / 'Contents/Info.plist') != hashes['tap_info_sha256']):
        parser.error('先行比較と同じ採取アプリを指定してください')
    subprocess.run(['/usr/bin/codesign', '--verify', str(app)], check=True)
    metadata['swift'] = subprocess.check_output(['xcrun', 'swiftc', '--version'], text=True).strip()
    return record_measurement(args.run_id, registered, sources, metadata,
        lambda folder, execute: measure(folder, execute, case, calibration, app, fixture, reference, period, prior),
        command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
