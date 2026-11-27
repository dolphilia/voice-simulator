"""保存したI/O周期をClient Start表とIOProc表へ対応付ける。"""

import argparse
import csv
from collections import defaultdict
from pathlib import Path
import sys

from measure_csd_envelope_timing import verified_file
from measure_speech_timing import read
from measure_tsp_listening import hydrate_run, snapshot_case
from measure_uniform_tube import record_measurement
from measure_worklet_fixed import ROOT
from measure_worklet_tsp_device_io import SERVER, XCTRACE, server_rows, trace_rows
from upstream_baseline import WORKSPACE


CASE = WORKSPACE / 'cases/worklet-live-tsp-firefox-io-client-start.json'
START = 'audio-hal-io-cycle-client-start'
IOPROC = 'audio-hal-client-io-cycle-ioproc'


def extract_tables(execute, trace, folder):
    folder.mkdir()
    tables = {}
    for schema in (START, IOPROC):
        path = folder / f'{schema}.xml'
        execute([*XCTRACE, 'export', '--input', str(trace),
                 '--xpath', f"/trace-toc/run/data/table[@schema='{schema}']", '--output', str(path)])
        tables[schema] = path
    return tables


def index_starts(path, tid):
    rows = defaultdict(list)
    for r in trace_rows(path, START):
        if r['thread'] == str(tid) and r['output-host-time']:
            rows[int(r['output-sample-time'])].append((int(r['timestamp']), int(r['output-host-time'])))
    return rows


def ioproc_rows(path, pid, tid):
    for row in trace_rows(path, IOPROC):
        if row['process'] == str(pid) and row['thread'] == str(tid) and row['name'] == 'IOProc':
            start = int(row['start'])
            yield {'start_ns': start, 'end_ns': start + int(row['duration'])}


def indexed_request(item, index, t, server, starts, calls, settings):
    client = t['system_io']['client_io']['cycles']
    left, right = client[index:index + 2]
    zero = left['start_ns']
    through = zero + left['duration_ns']
    next_start = right['start_ns']
    next_end = next_start + right['duration_ns']
    period = item['cycle_budget_ns']
    pulses = []
    for e in item['timeline']:
        if e['event'] != 'server_client_start':
            continue
        slot = e['server_slot']
        sample = item['server_samples'][slot]
        stamp = e['earliest_relative_ns'] + zero
        pulse = server[(sample, stamp)]
        # ホスト時計は前回計測で使ったMach tickの換算比で比較する。
        tick_ns = t['device']['host_tick_ms'] * 1e6
        matches = [when for when, host in starts[sample]
                   if abs(host - pulse['host_ticks']) * tick_ns <= settings['maximum_start_time_error_ns']]
        pulses.append({'server_slot': slot, 'sample_frame': sample, 'start_count': len(matches),
                       'relative_to_server_cycle_ns': [when - stamp for when in matches]})
    present = [row for row in calls if zero <= row['start_ns'] and row['end_ns'] <= through]
    following = [row for row in calls if next_start <= row['start_ns'] and row['end_ns'] <= next_end]
    between = [row for row in calls if through < row['start_ns'] < next_start]
    return {'pair': t['pair'], 'condition': t['condition'], 'request_offset': item['request_offset'],
            'gap_frames': item['gap_frames'], 'within_budget': max(item['callback_ns'], item['client_duration_ns']) <= period,
            'server_starts': pulses, 'ioproc_in_current_cycle': present,
            'ioproc_in_next_client_cycle': following, 'ioproc_between_client_cycles': between}


