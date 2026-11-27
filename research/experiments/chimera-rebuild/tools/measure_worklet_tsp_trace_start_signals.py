"""記録開始の二つの通知と発話開始を同じMach時計で照合する。"""

import argparse
from pathlib import Path
from statistics import median
import sys
from xml.etree import ElementTree

from measure_csd_envelope_timing import verified_file
from measure_cubeb_output_callback import load_blocks
from measure_speech_timing import read
from measure_tsp_listening import snapshot_case
from measure_uniform_tube import record_measurement
from measure_worklet_fixed import ROOT
from measure_worklet_tsp_device_io import HARDWARE
from measure_worklet_tsp_io_thread_state import acquisition_timing, trial_files
from measure_worklet_tsp_io_trace_instruments import audit_write_clock, describe_trial
from upstream_baseline import WORKSPACE


CASE = WORKSPACE / 'cases/worklet-live-tsp-firefox-trace-start-signals-56q.json'
EXTRAS = ('trace-start-signals.json', 'system-trace-ready.json', 'trace-release.json',
          'trace-recording-settings.json', 'trace-target.json', 'marker.json', 'system-trace-command.log')


def describe(trial, files, case, out, execute):
    io = case['system_io']
    limits = case['comparison']
    report = {'pair': trial['pair'], 'condition': trial['condition'], 'checks': {}}
    checks = report['checks']
    checks['canonical_speech_and_state'] = all(trial['checks'].get(k, False) for k in (
        'registered_pcm', 'registered_case_and_states', 'fixed_upstream_pcm'))
    checks['registered_onset_requests'] = [r['offset'] for r in trial.get('device_onset_requests', [])] == (
        limits['first_speech_offsets'])
    if not files or not all(n in files for n in EXTRAS):
        checks['start_times_available'] = False
        return report
    observed = read(files['trace-start-signals.json'])
    gate = observed.get('gate_monotonic_ns')
    darwin = observed.get('darwin_monotonic_ns')
    marker = observed.get('stdout_start_marker_monotonic_ns')
    line = observed.get('stdout_start_line_monotonic_ns')
    release = read(files['trace-release.json'])
    released = release.get('release_monotonic_ns')
    bridge = read(files['system-trace-ready.json'])['trace_notice_monotonic_ns']
    settings = read(files['trace-recording-settings.json'])
    pid = read(files['trace-target.json'])['firefox_pid']
    attached = trial['condition'] == 'attach-firefox'
    toc_target = ElementTree.parse(files['io-toc.xml']).find('.//target')
    target_pid = any(row.get('pid') == str(pid) for row in toc_target.iter())
    all_processes = toc_target.find('all-processes') is not None
    checks['registered_capture_target_and_instruments'] = (
        settings == {'time_limit': io['time_limit'], 'instruments': io['instruments'], 'window': None,
                     'ready_file': 'trace-target.json', 'firefox_pid': pid, 'attach_pid': pid if attached else None}
        and pid == trial['system_io']['pid']
        and (target_pid and not all_processes if attached else all_processes))
    checks['darwin_released_playback'] = (
        None not in (darwin, gate, released) and darwin <= gate == bridge <= released
        and not release['tap_requested'])
    checks['start_times_available'] = (
        None not in (darwin, marker, line) and observed.get('stdout_first_bytes_monotonic_ns', marker) <= marker <= line
        and observed.get('start_line_and_darwin_same_poll') == (line == darwin)
        and 'Starting recording' in files['system-trace-command.log'].read_text())
    report['signals_monotonic_ns'] = observed | {'release_monotonic_ns': released}

    mark = read(files['marker.json'])
    expected_frame = case['capture']['marker_ready_quanta'] * 128
    recorded_ready = mark['frames'][case['capture']['marker_ready_quanta'] - 1] + 128 - mark['startFrame']
    center = trial['device']['center_graph_marker_frame']
    checks['registered_ready_and_constructor'] = (
        recorded_ready == expected_frame and 0 <= center - expected_frame <= limits['maximum_constructor_after_ready_frames'])
    acquisition = acquisition_timing(trial, files, io, include_starts=True)
    audit = audit_write_clock(trial, files, acquisition, io)
    checks['hardware_clock_agrees'] = audit.get('metadata_origin_agrees', False)
    report['acquisition'] = acquisition
    report['write_clock'] = audit
    lead = darwin - line if checks['start_times_available'] else None
    report['stdout_line_lead_ns'] = lead
    if checks['start_times_available']:
        report['stdout_marker_lead_ns'] = darwin - marker
    if not audit['available']:
        return report

    stream, = trial['device']['matched_streams']
    raw = load_blocks(files['blocks.csv'].parent)
    first_data = next((b for b in raw if b['stage'] == 'data'), None)
    origin = audit['trace_origin_mach_ns']
    final_write = acquisition['table_last_end_ns'].get(HARDWARE)
    first_onset, = [row['offset'] for row in trial['device_onset_requests'] if 0 in row['speech_output_frames']]
    onset = origin + audit['cubeb_onset_trace_ns'][first_onset]
    positions = {'first_cubeb_data': (round(first_data['entered'] * trial['device']['host_tick_ms'] * 1e6)
                                     if first_data is not None else None),
                 'first_onset': onset, 'last_hardware_write_end': origin + final_write if final_write is not None else None}
    report['audio_monotonic_ns'] = positions
    if checks['start_times_available']:
        report['start_events_from_hardware_origin_ns'] = {
            'stdout_line': line - origin, 'darwin': darwin - origin,
            'first_onset': onset - origin, 'first_onset_if_advanced_by_stdout_lead': onset - lead - origin}
    if positions['last_hardware_write_end'] is not None:
        margin = positions['last_hardware_write_end'] - onset
        report['hardware_end_minus_first_onset_ns'] = margin
        if lead is not None and lead > 0:
            report['margin_if_advanced_by_stdout_lead_ns'] = margin + lead
            # 記録範囲と開始後の処理時間が同じと仮定した場合の換算を保存する。
            window_start, window_end = audit['cubeb_full_window_trace_ns']
            report['additional_delay_after_stdout_for_full_window_ns'] = [
                max(0, lead - window_start), final_write - window_end + lead]
    if 'trace' in files:
        report['onset_gap_comparison'] = describe_trial(trial, files, files['system-trace-command.log'],
                                                        case, out, execute)
    return report


