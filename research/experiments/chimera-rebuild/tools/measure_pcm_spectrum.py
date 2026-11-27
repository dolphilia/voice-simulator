"""保存WAVと固定上流PCMから、窓・片側振幅・表示座標を独立に照合する。"""

import numpy as np
from scipy.fft import rfft, rfftfreq
from scipy.signal.windows import blackman

from measure_ipa_timeline import maximum_error
from measure_wasm_fixed import read_json


def reference_spectrum(pcm, frame, window):
    size = len(window)
    first = frame - size // 2
    indices = np.arange(first, first + size)
    sample_mask = (indices >= 0) & (indices < len(pcm))
    segment = np.zeros(size)
    segment[sample_mask] = pcm[indices[sample_mask]]
    amplitude = 2 * abs(rfft(window * segment)) / window.sum()
    amplitude[[0, -1]] /= 2
    return amplitude


def compare_bin_amplitudes(actual, expected, tolerance):
    delta = abs(actual - expected)
    nonzero = np.flatnonzero(delta)
    excess = np.flatnonzero(delta > tolerance)
    return {
        'maximum_absolute_error': float(delta.max()),
        'first_difference_bin': int(nonzero[0]) if nonzero.size else None,
        'first_bin_over_tolerance': int(excess[0]) if excess.size else None,
    }


def analytic_passes(actual, spec):
    return (actual['tone_bin'] == spec['tone_bin'] and actual['silence_peak'] == 0
            and all(abs(actual[key] - spec[key]) <= spec['amplitude_tolerance']
                    for key in ('tone_peak', 'dc_peak', 'nyquist_peak')))


def compare(spec, artifacts, views, browser, native, upstream, rate, cli_state, closed_area):
    size = spec['fft_size']
    window = blackman(size, sym=False)
    freqs = rfftfreq(size, 1 / rate)
    minimum_hz, maximum_hz = spec['frequency_range_hz']
    maximum_hz = min(rate / 2, maximum_hz)
    mask = (minimum_hz <= freqs) & (freqs <= maximum_hz)
    shown_bins = np.flatnonzero(mask)
    db_min = spec['display_min_dbfs']
    expected_frames = spec['selected_frames']
    selected = [view['viewportWidth'] for view in views] == spec['viewport_widths_css_px']
    readouts = True
    metadata = True
    records = []
    peaks = {}
    for view in views:
        width = view['viewportWidth']
        selected &= [item['requested'] for item in view['selections']] == expected_frames
        for item in view['selections']:
            frame = item['requested']
            start = frame - size // 2
            source_start, source_end = max(0, start), min(len(browser), start + size)
            data = read_json(artifacts / item['filename'])
            actual = np.asarray(data.pop('amplitudes'), dtype=float)
            if actual.shape != freqs.shape or not np.isfinite(actual).all() or (actual < 0).any():
                raise ValueError('スペクトルのビン数または振幅値が条件外です')
            metadata &= data == {
                'source': 'rendered-pcm', 'frame': frame, 'sampleRate': rate, 'fftSize': size,
                'window': spec['window'], 'firstFrame': start, 'sourceFirstFrame': source_start,
                'sourceEndFrame': source_end, 'normalization': 'one-sided-peak-full-scale',
            }
            selected &= item['frame'] == frame and 0 < item['width'] <= width
            readouts &= (item['source'] == '保存WAVと同じPCM'
                         and item['samples'] == f'{source_end - source_start} / {size}'
                         and item['browserFilename'] == f'pcm-spectrum-{frame}.json')
            reference = {
                key: compare_bin_amplitudes(actual, reference_spectrum(pcm, frame, window), limit)
                for key, pcm, limit in (
                    ('browser_wav', browser, spec['independent_fft_absolute_tolerance']),
                    ('cli', native, spec['independent_fft_absolute_tolerance']),
                    ('upstream', upstream, spec['upstream_amplitude_absolute_tolerance']),
                )
            }
            peak_bin = shown_bins[actual[mask].argmax()]
            peak_hz = float(freqs[peak_bin])
            peak_db = float(20 * np.log10(actual[peak_bin])) if actual[peak_bin] > 0 else None
            peak = item['peak']
            if peak_db is None:
                readouts &= peak == '—'
            else:
                hz, db = peak.split(' Hz · ')
                readouts &= abs(float(hz) - peak_hz) <= 0.0051 and abs(float(db.removesuffix(' dBFS')) - peak_db) <= 0.0051
            left, top, span, height = item['axis']
            x = left + span * np.log(freqs[mask] / minimum_hz) / np.log(maximum_hz / minimum_hz)
            clipped = np.minimum(0, 20 * np.log10(np.maximum(actual[mask], 10 ** (db_min / 20.0))))
            y = top + height * clipped / db_min
            coords = np.fromstring(item['points'].replace(',', ' '), sep=' ').reshape(-1, 2)
            error = maximum_error(coords, np.column_stack((x, y)))
            peaks[frame] = peak_hz, peak_db
            records.append({'viewport_width_css_px': width, 'frame': frame, 'window_start': start,
                            'source_bounds': [source_start, source_end], 'peak_hz': peak_hz, 'peak_dbfs': peak_db,
                            'reference_bins': reference, 'svg_maximum_absolute_error': error})

    voiced_hz, voiced_db = peaks[spec['voiced_frame']]
    _, closure_db = peaks[spec['closure_frame']]
    _, release_db = peaks[spec['release_frame']]
    if None in (voiced_db, closure_db, release_db):
        raise ValueError('母音・閉鎖・再開口のピークが取得できません')
    drop = voiced_db - closure_db
    rise = release_db - closure_db
    lower, upper = spec['voiced_peak_frequency_hz']
    closure_start = spec['closure_frame'] - size // 2
    fully_closed = (cli_state['lip_minimum_cm2'][closure_start:closure_start + size] < closed_area).all()
    analytic = read_json(artifacts / 'analytic-spectrum.json')
    return {
        'spectrum_window_selection': selected and metadata,
        'spectrum_independent_fft': all(
            r['reference_bins'][key]['first_bin_over_tolerance'] is None
            for r in records for key in ('browser_wav', 'cli')),
        'spectrum_upstream_fft': all(r['reference_bins']['upstream']['first_bin_over_tolerance'] is None for r in records),
        'spectrum_coordinates': all(r['svg_maximum_absolute_error'] is not None
                                    and r['svg_maximum_absolute_error'] <= spec['svg_coordinate_tolerance'] for r in records),
        'spectrum_readouts_and_export': readouts,
        'spectrum_voiced_closure_and_release': bool(
            fully_closed and lower <= voiced_hz <= upper
            and drop >= spec['minimum_voiced_to_closure_drop_db']
            and rise >= spec['minimum_closure_to_release_rise_db']),
        'spectrum_analytic_amplitude': analytic_passes(analytic, spec['analytic']),
    }, {
        'fft_size': size, 'sample_rate_hz': rate, 'bin_width_hz': rate / size,
        'voiced_to_closure_drop_db': drop, 'closure_to_release_rise_db': rise,
        'analytic': analytic, 'display': records,
    }
