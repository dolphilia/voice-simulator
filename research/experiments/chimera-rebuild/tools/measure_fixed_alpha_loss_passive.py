"""選択枝で受動な接線を再描画し、口端複素応答への寄与を測る。"""

import argparse
from pathlib import Path
import re
import subprocess

import numpy as np

import measure_fixed_alpha_loss_tangent as tangent
from measure_fan_crossing_allocations import run_manifest, verified_path
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/fixed-alpha-loss-passive.json'
READ = tangent.READ
LOSSES = tangent.losses
EVIDENCE = tangent.EVIDENCE
NAMES = ('local_law_at_previous_flow', 'selected_branch_flow_response', 'unselected_branch_flow_response')
LIP = LOSSES.TRACE.index('flow_lips')


def archive_inputs(study):
    spec = study['reference']
    run, header = record = run_manifest(spec['run'], spec['case'], study['upstream_revision'])
    manifest = run / 'manifest.json'
    if header['status'] != 'pass' or sha256(manifest) != spec['sha256']:
        raise ValueError('接線実験の保存実行が登録値と一致しません')
    row, = [item for item in header['inputs'] if item['path'].endswith(f'/cases/{spec["case"]}.json')]
    definition = run / header['source_snapshot'] / row['path']
    if sha256(definition) != row['sha256']:
        raise ValueError('接線実験の保存ケースのハッシュが一致しません')
    archived = tangent.archive_inputs(READ(definition))
    names = ['summary.json', 'artifacts/branch-states.npz', 'upstream-geometry.csv',
             *(f'artifacts/{arm}.json' for arm in tangent.ARMS), *LOSSES.IMPULSE.harmonic.NETWORK_FILES]
    return {**{name: archived[name] for name in names},
            'tangent-manifest.json': manifest, 'tangent-case.json': definition,
            'tangent-summary.json': verified_path(record, 'summary.json'),
            'tangent-traces.npz': verified_path(record, 'artifacts/tangent-observations.npz')}


def loss_law(states, cfg, model, selected, *, passive):
    nodes, topology, _, geometry, _, _, connected, main, _ = model
    flow, observed, quadratic, affine = tangent.kinetic_terms(
        states, nodes, topology[connected], connected, geometry,
        cfg['internal_rate_hz'], main * cfg['reference_flow_cm3_s'])
    passive_force = np.where(flow >= 0, np.maximum(affine, 0), quadratic)
    expected = np.where(selected, passive_force if passive else affine, quadratic)
    balance = float(abs(observed - expected).max() / abs(expected).max())
    work = (flow * observed)[:, selected]
    peak = float(abs(work).max())
    negative = work < -cfg['work_rate_negative_tolerance_relative_to_peak'] * peak
    return {'remainder': expected - affine,
            'passive_minus_affine_at_same_flow': np.where(selected, passive_force - affine, 0),
            'balance_error': balance,
            'work': {'samples': int(work.size), 'negative_samples': int(negative.sum()),
                     'minimum_erg_s': float(work.min()), 'peak_absolute_erg_s': peak,
                     'mean_erg_s': float(work.mean())}}


