"""共有Contextの歌唱ノード構築をFirefoxの出力要求に対応づける。"""

import argparse
from bisect import bisect_left, bisect_right
import gzip
from io import BytesIO
import json
from pathlib import Path
from statistics import median
import subprocess
import sys

import numpy as np
from scipy.io import wavfile

import measure_worklet_live_song_shared_context as shared


song, phases, native = shared.song, shared.phases, shared.native
CASE = song.WORKSPACE / 'cases/worklet-live-song-output-callback.json'
DRIVER = 'AudioCallbackDriver::DataCallback'
BUDGET = 'AudioCallbackDriver real-time budget'
DISPATCH = 'GraphRunner::OneIteration'
GRAPH = 'MTG::OneIterationImpl'
ADVANCE = 'MTG graph advance'
ARTIFACTS = ('browser.wav.gz', 'browser.json.gz', 'firefox-profile.json.gz', 'marker.f32le.gz', 'marker.json')


def spans(thread, name, **options):
    return native.thread_intervals(thread, name, **options)[0]


def single_inside(intervals, outer):
    choices = [item for item in intervals if outer[0] <= item[0] <= item[1] <= outer[1]]
    return choices[0] if len(choices) == 1 else None


def marker_near_start(intervals, start, tolerance):
    choices = [item for item in intervals if abs(item[0] - start) <= tolerance]
    return choices[0] if len(choices) == 1 else None


def decode_frames(interval, rate, tolerance_us):
    duration_ms = interval[1] - interval[0]
    frames = round(duration_ms * rate / 1000)
    error_us = 1000 * (duration_ms - 1000 * frames / rate)
    return frames, error_us, frames >= 0 and abs(error_us) <= tolerance_us


def locate_callbacks(profile, prior):
    threads = list(native.threads(profile))
    graph = [t for t in threads if f"{t['name']}/{t['pid']}" == prior['thread']
             and spans(t, phases.CONSTRUCTOR_MARKER, processor=shared.SONG_PROCESSOR)]
    if len(graph) != 1:
        raise ValueError('歌唱ノードを構築したGraphRunnerが一意に見つかりません')
    graph = graph[0]
    constructors = spans(graph, phases.CONSTRUCTOR_MARKER, processor=shared.SONG_PROCESSOR)
    if len(constructors) != 1:
        raise ValueError('歌唱ノードの構築区間が一意に見つかりません')
    constructor = constructors[0]
    choices = []
    for thread in threads:
        if thread['pid'] != graph['pid'] or thread['name'] != 'AudioIPC Client Callback':
            continue
        callbacks = spans(thread, DRIVER)
        choices.extend((thread, callbacks, i) for i, (start, end) in enumerate(callbacks)
                       if start <= constructor[0] <= constructor[1] <= end)
    if len(choices) != 1:
        raise ValueError('歌唱ノード構築を含む出力コールバックが一意に見つかりません')
    driver, callbacks, index = choices[0]
    return constructor, graph, driver, callbacks, index


