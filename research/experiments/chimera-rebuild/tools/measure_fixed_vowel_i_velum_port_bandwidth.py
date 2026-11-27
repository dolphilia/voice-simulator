"""固定 /i/ の口蓋帆ポートで、選んだ周波数帯が二次損失の予測に与える影響を測る。"""

import argparse
from pathlib import Path
import re
import subprocess

import numpy as np

import measure_fixed_vowel_i_pharynx_predicted_radiation as preceding
from upstream_baseline import UPSTREAM, WORKSPACE


CASE = WORKSPACE / 'cases/fixed-vowel-i-velum-port-bandwidth.json'
READ, COUPLED, pair = preceding.READ, preceding.COUPLED, preceding.pair
steady, inlet, supra, prior = preceding.steady, preceding.inlet, preceding.supra, preceding.prior
harmonic, velum = preceding.harmonic, preceding.velum
EVIDENCE = ()
HYPOTHESIS = 'excluded_frequencies_explain_at_least_half_of_port_loss_residual'


def archive_inputs(case):
    spec = case['measurement']['reference']
    record, manifest, definition = COUPLED.smoothing.verified_reference(
        {'run': spec['run'], 'case': 'fixed-vowel-i-pharynx-predicted-radiation', 'sha256': spec['manifest_sha256']},
        case['upstream_revision'])
    return {**preceding.archive_inputs(READ(definition)), 'predicted-radiation-manifest.json': manifest,
            'predicted-radiation-case.json': definition,
            'predicted-radiation-summary.json': COUPLED.verified_path(record, 'summary.json')}


def evaluate_port(cfg, reference, layout, tracks, state, nodes, branches, source):
    groups, selected = supra.selected_groups(layout, branches, source)
    if len(selected) != cfg['supraglottal_branch_count'] or len(groups['port']) != 1:
        raise ValueError('声門上と口蓋帆ポートの枝数が事前登録値と一致しません')
    port = int(groups['port'][0])
    slot = selected.tolist().index(port)
    if branches[port, :2].astype(int).tolist() != cfg['port_nodes'] or layout['velum_port_cm2'] != cfg['port_area_cm2']:
        raise ValueError('口蓋帆ポートの節点または開口面積が事前登録値と一致しません')
    sinus = np.isin(selected, groups['sinus'])
    coefficients = tuple(np.where(sinus, 0., value) for value in prior.branch_coefficients(layout, branches[selected]))

    fs, frequency = cfg['internal_rate_hz'], cfg['frequency_hz']
    frequencies = cfg['frequencies_hz']
    target_index = frequencies.index(frequency)
    glottal = tracks[harmonic.GLOTTIS][1:]
    length = len(glottal)
    if any(length * value % fs for value in frequencies):
        raise ValueError('観測窓が選択した周波数の整数周期を含みません')
    bins = np.array(frequencies) * length // fs
    phases = np.exp(2j * np.pi / fs * np.outer(np.arange(length), frequencies))
    basis = phases.conj().T / length
    target = basis[target_index]
    drive = basis @ glottal
    target_drive = drive[target_index]
    measured_nose = (target @ tracks['nose_flow_cm3_s'][1:]) / target_drive

    model = nodes, branches, selected, coefficients
    _, predicted, waveform = preceding.predict_waveform(cfg, source, model, float(glottal.mean()), phases, drive)
    predicted_sources = target @ steady.kinetic_loss(waveform, coefficients)
    full_flow = state[1:, layout['node_count'] + port]
    measured_coefficients = basis @ full_flow
    mean_flow = float(full_flow.mean())
    flows = np.column_stack((waveform[:, slot], mean_flow + 2 * (phases @ predicted[:, slot]).real,
                             mean_flow + 2 * (phases @ measured_coefficients).real, full_flow))
    conditions = ('predicted', 'measured_mean', 'measured_selected_frequencies', 'measured_full_band')
    full_fft = np.fft.rfft(full_flow)
    selected_fft = np.zeros_like(full_fft)
    selected_fft[0], selected_fft[bins] = full_fft[0], full_fft[bins]
    fft_flow = np.fft.irfft(selected_fft, n=length)

    loss = steady.kinetic_loss(flows, tuple(option[slot] for option in coefficients))
    sources = target @ loss
    source_differences = sources[:-1] - sources[1:]
    residual = sources[0] - sources[-1]
    fractions = (source_differences * residual.conjugate()).real / abs(residual)**2
    effects = ('mean_flow', 'selected_frequency_coefficients', 'excluded_frequencies')
    pressure = prior.branch_pressure(frequency, fs, target, state, layout, selected, branches, 1.,
                                     coefficients=coefficients)
    observed_source = pressure['loss_per_drive'][slot]
    window_source = pressure['window_edge_per_drive'][slot]

    matrix, injection, dipoles, nose = supra.forcing(frequency, fs, nodes, branches, selected, source)
    substituted_sources = np.repeat(predicted_sources[:, None], len(conditions) + 1, axis=1)
    substituted_sources[slot] = np.append(sources, sources[-1] + window_source)
    responses = nose @ np.linalg.solve(matrix, target_drive * injection[:, None] + dipoles @ substituted_sources)
    responses /= target_drive
    gain = (np.linalg.solve(matrix.T, nose) @ dipoles[:, slot]) / target_drive
    previous_residual = reference['largest_nose_contribution_error']
    previous_nose = complex(*reference['nose_transfer']['full_predicted_loss'])
    numerical_errors = {
        'network_and_port_flow_traces_agree': inlet.relative_l2(full_flow, tracks[velum.PORT[1]][1:]),
        'selected_waveform_matches_inverse_fft': inlet.relative_l2(flows[:, 2], fft_flow),
        'loss_terms_match_fft': inlet.relative_l2(sources, np.fft.rfft(loss, axis=0)[bins[target_index]] / length),
        'measured_loss_matches_branch_equation': float(abs(sources[-1] - observed_source) / abs(observed_source)),
        'decomposition_reconstructs_complex_error': float(abs(source_differences.sum() - residual) / abs(residual)),
        'nose_superposition_matches_direct_solve': inlet.relative_l2(
            responses[0] - responses[1:], gain * (sources[0] - substituted_sources[slot, 1:])),
        'all_predicted_nose_matches_reference': float(abs(responses[0] - previous_nose) / abs(previous_nose)),
        'port_nose_error_with_window_matches_reference': float(
            abs(responses[0] - responses[-1] - complex(*previous_residual['nose_transfer_error']))
            / abs(complex(*previous_residual['nose_transfer_error']))),
    }
    checks = {name: error < cfg['numerical_identity_relative_error_lt'] for name, error in numerical_errors.items()}
    checks['port_nose_error_with_window_matches_reference'] &= previous_residual['nodes'] == cfg['port_nodes']
    return checks, {
        'port_loss_coefficients': [float(option[slot]) for option in coefficients],
        'samples': length,
        'conditions': {
            name: {'mean_flow_cm3_s': float(flows[:, idx].mean()), 'reverse_flow_samples': int((flows[:, idx] < 0.).sum()),
                   'pressure_loss_dyn_cm2': pair(sources[idx]), 'nose_transfer': pair(responses[idx]),
                   'nose_relative_error': float(abs(responses[idx] / measured_nose - 1.))}
            for idx, name in enumerate(conditions)},
        'predicted_vs_measured_selected_flow_relative_error': inlet.relative_l2(predicted[:, slot], measured_coefficients),
        'loss_difference_dyn_cm2': dict(zip(effects, map(pair, source_differences))),
        'residual_projection_fraction': dict(zip(effects, map(float, fractions))),
        'window_edge_source_dyn_cm2': pair(window_source),
        'nose_transfer_with_port_window_edge': pair(responses[-1]),
        'nose_relative_error_with_port_window_edge': float(abs(responses[-1] / measured_nose - 1.)),
        'numerical_relative_errors': numerical_errors,
        'hypothesis_met': bool(fractions[-1] >= cfg['minimum_bandwidth_projection_fraction']),
    }


