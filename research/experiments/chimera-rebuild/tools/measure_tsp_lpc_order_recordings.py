"""同じ録音窓でLPC次数だけを変え、F2の候補と採択を照合する。"""

import argparse
from collections import Counter
from pathlib import Path
from statistics import median
import subprocess

import numpy as np
from scipy.optimize import linear_sum_assignment

import measure_tsp_f2_bandwidth_envelope as envelope
from measure_tsp_f2_bandwidth_held_out import saved_case, selection_error
from measure_tsp_f2_harmonic_bandwidth import root_poles
import measure_tsp_lpc_pre_emphasis_recordings as recordings
import measure_tsp_stressed_vowel_formants as tsp
from measure_uniform_tube import record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/tsp-lpc-order-recordings.json'


def compare_raw_roots(raw, independent, rate):
    rust = np.array([complex(real, imaginary) for real, imaginary in raw])
    if rust.shape != independent.shape:
        raise ValueError('次数に対して複素根の数が一致しません')
    distance = abs(rust[:, None] - independent[None, :])
    rows, columns = linear_sum_assignment(distance)
    left, right = rust[rows], independent[columns]
    frequency_error = np.max(abs(abs(np.angle(left)) - abs(np.angle(right)))) * rate / (2 * np.pi)
    bandwidth_error = np.max(abs(np.log(abs(left)) - np.log(abs(right)))) * rate / np.pi
    axis = [{'fixed': [float(a.real), float(a.imag)], 'independent': [float(b.real), float(b.imag)]}
            for a, b in zip(left, right, strict=True) if (a.imag > 0) != (b.imag > 0)]
    return float(max(frequency_error, bandwidth_error)), float(np.max(distance[rows, columns])), axis


def observe(frame, rate, order, fixed, cfg):
    poles = fixed['poles']
    raw = root_poles(fixed['roots'], rate)
    selection = envelope.select(poles, cfg)
    independent, negative = tsp.independent_poles(frame, rate, order, cfg)
    _, pole_error, excluded_axis = tsp.compare_poles({'poles': independent, 'negative_real_roots': negative}, fixed, cfg)
    # 実軸上で虚部の符号が丸めで変わっても、同じ根を一対一で照合する。
    raw_error, complex_distance, raw_axis = compare_raw_roots(fixed['roots'], tsp.independent_roots(frame, rate, order, cfg), rate)
    in_public = [p for p in raw if p[0] >= cfg['pole_min_frequency_hz'] and p[1] <= cfg['pole_max_bandwidth_hz']]
    return {'public_poles_hz': poles, 'raw_poles_hz': raw, 'selected': selection,
            'real_axis_matches': {'raw': raw_axis, 'public': excluded_axis},
            'raw_complex_max_distance': complex_distance,
            'errors_hz': {'raw': raw_error, 'public': pole_error, 'public_filter': tsp.max_error(in_public, poles),
                          'selected': selection_error(selection, envelope.select(independent, cfg))}}


def eligible_f2(poles, f1, cfg):
    if f1 is None:
        return []
    return [p for p in poles if f1[0] + cfg['f2_min_gap_hz'] < p[0] < cfg['f2_max_frequency_hz']]


