"""確認用07の音声I/Oとスレッド状態の収録範囲を比較する。"""

import argparse
from pathlib import Path
from statistics import median
import subprocess
from xml.etree import ElementTree

from measure_csd_envelope_timing import verified_file
from measure_speech_timing import read
from measure_tsp_listening import snapshot_case
from measure_uniform_tube import record_measurement
from measure_worklet_fixed import ROOT
from measure_safari_audio_client_trace import read_cycles
from measure_worklet_tsp_device_io import CLIENT, HARDWARE, SERVER, matching_client_cycles, match_server, server_rows
from measure_worklet_tsp_device_tap import inspect_tap, onset_anchor_checks
from measure_worklet_tsp_io_deadline import cubeb_window, rejoin, server_window
from measure_worklet_tsp_io_thread_state import SCHEMAS, acquisition_timing, full_alignment, trial_files, trial_states
from upstream_baseline import WORKSPACE


CASE = WORKSPACE / 'cases/worklet-live-tsp-firefox-trace-instruments-56q.json'
CONDITIONS = ('thread-state', 'audio-only')
WINDOW_CONDITIONS = ('whole-trace', 'tail-900ms')
ATTACH_CONDITIONS = ('all-processes', 'attach-firefox')


def onset_states_covered(report, offsets):
    periods = [slot for request in report['requests'] if request['request_offset'] in offsets
               for slot in request['slots']]
    return bool(periods) and all(
        len(slot['server_client_starts_ns']) == 1
        and not slot['states_in_period']['uncovered_intervals_ns']
        and slot['states_in_period']['overlap_ns'] == 0
        and not slot['states_in_period']['duration_by_state_ns'].get('Unknown')
        for slot in periods)


def audit_write_clock(trial, files, acquisition, io):
    if HARDWARE + '.xml' not in files:
        return {'write_clock_samples': 0, 'available': False}
    tick_ns = trial['device']['host_tick_ms'] * 1e6
    rows = server_rows(files[HARDWARE + '.xml'], HARDWARE, intervals=True)
    anchors = [round(row['current_host_ticks'] * tick_ns) - row['start_ns']
               for row in rows if row['current_host_ticks'] > 0]
    audit = {'write_clock_samples': len(anchors), 'available': False}
    if len(anchors) < 2:
        return audit
    low, high = min(anchors), max(anchors)
    audit['origin_mach_ns_range'] = [low, high]
    if high - low > io['maximum_server_host_error_ms'] * 1e6:
        return audit
    origin = round(median(anchors))
    shift = origin - acquisition['trace_origin_mach_ns']
    targets = {offset: start - shift for offset, start in acquisition['onset_cubeb_entry_trace_ns'].items()}
    audit.update(available=True, trace_origin_mach_ns=origin, origin_minus_metadata_ns=shift,
                 cubeb_onset_trace_ns=targets,
                 cubeb_full_window_trace_ns=[stamp - shift for stamp in acquisition['cubeb_full_window_trace_ns']],
                 metadata_origin_agrees=abs(shift) <= io['maximum_trace_origin_error_ms'] * 1e6)
    offsets = [row['offset'] for row in trial['device_onset_requests'] if 0 in row['speech_output_frames']]
    if len(offsets) == 1 and 'client_last_end_ns' in acquisition:
        audit['first_onset_margin_ns'] = acquisition['client_last_end_ns'] - targets[offsets[0]]
    return audit


def release_timing(files, delay_ms, maximum_overshoot, *, tap_before_trace=False):
    observed = read(files['trace-start-signals.json'])
    ready = read(files['system-trace-ready.json'])
    release = read(files['trace-release.json'])
    gate = observed.get('gate_monotonic_ns')
    darwin = observed.get('darwin_monotonic_ns')
    line = observed.get('stdout_start_line_monotonic_ns')
    after_stdout = delay_ms is not None
    if None in (gate, darwin, line, release.get('release_monotonic_ns')):
        return observed, False
    expected = line + delay_ms * 1_000_000 if after_stdout else darwin
    measured = observed | {'release_monotonic_ns': release['release_monotonic_ns'],
                           'gate_minus_expected_ns': gate - expected,
                           'darwin_minus_gate_ns': darwin - gate}
    correct = (0 <= gate - expected <= maximum_overshoot
               and gate == ready['trace_notice_monotonic_ns'] <= release['release_monotonic_ns']
               and ready.get('release_source') == ('stdout-delayed' if after_stdout else None))
    if tap_before_trace:
        tap_ready = release.get('tap_ready_monotonic_ns')
        measured['tap_ready_monotonic_ns'] = tap_ready
        correct = correct and release['tap_requested'] and release['tap_ready'] and tap_ready is not None and tap_ready <= line
    else:
        correct = correct and not release['tap_requested']
    return measured, correct


