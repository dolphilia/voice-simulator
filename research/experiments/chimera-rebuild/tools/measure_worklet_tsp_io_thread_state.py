"""FirefoxのI/Oスレッドの状態をCore Audioの出力周期へ対応付ける。"""

import argparse
from collections import Counter
import csv
from pathlib import Path
import subprocess
import sys
from xml.etree import ElementTree

from measure_csd_envelope_timing import verified_file
from measure_safari_audio_client_trace import read_cycles
from measure_speech_timing import read
from measure_tsp_listening import hydrate_run, snapshot_case
from measure_uniform_tube import record_measurement
from measure_worklet_fixed import ROOT
from measure_worklet_tsp_device_io import CLIENT, HARDWARE, SERVER, XCTRACE, server_rows, trace_origin, trace_rows
from measure_worklet_tsp_io_client_start import IOPROC, START, index_starts, ioproc_rows
from measure_worklet_tsp_io_deadline import FILES, cubeb_window, rejoin, server_slot
from upstream_baseline import WORKSPACE


CASE = WORKSPACE / 'cases/worklet-live-tsp-firefox-io-thread-state.json'
STATE = 'thread-state'
SCHEMAS = (STATE, START, IOPROC)


def export_tables(trace, folder, execute):
    folder.mkdir()
    paths = {}
    for schema in SCHEMAS:
        path = folder / f'{schema}.xml'
        execute([*XCTRACE, 'export', '--input', str(trace),
                 '--xpath', f'/trace-toc/run/data/table[@schema="{schema}"]', '--output', str(path)])
        paths[schema] = path
    return paths


def state_rows(path, pid, tid):
    states = []
    for row in trace_rows(path, STATE):
        if row['process'] != str(pid) or row['thread'] != str(tid):
            continue
        start, duration = int(row['start']), int(row['duration'])
        if duration > 0:
            states.append({'start_ns': start, 'end_ns': start + duration, 'state': row['state'],
                           'core': row['core'], 'priority': row['priority']})
    return sorted(states, key=lambda row: row['start_ns'])


def coverage(states, start, end):
    durations = Counter()
    rows = []
    missing = []
    edge = start
    overlap = 0
    for row in states:
        left = max(start, row['start_ns'])
        right = min(end, row['end_ns'])
        if left >= right:
            continue
        if left > edge:
            missing.append([edge, left])
        overlap += max(0, min(edge, right) - left)
        edge = max(edge, right)
        durations[row['state']] += right - left
        rows.append(row | {'slice_start_ns': left, 'slice_end_ns': right})
    if edge < end:
        missing.append([edge, end])
    return {'states': rows, 'duration_by_state_ns': dict(durations), 'uncovered_intervals_ns': missing,
            'overlap_ns': overlap}


def classify(covered, procs, *, previous_run_tail_ns=0):
    durations = covered['duration_by_state_ns']
    if procs:
        return 'ioproc_observed'
    if covered['uncovered_intervals_ns'] or covered['overlap_ns'] or durations.get('Unknown'):
        return 'state_coverage_incomplete'
    if previous_run_tail_ns and durations.get('Running') == previous_run_tail_ns and set(durations) == {'Running', 'Blocked'}:
        return 'blocked_after_previous_run'
    if durations.get('Running'):
        return 'running_without_ioproc'
    if durations.get('Runnable') or durations.get('Preempted'):
        return 'runnable_without_running'
    if set(durations) == {'Blocked'}:
        return 'blocked_through_period'
    return 'other_state_without_ioproc'


