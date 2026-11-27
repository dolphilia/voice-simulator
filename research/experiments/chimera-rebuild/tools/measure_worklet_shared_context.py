"""先行音が鳴る96 kHzのContextでWASMラッパーの準備を対照する。"""

import argparse
from bisect import bisect_right
from pathlib import Path

import numpy as np

import measure_worklet_release_alignment as release
import measure_worklet_wrapper_threshold as threshold
import measure_worklet_wrapper_warmup as warmup
import smooth_tap_marker


CASE = release.WORKSPACE / 'cases/worklet-wasm-wrapper-shared-context.json'


def marker_signal(marker, path, quantum, rate):
    timeline = release.stored.read(path / 'marker.json')
    pcm_path = path / 'marker.f32le'
    pcm = np.fromfile(pcm_path, dtype='<f4')
    release.stored.compress(pcm_path)
    count = marker['capture_quanta']
    start = timeline['startFrame']
    frames = start + np.arange(count) * quantum
    if 'smooth_marker' in marker:
        expected = smooth_tap_marker.marker_pcm(count * quantum, marker['smooth_marker'])
    else:
        indices = np.arange(count * quantum, dtype='i8')
        encoded = (indices * marker['multiplier'] + marker['offset']) % marker['modulus']
        expected = ((encoded - marker['center']) / marker['scale']).astype('<f4')
    shape_matches = pcm.shape == expected.shape
    where = []
    check_name = 'marker_pcm_bit_identical'
    if shape_matches:
        difference = pcm.view('u4') != expected.view('u4')
        if 'smooth_marker' in marker:
            difference &= (expected != 0) | ~(np.abs(pcm) <= marker['maximum_graph_zero_error'])
        where = np.flatnonzero(difference)
    if 'smooth_marker' in marker:
        check_name = 'marker_pcm_with_zero_tolerance'
    checks = {check_name: shape_matches and not len(where),
              'marker_frame_continuity': bool(np.array_equal(timeline['frames'], frames)),
              'marker_rate_matches_voice': timeline['sampleRate'] == rate}
    details = {'sample_count': len(pcm), 'marker_start_frame': start,
               'marker_last_frame': int(frames[-1] + quantum - 1),
               'first_marker_pcm_difference': int(where[0]) if len(where) else None}
    return checks, details, timeline['frames']


def marker_audio(spec, path, report):
    marker = spec['marker']
    quantum = report['observations'][0][1]
    checks, details, frames = marker_signal(marker, path, quantum, report['sampleRate'])
    initialization = report['wrapperWarmup']['contextFrame']
    voice_later = report['observations'][999][0]
    checks['marker_spans_construction_and_quantum_1000'] = bool(
        details['marker_start_frame'] + marker['ready_quanta'] * quantum <= initialization <= voice_later <= frames[-1])
    details.update({'constructor_frame': initialization, 'voice_1000th_frame': voice_later})
    return checks, details


def trace_marks(events, extra=()):
    found = {name: [] for name in ('marker', 'live-start', 'live-end', 'dsp-render-start', 'dsp-render-end', *extra)}
    for event in events:
        if event['name'] == 'TimeStamp':
            label = event.get('args', {}).get('data', {}).get('message', '')
            prefix, sep, frame = label.partition(':')
            if sep and prefix.startswith('chimera-') and prefix[8:] in found and frame.isdigit():
                found[prefix[8:]].append((int(frame), event))
    return found


def function_compilations_in_interval(events, begin, end):
    return [{'index': event['args']['func_index'], 'duration_us': event['dur']}
            for event in events if begin <= event['ts'] and event['ts'] + event['dur'] <= end]


