"""44.1 kHzで発話直前の破棄描画と機器要求の予定時刻を測る。"""

import argparse
from collections import defaultdict
from pathlib import Path
from statistics import median
import subprocess
import sys

import numpy as np

from inspect_firefox_cubeb_output import host_tick_ms, inspect_pair
from measure_csd_envelope_timing import verified_file
from measure_firefox_output_marker import CLIENT, HARDWARE, SERVER, scan_cubeb
from measure_speech_timing import read
from measure_tsp_listening import hydrate_run
from measure_uniform_tube import record_measurement
from measure_worklet_fixed import ROOT, web_sources
from measure_worklet_tsp_44100_onset import CASE as ONSET_CASE, headphone_write_times, marker_window, measure
from measure_worklet_live_tsp_rate import same_states, wave
from measure_worklet_tsp_device_io import match_server, read_cycles, server_rows
from measure_worklet_tsp_io_deadline import server_window
from measure_worklet_tsp_tap_gap_repetition import compare_component, fit
from smooth_tap_marker import chip_values, waveform
from upstream_baseline import WORKSPACE, sha256


CASE = WORKSPACE / 'cases/worklet-live-tsp-44100-headphone-load.json'


def request_info(blocks, index, tick_ns, rate):
    current, following = blocks[index:index + 2]
    size = current['frames']
    skip = following['sample_time'] - current['sample_time'] - size
    if not np.isfinite(skip) or skip != round(skip):
        raise ValueError('機器要求の予定サンプル番号から整数フレームの間隔を取れません')
    return {'cubeb_index': index, 'cubeb_pcm_frame': current['pcm_byte_offset'] // 8,
            'sample_time': current['sample_time'], 'request_frames': size,
            'callback_ns': (current['returned'] - current['entered']) * tick_ns,
            'budget_ns': size * 1e9 / rate, 'gap_frames': int(skip)}


def device_requests(tables, blocks, tape, targets, uid, tolerance_us, rate, tick_ns):
    if set(tables) != {CLIENT, SERVER, HARDWARE}:
        return {}
    pid = tape['pid']
    client, _ = read_cycles(tables[CLIENT], pid, include_overloads=True)
    server = list(server_rows(tables[SERVER], SERVER, intervals=True))
    headphone = headphone_write_times(tables[HARDWARE], uid)
    hardware = [row for row in server_rows(tables[HARDWARE], HARDWARE, intervals=True)
                if (row['start_ns'], row['start_sample_time']) in headphone]
    cycles_by_tid, writes_by_tid = defaultdict(lambda: defaultdict(list)), defaultdict(lambda: defaultdict(list))
    for row in server:
        if row['client_pid'] in (None, str(pid)):
            cycles_by_tid[row['tid']][row['output_sample_time']].append(row)
    for row in hardware:
        writes_by_tid[row['tid']][row['start_sample_time']].append(row)

    evidence = {}
    for index in sorted(targets):
        pair = blocks[index:index + 2]
        width = pair[0]['frames']
        period = width * 1e9 / rate
        candidates = []
        for match in match_server(pair, server, pid, tick_ns, tolerance_us / 1000):
            thread = match['tid']
            try:
                candidates.append(server_window(*match['cycles'], cycles_by_tid[thread], writes_by_tid[thread],
                                                 period, width, tick_ns, tolerance_us * 1000))
            except ValueError:
                # 同じ予定ホスト時刻を使う別の出力先には対応するヘッドフォンWriteがない。
                continue
        if len(candidates) != 1:
            evidence[index] = {'missing': '音声サーバーとヘッドフォンWriteを一意に照合できません',
                               'candidate_count': len(candidates)}
            continue
        window, = candidates
        origin = median(round(w['current_host_ticks'] * tick_ns) - w['start_ns'] for _, w in window)
        cb = pair[0]
        begin, end = (round(cb[key] * tick_ns) - origin for key in ('entered', 'returned'))
        client_rows = [row for row in client if row['start_ns'] <= begin + 1000
                       and end <= row['start_ns'] + row['duration_ns'] + 1000]
        per_write = [{'device_sample_time': cycle['output_sample_time'],
                      'scheduled_host_ticks': cycle['host_ticks'], 'write_start_ns': write['start_ns'],
                      'frames': write['frames']} for cycle, write in window]
        evidence[index] = {'writes': per_write, 'audio_client_matches': len(client_rows),
                           'audio_client_duration_ns': client_rows[0]['duration_ns'] if len(client_rows) == 1 else None}
    return evidence


