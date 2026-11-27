"""実時間の声道測定線の転送、描画、背圧を、保存した測定値から照合する。"""

import numpy as np
from scipy.io import wavfile

import measure_wasm_fixed as wasm
from measure_fan_crossing_allocations import verified_path
from measure_worklet_realtime import timing_summary
from upstream_baseline import sha256


def compare_live_tract(registered, prior, artifacts, browser):
    spec = registered['measurement']
    offline = wasm.read_json(verified_path(prior, 'artifacts/browser.json'))
    wave = verified_path(prior, 'artifacts/browser.wav')
    evidence = {}
    checks = {}
    for name, metadata in [('browser', browser), ('mobile', browser['mobile']), ('stalled', browser['stalled'])]:
        report = wasm.read_json(artifacts / f'{name}.json')
        live = wasm.read_json(artifacts / f'{name}-live-tract.json')
        result, details = compare_trial(spec, offline, wave, artifacts / f'{name}.wav', report, live, metadata)
        checks.update({f'live_{name}_{key}': value for key, value in result.items()})
        evidence[name] = details
    return checks, evidence


def compare_trial(spec, offline, offline_wave, wave, report, live, metadata):
    rate, total, quantum = (spec[k] for k in ('output_rate_hz', 'output_frames', 'render_quantum_frames'))
    stride = spec['stride_output_frames']
    expected_points = np.minimum(np.arange(stride, total + stride, stride), total) - 1
    profile = report['tract']
    counts = profile['counts']
    packets = [p for p in live['packets'] if p['run'] == 0]
    draws = [p for p in live['draws'] if p['run'] == 0]
    captured = {row[0]: (row, acoustic, grid) for row, acoustic, grid in
                zip(profile['rows'], profile['acoustics']['rows'], profile['grid']['frames'], strict=True)}
    rt = report['realtime']
    start = rt['scheduledContextFrame']
    trace = report['tractLive']
    faults = []
    packet_frames = [p['frame'] for p in packets]
    for packet in packets:
        frame = packet['frame']
        entry = captured.get(frame)
        if entry is None:
            faults.append({'frame': frame, 'field': 'missing_frame'})
            continue
        row, acoustic, grid = entry
        word_count = (len(row) - 1) + (len(acoustic) - 1)
        data = packet['values']
        expected_geom = [value for section in grid['rows'] for value in section]
        if packet['counts'] != counts or packet['contextFrame'] != start + frame:
            faults.append({'frame': frame, 'field': 'counts_or_clock'})
        if data[:word_count] != [*row[1:], *acoustic[1:]]:
            faults.append({'frame': frame, 'field': 'acoustic'})
        if data[word_count:word_count + 1 + len(expected_geom)] != [len(grid['rows']), *expected_geom]:
            faults.append({'frame': frame, 'field': 'grid'})
    by_frame = {p['frame']: p for p in packets}
    phases = {name: [draw['frame'] for draw in draws if lo <= draw['frame'] <= hi]
              for name, (lo, hi) in spec['display_ranges'].items()}
    draw_faults = []
    for i, draw in enumerate(draws):
        frame = draw['frame']
        before = draws[i - 1] if i else None
        packet = by_frame.get(frame)
        if (packet is None or frame not in captured or draw['contextFrame'] != packet['contextFrame']
                or draw['atMs'] < packet['receivedMs'] or draw['lipArea'] != captured[frame][0][-1]
                or (before and (draw['frame'] <= before['frame'] or draw['draws'] <= before['draws']
                                or draw['updates'] <= before['updates']))):
            draw_faults.append(frame)
    timing = np.asarray(rt['blocks'])
    blocks = np.arange(0, total, quantum)
    budget = quantum * 1000 / rate
    warm = timing[spec['warm_exclude_first_quantums']:, rt['columns'].index('process_ms')]
    summary = timing_summary(warm, budget)
    normal = live['stall'] is None
    clocks = live['runs']
    stalled = None
    if not normal:
        stop = live['stall']
        # ページが回復するより前にWorkletで採取された送信分を数える。
        backlog = sum(stop['frame'] <= p['frame'] and p['contextFrame'] < stop['endedContextFrame'] - quantum
                      for p in packets)
        stalled = {
            **stop, 'queued_before_resume': backlog, 'elapsed_ms': stop['endedMs'] - stop['beganMs'],
            'delivered_after_resume': sum(p['contextFrame'] >= stop['endedContextFrame'] for p in packets),
        }
    bus_delay = [(p['receiptContextFrame'] - p['contextFrame']) * 1000 / rate for p in packets]
    draw_delay = [draw['atMs'] - by_frame[draw['frame']]['receivedMs'] for draw in draws if draw['frame'] in by_frame]
    final_wave_rate, pcm = wavfile.read(wave)
    first_gpu = draws[0]['buffers'] if draws else 0
    added_gpu = max((draw['buffers'] - first_gpu for draw in draws), default=0)
    return {
        'pcm_equals_offline': bool(final_wave_rate == rate and pcm.shape == (total,)
                                   and np.isfinite(pcm).all() and sha256(wave) == sha256(offline_wave)),
        'all_acoustic_and_grid_rows_equal_offline': (
            profile == offline['tract'] and list(captured) == expected_points.tolist()
            and len(captured) == spec['sample_count']),
        'worklet_contiguous_clock': bool(
            report['discontinuities'] == 0 and report['firstContextFrame'] == start
            and report['shortestQuantum'] == report['longestQuantum'] == quantum
            and np.array_equal(timing[:, 0], start + blocks)
            and np.array_equal(timing[:, 1], np.full(len(blocks), quantum))
            and np.array_equal(timing[:, 2], np.minimum(blocks + quantum, total))),
        'wire_same_frames_and_values': (
            not faults and packet_frames == sorted(set(packet_frames)) and trace['sent'] == len(packets)
            and trace['capacity'] == spec['transfer_buffer_count'] and trace['sent'] + trace['skipped'] == len(captured)),
        'presented_frames_are_current': (
            bool(draws) and not draw_faults and clocks[0]['completedAtMs'] is not None
            and all(draw['atMs'] <= clocks[0]['completedAtMs'] for draw in draws)),
        'presentation_and_audio_budget': (
            (len(packets) >= spec['normal_minimum_delivered'] and len(draws) >= spec['normal_minimum_displayed']
             and all(phases.values()) and summary['p95_ms'] <= budget * spec['maximum_warm_p95_quantum_budget_fraction'])
            if normal else
            (trace['skipped'] >= spec['stall_minimum_dropped'] and stalled['frame'] == spec['stall_trigger_frame']
             and stalled['elapsed_ms'] >= spec['stall_milliseconds'] and stalled['delivered_after_resume'] > 0
             and 1 <= stalled['queued_before_resume'] <= trace['capacity'])),
        'draw_buffer_reuse': (len({d['canvasId'] for d in draws}) == 1
                              and added_gpu <= spec['maximum_additional_gpu_buffers_after_first_draw']),
        'stop_clears_live_display': (len(clocks) == 2 and clocks[0]['contextClosedAtMs'] is not None
                                    and clocks[1]['completedAtMs'] is None and clocks[1]['contextClosedAtMs'] is not None
                                    and live['previewCleared'] and metadata['stopped'] and not metadata['errors']),
    }, {
        'sent_and_skipped': trace, 'received': len(packets), 'displayed': len(draws),
        'phase_frames': phases, 'first_wire_difference': faults[0] if faults else None,
        'first_draw_fault': draw_faults[0] if draw_faults else None, 'stall': stalled,
        'warm_timing': summary, 'new_gpu_buffers_after_first_draw': added_gpu,
        'maximum_receive_lag_ms_from_context_clock': max(bus_delay, default=None),
        'maximum_draw_lag_ms_from_receipt': max(draw_delay, default=None),
    }
