"""確認用07の出力予定とプロセスタップのPCMを同じ試行で照合する。"""

from bisect import bisect_right
from collections import Counter
import json
from pathlib import Path
from statistics import median
import sys

import numpy as np
from scipy.interpolate import CubicHermiteSpline

import inspect_firefox_cubeb_output as cubeb
from measure_csd_envelope_timing import verified_file
from measure_speech_timing import read
from measure_tsp_listening import hydrate_run
from smooth_tap_marker import chip_values, fit_wave, injected_controls, waveform
from upstream_baseline import WORKSPACE, sha256


TOOL = Path(__file__).resolve()
BRIDGE = TOOL.with_name('measure_worklet_live_song_process_tap.py')


def tap_inputs(study, revision, device, app):
    options = study['tap']
    spec = study['capture']
    backend, frame, marker = device
    profile = WORKSPACE / 'cases' / options['calibration_case']
    calibration = read(profile)
    parent = profile.with_name(calibration['base_case'])
    calibration = read(parent) | calibration
    record = hydrate_run(options['calibration_run'], calibration['id'], revision)
    effective = verified_file(*record, 'artifacts/effective-case.json')
    summary = verified_file(*record, 'summary.json')
    app = app.resolve(strict=True)
    hashes = {'tap_binary_sha256': sha256(app / 'Contents/MacOS/chimera-process-tap'),
              'tap_info_sha256': sha256(app / 'Contents/Info.plist')}
    required = ('sample_rate', 'buffers_complete', 'block_times_recorded', 'block_times_contiguous',
                'pcm_finite_and_nonzero', 'known_marker_continuous')
    ready_quanta = spec.get('marker_ready_quanta', marker['ready_quanta'])
    if (read(effective) != calibration or calibration['upstream_revision'] != revision or
            calibration['marker']['shape'] != 'smooth-binary' or
            not all(read(summary)['tape']['checks'].get(key) for key in required) or
            any(record[1].get(key) != value for key, value in hashes.items()) or
            not calibration['sample_rate_hz'] == options['sample_rate_hz'] == frame['output_rate_hz'] == backend['sample_rate_hz'] or
            not 0 < spec['tap_attach_quanta'] < ready_quanta < spec['marker_capture_quanta']):
        raise ValueError('採取器の校正、サンプル率、先行音の設定を照合できません')
    options = options | {'smooth_alignment': calibration}
    if 'local_pcm' in study:
        options['local_pcm'] = study['local_pcm']
    marker = marker | {'smooth_marker': calibration['marker'], 'waitForSystemTrace': True, 'ready_quanta': ready_quanta,
                       'trace_attach_quanta': spec['tap_attach_quanta'], 'capture_quanta': spec['marker_capture_quanta'],
                       'maximum_graph_zero_error': calibration['maximum_graph_zero_error'], 'defer_close_until_marker': True}
    if common := options.get('in_phase_marker'):
        difference = calibration['marker']
        if (any(common[key] != difference[key] for key in ('shape', 'chips', 'frames_per_chip'))
                or type(common['seed']) is not int or not 0 < common['seed'] <= 0xffffffff
                or common['seed'] == difference['seed'] or not np.isfinite(common['scale']) or common['scale'] <= 0):
            raise ValueError('同相信号には同じ長さの独立した滑らかな試験信号を指定してください')
        marker['in_phase_marker'] = common
    if spec.get('tap_request_before_marker'):
        marker.update(initial_lead_quanta=spec['marker_lead_quanta'], trace_request_before_marker=True)
    if spec.get('trace_before_playback'):
        marker.update(initial_lead_quanta=spec['marker_lead_quanta'], trace_before_playback=True, waitForSystemTrace=False)
        if spec.get('prime_tap_before_playback'):
            marker['tap_prime_sample_rate_hz'] = frame['output_rate_hz']
    inputs = [TOOL, BRIDGE, TOOL.with_name('chimera_process_tap.swift'), TOOL.with_name('chimera_process_tap_info.plist'),
              profile, parent, record[0] / 'manifest.json', effective, summary,
              *(verified_file(*record, f'artifacts/{name}') for name in ('tap.json', 'tap.f32le'))]
    details = hashes | {'tap_app': str(app), 'tap_calibration_run': options['calibration_run']}
    return (app, options), (backend | options, frame, marker), details, inputs


