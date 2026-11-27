"""保存した発話開始の欠落周期を、機器Writeの時計で比較する。"""

import argparse
import csv
from pathlib import Path
from statistics import median
import sys

from measure_csd_envelope_timing import verified_file
from measure_speech_timing import read
from measure_tsp_listening import snapshot_case
from measure_uniform_tube import record_measurement
from measure_worklet_fixed import ROOT
from measure_worklet_tsp_io_deadline import rejoin, server_window
from measure_worklet_tsp_io_thread_state import trial_files
from upstream_baseline import WORKSPACE


CASE = WORKSPACE / 'cases/worklet-live-tsp-firefox-onset-gap-write-timing.json'
METRICS = ('write_minus_client_end_ns', 'server_minus_client_end_ns', 'scheduled_minus_client_end_ns')


def load_run(run_id, revision, inputs):
    folder = WORKSPACE / 'runs' / run_id
    manifest_path = folder / 'manifest.json'
    manifest = read(manifest_path)
    if (manifest['run_id'], manifest['upstream_revision']) != (run_id, revision):
        raise ValueError(f'実行IDまたは固定上流版が登録条件と異なります ({run_id})')
    path = verified_file(folder, manifest, 'summary.json')
    inputs.extend((manifest_path, path))
    return (folder, manifest), read(path)


def pcm_results(data, kind, offset):
    if kind == 'repetition_fit':
        return {(row['trial'], row['condition']): row['selected'] for row in data['events']
                if row['request_offset'] == offset and row['second_block_matches_device_write']}
    if kind == 'zero_fit':
        return {(trial['pair'], trial['condition']): 'zero/' + gap['local_insertion_models']['selected']
                for trial in data['trials'] if trial['tap_pcm']['valid']
                for gap in trial['tap_pcm']['gaps']
                if gap['request_offset'] == offset and gap['local_insertion_models']['selected']}
    raise ValueError(f'未対応のPCMの判定形式です ({kind})')


def group_trials(group, case, inputs):
    revision = case['upstream_revision']
    capture, raw = load_run(group['capture_run'], revision, inputs)
    io, evidence = load_run(group['io_analysis'], revision, inputs)
    pcm, compared = load_run(group['pcm_analysis'], revision, inputs)
    capture_manifest = capture[1]
    case_id = capture_manifest['case_id']
    for _, manifest in (io, pcm):
        if (manifest['case_id'], manifest['capture_run']) != (case_id, group['capture_run']):
            raise ValueError('収録と音声I/O・PCMの比較が同じケースに属していません')
    case_path = snapshot_case(capture, case_id)
    inputs.append(case_path)
    source = read(case_path)
    offset = case['request_offset']
    models = pcm_results(compared, group['pcm_result'], offset)
    rows = []
    for trial, previous in zip(raw['trials'], evidence['trials'], strict=True):
        key = trial['pair'], trial['condition']
        if key != (previous['pair'], previous['condition']):
            raise ValueError('収録と音声I/O解析の試行識別子が一致しません')
        paths = trial_files(capture, trial) if previous['alignment_scope'] != 'missing' else None
        if paths is not None:
            inputs.extend(paths.values())
        rows.append((trial, previous, paths, models.get(key)))
    shared = {key: source[key] for key in ('base_case', 'capture', 'system_io')}
    shared['tap'] = {key: value for key, value in source['tap'].items() if key != 'in_phase_marker'}
    shared['firefox_xul_sha256'] = capture_manifest['firefox_xul_sha256']
    return case_id, source, rows, shared


