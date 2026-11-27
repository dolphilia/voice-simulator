"""ブラウザの発話時系列で使った図形と読み取り値を独立に照合する。"""

import re

import numpy as np


def maximum_error(actual, expected):
    actual = np.asarray(actual, dtype=float)
    if actual.shape != expected.shape or not actual.size or not np.isfinite(actual).all():
        return None
    return float(np.max(abs(actual - expected)))


def compare_cursor(record, plot, frames, rate, segments, observed_frames, areas, limits):
    frame = int(record['frame'])
    if not 0 <= frame < frames:
        return {'frame': frame, 'passed': False}
    time = (frame + 1) / rate
    phoneme = next((segment['ipa'] for segment in segments if segment['t0'] <= time < segment['t1']), '—')
    index = int(np.searchsorted(observed_frames, frame, side='right')) - 1
    observation = record['observation']
    area = record['area']
    expected_x = plot['left'] + (plot['right'] - plot['left']) * (time * rate / frames)
    x_error = abs(record['cursorX'] - expected_x)
    area_error = None
    if index >= 0 and area.endswith(' cm²'):
        area_error = abs(float(area.removesuffix(' cm²')) - areas[index])
    status = (observation == area == '—' if index < 0 else
              observation == str(observed_frames[index]) and area_error is not None
              and area_error <= limits['readout_area_tolerance_cm2'])
    return {'frame': frame, 'phoneme': record['phoneme'], 'observation': observation,
            'x_error': x_error, 'area_error_cm2': float(area_error) if area_error is not None else None,
            'passed': (bool(status) and record['slider'] == frame and record['phoneme'] == phoneme
                       and abs(float(record['time'].removesuffix(' s')) - time) <= limits['readout_time_tolerance_seconds']
                       and x_error <= limits['vector_coordinate_tolerance'])}


def compare_view(view, segments, sampled, closed_intervals, wave, rate, frames, limits):
    plot = view['plot']
    start, end = plot['left'], plot['right']
    width = end - start

    def x(elapsed):
        return start + np.asarray(elapsed) * (width / frames)

    actual_phones = [entry[0] for entry in plot['phonemes']]
    phone_start = x([s['t0'] * rate for s in segments])
    phone_end = x([s['t1'] * rate for s in segments])
    closed_left, closed_right = x(closed_intervals).T

    observed_frames, areas = sampled
    lip_points = np.fromstring(plot['lipPoints'].replace(',', ' '), sep=' ').reshape(-1, 2)
    pcm_points = re.findall(r'M([^, ]+),([^V ]+)V([^ ]+)', plot['pcmPath'])
    median_pcm_y = 179
    center_pcm, minimum, maximum = wave
    pcm_radius = 29 / max(-min(minimum), max(maximum))
    errors = {
        'phoneme_geometry': maximum_error([item[1:] for item in plot['phonemes']],
                                         np.column_stack([phone_start, phone_end - phone_start])),
        'closure_geometry': maximum_error(plot['closures'],
                                         np.column_stack([closed_left, closed_right - closed_left])),
        'lip_geometry': maximum_error(lip_points,
                                      np.column_stack([x(observed_frames + 1), 120 - 53 * areas / areas.max()])),
        'pcm_geometry': maximum_error(pcm_points,
                                      np.column_stack([x(center_pcm), median_pcm_y - pcm_radius * maximum,
                                                       median_pcm_y - pcm_radius * minimum])),
    }
    keyboard = [compare_cursor(record, plot, frames, rate, segments, observed_frames, areas, limits)
                for record in view['keyboard']]
    pointer = []
    for record in view['pointer']:
        result = compare_cursor(record, plot, frames, rate, segments, observed_frames, areas, limits)
        wanted = record['fraction'] * frames
        fraction_error = abs(result['frame'] + 1 - wanted) / frames
        pointer.append({**result, 'pointer_error_css_px': fraction_error * width * plot['cssWidth'] / plot['width']})
    checks = {
        'fit': 0 < start < end <= plot['width'] <= view['viewportWidth']
               and abs(plot['cssWidth'] - plot['width']) <= 1,
        'timestamped_geometry': actual_phones == limits['expected_phonemes']
                                and all(v is not None and v <= limits['vector_coordinate_tolerance'] for v in errors.values()),
        'cursor_keyboard': [r['frame'] for r in keyboard] == [0, frames - 1, frames - 2]
                           and all(r['passed'] for r in keyboard),
        'cursor_pointer': ([r['phoneme'] for r in pointer] == limits['expected_cursor_phonemes']
                           and [r['fraction'] for r in view['pointer']] == limits['cursor_fractions']
                           and all(r['passed'] and r['pointer_error_css_px'] <= limits['maximum_pointer_error_css_px']
                                   for r in pointer)),
    }
    return {'viewport_css_px': view['viewportWidth'], 'chart_css_px': plot['cssWidth'],
            'checks': checks, 'errors_svg_units': errors, 'keyboard': keyboard, 'pointer': pointer}


def compare(views, case, reference, observed, pcm, rate, threshold):
    limits = case['measurement']
    segments = [s for entry in reference['plans'] for s in entry['segments']]
    observed_frames = observed['frame'].astype(int)
    areas = observed['lip_minimum_cm2']
    closed = areas < threshold
    first_closed = np.flatnonzero(closed & ~np.r_[False, closed[:-1]])
    first_open = np.flatnonzero(~closed & np.r_[False, closed[:-1]])
    frames = len(pcm)
    closed_start = observed_frames[first_closed] + 1
    closed_end = observed_frames[first_open] + 1
    if closed[-1]:
        closed_end = np.r_[closed_end, frames]
    intervals = np.column_stack([closed_start, closed_end])

    bins = limits['pcm_envelope_bins']
    boundaries = np.arange(bins + 1) * frames // bins
    minima = np.minimum.reduceat(pcm, boundaries[:-1]).astype(float)
    maxima = np.maximum.reduceat(pcm, boundaries[:-1]).astype(float)
    envelope = ((boundaries[1:] + boundaries[:-1]) / 2, minima, maxima)
    results = [compare_view(view, segments, (observed_frames, areas), intervals, envelope, rate, frames, limits)
               for view in views]
    passed = {
        'timeline_observed_edges': [*observed_frames[first_closed], *observed_frames[first_open]] == limits['expected_sampled_lip_edges'],
        'timeline_responsive': ([view['viewport_css_px'] for view in results] == limits['viewport_widths_css_px']
                                and len({view['chart_css_px'] for view in results}) == len(results)),
        'timeline_coordinates_and_navigation': all(all(view['checks'].values()) for view in results),
    }
    stop = next(entry for entry in segments if entry['ipa'] == 'p')
    return passed, {'views': results, 'planned_p_seconds': [stop['t0'], stop['t1']],
                    'sampled_closed_intervals_seconds': (intervals / rate).tolist(),
                    'lip_point_count': len(observed_frames), 'envelope_bins': bins}