def capture_tap(execute, folder, settings, app, *, collect=True):
    def run(command, **options):
        settings_path = folder / 'tap-capture-settings.json'
        settings_path.write_text(json.dumps({'capture': settings}) + '\n')
        mode = [] if collect else ['--no-tap']
        return execute([sys.executable, str(BRIDGE), '--browser-bridge', str(app),
                        str(folder), str(settings_path), *mode, '--', *command], **options)
    return run


def zero_spans(stereo):
    zero = np.all(stereo == 0, axis=1)
    edges = np.flatnonzero(np.diff(np.r_[False, zero, False]))
    return edges.reshape(-1, 2).tolist()


def overlap(spans, start, stop):
    return sum(max(0, min(right, stop) - max(left, start)) for left, right in spans)


def insertion_model(reference, observed, gaps):
    parts = []
    previous = 0
    for offset, length in gaps:
        if not previous <= offset <= len(reference) or length <= 0:
            return None
        parts.extend((reference[previous:offset], np.zeros(length)))
        previous = offset
    basis = np.concatenate([*parts, reference[previous:]])
    if len(basis) != len(observed):
        return None
    residual, gain = fit_wave(observed, basis)
    return {'relative_rms_residual': residual, 'gain': gain}


def local_insertion_models(reference, observed, points, settings):
    if len(observed) != len(reference) + sum(size for _, _, size in points):
        return [{'reason': 'tap_length_does_not_match_scheduled_gaps'} for _ in points]
    reports = []
    preceding_end = added = 0
    flank, minimum = (settings[k] for k in ('flank_frames', 'minimum_flank_frames'))
    for i, (early, late, size) in enumerate(points):
        following_start = points[i + 1][0] if i + 1 < len(points) else len(reference)
        start = max(preceding_end, early - flank)
        stop = min(following_start, late + flank)
        if early - start < minimum or stop - late < minimum:
            report = {'reason': 'insufficient_flanks'}
        else:
            data = observed[start + added:stop + added + size]
            basis = reference[start:stop]
            if np.any(data) and np.any(basis):
                models = {label: insertion_model(basis, data, [(offset - start, size)])
                          for label, offset in (('preceding_request', early), ('next_sample_position', late))}
                report = {'reference_window': [start, stop], 'models': models, 'selected': None}
                first, second = sorted(models, key=lambda x: models[x]['relative_rms_residual'])
                a, b = (models[x]['relative_rms_residual'] for x in (first, second))
                if a <= settings['maximum_relative_residual'] and b - a >= settings['minimum_residual_difference']:
                    report['selected'] = first
            else:
                report = {'reason': 'no_marker_energy_in_local_window'}
        reports.append(report)
        preceding_end = late
        added += size
    return reports


def tap_frame(blocks, ticks, delay_frames, frames_per_tick):
    times = [row['hostTime'] for row in blocks]
    # 差を取ってから浮動小数点にし、大きなMach時刻の丸めを避ける。
    index = bisect_right(times, ticks)
    candidates = blocks[max(0, index - 1):index + 1]
    nearest = min(candidates, key=lambda row: abs((ticks - row['hostTime']) * frames_per_tick + delay_frames))
    return nearest['offset'] + (ticks - nearest['hostTime']) * frames_per_tick + delay_frames


