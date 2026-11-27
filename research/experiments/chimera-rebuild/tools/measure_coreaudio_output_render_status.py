"""描画コールバックの戻り値とAudio Clientの情報を照合する。"""

import argparse
from bisect import bisect_left, bisect_right
from collections import Counter
from datetime import datetime
import json
from pathlib import Path
from statistics import median
import subprocess
import sys
import time
from xml.etree import ElementTree

from capture_worklet_system_pair import darwin_notification, recording
from measure_fan_crossing_allocations import run_manifest, verified_path
from measure_safari_audio_client_trace import read_cycles
from measure_uniform_tube import record_measurement
from measure_worklet_fixed import ROOT, UPSTREAM, WORKSPACE


CASE = WORKSPACE / 'cases/coreaudio-output-render-status.json'
SOURCE = Path(__file__).with_name('chimera_output_deadline_probe.swift')
XCTRACE = ('xcrun', 'xctrace')


def capture(folder, binary, ready_args, duration):
    ready = folder / 'ready'
    with (folder / 'native.json').open('wb') as output, (folder / 'native.log').open('wb') as log:
        with subprocess.Popen([binary, *ready_args, ready], stdin=subprocess.PIPE, stdout=output, stderr=log) as probe:
            try:
                deadline = time.monotonic() + 5
                while not ready.exists():
                    if probe.poll() is not None or time.monotonic() >= deadline:
                        raise RuntimeError('AudioUnitの起動準備を確認できません')
                    time.sleep(0.02)
                with darwin_notification() as notice:
                    with recording(folder, ['--instrument', 'Audio Client'], duration, notice,
                                   attach_pid=probe.pid, output_wait=25):
                        probe.stdin.write(b'\x01')
                        probe.stdin.flush()
                        if probe.wait(timeout=5) != 0:
                            raise RuntimeError(f'AudioUnitの出力採取に失敗しました ({probe.returncode})')
            finally:
                if probe.poll() is None:
                    probe.kill()


def read_doc(path):
    return json.loads(path.read_text())


def table_contents(path, schema, pid, begin, end):
    node = ElementTree.parse(path).find('node')
    definition = node.find(f"schema[@name='{schema}']")
    if definition is None:
        raise ValueError(f'収録した表にスキーマがありません ({schema})')
    columns = [column.findtext('mnemonic') for column in definition]
    identities = {item.get('id'): item for item in node.iter() if item.get('id') is not None}

    def target(element):
        ref = element.get('ref')
        return identities[ref] if ref is not None else element

    def cell_value(element, child=None):
        element = target(element)
        item = element.find(child) if child is not None else None
        if item is not None:
            return cell_value(item)
        return element.text or element.get('fmt')

    counts = Counter()
    window = Counter()
    target_rows = in_window = 0
    interesting = {'concept', 'description', 'event', 'name', 'narrative', 'os-status', 'result', 'return', 'status'}
    for row in node.findall('row'):
        fields = dict(zip(columns, row, strict=True))
        process = fields.get('process')
        if process is None and 'description' in fields:
            process = target(fields['description']).find('process')
        if process is not None and cell_value(process, 'pid') != str(pid):
            continue
        target_rows += 1
        timestamp = fields.get('start', fields.get('timestamp'))
        in_range = timestamp is not None and begin <= int(cell_value(timestamp)) < end
        in_window += in_range
        for key in interesting.intersection(fields):
            name = cell_value(fields[key], 'event')
            if name is not None:
                label = f'{key}={name}'
                counts[label] += 1
                if in_range:
                    window[label] += 1
    return {'columns': columns, 'target_rows': target_rows, 'window_rows': in_window,
            'event_counts': dict(sorted(counts.items())), 'window_event_counts': dict(sorted(window.items()))}


def export_tables(spec, trace, folder, pid, begin, end, execute):
    tables = {}
    for schema in spec['tables']:
        xml = folder / f'{schema}.xml'
        execute([*XCTRACE, 'export', '--input', str(trace), '--xpath', f'/trace-toc/run/data/table[@schema="{schema}"]',
                 '--output', str(xml)])
        tables[schema] = table_contents(xml, schema, pid, begin, end)
    return tables


def audit_safari_cycles(trials):
    def overlapping_intervals(stamps, begin, end):
        return [right - left for left, right in zip(stamps, stamps[1:]) if left <= end and right >= begin]

    audit = {}
    for name, (safari, xml) in trials.items():
        cycles, _ = read_cycles(xml, safari['trace_bridge']['target']['pid'], include_overloads=True)
        audio = safari['audio_client']
        origin = audio['trace_start_epoch_ms']
        preparation_start = audio['windows']['preparation']['epoch_ms'][0] - origin
        starts = [row['start_ns'] / 1e6 for row in cycles]
        overload_starts = [stamp for stamp, row in zip(starts, cycles) if row['description'] == 'Cycle; Overload']
        normal_starts = [stamp for stamp, row in zip(starts, cycles) if row['description'] == 'Cycle']
        windows = {}
        for label, window in audio['windows'].items():
            begin, end = (value - origin for value in window['epoch_ms'])
            intervals = overlapping_intervals(starts, begin, end)
            normal = overlapping_intervals(normal_starts, begin, end)
            windows[label] = {'overload_starts': sum(begin <= stamp <= end for stamp in overload_starts),
                              'intervals_including_overload': len(intervals),
                              'maximum_interval_including_overload_ms': max(intervals),
                              'maximum_interval_excluding_overload_ms': max(normal),
                              'saved_maximum_interval_ms': window['maximum_interval_ms']}
        audit[name] = {'overloads_relative_to_preparation_ms': [stamp - preparation_start for stamp in overload_starts],
                       'windows': windows}
    return audit


