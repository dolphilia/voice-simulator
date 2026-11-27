"""逆流用の流量波形に第3〜第6倍音を加え、両肺圧で照合する。"""

import argparse
from pathlib import Path
import re
import subprocess

import numpy as np

import measure_fixed_vowel_i_pharynx_harmonic_pairs_low_pressure as lower
from upstream_baseline import UPSTREAM, WORKSPACE


CASE = WORKSPACE / 'cases/fixed-vowel-i-pharynx-reversal-low-harmonics.json'
READ, COUPLED = lower.READ, lower.COUPLED
pairs, supra, prior, harmonic, velum = lower.pairs, lower.supra, lower.prior, lower.harmonic, lower.velum
EVIDENCE = ()
SIGN_HYPOTHESIS = 'low_harmonics_improve_reversal_in_both_pressures'
NOSE_HYPOTHESIS = 'nose_error_growth_within_limit_in_both_pressures'


def archive_inputs(case):
    spec = case['measurement']['reference']
    record, manifest, definition = COUPLED.smoothing.verified_reference(
        {'run': spec['run'], 'case': 'fixed-vowel-i-pharynx-harmonic-pairs-low-pressure', 'sha256': spec['manifest_sha256']},
        case['upstream_revision'])
    return {**lower.archive_inputs(READ(definition)), 'low-pressure-manifest.json': manifest,
            'low-pressure-case.json': definition, 'low-pressure-summary.json': COUPLED.verified_path(record, 'summary.json'),
            **{f'low-{name}': COUPLED.verified_path(record, f'artifacts/{name}') for name in lower.CAPTURE_INPUTS}}


def augmented_waveform(cfg, flow, original):
    count = len(flow)
    target, fundamental, selected_pairs = pairs.bins_for_case(cfg, count)
    selected = {target, *(abs(item) for pair in selected_pairs for item in pair)}
    added = [fundamental * order for order in cfg['added_harmonic_orders']]
    if (not added or len(set(added)) != len(added)
            or any(index <= 0 or index >= count / 2 or index in selected for index in added)):
        raise ValueError('追加する倍音は未選択でナイキスト周波数未満の異なる正周波数である必要があります')
    spectrum = np.fft.rfft(flow, axis=0)
    modes = np.exp(2j * np.pi / count * np.outer(np.arange(count), added))
    augmented = original + 2 * (modes @ (spectrum[added] / count)).real
    retained = sorted({0, *selected, *added})
    filtered = np.zeros_like(spectrum)
    filtered[retained] = spectrum[retained]
    independent = np.fft.irfft(filtered, n=count, axis=0)
    return augmented, independent


def reversal_metrics(actual, predicted):
    matches = (actual & predicted).sum(axis=0)
    missed = (actual & ~predicted).sum(axis=0)
    false = (~actual & predicted).sum(axis=0)
    actual_branches = actual.any(axis=0)
    predicted_branches = predicted.any(axis=0)
    branch_counts = {'true_positive': int(np.count_nonzero(actual_branches & predicted_branches)),
                     'missed': int(np.count_nonzero(actual_branches & ~predicted_branches)),
                     'false_positive': int(np.count_nonzero(~actual_branches & predicted_branches))}
    return {'samples': {'true_positive': int(matches.sum()), 'missed': int(missed.sum()), 'false_positive': int(false.sum()),
                        'mismatched': int((missed + false).sum())},
            'branches': branch_counts,
            'branch_recall': branch_counts['true_positive'] / int(np.count_nonzero(actual_branches)),
            'mismatched_samples_by_branch': (missed + false).tolist()}


