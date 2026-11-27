"""声門の平均流量から定常分流を求め、咽頭の倍音と逆流を照合する。"""

import argparse
from pathlib import Path
import re
import subprocess

import numpy as np
from scipy.optimize import brentq, root

import measure_fixed_vowel_i_pharynx_from_glottal_flow as inlet
from upstream_baseline import UPSTREAM, WORKSPACE


CASE = WORKSPACE / 'cases/fixed-vowel-i-pharynx-steady-flow.json'
READ, COUPLED = inlet.READ, inlet.COUPLED
supra, prior, harmonic, velum = inlet.supra, inlet.prior, inlet.harmonic, inlet.velum
EVIDENCE = ()
DC_HYPOTHESIS = 'steady_flow_reproduces_measured_averages_and_outlet_split'
AC_HYPOTHESIS = 'predicted_means_preserve_pharyngeal_harmonics_and_reversal'


def archive_inputs(case):
    spec = case['measurement']['reference']
    record, manifest, definition = COUPLED.smoothing.verified_reference(
        {'run': spec['run'], 'case': 'fixed-vowel-i-pharynx-from-glottal-flow', 'sha256': spec['manifest_sha256']},
        case['upstream_revision'])
    return {**inlet.archive_inputs(READ(definition)), 'glottal-flow-manifest.json': manifest,
            'glottal-flow-case.json': definition, 'glottal-flow-summary.json': COUPLED.verified_path(record, 'summary.json')}


def outlet_paths(edges, source):
    """入口から口端と鼻端への、向きを含む経路を列にする。"""
    adjacent = {}
    for index, (left, right) in enumerate(edges):
        adjacent.setdefault(left, []).append((right, index, 1.))
        adjacent.setdefault(right, []).append((left, index, -1.))
    start = source['inject']
    parents = {start: None}
    pending = [start]
    while pending:
        node = pending.pop()
        for neighbor, edge, direction in adjacent[node]:
            if neighbor not in parents:
                parents[neighbor] = node, edge, direction
                pending.append(neighbor)
    if len(parents) != len(edges) + 1 or len(parents) != len(adjacent):
        raise ValueError('声門上の定常分流には連結した木を指定してください')
    paths = np.zeros((len(edges), 2))
    for column, name in enumerate(('lips', 'nose')):
        node = source[name]
        while node != start:
            parent, edge, direction = parents[node]
            paths[edge, column] = direction
            node = parent
    return paths


def kinetic_loss(flow, coefficients):
    return np.where(flow >= 0., *coefficients) * flow * abs(flow)


def solve_split(paths, total, resistance, coefficients):
    difference = paths[:, 0] - paths[:, 1]
    nasal_only = total * paths[:, 1]

    def equal_pressure(lip_flow):
        flow = nasal_only + lip_flow * difference
        return difference @ (resistance * flow + kinetic_loss(flow, coefficients))

    oral = brentq(equal_pressure, 0., total, xtol=1e-12)
    outlets = np.array([oral, total - oral])
    return paths @ outlets, outlets


def solve_pressures(edges, source, total, resistance, coefficients):
    """自由節点の圧力から各枝の流量を逆算し、質量保存を解く。"""
    free = sorted(set(edges.ravel()) - {source['lips'], source['nose']})
    incidence = np.zeros((max(edges.ravel()) + 1, len(edges)))
    left, right = edges.T
    incidence[left, np.arange(len(edges))] = 1.
    incidence[right, np.arange(len(edges))] = -1.
    free_incidence = incidence[free]
    rhs = np.zeros(len(free))
    rhs[free.index(source['inject'])] = total

    def flow_at(pressure):
        drop = free_incidence.T @ pressure
        loss = np.where(drop >= 0., *coefficients)
        return 2 * drop / (resistance + np.sqrt(resistance**2 + 4 * loss * abs(drop)))

    def residual(pressure):
        return free_incidence @ flow_at(pressure) - rhs

    def jacobian(pressure):
        flow = flow_at(pressure)
        k = np.where(flow >= 0., *coefficients)
        conductance = 1 / (resistance + 2 * k * abs(flow))
        return (free_incidence * conductance) @ free_incidence.T

    guess = np.linalg.solve((free_incidence / resistance) @ free_incidence.T, rhs)
    solution = root(residual, guess, jac=jacobian, method='hybr', options={'xtol': 1e-12})
    conservation_error = float(np.linalg.norm(residual(solution.x)) / abs(total))
    return flow_at(solution.x), conservation_error, float(solution.x[free.index(source['inject'])])


def average_loss_control(paths, total, resistance, coefficients, inertia, flow, pressure, source, fs):
    current = flow[1:]
    average_kinetic = kinetic_loss(current, coefficients).mean(axis=0)
    momentum = inertia * fs * (flow[-1] - flow[0]) / len(current)
    mean_pressure = pressure[:-1].mean(axis=0)
    end_pressure = np.array([mean_pressure[source['lips']], mean_pressure[source['nose']]])
    difference = paths[:, 0] - paths[:, 1]
    nasal_only = total * paths[:, 1]
    oral = (end_pressure[1] - end_pressure[0] - difference @ (
        resistance * nasal_only + average_kinetic + momentum)) / (difference @ (resistance * difference))
    return paths @ [oral, total - oral], average_kinetic, momentum, end_pressure