def inspect(spec, folder, count, execute):
    trace = folder / 'audio-system.trace'
    toc = folder / 'toc.xml'
    execute([*XCTRACE, 'export', '--input', str(trace), '--toc', '--output', str(toc)])
    tree = ElementTree.parse(toc)
    native = read_doc(folder / 'native.json')
    origin_ns = round(datetime.fromisoformat(tree.findtext('.//start-date')).timestamp() * 1e9)
    samples = native['frameMarks']
    clock = native['clock']
    tick = native['timebaseNumer'] / native['timebaseDenom']
    pid = native['pid']
    first = spec['first_error_callback']
    after = first + spec['error_callback_count']
    radius = spec['neighbor_callbacks']
    checks = {
        'native_target': tree.find('./run/info/target/process').get('pid') == str(pid),
        'native_buffers': native['invalidBuffers'] == 0 and native['sampleRate'] == spec['sample_rate_hz'] and native['delayMs'] == 0,
        'native_window_observed': first >= radius and len(samples) > after + radius,
        'expected_return_codes': all(mark.get('status') == (spec['error_status'] if first <= i < first + count else 0)
                                     for i, mark in enumerate(samples)),
        'native_clock_bracket_within_guard': clock['bracketsTicks'] * tick < spec['clock_guard_ms'] * 1e6,
    }
    if not checks['native_window_observed']:
        return checks, {'callbacks': len(samples)}

    def trace_ns(index):
        return clock['epochNs'] - origin_ns + round((samples[index]['entered'] - clock['hostTicks']) * tick)

    tables = export_tables(spec, trace, folder, pid, trace_ns(first), trace_ns(after), execute)

    cycles, _ = read_cycles(folder / 'audio-hal-client-io-cycle.xml', pid)
    starts = [cycle['start_ns'] for cycle in cycles]
    ends = [cycle['start_ns'] + cycle['duration_ns'] for cycle in cycles]
    checks['single_ordered_cycle_thread'] = bool(cycles and len({cycle['tid'] for cycle in cycles}) == 1
        and all(a < b for a, b in zip(starts, starts[1:])) and all(a < b for a, b in zip(ends, ends[1:])))
    guard = spec['clock_guard_ms'] * 1e6
    matches = []
    for i in range(first - radius, after + radius):
        entered = trace_ns(i)
        low, high = bisect_left(ends, entered - guard), bisect_right(starts, entered + guard)
        matches.append(low if high == low + 1 else None)
    mapped = [index for index in matches if index is not None]
    checks['cycle_matches'] = (len(mapped) >= len(matches) * spec['minimum_unique_trace_match_fraction']
                               and all(a < b for a, b in zip(mapped, mapped[1:])))
    window = samples[first - radius:after + radius + 1]
    checks['native_timestamps_and_marker'] = (all(mark.get('sampleTime') is not None and mark.get('hostTime') is not None
        for mark in window) and all(a['markerOffset'] + a['frames'] == b['markerOffset'] for a, b in zip(window, window[1:])))
    gaps = [b['sampleTime'] - a['sampleTime'] - a['frames'] for a, b in zip(window, window[1:])
            if a.get('sampleTime') is not None and b.get('sampleTime') is not None]
    intervals = [(b['entered'] - a['entered']) * tick / 1e6 for a, b in zip(window, window[1:])]
    maximum = max(intervals)
    nominal = median(intervals)
    trace_intervals = [(starts[b] - starts[a]) / 1e6 for a, b in zip(matches, matches[1:])
                       if a is not None and b is not None]
    return checks, {'callbacks': len(samples), 'actual_errors': sum(mark['status'] == spec['error_status'] for mark in samples),
                    'sample_gaps': gaps, 'request_frames': sorted({mark['frames'] for mark in window}),
                    'native_median_ms': nominal, 'native_maximum_ms': maximum, 'native_maximum_ratio': maximum / nominal,
                    'xctrace_median_ms': median(trace_intervals) if trace_intervals else None,
                    'xctrace_maximum_ms': max(trace_intervals) if trace_intervals else None,
                    'xctrace_cycles': len(cycles), 'xctrace_match_indices': matches, 'tables': tables}


