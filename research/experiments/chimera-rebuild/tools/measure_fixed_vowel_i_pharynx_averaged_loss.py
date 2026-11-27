"""予測した流量の周波数成分から平均二次損失と定常分流を求める。"""

import argparse
from pathlib import Path
import re
import subprocess

import numpy as np
from scipy.optimize import brentq

import measure_fixed_vowel_i_pharynx_steady_flow as steady
from upstream_baseline import UPSTREAM, WORKSPACE


CASE = WORKSPACE / 'cases/fixed-vowel-i-pharynx-averaged-loss.json'
READ, COUPLED = steady.READ, steady.COUPLED
inlet, supra, prior, harmonic, velum = steady.inlet, steady.supra, steady.prior, steady.harmonic, steady.velum
EVIDENCE = ()
DC_HYPOTHESIS = 'averaged_kinetic_loss_halves_steady_flow_errors'
AC_HYPOTHESIS = 'averaged_kinetic_loss_preserves_harmonics_and_reversal'


def archive_inputs(case):
    spec = case['measurement']['reference']
    record, manifest, definition = COUPLED.smoothing.verified_reference(
        {'run': spec['run'], 'case': 'fixed-vowel-i-pharynx-steady-flow', 'sha256': spec['manifest_sha256']},
        case['upstream_revision'])
    return {**steady.archive_inputs(READ(definition)), 'steady-flow-manifest.json': manifest,
            'steady-flow-case.json': definition, 'steady-flow-summary.json': COUPLED.verified_path(record, 'summary.json')}


def solve_averaged_split(paths, total, resistance, mean_loss):
    """一定の変動成分のもとで、両出口への時間平均圧力損失をそろえる。"""
    difference = paths[:, 0] - paths[:, 1]
    nasal_only = total * paths[:, 1]

    def pressure_residual(oral_flow):
        mean = nasal_only + oral_flow * difference
        return difference @ (resistance * mean + mean_loss(mean))

    oral = brentq(pressure_residual, 0., total, xtol=1e-12)
    outlets = np.array([oral, total - oral])
    return paths @ outlets, outlets, float(pressure_residual(oral))


def compare_flows(mean, outlets, observed_mean, observed_outlets):
    return {'oral_and_nasal_cm3_s': outlets.tolist(),
            'outlet_relative_error': (abs(outlets - observed_outlets) / abs(observed_outlets)).tolist(),
            'mean_flow_l2_error': inlet.relative_l2(mean, observed_mean)}


