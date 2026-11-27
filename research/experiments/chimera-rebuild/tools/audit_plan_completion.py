"""段階の完了条件を、元のケース・判定・観測値に結び付ける。"""

import argparse
from collections import Counter
import csv
import json
from pathlib import Path
import re
import shutil
import subprocess
from tempfile import TemporaryDirectory

import numpy as np
import measure_fixed_alpha_branch_loss as branch_alpha
import measure_fixed_alpha_discrete_impulse as discrete_alpha
import measure_fixed_alpha_lf_fundamental as lf_fundamental
import measure_fixed_alpha_lf_fundamental_amplitude as lf_fundamental_amplitude
import measure_fixed_alpha_lf_fundamental_amplitude_branch_loss as lf_fundamental_amplitude_branches
import measure_fixed_alpha_lf_fundamental_branch_loss as lf_fundamental_branches
import measure_fixed_alpha_lf_fundamental_smoothed_branches as lf_fundamental_smoothed
import measure_fixed_alpha_loss_high_flow as high_flow_alpha
import measure_fixed_alpha_loss_low_flow as low_flow_alpha
import measure_fixed_alpha_loss_passive as passive_alpha
import measure_fixed_alpha_loss_tangent as tangent_alpha
import measure_fixed_alpha_mean_flow as mean_alpha
import measure_fixed_alpha_periodic_flow as periodic_alpha
import measure_fixed_lf_harmonic_transfer as lf_transfer
import measure_fixed_lf_radiation_budget as lf_radiation_budget
import measure_fixed_vowel_i_cli_radiation as fixed_vowel_i_cli_radiation
import measure_fixed_vowel_i_coupled_smoothing as fixed_vowel_i_coupled
import measure_fixed_vowel_i_pharynx_averaged_loss as fixed_vowel_i_pharynx_averaged_loss
import measure_fixed_vowel_i_pharynx_from_glottal_flow as fixed_vowel_i_pharynx_from_glottal_flow
import measure_fixed_vowel_i_pharynx_harmonic_pairs as fixed_vowel_i_pharynx_harmonic_pairs
import measure_fixed_vowel_i_pharynx_harmonic_pairs_low_pressure as fixed_vowel_i_pharynx_harmonic_pairs_low_pressure
import measure_fixed_vowel_i_pharynx_mean_flow_tangent as fixed_vowel_i_pharynx_mean_flow_tangent
import measure_fixed_vowel_i_pharynx_predicted_radiation as fixed_vowel_i_pharynx_predicted_radiation
import measure_fixed_vowel_i_velum_port_bandwidth as fixed_vowel_i_velum_port_bandwidth
import measure_fixed_vowel_i_velum_port_middle_harmonics as fixed_vowel_i_velum_port_middle_harmonics
import measure_fixed_vowel_i_velum_port_loss_feedback as fixed_vowel_i_velum_port_loss_feedback
import measure_fixed_vowel_i_velum_port_loss_sensitivity as fixed_vowel_i_velum_port_loss_sensitivity
import measure_fixed_vowel_i_velum_port_complex_pair as fixed_vowel_i_velum_port_complex_pair
import measure_fixed_vowel_i_velum_port_selected_pair_feedback as fixed_vowel_i_velum_port_selected_pair_feedback
import measure_fixed_vowel_i_velum_narrow_port_feedback as fixed_vowel_i_velum_narrow_port_feedback
import measure_fixed_vowel_i_velum_narrow_port_bandwidth as fixed_vowel_i_velum_narrow_port_bandwidth
import measure_fixed_vowel_i_velum_narrow_port_all_harmonic_feedback as fixed_vowel_i_velum_narrow_port_all_harmonic_feedback
import measure_fixed_vowel_i_velum_narrow_port_upper_harmonics as fixed_vowel_i_velum_narrow_port_upper_harmonics
import measure_fixed_vowel_i_velum_wide_port_upper_harmonics as fixed_vowel_i_velum_wide_port_upper_harmonics
import measure_fixed_vowel_i_pharynx_reversal_low_harmonics as fixed_vowel_i_pharynx_reversal_low_harmonics
import measure_fixed_vowel_i_pharynx_steady_flow as fixed_vowel_i_pharynx_steady_flow
import measure_fixed_vowel_i_lf_branch_loss as fixed_vowel_i_lf
import measure_fixed_vowel_i_radiation_components as fixed_vowel_i_radiation
import measure_fixed_vowel_i_radiation_screen as fixed_vowel_i_radiation_screen
import measure_fixed_vowel_i_velum_harmonic_transfer as fixed_vowel_i_velum_harmonic_transfer
import measure_fixed_vowel_i_velum_mean_flow_tangent as fixed_vowel_i_velum_mean_flow_tangent
import measure_fixed_vowel_i_velum_oral_nasal_loss as fixed_vowel_i_velum_oral_nasal_loss
import measure_fixed_vowel_i_velum_supraglottal_loss as fixed_vowel_i_velum_supraglottal_loss
import measure_fixed_vowel_i_velum_port_only as fixed_vowel_i_velum_port_only
import measure_fixed_vowel_i_velum_radiation as fixed_vowel_i_velum_radiation
import measure_fixed_vowel_i_wasm_radiation as fixed_vowel_i_wasm_radiation
import measure_vowel_open_o_high_bandwidth as open_o_bandwidth
import measure_vowel_open_o_lpc_matched as open_o_lpc
import measure_vowel_open_o_lpc_orders as open_o_orders

from audit_plan_evidence import ROOT, RUNS, read_json, read_record
from audit_stage7_evidence import evaluation_evidence
from audit_stage7_f2_annotations import annotation_observations
from audit_stage7_listening_runs import CORPORA, RUN_ID, evaluation_run_inputs, listening_observations
from audit_stage7_physical_midi import physical_midi_observations
from measure_uniform_tube import candidate_sources, read_trace, record_measurement
from measure_wasm_fixed import compare_pcm
from measure_worklet_fixed import WEB, web_sources
from measure_worklet_live_tsp_rate import same_states, wave
from run_storage import WORK_DISK
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE_PATH = WORKSPACE / 'cases/plan-completion-evidence.json'
PLAN_PATH = ROOT / 'docs/plans/chimera-research-rebuild-plan.md'
TUBE_RUNS = ('uniform-tube-20261119-b', 'soft-wall-20261119-d')
VOWEL_RUN = 'vowels-reference-20261119-b'
VCV_RUN = 'bilabial-nasal-vcv-20261119-b'


def summary(run_id):
    return read_json(RUNS / run_id / 'summary.json')


def saved_case(run_id):
    run = RUNS / run_id
    manifest = read_json(run / 'manifest.json')
    filename = f"/{manifest['case_id']}.json"
    entry, = (item for item in manifest['inputs'] if item['path'].endswith(filename)
              and '/cases/' in '/' + item['path'])
    return read_json(run / manifest['source_snapshot'] / entry['path'])


def audit_tube(run_id, expected, revision):
    run = RUNS / run_id
    setup = read_json(run / 'artifacts/settings.json')
    case = setup['case']
    result = summary(run_id)
    tube, impulse, measurement = case['tube'], case['impulse'], case['measurement']
    wall = case.get('wall')
    header, trace = read_trace(run / 'artifacts/trace.csv', expected['samples'], 12 if wall else 6)
    source = trace[:, header.index('inlet_flow_cm3_s')]
    derivative = trace[:, header.index('radiation_flow_derivative_cm3_s2')]
    rate = tube['sample_rate_hz']
    driven = np.flatnonzero(source)
    arrived = np.flatnonzero(derivative)
    onset = int(arrived[0]) if arrived.size else None
    tail = float(np.max(np.abs(derivative[-measurement['tail_sample_count']:])))
    peak = float(np.max(np.abs(derivative)))
    tail_ratio = tail / peak if peak else float('inf')
    linear = np.array(result['linear_peaks_hz'])
    fdtd = np.array(result['fdtd_peaks_hz'])
    errors = np.abs(fdtd / linear - 1)
    checks = {
        'registered_geometry': tube == expected['settings'] and case['upstream_revision'] == revision,
        'samples_and_impulse': result['samples'] == trace.shape[0]
        and driven.tolist() == [impulse['sample']] == [0]
        and float(source[0]) / rate == impulse['volume_cm3'] == 1.0,
        'decay_and_causality': onset == result['first_radiation_sample'] == tube['cells'] - 1
        and tail_ratio == result['tail_over_peak'] < measurement['tail_over_peak_lt'],
        'fdtd_and_linear': errors.size >= 4 and bool(np.all(errors < expected['fdtd_vs_linear_relative_error_lt']))
        and bool(np.array_equal(errors, result['fdtd_vs_linear_relative_error'])),
    }
    observed = {'samples': len(trace), 'first_radiation_sample': onset, 'tail_over_peak': tail_ratio,
                'fdtd_vs_linear_max_relative_error': float(max(errors))}
    if wall is None:
        # 並列放射負荷の低域での長さ補正を含む開閉管の近似。
        end_cm = 8 * np.sqrt(tube['area_cm2'] / np.pi) / (3 * np.pi)
        quarter_hz = 35000 * np.array([1, 3, 5, 7]) / (4 * (tube['length_cm'] + end_cm))
        quarter_errors = np.abs(linear[:4] / quarter_hz - 1)
        checks['quarter_wave'] = (bool(np.array_equal(quarter_errors, result['quarter_wave_relative_error']))
                                  and bool(np.all(quarter_errors < expected['quarter_wave_relative_error_lt'])))
        observed['quarter_wave_max_relative_error'] = float(max(quarter_errors))
    return checks, observed


def vowel_entries(result):
    return [result['continuity_run'], *(v[key] for v in result['vowels'] for key in ('linear_run', 'voice_run'))]


def audit_vowels(result, order, records):
    vowels = result['vowels']
    transitions = result['transitions']
    voiced = summary('vowel-motion-voice-vowels-20261119-c')['windows']
    checks = {
        'ten_fixed_vowels': [v['ipa'] for v in vowels] == order and all(
            len(v['linear_hz']) >= 3 and len(v['lpc_hz_and_bandwidth']) >= 3
            and np.isfinite(v['pcm_f0_hz']) and v['pcm_f0_hz'] > 0
            and len(v['linear_bandwidth_hz']) == len(v['linear_hz'])
            and v['missing_bandwidth'] == [i for i, value in enumerate(v['linear_bandwidth_hz']) if value is None]
            for v in vowels),
        'adjacent_transitions': [(x['from_ipa'], x['to_ipa']) for x in transitions] == list(zip(order, order[1:]))
        and all(x['end_frame_exclusive'] > x['start_frame'] and x['passed'] is True for x in transitions),
        'linked_vowel_runs': all(
            not records[entry['run_id']]['errors']
            and sha256(RUNS / entry['run_id'] / 'manifest.json') == entry['manifest_sha256']
            for entry in vowel_entries(result)),
        'three_voiced_windows': [w['ipa'] for w in voiced] == ['i', 'ɑ', 'u']
        and all(w['frame_count'] > 0 and all(w['checks'].values()) for w in voiced),
    }
    return checks, {
        'vowels': [v['ipa'] for v in vowels], 'transitions': len(transitions),
        'missing_bandwidth': {v['ipa']: v['missing_bandwidth'] for v in vowels if v['missing_bandwidth']},
        'f0_hz': {v['ipa']: v['pcm_f0_hz'] for v in vowels},
    }


def independent_runs_match(config, records, artifact_names):
    first, repeat = (RUNS / config[key]['run'] for key in ('first', 'repeat'))
    files = ('summary.json', *(f'artifacts/{name}' for name in artifact_names))
    return (
        saved_case(first.name) == saved_case(repeat.name)
        and all(not records[run.name]['errors'] and sha256(run / 'manifest.json') == config[key]['manifest_sha256']
                for key, run in (('first', first), ('repeat', repeat)))
        and all(sha256(first / name) == sha256(repeat / name) for name in files))


def audit_open_o_bandwidth(config, records, vowels):
    repeat = RUNS / config['repeat']['run']
    study = saved_case(repeat.name)
    definition, _, archives = open_o_bandwidth.baseline_inputs(study)
    replay = open_o_bandwidth.analyze(study, read_json(definition), repeat / 'artifacts', archives)
    evidence = [f'{grid}/{file}' for grid in open_o_bandwidth.sweeps(study['grid'])
                for file in ('input.json', 'settings.json', 'trace.csv', 'upstream-trace.csv',
                             'upstream-peaks.csv', *open_o_bandwidth.NETWORK_FILES)]
    missing = replay['grids']['original']['missing_indices']
    checks = {
        'open_o_high_bandwidth/continuous_roots_replayed': all(replay['checks'].values()) and replay == summary(repeat.name),
        'open_o_high_bandwidth/independent_runs_match': independent_runs_match(config, records, evidence),
        'open_o_high_bandwidth/original_missing_and_extended_crossings_retained': (
            missing == vowels['missing_bandwidth']['ɔ'] == [4, 5]
            and all(row['left_hz'] is not None and row['right_hz'] is not None for row in replay['continuous'].values())),
    }
    observed = {key: replay[key] for key in ('hypotheses', 'continuous', 'interpeak_valley', 'crossing_errors_hz')}
    return checks, {'run': repeat.name, 'original_missing_indices': missing, **observed}


def open_o_bandwidth_inputs(config):
    run = RUNS / config['repeat']['run']
    study = saved_case(run.name)
    definition, references, _ = open_o_bandwidth.baseline_inputs(study)
    corpus = (run / 'artifacts' / grid / name for grid in open_o_bandwidth.sweeps(study['grid'])
              for name in ('trace.csv', 'upstream-trace.csv', 'upstream-peaks.csv', 'settings.json',
                           *open_o_bandwidth.NETWORK_FILES))
    return [definition, *references, Path(open_o_bandwidth.__file__), Path(open_o_bandwidth.vowel.__file__), *corpus]


OPEN_O_LPC_OUTPUTS = (*open_o_lpc.WAVES.values(), 'native-vowel-report.json', 'analysis-windows.npz',
                      'upstream-analysis.json')


def audit_open_o_lpc(config, records, vowels):
    repeat = RUNS / config['repeat']['run']
    study = saved_case(repeat.name)
    definitions, archived = open_o_lpc.archived_inputs(study)
    replay = open_o_lpc.analyze(study, definitions, archived, repeat / 'artifacts')
    checks = {
        'open_o_lpc/archived_inputs_and_crossed_analysis_replayed': all(replay['checks'].values()) and replay == summary(repeat.name),
        'open_o_lpc/independent_runs_match': independent_runs_match(config, records, OPEN_O_LPC_OUTPUTS),
        'open_o_lpc/linked_historical_waveforms': (
            study['sequence']['run'] == VOWEL_RUN
            and study['fixed']['run'] == next(row['voice_run']['run_id'] for row in summary(VOWEL_RUN)['vowels']
                                             if row['ipa'] == study['measurement']['ipa'])
            and study['measurement']['ipa'] in vowels['vowels']),
    }
    return checks, {'run': repeat.name, 'hypotheses': replay['hypotheses'], 'statistics': replay['statistics']}


def open_o_lpc_inputs(config):
    run = RUNS / config['repeat']['run']
    definitions, archived = open_o_lpc.archived_inputs(saved_case(run.name))
    return [*definitions.values(), *(path for entries in archived.values() for path in entries.values()),
            *(Path(mod.__file__) for mod in (open_o_lpc, open_o_lpc.vowel, open_o_lpc.benchmark)),
            *(run / 'artifacts' / name for name in OPEN_O_LPC_OUTPUTS)]


def order_artifacts(study):
    return ('lpc-window.npy', *open_o_orders.upstream_outputs(study))


def audit_open_o_orders(config, records, vowels):
    repeat = RUNS / config['repeat']['run']
    study = saved_case(repeat.name)
    replay = open_o_orders.analyze(study, open_o_orders.input_paths(study), repeat / 'artifacts')
    checks = {
        'open_o_lpc_orders/shared_window_and_each_order_replayed': all(replay['checks'].values()) and replay == summary(repeat.name),
        'open_o_lpc_orders/independent_runs_match': independent_runs_match(config, records, order_artifacts(study)),
        'open_o_lpc_orders/legacy_probe_defaults_reproduced': independent_runs_match(
            config['probe_compatibility'], records, ('upstream-pre-emphasis.json', 'spectra.json')),
        'open_o_lpc_orders/linked_matched_waveform_and_endpoint_orders': (
            study['reference']['run'] == vowels['open_o_matched_lpc']['run']
            and replay['checks']['archived_endpoints_reproduced']),
    }
    return checks, {'run': repeat.name, 'hypotheses': replay['hypotheses'],
                    'first_order_with_all_three_bands': replay['first_order_with_all_three_bands'],
                    'endpoints_lowest_shift_hz': replay['endpoints_lowest_shift_hz']}


def open_o_order_inputs(config):
    run = RUNS / config['repeat']['run']
    study = saved_case(run.name)
    return [*open_o_orders.input_paths(study).values(), Path(open_o_orders.__file__),
            *(run / 'artifacts' / name for name in order_artifacts(study))]


LF_RADIATION_OUTPUTS = ('radiation-observations.npz', 'wall-observation.patch', 'harmonic-power-deltas.csv')