def inspect_joined_tap(trial, files, case, joined=None, indices=None):
    core = trial['device']
    options = case['tap']
    stream, = core['matched_streams']
    intervals = core['streams'][stream]['intervals']
    pcm_start = core['streams'][stream]['pcm']['tap_window'][0]
    if joined is not None:
        _, _, _, server, cycles, writes = joined
        tick = core['host_tick_ms'] * 1e6
        tolerance = case['system_io']['maximum_server_host_error_ms'] * 1e6
    gaps = []
    for graph, interval in zip(core['graph_rows'], intervals, strict=True):
        if not interval['sample_time_gap_frames'] or interval['pcm_start_frame'] < pcm_start:
            continue
        offset = graph['offset']
        gap = interval | {'request_offset': offset}
        if joined is not None and offset in indices:
            index = indices[offset]
            frames = interval['request_frames']
            try:
                rows = server_window(*server[index:index + 2], cycles, writes, frames * 1e9 / options['sample_rate_hz'],
                                     frames, tick, tolerance)
                gap.update(server_write_cycles=[write for _, write in rows[:-1]],
                           intervening_server_client_cycles=[cycle for cycle, _ in rows[1:-1]])
            except ValueError as error:
                gap['server_mapping_error'] = str(error)
        gaps.append(gap)
    checks, report = inspect_tap(files['tap.json'].parent, core, {'gaps': gaps}, read(files['marker-settings.json']), options)
    if joined is not None:
        checks.update(onset_anchor_checks(core, trial['device_onset_requests'], {'server_candidate_count': 1}, options))
    return checks, report


def audit_gate_overlap(trial, files, acquisition, clock, io):
    if not clock.get('metadata_origin_agrees') or not all(
            schema + '.xml' in files for schema in (CLIENT, SERVER, HARDWARE)):
        return {}
    data = trial['device']
    selected, = data['matched_streams']
    blocks = cubeb_window(selected, data, files)
    indices = {row['offset']: i for i, row in enumerate(data['graph_rows'])}
    tick_ns = data['host_tick_ms'] * 1e6
    pid = trial['system_io']['pid']
    clients, _ = read_cycles(files[CLIENT + '.xml'], pid, include_overloads=True)
    servers = list(server_rows(files[SERVER + '.xml'], SERVER, intervals=True))
    writes = list(server_rows(files[HARDWARE + '.xml'], HARDWARE, intervals=True))
    onset = []
    for request in trial['device_onset_requests']:
        offset = request['offset']
        block = blocks[indices[offset]]
        client = matching_client_cycles([block], clients, clock['trace_origin_mach_ns'], tick_ns, io)
        server = match_server([block], servers, pid, tick_ns, io['maximum_server_host_error_ms'])
        associated = []
        if len(server) == 1:
            cycle, = server[0]['cycles']
            associated = [
                row for row in writes if row['tid'] == cycle['tid']
                and row['start_sample_time'] == cycle['output_sample_time'] and row['frames'] == block['frames']
                and abs(row['start_ns'] - cycle['start_ns']) < request['budget_ms'] * 1e6]
        onset.append({'offset': offset, 'client_matches': len(client), 'server_matches': len(server),
                      'write_matches': len(associated)})
    result = {'onset_requests': onset}
    if clients and all(value is not None for value in acquisition['table_first_start_ns'].values()):
        first_client = min(row['start_ns'] for row in clients)
        result['first_firefox_client_minus_first_onset_ns'] = first_client - min(clock['cubeb_onset_trace_ns'].values())
        first = max(first_client, *acquisition['table_first_start_ns'].values())
        last = min(max(row['start_ns'] + row['duration_ns'] for row in clients),
                   *acquisition['table_last_end_ns'].values())
        window_start, window_end = clock['cubeb_full_window_trace_ns']
        result['additional_delay_for_full_audio_window_ns'] = [max(0, first - window_start), last - window_end]
    return result