def project_branch_flow(cfg, source, model, drive, mean):
    fs, frequencies = cfg['internal_rate_hz'], cfg['frequencies_hz']
    nodes, branches, selected, coefficients = model
    zero_sources = np.zeros((1, len(selected)), dtype=complex)
    adjusted = branches.copy()
    adjusted[selected, 4] += 2 * np.where(mean >= 0., *coefficients) * abs(mean)
    return [
        inlet.branch_responses(frequency, fs, nodes, adjusted, selected, source, drive[index], zero_sources)[0]
        for index, frequency in enumerate(frequencies)]


def harmonic_comparison(cfg, source, model, pharynx, drive, phases, flow, observed, means):
    models, projections = {}, {}
    actual_reverse = flow[:, pharynx] < 0.
    for key, mean in means.items():
        predicted = np.array([value[pharynx] for value in project_branch_flow(cfg, source, model, drive, mean)])
        projections[key] = predicted
        signal = mean[pharynx] + 2 * (phases @ predicted).real
        signs = inlet.reversal.reversal_metrics(actual_reverse, signal < 0.)
        models[key] = {'pharynx_relative_l2_error': inlet.relative_l2(predicted, observed),
                       'error_by_frequency': [inlet.relative_l2(value, target) for value, target in zip(predicted, observed)],
                       'reversal': signs, 'mismatch_fraction': signs['samples']['mismatched'] / actual_reverse.size}
    return models, projections


def inspect_edition(cfg, reference, layout, tracks, state, nodes, branches, source):
    groups, selected = supra.selected_groups(layout, branches, source)
    pharynx = np.isin(selected, groups['pharynx'])
    if len(selected) != cfg['supraglottal_branch_count'] or int(pharynx.sum()) != cfg['pharynx_branch_count']:
        raise ValueError('声門上と咽頭の枝数が事前登録値と一致しません')
    chosen = branches[selected]
    sinus = np.isin(selected, groups['sinus'])
    coefficients = tuple(np.where(sinus, 0., item) for item in prior.branch_coefficients(layout, chosen))
    edges = chosen[:, :2].astype(int)
    inertia, resistance = chosen[:, 3:].T
    paths = outlet_paths(edges, source)
    node_count = layout['node_count']
    flow = state[:, node_count + selected]
    observed_mean = flow[1:].mean(axis=0)
    glottal_flow = tracks[harmonic.GLOTTIS][1:]
    total = float(glottal_flow.mean())
    predicted, outlet_flow = solve_split(paths, total, resistance, coefficients)
    independent, conservation, inlet_pressure = solve_pressures(edges, source, total, resistance, coefficients)
    fs = cfg['internal_rate_hz']
    control, mean_kinetic, momentum, end_pressure = average_loss_control(
        paths, total, resistance, coefficients, inertia, flow, state[:, :node_count], source, fs)
    measured_outlets = np.array([tracks[field][1:].mean() for field in ('lip_flow_cm3_s', 'nose_flow_cm3_s')])
    measured_at_exits = np.array([
        np.sum(observed_mean[edges[:, 1] == source[name]]) - np.sum(observed_mean[edges[:, 0] == source[name]])
        for name in ('lips', 'nose')])
    outlet_error = abs(outlet_flow - measured_outlets) / abs(measured_outlets)
    mean_error = inlet.relative_l2(predicted, observed_mean)
    control_error = inlet.relative_l2(control, observed_mean)
    bias = (paths[:, 0] - paths[:, 1]) @ (mean_kinetic - kinetic_loss(observed_mean, coefficients))
    phases = np.exp(2j * np.pi / fs * np.outer(np.arange(len(glottal_flow)), cfg['frequencies_hz']))
    basis = phases.conj().T / len(glottal_flow)
    models, projections = harmonic_comparison(
        cfg, source, (nodes, branches, selected, coefficients), pharynx, basis @ glottal_flow, phases,
        flow[1:], basis @ flow[1:, pharynx], {'measured_branch_means': observed_mean, 'steady_branch_means': predicted})
    result = models['steady_branch_means']
    tolerance = cfg['numerical_identity_relative_error_lt']
    previous = reference['models'][inlet.TANGENT]
    checks = {
        'independent_steady_solutions_and_conservation_agree': (
            inlet.relative_l2(predicted, independent) < tolerance and conservation < tolerance),
        'observed_loss_control_reproduces_mean_flow': control_error < cfg['observed_loss_control_relative_error_lt'],
        'branch_outflows_match_measured_outlets': (
            inlet.relative_l2(measured_at_exits, measured_outlets) < cfg['observed_loss_control_relative_error_lt']),
        'observed_mean_reproduces_prior_ac_result': (
            abs(models['measured_branch_means']['pharynx_relative_l2_error'] - previous['pharynx_relative_l2_error']) < tolerance
            and models['measured_branch_means']['reversal'] == previous['reversal']),
    }
    return checks, {
        'mean_glottal_flow_cm3_s': total, 'steady_inlet_pressure_dyn_cm2': inlet_pressure,
        'mean_flow_l2_error': mean_error, 'mean_control_l2_error': control_error,
        'free_node_conservation_relative_error': conservation,
        'oral_and_nasal_mean_flow_cm3_s': {'observed': measured_outlets.tolist(), 'steady': outlet_flow.tolist()},
        'outlet_relative_error': outlet_error.tolist(),
        'path_loss_difference_due_to_averaging_dyn_cm2': float(bias),
        'terminal_mean_pressures_dyn_cm2': end_pressure.tolist(),
        'path_momentum_end_effect_dyn_cm2': float((paths[:, 0] - paths[:, 1]) @ momentum),
        'ac_models': models,
        'dc_hypothesis_met': bool(mean_error <= cfg['maximum_mean_l2_error']
                                  and outlet_error.max() <= cfg['maximum_outlet_relative_error']),
        'ac_hypothesis_met': (result['pharynx_relative_l2_error'] <= cfg['maximum_pharynx_spectral_l2_error']
                              and result['reversal']['branches']['missed'] == 0
                              and result['reversal']['branches']['false_positive'] == 0
                              and result['mismatch_fraction'] <= cfg['maximum_sign_mismatch_fraction']),
        'branch_averages': [
            {'nodes': pair.tolist(), 'observed_cm3_s': float(measured), 'predicted_cm3_s': float(steady),
             'observed_loss_control_cm3_s': float(average_control)}
            for pair, measured, steady, average_control in zip(edges, observed_mean, predicted, control, strict=True)
        ],
    }, projections


