"""TSP候補レポートの全窓と既定評価を固定上流および独立結果に照合する。"""

import argparse
from collections import Counter
from pathlib import Path
from statistics import median

import measure_tsp_f2_bandwidth_envelope as formants
from measure_tsp_f2_bandwidth_held_out import saved_case
import measure_tsp_stressed_vowel_formants as tsp
from measure_uniform_tube import record_measurement
from upstream_baseline import WORKSPACE, sha256


CASE = WORKSPACE / 'cases/tsp-f2-candidate-report.json'
REPORT = 'artifacts/f2-candidates.json'
BASE_OUTPUTS = ('summary.json', 'artifacts/upstream-formants.json')


def window_matches(trace, observed, fixed, cfg):
    pair = formants.select(fixed['poles'], cfg)
    f1, f2 = pair['f1'], pair['f2']
    f1_index = fixed['poles'].index(f1) if f1 is not None else None
    lower = f1[0] + cfg['f2_min_gap_hz'] if f1 is not None else None
    upper = cfg['f2_max_frequency_hz']
    eligible = [i for i, (f, _) in enumerate(fixed['poles']) if lower is not None and lower < f < upper]
    ranks = {i: rank for rank, i in enumerate(eligible, 1)}
    expected = []
    for i, (f, bw) in enumerate(fixed['poles']):
        rank = ranks.get(i)
        if rank is not None:
            decision = 'selected' if rank == 1 else 'later_in_frequency_order'
        elif lower is None:
            decision = 'no_f1'
        else:
            decision = 'at_or_below_f1_gap' if f <= lower else 'at_or_above_f2_ceiling'
        expected.append({'frequency_hz': f, 'bandwidth_hz': bw, 'selected_f1': i == f1_index,
                         'f2_rank': rank, 'f2_decision': decision})
    reason = 'outside_wave' if fixed['reason'] == 'outside_wave' else pair['reason']
    f1_hz, f2_hz = (pole[0] if pole is not None else None for pole in (f1, f2))
    selected = [f1_hz, f2_hz] if f2 is not None else None
    error = tsp.max_error(selected, observed['f1_f2_hz'])
    return (trace['poles'] == expected and trace['f1_hz'] == f1_hz and trace['f2_hz'] == f2_hz
            and reason == fixed['reason'] == observed['reason'] == trace['missing_reason']
            and selected == fixed['f1_f2_hz'] and error is not None and error <= cfg['frequency_bandwidth_agreement_hz']
            and trace['start_sample'] == observed['start_sample'] == fixed['start_sample']
            and trace['outside_phone_ms'] == observed['outside_phone_ms']
            and trace['used_in_median'] == (observed['center'] in cfg['reference_centers'] and selected is not None))


def check_thresholds(cfg):
    boundary = tsp.describe_f2_candidates({'poles': [[250, 500], [300, 80], [500, 40], [501, 580], [3500, 30]],
                                           'f1_f2_hz': [300, 501], 'reason': None}, cfg)
    no_f2 = tsp.describe_f2_candidates({'poles': [[300, 80], [500, 40], [3500, 30]],
                                        'f1_f2_hz': None, 'reason': 'no_f2'}, cfg)
    no_f1 = tsp.describe_f2_candidates({'poles': [[300, 500], [1400, 30]], 'f1_f2_hz': None, 'reason': 'no_f1'}, cfg)
    return {
        'f2_edges_and_f1_bandwidth': boundary['f1_hz'] == 300 and boundary['f2_hz'] == 501
            and [pole['f2_rank'] for pole in boundary['poles']] == [None, None, None, 1, None],
        'still_has_f1_when_f2_missing': no_f2['missing_reason'] == 'no_f2' and no_f2['f1_hz'] == 300
            and no_f2['f2_hz'] is None and all(pole['f2_rank'] is None for pole in no_f2['poles']),
        'no_f1_has_no_rank': no_f1['missing_reason'] == 'no_f1' and no_f1['f1_hz'] is None
            and all(pole['f2_decision'] == 'no_f1' and pole['f2_rank'] is None for pole in no_f1['poles']),
    }


