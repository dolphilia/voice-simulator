"""定常点より大きい順流でだけ接線を使い、固定 /ɑ/ の口端応答を比較する。"""

import argparse
from pathlib import Path
import re
import subprocess

import numpy as np

import measure_fixed_alpha_loss_passive as passive
from measure_fan_crossing_allocations import run_manifest, verified_path
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/fixed-alpha-loss-high-flow.json'
TANGENT = passive.tangent
LOSSES = passive.LOSSES
READ = passive.READ
EVIDENCE = passive.EVIDENCE
CONTROLS = ('baseline', 'passive')


def archive_inputs(study):
    spec = study['reference']
    run, header = record = run_manifest(spec['run'], spec['case'], study['upstream_revision'])
    manifest = run / 'manifest.json'
    if header['status'] != 'pass' or sha256(manifest) != spec['sha256']:
        raise ValueError('受動化実験の保存実行が登録値と一致しません')
    row, = [item for item in header['inputs'] if item['path'].endswith(f'/cases/{spec["case"]}.json')]
    definition = run / header['source_snapshot'] / row['path']
    if sha256(definition) != row['sha256']:
        raise ValueError('受動化実験の保存ケースのハッシュが一致しません')
    sources = passive.archive_inputs(READ(definition))
    names = ('summary.json', 'artifacts/branch-states.npz', 'upstream-geometry.csv',
             *(f'artifacts/{arm}.json' for arm in TANGENT.ARMS), *LOSSES.IMPULSE.harmonic.NETWORK_FILES)
    return {**{name: sources[name] for name in names},
            'passive-manifest.json': manifest, 'passive-case.json': definition,
            'passive-summary.json': verified_path(record, 'summary.json'),
            'passive-traces.npz': verified_path(record, 'artifacts/tangent-observations.npz')}


def branch_forces(cfg, states, model, selected):
    nodes, topology, _, geometry, _, _, connected, main, _ = model
    q0 = cfg['reference_flow_cm3_s']
    flow, observed, quadratic, affine = TANGENT.kinetic_terms(
        states, nodes, topology[connected], connected, geometry, cfg['internal_rate_hz'], main * q0)
    return flow, observed, affine, {
        'baseline': quadratic,
        'passive': np.where(selected & (flow >= 0), np.maximum(affine, 0), quadratic),
        'high_flow': np.where(selected & (flow > q0), affine, quadratic),
        'low_flow': np.where(selected & (flow >= 0) & (flow <= q0), np.maximum(affine, 0), quadratic),
    }


def law_observations(cfg, states, model, selected, *, law='high_flow'):
    flow, observed, _, forces = branch_forces(cfg, states, model, selected)
    expected = forces[law][:, selected]
    work = (flow * observed)[:, selected]
    peak = float(abs(work).max())
    q0 = cfg['reference_flow_cm3_s']
    return {
        'pressure_law_peak_relative_error': float(abs(observed[:, selected] - expected).max() / abs(expected).max()),
        'negative_work_samples': int((work < -cfg['work_rate_negative_tolerance_relative_to_peak'] * peak).sum()),
        'minimum_work_erg_s': float(work.min()),
        'peak_absolute_work_erg_s': peak,
        'mean_work_erg_s': float(work.mean()),
        'flow_branches_samples': [
            {'reverse': int((u < 0).sum()), 'forward_at_or_below_q0': int(((0 <= u) & (u <= q0)).sum()),
             'above_q0': int((u > q0).sum())}
            for u in flow[:, selected].T],
    }


