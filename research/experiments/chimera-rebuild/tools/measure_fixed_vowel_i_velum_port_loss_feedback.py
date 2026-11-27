"""口蓋帆ポートの770 Hzと1,320 Hzを二次損失で一度補正する。"""

import argparse
from pathlib import Path
import re
import subprocess

import numpy as np

import measure_fixed_vowel_i_velum_port_middle_harmonics as middle
from upstream_baseline import UPSTREAM, WORKSPACE


CASE = WORKSPACE / 'cases/fixed-vowel-i-velum-port-loss-feedback.json'
READ, COUPLED, pair = middle.READ, middle.COUPLED, middle.pair
steady, inlet, supra, prior = middle.steady, middle.inlet, middle.supra, middle.prior
harmonic, velum = middle.harmonic, middle.velum
EVIDENCE = ()
PORT_HYPOTHESIS = 'one_feedback_reduces_port_coefficient_error_by_half'
NOSE_HYPOTHESIS = 'two_corrected_port_coefficients_reduce_nose_error_by_quarter'
CONDITIONS = ('tangent', 'predicted_loss_feedback', 'measured_loss_control')
MEASURED_COEFFICIENTS = 'measured_coefficients_control'


def archive_inputs(case):
    spec = case['measurement']['reference']
    record, manifest, definition = COUPLED.smoothing.verified_reference(
        {'run': spec['run'], 'case': 'fixed-vowel-i-velum-port-middle-harmonics', 'sha256': spec['manifest_sha256']},
        case['upstream_revision'])
    return {**middle.archive_inputs(READ(definition)), 'middle-harmonics-manifest.json': manifest,
            'middle-harmonics-case.json': definition,
            'middle-harmonics-summary.json': COUPLED.verified_path(record, 'summary.json')}


def port_source_gain(frequency, fs, nodes, branches, selected, source, slot):
    matrix, _, dipoles, _ = supra.forcing(frequency, fs, nodes, branches, selected, source)
    delay, impedance = inlet.frequency_factors(frequency, fs, branches[selected])
    a, b = branches[selected[slot], :2].astype(int)
    row = np.zeros(len(nodes), dtype=complex)
    row[[a, b]] = [delay / impedance[slot], -delay / impedance[slot]]
    response = np.linalg.solve(matrix.T, row) @ dipoles
    response[slot] -= 1. / impedance[slot]
    return response


def feedback_at_frequency(frequency, fs, basis, drive, layout, state, model, groups, source, slot,
                          tangent_branches, extra_r, tangent_flow, predicted_loss):
    nodes, branches, selected, coefficients = model
    observed_flow = basis @ state[1:, layout['node_count'] + selected]
    pressure = prior.branch_pressure(frequency, fs, basis, state, layout, selected, branches, 1.,
                                     coefficients=coefficients)
    observed_loss = pressure['loss_per_drive'] + pressure['window_edge_per_drive']
    source_rows = np.stack((np.zeros_like(predicted_loss), predicted_loss - extra_r * tangent_flow,
                            observed_loss - extra_r * observed_flow))
    flow = inlet.branch_responses(frequency, fs, nodes, tangent_branches, selected, source, drive, source_rows)
    # 接線解で計上した抵抗の圧力を戻し、元の粘性モデルで同じ枝流量になるか照合する。
    equivalent_sources = source_rows + extra_r * flow
    independent = inlet.branch_responses(frequency, fs, nodes, branches, selected, source, drive, equivalent_sources)
    gain = port_source_gain(frequency, fs, nodes, tangent_branches, selected, source, slot)
    residual_by_branch = gain * (source_rows[1] - source_rows[2])
    largest = int(np.argmax(abs(residual_by_branch)))
    by_group = {name: pair(residual_by_branch[np.isin(selected, indices)].sum()) for name, indices in groups.items()}
    port_flow = flow[:, slot]
    observed_port = observed_flow[slot]
    errors = {
        'tangent_matches_archived_prediction_model': inlet.relative_l2(flow[0], tangent_flow),
        'tangent_feedback_matches_viscous_source_solve': inlet.relative_l2(flow, independent),
        'port_source_superposition_matches_direct_solve': inlet.relative_l2(port_flow[1:] - port_flow[0],
                                                                            (source_rows @ gain)[1:]),
    }
    return port_flow, observed_port, errors, {
        'frequency_hz': frequency,
        'glottal_flow_cm3_s': pair(drive),
        'measured_port_flow_cm3_s': pair(observed_port),
        'port_flow_cm3_s': dict(zip(CONDITIONS, map(pair, port_flow))),
        'port_absolute_error_cm3_s': dict(zip(CONDITIONS, map(float, abs(port_flow - observed_port)))),
        'predicted_loss_source_relative_l2_error': inlet.relative_l2(predicted_loss, observed_loss),
        'port_flow_residual_from_source_error_by_group_cm3_s': by_group,
        'largest_port_flow_residual_branch': {
            'nodes': branches[selected[largest], :2].astype(int).tolist(),
            'port_flow_residual_cm3_s': pair(residual_by_branch[largest])},
    }