def reconcile(profile, prior, frames, spec, outer_marker):
    constructor, graph, driver, callbacks, index = locate_callbacks(profile, prior)
    radius, rate = spec['window_radius_callbacks'], spec['output_rate_hz']
    q = spec['worklet_quantum_frames']
    if index < radius or index + radius >= len(callbacks):
        raise ValueError('構築の前後の出力コールバックが不足しています')
    window = callbacks[index - radius:index + radius + 1]
    dispatches, graph_runs = spans(driver, DISPATCH), spans(graph, GRAPH)
    budgets, advances = spans(driver, BUDGET), spans(graph, ADVANCE)

    ref_calls = np.asarray(spans(graph, phases.AUTHOR_MARKER, processor=shared.MARKER_PROCESSOR))
    outer = np.asarray(spans(graph, outer_marker))
    parents = shared.enclosing_intervals(ref_calls, outer)
    if parents is None:
        raise ValueError('先行音の呼び出しに対応するグラフ処理区間を特定できません')
    ref_starts = shared.reference_callback_times(graph, ref_calls, outer[parents], frames)
    if ref_starts is None:
        raise ValueError('先行音のフレーム印をグラフ処理区間に対応づけられません')

    rows = []
    frame_stamps = []
    all_markers_decode = True
    for offset, request in enumerate(window, -radius):
        dispatch = single_inside(dispatches, request)
        graph_span = single_inside(graph_runs, dispatch) if dispatch is not None else None
        if graph_span is None:
            raise ValueError(f'相対位置 {offset} の要求に対応するグラフ反復が一意に見つかりません')
        tolerance = spec['marker_start_tolerance_ms']
        budget = marker_near_start(budgets, request[0], tolerance)
        advance = marker_near_start(advances, graph_span[0], tolerance)
        if budget is None or advance is None:
            raise ValueError(f'相対位置 {offset} の予算またはグラフ前進が一意に見つかりません')
        duration_tolerance = spec['marker_duration_tolerance_us']
        requested, budget_error, budget_ok = decode_frames(budget, rate, duration_tolerance)
        processed, advance_error, advance_ok = decode_frames(advance, rate, duration_tolerance)
        all_markers_decode &= requested > 0 and budget_ok and advance_ok
        lo, hi = bisect_left(ref_starts, graph_span[0]), bisect_right(ref_starts, graph_span[1])
        seen = frames[lo:hi]
        frame_stamps.extend(seen)
        duration = request[1] - request[0]
        budget_ms = 1000 * requested / rate
        rows.append({'offset': offset, 'start_ms': request[0], 'end_ms': request[1],
                     'dispatch_span_ms': dispatch, 'graph_span_ms': graph_span,
                     'requested_frames': requested, 'graph_advance_frames': processed, 'reference_frame_starts': seen,
                     'budget_ms': budget_ms, 'duration_ms': duration, 'duration_minus_budget_ms': duration - budget_ms,
                     'budget_mark_start_offset_ms': budget[0] - request[0],
                     'advance_mark_start_offset_ms': advance[0] - graph_span[0],
                     'budget_mark_error_us': budget_error, 'advance_mark_error_us': advance_error})

    central = rows[radius]
    graph_start, graph_end = central['graph_span_ms']
    checks = {'constructor_is_in_matched_graph_iteration': graph_start <= constructor[0] <= constructor[1] <= graph_end,
              'constructor_matches_capture_summary': abs(constructor[1] - constructor[0] -
                    prior['preparation']['constructor_ms']) <= 1e-6,
              'nonoverlapping_requests': all(a[1] <= b[0] for a, b in zip(window, window[1:])),
              'frame_count_markers_decode': all_markers_decode,
              'reference_frame_counts_match_graph': all(len(r['reference_frame_starts']) * q == r['graph_advance_frames']
                                                       for r in rows),
              'reference_continuous_through_window': bool(frame_stamps) and frame_stamps ==
                  list(range(frame_stamps[0], frame_stamps[-1] + q, q))}
    frames_before_center = sum(r['requested_frames'] for r in rows[:radius])
    requested_so_far = 0
    graph_minus_requested = 0
    for i, row in enumerate(rows):
        row['nominal_start_from_center_request_ms'] = 1000 * (requested_so_far - frames_before_center) / rate
        row['start_offset_from_nominal_ms'] = (row['start_ms'] - central['start_ms'] -
                                               row['nominal_start_from_center_request_ms'])
        graph_minus_requested += row['graph_advance_frames'] - row['requested_frames']
        row['cumulative_graph_minus_requested_frames'] = graph_minus_requested
        if i + 1 < len(rows):
            row['start_to_next_ms'] = rows[i+1]['start_ms'] - row['start_ms']
        requested_so_far += row['requested_frames']
    later = rows[radius+1:-1]
    later_error = median(abs(r['start_to_next_ms'] - r['budget_ms']) for r in later)
    next_late = rows[radius+1]['start_offset_from_nominal_ms']
    last_late = rows[-1]['start_offset_from_nominal_ms']
    predictions = {'constructor_callback_over_budget': central['duration_minus_budget_ms'] > 0,
                   'next_callback_delayed': next_late >= spec['minimum_next_callback_delay_ms'],
                   'later_intervals_close_to_budget': later_error <= spec['maximum_later_median_interval_error_ms'],
                   'offset_remains_at_eighth_callback': last_late >= spec['minimum_eighth_callback_offset_ms']}
    return checks, {'constructor_span_ms': constructor, 'driver_thread': driver['tid'], 'graph_thread': graph['tid'],
                    'pid': graph['pid'], 'rows': rows, 'next_callback_delay_ms': next_late,
                    'later_median_absolute_interval_error_ms': later_error, 'eighth_callback_offset_ms': last_late,
                    'requested_and_graph_frames_match_through_window': all(
                        r['requested_frames'] == r['graph_advance_frames'] for r in rows), 'predictions': predictions}