def complex_contrasts(cfg, states, stimulus, model, selected):
    nodes, _, inlet, _, compliance, active, connected, _, linear = model
    fs = cfg['internal_rate_hz']
    frequencies = cfg['frequencies_hz']
    phase = np.exp(-2j * np.pi / fs * np.outer(frequencies, np.arange(len(stimulus))))
    excitation = phase @ stimulus
    lip = {name: (phase @ data[1:, passive.LIP]) / excitation for name, data in states.items()}
    _, _, new_affine, new_forces = branch_forces(cfg, states['high_flow'], model, selected)
    new_remainder = new_forces['high_flow'] - new_affine
    drives = {}
    for control in CONTROLS:
        _, _, old_affine, old_forces = branch_forces(cfg, states[control], model, selected)
        direct = old_forces['high_flow'] - old_forces[control]
        # 節点方程式が持つ増分抵抗の寄与を除き、残差の差分を与える。
        total = new_remainder - (old_forces[control] - old_affine)
        terms = (direct, np.where(selected, total - direct, 0), np.where(~selected, total, 0))
        drives[control] = {name: (phase @ term) / excitation[:, None]
                           for name, term in zip(passive.NAMES, terms, strict=True)}
    pair = LOSSES.IMPULSE.harmonic.pair
    rows = []
    for i, frequency in enumerate(frequencies):
        def response(force):
            values, _, _ = LOSSES.responses(
                frequency, fs, nodes, linear, compliance, active, connected, inlet, force)
            return values

        linear_lip = response(np.zeros(len(connected)))[0]
        observed = {name: values[i] for name, values in lip.items()}
        residual = observed['baseline'] - linear_lip
        contrasts = {}
        for control in CONTROLS:
            measured = observed['high_flow'] - observed[control]
            components = {name: response(force[i])[1:].sum() for name, force in drives[control].items()}
            scale = max(abs(measured), np.finfo(float).eps * abs(observed['baseline']))
            contrasts[control] = {
                'high_flow_minus_control': pair(measured),
                'relative_to_original_residual': float(abs(measured) / abs(residual)),
                'closure_relative_error': float(abs(measured - sum(components.values())) / scale),
                'direct_only_relative_error': float(abs(measured - components[passive.NAMES[0]]) / scale),
                'components': {name: pair(value) for name, value in components.items()},
            }
        rows.append({
            'frequency_hz': frequency, 'linear_transfer': pair(linear_lip),
            'transfers': {name: pair(value) for name, value in observed.items()},
            'projected_original_difference_removed': {
                name: float(((observed['baseline'] - observed[name]) * residual.conjugate()).real / abs(residual)**2)
                for name in ('passive', 'high_flow')},
            'fraction_of_original_distance_remaining': {
                name: float(abs(observed[name] - linear_lip) / abs(residual)) for name in ('passive', 'high_flow')},
            'contrasts': contrasts,
        })
    return rows