def complex_contrast(cfg, reference, ordinary, passive, stimulus, model, local):
    nodes, linear_source, inlet, _, compliance, active, connected, _, linear = model
    fs = cfg['internal_rate_hz']
    frequencies = cfg['frequencies_hz']
    projection = np.exp(-2j * np.pi / fs * np.outer(frequencies, np.arange(len(stimulus))))
    excitation = projection @ stimulus
    lip = [(projection @ state[1:, LIP]) / excitation for state in (reference, ordinary, passive)]
    old = loss_law(ordinary, cfg, model, local, passive=False)
    new = loss_law(passive, cfg, model, local, passive=True)
    direct = old['passive_minus_affine_at_same_flow']
    feedback = new['remainder'] - old['remainder']
    terms = (direct, np.where(local, feedback - direct, 0), np.where(~local, feedback, 0))
    drive = [projection @ term / excitation[:, None] for term in terms]
    pair = LOSSES.IMPULSE.harmonic.pair
    rows = []
    for i, f in enumerate(frequencies):
        base, unclipped, clipped = (value[i] for value in lip)
        measured = clipped - unclipped
        parts = {}
        for name, coefficients in zip(NAMES, drive, strict=True):
            transfer, _, _ = LOSSES.responses(
                f, fs, nodes, linear, compliance, active, connected, inlet, coefficients[i])
            parts[name] = transfer[1:].sum()
        linear_lip = transfer[0]
        residual = base - linear_lip
        size = abs(residual)
        denominator = max(abs(measured), np.finfo(float).eps * abs(base))
        rows.append({'frequency_hz': f, 'baseline_transfer': pair(base),
                     'linear_transfer': pair(linear_lip), 'tangent_transfer': pair(unclipped),
                     'passive_transfer': pair(clipped), 'passive_minus_tangent': pair(measured),
                     'components': {key: pair(value) for key, value in parts.items()},
                     'closure_error_relative_to_passive_minus_tangent':
                         float(abs(measured - sum(parts.values())) / denominator),
                     'passive_minus_tangent_relative_to_original_difference': float(abs(measured) / size),
                     'projected_original_difference_removed_by_tangent': float(
                         ((base - unclipped) * residual.conjugate()).real / size**2),
                     'projected_original_difference_removed_by_passive': float(
                         ((base - clipped) * residual.conjugate()).real / size**2),
                     'relative_error_of_fixed_flow_prediction': float(
                         abs(measured - parts[NAMES[0]]) / denominator)})
    return rows, old, new


