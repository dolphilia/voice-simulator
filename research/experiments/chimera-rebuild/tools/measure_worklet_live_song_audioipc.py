"""歌唱ノード周辺のFirefoxマーカーとAudioIPCソケット操作を照合する。"""

import argparse
from collections import defaultdict
from datetime import datetime
import json
from pathlib import Path
from statistics import median
from xml.etree import ElementTree

from filter_worklet_audioipc_syscalls import field_value, filter_targets
import measure_worklet_live_song_output_callback as callback


def process_start(profile, pid):
    if any(thread['pid'] == pid for thread in profile['threads']):
        return profile['meta']['startTime']
    for child in profile.get('processes', ()):
        start = process_start(child, pid)
        if start is not None:
            return start
    return None


def marker_window(profile, trial, toc, radius):
    anchor_ms = datetime.fromisoformat(toc.findtext('.//start-date')).timestamp() * 1000
    trace_ms = float(toc.findtext('.//duration')) * 1000
    if 'timing' in trial and 'thread' in trial['timing']:
        timing = trial['timing']
    else:
        graph, = [thread for thread in callback.native.threads(profile)
                  if thread['name'] == 'GraphRunner'
                  and callback.spans(thread, callback.phases.CONSTRUCTOR_MARKER, processor=callback.shared.SONG_PROCESSOR)]
        timing = {'thread': f"{graph['name']}/{graph['pid']}"}
    ctor, graph, client, calls, center = callback.locate_callbacks(profile, timing)
    server, = [thread for thread in profile['threads'] if thread['name'] == 'AudioIPC Server Callback']
    if center < radius or center + radius >= len(calls):
        raise ValueError('歌唱ノードの構築前後に必要な要求数を取得できません')
    shift_ms = process_start(profile, client['pid']) - anchor_ms
    requests = [{'offset': index - center, 'client_start_ms': calls[index][0] + shift_ms,
                 'client_end_ms': calls[index][1] + shift_ms}
                for index in range(center - radius, center + radius + 1)]
    return (server, client), {'trace_start_ms': anchor_ms, 'trace_duration_ms': trace_ms,
                              'graph_thread': f"{graph['name']}/{graph['pid']}",
                              'constructor_ms': [value + shift_ms for value in ctor], 'requests': requests}


def io_pairs(events, outgoing_first):
    first, second = ('sendmsg', 'recvmsg') if outgoing_first else ('recvmsg', 'sendmsg')
    by_fd = defaultdict(list)
    for event in events:
        if event['syscall'] in (first, second):
            by_fd[event['fd']].append(event)
    for fd, stream in by_fd.items():
        stream.sort(key=lambda event: event['start_ns'])
        yield fd, [(a, b) for a, b in zip(stream, stream[1:]) if a['syscall'] == first and b['syscall'] == second]


def client_matches(events, calls, limits):
    for fd, pairs in io_pairs(events, outgoing_first=False):
        for index in range(len(pairs) - len(calls) + 1):
            window = pairs[index:index + len(calls)]
            offsets = [error for (read, write), call in zip(window, calls)
                       for error in (call['client_start_ms'] - read['end_ns'] / 1e6,
                                     call['client_end_ms'] - write['start_ns'] / 1e6)]
            correction = median(offsets)
            residual = max(abs(value - correction) for value in offsets)
            if (abs(correction) <= limits['maximum_trace_epoch_adjustment_ms']
                    and residual <= limits['maximum_client_clock_residual_ms']):
                yield fd, correction, residual, window


def transport_matches(events, client_window, maximum_ns):
    for fd, pairs in io_pairs(events, outgoing_first=True):
        for index in range(len(pairs) - len(client_window) + 1):
            window = pairs[index:index + len(client_window)]
            if all(server_send['bytes'] == client_receive['bytes']
                   and client_send['bytes'] == server_receive['bytes']
                   and 0 <= client_receive['end_ns'] - server_send['start_ns'] <= maximum_ns
                   and 0 <= server_receive['end_ns'] - client_send['start_ns'] <= maximum_ns
                   for (server_send, server_receive), (client_receive, client_send) in zip(window, client_window)):
                yield fd, window