def audit_lf_radiation_budget(config, records, failures):
    repeat = RUNS / config['repeat']['run']
    study = saved_case(repeat.name)
    replay = lf_radiation_budget.analyze(study, lf_radiation_budget.archive_inputs(study), repeat / 'artifacts')
    ref = study['reference']
    checks = {
        'lf_radiation/replayed_harmonic_and_wall_budget': all(replay['checks'].values()) and replay == summary(repeat.name),
        'lf_radiation/independent_runs_match': independent_runs_match(config, records, LF_RADIATION_OUTPUTS),
        'lf_radiation/original_decision_retained': (
            replay['legacy_decision'] is False and failures[ref['run']] == ref['expected_failed_checks']
            and not records[ref['run']]['errors']),
    }
    keys = ('hypotheses', 'all_bin_power_deltas', 'lip_derivative_fraction_of_radiation_loss',
            'priority_fraction_of_lip_derivative_loss', 'lip_fundamental_replaced_relative_rms', 'legacy_decision')
    return checks, {'run': repeat.name, **{key: replay[key] for key in keys}}


def lf_radiation_inputs(config):
    run = RUNS / config['repeat']['run']
    study = saved_case(run.name)
    return [*lf_radiation_budget.archive_inputs(study).values(), Path(lf_radiation_budget.__file__),
            Path(lf_radiation_budget.lf.__file__), *(run / 'artifacts' / name for name in LF_RADIATION_OUTPUTS)]


def audit_lf_transfer(config, records, failures):
    run = RUNS / config['repeat']['run']
    study = saved_case(run.name)
    replay = lf_transfer.analyze(study, lf_transfer.archive_inputs(study), run / 'artifacts')
    reference = study['references']['legacy']['run']
    checks = {
        'lf_transfer/replayed_complex_source_and_tract_partition': (
            all(replay['checks'].values()) and replay == summary(run.name)),
        'lf_transfer/independent_runs_match': independent_runs_match(config, records, lf_transfer.EVIDENCE),
        'lf_transfer/original_decision_retained': (
            replay['legacy_failed_checks'] == failures[reference] == study['measurement']['legacy_failed_checks']
            and not records[reference]['errors']),
    }
    return checks, {'run': run.name, **{key: value for key, value in replay.items() if key != 'checks'}}


def lf_transfer_inputs(config):
    run = RUNS / config['repeat']['run']
    study = saved_case(run.name)
    archive = lf_transfer.archive_inputs(study)
    return [*(path for group in archive.values() for path in group.values()),
            Path(lf_transfer.__file__), Path(lf_transfer.vowel.__file__),
            *(run / 'artifacts' / name for name in lf_transfer.EVIDENCE)]


def audit_discrete_alpha(config, records, failures):
    run = RUNS / config['repeat']['run']
    study = saved_case(run.name)
    replay = discrete_alpha.analyze(study, discrete_alpha.archive_inputs(study), run / 'artifacts')
    short = study['short_window_reference']
    checks = {
        'discrete_alpha/replayed_small_signal_and_discrete_network': (
            all(replay['checks'].values()) and replay == summary(run.name)),
        'discrete_alpha/independent_runs_match': independent_runs_match(config, records, discrete_alpha.EVIDENCE),
        'discrete_alpha/short_window_failures_retained': (
            not records[short['run']]['errors'] and failures[short['run']] == short['expected_failed_checks']),
    }
    return checks, {'run': run.name, **{key: value for key, value in replay.items() if key != 'checks'}}


def discrete_alpha_inputs(config):
    run = RUNS / config['repeat']['run']
    study = saved_case(run.name)
    return [*discrete_alpha.archive_inputs(study).values(), Path(discrete_alpha.__file__),
            Path(discrete_alpha.fixed.__file__), *(run / 'artifacts' / name for name in discrete_alpha.EVIDENCE)]


def audit_mean_alpha(config, records):
    run = RUNS / config['repeat']['run']
    study = saved_case(run.name)
    replay = mean_alpha.analyze(study, mean_alpha.archive_inputs(study), run / 'artifacts')
    checks = {
        'mean_alpha/replayed_steady_flow_and_complex_increment': (
            all(replay['checks'].values()) and replay == summary(run.name)),
        'mean_alpha/independent_runs_match': independent_runs_match(config, records, mean_alpha.EVIDENCE),
    }
    return checks, {'run': run.name, **{key: value for key, value in replay.items() if key != 'checks'}}


def mean_alpha_inputs(config):
    run = RUNS / config['repeat']['run']
    study = saved_case(run.name)
    return [*mean_alpha.archive_inputs(study).values(), Path(mean_alpha.__file__),
            mean_alpha.sagittal.PROBE, *(run / 'artifacts' / name for name in mean_alpha.EVIDENCE)]


def audit_periodic_alpha(config, records):
    run = RUNS / config['repeat']['run']
    study = saved_case(run.name)
    archive = periodic_alpha.archive_inputs(study)
    replay = periodic_alpha.analyze(study, archive, run / 'artifacts')
    observed = ('pressure_supra_dyn_cm2', periodic_alpha.LF.LIP, 'nose_flow_cm3_s', periodic_alpha.LF.RAD)
    fixed = ('pressure_pharynx_entry', 'flow_lips', 'flow_nose', 'radiation_derivative')
    original_columns = [periodic_alpha.LF.OBSERVED.index(field) for field in observed]
    replay_columns = [periodic_alpha.FIELDS.index(field) for field in fixed]
    with np.load(archive['source.npz'], allow_pickle=False) as original:
        with np.load(run / 'artifacts/replay-traces.npz', allow_pickle=False) as trace:
            matches = all(np.array_equal(
                original[f'{arm}_upstream'][:, original_columns].view(np.uint64),
                trace[f'{arm}-full_upstream'][:, replay_columns].view(np.uint64)) for arm in periodic_alpha.ARMS)
    checks = {
        'periodic_alpha/replayed_periodic_and_whole_history_transfer': (
            all(replay['checks'].values()) and replay == summary(run.name)),
        'periodic_alpha/independent_runs_match': independent_runs_match(config, records, periodic_alpha.EVIDENCE),
        'periodic_alpha/whole_history_fixed_upstream_matches_voiced_bits': matches,
    }
    return checks, {'run': run.name, 'conditions': replay['conditions']}


def periodic_alpha_inputs(config):
    run = RUNS / config['repeat']['run']
    study = saved_case(run.name)
    return [*periodic_alpha.archive_inputs(study).values(), Path(periodic_alpha.__file__),
            periodic_alpha.mean.sagittal.PROBE, *(run / 'artifacts' / name for name in periodic_alpha.EVIDENCE)]


def audit_branch_alpha(config, records, failures):
    run = RUNS / config['repeat']['run']
    study = saved_case(run.name)
    replay = branch_alpha.analyze(study, branch_alpha.archive_inputs(study), run / 'artifacts')
    checks = {
        'branch_alpha/replayed_kinetic_loss_and_lip_transfer': (
            all(replay['checks'].values()) and replay == summary(run.name)),
        'branch_alpha/independent_runs_match': independent_runs_match(config, records, branch_alpha.EVIDENCE),
        'branch_alpha/original_index_alignment_failures_retained': (
            failures[study['initial_alignment_failure']['run']] == replay['initial_failed_checks']),
    }
    return checks, {'run': run.name, 'conditions': replay['conditions']}


def branch_alpha_inputs(config):
    run = RUNS / config['repeat']['run']
    study = saved_case(run.name)
    return [*branch_alpha.archive_inputs(study).values(), Path(branch_alpha.__file__),
            Path(discrete_alpha.__file__), branch_alpha.MEAN.sagittal.PROBE,
            *(run / 'artifacts' / name for name in branch_alpha.EVIDENCE)]


def audit_tangent_alpha(config, records, failures):
    run = RUNS / config['repeat']['run']
    study = saved_case(run.name)
    replay = tangent_alpha.analyze(study, tangent_alpha.archive_inputs(study), run / 'artifacts')
    checks = {
        'tangent_alpha/replayed_dc_control_and_complex_changes': (
            all(replay['checks'].values()) and replay == summary(run.name)),
        'tangent_alpha/independent_runs_match': independent_runs_match(config, records, tangent_alpha.EVIDENCE),
        'tangent_alpha/initial_dc_failures_retained': (
            failures[study['initial_dc_comparison']['run']] == replay['initial_failed_checks']),
    }
    return checks, {'run': run.name, **{key: value for key, value in replay.items() if key != 'checks'}}


def tangent_alpha_inputs(config):
    run = RUNS / config['repeat']['run']
    study = saved_case(run.name)
    return [*tangent_alpha.archive_inputs(study).values(), Path(tangent_alpha.__file__),
            Path(branch_alpha.__file__), tangent_alpha.PROBE,
            *(run / 'artifacts' / name for name in tangent_alpha.EVIDENCE)]


def audit_alpha_loss_intervention(config, records, module, label, *, dc_key='dc_changes'):
    run = RUNS / config['repeat']['run']
    study = saved_case(run.name)
    replay = module.analyze(study, module.archive_inputs(study), run / 'artifacts')
    checks = {
        f'{label}/replayed_work_law_and_acoustic_contrast': (
            all(replay['checks'].values()) and replay == summary(run.name)),
        f'{label}/independent_runs_match': independent_runs_match(config, records, module.EVIDENCE),
    }
    followup = {'run': run.name, 'conditions': replay['conditions'], 'dc_changes': replay[dc_key]}
    followup.update({key: replay[key] for key in ('width_comparison', 'fixed_flow_comparison') if key in replay})
    return checks, followup


def alpha_loss_intervention_inputs(config, module):
    run = RUNS / config['repeat']['run']
    study = saved_case(run.name)
    return [*module.archive_inputs(study).values(), Path(module.__file__), Path(tangent_alpha.__file__),
            tangent_alpha.PROBE, *(run / 'artifacts' / name for name in module.EVIDENCE)]


def audit_lf_fundamental(config, records):
    run = RUNS / config['repeat']['run']
    study = saved_case(run.name)
    replay = lf_fundamental.analyze(study, lf_fundamental.archive_inputs(study), run / 'artifacts')
    return {
        'lf_fundamental/replayed_input_and_lip_radiation_budget': (
            all(replay['checks'].values()) and replay == summary(run.name)),
        'lf_fundamental/independent_runs_match': independent_runs_match(config, records, lf_fundamental.EVIDENCE),
    }, {'run': run.name, 'conditions': replay['conditions']}


def lf_fundamental_inputs(config):
    run = RUNS / config['repeat']['run']
    study = saved_case(run.name)
    return [*lf_fundamental.archive_inputs(study).values(), Path(lf_fundamental.__file__),
            *(run / 'artifacts' / name for name in lf_fundamental.EVIDENCE)]


def audit_lf_fundamental_branches(config, records):
    run = RUNS / config['repeat']['run']
    study = saved_case(run.name)
    module = lf_fundamental_branches
    replay = module.analyze(study, module.archive_inputs(study), run / 'artifacts')
    return {
        'lf_fundamental_branches/replayed_loss_and_acoustic_closure': (
            all(replay['checks'].values()) and replay == summary(run.name)
            and module.contribution_csv(replay['branch_contributions']) == (run / 'artifacts/branch-contributions.csv').read_bytes()),
        'lf_fundamental_branches/independent_runs_match': independent_runs_match(config, records, module.EVIDENCE),
    }, {'run': run.name, 'conditions': replay['conditions']}


def lf_fundamental_branches_inputs(config):
    run = RUNS / config['repeat']['run']
    study = saved_case(run.name)
    module = lf_fundamental_branches
    return [*module.archive_inputs(study).values(), Path(module.__file__),
            *(run / 'artifacts' / name for name in module.EVIDENCE)]


def amplitude_initial_capture_matches(spec, out, cfg):
    initial = RUNS / spec['run']
    record = initial / 'failure.json'
    diagnostic = read_json(record)
    if (sha256(record) != spec['sha256'] or diagnostic['status'] != 'fail' or diagnostic['exit_code'] != 1
            or diagnostic['error'] != "KeyError: 'prefix_sha256'"
            or not all(sha256(initial / row['path']) == row['sha256'] for row in diagnostic['outputs'])):
        return False
    negative = lf_fundamental_amplitude.JOBS[-1]
    meta = read_json(initial / 'artifacts/capture.json')
    corrected = read_json(out / 'capture.json')
    if 'prefix_sha256' in meta[negative] or any(row != corrected[key] for key, row in meta.items() if key != negative):
        return False
    start = cfg['warmup_samples']
    stop = start + cfg['after_onset_samples_to_keep']
    with (
        np.load(initial / 'artifacts/replay-traces.npz', allow_pickle=False) as old,
        np.load(out / 'replay-traces.npz', allow_pickle=False) as new,
    ):
        for edition in periodic_alpha.EDITIONS:
            key = f'{negative}_{edition}'
            if (periodic_alpha.mean.sha_array(old[key][:start]) != corrected[negative]['prefix_sha256'][edition]
                    or not np.array_equal(old[key][-len(new[key]):].view(np.uint64), new[key].view(np.uint64))
                    or not np.array_equal(old[key][start:stop].view(np.uint64), new[f'{key}_start'].view(np.uint64))):
                return False
        return all(np.array_equal(old[key].view(np.uint64), new[key].view(np.uint64))
                   for key in old.files if not key.startswith(negative))


def audit_lf_fundamental_amplitude(config, records):
    run = RUNS / config['repeat']['run']
    study = saved_case(run.name)
    module = lf_fundamental_amplitude
    replay = module.analyze(study, module.archive_inputs(study), run / 'artifacts')
    return {
        'lf_fundamental_amplitude/replayed_components_and_scaling': (
            all(replay['checks'].values()) and replay == summary(run.name)),
        'lf_fundamental_amplitude/independent_runs_match': independent_runs_match(config, records, module.EVIDENCE),
        'lf_fundamental_amplitude/initial_failed_captures_match': all(
            amplitude_initial_capture_matches(spec, run / 'artifacts', study['measurement'])
            for spec in config['failed_captures']),
        'lf_fundamental_amplitude/whole_history_replay_is_preserved': independent_runs_match(
            config['window_regression'], records, periodic_alpha.EVIDENCE),
    }, {'run': run.name, 'conditions': replay['conditions']}


def lf_fundamental_amplitude_inputs(config):
    run = RUNS / config['repeat']['run']
    study = saved_case(run.name)
    module = lf_fundamental_amplitude
    return [*module.archive_inputs(study).values(), Path(module.__file__),
            *(run / 'artifacts' / name for name in module.EVIDENCE),
            *(RUNS / failed['run'] / name for failed in config['failed_captures']
              for name in ('failure.json', 'artifacts/capture.json', 'artifacts/replay-traces.npz'))]


def audit_parity_branches(config, records, module, label):
    run = RUNS / config['repeat']['run']
    study = saved_case(run.name)
    replay, detail = module.analyze(study, module.archive_inputs(study), run / 'artifacts')
    followup = {'run': run.name, 'conditions': replay['conditions']}
    if 'shape_comparison' in replay:
        followup.update(shape_comparison=replay['shape_comparison'], hypotheses=replay['hypotheses'])
    return {
        f'{label}/replayed_pressure_sources_and_scaling': (
            all(replay['checks'].values()) and replay == summary(run.name)
            and lf_fundamental_amplitude_branches.single.contribution_csv(detail)
            == (run / 'artifacts/branch-contributions.csv').read_bytes()),
        f'{label}/independent_runs_match': independent_runs_match(config, records, module.EVIDENCE),
    }, followup


def archived_measurement_inputs(config, module, evidence=None):
    run = RUNS / config['repeat']['run']
    study = saved_case(run.name)
    return [*module.archive_inputs(study).values(), Path(module.__file__),
            *(run / 'artifacts' / name for name in (module.EVIDENCE if evidence is None else evidence))]


def audit_coupled_smoothing(config, records, label, evidence, module=fixed_vowel_i_coupled):
    run = RUNS / config['repeat']['run']
    study = saved_case(run.name)
    replay = module.analyze(study, module.archive_inputs(study), run / 'artifacts')
    checks = {
        f'{label}/replayed_branches_pressure_and_pcm': all(replay['checks'].values()) and replay == summary(run.name),
        f'{label}/independent_runs_match': independent_runs_match(config, records, evidence),
    }
    keys = ('results', 'pcm_delta_comparison', 'pressure_replay', 'radiation_components')
    return checks, {'run': run.name, **{key: replay[key] for key in keys if key in replay}}


def audit_rate(rate, native_id, browser_id):
    browser = summary(browser_id)
    native = summary(native_id)
    times = {key: browser['timing'][key] for key in ('voicing', 'release')}
    windows_ok = all(w['blocks'] > 0 and 0 <= w['median_ms'] <= w['p95_ms'] <= w['p99_ms'] <= w['maximum_ms']
                     for w in times.values())
    if 'native_allocations' in native:
        allocations = native['native_allocations']['total']
        native_ok = (native['rate_hz'] == rate and native['checks']['cli_partition_invariance']
                     and native['checks']['upstream_states'] and native['checks']['native_render_allocations'])
    else:
        allocations = native['native_abi_render_allocations']
        native_ok = (rate == saved_case(native_id)['measurement']['output_rate_hz']
                     and native['checks']['registered_clock_and_rates']
                     and native['checks']['block_128_pcm'] and native['checks']['allocation_free_native_abi'])
    measured = ('production_context', 'same_format_and_events', 'no_dsp_frame_gaps', 'cli_pcm_bit_equal',
                'states_match', 'release_to_silence', 'block_timing_budget')
    valid = (native_ok and allocations >= 0 and browser['rate_hz'] == browser.get('worklet_rate_hz', rate) == rate
             and windows_ok and all(browser['checks'].get(name) is True for name in measured))
    return valid, {'timing': times, 'budget_ms': browser['budget_ms'], 'frames': browser['frames'],
                   'native_allocations': allocations, 'wasm_memory_growths': browser.get('wasm_memory_growths')}


