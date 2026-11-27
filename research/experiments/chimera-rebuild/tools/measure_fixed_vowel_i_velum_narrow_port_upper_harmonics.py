"""狭い口蓋帆ポートで補正済みの低域に第23〜44倍音を加える。"""

import argparse
from pathlib import Path
import re
import subprocess

import numpy as np

import measure_fixed_vowel_i_velum_narrow_port_all_harmonic_feedback as previous
from upstream_baseline import UPSTREAM, WORKSPACE


CASE = WORKSPACE / 'cases/fixed-vowel-i-velum-narrow-port-upper-harmonics.json'
READ, COUPLED = previous.READ, previous.COUPLED
feedback, narrow, supra, inlet, velum = previous.feedback, previous.narrow, previous.supra, previous.inlet, previous.velum
steady, prior, harmonic, pair = feedback.steady, feedback.prior, feedback.harmonic, feedback.pair
preceding = feedback.middle.bandwidth.preceding
EVIDENCE = ()
PORT_HYPOTHESIS = 'upper_feedback_reduces_port_coefficient_error_by_half'
RECOVERY_HYPOTHESIS = 'upper_feedback_recovers_eighty_percent_of_measured_nose_improvement'
LOW_ONLY = 'compensated_low_only'
PREDICTED = 'predicted_loss_feedback'


def archive_inputs(case):
    spec = case['measurement']['reference']
    record, manifest, definition = COUPLED.smoothing.verified_reference(
        {'run': spec['run'], 'case': previous.CASE.stem, 'sha256': spec['manifest_sha256']},
        case['upstream_revision'])
    return {**previous.archive_inputs(READ(definition)), 'lower-feedback-case.json': definition,
            'lower-feedback-manifest.json': manifest,
            'lower-feedback-summary.json': COUPLED.verified_path(record, 'summary.json')}


def nose_response(frequency, fs, recording, model, slot, wave_ten, waves, basis, drive):
    tracks, _, nodes, branches, source = recording
    _, _, selected, coefficients = model
    fixed = basis @ steady.kinetic_loss(wave_ten, coefficients)
    pressures = np.repeat(fixed[:, None], waves.shape[1], axis=1)
    pressures[slot] = basis @ steady.kinetic_loss(waves, tuple(item[slot] for item in coefficients))
    matrix, injection, dipoles, nose = supra.forcing(frequency, fs, nodes, branches, selected, source)
    response = (nose @ np.linalg.solve(matrix, drive * injection[:, None] + dipoles @ pressures)) / drive
    measured = (basis @ tracks['nose_flow_cm3_s'][1:]) / drive
    port_gain = np.linalg.solve(matrix.T, nose) @ dipoles[:, slot]
    predicted_delta = port_gain * (pressures[slot, 1:] - pressures[slot, 0]) / drive
    return response, measured, pressures[slot], inlet.relative_l2(response[1:] - response[0], predicted_delta)


