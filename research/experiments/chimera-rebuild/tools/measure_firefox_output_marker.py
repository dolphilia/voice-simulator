"""44.1 kHzのFirefoxでWorklet、cubeb、タップ、機器Writeを照合する。"""

import argparse
from collections import Counter
import csv
import json
from pathlib import Path
from statistics import median
import subprocess
import sys
from xml.etree import ElementTree

import numpy as np

from inspect_firefox_cubeb_output import host_tick_ms, inspect_pair
from measure_csd_envelope_timing import verified_file
from measure_cubeb_output_callback import load_blocks
from measure_safari_audio_client_trace import read_cycles
from measure_safari_process_tap_calibration import OUTPUT_DEVICE, capture_on_output
from measure_speech_timing import read
from measure_tsp_listening import hydrate_run
from measure_uniform_tube import record_measurement
from measure_worklet_fixed import ROOT, WEB
from measure_worklet_tsp_device_io import CLIENT, HARDWARE, SERVER, XCTRACE, capture_io, match_server, server_rows
from measure_worklet_tsp_device_tap import capture_tap, tap_frame
from smooth_tap_marker import fit_wave, marker_pcm, resolve_window
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/firefox-process-tap-cubeb-write-44100.json'
BROWSER = WEB / 'tools/capture-firefox-output-marker.mjs'


def export_trace(folder, execute):
    trace, toc = folder / 'audio-system.trace', folder / 'io-toc.xml'
    execute([*XCTRACE, 'export', '--input', str(trace), '--toc', '--output', str(toc)])
    present = {row.attrib['schema'] for row in ElementTree.parse(toc).findall('.//table')}
    files = {}
    for schema in (CLIENT, SERVER, HARDWARE):
        if schema in present:
            files[schema] = folder / (schema + '.xml')
            execute([*XCTRACE, 'export', '--input', str(trace),
                     '--xpath', f'/trace-toc/run/data/table[@schema="{schema}"]', '--output', str(files[schema])])
    return files


def check_worklet(folder, case, calibration):
    observed = read(folder / 'graph.json')
    quantum = case['quantum_frames']
    count = (case['anchor']['last_exclusive'] + quantum - 1) // quantum
    pcm = np.fromfile(folder / 'graph.f32le', dtype='<f4')
    reference = marker_pcm(count * quantum, calibration['marker'])
    if pcm.shape != reference.shape:
        return False
    nonzero = reference != 0
    frame = observed['startFrame']
    ready = read(folder / 'trace-ready.json')
    return (ready == {'trustedClick': True, 'sampleRate': case['sample_rate_hz']}
            and observed['inputFrames'] == [quantum] * count
            and observed['frames'] == list(range(frame, frame + count * quantum, quantum))
            and np.array_equal(pcm[nonzero].view('<u4'), reference[nonzero].view('<u4'))
            and bool(np.all(np.abs(pcm[~nonzero]) <= calibration['maximum_graph_zero_error'])))


def scan_cubeb(folder, case, calibration):
    first, end = (case['anchor'][key] for key in ('first', 'last_exclusive'))
    inspected, good = [], []
    for path in sorted((folder / 'cubeb').glob('cubeb-output-*')):
        blocks = load_blocks(path)
        pcm = np.fromfile(path / 'pcm.f32le', dtype='<f4').reshape(-1, 2)
        with (path / 'format.csv').open(newline='') as stream:
            formats, = csv.DictReader(stream)
        total = 0
        valid_offsets = True
        for block in blocks:
            valid_offsets &= total == block['pcm_byte_offset'] // 8 and block['frames'] > 0
            total += block['frames']
        match = resolve_window(pcm, calibration, first, end - 1,
                               allowance=case['anchor']['maximum_anchor_displacement_frames'], quiet_amplitude=1e-5)
        valid = (valid_offsets and total == len(pcm) and (path / 'state.txt').read_text().strip() == 'ready'
                 and set(map(float, formats.values())) == {case['sample_rate_hz']}
                 and match.get('continuous', False))
        inspected.append({'stream': path.name, 'formats': formats, 'frames': len(pcm), 'valid': valid,
                          'peak': float(np.max(np.abs(pcm), initial=0)),
                          'block_frame_counts': dict(Counter(row['frames'] for row in blocks)), 'marker': match})
        if valid:
            good.append((path, blocks, pcm, match))
    return inspected, good


