"""口蓋帆ポートの各倍音を差し替え、2,310 Hzの損失と鼻端応答を測る。"""

import argparse
from pathlib import Path
import re
import subprocess

import numpy as np

import measure_fixed_vowel_i_velum_port_loss_feedback as feedback
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/fixed-vowel-i-velum-port-loss-sensitivity.json'
READ, COUPLED, pair = feedback.READ, feedback.COUPLED, feedback.pair
steady, inlet, supra, prior = feedback.steady, feedback.inlet, feedback.supra, feedback.prior
harmonic, velum = feedback.harmonic, feedback.velum
EVIDENCE = ()
LINEAR_HYPOTHESIS = 'linearized_single_replacement_matches_finite_replacement'
PAIR_HYPOTHESIS = 'reference_selected_pair_reduces_nose_error_by_quarter_and_beats_previous_pair'


def archive_inputs(case):
    spec = case['measurement']['reference']
    run, header = record = COUPLED.smoothing.run_manifest(
        spec['run'], 'fixed-vowel-i-velum-port-loss-feedback', case['upstream_revision'])
    manifest = run / 'manifest.json'
    summary = COUPLED.verified_path(record, 'summary.json')
    rejected = {name for name, passed in READ(summary)['checks'].items() if not passed}
    if sha256(manifest) != spec['manifest_sha256'] or header['status'] != 'fail' or rejected != {feedback.NOSE_HYPOTHESIS}:
        raise ValueError('先行実行のマニフェストと鼻端仮説の判定が登録値と一致しません')
    entry, = [item for item in header['inputs'] if item['path'].endswith('/cases/fixed-vowel-i-velum-port-loss-feedback.json')]
    definition = run / header['source_snapshot'] / entry['path']
    if sha256(definition) != entry['sha256']:
        raise ValueError('先行実行の保存ケースがマニフェストと一致しません')
    return {**feedback.archive_inputs(READ(definition)), 'loss-feedback-manifest.json': manifest,
            'loss-feedback-case.json': definition, 'loss-feedback-summary.json': summary}


def signed_projection(delta, residual):
    return (delta * residual.conjugate()).real / abs(residual)**2


def loss_derivative(baseline, phase, basis, coefficients, step):
    directions = 2 * np.column_stack((phase.real, -phase.imag))
    slope = 2 * np.where(baseline >= 0., *coefficients) * abs(baseline)
    derivative = (basis * slope) @ directions
    plus = steady.kinetic_loss(baseline[:, None] + step * directions, coefficients)
    minus = steady.kinetic_loss(baseline[:, None] - step * directions, coefficients)
    finite_difference = (basis @ (plus - minus)) / (2 * step)
    return np.split(derivative, 2), inlet.relative_l2(derivative, finite_difference)