def server_tap_rows(gap, blocks, spans, delay_frames, frames_per_tick, window, rate_options):
    writes = gap.get('server_write_cycles', ())
    rows = gap.get('intervening_server_client_cycles', ())
    # 最初のWriteは飛ぶ直前のFirefox要求に対応する。途中のWriteをサンプル位置で結ぶ。
    if not writes:
        return []
    preceding = writes[0]
    low = preceding['start_sample_time'] + gap['request_frames']
    high = low + gap['sample_time_gap_frames']
    output = []
    for row in rows:
        sample = row['output_sample_time']
        matches = [w for w in writes if w['start_sample_time'] == sample and
                   w['stream_index'] == preceding['stream_index'] and low <= sample < high]
        if len(matches) != 1:
            continue
        length = matches[0]['frames']
        position = tap_frame(blocks, row['host_ticks'], delay_frames, frames_per_tick)
        start, stop = round(position), round(position) + length
        error = position - start
        if (length <= 0 or sample + length > high or
                not window[0] <= start < stop <= window[1] or
                abs(error) > rate_options['maximum_server_to_tap_rounding_frames']):
            continue
        output.append({'server_sample_frame': sample, 'server_write_frames': length,
                       'tap_pcm_window': [start, stop], 'tap_rounding_frames': error,
                       'fully_zero_frames': overlap(spans, start, stop)})
    return output


def inspect_tap(folder, core, system, marker, options):
    pair = cubeb.inspect_pair(folder, core, marker, options)
    release = folder / 'trace-release.json'
    ready = release.is_file() and read(release)['tap_ready']
    checks = {'tap_ready_before_construction': ready, 'unique_tap_pcm_and_clock': pair['valid']}
    if not pair['valid']:
        return checks, pair
    rate = options['sample_rate_hz']
    delay_frames = np.asarray(pair['tap_minus_cubeb_host_time_at_window_ends_ms']) * rate / 1000
    stable = abs(delay_frames[1] - delay_frames[0]) <= options['maximum_host_offset_change_frames']
    checks['tap_sample_clock_continuous'] = not pair['tap_sample_clock_jumps']
    checks['stable_tap_to_cubeb_host_offset'] = bool(stable)
    checks['cubeb_marker_continuous'] = core['observations']['pcm_continuous']

    tape = read(folder / 'tap.json')
    pcm = np.fromfile(folder / 'tap.f32le', dtype='<f4').reshape(-1, 2)
    left, right = pair['pcm']['tap_window']
    spans = [[a + left, b + left] for a, b in zero_spans(pcm[left:right])]
    start, stop = core['graph_marker_window']
    raw_window = core['streams'][core['matched_streams'][0]]['pcm']['tap_window']
    difference = (pcm[left:right, 0].astype(float) - pcm[left:right, 1]) / 2
    phase = pair['pcm']['anchors'][0]['fraction']
    spec = options['smooth_alignment']['marker']
    reference = waveform(chip_values(spec), spec, np.arange(start, stop) + phase)
    frames_per_tick = core['host_tick_ms'] * rate / 1000
    gaps = []
    model_points = []
    added = 0
    for gap in system.get('gaps', ()):
        size = int(gap['sample_time_gap_frames'])
        offset = gap['pcm_start_frame'] - raw_window[0]
        if size <= 0 or size != gap['sample_time_gap_frames']:
            pair['gap_analysis_unavailable'] = 'non_positive_or_fractional_gap'
            break
        current = left + offset + added
        next_request = current + gap['request_frames']
        model_points.append((offset, offset + gap['request_frames'], size))
        windows = {}
        for label, position in (('preceding_request', current), ('next_sample_position', next_request)):
            windows[label] = {'tap_pcm_window': [position, position + size],
                              'fully_zero_frames': overlap(spans, position, position + size)}
        server = server_tap_rows(gap, tape['blocks'], spans, float(delay_frames.mean()), frames_per_tick,
                                 [left, right], options) if checks['tap_sample_clock_continuous'] and stable else []
        gaps.append({'request_offset': gap['request_offset'], 'sample_time_gap_frames': size,
                     'candidate_pcm': windows, 'server_pcm': server})
        added += size
    else:
        for index, label in enumerate(('preceding_request', 'next_sample_position')):
            pair.setdefault('zero_insertion_models', {})[label] = insertion_model(
                reference, difference, [(point[index], point[2]) for point in model_points])
        if 'local_pcm' in options:
            local = local_insertion_models(reference, difference, model_points, options['local_pcm'])
            for event, result in zip(gaps, local, strict=True):
                event['local_insertion_models'] = result
    pair['fully_zero_pcm_ranges'] = spans
    pair['gaps'] = gaps
    pair['net_added_pcm_frames'] = right - left - (stop - start)
    pair['server_pcm_unmapped_gaps'] = sum(sum(row['server_write_frames'] for row in g['server_pcm'])
                                           != g['sample_time_gap_frames'] for g in gaps)
    return checks, pair


