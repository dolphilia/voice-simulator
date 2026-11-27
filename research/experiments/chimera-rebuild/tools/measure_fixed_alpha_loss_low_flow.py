"""定常点以下の順流を変え、高流量側の効果との加算性を測る。"""

import argparse
from pathlib import Path
import re
import subprocess

import numpy as np

import measure_fixed_alpha_loss_high_flow as high
from measure_fan_crossing_allocations import run_manifest, verified_path
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/fixed-alpha-loss-low-flow.json'
TANGENT = high.TANGENT
LOSSES = high.LOSSES
READ = high.READ
EVIDENCE = high.EVIDENCE
INTERVENTIONS = ('low_flow', 'high_flow', 'passive')


def archive_inputs(study):
    spec = study['reference']
    run, header = record = run_manifest(spec['run'], spec['case'], study['upstream_revision'])
    manifest = run / 'manifest.json'
    if header['status'] != 'pass' or sha256(manifest) != spec['sha256']:
        raise ValueError('高流量側の保存実行が登録値と一致しません')
    row, = [item for item in header['inputs'] if item['path'].endswith(f'/cases/{spec["case"]}.json')]
    definition = run / header['source_snapshot'] / row['path']
    if sha256(definition) != row['sha256']:
        raise ValueError('高流量側の保存ケースのハッシュが一致しません')
    return {**high.archive_inputs(READ(definition)),
            'high-flow-manifest.json': manifest, 'high-flow-case.json': definition,
            'high-flow-summary.json': verified_path(record, 'summary.json'),
            'high-flow-traces.npz': verified_path(record, 'artifacts/tangent-observations.npz')}


def interaction(values):
    return (values['passive'] - values['high_flow']) - (values['low_flow'] - values['baseline'])


def complex_responses(cfg, states, stimulus, model, selected):
    nodes, _, inlet, _, compliance, active, connected, _, linear = model
    fs = cfg['internal_rate_hz']
    frequencies = cfg['frequencies_hz']
    phase = np.exp(-2j * np.pi / fs * np.outer(frequencies, np.arange(len(stimulus))))
    excitation = phase @ stimulus
    lip = {name: (phase @ data[1:, high.passive.LIP]) / excitation for name, data in states.items()}
    remainders = {}
    for name, data in states.items():
        _, _, affine, forces = high.branch_forces(cfg, data, model, selected)
        if name == 'baseline':
            fixed_flow = forces
        remainders[name] = forces[name] - affine
    low_effect = remainders['low_flow'] - remainders['baseline']
    pressure_interaction = interaction(remainders)
    forcing = {
        'low_effect': low_effect,
        'fixed_flow_low_effect': fixed_flow['low_flow'] - fixed_flow['baseline'],
        'selected_interaction': np.where(selected, pressure_interaction, 0),
        'unselected_interaction': np.where(~selected, pressure_interaction, 0),
    }
    drives = {name: (phase @ force) / excitation[:, None] for name, force in forcing.items()}
    pair = LOSSES.IMPULSE.harmonic.pair
    rows = []
    for i, frequency in enumerate(frequencies):
        values = {name: value[i] for name, value in lip.items()}
        reconstructed = {}
        for name, drive in drives.items():
            response, _, _ = LOSSES.responses(
                frequency, fs, nodes, linear, compliance, active, connected, inlet, drive[i])
            reconstructed[name] = response[1:].sum()
        baseline = values['baseline']
        linear_lip = response[0]
        residual = baseline - linear_lip
        effects = {name: values[name] - baseline for name in INTERVENTIONS}
        measured = interaction(values)
        joint_scale = max(abs(effects['passive']), np.finfo(float).eps * abs(baseline))
        low_scale = max(abs(effects['low_flow']), np.finfo(float).eps * abs(baseline))
        predicted = reconstructed['selected_interaction'] + reconstructed['unselected_interaction']
        projection = {name: float(-(effect * residual.conjugate()).real / abs(residual)**2)
                      for name, effect in effects.items()}
        rows.append({
            'frequency_hz': frequency, 'linear_transfer': pair(linear_lip),
            'transfers': {name: pair(value) for name, value in values.items()},
            'effects_vs_baseline': {name: pair(value) for name, value in effects.items()},
            'projected_original_difference_removed': projection,
            'interaction': pair(measured),
            'interaction_relative_to_joint_change': float(abs(measured) / joint_scale),
            'interaction_reconstruction_error_relative_to_joint_change': float(abs(measured - predicted) / joint_scale),
            'low_effect_reconstruction_error_relative_to_low_effect': float(
                abs(effects['low_flow'] - reconstructed['low_effect']) / low_scale),
            'fixed_flow_prediction_error_relative_to_low_effect': float(
                abs(effects['low_flow'] - reconstructed['fixed_flow_low_effect']) / low_scale),
            'pressure_components': {name: pair(value) for name, value in reconstructed.items()},
        })
    return rows, float(abs(interaction(fixed_flow)).max())