def inspect_recording(cfg, reference, layout, tracks, state, nodes, branches, source):
    groups, selected = supra.selected_groups(layout, branches, source)
    mask = np.isin(selected, groups['pharynx'])
    if int(mask.sum()) != cfg['pharynx_branch_count']:
        raise ValueError('事前登録した咽頭の枝数と一致しません')
    frequency, fs = cfg['frequency_hz'], cfg['internal_rate_hz']
    chosen = branches[selected]
    sinus = np.isin(selected, groups['sinus'])
    coefficients = tuple(np.where(sinus, 0., value) for value in prior.branch_coefficients(layout, chosen))
    forward, reverse = (value[mask] for value in coefficients)
    flow = state[1:, layout['node_count'] + selected[mask]]
    basis, pressures, _, measured, old_correction, original = pairs.candidate_sources(cfg, flow, (forward, reverse))
    augmented, independent = augmented_waveform(cfg, flow, original)
    new_correction = -(forward + reverse) * (basis @ np.where(augmented < 0., augmented**2, 0.))
    independent_correction = -(forward + reverse) * (basis @ np.where(independent < 0., independent**2, 0.))
    drive = basis @ tracks[harmonic.GLOTTIS][1:]
    measured_nose = (basis @ tracks['nose_flow_cm3_s'][1:]) / drive
    actual = prior.branch_pressure(frequency, fs, basis, state, layout, selected, branches, drive,
                                   coefficients=coefficients)['loss_per_drive']
    matrix, inlet, dipoles, nose = supra.forcing(frequency, fs, nodes, branches, selected, source)
    forward_pressure = pressures['three_pairs']
    rhs = inlet + dipoles @ np.where(mask, 0., actual) + dipoles[:, mask] @ (forward_pressure / drive)
    responses = {
        name: nose @ np.linalg.solve(matrix, rhs + dipoles[:, mask] @ (correction / drive))
        for name, correction in (('original', old_correction), ('added_low_harmonics', new_correction), ('observed', measured))
    }
    tolerance = cfg['numerical_identity_relative_error_lt']
    delta = nose @ np.linalg.solve(matrix, dipoles[:, mask] @ ((new_correction - old_correction) / drive))
    baseline = reversal_metrics(flow < 0., original < 0.)
    modified = reversal_metrics(flow < 0., augmented < 0.)
    sign_reduction = 1 - modified['samples']['mismatched'] / baseline['samples']['mismatched']
    nose_errors = {key: float(abs(value - measured_nose) / abs(measured_nose)) for key, value in responses.items()}
    growth = nose_errors['added_low_harmonics'] / nose_errors['original'] - 1
    checks = {
        'prior_sign_and_nose_reproduced': bool(
            baseline['mismatched_samples_by_branch'] == reference['reversal_sign_mismatch_samples_by_branch']
            and abs(responses['original'] - complex(*reference['nose_transfer']['three_pairs_and_reconstructed_reversal']))
            < tolerance * abs(measured_nose)),
        'direct_wave_and_inverse_fft_match': bool(
            np.max(abs(augmented - independent)) < tolerance * np.max(abs(flow))
            and np.max(abs(new_correction - independent_correction)) < tolerance * np.max(abs(pressures['three_pairs']))),
        'only_reversal_pressure_changes_the_nose': bool(
            abs(responses['added_low_harmonics'] - responses['original'] - delta) < tolerance * abs(measured_nose)),
    }
    sign_pass = (sign_reduction >= cfg['minimum_mismatch_reduction_fraction']
                 and modified['branch_recall'] >= cfg['minimum_reversing_branch_recall']
                 and modified['branches']['false_positive'] < baseline['branches']['false_positive'])
    nose_pass = growth <= cfg['maximum_nose_error_growth_fraction']
    return checks, {
        'sign_baseline': baseline, 'sign_added_low_harmonics': modified,
        'sign_mismatch_reduction_fraction': sign_reduction, 'sign_hypothesis_met': sign_pass,
        'nose_relative_error': nose_errors, 'nose_error_growth_fraction': growth, 'nose_hypothesis_met': nose_pass,
        'nose_complex_transfer': {name: pairs.tangent.pair(value) for name, value in responses.items()},
        'reversal_pressure_relative_l2_error': {
            name: float(np.linalg.norm(correction - measured) / np.linalg.norm(measured))
            for name, correction in (('original', old_correction), ('added_low_harmonics', new_correction))
        },
        'branches': [
            {'nodes': chosen[mask][slot, :2].astype(int).tolist(), 'observed_reverse_samples': int(np.sum(flow[:, slot] < 0.)),
             'original_reverse_samples': int(np.sum(original[:, slot] < 0.)),
             'added_low_harmonics_reverse_samples': int(np.sum(augmented[:, slot] < 0.))}
            for slot in range(flow.shape[1])
        ],
    }


