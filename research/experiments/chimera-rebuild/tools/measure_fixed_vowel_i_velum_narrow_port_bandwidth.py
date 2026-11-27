"""狭い口蓋帆ポートの2,310 Hz損失残差を、平均と2つの周波数群に分ける。"""

import argparse
from itertools import permutations
from pathlib import Path
import re
import subprocess

import numpy as np

import measure_fixed_vowel_i_velum_narrow_port_feedback as narrow
from upstream_baseline import UPSTREAM, WORKSPACE


CASE = WORKSPACE / 'cases/fixed-vowel-i-velum-narrow-port-bandwidth.json'
READ, COUPLED = narrow.READ, narrow.COUPLED
feedback, supra, inlet, prior, velum = narrow.feedback, narrow.supra, narrow.inlet, narrow.prior, narrow.velum
steady, harmonic, pair = feedback.steady, feedback.harmonic, feedback.pair
EVIDENCE = ()
FACTORS = ('mean_flow', 'included_harmonics', 'excluded_frequencies')
CONDITIONS = (
    'predicted', 'measured_mean', 'measured_coefficients', 'measured_mean_and_coefficients',
    'measured_excluded', 'measured_mean_and_excluded', 'measured_coefficients_and_excluded', 'measured_full_band',
)
HYPOTHESIS = 'excluded_frequencies_explain_half_of_narrow_port_loss_residual'


def archive_inputs(case):
    spec = case['measurement']['reference']
    record, manifest, definition = COUPLED.smoothing.verified_reference(
        {'run': spec['run'], 'case': 'fixed-vowel-i-velum-narrow-port-feedback', 'sha256': spec['manifest_sha256']},
        case['upstream_revision'])
    files = (*narrow.CAPTURE_FILES, 'linear-inspect.json', *(f'linear-upstream/{name}' for name in narrow.NETWORK_FILES))
    return {**narrow.archive_inputs(READ(definition)), 'narrow-bandwidth-reference-manifest.json': manifest,
            'narrow-bandwidth-reference-case.json': definition,
            'narrow-bandwidth-reference-summary.json': COUPLED.verified_path(record, 'summary.json'),
            **{f'narrow-{name}': COUPLED.verified_path(record, f'artifacts/{name}') for name in files}}


def factor_changes(values):
    changes = []
    for order in permutations(range(len(FACTORS))):
        contributions = np.zeros(len(FACTORS), dtype=complex)
        mask = 0
        for factor in order:
            next_mask = mask | (1 << factor)
            contributions[factor] = values[next_mask] - values[mask]
            mask = next_mask
        changes.append(contributions)
    return np.array(changes)


def projection_fraction(change, residual):
    return (change * residual.conjugate()).real / abs(residual)**2


