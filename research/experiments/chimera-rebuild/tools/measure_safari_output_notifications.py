"""Safariの出力I/OとWebKitのセマフォ通知を同じトレースで照合する。"""

import argparse
from bisect import bisect_left, bisect_right
from collections import Counter
from datetime import datetime
import json
from pathlib import Path
from statistics import median
import sys
from tempfile import TemporaryDirectory
from xml.etree import ElementTree

from filter_worklet_audioipc_syscalls import CHILD_ID, VALUE_TAGS, field_value
from measure_fan_crossing_allocations import run_manifest, verified_path
from measure_safari_audio_client_trace import read_cycles
from measure_uniform_tube import record_measurement
from measure_worklet_fixed import ROOT, WORKSPACE


CASE = WORKSPACE / 'cases/worklet-safari-song-output-notification.json'
SIGNAL = 'MSC_semaphore_signal_trap'
WAIT = 'MSC_semaphore_wait_trap'
PROXY = 'RemoteAudioDestinationProxy render thread '
WORKLET = 'WebCore: AudioWorklet '
GPU_IO = 'com.apple.audio.IOThread.client '


def read_json(path):
    return json.loads(path.read_text())


def read_syscalls(source, gpu_pid, gpu_tids, *, web_pid=None, retain_wait_stack_ids=False):
    values, threads, events = {}, {}, {}
    schema = None
    earliest, latest = None, None
    for event, element in ElementTree.iterparse(source, events=('start', 'end')):
        if event == 'start' and element.tag == 'node':
            node = element
        if event != 'end':
            continue
        if element.tag == 'schema':
            schema = [item.findtext('mnemonic') for item in element]
        if element.tag != 'row':
            continue
        for cell in element.iter():
            identity = cell.get('id')
            if identity is not None and (cell.tag in VALUE_TAGS or cell.tag in CHILD_ID):
                value = field_value(cell, values)
                values[identity] = value
                if cell.tag == 'thread' and value is not None:
                    threads[int(value)] = cell.get('fmt', '')
        row = dict(zip(schema, element, strict=True))
        pid = field_value(row['process'], values)
        tid = field_value(row['thread'], values)
        start = int(field_value(row['start'], values))
        earliest = start if earliest is None else min(earliest, start)
        latest = start if latest is None else max(latest, start)
        if pid is not None and tid is not None:
            pid, tid = int(pid), int(tid)
            name = threads.get(tid, '')
            is_gpu_io = pid == gpu_pid and (tid in gpu_tids if gpu_tids else name.startswith(GPU_IO))
            is_web = web_pid is None or pid == web_pid
            role = ('gpu' if is_gpu_io else 'proxy' if is_web and name.startswith(PROXY)
                    else 'worklet' if is_web and name.startswith(WORKLET) else None)
            if role:
                call = field_value(row['call'], values)
                duration = field_value(row['duration'], values)
                result = field_value(row['return'], values)
                counts, series = events.setdefault((role, pid, tid), (Counter(), []))
                counts[call] += 1
                if duration is not None:
                    observation = {'name': call, 'start_ns': start, 'end_ns': start + int(duration),
                                   'return': int(result) if result is not None else None}
                    if retain_wait_stack_ids and call in ('BSC_psynch_cvwait', 'BSC_psynch_cvsignal'):
                        stack = row['backtrace']
                        observation['stack_id'] = stack.get('ref', stack.get('id'))
                        address = field_value(row['arg1'], values)
                        observation['condition_address'] = int(address) if address is not None else None
                    series.append(observation)
        node.remove(element)
    if schema is None:
        raise ValueError('System Call Traceのsyscall表がありません')
    return (earliest, latest), [dict(role=role, pid=pid, tid=tid, name=threads.get(tid), totals=dict(counts),
                                      events=sorted(series, key=lambda row: row['start_ns']))
                                for (role, pid, tid), (counts, series) in sorted(events.items())]


