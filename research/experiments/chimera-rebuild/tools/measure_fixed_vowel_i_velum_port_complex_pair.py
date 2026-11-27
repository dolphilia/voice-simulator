"""鼻端の複素残差の大きさで口蓋帆ポートの2倍音を選び、有限差し替えで測る。"""

import argparse
from itertools import combinations
from pathlib import Path
import re
import subprocess

import numpy as np

import measure_fixed_vowel_i_velum_port_loss_sensitivity as sensitivity
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/fixed-vowel-i-velum-port-complex-pair.json'
READ, COUPLED, pair = sensitivity.READ, sensitivity.COUPLED, sensitivity.pair
steady, inlet, supra, prior = sensitivity.steady, sensitivity.inlet, sensitivity.supra, sensitivity.prior
harmonic, velum = sensitivity.harmonic, sensitivity.velum
EVIDENCE = ()
TRAIN_HYPOTHESIS = 'minimum_complex_residual_pair_is_within_five_points_of_training_optimum'
TRANSFER_HYPOTHESIS = 'fixed_pair_reduces_nose_error_by_quarter_and_beats_both_controls'


def archive_inputs(case):
    spec = case['measurement']['reference']
    run, header = record = COUPLED.smoothing.run_manifest(
        spec['run'], 'fixed-vowel-i-velum-port-loss-sensitivity', case['upstream_revision'])
    manifest = run / 'manifest.json'
    summary = COUPLED.verified_path(record, 'summary.json')
    rejected = {name for name, passed in READ(summary)['checks'].items() if not passed}
    if sha256(manifest) != spec['manifest_sha256'] or header['status'] != 'fail' or rejected != {sensitivity.PAIR_HYPOTHESIS}:
        raise ValueError('先行実行のマニフェストと不成立の判定が登録値と一致しません')
    entry, = [item for item in header['inputs'] if item['path'].endswith('/cases/fixed-vowel-i-velum-port-loss-sensitivity.json')]
    definition = run / header['source_snapshot'] / entry['path']
    if sha256(definition) != entry['sha256']:
        raise ValueError('先行実行の保存ケースがマニフェストと一致しません')
    return {**sensitivity.archive_inputs(READ(definition)), 'loss-sensitivity-manifest.json': manifest,
            'loss-sensitivity-case.json': definition, 'loss-sensitivity-summary.json': summary}


