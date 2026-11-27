"""保存した確認用07のI/Oを、音声サーバーの周期を含む時刻軸で比較する。"""

import argparse
import csv
from collections import defaultdict
from pathlib import Path
import subprocess
import sys

import numpy as np
from scipy.io import wavfile

from measure_csd_envelope_timing import verified_file
from measure_cubeb_output_callback import load_blocks
from measure_safari_audio_client_trace import read_cycles
from measure_speech_timing import read
from measure_tsp_listening import hydrate_run, snapshot_case
from measure_uniform_tube import record_measurement
from measure_worklet_fixed import ROOT
from measure_worklet_tsp_device_io import CLIENT, HARDWARE, SERVER, matching_client_cycles, match_server, server_rows, trace_origin
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/worklet-live-tsp-firefox-io-deadline.json'
IO_CASE = 'worklet-live-tsp-firefox-device-io'
SOURCE_CASE = 'worklet-live-tsp-source-defaults'
FILES = (CLIENT + '.xml', SERVER + '.xml', HARDWARE + '.xml', 'io-toc.xml', 'trace-clock.json', 'browser.wav')


def unique(rows, message):
    if len(rows) != 1:
        raise ValueError(message)
    return rows[0]


def cubeb_window(folder, recorded, files, offset_bounds=None):
    window = recorded['streams'][folder]
    raw = load_blocks(files['blocks.csv'].parent)
    indices = [row['block_index'] for row in window['intervals']]
    indices.append(indices[-1] + 1)
    if offset_bounds is not None:
        first, last = offset_bounds
        offsets = [row['request_offset'] for row in window['request_alignment']]
        start = offsets.index(first)
        stop = start + last - first + 1
        if offsets[start:stop] != list(range(first, last + 1)):
            raise ValueError('登録した局所窓の要求が連続していません')
        indices = indices[start:stop + 1]
    return [raw[i] for i in indices]


def rejoin(folder, recorded, recorded_io, tick_ns, settings, files, *, offset_bounds=None):
    blocks = cubeb_window(folder, recorded, files, offset_bounds)
    pid = recorded_io['pid']
    clients, _ = read_cycles(files[CLIENT + '.xml'], pid, include_overloads=True)
    origin = trace_origin(files['trace-clock.json'].parent, files['io-toc.xml'])
    client = unique(matching_client_cycles(blocks, clients, origin, tick_ns, settings),
                    'Firefoxの要求とAudio Clientを一意に照合できません')
    server_table = list(server_rows(files[SERVER + '.xml'], SERVER, intervals=True))
    server = unique(match_server(blocks, server_table, pid, tick_ns, settings['maximum_server_host_error_ms']),
                    '音声サーバーの要求を一意に照合できません')
    if offset_bounds is None:
        before = recorded_io['server_io']['cycles']
        same_server = (len(server['cycles']) == len(before) and
                       all(all(row[key] == value for key, value in expected.items())
                           for row, expected in zip(server['cycles'], before, strict=True)))
        if client != recorded_io['client_io'] or not same_server:
            raise ValueError('保存された要求の対応が生データからの再照合と異なります')
    cycles = defaultdict(list)
    for row in server_table:
        if row['tid'] == server['tid'] and row['client_pid'] in (None, str(pid)):
            cycles[row['output_sample_time']].append(row)
    writes = defaultdict(list)
    for row in server_rows(files[HARDWARE + '.xml'], HARDWARE, intervals=True):
        if row['tid'] == server['tid']:
            writes[row['start_sample_time']].append(row)
    return blocks, clients, client, server['cycles'], cycles, writes


def server_slot(first, cycles, slot, period_ns, frames, tick_ns, tolerance_ns):
    sample = first['output_sample_time'] + slot * frames
    return unique([row for row in cycles[sample] if
                   abs((row['host_ticks'] - first['host_ticks']) * tick_ns - slot * period_ns) <= tolerance_ns],
                  f'予定位置 {sample} のサーバー処理が一意に見つかりません')