def describe_trial(trial, files, log, case, out, execute):
    io = case['system_io']
    limits = case['comparison']
    retained_window = io.get('compare_retained_window')
    fixed_gate = io.get('stdout_release_delay_ms')
    gate_delay = fixed_gate or io.get('compare_stdout_release_delay_ms')
    attach_target = bool(io.get('compare_attach_target') or gate_delay)
    tap_before_trace = case['capture'].get('wait_for_trace_before_release', False) and bool(fixed_gate)
    condition = trial['condition']
    intended = [n for n in io['instruments'] if condition != 'audio-only' or n != 'Thread State Trace']
    captured_log = log.read_text() if log is not None else ''
    settings = ', '.join(intended) + ' Instruments.'
    expected_ready_frame = 128 * case['capture']['marker_ready_quanta']
    acquisition = acquisition_timing(trial, files, io, include_starts=bool(retained_window or attach_target))
    onset = trial.get('device_onset_requests', [])
    offsets = [request['offset'] for request in onset]
    center = acquisition['constructor_marker_frame']
    constructor_slack = limits.get('maximum_constructor_after_ready_frames', 0)
    checks = {
        'registered_instruments': (trial.get('trace_instruments') == intended and settings in captured_log
                                   and 'Time limit: 1.0 s' in captured_log
                                   and (condition == 'attach-firefox' or bool(gate_delay) or
                                        'Targeting All Processes.' in captured_log)),
        'registered_pcm_and_voice_state': all(trial['checks'].get(k, False) for k in
                                             ('registered_pcm', 'registered_case_and_states', 'fixed_upstream_pcm')),
        'registered_onset_offsets': offsets == limits['first_speech_offsets'],
        'registered_constructor_frame': center is not None and 0 <= center - expected_ready_frame <= constructor_slack,
    }
    report = {'pair': trial['pair'], 'condition': condition, 'acquisition': acquisition,
              'checks': checks, 'onset_requests': onset, 'alignment_scope': 'missing',
              'covered_onset_gaps': []}
    if retained_window or attach_target:
        recorded = read(files['trace-recording-settings.json']) if files and 'trace-recording-settings.json' in files else {}
        if retained_window:
            desired = retained_window if condition == 'tail-900ms' else None
            checks['registered_retention'] = (trial.get('trace_window') == desired and recorded == {
                'window': desired, 'time_limit': io['time_limit'], 'instruments': intended, 'ready_file': 'trace-ready.json'})
            report['recorded_window'] = recorded.get('window')
        else:
            report['target_and_io_tables'] = {'firefox_pid': recorded.get('firefox_pid'), 'attach_pid': recorded.get('attach_pid'),
                                              'available': trial.get('system_io', {}).get('trace_tables_available', []),
                                              'missing': trial.get('system_io', {}).get('missing_trace_tables', [])}
            report['joint_onset_covered'] = False
            checks['registered_attach_target'] = False
        report['thread_state_onset_covered'] = False
        if files and 'system-trace-ready.json' in files:
            gate = read(files['system-trace-ready.json'])['trace_notice_monotonic_ns']
            notice = gate
            if gate_delay:
                acquisition['trace_start_minus_gate_ns'] = acquisition['trace_origin_mach_ns'] - gate
                notice = (read(files['trace-start-signals.json']).get('darwin_monotonic_ns')
                          if 'trace-start-signals.json' in files else None)
            if notice is not None:
                acquisition['trace_start_minus_darwin_notice_ns'] = acquisition['trace_origin_mach_ns'] - notice
    if files is None:
        if gate_delay:
            checks['registered_release_signal'] = False
        return report
    if 'marker.json' in files:
        marker = read(files['marker.json'])
        ready_at = marker['frames'][case['capture']['marker_ready_quanta'] - 1] + 128 - marker['startFrame']
        checks['registered_marker_ready_frame'] = ready_at == expected_ready_frame
        report['marker_ready_frame'] = ready_at
        report['constructor_after_ready_frames'] = acquisition['constructor_marker_frame'] - ready_at
    onset_frame_zero = [r['offset'] for r in onset if 0 in r['speech_output_frames']]
    margins = acquisition.get('onset_entry_to_client_last_end_ns', {})
    if len(onset_frame_zero) == 1:
        report['first_onset_margin_ns'] = margins.get(onset_frame_zero[0])
    toc = ElementTree.parse(files['io-toc.xml'])
    schemas = {row.get('schema') for row in toc.findall('.//table')}
    report['thread_state_table_present'] = toc.find(".//table[@schema='thread-state']") is not None
    if attach_target:
        audio_schemas = (CLIENT, SERVER, HARDWARE)
        report['target_and_io_tables'].update(available=[schema for schema in audio_schemas if schema in schemas],
                                             missing=[schema for schema in audio_schemas if schema not in schemas])
        wanted = condition == 'attach-firefox' or gate_delay is not None
        pid = trial['system_io']['pid']
        target = toc.find('.//target')
        all_processes = target is not None and target.find('all-processes') is not None
        attached_pid = target is not None and any(row.get('pid') == str(pid) for row in target.iter())
        checks['registered_attach_target'] = (
            trial['trace_attach_requested'] is wanted and recorded.get('firefox_pid') == pid
            and recorded.get('attach_pid') == (pid if wanted else None)
            and recorded.get('ready_file') == 'trace-target.json' and recorded.get('window') is None
            and (attached_pid and not all_processes if wanted else all_processes))
        if gate_delay:
            wanted_delay = fixed_gate or (gate_delay if condition == f'stdout-{gate_delay}ms' else None)
            checks['registered_release_signal'] = False
            if {'trace-start-signals.json', 'trace-release.json', 'system-trace-ready.json'} <= files.keys():
                timing, correct = release_timing(files, wanted_delay, limits['maximum_release_overshoot_ns'],
                                                 tap_before_trace=tap_before_trace)
                report['release_timing'] = timing
                checks['registered_release_signal'] = correct and recorded.get('stdout_release_delay_ms') == wanted_delay
        processes = toc.findall('.//processes/process')
        report['target_and_io_tables'].update(processes_in_toc=len(processes), coreaudiod_pids=[
            row.get('pid') for row in processes if row.get('name') == 'coreaudiod'])
        if report['target_and_io_tables']['missing']:
            report['alignment_error'] = '音声I/Oの表がそろわないため要求を照合できません'
            return report
    data = trial['device']
    stream, = data['matched_streams']
    candidate_local = None if full_alignment(trial) else limits['local_onset_offsets']
    try:
        joined = rejoin(
            stream, data, trial['system_io'], data['host_tick_ms'] * 1e6, io, files, offset_bounds=candidate_local)
    except ValueError as error:
        report['alignment_error'] = str(error)
        return report
    window_offsets = (range(candidate_local[0], candidate_local[1] + 1) if candidate_local
                      else (r['offset'] for r in data['graph_rows']))
    indices = {offset: i for i, offset in enumerate(window_offsets)}
    if not set(offsets) <= indices.keys():
        report['alignment_error'] = '発話開始の要求が照合した窓に含まれません'
        return report
    report['alignment_scope'] = 'onset' if candidate_local else 'full'
    blocks, _, client, server, server_cycles, writes = joined
    if tap_before_trace and {'tap.json', 'tap.f32le', 'marker-settings.json'} <= files.keys():
        tap_checks, report['tap_pcm'] = inspect_joined_tap(trial, files, case, joined, indices)
        checks.update(tap_checks)
    if attach_target:
        try:
            report['onset_device_writes'] = {
                offset: [write for _, write in server_window(
                    *server[indices[offset]:indices[offset] + 2], server_cycles, writes,
                    256 * 1e9 / 48_000, 256, data['host_tick_ms'] * 1e6, io['maximum_server_host_error_ms'] * 1e6)]
                for offset in offsets}
        except ValueError as error:
            report['onset_device_write_error'] = str(error)
    for request in onset:
        index = indices[request['offset']]
        current, following = blocks[index:index + 2]
        gap = int(following['sample_time'] - current['sample_time'] - current['frames'])
        if gap <= 0:
            continue
        client_ns = client['cycles'][index]['duration_ns']
        budget_ns = request['budget_ms'] * 1e6
        report['covered_onset_gaps'].append({
            'offset': request['offset'], 'gap_frames': gap, 'client_duration_ns': client_ns,
            'cubeb_callback_ns': round(request['callback_ms'] * 1e6), 'budget_ns': budget_ns,
            'intervening_client_cycles': client['unmatched_cycles_between'][index],
            'within_budget': max(client_ns, request['callback_ms'] * 1e6) <= budget_ns,
        })
    if {'trace', 'tables'} & files.keys() and report['thread_state_table_present']:
        config = {'request_offsets': limits['first_speech_offsets'], 'positive_control_offset': 0,
                  'local_onset_offsets': limits['local_onset_offsets'], 'pre_cycle_ns': 25_000,
                  'request_frames': 256, 'sample_rate_hz': 48_000, 'maximum_server_interval_error_ms': 0.10}
        try:
            report['thread_states'] = trial_states(trial, files, config, io, out, execute)
            if retained_window or attach_target:
                report['thread_state_onset_covered'] = onset_states_covered(report['thread_states'], offsets)
            if attach_target:
                report['joint_onset_covered'] = report['thread_state_onset_covered'] and bool(
                    report.get('onset_device_writes'))
        except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
            report['thread_state_error'] = str(error)
    return report