def read_json(path):
    if path.suffix == '.gz':
        with gzip.open(path, 'rt', encoding='utf-8') as source:
            return json.load(source)
    return song.wasm.read_json(path)


def summarize(results, spec):
    groups = {}
    for condition in ('control', 'draw192'):
        accepted = [r['timing'] for r in results if r['condition'] == condition and r['valid']]
        if not accepted:
            continue
        budgets = [r['rows'][spec['window_radius_callbacks']] for r in accepted]
        group = {'valid_trials': len(accepted), 'requested_frames_at_constructor': sorted({r['requested_frames'] for r in budgets}),
                 'median_constructor_callback_ms': median(r['duration_ms'] for r in budgets),
                 'median_next_callback_delay_ms': median(r['next_callback_delay_ms'] for r in accepted),
                 'median_later_interval_error_ms': median(r['later_median_absolute_interval_error_ms'] for r in accepted),
                 'median_eighth_callback_offset_ms': median(r['eighth_callback_offset_ms'] for r in accepted),
                 'requests_match_graph_advance': sum(1 for r in accepted if r['requested_and_graph_frames_match_through_window']),
                 'predictions_met': sum(1 for r in accepted if all(r['predictions'].values()))}
        if condition == 'draw192':
            group['reaches_prediction_count'] = group['predictions_met'] >= spec['minimum_trials_showing_prediction']
        groups[condition] = group
    return groups