def localize(default, changed, cfg, case):
    old, new = default['selected'], changed['selected']
    old_f2, new_f2 = old['f2'], new['f2']
    shift = new_f2[0] - old_f2[0] if old_f2 is not None and new_f2 is not None else None
    availability_changed = (old_f2 is None) != (new_f2 is None)
    large = availability_changed or (shift is not None and abs(shift) >= case['large_difference_hz'])
    public = changed['public_poles_hz']
    held_f1 = eligible_f2(public, old['f1'], cfg)
    eligible = eligible_f2(public, new['f1'], cfg)
    tolerance = case['neighborhood_hz']

    def nearby(poles):
        return [p for p in poles if old_f2 is not None and abs(p[0] - old_f2[0]) < tolerance]

    near_raw, near_public, near_eligible = (nearby(poles) for poles in (changed['raw_poles_hz'], public, eligible))
    stage = None
    if large:
        if old_f2 is None:
            stage = 'default_f2_missing'
        elif not near_raw:
            stage = 'pole_estimation'
        elif not near_public:
            stage = 'public_pole_filter'
        elif not near_eligible:
            stage = 'f1_or_f2_eligibility'
        else:
            stage = 'f2_candidate_order'
    return {'signed_f2_change_hz': shift, 'availability_changed': availability_changed, 'large_change': large,
            'first_differing_stage': stage, 'near_default_f2_raw_hz': near_raw,
            'near_default_f2_public_hz': near_public, 'near_default_f2_eligible_hz': near_eligible,
            'f2_with_f1_held_at_default_hz': held_f1[0] if held_f1 else None}


def aggregate(rows, orders):
    result = {}
    for uid in dict.fromkeys(row['utterance'] for row in rows):
        related = [row for row in rows if row['utterance'] == uid]
        summaries = {}
        for order in orders:
            items = [row['by_order'][order]['selected'] for row in related]
            f2 = [item['f2'][0] for item in items if item['f2'] is not None]
            summaries[order] = {'f2_median_hz': median(f2) if f2 else None, 'finite_windows': len(f2),
                                'missing': [item['reason'] for item in items if item['f2'] is None]}
        result[uid] = summaries
    return result