def compare_preparation_load(trials, data, case):
    spec = case['measurement']['onset_load']
    limits = case['comparison']
    final_block_frames = spec.get('final_block_frames', {})
    conditions = (('split-onset-load', 'split-onset-load-224') if final_block_frames
                  else ('split-early-load', 'split-onset-load'))
    grouped = {}
    for trial, (capture, _, _) in zip(trials, data, strict=True):
        condition = trial['condition']
        state_requests = trial.get('thread_states', {}).get('requests', [])
        onset = [request for request in state_requests if request['contains_first_speech_quantum']]
        slots = onset[0]['slots'] if len(onset) == 1 else []
        pieces = capture.get('device', {}).get('split_requests', [])
        block_frames = spec['block_frames']
        offsets = spec['quantum_offsets'][condition]
        last_frames = block_frames * (len(offsets) - 1) + final_block_frames.get(condition, block_frames)
        final_offsets = [row['request_offset'] for row in pieces if last_frames in row['completed_pieces']]
        final_offset = final_offsets[0] if len(final_offsets) == 1 else None
        first_offset = limits['first_speech_offsets'][0]
        loaded = offsets[-1] == 16
        trial['checks'].update({
            'registered_split_schedule': bool(capture['checks'].get('split_matches_lead_quanta')
                                              and capture['checks'].get('split_pieces_match_device_requests')),
            'first_quantum_in_separate_request': [row['speech_output_frames'] for row in trial['onset_requests']]
                                                 == [[0], [128, 256]],
            'registered_final_piece_request': final_offset is not None
                                             and (final_offset == first_offset if loaded else final_offset < first_offset),
            'joint_onset_covered': bool(trial.get('joint_onset_covered') and slots),
        })
        trial['final_piece_request_offset'] = final_offset
        if slots:
            request, = onset
            trial['first_request'] = {
                'client_duration_ns': request['client_duration_ns'],
                'slack_to_next_server_ns': -slots[0]['previous_client_end_minus_server_start_ns'],
                'callback_ns': request['callback_ns'],
                'within_budget': request['within_budget'],
                'gap_frames': request['gap_frames'],
            }
        grouped.setdefault(trial['pair'], {})[condition] = trial
    paired = []
    for number, pair in grouped.items():
        comparable = all(all(trial['checks'].values()) for trial in pair.values())
        row = {'pair': number, 'comparable': comparable}
        if comparable:
            control, loaded = (pair[name]['first_request'] for name in conditions)
            growth = loaded['client_duration_ns'] - control['client_duration_ns']
            reduction = control['slack_to_next_server_ns'] - loaded['slack_to_next_server_ns']
            row.update(client_growth_ns=growth, slack_reduction_ns=reduction,
                       predicted_change=min(growth, reduction) >= limits['minimum_change_ns'])
        paired.append(row)
    count = sum(row['comparable'] for row in paired)
    supported = sum(row.get('predicted_change', False) for row in paired)
    evaluated = count >= limits['minimum_comparable_pairs']
    checks = {f"{trial['pair']}-{trial['condition']}/{key}": value
              for trial in trials for key, value in trial['checks'].items()}
    checks['enough_comparable_pairs'] = evaluated
    result = {'checks': checks, 'trials': trials, 'paired': paired,
              'prediction': {'evaluated': evaluated, 'supported': supported >= limits['minimum_comparable_pairs']
                             if evaluated else None, 'comparable_pairs': count, 'matching_pairs': supported}}
    if final_block_frames:
        slack_limit = limits['maximum_near_budget_slack_ns']
        near_budget = {name: [] for name in conditions}
        for trial in trials:
            request = trial.get('first_request')
            if (request and all(trial['checks'].values()) and request['within_budget']
                    and 0 <= request['slack_to_next_server_ns'] <= slack_limit):
                near_budget[trial['condition']].append(trial['pair'])
        result['near_budget_pairs_by_condition'] = near_budget
    return result