def evaluate_port(cfg, reference, middle_reference, layout, recording, selected_frequencies):
    tracks, state, nodes, branches, source = recording
    groups, selected = supra.selected_groups(layout, branches, source)
    if len(selected) != cfg['supraglottal_branch_count'] or len(groups['port']) != 1:
        raise ValueError('声門上と口蓋帆ポートの枝数が事前登録値と一致しません')
    port = int(groups['port'][0])
    slot = selected.tolist().index(port)
    if branches[port, :2].astype(int).tolist() != cfg['port_nodes'] or layout['velum_port_cm2'] != cfg['port_area_cm2']:
        raise ValueError('口蓋帆ポートの節点または開口面積が事前登録値と一致しません')
    sinus = np.isin(selected, groups['sinus'])
    coefficients = tuple(np.where(sinus, 0., value)
                         for value in prior.branch_coefficients(layout, branches[selected]))
    port_coefficients = tuple(value[slot] for value in coefficients)
    model = nodes, branches, selected, coefficients
    fs, target_frequency = cfg['internal_rate_hz'], cfg['frequency_hz']
    fundamental = cfg['fundamental_hz']
    frequencies = [fundamental * j for j in range(1, 23)]
    added = [fundamental * j for j in cfg['added_harmonics']]
    if sorted(cfg['frequencies_hz'] + added) != frequencies:
        raise ValueError('基準の10周波数と追加倍音の和が第1〜22倍音に一致しません')
    glottal = tracks[harmonic.GLOTTIS][1:]
    observed_flow = state[1:, layout['node_count'] + port]
    length = len(glottal)
    if any(f * length % fs or not 0 < f < fs / 2 for f in frequencies):
        raise ValueError('観測窓と倍音のビンが一致しません')
    phases = np.exp(2j * np.pi / fs * np.outer(np.arange(length), frequencies))
    basis = phases.conj().T / length
    drive = basis @ glottal
    base_indices = [frequencies.index(f) for f in cfg['frequencies_hz']]
    added_indices = [frequencies.index(f) for f in added]
    mean, base_coefficients, base_wave = feedback.middle.bandwidth.preceding.predict_waveform(
        cfg, source, model, float(glottal.mean()), phases[:, base_indices], drive[base_indices])
    added_coefficients = np.asarray(steady.project_branch_flow(
        {**cfg, 'frequencies_hz': added}, source, model, drive[added_indices], mean))
    predicted = np.empty(len(frequencies), dtype=complex)
    predicted[base_indices] = base_coefficients[:, slot]
    predicted[added_indices] = added_coefficients[:, slot]
    baseline = mean[slot] + 2 * (phases @ predicted).real
    observed = basis @ observed_flow
    coefficient_error = observed - predicted
    replacements = 2 * (phases * coefficient_error).real

    target_index = frequencies.index(target_frequency)
    target, target_drive = basis[target_index], drive[target_index]
    expected_nose = (target @ tracks['nose_flow_cm3_s'][1:]) / target_drive
    base_loss = target @ steady.kinetic_loss(baseline, port_coefficients)
    fixed_sources = target @ steady.kinetic_loss(base_wave, coefficients)
    fixed_sources[slot] = base_loss
    matrix, injection, dipoles, nose = supra.forcing(target_frequency, fs, nodes, branches, selected, source)
    gain = ((np.linalg.solve(matrix.T, nose) @ dipoles)[slot]) / target_drive
    base_nose = (nose @ np.linalg.solve(matrix, target_drive * injection + dipoles @ fixed_sources)) / target_drive
    residual = expected_nose - base_nose

    (derivative_real, derivative_imag), central_error = loss_derivative(
        baseline, phases, target, port_coefficients, cfg['finite_difference_coefficient_step_cm3_s'])
    linear_delta = derivative_real * coefficient_error.real + derivative_imag * coefficient_error.imag
    projected = signed_projection(gain * linear_delta, residual)
    local_rank = np.argsort(-projected, kind='stable')
    local_pair = [frequencies[j] for j in local_rank[:2]]
    selected_frequencies = local_pair if selected_frequencies is None else selected_frequencies
    previous_indices = [frequencies.index(f) for f in cfg['feedback_frequencies_hz']]
    chosen_indices = [frequencies.index(f) for f in selected_frequencies]
    comparisons = ('previous_pair', 'reference_selected_pair', 'all_22_coefficients', 'full_band_with_observed_mean')
    combined = np.column_stack((baseline + replacements[:, previous_indices].sum(axis=1),
                                baseline + replacements[:, chosen_indices].sum(axis=1),
                                baseline + replacements.sum(axis=1), observed_flow))
    waveforms = np.column_stack((baseline[:, None] + replacements, combined))
    loss = steady.kinetic_loss(waveforms, port_coefficients)
    losses = target @ loss
    loss_delta = losses - base_loss
    single_change = loss_delta[:len(frequencies)]
    nose_transfers = (nose @ np.linalg.solve(
        matrix, target_drive * injection[:, None] + (dipoles @ fixed_sources)[:, None]
        + dipoles[:, [slot]] * loss_delta)) / target_drive
    nose_errors = abs(nose_transfers / expected_nose - 1.)
    before_error = float(abs(base_nose / expected_nose - 1.))
    fractions = 1. - nose_errors / before_error
    swaps = {
        name: {'port_loss_dyn_cm2': pair(p), 'nose_transfer': pair(h), 'nose_relative_error': float(error),
               'nose_error_reduction_fraction': float(reduction)}
        for name, p, h, error, reduction in zip(comparisons, losses[len(frequencies):],
                                               nose_transfers[len(frequencies):], nose_errors[len(frequencies):],
                                               fractions[len(frequencies):])}
    linear_error = inlet.relative_l2(linear_delta, single_change)
    previous = reference['conditions']
    archived_previous_pair = complex(*previous['measured_loss_control']['nose_transfer'])
    archived_baseline = complex(*previous['tangent']['nose_transfer'])
    archived_full = complex(*middle_reference['conditions']['measured_full_band']['nose_transfer'])
    previous_sources = {row['frequency_hz']: complex(*row['port_flow_cm3_s']['tangent'])
                        for row in reference['feedback_frequencies']}
    numerical = {
        'baseline_nose_transfer_matches_archive': float(abs(base_nose / archived_baseline - 1.)),
        'previous_pair_nose_transfer_matches_observed_control': float(
            abs(complex(*swaps['previous_pair']['nose_transfer']) / archived_previous_pair - 1.)),
        'full_band_nose_transfer_matches_archive': float(
            abs(complex(*swaps['full_band_with_observed_mean']['nose_transfer']) / archived_full - 1.)),
        'previous_port_coefficients_match_archive': inlet.relative_l2(
            predicted[previous_indices], np.array([previous_sources[f] for f in cfg['feedback_frequencies_hz']])),
        'single_replacements_preserve_other_coefficients': inlet.relative_l2(
            basis @ waveforms[:, :len(frequencies)], predicted[:, None] + np.diag(coefficient_error)),
        'coefficient_replacements_preserve_mean': float(np.max(abs(waveforms[:, :-1].mean(axis=0) / mean[slot] - 1.))),
        'port_loss_matches_fft': inlet.relative_l2(losses, np.fft.rfft(loss, axis=0)[target_frequency * length // fs] / length),
        'nose_superposition_matches_direct_solve': inlet.relative_l2(nose_transfers - base_nose, gain * loss_delta),
    }
    checks = {key: value < cfg['numerical_identity_relative_error_lt'] for key, value in numerical.items()}
    checks['loss_derivative_matches_central_difference'] = central_error < cfg['finite_difference_relative_error_lt']
    checks['finite_waveforms_and_nose_transfers'] = bool(np.isfinite(waveforms).all() and np.isfinite(nose_transfers).all())
    return checks, {
        'observed_nose_transfer': pair(expected_nose),
        'baseline_nose_transfer': pair(base_nose),
        'baseline_nose_relative_error': before_error,
        'port_loss_to_nose_transfer_gain': pair(gain),
        'local_ranked_pair_hz': local_pair,
        'reference_selected_pair_hz': selected_frequencies,
        'largest_two_flow_errors_hz': [frequencies[j] for j in np.argsort(-abs(coefficient_error), kind='stable')[:2]],
        'linearized_replacement_relative_l2_error': linear_error,
        'central_difference_relative_l2_error': central_error,
        'numerical_relative_errors': numerical,
        'combined_replacements': swaps,
        'harmonics': [
            {'frequency_hz': f, 'predicted_flow_cm3_s': pair(predicted[j]), 'observed_flow_cm3_s': pair(observed[j]),
             'flow_error_cm3_s': float(abs(coefficient_error[j])),
             'loss_derivative_real': pair(derivative_real[j]), 'loss_derivative_imag': pair(derivative_imag[j]),
             'linearized_loss_change_dyn_cm2': pair(linear_delta[j]), 'finite_loss_change_dyn_cm2': pair(single_change[j]),
             'linearized_nose_residual_projection_fraction': float(projected[j]),
             'finite_nose_residual_projection_fraction': float(signed_projection(nose_transfers[j] - base_nose, residual)),
             'nose_transfer': pair(nose_transfers[j]), 'nose_error_reduction_fraction': float(fractions[j])}
            for j, f in enumerate(frequencies)],
        'hypotheses': {
            LINEAR_HYPOTHESIS: linear_error < cfg['linearized_single_replacements_relative_error_lt'],
            PAIR_HYPOTHESIS: (swaps['reference_selected_pair']['nose_error_reduction_fraction']
                              >= cfg['minimum_selected_pair_nose_error_reduction_fraction']
                              and swaps['reference_selected_pair']['nose_relative_error']
                              < swaps['previous_pair']['nose_relative_error'])},
    }


def analyze(case, archive):
    cfg = case['measurement']
    before = READ(archive['loss-feedback-case.json'])['measurement']
    frozen = ('pressure_cm_h2o', 'internal_rate_hz', 'frequency_hz', 'fundamental_hz', 'steady_window_internal_samples',
              'frequencies_hz', 'added_harmonics', 'feedback_frequencies_hz', 'port_nodes', 'port_area_cm2',
              'supraglottal_branch_count')
    if any(cfg[key] != before[key] for key in frozen):
        raise ValueError('観測条件が保存済みの実行と一致しません')
    saved = READ(archive['loss-feedback-summary.json'])['pressures']
    middle_summary = READ(archive['middle-harmonics-summary.json'])['pressures']
    low = {**archive, **{name: archive[f'low-{name}'] for name in inlet.lower.CAPTURE_INPUTS}}
    checks, pressures = {}, {}
    selected_frequencies = None
    for pressure, inputs in (('reference', archive), ('lower', low)):
        if READ(inputs['natural-case.json'])['voice']['pressure_cm_h2o'] != cfg['pressure_cm_h2o'][pressure]:
            raise ValueError('収録の肺圧が事前登録値と一致しません')
        layout, recordings = supra.recorded_editions(case, inputs)
        pressures[pressure] = {}
        for edition in ('candidate', 'upstream'):
            results, edition_result = evaluate_port(
                cfg, saved[pressure][edition], middle_summary[pressure][edition], layout, recordings[edition], selected_frequencies)
            if selected_frequencies is None:
                selected_frequencies = edition_result['reference_selected_pair_hz']
            pressures[pressure][edition] = edition_result
            checks.update({f'{pressure}/{edition}/{name}': answer for name, answer in results.items()})
        candidate, upstream = (pressures[pressure][edition] for edition in ('candidate', 'upstream'))
        limits = [
            inlet.relative_l2(*(np.array([complex(*row[key]) for row in item['harmonics']])
                                for item in (candidate, upstream)))
            for key in ('linearized_loss_change_dyn_cm2', 'finite_loss_change_dyn_cm2', 'nose_transfer')]
        checks[f'{pressure}/both_editions_agree'] = (
            max(limits) < cfg['edition_relative_error_lt']
            and candidate['local_ranked_pair_hz'] == upstream['local_ranked_pair_hz']
            and candidate['hypotheses'] == upstream['hypotheses'])
    for hypothesis in (LINEAR_HYPOTHESIS, PAIR_HYPOTHESIS):
        checks[hypothesis] = all(result['hypotheses'][hypothesis] for results in pressures.values() for result in results.values())
    return {'checks': checks, 'port_nodes': cfg['port_nodes'], 'nose_frequency_hz': cfg['frequency_hz'],
            'reference_selected_pair_hz': selected_frequencies, 'pressures': pressures}


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

    bandwidth = feedback.middle.bandwidth
    inputs = [CASE, Path(__file__), *archive.values(), *(Path(module.__file__) for module in (
        feedback, feedback.middle, bandwidth, bandwidth.preceding, bandwidth.preceding.averaged,
        steady, inlet, supra, prior, harmonic, velum, COUPLED, COUPLED.SHARED)),
        *(UPSTREAM / name for name in (velum.NETWORK, velum.VOICE, 'crates/chimera/src/voice/human_airway.rs',
          'crates/chimera/src/airway/frequency.rs', 'crates/chimera/tests/airway_adversarial.rs', 'Cargo.lock'))]
    details = {'case_id': case['id'], 'case_revision': case['measurement']['revision'], 'upstream_revision': revision,
               'invoked_from': str(Path.cwd())}
    return COUPLED.SHARED.record_measurement(
        args.run_id, CASE, inputs, details, measure, command=None, input_root=velum.screen.ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
