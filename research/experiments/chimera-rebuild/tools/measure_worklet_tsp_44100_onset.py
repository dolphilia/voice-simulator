"""確認用07の44.1 kHz発話開始をcubebとヘッドフォンのWriteへ対応付ける。"""

import argparse
from collections import Counter
import json
from pathlib import Path
import subprocess
import sys
from xml.etree import ElementTree

import numpy as np

from inspect_firefox_cubeb_output import host_tick_ms, inspect_pair
from measure_csd_envelope_timing import verified_file
from measure_firefox_output_marker import HARDWARE, export_trace, scan_cubeb, trace_candidates
from measure_safari_process_tap_calibration import OUTPUT_DEVICE, capture_on_output
from measure_speech_timing import read
from measure_tsp_listening import hydrate_run
from measure_uniform_tube import record_measurement
from measure_worklet_fixed import CAPTURE, ROOT, WEB, web_sources
from measure_worklet_live_tsp_rate import same_states, wave
from measure_worklet_live_tsp_source_defaults import CASE as BROWSER_CASE
from measure_worklet_tsp_device_io import capture_io, server_rows
from measure_worklet_tsp_device_tap import capture_tap
from smooth_tap_marker import chip_values, find_anchor, fit_wave, marker_pcm
from upstream_baseline import WORKSPACE, sha256


CASE = WORKSPACE / 'cases/worklet-live-tsp-44100-headphone-onset.json'


def first_rms(pcm, threshold, length):
    squares = np.r_[0.0, np.cumsum(pcm.astype(float)**2)]
    window = (squares[length:] - squares[:-length]) / length
    hits = np.flatnonzero(window >= threshold**2)
    return int(hits[0]) if hits.size else None


def marker_window(folder, case, calibration, context_onset, trim):
    marker = read(folder / 'marker.json')
    pcm = np.fromfile(folder / 'marker.f32le', dtype='<f4')
    quantum = case['marker']['quantum']
    frames = marker['frames']
    expected = marker_pcm(len(pcm), calibration['marker'])
    nonzero = expected != 0
    checks = {
        'marker_rate_and_frames': (marker['sampleRate'] == case['output_device']['sample_rate_hz']
            and len(pcm) == len(frames) * quantum and len(frames) == case['marker']['capture_quanta']
            and np.array_equal(frames, frames[0] + np.arange(len(frames)) * quantum)),
        'marker_pcm': (np.array_equal(pcm[nonzero], expected[nonzero])
                       and bool(np.all(np.abs(pcm[~nonzero]) <= calibration['maximum_graph_zero_error'])))
    }
    options = case['comparison']
    onset = context_onset - frames[0]
    first = onset - options['pre_onset_frames'] + trim
    end = onset + options['post_onset_frames']
    checks['marker_spans_onset'] = 0 <= first < onset < end <= len(pcm)
    return checks, {'first': first, 'last_exclusive': end, 'maximum_anchor_displacement_frames': 1024}, frames[0]


def headphone_write_times(path, uid):
    uid = uid + ' '
    doc = ElementTree.parse(path)
    values = {node.get('id'): node.text for node in doc.iter('tid') if node.get('id')}
    tids = {int(tid.text or values[tid.get('ref')]) for thread in doc.iter('thread')
            if uid in thread.get('fmt', '') and (tid := thread.find('tid')) is not None}
    return {(row['start_ns'], row['start_sample_time']) for row in server_rows(path, HARDWARE, intervals=True)
            if row['tid'] in tids}