def compare_tap_coverage(trials, data, case):
    limits = case['comparison']
    spec = case['measurement']['onset_load']
    valid = 0
    events = []
    for trial, (capture, files, _) in zip(trials, data, strict=True):
        condition = trial['condition']
        block_frames = spec['block_frames']
        offsets = spec['quantum_offsets'][condition]
        last_frames = block_frames * (len(offsets) - 1) + spec['final_block_frames'][condition]
        final_pieces = [row['request_offset'] for row in capture.get('device', {}).get('split_requests', [])
                        if last_frames in row['completed_pieces']]
        checks = trial['checks']
        checks['registered_split_schedule'] = bool(capture['checks'].get('split_matches_lead_quanta')
                                                  and final_pieces == limits['first_speech_offsets'][:1])
        checks['tap_from_attached_process'] = bool(files and 'tap.json' in files and
                                                  read(files['tap.json'])['pid'] ==
                                                  trial.get('target_and_io_tables', {}).get('attach_pid'))
        if 'tap_pcm' not in trial:
            # 音声I/O表の欠測時もcubebとタップの波形比較を残す。
            if files and {'tap.json', 'tap.f32le', 'marker-settings.json'} <= files.keys():
                pcm_checks, trial['tap_pcm'] = inspect_joined_tap(capture, files, case)
                checks.update(pcm_checks)
            else:
                trial['tap_pcm'] = capture.get('paired_output', {})
        else:
            checks['joint_onset_with_pcm'] = bool(trial['joint_onset_covered'] and trial['tap_pcm']['valid'])
        checks.setdefault('joint_onset_with_pcm', False)
        if all(checks.values()):
            valid += 1
        tap_gaps = {gap['request_offset']: gap for gap in trial['tap_pcm'].get('gaps', ())}
        for gap in trial['covered_onset_gaps']:
            if gap['within_budget'] and gap['intervening_client_cycles'] == 0:
                events.append(gap | {'trial': trial['pair'], 'tap_gap': tap_gaps.get(gap['offset'])})
    checks = {f"{trial['pair']}-{key}": value for trial in trials for key, value in trial['checks'].items()}
    checks['minimum_joint_windows'] = valid >= limits['minimum_joint_windows']
    return {'checks': checks, 'trials': trials, 'joint_windows': valid, 'within_budget_onset_gaps': events}


