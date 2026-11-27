"""W06の固定窓でプリエンファシスだけを変え、F2の採択を照合する。"""

import argparse
from collections import Counter
import math
from pathlib import Path
import subprocess

import numpy as np
from scipy.optimize import linear_sum_assignment

import measure_tsp_f2_bandwidth_envelope as envelope
from measure_tsp_f2_bandwidth_held_out import saved_case
import measure_tsp_lpc_lag_window as lag
import measure_tsp_lpc_pre_emphasis as pre
import measure_tsp_stressed_vowel_formants as tsp
from measure_uniform_tube import record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE


CASE = WORKSPACE / 'cases/tsp-f2-annotation-w06-pre-emphasis.json'


def selected_band(selection, settings):
    if (pole := selection['f2']) is None:
        return selection['reason']
    for band in ('low', 'high'):
        lo, hi = settings[f'{band}_f2_band_hz']
        if lo <= pole[0] <= hi:
            return band
    return 'other'


def matched_selected_poles(a, b, old_selection, new_selection, fs, cfg):
    before, after = (np.array([complex(*coords) for coords in row['roots']]) for row in (a, b))
    positions = abs(before[:, None] - after[None, :])
    origins, targets = linear_sum_assignment(positions)
    matched = dict(zip(origins, targets, strict=True))
    rows = {}
    for name in ('f1', 'f2'):
        pole = old_selection[name]
        if pole is None:
            continue
        freq, bandwidth = pole
        target = np.exp(complex(-math.pi * bandwidth / fs, 2 * math.pi * freq / fs))
        index = int(np.argmin(abs(before - target)))
        root = after[matched[index]]
        hz = float(np.angle(root) * fs / (2 * np.pi))
        bw = float(-math.log(abs(root)) * fs / math.pi)
        published = (root.imag > 0 and hz >= cfg['pole_min_frequency_hz'] and bw <= cfg['pole_max_bandwidth_hz'])
        f1_eligible = published and hz < cfg['f1_max_frequency_hz'] and bw < cfg['f1_max_bandwidth_hz']
        chosen = next((label for label in ('f1', 'f2')
                       if published and new_selection[label] is not None and
                       tsp.max_error([hz, bw], new_selection[label]) <= cfg['frequency_bandwidth_agreement_hz']), None)
        rows[name] = {'next_pole_hz': [hz, bw], 'next_root_imag': float(root.imag),
                      'root_displacement': float(abs(before[index] - root)),
                      'next_public': bool(published), 'next_f1_eligible': bool(f1_eligible), 'next_chosen_as': chosen}
    return rows


def transitions(settings, cfg, raw, rows):
    found = []
    for a, b, left, right in zip(raw, raw[1:], rows, rows[1:]):
        if left['band'] != right['band']:
            roots = matched_selected_poles(a, b, left['selected'], right['selected'], settings['sample_rate_hz'], cfg)
            found.append({'coefficients': [left['coefficient'], right['coefficient']],
                          'bands': [left['band'], right['band']],
                          'selections': [left['selected'], right['selected']], 'root_matches': roots})
    return found


def independent_trace(frame, rust, fs, order, cfg):
    coefficient = rust['pre_emphasis_coefficient']
    emphasized = frame - coefficient * np.r_[0, frame[:-1]]
    shaped = emphasized * np.hamming(len(frame))
    raw = np.correlate(shaped, shaped, mode='full')[len(shaped) - 1:len(shaped) + order]
    observed = lag.solve_independently(frame, fs, order, cfg | {'pre_emphasis': coefficient},
                                       cfg['lag_window_hz'], np.empty(0), raw, rust)
    errors = {
        'emphasized_samples': tsp.max_error(emphasized, rust['emphasized']),
        'windowed_samples': tsp.max_error(shaped, rust['shaped']),
        'autocorrelation': tsp.max_error(raw, rust['autocorrelation']),
        **observed['errors'],
    }
    return observed['fixed_selection'], errors


def coefficient_options(settings, cfg):
    lo, hi = settings['coefficient_steps']
    coefficients = [i / settings['coefficient_divisor'] for i in range(lo, hi + 1)]
    if coefficients[0] != 0 or coefficients[-1] != cfg['pre_emphasis']:
        raise ValueError('範囲は明示的な0から固定上流の既定値まで必要です')
    return coefficients, [*coefficients[:-1], None]


def archived_ends_match(raw, archived):
    compared = ('emphasized', 'shaped', 'autocorrelation', 'weighted_autocorrelation',
                'coefficients', 'prediction_error', 'roots', 'poles')
    return all(raw[i][key] == saved[key]
               for i, saved in ((0, archived[1]), (-1, archived[0])) for key in compared)


