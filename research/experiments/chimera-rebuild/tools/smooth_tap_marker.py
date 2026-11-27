"""滑らかな逆相試験音を位相と分数遅延で照合する。"""

import numpy as np
from scipy.optimize import minimize_scalar
from scipy.signal import correlate


def chip_values(spec):
    state = spec['seed']
    values = []
    for _ in range(spec['chips']):
        state ^= (state << 13) & 0xffffffff
        state ^= state >> 17
        state ^= (state << 5) & 0xffffffff
        values.append(2 * (state & 1) - 1)
    return np.asarray(values)


def waveform(chips, spec, frames):
    width = spec['frames_per_chip']
    position = (frames / width) % len(chips)
    index = position.astype(int)
    t = position - index
    return (chips[index] + (chips[(index + 1) % len(chips)] - chips[index])
            * (3 * t**2 - 2 * t**3)) / spec['scale']


def marker_pcm(count, spec):
    return waveform(chip_values(spec), spec, np.arange(count)).astype('<f4')


def fit_wave(block, basis):
    gain = np.dot(block, basis) / np.dot(basis, basis)
    residual = np.linalg.norm(block - gain * basis) / np.linalg.norm(block)
    return float(residual), float(gain)


def find_anchor(difference, chips, case, first):
    width = case['window_frames']
    if len(difference) < width:
        return None
    spec = case['marker']
    frames = first + np.arange(width)
    template = waveform(chips, spec, frames)
    centered = template - template.mean()
    sums = np.r_[0, np.cumsum(difference)]
    squared = np.r_[0, np.cumsum(difference**2)]
    variance = squared[width:] - squared[:-width] - (sums[width:] - sums[:-width])**2 / width
    norm = np.sqrt(np.maximum(variance, 0)) * np.linalg.norm(centered)
    scores = np.divide(correlate(difference, centered, mode='valid', method='fft'), norm,
                       out=np.zeros_like(norm), where=norm > 0)
    scores = np.clip(scores, -1, 1)
    offset = int(scores.argmax())
    correlation = float(scores[offset])
    competing = scores[np.abs(np.arange(len(scores)) - offset) > 32]
    margin = correlation - float(competing.max(initial=0))
    if correlation < case['minimum_correlation'] or margin < case['minimum_distinct_peak_margin']:
        return None
    block = difference[offset:offset + width]

    def fit(fraction):
        return fit_wave(block, waveform(chips, spec, frames + fraction))

    fraction = float(minimize_scalar(lambda shift: fit(shift)[0], bounds=(-1, 1), method='bounded').x)
    residual, gain = fit(fraction)
    if gain <= 0 or residual > case['maximum_relative_residual']:
        return None
    return {'offset': offset, 'fraction': fraction, 'correlation': correlation,
            'distinct_peak_margin': margin, 'relative_residual': residual, 'gain': gain}


def resolve_window(stereo, case, first, last, *, allowance, quiet_amplitude):
    length = last - first + 1
    width = case['window_frames']
    chips = chip_values(case['marker'])
    difference = (stereo[:, 0].astype(float) - stereo[:, 1]) / 2
    if length < width * 2:
        return {'valid': False, 'reason': 'graph_window_too_short'}
    left = find_anchor(difference, chips, case, first)
    right = find_anchor(difference, chips, case, last - width + 1)
    if left is None or right is None:
        return {'valid': False, 'reason': 'smooth_anchor_not_unique', 'anchors': [left, right]}
    start, stop = left['offset'], right['offset'] + width
    size = stop - start
    if size < width * 2 or abs(size - length) > allowance:
        return {'valid': False, 'reason': 'smooth_anchor_separation', 'anchors': [left, right]}
    shift = length - size + right['fraction'] - left['fraction']
    window = difference[start:stop]
    quiet = int(np.count_nonzero(np.abs(window) <= quiet_amplitude))
    zero = int(np.count_nonzero(np.all(stereo[start:stop] == 0, axis=1)))
    residual = None
    if size == length:
        basis = waveform(chips, case['marker'], first + np.arange(length) + left['fraction'])
        residual, _ = fit_wave(window, basis)
    continuous = (residual is not None and residual <= case['maximum_relative_residual']
                  and abs(shift) <= case['maximum_consecutive_delay_change_frames'])
    return {'valid': True, 'tap_window': [start, stop], 'expected_frames': length, 'captured_frames': size,
            'anchors': [left, right], 'net_marker_advance_frames': shift, 'continuous': continuous,
            'full_window_relative_residual': residual, 'quiet_frames': quiet, 'silent_frames': zero,
            'phase': observe(stereo[start:stop], case)}