def timeline(trial, previous, paths, source, case):
    offset, frames, rate = (case[key] for key in ('request_offset', 'request_frames', 'sample_rate_hz'))
    period_ns = frames * 1e9 / rate
    probe = trial['device']
    stream, = probe['matched_streams']
    tick_ns = probe['host_tick_ms'] * 1e6
    settings = source['system_io']
    bounds = source['comparison']['local_onset_offsets'] if previous['alignment_scope'] == 'onset' else None
    blocks, _, client, server, cycles, writes = rejoin(stream, probe, trial['system_io'], tick_ns,
                                                     settings, paths, offset_bounds=bounds)
    offsets = list(range(bounds[0], bounds[1] + 1)) if bounds else [r['offset'] for r in probe['graph_rows']]
    index = offsets.index(offset)
    current, following = blocks[index:index + 2]
    gap = following['sample_time'] - current['sample_time'] - current['frames']
    if current['frames'] != frames or gap != frames:
        raise ValueError('発話開始直後に欠落する周期が登録した1周期と一致しません')
    tolerance = settings['maximum_server_host_error_ms'] * 1e6
    window = server_window(*server[index:index + 2], cycles, writes, period_ns, frames, tick_ns, tolerance)
    stamps = [round(write['current_host_ticks'] * tick_ns) - write['start_ns'] for _, write in window]
    if max(stamps) - min(stamps) > case['maximum_write_clock_origin_spread_ns']:
        raise ValueError('機器Writeから求めた時計原点の幅が登録した範囲を超えています')
    start = client['cycles'][index]
    client_end = start['start_ns'] + start['duration_ns']
    missed, write = window[1]
    saved = next(r for r in previous['thread_states']['requests'] if r['request_offset'] == offset)
    slot, = saved['slots']
    saved_writes = previous['onset_device_writes'][str(offset)]
    if (saved['gap_frames'], slot['server_start_ns'], saved['client_duration_ns'], saved_writes[1]) != (
            gap, missed['start_ns'], start['duration_ns'], write):
        raise ValueError('生のトレースから結合した時刻が保存済みのI/O解析と一致しません')

    scheduled_mach = round(missed['host_ticks'] * tick_ns)
    scheduled = scheduled_mach - median(stamps)
    return {
        'missed_sample_time': missed['output_sample_time'],
        'period_ns': period_ns,
        'within_budget': saved['within_budget'],
        'clock_origin_spread_ns': max(stamps) - min(stamps),
        'cubeb_return_ns': round(current['returned'] * tick_ns) - scheduled_mach,
        'client_end_ns': client_end - scheduled,
        'server_start_ns': missed['start_ns'] - scheduled,
        'write_start_ns': write['start_ns'] - scheduled,
        'write_minus_client_end_ns': write['start_ns'] - client_end,
        'server_minus_client_end_ns': missed['start_ns'] - client_end,
        'scheduled_minus_client_end_ns': scheduled - client_end,
        'ioproc_count': len(slot['ioproc_starts_in_period']),
        'state_durations_ns': slot['states_in_period']['duration_by_state_ns'],
    }


def compare_modes(rows):
    groups = {mode: [row['timing'] for row in rows if row['mode'] == mode and row['timing'] is not None]
              for mode in ('repeat', 'zero')}
    result = {}
    for metric in METRICS:
        repeat, zero = ([item[metric] for item in groups[mode]] for mode in ('repeat', 'zero'))
        if repeat and zero:
            gap = min(repeat) - max(zero)
            result[metric] = {'repeat_range_ns': [min(repeat), max(repeat)], 'zero_range_ns': [min(zero), max(zero)],
                              'repeat_min_minus_zero_max_ns': gap, 'supports_prediction': gap > 0}
    return result


def measure(out, groups, case):
    rows = []
    for case_id, source, trials, _ in groups:
        for trial, previous, paths, model in trials:
            row = {'case_id': case_id, 'trial': trial['pair'], 'pcm_model': model, 'mode': None, 'timing': None}
            if model in ('current_block/preceding_request', 'zero/preceding_request'):
                row['mode'] = 'repeat' if model.startswith('current_block') else 'zero'
            if paths is None:
                row['timing_error'] = previous.get('alignment_error', '収録した音声I/O表が不足しています')
            else:
                try:
                    row['timing'] = timeline(trial, previous, paths, source, case)
                except (ValueError, KeyError, StopIteration) as error:
                    row['timing_error'] = str(error) or '保存済みの要求または状態が見つかりません'
            rows.append(row)
    joined = [row for row in rows if row['timing'] is not None]
    checks = {'all_trials_have_pcm_modes': all(row['mode'] is not None for row in rows),
              'registered_gaps_joined': len(joined) >= case['minimum_joined_trials'],
              'no_ioproc_in_measured_gap': bool(joined) and all(row['timing']['ioproc_count'] == 0 for row in joined)}
    fields = ['case_id', 'trial', 'pcm_model', 'mode', 'timing_error']
    if joined:
        fields.extend(joined[0]['timing'])
    with (out / 'timing.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row[key] for key in fields if key in row} | (row['timing'] or {}))
    return {'checks': checks, 'registered_prediction': case['prediction'], 'trials': rows,
            'by_condition': {name: compare_modes([row for row in rows if row['case_id'] == name])
                             for name, *_ in groups},
            'all_conditions': compare_modes(rows)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('--case', type=Path, default=CASE)
    args = parser.parse_args()
    path = args.case.resolve()
    case = read(path)
    inputs = [path, Path(__file__).resolve(), *(WORKSPACE / 'tools' / name for name in (
        'measure_worklet_tsp_io_deadline.py', 'measure_worklet_tsp_io_thread_state.py',
        'measure_worklet_tsp_device_io.py', 'measure_safari_audio_client_trace.py',
        'measure_cubeb_output_callback.py', 'measure_uniform_tube.py',
        'measure_tsp_listening.py', 'measure_speech_timing.py', 'measure_csd_envelope_timing.py'))]
    groups = [group_trials(group, case, inputs) for group in case['conditions']]
    common = groups[0][-1]
    if not all(shared == common for *_, shared in groups) or common['tap']['sample_rate_hz'] != case['sample_rate_hz']:
        parser.error('収録の共通条件、Firefoxのビルド、タップ形式が一致しません')
    details = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': case['upstream_revision'],
               'analysis_command': [sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]]}
    return record_measurement(args.run_id, path, inputs, details,
                              lambda out, _: measure(out, groups, case), command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