def onset_anchor_checks(core, requests, system, options):
    checks = {'unique_server_io_for_onset_comparison': system.get('server_candidate_count') == 1}
    protected = False
    if core['valid'] and requests:
        start, stop = core['graph_marker_window']
        start_frame = core['reference_signal']['marker_start_frame']
        width = options['smooth_alignment']['window_frames']
        rows = {row['offset']: row for row in core['graph_rows']}
        starts = [rows[request['offset']]['reference_frame_starts'][0] - start_frame for request in requests]
        protected = all(start + width <= first and first + request['graph_advance_frames'] <= stop - width
                        for first, request in zip(starts, requests, strict=True))
    return checks | {'onset_requests_outside_tap_anchor_windows': protected}


def tap_gap_events(trial):
    system = trial.get('system_io', {})
    tap = trial.get('paired_output', {})
    tap_gaps = {g['request_offset']: g for g in tap.get('gaps', ())}
    offsets = {row['offset']: i for i, row in enumerate(trial.get('device', {}).get('graph_rows', ()))}
    onset_offsets = {row['offset'] for row in trial.get('device_onset_requests', ())}
    for gap in system.get('gaps', ()):
        offset = gap['request_offset']
        client, following = system['client_io']['cycles'][offsets[offset]:offsets[offset] + 2]
        elapsed = client['duration_ns'] / 1e6
        yield {
            'pair': trial['pair'], 'condition': trial['condition'], 'request_offset': offset,
            'includes_onset': offset in onset_offsets, 'gap_frames': gap['sample_time_gap_frames'],
            'callback_ms': gap['callback_ms'], 'client_io_ms': elapsed, 'budget_ms': gap['budget_ms'],
            'callback_within_budget': gap['callback_ms'] <= gap['budget_ms'],
            'client_within_budget': elapsed <= gap['budget_ms'],
            'scheduled_host_minus_return_ms': gap['scheduled_host_minus_return_ms'],
            'client_io_start_interval_ms': gap['client_io_start_interval_ms'],
            'following_client_io_description': following.get('description'),
            'intervening_client_cycles': gap['intervening_client_cycles'],
            'client_minus_cubeb_entry_interval_ms': gap['client_minus_cubeb_entry_interval_ms'],
            'tap_analysis_qualified': tap.get('valid', False) and all(trial['checks'].values()),
            'tap_gap': tap_gaps.get(offset), 'tap_unavailable_reason': tap.get('reason'),
        }


def summarize_draw_tap(trials, maximum_interval_error_ms):
    events = [event for trial in trials for event in tap_gap_events(trial)]
    observed = [event for event in events if event['includes_onset'] and event['callback_within_budget']
                and event['client_within_budget'] and event['intervening_client_cycles'] == 0
                and abs(event['client_minus_cubeb_entry_interval_ms']) <= maximum_interval_error_ms]
    positions = [{'pair': trial['pair'], 'condition': trial['condition'],
                  'marker_frame': trial['device']['center_graph_marker_frame'],
                  'valid': all(trial['checks'].values()),
                  'onset_callback_ms': [r['callback_ms'] for r in trial.get('device_onset_requests', ())]}
                 for trial in trials if 'center_graph_marker_frame' in trial.get('device', {})]
    return {'gaps': events, 'construction_positions': positions,
            'construction_gaps': sum(g['request_offset'] == 0 for g in events),
            'onset_gaps': sum(g['includes_onset'] for g in events),
            'within_budget_onset_gaps': len(observed),
            'within_budget_onset_gaps_with_local_pcm': sum(
                g['tap_analysis_qualified'] and bool((g['tap_gap'] or {}).get('local_insertion_models', {}).get('selected'))
                for g in observed)}