def analyze(case, archive):
    cfg = case['measurement']
    previous = READ(archive['glottal-flow-case.json'])['measurement']
    frozen = ('internal_rate_hz', 'frequency_hz', 'fundamental_hz', 'steady_window_internal_samples',
              'frequencies_hz', 'pressure_cm_h2o', 'pharynx_branch_count')
    if any(cfg[key] != previous[key] for key in frozen):
        raise ValueError('事前登録した肺圧・周波数・観測窓が保存済みの実行と一致しません')
    saved = READ(archive['glottal-flow-summary.json'])['pressures']
    low = {**archive, **{name: archive[f'low-{name}'] for name in inlet.lower.CAPTURE_INPUTS}}
    checks, pressures = {}, {}
    for pressure, inputs in (('reference', archive), ('lower', low)):
        if READ(inputs['natural-case.json'])['voice']['pressure_cm_h2o'] != cfg['pressure_cm_h2o'][pressure]:
            raise ValueError('収録時の肺圧が事前登録値と一致しません')
        layout, recordings = supra.recorded_editions(case, inputs)
        pressures[pressure], spectra = {}, {}
        for edition, recording in recordings.items():
            conditions, pressures[pressure][edition], spectra[edition] = inspect_edition(
                cfg, saved[pressure][edition], layout, *recording)
            checks.update({f'{pressure}/{edition}/{key}': answer for key, answer in conditions.items()})
        candidate, upper = (pressures[pressure][edition] for edition in ('candidate', 'upstream'))
        checks[f'{pressure}/both_editions_agree'] = (
            max(inlet.relative_l2(spectra['candidate'][key], spectra['upstream'][key]) for key in spectra['candidate'])
            < cfg['edition_relative_error_lt']
            and candidate['ac_models']['steady_branch_means']['reversal'] == upper['ac_models']['steady_branch_means']['reversal']
            and all(candidate[key] == upper[key] for key in ('dc_hypothesis_met', 'ac_hypothesis_met')))
    checks[DC_HYPOTHESIS] = all(result['dc_hypothesis_met'] for group in pressures.values() for result in group.values())
    checks[AC_HYPOTHESIS] = all(result['ac_hypothesis_met'] for group in pressures.values() for result in group.values())
    return {'checks': checks, 'frequencies_hz': cfg['frequencies_hz'], 'pressures': pressures}


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
              *(Path(module.__file__) for module in (inlet, inlet.reversal, supra, prior, harmonic, velum, COUPLED, COUPLED.SHARED)),
              *(UPSTREAM / name for name in (velum.NETWORK, velum.VOICE, 'crates/chimera/src/voice/human_airway.rs',
                'crates/chimera/tests/airway_adversarial.rs', 'Cargo.lock'))]
    details = {'case_id': case['id'], 'case_revision': case['measurement']['revision'], 'upstream_revision': revision,
               'invoked_from': str(Path.cwd())}
    return COUPLED.SHARED.record_measurement(
        args.run_id, CASE, inputs, details, measure, command=None, input_root=velum.screen.ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
