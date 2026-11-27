"""口蓋帆ポートの上位倍音と他60枝の圧力源を独立に切り替える。"""

import argparse
from pathlib import Path
import re
import subprocess

import numpy as np

import measure_fixed_vowel_i_velum_wide_port_upper_harmonics as wide
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/fixed-vowel-i-velum-wide-port-nose-source-swap.json'
READ, COUPLED = wide.READ, wide.COUPLED
upper, supra, inlet, velum, pair = wide.upper, wide.supra, wide.inlet, wide.velum, wide.pair
feedback, prior, steady = upper.feedback, upper.prior, upper.steady
EVIDENCE = ()
HYPOTHESIS = 'observed_other_branch_sources_reverse_upper_harmonics_nose_error_change'
SOURCE_MODELS = ('predicted', 'observed')
PORT_BANDS = ('low_only', 'measured_upper')


def archive_inputs(case):
    spec = case['measurement']['reference']
    run, header = record = COUPLED.smoothing.run_manifest(spec['run'], wide.CASE.stem, case['upstream_revision'])
    manifest = run / 'manifest.json'
    summary = COUPLED.verified_path(record, 'summary.json')
    rejected = {name for name, passed in READ(summary)['checks'].items() if not passed}
    if sha256(manifest) != spec['manifest_sha256'] or header['status'] != 'fail' or rejected != {wide.RECOVERY_HYPOTHESIS}:
        raise ValueError('先行実行のマニフェストと不成立の判定が登録値と一致しません')
    entry, = (item for item in header['inputs'] if Path(item['path']).name == wide.CASE.name)
    definition = run / header['source_snapshot'] / entry['path']
    if sha256(definition) != entry['sha256']:
        raise ValueError('先行実行の保存ケースがマニフェストと一致しません')
    return {**wide.archive_inputs(READ(definition)), 'wide-upper-case.json': definition,
            'wide-upper-manifest.json': manifest, 'wide-upper-summary.json': summary}