def inspect_dsp(spec, events, marks, report, trial, ctor, voice_callbacks):
    expected = spec['expected_dsp_warmup_frames']
    began, ended = ctor
    thread = (began['pid'], began['tid'])
    compiled = [event for event in events if event['name'] == spec['lazy_event'] and event['ph'] == 'X'
                and (event['pid'], event['tid']) == thread]
    start_marks, end_marks = marks['dsp-render-start'], marks['dsp-render-end']
    first_seen = len(voice_callbacks) > report['startupCallbacks']
    first = voice_callbacks[report['startupCallbacks']] if first_seen else None
    first_functions = function_compilations_in_interval(compiled, first['ts'], first['ts'] + first['dur']) if first else []
    registered = set(spec['first_quantum_lazy_functions'])
    first_ids = {row['index'] for row in first_functions}
    discarded = []
    discard_us = None
    if expected is None:
        marks_valid = not start_marks and not end_marks
    else:
        marks_valid = len(start_marks) == len(end_marks) == 1
        if marks_valid:
            (_, start), = start_marks
            (_, end), = end_marks
            marks_valid = ((start['pid'], start['tid']) == (end['pid'], end['tid']) == thread
                           and began['ts'] <= start['ts'] <= end['ts'] <= ended['ts'])
            if marks_valid:
                discard_us = end['ts'] - start['ts']
                discarded = function_compilations_in_interval(compiled, start['ts'], end['ts'])
    discarded_ids = {row['index'] for row in discarded}
    checks = {'same_wasm_as_registered': trial['servedWasmSha256'] == spec['registered_wasm_sha256'],
              'discarded_frame_option_applied': report['wrapperWarmup'].get('discardedRenderFrames') == expected,
              'discarded_render_trace_aligned': marks_valid,
              'first_recorded_quantum_restarts_at_zero': report['observations'][0][4] == report['observations'][0][1],
              'registered_lazy_functions_in_expected_phase': first_seen and (
                  registered <= discarded_ids and registered.isdisjoint(first_ids)
                  if expected else first_ids == registered and not discarded_ids)}
    result = {'discarded_frames': expected, 'discarded_render_us': discard_us,
              'first_quantum_compilations': first_functions,
              'discarded_render_compilations': discarded,
              'first_quantum_thread_us': first.get('tdur') if first else None}
    return checks, result