TAP_CONTROL_STAGES = ('wasm_ms', 'worklet_ms', 'graph_ms', 'cubeb_ms', 'client_ms')


def control_trial_timing(trial):
    if not all(trial['checks'].values()):
        return None
    requests = trial['device_onset_requests']
    onset = next((row for row in requests if row['speech_output_frames'] == [0, 128]), None)
    if onset is None:
        return None
    graph_rows = trial['device']['graph_rows']
    offset = onset['offset']
    index, = (i for i, row in enumerate(graph_rows) if row['offset'] == offset)
    start, stop = graph_rows[index]['graph_span_ms']
    client = trial['system_io']['client_io']['cycles'][index]
    phases = trial['phases']['quanta'][:2]
    return {'construction_frame': trial['device']['center_graph_marker_frame'], 'request_offset': offset,
            'wasm_ms': sum(row['wasm_ms'] for row in phases), 'worklet_ms': sum(row['outer_ms'] for row in phases),
            'graph_ms': stop - start, 'cubeb_ms': onset['callback_ms'], 'client_ms': client['duration_ns'] / 1e6}


def summarize_tap_control(trials, settings):
    grouped = {}
    for trial in trials:
        grouped.setdefault(trial['pair'], {})[trial['condition']] = control_trial_timing(trial)
    pairs = []
    for number, group in grouped.items():
        tap, control = group.get('tap'), group.get('no-tap')
        pair = {'pair': number, 'timing': group}
        if tap is None or control is None:
            pair['reason'] = 'capture_or_first_two_quanta_unverified'
        elif (tap['construction_frame'] != control['construction_frame'] or
              abs(tap['construction_frame'] - settings['reference_center_marker_frame']) >
              settings['maximum_center_error_frames']):
            pair['reason'] = 'construction_position_not_matched'
        elif tap['request_offset'] != control['request_offset']:
            pair['reason'] = 'onset_request_position_not_matched'
        else:
            pair['tap_minus_control_ms'] = {k: tap[k] - control[k] for k in TAP_CONTROL_STAGES}
        pairs.append(pair)
    matched = [row['tap_minus_control_ms'] for row in pairs if 'tap_minus_control_ms' in row]
    target = settings['minimum_matched_pairs']
    threshold = settings['minimum_effect_ms']
    stages = {}
    for key in TAP_CONTROL_STAGES:
        values = [row[key] for row in matched]
        center = median(values) if values else None
        shorter = sum(v < 0 for v in values)
        longer = sum(v > 0 for v in values)
        direction = None
        if len(values) >= target and abs(center) >= threshold:
            if center < 0 and shorter >= target:
                direction = 'shorter'
            elif center > 0 and longer >= target:
                direction = 'longer'
        stages[key] = {'median_tap_minus_control_ms': center, 'shorter_with_tap': shorter,
                       'longer_with_tap': longer, 'supported_direction': direction}
    return {'pairs': pairs, 'matched_pairs': len(matched), 'stages': stages,
            'first_repeated_difference': next((k for k, stage in stages.items() if stage['supported_direction']), None),
            'wasm_shorter_as_predicted': stages['wasm_ms']['supported_direction'] == 'shorter' if len(matched) >= target else None}