def measure(out, execute, recordings, case):
    trials = [describe(t, files, case, out / f"{t['pair']}-{t['condition']}", execute) for t, files in recordings]
    checks = {f"{trial['pair']}-{trial['condition']}/{key}": passed
              for trial in trials for key, passed in trial['checks'].items()}
    qualified = [trial for trial in trials if all(p for key, p in trial['checks'].items() if key != 'hardware_clock_agrees')
                 and trial.get('stdout_line_lead_ns') is not None]
    limits = case['comparison']
    leads = [trial['stdout_line_lead_ns'] for trial in qualified]
    earlier = sum(lead >= limits['minimum_stdout_lead_ns'] for lead in leads)
    complete = len(qualified) == len(trials)
    return {'checks': checks, 'trials': trials,
            'prediction': {'evaluated': complete, 'supported': earlier >= limits['minimum_trials_with_lead'] if complete else None,
                           'trials_at_registered_lead': earlier,
                           'median_stdout_line_lead_ns': median(leads) if leads else None,
                           'stdout_earlier': sum(lead > 0 for lead in leads),
                           'same_poll': sum(lead == 0 for lead in leads),
                           'darwin_earlier': sum(lead < 0 for lead in leads)}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('capture_run')
    args = parser.parse_args()
    case = read(CASE)
    cap = WORKSPACE / 'runs' / args.capture_run
    capture_manifest = read(cap / 'manifest.json')
    capture = cap, capture_manifest
    snapshot = snapshot_case(capture, case['id'])
    if read(snapshot) != case or (capture_manifest['case_id'], capture_manifest['upstream_revision']) != (
            case['id'], case['upstream_revision']):
        parser.error('収録条件が登録と一致しません')
    previous = WORKSPACE / 'runs' / case['initial_control_run']
    prior_manifest = read(previous / 'manifest.json')
    prior_case = snapshot_case((previous, prior_manifest), case['initial_control_case'])
    prior = read(prior_case)
    if any({k: v for k, v in case[name].items() if k != 'observe_start_signals'} != prior[name]
           for name in ('capture', 'system_io')) or capture_manifest['firefox_xul_sha256'] != prior_manifest['firefox_xul_sha256']:
        parser.error('開始時刻の観測以外の採取条件が前回と一致しません')
    summary = verified_file(*capture, 'summary.json')
    rows = read(summary)['trials']
    expected = [(pair, condition) for pair, order in enumerate(case['measurement']['condition_order'], 1)
                for condition in order]
    if [(t['pair'], t['condition']) for t in rows] != expected:
        parser.error('試行の順序が登録と一致しません')
    inputs = [CASE, snapshot, prior_case, Path(__file__).resolve(), summary, cap / 'manifest.json', previous / 'manifest.json',
              *(WORKSPACE / 'tools' / name for name in ('measure_worklet_tsp_io_thread_state.py',
                  'measure_worklet_tsp_io_trace_instruments.py', 'measure_worklet_tsp_io_deadline.py',
                  'measure_worklet_tsp_device_io.py', 'measure_cubeb_output_callback.py',
                  'measure_safari_audio_client_trace.py', 'filter_worklet_audioipc_syscalls.py', 'measure_uniform_tube.py'))]
    files_recorded = {r['path'] for r in capture_manifest['outputs']}
    data = []
    for trial in rows:
        prefix = f"artifacts/{trial['pair']}-{trial['condition']}"
        files = trial_files(capture, trial, allow_missing_tables=True)
        if files is not None:
            files.update({n: verified_file(*capture, f'{prefix}/{n}') for n in EXTRAS if f'{prefix}/{n}' in files_recorded})
            inputs.extend(files.values())
            if any(r['clock_gap_frames'] > 0 for r in trial['device_onset_requests']):
                trace = f'{prefix}/audio-system.trace'
                trace_members = sorted(p for p in files_recorded if p.startswith(trace + '/'))
                if trace_members:
                    inputs.extend(verified_file(*capture, name) for name in trace_members)
                    files['trace'] = cap / trace
        data.append((trial, files))
    details = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': case['upstream_revision'],
               'capture_run': capture_manifest['run_id'], 'analysis_command': [sys.executable, *sys.argv],
               'analysis_directory': str(Path.cwd())}
    return record_measurement(args.run_id, CASE, inputs, details, lambda out, execute: measure(out, execute, data, case),
                              command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())