def analyze(study, archive, out):
    cfg = study['measurement']
    reference = READ(archive['high-flow-case.json'])['measurement']
    high_summary = READ(archive['high-flow-summary.json'])
    model, indices, selections, fields = TANGENT.measurement_model(cfg, archive, READ(archive['summary.json']))
    hashes = READ(out / 'trace-hashes.json')
    early_n = cfg['early_window_samples'][1] - cfg['early_window_samples'][0]
    relative = cfg['series_peak_relative_error_lt']
    checks = {
        'same_measurement_as_high_flow': all(cfg[key] == value for key, value in reference.items()),
        'dc_control_is_registered': READ(out / 'dc.json') == TANGENT.dc_case(study, archive),
    }
    dc, conditions = {}, {}
    with (
        np.load(out / 'tangent-observations.npz', allow_pickle=False) as current,
        np.load(archive['high-flow-traces.npz'], allow_pickle=False) as higher,
        np.load(archive['passive-traces.npz'], allow_pickle=False) as both,
        np.load(archive['artifacts/branch-states.npz'], allow_pickle=False) as original,
    ):
        archives = {'high_flow': higher, 'passive': both}
        for edition in TANGENT.EDITIONS:
            key = f'dc_three_branches_{edition}'
            controls = {'baseline': current[f'dc_baseline_{edition}'], **{k: v[key] for k, v in archives.items()}}
            dc[edition] = {k: TANGENT.dc_stationarity(cfg, fields, v, current[key]) for k, v in controls.items()}
            checks[f'dc/{edition}/stationary_in_all_controls'] = all(
                row['relative_error_at_stationary_scales'] < cfg['dc_stationarity_peak_relative_error_lt']
                for row in dc[edition].values())
        for arm in TANGENT.ARMS:
            drive = READ(archive[f'artifacts/{arm}.json'])
            stimulus = np.array([float(x) for x in drive['fixed_airway_periodic_flow']['flow_cm3_s']])
            checks[f'{arm}/using_registered_stimulus'] = (
                len(stimulus) == cfg['steady_window_samples'][1] - cfg['steady_window_samples'][0]
                and abs(float(stimulus.mean()) - cfg['reference_flow_cm3_s']) < cfg['input_mean_error_lt_cm3_s']
                and drive['fixed_airway']['sample_rate_hz'] == cfg['internal_rate_hz']
                and drive['fixed_airway_periodic_flow']['start_sample'] == cfg['activation_sample'])
            for edition in TANGENT.EDITIONS:
                key = f'{arm}_baseline_{edition}'
                checks[f'{arm}/{edition}/baseline_matches_archives'] = (
                    hashes[key] == LOSSES.MEAN.sha_array(original[f'{arm}_{edition}'])
                    and all(np.array_equal(current[key].view(np.uint64), traces[key].view(np.uint64))
                            for traces in archives.values()))
            conditions[arm] = {}
            for variant in TANGENT.VARIANTS[1:]:
                prefix = f'{arm}/{variant}'
                raw = {edition: current[f'{arm}_{variant}_{edition}'] for edition in TANGENT.EDITIONS}
                compare = TANGENT.peak_error(raw['candidate'][:, indices], raw['upstream'])
                checks[f'{prefix}/matches_upstream_series'] = compare < relative
                result = {'upstream_series_peak_relative_error': compare}
                for edition in TANGENT.EDITIONS:
                    key = f'{prefix}/{edition}'
                    trace_key = f'{arm}_{variant}_{edition}'
                    order = indices if edition == 'candidate' else slice(None)
                    baseline = original[f'{arm}_{edition}'][:, order]
                    states = {'baseline': baseline, 'low_flow': raw[edition][early_n:, order],
                              **{k: v[trace_key][early_n:, order] for k, v in archives.items()}}
                    early = {'baseline': current[f'{arm}_baseline_{edition}'][:, order],
                             'low_flow': raw[edition][:early_n, order],
                             **{k: v[trace_key][:early_n, order] for k, v in archives.items()}}
                    checks[f'{key}/same_finite_states_and_windows'] = (
                        all(np.array_equal(data[0].view(np.uint64), early['baseline'][0].view(np.uint64))
                            and data.shape == early['baseline'].shape and np.isfinite(data).all()
                            for data in early.values())
                        and all(data.shape == (len(stimulus) + 1, len(fields)) and np.isfinite(data).all()
                                for data in states.values()))
                    selected = selections[variant]
                    rows, fixed_flow_gap = complex_responses(cfg, states, stimulus, model, selected)
                    windows = {name: high.law_observations(cfg, data['low_flow'], model, selected, law='low_flow')
                               for name, data in (('early', early), ('steady', states))}
                    checks[f'{key}/pressure_law_matches_in_both_windows'] = all(
                        row['pressure_law_peak_relative_error'] < cfg['branch_pressure_law_peak_relative_error_lt']
                        for row in windows.values())
                    checks[f'{key}/no_negative_work_in_either_window'] = all(
                        row['negative_work_samples'] == 0 for row in windows.values())
                    checks[f'{key}/selected_branches_cross_q0'] = all(
                        counts['above_q0'] > 0 and counts['forward_at_or_below_q0'] > 0
                        for counts in windows['steady']['flow_branches_samples'])
                    checks[f'{key}/local_laws_add_at_identical_flow'] = fixed_flow_gap == 0.0
                    checks[f'{key}/low_effect_and_interaction_reconstructed'] = all(
                        row['low_effect_reconstruction_error_relative_to_low_effect']
                        < cfg['complex_change_reconstruction_error_lt']
                        and row['interaction_reconstruction_error_relative_to_joint_change']
                        < cfg['interaction_reconstruction_error_relative_to_joint_change_lt'] for row in rows)
                    saved = high_summary['conditions'][arm][variant][edition]['frequencies']
                    checks[f'{key}/prior_transfers_reproduced'] = all(
                        prior['transfers'] == {name: row['transfers'][name] for name in prior['transfers']}
                        for row, prior in zip(rows, saved, strict=True))
                    scale = abs(baseline).max(axis=0)
                    gap = interaction(early)
                    result[edition] = {
                        'frequencies': rows, 'windows': windows,
                        'first_low_flow_response': TANGENT.first_response(
                            cfg, early['baseline'], early['low_flow'], scale, fields),
                        'first_interaction': TANGENT.first_response(cfg, np.zeros_like(gap), gap, scale, fields),
                        'fixed_flow_interaction_peak_dyn_cm2': fixed_flow_gap,
                        'hypothesis_small_interaction': all(row['interaction_relative_to_joint_change']
                            < cfg['hypothesis_interaction_relative_to_joint_change_lt'] for row in rows),
                    }
                conditions[arm][variant] = result
    return {'checks': {name: bool(value) for name, value in checks.items()}, 'conditions': conditions, 'dc_changes': dc}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', args.run_id):
        parser.error('英数字で始まる実行IDを指定してください')
    study = READ(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != study['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    archive = archive_inputs(study)

    def measure(out, execute):
        TANGENT.capture(study, archive, out, execute, law='low_flow')
        return analyze(study, archive, out)

    inputs = [CASE, Path(__file__), *archive.values(), *LOSSES.MEAN.shared.candidate_sources(),
              *TANGENT.CANDIDATE_DATA, TANGENT.PROBE,
              *(Path(module.__file__) for module in (
                  high, high.passive, TANGENT, LOSSES, LOSSES.IMPULSE, LOSSES.MEAN, LOSSES.MEAN.shared)),
              UPSTREAM / TANGENT.UPPER, UPSTREAM / 'Cargo.lock', UPSTREAM / 'crates/chimera/tests/airway_adversarial.rs']
    details = {'case_id': study['id'], 'case_revision': study['revision'], 'upstream_revision': revision,
               'invoked_from': str(Path.cwd())}
    return LOSSES.MEAN.shared.record_measurement(args.run_id, CASE, inputs, details, measure, command=None,
                                                input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
