"""確認用07のcubebコールバックとCore Audioトレースを同じ要求で照合する。"""

from bisect import bisect_left, bisect_right
import argparse
from collections import defaultdict
from datetime import datetime
import json
from pathlib import Path
import subprocess
import sys
import time
from xml.etree import ElementTree

from capture_worklet_system_pair import darwin_notification, recording
from filter_worklet_audioipc_syscalls import field_value
from measure_cubeb_output_callback import load_blocks
from measure_safari_audio_client_trace import read_cycles
from measure_worklet_live_song_process_tap import await_file


TOOL = Path(__file__).resolve()
CLIENT = 'audio-hal-client-io-cycle'
SERVER = 'audio-hal-io-cycle-client'
HARDWARE = 'audio-hal-io-cycle-hardware'
XCTRACE = ('/usr/bin/xcrun', 'xctrace')


def capture_io(execute, folder, settings):
    def run(command, **options):
        gate = []
        if settings.get('attach_firefox') or settings.get('compare_attach_target') or settings.get('compare_stdout_release_delay_ms'):
            gate = ['--wait-for-ready', 'trace-target.json']
        elif settings.get('wait_for_browser_ready'):
            gate = ['--wait-for-ready', 'trace-ready.json']
        elif settings.get('wait_for_tap_ready'):
            gate = ['--wait-for-ready', 'trace-tap-ready.json']
        window = ['--window', settings['window']] if settings.get('window') else []
        attach = ['--attach-firefox'] if settings.get('attach_firefox') else []
        audit = ['--observe-start-signals'] if settings.get('observe_start_signals') else []
        delay = ['--stdout-delay-ms', str(settings['stdout_release_delay_ms'])] if 'stdout_release_delay_ms' in settings else []
        return execute([sys.executable, str(TOOL), *gate, *window, *attach, *audit, *delay, str(folder), settings['time_limit'],
                        *settings['instruments'], '--', *command], **options)
    return run


def record_trace_clock(folder):
    before = time.monotonic_ns()
    epoch_ns = time.time_ns()
    after = time.monotonic_ns()
    (folder / 'trace-clock.json').write_text(json.dumps({'epoch_ns': epoch_ns, 'monotonic_before_ns': before,
                                                        'monotonic_after_ns': after,
                                                        'clock_source': time.get_clock_info('monotonic').implementation}) + '\n')


def record(folder, limit, instruments, command, *, ready_file=None, window=None, attach_firefox=False,
           audit_start_signals=False, stdout_release_delay_ms=None):
    args = [arg for instrument in instruments for arg in ('--instrument', instrument)]
    source = time.get_clock_info('monotonic').implementation
    if source != 'mach_absolute_time()':
        raise ValueError('単調時計の単位をMachの時刻に対応付けられません')
    settings = {'time_limit': limit, 'instruments': instruments, 'window': window, 'ready_file': ready_file}
    settings_path = folder / 'trace-recording-settings.json'
    settings_path.write_text(json.dumps(settings, ensure_ascii=False) + '\n')
    if attach_firefox and ready_file != 'trace-target.json':
        raise ValueError('アタッチには計測用FirefoxのPIDが必要です')
    if audit_start_signals and ready_file is None:
        raise ValueError('開始時刻の同時観測には再生前の準備通知が必要です')
    if stdout_release_delay_ms is not None:
        if stdout_release_delay_ms < 0 or not audit_start_signals:
            raise ValueError('標準出力からの待ち時間と開始通知の観測が必要です')
        settings['stdout_release_delay_ms'] = stdout_release_delay_ms
    if ready_file:
        with subprocess.Popen(command) as browser:
            try:
                if not await_file(folder / ready_file, browser, time.monotonic() + 30):
                    raise ValueError(f'準備通知を受け取れません: {ready_file}')
                attach_pid = None
                if ready_file == 'trace-target.json':
                    pid = json.loads((folder / ready_file).read_text())['firefox_pid']
                    if type(pid) is not int or pid <= 0:
                        raise ValueError('計測用FirefoxのPIDが不正です')
                    attach_pid = pid if attach_firefox else None
                    settings.update(firefox_pid=pid, attach_pid=attach_pid)
                    settings_path.write_text(json.dumps(settings, ensure_ascii=False) + '\n')
                with (darwin_notification() as notification,
                      recording(folder, args, limit, notification, window=window, attach_pid=attach_pid,
                                audit_start_signals=audit_start_signals,
                                stdout_release_delay_ms=stdout_release_delay_ms) as (_, started)):
                    record_trace_clock(folder)
                    ready = {'trace_notice_monotonic_ns': started}
                    if stdout_release_delay_ms is not None:
                        ready['release_source'] = 'stdout-delayed'
                    (folder / 'system-trace-ready.json').write_text(json.dumps(ready) + '\n')
                return browser.wait(timeout=45)
            finally:
                if browser.poll() is None:
                    browser.terminate()
    with recording(folder, args, limit, window=window):
        record_trace_clock(folder)
        browser = subprocess.run(command)
    return browser.returncode