def inspect_shared_trace(spec, path, report, trial, expected, *, inspect_tail=None):
    events = release.stored.read(path)['traceEvents']
    release.stored.compress(path)
    checks, marker = marker_audio(spec, path.parent, report)
    marks = trace_marks(events)
    marker['trace_mark_counts'] = {key: len(values) for key, values in marks.items()}
    checks['constructor_and_marker_trace_ready'] = (
        len(marks['live-start']) == len(marks['live-end']) == 1 and bool(marks['marker']))
    if not checks['constructor_and_marker_trace_ready']:
        return checks, {'shared_context': marker}
    (frame, began), = marks['live-start']
    (end_frame, ended), = marks['live-end']
    thread = (began['pid'], began['tid'])
    index_event = lambda event: (event['pid'], event['tid'])
    callbacks = sorted((event for event in events if event['name'] == spec['callback_event']
                        and event['ph'] == 'X' and index_event(event) == thread), key=lambda event: event['ts'])
    beginnings = [event['ts'] for event in callbacks]
    mapped = {}
    for block, stamp in marks['marker']:
        index = bisect_right(beginnings, stamp['ts']) - 1
        if (index_event(stamp) == thread and index >= 0
                and stamp['ts'] <= callbacks[index]['ts'] + callbacks[index]['dur']):
            mapped[block] = index
    timeline = release.stored.read(path.parent / 'marker.json')
    checks['marker_callback_mapping'] = (len(mapped) == len(set(mapped.values())) == len(marks['marker'])
                                        and set(timeline['frames']).issubset(mapped))
    checks['constructor_trace_matches_context_frame'] = (
        frame == end_frame == marker['constructor_frame']
        and index_event(ended) == thread and began['ts'] <= ended['ts'])
    exclude = {id(callbacks[index]) for index in mapped.values()}
    voice_checks, voice = threshold.summarize_trace(
        spec, [event for event in events if id(event) not in exclude], report, trial, expected)
    checks.update(voice_checks)
    compilations = [event for event in events if event['name'] == spec['wrapper_event']
                    and event['ph'] == 'X' and index_event(event) == thread]
    during = [event for event in compilations if began['ts'] <= event['ts']
              and event['ts'] + event['dur'] <= ended['ts']]
    checks['compile_inside_constructor_as_requested'] = len(compilations) == 1 and len(during) == (expected is None)
    checks['both_processors_on_same_audio_thread'] = voice.get('audio_thread') == {'pid': thread[0], 'tid': thread[1]}

    quantum = report['observations'][0][1]
    radius = spec['marker']['constructor_window_radius_quanta'] * quantum
    rows = [(block, callbacks[mapped[block]]) for block in timeline['frames'] if block in mapped]
    neighbours = [{'frame': block, 'next_frame': next_frame,
                   'gap_us': later['ts'] - earlier['ts'],
                   'contains_constructor': earlier['ts'] <= began['ts'] <= ended['ts'] <= later['ts']}
                  for (block, earlier), (next_frame, later) in zip(rows, rows[1:])]
    near = [gap for gap in neighbours if frame - radius <= gap['frame'] < frame + radius]
    ordinary = [gap['gap_us'] for gap in neighbours if gap['next_frame'] < frame - radius]
    across = [gap for gap in near if gap['contains_constructor']]
    checks['constructor_bracketed_by_marker_callbacks'] = len(across) == 1 and bool(ordinary)
    marker.update({'constructor_us': ended['ts'] - began['ts'],
                   'compile_inside_constructor_us': [event['dur'] for event in during],
                   'constructor_gap': across, 'constructor_window_gaps': near,
                   'marker_baseline_gap_median_us': float(np.median(ordinary)) if ordinary else None,
                   'marker_baseline_gap_p99_us': float(np.percentile(ordinary, 99)) if ordinary else None,
                   'marker_baseline_gap_max_us': max(ordinary, default=None)})
    if 'lazy_event' in spec or inspect_tail:
        voice_callbacks = [event for event in callbacks if id(event) not in exclude]
    if 'lazy_event' in spec:
        dsp_checks, dsp = inspect_dsp(spec, events, marks, report, trial, (began, ended), voice_callbacks)
        checks.update(dsp_checks)
        voice['dsp_warmup'] = dsp
    if inspect_tail:
        tail_checks, finish = inspect_tail(spec, events, report, trial, (began, ended), voice_callbacks)
        checks.update(tail_checks)
        voice['finalization'] = finish
    return checks, {**voice, 'shared_context': marker}


def run_shared_study(run_id, case_path, study, *, extra_inputs=(), inspect_capture=inspect_shared_trace):
    warmup_path = release.WORKSPACE / 'cases' / study['warmup_case']
    registered = release.stored.read(warmup_path)
    prior, manifest = release.saved.load_saved_run(
        study['warmup_run'], registered['id'], study['upstream_revision'], ['summary.json'])
    saved_input, = (item['sha256'] for item in release.stored.read(manifest)['inputs']
                    if item['path'].endswith('/' + warmup_path.name))
    summary = release.stored.read(prior['summary.json'])
    if saved_input != release.sha256(warmup_path) or not all(summary['checks'].values()):
        raise ValueError('単独発声の比較記録を照合できません')
    prior_state, = {trial['initialization']['sound_state_sha256'] for trial in summary['trials']}
    measurement = study['measurement']
    measurement['trace_categories'] = [*release.stored.read(
        release.WORKSPACE / 'cases' / registered['threshold_case'])['measurement']['trace_categories'],
        'devtools.timeline']
    return warmup.run_study(run_id, case_path, {**registered, **study}, inspect_capture=inspect_capture,
                            extra_inputs=(Path(__file__).resolve(), warmup_path, manifest, *prior.values(), *extra_inputs),
                            prior_state=prior_state)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    try:
        return run_shared_study(args.run_id, CASE, release.stored.read(CASE))
    except ValueError as error:
        parser.error(str(error))


if __name__ == '__main__':
    raise SystemExit(main())