def evaluate(cfg, layout, recording, lower, upper, archived, archived_mean):
    tracks, state, nodes, branches, source = recording
    groups, selected = supra.selected_groups(layout, branches, source)
    if len(selected) != cfg['supraglottal_branch_count'] or len(groups['port']) != 1:
        raise ValueError('声門上と口蓋帆ポートの枝数が事前登録値と一致しません')
    port = int(groups['port'][0])
    slot = selected.tolist().index(port)
    if branches[port, :2].astype(int).tolist() != cfg['port_nodes'] or layout['velum_port_cm2'] != cfg['port_area_cm2']:
        raise ValueError('口蓋帆ポートの節点または開口面積が事前登録値と一致しません')
    sinus = np.isin(selected, groups['sinus'])
    coefficients = tuple(np.where(sinus, 0., item) for item in prior.branch_coefficients(layout, branches[selected]))
    model = nodes, branches, selected, coefficients
    glottal = tracks[harmonic.GLOTTIS][1:]
    fs, target = cfg['internal_rate_hz'], cfg['frequency_hz']
    base = cfg['frequencies_hz']
    additional = [f for f in lower if f not in base]
    frequencies = base + additional + upper
    n = len(glottal)
    if any(n * f % fs or not 0 < f < fs / 2 for f in frequencies):
        raise ValueError('観測窓と周波数が正の整数ビンで一致しません')
    bins = np.array(frequencies) * n // fs
    phases = np.exp(2j * np.pi / fs * np.outer(np.arange(n), frequencies))
    basis = phases.conj().T / n
    drive = basis @ glottal
    target_index = base.index(target)
    base_end, lower_end = len(base), len(lower)
    saved = {row['frequency_hz']: row['port_flow_cm3_s'] for row in archived['feedback_frequencies']}
    saved_tangent = np.array([complex(*saved[f]['tangent']) for f in frequencies[:lower_end]])
    saved_corrected = np.array([complex(*saved[f][PREDICTED]) for f in frequencies[:lower_end]])

    mean, base_flow, wave_ten = preceding.predict_waveform(
        cfg, source, model, float(glottal.mean()), phases[:, :base_end], drive[:base_end])
    extra_flow = np.asarray(steady.project_branch_flow(
        {**cfg, 'frequencies_hz': frequencies[base_end:]}, source, model, drive[base_end:], mean))
    tangent = np.concatenate((base_flow, extra_flow))
    spectra = tangent.copy()
    # 低域ではポートの係数だけを先行の予測補正に固定する。
    spectra[:lower_end, slot] = saved_corrected
    wave_full = mean + 2 * (phases @ spectra).real
    time_loss = steady.kinetic_loss(wave_full, coefficients)
    upper_basis = basis[lower_end:]
    predicted_losses = upper_basis @ time_loss
    extra_r = 2 * np.where(mean >= 0., *coefficients) * abs(mean)
    tangent_branches = branches.copy()
    tangent_branches[selected, 4] += extra_r

    flows, observed, rows, numerical = [], [], [], {}
    for f, weights, excitation, flow, loss in zip(upper, upper_basis, drive[lower_end:], tangent[lower_end:], predicted_losses):
        values, actual, comparisons, row = feedback.feedback_at_frequency(
            f, fs, weights, excitation, layout, state, model, groups, source, slot,
            tangent_branches, extra_r, flow, loss)
        flows.append(values)
        observed.append(actual)
        rows.append(row)
        numerical.update({f'{f}Hz/{key}': value for key, value in comparisons.items()})

    measured = np.asarray(observed)
    upper_flows = np.column_stack((np.zeros_like(measured), np.asarray(flows), measured))
    names = (LOW_ONLY, *feedback.CONDITIONS, feedback.MEASURED_COEFFICIENTS)
    low_wave = mean[slot] + 2 * (phases[:, :lower_end] @ saved_corrected).real
    waves = low_wave[:, None] + 2 * (phases[:, lower_end:] @ upper_flows).real
    response, measured_nose, losses, superposition_error = nose_response(
        target, fs, recording, model, slot, wave_ten, waves, basis[target_index], drive[target_index])
    archived_nose = complex(*archived['conditions'][PREDICTED]['nose_transfer'])
    wave_coefficients = np.fft.rfft(waves, axis=0) / n
    flow_fft = np.fft.rfft(state[1:, layout['node_count'] + port]) / n
    loss_fft = np.fft.rfft(time_loss, axis=0)[bins[lower_end:]] / n
    numerical.update({
        'archived_lower_tangent_flow_reproduced': inlet.relative_l2(tangent[:lower_end, slot], saved_tangent),
        'archived_mean_reproduced': float(abs(mean[slot] / archived_mean - 1.)),
        'archived_compensated_nose_transfer_reproduced': float(abs(response[0] / archived_nose - 1.)),
        'predicted_upper_loss_matches_fft': inlet.relative_l2(predicted_losses, loss_fft),
        'measured_upper_port_coefficients_match_fft': inlet.relative_l2(measured, flow_fft[bins[lower_end:]]),
        'compensated_lower_coefficients_preserved': max(
            inlet.relative_l2(values, saved_corrected) for values in wave_coefficients[bins[:lower_end]].T),
        'upper_coefficients_reconstructed': inlet.relative_l2(wave_coefficients[bins[lower_end:]], upper_flows),
        'port_mean_preserved': float(np.max(abs(wave_coefficients[0] / mean[slot] - 1.))),
        'nose_source_superposition_matches_direct_solve': superposition_error,
    })
    flow_errors = [inlet.relative_l2(flow, measured) for flow in upper_flows.T]
    nose_errors = abs(response / measured_nose - 1.)
    ideal_improvement = nose_errors[0] - nose_errors[-1]
    if flow_errors[1] <= 0.:
        raise ValueError('接線解の流量誤差が正になりません')
    recovery = ((nose_errors[0] - nose_errors) / ideal_improvement
                if ideal_improvement > 0. else (None,) * len(names))
    port_reduction = 1. - flow_errors[2] / flow_errors[1]
    measured_source_nose_error = float(abs(response[3] / response[-1] - 1.))
    checks = {name: error < cfg['numerical_identity_relative_error_lt'] for name, error in numerical.items()}
    checks.update({
        'finite_inputs_and_outputs': bool(np.isfinite(wave_full).all() and np.isfinite(response).all()),
        'measured_source_control_reproduces_port_flow': flow_errors[3] < cfg['measured_source_port_relative_error_lt'],
        'measured_source_control_agrees_with_measured_coefficients':
            measured_source_nose_error < cfg['measured_source_nose_transfer_relative_error_lt'],
    })
    return checks, {
        'feedback_frequencies': rows,
        'measured_nose_transfer': pair(measured_nose),
        'conditions': {
            name: {'upper_port_coefficients_relative_l2_error': error, 'nose_transfer': pair(response[j]),
                   'nose_relative_error': float(nose_errors[j]),
                   'fraction_of_measured_nose_improvement': float(recovery[j]) if recovery[j] is not None else None,
                   'port_loss_at_nose_frequency_dyn_cm2': pair(losses[j])}
            for j, (name, error) in enumerate(zip(names, flow_errors))},
        'port_error_reduction_fraction': port_reduction,
        'measured_source_nose_transfer_relative_error': measured_source_nose_error,
        'numerical_relative_errors': numerical,
        'hypotheses': {
            PORT_HYPOTHESIS: port_reduction >= cfg['minimum_port_error_reduction_fraction'],
            RECOVERY_HYPOTHESIS: recovery[2] is not None and bool(
                recovery[2] >= cfg['minimum_recovered_nose_improvement_fraction']),
        },
    }


