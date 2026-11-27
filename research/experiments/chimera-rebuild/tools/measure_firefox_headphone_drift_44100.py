"""長い44.1 kHz連続音でタップの帯域と低域位相が変化する位置を記録する。"""

import argparse
import csv
from pathlib import Path
import subprocess
import sys

import numpy as np

from inspect_firefox_cubeb_output import host_tick_ms
from measure_csd_envelope_timing import verified_file
from measure_cubeb_output_callback import load_blocks
from measure_firefox_headphone_response_44100 import (
    BROWSER, CASE as BASE, OUTPUT_DEVICE, anchors, collect, continuous_blocks, fit_tones, fixture, read_stereo,
)
from measure_speech_timing import read
from measure_tsp_listening import hydrate_run
from measure_uniform_tube import record_measurement
from measure_worklet_fixed import ROOT
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/firefox-process-tap-headphone-drift-44100.json'


def first_sustained(mask, count):
    runs = np.convolve(np.asarray(mask, dtype=int), np.ones(count, dtype=int), 'valid')
    positions = np.flatnonzero(runs == count)
    return int(positions[0]) if len(positions) else None


def clock_boundary(rows, offset, sample, host, position, origin, rate):
    if position is None:
        return None
    n = position + origin
    preceding = next(((i, row) for i, row in enumerate(rows)
                      if row[offset] <= n < row[offset] + row['frames']), None)
    if preceding is None:
        return None
    i, a = preceding
    following = rows[i + 1] if i + 1 < len(rows) else None

    def report(row, idx):
        return {'block_index': idx, 'source_frame': row[offset] - origin, 'frames': row['frames'],
                'sample_time': row[sample], 'host_ticks': row[host]}

    return {'containing': report(a, i), 'following': report(following, i + 1) if following else None,
            'frames_after_block_start': n - a[offset],
            'event_host_ns_from_block': a[host] * host_tick_ms() * 1e6 + (n - a[offset]) * 1e9 / rate}