def correlate(summary, server, client, limits):
    duration = min(summary['trace_duration_ms'], client['last_row_start_ns'] / 1e6)
    calls = [row for row in summary['requests'] if 0 <= row['client_start_ms'] <= row['client_end_ms'] <= duration]
    summary['covered_offsets'] = [row['offset'] for row in calls]
    summary['full_window'] = len(calls) == len(summary['requests'])
    if len(calls) < 3:
        return
    client_candidates = list(client_matches(client['completed_io'], calls, limits))
    summary['client_candidates'] = len(client_candidates)
    if len(client_candidates) != 1:
        return
    client_fd, shift, residual, client_window = client_candidates[0]
    server_candidates = list(transport_matches(server['completed_io'], client_window,
                                               limits['maximum_transport_time_ms'] * 1e6))
    summary.update(client_fd=client_fd, clock_shift_ms=shift, clock_residual_ms=residual,
                   server_candidates=len(server_candidates))
    if len(server_candidates) != 1:
        return
    server_fd, server_window = server_candidates[0]
    summary['server_fd'] = server_fd
    summary['matched'] = [{'offset': row['offset'], 'server_send': send, 'server_receive': receive,
                           'client_receive': client_receive, 'client_send': client_send}
                          for row, (send, receive), (client_receive, client_send)
                          in zip(calls, server_window, client_window)]
    by_offset = {row['offset']: row for row in summary['matched']}
    if 0 in by_offset and 1 in by_offset:
        current, following = by_offset[0], by_offset[1]
        server_interval = (following['server_send']['start_ns'] - current['server_send']['start_ns']) / 1e6
        client_interval = summary['client_interval_ms']
        summary['next_interval_ms'] = {'server_send': server_interval, 'client_callback': client_interval,
                                       'server_minus_client': server_interval - client_interval}


def add_audio_client_timing(result, source, pid):
    node, = [node for node in ElementTree.parse(source).getroot().findall('node')
             if node.find("schema[@name='audio-hal-client-io-cycle']") is not None]
    columns = [column.findtext('mnemonic') for column in node.find('schema')]
    values, cycles = {}, []
    rows = node.findall('row')
    for row in rows:
        for cell in row.iter():
            if 'id' in cell.attrib and cell.tag in ('process', 'thread', 'pid', 'tid', 'start-time', 'duration'):
                values[cell.attrib['id']] = field_value(cell, values)
        fields = dict(zip(columns, row))
        if field_value(fields['process'], values) == str(pid):
            start = int(field_value(fields['start'], values))
            duration = int(field_value(fields['duration'], values))
            cycles.append({'start_ns': start, 'end_ns': start + duration, 'tid': int(field_value(fields['thread'], values))})
    hal = {'table_rows': len(rows), 'target_pid': pid, 'target_cycles': len(cycles)}
    result['audio_client'] = hal
    if not result.get('full_window') or not result.get('matched'):
        return
    matches = []
    for request in result['matched']:
        sent = request['server_send']['start_ns']
        received = request['server_receive']['end_ns']
        options = [cycle for cycle in cycles if cycle['start_ns'] <= sent <= received <= cycle['end_ns']]
        if len(options) != 1:
            hal['unmatched_offset'] = request['offset']
            hal['candidate_cycles'] = len(options)
            return
        matches.append({'offset': request['offset'], **options[0], 'start_to_socket_send_ns': sent - options[0]['start_ns'],
                        'socket_reply_to_end_ns': options[0]['end_ns'] - received})
    if (len({row['tid'] for row in matches}) != 1
            or any(a['end_ns'] > b['start_ns'] for a, b in zip(matches, matches[1:]))):
        return
    hal['matched_cycles'] = matches
    by_offset = {row['offset']: row for row in matches}
    if 0 in by_offset and 1 in by_offset:
        interval = (by_offset[1]['start_ns'] - by_offset[0]['start_ns']) / 1e6
        hal['next_interval_ms'] = interval
        hal['interval_minus_socket_ms'] = interval - result['next_interval_ms']['server_send']


