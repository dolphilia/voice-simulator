"""保存した咽頭流量の周波数対から2,310 Hzの圧力損失を推定する。"""

import argparse
from pathlib import Path
import re
import subprocess

import numpy as np

import measure_fixed_vowel_i_pharynx_mean_flow_tangent as preceding
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/fixed-vowel-i-pharynx-harmonic-pairs.json'
READ, COUPLED = preceding.READ, preceding.COUPLED
supra, prior, tangent = preceding.supra, preceding.prior, preceding.tangent
harmonic, velum = preceding.harmonic, preceding.velum
EVIDENCE = ()
HYPOTHESIS = 'three_pairs_with_reconstructed_reversal_remove_half_of_nose_error'


def archive_inputs(case):
    spec = case['measurement']['reference']
    run, header = record = COUPLED.run_manifest(
        spec['run'], 'fixed-vowel-i-pharynx-mean-flow-tangent', case['upstream_revision'])
    manifest = run / 'manifest.json'
    if header['status'] != 'fail' or sha256(manifest) != spec['manifest_sha256']:
        raise ValueError('事前登録した接線診断のマニフェストと一致しません')
    summary = COUPLED.verified_path(record, 'summary.json')
    if {name for name, answer in READ(summary)['checks'].items() if not answer} != {spec['known_failed_check']}:
        raise ValueError('前回の不成立判定と一致しません')
    entry, = (item for item in header['inputs'] if Path(item['path']).name == preceding.CASE.name)
    definition = run / header['source_snapshot'] / entry['path']
    if sha256(definition) != entry['sha256']:
        raise ValueError('保存済みの接線診断の条件と一致しません')
    return {**preceding.archive_inputs(READ(definition)), 'mean-flow-manifest.json': manifest,
            'mean-flow-case.json': definition, 'mean-flow-summary.json': summary}


def bins_for_case(cfg, count):
    fs = cfg['internal_rate_hz']

    def bin_for(frequency):
        index, leftover = divmod(frequency * count, fs)
        if leftover or abs(frequency) >= fs / 2:
            raise ValueError('測定周波数は観測窓で整数周期を含み、ナイキスト周波数未満である必要があります')
        return index

    target = bin_for(cfg['frequency_hz'])
    fundamental = bin_for(cfg['fundamental_hz'])
    pairs = [tuple(sorted(bin_for(frequency) for frequency in pair)) for pair in cfg['pairs_hz']]
    if (len(pairs) != 3 or len(set(pairs)) != len(pairs) or fundamental <= 0
            or any(left + right != target or left == 0 or right == 0 or left % fundamental or right % fundamental
                   for left, right in pairs)):
        raise ValueError('3組の異なる倍音対を2,310 Hzにそろえて指定してください')
    return target, fundamental, pairs


