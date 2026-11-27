"""固定 /i/ の咽頭内の損失を平均流量の接線抵抗に置き換える。"""

import argparse
from pathlib import Path
import re
import subprocess

import numpy as np

import measure_fixed_vowel_i_velum_supraglottal_loss as supra
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/fixed-vowel-i-pharynx-mean-flow-tangent.json'
READ, COUPLED = supra.READ, supra.COUPLED
prior, tangent, harmonic, velum = supra.prior, supra.tangent, supra.harmonic, supra.velum
EVIDENCE = ()
HYPOTHESIS = 'pharynx_mean_flow_tangent_removes_half_of_nose_error'


def archive_inputs(case):
    spec = case['measurement']['reference']
    record, manifest, definition = COUPLED.smoothing.verified_reference(
        {'run': spec['run'], 'case': 'fixed-vowel-i-velum-supraglottal-loss', 'sha256': spec['manifest_sha256']},
        case['upstream_revision'])
    return {**supra.archive_inputs(READ(definition)), 'supraglottal-manifest.json': manifest,
            'supraglottal-case.json': definition, 'supraglottal-summary.json': COUPLED.verified_path(record, 'summary.json')}


def tangent_resistance(flow, coefficients):
    mean = flow.mean(axis=0)
    losses = np.where(mean >= 0., *coefficients)
    resistance = 2 * losses * abs(mean)
    step = 0.001 * abs(mean)
    left, right = mean - step, mean + step
    difference = losses * (right * abs(right) - left * abs(left))
    secant = np.divide(difference, 2 * step, out=np.zeros_like(mean), where=step > 0.)
    return mean, resistance, secant


def feedback_pressure(frequency, fs, matrix, rhs, dipoles, pharynx, added_resistance):
    """元の節点行列を使い、咽頭の圧力損失による枝流量の帰還を解く。"""
    left, right = pharynx[:, :2].astype(int).T
    inertia, resistance = pharynx[:, 3:].T
    delay = np.exp(-2j * np.pi * frequency / fs)
    impedance = resistance + inertia * fs * (1 - delay)
    unmodified, *modes = np.linalg.solve(matrix, np.column_stack((rhs, dipoles))).T
    responses = np.asarray(modes).T
    free_flow = delay * (unmodified[left] - unmodified[right]) / impedance
    identity = np.eye(len(left))
    feedback = (delay * (responses[left] - responses[right]) - identity) / impedance[:, None]
    added_pressure = np.linalg.solve(
        identity - added_resistance[:, None] * feedback, added_resistance * free_flow)
    return unmodified + responses @ added_pressure, free_flow + feedback @ added_pressure