def observed_window(folder, case, calibration, graph_window):
    rate = case['output_device']['sample_rate_hz']
    observed, viable = scan_cubeb(folder, {'sample_rate_hz': rate, 'anchor': graph_window}, calibration)
    if len(viable) != 1:
        return observed, None, {'valid': False, 'reason': 'cubebの連続マーカー窓を一意に照合できません'}
    path, _, _, match = viable[0]
    stream = str(path.relative_to(folder))
    anchor = [graph_window[key] for key in ('first', 'last_exclusive')]
    core = {'valid': True, 'matched_streams': [stream], 'graph_marker_window': anchor, 'host_tick_ms': host_tick_ms(),
            'streams': {stream: {'pcm': match}}}
    settings = {'smooth_alignment': calibration, 'sample_rate_hz': rate, 'quiet_marker_amplitude': 1e-5,
                'maximum_anchor_displacement_frames': graph_window['maximum_anchor_displacement_frames']}
    return observed, viable[0], inspect_pair(folder, core, calibration['marker'], settings)


def compare_gaps(gaps, raw, captured, windows, case, marker_first, references):
    limits = case['gap_comparison']
    channels = [(a.mean(axis=1), (a[:, 0] - a[:, 1]) / 2) for a in (raw, captured)]
    n = case['comparison']['expected_device_request_frames']
    code = case['load']['in_phase_marker']
    chips = chip_values(code)
    off = 0
    for j, gap in enumerate(gaps):
        first = gap['cubeb_pcm_frame'] - windows[0][0]
        following = first + n
        stop = gaps[j + 1]['cubeb_pcm_frame'] - windows[0][0] if j + 1 < len(gaps) else len(raw)
        previous = gaps[j - 1]['cubeb_pcm_frame'] - windows[0][0] + n if j else 0
        a, b = max(previous, first - limits['flank_frames']), min(stop, following + limits['flank_frames'])
        extra = gap['gap_frames']
        if (extra == n and 0 <= a <= first - n < following + n <= b
                and b + off + extra <= len(captured)):
            for name, col in (('in_phase', 0), ('out_of_phase', 1)):
                gap[name] = compare_component(channels[0][col], channels[1][col], a, b, first, following, off, limits)
            expected = waveform(chips, code, marker_first + np.arange(first, following) + references['cubeb_fraction'])
            gap['in_phase']['reference_fit'] = fit(channels[0][0][first:following], expected)
            gap['selected_both'] = (gap['out_of_phase']['selected']
                                    if gap['out_of_phase']['selected'] == gap['in_phase']['selected'] else None)
            gap['tap_pcm_at_gap'] = windows[1][0] + first + off
            gap['tap_pcm_at_next_period'] = gap['tap_pcm_at_gap'] + n
            timed = gap.get('writes', [])
            if len(timed) == 3:
                gap['missing_period_device_sample_time'] = timed[1]['device_sample_time']
                gap['tap_pcm_written_period'] = (gap['tap_pcm_at_gap'] + timed[1]['device_sample_time']
                                                 - timed[0]['device_sample_time'])
            window = captured[first + off:following + off + n]
            gap['fully_zero_frames'] = int(np.count_nonzero(np.all(window == 0, axis=1)))
        else:
            gap['model_missing'] = '1要求分の飛びと局所比較に必要な前後のPCMがそろいません'
        off += extra


