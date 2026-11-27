"""FK61_01の全発話でf64の差とPCMへの丸めを照合する。"""

import argparse
from fractions import Fraction
import os
from pathlib import Path
import subprocess

import numpy as np

import measure_tsp_fk61_pcm16682_rounding as prefix


paired, lip, load, radiation, tsp, pcm = prefix.paired, prefix.lip, prefix.load, prefix.radiation, prefix.tsp, prefix.pcm
CASE = radiation.WORKSPACE / 'cases/tsp-fk61-full-pcm-rounding.json'
SAVED_FILES = ('full-trace.npz', 'pcm-digests.json')
COMPARE = ('indexed', 'expanded')
GAINED = pcm.COLUMNS.index('gain_applied')
DC = prefix.DC


def sample_rank(samples):
    bits = samples.view('<u4')
    magnitude = (bits & 0x7fffffff).astype(np.int64)
    return np.where((bits >> 31) != 0, -magnitude, magnitude)


def metrics(delta, start=0):
    size = len(delta)
    if not size:
        return {'frames': 0, 'first_nonzero_frame': None, 'peak_frame': None, 'peak': None,
                'rms': None, 'absolute_p99': None}
    magnitude = np.abs(delta)
    changed = np.flatnonzero(delta)
    peak = int(np.argmax(magnitude))
    return {'frames': size, 'first_nonzero_frame': int(changed[0]) + start if len(changed) else None,
            'peak_frame': peak + start, 'peak': float(magnitude[peak]), 'rms': paired.rms(delta),
            'absolute_p99': float(np.quantile(magnitude, 0.99))}


def dc_difference(left, right, frame, poles):
    def difference(n, column):
        return Fraction(float(right[n, column])) - Fraction(float(left[n, column]))

    recent = difference(frame, GAINED) - difference(frame - 1, GAINED)
    history = Fraction(poles[1]) * Fraction(float(right[frame - 1, DC])) \
        - Fraction(poles[0]) * Fraction(float(left[frame - 1, DC]))
    measured = difference(frame, DC)
    return {'current_minus_previous_input': float(recent), 'previous_dc_state': float(history),
            'measured_research_minus_upstream': float(measured),
            'floating_point_residual': float(measured - recent - history)}


def compare(upstream, research, current, measure, poles, *, precast=None):
    left_output, right_output = (current[f'{side}_output'] for side in (upstream, research))
    left_precast, right_precast = (row[:, DC] for row in (left_output, right_output)) if precast is None else precast
    left_pcm, right_pcm = (current[f'{side}_pcm'] for side in (upstream, research))
    left_value, right_value = (row.astype(np.float64) for row in (left_pcm, right_pcm))
    distance = np.abs(sample_rank(left_pcm) - sample_rank(right_pcm))
    unequal = distance != 0
    one_step = distance == 1
    bit_unequal = left_pcm.view('<u4') != right_pcm.view('<u4')
    midpoint = (left_value + right_value) / 2
    lower, upper = np.minimum(left_precast, right_precast), np.maximum(left_precast, right_precast)
    straddles = (lower <= midpoint) & (midpoint <= upper)
    ties = (left_precast == midpoint) | (right_precast == midpoint)
    precast_delta = right_precast - left_precast
    pcm_delta = right_value - left_value
    errors = {'precast': precast_delta, 'pcm': pcm_delta, 'change_at_rounding': pcm_delta - precast_delta}
    exclude = measure['pcm_outlier_to_exclude']
    indexed_frames = np.flatnonzero(unequal)
    witnesses = {}
    for n in sorted(set(measure['focus_frames']) | {int(np.argmax(np.abs(delta))) for delta in errors.values()}):
        witnesses[str(n)] = {
            'precast': [float(left_precast[n]), float(right_precast[n])],
            'pcm': [float(left_value[n]), float(right_value[n])],
            'ulp_distance': int(distance[n]),
            'midpoint': float(midpoint[n]) if one_step[n] else None,
            'from_midpoint': [float(left_precast[n] - midpoint[n]), float(right_precast[n] - midpoint[n])]
                if one_step[n] else None,
            'dc_difference': dc_difference(left_output, right_output, n, poles) if n > 0 else None,
        }
    energy = np.square(pcm_delta)
    two_sides = np.count_nonzero(unequal)
    return {
        'full': {field: metrics(delta) for field, delta in errors.items()},
        'segments': {name: {field: metrics(delta[start:stop], start) for field, delta in errors.items()}
                     for name, (start, stop) in measure['segments'].items()},
        'precast_where_pcm_equal': metrics(precast_delta[~unequal]) | {'peak_frame': None, 'first_nonzero_frame': None},
        'precast_where_pcm_differs': metrics(precast_delta[unequal]) | {'peak_frame': None, 'first_nonzero_frame': None},
        'pcm_rms_excluding_focus_outlier': paired.rms(np.delete(pcm_delta, exclude)),
        'pcm_squared_error_fraction_at_outlier': float(energy[exclude] / energy.sum()) if two_sides else 0.0,
        'pcm_unequal_values': int(two_sides), 'signed_zero_mismatches': int(np.count_nonzero(bit_unequal & ~unequal)),
        'pcm_unequal_first': int(indexed_frames[0]) if len(indexed_frames) else None,
        'pcm_one_ulp': int(np.count_nonzero(one_step)),
        'pcm_one_ulp_with_exact_midpoint_tie': int(np.count_nonzero(one_step & ties)),
        'pcm_more_than_one_ulp': int(np.count_nonzero(distance > 1)),
        'pcm_max_ulp_distance': int(np.max(distance)),
        'pcm_all_one_ulp_straddle': bool(np.all(straddles[one_step])),
        'witnesses': witnesses,
    }