def analyze(case, archive):
    cfg = case['measurement']
    prior_case = READ(archive['lower-feedback-case.json'])['measurement']
    frozen = ('pressure_cm_h2o', 'internal_rate_hz', 'frequency_hz', 'fundamental_hz', 'steady_window_internal_samples',
              'frequencies_hz', 'added_harmonics', 'port_nodes', 'port_area_cm2', 'supraglottal_branch_count')
    if any(cfg[key] != prior_case[key] for key in frozen):
        raise ValueError('肺圧、開口、周波数または窓が保存実行と一致しません')
    fundamental = cfg['fundamental_hz']
    lower = [fundamental * j for j in prior_case['feedback_harmonics']]
    upper = [fundamental * j for j in cfg['upper_harmonics']]
    if prior_case['feedback_harmonics'] + cfg['upper_harmonics'] != list(range(1, 45)):
        raise ValueError('対象が第1〜44倍音と一致しません')
    captured = {**archive, **{name: archive[f'narrow-{name}'] for name in narrow.CAPTURE_FILES},
                'archive-linear-inspect.json': archive['narrow-linear-inspect.json'],
                **{f'archive-{name}': archive[f'narrow-linear-upstream/{name}'] for name in narrow.NETWORK_FILES}}
    if READ(captured['natural-case.json'])['voice']['pressure_cm_h2o'] != cfg['pressure_cm_h2o']:
        raise ValueError('収録の肺圧が事前登録値と一致しません')
    layout, recordings = supra.recorded_editions(case, captured)
    prior_results = READ(archive['lower-feedback-summary.json'])['editions']
    bandwidth_results = READ(archive['narrow-bandwidth-summary.json'])['editions']
    checks, editions = {}, {}
    for edition, recording in recordings.items():
        mean = bandwidth_results[edition]['conditions']['predicted']['port_mean_flow_cm3_s']
        results, editions[edition] = evaluate(cfg, layout, recording, lower, upper, prior_results[edition], mean)
        checks.update({f'{edition}/{key}': passed for key, passed in results.items()})
    candidate, upstream = (editions[edition] for edition in ('candidate', 'upstream'))
    flows = [np.array([complex(*value) for row in item['feedback_frequencies']
                       for value in row['port_flow_cm3_s'].values()]) for item in (candidate, upstream)]
    noses = [np.array([complex(*row['nose_transfer']) for row in item['conditions'].values()])
             for item in (candidate, upstream)]
    checks['both_editions_agree'] = (max(inlet.relative_l2(*flows), inlet.relative_l2(*noses)) < cfg['edition_relative_error_lt']
                                    and candidate['hypotheses'] == upstream['hypotheses'])
    for hypothesis in (PORT_HYPOTHESIS, RECOVERY_HYPOTHESIS):
        checks[hypothesis] = all(detail['hypotheses'][hypothesis] for detail in editions.values())
    return {'checks': checks, 'port_area_cm2': cfg['port_area_cm2'], 'nose_frequency_hz': cfg['frequency_hz'],
            'added_frequencies_hz': upper, 'editions': editions}


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
        previous, previous.bandwidth, narrow, feedback, preceding, preceding.averaged,
        steady, inlet, supra, prior, harmonic, velum, COUPLED, COUPLED.SHARED)),
        *(UPSTREAM / name for name in (velum.NETWORK, velum.VOICE, 'crates/chimera/src/voice/human_airway.rs',
          'crates/chimera/src/airway/frequency.rs', 'crates/chimera/tests/airway_adversarial.rs', 'Cargo.lock'))]
    details = {'case_id': case['id'], 'case_revision': case['measurement']['revision'], 'upstream_revision': revision,
               'invoked_from': str(Path.cwd())}
    return COUPLED.SHARED.record_measurement(
        args.run_id, CASE, inputs, details, measure, command=None, input_root=velum.screen.ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
