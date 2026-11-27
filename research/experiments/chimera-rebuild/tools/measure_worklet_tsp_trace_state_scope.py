"""アタッチ対照に保存したThread State表の収録範囲を検算する。"""

import argparse
from collections import Counter
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

from measure_csd_envelope_timing import verified_file
from measure_speech_timing import read
from measure_tsp_listening import snapshot_case
from measure_uniform_tube import record_measurement
from measure_worklet_fixed import ROOT
from measure_worklet_tsp_device_io import XCTRACE, trace_rows
from upstream_baseline import WORKSPACE

SCHEMA = 'thread-state'


def measure_scope(path, trial):
    counts = Counter()
    late = Counter()
    last = None
    last_start = None
    audio_ends = [value for value in trial['acquisition']['table_last_end_ns'].values() if value is not None]
    audio_last = max(audio_ends, default=None)
    for row in trace_rows(path, SCHEMA):
        pid = row['process']
        counts[pid] += 1
        start, duration = int(row['start']), int(row['duration'])
        end = start + duration
        last = end if last is None else max(last, end)
        if duration > 0:
            last_start = start if last_start is None else max(last_start, start)
            if audio_last is not None and start > audio_last:
                late[pid] += 1
    targets = trial['target_and_io_tables']
    target = str(targets['firefox_pid'])
    identified = {pid for pid in counts if pid and pid.isdecimal() and int(pid) > 0}
    return {'pair': trial['pair'], 'condition': trial['condition'], 'toc_processes': targets['processes_in_toc'],
            'state_processes': len(identified), 'state_rows': counts.total(), 'firefox_state_rows': counts[target],
            'other_identified_state_rows': sum(counts[pid] for pid in identified if pid != target),
            'coreaudiod_state_rows': sum(counts[pid] for pid in targets['coreaudiod_pids']),
            'last_state_start_ns': last_start, 'last_state_end_ns': last, 'last_audio_end_ns': audio_last,
            'state_rows_starting_after_audio': late.total(), 'firefox_rows_starting_after_audio': late[target]}


def measure(out, execute, data):
    trials = []
    for trial, stored_table, trace in data:
        if stored_table is not None:
            trials.append(measure_scope(stored_table, trial))
            continue
        with TemporaryDirectory(dir=out, prefix='scheduler-scope-') as folder:
            table = Path(folder) / f'{SCHEMA}.xml'
            execute([*XCTRACE, 'export', '--input', str(trace),
                     '--xpath', f"/trace-toc/run/data/table[@schema='{SCHEMA}']", '--output', str(table)])
            trials.append(measure_scope(table, trial))
    checks = {f"{r['pair']}-{r['condition']}/scheduler_rows_available": r['state_rows'] > 0
              for r in trials}
    return {'checks': checks, 'trials': trials}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('analysis_run')
    args = parser.parse_args()
    analysis = WORKSPACE / 'runs' / args.analysis_run
    analysis_manifest_path = analysis / 'manifest.json'
    analysis_manifest = read(analysis_manifest_path)
    run = WORKSPACE / 'runs' / analysis_manifest['capture_run']
    manifest_path = run / 'manifest.json'
    manifest = read(manifest_path)
    case_path = snapshot_case((run, manifest), manifest['case_id'])
    case = read(case_path)
    if not case['system_io'].get('compare_attach_target') or any(
            analysis_manifest[key] != manifest[key] for key in ('case_id', 'upstream_revision')):
        parser.error('収録対象を切り替えた同じケースと解析が必要です')
    summary = verified_file(analysis, analysis_manifest, 'summary.json')
    inputs = [Path(__file__).resolve(), case_path, manifest_path, analysis_manifest_path, summary,
              WORKSPACE / 'tools' / 'measure_worklet_tsp_device_io.py',
              WORKSPACE / 'tools' / 'filter_worklet_audioipc_syscalls.py']
    exported = {row['path'] for row in analysis_manifest['outputs']}
    capture_outputs = {row['path'] for row in manifest['outputs']}
    data = []
    for trial in read(summary)['trials']:
        prefix = f"artifacts/{trial['pair']}-{trial['condition']}"
        table_name = f'{prefix}/{SCHEMA}.xml'
        if table_name in exported:
            source = verified_file(analysis, analysis_manifest, table_name)
            inputs.append(source)
            data.append((trial, source, None))
        else:
            trace = f'{prefix}/audio-system.trace'
            names = sorted(name for name in capture_outputs if name.startswith(trace + '/'))
            if not names:
                parser.error('全試行の生トレースが必要です')
            inputs.extend(verified_file(run, manifest, name) for name in names)
            data.append((trial, None, run / trace))
    details = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': case['upstream_revision'],
               'capture_run': manifest['run_id'], 'analysis_run': args.analysis_run,
               'analysis_command': [sys.executable, *sys.argv], 'analysis_directory': str(Path.cwd())}
    return record_measurement(args.run_id, case_path, inputs, details,
                              lambda out, execute: measure(out, execute, data), command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())

