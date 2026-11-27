"""追加共鳴を780 Hzへ変更し、固定F0で760 Hzの全位相に照合する。"""

import argparse
from collections import Counter
from pathlib import Path
import subprocess

import measure_tsp_f2_bandwidth_envelope as envelope
from measure_tsp_f2_bandwidth_held_out import saved_case
import measure_tsp_f2_intervening_excitation as excitation
import measure_tsp_f2_intervening_phase as phase
import measure_tsp_f2_intervening_resonance as resonance
import measure_tsp_stressed_vowel_formants as tsp
from measure_uniform_tube import record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE


CASE = WORKSPACE / 'cases/tsp-f2-intervening-phase-midpoint.json'


def window_id(row):
    return row['order'], row['center'], row['excitation_phase_samples']


def compare(report, baseline, cfg):
    before = {window_id(row): row for row in baseline['windows']}
    after = {window_id(row): row for row in report['windows']}
    same_windows = (before.keys() == after.keys() and len(before) == len(baseline['windows']) == len(report['windows'])
                    and all(old['start_sample'] == after[key]['start_sample']
                            and old['pulse_offset_samples'] == after[key]['pulse_offset_samples']
                            for key, old in before.items()))
    boundary = cfg['f2_min_gap_hz']
    displaced = [row for row in after.values() if row['association'] == 'added_mode']
    exceptions = []
    changes = Counter()
    for key, row in after.items():
        old = before.get(key)
        if old is not None and row['association'] != old['association']:
            changes[str(row['order'])] += 1
        gap = row['added_mode_gap_from_selected_f1_hz']
        if (gap is not None and gap > boundary) != (row['association'] == 'added_mode'):
            exceptions.append({name: row[name] for name in ('order', 'center', 'excitation_phase_samples',
                               'association', 'added_mode_gap_from_selected_f1_hz', 'first_difference_from_model_f2')})
    result = report['phase_results']
    predictions = {
        'order_12_always_adds_mode': result['counts_by_order']['12'] == {'added_mode': report['period_samples']}
            and not any(row['order'] == 12 for row in exceptions),
        'order_14_phase_switch_crosses_gap':
            any(row['crosses_gap'] and set(row['associations']) == {'model_f2', 'added_mode'}
                for row in result['transitions_by_order']['14']),
        'model_f2_stays_eligible_when_displaced': bool(displaced) and all(row['f2_near_eligible_poles'] for row in displaced),
    }
    return same_windows, predictions, {
        'changed_windows_by_order': dict(changes),
        'first_differences_in_displaced_windows': dict(Counter(row['first_difference_from_model_f2'] for row in displaced)),
        'gap_rule_exceptions': exceptions,
    }


def measure(case, reference, cfg, baseline_path, endpoint_path, out, execute):
    report, _, _ = phase.measure_cycle(case, reference, cfg, out, execute)
    baseline = tsp.read(baseline_path)
    same_windows, predictions, comparison = compare(report, baseline, cfg)
    pitch = case['signal']['f0_hz']
    low, high = case['endpoint_frequencies_hz']
    endpoints = {freq: {window_id(row): row for row in tsp.read(endpoint_path)['windows']
                       if row['f0_hz'] == pitch and row['added_pole_hz'] == freq} for freq in (low, high)}
    zero_delay = {window_id(row): row for row in baseline['windows'] if row['pulse_offset_samples'] == 0}
    baseline_matches = zero_delay.keys() == endpoints[low].keys() and all(
        row['selection'] == endpoints[low][key]['selection'] for key, row in zero_delay.items())
    endpoint_counts = {str(freq): dict(Counter(row['association'] for row in rows.values()))
                       for freq, rows in endpoints.items()}
    windows_at_zero = len(reference['measurement']['orders']) * len(reference['measurement']['centers'])
    report['checks'].update(same_windows_as_lower_endpoint=same_windows,
                            archived_endpoints_at_zero_delay=baseline_matches
                            and endpoints[low].keys() == endpoints[high].keys()
                            and endpoint_counts == {str(low): {'model_f2': windows_at_zero},
                                                    str(high): {'added_mode': windows_at_zero}})
    return {**report, 'predictions': predictions,
            'midpoint_comparison': {**comparison, 'endpoint_zero_delay_counts': endpoint_counts}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    case = tsp.read(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    baseline = tsp.open_run(case['phase_reference'], revision)
    previous, previous_path = saved_case(baseline, phase.CASE)
    endpoint = tsp.open_run(previous['excitation_reference'], revision)
    endpoint_case, endpoint_case_path = saved_case(endpoint, excitation.CASE)
    lower, upper = case['endpoint_frequencies_hz']
    spec = case['signal']
    if (lower >= upper or 2 * spec['added_pole_hz'] != lower + upper
            or previous['signal'] != {**spec, 'added_pole_hz': lower}
            or not {lower, upper} <= set(endpoint_case['signal']['added_pole_frequencies_hz'])):
        parser.error('先行対照から追加共鳴だけを両端の中点へ動かしてください')
    reference = tsp.open_run(endpoint_case['resonance_reference'], revision)
    definition, reference_path = saved_case(reference, resonance.CASE)
    registered = tsp.open_run(definition['tsp_reference'], revision)
    cfg, cfg_path = saved_case(registered, tsp.CASE)
    baseline_path, endpoint_path = (tsp.verified_path(run, 'summary.json') for run in (baseline, endpoint))
    tools = ('measure_tsp_f2_intervening_phase', 'measure_tsp_f2_intervening_excitation',
             'measure_tsp_f2_intervening_resonance', 'measure_tsp_f2_harmonic_spacing',
             'measure_tsp_f2_harmonic_bandwidth', 'measure_tsp_f2_bandwidth_envelope',
             'measure_tsp_f2_known_poles', 'measure_tsp_stressed_vowel_formants', 'measure_tsp_f2_bandwidth_held_out',
             'measure_tsp_f2_annotation', 'measure_fan_crossing_allocations', 'measure_uniform_tube', 'upstream_baseline')
    inputs = [CASE, Path(__file__).resolve(), previous_path, endpoint_case_path, reference_path, cfg_path,
              baseline_path, endpoint_path, envelope.PROBE,
              *(run[0] / 'manifest.json' for run in (baseline, endpoint, reference, registered)),
              *(WORKSPACE / f'tools/{name}.py' for name in tools),
              UPSTREAM / tsp.TSP_SOURCE, UPSTREAM / 'crates/chimera/src/analysis/lpc.rs',
              UPSTREAM / 'crates/chimera/tests/golden_analysis.rs']
    details = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision}
    return record_measurement(args.run_id, CASE, inputs, details,
        lambda out, execute: measure(case, definition, cfg['measurement'], baseline_path, endpoint_path, out, execute),
        command=None, input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
