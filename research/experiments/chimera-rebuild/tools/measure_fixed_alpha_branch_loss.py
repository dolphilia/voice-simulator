"""固定 /ɑ/ の枝ごとの二次損失から、口端の複素応答の差を再構成する。"""

import argparse
import csv
import json
from pathlib import Path
import re
import subprocess
from tempfile import TemporaryDirectory

import numpy as np

import measure_fixed_alpha_periodic_flow as periodic
from measure_fan_crossing_allocations import run_manifest, verified_path
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/fixed-alpha-branch-loss.json'
ARMS = periodic.ARMS
EDITIONS = periodic.EDITIONS
TRACE = periodic.FIELDS
MEAN = periodic.mean
IMPULSE = MEAN.impulse
READ = periodic.READ
EVIDENCE = ('branch-states.npz', 'branch-contributions.csv', 'candidate-topology.json',
            'candidate-topology-case.json', *(f'{arm}.json' for arm in ARMS))


def archive_inputs(study):
    ref = study['reference']
    run, header = record = run_manifest(ref['run'], ref['case'], study['upstream_revision'])
    manifest = run / 'manifest.json'
    if header['status'] != 'pass' or sha256(manifest) != ref['sha256']:
        raise ValueError('周期流量の保存実行が登録値と一致しません')
    row, = [item for item in header['inputs'] if item['path'].endswith(f'/cases/{ref["case"]}.json')]
    case = run / header['source_snapshot'] / row['path']
    if sha256(case) != row['sha256']:
        raise ValueError('周期流量の保存ケースのハッシュが一致しません')
    archive = periodic.archive_inputs(READ(case))
    geometry = ('upstream-geometry.csv', *IMPULSE.harmonic.NETWORK_FILES)
    files = ('replay-traces.npz', *(f'{arm}-periodic.json' for arm in ARMS))
    paths = {'manifest.json': manifest, 'periodic-definition.json': case,
             'summary.json': verified_path(record, 'summary.json'),
             **{name: verified_path(record, f'artifacts/{name}') for name in files},
             **{name: archive[name] for name in geometry}}
    initial = study['initial_alignment_failure']
    first_run, first_header = first = run_manifest(initial['run'], study['id'], study['upstream_revision'])
    first_manifest = first_run / 'manifest.json'
    if first_header['status'] != 'fail' or sha256(first_manifest) != initial['sha256']:
        raise ValueError('比較列がずれた初回実行の保存状態が一致しません')
    paths.update({'initial-manifest.json': first_manifest, 'initial-summary.json': verified_path(first, 'summary.json'),
                  'initial-trace.npz': verified_path(first, 'artifacts/branch-states.npz')})
    return paths


def trace_case(study, archive, arm):
    case = READ(archive[f'{arm}-periodic.json'])
    start, end = study['measurement']['window_samples']
    case['fixed_airway']['trace_state_samples'] = [start - 1, end]
    return case


def topology_case(study, archive):
    case = READ(archive['coupled-periodic.json'])
    case.pop('fixed_airway_periodic_flow')
    lo, hi = study['measurement']['frequencies_hz']
    case['transfer'] = {'start_hz': lo, 'end_hz': hi, 'points': 2}
    return case


def read_trace(path, start, end, nodes, branches):
    expected = ('sample', *TRACE, *(f'pressure_node_{node}' for node in range(nodes)),
                *(f'flow_branch_{branch}' for branch in range(branches)))
    with path.open() as stream:
        actual = tuple(stream.readline().strip().split(','))
        if actual != expected:
            raise ValueError(f'節点・枝の観測列が不正です ({path.name})')
        rows = np.loadtxt(stream, delimiter=',', ndmin=2)
    if rows.shape != (end - start, len(expected)) or not np.array_equal(rows[:, 0], np.arange(start, end)):
        raise ValueError(f'観測標本の範囲が不正です ({path.name})')
    if not np.isfinite(rows).all():
        raise ValueError(f'節点または枝の系列に非有限値があります ({path.name})')
    return rows[:, 1:]


def capture(study, archive, out, execute):
    cases = ((arm, trace_case(study, archive, arm)) for arm in ARMS)
    capture_cases(archive, out, execute, topology_case(study, archive), cases)