def measure(case, cfg, rate, windows, observations, archived_diagnostics, out, execute):
    orders = case['orders']
    if (set(orders) != set(cfg['order'].values()) or len(orders) != 2 or case['pre_emphasis'] != cfg['pre_emphasis']
            or len(windows) != case['expected_recorded_windows'] or rate != 12000):
        raise ValueError('固定上流と同じ録音窓・プリエンファシス・次数を指定してください')
    frames = [frame for _, frame, _ in windows for _ in orders]
    fixed = envelope.fixed_spectra(frames, np.arange(0, rate / 2 + 5, 5), out, execute,
        orders=orders * len(windows), include_roots=True)
    if len(fixed) != len(frames):
        raise ValueError('固定上流の観測件数が録音窓と一致しません')
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera-cli', 'compare::tsp::tests'],
            cwd=UPSTREAM, stdout=out / 'upstream-tsp-tests.log')
    rows, default_matches = [], []
    same = cfg['frequency_bandwidth_agreement_hz']
    fixed_iters = iter(fixed)
    for (meta, frame, old_tsp), saved, expected in zip(windows, observations, archived_diagnostics, strict=True):
        default_order = meta['order']
        meta_keys = ('utterance', 'phone_index', 'order', 'center', 'start_sample', 'frame_samples')
        if any(meta[key] != saved[key] for key in meta_keys):
            raise ValueError('窓の時刻、語、または既定次数が保存結果と一致しません')
        upstream = {order: next(fixed_iters) for order in orders}
        order_metrics = {order: observe(frame, rate, order, obj, cfg) for order, obj in upstream.items()}
        default_rust = upstream[default_order]
        default = order_metrics[default_order]
        other_order, = (order for order in orders if order != default_order)
        tsp_error = tsp.max_error(default_rust['poles'], old_tsp['poles'])
        default_matches.append(expected['pre_emphasis_coefficient'] == case['pre_emphasis']
            and all(default_rust[key] == expected[key] for key in default_rust)
            and tsp_error is not None and tsp_error <= same
            and default['selected'] == saved['variants'][0]['fixed_selection'])
        rows.append({**meta, 'default_order': default_order, 'comparison_order': other_order, 'by_order': order_metrics,
                     'change': localize(default, order_metrics[other_order], cfg, case)})
    jumps = [row for row in rows if row['change']['large_change']]
    return {'checks': {'all_registered_recording_windows': all(len(frame) == 300 and np.isfinite(frame).all() for frame in frames),
                       'default_order_matches_archive': all(default_matches),
                       'independent_raw_roots': all(r['errors_hz']['raw'] is not None
                           and r['errors_hz']['raw'] <= case['raw_root_comparison_hz']
                           and r['raw_complex_max_distance'] <= case['raw_complex_distance_tolerance']
                           and all(abs(entry[side][1]) <= case['raw_complex_distance_tolerance']
                                   for entry in r['real_axis_matches']['raw'] for side in ('fixed', 'independent'))
                           for row in rows for r in row['by_order'].values()),
                       'independent_filter_and_selection': all(r['errors_hz'][k] is not None and r['errors_hz'][k] <= same
                           for row in rows for r in row['by_order'].values() for k in ('public', 'public_filter', 'selected'))},
            'predictions': {'order_changes_f2_or_availability': bool(jumps),
                            'large_change_has_preserved_candidate_in_some_window': any(
                                r['change']['near_default_f2_public_hz'] for r in jumps)},
            'large_change_windows': len(jumps), 'large_change_stages': dict(Counter(r['change']['first_differing_stage'] for r in jumps)),
            'by_recording': aggregate(rows, orders), 'windows': rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    case = tsp.read(CASE)
    rev = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if rev != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    source = tsp.open_run(case['recording_reference'], rev)
    source_case, source_path = saved_case(source, recordings.CASE)
    baseline = tsp.open_run(source_case['baseline'], rev)
    parent, parent_path = saved_case(baseline, tsp.CASE)
    alignment, duration = (tsp.open_run(parent[name], rev) for name in ('alignment', 'render'))
    align = tsp.verified_path(alignment, 'summary.json')
    timing = tsp.verified_path(duration, 'summary.json')
    previous = tsp.verified_path(baseline, 'summary.json')
    previous_fixed = tsp.verified_path(baseline, 'artifacts/upstream-formants.json')
    recorded = tsp.verified_path(source, 'summary.json')
    old_diagnostics = [tsp.verified_path(source, f'artifacts/upstream-pre-emphasis-{i:02d}.json')
                       for i in range(case['expected_recorded_windows'])]
    cfg = parent['measurement']
    rate, windows, _, wavs = recordings.prepare(source_case, cfg, alignment, tsp.read(align)['intervals'],
        tsp.read(timing), tsp.read(previous), tsp.read(previous_fixed))
    previous_inputs = {row['path']: row['sha256'] for row in source[1]['inputs']}
    root = WORKSPACE.parents[2]
    if any(previous_inputs.get(str(wav.relative_to(root))) != sha256(wav) for wav in wavs):
        parser.error('再比較するWAVが元のプリエンファシス実行と一致しません')
    observations = tsp.read(recorded)['windows']
    archived = [tsp.read(path)[0] for path in old_diagnostics]
    inputs = [CASE, Path(__file__).resolve(), source_path, parent_path, align, timing, previous, previous_fixed, recorded,
              *old_diagnostics, *wavs, *(run[0] / 'manifest.json' for run in (source, baseline, alignment, duration)),
              envelope.PROBE, *(Path(module.__file__) for module in (envelope, recordings, tsp)),
              *(WORKSPACE / f'tools/{name}.py' for name in ('measure_tsp_f2_harmonic_bandwidth', 'measure_tsp_f2_bandwidth_held_out',
                  'measure_fan_crossing_allocations', 'measure_uniform_tube', 'upstream_baseline')),
              UPSTREAM / tsp.TSP_SOURCE, UPSTREAM / 'crates/chimera/src/analysis/lpc.rs',
              UPSTREAM / 'crates/chimera/tests/golden_analysis.rs']
    metadata = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': rev}
    return record_measurement(args.run_id, CASE, inputs, metadata,
        lambda out, execute: measure(case, cfg, rate, windows, observations, archived, out, execute),
        command=None, input_root=root)


if __name__ == '__main__':
    raise SystemExit(main())