def inspect_edition(cfg, reference, layout, tracks, state, nodes, branches, source):
    groups, selected = supra.selected_groups(layout, branches, source)
    pharynx = np.isin(selected, groups['pharynx'])
    if len(selected) != cfg['supraglottal_branch_count'] or int(pharynx.sum()) != cfg['pharynx_branch_count']:
        raise ValueError('声門上と咽頭の枝数が事前登録値と一致しません')
    chosen = branches[selected]
    paths = steady.outlet_paths(chosen[:, :2].astype(int), source)
    resistance = chosen[:, 4]
    sinus = np.isin(selected, groups['sinus'])
    coefficients = tuple(np.where(sinus, 0., item) for item in prior.branch_coefficients(layout, chosen))
    forward, reverse = coefficients
    glottal = tracks[harmonic.GLOTTIS][1:]
    total = float(glottal.mean())
    baseline, baseline_outlets = steady.solve_split(paths, total, resistance, coefficients)
    phases = np.exp(2j * np.pi / cfg['internal_rate_hz'] * np.outer(np.arange(len(glottal)), cfg['frequencies_hz']))
    basis = phases.conj().T / len(glottal)
    drive = basis @ glottal
    model = nodes, branches, selected, coefficients
    predicted = np.asarray(steady.project_branch_flow(cfg, source, model, drive, baseline))
    fluctuations = 2 * (phases @ predicted).real
    variance = 2 * (abs(predicted)**2).sum(axis=0)

    def signed_loss(mean):
        return steady.kinetic_loss(mean + fluctuations, coefficients).mean(axis=0)

    def square_loss(mean):
        return forward * (mean**2 + variance)

    corrected, corrected_outlets, pressure_residual = solve_averaged_split(paths, total, resistance, signed_loss)
    square, square_outlets, square_residual = solve_averaged_split(paths, total, resistance, square_loss)
    reconstructed = corrected + fluctuations
    reverse_correction = -(forward + reverse) * np.where(reconstructed < 0., reconstructed**2, 0.).mean(axis=0)
    direct_loss = signed_loss(corrected)
    expanded_loss = square_loss(corrected) + reverse_correction
    observed_flow = state[1:, layout['node_count'] + selected]
    observed_outlets = np.array([tracks[field][1:].mean() for field in ('lip_flow_cm3_s', 'nose_flow_cm3_s')])
    observed_mean = observed_flow.mean(axis=0)
    results = {
        name: compare_flows(mean, outlets, observed_mean, observed_outlets)
        for name, mean, outlets in (('steady', baseline, baseline_outlets), ('signed_time_average', corrected, corrected_outlets),
                                    ('positive_square_average', square, square_outlets))
    }
    ac, spectra = steady.harmonic_comparison(
        cfg, source, model, pharynx, drive, phases, observed_flow, basis @ observed_flow[:, pharynx],
        {'steady': baseline, 'signed_time_average': corrected})
    earlier = reference['ac_models']['steady_branch_means']
    selected_ac = ac['signed_time_average']
    ratio_nose = 1 - results['signed_time_average']['outlet_relative_error'][1] / results['steady']['outlet_relative_error'][1]
    ratio_branches = 1 - results['signed_time_average']['mean_flow_l2_error'] / results['steady']['mean_flow_l2_error']
    tolerance = cfg['numerical_identity_relative_error_lt']
    difference = paths[:, 0] - paths[:, 1]
    pressure_scale = float(np.max(abs(paths.T @ (resistance * corrected + direct_loss))))
    checks = {
        'steady_split_and_harmonics_match_reference': (
            inlet.relative_l2(baseline_outlets, reference['oral_and_nasal_mean_flow_cm3_s']['steady']) < tolerance
            and abs(ac['steady']['pharynx_relative_l2_error'] - earlier['pharynx_relative_l2_error']) < tolerance
            and ac['steady']['reversal'] == earlier['reversal']),
        'frequency_variance_matches_time_samples': (
            inlet.relative_l2(variance, (fluctuations**2).mean(axis=0)) < tolerance),
        'signed_pressure_expansion_matches_time_average': inlet.relative_l2(expanded_loss, direct_loss) < tolerance,
        'averaged_outlet_pressure_loss_and_flow_balance': bool(
            max(abs(pressure_residual), abs(square_residual)) < tolerance * pressure_scale
            and abs(corrected_outlets.sum() - total) < tolerance * abs(total)),
    }
    summary = {
        'mean_glottal_flow_cm3_s': total, 'observed_outlet_flows_cm3_s': observed_outlets.tolist(),
        'dc_models': results, 'ac_models': ac,
        'nose_mean_error_reduction_fraction': ratio_nose, 'all_branch_mean_error_reduction_fraction': ratio_branches,
        'mean_loss_path_correction_dyn_cm2': {
            'observed': reference['path_loss_difference_due_to_averaging_dyn_cm2'],
            'estimated': float(difference @ (direct_loss - steady.kinetic_loss(corrected, coefficients))),
            'variance': float(difference @ (forward * variance)),
            'sign_correction': float(difference @ (expanded_loss - steady.kinetic_loss(corrected, coefficients) - forward * variance)),
        },
        'dc_hypothesis_met': min(ratio_nose, ratio_branches) >= cfg['minimum_mean_error_reduction_fraction'],
        'ac_hypothesis_met': (
            selected_ac['pharynx_relative_l2_error'] <= cfg['maximum_pharynx_spectral_l2_error']
            and selected_ac['reversal']['branches']['missed'] == 0
            and selected_ac['reversal']['branches']['false_positive'] == 0
            and selected_ac['mismatch_fraction'] <= cfg['maximum_sign_mismatch_fraction']),
        'branch_averages': [
            {'nodes': edge[:2].astype(int).tolist(), 'observed_cm3_s': float(observed), 'steady_cm3_s': float(base),
             'averaged_loss_cm3_s': float(updated), 'estimated_variance_cm6_s2': float(variation),
             'estimated_mean_kinetic_pressure_dyn_cm2': float(loss)}
            for edge, observed, base, updated, variation, loss
            in zip(chosen, observed_mean, baseline, corrected, variance, direct_loss, strict=True)
        ],
    }
    return checks, summary, spectra['signed_time_average']