def speech_compare(pcm, reference, rules, speech_in_window):
    mono = pcm.astype(float).mean(axis=1)
    threshold, length = rules['threshold_pcm'], rules['threshold_smoothing_frames']
    residual, gain = fit_wave(mono, reference)
    expected = first_rms(reference, threshold, length)
    actual = first_rms(mono, threshold, length)
    valid = (gain > 0 and residual <= rules['maximum_speech_relative_residual']
             and expected is not None and actual is not None
             and abs(actual - expected) <= rules['measurable_onset_tolerance_frames'])
    return valid, {'relative_residual': residual, 'gain': gain,
                   'measured_onset_frame': actual + speech_in_window if actual is not None else None,
                   'reference_onset_frame': expected + speech_in_window if expected is not None else None,
                   'measured_onset_in_pcm_window': actual}


def analyze(folder, case, calibration, baseline, pristine, route, tables, *, trim=0):
    rule = case['comparison']
    rate = case['output_device']['sample_rate_hz']
    length = len(baseline)
    live = wave(folder / 'browser.wav', rate, length)
    observed = read(folder / 'browser.json')
    actual_case = read(folder / 'browser-case.json')
    replay = read(folder / 'speech-case.json')
    speech_start = observed['realtime']['scheduledContextFrame']
    technical = int(np.flatnonzero(baseline)[0])
    onset = speech_start + technical
    graph_checks, anchor, marker_start = marker_window(folder, case, calibration, onset, trim)
    checks = graph_checks | {
        'canonical_speech_pcm_and_states': (live.tobytes() == baseline.tobytes() and same_states(observed, pristine)
            and actual_case == replay and all(observed[key] == pristine[key] for key in ('speech', 'gestures'))),
        'original_output_restored': route['before']['defaultOutput'] == route['after']['defaultOutput'],
    }
    report = {'checks': checks, 'output_route': route, 'trace_tables': list(tables),
              'speech_start_context_frame': speech_start, 'first_nonzero_speech_frame': technical,
              'first_nonzero_context_frame': onset, 'marker_start_context_frame': marker_start,
              'graph_window': [anchor['first'], anchor['last_exclusive']], 'trimmed_leading_anchor_frames': trim}
    if not checks['marker_spans_onset']:
        return report
    capture_case = {'sample_rate_hz': rate, 'anchor': anchor}
    streams, good = scan_cubeb(folder, capture_case, calibration)
    report['cubeb_streams'] = streams
    checks['unique_cubeb_marker'] = len(good) == 1
    if len(good) != 1:
        return report
    path, blocks, cubeb, match = good[0]
    layout = str(path.relative_to(folder))
    tick = host_tick_ms()
    core = {'valid': True, 'matched_streams': [layout], 'graph_marker_window': report['graph_window'],
            'streams': {layout: {'pcm': match}}, 'host_tick_ms': tick}
    settings = {'smooth_alignment': calibration, 'sample_rate_hz': rate,
                'maximum_anchor_displacement_frames': anchor['maximum_anchor_displacement_frames'],
                'quiet_marker_amplitude': 1e-5}
    pair = inspect_pair(folder, core, calibration['marker'], settings)
    report['tap'] = pair
    checks['tap_marker_and_sample_clock'] = pair['valid'] and pair['pcm']['continuous'] and not pair['tap_sample_clock_jumps']
    if not checks['tap_marker_and_sample_clock']:
        return report

    tape = read(folder / 'tap.json')
    tap = np.fromfile(folder / 'tap.f32le', dtype='<f4').reshape(-1, 2)
    cw, tw = match['tap_window'], pair['pcm']['tap_window']
    speech_offset = technical - rule['pre_onset_frames'] + trim
    graph_start = marker_start + anchor['first']
    window_frames = np.arange(graph_start - speech_start, graph_start - speech_start + cw[1] - cw[0])
    reference = np.zeros(len(window_frames))
    within = (window_frames >= 0) & (window_frames < length)
    reference[within] = baseline[window_frames[within]]
    for name, data in (('cubeb', cubeb[slice(*cw)]), ('tap', tap[slice(*tw)])):
        checks[name + '_speech_onset'], report[name + '_speech'] = speech_compare(data, reference, rule, speech_offset)
    delta = tap[slice(*tw)].astype(float).mean(axis=1) - cubeb[slice(*cw)].astype(float).mean(axis=1)
    detectable = np.flatnonzero(np.abs(delta) > 1e-6)
    report['first_cubeb_to_tap_speech_difference_over_1e_6'] = (
        int(detectable[0]) + speech_offset if detectable.size else None)

    picks = trace_candidates(tables, blocks, tape, cw, tw, cubeb, tap,
                             pair['tap_minus_cubeb_host_time_at_window_ends_ms'],
                             case['trace'], tick * 1e6, rate)
    origins = {row['server_sample_time'] - row['cubeb_pcm_frame'] for row in picks}
    head_writes = headphone_write_times(tables[HARDWARE], case['output_device']['uid']) if HARDWARE in tables else set()
    clips = [(data[:, 0].astype(float) - data[:, 1]) / 2 for data in (cubeb, tap)]
    rows = []
    if len(origins) == 1:
        dev_origin, = origins
        for row in picks:
            raw = row['cubeb_pcm_frame']
            pos = row['server_sample_time'] - dev_origin + tw[0] - cw[0]
            size = row['frames']
            residual, _ = fit_wave(clips[1][pos:pos + size], clips[0][raw:raw + size])
            rows.append(row | {'tap_sample_clock_pcm_frame': pos,
                               'tap_sample_clock_marker_residual': residual,
                               'is_headphone': (row['write_start_ns'], row['server_sample_time']) in head_writes})
    chips = chip_values(calibration['marker'])
    anchors = []
    for frame in range(anchor['first'] + rule['verification_stride_frames'],
                       anchor['last_exclusive'] - calibration['window_frames'], rule['verification_stride_frames']):
        matches = [find_anchor(clip, chips, calibration, frame) for clip in clips]
        error = None
        if all(matches):
            left, right = matches
            error = (right['offset'] - right['fraction'] - left['offset'] + left['fraction'] - (tw[0] - cw[0]))
        anchors.append({'marker_frame': frame, 'position_error_frames': error, 'matches': matches})
    checks['interior_markers_match_sample_clock'] = bool(anchors) and all(
        row['position_error_frames'] is not None
        and abs(row['position_error_frames']) <= rule['maximum_anchor_position_error_frames'] for row in anchors)
    report['verification_anchors'] = anchors
    report['joint_writes'] = rows
    report['device_request_frame_counts'] = dict(Counter(row['frames'] for row in blocks
                                                        if cw[0] <= row['pcm_byte_offset'] // 8 < cw[1]))
    report['tap_block_frame_counts'] = dict(Counter(block['frames'] for block in tape['blocks']))
    checks['registered_widths'] = (set(report['device_request_frame_counts']) == {rule['expected_device_request_frames']}
                                   and set(report['tap_block_frame_counts']) == {rule['expected_tap_block_frames']})
    positions = {
        'technical': technical - speech_offset,
        'measurable_cubeb': report['cubeb_speech']['measured_onset_in_pcm_window'],
        'measurable_tap': report['tap_speech']['measured_onset_in_pcm_window'],
    }
    onset_rows = {}
    for label, frame in positions.items():
        onset_rows[label] = [row for row in rows if frame is not None and row['is_headphone']
                            and row['matching_audio_client'] == 1
                            and row['tap_sample_clock_marker_residual'] <= rule['maximum_marker_relative_residual']
                            and row['cubeb_pcm_frame'] <= cw[0] + frame < row['cubeb_pcm_frame'] + row['frames']]
    report['onset_device_writes'] = onset_rows
    checks['technical_and_measurable_onsets_map_to_writes'] = all(len(matches) == 1 for matches in onset_rows.values())
    return report


def measure(out, execute, case, calibration, input_path, baseline, reference, firefox, app, *, analyzer=analyze):
    probe = out / 'coreaudio-output-device'
    execute(['xcrun', 'swiftc', '-O', '-framework', 'CoreAudio', str(OUTPUT_DEVICE), '-o', str(probe)])
    inputs = out / 'speech-case.json'
    inputs.write_bytes(input_path.read_bytes())
    settings = case['marker'] | {'smooth_marker': calibration['marker'], 'stereo_difference': True,
        'trace_before_playback': True, 'tap_prime_sample_rate_hz': case['output_device']['sample_rate_hz'],
        'maximum_graph_zero_error': calibration['maximum_graph_zero_error'], 'defer_close_until_marker': True}
    if 'load' in case:
        settings['in_phase_marker'] = case['load']['in_phase_marker']
    marker_path = out / 'marker-settings.json'
    marker_path.write_text(json.dumps(settings, ensure_ascii=False, indent=2) + '\n')
    cubeb = out / 'cubeb'
    cubeb.mkdir()
    recorder = capture_tap(capture_io(execute, out, case['trace']), out, case['capture'], app)
    command = ['env', f'CHIMERA_FIREFOX={firefox}', f'CHIMERA_CUBEB_OUTPUT_DIR={cubeb}',
               f"CHIMERA_CUBEB_OUTPUT_BLOCKS={case['snapshot_blocks']}", 'node', str(CAPTURE), str(out),
               str(BROWSER_CASE), str(inputs), 'firefox', '--native-clock', f'--speech-marker={marker_path}']
    if 'load' in case:
        command.append(f"--speech-preparation=split-onset-load-{case['load']['final_frames']}")
        if case['load'].get('delay_one_quantum'):
            command.append('--speech-delay-one-quantum')
    route = capture_on_output(case, out, probe, lambda: recorder(command, cwd=WEB, stdout=out / 'browser-command.log'))
    return analyzer(out, case, calibration, baseline, reference, route, export_trace(out, execute))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('firefox', type=Path)
    parser.add_argument('tap', type=Path)
    parser.add_argument('--case', type=Path, default=CASE)
    parser.add_argument('--from-run', help='同じ収録ケースの生データとマニフェストを照合して再解析する')
    parser.add_argument('--trim-leading-anchor-frames', type=int, default=0,
                        help='収録済みのタップ前端が照合できない場合に比較窓の前端を短くする')
    args = parser.parse_args()
    case_path = args.case.resolve()
    case = read(case_path)
    case_inputs = [case_path]
    if 'base_case' in case:
        if case['base_case'] != CASE.name:
            parser.error('指定された発話開始の基準ケースに対応していません')
        case = read(CASE) | case
        case_inputs.append(CASE)
    revision = case['upstream_revision']
    firefox, app = args.firefox.resolve(strict=True), args.tap.resolve(strict=True)
    run = hydrate_run(case['baseline_run'], case['baseline_case'], revision)
    prior = WORKSPACE / 'runs' / case['calibration_run']
    prior_meta = read(prior / 'manifest.json')
    reviewed, review_meta = hydrate_run(case['sample_clock_review_run'], 'firefox-process-tap-sample-clock-44100', revision)
    if (prior_meta['run_id'], prior_meta['case_id'], prior_meta['upstream_revision'], review_meta['capture_run']) != (
            case['calibration_run'], case['calibration_case'], revision, case['calibration_run']):
        parser.error('採取条件とサンプル番号の校正実行が一致しません')
    reference, meta = hydrate_run(case['safari_calibration_run'], case['safari_calibration_case'], revision)
    digests = {'firefox_binary_sha256': sha256(firefox), 'firefox_xul_sha256': sha256(firefox.with_name('XUL'))}
    tap_bin = sha256(app / 'Contents/MacOS/chimera-process-tap')
    if any(prior_meta[key] != value or run[1][key] != value for key, value in digests.items()) or (
            tap_bin != meta['tap_binary_sha256'] or tap_bin != prior_meta['tap_binary_sha256']):
        parser.error('校正と通常発話で使ったFirefoxおよびタップのバイナリが必要です')
    prior_summary = verified_file(prior, prior_meta, 'summary.json')
    if not all(read(prior_summary)['prediction_widths'].values()):
        parser.error('校正で確認した機器とタップの幅が必要です')
    calibration_path = verified_file(reference, meta, 'artifacts/effective-case.json')
    calibration = read(calibration_path)
    calibration['marker'] = calibration['marker'] | {'chips': case['marker']['chips']}
    input_path, speech_wave, speech_json = (verified_file(*run, 'artifacts/' + name) for name in
                                           ('browser-case.json', 'browser.wav', 'browser.json'))
    spec = read(speech_json)
    baseline = wave(speech_wave, case['output_device']['sample_rate_hz'], spec['outputFrames'])
    subprocess.run(['/usr/bin/codesign', '--verify', str(app)], check=True)
    inputs = [*case_inputs, BROWSER_CASE, Path(__file__).resolve(), OUTPUT_DEVICE, input_path, speech_wave, speech_json,
              calibration_path, prior_summary, prior / 'manifest.json', reference / 'manifest.json',
              reviewed / 'manifest.json', verified_file(reviewed, review_meta, 'summary.json'),
              run[0] / 'manifest.json', *web_sources(), *(WORKSPACE / 'tools' / name for name in (
                  'measure_worklet_live_tsp_rate.py', 'measure_firefox_output_marker.py', 'measure_worklet_tsp_device_tap.py',
                  'measure_worklet_tsp_device_io.py', 'measure_safari_process_tap_calibration.py', 'smooth_tap_marker.py',
                  'inspect_firefox_cubeb_output.py', 'measure_worklet_live_song_process_tap.py',
                  'capture_worklet_system_pair.py', 'measure_cubeb_output_callback.py', 'measure_uniform_tube.py'))]
    details = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision,
               'analysis_command': [sys.executable, *sys.argv], **digests, 'tap_binary_sha256': tap_bin}
    trim = args.trim_leading_anchor_frames
    if not 0 <= trim < case['comparison']['pre_onset_frames'] or trim % case['comparison']['expected_device_request_frames']:
        parser.error('短縮幅は開始点を含む範囲内の機器要求の整数倍を指定してください')
    if trim and not args.from_run:
        parser.error('前端を短縮した照合には収録済みの実行を指定してください')
    if args.from_run:
        previous = WORKSPACE / 'runs' / args.from_run
        saved = read(previous / 'manifest.json')
        identity = {'run_id': args.from_run, 'case_id': case['id'], 'case_revision': case['revision'],
                    'upstream_revision': revision, 'tap_binary_sha256': tap_bin, **digests}
        if any(saved.get(key) != value for key, value in identity.items()):
            parser.error('収録の識別子、ケース、またはバイナリが一致しません')
        verified = {row['path']: verified_file(previous, saved, row['path']) for row in saved['outputs']}
        if read(verified['artifacts/speech-case.json']) != read(input_path):
            parser.error('収録した発話ケースと通常発話の基準が一致しません')
        prior_summary = read(verified['summary.json'])
        if trim and prior_summary.get('tap', {}).get('pcm', {}).get('reason') != 'smooth_anchor_not_unique':
            parser.error('前端が一意に照合できなかった収録を指定してください')
        tables = {schema: verified[f'artifacts/{schema}.xml'] for schema in prior_summary['trace_tables']}
        details['capture_run'] = args.from_run
        inputs.extend((previous / 'manifest.json', *verified.values()))
        return record_measurement(args.run_id, case_path, inputs, details, lambda out, execute: analyze(
            previous / 'artifacts', case, calibration, baseline, spec, prior_summary['output_route'],
            tables, trim=trim), command=None, input_root=ROOT)
    return record_measurement(args.run_id, case_path, inputs, details, lambda out, execute: measure(
        out, execute, case, calibration, input_path, baseline, spec, firefox, app), command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