def trace_candidates(tables, blocks, tape, cb_window, tap_window, cubeb_pcm, tap_pcm, delays, options, tick_ns, rate):
    if set(tables) != {CLIENT, SERVER, HARDWARE}:
        return []
    pid = tape['pid']
    client, _ = read_cycles(tables[CLIENT], pid, include_overloads=True)
    server = list(server_rows(tables[SERVER], SERVER, intervals=True))
    writes = list(server_rows(tables[HARDWARE], HARDWARE, intervals=True))
    picked = []
    for i, block in enumerate(blocks):
        start = block['pcm_byte_offset'] // 8
        size = block['frames']
        if (not cb_window[0] <= start <= cb_window[1] - size
                or block['timestamp_flags'] & 3 != 3 or block['stage'] != 'data'):
            continue
        candidates = match_server([block], server, pid, tick_ns, options['maximum_server_host_error_us'] / 1000)
        period_ns = size * 1e9 / rate
        choices = [(candidate['cycles'][0], write)
                   for candidate in candidates
                   for write in writes
                   if write['tid'] == candidate['tid'] and write['frames'] == size
                   and write['start_sample_time'] == candidate['cycles'][0]['output_sample_time']
                   and abs(write['start_ns'] - candidate['cycles'][0]['start_ns']) < period_ns]
        if len(choices) == 1:
            cycle, write = choices[0]
            origin = round(write['current_host_ticks'] * tick_ns) - write['start_ns']
            picked.append((i, block, cycle, write, origin))
    if not picked:
        return []
    origin = median(item[-1] for item in picked)
    frames_per_tick = tick_ns * rate / 1e9
    delay_frames = sum(delays) / 2 * rate / 1000
    result = []
    for i, block, cycle, write, write_origin in picked:
        size = block['frames']
        start = block['pcm_byte_offset'] // 8
        expected = tap_window[0] + start - cb_window[0]
        position = tap_frame(tape['blocks'], cycle['host_ticks'], delay_frames, frames_per_tick)
        offset = round(position)
        error = position - expected
        a, b = (round(block[key] * tick_ns) - origin for key in ('entered', 'returned'))
        matching = [row for row in client if row['start_ns'] <= a + 1000
                    and b <= row['start_ns'] + row['duration_ns'] + 1000]
        origin_delta = abs(write_origin - origin)
        if tap_window[0] <= offset <= tap_window[1] - size:
            actual = np.diff(tap_pcm[offset:offset + size].astype(float), axis=1).ravel()
            reference = np.diff(cubeb_pcm[start:start + size].astype(float), axis=1).ravel()
            residual, gain = fit_wave(actual, reference)
            result.append({'cubeb_index': i, 'cubeb_pcm_frame': start, 'frames': size,
                           'buffer_sample_time': block['sample_time'],
                           'cubeb_host_ticks': block['host_time'], 'server_host_ticks': cycle['host_ticks'],
                           'server_sample_time': cycle['output_sample_time'], 'write_start_ns': write['start_ns'],
                           'engine_id': write['engine_id'], 'stream_index': write['stream_index'],
                           'tap_pcm_frame': offset, 'tap_position_error_frames': error,
                           'clock_origin_delta_ns': origin_delta, 'matching_audio_client': len(matching),
                           'relative_pcm_residual': residual, 'pcm_gain': gain})
    return result


def longest_joint(rows, rules, trace):
    longest = count = 0
    previous = None
    for row in rows:
        row['matched'] = (row['matching_audio_client'] == 1
                          and abs(row['tap_position_error_frames']) <= rules['maximum_write_position_error_frames']
                          and row['clock_origin_delta_ns'] <= trace['maximum_server_host_error_us'] * 1000
                          and row['relative_pcm_residual'] <= rules['maximum_relative_residual']
                          and row['pcm_gain'] > 0)
        if not row['matched']:
            count, previous = 0, None
            continue
        same_stream = previous is not None and all(row[key] == previous[key] for key in ('engine_id', 'stream_index'))
        adjacent = same_stream and row['cubeb_index'] == previous['cubeb_index'] + 1 and all(
            row[key] == previous[key] + previous['frames'] for key in
            ('buffer_sample_time', 'server_sample_time', 'tap_pcm_frame'))
        count = count + 1 if adjacent else 1
        longest = max(longest, count)
        previous = row
    return longest