def analyze(case, archive):
    cfg = case['measurement']
    before = READ(archive['predicted-radiation-case.json'])['measurement']
    frozen = ('pressure_cm_h2o', 'internal_rate_hz', 'frequency_hz', 'fundamental_hz', 'steady_window_internal_samples',
              'frequencies_hz', 'supraglottal_branch_count')
    if any(cfg[key] != before[key] for key in frozen):
        raise ValueError('肺圧、周波数、観測窓が保存済みの実行と一致しません')
    saved = READ(archive['predicted-radiation-summary.json'])['pressures']
    low = {**archive, **{name: archive[f'low-{name}'] for name in inlet.lower.CAPTURE_INPUTS}}
    checks, pressures = {}, {}
    for pressure, inputs in (('reference', archive), ('lower', low)):
        if READ(inputs['natural-case.json'])['voice']['pressure_cm_h2o'] != cfg['pressure_cm_h2o'][pressure]:
            raise ValueError('収録時の肺圧が事前登録値と一致しません')
        layout, recordings = supra.recorded_editions(case, inputs)
        pressures[pressure] = {}
        for edition, recording in recordings.items():
            conditions, pressures[pressure][edition] = evaluate_port(cfg, saved[pressure][edition], layout, *recording)
            checks.update({f'{pressure}/{edition}/{key}': answer for key, answer in conditions.items()})
        candidate, upstream = (pressures[pressure][edition] for edition in ('candidate', 'upstream'))
        losses = [np.array([complex(*row['pressure_loss_dyn_cm2']) for row in result['conditions'].values()])
                  for result in (candidate, upstream)]
        transfers = [np.array([complex(*row['nose_transfer']) for row in result['conditions'].values()])
                     for result in (candidate, upstream)]
        checks[f'{pressure}/both_editions_agree'] = (
            max(inlet.relative_l2(*losses), inlet.relative_l2(*transfers)) < cfg['edition_relative_error_lt']
            and candidate['hypothesis_met'] == upstream['hypothesis_met'])
    checks[HYPOTHESIS] = all(result['hypothesis_met'] for group in pressures.values() for result in group.values())
    return {'checks': checks, 'frequency_hz': cfg['frequency_hz'], 'port_nodes': cfg['port_nodes'], 'pressures': pressures}


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
                cwd=UPSTREAM, stdout=out / 'upstream-pressure-loss-test.log')
        return analyze(case, archive)

    inputs = [CASE, Path(__file__), *archive.values(), *(Path(module.__file__) for module in (
        preceding, preceding.averaged, steady, inlet, supra, prior, harmonic, velum, COUPLED, COUPLED.SHARED)),
        *(UPSTREAM / name for name in (velum.NETWORK, velum.VOICE, 'crates/chimera/src/voice/human_airway.rs',
          'crates/chimera/src/airway/frequency.rs', 'crates/chimera/tests/airway_adversarial.rs', 'Cargo.lock'))]
    details = {'case_id': case['id'], 'case_revision': case['measurement']['revision'], 'upstream_revision': revision,
               'invoked_from': str(Path.cwd())}
    return COUPLED.SHARED.record_measurement(
        args.run_id, CASE, inputs, details, measure, command=None, input_root=velum.screen.ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
