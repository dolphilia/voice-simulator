"""歌唱ノード構築の前後でFirefoxがCore Audioへ返したPCMを照合する。"""

from ctypes import CDLL, byref, c_uint32
from statistics import median

import numpy as np

import measure_cubeb_output_callback as cubeb
import measure_worklet_live_song_process_tap as tap
import smooth_tap_marker


CASE = tap.song.WORKSPACE / 'cases/worklet-live-song-cubeb-output.json'


def host_tick_ms():
    timebase = (c_uint32 * 2)()
    if CDLL(None).mach_timebase_info(byref(timebase)) or not timebase[1]:
        raise ValueError('Core Audioのホスト時刻の換算に失敗しました')
    return timebase[0] / timebase[1] / 1e6


def resolve_output_window(stereo, marker, case, first, last):
    if 'smooth_alignment' in case:
        return smooth_tap_marker.resolve_window(
            stereo, case['smooth_alignment'], first, last,
            allowance=case['maximum_anchor_displacement_frames'], quiet_amplitude=case['quiet_marker_amplitude'])
    return tap.resolve_marker_window(stereo, marker, case, first, last)


def align_variable_requests(blocks, graph_rows, marker_window, quantum):
    start, end = marker_window
    starts = [i for i, row in enumerate(blocks) if 0 <= start - row['pcm_byte_offset'] // 8 < quantum]
    if len(starts) != 1:
        return None
    first = starts[0]
    selected = blocks[first:first + len(graph_rows) + 1]
    if len(selected) != len(graph_rows) + 1:
        return None
    available = start - selected[0]['pcm_byte_offset'] // 8
    aligned = []
    for index, (graph, block) in enumerate(zip(graph_rows, selected[:-1], strict=True)):
        if graph['requested_frames'] != block['frames'] or not 0 <= available < quantum:
            return None
        aligned.append({'request_offset': graph['offset'], 'block_index': first + index,
                        'frames': block['frames'], 'queued_before_request': available})
        available += graph['graph_advance_frames'] - block['frames']
    if not 0 <= available < quantum or end != selected[-1]['pcm_byte_offset'] // 8 + available:
        return None
    return aligned


def stream_window(folder, marker, case, graph_range, center, tick_ms, *, graph_rows=None, quantum=None):
    blocks = cubeb.load_blocks(folder)
    stereo = np.fromfile(folder / 'pcm.f32le', dtype='<f4').reshape(-1, 2)
    expected_offset = 0
    for row in blocks:
        if row['pcm_byte_offset'] != expected_offset or row['frames'] <= 0:
            return {'valid': False, 'reason': 'invalid_pcm_offsets'}
        expected_offset += row['frames'] * 8
    if expected_offset != len(stereo) * 8 or (folder / 'state.txt').read_text().strip() != 'ready':
        return {'valid': False, 'reason': 'incomplete_pcm'}
    first, last = graph_range
    match = resolve_output_window(stereo, marker, case, first, last)
    if not match['valid']:
        return match
    start, end = match['tap_window']
    alignment = None
    if graph_rows is not None:
        alignment = align_variable_requests(blocks, graph_rows, match['tap_window'], quantum)
        if alignment is None:
            return {'valid': False, 'reason': 'variable_requests_not_aligned', 'pcm': match}
        first_block, last_block = alignment[0]['block_index'], alignment[-1]['block_index'] + 1
    else:
        indices = [i for i, row in enumerate(blocks)
                   if row['pcm_byte_offset'] // 8 < end and
                   row['pcm_byte_offset'] // 8 + row['frames'] > start]
        if not indices:
            return {'valid': False, 'reason': 'missing_request_times', 'pcm': match}
        first_block, last_block = indices[0], indices[-1]
    window = blocks[first_block:last_block + 1]
    min_frames = case['minimum_request_frames'] if alignment else case['expected_request_frames']
    max_frames = case['maximum_request_frames'] if alignment else case['expected_request_frames']
    rate = case['sample_rate_hz']
    if any(not min_frames <= row['frames'] <= max_frames or row['timestamp_flags'] & 3 != 3 or
           not np.isfinite(row['sample_time']) or row['returned'] < row['entered'] for row in window):
        return {'valid': False, 'reason': 'unverified_request_size_or_clock', 'pcm': match}
    intervals = []
    for block_index, (a, b) in enumerate(zip(window, window[1:]), first_block):
        frames = b['sample_time'] - a['sample_time']
        scheduled = (b['host_time'] - a['host_time']) * tick_ms
        if frames <= 0 or abs(scheduled - 1000 * frames / rate) > case['host_clock_tolerance_ms']:
            return {'valid': False, 'reason': 'sample_and_host_clock_disagree', 'pcm': match}
        intervals.append({'block_index': block_index, 'stage': a['stage'],
                          'request_frames': a['frames'], 'budget_ms': 1000 * a['frames'] / rate,
                          'pcm_start_frame': a['pcm_byte_offset'] // 8,
                          'sample_time_gap_frames': frames - a['frames'],
                          'scheduled_interval_ms': scheduled,
                          'entry_interval_ms': (b['entered'] - a['entered']) * tick_ms,
                          'callback_ms': (a['returned'] - a['entered']) * tick_ms,
                          'scheduled_host_minus_entry_ms': (a['host_time'] - a['entered']) * tick_ms,
                          'scheduled_host_minus_return_ms': (a['host_time'] - a['returned']) * tick_ms})
    if 'smooth_alignment' in case:
        positions = [start + center - first] if match['continuous'] else []
    else:
        decoded = tap.decode(stereo[start:end], marker, case['maximum_error_marker_units'])
        if decoded is None:
            return {'valid': False, 'reason': 'center_marker_gain_not_recovered', 'pcm': match}
        _, _, phases, valid = decoded
        positions = [int(i + start) for i in np.flatnonzero(valid & (phases == center % marker['modulus']))]
    # 連番の繰り返しがあれば中央を一意に選べないことも観測結果になる。
    if alignment:
        center_intervals = [row for row, match_row in zip(intervals, alignment, strict=True)
                            if match_row['request_offset'] == 0]
    else:
        center_intervals = [row for row in intervals if any(
            row['pcm_start_frame'] <= position < row['pcm_start_frame'] + row['request_frames'] for position in positions)]
    result = {'valid': True, 'pcm': match, 'stream_blocks': len(blocks), 'intervals': intervals,
              'center_marker_positions': positions, 'center_intervals': center_intervals}
    if alignment:
        result['request_alignment'] = alignment
    return result


def split_requests(trial, rows, stream, last_required=0):
    pieces = trial['timing']['split_preparation']['windows']
    matched = {}
    for piece in pieces:
        candidates = [row for row in rows if piece['context_frame'] in row['reference_frame_starts'] and
                      row['graph_span_ms'][0] <= piece['start_ms'] <= piece['end_ms'] <= row['graph_span_ms'][1]]
        if len(candidates) != 1:
            return False, []
        offset = candidates[0]['offset']
        if offset < 0 or (offset in matched and 'request_alignment' not in stream):
            return False, []
        matched.setdefault(offset, []).append(piece['frames_prepared'])
    if not matched or list(matched) != sorted(matched):
        return False, []
    if 'request_alignment' in stream:
        last_request = max(last_required, max(matched))
        return True, [{'request_offset': item['request_offset'],
                       'completed_pieces': matched.get(item['request_offset'], []),
                       'cubeb_callback_ms': interval['callback_ms'], 'budget_ms': interval['budget_ms']}
                      for item, interval in zip(stream['request_alignment'], stream['intervals'], strict=True)
                      if 0 <= item['request_offset'] <= last_request]
    pcm = stream['pcm']
    pcm_start = pcm['tap_window'][0]
    # PCMの連番が連続しているときだけ、窓の先頭から各要求のPCM位置を計算できる。
    callback_ms_by_offset = ({} if pcm['transitions'] else
                             {interval['pcm_start_frame']: interval['callback_ms'] for interval in stream['intervals']})
    last_request = max(last_required, max(matched))
    intervals = []
    for row in rows:
        if not 0 <= row['offset'] <= last_request:
            continue
        context_start = row['reference_frame_starts'][0]
        offset = pcm_start + context_start - rows[0]['reference_frame_starts'][0]
        intervals.append({'request_offset': row['offset'], 'graph_context_start': context_start,
                          'frames_prepared': matched[row['offset']][-1] if row['offset'] in matched else None,
                          'graph_request_ms': row['duration_ms'],
                          'cubeb_callback_ms': callback_ms_by_offset.get(offset)})
    return True, intervals


def inspect(folder, trial, marker_spec, case, frame_spec, outer_marker, last_preparation_request=0, *, tick_ms=None,
            expected_clock_gap_frames=None):
    callback = tap.callback
    marker = callback.read_json(folder / 'marker.json')
    profile_path = folder / 'firefox-profile.json'
    profile = callback.read_json(profile_path if profile_path.is_file() else profile_path.with_suffix('.json.gz'))
    checks, graph = callback.reconcile(profile, trial['timing'], marker['frames'], frame_spec, outer_marker)
    rows = graph['rows']
    radius = case['window_radius_requests']
    frames = case['expected_request_frames']
    variable = case.get('variable_requests', False)
    if (not all(checks.values()) or len(rows) != 2 * radius + 1 or
            (not variable and any(row['requested_frames'] != frames or row['graph_advance_frames'] != frames for row in rows))):
        return {'valid': False, 'reason': 'graph_window_unverified', 'graph_checks': checks, 'graph_rows': rows}
    first = rows[0]['reference_frame_starts'][0] - marker['startFrame']
    last = rows[-1]['reference_frame_starts'][-1] - marker['startFrame'] + frame_spec['worklet_quantum_frames'] - 1
    center = rows[radius]['reference_frame_starts'][0] - marker['startFrame']
    if first < 0 or last >= len(marker['frames']) * frame_spec['worklet_quantum_frames']:
        return {'valid': False, 'reason': 'outside_saved_marker'}
    if tick_ms is None:
        tick_ms = host_tick_ms()
    streams = {str(stream.relative_to(folder)): stream_window(
        stream, marker_spec, case, (first, last), center, tick_ms, graph_rows=rows if variable else None,
        quantum=frame_spec['worklet_quantum_frames'])
               for stream in sorted((folder / 'cubeb').glob('cubeb-output-*'))}
    matched = [name for name, value in streams.items() if value['valid']]
    result = {'valid': len(matched) == 1, 'matched_streams': matched, 'streams': streams,
              'graph_marker_window': [first, last + 1], 'center_graph_marker_frame': center,
              'client_next_callback_delay_ms': graph['next_callback_delay_ms'], 'host_tick_ms': tick_ms}
    if variable:
        result['graph_rows'] = rows
    if result['valid']:
        stream = streams[matched[0]]
        intervals = stream['center_intervals']
        gap = intervals[0]['sample_time_gap_frames'] if len(intervals) == len(stream['center_marker_positions']) == 1 else None
        expected_gap = (frames if trial['condition'] == 'draw192' else 0
                        ) if expected_clock_gap_frames is None else expected_clock_gap_frames
        pcm = stream['pcm']
        continuous = pcm['continuous'] if 'smooth_alignment' in case else not any(
            pcm[key] for key in ('missing_marker_frames', 'repeated_marker_frames', 'undecoded_frames'))
        result['predictions'] = {'expected_clock_gap_frames': expected_gap, 'observed_clock_gap_frames': gap,
                                 'clock_gap_as_predicted': None if gap is None else gap == expected_gap,
                                 'marker_continuous_as_predicted': continuous}
        if 'split_preparation' in trial['timing']:
            result['split_requests_valid'], result['split_requests'] = split_requests(
                trial, rows, stream, last_preparation_request)
    return result


def split_trial_checks(trial, budget, native_calls):
    core = trial['coreaudio']
    stream = core['streams'][core['matched_streams'][0]]
    song = trial['timing']['song']
    continuous = core['predictions']['marker_continuous_as_predicted'] and not stream['pcm']['silent_frames']
    return {'all_preparation_requests_within_budget': continuous and
            all(ms is not None and ms <= budget for ms in native_calls),
            'both_clocks_contiguous': all(not row['sample_time_gap_frames'] for row in stream['intervals']),
            'marker_pcm_contiguous': continuous,
            'first_two_song_quanta_within_budget': all(ms <= song['budget_ms'] for ms in song['first_two_outer_ms'])}


def summarize_split(trials, case):
    trials_by_id = {row['trial']: row for row in trials}
    budget = 1000 * case['expected_request_frames'] / case['sample_rate_hz']
    verdicts = {}
    for split in (row for row in trials if row['condition'] == 'split192'):
        label = split['trial']
        draw = trials_by_id[label.replace('split192', 'draw192')]
        core = split.get('coreaudio', {})
        if not (core.get('split_requests_valid') and split.get('timing_checks_passed') and draw.get('timing_checks_passed')):
            verdicts[label] = {'valid': False}
            continue
        native_calls = [row['cubeb_callback_ms'] for row in core['split_requests']]
        saved = split_trial_checks(split, budget, native_calls)
        checks = {'constructor_shorter': split['timing']['preparation']['constructor_ms'] <
                                          draw['timing']['preparation']['constructor_ms'], **saved}
        verdicts[label] = {'valid': True, 'checks': checks, 'supports_hypothesis': all(checks.values())}
    return {'request_budget_ms': budget, 'trials': verdicts}


def summarize_deferred(trials, case, spec):
    budget = 1000 * case['expected_request_frames'] / case['sample_rate_hz']
    last = spec['comparison_last_request_offset']
    pairs = []
    for number in range(1, len(spec['condition_order']) + 1):
        pair = {}
        for trial in (t for t in trials if t['trial'].startswith(f'{number}-') and t['condition'] in ('split192', 'deferred192')):
            condition = trial['condition']
            core = trial.get('coreaudio', {})
            if not (trial.get('timing_checks_passed') and core.get('split_requests_valid')):
                pair[condition] = {'valid': False}
                continue
            rows = core['split_requests']
            window = [row for row in rows if row['request_offset'] <= last]
            calls = [row['cubeb_callback_ms'] for row in window]
            prepared_at = [row['request_offset'] for row in rows if row['frames_prepared'] is not None]
            valid = ([row['request_offset'] for row in window] == list(range(last + 1)) and
                     all(ms is not None for ms in calls))
            expected_offsets = list(range(last)) if condition == 'split192' else list(range(1, last + 1))
            pair[condition] = {'valid': valid, 'callback_ms': calls, 'maximum_callback_ms': max(calls) if valid else None,
                               'preparation_requests': prepared_at, 'frames_before_song':
                               trial['timing']['split_preparation']['frames_before_song'],
                               'checks': {**split_trial_checks(trial, budget, calls),
                                          'prepared_on_expected_requests': prepared_at == expected_offsets}}
        current, delayed = (pair[name] for name in ('split192', 'deferred192'))
        if current['valid'] and delayed['valid']:
            pair['peak_reduction_ms'] = current['maximum_callback_ms'] - delayed['maximum_callback_ms']
            pair['same_frames_before_song'] = current['frames_before_song'] == delayed['frames_before_song']
        pairs.append(pair)
    reductions = [p['peak_reduction_ms'] for p in pairs if 'peak_reduction_ms' in p]
    complete = len(reductions) == len(pairs)
    reduction = median(reductions) if complete else None
    checks = {'peak_reduced_by_expected_amount': complete and reduction >= spec['minimum_median_peak_reduction_ms'],
              'all_trial_checks_passed': complete and all(p['same_frames_before_song'] and all(
                  all(p[condition]['checks'].values()) for condition in ('split192', 'deferred192')) for p in pairs)}
    return {'request_budget_ms': budget, 'pairs': pairs, 'median_peak_reduction_ms': reduction,
            'checks': checks, 'supports_hypothesis': all(checks.values())}


def compare_overhead(trials, case):
    result = {}
    limit = case['maximum_instrumentation_constructor_increase_ms']
    for condition in ('control', 'draw192'):
        durations = {row['cubeb_capture']: row['timing']['preparation']['constructor_ms']
                     for row in trials if row['condition'] == condition and row.get('timing_checks_passed')}
        if len(durations) == 2:
            increase = durations[True] - durations[False]
            result[condition] = {'increase_ms': increase, 'within_limit': increase <= limit}
    return result


def inspect_pair(folder, core, marker_spec, case):
    if not core['valid']:
        return {'valid': False, 'reason': 'cubeb_window_unverified'}
    tape_path = folder / 'tap.json'
    pcm_path = folder / 'tap.f32le'
    if not tape_path.is_file() or not pcm_path.is_file():
        return {'valid': False, 'reason': 'tap_not_recorded'}
    tape = tap.callback.read_json(tape_path)
    pcm = np.fromfile(pcm_path, dtype='<f4').reshape(-1, 2)
    rate = case['sample_rate_hz']
    if (tape['sampleRate'] != rate or tape['overflow'] or tape['formatErrors'] or
            tape['frames'] != len(pcm) or not len(pcm) or not np.isfinite(pcm).all()):
        return {'valid': False, 'reason': 'invalid_tap_recording'}

    position = 0
    for row in tape['blocks']:
        if row['offset'] != position or row['frames'] <= 0:
            return {'valid': False, 'reason': 'invalid_tap_offsets'}
        position += row['frames']
    if position != len(pcm):
        return {'valid': False, 'reason': 'incomplete_tap_pcm'}
    first, end = core['graph_marker_window']
    match = resolve_output_window(pcm, marker_spec, case, first, end - 1)
    if not match['valid']:
        return {'valid': False, 'reason': 'tap_window_unverified', 'pcm': match}
    start, end = match['tap_window']
    blocks = [row for row in tape['blocks']
              if row['offset'] < end and row['offset'] + row['frames'] > start]
    if (not blocks or any(row.get('sampleTime') is None or not np.isfinite(row['sampleTime']) or
                          row.get('hostTime') is None for row in blocks)):
        return {'valid': False, 'reason': 'missing_tap_clock', 'pcm': match}
    intervals = list(zip(blocks, blocks[1:]))
    if any(b['hostTime'] <= a['hostTime'] or b['sampleTime'] <= a['sampleTime'] for a, b in intervals):
        return {'valid': False, 'reason': 'backwards_tap_clock', 'pcm': match}
    denom = tape['timebaseDenom']
    tick_ms = tape['timebaseNumer'] / denom / 1e6 if denom else 0
    if not np.isclose(tick_ms, core['host_tick_ms'], rtol=1e-12, atol=0):
        return {'valid': False, 'reason': 'host_timebases_disagree', 'pcm': match}

    stream = core['matched_streams'][0]
    stream_path = folder / stream
    if stream_path.name.rsplit('-', 1)[0] != f"cubeb-output-{tape['pid']}":
        return {'valid': False, 'reason': 'different_audio_process', 'pcm': match}
    cubeb_match = core['streams'][stream]['pcm']
    cubeb_start, cubeb_end = cubeb_match['tap_window']
    cubeb_blocks = cubeb.load_blocks(stream_path)
    offsets_ms = []
    for side, (cubeb_frame, tap_frame) in enumerate(zip((cubeb_start, cubeb_end - 1), (start, end - 1))):
        cb = next(row for row in cubeb_blocks if row['pcm_byte_offset'] // 8 <= cubeb_frame
                  < row['pcm_byte_offset'] // 8 + row['frames'])
        tb = next(row for row in blocks if row['offset'] <= tap_frame < row['offset'] + row['frames'])
        relative_frames = (tap_frame - tb['offset']) - (cubeb_frame - cb['pcm_byte_offset'] // 8)
        if 'smooth_alignment' in case:
            relative_frames += cubeb_match['anchors'][side]['fraction'] - match['anchors'][side]['fraction']
        offsets_ms.append((tb['hostTime'] - cb['host_time']) * tick_ms + relative_frames * 1000 / rate)
    jumps = []
    for a, b in intervals:
        gap = b['sampleTime'] - a['sampleTime'] - a['frames']
        if gap:
            jumps.append({'tap_pcm_frame': b['offset'], 'sample_time_gap_frames': gap})
    return {'valid': True, 'pcm': match, 'tap_sample_clock_jumps': jumps,
            'tap_minus_cubeb_host_time_at_window_ends_ms': offsets_ms,
            'host_time_offset_change_ms': offsets_ms[1] - offsets_ms[0]}