def measure(spec, order, reference, archive_trials, artifacts, execute):
    binary = artifacts / 'render-status-probe'
    execute(['xcrun', 'swiftc', '-O', '-framework', 'AudioToolbox', str(SOURCE), '-o', str(binary)])
    checks, results = {}, {}
    for label in order:
        folder = artifacts / label
        folder.mkdir()
        count = spec['error_callback_count'] if label == 'render-error' else 0
        args = [str(value) for value in (spec['first_error_callback'], 0, spec['sample_rate_hz'], spec['duration_seconds'], count)]
        try:
            execute([sys.executable, str(Path(__file__).resolve()), '--capture', str(folder), str(binary),
                     f"{spec['trace_seconds']}s", *args], stdout=folder / 'trace-command.log')
            observed, results[label] = inspect(spec, folder, count, execute)
            checks.update({f'{label}/{key}': value for key, value in observed.items()})
        except (OSError, AttributeError, ValueError, KeyError, TypeError, ElementTree.ParseError, subprocess.CalledProcessError) as error:
            checks[f'{label}/capture_and_analysis'] = False
            results[label] = {'error': str(error)}
    predictions = {'continuous_sample_clock': all(result.get('sample_gaps') and not any(result['sample_gaps']) for result in results.values()),
                   'cycle_period_within_limit': all(result.get('native_maximum_ratio', float('inf')) <= spec['maximum_period_ratio']
                                                    for result in results.values())}
    archive, pid, begin, end = reference
    folder = artifacts / 'safari-reference'
    folder.mkdir()
    tables = export_tables(spec, archive, folder, pid, begin, end, execute)
    checks['safari_reference_cycle_table'] = tables[spec['tables'][0]]['window_rows'] > 0
    audit = audit_safari_cycles(archive_trials)
    checks['safari_saved_windows_recalculated'] = bool(audit) and all(
        abs(window['maximum_interval_excluding_overload_ms'] - window['saved_maximum_interval_ms']) < 1e-9
        for trial in audit.values() for window in trial['windows'].values())
    return {'checks': checks, 'predictions': predictions, 'conditions': results,
            'safari_reference': {'pid': pid, 'window_ns': [begin, end], 'tables': tables, 'cycle_audit': audit}}


def main():
    if sys.argv[1:2] == ['--capture']:
        _, _, folder, binary, duration, *args = sys.argv
        capture(Path(folder), binary, args, duration)
        return 0
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('--reverse', action='store_true')
    args = parser.parse_args()
    spec = read_doc(CASE)
    revision = spec['upstream_revision']
    if (subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip() != revision
            or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True)):
        parser.error('変更のない固定上流が必要です')
    reference = run_manifest(spec['reference_run'], 'worklet-safari-song-audio-client', revision)
    if reference[1]['status'] != 'pass':
        parser.error('比較対象のSafariの観測が必要です')
    summary = verified_path(reference, 'summary.json')
    label = spec['reference_trial']
    paths = [CASE, SOURCE, Path(__file__).resolve(), reference[0] / 'manifest.json', summary]
    archive_root = Path(reference[1]['storage']['artifacts_root'])
    trace_name = f'artifacts/{label}/audio-system.trace'
    trace_files = [row['path'] for row in reference[1]['outputs'] if row['path'].startswith(f'{trace_name}/')]
    if not trace_files:
        parser.error('比較対象のSafariトレースがありません')
    paths.extend(verified_path(reference, name) for name in trace_files)
    trial = read_doc(summary)['trials'][label]
    io = trial['audio_client']
    begin, end = (round((value - io['trace_start_epoch_ms']) * 1e6) for value in io['windows']['preparation']['epoch_ms'])
    archive = (archive_root / label / 'audio-system.trace', trial['trace_bridge']['target']['pid'], begin, end)
    archive_trials = {}
    for name in spec['archive_audit_runs']:
        prior = run_manifest(name, 'worklet-safari-song-audio-client', revision)
        prior_summary = verified_path(prior, 'summary.json')
        paths.extend([prior[0] / 'manifest.json', prior_summary])
        for label, trial in read_doc(prior_summary)['trials'].items():
            xml = verified_path(prior, f'artifacts/{label}/audio-system-cycles.xml')
            paths.append(xml)
            archive_trials[f'{name}/{label}'] = (trial, xml)
    paths.extend(WORKSPACE / 'tools' / f'{basename}.py' for basename in (
        'capture_worklet_system_pair', 'measure_safari_audio_client_trace', 'measure_uniform_tube', 'filter_worklet_audioipc_syscalls'))
    order = list(reversed(spec['order'])) if args.reverse else spec['order']
    details = {'case_id': spec['id'], 'upstream_revision': revision, 'webkit_revision': spec['webkit_revision'],
               'analysis_directory': str(Path.cwd()), 'analysis_command': [sys.executable, *sys.argv],
               'xctrace': subprocess.check_output([*XCTRACE, 'version'], text=True).strip(), 'condition_order': order}
    return record_measurement(args.run_id, CASE, paths, details,
                              lambda artifacts, execute: measure(spec, order, archive, archive_trials, artifacts, execute),
                              command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