def describe_request(index, offset, joined, state, io, starts, config, io_config, tick_ns):
    blocks, _, client, server, server_cycles, _ = joined
    left = client['cycles'][index]
    current, following = blocks[index:index + 2]
    frames = config['request_frames']
    period = frames * 1e9 / config['sample_rate_hz']
    gap = following['sample_time'] - current['sample_time'] - current['frames']
    if gap < 0 or gap % frames or current['frames'] != frames:
        raise ValueError('出力要求に合わない予定サンプル差です')
    first = server[index]
    previous_end = left['start_ns'] + left['duration_ns']
    returned = round(current['returned'] * tick_ns)
    entered = round(current['entered'] * tick_ns)
    slots = []
    tolerance_ns = io_config['maximum_server_host_error_ms'] * 1e6
    for slot in range(1, max(1, int(gap) // frames) + 1):
        middle = server_slot(first, server_cycles, slot, period, frames, tick_ns, tolerance_ns)
        after = server_slot(first, server_cycles, slot + 1, period, frames, tick_ns, tolerance_ns)
        begin, end = middle['start_ns'], after['start_ns']
        check_start = max(begin, previous_end)
        markers = [when for when, host in starts[middle['output_sample_time']]
                   if abs(host - middle['host_ticks']) * tick_ns <= tolerance_ns]
        procs = [event for event in io if begin <= event['start_ns'] < end]
        after_procs = [event for event in procs if event['start_ns'] >= check_start]
        observed = coverage(state, begin, end)
        after_previous = coverage(state, check_start, end) if check_start < end else None
        tail = 0
        if previous_end >= begin and after_previous and after_previous['states']:
            carrying = after_previous['states'][0]
            if carrying['state'] == 'Running' and carrying['start_ns'] < previous_end == carrying['slice_start_ns']:
                tail = carrying['slice_end_ns'] - previous_end
        slots.append({'slot': slot, 'server_start_ns': begin, 'server_end_ns': end,
                      'server_client_starts_ns': markers, 'ioproc_starts_in_period': procs,
                      'preceding_states': coverage(state, begin - config['pre_cycle_ns'], begin),
                      'states_in_period': observed, 'states_after_previous_client_end': after_previous,
                      'previous_client_end_minus_server_start_ns': previous_end - begin,
                      'previous_run_tail_ns': tail,
                      'classification_after_previous_client_end':
                          classify(after_previous, after_procs, previous_run_tail_ns=tail)
                          if after_previous is not None else 'previous_client_spans_period'})
    return {'request_offset': offset, 'gap_frames': int(gap), 'callback_ns': returned - entered,
            'client_duration_ns': left['duration_ns'], 'within_budget': max(returned - entered, left['duration_ns']) <= period,
            'server_period_ns': period, 'slots': slots}


def full_alignment(trial):
    return {'client_io', 'server_io'} <= trial.get('system_io', {}).keys()


def trial_states(t, paths, config, io_config, out, execute):
    data = t['device']
    selected, = data['matched_streams']
    tick_ns = data['host_tick_ms'] * 1e6
    local = config.get('local_onset_offsets') if not full_alignment(t) else None
    joined = rejoin(selected, data, t['system_io'], tick_ns, io_config, paths, offset_bounds=local)
    tables = paths['tables'] if 'tables' in paths else export_tables(paths['trace'], out, execute)
    _, _, client, server, _, _ = joined
    pid, tid = t['system_io']['pid'], client['tid']
    states = state_rows(tables[STATE], pid, tid)
    starts = index_starts(tables[START], server[0]['tid'])
    procs = list(ioproc_rows(tables[IOPROC], pid, tid))
    indices = {row['offset']: i for i, row in enumerate(data['graph_rows'])}
    offsets = config['request_offsets']
    if local:
        indices = {offset: i for i, offset in enumerate(range(local[0], local[1] + 1))}
    else:
        offsets = [config['positive_control_offset'], *offsets]
    speech = {r['offset']: r['speech_output_frames'] for r in t['device_onset_requests']}
    onset, = (offset for offset, values in speech.items() if 0 in values)
    requests = [describe_request(indices[k], k, joined, states, procs, starts, config, io_config, tick_ns)
                | {'contains_first_speech_quantum': k == onset} for k in offsets]
    period_error_ns = config['maximum_server_interval_error_ms'] * 1e6
    report = {'pid': pid, 'tid': tid, 'thread_state_rows': len(states), 'ioproc_rows': len(procs),
            'requests': requests, 'checks': {
                'matched_thread_has_state_records': bool(states),
                'speech_onset_within_registered_window': onset in config['request_offsets'],
                'server_client_starts_unique': all(len(s['server_client_starts_ns']) == 1 for r in requests for s in r['slots']),
                'server_period_within_tolerance': all(
                    abs(s['server_end_ns'] - s['server_start_ns'] - r['server_period_ns']) <= period_error_ns
                    for r in requests for s in r['slots']),
                'continuous_ioproc_has_running_state': all(
                    s['ioproc_starts_in_period'] and s['states_in_period']['duration_by_state_ns'].get('Running', 0) > 0
                    for r in requests if not r['gap_frames'] for s in r['slots'])}}
    if 'local_onset_offsets' in config:
        report['alignment_scope'] = 'onset' if local else 'full'
        report['server_tid'] = server[0]['tid']
        report['checks']['all_onset_quanta_in_registered_window'] = set(speech) <= set(config['request_offsets'])
        for request in requests:
            offset = request['request_offset']
            request['speech_onset_frames'] = speech.get(offset, [])
            request['intervening_client_cycles'] = client['unmatched_cycles_between'][indices[offset]]
    return report


def trace_table_extent(starts_and_ends):
    first, last = None, None
    for start, end in starts_and_ends:
        first = start if first is None else min(first, start)
        last = end if last is None else max(last, end)
    return first, last


def acquisition_timing(trial, paths, io_config, *, include_starts=False):
    data = trial.get('device', {})
    result = {'whole_window_aligned': full_alignment(trial),
              'constructor_marker_frame': data.get('center_graph_marker_frame')}
    if paths is None:
        return result
    stream, = data['matched_streams']
    blocks = cubeb_window(stream, data, paths)
    indices = {row['offset']: i for i, row in enumerate(data['graph_rows'])}
    pid = trial['system_io']['pid']
    client_path = paths.get(CLIENT + '.xml')
    clients, _ = read_cycles(client_path, pid, include_overloads=True) if client_path else ([], 0)
    toc = paths['io-toc.xml']
    duration = ElementTree.parse(toc).findtext('.//duration')
    extents = {}
    if client_path:
        extents[CLIENT] = trace_table_extent(
            (int(r['start']), int(r['start']) + int(r['duration']))
            for r in trace_rows(client_path, CLIENT) if r['start'] and r['duration'])
    for schema in (SERVER, HARDWARE):
        if path := paths.get(schema + '.xml'):
            rows = server_rows(path, schema, intervals=True)
            extents[schema] = trace_table_extent((r['start_ns'], r['start_ns'] + r['duration_ns']) for r in rows)
    result['trace_duration_ns'] = round(float(duration) * 1e9)
    result['table_last_end_ns'] = {schema: latest for schema, (_, latest) in extents.items()}
    clock = trace_origin(paths['trace-clock.json'].parent, toc)
    tick_ns = data['host_tick_ms'] * 1e6
    samples = [(r['offset'], indices[r['offset']]) for r in trial['device_onset_requests']]
    targets = {off: round(blocks[i]['entered'] * tick_ns) - clock for off, i in samples}
    last_return = round(blocks[-1]['returned'] * tick_ns) - clock
    if include_starts:
        result['table_first_start_ns'] = {schema: first for schema, (first, _) in extents.items()}
        result['trace_origin_mach_ns'] = clock
        result['onset_cubeb_entry_trace_ns'] = targets
        result['cubeb_full_window_trace_ns'] = [round(blocks[0]['entered'] * tick_ns) - clock, last_return]
    if not clients:
        return result
    last = max(c['start_ns'] + c['duration_ns'] for c in clients)
    result.update(client_last_end_ns=last,
                  onset_entry_to_client_last_end_ns={off: last - start for off, start in targets.items()},
                  full_window_last_return_to_client_last_end_ns=last - last_return,
                  estimated_origin_error_ns=round(io_config['maximum_trace_origin_error_ms'] * 1e6))
    return result


def measure(out, execute, trials, config, io_config, reference_trials=()):
    observations = []
    checks = {}
    for t, paths in trials:
        label = f"{t['pair']}-{t['condition']}"
        try:
            if paths is None:
                raise ValueError('収録内でブラウザとサーバーのI/Oを照合できません')
            result = trial_states(t, paths, config, io_config, out / label, execute)
        except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
            result = {'requests': [], 'checks': {'scheduler_alignment_available': False}, 'error': str(error)}
        if 'local_onset_offsets' in config:
            result['acquisition'] = acquisition_timing(t, paths, io_config)
            expected_frames = config['candidate_ready_quanta'] * config['worklet_quantum_frames']
            result['checks']['constructor_at_registered_marker_frame'] = (
                result['acquisition']['constructor_marker_frame'] == expected_frames)
        observations.append({'pair': t['pair'], 'condition': t['condition'], **result})
        checks.update({f'{label}/{key}': value for key, value in result['checks'].items()})
    by_request = [(t, req) for t in observations for req in t['requests']]
    onset = [r for _, r in by_request if r['contains_first_speech_quantum']]
    missing_onset = [r for r in onset if r['gap_frames']]
    within = [r for r in missing_onset if r['within_budget']]
    controls = [r for _, r in by_request if r['request_offset'] == config['positive_control_offset']]
    totals = {'onset_requests': len(onset), 'onset_gaps': len(missing_onset), 'onset_gaps_within_budget': len(within),
              'onset_gaps_within_budget_states': dict(Counter(
                  s['classification_after_previous_client_end'] for r in within for s in r['slots'])),
              'construction_gaps': sum(r['gap_frames'] > 0 for r in controls)}
    with (out / 'slot-states.csv').open('w', newline='') as stream:
        fields = ['pair', 'condition', 'request_offset', 'slot', 'state', 'start_relative_ns', 'end_relative_ns']
        writer = csv.DictWriter(stream, fields)
        writer.writeheader()
        for t, r in by_request:
            for slot in r['slots']:
                origin = slot['server_start_ns']
                for item in slot['states_in_period']['states']:
                    writer.writerow({'pair': t['pair'], 'condition': t['condition'], 'request_offset': r['request_offset'],
                                     'slot': slot['slot'], 'state': item['state'],
                                     'start_relative_ns': item['slice_start_ns'] - origin,
                                     'end_relative_ns': item['slice_end_ns'] - origin})
    report = {'checks': checks, 'totals': totals, 'trials': observations}
    if 'local_onset_offsets' in config:
        all_onset = [r for _, r in by_request if r['speech_onset_frames']]
        totals.update(full_windows=sum(t['acquisition']['whole_window_aligned'] for t in observations),
                      local_windows=sum(t.get('alignment_scope') == 'onset' for t in observations),
                      onset_quantum_requests=len(all_onset),
                      onset_quantum_request_gaps=sum(r['gap_frames'] > 0 for r in all_onset),
                      onset_quantum_request_gaps_within_budget=sum(
                          bool(r['gap_frames'] and r['within_budget'] and not r['intervening_client_cycles'])
                          for r in all_onset))
        report['reference_acquisition'] = [dict(pair=t['pair'], **acquisition_timing(t, paths, io_config))
                                           for t, paths in reference_trials]
    return report


def trial_files(capture, trial, *, allow_missing_tables=False):
    if 'pid' not in trial.get('system_io', {}):
        return None
    missing = {schema + '.xml' for schema in trial['system_io'].get('missing_trace_tables', [])}
    if missing and not allow_missing_tables:
        return None
    prefix = f"artifacts/{trial['pair']}-{trial['condition']}"
    stream, = trial['device']['matched_streams']
    files = {name: verified_file(*capture, f'{prefix}/{name}') for name in FILES if name not in missing}
    files['blocks.csv'] = verified_file(*capture, f'{prefix}/{stream}/blocks.csv')
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('--case', type=Path, default=CASE)
    args = parser.parse_args()
    case = args.case.resolve()
    config = read(case)
    revision = config['upstream_revision']
    run = WORKSPACE / 'runs' / config['capture_run']
    manifest = read(run / 'manifest.json')
    if (manifest['run_id'], manifest['case_id'], manifest['upstream_revision']) != (
            config['capture_run'], config['capture_case'], revision):
        parser.error('登録された収録とマニフェストが一致しません')
    capture = run, manifest
    source_case = snapshot_case(capture, config['capture_case'])
    source = read(source_case)
    io_config = source['system_io']
    captured = verified_file(*capture, 'summary.json')
    reference = hydrate_run(config['reference_run'], 'worklet-live-tsp-firefox-io-client-start', revision)
    inputs = [case, Path(__file__).resolve(), source_case, captured, capture[0] / 'manifest.json',
              reference[0] / 'manifest.json', verified_file(*reference, 'summary.json'),
              *(WORKSPACE / 'tools' / name for name in ('measure_worklet_tsp_io_deadline.py',
                  'measure_worklet_tsp_io_client_start.py', 'measure_worklet_tsp_device_io.py',
                  'measure_cubeb_output_callback.py', 'measure_safari_audio_client_trace.py',
                  'filter_worklet_audioipc_syscalls.py', 'measure_uniform_tube.py'))]
    reference_trials = []
    if 'reference_capture_run' in config:
        earlier = WORKSPACE / 'runs' / config['reference_capture_run']
        earlier_manifest = read(earlier / 'manifest.json')
        if (earlier_manifest['run_id'], earlier_manifest['case_id'], earlier_manifest['upstream_revision']) != (
                config['reference_capture_run'], config['reference_capture_case'], revision):
            parser.error('参照収録とマニフェストが一致しません')
        earlier_capture = earlier, earlier_manifest
        reference_case = snapshot_case(earlier_capture, config['reference_capture_case'])
        older = read(reference_case)
        old_capture = older['capture'].copy()
        new_capture = source['capture'].copy()
        if (old_capture.pop('marker_ready_quanta') != config['reference_ready_quanta']
                or new_capture.pop('marker_ready_quanta') != config['candidate_ready_quanta']
                or old_capture != new_capture or older['system_io'] != io_config
                or earlier_manifest['firefox_xul_sha256'] != manifest['firefox_xul_sha256']):
            parser.error('先行音の準備時間を比較するための共通条件が一致しません')
        earlier_results = verified_file(*earlier_capture, 'summary.json')
        earlier_analysis = WORKSPACE / 'runs' / config['reference_analysis_run']
        analysis_manifest = read(earlier_analysis / 'manifest.json')
        if analysis_manifest.get('capture_run') != config['reference_capture_run']:
            parser.error('登録した参照解析と参照収録が一致しません')
        inputs += [reference_case, earlier_results, earlier / 'manifest.json',
                   earlier_analysis / 'manifest.json', verified_file(earlier_analysis, analysis_manifest, 'summary.json')]
        for trial in read(earlier_results)['trials']:
            paths = trial_files(earlier_capture, trial)
            if paths:
                inputs += list(paths.values())
            reference_trials.append((trial, paths))
    prior_run = None
    if earlier := config.get('previous_analysis_run'):
        original = WORKSPACE / 'runs' / earlier
        prior = read(original / 'manifest.json')
        if (prior['run_id'], prior['case_id'], prior['upstream_revision']) != (earlier, config['id'], revision):
            parser.error('前版の解析記録が一致しません')
        inputs += [original / 'manifest.json', verified_file(original, prior, 'summary.json')]
        if prior.get('capture_run') == config['capture_run']:
            prior_run = original, prior
    prior_outputs = {row['path'] for row in prior_run[1]['outputs']} if prior_run else set()
    trials = []
    for t in read(captured)['trials']:
        if not full_alignment(t) and 'local_onset_offsets' not in config:
            trials.append((t, None))
            continue
        paths = trial_files(capture, t)
        if paths is None:
            trials.append((t, None))
            continue
        prefix = f"artifacts/{t['pair']}-{t['condition']}"
        inputs += list(paths.values())
        tables = {schema: f'{prefix}/{schema}.xml' for schema in SCHEMAS}
        if set(tables.values()) <= prior_outputs:
            paths['tables'] = {schema: verified_file(*prior_run, name) for schema, name in tables.items()}
            inputs += list(paths['tables'].values())
            trials.append((t, paths))
            continue
        trace = f'{prefix}/audio-system.trace'
        members = [row['path'] for row in capture[1]['outputs'] if row['path'].startswith(trace + '/')]
        if not members:
            parser.error(f'元のトレースのマニフェストがありません ({trace})')
        inputs += [verified_file(*capture, name) for name in members]
        paths['trace'] = capture[0] / trace
        trials.append((t, paths))
    details = {'case_id': config['id'], 'case_revision': config['revision'], 'upstream_revision': revision,
               'capture_run': config['capture_run'], 'analysis_command': [sys.executable, *sys.argv],
               'analysis_directory': str(Path.cwd())}
    return record_measurement(args.run_id, case, inputs, details, lambda out, execute: measure(
        out, execute, trials, config, io_config, reference_trials), command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