def analyze(case, archive):
    cfg = case['measurement']
    frozen = ('internal_rate_hz', 'frequency_hz', 'fundamental_hz', 'steady_window_internal_samples',
              'pairs_hz', 'pharynx_branch_count')
    for name in ('harmonic-pairs-case.json', 'low-pressure-case.json'):
        recorded = READ(archive[name])['measurement']
        if any(cfg[key] != recorded[key] for key in frozen):
            raise ValueError('事前登録した周波数対または測定条件が保存済みの実行と一致しません')
    lower_archive = {**archive, **{name: archive[f'low-{name}'] for name in lower.CAPTURE_INPUTS}}
    checks, results = {}, {}
    for pressure, inputs, prior_summary in (
        ('reference', archive, 'harmonic-pairs-summary.json'),
        ('lower', lower_archive, 'low-pressure-summary.json'),
    ):
        if READ(inputs['natural-case.json'])['voice']['pressure_cm_h2o'] != cfg['pressure_cm_h2o'][pressure]:
            raise ValueError('保存した収録の肺圧が事前登録値と一致しません')
        reference = READ(archive[prior_summary])['editions']
        layout, recorded = supra.recorded_editions(case, inputs)
        results[pressure] = {}
        for edition, recording in recorded.items():
            conditions, results[pressure][edition] = inspect_recording(cfg, reference[edition], layout, *recording)
            checks.update({f'{pressure}/{edition}/{name}': answer for name, answer in conditions.items()})
        candidate, upstream = (results[pressure][name] for name in ('candidate', 'upstream'))
        responses = np.array([
            [complex(*value) for value in edition['nose_complex_transfer'].values()] for edition in (candidate, upstream)])
        checks[f'{pressure}/both_editions_agree'] = (
            candidate['sign_added_low_harmonics'] == upstream['sign_added_low_harmonics']
            and candidate['sign_hypothesis_met'] == upstream['sign_hypothesis_met']
            and candidate['nose_hypothesis_met'] == upstream['nose_hypothesis_met']
            and harmonic.max_row_relative(responses[:1], responses[1:]) < cfg['edition_relative_error_lt'])
    checks[SIGN_HYPOTHESIS] = all(result['sign_hypothesis_met'] for pressure in results.values() for result in pressure.values())
    checks[NOSE_HYPOTHESIS] = all(result['nose_hypothesis_met'] for pressure in results.values() for result in pressure.values())
    return {'checks': checks, 'frequency_hz': cfg['frequency_hz'], 'added_harmonic_orders': cfg['added_harmonic_orders'],
            'pressures': results}


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
              *(Path(module.__file__) for module in (lower, pairs, supra, prior, harmonic, velum, COUPLED, COUPLED.SHARED)),
              *(UPSTREAM / name for name in (velum.NETWORK, velum.VOICE,
                'crates/chimera/tests/airway_adversarial.rs', 'Cargo.lock'))]
    details = {'case_id': case['id'], 'case_revision': case['measurement']['revision'], 'upstream_revision': revision,
               'invoked_from': str(Path.cwd())}
    return COUPLED.SHARED.record_measurement(
        args.run_id, CASE, inputs, details, measure, command=None, input_root=velum.screen.ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