def trace_origin(folder, toc):
    start = ElementTree.parse(toc).findtext('.//start-date')
    trace_epoch = round(datetime.fromisoformat(start).timestamp() * 1e9)
    clock = json.loads((folder / 'trace-clock.json').read_text())
    return trace_epoch - clock['epoch_ns'] + (clock['monotonic_before_ns'] + clock['monotonic_after_ns']) // 2


def matching_client_cycles(blocks, cycles, origin, tick_ns, settings):
    pad = round(settings['maximum_client_padding_ms'] * 1e6)
    origin_error = round(settings['maximum_trace_origin_error_ms'] * 1e6)
    interval_error = round(settings['maximum_client_interval_error_ms'] * 1e6)
    entries = [round(row['entered'] * tick_ns) for row in blocks]
    returns = [round(row['returned'] * tick_ns) for row in blocks]
    threads = defaultdict(list)
    for row in cycles:
        threads[row['tid']].append(row)
    matches = []
    for tid, events in threads.items():
        events.sort(key=lambda row: row['start_ns'])
        starts = [row['start_ns'] for row in events]
        first_expected = entries[0] - origin
        first_candidates = starts[bisect_left(starts, first_expected - origin_error - pad):
                                  bisect_right(starts, first_expected + origin_error + pad)]
        for candidate in first_candidates:
            targets = [candidate + value - entries[0] for value in entries]
            positions = [bisect_left(starts, target - interval_error) for target in targets]
            limits = [bisect_right(starts, target + interval_error) for target in targets]
            if (any(hi != lo + 1 for lo, hi in zip(positions, limits, strict=True))
                    or any(a >= b for a, b in zip(positions, positions[1:]))):
                continue
            selected = [events[i] for i in positions]
            endpoints = [row['start_ns'] + row['duration_ns'] for row in selected]
            lower = max(origin - origin_error,
                        *(returned - end for returned, end in zip(returns, endpoints, strict=True)),
                        *(entry - start - pad for entry, start in zip(entries, (r['start_ns'] for r in selected), strict=True)))
            upper = min(origin + origin_error,
                        *(entry - start for entry, start in zip(entries, (r['start_ns'] for r in selected), strict=True)),
                        *(returned - end + pad for returned, end in zip(returns, endpoints, strict=True)))
            if lower > upper:
                continue
            matches.append({'tid': tid, 'origin_range_ns': [lower, upper], 'cycles': selected,
                            'unmatched_cycles_between': [b - a - 1 for a, b in zip(positions, positions[1:])]})
    return matches


def trace_rows(source, schema):
    node, = (n for n in ElementTree.parse(source).getroot().findall('node')
             if n.find(f"schema[@name='{schema}']") is not None)
    columns = [column.findtext('mnemonic') for column in node.find('schema')]
    values = {}
    for row in node.findall('row'):
        for cell in row.iter():
            if 'id' in cell.attrib:
                values[cell.attrib['id']] = field_value(cell, values)
        yield {column: field_value(cell, values) for column, cell in zip(columns, row, strict=True)}


def server_rows(source, schema, *, intervals=False):
    for fields in trace_rows(source, schema):
        timing = {'duration_ns': int(fields['duration'])} if intervals else {}
        if schema == SERVER and fields['output-host-time'] and fields['thread']:
            yield {'tid': int(fields['thread']), 'client_pid': fields['client-process'],
                   'start_ns': int(fields['start']), 'host_ticks': int(fields['output-host-time']),
                   'output_sample_time': int(fields['output-sample-time']), **timing}
        if schema == HARDWARE and fields['operation'] == 'Write':
            if intervals:
                timing.update(engine_id=fields['engine-id'], current_host_ticks=int(fields['current-host-time']))
            yield {'tid': int(fields['thread']), 'stream_index': int(fields['stream-index']),
                   'start_ns': int(fields['start']), 'start_sample_time': int(fields['start-sample-time']),
                   'frames': int(fields['frame-length']), **timing}


def match_server(blocks, rows, pid, tick_ns, tolerance_ms):
    by_thread = defaultdict(list)
    for row in rows:
        if row['client_pid'] in (None, str(pid)):
            by_thread[row['tid']].append(row)
    bound = tolerance_ms * 1e6 / tick_ns
    matches = []
    for tid, events in by_thread.items():
        events.sort(key=lambda event: event['host_ticks'])
        ticks = [event['host_ticks'] for event in events]
        positions = [bisect_left(ticks, row['host_time'] - bound) for row in blocks]
        limits = [bisect_right(ticks, row['host_time'] + bound) for row in blocks]
        if (any(hi != lo + 1 for lo, hi in zip(positions, limits, strict=True))
                or any(a >= b for a, b in zip(positions, positions[1:]))):
            continue
        matches.append({'tid': tid, 'cycles': [events[i] for i in positions],
                        'server_client_cycles_between': [events[a + 1:b] for a, b in zip(positions, positions[1:])]})
    return matches