def summarize_tap_onset(trials, spec):
    groups = {}
    loads_by_pair = {}
    events = []
    for trial in trials:
        pair, condition = trial['pair'], trial['condition']
        requests = trial.get('device_onset_requests', [])
        if requests and all(trial['checks'].values()):
            layout = tuple(len(row['speech_output_frames']) for row in requests)
            worst = max(row['duration_minus_budget_ms'] for row in requests)
            loads_by_pair.setdefault(pair, {})[condition] = (layout, worst)
        events.extend(tap_gap_events(trial))
    for condition in ('split', 'split-late'):
        rows = [pair[condition] for pair in loads_by_pair.values() if condition in pair]
        groups[condition] = {
            'valid_trials': len(rows), 'layouts': dict(Counter('+'.join(map(str, layout)) for layout, _ in rows)),
            'median_worst_callback_minus_budget_ms': median(value for _, value in rows) if rows else None,
        }
    complete = [pair for pair in loads_by_pair.values() if 'split' in pair and 'split-late' in pair]
    changed = sum(pair['split'][0] == (2, 1) and pair['split-late'][0] == (1, 2) for pair in complete)
    full = len(complete) == len(spec['condition_order'])
    return {
        'groups': groups,
        'complete_pairs': len(complete), 'pairs_with_first_quantum_separated': changed,
        'hypothesis': {
            'first_quantum_separated': changed >= spec['minimum_pairs_with_first_quantum_separated'] if full else None,
            'lower_median_worst_callback_minus_budget': (
                groups['split-late']['median_worst_callback_minus_budget_ms']
                < groups['split']['median_worst_callback_minus_budget_ms']) if full else None,
        },
        'gaps': events,
        'onset_gaps': sum(g['includes_onset'] for g in events),
        'within_budget_onset_gaps': sum(g['includes_onset'] and g['callback_within_budget'] for g in events),
    }


def controls(options):
    spec = options['smooth_alignment']
    checks, data = injected_controls(spec)
    preceding, length = 2048, 256
    following = preceding + length
    marker = spec['marker']
    values = chip_values(marker)
    chips = np.r_[values, values[0]] / marker['scale']
    samples = CubicHermiteSpline(np.arange(len(chips)) * marker['frames_per_chip'], chips, np.zeros_like(chips))(
        np.arange(4352) + 0.25)
    observed = np.r_[samples[:preceding], np.zeros(length), samples[preceding:]]
    early = insertion_model(samples, observed, [(preceding, length)])
    late = insertion_model(samples, observed, [(following, length)])
    blocks = [{'offset': 0, 'hostTime': 1000}, {'offset': 2304, 'hostTime': 3304}]
    fake = {'request_frames': length, 'sample_time_gap_frames': length,
            'server_write_cycles': [{'start_sample_time': n, 'stream_index': 0, 'frames': length}
                                    for n in (1024, 1280)],
            'intervening_server_client_cycles': [{'output_sample_time': 1280, 'host_ticks': 3200}]}
    spans = zero_spans(np.column_stack((observed, -observed)))
    mapped, = server_tap_rows(fake, blocks, spans, 104, 1, [0, len(observed)], options)
    checks['injected/zero_insertion_location'] = early['relative_rms_residual'] < 1e-12 < late['relative_rms_residual']
    checks['injected/server_write_pcm_window'] = mapped['tap_pcm_window'] == [following, following + length] and not mapped['fully_zero_frames']
    data['insertion'] = {'preceding_request': early, 'next_sample_position': late, 'server_pcm': mapped}
    if 'local_pcm' in options:
        mixed = np.r_[samples[:preceding], np.zeros(length), samples[preceding:3840], np.zeros(length), samples[3840:]]
        points = [(preceding, following, length), (3840 - length, 3840, length)]
        reports = local_insertion_models(samples, mixed, points, options['local_pcm'])
        checks['injected/independent_insertion_locations'] = [r['selected'] for r in reports] == [
            'preceding_request', 'next_sample_position']
        data['local_insertions'] = reports
    return checks, data
