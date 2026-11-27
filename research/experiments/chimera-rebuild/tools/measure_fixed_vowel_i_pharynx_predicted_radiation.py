"""予測した枝の二次圧力損失から鼻端放射の2,310 Hz成分を求める。"""

import argparse
from pathlib import Path
import re
import subprocess

import numpy as np

import measure_fixed_vowel_i_pharynx_averaged_loss as averaged
from upstream_baseline import UPSTREAM, WORKSPACE


CASE = WORKSPACE / 'cases/fixed-vowel-i-pharynx-predicted-radiation.json'
READ, COUPLED = averaged.READ, averaged.COUPLED
steady, inlet, supra, prior = averaged.steady, averaged.inlet, averaged.supra, averaged.prior
harmonic, velum = averaged.harmonic, averaged.velum
pair = prior.tangent.pair
EVIDENCE = ()
HYPOTHESIS = 'predicted_loss_residual_improves_nose_radiation_in_both_pressures'


def archive_inputs(case):
    spec = case['measurement']['reference']
    record, manifest, definition = COUPLED.smoothing.verified_reference(
        {'run': spec['run'], 'case': 'fixed-vowel-i-pharynx-averaged-loss', 'sha256': spec['manifest_sha256']},
        case['upstream_revision'])
    return {**averaged.archive_inputs(READ(definition)), 'averaged-loss-manifest.json': manifest,
            'averaged-loss-case.json': definition, 'averaged-loss-summary.json': COUPLED.verified_path(record, 'summary.json')}


def predict_waveform(cfg, source, model, total, phases, drive):
    _, branches, selected, coefficients = model
    chosen = branches[selected]
    paths = steady.outlet_paths(chosen[:, :2].astype(int), source)
    resistance = chosen[:, 4]
    baseline, _ = steady.solve_split(paths, total, resistance, coefficients)
    initial = np.asarray(steady.project_branch_flow(cfg, source, model, drive, baseline))
    fluctuations = 2 * (phases @ initial).real

    def mean_loss(mean):
        return steady.kinetic_loss(mean + fluctuations, coefficients).mean(axis=0)

    mean, _, _ = averaged.solve_averaged_split(paths, total, resistance, mean_loss)
    spectrum = np.asarray(steady.project_branch_flow(cfg, source, model, drive, mean))
    return mean, spectrum, mean + 2 * (phases @ spectrum).real