def inspect_write_threads(data, previous, case):
    io = case['system_io']
    limits = case['comparison']
    reports = []
    for (capture, files, _), trial in zip(data, previous['trials'], strict=True):
        if not trial.get('onset_device_write_error') or not files:
            continue
        device = capture['device']
        stream, = device['matched_streams']
        tick_ns = device['host_tick_ms'] * 1e6
        tolerance_ns = io['maximum_server_host_error_ms'] * 1e6
        bounds = limits['local_onset_offsets'] if trial['alignment_scope'] == 'onset' else None
        _, _, _, server, _, writes = rejoin(stream, device, capture['system_io'], tick_ns, io, files, offset_bounds=bounds)
        offsets = range(bounds[0], bounds[1] + 1) if bounds else (r['offset'] for r in device['graph_rows'])
        cycles = dict(zip(offsets, server))
        requests = trial['onset_requests']
        anchors = []
        for request in requests:
            cycle = cycles[request['offset']]
            anchors.append({(row['engine_id'], row['stream_index'])
                            for row in writes[cycle['output_sample_time']]
                            if row['frames'] == request['requested_frames']
                            and 0 <= row['start_ns'] - cycle['start_ns'] < request['budget_ms'] * 1e6})
        stream_ids = set.intersection(*anchors)
        report = {'pair': trial['pair'], 'condition': trial['condition'], 'streams_from_speech_requests': sorted(stream_ids),
                  'following_writes': []}
        reports.append(report)
        if len(stream_ids) != 1:
            continue
        source_rows = list(server_rows(files[SERVER + '.xml'], SERVER, intervals=True))
        hardware_rows = list(server_rows(files[HARDWARE + '.xml'], HARDWARE, intervals=True))
        for request in requests:
            offset = request['offset'] + 1
            expected = cycles[offset]
            options = [row for row in hardware_rows if (row['engine_id'], row['stream_index']) in stream_ids
                       and row['start_sample_time'] == expected['output_sample_time']
                       and row['frames'] == request['requested_frames']
                       and 0 <= row['start_ns'] - expected['start_ns'] < request['budget_ms'] * 1e6]
            matches = []
            for write in options:
                if write['tid'] == expected['tid']:
                    matches.append({'write': write, 'cycle': expected, 'host_time_delta_ns': 0,
                                    'write_after_cycle_end_ns': write['start_ns'] - expected['start_ns']
                                    - expected['duration_ns']})
                    continue
                for cycle in source_rows:
                    if (cycle['tid'] == write['tid'] and cycle['output_sample_time'] == expected['output_sample_time']
                            and abs(cycle['host_ticks'] - expected['host_ticks']) * tick_ns <= tolerance_ns
                            and 0 <= write['start_ns'] - cycle['start_ns'] - cycle['duration_ns'] <= tolerance_ns):
                        matches.append({'write': write, 'cycle': cycle,
                                        'host_time_delta_ns': (cycle['host_ticks'] - expected['host_ticks']) * tick_ns,
                                        'write_after_cycle_end_ns': write['start_ns'] - cycle['start_ns'] - cycle['duration_ns']})
            report['following_writes'].append({'offset': offset, 'registered_server_thread': expected['tid'],
                                               'matched_worker_rows': matches})
    return previous | {'write_thread_inspection': reports}