def count_cycles(cycles, signals, worklet_waits, proxy_waits, begin, end):
    native = [cycle for cycle in (cycles or []) if begin <= cycle['start_ns'] < end]
    starts = [row['start_ns'] for row in signals]
    signal_window = starts[bisect_left(starts, begin):bisect_left(starts, end)]
    signal_intervals = [(b - a) / 1e6 for a, b in zip(signal_window, signal_window[1:])]
    matching = [bisect_right(starts, row['start_ns'] + row['duration_ns']) - bisect_left(starts, row['start_ns'])
                for row in native]
    proxy_window = sorted(row['end_ns'] for row in (proxy_waits or []) if begin <= row['end_ns'] < end)
    proxy_intervals = [(b - a) / 1e6 for a, b in zip(proxy_window, proxy_window[1:])]
    # 待機明けの直前にあった通知との時差を記録する。プロセス間のポート名は照合に使わない。
    lags = [(stamp - starts[i - 1]) / 1e6 for stamp in proxy_window if (i := bisect_right(starts, stamp))]
    return {'cycles': len(native) if cycles is not None else None,
            'one_signal_per_cycle': matching.count(1) if cycles is not None else None,
            'signal_count': len(signal_window), 'maximum_signal_gap_ms': max(signal_intervals, default=None),
            'proxy_wait_completions': len(proxy_window) if proxy_waits is not None else None,
            'maximum_proxy_wake_gap_ms': max(proxy_intervals, default=None),
            'proxy_median_since_previous_signal_ms': median(lags) if lags else None,
            'proxy_maximum_since_previous_signal_ms': max(lags, default=None),
            'worklet_mach_waits': sum(begin <= row['end_ns'] < end for row in worklet_waits) if worklet_waits is not None else None}


def inspect(toc, cycles_xml, syscalls_xml, report, item, spec, transcript):
    pid = item['trace_bridge']['target']['pid']
    cycles = read_cycles(cycles_xml, pid, include_overloads=True)[0] if cycles_xml is not None else None
    span, rows = read_syscalls(syscalls_xml, pid, {row['tid'] for row in (cycles or [])})
    transcript.write_text(json.dumps({'syscall_start_span_ns': span, 'threads': rows}, ensure_ascii=False, indent=2) + '\n')
    proxy = [row for row in rows if row['role'] == 'proxy']
    worklet = [row for row in rows if row['role'] == 'worklet' and any(row['pid'] == p['pid'] for p in proxy)]
    signals = sorted((call for row in rows if row['role'] == 'gpu' for call in row['events']
                      if call['name'] == SIGNAL and call['return'] == 0), key=lambda call: call['start_ns'])
    waits = [call for row in proxy for call in row['events'] if call['name'] == WAIT and call['return'] == 0]
    worklet_waits = [call for row in worklet for call in row['events'] if call['name'] == WAIT and call['return'] == 0]
    origin = datetime.fromisoformat(ElementTree.parse(toc).findtext('.//start-date')).timestamp() * 1000
    begin = round((report['scoreConstruction']['startedAtEpochMs'] - origin) * 1e6)
    end = round((report.get('scorePreparation', report['scoreConstruction'])['finishedAtEpochMs'] - origin) * 1e6)
    windows = {'baseline': (begin - 90_000_000, begin - 10_000_000), 'preparation': (begin, end),
               'post': (end + 10_000_000, end + 90_000_000)}
    if cycles:
        lead_start = cycles[0]['start_ns'] + 30_000_000
        lead_end = min(cycles[-1]['start_ns'] - 10_000_000, windows['baseline'][0])
        if lead_start < lead_end:
            windows['observed_lead'] = (lead_start, lead_end)
    metrics = {label: count_cycles(cycles, signals, worklet_waits if worklet else None, waits if proxy else None, *bounds)
               for label, bounds in windows.items()}
    coverage = span[0] is not None and span[0] <= windows['baseline'][0] and span[1] >= windows['post'][1]
    minimum = spec['baseline_minimum_events']
    if cycles_xml is not None:
        coverage = (coverage and bool(cycles) and cycles[0]['start_ns'] <= windows['baseline'][0]
                    and cycles[-1]['start_ns'] >= windows['post'][1])
    else:
        coverage = (coverage and bool(signals) and signals[0]['start_ns'] <= windows['baseline'][0]
                    and signals[-1]['start_ns'] >= windows['post'][1]
                    and all(item['signal_count'] >= minimum for item in metrics.values()))
    fraction = spec['minimum_gpu_cycle_fraction']
    base = metrics['baseline']
    prepared = metrics['preparation']
    calibrated = (coverage and base['signal_count'] >= minimum and sum(row['role'] == 'gpu' for row in rows) == 1)
    if cycles_xml is not None:
        calibrated = (calibrated and base['cycles'] >= minimum and base['one_signal_per_cycle'] >= fraction * base['cycles'])
    matched = cycles_xml is None or bool(prepared['cycles']) and prepared['one_signal_per_cycle'] >= fraction * prepared['cycles']
    return {'covered_all_windows': coverage, 'gpu_signal_calibrated': calibrated,
            'native_cycle_span_ns': [cycles[0]['start_ns'], cycles[-1]['start_ns']] if cycles else None,
            'syscall_start_span_ns': list(span), 'window_bounds_ns': windows,
            'expected_gpu_timing': (matched and prepared['maximum_signal_gap_ms'] is not None
                   and prepared['maximum_signal_gap_ms'] <= spec['maximum_gpu_signal_interval_ms']) if calibrated else None,
            'proxy_thread_identified': len(proxy) == 1 and base['proxy_wait_completions'] >= minimum,
            'thread_identities': [{k: v for k, v in row.items() if k != 'events'} for row in rows],
            'metrics': metrics, 'graph_maximum_ms': item['marker']['preparation_window_max_gap_ms']}


