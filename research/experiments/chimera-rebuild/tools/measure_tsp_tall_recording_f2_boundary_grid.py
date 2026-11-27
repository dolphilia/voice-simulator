"""同じtallの実録音で母音終端とF2推定の感度を照合する。"""

import argparse
from pathlib import Path
import subprocess

import measure_tsp_again_initial_tip_mfa as single
from measure_tsp_f2_bandwidth_held_out import saved_case
import measure_tsp_phone_boundaries as mfa
import measure_tsp_stressed_vowel_formants as formants
import measure_tsp_tall_f2_boundary_grid as grid_probe
from measure_uniform_tube import record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE


CASE = WORKSPACE / 'cases/tsp-tall-recording-f2-boundary-grid.json'


def recording_paths(uid):
    return {'recording': f'artifacts/corpus/recording/{uid}/{uid}.wav',
            **{f'aligned_{n}': f'artifacts/aligned-{n}-recording/{uid}/{uid}.json' for n in (1, 2)}}


def measure(case, analysis, synth, paths, out, execute):
    settings, cfg = case['measurement'], analysis['measurement']
    grid = grid_probe.interval_grid(settings)
    observed, = settings['observed_modes']
    tiers = [mfa.tiers(paths[f'aligned_{n}']) for n in (1, 2)]
    anchor = tuple(tiers[0]['phones'][single.phone_at_word(tiers[0], settings)])
    fixed, summary = grid_probe.measure_windows(case, analysis, grid, paths['recording'], 'recording', out, execute)
    rate = cfg['sample_rate_hz'] / cfg['decimation']
    length = int(cfg['frame_seconds'] * rate)
    for row in summary['trajectories']:
        point = str(row['end_ms'])
        late = fixed[point][0]['windows'][-1]
        chosen = row['late_f2_hz']
        row['late_selected_pole_rank'] = next(
            (i for i, (frequency, _) in enumerate(late['poles'], 1) if frequency == chosen), None)
        row['late_after_mfa_boundary_ms'] = 1000 * max(0, (late['start_sample'] + length) / rate - anchor[1])

    spans = summary['f2_spans_hz']
    middle, late = spans['median_f2_hz'], spans['late_f2_hz']
    limit = settings['sensitivity_threshold_hz']
    summary['checks'].update({
        'saved_mfa_alignments_match': tiers[0] == tiers[1],
        'saved_tall_aa1_interval_matches_grid': anchor == grid[observed],
        'window_starts_match_rounded_timestamps': all(
            row['start_samples'] == settings['start_samples_by_end'][str(row['end_ms'])]
            for row in summary['trajectories']),
    })
    return summary | {
        'predictions': {
            'median_span_below_threshold': middle is not None and middle < limit,
            'late_span_meets_threshold': late is not None and late >= limit,
            'late_span_exceeds_median_span': late is not None and middle is not None and late > middle,
        },
        'mfa_interval': anchor, 'synth_f2_spans_hz': synth['f2_spans_hz'],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    case = formants.read(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    alignment, reference, synth = (formants.open_run(case[key], revision) for key in ('alignment', 'formants', 'synth_grid'))
    analysis, snapshot = saved_case(reference, formants.CASE)
    paths = {key: formants.verified_path(alignment, name) for key, name in recording_paths(case['utterance']).items()}
    synth_summary = formants.verified_path(synth, 'summary.json')
    source = (formants.TSP_SOURCE, 'crates/chimera-cli/src/compare.rs', 'crates/chimera-cli/src/main.rs',
              'crates/chimera/src/phonetics/english.rs', 'crates/chimera/src/analysis/lpc.rs',
              'crates/chimera/tests/golden_analysis.rs')
    inputs = [
        CASE, Path(__file__).resolve(), snapshot, *paths.values(), synth_summary, formants.PROBE,
        *(run[0] / 'manifest.json' for run in (alignment, reference, synth)),
        *(Path(module.__file__) for module in (single, mfa, formants, grid_probe)),
        WORKSPACE / 'tools/measure_tsp_f2_bandwidth_held_out.py', *(UPSTREAM / item for item in source),
    ]
    details = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision}
    return record_measurement(args.run_id, CASE, inputs, details, lambda out, execute: measure(
        case, analysis, formants.read(synth_summary), paths, out, execute),
        command=None, input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