def candidate_sources(cfg, flow, coefficients):
    count = len(flow)
    target, fundamental, pairs = bins_for_case(cfg, count)
    phase = 2j * np.pi * np.arange(count) / count
    basis = np.exp(-target * phase) / count
    mean = flow.mean(axis=0)
    centered = flow - mean
    spectrum = np.fft.fft(centered, axis=0) / count
    forward, reverse = coefficients
    base = (2 * forward * mean) * spectrum[target]
    # 負の周波数も配列の末尾から参照できる。
    indices = np.arange(count)
    complements = (target - indices) % count
    all_products = spectrum * spectrum[complements]
    signed_bins = (indices + count // 2) % count - count // 2
    on_grid = signed_bins % fundamental == 0
    harmonic_products = all_products[on_grid & on_grid[complements]].sum(axis=0)
    pair_products = [(1 if left == right else 2) * spectrum[left] * spectrum[right] for left, right in pairs]
    selected_bins = sorted({target, *(abs(item) for pair in pairs for item in pair)})
    modes = np.exp(phase[:, None] * selected_bins)
    reconstructed = mean + 2 * (modes @ spectrum[selected_bins]).real
    measured_reversal = -(forward + reverse) * (basis @ np.where(flow < 0., flow**2, 0.))
    approximate_reversal = -(forward + reverse) * (basis @ np.where(reconstructed < 0., reconstructed**2, 0.))
    selected_square = forward * np.sum(pair_products, axis=0)
    pressures = {
        'observed_flow_tangent': base,
        'one_pair': base + forward * pair_products[0],
        'three_pairs': base + selected_square,
        'three_pairs_and_reconstructed_reversal': base + selected_square + approximate_reversal,
        'three_pairs_and_observed_reversal': base + selected_square + measured_reversal,
        'all_110hz_pairs_and_observed_reversal': base + forward * harmonic_products + measured_reversal,
        'all_fft_pairs_and_observed_reversal': base + forward * all_products.sum(axis=0) + measured_reversal,
    }
    direct = basis @ (np.where(flow >= 0., forward, reverse) * flow * abs(flow))
    reconstructed_direct = basis @ (np.where(reconstructed >= 0., forward, reverse) * reconstructed * abs(reconstructed))
    scale = abs(direct).max()
    errors = {
        'full_convolution_vs_time_square': float(abs(all_products.sum(axis=0) - basis @ centered**2).max()
                                                 / abs(basis @ centered**2).max()),
        'full_decomposition_vs_signed_loss': float(abs(pressures['all_fft_pairs_and_observed_reversal'] - direct).max() / scale),
        'selected_pairs_vs_reconstructed_signed_loss': float(
            abs(pressures['three_pairs_and_reconstructed_reversal'] - reconstructed_direct).max() / scale),
    }
    return basis, pressures, errors, measured_reversal, approximate_reversal, reconstructed


def inspect_edition(cfg, reference, layout, tracks, state, nodes, branches, source):
    groups, selected = supra.selected_groups(layout, branches, source)
    mask = np.isin(selected, groups['pharynx'])
    if int(mask.sum()) != cfg['pharynx_branch_count']:
        raise ValueError('事前登録した咽頭の枝数と一致しません')
    frequency, fs = cfg['frequency_hz'], cfg['internal_rate_hz']
    chosen = branches[selected]
    sinus = np.isin(selected, groups['sinus'])
    coefficients = tuple(np.where(sinus, 0., option) for option in prior.branch_coefficients(layout, chosen))
    flow = state[1:, layout['node_count'] + selected[mask]]
    basis, pressures, identity_errors, measured_reversal, estimate_reversal, reconstructed = candidate_sources(
        cfg, flow, tuple(value[mask] for value in coefficients))
    drive = basis @ tracks[harmonic.GLOTTIS][1:]
    measured_nose = (basis @ tracks['nose_flow_cm3_s'][1:]) / drive
    actual = prior.branch_pressure(frequency, fs, basis, state, layout, selected, branches, drive,
                                   coefficients=coefficients)['loss_per_drive']
    matrix, inlet, dipoles, nose = supra.forcing(frequency, fs, nodes, branches, selected, source)
    rhs = inlet + dipoles @ np.where(mask, 0., actual)
    nominal = nose @ np.linalg.solve(matrix, inlet + dipoles @ actual)
    responses = {
        name: nose @ np.linalg.solve(matrix, rhs + dipoles[:, mask] @ (value / drive))
        for name, value in pressures.items()
    }
    tolerance = cfg['numerical_identity_relative_error_lt']
    checks = {key: error < tolerance for key, error in identity_errors.items()}
    if reference is None:
        checks['full_convolution_matches_observed_loss_replay'] = bool(
            abs(responses['all_fft_pairs_and_observed_reversal'] - nominal) < tolerance * abs(measured_nose))
    else:
        archived_replay = complex(*reference['nose_transfer']['observed_loss_replay'])
        archived_tangent = complex(*reference['nose_transfer']['observed_flow_times_tangent'])
        checks['previous_tangent_and_full_replay_match'] = bool(
            abs(nominal - archived_replay) < tolerance * abs(measured_nose)
            and abs(responses['observed_flow_tangent'] - archived_tangent) < tolerance * abs(measured_nose)
            and abs(responses['all_fft_pairs_and_observed_reversal'] - archived_replay) < tolerance * abs(measured_nose))
    reversed_count = np.sum(flow < 0., axis=0)
    reconstructed_count = np.sum(reconstructed < 0., axis=0)
    correction_errors = np.abs(estimate_reversal - measured_reversal) / abs(drive)
    nose_errors = {name: float(abs(value - measured_nose) / abs(measured_nose)) for name, value in responses.items()}
    summary = {
        'nose_transfer': {name: tangent.pair(value) for name, value in responses.items()},
        'nose_relative_error': nose_errors,
        'nose_error_reduction_fraction': (
            1 - nose_errors['three_pairs_and_reconstructed_reversal'] / nose_errors['observed_flow_tangent']),
        'nose_amplitude_error_db': {name: float(20 * np.log10(abs(value / measured_nose)))
                                    for name, value in responses.items()},
        'nose_phase_error_deg': {name: float(np.angle(value / measured_nose, deg=True))
                                 for name, value in responses.items()},
        'pressure_relative_l2_error': {name: float(np.linalg.norm(value / drive - actual[mask])
                                                   / np.linalg.norm(actual[mask]))
                                       for name, value in pressures.items()},
        'identity_errors': identity_errors,
        'reversing_branches': {'observed': int(np.count_nonzero(reversed_count)),
                               'reconstructed': int(np.count_nonzero(reconstructed_count))},
        'reversal_sign_mismatch_samples_by_branch': np.sum((flow < 0.) != (reconstructed < 0.), axis=0).tolist(),
        'branches': [
            {'nodes': chosen[mask][slot, :2].astype(int).tolist(), 'observed_reverse_samples': int(count),
             'reconstructed_reverse_samples': int(reconstructed_count[slot]),
             'observed_reversal_per_drive': tangent.pair(measured_reversal[slot] / drive),
             'reconstructed_reversal_per_drive': tangent.pair(estimate_reversal[slot] / drive),
             'absolute_reversal_error_per_drive': float(correction_errors[slot]),
             'pressure_sources_per_drive': {name: tangent.pair(value[slot] / drive) for name, value in pressures.items()}}
            for slot, count in enumerate(reversed_count)
        ],
    }
    return checks, summary


def analyze(case, archive):
    cfg = case['measurement']
    previous = READ(archive['mean-flow-case.json'])['measurement']
    if (any(previous[key] != cfg[key] for key in ('internal_rate_hz', 'frequency_hz', 'steady_window_internal_samples'))
            or READ(archive['natural-case.json'])['voice']['f0_hz'] != cfg['fundamental_hz']):
        raise ValueError('記録済みの測定窓・周波数・基本周波数と一致しません')
    layout, recordings = supra.recorded_editions(case, archive)
    reference = READ(archive['mean-flow-summary.json'])['editions']
    checks, editions = {}, {}
    for name, recording in recordings.items():
        conditions, editions[name] = inspect_edition(cfg, reference[name], layout, *recording)
        checks.update({f'{name}/{key}': answer for key, answer in conditions.items()})
    transfers = [np.array([complex(*value) for value in edition['nose_transfer'].values()]) for edition in editions.values()]
    checks['nose_transfers_match_fixed_upstream'] = (
        harmonic.max_row_relative(transfers[0][None, :], transfers[1][None, :]) < cfg['edition_relative_error_lt'])
    decisions = [edition['nose_error_reduction_fraction'] >= cfg['minimum_nose_error_reduction_fraction']
                 for edition in editions.values()]
    checks['both_editions_agree_on_registered_prediction'] = decisions[0] == decisions[1]
    checks[HYPOTHESIS] = all(decisions)
    return {'checks': checks, 'frequency_hz': cfg['frequency_hz'], 'pairs_hz': cfg['pairs_hz'], 'editions': editions}


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
              *(Path(module.__file__) for module in (preceding, supra, prior, tangent, harmonic, velum, COUPLED, COUPLED.SHARED)),
              *(UPSTREAM / name for name in (velum.NETWORK, velum.VOICE, 'crates/chimera/src/voice/human_airway.rs',
                'crates/chimera/tests/airway_adversarial.rs', 'Cargo.lock'))]
    details = {'case_id': case['id'], 'case_revision': case['measurement']['revision'], 'upstream_revision': revision,
               'invoked_from': str(Path.cwd())}
    return COUPLED.SHARED.record_measurement(
        args.run_id, CASE, inputs, details, measure, command=None, input_root=velum.screen.ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
