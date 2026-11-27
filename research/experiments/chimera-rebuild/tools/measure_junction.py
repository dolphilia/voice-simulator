"""固定三分岐の CLI 出力を上流・圧力収支・離散周波数計算と比較する。"""

import argparse
import json
from pathlib import Path
import re
import subprocess

import numpy as np

import measure_uniform_tube as shared
from upstream_baseline import UPSTREAM, WORKSPACE


PROBE = WORKSPACE / 'tools/upstream_network_probe.rs'


def capture_upstream(case, artifacts, execute, upstream_test=None):
    network, observe = (case[key] for key in ('network', 'observe'))
    impulse = case.get('impulse', {'node': 0, 'sample': 0, 'volume_cm3': 0.0})
    rows = [[network['sample_rate_hz'], case['measurement']['sample_count'], impulse['node'],
             impulse['sample'], impulse['volume_cm3']], [len(network['tubes'])]]
    for tube in network['tubes']:
        row = [tube['length_cm'], len(tube['areas_cm2']), *tube['areas_cm2'],
               tube.get('perimeter_factor', 1.0), tube.get('viscous_factor', 1.0)]
        if wall := tube.get('wall'):
            row.extend([1, wall['mass_g_cm2'], wall['resistance_dyn_s_cm3'],
                        wall['stiffness_dyn_cm3'], wall['radiation_fraction']])
        else:
            row.append(0)
        rows.append(row)
    rows.extend(([len(network['connections'])], *network['connections'],
                 [len(network['radiators']), *network['radiators']],
                 [len(observe['pressure_nodes']), *observe['pressure_nodes']],
                 [len(observe['branches'])], *observe['branches']))
    for key in ('area_nodes', 'minimum_area_nodes', 'wall_nodes'):
        nodes = observe.get(key, [])
        rows.append([len(nodes), *nodes])
    ramps = case.get('area_ramps', [])
    rows.append([len(ramps)])
    for ramp in ramps:
        rows.append([ramp['start_sample'], ramp['sample_count'], ramp['block_samples'], len(ramp['targets'])])
        rows.extend([target['node'], target['area_cm2'], target.get('minimum_area_cm2', target['area_cm2'])]
                    for target in ramp['targets'])
    drives, ports = network.get('pressure_nodes', []), network.get('ports', [])
    rows.append([len(drives)])
    rows.extend([drive['pressure_dyn_cm2'], drive['ramp_samples']] for drive in drives)
    rows.append([len(ports)])
    rows.extend([*port['nodes'], port['area_cm2'], port['length_cm'], port['entrance_loss'],
                 port['expansion_loss'], port.get('slit_width_cm', 0.0),
                 int(port.get('include_half_sections', True)), port.get('extra_resistance', 0.0)]
                for port in ports)
    turbulence = network.get('turbulence', {})
    sources = turbulence.get('sources', [])
    rows.append([turbulence.get('scale', 1.0), len(sources)])
    rows.extend([*source['source'], *source['forward'], *source['reverse'], source['gain'],
                 source['lowpass_hz'], source['highpass_hz']] for source in sources)
    noise_nodes = observe.get('noise_sources', [])
    rows.append([len(noise_nodes), *noise_nodes])
    glottis = case.get('glottis')
    rows.append([int(glottis is not None)])
    if glottis is not None:
        params = glottis['params']
        steps = glottis['abduction_steps']
        if params.get('cycle_seed', 777) != 777:
            raise ValueError('上流の声門のシードは777に固定されています')
        rows.append([*glottis['port'], *(params[name] for name in (
            'f0_hz', 'amplitude_cm2', 'chink_cm2', 'open_quotient', 'open_with_abduction',
            'skew', 'closure_sharpness', 'effort', 'closure', 'threshold_dyn_cm2')),
            params.get('jitter', 0.0), params.get('shimmer', 0.0), params.get('drift_cents', 0.0),
            params.get('vibrato_depth_cents', 0.0), params.get('vibrato_rate_hz', 6.0), params.get('fry', 0.0),
            params.get('diplophonia', 0.0), params.get('chaos', 0.0),
            int(observe.get('glottal_f0', False)), len(steps)])
        rows.extend(steps)
    breath = case.get('breath')
    rows.append([int(breath is not None)])
    if breath is not None:
        port = next(port for port in ports if port['nodes'] == breath['port'])
        rows.append([*breath['port'], breath['pressure_cm_h2o'], breath['body_scale'],
                     breath['control_block_samples'], port.get('extra_resistance', 0.0),
                     int(breath['compensate']), len(breath['steps'])])
        rows.extend(breath['steps'])
    test_suite = 'airway_adversarial'
    if upstream_test is not None:
        test_suite, regression = upstream_test
    elif drives:
        regression = 'steady_flow_through_a_short_constriction_obeys_bernoulli_with_jet_loss'
    elif ramps:
        regression = 'sealed_cavity_compression_follows_the_linearised_adiabatic_law'
    elif any(tube.get('wall') for tube in network['tubes']):
        test_suite = 'airway'
        regression = 'fdtd_impulse_response_agrees_with_frequency_domain_model'
    else:
        regression = 'nearly_closed_three_way_junction_stays_stable_at_the_working_cfl'
    configuration = artifacts / 'upstream-input.txt'
    configuration.write_text('\n'.join(' '.join(map(str, row)) for row in rows) + '\n')
    execute(['cargo', 'test', '--locked', '-p', 'chimera', '--test', test_suite,
             regression, '--', '--nocapture'], cwd=UPSTREAM, stdout=artifacts / 'upstream-network-test.log')
    executable = shared.build_upstream_probe(PROBE, artifacts, execute)
    trace = artifacts / 'upstream-trace.csv'
    execute([str(executable), str(configuration)], cwd=UPSTREAM, stdout=trace)
    return trace