def measure(out, execute, sources, config):
    all_rows = []
    checks = {}
    for aligned, capture, trace, server_path in sources:
        label = f"{aligned['pair']}-{aligned['condition']}"
        try:
            selected = capture['system_io']
            client = selected['client_io']
            tid = selected['server_io']['tid']
            paths = extract_tables(execute, trace, out / label)
            starts = index_starts(paths[START], tid)
            server = {(r['output_sample_time'], r['start_ns']): r for r in server_rows(server_path, SERVER) if r['tid'] == tid}
            calls = list(ioproc_rows(paths[IOPROC], selected['pid'], client['tid']))
            indices = {r['offset']: i for i, r in enumerate(capture['device']['graph_rows'])}
            rows = [indexed_request(req, indices[req['request_offset']], capture, server, starts, calls, config)
                    for req in aligned['requests']]
            all_rows.extend(rows)
            checks[f'{label}/tables_available'] = True
            checks[f'{label}/all_server_starts_unique'] = all(s['start_count'] == 1 for r in rows for s in r['server_starts'])
            checks[f'{label}/observed_client_cycles_contain_ioproc'] = all(
                r['ioproc_in_current_cycle'] and r['ioproc_in_next_client_cycle'] for r in rows)
        except (OSError, subprocess.CalledProcessError, KeyError, ValueError) as error:
            checks[f'{label}/tables_available'] = False
            all_rows.append({'pair': aligned['pair'], 'condition': aligned['condition'], 'error': str(error)})
    trials = [r for r in all_rows if 'request_offset' in r]
    hidden = [r for r in trials if r['gap_frames'] and r['within_budget']]
    matched = [d for r in trials for s in r['server_starts'] for d in s['relative_to_server_cycle_ns']]
    if trials:
        with (out / 'client-start-slots.csv').open('w', newline='') as stream:
            keys = ['pair', 'condition', 'request_offset', 'gap_frames', 'within_budget']
            writer = csv.DictWriter(stream, [*keys, *trials[0]['server_starts'][0]])
            writer.writeheader()
            for r in trials:
                for stage in r['server_starts']:
                    writer.writerow({k: r[k] for k in keys} | stage)
    return {'checks': checks, 'requests': all_rows, 'observations': {
        'requests': len(trials), 'server_start_events_matched': len(matched),
        'maximum_server_start_marker_delta_ns': max(map(abs, matched), default=None),
        'within_budget_gaps': len(hidden),
        'within_budget_gaps_with_intermediate_server_start': sum(r['server_starts'][1]['start_count'] == 1 for r in hidden),
        'within_budget_gaps_with_intermediate_ioproc': sum(bool(r['ioproc_between_client_cycles']) for r in hidden)}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    case = read(CASE)
    revision = case['upstream_revision']
    timeline = hydrate_run(case['timeline_run'], case['timeline_case'], revision)
    registered = snapshot_case(timeline, case['timeline_case'])
    prior = read(registered)
    capture = hydrate_run(prior['capture_run'], prior['capture_case'], revision)
    aligned = verified_file(*timeline, 'summary.json')
    captured = verified_file(*capture, 'summary.json')
    source = {(t['pair'], t['condition']): t for t in read(captured)['trials']}
    inputs = [CASE, Path(__file__).resolve(), registered, aligned, captured,
              *(p[0] / 'manifest.json' for p in (timeline, capture)),
              *(WORKSPACE / 'tools' / filename for filename in ('measure_worklet_tsp_device_io.py',
                  'filter_worklet_audioipc_syscalls.py', 'measure_tsp_listening.py', 'measure_uniform_tube.py'))]
    traces = []
    for item in read(aligned)['trials']:
        key = (item['pair'], item['condition'])
        prefix = f'artifacts/{key[0]}-{key[1]}'
        trace = f'{prefix}/audio-system.trace'
        members = [r['path'] for r in capture[1]['outputs'] if r['path'].startswith(trace + '/')]
        if not members:
            parser.error(f'元のトレースのマニフェストがありません ({trace})')
        inputs += [verified_file(*capture, member) for member in members]
        server_path = verified_file(*capture, f'{prefix}/{SERVER}.xml')
        inputs.append(server_path)
        traces.append((item, source[key], capture[0] / trace, server_path))
    details = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision,
               'capture_run': prior['capture_run'], 'timeline_run': case['timeline_run'],
               'analysis_command': [sys.executable, *sys.argv], 'analysis_directory': str(Path.cwd())}
    return record_measurement(args.run_id, CASE, inputs, details,
                              lambda out, execute: measure(out, execute, traces, case),
                              command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
