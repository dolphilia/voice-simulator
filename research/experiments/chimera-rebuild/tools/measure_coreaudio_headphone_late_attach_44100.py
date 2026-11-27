"""継続出力にタップを後から接続し、帯域の変化を先行接続と比較する。"""

import argparse
from itertools import groupby
from pathlib import Path
import sys

import numpy as np

from inspect_firefox_cubeb_output import host_tick_ms
from measure_csd_envelope_timing import verified_file
from measure_firefox_headphone_drift_44100 import clock_boundary, compare, first_sustained
from measure_firefox_headphone_response_44100 import read_stereo, continuous_blocks
from measure_speech_timing import read
from measure_uniform_tube import record_measurement
from measure_worklet_fixed import ROOT, WORKSPACE
from smooth_tap_marker import chip_values, find_anchor, marker_pcm


CASE = WORKSPACE / 'cases/coreaudio-headphone-drift-44100-late-attach.json'


def extended_fixture(reference, setup, calibration, silence=None):
    pcm = marker_pcm(setup['fixture_frames'], calibration['marker'])
    prefix, tail = (setup[k] for k in ('identical_prefix_frames', 'tone_end_frame'))
    origin, length = (setup[k] for k in ('period_start_frame', 'period_frames'))
    pcm[:prefix] = reference[:prefix]
    indices = np.arange(prefix, tail)
    tone = reference[origin + (indices - origin) % length]
    overlap = min(128, len(tone))
    weight = np.arange(overlap) / overlap
    ending = pcm[tail-overlap:tail].copy()
    pcm[prefix:tail] = tone
    pcm[tail-overlap:tail] = tone[-overlap:] * (1 - weight) + ending * weight
    if silence and silence['enabled']:
        start, end, width = (silence[key] for key in ('start_frame', 'end_frame', 'ramp_frames'))
        ramp = (1 + np.cos(np.linspace(0, np.pi, width))) * .5
        pcm[start:start+width] *= ramp
        pcm[start+width:end-width] = 0.
        pcm[end-width:end] *= ramp[::-1]
    return pcm


def match_anchors(signal, calibration, case, late):
    setup = case['attach_comparison']
    chips = chip_values(calibration['marker'])
    left, right = setup['terminal_anchors']
    first_tail = find_anchor(signal, chips, calibration, left)
    result = {'tail_first': first_tail}
    if first_tail is None:
        return result
    search = case['trailing_anchor_search_frames']
    second_guess = first_tail['offset'] + right - left
    start = max(0, second_guess - search)
    stop = second_guess + search + calibration['window_frames']
    last_tail = find_anchor(signal[start:stop], chips, calibration, right)
    result['tail_last'] = last_tail
    if last_tail is None:
        return result
    last_tail['offset'] += start
    result['tail_integer_advance'] = last_tail['offset'] - first_tail['offset'] - (right - left)
    if late:
        result['origin_in_pcm'] = first_tail['offset'] - left
    else:
        front = find_anchor(signal[:setup.get('front_search_end_frame')], chips, calibration, case['anchor']['first'])
        result['front'] = front
        if front is not None:
            result['origin_in_pcm'] = front['offset'] - case['anchor']['first']
    return result