def elements(network):
    rho, c, mu = 1.14e-3, 35000.0, 1.86e-4
    areas, lengths, edges = [], [], []
    for tube in network['tubes']:
        start = len(areas)
        areas.extend(tube['areas_cm2'])
        lengths.extend([tube['length_cm'] / len(tube['areas_cm2'])] * len(tube['areas_cm2']))
        edges.extend((a, a + 1) for a in range(start, len(areas) - 1))
    edges.extend(map(tuple, network['connections']))
    left, right = np.asarray(edges).T
    areas, lengths = np.asarray(areas), np.asarray(lengths)
    halves = lengths / (2 * areas)
    inertance = rho * (halves[left] + halves[right])
    viscous_halves = np.sqrt(np.pi * areas) * lengths / areas**2
    resistance = np.sqrt(rho * mu * np.pi * 700) * (viscous_halves[left] + viscous_halves[right])
    geometric = np.maximum(areas, 0.02) * lengths / (rho * c**2)
    incident = np.r_[left, right]
    degree = np.bincount(incident, minlength=areas.size)
    inverse_l = np.bincount(incident, weights=np.tile(1 / inertance, 2), minlength=areas.size)
    dt = 1 / network['sample_rate_hz']
    compliance = np.where(degree >= 3, np.maximum(geometric, dt**2 * inverse_l / 2.4), geometric)
    return areas, edges, inertance, resistance, geometric, compliance


def discrete_response(frequencies, network, inlet, areas, edges, inertance, resistance, compliance):
    fs = network['sample_rate_hz']
    left, right = np.asarray(edges).T
    terminals = np.asarray(network['radiators'])
    rho, speed = 1.14e-3, 35000.0
    rl = 8 * rho / (3 * np.pi * np.sqrt(np.pi * areas[terminals]))
    rr = 128 * rho * speed / (9 * np.pi**2 * areas[terminals])
    unit_drive = np.zeros(areas.size)
    unit_drive[inlet] = 1.0
    transfer = []
    for hz in frequencies:
        delay = np.exp(-2j * np.pi * hz / fs)
        difference = 1 - delay
        midpoint = (1 + delay) / 2
        load = midpoint * (1 / rr + midpoint / (fs * rl * difference))
        branch = delay / (resistance + inertance * fs * difference)
        matrix = np.diag(compliance * difference * fs)
        np.add.at(matrix, (left, left), branch)
        np.add.at(matrix, (right, right), branch)
        np.add.at(matrix, (left, right), -branch)
        np.add.at(matrix, (right, left), -branch)
        matrix[terminals, terminals] += load
        pressure = np.linalg.solve(matrix, unit_drive)
        transfer.append((pressure[terminals] * load).sum())
    return np.asarray(transfer)