def analyze(folder, case, calibration, route, tables):
    report = {'output_route': route, 'trace_tables': list(tables)}
    graph = read(folder / 'graph.json')
    report['worklet_frames'] = {'scheduled': graph['scheduledFrame'], 'first_observed': graph['startFrame'],
                                'start_delay': graph['startFrame'] - graph['scheduledFrame']}
    checks = report['checks'] = {
        'graph_marker': check_worklet(folder, case, calibration),
        'original_output_restored': route['before']['defaultOutput'] == route['after']['defaultOutput'],
    }
    info = read(folder / 'browser.json')['output']
    device, = [row for row in info['devices'] if row['id'] == info['defaultOutput']]
    rate = case['sample_rate_hz']
    checks['headphone_during_capture'] = (device['uid'], device['sampleRate']) == (case['output_device']['uid'], rate)
    report['device'] = device
    observed, good = scan_cubeb(folder, case, calibration)
    report['cubeb_streams'] = observed
    checks['unique_cubeb_stream'] = len(good) == 1
    if len(good) != 1:
        return report
    path, blocks, pcm, marker = good[0]
    stream = str(path.relative_to(folder))
    first, end = (case['anchor'][key] for key in ('first', 'last_exclusive'))
    core = {'valid': True, 'graph_marker_window': [first, end], 'matched_streams': [stream],
            'streams': {stream: {'pcm': marker}}, 'host_tick_ms': host_tick_ms()}
    settings = {'smooth_alignment': calibration, 'sample_rate_hz': rate,
                'maximum_anchor_displacement_frames': case['anchor']['maximum_anchor_displacement_frames'],
                'quiet_marker_amplitude': 1e-5}
    pair = inspect_pair(folder, core, calibration['marker'], settings)
    report['tap'] = pair
    checks['unique_tap_window'] = pair['valid'] and pair['pcm']['continuous'] and not pair['tap_sample_clock_jumps']
    if not checks['unique_tap_window']:
        return report
    delta = pair['host_time_offset_change_ms'] * rate / 1000
    checks['stable_pcm_clock_alignment'] = abs(delta) <= case['anchor']['maximum_endpoint_change_frames']
    tape = read(folder / 'tap.json')
    tap_pcm = np.fromfile(folder / 'tap.f32le', dtype='<f4').reshape(-1, 2)
    widths = dict(sorted(Counter(block['frames'] for block in tape['blocks']).items()))
    report['tap_block_frame_counts'] = widths
    rows = trace_candidates(tables, blocks, tape, marker['tap_window'], pair['pcm']['tap_window'], pcm, tap_pcm,
                            pair['tap_minus_cubeb_host_time_at_window_ends_ms'], case['trace'],
                            core['host_tick_ms'] * 1e6, rate)
    report['joint_writes'] = rows
    count = longest_joint(rows, case['anchor'], case['trace'])
    report['longest_joint_writes'] = count
    checks['registered_joint_writes'] = count >= case['trace']['minimum_joint_writes']
    expected = case.get('width_prediction', dict.fromkeys(('device', 'tap', 'cubeb', 'write'),
                                                         case['output_device']['expected_frames']))
    measured = {'device': {device['bufferFrames']}, 'tap': set(widths), 'cubeb': {row['frames'] for row in blocks},
                'write': {row['frames'] for row in rows}}
    report['prediction_widths'] = {name: values == {expected[name]} for name, values in measured.items()}
    return report