def export_inputs(trace, work, io_needed, execute):
    toc = work / 'toc.xml'
    execute(['xcrun', 'xctrace', 'export', '--input', str(trace), '--toc', '--output', str(toc)])
    files = [toc]
    for schema in ('audio-hal-client-io-cycle', 'syscall'):
        if schema == 'audio-hal-client-io-cycle' and not io_needed:
            files.append(None)
            continue
        path = work / f'{schema}.xml'
        execute(['xcrun', 'xctrace', 'export', '--input', str(trace), '--xpath',
                 f'/trace-toc/run/data/table[@schema="{schema}"]', '--output', str(path)])
        files.append(path)
    return files


def measure(study, captures, artifacts, execute):
    checks, data = {}, {}
    spec = study['notification']
    for name, trials in captures.items():
        results = data[name] = {}
        folder = artifacts / name
        folder.mkdir()
        for label, (files, trace, io_needed, report, item) in trials.items():
            with TemporaryDirectory(dir=artifacts) as scratch:
                if files is None:
                    files = export_inputs(trace, Path(scratch), io_needed, execute)
                result = inspect(*files, report, item, spec, folder / f'{label}.json')
            results[label] = result
            checks[f'{name}/{label}/covered_all_windows'] = result['covered_all_windows']
    predictions = {}
    for name, results in data.items():
        if {label.removeprefix('pair-1-') for label in results} == {'bulk', 'split'}:
            bulk, split = results['pair-1-bulk'], results['pair-1-split']
            predictions[name] = {'graph_gap_reduction': bulk['graph_maximum_ms'] - split['graph_maximum_ms']
                                 >= spec['minimum_marker_gap_reduction_ms'], 'bulk_gpu_timing': bulk['expected_gpu_timing']}
    return {'checks': checks, 'predictions': predictions, 'captures': data}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('capture', nargs='+')
    args = parser.parse_args()
    study = read_json(CASE)
    paths = [CASE, Path(__file__).resolve(), *[WORKSPACE / 'tools' / f'{module}.py' for module in (
        'measure_safari_audio_client_trace', 'filter_worklet_audioipc_syscalls', 'measure_uniform_tube')]]
    captures = {}
    for name in args.capture:
        run = run_manifest(name, study['id'], study['upstream_revision'])
        summary_path = verified_path(run, 'summary.json')
        summary = read_json(summary_path)
        paths.extend([run[0] / 'manifest.json', summary_path])
        recorded = {entry['path'] for entry in run[1]['outputs']}
        trials = captures[name] = {}
        for label, item in summary['trials'].items():
            if not all(summary['checks'].get(f'{label}/{check}') for check in
                       ('pcm_bits', 'marker_pcm_bits', 'observed_state_and_plan', 'preparation_sequence')):
                parser.error(f'{name}/{label} の歌唱と先行信号が基準に一致しません')
            folder = f'artifacts/{label}'
            browser = verified_path(run, f'{folder}/browser.json')
            paths.append(browser)
            config = verified_path(run, f'{folder}/capture-case.json')
            paths.append(config)
            instruments = read_json(config)['audio_client_trace'].get('instruments', ['Audio Client'])
            io_needed = 'Audio Client' in instruments
            xml = [f'{folder}/audio-system-toc.xml', f'{folder}/audio-system-cycles.xml' if io_needed else None,
                   f'{folder}/syscall.xml']
            files = trace = None
            if all(path is None or path in recorded for path in xml):
                files = [verified_path(run, path) if path is not None else None for path in xml]
                paths.extend(path for path in files if path is not None)
            else:
                trace = Path(run[1]['storage']['artifacts_root']) / label / 'audio-system.trace'
                trace_paths = sorted(path for path in recorded if path.startswith(f'{folder}/audio-system.trace/'))
                if not trace_paths:
                    parser.error(f'{name}/{label} の生トレースがありません')
                paths.extend(verified_path(run, path) for path in trace_paths)
            trials[label] = (files, trace, io_needed, read_json(browser), item)
    details = {'case_id': study['id'] + '-analysis', 'upstream_revision': study['upstream_revision'], 'capture_runs': args.capture,
               'analysis_directory': str(Path.cwd()), 'analysis_command': [sys.executable, *sys.argv]}
    return record_measurement(args.run_id, CASE, paths, details, lambda artifacts, execute: measure(study, captures, artifacts, execute),
                              command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
