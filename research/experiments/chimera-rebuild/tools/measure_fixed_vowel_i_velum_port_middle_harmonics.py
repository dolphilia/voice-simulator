"""口蓋帆ポートに第7〜18倍音を加え、2,310 Hzの二次損失と鼻端放射を照合する。"""

import argparse
from pathlib import Path
import re
import subprocess

import numpy as np

import measure_fixed_vowel_i_velum_port_bandwidth as bandwidth
from upstream_baseline import UPSTREAM, WORKSPACE


CASE = WORKSPACE / 'cases/fixed-vowel-i-velum-port-middle-harmonics.json'
READ, COUPLED, pair = bandwidth.READ, bandwidth.COUPLED, bandwidth.pair
steady, inlet, supra, prior = bandwidth.steady, bandwidth.inlet, bandwidth.supra, bandwidth.prior
harmonic, velum = bandwidth.harmonic, bandwidth.velum
EVIDENCE = ()
MEASURED_HYPOTHESIS = 'measured_middle_harmonics_recover_half_of_excluded_loss'
PREDICTED_HYPOTHESIS = 'predicted_middle_harmonics_recover_half_of_loss_and_nose_error'


def archive_inputs(case):
    spec = case['measurement']['reference']
    record, manifest, definition = COUPLED.smoothing.verified_reference(
        {'run': spec['run'], 'case': 'fixed-vowel-i-velum-port-bandwidth', 'sha256': spec['manifest_sha256']},
        case['upstream_revision'])
    return {**bandwidth.archive_inputs(READ(definition)), 'port-bandwidth-manifest.json': manifest,
            'port-bandwidth-case.json': definition, 'port-bandwidth-summary.json': COUPLED.verified_path(record, 'summary.json')}


def retained_projection(actual, target):
    return float((actual * target.conjugate()).real / abs(target)**2)


def port_flow_from_admittance_update(cfg, frequencies, drive, nodes, branches, selected, source, mean, coefficients, slot):
    left, right = branches[selected, :2].astype(int).T
    incidence = np.zeros((len(nodes), len(selected)))
    incidence[left, np.arange(len(selected))] = 1.
    incidence[right, np.arange(len(selected))] = -1.
    extra_r = 2 * np.where(mean >= 0., *coefficients) * abs(mean)
    fs = cfg['internal_rate_hz']
    flow = []
    for frequency, injection_flow in zip(frequencies, drive):
        matrix, injection, _, _ = supra.forcing(frequency, fs, nodes, branches, selected, source)
        delay, impedance = inlet.frequency_factors(frequency, fs, branches[selected])
        admittance_change = delay / (impedance + extra_r) - delay / impedance
        pressure = np.linalg.solve(matrix + (incidence * admittance_change) @ incidence.T, injection_flow * injection)
        flow.append(delay * (incidence[:, slot] @ pressure) / (impedance[slot] + extra_r[slot]))
    return np.asarray(flow)