def measure(folder, execute, case, calibration, binary, app):
    probe = folder / 'coreaudio-output-device'
    execute(['xcrun', 'swiftc', '-O', '-framework', 'CoreAudio', str(OUTPUT_DEVICE), '-o', str(probe)])
    effective = folder / 'effective-case.json'
    effective.write_text(json.dumps(case | {'marker': calibration['marker']}, ensure_ascii=False, indent=2) + '\n')
    cubeb = folder / 'cubeb'
    cubeb.mkdir()
    capture = capture_tap(capture_io(execute, folder, case['trace']), folder, case['capture'], app)
    command = ['env', f'CHIMERA_FIREFOX={binary}', f'CHIMERA_CUBEB_OUTPUT_DIR={cubeb}',
               f"CHIMERA_CUBEB_OUTPUT_BLOCKS={case['snapshot_blocks']}", 'node', str(BROWSER),
               str(effective), str(folder), str(probe)]
    route = capture_on_output(case, folder, probe, lambda: capture(
        command, cwd=WEB, stdout=folder / 'browser-command.log'))
    return analyze(folder, case, calibration, route, export_trace(folder, execute))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('firefox', type=Path)
    parser.add_argument('app', type=Path)
    parser.add_argument('--case', type=Path, default=CASE)
    parser.add_argument('--from-run', help='採取済みのマニフェストと生データを検証して再解析する')
    args = parser.parse_args()
    path = args.case.resolve()
    case = read(path)
    case_sources = [path]
    if 'base_case' in case:
        if case['base_case'] != CASE.name:
            parser.error('指定された観測の基準ケースに対応していません')
        case_sources.append(CASE)
        case = read(CASE) | case
    revision = case['upstream_revision']
    if (subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip() != revision
            or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True)):
        parser.error('変更のない固定上流が必要です')
    binary, app = args.firefox.resolve(strict=True), args.app.resolve(strict=True)
    xul = binary.with_name('XUL')
    reference, meta = hydrate_run(case['safari_calibration_run'], case['safari_calibration_case'], revision)
    calibration_path = verified_file(reference, meta, 'artifacts/effective-case.json')
    summary_path = verified_file(reference, meta, 'summary.json')
    calibration = read(calibration_path)
    native_tap = {'tap_binary_sha256': sha256(app / 'Contents/MacOS/chimera-process-tap'),
                  'tap_info_sha256': sha256(app / 'Contents/Info.plist')}
    summary = read(summary_path)
    if (case['sample_rate_hz'] != calibration['sample_rate_hz'] or not all(summary['checks'].values())
            or any(meta[k] != v for k, v in native_tap.items())
            or summary['output_measurement']['device']['uid'] != case['output_device']['uid']):
        parser.error('Safariで校正した採取器、出力機器、周波数の組が必要です')
    prior = WORKSPACE / 'runs' / case['firefox_reference_run'] / 'manifest.json'
    old = read(prior)
    firefox = {'firefox_binary_sha256': sha256(binary), 'firefox_xul_sha256': sha256(xul)}
    if (old['upstream_revision'] != revision or firefox['firefox_xul_sha256'] == old['firefox_xul_sha256']):
        parser.error('44.1 kHz用の計測器を組み込んだFirefoxを指定してください')
    subprocess.run(['/usr/bin/codesign', '--verify', str(app)], check=True)
    sources = [Path(__file__).resolve(), OUTPUT_DEVICE, BROWSER, BROWSER.with_name('shared-context-marker.mjs'),
               BROWSER.with_name('shared-context-marker-worklet.js'), prior, reference / 'manifest.json',
               summary_path, calibration_path, *case_sources,
               *(WORKSPACE / 'tools' / name for name in (
                   'chimera-cubeb-output-snapshot.patch', 'chimera_process_tap.swift',
                   'inspect_firefox_cubeb_output.py', 'measure_worklet_tsp_device_io.py',
                   'measure_worklet_tsp_device_tap.py', 'measure_safari_process_tap_calibration.py',
                   'measure_worklet_live_song_process_tap.py', 'capture_worklet_system_pair.py',
                   'smooth_tap_marker.py', 'measure_cubeb_output_callback.py', 'measure_safari_audio_client_trace.py',
                   'measure_uniform_tube.py'))]
    details = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision,
               'analysis_command': [sys.executable, *sys.argv], 'firefox_binary': str(binary),
               **firefox, **native_tap}
    if args.from_run:
        capture = WORKSPACE / 'runs' / args.from_run
        manifest_path = capture / 'manifest.json'
        saved = read(manifest_path)
        identity = {'run_id': args.from_run, 'case_id': case['id'], 'case_revision': case['revision'],
                    'upstream_revision': revision, **firefox, **native_tap}
        if any(saved.get(key) != value for key, value in identity.items()):
            parser.error('保存済みの収録と実行環境またはケースが異なります')
        effective = read(verified_file(capture, saved, 'artifacts/effective-case.json'))
        if effective != case | {'marker': calibration['marker']}:
            parser.error('保存済みの試験信号とケースが異なります')
        names = ('effective-case.json', 'graph.f32le', 'graph.json', 'trace-ready.json', 'browser.json',
                 'output-device.json', 'tap.json', 'tap.f32le', *(schema + '.xml' for schema in (CLIENT, SERVER, HARDWARE)))
        rows = [row['path'] for row in saved['outputs']]
        required = list('artifacts/' + name for name in names)
        snapshots = [name for name in rows if name.startswith('artifacts/cubeb/')]
        sources.extend([manifest_path, *(verified_file(capture, saved, name) for name in required + snapshots)])
        folder = capture / 'artifacts'
        tables = {schema: folder / (schema + '.xml') for schema in (CLIENT, SERVER, HARDWARE)}
        details['capture_run'] = args.from_run
        return record_measurement(args.run_id, path, sources, details, lambda out, execute: analyze(
            folder, case, calibration, read(folder / 'output-device.json'), tables), command=None, input_root=ROOT)
    return record_measurement(args.run_id, path, sources, details, lambda out, execute: measure(
        out, execute, case, calibration, binary, app), command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