def port_sources(cfg, mean, observed_flow, coefficients, reference):
    n = len(observed_flow)
    fundamental, fs = cfg['fundamental_hz'], cfg['internal_rate_hz']
    lower_rows = reference['lower']['feedback_frequencies']
    upper_rows = reference['upper']['feedback_frequencies']
    if [row['frequency_hz'] for row in lower_rows + upper_rows] != [fundamental * j for j in range(1, 45)]:
        raise ValueError('保存した第1〜44倍音の周波数が一致しません')
    frequencies = np.array([row['frequency_hz'] for row in lower_rows + upper_rows])
    if (frequencies * n % fs).any() or not 0 < frequencies[0] < frequencies[-1] < fs / 2:
        raise ValueError('第1〜44倍音が観測窓の正の整数ビンと一致しません')
    low, high = np.split(frequencies * n // fs, [len(lower_rows)])
    flow_fft = np.fft.rfft(observed_flow) / n
    lower = np.array([complex(*row['port_flow_cm3_s'][upper.PREDICTED]) for row in lower_rows])
    archived_upper = np.array([complex(*row['measured_port_flow_cm3_s']) for row in upper_rows])
    spectra = np.zeros((len(flow_fft), 2), dtype=complex)
    spectra[0] = mean
    spectra[low] = lower[:, None]
    spectra[high, 1] = flow_fft[high]
    waves = np.fft.irfft(spectra * n, n=n, axis=0)
    losses = steady.kinetic_loss(waves, coefficients)
    target_bin = cfg['frequency_hz'] * n // fs
    values = np.fft.rfft(losses, axis=0)[target_bin] / n
    archived_loss = np.array([
        complex(*reference['upper']['conditions'][name]['port_loss_at_nose_frequency_dyn_cm2'])
        for name in (upper.LOW_ONLY, feedback.MEASURED_COEFFICIENTS)])
    return values, {
        'measured_upper_flow_matches_archived_coefficients': inlet.relative_l2(flow_fft[high], archived_upper),
        'port_mean_and_22_lower_coefficients_preserved': inlet.relative_l2(
            np.fft.rfft(waves, axis=0)[np.r_[0, low]] / n, spectra[np.r_[0, low]]),
        'port_sources_match_archived_losses': inlet.relative_l2(values, archived_loss),
    }


def observed_sources(frequency, fs, basis, state, layout, selected, branches, coefficients):
    pressure = prior.branch_pressure(frequency, fs, basis, state, layout, selected, branches, 1.,
                                     coefficients=coefficients)
    window = pressure['window_edge_per_drive']
    sources = pressure['loss_per_drive'] + window
    edges = branches[selected]
    left, right = edges[:, :2].astype(int).T
    inertia, resistance = edges[:, 3:].T
    flow = state[:, layout['node_count'] + selected]
    pressure_drop = state[:, left] - state[:, right]
    # 同じ圧力源を幾何の損失係数を使わず、枝の圧力・流量の差分から復元する。
    from_balance = pressure_drop[:-1] - resistance * flow[1:] - inertia * fs * np.diff(flow, axis=0)
    n = len(basis)
    endpoint = (inertia * fs * (flow[-1] - flow[0]) + pressure_drop[-1] - pressure_drop[0]) / n
    from_fft = np.fft.rfft(from_balance, axis=0)[frequency * n // fs] / n + endpoint
    return sources, inlet.relative_l2(from_fft, sources)


def compare_effects(transfers, observed, groups, selected, by_edge, minimum_change):
    residuals = transfers / observed - 1.
    errors = abs(residuals)
    port_delta = (transfers[:, 1] - transfers[:, 0]) / observed
    other_delta = (transfers[1, 0] - transfers[0, 0]) / observed
    projection = 2. * (residuals[:, 0].conj() * port_delta).real
    delta_power = abs(port_delta)**2
    squared_error_change = errors[:, 1]**2 - errors[:, 0]**2
    interaction = float(2. * (other_delta.conj() * port_delta[0]).real)
    error_change = errors[:, 1] - errors[:, 0]
    by_group = {}
    for name, edges in groups.items():
        if name == 'port':
            continue
        change = by_edge[np.isin(selected, edges)].sum()
        by_group[name] = {
            'nose_transfer_change': pair(change),
            'squared_error_interaction': float(2. * ((change / observed).conj() * port_delta[0]).real),
        }
    tests = {
        'same_complex_port_effect_with_either_other_source': float(abs(port_delta[1] / port_delta[0] - 1.)),
        'squared_error_change_matches_projection_and_magnitude': inlet.relative_l2(projection + delta_power,
                                                                                 squared_error_change),
        'squared_error_interaction_matches_complex_cross_term': float(
            abs(interaction - np.diff(squared_error_change)[0]) / np.linalg.norm(squared_error_change)),
        'branch_groups_reconstruct_complex_other_source_change': float(
            abs(by_edge.sum() / observed - other_delta) / max(abs(other_delta), abs(port_delta[0]))),
    }
    return tests, {
        'conditions': {
            other: {port: {'nose_transfer': pair(transfers[i, j]), 'relative_residual': pair(residuals[i, j]),
                           'nose_relative_error': float(errors[i, j])} for j, port in enumerate(PORT_BANDS)}
            for i, other in enumerate(SOURCE_MODELS)},
        'relative_nose_change_from_port_upper': pair(port_delta[0]),
        'relative_nose_change_from_other_branches': pair(other_delta),
        'port_upper_error_effect': {
            other: {'nose_relative_error_change': float(error_change[i]), 'projection_term': float(projection[i]),
                    'squared_magnitude_term': float(delta_power[i]), 'squared_error_change': float(squared_error_change[i])}
            for i, other in enumerate(SOURCE_MODELS)},
        'squared_error_interaction': interaction,
        'other_branch_contributions': by_group,
        'hypothesis': bool(error_change[0] > minimum_change and error_change[1] < -minimum_change),
    }


def evaluate(cfg, layout, recording, reference, archived_mean):
    tracks, state, nodes, branches, source = recording
    groups, selected = supra.selected_groups(layout, branches, source)
    port, = groups['port']
    slot, = np.flatnonzero(selected == port)
    if (len(selected) != cfg['supraglottal_branch_count']
            or branches[port, :2].astype(int).tolist() != cfg['port_nodes']
            or layout['velum_port_cm2'] != cfg['port_area_cm2']):
        raise ValueError('声門上の枝数または口蓋帆ポートが事前登録値と一致しません')
    sinus = np.isin(selected, groups['sinus'])
    coefficients = tuple(np.where(sinus, 0., k) for k in prior.branch_coefficients(layout, branches[selected]))
    model = nodes, branches, selected, coefficients
    fs, frequency = cfg['internal_rate_hz'], cfg['frequency_hz']
    glottal = tracks[upper.harmonic.GLOTTIS][1:]
    freqs = cfg['frequencies_hz']
    target = freqs.index(frequency)
    phases = np.exp(2j * np.pi / fs * np.outer(np.arange(len(glottal)), freqs))
    basis = phases.conj().T / len(glottal)
    drives = basis @ glottal
    target_basis, drive = basis[target], drives[target]
    observed = (target_basis @ tracks['nose_flow_cm3_s'][1:]) / drive
    mean, _, wave_ten = upper.preceding.predict_waveform(cfg, source, model, float(glottal.mean()), phases, drives)
    predicted = target_basis @ steady.kinetic_loss(wave_ten, coefficients)
    measured, pressure_error = observed_sources(frequency, fs, target_basis, state, layout, selected, branches, coefficients)
    port_loss, numerical = port_sources(
        cfg, mean[slot], state[1:, layout['node_count'] + port],
        tuple(k[slot] for k in coefficients), reference)

    # 最後の列は全61枝を観測へ置き換える対照。先頭4列のポートは平均と補正済み低域をそろえる。
    pressures = np.column_stack((predicted, predicted, measured, measured, measured))
    pressures[slot, :4] = np.tile(port_loss, len(SOURCE_MODELS))
    matrix, injection, dipoles, nose = supra.forcing(frequency, fs, nodes, branches, selected, source)
    response = (nose @ np.linalg.solve(matrix, drive * injection[:, None] + dipoles @ pressures)) / drive
    readout = np.linalg.solve(matrix.T, nose)
    gain = (readout @ dipoles) / drive
    changes = gain * (measured - predicted)
    changes[slot] = 0.
    tests, detail = compare_effects(response[:4].reshape(2, 2), observed, groups, selected, changes,
                                    cfg['minimum_nose_relative_error_change'])
    archived_transfer = np.array([
        complex(*reference['upper']['conditions'][name]['nose_transfer'])
        for name in (upper.LOW_ONLY, feedback.MEASURED_COEFFICIENTS)])
    measured_error = float(abs(response[-1] / observed - 1.))
    numerical.update(tests)
    numerical.update({
        'archived_mean_reproduced': float(abs(mean[slot] / archived_mean - 1.)),
        'observed_pressure_sources_match_branch_balance_fft': pressure_error,
        'predicted_other_sources_match_archived_nose_transfers': inlet.relative_l2(response[:2], archived_transfer),
        'all_conditions_match_transpose_solution': inlet.relative_l2(response, readout @ injection + gain @ pressures),
    })
    checks = {name: error < cfg['numerical_identity_relative_error_lt'] for name, error in numerical.items()}
    checks['full_measured_sources_reproduce_nose_transfer'] = measured_error < cfg['full_measured_sources_nose_relative_error_lt']
    return checks, {
        **detail, 'port_sources_dyn_cm2': dict(zip(PORT_BANDS, map(pair, port_loss))),
        'recorded_nose_transfer': pair(observed), 'all_measured_source_control': {
            'nose_transfer': pair(response[-1]), 'nose_relative_error': measured_error},
        'numerical_relative_errors': numerical,
    }


def analyze(case, archive):
    cfg = case['measurement']
    previous = READ(archive['wide-upper-case.json'])['measurement']
    frozen = (*wide.MODEL_SETTINGS, 'pressure_cm_h2o', 'port_area_cm2')
    if any(cfg[key] != previous[key] for key in frozen if key != 'added_harmonics'):
        raise ValueError('肺圧、開口、周波数または観測窓が先行実行と一致しません')
    wide.verify_settings(previous, archive)
    layout, recordings = supra.recorded_editions(case, archive)
    prior_results = READ(archive['wide-upper-summary.json'])['editions']
    middle = READ(archive['middle-harmonics-summary.json'])['pressures']['reference']
    checks, editions = {}, {}
    for edition, recording in recordings.items():
        mean = middle[edition]['conditions']['predicted_with_predicted_middle']['port_mean_flow_cm3_s']
        local, editions[edition] = evaluate(cfg, layout, recording, prior_results[edition], mean)
        checks.update({f'{edition}/{name}': value for name, value in local.items()})
    candidate, upstream = (editions[edition] for edition in ('candidate', 'upstream'))
    comparisons = [
        np.array([complex(*condition['relative_residual'])
                  for model in edition['conditions'].values() for condition in model.values()])
        for edition in (candidate, upstream)]
    checks['both_editions_agree'] = (
        inlet.relative_l2(*comparisons) < cfg['edition_relative_error_lt']
        and candidate['hypothesis'] == upstream['hypothesis'])
    checks[HYPOTHESIS] = all(detail['hypothesis'] for detail in editions.values())
    return {'checks': checks, 'editions': editions, 'frequency_hz': cfg['frequency_hz'], 'port_area_cm2': cfg['port_area_cm2']}


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
        wide, upper, feedback, prior, steady, upper.preceding, upper.preceding.averaged, upper.harmonic,
        inlet, supra, velum, COUPLED, COUPLED.SHARED)),
        *(UPSTREAM / name for name in (velum.NETWORK, velum.VOICE, 'crates/chimera/src/voice/human_airway.rs',
          'crates/chimera/src/airway/frequency.rs', 'crates/chimera/tests/airway_adversarial.rs', 'Cargo.lock'))]
    details = {'case_id': case['id'], 'case_revision': case['measurement']['revision'], 'upstream_revision': revision,
               'invoked_from': str(Path.cwd())}
    return COUPLED.SHARED.record_measurement(
        args.run_id, CASE, inputs, details, measure, command=None, input_root=velum.screen.ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
