"""観測した声門流量を入口にして、咽頭の複素枝流量を求める。"""

import argparse
from pathlib import Path
import re
import subprocess

import numpy as np

import measure_fixed_vowel_i_pharynx_reversal_low_harmonics as reversal
from upstream_baseline import UPSTREAM, WORKSPACE


CASE = WORKSPACE / 'cases/fixed-vowel-i-pharynx-from-glottal-flow.json'
READ, COUPLED = reversal.READ, reversal.COUPLED
lower, pairs, supra, prior = reversal.lower, reversal.pairs, reversal.supra, reversal.prior
harmonic, velum = reversal.harmonic, reversal.velum
EVIDENCE = ()
HYPOTHESIS = 'glottal_flow_predicts_pharyngeal_harmonics_and_reversal_in_both_pressures'
TANGENT = 'mean_flow_tangent'


def archive_inputs(case):
    spec = case['measurement']['reference']
    record, manifest, definition = COUPLED.smoothing.verified_reference(
        {'run': spec['run'], 'case': 'fixed-vowel-i-pharynx-reversal-low-harmonics', 'sha256': spec['manifest_sha256']},
        case['upstream_revision'])
    return {**reversal.archive_inputs(READ(definition)), 'reversal-manifest.json': manifest,
            'reversal-case.json': definition, 'reversal-summary.json': COUPLED.verified_path(record, 'summary.json')}


def relative_l2(actual, reference):
    return float(np.linalg.norm(actual - reference) / np.linalg.norm(reference))


def frequency_factors(frequency, fs, branches):
    delay = np.exp(-2j * np.pi * frequency / fs)
    inertia, resistance = branches[:, 3:].T
    return delay, resistance + inertia * fs * (1 - delay)


def branch_responses(frequency, fs, nodes, branches, selected, source, drive, losses):
    matrix, inlet, dipoles, _ = supra.forcing(frequency, fs, nodes, branches, selected, source)
    pressure = np.linalg.solve(matrix, drive * inlet[:, None] + dipoles @ losses.T).T
    chosen = branches[selected]
    left, right = chosen[:, :2].astype(int).T
    delay, impedance = frequency_factors(frequency, fs, chosen)
    return (delay * (pressure[:, left] - pressure[:, right]) - losses) / impedance


def branch_observations(selected, branches, state, coefficients, layout, fs, basis):
    node_count = layout['node_count']
    chosen = branches[selected]
    left, right = chosen[:, :2].astype(int).T
    pressure = state[:, left] - state[:, right]
    flow = state[:, node_count + selected]
    current = flow[1:]
    loss = np.where(current >= 0., *coefficients) * current * abs(current)
    # 先頭の前標本を含む、枝の慣性項と駆動圧の有限窓補正。
    edge = (chosen[:, 3] * fs * (flow[-1] - flow[0]) + pressure[-1] - pressure[0]) / len(current)
    return current, basis @ current, basis @ pressure[1:], basis @ loss + edge


def inspect_recording(cfg, reference, layout, tracks, state, nodes, branches, source):
    groups, selected = supra.selected_groups(layout, branches, source)
    pharynx = np.isin(selected, groups['pharynx'])
    if int(pharynx.sum()) != cfg['pharynx_branch_count']:
        raise ValueError('事前登録した咽頭の枝数と一致しません')
    first, end = cfg['steady_window_internal_samples']
    fs, frequencies = cfg['internal_rate_hz'], cfg['frequencies_hz']
    phases = np.exp(2j * np.pi / fs * np.outer(np.arange(end - first), frequencies))
    basis = phases.conj().T / (end - first)
    drive = basis @ tracks[harmonic.GLOTTIS][1:]
    chosen = branches[selected]
    sinus = np.isin(selected, groups['sinus'])
    coefficients = tuple(np.where(sinus, 0., values) for values in prior.branch_coefficients(layout, chosen))
    flow, measured, pressure, measured_sources = branch_observations(selected, branches, state, coefficients, layout, fs, basis)
    mean = flow.mean(axis=0)
    perturbed = branches.copy()
    perturbed[selected, 4] += 2 * np.where(mean >= 0., *coefficients) * abs(mean)
    zero = np.zeros(len(selected), dtype=complex)
    projections = {name: [] for name in ('viscous_only', TANGENT, 'observed_loss_control', 'measured')}
    local_errors = []
    for index, frequency in enumerate(frequencies):
        replay_source = measured_sources[index]
        viscous, replay = branch_responses(frequency, fs, nodes, branches, selected, source,
                                            drive[index], np.stack((zero, replay_source)))
        tangent, = branch_responses(frequency, fs, nodes, perturbed, selected, source, drive[index], zero[None, :])
        delay, impedance = frequency_factors(frequency, fs, chosen)
        local = (delay * pressure[index] - replay_source) / impedance
        local_errors.append(relative_l2(local, measured[index]))
        for name, values in (('viscous_only', viscous), (TANGENT, tangent),
                             ('observed_loss_control', replay), ('measured', measured[index])):
            projections[name].append(values[pharynx])
    projections = {name: np.asarray(values) for name, values in projections.items()}
    actual_reverse = flow[:, pharynx] < 0.
    reference_flow = projections['measured']
    pharynx_nodes = chosen[pharynx, :2].astype(int)
    target_branch, = np.flatnonzero((pharynx_nodes == (22, 23)).all(axis=1))
    scores = {}
    tangent_reverse = None
    for name, values in projections.items():
        reverse = mean[pharynx] + 2 * (phases @ values).real < 0.
        if name == TANGENT:
            tangent_reverse = reverse
        signs = reversal.reversal_metrics(actual_reverse, reverse)
        scores[name] = {
            'pharynx_relative_l2_error': relative_l2(values, reference_flow),
            'error_by_frequency': [relative_l2(value, expected) for value, expected in zip(values, reference_flow)],
            'reversal': signs,
            'mismatch_fraction': signs['samples']['mismatched'] / actual_reverse.size,
            'most_contributing_branch_flow_by_frequency': [pairs.tangent.pair(value) for value in values[:, target_branch]],
        }
    check_tangent = scores[TANGENT]
    decision = (check_tangent['pharynx_relative_l2_error'] <= cfg['maximum_pharynx_spectral_l2_error']
                and check_tangent['reversal']['branch_recall'] >= cfg['minimum_reversing_branch_recall']
                and check_tangent['mismatch_fraction'] <= cfg['maximum_sign_mismatch_fraction'])
    checks = {
        'observed_pressure_and_loss_obey_branch_equation': max(local_errors) < cfg['numerical_identity_relative_error_lt'],
        'observed_loss_control_reproduces_pharyngeal_flow': (
            scores['observed_loss_control']['pharynx_relative_l2_error'] < cfg['observed_loss_control_l2_error_lt']),
        'measured_ten_frequencies_reproduce_previous_reversal': (
            scores['measured']['reversal'] == reference['sign_added_low_harmonics']),
    }
    return checks, {
        'models': scores, 'model_hypothesis_met': decision,
        'local_branch_max_relative_error': max(local_errors),
        'branches': [
            {'nodes': pharynx_nodes[index].tolist(), 'mean_flow_cm3_s': float(average),
             'observed_reverse_samples': int(np.sum(actual_reverse[:, index])),
             'tangent_reverse_samples': int(np.sum(tangent_reverse[:, index]))}
            for index, average in enumerate(mean[pharynx])
        ],
    }, projections


