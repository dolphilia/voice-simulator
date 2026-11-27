"""声門の毎フレーム観測、時間窓の波形と読み取り値を照合する。"""

import numpy as np
from scipy.signal import find_peaks

from measure_ipa_timeline import maximum_error

FIELDS = ('glottal_area_cm2', 'glottal_flow_cm3_s')


def compare_trace(actual, expected, limits):
    results = {}
    for i, (name, limit) in enumerate(zip(FIELDS, limits, strict=True)):
        a, b = actual[:, i], expected[name]
        error = abs(a - b)
        first = np.flatnonzero(error)
        excess = np.flatnonzero(error > limit)
        results[name] = {
            'maximum_absolute_error': float(error.max()), 'tolerance': limit,
            'first_frame_over_tolerance': int(excess[0]) if excess.size else None,
            'first_difference': ({'frame': int(first[0]), 'browser': float(a[first[0]]),
                                  'reference': float(b[first[0]])} if first.size else None),
        }
    return results


def window(frame, half, frames):
    return slice(max(frame - half, 0), min(frame + half + 1, frames))


def compare_display(views, spec, all_samples, half):
    scales = (max(0.01, float(all_samples[:, 0].max())), max(1, float(abs(all_samples[:, 1]).max())))
    same_selection = [view['viewportWidth'] for view in views] == spec['viewport_widths_css_px']
    readout_ok = True
    records = []
    for view in views:
        same_selection &= [entry['requested'] for entry in view['selections']] == spec['selected_frames']
        for entry in view['selections']:
            frame = entry['requested']
            actual = window(frame, half, len(all_samples))
            same_selection &= (
                [entry['frame'], entry['first'], entry['last']] == [frame, actual.start, actual.stop - 1]
                and 0 < entry['width'] <= view['viewportWidth'])
            frames = np.arange(actual.start, actual.stop)
            fraction = 0.5 + (frames - frame) / (2 * half)
            errors = {}
            for i, (key, unit) in enumerate((('area', ' cm²'), ('flow', ' cm³/s'))):
                plot = entry['tracks'][key]
                left, right = plot['x']
                top, bottom = plot['range']
                baseline = bottom if key == 'area' else (top + bottom) / 2
                x = left + (right - left) * fraction
                y = baseline - (baseline - top) * all_samples[actual, i] / scales[i]
                points = np.fromstring(plot['points'].replace(',', ' '), sep=' ').reshape(-1, 2)
                error = maximum_error(points, np.column_stack([x, y]))
                errors[key] = (None if error is None or not (left < right and top < bottom) else
                               max(error, abs(baseline - plot['zero']), abs(entry['cursor'] - (left + right) / 2)))
                value = plot['readout']
                readout_ok &= (value.endswith(unit) and bool(
                    np.isclose(float(value.removesuffix(unit)), all_samples[frame, i], rtol=5.1e-5, atol=0)))
            records.append({'viewport_width_css_px': view['viewportWidth'], 'frame': frame,
                            'first': actual.start, 'last': actual.stop - 1, 'maximum_coordinate_errors': errors})
    coordinates = bool(records) and all(error is not None and error <= spec['svg_coordinate_tolerance']
                                        for r in records for error in r['maximum_coordinate_errors'].values())
    return same_selection, coordinates, readout_ok, records


def compare(spec, report, views, cli, upstream, sparse, rate, closed_area):
    trace = report.get('glottal') or {}
    frames = len(cli)
    flat = np.asarray(trace.get('values'), dtype=float)
    if trace.get('columns') != list(FIELDS) or flat.shape != (frames * 2,) or not np.isfinite(flat).all():
        raise ValueError('声門観測の列、フレーム数または有限性が登録条件と一致しません')
    wave = flat.reshape(frames, len(FIELDS))
    cli_result = compare_trace(wave, cli, (0, 0))
    upstream_result = compare_trace(wave, upstream, (spec['area_tolerance_cm2'], spec['flow_tolerance_cm3_s']))
    sparse_values = np.column_stack([sparse[key] for key in FIELDS])
    same_sparse = np.array_equal(wave[sparse['frame'].astype(int)], sparse_values)
    half = round(spec['half_window_seconds'] * rate)
    voiced_window = window(spec['voiced_frame'], half, frames)
    closure_window = window(spec['closure_frame'], half, frames)
    voiced = wave[voiced_window]
    closure = wave[closure_window]
    prominence = spec['peak_prominence_cm2']
    peaks = find_peaks(voiced[:, 0], prominence=prominence)[0] + voiced_window.start
    closed_peaks = find_peaks(closure[:, 0], prominence=prominence)[0]
    intervals = np.diff(peaks)
    predicted = rate / float(cli['glottal_f0_hz'][voiced_window].mean())
    relative = float(abs(intervals / predicted - 1).max()) if intervals.size else None
    selection, coordinates, readout, plotted = compare_display(views, spec, wave, half)
    return {
        'glottal_cli_every_output_frame': all(row['first_difference'] is None for row in cli_result.values()),
        'glottal_upstream_every_output_frame': all(row['first_frame_over_tolerance'] is None
                                                    for row in upstream_result.values()),
        'glottal_sparse_observation_agreement': same_sparse,
        'glottal_voiced_area_and_period': bool(
            np.ptp(voiced[:, 0]) >= spec['voiced_min_area_range_cm2']
            and intervals.size >= spec['min_voiced_peak_intervals'] and relative is not None
            and relative <= spec['voiced_period_relative_tolerance']),
        'glottal_closed_area_and_reverse_flow': bool(
            (cli['lip_minimum_cm2'][closure_window] < closed_area).all()
            and np.ptp(closure[:, 0]) <= spec['closed_max_area_range_cm2']
            and not len(closed_peaks) and closure[:, 1].min() <= -spec['closed_min_reverse_flow_cm3_s']),
        'glottal_window_selection': selection,
        'glottal_wave_coordinates': coordinates,
        'glottal_readouts': readout,
    }, {
        'observed_frames': frames,
        'half_window_frames': half,
        'cli': cli_result, 'upstream': upstream_result,
        'voiced': {'area_range_cm2': float(np.ptp(voiced[:, 0])), 'peaks': peaks.tolist(),
                   'peak_intervals_frames': intervals.tolist(), 'predicted_period_frames': predicted,
                   'peak_interval_max_relative_error': relative},
        'closure': {'area_range_cm2': float(np.ptp(closure[:, 0])), 'mean_area_cm2': float(closure[:, 0].mean()),
                    'minimum_flow_cm3_s': float(closure[:, 1].min()),
                    'minimum_flow_frame': int(closure_window.start + closure[:, 1].argmin())},
        'display': plotted,
    }