def capture_cases(archive, out, execute, topology, cases, *, save_geometry=False):
    nodes, branches, _ = IMPULSE.source_elements(archive)
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera', '--test', 'airway_adversarial',
             'steady_flow_through_a_short_constriction_obeys_bernoulli_with_jet_loss'], cwd=UPSTREAM,
            stdout=out / 'upstream-kinetic-test.log')
    probe = MEAN.shared.build_upstream_probe(MEAN.sagittal.PROBE, out, execute, cargo_args=('--offline',))
    cli = ['cargo', 'run', '--locked', '--offline', '--release', '-p', 'vocal-cli', '--']
    path = out / 'candidate-topology-case.json'
    path.write_text(json.dumps(topology, ensure_ascii=False, indent=2) + '\n')
    execute([*cli, 'inspect', str(path)], stdout=out / 'candidate-topology.json')
    if save_geometry:
        rate = topology['fixed_airway']['sample_rate_hz']
        execute([str(probe), '--fixed-airway', str(rate), '0', '0', *MEAN.sagittal.pose_controls(topology)],
                cwd=UPSTREAM, stdout=out / 'upstream-geometry.csv')
    arrays = {}
    with TemporaryDirectory(prefix='branch-state-csv-', dir=out) as temp:
        directory = Path(temp)
        for arm, case in cases:
            definition = out / f'{arm}.json'
            definition.write_text(json.dumps(case, ensure_ascii=False, separators=(',', ':')) + '\n')
            settings = case['fixed_airway']
            start, end = settings['trace_state_samples']
            drive = case['fixed_airway_periodic_flow']
            stimulus = directory / 'flow.txt'
            stimulus.write_text('\n'.join(drive['flow_cm3_s']) + '\n')
            args = [settings['sample_rate_hz'], settings['sample_count'], drive['start_sample'],
                    settings['steady_flow_cm3_s'], stimulus, start, end]
            for edition in EDITIONS:
                path = directory / f'{edition}.csv'
                if edition == 'candidate':
                    execute([*cli, 'render', str(definition), str(path)])
                else:
                    execute([str(probe), '--fixed-airway-state', *map(str, args), *MEAN.sagittal.pose_controls(case)],
                            cwd=UPSTREAM, stdout=path)
                arrays[f'{arm}_{edition}'] = read_trace(path, start, end, len(nodes), len(branches))
                path.unlink()
    np.savez_compressed(out / 'branch-states.npz', **arrays)


def connected_links(branches, active, inlet):
    edges = branches[:, :2].astype(int)
    reachable = {inlet}
    frontier = {inlet}
    while frontier:
        frontier = ({right for left, right in edges[active] if left in frontier}
                    | {left for left, right in edges[active] if right in frontier}) - reachable
        reachable |= frontier
    return np.flatnonzero(active & np.isin(edges[:, 0], list(reachable)))


def match_branch_indices(study, archive, out, branches, nodes, source, checks):
    case = topology_case(study, archive)
    runs = [READ(archive[f'{arm}-periodic.json']) for arm in ARMS]
    return align_branch_indices(study, out, branches, nodes, source, checks, case, runs)


def align_branch_indices(study, out, branches, nodes, source, checks, case, runs):
    topology = READ(out / 'candidate-topology.json')
    table = topology['transfer']
    checks['topology_inspected_from_the_same_geometry'] = (
        topology['case'] == READ(out / 'candidate-topology-case.json') == case
        and all(run['body'] == case['body'] and run['posture'] == case['posture'] for run in runs)
        and table['inject'] == source['inject'] and table['lips'] == source['lips']
        and table['nose'] == source['nose'] and len(table['nodes']) == len(nodes)
        and [table['branches'][i]['nodes'] for i in table['cut']] == [list(source['cut'])])
    pairs = {tuple(item['nodes']): i for i, item in enumerate(table['branches'])}
    addresses = [tuple(row[:2].astype(int)) for row in branches]
    if len(pairs) != len(table['branches']) or pairs.keys() != set(addresses) or len(pairs) != len(addresses):
        raise ValueError('上流と研究版で向き付きの枝の両端を一対一対応できません')
    mapping = [pairs[address] for address in addresses]
    items = [table['branches'][index] for index in mapping]
    observed = np.array([[row['open'], row['inertance'], row['resistance']] for row in items])
    tol = study['measurement']['topology_element_relative_error_lt']
    checks['mapped_branch_elements_match'] = np.allclose(branches[:, 2:], observed, rtol=tol, atol=0)
    compliances = np.array([item['compliance'] for item in table['nodes']])
    checks['mapped_node_compliances_match'] = np.allclose(nodes[:, 0], compliances, rtol=tol, atol=0)
    return mapping