def measure(case, artifacts, reference_path):
    network, m, observation = (case[key] for key in ('network', 'measurement', 'observe'))
    count = 4 + len(observation['pressure_nodes']) + len(observation['branches']) + len(network['radiators'])
    header, trace = shared.read_trace(artifacts / 'trace.csv', m['sample_count'], count)
    reference_header, reference = shared.read_trace(reference_path, m['sample_count'], count)
    if header != reference_header:
        raise ValueError('候補と上流の計測列が一致しません')
    tol = m['upstream_trace_peak_relative_error_lt']
    comparisons = {name: shared.compare_series(trace[:, i], reference[:, i], tol)
                   for i, name in enumerate(header[1:], start=1)}
    columns = dict(zip(header, trace.T, strict=True))
    areas, edges, inertance, resistance, geometric, compliance = elements(network)
    fs = network['sample_rate_hz']
    inlet = case['impulse']
    q = columns['inlet_flow_cm3_s']
    expected_drive = np.zeros(q.size)
    expected_drive[inlet['sample']] = fs * inlet['volume_cm3']

    junction = m['junction_node']
    left, right = m['junction_outgoing_nodes']
    end_left, end_right = network['radiators']
    pressure = columns[f'pressure_{junction}_dyn_cm2']
    flow_in = columns[f'branch_flow_{m["junction_incoming_node"]}_{junction}_cm3_s']
    flow_left, flow_right = (columns[f'branch_flow_{junction}_{n}_cm3_s'] for n in (left, right))
    radiation_left, radiation_right = (columns[f'radiation_{n}_cm3_s'] for n in (end_left, end_right))
    radiation = columns['radiation_flow_cm3_s']
    derivative = columns['radiation_flow_derivative_cm3_s2']
    balance_tol = m['balance_peak_relative_error_lt']
    balance = {
        'junction': shared.compare_series(np.diff(pressure, prepend=0.0) * fs * compliance[junction],
                                         flow_in - flow_left - flow_right, balance_tol),
        'radiation_sum': shared.compare_series(radiation, radiation_left + radiation_right, balance_tol),
        'radiation_derivative': shared.compare_series(derivative, np.diff(radiation, prepend=0.0) * fs, balance_tol),
    }
    branch_results = {}
    nonlinear_directions = {'forward': 0, 'reverse': 0}
    indices = {tuple(sorted(edge)): i for i, edge in enumerate(edges)}
    for a, b in observation['branches']:
        index = indices[tuple(sorted((a, b)))]
        u = columns[f'branch_flow_{a}_{b}_cm3_s']
        dp = columns[f'pressure_{a}_dyn_cm2'] - columns[f'pressure_{b}_dyn_cm2']
        step_pressure = np.r_[0.0, dp[:-1]]
        delta = 1 / areas[a] - 1 / areas[b]
        expansion = delta * u > 0
        coefficient = 0.5 * 1.14e-3 * delta**2 * np.where(expansion, 1.0, 0.1)
        loss = coefficient * np.abs(u) * u
        nonlinear_directions['forward'] += int(np.count_nonzero(loss > 0))
        nonlinear_directions['reverse'] += int(np.count_nonzero(loss < 0))
        model_pressure = inertance[index] * fs * np.diff(u, prepend=0) + resistance[index] * u + loss
        branch_results[f'{a}_{b}'] = shared.compare_series(model_pressure, step_pressure, balance_tol)

    symmetry_tol = m['symmetric_trace_peak_relative_error_lt']
    symmetry = {'branch_flow': shared.compare_series(flow_left, flow_right, symmetry_tol),
                'outlet_radiation': shared.compare_series(radiation_left, radiation_right, symmetry_tol)}
    pressure_peak = np.max(np.abs(pressure))
    tail = float(np.max(np.abs(pressure[-m['tail_sample_count']:])) / pressure_peak) if pressure_peak > 0.0 else None
    nonzero = np.flatnonzero(derivative)
    first = int(nonzero[0]) if nonzero.size else None
    settings = json.loads((artifacts / 'settings.json').read_text())
    effective = settings['junction_effective_compliance_cm3_per_dyn_cm2']
    stated_geometric = settings['junction_geometric_compliance_cm3_per_dyn_cm2']
    floor_active = compliance[junction] > geometric[junction]
    active_directions = all(count > 0 for count in nonlinear_directions.values())
    checks = {
        'finite_samples': True,
        'input_impulse': bool(np.array_equal(q, expected_drive)),
        'causal_support': first == m['expected_first_radiation_sample'],
        'symmetry': all(item['status'] for item in symmetry.values()),
        'upstream_time_series': all(item['status'] for item in comparisons.values()),
        'volume_and_radiation_balance': all(item['status'] for item in balance.values()),
        'directional_branch_balance': all(item['status'] for item in branch_results.values()),
        'directional_loss_activation': (active_directions if m['expect_nonlinear_loss']
                                        else not any(nonlinear_directions.values())),
        'junction_compliance': bool(floor_active == m['expect_junction_compliance_floor_active']
                                    and abs(effective / compliance[junction] - 1) < balance_tol
                                    and abs(stated_geometric / geometric[junction] - 1) < balance_tol),
        'pressure_bound_and_decay': bool(0.0 < pressure_peak < m['junction_pressure_peak_lt_dyn_cm2']
                                         and tail is not None and tail < m['tail_over_peak_lt']),
    }
    frequency_points = m['linear_frequency_points_hz']
    spectral = None
    if frequency_points:
        bins = np.rint(np.asarray(frequency_points) * radiation.size / fs).astype(int)
        frequencies = bins * fs / radiation.size
        expected = discrete_response(frequencies, network, inlet['node'], areas, edges,
                                     inertance, resistance, compliance)
        measured = np.fft.rfft(radiation)[bins] / np.fft.rfft(q)[bins]
        spectral = shared.compare_series(measured, expected, m['linear_complex_peak_relative_error_lt'])
        spectral.pop('first_sample_over_tolerance')
        spectral['frequencies_hz'] = frequencies.tolist()
        spectral['absolute_errors'] = np.abs(measured - expected).tolist()
        checks['independent_discrete_frequency_response'] = spectral['status']
    return {'checks': checks, 'samples': q.size, 'first_radiation_sample': first,
            'junction_pressure_peak_dyn_cm2': float(pressure_peak), 'junction_tail_over_peak': tail,
            'junction_geometric_compliance': float(geometric[junction]),
            'junction_effective_compliance': float(compliance[junction]),
            'junction_compliance_floor_active': bool(floor_active), 'symmetry': symmetry,
            'balance': balance, 'branch_pressure_balance': branch_results,
            'nonlinear_loss_sample_counts': nonlinear_directions, 'upstream_time_series': comparisons,
            'discrete_frequency_response': spectral}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('case', choices=['symmetric-junction', 'narrow-junction'])
    args = parser.parse_args()
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]*', args.run_id):
        parser.error('実行 ID は英数字で始め、英数字、ハイフン、アンダースコアで指定してください')
    case_path = WORKSPACE / 'cases' / (args.case + '.json')
    case = json.loads(case_path.read_text())
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        raise ValueError('変更のない固定上流版が必要です')

    def measure_run(artifacts, execute):
        return measure(case, artifacts, capture_upstream(case, artifacts, execute))

    inputs = [case_path, PROBE, Path(__file__).resolve(), Path(shared.__file__),
              WORKSPACE / 'tools/upstream_baseline.py', *shared.candidate_sources()]
    return shared.record_measurement(args.run_id, case_path, inputs,
                                     {'upstream_revision': revision, 'case_id': case['id']}, measure_run)


if __name__ == '__main__':
    raise SystemExit(main())