def analyze(case, archive):
    cfg = case['measurement']
    previous = READ(archive['steady-flow-case.json'])['measurement']
    frozen = ('internal_rate_hz', 'frequency_hz', 'fundamental_hz', 'steady_window_internal_samples',
              'frequencies_hz', 'pressure_cm_h2o', 'pharynx_branch_count', 'supraglottal_branch_count')
    if any(cfg[key] != previous[key] for key in frozen):
        raise ValueError('事前登録した肺圧、観測窓、周波数が前回と一致しません')
    saved = READ(archive['steady-flow-summary.json'])['pressures']
    low = {**archive, **{name: archive[f'low-{name}'] for name in inlet.lower.CAPTURE_INPUTS}}
    checks, pressures = {}, {}
    for pressure, inputs in (('reference', archive), ('lower', low)):
        if READ(inputs['natural-case.json'])['voice']['pressure_cm_h2o'] != cfg['pressure_cm_h2o'][pressure]:
            raise ValueError('保存した収録の肺圧が事前登録値と一致しません')
        layout, recordings = supra.recorded_editions(case, inputs)
        pressures[pressure], spectra = {}, {}
        for edition, recording in recordings.items():
            conditions, pressures[pressure][edition], spectra[edition] = inspect_edition(
                cfg, saved[pressure][edition], layout, *recording)
            checks.update({f'{pressure}/{edition}/{key}': answer for key, answer in conditions.items()})
        candidate, upper = (pressures[pressure][edition] for edition in ('candidate', 'upstream'))
        pair = tuple(np.array(result['dc_models']['signed_time_average']['oral_and_nasal_cm3_s'])
                     for result in (candidate, upper))
        checks[f'{pressure}/both_editions_agree'] = (
            inlet.relative_l2(*pair) < cfg['edition_relative_error_lt']
            and inlet.relative_l2(spectra['candidate'], spectra['upstream']) < cfg['edition_relative_error_lt']
            and candidate['ac_models']['signed_time_average']['reversal'] == upper['ac_models']['signed_time_average']['reversal']
            and all(candidate[key] == upper[key] for key in ('dc_hypothesis_met', 'ac_hypothesis_met')))
    checks[DC_HYPOTHESIS] = all(result['dc_hypothesis_met'] for group in pressures.values() for result in group.values())
    checks[AC_HYPOTHESIS] = all(result['ac_hypothesis_met'] for group in pressures.values() for result in group.values())
    return {'checks': checks, 'frequencies_hz': cfg['frequencies_hz'], 'pressures': pressures}


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
              *(Path(module.__file__) for module in (steady, inlet, supra, prior, harmonic, velum, COUPLED, COUPLED.SHARED)),
              *(UPSTREAM / name for name in (velum.NETWORK, velum.VOICE, 'crates/chimera/src/voice/human_airway.rs',
                'crates/chimera/tests/airway_adversarial.rs', 'Cargo.lock'))]
    details = {'case_id': case['id'], 'case_revision': case['measurement']['revision'], 'upstream_revision': revision,
               'invoked_from': str(Path.cwd())}
    return COUPLED.SHARED.record_measurement(
        args.run_id, CASE, inputs, details, measure, command=None, input_root=velum.screen.ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