def evaluate_radiation(cfg, reference, layout, tracks, state, nodes, branches, source):
    groups, selected = supra.selected_groups(layout, branches, source)
    pharynx = np.isin(selected, groups['pharynx'])
    if len(selected) != cfg['supraglottal_branch_count'] or int(pharynx.sum()) != cfg['pharynx_branch_count']:
        raise ValueError('声門上と咽頭の枝数が事前登録値と一致しません')
    chosen = branches[selected]
    sinus = np.isin(selected, groups['sinus'])
    coefficients = tuple(np.where(sinus, 0., value) for value in prior.branch_coefficients(layout, chosen))
    fs, frequency = cfg['internal_rate_hz'], cfg['frequency_hz']
    frequencies = cfg['frequencies_hz']
    target_index = frequencies.index(frequency)
    glottal = tracks[harmonic.GLOTTIS][1:]
    phases = np.exp(2j * np.pi / fs * np.outer(np.arange(len(glottal)), frequencies))
    basis = phases.conj().T / len(glottal)
    drive = basis @ glottal
    target_drive = drive[target_index]
    basis_target = basis[target_index]
    measured_nose = (basis_target @ tracks['nose_flow_cm3_s'][1:]) / target_drive

    model = nodes, branches, selected, coefficients
    mean, predicted, waveform = predict_waveform(cfg, source, model, float(glottal.mean()), phases, drive)
    signed_loss = steady.kinetic_loss(waveform, coefficients)
    predicted_source = basis_target @ signed_loss
    fft_source = np.fft.fft(signed_loss, axis=0)[frequency * len(glottal) // fs] / len(glottal)
    measured = prior.branch_pressure(frequency, fs, basis_target, state, layout, selected, branches, 1.,
                                     coefficients=coefficients)
    observed_source = measured['loss_per_drive'] + measured['window_edge_per_drive']

    extra_resistance = 2 * np.where(mean >= 0., *coefficients) * abs(mean)
    adjusted = branches.copy()
    adjusted[selected, 4] += extra_resistance
    matrix, injection, dipoles, nose = supra.forcing(frequency, fs, nodes, branches, selected, source)
    tangent_matrix, tangent_inject, tangent_dipoles, tangent_nose = supra.forcing(
        frequency, fs, nodes, adjusted, selected, source)
    residual_source = predicted_source - extra_resistance * predicted[target_index]
    direct = np.linalg.solve(matrix, target_drive * injection[:, None] + dipoles @ np.stack(
        (np.zeros_like(predicted_source), predicted_source, observed_source), axis=1))
    base = np.linalg.solve(tangent_matrix, target_drive * tangent_inject)
    corrected = np.linalg.solve(tangent_matrix, target_drive * tangent_inject + tangent_dipoles @ residual_source)
    nose_with_base, nose_with_predicted, nose_with_observed = (nose @ direct) / target_drive
    tangent_nose_transfer = tangent_nose @ base / target_drive
    corrected_nose_transfer = tangent_nose @ corrected / target_drive
    response = np.linalg.solve(matrix.T, nose) @ dipoles
    tangent_response = np.linalg.solve(tangent_matrix.T, tangent_nose) @ tangent_dipoles
    group_error = {}
    for name, indices in groups.items():
        in_group = np.isin(selected, indices)
        error = response[in_group] @ (predicted_source[in_group] - observed_source[in_group]) / target_drive
        group_error[name] = pair(error)
    response_by_branch = response * (predicted_source - observed_source) / target_drive
    largest = int(np.argmax(abs(response_by_branch)))
    predicted_means_by_edge = {tuple(row['nodes']): row['averaged_loss_cm3_s'] for row in reference['branch_averages']}
    archived_mean = np.array([predicted_means_by_edge[tuple(edge)] for edge in chosen[:, :2].astype(int)])
    flow = state[1:, layout['node_count'] + selected[pharynx]]
    pharynx_error = inlet.relative_l2(predicted[:, pharynx], basis @ flow)
    tolerance = cfg['numerical_identity_relative_error_lt']
    checks = {
        'predicted_means_and_pharynx_harmonics_match_reference': (
            inlet.relative_l2(mean, archived_mean) < tolerance
            and abs(pharynx_error - reference['ac_models']['signed_time_average']['pharynx_relative_l2_error']) < tolerance),
        'predicted_loss_fft_matches_direct_coefficient': inlet.relative_l2(fft_source, predicted_source) < tolerance,
        'tangent_residual_superposition_matches_direct_solve': bool(
            abs(corrected_nose_transfer - tangent_nose_transfer - tangent_response @ residual_source / target_drive)
            < tolerance * abs(measured_nose)),
        'observed_loss_control_reproduces_nose': bool(
            abs(nose_with_observed - measured_nose) / abs(measured_nose) < cfg['observed_loss_nose_error_lt']),
    }
    responses = {'viscous_only': nose_with_base, 'mean_flow_tangent': tangent_nose_transfer,
                 'full_predicted_loss': nose_with_predicted, 'tangent_residual_update': corrected_nose_transfer,
                 'observed_loss_control': nose_with_observed}
    ratios = {name: value / measured_nose for name, value in responses.items()}
    errors = {name: float(abs(ratio - 1.)) for name, ratio in ratios.items()}
    corrected_error = errors['tangent_residual_update']
    improvement = 1 - corrected_error / errors['mean_flow_tangent']
    return checks, {
        'observed_nose_transfer': pair(measured_nose),
        'nose_transfer': {name: pair(value) for name, value in responses.items()},
        'nose_relative_error': errors,
        'amplitude_error_db': {name: float(20 * np.log10(abs(ratio))) for name, ratio in ratios.items()},
        'phase_error_deg': {name: float(np.angle(ratio, deg=True)) for name, ratio in ratios.items()},
        'nose_error_reduction_fraction': improvement,
        'hypothesis_met': (corrected_error <= cfg['maximum_nose_relative_error']
                           and improvement >= cfg['minimum_nose_error_reduction_fraction']),
        'pressure_source_l2_relative_error': inlet.relative_l2(predicted_source, observed_source),
        'nose_transfer_error_by_branch_group': group_error,
        'largest_nose_contribution_error': {'nodes': chosen[largest, :2].astype(int).tolist(),
                                            'nose_transfer_error': pair(response_by_branch[largest])},
    }


def analyze(case, archive):
    cfg = case['measurement']
    before = READ(archive['averaged-loss-case.json'])['measurement']
    frozen = ('pressure_cm_h2o', 'internal_rate_hz', 'frequency_hz', 'fundamental_hz', 'steady_window_internal_samples',
              'frequencies_hz', 'pharynx_branch_count', 'supraglottal_branch_count')
    if any(cfg[key] != before[key] for key in frozen):
        raise ValueError('肺圧、周波数、観測窓が保存済みの実行と一致しません')
    saved = READ(archive['averaged-loss-summary.json'])['pressures']
    low = {**archive, **{name: archive[f'low-{name}'] for name in inlet.lower.CAPTURE_INPUTS}}
    checks, pressures = {}, {}
    for pressure, inputs in (('reference', archive), ('lower', low)):
        if READ(inputs['natural-case.json'])['voice']['pressure_cm_h2o'] != cfg['pressure_cm_h2o'][pressure]:
            raise ValueError('収録時の肺圧が事前登録値と一致しません')
        layout, recordings = supra.recorded_editions(case, inputs)
        pressures[pressure] = {}
        for edition, recording in recordings.items():
            conditions, pressures[pressure][edition] = evaluate_radiation(cfg, saved[pressure][edition], layout, *recording)
            checks.update({f'{pressure}/{edition}/{key}': answer for key, answer in conditions.items()})
        candidate, upstream = (pressures[pressure][edition] for edition in ('candidate', 'upstream'))
        transfers = [np.array([complex(*value) for value in result['nose_transfer'].values()]) for result in (candidate, upstream)]
        checks[f'{pressure}/both_editions_agree'] = (
            inlet.relative_l2(*transfers) < cfg['edition_relative_error_lt']
            and candidate['hypothesis_met'] == upstream['hypothesis_met'])
    checks[HYPOTHESIS] = all(result['hypothesis_met'] for group in pressures.values() for result in group.values())
    return {'checks': checks, 'frequency_hz': cfg['frequency_hz'], 'pressures': pressures}


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
        execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera', '--test', 'airway_adversarial'],
                cwd=UPSTREAM, stdout=out / 'upstream-airway-adversarial.log')
        return analyze(case, archive)

    inputs = [CASE, Path(__file__), *archive.values(),
              *(Path(module.__file__) for module in (averaged, steady, inlet, supra, prior, harmonic, velum, COUPLED, COUPLED.SHARED)),
              *(UPSTREAM / name for name in (velum.NETWORK, velum.VOICE, 'crates/chimera/src/airway/frequency.rs',
                'crates/chimera/tests/airway_adversarial.rs', 'Cargo.lock'))]
    details = {'case_id': case['id'], 'case_revision': case['measurement']['revision'], 'upstream_revision': revision,
               'invoked_from': str(Path.cwd())}
    return COUPLED.SHARED.record_measurement(
        args.run_id, CASE, inputs, details, measure, command=None, input_root=velum.screen.ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