def analyze(study, shared_spec, phase_spec, captures, wav_path):
    spec = study['measurement']
    reference = wav_path.read_bytes()
    rate, audio = wavfile.read(BytesIO(reference))
    marker = shared_spec['marker']
    count = marker['capture_quanta'] * spec['worklet_quantum_frames']
    indices = np.arange(count, dtype=np.int64)
    expected_marker = (((indices * marker['multiplier'] + marker['offset']) % marker['modulus'] -
                        marker['center']) / marker['scale']).astype('<f4').tobytes()
    checks, runs = {'reference_wav_rate': rate == spec['output_rate_hz'],
                    'reference_wav_finite_mono': audio.ndim == 1 and bool(np.isfinite(audio).all())}, []
    for name, summary, paths in captures:
        results = []
        for trial in summary['trials']:
            label, condition = trial['trial'], trial['condition']
            files = paths[label]
            result = {'trial': label, 'condition': condition, 'pilot': f"{name}/{label.partition('-')[0]}" == study['pilot_pair']}
            local = {}
            try:
                timeline = read_json(files['marker.json'])
                frames = timeline['frames']
                q = spec['worklet_quantum_frames']
                start = timeline['startFrame']
                local['marker_coordinates'] = (timeline['sampleRate'] == rate and frames == list(range(start, start + count, q)))
                local['marker_pcm_identical'] = gzip.decompress(files['marker.f32le.gz'].read_bytes()) == expected_marker
                local['song_pcm_identical'] = gzip.decompress(files['browser.wav.gz'].read_bytes()) == reference
                report = read_json(files['browser.json.gz'])
                local['song_plan_and_observations_identical'] = shared.cross.signature(report, audio) == summary['reference_hashes']
                timing_checks, result['timing'] = reconcile(read_json(files['firefox-profile.json.gz']), trial['timing'],
                                                          frames, spec, phase_spec['engine_marker'])
                local.update(timing_checks)
            except (OSError, EOFError, KeyError, TypeError, ValueError) as error:
                local['trial_analysis_complete'] = False
                result['error'] = str(error)
            result['valid'] = all(local.values())
            checks.update({f'{name}/{label}/{key}': value for key, value in local.items()})
            results.append(result)
        runs.append({'run_id': name, 'trials': results, 'groups': summarize(results, spec),
                     'groups_excluding_pilot_pair': summarize([r for r in results if not r['pilot']], spec)})
    return {'checks': checks, 'source_runs': runs}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('--fresh-run', required=True, help='同じ共有Contextケースで新しく採取した実行ID')
    args = parser.parse_args()
    study, source = read_json(CASE), read_json(shared.CASE)
    revision = study['upstream_revision']
    spec = study['measurement']
    if (study['shared_context_case'] != shared.CASE.name or source['upstream_revision'] != revision
            or spec['worklet_quantum_frames'] != source['measurement']['marker']['quantum']
            or spec['window_radius_callbacks'] != 8
            or subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=song.UPSTREAM, text=True).strip() != revision
            or subprocess.check_output(['git', 'status', '--porcelain'], cwd=song.UPSTREAM, text=True)):
        parser.error('固定上流または共有Contextケースが一致しません')
    phase = read_json(phases.CASE)
    baseline = song.run_manifest(phase['reference_run'], shared.cross.CASE.stem, revision)
    if baseline[1]['status'] != 'pass':
        parser.error('歌唱の参照実行が不合格です')
    wav_path = song.verified_path(baseline, phases.REFERENCE[2])
    if args.fresh_run in study['saved_runs'] or len(set(study['saved_runs'])) != len(study['saved_runs']):
        parser.error('新規採取と保存済みの実行は別々に指定してください')
    runs, inputs = [], [CASE, shared.CASE, phases.CASE, wav_path, baseline[0] / 'manifest.json', Path(__file__).resolve(),
                        *(Path(m.__file__).resolve() for m in (shared, phases, native, shared.cross, song, song.wasm,
                                                               song.shared))]
    labels = [(f'{i}-{condition}', condition) for i, order in enumerate(source['measurement']['condition_order'], 1)
              for condition in order]
    for run_id in (*study['saved_runs'], args.fresh_run):
        run = song.run_manifest(run_id, shared.CASE.stem, revision)
        result_path = song.verified_path(run, 'summary.json')
        result = read_json(result_path)
        case_hashes = [entry['sha256'] for entry in run[1]['inputs'] if Path(entry['path']).name == shared.CASE.name]
        if (run[1]['status'] != 'pass' or case_hashes != [song.sha256(shared.CASE)] or not all(result['checks'].values())
                or [(t['trial'], t['condition']) for t in result['trials']] != labels):
            parser.error(f'{run_id} の条件順または共有Contextの判定が一致しません')
        paths = {label: {f: song.verified_path(run, f'artifacts/{label}/{f}') for f in ARTIFACTS} for label, _ in labels}
        inputs.extend([run[0] / 'manifest.json', result_path, *(p for trial in paths.values() for p in trial.values())])
        runs.append((run_id, result, paths))
    metadata = {'case_id': study['id'], 'upstream_revision': revision, 'capture_runs': [name for name, _, _ in runs],
                'analysis_command': [sys.executable, *sys.argv], 'analysis_directory': str(Path.cwd())}
    return song.shared.record_measurement(args.run_id, CASE, inputs, metadata,
        lambda _artifacts, _execute: analyze(study, source['measurement'], phase['measurement'], runs, wav_path),
        command=None, input_root=song.ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