def loss_remainder(rate, pressure, velocity, links, geometry, bias):
    left, right = links[:, :2].astype(int).T
    inertance, resistance = links[:, 3:5].T
    route = np.column_stack((left, right, np.arange(len(links))))
    forward = MEAN.drag_on_path(route, geometry)
    reverse = MEAN.drag_on_path(route[:, [1, 0, 2]], geometry)
    flow = velocity[1:]
    dynamic = np.where(flow >= 0, forward, reverse) * flow * abs(flow)
    observed = (pressure[:-1, left] - pressure[:-1, right]
                - (rate * inertance) * (flow - velocity[:-1]) - resistance * flow)
    tangent = forward * (bias**2 + 2 * bias * (flow - bias))
    errors = abs(observed - dynamic).max(axis=0)
    return dynamic - tangent, 2 * forward * bias, float(errors.max() / abs(dynamic).max())


def project(projection, bins, signal):
    dft = projection @ signal / len(signal)
    fft = np.fft.rfft(signal, axis=0)[bins] / len(signal)
    return dft, float(abs(dft - fft).max() / abs(dft).max())


def responses(frequency, rate, nodes, branches, compliance, active, connected, source, nonlinear):
    chosen = branches[active]
    matrix, impedances, wall, opening = IMPULSE.discrete_elements(frequency, rate, nodes, chosen, compliance)
    z = nonlinear / impedances[np.isin(np.flatnonzero(active), connected)]
    rhs = np.zeros((len(nodes), len(connected) + 1), dtype=complex)
    rhs[source['inject'], 0] = 1
    left, right = branches[connected, :2].astype(int).T
    sparse_columns = np.arange(1, len(connected) + 1)
    rhs[left, sparse_columns] = z
    rhs[right, sparse_columns] = -z
    pressure = np.linalg.solve(matrix, rhs)
    lip = source['lips']
    return pressure[lip] * opening[lip], (wall * nodes[:, 6]) @ pressure, pressure


def serialize_branches(frequency, arm, connected, links, drag_spectrum, contribution, residual, labels, main):
    shares = (contribution * residual.conjugate()).real / abs(residual)**2
    order = np.argsort(-abs(contribution), kind='stable')
    rows = []
    for rank, j in enumerate(order, start=1):
        left, right = (int(node) for node in links[j, :2])
        on_path = bool(main[j])
        rows.append({
            'arm': arm, 'frequency_hz': frequency, 'rank_by_magnitude': rank,
            'branch': int(connected[j]), 'from': left, 'to': right,
            'region': 'oral_path' if on_path else 'piriform_side_branch',
            'from_tube': labels[left]['tube'], 'to_tube': labels[right]['tube'],
            'residual_pressure_real_dyn_cm2': float(drag_spectrum[j].real),
            'residual_pressure_imag_dyn_cm2': float(drag_spectrum[j].imag),
            'lip_transfer_contribution_real': float(contribution[j].real),
            'lip_transfer_contribution_imag': float(contribution[j].imag),
            'projected_fraction_of_difference': float(shares[j]),
        })
    return rows