def observe(stereo, case):
    spec = case['marker']
    width = case['window_frames']
    chips = chip_values(spec)
    period = len(chips) * spec['frames_per_chip']
    source = waveform(chips, spec, np.arange(period))
    spectrum = np.fft.rfft(source)
    extended = np.r_[source, source[:width - 1]]
    summed = np.r_[0, np.cumsum(extended)]
    squared = np.r_[0, np.cumsum(extended**2)]
    variance = squared[width:] - squared[:-width] - (summed[width:] - summed[:-width])**2 / width
    norm = np.sqrt(np.maximum(variance, 0))
    difference = (stereo[:, 0].astype(float) - stereo[:, 1]) / 2
    frames = np.arange(width)
    offsets = np.arange(period)
    rows = []
    for start in range(0, len(difference) - width + 1, width):
        block = difference[start:start + width]
        block_norm = np.linalg.norm(block)
        row = {'start': start, 'accepted': False}
        rows.append(row)
        spread = block - block.mean()
        spread_norm = np.linalg.norm(spread)
        if spread_norm == 0 or not np.isfinite(spread_norm):
            continue
        cross = np.fft.irfft(spectrum * np.fft.rfft(spread, n=period).conj(), n=period)
        peaks = np.divide(cross, norm * spread_norm, out=np.full(period, -1.0), where=norm > 0)
        peaks = np.clip(peaks, -1, 1)
        phase = int(peaks.argmax())
        distance = (offsets - phase + period // 2) % period - period // 2
        correlation = float(peaks[phase])
        margin = float(correlation - np.max(peaks[np.abs(distance) > 32]))
        row.update(correlation=correlation, distinct_peak_margin=margin)
        if correlation < case['minimum_correlation'] or margin < case['minimum_distinct_peak_margin']:
            continue

        def fit(delay):
            basis = waveform(chips, spec, frames + phase + delay)
            gain = np.dot(block, basis) / np.dot(basis, basis)
            error = np.linalg.norm(block - gain * basis) / block_norm
            return error, gain

        delay = float(minimize_scalar(lambda d: fit(d)[0], bounds=(-1, 1), method='bounded').x)
        error, gain = map(float, fit(delay))
        row.update(accepted=gain > 0 and error <= case['maximum_relative_residual'],
                   marker_position_frames=(phase + delay) % period, gain=gain, relative_residual=error)

    jumps = []
    longest = count = 0
    previous = None
    for row in rows:
        if not row['accepted']:
            continue
        adjustment = 0
        if previous is not None:
            distance = row['start'] - previous['start']
            change = row['marker_position_frames'] - previous['marker_position_frames'] - distance
            adjustment = (change + period / 2) % period - period / 2
            if abs(adjustment) > case['maximum_consecutive_delay_change_frames']:
                jumps.append({'start': row['start'], 'marker_displacement_frames': adjustment})
        count = count + 1 if (previous is not None and distance == width
                              and abs(adjustment) <= case['maximum_consecutive_delay_change_frames']) else 1
        longest = max(longest, count)
        previous = row
    return {'windows': rows, 'longest_consecutive_frames': longest * width, 'phase_jumps': jumps,
            'known_marker_continuous': longest >= case['minimum_consecutive_windows']}


def injected_controls(case):
    width = case['window_frames']
    cut = (case['minimum_consecutive_windows'] + 1) * width
    discontinuity = case['control_discontinuity_frames']
    count = 2 * cut
    fraction = 0.25
    spec = case['marker']
    source = waveform(chip_values(spec), spec, np.arange(count + discontinuity) + fraction).astype('<f4')
    silence = np.zeros(discontinuity, dtype='<f4')
    controls = {
        'continuous': source[:count],
        'missing': np.r_[source[:cut], source[cut + discontinuity:]],
        'repeated': np.r_[source[:cut], source[cut - discontinuity:count - discontinuity]],
        'silent': np.r_[source[:cut], silence, source[cut + discontinuity:count]],
    }
    results = {}
    checks = {}
    for label, signal in controls.items():
        report = observe(np.column_stack((signal, -signal)), case)
        rejected = [row['start'] for row in report['windows'] if not row['accepted']]
        jumps = report['phase_jumps']
        first = report['windows'][0]
        aligned = (report['known_marker_continuous'] and first['accepted']
                   and abs(first['marker_position_frames'] - fraction) < 0.01)
        if label in ('missing', 'repeated'):
            expected = discontinuity if label == 'missing' else -discontinuity
            classified = (not rejected and len(jumps) == 1 and jumps[0]['start'] == cut
                          and abs(jumps[0]['marker_displacement_frames'] - expected) < 0.01)
        else:
            classified = not jumps and rejected == ([cut] if label == 'silent' else [])
            if label == 'silent':
                classified = classified and bool(np.all(signal[cut:cut + discontinuity] == 0))
        checks[f'injected/{label}'] = bool(aligned and classified)
        results[label] = {'first_window': first, 'rejected_windows': rejected, 'phase_jumps': jumps,
                          'longest_consecutive_frames': report['longest_consecutive_frames']}
    return checks, results