def evaluate(cfg, before, layout, recording):
    tracks, state, nodes, branches, source = recording
    groups, selected = supra.selected_groups(layout, branches, source)
    if len(selected) != cfg['supraglottal_branch_count'] or len(groups['port']) != 1:
        raise ValueError('声門上と口蓋帆ポートの枝数が事前登録値と一致しません')
    port = int(groups['port'][0])
    slot = selected.tolist().index(port)
    if branches[port, :2].astype(int).tolist() != cfg['port_nodes'] or layout['velum_port_cm2'] != cfg['port_area_cm2']:
        raise ValueError('ポートの節点または開口面積が事前登録値と一致しません')
    sinus = np.isin(selected, groups['sinus'])
    coefficients = tuple(np.where(sinus, 0., value) for value in prior.branch_coefficients(layout, branches[selected]))
    port_k = tuple(value[slot] for value in coefficients)
    model = nodes, branches, selected, coefficients
    fs, frequency = cfg['internal_rate_hz'], cfg['frequency_hz']
    fundamental = cfg['fundamental_hz']
    fixed_frequencies = cfg['frequencies_hz']
    added = [fundamental * h for h in cfg['added_harmonics']]
    frequencies = sorted(fixed_frequencies + added)
    if frequencies != [fundamental * h for h in range(1, 23)]:
        raise ValueError('基準と追加成分を合わせた周波数が第1〜22倍音と一致しません')
    glottal = tracks[harmonic.GLOTTIS][1:]
    length = len(glottal)
    if length * fundamental % fs:
        raise ValueError('観測窓に基本周波数の整数周期が必要です')
    samples = np.arange(length)
    base_phases = np.exp(2j * np.pi / fs * np.outer(samples, fixed_frequencies))
    added_phases = np.exp(2j * np.pi / fs * np.outer(samples, added))
    base_basis, added_basis = base_phases.conj().T / length, added_phases.conj().T / length
    target_index = fixed_frequencies.index(frequency)
    target = base_basis[target_index]
    drive = base_basis @ glottal
    target_drive = drive[target_index]
    observed_nose = (target @ tracks['nose_flow_cm3_s'][1:]) / target_drive

    mean, predicted, wave_ten = feedback.middle.bandwidth.preceding.predict_waveform(
        cfg, source, model, float(glottal.mean()), base_phases, drive)
    extra = np.asarray(steady.project_branch_flow(
        {**cfg, 'frequencies_hz': added}, source, model, added_basis @ glottal, mean))
    baseline = wave_ten[:, slot] + 2 * (added_phases @ extra[:, slot]).real
    full_flow = state[1:, layout['node_count'] + port]
    observed_mean = float(full_flow.mean())
    observed_base = base_basis @ full_flow
    observed_added = added_basis @ full_flow
    observed_band = observed_mean + 2 * ((base_phases @ observed_base) + (added_phases @ observed_added)).real
    mean_delta = np.full(length, observed_mean - mean[slot])
    harmonic_delta = 2 * (base_phases @ (observed_base - predicted[:, slot])
                          + added_phases @ (observed_added - extra[:, slot])).real
    excluded = full_flow - observed_band
    changes = np.column_stack((mean_delta, harmonic_delta, excluded))
    flags = ((np.arange(len(CONDITIONS))[None, :] >> np.arange(len(FACTORS))[:, None]) & 1)
    waves = baseline[:, None] + changes @ flags

    observed_fft = np.fft.rfft(full_flow)
    harmonic_bins = np.arange(0, fs // 2 + 1, fundamental) * length // fs
    band_fft = np.zeros_like(observed_fft)
    band_fft[harmonic_bins[:23]] = observed_fft[harmonic_bins[:23]]
    harmonic_fft = np.zeros_like(observed_fft)
    harmonic_fft[harmonic_bins] = observed_fft[harmonic_bins]
    all_harmonics = np.fft.irfft(harmonic_fft, n=length)
    waves_and_harmonics = np.column_stack((waves, all_harmonics))
    losses = steady.kinetic_loss(waves_and_harmonics, port_k)
    port_sources = target @ losses
    baseline_source = port_sources[0]
    full_source = port_sources[len(CONDITIONS) - 1]
    residual = full_source - baseline_source

    observed_pressure = prior.branch_pressure(frequency, fs, target, state, layout, selected, branches, 1.,
                                              coefficients=coefficients)
    window = observed_pressure['window_edge_per_drive']
    measured_sources = observed_pressure['loss_per_drive'] + window
    fixed_sources = target @ steady.kinetic_loss(wave_ten, coefficients)
    substitutions = np.repeat(fixed_sources[:, None], len(port_sources) + 2, axis=1)
    substitutions[slot, :-1] = np.append(port_sources, full_source + window[slot])
    substitutions[:, -1] = measured_sources
    matrix, injection, dipoles, nose = supra.forcing(frequency, fs, nodes, branches, selected, source)
    responses = (nose @ np.linalg.solve(matrix, target_drive * injection[:, None] + dipoles @ substitutions)) / target_drive
    gain = (np.linalg.solve(matrix.T, nose) @ dipoles) / target_drive
    source_orders = factor_changes(port_sources[:len(CONDITIONS)])
    nose_orders = factor_changes(responses[:len(CONDITIONS)])
    sequence, averaged = source_orders[0], source_orders.mean(axis=0)
    nose_residual = observed_nose - responses[0]
    windowed_port_delta = responses[-2] - responses[0]
    group_delta = {name: pair(np.sum((gain * (measured_sources - substitutions[:, 0]))[np.isin(selected, edges)]))
                   for name, edges in groups.items()}
    decomposition = {
        'registered_order': dict(zip(FACTORS, map(pair, sequence))),
        'average_of_six_orders': dict(zip(FACTORS, map(pair, averaged))),
    }
    projected = {name: dict(zip(FACTORS, map(float, projection_fraction(change, residual))))
                 for name, change in (('registered_order', sequence), ('average_of_six_orders', averaged))}
    nose_projected = {name: dict(zip(FACTORS, map(float, projection_fraction(change, nose_residual))))
                      for name, change in (('registered_order', nose_orders[0]), ('average_of_six_orders', nose_orders.mean(axis=0)))}
    numerics = {
        'full_band_reconstructed_from_three_changes': inlet.relative_l2(waves[:, -1], full_flow),
        'network_and_dedicated_port_flow_match': inlet.relative_l2(full_flow, tracks[velum.PORT[1]][1:]),
        'observed_22_harmonics_match_inverse_fft': inlet.relative_l2(observed_band, np.fft.irfft(band_fft, n=length)),
        'paired_loss_coefficients_match_fft': inlet.relative_l2(
            port_sources, np.fft.rfft(losses, axis=0)[frequency * length // fs] / length),
        'full_band_loss_matches_pressure_balance': float(
            abs(full_source / observed_pressure['loss_from_pressure_per_drive'][slot] - 1.)),
        'all_orders_reconstruct_source_difference': float(np.max(abs(source_orders.sum(axis=1) - residual)) / abs(residual)),
        'all_orders_reconstruct_nose_change': float(
            np.max(abs(nose_orders.sum(axis=1) - (responses[len(CONDITIONS) - 1] - responses[0]))) / abs(nose_residual)),
        'branch_superposition_matches_direct_nose_solve': inlet.relative_l2(
            responses[1:] - responses[0], gain @ (substitutions[:, 1:] - substitutions[:, :1])),
        'baseline_matches_narrow_port_archive': float(abs(responses[0] / complex(*before['conditions']['tangent']['nose_transfer']) - 1.)),
    }
    checks = {name: error < cfg['numerical_identity_relative_error_lt'] for name, error in numerics.items()}
    nose_errors = abs(responses / observed_nose - 1.)
    checks['measured_full_network_reproduces_observed_nose'] = bool(nose_errors[-1] < cfg['observed_full_network_nose_relative_error_lt'])
    checks['finite_waveforms_and_nose_transfers'] = bool(np.isfinite(waves_and_harmonics).all() and np.isfinite(responses).all())
    high_harmonic_change = port_sources[-1] - port_sources[CONDITIONS.index('measured_mean_and_coefficients')]
    other_change = full_source - port_sources[-1]
    return checks, {
        'conditions': {
            name: {'port_mean_flow_cm3_s': float(waves_and_harmonics[:, j].mean()),
                   'reverse_flow_samples': int(np.count_nonzero(waves_and_harmonics[:, j] < 0.)),
                   'port_loss_dyn_cm2': pair(port_sources[j]), 'nose_transfer': pair(responses[j]),
                   'nose_relative_error': float(nose_errors[j])}
            for j, name in enumerate((*CONDITIONS, 'measured_mean_and_all_integer_harmonics'))},
        'port_residual_dyn_cm2': pair(residual),
        'loss_changes_dyn_cm2': decomposition,
        'port_loss_residual_projection_fractions': projected,
        'nose_residual_projection_fractions': nose_projected,
        'excluded_component_projection_fractions': {
            'integer_harmonics_above_22': float(projection_fraction(high_harmonic_change, high_harmonic_change + other_change)),
            'nonharmonic_bins': float(projection_fraction(other_change, high_harmonic_change + other_change))},
        'port_with_window_nose_relative_error': float(nose_errors[-2]),
        'port_with_window_nose_residual_change_ratio': pair(windowed_port_delta / nose_residual),
        'measured_full_network_nose_relative_error': float(nose_errors[-1]),
        'observed_source_nose_transfer_change_by_group': group_delta,
        'numerical_relative_errors': numerics,
        'hypothesis_met': all(
            item['excluded_frequencies'] >= cfg['minimum_excluded_projection_fraction'] for item in projected.values()),
    }


def analyze(case, archive):
    cfg = case['measurement']
    previous_case = READ(archive['narrow-bandwidth-reference-case.json'])['measurement']
    frozen = ('pressure_cm_h2o', 'internal_rate_hz', 'frequency_hz', 'fundamental_hz', 'steady_window_internal_samples',
              'frequencies_hz', 'added_harmonics', 'port_nodes', 'port_area_cm2', 'supraglottal_branch_count')
    if any(cfg[key] != previous_case[key] for key in frozen):
        raise ValueError('肺圧、開口、周波数または窓が保存済み実行と一致しません')
    selected_inputs = {**archive, **{name: archive[f'narrow-{name}'] for name in narrow.CAPTURE_FILES},
                       'archive-linear-inspect.json': archive['narrow-linear-inspect.json'],
                       **{f'archive-{name}': archive[f'narrow-linear-upstream/{name}'] for name in narrow.NETWORK_FILES}}
    layout, recordings = supra.recorded_editions(case, selected_inputs)
    before = READ(archive['narrow-bandwidth-reference-summary.json'])['editions']
    checks, editions = {}, {}
    for edition, recording in recordings.items():
        results, editions[edition] = evaluate(cfg, before[edition], layout, recording)
        checks.update({f'{edition}/{name}': passed for name, passed in results.items()})
    candidate, upstream = (editions[name] for name in ('candidate', 'upstream'))
    agreement = [
        inlet.relative_l2(*(np.array([complex(*row[key]) for row in item['conditions'].values()])
                            for item in (candidate, upstream)))
        for key in ('port_loss_dyn_cm2', 'nose_transfer')]
    checks['both_editions_agree'] = (
        max(agreement) < cfg['edition_relative_error_lt'] and candidate['hypothesis_met'] == upstream['hypothesis_met'])
    checks[HYPOTHESIS] = all(detail['hypothesis_met'] for detail in editions.values())
    return {'checks': checks, 'port_area_cm2': cfg['port_area_cm2'], 'frequency_hz': cfg['frequency_hz'], 'editions': editions}


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

    preceding = feedback.middle.bandwidth.preceding
    inputs = [CASE, Path(__file__), *archive.values(), *(Path(module.__file__) for module in (
        narrow, feedback, preceding, preceding.averaged, steady, inlet, supra, prior, harmonic, velum, COUPLED, COUPLED.SHARED)),
        *(UPSTREAM / name for name in (velum.NETWORK, velum.VOICE, 'crates/chimera/src/voice/human_airway.rs',
          'crates/chimera/src/airway/frequency.rs', 'crates/chimera/tests/airway_adversarial.rs', 'Cargo.lock'))]
    details = {'case_id': case['id'], 'case_revision': case['measurement']['revision'], 'upstream_revision': revision,
               'invoked_from': str(Path.cwd())}
    return COUPLED.SHARED.record_measurement(
        args.run_id, CASE, inputs, details, measure, command=None, input_root=velum.screen.ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