def server_window(first, following, cycles, writes, period_ns, frames, tick_ns, tolerance_ns):
    distance = following['output_sample_time'] - first['output_sample_time']
    if distance < frames or distance % frames:
        raise ValueError('サーバーの予定位置が要求の幅に一致しません')
    window = []
    for slot in range(distance // frames + 1):
        cycle = server_slot(first, cycles, slot, period_ns, frames, tick_ns, tolerance_ns)
        candidates = [row for row in writes[cycle['output_sample_time']] if row['frames'] == frames
                      and abs(row['start_ns'] - cycle['start_ns']) < period_ns]
        window.append((cycle, candidates))
    streams = set.intersection(*({(w['engine_id'], w['stream_index']) for w in choices} for _, choices in window))
    device = unique(list(streams), '連続するWriteのエンジンとストリームを一意に照合できません')
    return [(cycle, unique([w for w in choices if (w['engine_id'], w['stream_index']) == device],
                           '同じ予定位置のWriteを一意に照合できません')) for cycle, choices in window]


def request_timeline(blocks, clients, client, server, cycles, writes, index, case, tick_ns, io_settings):
    current, following = blocks[index:index + 2]
    left, right = client['cycles'][index:index + 2]
    frames = case['request_frames']
    period = frames * 1e9 / case['sample_rate_hz']
    if current['frames'] != frames:
        raise ValueError('予定と異なる出力要求サイズです')
    tolerance = io_settings['maximum_server_host_error_ms'] * 1e6
    window = server_window(*server[index:index + 2], cycles, writes, period, frames, tick_ns, tolerance)
    skip = following['sample_time'] - current['sample_time'] - frames
    if skip != frames * (len(window) - 2):
        raise ValueError('cubebと音声サーバーの予定周期数が異なります')
    zero = left['start_ns']
    end = zero + left['duration_ns']
    lower, upper = client['origin_range_ns']
    entry, returned = (round(current[key] * tick_ns) for key in ('entered', 'returned'))
    timeline = []

    def event(label, time_ns, *, latest=None, slot=None):
        stop = time_ns if latest is None else latest
        timeline.append({'event': label, 'earliest_relative_ns': time_ns - zero,
                         'latest_relative_ns': stop - zero, 'server_slot': slot})

    event('client_start', zero)
    event('cubeb_enter', entry - upper, latest=entry - lower)
    event('cubeb_return', returned - upper, latest=returned - lower)
    event('client_end', end)
    for slot, (cycle, write) in enumerate(window):
        event('server_client_start', cycle['start_ns'], slot=slot)
        event('server_client_end', cycle['start_ns'] + cycle['duration_ns'], slot=slot)
        event('server_write_start', write['start_ns'], slot=slot)
        event('server_write_end', write['start_ns'] + write['duration_ns'], slot=slot)
    event('next_client_start', right['start_ns'])
    event('next_client_end', right['start_ns'] + right['duration_ns'])
    server_first = window[0][0]['start_ns']
    server_next = window[1][0]['start_ns']
    write_next = window[1][1]['start_ns']
    intervals = [b[0]['start_ns'] - a[0]['start_ns'] for a, b in zip(window, window[1:])]
    intervening = [r for r in clients if zero < r['start_ns'] < right['start_ns']]
    return {
        'gap_frames': skip, 'cycle_budget_ns': period,
        'callback_ns': returned - entry, 'client_duration_ns': left['duration_ns'],
        'client_start_minus_server_start_ns': zero - server_first,
        'next_server_start_minus_client_end_ns': server_next - end,
        'next_write_start_minus_client_end_ns': write_next - end,
        'next_server_start_minus_cubeb_return_ns': [server_next - returned + lower, server_next - returned + upper],
        'next_client_start_minus_next_server_start_ns': right['start_ns'] - server_next,
        'server_cycle_intervals_ns': intervals,
        'server_cadence_matches_budget': all(abs(dt - period) <= case['maximum_server_interval_error_ms'] * 1e6
                                             for dt in intervals),
        'intervening_client_cycles_same_process': intervening,
        'next_client_description': right['description'],
        'server_samples': [cycle['output_sample_time'] for cycle, _ in window],
        'hardware_clock_origin_ns': [round(w['current_host_ticks'] * tick_ns) - w['start_ns'] for _, w in window],
        'timeline': timeline,
    }


def inspect(trial, case, settings, paths, wav_reference, upper, tolerance):
    probe = trial['device']
    recorded, = probe['matched_streams']
    tick_ns = probe['host_tick_ms'] * 1e6
    joined = rejoin(recorded, probe, trial['system_io'], tick_ns, settings, paths)
    rate, pcm = wavfile.read(paths['browser.wav'])
    agrees = rate == case['sample_rate_hz'] and pcm.dtype == np.float32 and pcm.shape == upper.shape
    delta = float(np.max(np.abs(pcm.astype(float) - upper))) if agrees and np.isfinite(pcm).all() else None
    rows = {row['offset']: i for i, row in enumerate(probe['graph_rows'])}
    checks = {'canonical_speech_wav': sha256(paths['browser.wav']) == wav_reference,
              'fixed_upstream_pcm': delta is not None and delta <= tolerance,
              'speech_state_checks': trial['checks']['registered_case_and_states'], 'raw_clock_alignment': True}
    requests = []
    for offset in case['request_offsets']:
        try:
            timeline = request_timeline(*joined, rows[offset], case, tick_ns, settings)
            request = {'request_offset': offset, **timeline}
            checks[f'offset_{offset}_timeline'] = True
        except (ValueError, KeyError) as error:
            request = {'request_offset': offset, 'error': str(error)}
            checks[f'offset_{offset}_timeline'] = False
        requests.append(request)
    return {'pair': trial['pair'], 'condition': trial['condition'], 'checks': checks, 'requests': requests,
            'maximum_fixed_upstream_absolute_error': delta}


def summarize(trials):
    rows = [req | {'pair': t['pair'], 'condition': t['condition']}
            for t in trials for req in t['requests'] if 'error' not in req]
    onset = [r for r in rows if r['request_offset'] == 12]
    missed = [r for r in onset if r['gap_frames'] > 0]
    within = [r for r in missed if max(r['callback_ns'], r['client_duration_ns']) <= r['cycle_budget_ns']]
    continuous = [r for r in onset if not r['gap_frames']]
    prediction = {
        'server_cadence_continues_on_budgeted_gaps': all(r['server_cadence_matches_budget'] for r in within) if within else None,
        'server_starts_before_client_end_on_budgeted_gaps': bool(within) and
        all(r['next_server_start_minus_client_end_ns'] < 0 for r in within),
        'server_starts_after_client_end_without_gaps': bool(continuous) and
        all(r['next_server_start_minus_client_end_ns'] > 0 for r in continuous),
    }
    return rows, {'onset_requests': len(onset), 'onset_gaps': len(missed), 'onset_gaps_within_budget': len(within),
                  'onset_continuous': len(continuous), 'predictions': prediction}


def measure(out, trials, case, settings, wav, upper, tolerance):
    results = [inspect(t, case, settings, paths, wav, upper, tolerance) for t, paths in trials]
    rows, totals = summarize(results)
    status = {f"{t['pair']}-{t['condition']}/{key}": passed for t in results for key, passed in t['checks'].items()}
    if rows:
        with (out / 'io-events.csv').open('w', newline='') as stream:
            writer = csv.DictWriter(stream, ['pair', 'condition', 'request_offset', *rows[0]['timeline'][0]])
            writer.writeheader()
            for r in rows:
                for event in r['timeline']:
                    writer.writerow({k: r[k] for k in ('pair', 'condition', 'request_offset')} | event)
    return {'checks': status, 'totals': totals, 'trials': results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    case = read(CASE)
    revision = case['upstream_revision']
    if (subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip() != revision or
            subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM)):
        parser.error('差分のない固定上流版が必要です')
    capture = hydrate_run(case['capture_run'], case['capture_case'], revision)
    capture_case = snapshot_case(capture, case['capture_case'])
    settings_path = snapshot_case(capture, IO_CASE)
    summary_path = verified_file(*capture, 'summary.json')
    baseline = hydrate_run(case['baseline_run'], SOURCE_CASE, revision)
    baseline_case = snapshot_case(baseline, SOURCE_CASE)
    source = read(baseline_case)
    upper_run = hydrate_run(source['upstream_run'], source['upstream_case'], revision)
    upper_path = verified_file(*upper_run, 'artifacts/upstream.f32le')
    wav = verified_file(*baseline, 'artifacts/firefox/browser.wav')
    upper = np.fromfile(upper_path, dtype='<f4')
    if upper.size != source['measurement']['output_frames'] or not np.isfinite(upper).all():
        parser.error('固定上流のPCMを確認できません')
    settings = read(settings_path)['system_io']
    inputs = [CASE, Path(__file__).resolve(), capture_case, settings_path, baseline_case, summary_path, wav, upper_path,
              *(r[0] / 'manifest.json' for r in (capture, baseline, upper_run)),
              *(WORKSPACE / 'tools' / name for name in ('measure_worklet_tsp_device_io.py',
                  'measure_cubeb_output_callback.py', 'measure_safari_audio_client_trace.py',
                  'filter_worklet_audioipc_syscalls.py', 'measure_csd_envelope_timing.py', 'measure_tsp_listening.py',
                  'measure_speech_timing.py', 'measure_uniform_tube.py', 'upstream_baseline.py'))]
    trials = []
    for trial in read(summary_path)['trials']:
        prefix = f"artifacts/{trial['pair']}-{trial['condition']}"
        recorded, = trial['device']['matched_streams']
        paths = {name: verified_file(*capture, f'{prefix}/{name}') for name in FILES}
        paths['blocks.csv'] = verified_file(*capture, f'{prefix}/{recorded}/blocks.csv')
        inputs += list(paths.values())
        trials.append((trial, paths))
    details = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision,
               'capture_run': case['capture_run'], 'analysis_command': [sys.executable, *sys.argv],
               'analysis_directory': str(Path.cwd())}
    return record_measurement(args.run_id, CASE, inputs, details, lambda out, _: measure(
        out, trials, case, settings, sha256(wav), upper, source['measurement']['upper_pcm_absolute_tolerance']),
        command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