def analyze_arm(study, arm, archive, aligned, previous, nodes, branches, source, geometry, labels, compliance, active):
    cfg = study['measurement']
    periodic_case = READ(archive[f'{arm}-periodic.json'])
    settings = periodic_case['fixed_airway']
    stimulus = np.array([float(value) for value in periodic_case['fixed_airway_periodic_flow']['flow_cm3_s']])
    count = len(stimulus)
    fs = cfg['internal_rate_hz']
    frequencies = np.array(cfg['frequencies_hz'])
    bins = (frequencies * count // fs).astype(int)
    projection = np.exp(-2j * np.pi / fs * np.outer(frequencies, np.arange(count)))
    excitation, fft_error = project(projection, bins, stimulus)
    connected = connected_links(branches, active, source['inject'])
    path = MEAN.airway_path(branches, active, source)
    main = np.isin(connected, path[:, 2])
    values, checks, rows = {}, {
        'frequencies_align_with_period': np.array_equal(bins * fs / count, frequencies),
        'registered_connected_and_main_path_branches': (
            len(connected) == cfg['expected_connected_branches']
            and int(main.sum()) == len(path) == cfg['expected_main_path_branches']
            and np.array_equal(path[:, :2], branches[path[:, 2], :2])),
    }, []
    old = READ(archive['summary.json'])['conditions'][arm]['frequencies']
    by_edition = {}
    for edition in EDITIONS:
        data = aligned[edition]
        pressure = data[:, len(TRACE):len(TRACE) + len(nodes)]
        flow = data[:, len(TRACE) + len(nodes):][:, connected]
        bias = settings['steady_flow_cm3_s'] * main
        remainder, slope, balance_error = loss_remainder(fs, pressure, flow, branches[connected], geometry, bias)
        nonlinear, nonlinear_error = project(projection, bins, remainder)
        lip_and_wall, trace_error = project(projection, bins, data[1:, [TRACE.index('flow_lips'), TRACE.index('flow_walls')]])
        pressure_hat, pressure_error = project(projection, bins, pressure[1:])
        checks[f'{edition}/branch_kinetic_pressure_balance'] = balance_error < cfg['kinetic_balance_peak_relative_error_lt']
        checks[f'{edition}/direct_projection_matches_fft'] = max(fft_error, nonlinear_error, trace_error, pressure_error) < cfg['dft_relative_error_lt']
        checks[f'{edition}/observed_trace_matches_archived_replay'] = np.array_equal(
            data[:, :len(TRACE)], previous[f'{arm}-periodic_{edition}'][-len(data):])
        linear = branches.copy()
        linear[connected, 4] += slope
        frequency_values = []
        for index, freq in enumerate(cfg['frequencies_hz']):
            driving = excitation[index]
            lip, wall, solution = responses(freq, fs, nodes, linear, compliance, active, connected, source,
                                             nonlinear[index] / driving)
            measured, wall_measured = lip_and_wall[index] / driving
            base, contributions = lip[0], lip[1:]
            residual = measured - base
            target = complex(*old[index]['transfer']['linear_at_mean'])
            base_error = float(abs(base / target - 1))
            closure = float(abs(contributions.sum() - residual) / abs(residual))
            wall_error = float(abs(wall.sum() / wall_measured - 1))
            p_expected = pressure_hat[index] / driving
            p_error = float(abs(solution.sum(axis=1) - p_expected).max() / abs(p_expected).max())
            checks[f'{edition}/{freq}/previous_linear_baseline'] = base_error < cfg['prior_linear_relative_error_lt']
            checks[f'{edition}/{freq}/reconstructed_lip_difference'] = closure < cfg['lip_complex_residual_reconstruction_error_lt']
            if edition == 'candidate':
                branch_rows = serialize_branches(freq, arm, connected, branches[connected],
                                                 nonlinear[index], contributions, residual, labels, main)
                rows.extend(branch_rows)
            group = {name: IMPULSE.harmonic.pair(value) for name, value in (
                ('oral_path', contributions[main].sum()), ('piriform_side_branch', contributions[~main].sum()))}
            ratio = float(abs(contributions[~main].sum()) / abs(residual))
            frequency_values.append({'frequency_hz': freq, 'linear_lip_transfer': IMPULSE.harmonic.pair(base),
                                     'measured_lip_transfer': IMPULSE.harmonic.pair(measured),
                                     'lip_transfer_difference': IMPULSE.harmonic.pair(residual),
                                     'branch_sum_relative_closure_error': closure,
                                     'wall_relative_reconstruction_error': wall_error,
                                     'node_pressure_peak_relative_reconstruction_error': p_error,
                                     'group_contributions': group, 'side_branch_relative_magnitude': ratio,
                                     'side_branch_small_hypothesis': ratio < cfg['side_branch_relative_contribution_lt']})
        by_edition[edition] = {'kinetic_pressure_balance_peak_relative_error': balance_error, 'frequencies': frequency_values}
    upstream, native = (aligned[edition] for edition in ('upstream', 'candidate'))
    peak = abs(upstream).max(axis=0)
    error = abs(native - upstream) / np.where(peak > 0, peak, 1)
    checks['node_branch_and_radiation_series_match_upstream'] = bool(np.all(error < cfg['series_peak_relative_error_lt']))
    values.update(editions=by_edition, upstream_series_peak_relative_error=float(error.max()),
                  strongest_branches=[row for row in rows if row['rank_by_magnitude'] <= 3])
    return checks, values, rows


def analyze(study, archive, out):
    cfg = study['measurement']
    nodes, branches, source = IMPULSE.source_elements(archive)
    labels, geometry = MEAN.fixed.read_upper_geometry(archive['upstream-geometry.csv'])
    compliance, active = IMPULSE.compliance_floor(nodes, branches, source, cfg['internal_rate_hz'])
    checks = {'capture_starts_one_sample_before_window': cfg['capture_previous_sample'] is True}
    mapping = match_branch_indices(study, archive, out, branches, nodes, source, checks)
    indices = list(range(len(TRACE) + len(nodes))) + [len(TRACE) + len(nodes) + i for i in mapping]
    previous_failures = sorted(key for key, ok in READ(archive['initial-summary.json'])['checks'].items() if not ok)
    checks['initial_index_alignment_failures_retained'] = previous_failures == study['initial_alignment_failure']['failed_checks']
    arms, rows = {}, []
    with (
        np.load(out / 'branch-states.npz', allow_pickle=False) as trace,
        np.load(archive['replay-traces.npz'], allow_pickle=False) as previous,
        np.load(archive['initial-trace.npz'], allow_pickle=False) as first,
    ):
        checks['raw_observations_equal_initial_capture'] = trace.files == first.files and all(np.array_equal(
            trace[key].view(np.uint64), first[key].view(np.uint64)) for key in trace.files)
        for arm in ARMS:
            case = trace_case(study, archive, arm)
            checks[f'{arm}/archived_drive_and_capture_window'] = (
                case == READ(out / f'{arm}.json')
                and case['fixed_airway']['sample_count'] == cfg['window_samples'][1]
                and case['fixed_airway']['sample_rate_hz'] == cfg['internal_rate_hz'])
            aligned = {'upstream': trace[f'{arm}_upstream'], 'candidate': trace[f'{arm}_candidate'][:, indices]}
            arm_checks, arms[arm], contributions = analyze_arm(
                study, arm, archive, aligned, previous, nodes, branches, source, geometry, labels, compliance, active)
            checks.update({f'{arm}/{key}': value for key, value in arm_checks.items()})
            rows.extend(contributions)
    return {'checks': {key: bool(value) for key, value in checks.items()},
            'conditions': arms, 'branch_contributions': rows,
            'initial_failed_checks': previous_failures,
            'realigned_branches': [{'upstream': i, 'candidate': j, 'nodes': branches[i, :2].astype(int).tolist()}
                                   for i, j in enumerate(mapping) if i != j]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', args.run_id):
        parser.error('英数字で始まる実行IDを指定してください')
    study = READ(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != study['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    archive = archive_inputs(study)

    def measure(out, execute):
        capture(study, archive, out, execute)
        result = analyze(study, archive, out)
        rows = result['branch_contributions']
        with (out / 'branch-contributions.csv').open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator='\n')
            writer.writeheader()
            writer.writerows(rows)
        return result

    inputs = [CASE, Path(__file__), *archive.values(), *MEAN.shared.candidate_sources(), MEAN.sagittal.PROBE,
              *(Path(module.__file__) for module in (periodic, MEAN, IMPULSE, MEAN.fixed, MEAN.sagittal, MEAN.shared)),
              UPSTREAM / 'crates/chimera/src/airway/network.rs', UPSTREAM / 'crates/chimera/src/voice/human_airway.rs',
              UPSTREAM / 'crates/chimera/tests/airway_adversarial.rs']
    details = {'case_id': study['id'], 'case_revision': study['revision'], 'upstream_revision': revision,
               'invoked_from': str(Path.cwd())}
    return MEAN.shared.record_measurement(args.run_id, CASE, inputs, details, measure, command=None,
                                          input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