def analyze(folder, case, calibration, baseline, pristine, route, tables, *, trim=0):
    rule = case['comparison']
    rate = case['output_device']['sample_rate_hz']
    observed = read(folder / 'browser.json')
    load = case['load']
    live = wave(folder / 'browser.wav', rate, len(baseline))
    live_clock = observed['realtime']
    speech_start = live_clock['scheduledContextFrame']
    prep = observed.get('renderPreparationTrace', [])
    q = case['marker']['quantum']
    expected = [{'contextFrame': live_clock['armedContextFrame'] + offset * q, 'preparedFrames': frames}
                for offset, frames in zip(load['lead_offsets'], [
                    load['first_draw_frames'] * i for i in (1, 2, 3)
                ] + [3 * load['first_draw_frames'] + load['final_frames']], strict=True)]
    window_case = case | {'comparison': rule | {'pre_onset_frames': load['preparation_window_before_frames'],
                                                'post_onset_frames': load['preparation_window_after_frames']}}
    checks, graph, marker_start = marker_window(folder, window_case, calibration, speech_start, trim)
    checks.update(canonical_speech_pcm_and_states=(live.tobytes() == baseline.tobytes()
        and same_states(observed, pristine) and read(folder / 'browser-case.json') == read(folder / 'speech-case.json')
        and all(observed[key] == pristine[key] for key in ('speech', 'gestures'))),
        registered_preparation=prep == expected and bool(prep) and prep[-1]['contextFrame'] == speech_start - q,
        original_output_restored=route['before']['defaultOutput'] == route['after']['defaultOutput'])
    result = {'checks': checks, 'final_draw_frames': load['final_frames'], 'preparation': prep,
              'speech_start_context_frame': speech_start, 'marker_start_context_frame': marker_start,
              'graph_window': graph, 'trimmed_leading_anchor_frames': trim, 'trace_tables': list(tables),
              'output_route': route}
    if not checks['marker_spans_onset'] or not checks['registered_preparation']:
        return result
    observed, viable, pair = observed_window(folder, case, calibration, graph)
    result.update(cubeb_streams=observed, tap=pair)
    checks['unique_cubeb_marker'] = viable is not None
    if viable is None:
        return result

    _, blocks, cubeb, matched = viable
    cw = matched['tap_window']
    tick_ns = host_tick_ms() * 1e6
    offset = cw[0] - marker_start - graph['first']
    want = {'last_draw': prep[-1]['contextFrame'], 'speech_render_start': speech_start}
    targets = {}
    requests = {}
    gaps = []
    for i, b in enumerate(blocks[:-1]):
        f = b['pcm_byte_offset'] // 8
        width = b['frames']
        if any(f <= pos + offset < f + width for pos in want.values()) or cw[0] <= f < cw[1]:
            item = request_info(blocks, i, tick_ns, rate)
            if item['gap_frames'] != 0 and cw[0] <= f and f + width < cw[1]:
                gaps.append(item | {'context_frame': f - offset})
            for name, pos in want.items():
                if f <= pos + offset < f + width:
                    targets[name] = i
                    requests[name] = item | {'context_frame': pos, 'request_frame_offset': pos + offset - f}
    result.update(requests=requests, gaps=gaps)
    checks['both_load_and_speech_requests_located'] = set(targets) == set(want)
    if checks['both_load_and_speech_requests_located']:
        same = targets['last_draw'] == targets['speech_render_start']
        result['load_and_speech_same_request'] = same
        if load.get('delay_one_quantum'):
            checks['registered_same_request'] = same
    checks['tap_pcm_and_sample_clock'] = pair['valid'] and not pair['tap_sample_clock_jumps']
    if not checks['tap_pcm_and_sample_clock']:
        return result
    tw = pair['pcm']['tap_window']
    checks['tap_length_matches_scheduled_gaps'] = tw[1] - tw[0] - (cw[1] - cw[0]) == sum(row['gap_frames'] for row in gaps)
    tape = read(folder / 'tap.json')
    tap = np.fromfile(folder / 'tap.f32le', dtype='<f4').reshape(-1, 2)
    checks['registered_tap_width'] = {row['frames'] for row in tape['blocks']} == {rule['expected_tap_block_frames']}
    trace = device_requests(tables, blocks, tape, set(targets.values()) | {gap['cubeb_index'] for gap in gaps},
                            case['output_device']['uid'], case['trace']['maximum_server_host_error_us'], rate, tick_ns)
    for row in [*requests.values(), *gaps]:
        row.update(trace.get(row['cubeb_index'], {}))
        client = row.get('audio_client_duration_ns')
        row['within_budget'] = max(row['callback_ns'], client) <= row['budget_ns'] if client is not None else None
    checks['load_request_matches_audio_client_and_write'] = (checks['both_load_and_speech_requests_located']
        and all(row.get('audio_client_matches') == 1 for row in requests.values()))
    if checks['tap_length_matches_scheduled_gaps']:
        compare_gaps(gaps, cubeb[slice(*cw)].astype(float), tap[slice(*tw)].astype(float), [cw, tw],
                     case, graph['first'], {'cubeb_fraction': matched['anchors'][0]['fraction']})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('firefox', type=Path)
    parser.add_argument('tap', type=Path)
    parser.add_argument('--trial', type=int, required=True)
    parser.add_argument('--case', type=Path, default=CASE)
    parser.add_argument('--from-run', help='保存した同じ試行を再解析する')
    parser.add_argument('--trim-leading-anchor-frames', type=int, default=0)
    args = parser.parse_args()
    path = args.case.resolve()
    case = read(ONSET_CASE) | read(CASE)
    case_inputs = [ONSET_CASE, CASE]
    if path != CASE:
        child = read(path)
        if child['base_case'] != CASE.name:
            parser.error('指定された負荷比較の基準ケースに対応していません')
        case |= child
        case_inputs.append(path)
    load = case['load']
    if not 1 <= args.trial <= len(load['order']):
        parser.error('登録された試行番号を指定してください')
    load['final_frames'] = load['order'][args.trial - 1]
    revision = case['upstream_revision']
    firefox, app = args.firefox.resolve(strict=True), args.tap.resolve(strict=True)
    digests = {'firefox_binary_sha256': sha256(firefox), 'firefox_xul_sha256': sha256(firefox.with_name('XUL'))}
    tap_hash = sha256(app / 'Contents/MacOS/chimera-process-tap')
    baseline = hydrate_run(case['baseline_run'], case['baseline_case'], revision)
    control = hydrate_run(case['control_run'], 'worklet-live-tsp-44100-headphone-onset-gate-400ms', revision)
    calibration = hydrate_run(case['safari_calibration_run'], case['safari_calibration_case'], revision)
    if any(control[1][name] != digest or baseline[1][name] != digest for name, digest in digests.items()) or (
            tap_hash != control[1]['tap_binary_sha256'] or tap_hash != calibration[1]['tap_binary_sha256']):
        parser.error('基準と同じFirefoxおよびタップを指定してください')
    control_summary = verified_file(*control, 'summary.json')
    if not all(read(control_summary)['checks'].values()):
        parser.error('通常発話の機器照合を通過した実行を使用してください')
    wave_path, report_path, voice_case = (verified_file(*baseline, 'artifacts/' + name) for name in
                                             ('browser.wav', 'browser.json', 'browser-case.json'))
    reference = read(report_path)
    pcm = wave(wave_path, case['output_device']['sample_rate_hz'], reference['outputFrames'])
    cal_path = verified_file(*calibration, 'artifacts/effective-case.json')
    cal = read(cal_path)
    cal['marker'] |= {'chips': case['marker']['chips']}
    subprocess.run(['/usr/bin/codesign', '--verify', str(app)], check=True)
    inputs = [*case_inputs, Path(__file__).resolve(), voice_case, wave_path, report_path, control_summary, cal_path,
              *(run[0] / 'manifest.json' for run in (baseline, control, calibration)), *web_sources(),
              *(WORKSPACE / 'tools' / name for name in (
                 'measure_worklet_tsp_44100_onset.py', 'measure_worklet_tsp_io_deadline.py',
                 'measure_worklet_tsp_tap_gap_repetition.py', 'measure_firefox_output_marker.py',
                 'measure_worklet_tsp_device_io.py', 'measure_worklet_tsp_device_tap.py',
                 'inspect_firefox_cubeb_output.py', 'measure_safari_process_tap_calibration.py',
                 'chimera_coreaudio_output_device.swift', 'smooth_tap_marker.py', 'measure_uniform_tube.py'))]
    metadata = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision,
                'trial': args.trial, 'last_preparation_frames': load['final_frames'],
                'analysis_command': [sys.executable, *sys.argv], **digests, 'tap_binary_sha256': tap_hash}
    trim = args.trim_leading_anchor_frames
    if not 0 <= trim < load['preparation_window_before_frames'] or trim % case['comparison']['expected_device_request_frames']:
        parser.error('前端の短縮幅には、開始前の観測範囲内で機器要求の整数倍を指定してください')
    if trim and not args.from_run:
        parser.error('前端を短縮するには収録済みの実行を指定してください')
    if args.from_run:
        saved_run = WORKSPACE / 'runs' / args.from_run
        manifest_path = saved_run / 'manifest.json'
        stored = read(manifest_path)
        identity = {key: value for key, value in metadata.items() if key != 'analysis_command'}
        if stored['run_id'] != args.from_run or any(stored[key] != value for key, value in identity.items()):
            parser.error('指定した実行とケース・試行番号・バイナリが一致しません')
        outputs = {row['path']: verified_file(saved_run, stored, row['path']) for row in stored['outputs']}
        previous = read(outputs['summary.json'])
        if trim and previous.get('tap', {}).get('pcm', {}).get('reason') != 'smooth_anchor_not_unique':
            parser.error('登録したタップ窓が一意に決まらなかった試行を指定してください')
        tables = {schema: outputs[f'artifacts/{schema}.xml'] for schema in previous['trace_tables']}
        metadata['capture_run'] = args.from_run
        return record_measurement(args.run_id, path, inputs + [manifest_path, *outputs.values()], metadata,
            lambda out, execute: analyze(saved_run / 'artifacts', case, cal, pcm, reference,
                                         previous['output_route'], tables, trim=trim), command=None, input_root=ROOT)
    return record_measurement(args.run_id, path, inputs, metadata, lambda out, execute: measure(
        out, execute, case, cal, voice_case, pcm, reference, firefox, app, analyzer=analyze),
        command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