def inspect_io(folder, output, settings, execute):
    result = {}
    if not output['valid']:
        return {'io_device_window_available': False}, result
    trace, toc = folder / 'audio-system.trace', folder / 'io-toc.xml'
    execute([*XCTRACE, 'export', '--input', str(trace), '--toc', '--output', str(toc)])
    schemas = {row.get('schema') for row in ElementTree.parse(toc).findall('.//table')}
    tables = {}
    for name in (CLIENT, SERVER, HARDWARE):
        if name not in schemas:
            continue
        tables[name] = folder / f'{name}.xml'
        execute([*XCTRACE, 'export', '--input', str(trace), '--xpath', f'/trace-toc/run/data/table[@schema="{name}"]',
                 '--output', str(tables[name])])
    recorded = output['matched_streams'][0]
    pid = int(Path(recorded).name.split('-')[2])
    if settings.get('compare_attach_target') or settings.get('compare_stdout_release_delay_ms') or len(tables) != 3:
        result.update(pid=pid, trace_tables_available=list(tables),
                      missing_trace_tables=[name for name in (CLIENT, SERVER, HARDWARE) if name not in tables],
                      thread_state_table_available='thread-state' in schemas)
    if len(tables) != 3:
        if CLIENT in tables:
            cycles, rows = read_cycles(tables[CLIENT], pid, include_overloads=True)
            result.update(client_table_rows=rows, client_pid_cycles=len(cycles))
        return {'io_trace_tables_available': False}, result
    window = output['streams'][recorded]
    raw = load_blocks(folder / recorded)
    block_indices = [row['block_index'] for row in window['intervals']]
    indices = [*block_indices, block_indices[-1] + 1]
    blocks = [raw[i] for i in indices]
    tick_ns = output['host_tick_ms'] * 1e6
    origin = trace_origin(folder, toc)
    cycles, rows = read_cycles(tables[CLIENT], pid, include_overloads=True)
    candidates = matching_client_cycles(blocks, cycles, origin, tick_ns, settings)
    server = match_server(blocks, list(server_rows(tables[SERVER], SERVER)), pid, tick_ns,
                          settings['maximum_server_host_error_ms'])
    result.update({'pid': pid, 'client_table_rows': rows, 'client_pid_cycles': len(cycles),
                   'client_candidate_count': len(candidates), 'server_candidate_count': len(server)})
    if len(candidates) != 1:
        return {'unique_client_io_window': False}, result
    client, = candidates
    result['client_io'] = client
    if len(server) == 1:
        result['server_io'] = server[0]
        hardware = list(server_rows(tables[HARDWARE], HARDWARE))
    gaps = []
    for i, row in enumerate(window['intervals']):
        if not row['sample_time_gap_frames']:
            continue
        a, b = client['cycles'][i:i + 2]
        observed = (b['start_ns'] - a['start_ns']) / 1e6
        gap = row | {'client_io_start_interval_ms': observed,
                     'client_minus_cubeb_entry_interval_ms': observed - row['entry_interval_ms'],
                     'client_io_idle_until_next_ms': (b['start_ns'] - a['start_ns'] - a['duration_ns']) / 1e6,
                     'intervening_client_cycles': client['unmatched_cycles_between'][i],
                     'request_offset': window['request_alignment'][i]['request_offset']}
        if len(server) == 1:
            sa, sb = server[0]['cycles'][i:i + 2]
            gap['intervening_server_client_cycles'] = server[0]['server_client_cycles_between'][i]
            gap['server_write_cycles'] = [h for h in hardware if h['tid'] == server[0]['tid']
                                          and sa['start_ns'] <= h['start_ns'] < sb['start_ns']]
        gaps.append(gap)
    result['gaps'] = gaps
    return {'unique_client_io_window': True}, result


if __name__ == '__main__':
    args = sys.argv[1:]
    separator = args.index('--')
    parser = argparse.ArgumentParser(description=__doc__)
    gate = parser.add_mutually_exclusive_group()
    gate.add_argument('--wait-for-ready', dest='ready_file')
    gate.add_argument('--wait-for-tap-ready', dest='ready_file', action='store_const', const='trace-tap-ready.json')
    parser.add_argument('--window')
    parser.add_argument('--attach-firefox', action='store_true')
    parser.add_argument('--observe-start-signals', action='store_true')
    parser.add_argument('--stdout-delay-ms', type=int)
    parser.add_argument('folder', type=Path)
    parser.add_argument('limit')
    parser.add_argument('instruments', nargs='+')
    options = parser.parse_args(args[:separator])
    raise SystemExit(record(options.folder, options.limit, options.instruments, args[separator + 1:],
                            ready_file=options.ready_file, window=options.window, attach_firefox=options.attach_firefox,
                            audit_start_signals=options.observe_start_signals,
                            stdout_release_delay_ms=options.stdout_delay_ms))