def verify(case, cfg, reference, default, enabled, path):
    source = tsp.read(enabled[0])
    upstream = tsp.read(enabled[1])
    artifact = tsp.read(path)
    windows = artifact['windows']
    index = {(r['utterance'], r['source'], r['phone_index'], r['center']): r for r in windows}
    visited, matches, medians = set(), True, True
    for uid, voices in upstream.items():
        for voice, entries in voices['sources'].items():
            for entry in entries:
                phone_index = entry['index']
                control = uid == 'control'
                if control:
                    observed = source['control']
                else:
                    token, = (t for t in source['tokens'][uid] if t['indexes'][voice] == phone_index)
                    observed = token[voice]
                used = []
                for local, fixed in zip(observed['windows'], entry['windows'], strict=True):
                    key = uid, voice, phone_index, local['center']
                    visited.add(key)
                    trace = index[key]
                    matches = matches and window_matches(trace, local, fixed, cfg)
                    if not control:
                        matches = (matches and trace['word'] == observed['word'] and trace['ipa'] == token['ipa']
                                   and trace['interval_seconds'] == observed['interval'][:2])
                    if trace['used_in_median']:
                        used.append((trace['f1_hz'], trace['f2_hz']))
                aggregate = [median(series) for series in zip(*used, strict=True)] if used else [None, None]
                medians = medians and aggregate == entry['baseline_hz']
                if not control:
                    error = tsp.max_error(aggregate, observed['baseline_hz'])
                    medians = (medians and len(used) == observed['baseline_support'] and error is not None
                               and error <= cfg['frequency_bandwidth_agreement_hz'])
    expected = case['example']
    example = index[expected['utterance'], expected['source'], expected['phone_index'], expected['center']]
    candidates = [pole for pole in example['poles'] if pole['f2_rank'] is not None]
    difference = tsp.max_error([p['frequency_hz'] for p in candidates], expected['candidate_frequencies_hz'])
    exact = all(sha256(a) == sha256(b) == sha256(c) for a, b, c in zip(reference, default, enabled, strict=True))
    missing = Counter(window['missing_reason'] for window in windows if window['missing_reason'] is not None)
    thresholds = check_thresholds(cfg)
    checks = {'all_windows_and_public_pole_decisions':
                  matches and visited == index.keys() and len(index) == len(windows) == case['expected_windows']
                  and artifact['schema_version'] == 1 and artifact['sample_rate_hz'] == cfg['sample_rate_hz'] / cfg['decimation']
                  and artifact['frame_samples'] == int(artifact['sample_rate_hz'] * cfg['frame_seconds']),
              'token_medians_and_support': medians,
              'observed_and_control_missing_reasons': missing == {'no_f1': 3, 'outside_wave': 3} and all(thresholds.values()),
              'unchanged_evaluation_bytes': exact,
              'seems_midpoint_f2_candidates':
                  example['word'] == expected['word'] and example['start_sample'] == expected['start_sample']
                  and [pole['f2_rank'] for pole in candidates] == [1, 2, 3]
                  and difference is not None and difference <= expected['frequency_tolerance_hz']}
    return {'checks': checks, 'missing_reasons': dict(missing), 'threshold_controls': thresholds,
            'windows': len(windows), 'windows_with_multiple_candidates':
                sum(sum(p['f2_rank'] is not None for p in w['poles']) > 1 for w in windows),
            'example': example}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('--default-run', required=True)
    parser.add_argument('--diagnostic-run', required=True)
    args = parser.parse_args()
    case = tsp.read(CASE)
    revision = case['upstream_revision']
    reference = tsp.open_run(case['reference'], revision)
    settings, settings_path = saved_case(reference, tsp.CASE)
    default, enabled = (tsp.run_manifest(name, case['reference']['case'], revision)
                        for name in (args.default_run, args.diagnostic_run))
    if any(run[1]['status'] != 'pass' for run in (default, enabled)) or (default[0] / REPORT).exists():
        parser.error('診断の有無に対応する合格済みの実行を指定してください')
    paths = [[tsp.verified_path(run, name) for name in BASE_OUTPUTS] for run in (reference, default, enabled)]
    report = tsp.verified_path(enabled, REPORT)
    inputs = [CASE, Path(__file__).resolve(), settings_path, report,
              *(part for run_paths in paths for part in run_paths),
              *(run[0] / 'manifest.json' for run in (reference, default, enabled)),
              *(WORKSPACE / f'tools/{name}.py' for name in ('measure_tsp_stressed_vowel_formants',
                   'measure_tsp_f2_bandwidth_envelope', 'measure_tsp_f2_bandwidth_held_out',
                   'measure_fan_crossing_allocations', 'measure_uniform_tube', 'upstream_baseline'))]
    details = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision,
               'default_run': default[0].name, 'diagnostic_run': enabled[0].name}
    return record_measurement(args.run_id, CASE, inputs, details,
        lambda out, execute: verify(case, settings['measurement'], *paths, report),
        command=None, input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
