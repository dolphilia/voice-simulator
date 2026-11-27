"""同じ周期でシマーだけを変えて声門振幅とPCMを照合する。"""

import argparse
from pathlib import Path
import subprocess

import numpy as np

import measure_tsp_seems_drift_only as drift
import measure_tsp_seems_period_jitter as jitter
import measure_tsp_stressed_vowel_formants as tsp
from measure_tsp_f2_bandwidth_held_out import saved_case
from measure_tsp_fine_variation import FIELDS, first_difference
from measure_tsp_seems_spectrum_stages import compare_spectra
from measure_uniform_tube import record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE


CASE = WORKSPACE / 'cases/tsp-seems-amplitude-shimmer.json'
PAIRS = {'upstream': ('shimmer_zero', 'jitter_zero'), 'candidate': ('candidate', 'candidate_shimmer')}
MATCHED = dict(zip(('shimmer_zero', 'shimmer_active'), zip(*PAIRS.values(), strict=True), strict=True))
PARTS = ('upstream', 'drift_zero', 'jitter_zero', 'shimmer_zero', 'candidate', 'candidate_shimmer')
ARCHIVED = ('upstream', 'drift_zero', 'jitter_zero', 'candidate')


def parameters(settings, name):
    if name == 'shimmer_zero':
        return settings['jitter_inactive'], settings['shimmer_inactive']
    if name == 'candidate_shimmer':
        return settings['jitter_inactive'], settings['shimmer_active']
    return jitter.cycle_parameters(settings, name)


def matched_effects(pairs, signals, amplitudes, poles, pcm_tolerance):
    results = {}
    for tag, (left, right) in pairs.items():
        control, compared = signals[left], signals[right]
        pcm_delta = compared[2].astype('f8') - control[2]
        deltas = {name: compared[0][name] - control[0][name] for name in FIELDS}
        deltas['cycle_amplitude'] = amplitudes[right] - amplitudes[left]
        first = {name: first_difference(values) for name, values in deltas.items()}
        peak = {name: float(np.max(abs(values))) for name, values in deltas.items()}
        results[tag] = {
            'first_different_internal_sample': first,
            'peak_absolute_internal_difference': peak,
            'first_different_pcm_frame': first_difference(pcm_delta),
            'first_pcm_frame_over_tolerance': first_difference(pcm_delta, pcm_tolerance),
            'peak_absolute_pcm_difference': float(np.max(abs(pcm_delta))),
            'lpc_delta_hz': poles[right][0] - poles[left][0] if poles[left] is not None and poles[right] is not None else None,
        }
    return results


def measure(case, prior_case, base, cfg, original, references, out, execute):
    settings = {**prior_case['cycle'], 'shimmer_inactive': case['shimmer']['inactive'],
                'shimmer_active': case['shimmer']['active']}
    signals, upstream_checks, _, cycles = drift.capture(
        base, original, references['upstream.wav'], out, execute, cycle_patch=jitter.PATCH, include_shimmer_zero=True)
    candidate_signals, candidate_amplitudes, candidate_checks, candidate_plan = jitter.candidate_capture(
        base, original, references['candidate.wav'], references['inspect.json'], out, execute,
        adjustment=('candidate_shimmer', 'amplitude_shimmer', settings['shimmer_active']))
    signals.update(candidate_signals)
    amplitudes = {name: values[:, 1] for name, values in cycles.items()} | candidate_amplitudes
    checks, result = drift.analyze(base, cfg, signals, references['stage-windows.npz'], out, execute)
    checks['radiation_and_output_stages_agree'] = checks.pop('both_radiation_and_output_stages_agree')
    cycle_specs = {**prior_case, 'cycle': settings}
    cycle_checks, independent, pairs = jitter.compare_cycles(
        cycle_specs, base, signals, cycles, amplitudes, out, pairs=PAIRS, parameters=parameters)
    checks.update(cycle_checks)
    verification = upstream_checks | candidate_checks
    archived = tsp.read(references['jitter-summary.json'])
    with np.load(references['jitter-windows.npz'], allow_pickle=False) as before, np.load(out / 'drift-windows.npz', allow_pickle=False) as after:
        same_baselines = all(verification[name] == archived['pcm_verification'][name] and all(
            np.array_equal(before[f'{name}_{field}'], after[f'{name}_{field}']) for field in (*FIELDS, 'lpc_pcm')) for name in ARCHIVED)
    checks.update(
        upstream_cli_plans_and_baseline_match=all(upstream_checks[key] for key in
            ('default_matches_ordinary_pcm', 'ordinary_matches_archived_wav', 'same_plan')),
        candidate_cli_plans_and_archive_match=candidate_plan and candidate_checks['candidate']['default_wav_matches_archive']
            and all(row['pcm_matches_candidate_cli'] for row in candidate_checks.values()),
        previous_jitter_conditions_match=same_baselines)

    poles = result['lpc_high_poles_hz']
    pcm_tolerance = base['limits']['full_output_replay_absolute']
    within_engine = matched_effects(PAIRS, signals, amplitudes, poles, pcm_tolerance)
    across_engines = matched_effects(MATCHED, signals, amplitudes, poles, pcm_tolerance)
    with np.load(out / 'drift-spectra.npz', allow_pickle=False) as data:
        for tag, (left, right) in (PAIRS | MATCHED).items():
            row = (within_engine | across_engines)[tag]
            row['glottal_spectra'] = compare_spectra(base['spectra'], data['frequency_hz'], data[left], data[right])

    predictions = {
        'first_amplitude_difference_at_first_boundary': all(
            pairs[engine]['first_boundary'] is not None
            and row['first_different_internal_sample']['cycle_amplitude'] == pairs[engine]['first_boundary']
            and all(row['first_different_internal_sample'][field] is None for field in ('f0_hz', 'phase'))
            for engine, row in within_engine.items()),
        'amplitudes_match_at_equal_settings': all(row['first_different_internal_sample']['cycle_amplitude'] is None
                                                for row in across_engines.values()),
        'matched_settings_reduce_both_lpc_gaps': all(row['lpc_delta_hz'] is not None
            and abs(row['lpc_delta_hz']) <= case['limits']['matched_lpc_gap_hz'] for row in across_engines.values()),
    }
    return {'checks': checks, 'predictions': predictions, **result, 'cycle_models': independent,
            'pcm_verification': verification, 'within_engine': within_engine, 'across_engines': across_engines,
            'baseline_jitter_zero_lpc_gap_hz': archived['candidate_minus_upstream_also_jitter_zero_hz']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    case = tsp.read(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    run = tsp.open_run(case['reference'], revision)
    prior_case, prior_case_path = saved_case(run, jitter.CASE)
    base, cfg, original, references, paths = jitter.reference_inputs(prior_case, revision)
    references['jitter-summary.json'] = tsp.verified_path(run, 'summary.json')
    references['jitter-windows.npz'] = tsp.verified_path(run, 'artifacts/drift-windows.npz')
    inputs = [CASE, Path(__file__).resolve(), prior_case_path, run[0] / 'manifest.json', *references.values(), *paths]
    details = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision}
    return record_measurement(args.run_id, CASE, inputs, details,
        lambda out, execute: measure(case, prior_case, base, cfg, original, references, out, execute),
        command=None, input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