def audit_render_memory(run_id, rate):
    measurement = saved_case(run_id)['measurement']
    report = read_json(RUNS / run_id / 'artifacts/browser.json')
    saved = summary(run_id)
    quantum = measurement['expected_quantum_frames']
    frames = report['outputFrames']
    rows = report['observations']
    growths = report.get('wasmMemoryGrowths')
    first = report.get('firstWasmMemoryGrowthFrame')
    valid = (
        type(growths) is int and growths == 0 and 'firstWasmMemoryGrowthFrame' in report and first is None
        and report['stableWasmBuffers'] is True
        and report['sampleRate'] == report['workletSampleRate'] == rate == measurement['output_rate_hz']
        and report['internalSampleRate'] == measurement['internal_rate_hz']
        and report['controlIntervalOutputFrames'] == measurement['control_interval_output_frames']
        and frames == saved['frames'] > 0 and len(rows) * quantum == frames
        and report['columns'][:5] == [
            'context_frame', 'quantum_frames', 'process_ms', 'callback_elapsed_ms', 'frames_rendered']
        and all(row[0] == rows[0][0] + index * quantum and row[1] == quantum and row[4] == (index + 1) * quantum
                for index, row in enumerate(rows))
        and ('wasm_memory_growths' not in saved or (
            type(saved['wasm_memory_growths']) is int and saved['wasm_memory_growths'] == growths
            and 'first_wasm_memory_growth_frame' in saved and saved['first_wasm_memory_growth_frame'] == first)))
    return valid, {'run': run_id, 'frames': frames, 'quanta': len(rows), 'wasm_memory_growths': growths,
                   'first_wasm_memory_growth_frame': first}


def audit_native_web_render(native, browser, frames, rate, quantum):
    with (native / 'allocations-by-quantum.csv').open(newline='') as stream:
        rows = list(csv.DictReader(stream))
    geometry = [(int(row['output_frame']), int(row['output_frames'])) for row in rows]
    expected = [(start, min(quantum, frames - start)) for start in range(0, frames, quantum)]
    native_pcm = np.fromfile(native / 'plain.f32le', dtype='<f4')
    web_pcm = wave(browser / 'browser.wav', rate, frames)
    reference = wave(browser / 'offline.wav', rate, frames)
    report = read_json(browser / 'browser.json')
    offline = read_json(browser / 'offline.json')
    observed = np.asarray(report['observations'], dtype='f8')
    expected_observations = np.asarray(offline['observations'], dtype='f8')
    observations_match = report['columns'][1:] == offline['columns'][1:] and np.array_equal(
        observed.view('u8'), expected_observations.view('u8'))
    if rate == 44100:
        observations_match = observations_match and same_states(report, offline)
    allocations = sum(int(row['allocations']) for row in rows)
    return {
        'all_native_quanta_are_allocation_free': geometry == expected and all(int(row['allocations']) == 0 for row in rows),
        'native_offline_and_browser_pcm_match': native_pcm.tobytes() == web_pcm.tobytes() == reference.tobytes(),
        'offline_and_browser_observations_match': observations_match and bool(np.isfinite(observed).all()),
    }, {'frames': frames, 'rate_hz': rate, 'native_quanta': len(rows), 'native_render_allocations': allocations}


def audit_web_followup(case, out, execute, sources):
    web = case['web_followup']
    folders = {name: RUNS / web[name] / 'artifacts' for name in (
        'english', 'english_native', 'english_cross_browser', 'english_abort', 'song', 'song_native')}
    checks = {}
    results = {}
    for name, rate in (('english', 44100), ('song', 48000)):
        comparison, results[name] = audit_native_web_render(
            folders[f'{name}_native'], folders[name], web[f'{name}_frames'], rate, web['quantum_frames'])
        checks.update({f'current_web/{name}/{key}': passed for key, passed in comparison.items()})
    clocks = {
        'english': summary(web['english'])['timing']['all'],
        'song': summary(web['song'])['realtime']['timing']['all'],
    }
    for name, timing in clocks.items():
        results[name]['browser_timing'] = timing

    english = folders['english']
    english_browser = read_json(english / 'browser-run.json')
    wasm_hash = english_browser['servedWasmSha256']
    abort_run = web['english_abort']
    if refresh := web.get('english_abort_refresh'):
        abort_run = refresh['run']
        capture = summary(abort_run)
        checks['current_web/refreshed_wasm_capture_linked'] = (
            sha256(RUNS / abort_run / 'manifest.json') == refresh['manifest_sha256']
            and capture['reference_wasm_sha256'] == wasm_hash
            and capture['wasm_sha256'] != wasm_hash)
        wasm_hash = capture['wasm_sha256']
    pcm_hashes = {name: sha256(english / f'{name}.wav') for name in ('offline', 'browser')}
    controls = {}
    for engine in ('chromium', 'firefox'):
        folder = RUNS / abort_run / 'artifacts' / engine
        stopped = read_json(folder / 'abort-evidence.json')
        held = stopped['whileHeld']
        final = stopped['afterRestart']
        controls[engine] = {'wasm_requests': stopped['routeRequests'], 'realtime_contexts': final['contexts']}
        checks[f'current_web/{engine}/stop_and_restart'] = (
            held['contexts'] == [{'state': 'closed', 'rate': 44100, 'nodes': 0}]
            and held['calls']['offline']['outcome'] == 'pending' and held['compilations'] == 0
            and final['calls']['offline']['outcome'] == final['calls']['restarted']['outcome'] == 'fulfilled'
            and stopped['routeRequests'] == final['compilations'] == final['planners'] == 1
            and stopped['compiledSha256'] == [wasm_hash]
            and sha256(folder / 'offline.wav') == pcm_hashes['offline']
            and sha256(folder / 'restarted.wav') == pcm_hashes['browser'])
    checks['current_web/cross_browser_48000_pcm'] = (
        sha256(folders['english_cross_browser'] / 'chromium/browser.wav')
        == sha256(folders['english_cross_browser'] / 'firefox/browser.wav'))

    manifest = read_json(RUNS / abort_run / 'manifest.json')
    recorded_sources = {entry['path']: entry['sha256'] for entry in manifest['inputs']}
    runtime_sources = [path for path in sources if path.is_relative_to(WEB / 'src')
                       or path.is_relative_to(WORKSPACE / 'crates/vocal-wasm/host')]
    checks['current_web/runtime_sources_match_abort_capture'] = bool(runtime_sources) and all(
        recorded_sources.get(str(path.relative_to(ROOT))) == sha256(path) for path in runtime_sources)

    builds = WORK_DISK / 'voice-simulator/build'
    candidate_log, upstream_log = (out / f'{name}-cargo-tests.log' for name in ('candidate', 'upstream'))
    execute(['env', f'CARGO_TARGET_DIR={builds / "chimera-rebuild-debug"}',
             'cargo', 'test', '--locked', '--offline', '--workspace'], stdout=candidate_log)
    execute(['env', f'CARGO_TARGET_DIR={builds / "chimera-upstream-debug"}',
             'cargo', 'test', '--locked', '--offline', '-p', 'chimera', '--test', 'airway',
             '--test', 'engine', '--test', 'english', '--test', 'lung_port'], cwd=UPSTREAM, stdout=upstream_log)
    test_counts = {name: sum(map(int, re.findall(r'test result: ok\. (\d+) passed; 0 failed', log.read_text())))
                   for name, log in (('candidate', candidate_log), ('upstream', upstream_log))}
    checks.update({f'current_web/{name}_tests_ran': count > 0 for name, count in test_counts.items()})
    bun = ['bun'] if shutil.which('bun') else ['npx', '--offline', '--yes', '--package=bun@1.4.4', '--', 'bun']
    with TemporaryDirectory(dir=out.parent) as build:
        execute([*bun, 'run', 'build', '--outDir', build], cwd=WEB, stdout=out / 'candidate-web-build.log')
        binaries = sorted(Path(build).glob('assets/vocal_wasm-*.wasm'))
        checks['current_web/current_build_matches_browser_wasm'] = len(binaries) == 1 and sha256(binaries[0]) == wasm_hash

    midi_log = out / 'coremidi-endpoint-counts.txt'
    execute(['/usr/bin/xcrun', 'swift', '-e',
             'import CoreMIDI; print(MIDIGetNumberOfSources(), MIDIGetNumberOfDestinations())'], stdout=midi_log)
    midi_sources, midi_destinations = map(int, midi_log.read_text().split())
    results.update(controls=controls, test_counts=test_counts, wasm_sha256=wasm_hash,
                   runtime_source_count=len(runtime_sources),
                   coremidi_endpoints={'inputs': midi_sources, 'outputs': midi_destinations})
    if refresh:
        results['wasm_capture_run'] = abort_run
    return checks, results


def audit_stage7_followup(case, stage7_run):
    config = case['stage7_followup']
    baseline_run = config['baseline_run']
    baseline = summary(baseline_run)
    current = summary(stage7_run)
    definition = saved_case(stage7_run)
    manifest = read_json(RUNS / stage7_run / 'manifest.json')
    baseline_case = saved_case(baseline_run)
    baseline_items = {item['run']: item for item in baseline_case['evidence']}
    current_items = {item['run']: item for item in definition['evidence']}
    coverage = current['coverage']
    checks = {
        'stage7/latest_baseline_pinned': sha256(RUNS / baseline_run / 'manifest.json') == config['baseline_manifest_sha256'],
        'stage7/selected_audit_identity': manifest['run_id'] == stage7_run
        and manifest['case_id'] == definition['id'] == 'plan-evidence-stage7'
        and manifest['case_revision'] == definition['revision'] >= config['minimum_audit_revision']
        and definition['upstream_revision'] == manifest['upstream_revision'] == case['upstream_revision'],
        'stage7/baseline_registrations_preserved': (
            set(baseline['records']) == set(baseline_items) and set(current['records']) == set(current_items)
            and all(current_items.get(run) == item for run, item in baseline_items.items())
            and all(current['checks'].get(key) is status for key, status in baseline['checks'].items())
            and set(current['verified_runs_by_topic']) == set(case['stage7_topics'])
            and all(current['verified_runs_by_topic'].values())),
    }
    listening_checks, listening = listening_observations(definition, manifest['listening_runs'])
    f2_checks, f2 = annotation_observations(definition, manifest['f2_annotation_run'])
    midi_checks, midi = physical_midi_observations(definition, manifest['physical_midi_run'])
    checks.update({f'stage7/{name}': value for name, value in (listening_checks | f2_checks | midi_checks).items()})
    primary = {'human_listening': listening, 'human_f2_annotations': f2, 'physical_midi_capture': midi}
    pending = evaluation_evidence(listening, f2, midi, coverage['listening_response_kind'],
                                  coverage['listening_package_human_returned'],
                                  coverage['f2_followup'].get('annotation', {}).get('human_annotations_recorded_in_material'))
    checks['stage7/primary_observations_recalculated'] = all(
        json.dumps(result, sort_keys=True) == json.dumps(coverage[key], sort_keys=True)
        for key, result in primary.items())
    checks['stage7/availability_matches_primary_observations'] = pending == coverage['unverified_evaluation_evidence']

    review_run = config['review_archives_run']
    review_manifest = read_json(RUNS / review_run / 'manifest.json')
    review = summary(review_run)
    hashes = {entry['path']: entry['sha256'] for entry in review_manifest['outputs']}
    checks['stage7/review_archives_linked_as_preparation'] = (
        sha256(RUNS / review_run / 'manifest.json') == config['review_archives_manifest_sha256']
        and review_manifest['case_id'] == 'stage7-review-archives' and review['response_kind'] == 'synthetic'
        and set(review['packets']) == {'tsp-listening', 'csd-listening', 'tsp-f2'}
        and all(hashes.get(f'artifacts/{name}.zip') == info['archive_sha256']
                for name, info in review['packets'].items()))
    return checks, {'run': stage7_run, 'revision': manifest['case_revision'], 'verified_runs': len(current['records']),
                    'topics': current['verified_runs_by_topic'], **primary, 'primary_evidence': pending,
                    'review_archives': {'run': review_run, 'packets': review['packets']}}


def release_pcm_inputs(config, blocks):
    yield RUNS / config['reference_run'] / 'artifacts/upstream-voice.f32'
    for name in config['captures']:
        folder = RUNS / name / 'artifacts'
        if name == config['variant_run']:
            for side in ('control', 'reordered'):
                yield from (folder / side / f'candidate-{block}.wav' for block in blocks)
        else:
            yield folder / 'upstream-voice.f32'
            yield from (folder / f'candidate-{block}.wav' for block in blocks)


def audit_release_followup(config):
    output_run = config['output_run']
    variant_run = config['variant_run']
    reference_run = config['reference_run']
    source = saved_case(output_run)
    variant = saved_case(variant_run)
    rate, frames = source['output_rate_hz'], source['full_frames']
    first, second = source['blocks']
    start, stop = source['gate_open_frame'], source['gate_close_frame']

    def capture(folder):
        a, b = (wave(folder / f'candidate-{block}.wav', rate, frames) for block in (first, second))
        return a, a.tobytes() == b.tobytes()

    reference = RUNS / reference_run / 'artifacts/upstream-voice.f32'
    upstream = np.fromfile(reference, dtype='<f4')
    folder = RUNS / variant_run / 'artifacts'
    control, control_partition = capture(folder / 'control')
    reordered, reordered_partition = capture(folder / 'reordered')
    pinned = config['captures'] | {
        reference_run: config['reference_manifest_sha256'],
        config['failed_run']: config['failed_manifest_sha256'],
    }
    checks = {'fixed_release/manifests': all(sha256(RUNS / name / 'manifest.json') == digest
                                            for name, digest in pinned.items()),
              f'fixed_release/host_partitions/{variant_run}': control_partition and reordered_partition}
    for name in config['captures']:
        if name == variant_run:
            continue
        folder = RUNS / name / 'artifacts'
        archived, same_partition = capture(folder)
        checks[f'fixed_release/host_partitions/{name}'] = same_partition
        checks[f'fixed_release/reference_and_control/{name}'] = (
            archived.tobytes() == control.tobytes() and sha256(folder / 'upstream-voice.f32') == sha256(reference))

    pairs = {'control_upstream': (control, upstream), 'reordered_upstream': (reordered, upstream),
             'reordered_control': (reordered, control)}
    reports, mismatches = {}, {}
    for name, (left, right) in pairs.items():
        report = compare_pcm(left, right, variant['pcm_absolute_tolerance'])
        different = left.view('<u4') != right.view('<u4')
        report['different_frames'] = int(different.sum())
        report['different_frames_by_period'] = {
            'before_gate': int(different[:start].sum()),
            'voiced': int(different[start:stop].sum()),
            'after_gate_close': int(different[stop:].sum()),
        }
        reports[name] = report
        mismatches[name] = set(np.flatnonzero(different).tolist())
    before, after = (mismatches[name] for name in ('control_upstream', 'reordered_upstream'))
    earlier, later = (reports[name] for name in ('control_upstream', 'reordered_upstream'))
    target = source['target_frame']
    first_difference_ulps = abs(int(control.view('<u4')[target]) - int(upstream.view('<u4')[target]))
    observed = {'first_bit_difference_frame': earlier['first_bit_difference_frame'],
                'first_difference_ulps': first_difference_ulps,
                'control_different_frames': len(before), 'reordered_different_frames': len(after),
                'resolved_frames': len(before - after), 'new_differences': len(after - before)}
    checks.update({
        'fixed_release/pcm_calculated_from_waveforms': reports == summary(variant_run)['pcm'],
        'fixed_release/remaining_differences': (
            observed == config['expected_pcm']
            and earlier['first_bit_difference_frame'] == later['first_bit_difference_frame'] == variant['target_output_frame']
            and earlier['maximum_absolute_error'] == later['maximum_absolute_error']
            and all(not any(i < stop for i in difference) for difference in mismatches.values())
            and all(report['first_frame_over_tolerance'] is None for report in reports.values())),
    })
    return checks, {
        'source_case': source['id'], 'registered_runs': list(config['captures']), 'upstream_pcm_run': reference_run,
        'failed_capture': {'run': config['failed_run'], 'error': config['failed_error']},
        'scope': '固定 /i/ の隔離ビルド', 'output_rate_hz': rate, 'internal_rate_hz': source['internal_rate_hz'],
        'frames': frames, 'gate_frames': [start, stop], 'host_blocks': [first, second],
        'absolute_tolerance': variant['pcm_absolute_tolerance'], 'pcm': reports, **observed,
    }