def analyze(case, archive):
    cfg = case['measurement']
    old_case = READ(archive['reversal-case.json'])
    old = old_case['measurement']
    frozen = ('internal_rate_hz', 'frequency_hz', 'fundamental_hz', 'steady_window_internal_samples',
              'pressure_cm_h2o', 'pharynx_branch_count')
    components = {old['frequency_hz'], *(abs(f) for pair in old['pairs_hz'] for f in pair),
                  *(order * old['fundamental_hz'] for order in old['added_harmonic_orders'])}
    if any(cfg[key] != old[key] for key in frozen) or cfg['frequencies_hz'] != sorted(components):
        raise ValueError('前回の10周波数と観測条件が事前登録値に一致しません')
    previous = READ(archive['reversal-summary.json'])['pressures']
    low_archive = {**archive, **{name: archive[f'low-{name}'] for name in lower.CAPTURE_INPUTS}}
    checks, results = {}, {}
    for pressure, inputs in (('reference', archive), ('lower', low_archive)):
        if READ(inputs['natural-case.json'])['voice']['pressure_cm_h2o'] != cfg['pressure_cm_h2o'][pressure]:
            raise ValueError('保存した収録の肺圧が事前登録値と一致しません')
        layout, recorded = supra.recorded_editions(case, inputs)
        results[pressure], resolved = {}, {}
        for edition, recording in recorded.items():
            conditions, results[pressure][edition], resolved[edition] = inspect_recording(
                cfg, previous[pressure][edition], layout, *recording)
            checks.update({f'{pressure}/{edition}/{name}': answer for name, answer in conditions.items()})
        candidate, upstream = (results[pressure][name] for name in ('candidate', 'upstream'))
        checks[f'{pressure}/both_editions_agree'] = (
            max(relative_l2(resolved['candidate'][key], resolved['upstream'][key]) for key in resolved['candidate'])
            < cfg['edition_relative_error_lt']
            and candidate['models'][TANGENT]['reversal'] == upstream['models'][TANGENT]['reversal']
            and candidate['model_hypothesis_met'] == upstream['model_hypothesis_met'])
    checks[HYPOTHESIS] = all(result['model_hypothesis_met'] for pressure in results.values() for result in pressure.values())
    return {'checks': checks, 'frequencies_hz': cfg['frequencies_hz'], 'pressures': results}


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

    inputs = [CASE, Path(__file__), *archive.values(),
              *(Path(module.__file__) for module in (reversal, lower, pairs, supra, prior, harmonic, velum, COUPLED, COUPLED.SHARED)),
              *(UPSTREAM / name for name in (velum.NETWORK, velum.VOICE, 'crates/chimera/src/airway/frequency.rs',
                'crates/chimera/tests/airway_adversarial.rs', 'Cargo.lock'))]
    details = {'case_id': case['id'], 'case_revision': case['measurement']['revision'], 'upstream_revision': revision,
               'invoked_from': str(Path.cwd())}
    return COUPLED.SHARED.record_measurement(
        args.run_id, CASE, inputs, details, measure, command=None, input_root=velum.screen.ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