def analyze(study, archive, out):
    cfg = study['measurement']
    original = READ(archive['tangent-case.json'])
    reference = READ(archive['summary.json'])
    previous_summary = READ(archive['tangent-summary.json'])
    model, indices, selections, fields = tangent.measurement_model(cfg, archive, reference)
    hashes = READ(out / 'trace-hashes.json')
    early_n = cfg['early_window_samples'][1] - cfg['early_window_samples'][0]
    prerequisites = ('internal_rate_hz', 'frequencies_hz', 'reference_flow_cm3_s', 'activation_sample',
                     'early_window_samples', 'steady_window_samples', 'dc_window_samples', 'variants')
    checks = {
        'same_stimulus_clock_and_branches_as_tangent': all(cfg[key] == original['measurement'][key] for key in prerequisites),
        'dc_control_is_registered': READ(out / 'dc.json') == tangent.dc_case(study, archive),
    }
    dc, conditions = {}, {}
    relative = cfg['series_peak_relative_error_lt']
    with (
        np.load(out / 'tangent-observations.npz', allow_pickle=False) as current,
        np.load(archive['tangent-traces.npz'], allow_pickle=False) as previous,
        np.load(archive['artifacts/branch-states.npz'], allow_pickle=False) as lost,
    ):
        for edition in tangent.EDITIONS:
            base = current[f'dc_baseline_{edition}']
            changed = current[f'dc_three_branches_{edition}']
            dc[edition] = tangent.dc_stationarity(cfg, fields, base, changed)
            checks[f'dc/{edition}/stationarity_at_tangent_point'] = (
                dc[edition]['relative_error_at_stationary_scales'] < cfg['dc_stationarity_peak_relative_error_lt'])
            checks[f'dc/{edition}/same_as_tangent'] = np.array_equal(
                changed.view(np.uint64), previous[f'dc_three_branches_{edition}'].view(np.uint64))
        for arm in tangent.ARMS:
            drive = READ(archive[f'artifacts/{arm}.json'])
            stimulus = np.array([float(x) for x in drive['fixed_airway_periodic_flow']['flow_cm3_s']])
            checks[f'{arm}/using_registered_stimulus'] = (
                len(stimulus) == cfg['steady_window_samples'][1] - cfg['steady_window_samples'][0]
                and abs(float(stimulus.mean()) - cfg['reference_flow_cm3_s']) < cfg['input_mean_error_lt_cm3_s']
                and drive['fixed_airway']['sample_rate_hz'] == cfg['internal_rate_hz']
                and drive['fixed_airway_periodic_flow']['start_sample'] == cfg['activation_sample'])
            controls = {}
            for edition in tangent.EDITIONS:
                base = lost[f'{arm}_{edition}']
                key = f'{arm}_baseline_{edition}'
                checks[f'{arm}/{edition}/baseline_matches_archived_recording'] = (
                    hashes[key] == LOSSES.MEAN.sha_array(base)
                    and np.array_equal(current[key].view(np.uint64), previous[key].view(np.uint64)))
                controls[edition] = base
            conditions[arm] = {}
            for variant in tangent.VARIANTS[1:]:
                prefix = f'{arm}/{variant}'
                result = {}
                raw = {edition: current[f'{arm}_{variant}_{edition}'] for edition in tangent.EDITIONS}
                compare = tangent.peak_error(raw['candidate'][:, indices], raw['upstream'])
                checks[f'{prefix}/matches_upstream_series'] = compare < relative
                for edition in tangent.EDITIONS:
                    key = f'{prefix}/{edition}'
                    before = previous[f'{arm}_{variant}_{edition}']
                    after = raw[edition]
                    base = controls[edition]
                    frame = before[:early_n, :]
                    first = tangent.first_response(cfg, frame, after[:early_n], abs(base).max(axis=0), fields)
                    checks[f'{key}/same_states_before_switch'] = np.array_equal(
                        frame[0].view(np.uint64), after[0].view(np.uint64))
                    checks[f'{key}/effect_observed_after_switch'] = first is not None and first['sample'] >= cfg['activation_sample']
                    order = indices if edition == 'candidate' else slice(None)
                    rows, old, new = complex_contrast(
                        cfg, base[:, order], before[early_n:, order], after[early_n:, order],
                        stimulus, model, selections[variant])
                    early = loss_law(after[:early_n, order], cfg, model, selections[variant], passive=True)
                    checks[f'{key}/pressure_law_matches_in_both_windows'] = (
                        max(new['balance_error'], early['balance_error']) < cfg['branch_pressure_law_peak_relative_error_lt'])
                    checks[f'{key}/no_negative_work_in_either_window'] = (
                        new['work']['negative_samples'] == early['work']['negative_samples'] == 0
                        and old['work']['negative_samples'] > 0)
                    checks[f'{key}/reconstructed_complex_change'] = all(
                        row['closure_error_relative_to_passive_minus_tangent'] < cfg['complex_change_reconstruction_error_lt']
                        for row in rows)
                    prior = previous_summary['conditions'][arm][variant][edition]['frequencies']
                    checks[f'{key}/prior_tangent_contrast_reproduced'] = all(
                        abs(row['projected_original_difference_removed_by_tangent'] - saved['projected_fraction_of_original_difference_removed'])
                        < relative for row, saved in zip(rows, prior, strict=True))
                    result[edition] = {'frequencies': rows, 'first_response': first,
                                       'tangent_work': old['work'], 'passive_work': new['work'],
                                       'early_passive_work': early['work'],
                                       'steady_law_peak_relative_error': new['balance_error'],
                                       'early_law_peak_relative_error': early['balance_error']}
                result['upstream_series_peak_relative_error'] = compare
                result['hypothesis_detectable'] = all(
                    row['passive_minus_tangent_relative_to_original_difference'] > cfg['observable_passivity_effect_relative_to_original_residual']
                    for row in result['candidate']['frequencies'])
                conditions[arm][variant] = result
    return {'checks': {key: bool(value) for key, value in checks.items()}, 'conditions': conditions, 'dc_changes': dc}


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
        tangent.capture(study, archive, out, execute, law='passive')
        return analyze(study, archive, out)

    inputs = [CASE, Path(__file__), *archive.values(), *LOSSES.MEAN.shared.candidate_sources(),
              *tangent.CANDIDATE_DATA, tangent.PROBE,
              *(Path(module.__file__) for module in (tangent, LOSSES, LOSSES.IMPULSE, LOSSES.MEAN, LOSSES.MEAN.shared)),
              UPSTREAM / tangent.UPPER, UPSTREAM / 'Cargo.lock', UPSTREAM / 'crates/chimera/tests/airway_adversarial.rs']
    details = {'case_id': study['id'], 'case_revision': study['revision'], 'upstream_revision': revision,
               'invoked_from': str(Path.cwd())}
    return LOSSES.MEAN.shared.record_measurement(args.run_id, CASE, inputs, details, measure, command=None,
                                                input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