def evaluate_port(cfg, reference, layout, tracks, state, nodes, branches, source, added_frequencies):
    groups, selected = supra.selected_groups(layout, branches, source)
    if len(selected) != cfg['supraglottal_branch_count'] or len(groups['port']) != 1:
        raise ValueError('声門上と口蓋帆ポートの枝数が事前登録値と一致しません')
    port = int(groups['port'][0])
    slot = selected.tolist().index(port)
    if branches[port, :2].astype(int).tolist() != cfg['port_nodes'] or layout['velum_port_cm2'] != cfg['port_area_cm2']:
        raise ValueError('口蓋帆ポートの節点または開口面積が事前登録値と一致しません')
    coefficients = tuple(np.where(np.isin(selected, groups['sinus']), 0., value)
                         for value in prior.branch_coefficients(layout, branches[selected]))
    fs, frequency = cfg['internal_rate_hz'], cfg['frequency_hz']
    base_frequencies = cfg['frequencies_hz']
    glottal = tracks[harmonic.GLOTTIS][1:]
    length = len(glottal)
    if any(length * f % fs or not 0 < f < fs / 2 for f in (*base_frequencies, *added_frequencies)):
        raise ValueError('事前登録した周波数が観測窓の正の整数ビンに一致しません')
    samples = np.arange(length)
    base_phases = np.exp(2j * np.pi / fs * np.outer(samples, base_frequencies))
    added_phases = np.exp(2j * np.pi / fs * np.outer(samples, added_frequencies))
    base_basis, added_basis = base_phases.conj().T / length, added_phases.conj().T / length
    target_index = base_frequencies.index(frequency)
    target = base_basis[target_index]
    drive = base_basis @ glottal
    added_drive = added_basis @ glottal
    measured_nose = (target @ tracks['nose_flow_cm3_s'][1:]) / drive[target_index]

    model = nodes, branches, selected, coefficients
    mean, _, baseline = bandwidth.preceding.predict_waveform(cfg, source, model, float(glottal.mean()), base_phases, drive)
    predicted_added = np.asarray(steady.project_branch_flow(
        {**cfg, 'frequencies_hz': added_frequencies}, source, model, added_drive, mean))[:, slot]
    independent_added = port_flow_from_admittance_update(
        cfg, added_frequencies, added_drive, nodes, branches, selected, source, mean, coefficients, slot)
    observed = state[1:, layout['node_count'] + port]
    measured_added = added_basis @ observed
    measured_baseline = observed.mean() + 2 * (base_phases @ (base_basis @ observed)).real
    added_measured_flow = 2 * (added_phases @ measured_added).real
    flows = {
        'predicted': baseline[:, slot],
        'predicted_with_predicted_middle': baseline[:, slot] + 2 * (added_phases @ predicted_added).real,
        'predicted_with_measured_middle': baseline[:, slot] + added_measured_flow,
        'measured_selected_frequencies': measured_baseline,
        'measured_with_measured_middle': measured_baseline + added_measured_flow,
        'measured_full_band': observed,
    }
    flow_matrix = np.column_stack(list(flows.values()))
    losses = steady.kinetic_loss(flow_matrix, tuple(value[slot] for value in coefficients))
    pressures = dict(zip(flows, target @ losses))
    predicted_sources = target @ steady.kinetic_loss(baseline, coefficients)
    substitutions = np.repeat(predicted_sources[:, None], len(flows), axis=1)
    substitutions[slot] = list(pressures.values())
    matrix, injection, dipoles, nose = supra.forcing(frequency, fs, nodes, branches, selected, source)
    nose_ratios = (nose @ np.linalg.solve(matrix, drive[target_index] * injection[:, None] + dipoles @ substitutions)
                   / drive[target_index])
    gain = (np.linalg.solve(matrix.T, nose) @ dipoles[:, slot]) / drive[target_index]
    nose_errors = {name: float(abs(ratio / measured_nose - 1.)) for name, ratio in zip(flows, nose_ratios)}

    full = pressures['measured_full_band']
    measured_base = pressures['measured_selected_frequencies']
    predicted_base = pressures['predicted']
    measured_gain = pressures['measured_with_measured_middle'] - measured_base
    predicted_gain = pressures['predicted_with_predicted_middle'] - predicted_base
    hybrid_gain = pressures['predicted_with_measured_middle'] - predicted_base
    recovery = {
        'measured_middle_on_measured_base': retained_projection(measured_gain, full - measured_base),
        'predicted_middle_on_predicted_base': retained_projection(predicted_gain, full - predicted_base),
        'measured_middle_on_predicted_base': retained_projection(hybrid_gain, full - predicted_base),
    }
    nose_reduction = 1 - nose_errors['predicted_with_predicted_middle'] / nose_errors['predicted']
    measured_met = recovery['measured_middle_on_measured_base'] >= cfg['minimum_measured_projection_fraction']
    predicted_met = (recovery['predicted_middle_on_predicted_base'] >= cfg['minimum_predicted_projection_fraction']
                     and nose_reduction >= cfg['minimum_nose_error_reduction_fraction'])

    bins = np.array(added_frequencies) * length // fs
    fft = np.fft.rfft(observed)
    masked = np.zeros_like(fft)
    masked[bins] = fft[bins]
    extended_and_original = (
        ('predicted_with_predicted_middle', 'predicted'),
        ('predicted_with_measured_middle', 'predicted'),
        ('measured_with_measured_middle', 'measured_selected_frequencies'),
    )
    waveform_checks = {
        'measured_additions_match_inverse_fft': inlet.relative_l2(added_measured_flow, np.fft.irfft(masked, n=length)),
        'predicted_additions_match_admittance_update': inlet.relative_l2(predicted_added, independent_added),
        'additions_leave_original_coefficients_unchanged': max(
            inlet.relative_l2(base_basis @ flows[extended], base_basis @ flows[original])
            for extended, original in extended_and_original),
        'additions_leave_mean_flow_unchanged': max(
            float(abs(flows[extended].mean() / flows[original].mean() - 1.))
            for extended, original in extended_and_original),
        'loss_matches_fft': inlet.relative_l2(np.asarray(list(pressures.values())),
                                             np.fft.rfft(losses, axis=0)[frequency * length // fs] / length),
        'port_substitution_matches_nose_superposition': inlet.relative_l2(
            nose_ratios[1:] - nose_ratios[0], gain * (substitutions[slot, 1:] - predicted_base)),
    }
    previous = reference['conditions']
    reference_keys = ('predicted', 'measured_selected_frequencies', 'measured_full_band')
    reference_indices = [list(flows).index(key) for key in reference_keys]
    waveform_checks['reference_port_loss_matches'] = inlet.relative_l2(
        np.array([pressures[key] for key in reference_keys]),
        np.array([complex(*previous[key]['pressure_loss_dyn_cm2']) for key in reference_keys]))
    waveform_checks['reference_nose_transfers_match'] = inlet.relative_l2(
        nose_ratios[reference_indices], np.array([complex(*previous[key]['nose_transfer']) for key in reference_keys]))
    checks = {key: value < cfg['numerical_identity_relative_error_lt'] for key, value in waveform_checks.items()}
    checks['finite_inputs_and_outputs'] = bool(np.isfinite(flow_matrix).all() and np.isfinite(nose_ratios).all())
    reverse = observed < 0.
    return checks, {
        'samples': length,
        'conditions': {
            name: {'port_loss_dyn_cm2': pair(pressures[name]), 'nose_transfer': pair(ratio),
                   'nose_relative_error': nose_errors[name], 'port_mean_flow_cm3_s': float(flow.mean()),
                   'reverse_flow_mismatches': int(np.count_nonzero((flow < 0.) != reverse))}
            for (name, flow), ratio in zip(flows.items(), nose_ratios)},
        'middle_band': {
            'flow_coefficient_relative_l2_error': inlet.relative_l2(predicted_added, measured_added),
            'incremental_loss_measured_base_dyn_cm2': pair(measured_gain),
            'incremental_loss_predicted_base_dyn_cm2': pair(predicted_gain),
            'incremental_loss_hybrid_dyn_cm2': pair(hybrid_gain),
            'incremental_loss_prediction_vs_hybrid_relative_error': float(abs(predicted_gain - hybrid_gain) / abs(hybrid_gain)),
            'coefficients_cm3_s': [
                {'frequency_hz': f, 'glottal': pair(u), 'predicted': pair(p), 'measured': pair(m)}
                for f, u, p, m in zip(added_frequencies, added_drive, predicted_added, measured_added)]},
        'loss_recovery_projection_fraction': recovery,
        'predicted_nose_error_reduction_fraction': nose_reduction,
        'numerical_relative_errors': waveform_checks,
        'hypotheses': {MEASURED_HYPOTHESIS: measured_met, PREDICTED_HYPOTHESIS: predicted_met},
    }


def analyze(case, archive):
    cfg = case['measurement']
    before = READ(archive['port-bandwidth-case.json'])['measurement']
    frozen = ('pressure_cm_h2o', 'internal_rate_hz', 'frequency_hz', 'fundamental_hz', 'steady_window_internal_samples',
              'frequencies_hz', 'port_nodes', 'port_area_cm2', 'supraglottal_branch_count')
    if any(cfg[key] != before[key] for key in frozen):
        raise ValueError('肺圧、周波数、窓、または口蓋帆ポートが保存済みの実行と一致しません')
    added = [cfg['fundamental_hz'] * number for number in cfg['added_harmonics']]
    if not added or added != sorted(set(added)) or set(added).intersection(cfg['frequencies_hz']):
        raise ValueError('追加周波数は昇順の非重複の成分として指定してください')
    old_pressures = READ(archive['port-bandwidth-summary.json'])['pressures']
    low = {**archive, **{name: archive[f'low-{name}'] for name in inlet.lower.CAPTURE_INPUTS}}
    checks, pressures = {}, {}
    for pressure, inputs in (('reference', archive), ('lower', low)):
        if READ(inputs['natural-case.json'])['voice']['pressure_cm_h2o'] != cfg['pressure_cm_h2o'][pressure]:
            raise ValueError('収録時の肺圧が事前登録値と一致しません')
        layout, recordings = supra.recorded_editions(case, inputs)
        pressures[pressure] = {}
        for edition, recording in recordings.items():
            results, pressures[pressure][edition] = evaluate_port(
                cfg, old_pressures[pressure][edition], layout, *recording, added)
            checks.update({f'{pressure}/{edition}/{name}': answer for name, answer in results.items()})
        candidate, upstream = (pressures[pressure][edition] for edition in ('candidate', 'upstream'))
        comparison = [
            inlet.relative_l2(*(np.array([complex(*row[key]) for row in item['conditions'].values()])
                                for item in (candidate, upstream)))
            for key in ('port_loss_dyn_cm2', 'nose_transfer')]
        checks[f'{pressure}/both_editions_agree'] = (
            max(comparison) < cfg['edition_relative_error_lt'] and candidate['hypotheses'] == upstream['hypotheses'])
    for hypothesis in (MEASURED_HYPOTHESIS, PREDICTED_HYPOTHESIS):
        checks[hypothesis] = all(result['hypotheses'][hypothesis] for results in pressures.values() for result in results.values())
    return {'checks': checks, 'port_nodes': cfg['port_nodes'], 'added_frequencies_hz': added,
            'frequency_hz': cfg['frequency_hz'], 'pressures': pressures}


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
        bandwidth, bandwidth.preceding, bandwidth.preceding.averaged, steady, inlet, supra, prior,
        harmonic, velum, COUPLED, COUPLED.SHARED)),
        *(UPSTREAM / name for name in (velum.NETWORK, velum.VOICE, 'crates/chimera/src/voice/human_airway.rs',
          'crates/chimera/src/airway/frequency.rs', 'crates/chimera/tests/airway_adversarial.rs', 'Cargo.lock'))]
    details = {'case_id': case['id'], 'case_revision': case['measurement']['revision'], 'upstream_revision': revision,
               'invoked_from': str(Path.cwd())}
    return COUPLED.SHARED.record_measurement(
        args.run_id, CASE, inputs, details, measure, command=None, input_root=velum.screen.ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