def evaluate_pairs(cfg, archived, previous, layout, recording, fixed_pair):
    tracks, state, nodes, branches, source = recording
    groups, selected = supra.selected_groups(layout, branches, source)
    if len(selected) != cfg['supraglottal_branch_count'] or len(groups['port']) != 1:
        raise ValueError('声門上と口蓋帆ポートの枝数が事前登録値と一致しません')
    port = int(groups['port'][0])
    slot = selected.tolist().index(port)
    ends, coefficients = prior.tangent.port_parameters(layout)
    if list(ends) != cfg['port_nodes'] or layout['velum_port_cm2'] != cfg['port_area_cm2']:
        raise ValueError('口蓋帆ポートの節点または開口面積が事前登録値と一致しません')
    fs, target_frequency = cfg['internal_rate_hz'], cfg['frequency_hz']
    frequencies = [cfg['fundamental_hz'] * j for j in range(1, cfg['harmonic_count'] + 1)]
    rows = archived['harmonics']
    if [row['frequency_hz'] for row in rows] != frequencies:
        raise ValueError('保存された倍音が事前登録の集合と一致しません')
    observed_flow = state[1:, layout['node_count'] + port]
    length = len(observed_flow)
    if any(f * length % fs or not 0 < f < fs / 2 for f in frequencies):
        raise ValueError('観測窓と倍音のビンが一致しません')
    phases = np.exp(2j * np.pi / fs * np.outer(np.arange(length), frequencies))
    basis = phases.conj().T / length
    target = basis[frequencies.index(target_frequency)]
    predicted = np.array([complex(*row['predicted_flow_cm3_s']) for row in rows])
    observed = np.array([complex(*row['observed_flow_cm3_s']) for row in rows])
    mean = previous['port_mean_flow_cm3_s']
    baseline = mean + 2 * (phases @ predicted).real
    coefficient_change = observed - predicted
    replacements = 2 * (phases * coefficient_change).real
    base_loss = target @ steady.kinetic_loss(baseline, coefficients)
    stored_linear_loss = np.array([complex(*row['linearized_loss_change_dyn_cm2']) for row in rows])
    slope = 2 * np.where(baseline >= 0., *coefficients) * abs(baseline)
    linear_loss = (target * slope) @ replacements

    drive = target @ tracks[harmonic.GLOTTIS][1:]
    measured_nose = (target @ tracks['nose_flow_cm3_s'][1:]) / drive
    base_nose = complex(*archived['baseline_nose_transfer'])
    residual = measured_nose - base_nose
    base_error = abs(residual)
    matrix, _, dipoles, nose = supra.forcing(target_frequency, fs, nodes, branches, selected, source)
    gain = (nose @ np.linalg.solve(matrix, dipoles[:, slot])) / drive
    stored_gain = complex(*archived['port_loss_to_nose_transfer_gain'])
    left, right = np.array(list(combinations(range(len(frequencies)), 2))).T
    frequency_pairs = [(frequencies[i], frequencies[j]) for i, j in zip(left, right)]
    predicted_delta = stored_gain * (stored_linear_loss[left] + stored_linear_loss[right])
    predicted_errors = abs(residual - predicted_delta) / base_error
    linear_best = int(np.argmin(predicted_errors))
    chosen = linear_best if fixed_pair is None else frequency_pairs.index(tuple(fixed_pair))

    waves = baseline[:, None] + replacements[:, left] + replacements[:, right]
    time_loss = steady.kinetic_loss(waves, coefficients)
    pair_losses = target @ time_loss
    loss_delta = pair_losses - base_loss
    actual_delta = (nose @ np.linalg.solve(matrix, dipoles[:, [slot]] * loss_delta)) / drive
    actual_errors = abs(residual - actual_delta) / base_error
    exact_best = int(np.argmin(actual_errors))
    old_pair = frequency_pairs.index(tuple(sorted(archived['reference_selected_pair_hz'])))
    single = frequencies.index(cfg['single_control_frequency_hz'])
    single_loss = target @ steady.kinetic_loss(baseline + replacements[:, single], coefficients) - base_loss
    single_delta = gain * single_loss
    single_error = abs(residual - single_delta) / base_error

    archive_old = complex(*archived['combined_replacements']['reference_selected_pair']['nose_transfer'])
    archive_single = complex(*rows[single]['nose_transfer'])
    expected_coefficients = np.broadcast_to(predicted[:, None], (len(frequencies), len(left))).copy()
    expected_coefficients[left, np.arange(len(left))] = observed[left]
    expected_coefficients[right, np.arange(len(right))] = observed[right]
    numerical = {
        'recorded_coefficients_match_archive': inlet.relative_l2(basis @ observed_flow, observed),
        'baseline_loss_matches_archive': float(abs(base_loss / complex(*previous['port_loss_dyn_cm2']) - 1.)),
        'recorded_nose_transfer_matches_archive': float(abs(measured_nose / complex(*archived['observed_nose_transfer']) - 1.)),
        'direct_gain_matches_archive': float(abs(gain / stored_gain - 1.)),
        'linearized_loss_matches_archive': inlet.relative_l2(linear_loss, stored_linear_loss),
        'pair_replacements_preserve_other_coefficients': inlet.relative_l2(basis @ waves, expected_coefficients),
        'pair_replacements_preserve_mean': float(np.max(abs(waves.mean(axis=0) / mean - 1.))),
        'pair_losses_match_fft': inlet.relative_l2(
            pair_losses, np.fft.rfft(time_loss, axis=0)[target_frequency * length // fs] / length),
        'nose_superposition_matches_direct_solve': inlet.relative_l2(stored_gain * loss_delta, actual_delta),
        'projection_pair_matches_archive': float(abs((base_nose + actual_delta[old_pair]) / archive_old - 1.)),
        'single_control_matches_archive': float(abs((base_nose + single_delta) / archive_single - 1.)),
    }
    checks = {key: value < cfg['numerical_identity_relative_error_lt'] for key, value in numerical.items()}
    checks['finite_waveforms_and_errors'] = bool(np.isfinite(waves).all() and np.isfinite(actual_errors).all())
    gap = float(actual_errors[chosen] - actual_errors[exact_best])
    scale = base_error / abs(measured_nose)

    def describe(position):
        return {
            'frequencies_hz': list(frequency_pairs[position]),
            'linearized_nose_error_reduction_fraction': float(1. - predicted_errors[position]),
            'finite_nose_error_reduction_fraction': float(1. - actual_errors[position]),
            'finite_nose_relative_error': float(scale * actual_errors[position]),
            'finite_port_loss_change_dyn_cm2': pair(loss_delta[position]),
            'finite_nose_transfer_change': pair(actual_delta[position]),
        }

    return checks, {
        'pair_count': len(frequency_pairs),
        'baseline_nose_relative_error': float(scale),
        'linearized_local_optimum': describe(linear_best),
        'finite_local_optimum': describe(exact_best),
        'fixed_selected_pair': describe(chosen),
        'projection_pair_control': describe(old_pair),
        'single_control': {
            'frequency_hz': cfg['single_control_frequency_hz'], 'finite_nose_relative_error': float(scale * single_error),
            'finite_nose_error_reduction_fraction': float(1. - single_error)},
        'selected_pair_reduction_gap_to_finite_optimum': gap,
        'pair_results': [describe(j) for j in range(len(frequency_pairs))],
        'numerical_relative_errors': numerical,
        'selection_passes_reduction_criterion': bool(
            1. - actual_errors[chosen] >= cfg['minimum_selected_pair_nose_error_reduction_fraction']
            and actual_errors[chosen] < min(actual_errors[old_pair], single_error)),
    }


def analyze(case, archive):
    cfg = case['measurement']
    before = READ(archive['loss-sensitivity-case.json'])['measurement']
    frozen = ('pressure_cm_h2o', 'internal_rate_hz', 'frequency_hz', 'fundamental_hz', 'steady_window_internal_samples',
              'port_nodes', 'port_area_cm2', 'supraglottal_branch_count')
    if any(cfg[key] != before[key] for key in frozen):
        raise ValueError('観測条件が保存済みの実行と一致しません')
    earlier = READ(archive['loss-sensitivity-summary.json'])['pressures']
    mid = READ(archive['middle-harmonics-summary.json'])['pressures']
    low = {**archive, **{name: archive[f'low-{name}'] for name in inlet.lower.CAPTURE_INPUTS}}
    checks, pressures = {}, {}
    fixed_pair = None
    for pressure, inputs in (('reference', archive), ('lower', low)):
        if READ(inputs['natural-case.json'])['voice']['pressure_cm_h2o'] != cfg['pressure_cm_h2o'][pressure]:
            raise ValueError('収録の肺圧が事前登録値と一致しません')
        layout, recordings = supra.recorded_editions(case, inputs)
        pressures[pressure] = {}
        for edition in ('candidate', 'upstream'):
            previous = mid[pressure][edition]['conditions']['predicted_with_predicted_middle']
            results, detail = evaluate_pairs(cfg, earlier[pressure][edition], previous, layout, recordings[edition], fixed_pair)
            if fixed_pair is None:
                fixed_pair = detail['fixed_selected_pair']['frequencies_hz']
            pressures[pressure][edition] = detail
            checks.update({f'{pressure}/{edition}/{name}': passed for name, passed in results.items()})
        candidate, upstream = (pressures[pressure][edition] for edition in ('candidate', 'upstream'))
        scores = [np.array([row['finite_nose_relative_error'] for row in result['pair_results']])
                  for result in (candidate, upstream)]
        checks[f'{pressure}/both_editions_agree'] = (
            inlet.relative_l2(*scores) < cfg['edition_relative_error_lt']
            and all(candidate[key]['frequencies_hz'] == upstream[key]['frequencies_hz']
                    for key in ('linearized_local_optimum', 'finite_local_optimum'))
            and candidate['selection_passes_reduction_criterion'] == upstream['selection_passes_reduction_criterion'])
    checks[TRAIN_HYPOTHESIS] = all(
        detail['selected_pair_reduction_gap_to_finite_optimum'] <= cfg['train_pair_maximum_reduction_gap']
        for detail in pressures['reference'].values())
    checks[TRANSFER_HYPOTHESIS] = all(
        detail['selection_passes_reduction_criterion'] for group in pressures.values() for detail in group.values())
    return {'checks': checks, 'port_nodes': cfg['port_nodes'], 'nose_frequency_hz': cfg['frequency_hz'],
            'selected_pair_hz': fixed_pair, 'pressures': pressures}


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

    inputs = [CASE, Path(__file__), *archive.values(), *(Path(module.__file__) for module in (
        sensitivity, sensitivity.feedback, sensitivity.feedback.middle, steady, inlet, supra, prior, harmonic,
        velum, COUPLED, COUPLED.SHARED, prior.tangent)),
        *(UPSTREAM / name for name in (velum.NETWORK, velum.VOICE, 'crates/chimera/src/voice/human_airway.rs',
          'crates/chimera/src/airway/frequency.rs', 'crates/chimera/tests/airway_adversarial.rs', 'Cargo.lock'))]
    details = {'case_id': case['id'], 'case_revision': case['measurement']['revision'], 'upstream_revision': revision,
               'invoked_from': str(Path.cwd())}
    return COUPLED.SHARED.record_measurement(
        args.run_id, CASE, inputs, details, measure, command=None, input_root=velum.screen.ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