def verify(case, vowel_result, run_ids, out, execute, web_inputs, stage7_run=None):
    revision = case['upstream_revision']
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    status = subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True)
    execute(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM)
    execute(['git', 'status', '--porcelain'], cwd=UPSTREAM)
    checks = {'fixed_upstream': head == revision and not status}
    failures = case['archived_failures']
    release = case.get('release_followup')
    exceptions = {release['failed_run']: release['failed_error']} if release else {}
    wasm_radiation = case.get('fixed_vowel_i_wasm_radiation_followup')
    if wasm_radiation:
        initial = wasm_radiation['runner_failure']['run']
        exceptions[initial] = read_json(RUNS / initial / 'manifest.json')['error']
    if reversal := case.get('fixed_vowel_i_pharynx_reversal_low_harmonics_followup'):
        initial = reversal['initial']
        exceptions[initial['run']] = initial['expected_error']
    records = {name: read_record(name, revision, name in failures or name in exceptions,
                                 expected_failed_checks=failures.get(name, ()), expected_error=exceptions.get(name))[0]
               for name in run_ids}
    checks.update({f'archive/{name}': not record['errors'] for name, record in records.items()})
    for stage, group in case['stages'].items():
        for name, expected in group.items():
            checks[f'stage_{stage}/{name}'] = set(expected) <= set(records[name]['passed_checks'])
    for name, expected in case['investigations'].items():
        checks[f'investigation/{name}'] = set(expected) <= set(records[name]['passed_checks'])

    tubes = {}
    for name in TUBE_RUNS:
        conditions, tubes[name] = audit_tube(name, case['tube'], revision)
        checks.update({f'{name}/{key}': ok for key, ok in conditions.items()})
    conditions, vowels = audit_vowels(vowel_result, case['vowels'], records)
    checks.update(conditions)

    vcv_result = summary(VCV_RUN)
    vcv = vcv_result['plan_observations']['ordered_utterances']
    checks['five_ipa_inputs_and_events'] = (
        vcv == case['vcv'] == saved_case(VCV_RUN)['measurement']['expected']['ordered_utterances']
        and vcv_result['candidate_events']['passed'] and vcv_result['upstream_events']['passed']
        and vcv_result['frames'] > 0)

    rates = {}
    for rate, (native, browser) in case['output_rates'].items():
        checks[f'output_rate/{rate}'], rates[rate] = audit_rate(int(rate), native or case['native_48000'], browser)
    realtime = {}
    for name, required in case['realtime'].items():
        result = summary(name)
        trials = result['trials']
        checks[f'realtime/{name}'] = (
            set(t['engine'] for t in trials) == {'chromium', 'firefox'}
            and all(t['frames'] > 0 and all(t['checks'].get(key) is True for key in required) for t in trials))
        realtime[name] = {'frames': sorted({t['frames'] for t in trials}),
                          'trials_by_browser': dict(Counter(t['engine'] for t in trials))}
        if 'native_allocations' in result:
            realtime[name]['native_abi_allocations'] = result['native_allocations']['total']

    stage7 = summary(next(iter(case['stages']['7'])))
    topics = stage7['verified_runs_by_topic']
    outstanding = stage7['coverage']['unverified_evaluation_evidence']
    checks['stage_7_topics'] = set(topics) == set(case['stage7_topics']) and all(topics.values())
    checks['unverified_evidence_remains_visible'] = set(outstanding) == set(case['stage7_unverified']) and all(
        outstanding[name]['status'] == 'unverified' and outstanding[name]['required_observation'] == observation
        for name, observation in case['stage7_unverified'].items())

    previous = summary(case['previous_audit'])
    checks['revision_2_checks_reproduced'] = all(
        checks.get(name) is answer for name, answer in previous['checks'].items())
    conditions, current_web = audit_web_followup(case, out, execute, web_inputs)
    checks.update(conditions)
    followup = {}
    if stage7_run is not None:
        config = case['stage7_followup']
        previous_run = config['previous_run']
        checks['revision_3_checks_reproduced'] = (
            sha256(RUNS / previous_run / 'manifest.json') == config['previous_manifest_sha256']
            and all(checks.get(name) is answer for name, answer in summary(previous_run)['checks'].items()))
        conditions, latest = audit_stage7_followup(case, stage7_run)
        checks.update(conditions)
        followup['stage_7_followup'] = latest
        topics = latest['topics']
        outstanding = latest['primary_evidence']
    if memory := case.get('render_memory_followup'):
        readings = {}
        for rate, (_, browser) in case['output_rates'].items():
            checks[f'output_rate/{rate}/render_memory'], readings[rate] = audit_render_memory(browser, int(rate))
            rates[rate]['wasm_memory_growths'] = readings[rate]['wasm_memory_growths']
        current = memory['current_48000']
        frames_ok, current_rate = audit_rate(48000, case['native_48000'], current)
        memory_ok, current_memory = audit_render_memory(current, 48000)
        checks['current_web/fixed_48000_render_memory'] = (
            frames_ok and memory_ok and current_rate['wasm_memory_growths'] == 0
            and summary(current)['checks'].get('render_memory_growth') is True)
        capture = RUNS / current / 'artifacts'
        checks['current_web/fixed_48000_wasm_matches_build'] = (
            read_json(capture / 'browser-run.json')['servedWasmSha256']
            == sha256(capture / 'vocal_wasm.wasm') == current_web['wasm_sha256'])
        previous_run = memory['previous_run']
        checks['revision_4_checks_reproduced'] = (
            sha256(RUNS / previous_run / 'manifest.json') == memory['previous_manifest_sha256']
            and all(checks.get(name) is answer for name, answer in summary(previous_run)['checks'].items()))
        followup['render_memory'] = {'archived_rates': readings, 'current_48000': {**current_rate, **current_memory}}
    if release:
        previous_run = release['previous_run']
        checks['revision_5_checks_reproduced'] = (
            sha256(RUNS / previous_run / 'manifest.json') == release['previous_manifest_sha256']
            and all(checks.get(name) is answer for name, answer in summary(previous_run)['checks'].items()))
        conditions, followup['fixed_release'] = audit_release_followup(release)
        checks.update(conditions)
    if bandwidth := case.get('open_o_bandwidth_followup'):
        previous_run = bandwidth['previous_run']
        checks['revision_6_checks_reproduced'] = (
            sha256(RUNS / previous_run / 'manifest.json') == bandwidth['previous_manifest_sha256']
            and all(checks.get(name) is answer for name, answer in summary(previous_run)['checks'].items()))
        conditions, vowels['open_o_high_bandwidth'] = audit_open_o_bandwidth(bandwidth, records, vowels)
        checks.update(conditions)
    if lpc := case.get('open_o_lpc_followup'):
        previous_run = lpc['previous_run']
        checks['revision_7_checks_reproduced'] = (
            sha256(RUNS / previous_run / 'manifest.json') == lpc['previous_manifest_sha256']
            and all(checks.get(name) is answer for name, answer in summary(previous_run)['checks'].items()))
        conditions, vowels['open_o_matched_lpc'] = audit_open_o_lpc(lpc, records, vowels)
        checks.update(conditions)
    if orders := case.get('open_o_orders_followup'):
        previous_run = orders['previous_run']
        checks['revision_8_checks_reproduced'] = (
            sha256(RUNS / previous_run / 'manifest.json') == orders['previous_manifest_sha256']
            and all(checks.get(name) is answer for name, answer in summary(previous_run)['checks'].items()))
        conditions, vowels['open_o_lpc_orders'] = audit_open_o_orders(orders, records, vowels)
        checks.update(conditions)
    if lf_budget := case.get('lf_radiation_budget_followup'):
        previous_run = lf_budget['previous_run']
        checks['revision_9_checks_reproduced'] = (
            sha256(RUNS / previous_run / 'manifest.json') == lf_budget['previous_manifest_sha256']
            and all(checks.get(name) is answer for name, answer in summary(previous_run)['checks'].items()))
        conditions, followup['lf_radiation_harmonic_budget'] = audit_lf_radiation_budget(lf_budget, records, failures)
        checks.update(conditions)
    if lf_harmonics := case.get('lf_harmonic_transfer_followup'):
        previous_run = lf_harmonics['previous_run']
        checks['revision_10_checks_reproduced'] = (
            sha256(RUNS / previous_run / 'manifest.json') == lf_harmonics['previous_manifest_sha256']
            and all(checks.get(name) is answer for name, answer in summary(previous_run)['checks'].items()))
        conditions, followup['lf_harmonic_transfer'] = audit_lf_transfer(lf_harmonics, records, failures)
        checks.update(conditions)
    if discrete := case.get('discrete_alpha_followup'):
        previous_run = discrete['previous_run']
        checks['revision_11_checks_reproduced'] = (
            sha256(RUNS / previous_run / 'manifest.json') == discrete['previous_manifest_sha256']
            and all(checks.get(name) is answer for name, answer in summary(previous_run)['checks'].items()))
        conditions, followup['discrete_alpha_impulse'] = audit_discrete_alpha(discrete, records, failures)
        checks.update(conditions)
    if mean := case.get('mean_alpha_followup'):
        previous_run = mean['previous_run']
        checks['revision_12_checks_reproduced'] = (
            sha256(RUNS / previous_run / 'manifest.json') == mean['previous_manifest_sha256']
            and all(checks.get(name) is answer for name, answer in summary(previous_run)['checks'].items()))
        conditions, followup['mean_alpha_impulse'] = audit_mean_alpha(mean, records)
        checks.update(conditions)
    if periodic := case.get('periodic_alpha_followup'):
        previous_run = periodic['previous_run']
        checks['revision_13_checks_reproduced'] = (
            sha256(RUNS / previous_run / 'manifest.json') == periodic['previous_manifest_sha256']
            and all(checks.get(name) is answer for name, answer in summary(previous_run)['checks'].items()))
        conditions, followup['periodic_alpha_replay'] = audit_periodic_alpha(periodic, records)
        checks.update(conditions)
    if branch := case.get('branch_alpha_followup'):
        previous_run = branch['previous_run']
        checks['revision_14_checks_reproduced'] = (
            sha256(RUNS / previous_run / 'manifest.json') == branch['previous_manifest_sha256']
            and all(checks.get(name) is answer for name, answer in summary(previous_run)['checks'].items()))
        conditions, followup['branch_alpha_loss'] = audit_branch_alpha(branch, records, failures)
        checks.update(conditions)
    if tangent := case.get('tangent_alpha_followup'):
        previous_run = tangent['previous_run']
        checks['revision_15_checks_reproduced'] = (
            sha256(RUNS / previous_run / 'manifest.json') == tangent['previous_manifest_sha256']
            and all(checks.get(name) is answer for name, answer in summary(previous_run)['checks'].items()))
        conditions, followup['tangent_alpha_intervention'] = audit_tangent_alpha(tangent, records, failures)
        checks.update(conditions)
    if passive := case.get('passive_alpha_followup'):
        previous_run = passive['previous_run']
        checks['revision_16_checks_reproduced'] = (
            sha256(RUNS / previous_run / 'manifest.json') == passive['previous_manifest_sha256']
            and all(checks.get(name) is answer for name, answer in summary(previous_run)['checks'].items()))
        conditions, followup['passive_alpha_intervention'] = audit_alpha_loss_intervention(
            passive, records, passive_alpha, 'passive_alpha')
        checks.update(conditions)
    if high_flow := case.get('high_flow_alpha_followup'):
        previous_run = high_flow['previous_run']
        checks['revision_17_checks_reproduced'] = (
            sha256(RUNS / previous_run / 'manifest.json') == high_flow['previous_manifest_sha256']
            and all(checks.get(name) is answer for name, answer in summary(previous_run)['checks'].items()))
        conditions, followup['high_flow_alpha_intervention'] = audit_alpha_loss_intervention(
            high_flow, records, high_flow_alpha, 'high_flow_alpha')
        unchanged = high_flow_alpha.EVIDENCE
        accepted = RUNS / high_flow['repeat']['run'] / 'artifacts'
        checks['high_flow_alpha/initial_failures_and_unchanged_observations_retained'] = all(
            (name in failures and not records[name]['errors']
             and sha256(RUNS / name / 'manifest.json') == digest
             and all(sha256(RUNS / name / 'artifacts' / item) == sha256(accepted / item) for item in unchanged))
            for name, digest in high_flow['initial_manifests'].items()
        )
        checks.update(conditions)
    if low_flow := case.get('low_flow_alpha_followup'):
        previous_run = low_flow['previous_run']
        checks['revision_18_checks_reproduced'] = (
            sha256(RUNS / previous_run / 'manifest.json') == low_flow['previous_manifest_sha256']
            and all(checks.get(name) is answer for name, answer in summary(previous_run)['checks'].items()))
        conditions, followup['low_flow_alpha_intervention'] = audit_alpha_loss_intervention(
            low_flow, records, low_flow_alpha, 'low_flow_alpha')
        checks.update(conditions)
    if fundamental := case.get('lf_fundamental_followup'):
        previous_run = fundamental['previous_run']
        checks['revision_19_checks_reproduced'] = (
            sha256(RUNS / previous_run / 'manifest.json') == fundamental['previous_manifest_sha256']
            and all(checks.get(name) is answer for name, answer in summary(previous_run)['checks'].items()))
        conditions, followup['lf_fundamental_intervention'] = audit_lf_fundamental(fundamental, records)
        checks.update(conditions)
    if fundamental_branches := case.get('lf_fundamental_branches_followup'):
        previous_run = fundamental_branches['previous_run']
        checks['revision_20_checks_reproduced'] = (
            sha256(RUNS / previous_run / 'manifest.json') == fundamental_branches['previous_manifest_sha256']
            and all(checks.get(name) is answer for name, answer in summary(previous_run)['checks'].items()))
        conditions, followup['lf_fundamental_branches'] = audit_lf_fundamental_branches(fundamental_branches, records)
        checks.update(conditions)
    if amplitude := case.get('lf_fundamental_amplitude_followup'):
        previous_run = amplitude['previous_run']
        checks['revision_21_checks_reproduced'] = (
            sha256(RUNS / previous_run / 'manifest.json') == amplitude['previous_manifest_sha256']
            and all(checks.get(name) is answer for name, answer in summary(previous_run)['checks'].items()))
        conditions, followup['lf_fundamental_amplitude'] = audit_lf_fundamental_amplitude(amplitude, records)
        checks.update(conditions)
    if amplitude_branches := case.get('lf_fundamental_amplitude_branches_followup'):
        previous_run = amplitude_branches['previous_run']
        checks['revision_22_checks_reproduced'] = (
            sha256(RUNS / previous_run / 'manifest.json') == amplitude_branches['previous_manifest_sha256']
            and all(checks.get(name) is answer for name, answer in summary(previous_run)['checks'].items()))
        conditions, followup['lf_fundamental_amplitude_branches'] = audit_parity_branches(
            amplitude_branches, records, lf_fundamental_amplitude_branches, 'lf_fundamental_amplitude_branches')
        checks.update(conditions)
    if smoothed := case.get('lf_fundamental_smoothed_followup'):
        previous_run = smoothed['previous_run']
        checks['revision_23_checks_reproduced'] = (
            sha256(RUNS / previous_run / 'manifest.json') == smoothed['previous_manifest_sha256']
            and all(checks.get(name) is answer for name, answer in summary(previous_run)['checks'].items()))
        conditions, followup['lf_fundamental_smoothed'] = audit_alpha_loss_intervention(
            smoothed, records, lf_fundamental_smoothed, 'lf_fundamental_smoothed', dc_key='dc_checks')
        checks.update(conditions)
    if narrow := case.get('lf_fundamental_smoothed_width_30_followup'):
        previous_run = narrow['previous_run']
        checks['revision_24_checks_reproduced'] = (
            sha256(RUNS / previous_run / 'manifest.json') == narrow['previous_manifest_sha256']
            and all(checks.get(name) is answer for name, answer in summary(previous_run)['checks'].items()))
        conditions, followup['lf_fundamental_smoothed_width_30'] = audit_alpha_loss_intervention(
            narrow, records, lf_fundamental_smoothed, 'lf_fundamental_smoothed_width_30', dc_key='dc_checks')
        checks.update(conditions)
    if same_input_i := case.get('fixed_vowel_i_lf_followup'):
        previous_run = same_input_i['previous_run']
        checks['revision_25_checks_reproduced'] = (
            sha256(RUNS / previous_run / 'manifest.json') == same_input_i['previous_manifest_sha256']
            and all(checks.get(name) is answer for name, answer in summary(previous_run)['checks'].items()))
        conditions, followup['fixed_vowel_i_lf'] = audit_parity_branches(
            same_input_i, records, fixed_vowel_i_lf, 'fixed_vowel_i_lf')
        checks.update(conditions)
    if smoothing_i := case.get('fixed_vowel_i_lf_smoothing_followup'):
        previous_run = smoothing_i['previous_run']
        checks['revision_26_checks_reproduced'] = (
            sha256(RUNS / previous_run / 'manifest.json') == smoothing_i['previous_manifest_sha256']
            and all(checks.get(name) is answer for name, answer in summary(previous_run)['checks'].items()))
        conditions, followup['fixed_vowel_i_lf_smoothing'] = audit_alpha_loss_intervention(
            smoothing_i, records, lf_fundamental_smoothed, 'fixed_vowel_i_lf_smoothing', dc_key='dc_checks')
        checks.update(conditions)
    if coupled_i := case.get('fixed_vowel_i_coupled_smoothing_followup'):
        previous_run = coupled_i['previous_run']
        checks['revision_27_checks_reproduced'] = (
            sha256(RUNS / previous_run / 'manifest.json') == coupled_i['previous_manifest_sha256']
            and all(checks.get(name) is answer for name, answer in summary(previous_run)['checks'].items()))
        conditions, followup['fixed_vowel_i_coupled_smoothing'] = audit_coupled_smoothing(
            coupled_i, records, 'fixed_vowel_i_coupled_smoothing', fixed_vowel_i_coupled.EVIDENCE)
        checks.update(conditions)
    if low_pressure := case.get('fixed_vowel_i_low_pressure_smoothing_followup'):
        previous_run = low_pressure['previous_run']
        checks['revision_28_checks_reproduced'] = (
            sha256(RUNS / previous_run / 'manifest.json') == low_pressure['previous_manifest_sha256']
            and all(checks.get(name) is answer for name, answer in summary(previous_run)['checks'].items()))
        conditions, followup['fixed_vowel_i_low_pressure_smoothing'] = audit_coupled_smoothing(
            low_pressure, records, 'fixed_vowel_i_low_pressure_smoothing', fixed_vowel_i_coupled.GATE_EVIDENCE)
        checks.update(conditions)
    if pressure_replay := case.get('fixed_vowel_i_pressure_replay_followup'):
        previous_run = pressure_replay['previous_run']
        checks['revision_29_checks_reproduced'] = (
            sha256(RUNS / previous_run / 'manifest.json') == pressure_replay['previous_manifest_sha256']
            and all(checks.get(name) is answer for name, answer in summary(previous_run)['checks'].items()))
        conditions, followup['fixed_vowel_i_pressure_replay'] = audit_coupled_smoothing(
            pressure_replay, records, 'fixed_vowel_i_pressure_replay', fixed_vowel_i_coupled.REPLAY_EVIDENCE)
        checks.update(conditions)
    if radiation_split := case.get('fixed_vowel_i_radiation_components_followup'):
        previous_run = radiation_split['previous_run']
        checks['revision_30_checks_reproduced'] = (
            sha256(RUNS / previous_run / 'manifest.json') == radiation_split['previous_manifest_sha256']
            and all(checks.get(name) is answer for name, answer in summary(previous_run)['checks'].items()))
        conditions, followup['fixed_vowel_i_radiation_components'] = audit_coupled_smoothing(
            radiation_split, records, 'fixed_vowel_i_radiation_components',
            fixed_vowel_i_radiation.EVIDENCE, module=fixed_vowel_i_radiation)
        checks.update(conditions)
    if cli_radiation := case.get('fixed_vowel_i_cli_radiation_followup'):
        previous_run = cli_radiation['previous_run']
        checks['revision_31_checks_reproduced'] = (
            sha256(RUNS / previous_run / 'manifest.json') == cli_radiation['previous_manifest_sha256']
            and all(checks.get(name) is answer for name, answer in summary(previous_run)['checks'].items()))
        module = fixed_vowel_i_cli_radiation
        repeat = RUNS / cli_radiation['repeat']['run']
        initial = RUNS / cli_radiation['initial']['run']
        study = saved_case(repeat.name)
        archive = module.archive_inputs(study)
        replay = module.analyze(study, archive, repeat / 'artifacts')
        checks['fixed_vowel_i_cli_radiation/replayed_samples_pcm_and_clocks'] = (
            all(replay['checks'].values()) and replay == summary(repeat.name))
        checks['fixed_vowel_i_cli_radiation/independent_runs_match'] = (
            independent_runs_match(cli_radiation, records, module.EVIDENCE))
        original = summary(initial.name)
        checks['fixed_vowel_i_cli_radiation/only_initial_schema_check_corrected'] = (
            sha256(initial / 'manifest.json') == cli_radiation['initial']['manifest_sha256']
            and all(sha256(initial / 'artifacts' / filename) == sha256(repeat / 'artifacts' / filename)
                    for filename in module.EVIDENCE)
            and {**original, 'checks': {**original['checks'], 'only_two_explicit_columns_appended': True}} == replay)
        followup['fixed_vowel_i_cli_radiation'] = {'run': repeat.name, **replay}
    if wasm_radiation:
        previous_run = wasm_radiation['previous_run']
        checks['revision_32_checks_reproduced'] = (
            sha256(RUNS / previous_run / 'manifest.json') == wasm_radiation['previous_manifest_sha256']
            and all(checks.get(name) is answer for name, answer in summary(previous_run)['checks'].items()))
        module = fixed_vowel_i_wasm_radiation
        repeat = RUNS / wasm_radiation['repeat']['run']
        study = saved_case(repeat.name)
        replay = module.analyze(study, module.archive_inputs(study), repeat / 'artifacts')
        checks['fixed_vowel_i_wasm_radiation/replayed_clocks_radiation_and_pcm'] = (
            all(replay['checks'].values()) and replay == summary(repeat.name)
            and replay['wasm_sha256'] == current_web['wasm_sha256'])
        checks['fixed_vowel_i_wasm_radiation/independent_runs_match'] = (
            independent_runs_match(wasm_radiation, records, module.EVIDENCE))
        initial, hash_check = (RUNS / wasm_radiation[key]['run'] for key in ('runner_failure', 'hash_failure'))
        checks['fixed_vowel_i_wasm_radiation/initial_capture_failures_preserved'] = (
            all(not records[attempt.name]['errors']
                and sha256(attempt / 'manifest.json') == wasm_radiation[key]['manifest_sha256']
                for key, attempt in (('runner_failure', initial), ('hash_failure', hash_check)))
            and 'ERR_UNSUPPORTED_TYPESCRIPT_SYNTAX' in (initial / 'artifacts/cargo.log').read_text()
            and failures[hash_check.name] == ['browser_served_current_wasm'])
        followup['fixed_vowel_i_wasm_radiation'] = {'run': repeat.name, **replay}
    if screen := case.get('fixed_vowel_i_radiation_screen_followup'):
        previous_run = screen['previous_run']
        checks['revision_33_checks_reproduced'] = (
            sha256(RUNS / previous_run / 'manifest.json') == screen['previous_manifest_sha256']
            and all(checks.get(name) is answer for name, answer in summary(previous_run)['checks'].items()))
        module = fixed_vowel_i_radiation_screen
        repeat = RUNS / screen['repeat']['run']
        study = saved_case(repeat.name)
        replay = module.analyze(study, module.archive_inputs(study), repeat / 'artifacts')
        checks['fixed_vowel_i_radiation_screen/replayed_downloads_clocks_and_pcm'] = (
            all(replay['checks'].values()) and replay == summary(repeat.name)
            and replay['wasm_sha256'] == current_web['wasm_sha256'])
        checks['fixed_vowel_i_radiation_screen/independent_runs_match'] = (
            independent_runs_match(screen, records, module.EVIDENCE))
        followup['fixed_vowel_i_radiation_screen'] = {'run': repeat.name, **replay}
    if velum := case.get('fixed_vowel_i_velum_radiation_followup'):
        previous_run = velum['previous_run']
        checks['revision_34_checks_reproduced'] = (
            sha256(RUNS / previous_run / 'manifest.json') == velum['previous_manifest_sha256']
            and all(checks.get(name) is answer for name, answer in summary(previous_run)['checks'].items()))
        module = fixed_vowel_i_velum_radiation
        repeat = RUNS / velum['repeat']['run']
        initial = RUNS / velum['initial']['run']
        study = saved_case(repeat.name)
        archive = module.archive_inputs(study)
        replay = module.analyze(study, archive, repeat / 'artifacts')
        checks['fixed_vowel_i_velum_radiation/replayed_port_flows_radiation_and_pcm'] = (
            all(replay['checks'].values()) and replay == summary(repeat.name)
            and replay['wasm_sha256'] == current_web['wasm_sha256'])
        checks['fixed_vowel_i_velum_radiation/independent_runs_match'] = (
            independent_runs_match(velum, records, module.EVIDENCE))
        checks['fixed_vowel_i_velum_radiation/initial_inspect_checks_preserved'] = (
            not records[initial.name]['errors']
            and sha256(initial / 'manifest.json') == velum['initial']['manifest_sha256']
            and all(sha256(initial / 'artifacts' / filename) == sha256(repeat / 'artifacts' / filename)
                    for filename in module.EVIDENCE)
            and {**summary(initial.name), 'checks': replay['checks']} == replay)
        followup['fixed_vowel_i_velum_radiation'] = {'run': repeat.name, **replay}
    if port := case.get('fixed_vowel_i_velum_port_only_followup'):
        previous_run = port['previous_run']
        checks['revision_35_checks_reproduced'] = (
            sha256(RUNS / previous_run / 'manifest.json') == port['previous_manifest_sha256']
            and all(checks.get(name) is answer for name, answer in summary(previous_run)['checks'].items()))
        module = fixed_vowel_i_velum_port_only
        repeat = RUNS / port['repeat']['run']
        study = saved_case(repeat.name)
        replay = module.analyze(study, module.archive_inputs(study), repeat / 'artifacts')
        checks['fixed_vowel_i_velum_port_only/replayed_geometry_port_balance_and_pcm'] = (
            all(replay['checks'].values()) and replay == summary(repeat.name))
        checks['fixed_vowel_i_velum_port_only/independent_runs_match'] = (
            independent_runs_match(port, records, module.EVIDENCE))
        followup['fixed_vowel_i_velum_port_only'] = {'run': repeat.name, **replay}
    if transfer := case.get('fixed_vowel_i_velum_harmonic_transfer_followup'):
        previous_run = transfer['previous_run']
        checks['revision_36_checks_reproduced'] = (
            sha256(RUNS / previous_run / 'manifest.json') == transfer['previous_manifest_sha256']
            and all(checks.get(name) is answer for name, answer in summary(previous_run)['checks'].items()))
        module = fixed_vowel_i_velum_harmonic_transfer
        repeat = RUNS / transfer['repeat']['run']
        study = saved_case(repeat.name)
        replay = module.analyze(study, module.archive_inputs(study), repeat / 'artifacts')
        rejected = {name for name, answer in replay['checks'].items() if not answer}
        checks['fixed_vowel_i_velum_harmonic_transfer/replayed_transfer_and_registered_hypothesis'] = (
            replay == summary(repeat.name)
            and rejected == set(failures[repeat.name]) == {'measurable_finite_amplitude_remainder'})
        checks['fixed_vowel_i_velum_harmonic_transfer/independent_runs_match'] = (
            independent_runs_match(transfer, records, module.EVIDENCE))
        followup['fixed_vowel_i_velum_harmonic_transfer'] = {'run': repeat.name, **replay}
    if tangent := case.get('fixed_vowel_i_velum_mean_flow_tangent_followup'):
        previous_run = tangent['previous_run']
        checks['revision_37_checks_reproduced'] = (
            sha256(RUNS / previous_run / 'manifest.json') == tangent['previous_manifest_sha256']
            and all(checks.get(name) is answer for name, answer in summary(previous_run)['checks'].items()))
        module = fixed_vowel_i_velum_mean_flow_tangent
        repeat = RUNS / tangent['repeat']['run']
        study = saved_case(repeat.name)
        replay = module.analyze(study, module.archive_inputs(study), repeat / 'artifacts')
        checks['fixed_vowel_i_velum_mean_flow_tangent/replayed_pressure_balance_and_nose_response'] = (
            all(replay['checks'].values()) and replay == summary(repeat.name))
        checks['fixed_vowel_i_velum_mean_flow_tangent/independent_runs_match'] = (
            independent_runs_match(tangent, records, module.EVIDENCE))
        followup['fixed_vowel_i_velum_mean_flow_tangent'] = {'run': repeat.name, **replay}
    if loss := case.get('fixed_vowel_i_velum_oral_nasal_loss_followup'):
        previous_run = loss['previous_run']
        checks['revision_38_checks_reproduced'] = (
            sha256(RUNS / previous_run / 'manifest.json') == loss['previous_manifest_sha256']
            and all(checks.get(name) is answer for name, answer in summary(previous_run)['checks'].items()))
        module = fixed_vowel_i_velum_oral_nasal_loss
        repeat, initial = (RUNS / loss[key]['run'] for key in ('repeat', 'initial'))
        study = saved_case(repeat.name)
        replay = module.analyze(study, module.archive_inputs(study), repeat / 'artifacts')
        rejected = {name for name, answer in replay['checks'].items() if not answer}
        checks['fixed_vowel_i_velum_oral_nasal_loss/replayed_branch_balance_and_registered_hypothesis'] = (
            replay == summary(repeat.name) and rejected == set(failures[repeat.name]) == {module.HYPOTHESIS})
        checks['fixed_vowel_i_velum_oral_nasal_loss/independent_runs_match'] = (
            independent_runs_match(loss, records, module.EVIDENCE))
        checks['fixed_vowel_i_velum_oral_nasal_loss/initial_index_comparison_retained'] = (
            not records[initial.name]['errors']
            and sha256(initial / 'manifest.json') == loss['initial']['manifest_sha256']
            and saved_case(initial.name) == study
            and all(sha256(initial / 'artifacts' / name) == sha256(repeat / 'artifacts' / name)
                    for name in module.EVIDENCE)
            and summary(initial.name)['editions'] == replay['editions'])
        followup['fixed_vowel_i_velum_oral_nasal_loss'] = {'run': repeat.name, **replay}
    if supraglottal := case.get('fixed_vowel_i_velum_supraglottal_loss_followup'):
        previous_run = supraglottal['previous_run']
        checks['revision_39_checks_reproduced'] = (
            sha256(RUNS / previous_run / 'manifest.json') == supraglottal['previous_manifest_sha256']
            and all(checks.get(name) is answer for name, answer in summary(previous_run)['checks'].items()))
        module = fixed_vowel_i_velum_supraglottal_loss
        repeat = RUNS / supraglottal['repeat']['run']
        study = saved_case(repeat.name)
        replay = module.analyze(study, module.archive_inputs(study))
        checks['fixed_vowel_i_velum_supraglottal_loss/replayed_all_branch_losses_and_nose_response'] = (
            all(replay['checks'].values()) and replay == summary(repeat.name))
        checks['fixed_vowel_i_velum_supraglottal_loss/independent_runs_match'] = (
            independent_runs_match(supraglottal, records, module.EVIDENCE))
        followup['fixed_vowel_i_velum_supraglottal_loss'] = {'run': repeat.name, **replay}
    if pharynx := case.get('fixed_vowel_i_pharynx_mean_flow_tangent_followup'):
        previous_run = pharynx['previous_run']
        checks['revision_40_checks_reproduced'] = (
            sha256(RUNS / previous_run / 'manifest.json') == pharynx['previous_manifest_sha256']
            and all(checks.get(name) is answer for name, answer in summary(previous_run)['checks'].items()))
        module = fixed_vowel_i_pharynx_mean_flow_tangent
        repeat = RUNS / pharynx['repeat']['run']
        study = saved_case(repeat.name)
        replay = module.analyze(study, module.archive_inputs(study))
        rejected = {name for name, answer in replay['checks'].items() if not answer}
        checks['fixed_vowel_i_pharynx_mean_flow_tangent/replayed_feedback_and_registered_hypothesis'] = (
            replay == summary(repeat.name) and rejected == set(failures[repeat.name]) == {module.HYPOTHESIS})
        checks['fixed_vowel_i_pharynx_mean_flow_tangent/independent_runs_match'] = (
            independent_runs_match(pharynx, records, module.EVIDENCE))
        followup['fixed_vowel_i_pharynx_mean_flow_tangent'] = {'run': repeat.name, **replay}
    if pairs := case.get('fixed_vowel_i_pharynx_harmonic_pairs_followup'):
        previous_run = pairs['previous_run']
        checks['revision_41_checks_reproduced'] = (
            sha256(RUNS / previous_run / 'manifest.json') == pairs['previous_manifest_sha256']
            and all(checks.get(name) is answer for name, answer in summary(previous_run)['checks'].items()))
        module = fixed_vowel_i_pharynx_harmonic_pairs
        repeat = RUNS / pairs['repeat']['run']
        study = saved_case(repeat.name)
        replay = module.analyze(study, module.archive_inputs(study))
        checks['fixed_vowel_i_pharynx_harmonic_pairs/replayed_spectral_losses_and_nose_response'] = (
            all(replay['checks'].values()) and replay == summary(repeat.name))
        checks['fixed_vowel_i_pharynx_harmonic_pairs/independent_runs_match'] = (
            independent_runs_match(pairs, records, module.EVIDENCE))
        followup['fixed_vowel_i_pharynx_harmonic_pairs'] = {'run': repeat.name, **replay}
    if low_pressure_pairs := case.get('fixed_vowel_i_pharynx_harmonic_pairs_low_pressure_followup'):
        previous_run = low_pressure_pairs['previous_run']
        checks['revision_42_checks_reproduced'] = (
            sha256(RUNS / previous_run / 'manifest.json') == low_pressure_pairs['previous_manifest_sha256']
            and all(checks.get(name) is answer for name, answer in summary(previous_run)['checks'].items()))
        module = fixed_vowel_i_pharynx_harmonic_pairs_low_pressure
        repeat = RUNS / low_pressure_pairs['repeat']['run']
        study = saved_case(repeat.name)
        replay = module.analyze(study, module.archive_inputs(study), repeat / 'artifacts')
        checks['fixed_vowel_i_pharynx_harmonic_pairs_low_pressure/replayed_new_capture_and_unchanged_pairs'] = (
            all(replay['checks'].values()) and replay == summary(repeat.name))
        checks['fixed_vowel_i_pharynx_harmonic_pairs_low_pressure/independent_runs_match'] = (
            independent_runs_match(low_pressure_pairs, records, module.EVIDENCE))
        followup['fixed_vowel_i_pharynx_harmonic_pairs_low_pressure'] = {'run': repeat.name, **replay}
    if reversal := case.get('fixed_vowel_i_pharynx_reversal_low_harmonics_followup'):
        previous_run = reversal['previous_run']
        checks['revision_43_checks_reproduced'] = (
            sha256(RUNS / previous_run / 'manifest.json') == reversal['previous_manifest_sha256']
            and all(checks.get(name) is answer for name, answer in summary(previous_run)['checks'].items()))
        module = fixed_vowel_i_pharynx_reversal_low_harmonics
        repeat = RUNS / reversal['repeat']['run']
        study = saved_case(repeat.name)
        replay = module.analyze(study, module.archive_inputs(study))
        checks['fixed_vowel_i_pharynx_reversal_low_harmonics/replayed_reversal_and_nose_response'] = (
            all(replay['checks'].values()) and replay == summary(repeat.name))
        checks['fixed_vowel_i_pharynx_reversal_low_harmonics/independent_runs_match'] = (
            independent_runs_match(reversal, records, module.EVIDENCE))
        initial = reversal['initial']
        checks['fixed_vowel_i_pharynx_reversal_low_harmonics/initial_serialization_failure_retained'] = (
            not records[initial['run']]['errors']
            and sha256(RUNS / initial['run'] / 'manifest.json') == initial['manifest_sha256']
            and saved_case(initial['run']) == study)
        followup['fixed_vowel_i_pharynx_reversal_low_harmonics'] = {'run': repeat.name, **replay}
    if glottal_flow := case.get('fixed_vowel_i_pharynx_from_glottal_flow_followup'):
        previous_run = glottal_flow['previous_run']
        checks['revision_44_checks_reproduced'] = (
            sha256(RUNS / previous_run / 'manifest.json') == glottal_flow['previous_manifest_sha256']
            and all(checks.get(name) is answer for name, answer in summary(previous_run)['checks'].items()))
        module = fixed_vowel_i_pharynx_from_glottal_flow
        repeat = RUNS / glottal_flow['repeat']['run']
        study = saved_case(repeat.name)
        replay = module.analyze(study, module.archive_inputs(study))
        checks['fixed_vowel_i_pharynx_from_glottal_flow/replayed_complex_flows_and_reversal'] = (
            all(replay['checks'].values()) and replay == summary(repeat.name))
        checks['fixed_vowel_i_pharynx_from_glottal_flow/independent_runs_match'] = (
            independent_runs_match(glottal_flow, records, module.EVIDENCE))
        followup['fixed_vowel_i_pharynx_from_glottal_flow'] = {'run': repeat.name, **replay}
    if steady_flow := case.get('fixed_vowel_i_pharynx_steady_flow_followup'):
        previous_run = steady_flow['previous_run']
        checks['revision_45_checks_reproduced'] = (
            sha256(RUNS / previous_run / 'manifest.json') == steady_flow['previous_manifest_sha256']
            and all(checks.get(name) is answer for name, answer in summary(previous_run)['checks'].items()))
        module = fixed_vowel_i_pharynx_steady_flow
        repeat = RUNS / steady_flow['repeat']['run']
        study = saved_case(repeat.name)
        replay = module.analyze(study, module.archive_inputs(study))
        checks['fixed_vowel_i_pharynx_steady_flow/replayed_outlet_split_and_harmonics'] = (
            all(replay['checks'].values()) and replay == summary(repeat.name))
        checks['fixed_vowel_i_pharynx_steady_flow/independent_runs_match'] = (
            independent_runs_match(steady_flow, records, module.EVIDENCE))
        followup['fixed_vowel_i_pharynx_steady_flow'] = {'run': repeat.name, **replay}
    if averaged_loss := case.get('fixed_vowel_i_pharynx_averaged_loss_followup'):
        previous_run = averaged_loss['previous_run']
        checks['revision_46_checks_reproduced'] = (
            sha256(RUNS / previous_run / 'manifest.json') == averaged_loss['previous_manifest_sha256']
            and all(checks.get(name) is answer for name, answer in summary(previous_run)['checks'].items()))
        module = fixed_vowel_i_pharynx_averaged_loss
        repeat = RUNS / averaged_loss['repeat']['run']
        study = saved_case(repeat.name)
        replay = module.analyze(study, module.archive_inputs(study))
        checks['fixed_vowel_i_pharynx_averaged_loss/replayed_averaged_loss_and_flow_split'] = (
            all(replay['checks'].values()) and replay == summary(repeat.name))
        checks['fixed_vowel_i_pharynx_averaged_loss/independent_runs_match'] = (
            independent_runs_match(averaged_loss, records, module.EVIDENCE))
        followup['fixed_vowel_i_pharynx_averaged_loss'] = {'run': repeat.name, **replay}
    if predicted_radiation := case.get('fixed_vowel_i_pharynx_predicted_radiation_followup'):
        previous_run = predicted_radiation['previous_run']
        checks['revision_47_checks_reproduced'] = (
            sha256(RUNS / previous_run / 'manifest.json') == predicted_radiation['previous_manifest_sha256']
            and all(checks.get(name) is answer for name, answer in summary(previous_run)['checks'].items()))
        module = fixed_vowel_i_pharynx_predicted_radiation
        repeat = RUNS / predicted_radiation['repeat']['run']
        study = saved_case(repeat.name)
        replay = module.analyze(study, module.archive_inputs(study))
        checks['fixed_vowel_i_pharynx_predicted_radiation/replayed_prediction_and_loss_sources'] = (
            all(replay['checks'].values()) and replay == summary(repeat.name))
        checks['fixed_vowel_i_pharynx_predicted_radiation/independent_runs_match'] = (
            independent_runs_match(predicted_radiation, records, module.EVIDENCE))
        followup['fixed_vowel_i_pharynx_predicted_radiation'] = {'run': repeat.name, **replay}
    if port_bandwidth := case.get('fixed_vowel_i_velum_port_bandwidth_followup'):
        previous_run = port_bandwidth['previous_run']
        checks['revision_48_checks_reproduced'] = (
            sha256(RUNS / previous_run / 'manifest.json') == port_bandwidth['previous_manifest_sha256']
            and all(checks.get(name) is answer for name, answer in summary(previous_run)['checks'].items()))
        module = fixed_vowel_i_velum_port_bandwidth
        repeat = RUNS / port_bandwidth['repeat']['run']
        study = saved_case(repeat.name)
        replay = module.analyze(study, module.archive_inputs(study))
        checks['fixed_vowel_i_velum_port_bandwidth/replayed_loss_decomposition_and_port_substitution'] = (
            all(replay['checks'].values()) and replay == summary(repeat.name))
        checks['fixed_vowel_i_velum_port_bandwidth/independent_runs_match'] = (
            independent_runs_match(port_bandwidth, records, module.EVIDENCE))
        followup['fixed_vowel_i_velum_port_bandwidth'] = {'run': repeat.name, **replay}
    if middle_harmonics := case.get('fixed_vowel_i_velum_port_middle_harmonics_followup'):
        previous_run = middle_harmonics['previous_run']
        checks['revision_49_checks_reproduced'] = (
            sha256(RUNS / previous_run / 'manifest.json') == middle_harmonics['previous_manifest_sha256']
            and all(checks.get(name) is answer for name, answer in summary(previous_run)['checks'].items()))
        module = fixed_vowel_i_velum_port_middle_harmonics
        repeat = RUNS / middle_harmonics['repeat']['run']
        study = saved_case(repeat.name)
        replay = module.analyze(study, module.archive_inputs(study))
        checks['fixed_vowel_i_velum_port_middle_harmonics/replayed_added_flow_and_nose_response'] = (
            all(replay['checks'].values()) and replay == summary(repeat.name))
        checks['fixed_vowel_i_velum_port_middle_harmonics/independent_runs_match'] = (
            independent_runs_match(middle_harmonics, records, module.EVIDENCE))
        followup['fixed_vowel_i_velum_port_middle_harmonics'] = {'run': repeat.name, **replay}
    if port_feedback := case.get('fixed_vowel_i_velum_port_loss_feedback_followup'):
        previous_run = port_feedback['previous_run']
        checks['revision_50_checks_reproduced'] = (
            sha256(RUNS / previous_run / 'manifest.json') == port_feedback['previous_manifest_sha256']
            and all(checks.get(name) is answer for name, answer in summary(previous_run)['checks'].items()))
        module = fixed_vowel_i_velum_port_loss_feedback
        repeat = RUNS / port_feedback['repeat']['run']
        study = saved_case(repeat.name)
        replay = module.analyze(study, module.archive_inputs(study))
        rejected = {name for name, answer in replay['checks'].items() if not answer}
        checks['fixed_vowel_i_velum_port_loss_feedback/replayed_port_improvement_and_nose_limit'] = (
            replay == summary(repeat.name) and rejected == set(failures[repeat.name]) == {module.NOSE_HYPOTHESIS})
        checks['fixed_vowel_i_velum_port_loss_feedback/independent_runs_match'] = (
            independent_runs_match(port_feedback, records, module.EVIDENCE))
        followup['fixed_vowel_i_velum_port_loss_feedback'] = {'run': repeat.name, **replay}
    if sensitivity := case.get('fixed_vowel_i_velum_port_loss_sensitivity_followup'):
        previous_run = sensitivity['previous_run']
        checks['revision_51_checks_reproduced'] = (
            sha256(RUNS / previous_run / 'manifest.json') == sensitivity['previous_manifest_sha256']
            and all(checks.get(name) is answer for name, answer in summary(previous_run)['checks'].items()))
        module = fixed_vowel_i_velum_port_loss_sensitivity
        repeat = RUNS / sensitivity['repeat']['run']
        study = saved_case(repeat.name)
        replay = module.analyze(study, module.archive_inputs(study))
        rejected = {name for name, answer in replay['checks'].items() if not answer}
        checks['fixed_vowel_i_velum_port_loss_sensitivity/replayed_harmonic_derivatives_and_pair_limit'] = (
            replay == summary(repeat.name) and rejected == set(failures[repeat.name]) == {module.PAIR_HYPOTHESIS})
        checks['fixed_vowel_i_velum_port_loss_sensitivity/independent_runs_match'] = (
            independent_runs_match(sensitivity, records, module.EVIDENCE))
        followup['fixed_vowel_i_velum_port_loss_sensitivity'] = {'run': repeat.name, **replay}
    if complex_pair := case.get('fixed_vowel_i_velum_port_complex_pair_followup'):
        previous_run = complex_pair['previous_run']
        checks['revision_52_checks_reproduced'] = (
            sha256(RUNS / previous_run / 'manifest.json') == complex_pair['previous_manifest_sha256']
            and all(checks.get(name) is answer for name, answer in summary(previous_run)['checks'].items()))
        module = fixed_vowel_i_velum_port_complex_pair
        repeat = RUNS / complex_pair['repeat']['run']
        study = saved_case(repeat.name)
        replay = module.analyze(study, module.archive_inputs(study))
        rejected = {name for name, answer in replay['checks'].items() if not answer}
        checks['fixed_vowel_i_velum_port_complex_pair/replayed_pair_selection_and_transfer_limit'] = (
            replay == summary(repeat.name) and rejected == set(failures[repeat.name]) == {module.TRANSFER_HYPOTHESIS})
        checks['fixed_vowel_i_velum_port_complex_pair/independent_runs_match'] = (
            independent_runs_match(complex_pair, records, module.EVIDENCE))
        followup['fixed_vowel_i_velum_port_complex_pair'] = {'run': repeat.name, **replay}
    if selected_pair_feedback := case.get('fixed_vowel_i_velum_port_selected_pair_feedback_followup'):
        previous_run = selected_pair_feedback['previous_run']
        checks['revision_53_checks_reproduced'] = (
            sha256(RUNS / previous_run / 'manifest.json') == selected_pair_feedback['previous_manifest_sha256']
            and all(checks.get(name) is answer for name, answer in summary(previous_run)['checks'].items()))
        module = fixed_vowel_i_velum_port_selected_pair_feedback
        repeat = RUNS / selected_pair_feedback['repeat']['run']
        study = saved_case(repeat.name)
        replay = module.analyze(study, module.archive_inputs(study))
        checks['fixed_vowel_i_velum_port_selected_pair_feedback/replayed_predicted_feedback_and_measured_control'] = (
            all(replay['checks'].values()) and replay == summary(repeat.name))
        checks['fixed_vowel_i_velum_port_selected_pair_feedback/independent_runs_match'] = (
            independent_runs_match(selected_pair_feedback, records, module.EVIDENCE))
        followup['fixed_vowel_i_velum_port_selected_pair_feedback'] = {'run': repeat.name, **replay}
    if narrow_port := case.get('fixed_vowel_i_velum_narrow_port_feedback_followup'):
        previous_run = narrow_port['previous_run']
        checks['revision_54_checks_reproduced'] = (
            sha256(RUNS / previous_run / 'manifest.json') == narrow_port['previous_manifest_sha256']
            and all(checks.get(name) is answer for name, answer in summary(previous_run)['checks'].items()))
        module = fixed_vowel_i_velum_narrow_port_feedback
        repeat = RUNS / narrow_port['repeat']['run']
        study = saved_case(repeat.name)
        replay = module.analyze(study, module.archive_inputs(study), repeat / 'artifacts')
        checks['fixed_vowel_i_velum_narrow_port_feedback/replayed_capture_and_fixed_pair_feedback'] = (
            all(replay['checks'].values()) and replay == summary(repeat.name))
        checks['fixed_vowel_i_velum_narrow_port_feedback/independent_runs_match'] = (
            independent_runs_match(narrow_port, records, module.EVIDENCE))
        followup['fixed_vowel_i_velum_narrow_port_feedback'] = {'run': repeat.name, **replay}
    if narrow_bandwidth := case.get('fixed_vowel_i_velum_narrow_port_bandwidth_followup'):
        previous_run = narrow_bandwidth['previous_run']
        checks['revision_55_checks_reproduced'] = (
            sha256(RUNS / previous_run / 'manifest.json') == narrow_bandwidth['previous_manifest_sha256']
            and all(checks.get(name) is answer for name, answer in summary(previous_run)['checks'].items()))
        module = fixed_vowel_i_velum_narrow_port_bandwidth
        repeat = RUNS / narrow_bandwidth['repeat']['run']
        study = saved_case(repeat.name)
        replay = module.analyze(study, module.archive_inputs(study))
        rejected = {name for name, answer in replay['checks'].items() if not answer}
        checks['fixed_vowel_i_velum_narrow_port_bandwidth/replayed_factor_contributions_and_hypothesis'] = (
            replay == summary(repeat.name) and rejected == set(failures[repeat.name]) == {module.HYPOTHESIS})
        checks['fixed_vowel_i_velum_narrow_port_bandwidth/independent_runs_match'] = (
            independent_runs_match(narrow_bandwidth, records, module.EVIDENCE))
        followup['fixed_vowel_i_velum_narrow_port_bandwidth'] = {'run': repeat.name, **replay}
    if all_harmonics := case.get('fixed_vowel_i_velum_narrow_port_all_harmonic_feedback_followup'):
        previous_run = all_harmonics['previous_run']
        checks['revision_56_checks_reproduced'] = (
            sha256(RUNS / previous_run / 'manifest.json') == all_harmonics['previous_manifest_sha256']
            and all(checks.get(name) is answer for name, answer in summary(previous_run)['checks'].items()))
        module = fixed_vowel_i_velum_narrow_port_all_harmonic_feedback
        repeat = RUNS / all_harmonics['repeat']['run']
        study = saved_case(repeat.name)
        replay = module.analyze(study, module.archive_inputs(study))
        checks['fixed_vowel_i_velum_narrow_port_all_harmonic_feedback/replayed_22_coefficients_and_nose'] = (
            all(replay['checks'].values()) and replay == summary(repeat.name))
        checks['fixed_vowel_i_velum_narrow_port_all_harmonic_feedback/independent_runs_match'] = (
            independent_runs_match(all_harmonics, records, module.EVIDENCE))
        followup['fixed_vowel_i_velum_narrow_port_all_harmonic_feedback'] = {'run': repeat.name, **replay}
    if upper := case.get('fixed_vowel_i_velum_narrow_port_upper_harmonics_followup'):
        previous_run = upper['previous_run']
        checks['revision_57_checks_reproduced'] = (
            sha256(RUNS / previous_run / 'manifest.json') == upper['previous_manifest_sha256']
            and all(checks.get(name) is answer for name, answer in summary(previous_run)['checks'].items()))
        module = fixed_vowel_i_velum_narrow_port_upper_harmonics
        repeat = RUNS / upper['repeat']['run']
        study = saved_case(repeat.name)
        replay = module.analyze(study, module.archive_inputs(study))
        checks['fixed_vowel_i_velum_narrow_port_upper_harmonics/replayed_port_coefficients_and_nose'] = (
            all(replay['checks'].values()) and replay == summary(repeat.name))
        checks['fixed_vowel_i_velum_narrow_port_upper_harmonics/independent_runs_match'] = (
            independent_runs_match(upper, records, module.EVIDENCE))
        followup['fixed_vowel_i_velum_narrow_port_upper_harmonics'] = {'run': repeat.name, **replay}
    if wide := case.get('fixed_vowel_i_velum_wide_port_upper_harmonics_followup'):
        previous_run = wide['previous_run']
        checks['revision_58_checks_reproduced'] = (
            sha256(RUNS / previous_run / 'manifest.json') == wide['previous_manifest_sha256']
            and all(checks.get(name) is answer for name, answer in summary(previous_run)['checks'].items()))
        module = fixed_vowel_i_velum_wide_port_upper_harmonics
        repeat = RUNS / wide['repeat']['run']
        study = saved_case(repeat.name)
        replay = module.analyze(study, module.archive_inputs(study))
        rejected = {name for name, answer in replay['checks'].items() if not answer}
        checks['fixed_vowel_i_velum_wide_port_upper_harmonics/replayed_both_bands_and_hypothesis'] = (
            replay == summary(repeat.name) and rejected == set(failures[repeat.name]) == {module.RECOVERY_HYPOTHESIS})
        checks['fixed_vowel_i_velum_wide_port_upper_harmonics/independent_runs_match'] = independent_runs_match(wide, records, module.EVIDENCE)
        followup['fixed_vowel_i_velum_wide_port_upper_harmonics'] = {'run': repeat.name, **replay}
    locations = Counter()
    for record in records.values():
        locations.update(record['verified_outputs'])
    return {'checks': checks, 'records': records,
            'totals': {'outputs': sum(locations.values()), 'locations': dict(locations),
                       'bytes': sum(record['bytes'] for record in records.values())},
            'tube': tubes, 'vowels': vowels, 'ipa': {'utterances': vcv, 'frames': vcv_result['frames']},
            'output_rates': rates, 'realtime': realtime, 'current_web': current_web, 'stage_7_topics': topics,
            'unverified_evaluation_evidence': outstanding,
            'archived_failed_checks': failures, **followup}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('--stage7-run', help='一次記録を照合済みの第7段階監査の実行ID')
    args = parser.parse_args()
    case = read_json(CASE_PATH)
    stage7_config = case.get('stage7_followup', {})
    memory_config = case.get('render_memory_followup')
    release_config = case.get('release_followup')
    bandwidth_config = case.get('open_o_bandwidth_followup')
    lpc_config = case.get('open_o_lpc_followup')
    order_config = case.get('open_o_orders_followup')
    lf_budget_config = case.get('lf_radiation_budget_followup')
    lf_harmonic_config = case.get('lf_harmonic_transfer_followup')
    discrete_alpha_config = case.get('discrete_alpha_followup')
    mean_alpha_config = case.get('mean_alpha_followup')
    periodic_alpha_config = case.get('periodic_alpha_followup')
    branch_alpha_config = case.get('branch_alpha_followup')
    tangent_alpha_config = case.get('tangent_alpha_followup')
    passive_alpha_config = case.get('passive_alpha_followup')
    high_flow_alpha_config = case.get('high_flow_alpha_followup')
    low_flow_alpha_config = case.get('low_flow_alpha_followup')
    lf_fundamental_config = case.get('lf_fundamental_followup')
    lf_fundamental_branches_config = case.get('lf_fundamental_branches_followup')
    lf_fundamental_amplitude_config = case.get('lf_fundamental_amplitude_followup')
    lf_fundamental_amplitude_branches_config = case.get('lf_fundamental_amplitude_branches_followup')
    lf_fundamental_smoothed_config = case.get('lf_fundamental_smoothed_followup')
    lf_fundamental_smoothed_width_30_config = case.get('lf_fundamental_smoothed_width_30_followup')
    fixed_vowel_i_lf_config = case.get('fixed_vowel_i_lf_followup')
    fixed_vowel_i_lf_smoothing_config = case.get('fixed_vowel_i_lf_smoothing_followup')
    fixed_vowel_i_coupled_config = case.get('fixed_vowel_i_coupled_smoothing_followup')
    fixed_vowel_i_low_pressure_config = case.get('fixed_vowel_i_low_pressure_smoothing_followup')
    fixed_vowel_i_pressure_replay_config = case.get('fixed_vowel_i_pressure_replay_followup')
    fixed_vowel_i_radiation_config = case.get('fixed_vowel_i_radiation_components_followup')
    fixed_vowel_i_cli_radiation_config = case.get('fixed_vowel_i_cli_radiation_followup')
    fixed_vowel_i_wasm_radiation_config = case.get('fixed_vowel_i_wasm_radiation_followup')
    fixed_vowel_i_radiation_screen_config = case.get('fixed_vowel_i_radiation_screen_followup')
    fixed_vowel_i_velum_radiation_config = case.get('fixed_vowel_i_velum_radiation_followup')
    fixed_vowel_i_velum_port_only_config = case.get('fixed_vowel_i_velum_port_only_followup')
    fixed_vowel_i_velum_harmonic_transfer_config = case.get('fixed_vowel_i_velum_harmonic_transfer_followup')
    fixed_vowel_i_velum_mean_flow_tangent_config = case.get('fixed_vowel_i_velum_mean_flow_tangent_followup')
    fixed_vowel_i_velum_oral_nasal_loss_config = case.get('fixed_vowel_i_velum_oral_nasal_loss_followup')
    fixed_vowel_i_velum_supraglottal_loss_config = case.get('fixed_vowel_i_velum_supraglottal_loss_followup')
    fixed_vowel_i_pharynx_mean_flow_tangent_config = case.get('fixed_vowel_i_pharynx_mean_flow_tangent_followup')
    fixed_vowel_i_pharynx_harmonic_pairs_config = case.get('fixed_vowel_i_pharynx_harmonic_pairs_followup')
    fixed_vowel_i_pharynx_harmonic_pairs_low_pressure_config = case.get('fixed_vowel_i_pharynx_harmonic_pairs_low_pressure_followup')
    fixed_vowel_i_pharynx_reversal_low_harmonics_config = case.get('fixed_vowel_i_pharynx_reversal_low_harmonics_followup')
    fixed_vowel_i_pharynx_from_glottal_flow_config = case.get('fixed_vowel_i_pharynx_from_glottal_flow_followup')
    fixed_vowel_i_pharynx_steady_flow_config = case.get('fixed_vowel_i_pharynx_steady_flow_followup')
    fixed_vowel_i_pharynx_averaged_loss_config = case.get('fixed_vowel_i_pharynx_averaged_loss_followup')
    fixed_vowel_i_pharynx_predicted_radiation_config = case.get('fixed_vowel_i_pharynx_predicted_radiation_followup')
    fixed_vowel_i_velum_port_bandwidth_config = case.get('fixed_vowel_i_velum_port_bandwidth_followup')
    fixed_vowel_i_velum_port_middle_harmonics_config = case.get('fixed_vowel_i_velum_port_middle_harmonics_followup')
    fixed_vowel_i_velum_port_loss_feedback_config = case.get('fixed_vowel_i_velum_port_loss_feedback_followup')
    fixed_vowel_i_velum_port_loss_sensitivity_config = case.get('fixed_vowel_i_velum_port_loss_sensitivity_followup')
    fixed_vowel_i_velum_port_complex_pair_config = case.get('fixed_vowel_i_velum_port_complex_pair_followup')
    fixed_vowel_i_velum_port_selected_pair_feedback_config = case.get('fixed_vowel_i_velum_port_selected_pair_feedback_followup')
    fixed_vowel_i_velum_narrow_port_feedback_config = case.get('fixed_vowel_i_velum_narrow_port_feedback_followup')
    fixed_vowel_i_velum_narrow_port_bandwidth_config = case.get('fixed_vowel_i_velum_narrow_port_bandwidth_followup')
    fixed_vowel_i_velum_narrow_port_all_harmonic_feedback_config = case.get('fixed_vowel_i_velum_narrow_port_all_harmonic_feedback_followup')
    upper_harmonics_config = case.get('fixed_vowel_i_velum_narrow_port_upper_harmonics_followup')
    wide_upper_harmonics_config = case.get('fixed_vowel_i_velum_wide_port_upper_harmonics_followup')
    stage7_run = args.stage7_run or stage7_config.get('baseline_run')
    primary_inputs = []
    if stage7_run is not None:
        if not stage7_config or not RUN_ID.fullmatch(stage7_run):
            parser.error('登録済みの第7段階監査の実行IDを指定してください')
        path = RUNS / stage7_run / 'manifest.json'
        if not path.is_file():
            parser.error('指定した第7段階の監査実行が見つかりません')
        stage7_manifest = read_json(path)
        if (stage7_manifest.get('case_id') != 'plan-evidence-stage7' or stage7_manifest.get('status') != 'pass'
                or stage7_manifest.get('case_revision', 0) < stage7_config['minimum_audit_revision']
                or stage7_manifest.get('upstream_revision') != case['upstream_revision']):
            parser.error('合格済みで、対応する版と固定上流の第7段階監査を指定してください')
        listening = stage7_manifest['listening_runs']
        names = [*listening.values(), stage7_manifest['f2_annotation_run'], stage7_manifest['physical_midi_run']]
        names = [name for name in names if name is not None]
        if not set(listening) <= set(CORPORA) or not all(isinstance(name, str) and RUN_ID.fullmatch(name) for name in names):
            parser.error('監査実行に記録された一次記録の実行IDが不正です')
        primary_inputs = evaluation_run_inputs(names)
    vowel_result = summary(VOWEL_RUN)
    run_ids = list(dict.fromkeys([
        *(name for stage in case['stages'].values() for name in stage),
        *case['investigations'], *case['archived_failures'], *case['realtime'], case['native_48000'],
        *(name for pair in case['output_rates'].values() for name in pair if name),
        *(entry['run_id'] for entry in vowel_entries(vowel_result)),
        case['previous_audit'],
        *([refresh['run']] if (refresh := case['web_followup'].get('english_abort_refresh')) else ()),
        *([stage7_run, *(stage7_config[key] for key in ('baseline_run', 'previous_run', 'review_archives_run'))]
          if stage7_run is not None else ()),
        *([memory_config['previous_run'], memory_config['current_48000']] if memory_config else ()),
        *([*(release_config[key] for key in ('previous_run', 'reference_run', 'failed_run')), *release_config['captures']]
          if release_config else ()),
        *([bandwidth_config['previous_run'], *(bandwidth_config[key]['run'] for key in ('first', 'repeat'))]
          if bandwidth_config else ()),
        *([lpc_config['previous_run'], *(lpc_config[key]['run'] for key in ('first', 'repeat'))]
          if lpc_config else ()),
        *([order_config['previous_run'], *(order_config[key]['run'] for key in ('first', 'repeat')),
           *(entry['run'] for entry in order_config['probe_compatibility'].values())]
          if order_config else ()),
        *([lf_budget_config['previous_run'], *(lf_budget_config[key]['run'] for key in ('first', 'repeat'))]
          if lf_budget_config else ()),
        *([lf_harmonic_config['previous_run'], *(lf_harmonic_config[key]['run'] for key in ('first', 'repeat'))]
          if lf_harmonic_config else ()),
        *([discrete_alpha_config['previous_run'], *(discrete_alpha_config[key]['run'] for key in ('first', 'repeat'))]
          if discrete_alpha_config else ()),
        *([mean_alpha_config['previous_run'], *(mean_alpha_config[key]['run'] for key in ('first', 'repeat'))]
          if mean_alpha_config else ()),
        *([periodic_alpha_config['previous_run'], *(periodic_alpha_config[key]['run'] for key in ('first', 'repeat'))]
          if periodic_alpha_config else ()),
        *([branch_alpha_config['previous_run'], *(branch_alpha_config[key]['run'] for key in ('first', 'repeat'))]
          if branch_alpha_config else ()),
        *([tangent_alpha_config['previous_run'], *(tangent_alpha_config[key]['run'] for key in ('first', 'repeat'))]
          if tangent_alpha_config else ()),
        *([passive_alpha_config['previous_run'], *(passive_alpha_config[key]['run'] for key in ('first', 'repeat'))]
          if passive_alpha_config else ()),
        *([high_flow_alpha_config['previous_run'], *(high_flow_alpha_config[key]['run'] for key in ('first', 'repeat'))]
          if high_flow_alpha_config else ()),
        *([low_flow_alpha_config['previous_run'], *(low_flow_alpha_config[key]['run'] for key in ('first', 'repeat'))]
          if low_flow_alpha_config else ()),
        *([lf_fundamental_config['previous_run'], *(lf_fundamental_config[key]['run'] for key in ('first', 'repeat'))]
          if lf_fundamental_config else ()),
        *([lf_fundamental_branches_config['previous_run'],
           *(lf_fundamental_branches_config[key]['run'] for key in ('first', 'repeat'))]
          if lf_fundamental_branches_config else ()),
        *([lf_fundamental_amplitude_config['previous_run'],
           *(lf_fundamental_amplitude_config[key]['run'] for key in ('first', 'repeat')),
           *(lf_fundamental_amplitude_config['window_regression'][key]['run'] for key in ('first', 'repeat'))]
          if lf_fundamental_amplitude_config else ()),
        *([lf_fundamental_amplitude_branches_config['previous_run'],
           *(lf_fundamental_amplitude_branches_config[key]['run'] for key in ('first', 'repeat'))]
          if lf_fundamental_amplitude_branches_config else ()),
        *([lf_fundamental_smoothed_config['previous_run'],
           *(lf_fundamental_smoothed_config[key]['run'] for key in ('first', 'repeat'))]
          if lf_fundamental_smoothed_config else ()),
        *([lf_fundamental_smoothed_width_30_config['previous_run'],
           *(lf_fundamental_smoothed_width_30_config[key]['run'] for key in ('first', 'repeat'))]
          if lf_fundamental_smoothed_width_30_config else ()),
        *([fixed_vowel_i_lf_config['previous_run'],
           *(fixed_vowel_i_lf_config[key]['run'] for key in ('first', 'repeat'))] if fixed_vowel_i_lf_config else ()),
        *([fixed_vowel_i_lf_smoothing_config['previous_run'],
           *(fixed_vowel_i_lf_smoothing_config[key]['run'] for key in ('first', 'repeat'))]
          if fixed_vowel_i_lf_smoothing_config else ()),
        *([fixed_vowel_i_coupled_config['previous_run'],
           *(fixed_vowel_i_coupled_config[key]['run'] for key in ('first', 'repeat'))]
          if fixed_vowel_i_coupled_config else ()),
        *([fixed_vowel_i_low_pressure_config['previous_run'],
           *(fixed_vowel_i_low_pressure_config[key]['run'] for key in ('first', 'repeat'))]
          if fixed_vowel_i_low_pressure_config else ()),
        *([fixed_vowel_i_pressure_replay_config['previous_run'],
           *(fixed_vowel_i_pressure_replay_config[key]['run'] for key in ('first', 'repeat'))]
          if fixed_vowel_i_pressure_replay_config else ()),
        *([fixed_vowel_i_radiation_config['previous_run'],
           *(fixed_vowel_i_radiation_config[key]['run'] for key in ('first', 'repeat'))]
          if fixed_vowel_i_radiation_config else ()),
        *([fixed_vowel_i_cli_radiation_config['previous_run'],
           *(fixed_vowel_i_cli_radiation_config[key]['run'] for key in ('initial', 'first', 'repeat'))]
          if fixed_vowel_i_cli_radiation_config else ()),
        *([fixed_vowel_i_wasm_radiation_config['previous_run'], *fixed_vowel_i_wasm_radiation_config['previous_web_runs'],
           *(fixed_vowel_i_wasm_radiation_config[key]['run'] for key in (
               'runner_failure', 'hash_failure', 'first', 'repeat'))] if fixed_vowel_i_wasm_radiation_config else ()),
        *([fixed_vowel_i_radiation_screen_config[key] for key in ('previous_run', 'previous_web_run')]
          if fixed_vowel_i_radiation_screen_config else ()),
        *(fixed_vowel_i_radiation_screen_config[key]['run'] for key in ('first', 'repeat')
          if fixed_vowel_i_radiation_screen_config),
        *([fixed_vowel_i_velum_radiation_config['previous_run'],
           *(fixed_vowel_i_velum_radiation_config[key]['run'] for key in ('initial', 'first', 'repeat'))]
          if fixed_vowel_i_velum_radiation_config else ()),
        *([fixed_vowel_i_velum_port_only_config['previous_run'],
           *(fixed_vowel_i_velum_port_only_config[key]['run'] for key in ('first', 'repeat'))]
          if fixed_vowel_i_velum_port_only_config else ()),
        *([fixed_vowel_i_velum_harmonic_transfer_config['previous_run'],
           *(fixed_vowel_i_velum_harmonic_transfer_config[key]['run'] for key in ('first', 'repeat'))]
          if fixed_vowel_i_velum_harmonic_transfer_config else ()),
        *([fixed_vowel_i_velum_mean_flow_tangent_config['previous_run'],
           *(fixed_vowel_i_velum_mean_flow_tangent_config[key]['run'] for key in ('first', 'repeat'))]
          if fixed_vowel_i_velum_mean_flow_tangent_config else ()),
        *([fixed_vowel_i_velum_oral_nasal_loss_config['previous_run'],
           *(fixed_vowel_i_velum_oral_nasal_loss_config[key]['run'] for key in ('initial', 'first', 'repeat'))]
          if fixed_vowel_i_velum_oral_nasal_loss_config else ()),
        *([fixed_vowel_i_velum_supraglottal_loss_config['previous_run'],
           *(fixed_vowel_i_velum_supraglottal_loss_config[key]['run'] for key in ('first', 'repeat'))]
          if fixed_vowel_i_velum_supraglottal_loss_config else ()),
        *([fixed_vowel_i_pharynx_mean_flow_tangent_config['previous_run'],
           *(fixed_vowel_i_pharynx_mean_flow_tangent_config[key]['run'] for key in ('first', 'repeat'))]
          if fixed_vowel_i_pharynx_mean_flow_tangent_config else ()),
        *([fixed_vowel_i_pharynx_harmonic_pairs_config['previous_run'],
           *(fixed_vowel_i_pharynx_harmonic_pairs_config[key]['run'] for key in ('first', 'repeat'))]
          if fixed_vowel_i_pharynx_harmonic_pairs_config else ()),
        *([fixed_vowel_i_pharynx_harmonic_pairs_low_pressure_config['previous_run'],
           *(fixed_vowel_i_pharynx_harmonic_pairs_low_pressure_config[key]['run'] for key in ('first', 'repeat'))]
          if fixed_vowel_i_pharynx_harmonic_pairs_low_pressure_config else ()),
        *([fixed_vowel_i_pharynx_reversal_low_harmonics_config['previous_run'],
           *(fixed_vowel_i_pharynx_reversal_low_harmonics_config[key]['run'] for key in ('initial', 'first', 'repeat'))]
          if fixed_vowel_i_pharynx_reversal_low_harmonics_config else ()),
        *([fixed_vowel_i_pharynx_from_glottal_flow_config['previous_run'],
           *(fixed_vowel_i_pharynx_from_glottal_flow_config[key]['run'] for key in ('first', 'repeat'))]
          if fixed_vowel_i_pharynx_from_glottal_flow_config else ()),
        *([fixed_vowel_i_pharynx_steady_flow_config['previous_run'],
           *(fixed_vowel_i_pharynx_steady_flow_config[key]['run'] for key in ('first', 'repeat'))]
          if fixed_vowel_i_pharynx_steady_flow_config else ()),
        *([fixed_vowel_i_pharynx_averaged_loss_config['previous_run'],
           *(fixed_vowel_i_pharynx_averaged_loss_config[key]['run'] for key in ('first', 'repeat'))]
          if fixed_vowel_i_pharynx_averaged_loss_config else ()),
        *([fixed_vowel_i_pharynx_predicted_radiation_config['previous_run'],
           *(fixed_vowel_i_pharynx_predicted_radiation_config[key]['run'] for key in ('first', 'repeat'))]
          if fixed_vowel_i_pharynx_predicted_radiation_config else ()),
        *([fixed_vowel_i_velum_port_bandwidth_config['previous_run'],
           *(fixed_vowel_i_velum_port_bandwidth_config[key]['run'] for key in ('first', 'repeat'))]
          if fixed_vowel_i_velum_port_bandwidth_config else ()),
        *([fixed_vowel_i_velum_port_middle_harmonics_config['previous_run'],
           *(fixed_vowel_i_velum_port_middle_harmonics_config[key]['run'] for key in ('first', 'repeat'))]
          if fixed_vowel_i_velum_port_middle_harmonics_config else ()),
        *([fixed_vowel_i_velum_port_loss_feedback_config['previous_run'],
           *(fixed_vowel_i_velum_port_loss_feedback_config[key]['run'] for key in ('first', 'repeat'))]
          if fixed_vowel_i_velum_port_loss_feedback_config else ()),
        *([fixed_vowel_i_velum_port_loss_sensitivity_config['previous_run'],
           *(fixed_vowel_i_velum_port_loss_sensitivity_config[key]['run'] for key in ('first', 'repeat'))]
          if fixed_vowel_i_velum_port_loss_sensitivity_config else ()),
        *([fixed_vowel_i_velum_port_complex_pair_config['previous_run'],
           *(fixed_vowel_i_velum_port_complex_pair_config[key]['run'] for key in ('first', 'repeat'))]
          if fixed_vowel_i_velum_port_complex_pair_config else ()),
        *([fixed_vowel_i_velum_port_selected_pair_feedback_config['previous_run'],
           *(fixed_vowel_i_velum_port_selected_pair_feedback_config[key]['run'] for key in ('first', 'repeat'))]
          if fixed_vowel_i_velum_port_selected_pair_feedback_config else ()),
        *([fixed_vowel_i_velum_narrow_port_feedback_config['previous_run'],
           *(fixed_vowel_i_velum_narrow_port_feedback_config[key]['run'] for key in ('first', 'repeat'))]
          if fixed_vowel_i_velum_narrow_port_feedback_config else ()),
        *([fixed_vowel_i_velum_narrow_port_bandwidth_config['previous_run'],
           *(fixed_vowel_i_velum_narrow_port_bandwidth_config[key]['run'] for key in ('first', 'repeat'))]
          if fixed_vowel_i_velum_narrow_port_bandwidth_config else ()),
        *([fixed_vowel_i_velum_narrow_port_all_harmonic_feedback_config['previous_run'],
           *(fixed_vowel_i_velum_narrow_port_all_harmonic_feedback_config[key]['run'] for key in ('first', 'repeat'))]
          if fixed_vowel_i_velum_narrow_port_all_harmonic_feedback_config else ()),
        *([upper_harmonics_config['previous_run'],
           *(upper_harmonics_config[key]['run'] for key in ('first', 'repeat'))] if upper_harmonics_config else ()),
        *([wide_upper_harmonics_config['previous_run'],
           *(wide_upper_harmonics_config[key]['run'] for key in ('first', 'repeat'))] if wide_upper_harmonics_config else ()),
    ]))
    inputs = [
        Path(__file__).resolve(), CASE_PATH, PLAN_PATH,
        WORKSPACE / 'tools/audit_plan_evidence.py', WORKSPACE / 'tools/measure_uniform_tube.py',
        WORKSPACE / 'tools/upstream_baseline.py',
        *(RUNS / name / filename for name in run_ids for filename in ('manifest.json', 'summary.json')
          if filename == 'manifest.json' or (RUNS / name / filename).is_file()),
        *(RUNS / name / 'artifacts' / filename for name in TUBE_RUNS for filename in ('settings.json', 'trace.csv')),
    ]
    web_inputs = web_sources()
    if memory_config:
        current = RUNS / memory_config['current_48000'] / 'artifacts'
        inputs.extend(RUNS / browser / 'artifacts/browser.json' for _, browser in case['output_rates'].values())
        inputs.extend(current / name for name in ('browser.json', 'browser-run.json', 'vocal_wasm.wasm'))
    if release_config:
        source = saved_case(release_config['output_run'])
        inputs.extend(release_pcm_inputs(release_config, source['blocks']))
        inputs.append(WORKSPACE / 'tools/measure_wasm_fixed.py')
    if bandwidth_config:
        inputs.extend(open_o_bandwidth_inputs(bandwidth_config))
    if lpc_config:
        inputs.extend(open_o_lpc_inputs(lpc_config))
    if order_config:
        inputs.extend(open_o_order_inputs(order_config))
    if lf_budget_config:
        inputs.extend(lf_radiation_inputs(lf_budget_config))
    if lf_harmonic_config:
        inputs.extend(lf_transfer_inputs(lf_harmonic_config))
    if discrete_alpha_config:
        inputs.extend(discrete_alpha_inputs(discrete_alpha_config))
    if mean_alpha_config:
        inputs.extend(mean_alpha_inputs(mean_alpha_config))
    if periodic_alpha_config:
        inputs.extend(periodic_alpha_inputs(periodic_alpha_config))
    if branch_alpha_config:
        inputs.extend(branch_alpha_inputs(branch_alpha_config))
    if tangent_alpha_config:
        inputs.extend(tangent_alpha_inputs(tangent_alpha_config))
    if passive_alpha_config:
        inputs.extend(alpha_loss_intervention_inputs(passive_alpha_config, passive_alpha))
    if high_flow_alpha_config:
        inputs.extend(alpha_loss_intervention_inputs(high_flow_alpha_config, high_flow_alpha))
    if low_flow_alpha_config:
        inputs.extend(alpha_loss_intervention_inputs(low_flow_alpha_config, low_flow_alpha))
    if lf_fundamental_config:
        inputs.extend(lf_fundamental_inputs(lf_fundamental_config))
    if lf_fundamental_branches_config:
        inputs.extend(lf_fundamental_branches_inputs(lf_fundamental_branches_config))
    if lf_fundamental_amplitude_config:
        inputs.extend(lf_fundamental_amplitude_inputs(lf_fundamental_amplitude_config))
    if lf_fundamental_amplitude_branches_config:
        inputs.extend(archived_measurement_inputs(lf_fundamental_amplitude_branches_config, lf_fundamental_amplitude_branches))
    if lf_fundamental_smoothed_config:
        inputs.extend(alpha_loss_intervention_inputs(lf_fundamental_smoothed_config, lf_fundamental_smoothed))
    if lf_fundamental_smoothed_width_30_config:
        inputs.extend(alpha_loss_intervention_inputs(lf_fundamental_smoothed_width_30_config, lf_fundamental_smoothed))
    if fixed_vowel_i_lf_config:
        inputs.extend(archived_measurement_inputs(fixed_vowel_i_lf_config, fixed_vowel_i_lf))
    if fixed_vowel_i_lf_smoothing_config:
        inputs.extend(alpha_loss_intervention_inputs(fixed_vowel_i_lf_smoothing_config, lf_fundamental_smoothed))
    if fixed_vowel_i_coupled_config:
        inputs.extend(archived_measurement_inputs(fixed_vowel_i_coupled_config, fixed_vowel_i_coupled))
    if fixed_vowel_i_low_pressure_config:
        inputs.extend(archived_measurement_inputs(
            fixed_vowel_i_low_pressure_config, fixed_vowel_i_coupled, fixed_vowel_i_coupled.GATE_EVIDENCE))
    if fixed_vowel_i_pressure_replay_config:
        inputs.extend(archived_measurement_inputs(
            fixed_vowel_i_pressure_replay_config, fixed_vowel_i_coupled, fixed_vowel_i_coupled.REPLAY_EVIDENCE))
    if fixed_vowel_i_radiation_config:
        inputs.extend(archived_measurement_inputs(fixed_vowel_i_radiation_config, fixed_vowel_i_radiation))
    if fixed_vowel_i_cli_radiation_config:
        inputs.extend(archived_measurement_inputs(fixed_vowel_i_cli_radiation_config, fixed_vowel_i_cli_radiation))
    if fixed_vowel_i_wasm_radiation_config:
        module = fixed_vowel_i_wasm_radiation
        inputs.extend(archived_measurement_inputs(
            fixed_vowel_i_wasm_radiation_config, module, (*module.EVIDENCE, 'native-abi-test.log')))
    if fixed_vowel_i_radiation_screen_config:
        inputs.extend(archived_measurement_inputs(fixed_vowel_i_radiation_screen_config, fixed_vowel_i_radiation_screen))
    if fixed_vowel_i_velum_radiation_config:
        inputs.extend(archived_measurement_inputs(fixed_vowel_i_velum_radiation_config, fixed_vowel_i_velum_radiation))
    if fixed_vowel_i_velum_port_only_config:
        inputs.extend(archived_measurement_inputs(fixed_vowel_i_velum_port_only_config, fixed_vowel_i_velum_port_only))
    if fixed_vowel_i_velum_harmonic_transfer_config:
        inputs.extend(archived_measurement_inputs(
            fixed_vowel_i_velum_harmonic_transfer_config, fixed_vowel_i_velum_harmonic_transfer))
    if fixed_vowel_i_velum_mean_flow_tangent_config:
        inputs.extend(archived_measurement_inputs(
            fixed_vowel_i_velum_mean_flow_tangent_config, fixed_vowel_i_velum_mean_flow_tangent))
    if fixed_vowel_i_velum_oral_nasal_loss_config:
        inputs.extend(archived_measurement_inputs(
            fixed_vowel_i_velum_oral_nasal_loss_config, fixed_vowel_i_velum_oral_nasal_loss))
    if fixed_vowel_i_velum_supraglottal_loss_config:
        inputs.extend(archived_measurement_inputs(
            fixed_vowel_i_velum_supraglottal_loss_config, fixed_vowel_i_velum_supraglottal_loss))
    if fixed_vowel_i_pharynx_mean_flow_tangent_config:
        inputs.extend(archived_measurement_inputs(
            fixed_vowel_i_pharynx_mean_flow_tangent_config, fixed_vowel_i_pharynx_mean_flow_tangent))
    if fixed_vowel_i_pharynx_harmonic_pairs_config:
        inputs.extend(archived_measurement_inputs(
            fixed_vowel_i_pharynx_harmonic_pairs_config, fixed_vowel_i_pharynx_harmonic_pairs))
    if fixed_vowel_i_pharynx_harmonic_pairs_low_pressure_config:
        inputs.extend(archived_measurement_inputs(
            fixed_vowel_i_pharynx_harmonic_pairs_low_pressure_config, fixed_vowel_i_pharynx_harmonic_pairs_low_pressure))
    if fixed_vowel_i_pharynx_reversal_low_harmonics_config:
        inputs.extend(archived_measurement_inputs(
            fixed_vowel_i_pharynx_reversal_low_harmonics_config, fixed_vowel_i_pharynx_reversal_low_harmonics))
    if fixed_vowel_i_pharynx_from_glottal_flow_config:
        inputs.extend(archived_measurement_inputs(
            fixed_vowel_i_pharynx_from_glottal_flow_config, fixed_vowel_i_pharynx_from_glottal_flow))
    if fixed_vowel_i_pharynx_steady_flow_config:
        inputs.extend(archived_measurement_inputs(
            fixed_vowel_i_pharynx_steady_flow_config, fixed_vowel_i_pharynx_steady_flow))
    if fixed_vowel_i_pharynx_averaged_loss_config:
        inputs.extend(archived_measurement_inputs(
            fixed_vowel_i_pharynx_averaged_loss_config, fixed_vowel_i_pharynx_averaged_loss))
    if fixed_vowel_i_pharynx_predicted_radiation_config:
        inputs.extend(archived_measurement_inputs(
            fixed_vowel_i_pharynx_predicted_radiation_config, fixed_vowel_i_pharynx_predicted_radiation))
    if fixed_vowel_i_velum_port_bandwidth_config:
        inputs.extend(archived_measurement_inputs(
            fixed_vowel_i_velum_port_bandwidth_config, fixed_vowel_i_velum_port_bandwidth))
    if fixed_vowel_i_velum_port_middle_harmonics_config:
        inputs.extend(archived_measurement_inputs(
            fixed_vowel_i_velum_port_middle_harmonics_config, fixed_vowel_i_velum_port_middle_harmonics))
    if fixed_vowel_i_velum_port_loss_feedback_config:
        inputs.extend(archived_measurement_inputs(
            fixed_vowel_i_velum_port_loss_feedback_config, fixed_vowel_i_velum_port_loss_feedback))
    if fixed_vowel_i_velum_port_loss_sensitivity_config:
        inputs.extend(archived_measurement_inputs(
            fixed_vowel_i_velum_port_loss_sensitivity_config, fixed_vowel_i_velum_port_loss_sensitivity))
    if fixed_vowel_i_velum_port_complex_pair_config:
        inputs.extend(archived_measurement_inputs(
            fixed_vowel_i_velum_port_complex_pair_config, fixed_vowel_i_velum_port_complex_pair))
    if fixed_vowel_i_velum_port_selected_pair_feedback_config:
        inputs.extend(archived_measurement_inputs(
            fixed_vowel_i_velum_port_selected_pair_feedback_config, fixed_vowel_i_velum_port_selected_pair_feedback))
    if fixed_vowel_i_velum_narrow_port_feedback_config:
        inputs.extend(archived_measurement_inputs(
            fixed_vowel_i_velum_narrow_port_feedback_config, fixed_vowel_i_velum_narrow_port_feedback))
    if fixed_vowel_i_velum_narrow_port_bandwidth_config:
        inputs.extend(archived_measurement_inputs(
            fixed_vowel_i_velum_narrow_port_bandwidth_config, fixed_vowel_i_velum_narrow_port_bandwidth))
    if fixed_vowel_i_velum_narrow_port_all_harmonic_feedback_config:
        inputs.extend(archived_measurement_inputs(
            fixed_vowel_i_velum_narrow_port_all_harmonic_feedback_config, fixed_vowel_i_velum_narrow_port_all_harmonic_feedback))
    if upper_harmonics_config:
        inputs.extend(archived_measurement_inputs(upper_harmonics_config, fixed_vowel_i_velum_narrow_port_upper_harmonics))
    if wide_upper_harmonics_config:
        inputs.extend(archived_measurement_inputs(wide_upper_harmonics_config, fixed_vowel_i_velum_wide_port_upper_harmonics))
    if stage7_run is not None:
        inputs.extend([*primary_inputs, *(WORKSPACE / f'tools/{name}.py' for name in (
            'audit_stage7_evidence', 'audit_stage7_listening_runs', 'audit_stage7_f2_annotations',
            'audit_stage7_physical_midi'))])
    inputs.extend([*candidate_sources(), *web_inputs,
                   WORKSPACE / 'tools/measure_worklet_live_tsp_rate.py',
                   WORKSPACE / 'tools/measure_worklet_fixed.py'])
    details = {'case_id': case['id'], 'revision': case['revision'], 'upstream_revision': case['upstream_revision'],
               'invoked_from': str(Path.cwd()), **({'stage7_run': stage7_run} if stage7_run is not None else {})}
    return record_measurement(args.run_id, CASE_PATH, inputs, details,
                              lambda out, execute: verify(case, vowel_result, run_ids, out, execute, web_inputs, stage7_run),
                              command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