def inspect_edition(cfg, reference, layout, tracks, state, nodes, branches, source):
    groups, selected = supra.selected_groups(layout, branches, source)
    pharynx = groups['pharynx']
    mask = np.isin(selected, pharynx)
    if int(mask.sum()) != cfg['pharynx_branch_count']:
        raise ValueError('登録した咽頭の枝数と観測の対応が一致しません')
    first, end = cfg['steady_window_internal_samples']
    frequency, fs = cfg['frequency_hz'], cfg['internal_rate_hz']
    basis = np.exp(-2j * np.pi * frequency * np.arange(end - first) / fs) / (end - first)
    drive = basis @ tracks[harmonic.GLOTTIS][1:]
    target = (basis @ tracks['nose_flow_cm3_s'][1:]) / drive
    chosen = branches[selected]
    sinus = np.isin(selected, groups['sinus'])
    coefficients = tuple(np.where(sinus, 0., values) for values in prior.branch_coefficients(layout, chosen))
    loss = prior.branch_pressure(frequency, fs, basis, state, layout, selected, branches, drive,
                                 coefficients=coefficients)['loss_per_drive']
    observed_flow = state[1:, layout['node_count'] + selected[mask]]
    mean, added_resistance, secant = tangent_resistance(observed_flow, tuple(item[mask] for item in coefficients))

    matrix, inlet, dipoles, nose = supra.forcing(frequency, fs, nodes, branches, selected, source)
    other_loss = np.where(mask, 0., loss)
    rhs = inlet + dipoles @ other_loss
    omitted = nose @ np.linalg.solve(matrix, rhs)
    replay = nose @ np.linalg.solve(matrix, inlet + dipoles @ loss)
    ideal_pharynx_effect = replay - omitted
    observed_flow_hat = (basis @ observed_flow) / drive
    fixed_flow_loss = added_resistance * observed_flow_hat
    fixed_flow_diagnostic = nose @ np.linalg.solve(matrix, rhs + dipoles[:, mask] @ fixed_flow_loss)

    adjusted = branches.copy()
    adjusted[selected[mask], 4] += added_resistance
    adjusted_matrix, adjusted_inlet, adjusted_dipoles, _ = supra.forcing(
        frequency, fs, nodes, adjusted, selected, source)
    direct = np.linalg.solve(adjusted_matrix, adjusted_inlet + adjusted_dipoles @ other_loss)
    estimated = nose @ direct
    reconstructed, returned_flow = feedback_pressure(
        frequency, fs, matrix, rhs, dipoles[:, mask], chosen[mask], added_resistance)
    left, right = chosen[mask, :2].astype(int).T
    inertia, resistance = adjusted[selected[mask], 3:].T
    delay = np.exp(-2j * np.pi * frequency / fs)
    direct_flow = delay * (direct[left] - direct[right]) / (resistance + inertia * fs * (1 - delay))

    tolerance = cfg['model_identity_relative_error_lt']
    previous_replay = complex(*reference['observed_nose_transfer']) - complex(*reference['nose_residual_after_all_losses'])
    previous_effect = complex(*reference['nose_transfer_change_by_group']['pharynx'])
    checks = {
        'tangent_resistance_matches_local_difference': bool(
            np.max(abs(added_resistance - secant)) < tolerance * np.max(abs(added_resistance))),
        'resistance_change_and_feedback_agree_on_pressure_and_flow': bool(
            np.max(abs(direct - reconstructed)) < tolerance * np.max(abs(direct))
            and np.max(abs(direct_flow - returned_flow)) < tolerance * np.max(abs(direct_flow))),
        'previous_nose_replay_and_pharynx_contribution_preserved': bool(
            abs(replay - previous_replay) < tolerance * abs(target)
            and abs(ideal_pharynx_effect - previous_effect) < tolerance * abs(previous_effect)),
    }
    responses = {'without_pharynx_loss': omitted, 'mean_flow_tangent': estimated,
                 'observed_flow_times_tangent': fixed_flow_diagnostic, 'observed_loss_replay': replay}
    pair = tangent.pair
    summary = {
        'nose_transfer': {key: pair(value) for key, value in responses.items()},
        'nose_relative_error': {key: float(abs(value - target) / abs(target)) for key, value in responses.items()},
        'nose_error_reduction_fraction': float(1 - abs(estimated - target) / abs(omitted - target)),
        'tangent_effect_relative_error': float(abs(estimated - replay) / abs(ideal_pharynx_effect)),
        'fixed_flow_effect_relative_error': float(abs(fixed_flow_diagnostic - replay) / abs(ideal_pharynx_effect)),
        'tangent_effect_projection': harmonic.projection(estimated - omitted, ideal_pharynx_effect),
        'tangent_effect_phase_error_deg': float(np.angle((estimated - omitted) / ideal_pharynx_effect, deg=True)),
        'branches': [
            {'nodes': [int(left[slot]), int(right[slot])], 'mean_flow_cm3_s': float(mean[slot]),
             'flow_rms_cm3_s': float(np.sqrt(np.mean(observed_flow[:, slot]**2))),
             'reverse_samples': int(np.count_nonzero(observed_flow[:, slot] < 0.)),
             'added_resistance_cgs': float(added_resistance[slot]),
             'observed_loss_per_drive': pair(actual),
             'tangent_loss_per_drive_using_observed_flow': pair(fixed_flow_loss[slot]),
             'tangent_loss_per_drive_using_solved_flow': pair(added_resistance[slot] * direct_flow[slot])}
            for slot, actual in enumerate(loss[mask])
        ],
    }
    return checks, summary


def analyze(case, archive):
    cfg = case['measurement']
    before = READ(archive['supraglottal-case.json'])['measurement']
    if any(cfg[field] != before[field] for field in ('internal_rate_hz', 'frequency_hz', 'steady_window_internal_samples')):
        raise ValueError('前回と同じ標本化周波数、周波数、観測窓が必要です')
    layout, recordings = supra.recorded_editions(case, archive)
    reference = READ(archive['supraglottal-summary.json'])['editions']
    checks, editions = {}, {}
    for name, values in recordings.items():
        results, editions[name] = inspect_edition(cfg, reference[name], layout, *values)
        checks.update({f'{name}/{key}': value for key, value in results.items()})
    transfers = [np.array([complex(*value) for value in edition['nose_transfer'].values()]) for edition in editions.values()]
    checks['nose_transfers_match_fixed_upstream'] = (
        harmonic.max_row_relative(transfers[0][None, :], transfers[1][None, :]) < cfg['edition_relative_error_lt'])
    decisions = [edition['nose_error_reduction_fraction'] >= cfg['minimum_nose_error_reduction_fraction']
                 for edition in editions.values()]
    checks['both_editions_agree_on_registered_prediction'] = decisions[0] == decisions[1]
    checks[HYPOTHESIS] = all(decisions)
    return {'checks': checks, 'frequency_hz': cfg['frequency_hz'], 'editions': editions}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', args.run_id):
        parser.error('英数字で始まる実行IDを指定してください')
    case = READ(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    archive = archive_inputs(case)

    def measure(out, execute):
        execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera', '--test', 'airway_adversarial',
                 'steady_flow_through_a_short_constriction_obeys_bernoulli_with_jet_loss'],
                cwd=UPSTREAM, stdout=out / 'upstream-steady-constriction.log')
        return analyze(case, archive)

    inputs = [CASE, Path(__file__), *archive.values(),
              *(Path(module.__file__) for module in (supra, prior, tangent, harmonic, velum, COUPLED, COUPLED.SHARED)),
              *(UPSTREAM / name for name in (velum.NETWORK, velum.VOICE, 'crates/chimera/src/voice/human_airway.rs',
                'crates/chimera/tests/airway_adversarial.rs', 'Cargo.lock'))]
    details = {'case_id': case['id'], 'case_revision': case['measurement']['revision'], 'upstream_revision': revision,
               'invoked_from': str(Path.cwd())}
    return COUPLED.SHARED.record_measurement(
        args.run_id, CASE, inputs, details, measure, command=None, input_root=velum.screen.ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