def inspect_attach(folder, case, calibration, route, recorded, reference, period):
    output, tape = (read(folder / name) for name in ('native.json', 'tap.json'))
    pcm, tap_pcm = (read_stereo(folder / name) for name in ('native.f32le', 'tap.f32le'))
    tap = (tap_pcm[:, 0] - tap_pcm[:, 1]) * .5
    setup, spec, analysis = (case[key] for key in ('attach_comparison', 'capture_direct', 'analysis'))
    late = 'tap_attach_after_release_seconds' in spec
    active = recorded['during_playback']
    device, = [row for row in active['devices'] if row['id'] == active['defaultOutput']]
    rate = case['sample_rate_hz']
    width = spec['observed_output_expected_frames']
    marks = [{'pcm_frame': row['markerOffset'], 'sample_time': row.get('sampleTime'),
              'host_time': row.get('hostTime'), 'frames': row['frames']} for row in output['frameMarks']]
    last = setup['terminal_anchors'][-1] + calibration['window_frames']
    out_rows = continuous_blocks(marks, 'pcm_frame', 'sample_time', 0, last, width, len(pcm))
    want = np.resize(reference, len(pcm))
    expected_bits = np.column_stack((want, -want)).astype('<f4').tobytes()
    anchor = match_anchors(tap, calibration, case, late) if np.isfinite(tap).all() else {}
    origin = anchor.get('origin_in_pcm')
    start = analysis['first_frames'][0]
    hop = analysis['hop_frames']
    if late and origin is not None:
        start += max(0, (-origin - start + hop - 1)//hop) * hop
    stop = setup['analysis_end_frame']
    tap_rows = continuous_blocks(tape['blocks'], 'offset', 'sampleTime', start + origin, last + origin,
                                 analysis['tap_expected_frames'], len(tap_pcm)) if origin is not None else None
    tick = host_tick_ms()
    checks = {
        'capture_completed': recorded['tap_started'] and recorded['output_exit_code'] == recorded['tap_exit_code'] == 0,
        'tap_pid_matches': output['pid'] == tape['pid'] == recorded['output_pid'],
        'device_rate_and_width': (device['uid'], device['sampleRate'], device['bufferFrames']) ==
                                 (case['output_device']['uid'], rate, width),
        'default_output_restored': route['after']['defaultOutput'] == route['before']['defaultOutput'],
        'raw_pcm_matches_fixture': (folder / 'native.f32le').read_bytes() == expected_bits,
        'output_ok': output['sampleRate'] == rate and output['delayMs'] == 0 and not output['invalidBuffers']
                     and all(mark.get('status') == 0 for mark in output['frameMarks']),
        'tap_ok': tape['sampleRate'] == rate and tape['frames'] == len(tap_pcm)
                  and not tape['overflow'] and not tape['formatErrors'],
        'tap_markers': origin is not None and abs(anchor['tail_integer_advance']) <= 1,
    }
    for key, rows, evidence, host in (('direct', out_rows, output, 'host_time'), ('tap', tap_rows, tape, 'hostTime')):
        checks[f'{key}_clock'] = bool(rows and all(r.get(host) is not None for r in rows)
            and all(b[host] > a[host] for a, b in zip(rows, rows[1:]))
            and np.isclose(evidence['timebaseNumer'] / evidence['timebaseDenom'] / 1e6, tick, rtol=1e-12, atol=0))
    result = {'checks': checks, 'attachment': 'late' if late else 'before', 'active_output_device': device,
              'anchor': anchor, 'tap_launch_after_release_seconds': recorded.get('seconds_from_release_to_tap_launch')}
    if not all(checks.values()):
        return result
    silence = case.get('silence_comparison')
    aligned = tap[origin:] if origin >= 0 else np.pad(tap, (-origin, 0))
    direct = (pcm[:, 0] - pcm[:, 1]) * .5
    prior_event = clock_boundary(marks, 'pcm_frame', 'sample_time', 'host_time',
                                 setup['prior_event_output_frame'], 0, rate)
    first_tap = tape['blocks'][0]['hostTime']
    result['first_tap_host_ticks'] = first_tap
    result['first_output_host_ticks'] = marks[0]['host_time']
    delta = first_tap * tick - prior_event['event_host_ns_from_block'] / 1e6
    result['first_tap_ms_from_prior_event'] = delta
    checks['expected_attachment_order'] = delta >= setup['minimum_late_after_prior_event_ms'] if late else delta < 0
    if late:
        window = analysis['window_frames']
        pilot_bin = round(analysis['reference_tone_hz'] * window / rate)
        starts = range(start, stop-window+1, hop)
        ratios = [abs(np.fft.rfft(aligned[i:i+window])[pilot_bin] / np.fft.rfft(direct[i:i+window])[pilot_bin])
                  for i in starts]
        lo, hi = setup['pilot_amplitude_ratio_bounds']
        found = first_sustained([lo <= ratio <= hi for ratio in ratios], analysis['minimum_consecutive_windows'])
        checks['usable_pilot_observed'] = found is not None
        if found is None:
            return result
        start = starts[found]
        checks['late_observation_duration'] = (stop - start) / rate >= setup['minimum_late_observation_seconds']
    elif not setup.get('early_full_analysis'):
        stop = analysis['last_exclusive']
    pre_stop = silence['pre_last_exclusive'] if silence else stop
    result['observed_source_frames'] = [start, pre_stop]
    result['observation_seconds'] = (pre_stop - start) / rate
    options = analysis | {'first_frames': [start], 'last_exclusive': pre_stop}
    clock = {'cubeb': marks, 'tap': tape['blocks'], 'cb_origin': 0, 'tb_origin': origin}
    measured = compare(direct, aligned, period, case | {'analysis': options}, clock)
    checks['direct_tone_fits'] = measured['checks']['cubeb_tone_fits']
    outcome = measured['predictions']
    outcome['initial_band_matches_prior'] = measured['checks']['initial_band_matches_prior']
    for event in measured['events'].values():
        event['direct'] = event.pop('cubeb')
    for row in measured['windows']:
        row['direct_residual'] = row.pop('cubeb_residual')
    slopes = [row['pilot_slope_from_previous_ppm'] for row in measured['windows'][1:]]
    positive = first_sustained(np.asarray(slopes) > analysis['phase_slope_threshold_ppm'],
                              analysis['minimum_consecutive_windows'])
    outcome['positive_pilot_seen'] = positive is not None
    high = [f['amplitude_ratio'] for row in measured['windows'] for f in row['frequencies']
            if f['hz'] == analysis['band_tone_hz']]
    outcome['minimum_band_ratio'] = min(high)
    outcome['maximum_band_ratio'] = max(high)
    outcome['wide_band_in_all_windows'] = min(high) >= setup['wide_band_lower_limit']
    if silence:
        after = analysis | {'first_frames': [silence['post_first_frame']], 'last_exclusive': stop}
        post = compare(direct, aligned, period, case | {'analysis': after}, clock)
        checks['resumption_direct_tone_fits'] = post['checks']['cubeb_tone_fits']
        result['resumption'] = inspect_resumption(high, post, silence, case) | gap_capture_metrics(
            pcm, tap_pcm, origin, silence)
        checks['gap_input_as_registered'] = result['resumption']['direct_gap']['all_frames_zero'] == silence['enabled']
    return {**result, **{key: measured[key] for key in ('predictions', 'events', 'windows')}}


def gap_capture_metrics(direct, tap, origin, silence):
    start, stop = (silence[key] for key in ('start_frame', 'end_frame'))
    lo = silence['start_frame'] + silence['quiet_margin_frames']
    hi = silence['end_frame'] - silence['quiet_margin_frames']
    gap_metrics = {}
    for label, pcm, offset in (('direct', direct, 0), ('tap', tap, origin)):
        samples = pcm[lo+offset:hi+offset]
        quiet = bool(np.all(samples == 0))
        metrics = {'all_frames_zero': quiet, 'peak': float(np.max(abs(samples))),
                   'rms': float(np.sqrt(np.mean(samples**2)))}
        if quiet:
            active = np.flatnonzero(np.any(pcm[start+offset:stop+offset] != 0, axis=1))
            mid = (stop - start) // 2
            left = active[active < mid].max(initial=-1) + 1
            right = active[active >= mid].min(initial=stop-start)
            metrics['zero_span_within_gap_in_output_frames'] = [int(start + left), int(start + right)]
        gap_metrics[f'{label}_gap'] = metrics
    return gap_metrics


def inspect_resumption(before_ratios, post, silence, case):
    analysis = case['analysis']
    window_count = silence['pre_band_window_count']
    pre = before_ratios[-window_count:]
    high = np.asarray([f['amplitude_ratio'] for row in post['windows'] for f in row['frequencies']
                       if f['hz'] == analysis['band_tone_hz']])
    threshold = analysis['reduced_band_upper_limit']
    required = analysis['minimum_consecutive_windows']
    wide = first_sustained(high >= case['attach_comparison']['wide_band_lower_limit'], required)
    later_start = wide + required if wide is not None else len(high)
    narrower = first_sustained(high[later_start:] < threshold, required) if len(high) - later_start >= required else None
    centers = [sum(row['source_frames']) // 2 for row in post['windows']]
    return {'gap_applied': silence['enabled'], 'pre_median_ratio': float(np.median(pre)),
            'pre_narrow_in_all_windows': len(pre) == window_count and max(pre) < threshold,
            'post_frames': [post['windows'][0]['source_frames'][0], post['windows'][-1]['source_frames'][1]],
            'post_first_ratio': float(high[0]), 'post_median_ratio': float(np.median(high)),
            'post_maximum_ratio': float(max(high)), 'post_narrow_in_all_windows': bool(max(high) < threshold),
            'post_wide_first_center': centers[wide] if wide is not None else None,
            'post_drop_after_wide_center': centers[later_start + narrower] if narrower is not None else None,
            'windows': post['windows']}


def phase_across_gap(before, after, direct, tape, origin, pilot_hz):
    after_window, before_window = after['windows'][0], before['windows'][-1]
    centers = [sum(row['source_frames']) // 2 for row in (before_window, after_window)]
    degrees = [next(tone['raw_phase_degrees'] for tone in row['frequencies'] if tone['hz'] == pilot_hz)
               for row in (before_window, after_window)]
    rate = tape['sampleRate']
    changes = {}
    for label, rows, field, offset in (('direct', direct['frameMarks'], 'markerOffset', 0),
                                        ('tap', tape['blocks'], 'offset', origin)):
        left, right = (clock_boundary(rows, field, 'sampleTime', 'hostTime', center, offset, rate) for center in centers)
        changes[label] = (right['containing']['host_ticks'] - left['containing']['host_ticks'],
                          right['frames_after_block_start'] - left['frames_after_block_start'])
    direct_ticks, direct_frames = changes['direct']
    tap_ticks, tap_frames = changes['tap']
    tick_ns = tape['timebaseNumer'] / tape['timebaseDenom']
    host_shift = (tap_ticks - direct_ticks) * tick_ns * rate / 1e9 + tap_frames - direct_frames
    phase_shift = ((degrees[1] - degrees[0] + 180) % 360 - 180) * rate / (360 * pilot_hz)
    return {'source_window_centers': centers, 'wrapped_pilot_change_frames': phase_shift,
            'host_elapsed_difference_frames': host_shift, 'wrapped_phase_minus_host_frames': phase_shift - host_shift}


def attachment_timing(measured, direct, tape, drift, setup):
    tick = tape['timebaseNumer'] / tape['timebaseDenom'] / 1e6
    rate = tape['sampleRate']
    first_direct, first_tap = direct['frameMarks'][0]['hostTime'], tape['blocks'][0]['hostTime']
    result = {'first_tap_after_output_ms': (first_tap - first_direct) * tick}
    windows = measured['windows']
    level = np.asarray([tone['amplitude_ratio'] for row in windows for tone in row['frequencies']
                        if tone['hz'] == drift['band_tone_hz']])
    required = drift['minimum_consecutive_windows']
    wide = first_sustained(level >= setup['wide_band_lower_limit'], required)
    if wide is None:
        return result
    result['wide_source_frame'] = sum(windows[wide]['source_frames']) // 2
    start = wide + required
    if len(level) - start < required:
        return result
    reduced = first_sustained(level[start:] < drift['reduced_band_upper_limit'], required)
    if reduced is None:
        return result
    frame = sum(windows[start + reduced]['source_frames']) // 2
    origin = measured['anchor']['origin_in_pcm']
    out = clock_boundary(direct['frameMarks'], 'markerOffset', 'sampleTime', 'hostTime', frame, 0, rate)
    tap = clock_boundary(tape['blocks'], 'offset', 'sampleTime', 'hostTime', frame, origin, rate)
    result['band_drop_source_frame'] = frame
    for label, point, first in (('output', out, first_direct), ('tap', tap, first_tap)):
        result[f'band_drop_ms_from_first_{label}'] = (
            (point['containing']['host_ticks'] - first) * tick + point['frames_after_block_start'] * 1e3 / rate)
    return result


def compare_attachment_times(short, long, settings):
    valid = short['manifest_status'] == long['manifest_status'] == 'pass'
    if not valid:
        return {'capture_valid': False, 'classification': 'capture_failed'}
    a, b = (trial['attachment_timing'] for trial in (short, long))
    gap = b['first_tap_after_output_ms'] - a['first_tap_after_output_ms']
    low, high = settings['start_gap_change_ms_range']
    separated = low <= gap <= high
    result = {'capture_valid': True, 'start_clocks_separated': separated, 'start_gap_change_ms': gap}
    if not separated:
        return {**result, 'classification': 'start_gap_outside_range'}
    if 'band_drop_source_frame' not in a or 'band_drop_source_frame' not in b:
        return {**result, 'classification': 'band_drop_missing'}
    output_change = b['band_drop_ms_from_first_output'] - a['band_drop_ms_from_first_output']
    tap_change = b['band_drop_ms_from_first_tap'] - a['band_drop_ms_from_first_tap']
    tolerance = settings['maximum_reference_error_ms']
    if abs(tap_change) <= tolerance and abs(output_change - gap) <= tolerance:
        classification = 'tap_start'
    elif abs(output_change) <= tolerance and abs(tap_change + gap) <= tolerance:
        classification = 'output_start'
    else:
        classification = 'neither'
    return {**result, 'classification': classification, 'band_drop_output_change_ms': output_change,
            'band_drop_tap_change_ms': tap_change, 'band_drop_frame_change': b['band_drop_source_frame'] - a['band_drop_source_frame']}


def recurrence_profile(measured, rules, setup, drift, rate):
    windows = measured['windows']
    level = [tone['amplitude_ratio'] for row in windows for tone in row['frequencies'] if tone['hz'] == drift['band_tone_hz']]
    centers = [sum(row['source_frames']) // 2 for row in windows]
    labels = ['wide' if value >= setup['wide_band_lower_limit']
              else 'reduced' if value < drift['reduced_band_upper_limit'] else 'transition' for value in level]
    spans = []
    for label, group in groupby(enumerate(labels), key=lambda point: point[1]):
        indices = [index for index, _ in group]
        if label != 'transition' and len(indices) >= drift['minimum_consecutive_windows']:
            spans.append({'band': label, 'centers': [centers[indices[0]], centers[indices[-1]]],
                          'windows': len(indices), 'median_amplitude_ratio': float(np.median([level[i] for i in indices]))})
    drops = [row['centers'][0] for previous, row in zip(spans, spans[1:])
             if previous['band'] == 'wide' and row['band'] == 'reduced']
    interval = rules['interval_frames']
    tolerance = rules['maximum_interval_error_frames']
    reference = rules['reference_drop_frames']
    reference_matches = len(drops) >= len(reference) and all(abs(a - b) <= tolerance for a, b in zip(drops, reference))
    gaps = [b - a for a, b in zip(drops, drops[1:])]
    prefix_length = next((i + 1 for i, gap in enumerate(gaps) if abs(gap - interval) > tolerance), len(drops))
    continued = sum(frame >= rules['after_seconds'] * rate for frame in drops[:prefix_length]) if reference_matches else 0
    final = spans[-1] if spans and spans[-1]['centers'][1] == centers[-1] else None
    stable_until_end = bool(final and final['centers'][1] - final['centers'][0] >=
                            rules['minimum_terminal_observation_intervals'] * interval)
    expected_next = drops[-1] + interval if drops else None
    return {'band_spans': spans, 'observed_window_centers': [centers[0], centers[-1]],
            'drop_frames': drops, 'interval_frames': gaps, 'reference_drop_frames_match': reference_matches,
            'consecutive_matching_drop_count': prefix_length, 'matching_drops_after_boundary': continued,
            'prediction_matched': reference_matches and continued >= rules['minimum_extra_qualified_drops'],
            'stable_until_end': stable_until_end, 'terminal_band': final,
            'expected_next_drop_frame': expected_next,
            'next_expected_drop_within_observation': expected_next is not None and expected_next <= centers[-1]}


def main():
    from measure_firefox_headphone_clock_plateaus_44100 import CASE as CLOCK_CASE, estimate_clock, slope_fit, track

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('--case', type=Path, default=CASE)
    args = parser.parse_args()
    registered = args.case.resolve()
    case = read(registered)
    base = registered.with_name(case['capture_base'])
    capture_base = read(base)
    drift_path = base.with_name(capture_base['base_case'])
    drift_analysis = read(drift_path)['analysis']
    clock_spec = read(CLOCK_CASE) | {'clock_reference': 'direct'}
    inputs = [registered, base, drift_path, CLOCK_CASE, Path(__file__).resolve(),
              Path(__file__).with_name('measure_firefox_headphone_clock_plateaus_44100.py')]
    timing = case.get('timing_comparison')
    recurrence = case.get('recurrence')
    silence = case.get('silence_comparison')
    if timing is not None:
        attach_case = registered.with_name(case['attach_reference_case'])
        inputs.append(attach_case)
        setup = read(attach_case)['attach_comparison']
    if recurrence is not None:
        setup = case['attach_comparison']
        preserved = registered.with_name(case['preserved_case'])
        old_run = WORKSPACE / 'runs' / case['reference_run']
        old_manifest = old_run / 'manifest.json'
        old = read(old_manifest)
        if (old['status'] != 'pass' or old['case_id'] != read(preserved)['id']
                or old['run_id'] != case['reference_run']):
            parser.error('間隔の算出に使った保存済みの実行と一致しません')
        inputs.extend((preserved, old_manifest, verified_file(old_run, old, 'summary.json')))
    if silence is not None:
        long_case = registered.with_name(case['attach_reference_case'])
        old_run = WORKSPACE / 'runs' / case['reference_run']
        old_manifest = old_run / 'manifest.json'
        old = read(old_manifest)
        if (old['status'], old['case_id'], old['run_id']) != ('pass', read(long_case)['id'], case['reference_run']):
            parser.error('長い直接出力の基準実行と一致しません')
        inputs.extend((long_case, old_manifest, verified_file(old_run, old, 'summary.json')))
    trials = {}
    revisions = set()
    for trial in case['trials']:
        key = trial['run_id']
        folder = WORKSPACE / 'runs' / key
        manifest_file = folder / 'manifest.json'
        manifest = read(manifest_file)
        revisions.add(manifest['upstream_revision'])
        if (manifest['run_id'], manifest['case_id'], manifest['case_revision']) != (key, case['id'], case['revision']):
            parser.error(f'{key} は登録した試行と一致しません')
        inputs.append(manifest_file)
        info = {'checks': {}, 'manifest_status': manifest['status']}
        if any(item['path'] == 'summary.json' for item in manifest['outputs']):
            path = verified_file(folder, manifest, 'summary.json')
            inputs.append(path)
            measured = read(path)
            info.update({k: v for k, v in measured.items() if k not in ('windows', 'resumption')})
            if manifest['status'] == 'pass':
                direct_file, tap_file = (verified_file(folder, manifest, f'artifacts/native/{kind}.json')
                                         for kind in ('native', 'tap'))
                inputs.extend((direct_file, tap_file))
                direct, tap = read(direct_file), read(tap_file)
                tick = tap['timebaseNumer'] / tap['timebaseDenom']
                origin = measured['anchor']['origin_in_pcm']
                clock = {'direct': [(r['markerOffset'], r['hostTime']) for r in direct['frameMarks'] if 'hostTime' in r],
                         'tap': [(r['offset'] - origin, r['hostTime']) for r in tap['blocks']], 'tick': tick}
                info['clock_plateaus'] = track(clock, measured, clock_spec)
                info['event_ms_from_first_tap_timestamp'] = {
                    key: (point['tap']['containing']['host_ticks'] - tap['blocks'][0]['hostTime']) * tick / 1e6
                         + point['tap']['frames_after_block_start'] * 1000 / tap['sampleRate']
                    for key, point in measured['events'].items() if point['tap'] is not None}
                info['first_band_ratio'], = [tone['amplitude_ratio'] for tone in measured['windows'][0]['frequencies']
                                             if tone['hz'] == drift_analysis['band_tone_hz']]
                positive = first_sustained(
                    [row['pilot_slope_from_previous_ppm'] > drift_analysis['phase_slope_threshold_ppm']
                     for row in measured['windows'][1:]], drift_analysis['minimum_consecutive_windows'])
                info['first_positive_pilot_source_frame'] = (
                    sum(measured['windows'][positive + 1]['source_frames']) // 2 if positive is not None else None)
                if timing is not None:
                    info['attachment_timing'] = attachment_timing(measured, direct, tap, drift_analysis, setup)
                if silence is not None:
                    resumed = measured['resumption']
                    if resumed['gap_applied'] != trial['apply_silence']:
                        parser.error(f'{key} の無音条件が登録値と一致しません')
                    info['resumption'] = {k: v for k, v in resumed.items() if k != 'windows'}
                    samples = [verified_file(folder, manifest, f'artifacts/native/{kind}.f32le')
                               for kind in ('native', 'tap')]
                    inputs.extend(samples)
                    out_pcm, tap_pcm = map(read_stereo, samples)
                    info['resumption'].update(gap_capture_metrics(out_pcm, tap_pcm, origin, silence))
                    info['resumption']['clock_plateaus'] = track(clock, resumed, clock_spec)
                    info['resumption']['phase_across_gap'] = phase_across_gap(
                        measured, resumed, direct, tap, origin, drift_analysis['reference_tone_hz'])
                if recurrence is not None:
                    profile = recurrence_profile(measured, recurrence, setup, drift_analysis, tap['sampleRate'])
                    info['recurrence'] = profile
                    if profile['stable_until_end']:
                        start, stop = profile['terminal_band']['centers']
                        start += recurrence['minimum_terminal_observation_intervals'] * recurrence['interval_frames']
                        centers = [(sum(row['source_frames']) // 2, row['pilot_offset_frames']) for row in measured['windows']]
                        points = [(center, phase) for center, phase in centers if start <= center <= stop]
                        if stop - start >= 2 * capture_base['capture_direct']['observed_output_expected_frames']:
                            ts, phase = zip(*points, strict=True)
                            pilot, _ = slope_fit(ts, phase)
                            nominal = 1e9 / tap['sampleRate']
                            times = {point: estimate_clock(clock[point], start, stop, tick, nominal)
                                     for point in ('direct', 'tap')}
                            difference = (times['tap']['ns_per_frame'] - times['direct']['ns_per_frame']) / nominal * 1e6
                            profile['terminal_clock'] = {'centers': [start, stop], 'pilot_slope_ppm': pilot * 1e6,
                                                         'host_difference_ppm': difference, 'clocks': times}
        trials[key] = info
    revision, = revisions

    def measure(folder, execute):
        if silence is not None:
            pairs = []
            for continued, gap in case['pairs']:
                a, b = (trials[key].get('resumption') for key in (continued, gap))
                valid = a is not None and b is not None
                conditioned = valid and a['pre_narrow_in_all_windows'] and b['pre_narrow_in_all_windows']
                quiet = valid and b['direct_gap']['all_frames_zero'] and b['tap_gap']['all_frames_zero']
                pairs.append({'continuous': continued, 'silence': gap, 'capture_valid': valid, 'pre_band_narrow': conditioned,
                              'silence_verified_in_stereo': quiet,
                              'control_wide_after_gap': a['post_wide_first_center'] is not None if valid else None,
                              'silence_wide_after_gap': b['post_wide_first_center'] is not None if valid else None,
                              'silence_narrow_through_post': b['post_narrow_in_all_windows'] if valid else None})
            return {'checks': {'all_pairs_captured': all(pair['capture_valid'] for pair in pairs),
                               'all_pairs_initially_narrow': all(pair['pre_band_narrow'] for pair in pairs),
                               'all_stereo_gaps_verified': all(pair['silence_verified_in_stereo'] for pair in pairs)},
                    'prediction_matched': all(pair['pre_band_narrow'] and pair['silence_verified_in_stereo']
                                              and pair['silence_narrow_through_post']
                                              and not pair['control_wide_after_gap'] for pair in pairs),
                    'pairs': pairs, 'trials': trials}
        if recurrence is not None:
            return {'checks': {'all_trials_captured': all(row['manifest_status'] == 'pass' for row in trials.values())},
                    'prediction_matched': all(row.get('recurrence', {}).get('prediction_matched', False)
                                              for row in trials.values()), 'trials': trials}
        if timing is not None:
            pairs = [{'short_wait': short, 'long_wait': long, **compare_attachment_times(trials[short], trials[long], timing)}
                     for short, long in case['pairs']]
            counts = {state: sum(row['classification'] == state for row in pairs)
                      for state in sorted({row['classification'] for row in pairs})}
            return {'checks': {'all_pairs_captured': all(row['capture_valid'] for row in pairs),
                               'start_clocks_separated': all(row.get('start_clocks_separated', False) for row in pairs)},
                    'prediction_matched': counts.get('tap_start', 0) >= timing['minimum_tap_aligned_pairs'],
                    'pair_counts': counts, 'pairs': pairs, 'trials': trials}
        pairs = []
        for before, late in case['pairs']:
            a, b = (trials[k] for k in (before, late))
            valid = a['manifest_status'] == b['manifest_status'] == 'pass'
            reproduced = (valid and a['predictions']['band_drop_seen'] and a['predictions']['positive_pilot_seen']
                          and a['events']['waveform_departure']['source_frame'] == case['attach_comparison']['prior_event_output_frame'])
            pairs.append({'before': before, 'late': late, 'capture_valid': valid, 'early_reproduced': reproduced,
                          'late_band_drop_seen': b['predictions']['band_drop_seen'] if valid else None})
        return {'checks': {'all_pairs_captured': all(pair['capture_valid'] for pair in pairs)},
                'prediction_matched': sum(pair['early_reproduced'] and pair['late_band_drop_seen'] is False for pair in pairs) >= 2,
                'pairs': pairs, 'trials': trials}
    metadata = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision,
                'analysis_command': [sys.executable, *sys.argv]}
    return record_measurement(args.run_id, registered, inputs, metadata, measure, command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
