"""PCM2937に効く口端流量の時間範囲を、保存系列から再計算する。"""

import argparse
import os
from pathlib import Path
import subprocess

import numpy as np

import measure_tsp_fk61_pcm2937_output as comparison


pcm, lip, tsp, radiation = comparison.pcm, comparison.lip, comparison.tsp, comparison.radiation
CASE = pcm.WORKSPACE / 'cases/tsp-fk61-pcm2937-lip-window.json'
LIP = 'lip_cm3_s'
GAIN = pcm.COLUMNS.index('gain_applied')
DC = pcm.COLUMNS.index('dc_removed')


def linear_weights(frame, rate, factor, coefficients, gain):
    """放射入力の差を出力2937へ運ぶ係数を逆算する。"""
    ages = np.arange(frame, -1, -1)
    pole = coefficients['dc_pole']
    fir_weights = np.empty(frame + 1, dtype='f8')
    fir_weights[-1] = gain
    fir_weights[:-1] = gain * (pole - 1.0) * pole ** (ages[:-1] - 1)
    ends = np.arange(1, frame + 2) * factor - 1
    radiation_weights = np.zeros((frame + 1) * factor)
    for offset, tap in enumerate(coefficients['taps']):
        indices = ends - offset
        valid = indices >= 0
        radiation_weights[indices[valid]] += tap * fir_weights[valid]
    return rate * (radiation_weights - np.r_[radiation_weights[1:], 0.0])


def scan_windows(totals, intervals, frame, rate, factor, coefficients, gain, prior, expected):
    """同じ開始状態から区間ごとの逐次加算を並行して再計算する。"""
    base, replaced = totals
    begin_frame = int(np.min(intervals[:, 0])) // factor
    taps = coefficients['taps'][::-1]
    begin_input = (begin_frame + 1) * factor - len(taps)
    if begin_frame < 1 or begin_input < 1:
        raise ValueError('区間走査には既存のDC状態とFIR入力の履歴が必要です')
    indices = np.arange(begin_input - 1, factor * (frame + 1))
    low, high = intervals.T
    mask = (indices[None, :] >= low[:, None]) & (indices[None, :] < high[:, None])
    combined = np.where(mask, replaced[indices], base[indices])
    signal = np.diff(combined, axis=1) / (1 / rate)
    previous_gain = prior[begin_frame - 1, GAIN]
    dc = prior[begin_frame - 1, DC]
    pole = coefficients['dc_pole']
    first_difference = np.full(len(intervals), -1, dtype=int)
    peak = 0.0
    for count, n in enumerate(range(begin_frame, frame + 1)):
        start = count * factor
        acc = np.zeros(len(intervals))
        for i, tap in enumerate(taps):
            acc += signal[:, start + i] * tap
        value = gain * acc
        dc = (value - previous_gain) + pole * dc
        previous_gain = value
        peak = max(peak, float(np.max(np.abs(dc))))
        differs = dc.astype('<f4').view('<u4') != expected[n:n + 1].view('<u4')[0]
        first_difference[(first_difference == -1) & differs] = n
    return dc, first_difference, peak, begin_frame


def full_window(totals, interval, frame, rate, coefficients, gain, config, expected):
    base, replaced = totals
    start, stop = interval
    total = base.copy()
    total[start:stop] = replaced[start:stop]
    derivative = np.diff(total, prepend=0.0) / (1 / rate)
    output, samples = pcm.replay(derivative, coefficients, gain, config)
    first = radiation.signal_difference(expected, samples)['first_unequal_sample']
    return {'interval': list(map(int, interval)), 'precast': float(output[frame, 2]),
            'pcm': float(samples[frame]), 'first_difference_through_focus': first,
            'matches_through_focus': first is None}


def load_series(upstream, bernstein, count):
    with np.load(upstream, allow_pickle=False) as a, np.load(bernstein, allow_pickle=False) as b:
        arrays = {mode: (data['source'], data['output'], data['pcm'][:count])
                  for mode, data in zip(comparison.MODES, (a, b), strict=True)}
    return {mode: (dict(zip(radiation.FIELDS, source.T, strict=True)), output, samples)
            for mode, (source, output, samples) in arrays.items()}