def analyze(study, out, archives, observed_prefix, config, gain, coefficients):
    measure = study['measurement']
    with np.load(out / SAVED_FILES[0], allow_pickle=False) as saved:
        current = dict(saved)
    proof = tsp.read(out / SAVED_FILES[1])
    archived = prefix.archived_matches(current, proof, archives, measure)
    states = {name: dict(zip(radiation.FIELDS, current[f'{name}_source'].T, strict=True)) for name in prefix.CONDITIONS}
    replay = prefix.exact_output_replays(current, states, measure, config, gain, coefficients)
    with np.load(observed_prefix, allow_pickle=False) as earlier:
        prefix_exact = {key: load.same_bits(current[key][:len(earlier[key])], earlier[key]) for key in earlier.files}
    poles = (coefficients['upstream']['dc_pole'], coefficients['candidate']['dc_pole'])
    comparisons = {f'{a}:{b}': compare(f'upstream_{a}', f'research_{b}', current, measure, poles)
                   for a in COMPARE for b in COMPARE}
    usual, expanded = (comparisons[f'{mode}:{mode}'] for mode in COMPARE)
    peak_frame = measure['registered_expanded_peak_frame']
    focus = expanded['witnesses'][str(peak_frame)]
    u, r = focus['from_midpoint'] or (0.0, 0.0)
    rms_ratio = expanded['full']['precast']['rms'] / usual['full']['precast']['rms']
    ratio_min, ratio_max = measure['precast_rms_ratio_limits']
    checks = {
        'full_pcm_and_mouth_match_archived_observation': all(passed for row in archived.values() for passed in row.values()),
        'first_16704_frames_match_previous_observation': all(prefix_exact.values()),
        'radiation_to_unlimited_pcm_replayed_for_full_utterance': all(replay.values()) and all(
            lip.bit_equal(current[f'{name}_output'][:, DC].astype('<f4'), current[f'{name}_pcm'])
            for name in prefix.CONDITIONS),
        'full_adjacent_pcm_pairs_have_consistent_midpoints': all(row['pcm_all_one_ulp_straddle'] for row in comparisons.values()),
        'expanded_pair_peak_pcm_at_registered_adjacent_values': focus['ulp_distance'] == 1
            and expanded['full']['pcm']['peak_frame'] == peak_frame,
    }
    hypotheses = {
        'expanded_pair_focus_straddles_with_upstream_above': u > 0 > r,
        'expanded_pair_at_least_99_percent_of_pcm_differences_are_one_ulp':
            expanded['pcm_one_ulp'] >= measure['minimum_adjacent_fraction'] * expanded['pcm_unequal_values'],
        'expanded_pair_precast_rms_ratio_between_0p8_and_1p2': ratio_min <= rms_ratio <= ratio_max,
    }
    return {'checks': checks, 'hypotheses': hypotheses, 'precast_rms_ratio': rms_ratio, 'replay': replay,
            'previous_prefix': prefix_exact, 'archive_matches': archived, 'comparisons': comparisons,
            'max_envelope': {name: float(np.max(current[f'{name}_output'][:, pcm.COLUMNS.index('envelope')]))
                             for name in prefix.CONDITIONS}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    ws, upper = radiation.WORKSPACE, radiation.UPSTREAM
    study = tsp.read(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=upper, text=True).strip()
    if revision != study['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=upper):
        parser.error('変更のない固定上流版が必要です')
    if os.environ.get('CHIMERA_RUN_STORAGE') != 'rtl9210b':
        parser.error('試験ビルドにCHIMERA_RUN_STORAGE=rtl9210bを指定してください')
    runs = {key: tsp.open_run(study[key], revision) for key in ('matched', 'coefficients', *prefix.ARCHIVED, 'observed_prefix')}
    uid = study['measurement']['recording_id']
    spec = tsp.verified_path(runs['matched'], f'artifacts/{uid}/matched-case.json')
    config, config_path = radiation.saved_case(runs['matched'], lip.CONFIG)
    coeff = tsp.verified_path(runs['coefficients'], 'artifacts/coefficients.json')
    observed = tsp.verified_path(runs['observed_prefix'], 'artifacts/prefix.npz')
    files = {key: [tsp.verified_path(runs[key], f'artifacts/{name}') for name in names]
             for key, names in prefix.ARCHIVED.items()}
    inputs = [CASE, Path(__file__).resolve(), spec, config_path, coeff, observed, *prefix.capture_dependencies(),
              *(run[0] / 'manifest.json' for run in runs.values()), *(path for paths in files.values() for path in paths)]

    def measure(out, execute):
        prefix.capture(study, config, spec, prefix.patch_paths(files), out, execute, filename=SAVED_FILES[0])
        gain = tsp.read(spec)['speech_voice']['voice']['output_gain']
        return analyze(study, out, prefix.archived_paths(files), observed, config, gain, tsp.read(coeff))

    details = {'case_id': study['id'], 'case_revision': study['revision'], 'upstream_revision': revision}
    return radiation.record_measurement(args.run_id, CASE, inputs, details, measure, command=None, input_root=ws.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