def analyze_trial(capture, export, trial, reference, limits, capture_checks_passed, clock_only=False):
    label = trial['trial']
    folder = capture / 'artifacts' / label
    profile = callback.read_json(folder / 'firefox-profile.json.gz')
    toc = ElementTree.parse(export / label / 'toc.xml')
    threads, model = marker_window(profile, trial, toc, limits['window_radius_requests'])
    by_offset = {row['offset']: row for row in model['requests']}
    interval = by_offset[1]['client_start_ms'] - by_offset[0]['client_start_ms']
    model.update(trial=label, capture_checks_passed=capture_checks_passed,
                 client_interval_ms=interval,
                 instrumentation_increase_ms={'constructor': model['constructor_ms'][1] - model['constructor_ms'][0]
                                              - reference['constructor'],
                                              'next_interval': interval - reference['next_interval']})
    model['timing_comparable'] = all(value <= limits['maximum_instrumentation_increase_ms']
                                     for value in model['instrumentation_increase_ms'].values())
    clock = callback.read_json(folder / 'trace-release.json')
    model['notice_to_trace_start_ms'] = model['trace_start_ms'] - clock['trace_notice_epoch_ns'] / 1e6
    model['release_from_trace_start_ms'] = clock['release_epoch_ns'] / 1e6 - model['trace_start_ms']
    targets = [(thread['pid'], thread['tid']) for thread in threads]
    model['targets'] = dict(zip(('server', 'client'), targets))
    if not clock_only:
        server, client, server_process, client_process = filter_targets(
            export / label / 'syscall.xml', targets + [(pid, None) for pid, _ in targets])
        model['syscall_counts'] = {'server': server['syscalls'], 'client': client['syscalls']}
        model['process_io'] = {role: [event for event in process['completed_io']
                                     if event['syscall'] in ('sendmsg', 'recvmsg')]
                               for role, process in (('server', server_process), ('client', client_process))}
        model['process_syscall_rows'] = {'server': sum(server_process['syscalls'].values()),
                                         'client': sum(client_process['syscalls'].values())}
        model['syscall_rows'] = client['table_rows']
        if client['last_row_start_ns'] is not None:
            correlate(model, server, client, limits)
        hal = export / label / 'audio-hal.xml'
        if hal.is_file():
            model['audio_hal_rows'] = sum(element.tag == 'row' for _, element
                                          in ElementTree.iterparse(hal, events=('end',)))
        audio_client = export / label / 'audio-client.xml'
        if audio_client.is_file():
            add_audio_client_timing(model, audio_client, targets[0][0])
    return model


def analyze(capture, export, baseline, limits, clock_only):
    capture_summary = callback.read_json(capture / 'summary.json')
    results = []
    for trial in capture_summary['trials']:
        label = trial['trial']
        checks = [value for name, value in capture_summary['checks'].items() if name.startswith(f'{label}/')]
        results.append(analyze_trial(capture, export, trial, baseline[label], limits, bool(checks) and all(checks),
                                     clock_only))
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capture', type=Path)
    parser.add_argument('exports', type=Path)
    parser.add_argument('--clock-only', action='store_true')
    args = parser.parse_args()
    root = callback.song.WORKSPACE
    limits = callback.read_json(root / 'cases/worklet-live-song-audioipc.json')['analysis']
    centered = callback.read_json(root / 'cases/worklet-live-song-audioipc-system-centered.json')
    original = callback.read_json(root / 'cases' / centered['previous_gated_case'])
    limits.update(centered['correlation'])
    prior = root / 'runs' / original['comparison_run']
    baseline = {}
    for trial in callback.read_json(prior / 'summary.json')['trials']:
        profile = callback.read_json(prior / 'artifacts' / trial['trial'] / 'firefox-profile.json.gz')
        ctor, _, _, calls, i = callback.locate_callbacks(profile, trial['timing'])
        baseline[trial['trial']] = {'constructor': ctor[1] - ctor[0], 'next_interval': calls[i + 1][0] - calls[i][0]}
    print(json.dumps(analyze(args.capture, args.exports, baseline, limits, args.clock_only), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
