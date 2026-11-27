"""同一PCMの母音終端だけをずらし、中央3窓と90%窓のF2を照合する。"""

import argparse
from pathlib import Path
import subprocess

import numpy as np

import measure_tsp_again_initial_tip_mfa as single
from measure_tsp_f2_bandwidth_held_out import saved_case
import measure_tsp_phone_boundaries as mfa
import measure_tsp_stressed_vowel_formants as formants
from measure_uniform_tube import record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE


CASE = WORKSPACE / 'cases/tsp-tall-f2-boundary-grid.json'


def interval_grid(settings):
    start = float(np.float32(settings['start_ms'] / 1000))
    return {str(ms): (start, float(np.float32(ms / 1000)), settings['phones'][0])
            for ms in settings['end_ms']}


def f2_spans(trajectory):
    spans = {}
    for key in ('median_f2_hz', 'late_f2_hz'):
        values = [row[key] for row in trajectory]
        spans[key] = max(values) - min(values) if all(value is not None for value in values) else None
    return spans


def measure_windows(case, analysis, grid, wave, voice, out, execute):
    settings, cfg = case['measurement'], analysis['measurement']
    centers = settings['centers']
    if centers != [*cfg['reference_centers'], cfg['boundary_centers'][-1]]:
        raise ValueError('観測窓が登録済みの基準と違います')
    uid = case['utterance']
    layout = {uid: {'source': {key: {'wave': wave, 'phones': [row]} for key, row in grid.items()},
                    'tokens': [dict.fromkeys(grid, 0)]}}
    fixed, _ = formants.measure_fixed(analysis, layout, centers, out, execute)
    native_rows = fixed[uid]['sources']
    lo = formants.filtered_wave(wave, voice, cfg)
    order = cfg['order']['F' if uid.startswith('F') else 'M']
    rows, trajectory = {}, []
    for key, interval in grid.items():
        native, = native_rows[key]
        local = formants.token_measurement(lo, interval, order, centers, native, cfg)
        rows[key] = local
        late = local['windows'][-1]
        native_late = native['windows'][-1]
        trajectory.append({
            'end_ms': int(key), 'origin': settings['observed_modes'].get(key, 'assigned'),
            'median_f2_hz': native['baseline_hz'][1], 'median_support': local['baseline_support'],
            'late_f2_hz': native_late['f1_f2_hz'][1] if native_late['f1_f2_hz'] is not None else None,
            'late_outside_phone_ms': late['outside_phone_ms'], 'late_reason': native_late['reason'],
            'start_samples': [window['start_sample'] for window in native['windows']],
        })
    single.save(out / 'window-comparisons.json', rows)
    limit = cfg['frequency_bandwidth_agreement_hz']
    steps = [[b - a for a, b in zip(left['start_samples'], right['start_samples'], strict=True)]
             for left, right in zip(trajectory, trajectory[1:])]
    checks = {
        'fixed_and_independent_window_stages_agree': all(
            len(row['windows']) == len(centers) and all(
                item['first_different_stage'] is None for item in row['window_comparison'])
            for row in rows.values()),
        'fixed_and_independent_medians_agree': all(
            row['baseline_error_hz'] is not None and row['baseline_error_hz'] <= limit for row in rows.values()),
    }
    return native_rows, {'checks': checks, 'intervals': grid, 'trajectories': trajectory,
                         'f2_spans_hz': f2_spans(trajectory), 'window_start_steps': steps}


def measure(case, analysis, prior_centers, paths, out, execute):
    settings = case['measurement']
    grid = interval_grid(settings)
    observed = {key: mfa.tiers(paths[f'{key}_tier']) for key in settings['observed_modes']}
    actual_intervals = {key: tuple(rows['phones'][single.phone_at_word(rows, settings)])
                        for key, rows in observed.items()}
    same_wave = len({paths[f'{key}_pcm'].read_bytes() for key in observed}) == 1
    native_rows, result = measure_windows(case, analysis, grid, paths['clean'], 'clean', out, execute)
    earlier = formants.read(paths['endpoint_formants'])[case['utterance']]['sources']
    endpoints_match = True
    for key, mode in settings['endpoint_routes'].items():
        native, = native_rows[key]
        prior, = earlier[mode]
        prior_windows = dict(zip(prior_centers, prior['windows'], strict=True))
        endpoints_match &= native['baseline_hz'] == prior['baseline_hz'] and native['windows'] == [
            prior_windows[center] for center in settings['centers']]

    trajectory = result['trajectories']
    spans = result['f2_spans_hz']
    early_span, late_span = spans['median_f2_hz'], spans['late_f2_hz']
    sensitivity = settings['sensitivity_threshold_hz']
    return {
        'checks': {
            'same_alignment_pcm_at_observed_ends': same_wave,
            'observed_intervals_match_registered_grid': all(value == grid[key] for key, value in actual_intervals.items()),
            'window_starts_step_as_registered': all(step == settings['start_sample_step']
                                                    for step in result['window_start_steps']),
            **result.pop('checks'),
            'recorded_formant_endpoints_replayed': endpoints_match,
        },
        'predictions': {
            'median_span_below_threshold': early_span is not None and early_span < sensitivity,
            'late_span_meets_threshold': late_span is not None and late_span >= sensitivity,
            'late_f2_nondecreasing': late_span is not None and all(
                left['late_f2_hz'] <= right['late_f2_hz'] for left, right in zip(trajectory, trajectory[1:])),
        },
        **result,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    case = formants.read(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    boundary, prior, clean, reference = (formants.open_run(case[key], revision) for key in
                                         ('boundary_runs', 'endpoint_formants', 'clean_render', 'formants'))
    analysis, snapshot = saved_case(reference, formants.CASE)
    endpoints, endpoint_snapshot = saved_case(prior, CASE.with_name(case['endpoint_formants']['case'] + '.json'))
    paths = {'clean': formants.verified_path(clean, 'artifacts/matched-clean.wav'),
             'endpoint_formants': formants.verified_path(prior, 'artifacts/upstream-formants.json')}
    for end, mode in case['measurement']['observed_modes'].items():
        tag = f"{case['utterance']}-{mode}"
        paths[f'{end}_tier'] = formants.verified_path(boundary, f'artifacts/aligned/{tag}/{tag}.json')
        paths[f'{end}_pcm'] = formants.verified_path(boundary, f'artifacts/corpus/{tag}/{tag}.wav')
    source = (formants.TSP_SOURCE, 'crates/chimera-cli/src/compare.rs', 'crates/chimera-cli/src/main.rs',
              'crates/chimera/src/analysis/lpc.rs', 'crates/chimera/tests/golden_analysis.rs')
    inputs = [
        CASE, Path(__file__).resolve(), snapshot, endpoint_snapshot, *paths.values(), formants.PROBE,
        *(run[0] / 'manifest.json' for run in (boundary, prior, clean, reference)),
        *(Path(module.__file__) for module in (single, mfa, formants)),
        WORKSPACE / 'tools/measure_tsp_f2_bandwidth_held_out.py', *(UPSTREAM / item for item in source),
    ]
    details = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision}
    return record_measurement(args.run_id, CASE, inputs, details, lambda out, execute: measure(
        case, analysis, endpoints['measurement']['analysis_centers'], paths, out, execute),
        command=None, input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