def analyze(study, config, gain, coefficients, series, proof, upstream_summary):
    m = study['measurement']
    rate, frame = m['internal_sample_rate_hz'], m['focus_frame']
    factor = rate // m['sample_rate_hz']
    end = factor * (frame + 1)
    start, stop = m['scan_internal_samples']
    anchor = m['anchor_internal_sample']
    upper, _, reference = series['upstream']
    base, stages, expected_base = series['bernstein']
    totals = (
        base['total_cm3_s'][:end],
        ((base['wall_cm3_s'] + upper[LIP]) + base['nose_cm3_s'])[:end],
    )
    expected = reference[:frame + 1]
    used = coefficients['candidate']
    fir_start = end - len(used['taps'])
    lo, hi = np.triu_indices(stop - start + 1, k=1)
    intervals = np.column_stack((lo + start, hi + start))
    values, difference, peak, begin_frame = scan_windows(totals, intervals, frame, rate, factor, used, gain, stages, expected)
    matched = difference == -1
    matched_at_focus = values.astype('<f4').view('<u4') == expected[frame:frame + 1].view('<u4')[0]
    lengths = intervals[:, 1] - intervals[:, 0]
    shortest = int(np.min(lengths[matched])) if matched.any() else None
    selected = intervals[matched & (lengths == shortest)].tolist() if shortest is not None else []
    by_anchor = (intervals[:, 0] == anchor) & (intervals[:, 1] == anchor + 1)
    best_index = int(np.argmax(values))
    full_controls = {
        'none': (0, 0), 'all': (0, end), 'before_scan': (0, start), 'entire_scan': (start, stop),
        'before_fir': (0, fir_start), 'fir_window': (fir_start, end), 'anchor_only': (anchor, anchor + 1),
        'largest_in_scan': tuple(intervals[best_index]),
    }
    if selected:
        full_controls['first_shortest'] = tuple(selected[0])
        full_controls['last_shortest'] = tuple(selected[-1])
    controls = {name: full_window(totals, interval, frame, rate, used, gain, config, expected)
                for name, interval in full_controls.items()}
    weights = linear_weights(frame, rate, factor, used, gain)
    contributions = weights * (totals[1] - totals[0])
    integrated = np.r_[0.0, np.cumsum(contributions)]
    projected = stages[frame, DC] + (integrated[intervals[:, 1]] - integrated[intervals[:, 0]])
    max_error = float(max(np.max(np.abs(projected - values)),
                          *(abs(result['precast'] - stages[frame, DC] - (integrated[b] - integrated[a]))
                            for (a, b), result in zip(full_controls.values(), controls.values(), strict=True))))
    confirmed = []
    for label, (a, b) in full_controls.items():
        if not start <= a < b <= stop:
            continue
        i = int(np.flatnonzero((intervals[:, 0] == a) & (intervals[:, 1] == b))[0])
        whole = controls[label]
        confirmed.append(whole['precast'] == values[i] and
                         whole['first_difference_through_focus'] == (int(difference[i]) if difference[i] >= 0 else None))
    physical = []
    for mode, (source, native, samples) in series.items():
        total, signal = radiation.radiation_from_components(source, rate, mode == 'upstream')
        replayed, pcm_samples = pcm.replay(signal, coefficients['upstream' if mode == 'upstream' else 'candidate'],
                                            gain, config)
        physical.append(np.array_equal(total, source['total_cm3_s'])
                        and np.array_equal(signal, source[radiation.RADIATION])
                        and np.array_equal(replayed, native[:, 2:]) and pcm.bit_equal(pcm_samples, samples))
    strongest = int(np.argmax(np.abs(contributions)))
    summary = {
        'checks': {
            'native_and_saved_pcm_and_output_replayed': (
                all(proof[mode]['bit_equal'] for mode in comparison.MODES) and all(physical)
                and coefficients['upstream'] == coefficients['candidate']
                and pcm.bit_equal(reference[:frame], expected_base[:frame]) and bool(reference[frame] != expected_base[frame])),
            'all_contiguous_windows_and_full_replays_match': (
                len(intervals) == (stop - start) * (stop - start + 1) // 2
                and all(confirmed) and len(confirmed) >= 4 and peak < config['stage']['clip_threshold']
                and peak < config['stage']['peak_threshold']),
            'full_lip_swap_reproduces_previous_intervention': (
                controls['none']['precast'] == upstream_summary['rounding']['precast']['bernstein']
                and controls['all']['matches_through_focus']
                and controls['all']['precast'] == next(
                    row['precast'] for row in upstream_summary['radiation_component_swaps']
                    if row['derivative_order'] == 'bernstein' and row['components'] == [LIP])),
            'linear_projection_within_registered_budget': max_error <= m['linear_residual_tolerance_pcm'],
        },
        'predictions': {
            'anchor_alone_insufficient': not bool(matched_at_focus[by_anchor][0]),
            'late_contiguous_window_suffices': shortest is not None and shortest <= len(used['taps']),
            'history_before_late_window_alone_insufficient': controls['before_scan']['pcm'] != float(expected[frame]),
            'strongest_lip_term_inside_fir_window': fir_start <= strongest < end,
        },
        'focus_frame': frame, 'scan_internal_samples': [start, stop], 'fir_internal_samples': [fir_start, end],
        'seed_frame': begin_frame - 1, 'intervals_scanned': len(intervals), 'matching_intervals': int(np.count_nonzero(matched)),
        'matching_at_focus': int(np.count_nonzero(matched_at_focus)),
        'shortest_length': shortest, 'shortest_intervals': selected,
        'single_matching_samples': intervals[matched & (lengths == 1), 0].tolist(),
        'single_matching_at_focus': intervals[matched_at_focus & (lengths == 1), 0].tolist(),
        'strongest_linear_term': {'sample': strongest, 'delta_pcm': float(contributions[strongest])},
        'linear_projection_peak_error': max_error,
        'linear_effects': {'before_scan': float(integrated[start]), 'from_scan_start': float(integrated[end] - integrated[start]),
                           'before_fir': float(integrated[fir_start]), 'from_fir_start': float(integrated[end] - integrated[fir_start])},
        'controls': controls,
    }
    return summary, {'intervals': intervals, 'precast': values, 'first_difference': difference,
                     'projected': projected, 'linear_weights': weights, 'linear_contributions': contributions}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    study = tsp.read(CASE)
    ws = pcm.WORKSPACE
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=pcm.UPSTREAM, text=True).strip()
    if revision != study['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=pcm.UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    compared, bernstein, output, matched = (tsp.open_run(study[key], revision)
                                           for key in ('comparison', 'bernstein', 'output', 'matched'))
    config, config_path = radiation.saved_case(matched, lip.CONFIG)
    uid = study['measurement']['recording_id']
    spec = tsp.verified_path(matched, f'artifacts/{uid}/matched-case.json')
    saved_upper = tsp.verified_path(compared, 'artifacts/upstream-prefix.npz')
    saved_trial = tsp.verified_path(bernstein, 'artifacts/render.npz')
    proof = {mode: tsp.verified_path(run, 'artifacts/pcm-digests.json')
             for mode, run in zip(comparison.MODES, (compared, bernstein), strict=True)}
    coefficients = tsp.verified_path(output, 'artifacts/coefficients.json')
    prior_summary = tsp.verified_path(compared, 'summary.json')
    inputs = [CASE, Path(__file__).resolve(), Path(comparison.__file__), Path(pcm.__file__), config_path, spec,
              saved_upper, saved_trial, *proof.values(), coefficients, prior_summary,
              *(run[0] / 'manifest.json' for run in (compared, bernstein, output, matched)),
              *(ws / 'tools' / name for name in ('measure_tsp_fk61_lip_front_radiation.py',
                                                 'measure_tsp_fine_variation.py', 'measure_uniform_tube.py'))]

    def measure(out, _execute):
        gain = tsp.read(spec)['speech_voice']['voice']['output_gain']
        series = load_series(saved_upper, saved_trial, study['measurement']['prefix_frames'])
        result, arrays = analyze(study, config, gain, tsp.read(coefficients), series,
                                 {mode: tsp.read(path) for mode, path in proof.items()}, tsp.read(prior_summary))
        np.savez_compressed(out / 'window-scan.npz', **arrays)
        return result

    details = {'case_id': study['id'], 'case_revision': study['revision'], 'upstream_revision': revision}
    return pcm.record_measurement(args.run_id, CASE, inputs, details, measure, command=None, input_root=ws.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