def analyze(study, archive, out):
    cfg = study['measurement']
    previous = READ(archive['passive-case.json'])['measurement']
    summary = READ(archive['passive-summary.json'])
    model, indices, selections, fields = TANGENT.measurement_model(cfg, archive, READ(archive['summary.json']))
    hashes = READ(out / 'trace-hashes.json')
    early_n = cfg['early_window_samples'][1] - cfg['early_window_samples'][0]
    relative = cfg['series_peak_relative_error_lt']
    checks = {
        'same_stimulus_clock_and_branches_as_passive': all(cfg[key] == previous[key] for key in cfg if key in previous),
        'dc_control_is_registered': READ(out / 'dc.json') == TANGENT.dc_case(study, archive),
    }
    dc, conditions = {}, {}
    with (
        np.load(out / 'tangent-observations.npz', allow_pickle=False) as current,
        np.load(archive['passive-traces.npz'], allow_pickle=False) as prior,
        np.load(archive['artifacts/branch-states.npz'], allow_pickle=False) as original,
    ):
        for edition in TANGENT.EDITIONS:
            key = f'dc_three_branches_{edition}'
            dc[edition] = {
                'baseline': TANGENT.dc_stationarity(cfg, fields, current[f'dc_baseline_{edition}'], current[key]),
                'passive': TANGENT.dc_stationarity(cfg, fields, prior[key], current[key]),
            }
            for control, data in dc[edition].items():
                checks[f'dc/{edition}/{control}_stationarity'] = (
                    data['relative_error_at_stationary_scales'] < cfg['dc_stationarity_peak_relative_error_lt'])
        for arm in TANGENT.ARMS:
            drive = READ(archive[f'artifacts/{arm}.json'])
            stimulus = np.array([float(x) for x in drive['fixed_airway_periodic_flow']['flow_cm3_s']])
            checks[f'{arm}/using_registered_stimulus'] = (
                len(stimulus) == cfg['steady_window_samples'][1] - cfg['steady_window_samples'][0]
                and abs(float(stimulus.mean()) - cfg['reference_flow_cm3_s']) < cfg['input_mean_error_lt_cm3_s']
                and drive['fixed_airway']['sample_rate_hz'] == cfg['internal_rate_hz']
                and drive['fixed_airway_periodic_flow']['start_sample'] == cfg['activation_sample'])
            conditions[arm] = {}
            for edition in TANGENT.EDITIONS:
                key = f'{arm}_baseline_{edition}'
                checks[f'{arm}/{edition}/baseline_matches_archive'] = (
                    hashes[key] == LOSSES.MEAN.sha_array(original[f'{arm}_{edition}'])
                    and np.array_equal(current[key].view(np.uint64), prior[key].view(np.uint64)))
            for variant in TANGENT.VARIANTS[1:]:
                prefix = f'{arm}/{variant}'
                raw = {edition: current[f'{arm}_{variant}_{edition}'] for edition in TANGENT.EDITIONS}
                compare = TANGENT.peak_error(raw['candidate'][:, indices], raw['upstream'])
                result = {'upstream_series_peak_relative_error': compare}
                checks[f'{prefix}/matches_upstream_series'] = compare < relative
                for edition in TANGENT.EDITIONS:
                    key = f'{prefix}/{edition}'
                    order = indices if edition == 'candidate' else slice(None)
                    base = original[f'{arm}_{edition}'][:, order]
                    early = {'baseline': current[f'{arm}_baseline_{edition}'][:, order],
                             'passive': prior[f'{arm}_{variant}_{edition}'][:early_n, order]}
                    changed = raw[edition][:, order]
                    checks[f'{key}/same_states_before_switch'] = all(
                        np.array_equal(data[0].view(np.uint64), changed[0].view(np.uint64)) for data in early.values())
                    first = {name: TANGENT.first_response(cfg, data, changed[:early_n], abs(base).max(axis=0), fields)
                             for name, data in early.items()}
                    states = {'baseline': base, 'passive': prior[f'{arm}_{variant}_{edition}'][early_n:, order],
                              'high_flow': changed[early_n:]}
                    selected = selections[variant]
                    rows = complex_contrasts(cfg, states, stimulus, model, selected)
                    windows = {'early': law_observations(cfg, changed[:early_n], model, selected),
                               'steady': law_observations(cfg, states['high_flow'], model, selected)}
                    checks[f'{key}/pressure_law_matches_in_both_windows'] = all(
                        data['pressure_law_peak_relative_error'] < cfg['branch_pressure_law_peak_relative_error_lt']
                        for data in windows.values())
                    checks[f'{key}/no_negative_work_in_either_window'] = all(
                        data['negative_work_samples'] == 0 for data in windows.values())
                    checks[f'{key}/selected_branches_cross_q0'] = all(
                        counts['above_q0'] > 0 and counts['forward_at_or_below_q0'] > 0
                        for counts in windows['steady']['flow_branches_samples'])
                    for control in CONTROLS:
                        checks[f'{key}/{control}_complex_change_reconstructed'] = all(
                            row['contrasts'][control]['closure_relative_error']
                            < cfg['complex_change_reconstruction_error_lt'] for row in rows)
                    prior_rows = summary['conditions'][arm][variant][edition]['frequencies']
                    checks[f'{key}/prior_passive_contrast_reproduced'] = all(
                        abs(row['projected_original_difference_removed']['passive']
                            - saved['projected_original_difference_removed_by_passive']) < relative
                        for row, saved in zip(rows, prior_rows, strict=True))
                    result[edition] = {'frequencies': rows, 'first_response': first, 'windows': windows,
                                       'hypothesis_closer_in_both_harmonics': all(
                                           row['fraction_of_original_distance_remaining']['high_flow'] < 1 for row in rows)}
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
        TANGENT.capture(study, archive, out, execute, law='high_flow')
        return analyze(study, archive, out)

    inputs = [CASE, Path(__file__), *archive.values(), *LOSSES.MEAN.shared.candidate_sources(),
              *TANGENT.CANDIDATE_DATA, TANGENT.PROBE,
              *(Path(module.__file__) for module in (passive, TANGENT, LOSSES, LOSSES.IMPULSE, LOSSES.MEAN, LOSSES.MEAN.shared)),
              UPSTREAM / TANGENT.UPPER, UPSTREAM / 'Cargo.lock', UPSTREAM / 'crates/chimera/tests/airway_adversarial.rs']
    details = {'case_id': study['id'], 'case_revision': study['revision'], 'upstream_revision': revision,
               'invoked_from': str(Path.cwd())}
    return LOSSES.MEAN.shared.record_measurement(args.run_id, CASE, inputs, details, measure, command=None,
                                                input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