def evaluate_port(cfg, reference, layout, recording, added, archived_port_coefficients, *,
                  include_measured_coefficients=False):
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
    n = len(glottal)
    fs, frequency = cfg['internal_rate_hz'], cfg['frequency_hz']
    base_frequencies = cfg['frequencies_hz']
    frequencies = base_frequencies + added
    if any(n * f % fs or not 0 < f < fs / 2 for f in frequencies):
        raise ValueError('観測窓と周波数が正の整数ビンで一致しません')
    samples = np.arange(n)
    base_phases = np.exp(2j * np.pi / fs * np.outer(samples, cfg['frequencies_hz']))
    added_phases = np.exp(2j * np.pi / fs * np.outer(samples, added))
    base_basis, added_basis = base_phases.conj().T / n, added_phases.conj().T / n
    drive, added_drive = base_basis @ glottal, added_basis @ glottal
    mean, base_coefficients, wave_ten = middle.bandwidth.preceding.predict_waveform(
        cfg, source, model, float(glottal.mean()), base_phases, drive)
    added_coefficients = np.asarray(steady.project_branch_flow(
        {**cfg, 'frequencies_hz': added}, source, model, added_drive, mean))
    wave_full = wave_ten + 2 * (added_phases @ added_coefficients).real
    time_loss = steady.kinetic_loss(wave_full, coefficients)
    # 平均と波形を作る周波数群を保ったまま、補正する周波数だけを取り出す。
    feedback_frequencies = cfg['feedback_frequencies_hz']
    feedback_indices = [frequencies.index(f) for f in feedback_frequencies]
    basis_rows = (*base_basis, *added_basis)
    drives = (*drive, *added_drive)
    tangent_flows = (*base_coefficients, *added_coefficients)
    feedback_basis = np.stack([basis_rows[j] for j in feedback_indices])
    predicted_sources = feedback_basis @ time_loss
    loss_fft = np.fft.rfft(time_loss, axis=0)[np.array(cfg['feedback_frequencies_hz']) * n // fs] / n
    extra_r = 2 * np.where(mean >= 0., *coefficients) * abs(mean)
    tangent_branches = branches.copy()
    tangent_branches[selected, 4] += extra_r

    flows, measured, rows, numerical = [], [], [], {}
    for frequency_hz, j, loss in zip(feedback_frequencies, feedback_indices, predicted_sources):
        flow, actual, comparisons, row = feedback_at_frequency(
            frequency_hz, fs, basis_rows[j], drives[j], layout, state, model, groups, source, slot,
            tangent_branches, extra_r, tangent_flows[j], loss)
        flows.append(flow)
        measured.append(actual)
        rows.append(row)
        numerical.update({f'{frequency_hz}Hz/{key}': value for key, value in comparisons.items()})
    port_flows = np.array(flows)
    measured = np.array(measured)
    if archived_port_coefficients is not None:
        numerical['archived_port_coefficients_reproduced'] = inlet.relative_l2(port_flows[:, 0], archived_port_coefficients)
    numerical['predicted_loss_coefficients_match_fft'] = inlet.relative_l2(predicted_sources, loss_fft)

    # 鼻端の比較では基準のポート波形のうち、補正対象の成分だけを差し替える。
    conditions = CONDITIONS
    if include_measured_coefficients:
        port_flows = np.column_stack((port_flows, measured))
        conditions = (*conditions, MEASURED_COEFFICIENTS)
    delta = port_flows - port_flows[:, :1]
    phases = np.concatenate((base_phases, added_phases), axis=1)
    waves = wave_full[:, [slot]] + 2 * (phases[:, feedback_indices] @ delta).real
    target_index = cfg['frequencies_hz'].index(frequency)
    target_basis, target_drive = base_basis[target_index], drive[target_index]
    fixed_sources = target_basis @ steady.kinetic_loss(wave_ten, coefficients)
    substituted = np.repeat(fixed_sources[:, None], len(conditions), axis=1)
    substituted[slot] = target_basis @ steady.kinetic_loss(waves, tuple(item[slot] for item in coefficients))
    matrix, injection, dipoles, nose = supra.forcing(frequency, fs, nodes, branches, selected, source)
    response = (nose @ np.linalg.solve(matrix, target_drive * injection[:, None] + dipoles @ substituted)) / target_drive
    measured_nose = (target_basis @ tracks['nose_flow_cm3_s'][1:]) / target_drive
    nose_errors = abs(response / measured_nose - 1.)
    nose_reduction = float(1. - nose_errors[1] / nose_errors[0])
    if reference is not None:
        base_nose = complex(*reference['conditions']['predicted_with_predicted_middle']['nose_transfer'])
        numerical['archived_nose_transfer_reproduced'] = float(abs(response[0] / base_nose - 1.))
    untouched_basis = np.delete(np.concatenate((base_basis, added_basis), axis=0), feedback_indices, axis=0)
    if untouched_basis.size:
        fixed_coefficients = untouched_basis @ waves[:, 0]
        numerical['unchanged_port_coefficients_preserved'] = max(
            inlet.relative_l2(untouched_basis @ wave, fixed_coefficients) for wave in waves.T[1:])
    else:
        numerical['port_coefficients_reconstructed_from_feedback'] = inlet.relative_l2(feedback_basis @ waves, port_flows)
    numerical['unchanged_port_mean_preserved'] = float(np.max(abs(waves.mean(axis=0) / mean[slot] - 1.)))
    flow_errors = [inlet.relative_l2(port_flow, measured) for port_flow in port_flows.T]
    port_reduction = 1. - flow_errors[1] / flow_errors[0]
    checks = {key: value < cfg['numerical_identity_relative_error_lt'] for key, value in numerical.items()}
    checks['measured_source_control_reproduces_port_flow'] = flow_errors[2] < cfg['measured_source_port_relative_error_lt']
    checks['finite_inputs_and_outputs'] = bool(np.isfinite(waves).all() and np.isfinite(response).all())
    error_key = 'two_port_coefficients_relative_l2_error' if len(feedback_indices) == 2 else 'port_coefficients_relative_l2_error'
    return checks, {
        'feedback_frequencies': rows,
        'conditions': {
            name: {error_key: port_error,
                   'port_loss_at_nose_frequency_dyn_cm2': pair(loss), 'nose_transfer': pair(ratio),
                   'nose_relative_error': float(nose_error)}
            for name, port_error, loss, ratio, nose_error in zip(conditions, flow_errors, substituted[slot], response, nose_errors)},
        'port_error_reduction_fraction': port_reduction,
        'nose_error_reduction_fraction': nose_reduction,
        'numerical_relative_errors': numerical,
    }


def analyze(case, archive):
    cfg = case['measurement']
    before = READ(archive['middle-harmonics-case.json'])['measurement']
    frozen = ('pressure_cm_h2o', 'internal_rate_hz', 'frequency_hz', 'fundamental_hz', 'steady_window_internal_samples',
              'frequencies_hz', 'added_harmonics', 'port_nodes', 'port_area_cm2', 'supraglottal_branch_count')
    if any(cfg[key] != before[key] for key in frozen):
        raise ValueError('観測条件が保存済みの実行と一致しません')
    added = [cfg['fundamental_hz'] * harmonic for harmonic in cfg['added_harmonics']]
    feedback = cfg['feedback_frequencies_hz']
    if len(feedback) != 2 or len(set(feedback)) != 2 or not set(feedback) <= set(added):
        raise ValueError('追加倍音のうち異なる2成分を補正してください')
    saved = READ(archive['middle-harmonics-summary.json'])['pressures']
    low = {**archive, **{name: archive[f'low-{name}'] for name in inlet.lower.CAPTURE_INPUTS}}
    checks, pressures = {}, {}
    for pressure, inputs in (('reference', archive), ('lower', low)):
        if READ(inputs['natural-case.json'])['voice']['pressure_cm_h2o'] != cfg['pressure_cm_h2o'][pressure]:
            raise ValueError('収録の肺圧が事前登録値と一致しません')
        layout, recordings = supra.recorded_editions(case, inputs)
        pressures[pressure] = {}
        for edition, recording in recordings.items():
            reference = saved[pressure][edition]
            by_frequency = {row['frequency_hz']: complex(*row['predicted'])
                            for row in reference['middle_band']['coefficients_cm3_s']}
            archived_coefficients = np.array([by_frequency[f] for f in feedback])
            results, detail = evaluate_port(cfg, reference, layout, recording, added, archived_coefficients)
            detail['hypotheses'] = {
                PORT_HYPOTHESIS: detail['port_error_reduction_fraction'] >= cfg['minimum_port_error_reduction_fraction'],
                NOSE_HYPOTHESIS: detail['nose_error_reduction_fraction'] >= cfg['minimum_nose_error_reduction_fraction'],
            }
            pressures[pressure][edition] = detail
            checks.update({f'{pressure}/{edition}/{key}': passed for key, passed in results.items()})
        candidate, upstream = (pressures[pressure][edition] for edition in ('candidate', 'upstream'))
        port_vectors = [
            np.array([complex(*value) for row in result['feedback_frequencies'] for value in row['port_flow_cm3_s'].values()])
            for result in (candidate, upstream)]
        nose_vectors = [
            np.array([complex(*row['nose_transfer']) for row in result['conditions'].values()])
            for result in (candidate, upstream)]
        checks[f'{pressure}/both_editions_agree'] = (
            max(inlet.relative_l2(*port_vectors), inlet.relative_l2(*nose_vectors)) < cfg['edition_relative_error_lt']
            and candidate['hypotheses'] == upstream['hypotheses'])
    for hypothesis in (PORT_HYPOTHESIS, NOSE_HYPOTHESIS):
        checks[hypothesis] = all(result['hypotheses'][hypothesis] for results in pressures.values() for result in results.values())
    return {'checks': checks, 'port_nodes': cfg['port_nodes'], 'feedback_frequencies_hz': feedback,
            'nose_frequency_hz': cfg['frequency_hz'], 'pressures': pressures}


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
        middle, middle.bandwidth, middle.bandwidth.preceding, middle.bandwidth.preceding.averaged,
        steady, inlet, supra, prior, harmonic, velum, COUPLED, COUPLED.SHARED)),
        *(UPSTREAM / name for name in (velum.NETWORK, velum.VOICE, 'crates/chimera/src/voice/human_airway.rs',
          'crates/chimera/src/airway/frequency.rs', 'crates/chimera/tests/airway_adversarial.rs', 'Cargo.lock'))]
    details = {'case_id': case['id'], 'case_revision': case['measurement']['revision'], 'upstream_revision': revision,
               'invoked_from': str(Path.cwd())}
    return COUPLED.SHARED.record_measurement(
        args.run_id, CASE, inputs, details, measure, command=None, input_root=velum.screen.ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