def compare(cubeb, tap, expected_period, case, clock):
    opts = case['analysis']
    first = opts['first_frames'][0]
    stop = opts['last_exclusive']
    width = opts['window_frames']
    hop = opts['hop_frames']
    rate = case['sample_rate_hz']
    hz = case['tone_probe']['frequencies_hz']
    pilot = hz.index(opts['reference_tone_hz'])
    high = hz.index(opts['band_tone_hz'])
    w = np.asarray(hz) * 2 * np.pi / rate
    basis = np.exp(1j * np.arange(width)[:, None] * w)
    starts = np.arange(first, stop - width + 1, hop)
    estimates = []
    rows = []
    for start in starts:
        a, error_a = fit_tones(cubeb[start:start + width], basis)
        b, error_b = fit_tones(tap[start:start + width], basis)
        if np.any(abs(a) < case['tone_probe']['amplitude'] / 4):
            raise ValueError(f'cubebの周波数成分が不足しています ({start})')
        ratio = b / a
        estimates.append(ratio)
        rows.append({'source_frames': [int(start), int(start) + width], 'cubeb_residual': error_a,
                     'tap_residual': error_b})
    transfer = np.asarray(estimates)
    delay = np.unwrap(np.angle(transfer[:, pilot])) / w[pilot]
    slope = np.diff(delay) * 1e6 / hop
    amplitude = np.abs(transfer)
    for k, row in enumerate(rows):
        row.update(pilot_offset_frames=float(delay[k]), pilot_slope_from_previous_ppm=float(slope[k-1]) if k else None,
                   frequencies=[{'hz': f, 'amplitude_ratio': float(a), 'raw_phase_degrees': float(p)}
                                for f, a, p in zip(hz, amplitude[k], np.angle(transfer[k], deg=True), strict=True)])
    count = opts['minimum_consecutive_windows']
    low = first_sustained(amplitude[:, high] < opts['reduced_band_upper_limit'], count)
    phase = first_sustained(np.abs(slope) > opts['phase_slope_threshold_ppm'], count)
    low_center = int(starts[low] + width // 2) if low is not None else None
    phase_center = int(starts[phase + 1] + width // 2) if phase is not None else None
    period = case['reference_waveform']['period_frames']
    x = np.arange(first, stop)
    expected = expected_period[(x - case['reference_waveform']['start_frame']) % period]
    differences = np.abs(tap[first:stop] - expected)
    differences_over_limit = differences > opts['repeat_motion_absolute_limit']
    repeated = np.convolve(np.asarray(differences_over_limit, dtype=int),
                           np.ones(opts['repeat_motion_check_frames'], dtype=int), 'valid')
    edges = np.flatnonzero(differences_over_limit[:len(repeated)] & (repeated >= opts['repeat_motion_minimum_count']))
    first_difference = int(first + edges[0]) if len(edges) else None
    results = {}
    for tag, pos in (('waveform_departure', first_difference), ('band_drop', low_center), ('pilot_drift', phase_center)):
        results[tag] = {'source_frame': pos,
                        'cubeb': clock_boundary(clock['cubeb'], 'pcm_frame', 'sample_time', 'host_time', pos,
                                                clock['cb_origin'], rate),
                        'tap': clock_boundary(clock['tap'], 'offset', 'sampleTime', 'hostTime', pos,
                                               clock['tb_origin'], rate)}
    begin, end = opts['stable_band']
    in_band = (begin <= amplitude[:, high]) & (amplitude[:, high] <= end)
    return {'checks': {'initial_band_matches_prior': bool(np.all(in_band[:count])),
                       'cubeb_tone_fits': all(row['cubeb_residual'] <= opts['maximum_tone_residual'] for row in rows)},
            'predictions': {'band_drop_seen': low is not None, 'pilot_drift_seen': phase is not None,
                            'change_within_tap_block': (abs(low_center - phase_center) <= opts['tap_expected_frames']
                                                       if low_center is not None and phase_center is not None else None)},
            'events': results, 'windows': rows}


def analyze(folder, case, cal, route, expected_period):
    graph = read(folder / 'graph.json')
    ready = read(folder / 'trace-ready.json')
    played = np.fromfile(folder / 'graph.f32le', dtype='<f4')
    opts = case['analysis']
    first, last = (case['anchor'][key] for key in ('first', 'last_exclusive'))
    quantum = case['quantum_frames']
    device, = [d for d in route['selected']['devices'] if d['id'] == route['selected']['defaultOutput']]
    checks = {
        'graph_and_rate': bool(
            ready == {'sampleRate': case['sample_rate_hz'], 'trustedClick': True}
            and graph['scheduledFrame'] == graph['startFrame'] and len(played) == last
            and graph['frames'] == list(range(graph['startFrame'], graph['startFrame'] + last, quantum))
            and graph['inputFrames'] == [quantum] * (last // quantum)
            and np.max(np.abs(played - fixture(case, last))) <= opts['maximum_graph_absolute_difference']),
        'registered_output_device': device['uid'] == case['output_device']['uid']
                                    and device['sampleRate'] == case['sample_rate_hz']
                                    and device['bufferFrames'] == case['output_device']['expected_frames'],
        'original_output_restored': route['after']['defaultOutput'] == route['before']['defaultOutput'],
    }
    return analyze_pcm(folder, folder / 'cubeb', case, cal, expected_period, checks)


def analyze_pcm(folder, cubeb_folder, case, cal, expected_period, checks, *, reference_pcm=None,
                snapshot_rate_validated=False):
    opts = case['analysis']
    first, last = (case['anchor'][key] for key in ('first', 'last_exclusive'))
    tape = read(folder / 'tap.json')
    tap = read_stereo(folder / 'tap.f32le')
    trailing = case.get('trailing_anchor_search_frames')
    tb = anchors(tap, cal, case['anchor'], trailing_search_frames=trailing)
    result = {'checks': checks, 'tap_anchor': tb, 'tap_pid': tape['pid'], 'cubeb_candidates': []}
    checks['tap_front_and_trailing_anchors'] = tb is not None
    if tb is None:
        return result
    origin = tb['origin_in_pcm']
    tb_rows = continuous_blocks(tape['blocks'], 'offset', 'sampleTime', origin + first, origin + last,
                                opts['tap_expected_frames'], len(tap))
    checks['tap_clock_and_format'] = bool(
        tb_rows and tape['sampleRate'] == case['sample_rate_hz'] and not tape['overflow'] and not tape['formatErrors']
        and tape['frames'] == len(tap) and all(row.get('hostTime') is not None for row in tb_rows)
        and all(b['hostTime'] > a['hostTime'] for a, b in zip(tb_rows, tb_rows[1:]))
        and np.isclose(tape['timebaseNumer'] / tape['timebaseDenom'] / 1e6, host_tick_ms(), rtol=1e-12, atol=0))
    matches = []
    for path in sorted(cubeb_folder.glob(f"cubeb-output-{tape['pid']}-*")):
        pcm = read_stereo(path / 'pcm.f32le')
        cb = anchors(pcm, cal, case['anchor'], trailing_search_frames=trailing)
        rows = load_blocks(path)
        result['cubeb_candidates'].append({'name': path.name, 'anchor': cb,
                                          'block_widths': sorted({row['frames'] for row in rows})})
        if cb is None or cb['integer_advance'] != 0:
            continue
        format_path = path / 'format.csv'
        if format_path.is_file():
            with format_path.open(newline='') as stream:
                formats, = csv.DictReader(stream)
            rates_match = set(map(float, formats.values())) == {case['sample_rate_hz']}
        else:
            rates_match = snapshot_rate_validated
            result['cubeb_format_basis'] = 'snapshot_rate_and_sample_format_guard' if rates_match else 'missing'
        for row in rows:
            row['pcm_frame'] = row['pcm_byte_offset'] // 8
        lo = cb['origin_in_pcm']
        cb_rows = continuous_blocks(rows, 'pcm_frame', 'sample_time', lo + first, lo + last,
                                    opts['cubeb_expected_frames'], len(pcm))
        if (cb_rows and rates_match
                and (path / 'state.txt').read_text().strip() == 'ready'
                and all(row['stage'] == 'data' and row['timestamp_flags'] & 3 == 3 for row in cb_rows)
                and all(b['host_time'] > a['host_time'] for a, b in zip(cb_rows, cb_rows[1:]))):
            matches.append((pcm, cb, rows, len(cb_rows), path.name))
    checks['continuous_cubeb_clock'] = len(matches) == 1
    if not matches or not checks['continuous_cubeb_clock'] or not checks['tap_clock_and_format']:
        return result
    pcm, cb, cb_rows, cb_count, name = matches[0]
    if reference_pcm is not None:
        start = cb['origin_in_pcm']
        samples = pcm[start:start + len(reference_pcm)]
        checks['cubeb_matches_reference_pcm'] = (len(samples) == len(reference_pcm)
            and np.array_equal(samples[:, 0], reference_pcm) and np.array_equal(samples[:, 1], -reference_pcm))
    clock = {'cubeb': cb_rows, 'tap': tape['blocks'], 'cb_origin': cb['origin_in_pcm'], 'tb_origin': origin}
    graph_side = (pcm[:, 0] - pcm[:, 1]) / 2
    tap_side = (tap[:, 0] - tap[:, 1]) / 2
    data = compare(graph_side[cb['origin_in_pcm']:], tap_side[origin:], expected_period, case, clock)
    checks.update(data.pop('checks'))
    result.update(cubeb_anchor=cb, cubeb_stream=name, cubeb_blocks_in_window=cb_count,
                  tap_blocks_in_window=len(tb_rows), **data)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('firefox', type=Path)
    parser.add_argument('app', type=Path)
    args = parser.parse_args()
    spec, base = read(CASE), read(BASE)
    case = base | spec
    for key in ('anchor', 'tone_probe', 'analysis'):
        case[key] = base[key] | spec[key]
    revision = case['upstream_revision']
    if spec['base_case'] != BASE.name or args.run_id not in case['trial_ids']:
        parser.error('登録されたケースと試行IDを指定してください')
    if (subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip() != revision
            or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True)):
        parser.error('変更のない固定上流が必要です')
    cal = hydrate_run(case['safari_calibration_run'], 'safari-process-tap-smooth-marker-44100', revision)
    calibration_path = verified_file(*cal, 'artifacts/effective-case.json')
    calibration = read(calibration_path)
    case['marker'] = calibration['marker']
    if (calibration['sample_rate_hz'] != case['sample_rate_hz']
            or case['anchor']['last_exclusive'] > case['marker']['chips'] * case['marker']['frames_per_chip']
            or case['play_seconds'] * case['sample_rate_hz'] < case['anchor']['last_exclusive']):
        parser.error('校正レートまたは試験音の長さが収録条件に対応しません')
    binary, app = args.firefox.resolve(strict=True), args.app.resolve(strict=True)
    hashes = {'firefox_binary_sha256': sha256(binary), 'firefox_xul_sha256': sha256(binary.with_name('XUL')),
              'tap_binary_sha256': sha256(app / 'Contents/MacOS/chimera-process-tap'),
              'tap_info_sha256': sha256(app / 'Contents/Info.plist')}
    reference = case['reference_waveform']
    previous = WORKSPACE / 'runs' / reference['run']
    before = read(previous / 'manifest.json')
    if before['upstream_revision'] != revision or any(before[key] != value for key, value in hashes.items()):
        parser.error('比較元と同じFirefoxおよびプロセスタップを指定してください')
    subprocess.run(['/usr/bin/codesign', '--verify', str(app)], check=True)
    review = hydrate_run(reference['review'], base['id'], revision)
    report_path = verified_file(*review, 'summary.json')
    report = read(report_path)
    reference_end = reference['start_frame'] + reference['length_frames']
    if report['capture_run'] != reference['run'] or not any(
            w['source_frames'] == [reference['start_frame'], reference_end] and w['stationary'] for w in report['windows']):
        parser.error('比較元のPCMに検証済みの定常窓がありません')
    raw_path = verified_file(previous, before, 'artifacts/tap.f32le')
    stereo = read_stereo(raw_path)
    offset = report['tap_anchor']['origin_in_pcm'] + reference['start_frame']
    samples = stereo[offset:offset + reference['length_frames']]
    expected_period = ((samples[:, 0] - samples[:, 1]) / 2).reshape(-1, reference['period_frames']).mean(axis=0)
    sources = [CASE, BASE, Path(__file__).resolve(), WORKSPACE / 'tools/measure_firefox_headphone_response_44100.py', BROWSER,
               BROWSER.with_name('shared-context-marker.mjs'), BROWSER.with_name('shared-context-marker-worklet.js'),
               OUTPUT_DEVICE, cal[0] / 'manifest.json', calibration_path, previous / 'manifest.json',
               raw_path, review[0] / 'manifest.json', report_path,
               *(WORKSPACE / 'tools' / name for name in ('measure_worklet_live_song_process_tap.py',
                 'measure_worklet_tsp_device_tap.py', 'measure_safari_process_tap_calibration.py',
                 'measure_cubeb_output_callback.py', 'chimera-cubeb-output-snapshot.patch',
                 'chimera_process_tap.swift', 'smooth_tap_marker.py'))]
    details = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision,
               'analysis_command': [sys.executable, *sys.argv], **hashes}

    def measure(folder, execute):
        route = collect(folder, execute, case, binary, app)
        return analyze(folder, case, calibration, route, expected_period)

    return record_measurement(args.run_id, CASE, sources, details, measure, command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