def sweep_rows(settings, cfg, limits, frame, raw):
    rows = []
    for variant in raw:
        chosen, errors = independent_trace(frame, variant, settings['sample_rate_hz'], settings['order'], cfg)
        first_difference = next((stage for stage, error in errors.items()
                                 if error is None or error > limits[stage]), None)
        rows.append({'coefficient': variant['pre_emphasis_coefficient'], 'selected': chosen,
                     'band': selected_band(chosen, settings), 'errors': errors, 'first_difference': first_difference})
    return rows


def measure(case, cfg, limits, paths, out, execute):
    settings = case['measurement']
    start, stop = settings['frame_samples']
    rate, order = settings['sample_rate_hz'], settings['order']
    archive = tsp.read(paths['window_summary'])
    if (archive['annotation']['trial'] != settings['trial']
            or archive['annotation']['analysis_samples'] != [start, stop]
            or rate != cfg['sample_rate_hz'] / cfg['decimation']
            or archive['target']['order'] != order):
        raise ValueError('W06の窓とLPC条件が登録値と一致しません')
    with np.load(paths['segment'], allow_pickle=False) as segment:
        first = int(segment['first_sample'])
        frame = segment['samples'][start - first:stop - first]
    if frame.shape != (stop - start,) or not np.isfinite(frame).all():
        raise ValueError('W06の音声の長さまたは標本値が不正です')
    np.save(out / 'frame.npy', frame)
    coefficients, options = coefficient_options(settings, cfg)
    raw = pre.run_probe(frame, rate, order, np.empty(0), out, execute, coefficients=options)
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera-cli', 'compare::tsp::tests'],
            cwd=UPSTREAM, stdout=out / 'upstream-tsp-tests.log')
    archived = tsp.read(paths['endpoint_traces'])
    endpoints_match = archived_ends_match(raw, archived)
    rows = sweep_rows(settings, cfg, limits, frame, raw)
    found = transitions(settings, cfg, raw, rows)
    changes = [t for t in found if t['bands'] == ['low', 'high']]
    return {
        'checks': {
            'registered_coefficients_and_default_option': [row['coefficient'] for row in rows] == coefficients
                and [v['pre_emphasis_option'] for v in raw] == options,
            'archived_endpoints_replayed': endpoints_match and rows[-1]['selected'] ==
                next(row['selected'] for row in archive['windows'] if row['offset_samples'] == 0),
            'preprocessing_coefficients_roots_and_selection_agree': all(row['first_difference'] is None for row in rows),
        },
        'predictions': {'low_to_high_selection_transition': bool(changes),
                        'low_f2_becomes_f1_at_transition': bool(changes) and all(
                            t['root_matches']['f2']['next_chosen_as'] == 'f1'
                            and not t['root_matches']['f1']['next_f1_eligible'] for t in changes)},
        'annotation': archive['annotation'], 'selection_counts': dict(Counter(row['band'] for row in rows)),
        'transitions': found, 'rows': rows,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    case = tsp.read(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    window, endpoints, reference = (tsp.open_run(case[key], revision)
                                    for key in ('window_sweep', 'endpoints', 'baseline'))
    config, cfg_snapshot = saved_case(reference, tsp.CASE)
    endpoint_definition, endpoint_snapshot = saved_case(endpoints, CASE.with_name(case['endpoints']['case'] + '.json'))
    control = tsp.open_run(endpoint_definition['synthetic_control'], revision)
    limit_case, limit_snapshot = saved_case(control, pre.CASE)
    paths = {name: tsp.verified_path(run, path) for name, run, path in (
        ('window_summary', window, 'summary.json'), ('segment', window, 'artifacts/decimated-segment.npz'),
        ('endpoint_traces', endpoints, 'artifacts/upstream-pre-emphasis-04.json'))}
    source = (tsp.TSP_SOURCE, lag.LPC, 'crates/chimera/tests/golden_analysis.rs')
    inputs = [
        CASE, Path(__file__).resolve(), pre.PROBE, cfg_snapshot, endpoint_snapshot, limit_snapshot, *paths.values(),
        *(run[0] / 'manifest.json' for run in (window, endpoints, reference, control)),
        *(Path(module.__file__) for module in (tsp, pre, lag, envelope)),
        WORKSPACE / 'tools/measure_tsp_f2_bandwidth_held_out.py', *(UPSTREAM / item for item in source),
    ]
    info = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision}
    cfg = config['measurement']
    limits = pre.trace_limits(limit_case['measurement'], cfg)
    return record_measurement(args.run_id, CASE, inputs, info, lambda out, execute: measure(
        case, cfg, limits, paths, out, execute), command=None, input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