def compare_trials(out, execute, data, case, *, verify_write_clock=False):
    trials = [describe_trial(trial, files, log, case, out / f"{trial['pair']}-{trial['condition']}", execute)
              for trial, files, log in data]
    limits = case['comparison']
    retained_window = case['system_io'].get('compare_retained_window')
    fixed_gate = case['system_io'].get('stdout_release_delay_ms')
    gate_delay = fixed_gate or case['system_io'].get('compare_stdout_release_delay_ms')
    attach_target = bool(case['system_io'].get('compare_attach_target') or gate_delay)
    extended_load = case['measurement'].get('onset_load', {}).get('final_block_frames')
    if verify_write_clock or attach_target:
        for trial, (capture, files, _) in zip(trials, data, strict=True):
            audit = audit_write_clock(capture, files, trial['acquisition'], case['system_io']) if files else {}
            trial['write_clock_audit'] = audit
            trial['checks']['trace_origin_agrees_with_write_clock'] = audit.get('metadata_origin_agrees', False)
            if gate_delay and (verify_write_clock or extended_load) and files:
                trial['onset_overlap_audit'] = audit_gate_overlap(
                    capture, files, trial['acquisition'], audit, case['system_io'])
    if fixed_gate and case['capture'].get('wait_for_trace_before_release'):
        return compare_tap_coverage(trials, data, case)
    if fixed_gate:
        return compare_preparation_load(trials, data, case)
    conditions = (('darwin', f'stdout-{gate_delay}ms') if gate_delay else ATTACH_CONDITIONS if attach_target
                  else WINDOW_CONDITIONS if retained_window else CONDITIONS)
    control_name, candidate_name = conditions
    difference_key = ('stdout_delay_minus_darwin_ns' if gate_delay else 'attach_minus_all_ns' if attach_target else
                      'tail_minus_whole_ns' if retained_window else 'audio_only_minus_thread_state_ns')
    checks = {f"{r['pair']}-{r['condition']}/{k}": value for r in trials for k, value in r['checks'].items()}
    groups = {name: [t for t in trials if t['condition'] == name] for name in conditions}
    onset_covered = {name: sum(t['alignment_scope'] in ('onset', 'full') for t in group)
                     for name, group in groups.items()}
    paired = []
    for control, candidate in zip(*(groups[name] for name in conditions), strict=True):
        control_ns, candidate_ns = (r.get('first_onset_margin_ns') for r in (control, candidate))
        observed = candidate_ns - control_ns if None not in (control_ns, candidate_ns) else None
        comparable = observed is not None and all(all(row['checks'].values()) for row in (control, candidate))
        paired.append({'pair': control['pair'], 'first_onset_margin_ns': dict(zip(conditions, (control_ns, candidate_ns))),
                       difference_key: observed if comparable else None,
                       'observed_margin_difference_ns': observed,
                       'alignment': {r['condition']: r['alignment_scope'] for r in (control, candidate)}})
        if verify_write_clock and retained_window:
            c, t = (r['write_clock_audit'].get('first_onset_margin_ns') for r in (control, candidate))
            paired[-1]['write_anchored_tail_minus_whole_ns'] = t - c if None not in (c, t) else None
    gains = [r[difference_key] for r in paired if r[difference_key] is not None]
    checks['all_pairs_comparable'] = len(gains) == len(paired)
    count = sum(gain > limits['minimum_margin_gain_ns'] for gain in gains)
    relevant_windows = onset_covered
    if retained_window or attach_target:
        metric = 'joint_onset_covered' if attach_target else 'thread_state_onset_covered'
        relevant_windows = {name: sum(t[metric] for t in group) for name, group in groups.items()}
    supported = (count >= limits['minimum_pairs_with_margin_gain']
                 and relevant_windows[candidate_name] > relevant_windows[control_name])
    report = {'checks': checks, 'trials': trials, 'paired': paired, 'onset_windows': onset_covered,
            'full_windows': {name: sum(t['alignment_scope'] == 'full' for t in group)
                             for name, group in groups.items()},
            'prediction': {'evaluated': checks['all_pairs_comparable'],
                           'supported': supported if checks['all_pairs_comparable'] else None,
                           'pairs_with_registered_margin_gain': count,
                           'median_margin_gain_ns': median(gains) if gains else None}}
    if retained_window:
        report['thread_state_onset_windows'] = relevant_windows
    if attach_target:
        report['joint_onset_windows'] = relevant_windows
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('capture_run')
    parser.add_argument('--case', type=Path, default=CASE)
    parser.add_argument('--previous-analysis', help='機器Writeのホスト時計で前版のトレース起点を検算する')
    parser.add_argument('--inspect-local-end', type=int, help='登録済みの判定を保ち、局所窓の末尾だけを短くして検算する')
    parser.add_argument('--inspect-write-threads', action='store_true',
                        help='元の判定を保ち、別スレッドで記録された機器Writeを検算する')
    args = parser.parse_args()
    run = WORKSPACE / 'runs' / args.capture_run
    manifest = read(run / 'manifest.json')
    case_path = args.case.resolve()
    case = read(case_path)
    rev = case['upstream_revision']
    capture = run, manifest
    if (manifest['run_id'], manifest['case_id'], manifest['upstream_revision']) != (args.capture_run, case['id'], rev):
        parser.error('登録した収録とマニフェストが一致しません')
    snapshot = snapshot_case(capture, case['id'])
    if read(snapshot) != case:
        parser.error('収録時のケースが一致しません')
    summary = verified_file(*capture, 'summary.json')
    rows = read(summary)['trials']
    expected = [(pair, condition) for pair, order in enumerate(case['measurement']['condition_order'], 1)
                for condition in order]
    if [(t['pair'], t['condition']) for t in rows] != expected:
        parser.error('登録した組の順序と試行が一致しません')
    inputs = [case_path, snapshot, Path(__file__).resolve(), summary, run / 'manifest.json',
              *(WORKSPACE / 'tools' / name for name in ('measure_worklet_tsp_io_thread_state.py',
                  'measure_worklet_tsp_io_deadline.py', 'measure_worklet_tsp_io_client_start.py',
                  'measure_worklet_tsp_device_io.py', 'measure_cubeb_output_callback.py',
                  'measure_safari_audio_client_trace.py', 'filter_worklet_audioipc_syscalls.py',
                  'measure_uniform_tube.py'))]
    outputs = {row['path'] for row in manifest['outputs']}
    data = []
    retained_window = case['system_io'].get('compare_retained_window')
    fixed_gate = case['system_io'].get('stdout_release_delay_ms')
    gate_delay = fixed_gate or case['system_io'].get('compare_stdout_release_delay_ms')
    attach_target = bool(case['system_io'].get('compare_attach_target') or gate_delay)
    tap_before_trace = case['capture'].get('wait_for_trace_before_release', False) and bool(fixed_gate)
    if tap_before_trace:
        calibration_run = WORKSPACE / 'runs' / case['tap']['calibration_run']
        calibration_manifest = read(calibration_run / 'manifest.json')
        calibration = verified_file(calibration_run, calibration_manifest, 'artifacts/effective-case.json')
        inputs += [calibration_run / 'manifest.json', calibration]
        case['tap'].update(smooth_alignment=read(calibration), local_pcm=case['local_pcm'])
    if retained_window or attach_target:
        reference_run = WORKSPACE / 'runs' / case['initial_control_run']
        reference_manifest = read(reference_run / 'manifest.json')
        reference_case = snapshot_case((reference_run, reference_manifest), case['initial_control_case'])
        previous_capture = read(reference_case)['capture']
        registered_capture = {k: v for k, v in case['capture'].items()
                              if k != 'publish_trace_target' or k in previous_capture}
        if tap_before_trace:
            tap_settings = {'wait_for_trace_before_release', 'tap_ready_timeout_seconds', 'tap_duration_seconds',
                            'prime_tap_before_playback'}
            registered_capture = {k: v for k, v in registered_capture.items() if k not in tap_settings}
            previous_capture = {k: v for k, v in previous_capture.items() if k not in tap_settings}
        if previous_capture != registered_capture or (
                reference_manifest['firefox_xul_sha256'] != manifest['firefox_xul_sha256']):
            parser.error('前回と今回の先行音条件または採取用Firefoxが一致しません')
        inputs += [reference_run / 'manifest.json', reference_case]
    earlier_outputs = set()
    previous_report = None
    if args.previous_analysis:
        earlier = WORKSPACE / 'runs' / args.previous_analysis
        earlier_manifest = read(earlier / 'manifest.json')
        if not (retained_window or gate_delay) or (earlier_manifest.get('capture_run'), earlier_manifest.get('case_id')) != (
                args.capture_run, case['id']):
            parser.error('同じ収録の前版の解析記録が一致しません')
        previous_summary = verified_file(earlier, earlier_manifest, 'summary.json')
        inputs += [earlier / 'manifest.json', previous_summary]
        if args.inspect_local_end is not None or args.inspect_write_threads:
            previous_report = read(previous_summary)
        earlier_outputs = {row['path'] for row in earlier_manifest['outputs']}
    inspection_case = case
    if args.inspect_write_threads and (previous_report is None or not tap_before_trace or args.inspect_local_end is not None):
        parser.error('同じタップ併用収録の前版を指定してください')
    if args.inspect_local_end is not None:
        limits = case['comparison']
        start, end = limits['local_onset_offsets']
        if previous_report is None or not fixed_gate or tap_before_trace or not (
                max(limits['first_speech_offsets']) <= args.inspect_local_end < end):
            parser.error('同じ収録の前版と、発話要求を含む短い局所窓の末尾を指定してください')
        bounds = [start, args.inspect_local_end]
        inspection_case = case | {'comparison': limits | {'local_onset_offsets': bounds}}
    for trial in rows:
        prefix = f"artifacts/{trial['pair']}-{trial['condition']}"
        files = trial_files(capture, trial, allow_missing_tables=attach_target)
        log_name = f'{prefix}/system-trace-command.log'
        log = verified_file(*capture, log_name) if log_name in outputs else None
        if log is not None:
            inputs.append(log)
        if files is not None:
            marker_name = f'{prefix}/marker.json'
            if marker_name in outputs:
                files['marker.json'] = verified_file(*capture, marker_name)
            if retained_window or attach_target:
                names = ('trace-recording-settings.json', 'system-trace-ready.json')
                if gate_delay:
                    names += ('trace-start-signals.json', 'trace-release.json')
                if tap_before_trace:
                    names += ('tap.json', 'tap.f32le', 'marker-settings.json', 'trace-ready.json')
                for name in names:
                    source = f'{prefix}/{name}'
                    if source in outputs:
                        files[name] = verified_file(*capture, source)
            inputs.extend(files.values())
            if retained_window or attach_target or trial['condition'] == 'thread-state':
                tables = {schema: f'{prefix}/{schema}.xml' for schema in SCHEMAS}
                if set(tables.values()) <= earlier_outputs:
                    files['tables'] = {schema: verified_file(earlier, earlier_manifest, name)
                                       for schema, name in tables.items()}
                    inputs.extend(files['tables'].values())
                else:
                    trace = f'{prefix}/audio-system.trace'
                    members = sorted(name for name in outputs if name.startswith(trace + '/'))
                    if members:
                        inputs.extend(verified_file(*capture, name) for name in members)
                        files['trace'] = run / trace
        data.append((trial, files, log))
    details = {'case_id': case['id'], 'case_revision': case['revision'], 'analysis_revision': 8 if args.inspect_write_threads
               else 7 if previous_report is not None
               else 6 if fixed_gate
               else 5 if gate_delay and args.previous_analysis
               else 4 if args.previous_analysis else 3,
               'upstream_revision': rev,
               'capture_run': args.capture_run}
    def measure(out, execute):
        if args.inspect_write_threads:
            return inspect_write_threads(data, previous_report, case)
        result = compare_trials(out, execute, data, inspection_case, verify_write_clock=bool(args.previous_analysis))
        if previous_report is None:
            return result
        return previous_report | {'local_window_inspection': {
            'offset_bounds': bounds, 'pairs': result['paired'],
            'trials': [new for old, new in zip(previous_report['trials'], result['trials'], strict=True)
                       if old['alignment_scope'] == 'missing'],
        }}

    return record_measurement(args.run_id, case_path, inputs, details, measure, command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())

