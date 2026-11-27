"""固定 /i/ の口腔・鼻腔で観測した二次損失を複素応答へ戻す。"""

import argparse
from pathlib import Path
import re
import subprocess
from tempfile import TemporaryDirectory

import numpy as np

import measure_fixed_vowel_i_velum_mean_flow_tangent as tangent
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/fixed-vowel-i-velum-oral-nasal-loss.json'
READ, COUPLED = tangent.READ, tangent.COUPLED
harmonic, velum = tangent.previous, tangent.velum
EVIDENCE = ('natural-case.json', 'natural-inspect.json', 'natural-network.csv', 'natural.wav',
            'upper-network.patch', 'upper-voice.patch', 'upper-columns.json',
            'upper.f32', 'upper.f64', 'upper-network.f64')
HYPOTHESIS = 'oral_and_nasal_losses_explain_half_of_nose_residual'


def archive_inputs(case):
    info = case['measurement']['reference']
    verify = COUPLED.smoothing.verified_reference
    record, manifest, definition = verify(
        {'run': info['run'], 'case': info['case_id'], 'sha256': info['manifest_sha256']},
        case['upstream_revision'])
    archive = tangent.archive_inputs(READ(definition))
    older = harmonic.archive_inputs(READ(archive['reference-case.json']))
    return {**archive, 'tangent-manifest.json': manifest, 'tangent-case.json': definition,
            'tangent-summary.json': COUPLED.verified_path(record, 'summary.json'),
            'archive-upper.f32': older['port_only-upper.f32']}


def capture(case, archive, out, execute):
    capture_voice_network(case, READ(archive['archive-input.json']), out, execute)


def capture_voice_network(case, base, out, execute):
    first, end = case['measurement']['steady_window_internal_samples']
    base['fixed_voice_probe']['network_trace_range'] = [first - 1, end]
    natural = out / 'natural-case.json'
    harmonic.port.write_case(natural, base)
    cargo = ['cargo', 'run', '--locked', '--offline', '--release', '-p', 'vocal-cli', '--']
    execute([*cargo, 'inspect', str(natural)], stdout=out / 'natural-inspect.json')
    execute([*cargo, 'render', str(natural), str(out / 'natural-network.csv')])
    execute([*cargo, 'render-pcm', str(natural), str(out / 'natural.wav'), '--no-trace', '128'])
    fs = base['fixed_airway']['sample_rate_hz']
    voice = base['voice']
    output = voice['output_sample_rate_hz']
    frames = base['fixed_airway']['sample_count'] // (fs // output)
    settings = [voice[key] for key in ('pressure_cm_h2o', 'gate', 'f0_hz', 'breathiness', 'tension', 'output_gain')]
    area = base['fixed_voice_probe']['velum_area_override_cm2']
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera', '--test', 'airway_adversarial',
             'steady_flow_through_a_short_constriction_obeys_bernoulli_with_jet_loss'],
            cwd=UPSTREAM, stdout=out / 'upstream-constriction-test.log')
    with TemporaryDirectory(prefix='oral-nasal-loss-', dir=out.parent) as temporary:
        upper = velum.build_upstream(case, out, Path(temporary), execute, port_override=True, network_trace=True)
        execute([str(upper), *map(str, (base['posture']['velum_cm2'], fs, output, frames, *settings)),
                 str(out / 'upper'), 'observer', *map(str, (area, first - 1, end))])


def candidate_state(out, first, end, node_count, branch_count):
    with (out / 'natural-network.csv').open() as stream:
        columns = stream.readline().strip().split(',')
        data = np.loadtxt(stream, delimiter=',', ndmin=2)
    expected = [*(f'node_{node}_pressure_dyn_cm2' for node in range(node_count)),
                *(f'branch_{edge}_flow_cm3_s' for edge in range(branch_count))]
    if (columns[-len(expected):] != expected or data.shape != (end - first + 1, len(columns))
            or not np.isfinite(data).all() or not np.array_equal(data[:, 1], np.arange(first - 1, end))):
        raise ValueError('研究版の節点・枝の並び、標本または有限性が一致しません')
    return dict(zip(columns, data.T)), data[:, -len(expected):]


def branch_groups(tubes, names, branches, port):
    groups = {'port': np.flatnonzero((branches[:, :2] == port).all(axis=1) & (branches[:, 2] == 1))}
    pairs = {(int(a), int(b)): index for index, (a, b, _, _, _) in enumerate(branches)}
    for name in names:
        tube, = (tube for tube in tubes if tube['name'] == name)
        first = tube['first_node']
        groups[name] = np.array([pairs[node, node + 1] for node in range(first, first + tube['cells'] - 1)])
    if len(groups['port']) != 1 or any(not branches[indices, 2].all() for indices in groups.values()):
        raise ValueError('固定ポートと対象の通常枝は開いている必要があります')
    return groups


def upstream_branch_order(candidate, upstream):
    by_nodes = {tuple(branch[:2]): index for index, branch in enumerate(upstream)}
    order = [by_nodes.get(tuple(branch[:2])) for branch in candidate]
    if None in order or len(set(order)) != len(candidate) or len(order) != len(upstream):
        raise ValueError('両版の枝を有向の節点対で一意に対応づけられません')
    return np.asarray(order)


def branch_coefficients(layout, selected_branches):
    port, port_losses = tangent.port_parameters(layout)
    areas = np.array([row['area_cm2'] for row in layout['sections']])
    minima = np.array([row['minimum_area_cm2'] for row in layout['sections']])
    left, right = selected_branches[:, :2].astype(int).T
    forward = 0.5 * 1.14e-3 * np.maximum(1 / minima[left] - 1 / areas[right], 0)**2
    reverse = 0.5 * 1.14e-3 * np.maximum(1 / minima[right] - 1 / areas[left], 0)**2
    is_port = (left == port[0]) & (right == port[1])
    return (np.where(is_port, port_losses[0], forward + 0.1 * reverse),
            np.where(is_port, port_losses[1], reverse + 0.1 * forward))


def branch_pressure(frequency, fs, basis, state, layout, selected, branches, drive, *, coefficients=None):
    node_count = layout['node_count']
    edges = branches[selected]
    left, right = edges[:, :2].astype(int).T
    inertia, resistance = edges[:, 3:].T
    flow = state[:, node_count + selected]
    pressure = state[:, left] - state[:, right]
    sample = flow[1:]
    if coefficients is None:
        coefficients = branch_coefficients(layout, edges)
    loss = np.where(sample >= 0., *coefficients) * sample * abs(sample)
    momentum = inertia * fs * np.diff(flow, axis=0)
    viscous = resistance * sample
    error = momentum + viscous + loss - pressure[:-1]
    time_scale = np.maximum.reduce([abs(item).max(axis=0) for item in (momentum, viscous, loss, pressure[:-1])])
    delay = np.exp(-2j * np.pi * frequency / fs)
    impedance = resistance + inertia * (1 - delay) * fs
    window_edge = (inertia * fs * (flow[-1] - flow[0]) + pressure[-1] - pressure[0]) / len(basis)
    loss_hat = basis @ loss
    spectral_terms = impedance * (basis @ sample), loss_hat, -delay * (basis @ pressure[1:]), window_edge
    spectral_scale = np.maximum.reduce([abs(term) for term in spectral_terms])
    return {
        'loss_per_drive': loss_hat / drive, 'window_edge_per_drive': window_edge / drive,
        'loss_from_pressure_per_drive': (basis @ (pressure[:-1] - momentum - viscous)) / drive,
        'time_relative': abs(error).max(axis=0) / time_scale,
        'spectral_relative': abs(sum(spectral_terms)) / spectral_scale,
    }


def analyze_edition(cfg, tracks, state, layout, nodes, branches, source, before):
    frequency, fs = cfg['frequency_hz'], cfg['internal_rate_hz']
    groups = branch_groups(layout['tubes'], cfg['tubes'], branches, tangent.port_parameters(layout)[0])
    selected = np.concatenate(list(groups.values()))
    first, end = cfg['steady_window_internal_samples']
    basis = np.exp(-2j * np.pi * frequency * np.arange(end - first) / fs) / (end - first)
    drive = basis @ tracks[harmonic.GLOTTIS][1:]
    target = (basis @ np.column_stack([tracks[name][1:] for name in harmonic.RAD])) / drive
    pressure = branch_pressure(frequency, fs, basis, state, layout, selected, branches, drive)

    matrix, wall, radiation, share = harmonic.discrete_system(frequency, fs, nodes, branches, source)
    left, right = branches[selected, :2].astype(int).T
    delay = np.exp(-2j * np.pi * frequency / fs)
    impedance = branches[selected, 4] + branches[selected, 3] * (1 - delay) * fs
    inject = np.zeros(len(nodes), dtype=complex)
    inject[source['inject']] = 1.
    dipoles = np.zeros((len(nodes), len(selected)), dtype=complex)
    dipoles[left, np.arange(len(selected))] = 1 / impedance
    dipoles[right, np.arange(len(selected))] = -1 / impedance
    modes = np.linalg.solve(matrix, np.column_stack((inject, dipoles))).T
    responses = np.array([harmonic.radiation_from_pressure(mode, wall, radiation, share, source) for mode in modes])
    baseline = responses[0]
    contribution = responses[1:] * pressure['loss_per_drive'][:, None]
    endpoint = responses[1:] * pressure['window_edge_per_drive'][:, None]
    all_pressure = np.linalg.solve(matrix, inject + dipoles @ pressure['loss_per_drive'])
    total = np.array(harmonic.radiation_from_pressure(all_pressure, wall, radiation, share, source))
    by_tube, by_edge = {}, []
    for name, indices in groups.items():
        mask = np.isin(selected, indices)
        by_tube[name] = contribution[mask].sum(axis=0)
        for slot in np.flatnonzero(mask):
            by_edge.append({
                'tube': name, 'branch': int(selected[slot]), 'nodes': [int(left[slot]), int(right[slot])],
                'pressure_per_drive': tangent.pair(pressure['loss_per_drive'][slot]),
                'nose_transfer_change': tangent.pair(contribution[slot, 1]),
                'nose_transfer_change_from_window_edge': tangent.pair(endpoint[slot, 1]),
            })
    after_port = baseline + by_tube['port']
    combined = after_port + by_tube['oral'] + by_tube['nasal']
    port_error = abs(after_port[1] - target[1])
    improvement = float(1 - abs(combined[1] - target[1]) / port_error)
    comparison = {'port': after_port, 'port_and_oral': after_port + by_tube['oral'],
                  'port_and_nasal': after_port + by_tube['nasal'], 'port_oral_nasal': combined,
                  'including_tested_branch_window_edges': combined + endpoint.sum(axis=0)}
    tolerance = cfg['complex_identity_relative_error_lt']
    recorded = before['responses']['observed_port_loss']['radiation_transfer']
    recorded_port = np.array([complex(*recorded[key]) for key in harmonic.vowel.COMPONENTS])
    checks = {
        'time_domain_pressure_balance': bool(pressure['time_relative'].max() < cfg['branch_balance_relative_error_lt']),
        'spectral_pressure_balance_with_window_edges': bool(pressure['spectral_relative'].max() < tolerance),
        'port_only_replays_previous_run': harmonic.max_row_relative(after_port[None, :], recorded_port[None, :]) < tolerance,
        'superposition_matches_combined_solve': harmonic.max_row_relative(combined[None, :], total[None, :]) < tolerance,
    }
    summary = {
        'nose_error_reduction_fraction': improvement,
        'nose_target': tangent.pair(target[1]),
        'nose_residual_after_all_tested_losses': tangent.pair(target[1] - combined[1]),
        'nose_complex_relative_error': {name: float(abs(value[1] - target[1]) / abs(target[1]))
                                        for name, value in comparison.items()},
        'nose_transfer_changes': {name: tangent.pair(value[1]) for name, value in by_tube.items()},
        'nose_projection_onto_port_only_residual': {
            name: harmonic.projection(value[1], target[1] - after_port[1]) for name, value in by_tube.items() if name != 'port'},
        'max_pressure_balance_relative': {'time': float(pressure['time_relative'].max()),
                                          'spectral': float(pressure['spectral_relative'].max())},
        'branches': by_edge,
    }
    return checks, summary


def analyze(case, archive, out):
    cfg = case['measurement']
    first, end = cfg['steady_window_internal_samples']
    count = READ(out / 'natural-case.json')['fixed_airway']['sample_count']
    report = READ(archive['archive-linear-inspect.json'])
    layout = report['fixed_airway']
    nodes, branches, source = harmonic.candidate_elements(report)
    upper_nodes, upper_branches, upper_source = harmonic.harmonic.source_elements(
        {name: archive[f'archive-{name}'] for name in harmonic.harmonic.NETWORK_FILES})
    columns, candidate = candidate_state(out, first, end, len(nodes), len(branches))
    upper = velum.screen.prior.binary_trace(out / 'upper-network.f64', end - first + 1, len(upper_nodes) + len(upper_branches))
    upper_trace = velum.screen.prior.binary_trace(out / 'upper.f64', count, len(velum.FIELDS))
    upper_tracks = dict(zip(velum.FIELDS, upper_trace[first - 1:end].T))
    header, baseline = COUPLED.pcm.read_columns(archive['archive-internal.csv'], count)
    toler = cfg['upstream_series_peak_relative_error_lt']
    upper_order = upstream_branch_order(branches, upper_branches)
    upper_aligned = np.column_stack((upper[:, :len(nodes)], upper[:, len(nodes) + upper_order]))
    state_parity = harmonic.max_row_relative(candidate.T, upper_aligned.T)
    checks = {
        'registered_frequency_and_window': (
            {key: cfg[key] for key in ('frequency_hz', 'internal_rate_hz', 'steady_window_internal_samples')}
            == {key: READ(archive['tangent-case.json'])['measurement'][key]
                for key in ('frequency_hz', 'internal_rate_hz', 'steady_window_internal_samples')}
            and READ(out / 'natural-inspect.json')['voice']['probe']['network_trace_range'] == [first - 1, end]),
        'observed_cli_channels_match_previous_run': all(
            np.array_equal(columns[key], baseline[key][first - 1:end]) for key in header),
        'upstream_observer_and_both_pcm_match_previous_runs': all(sha256(out / path) == sha256(archive[key])
            for path, key in (('upper.f64', 'archive-upper.f64'), ('upper.f32', 'archive-upper.f32'),
                              ('natural.wav', 'archive-pcm.wav'))),
        'branch_topology_and_source_match_upstream': (
            source == upper_source and np.array_equal(branches[:, :3], upper_branches[upper_order, :3])),
        'observed_network_matches_upstream': state_parity < toler,
    }
    before = READ(archive['tangent-summary.json'])['editions']
    results = {}
    for edition, tracks, state, model in (
        ('candidate', columns, candidate, (nodes, branches, source)),
        ('upstream', upper_tracks, upper, (upper_nodes, upper_branches, upper_source)),
    ):
        conditions, results[edition] = analyze_edition(cfg, tracks, state, layout, *model, before[edition])
        checks.update({f'{edition}/{key}': answer for key, answer in conditions.items()})
    prediction = [edition['nose_error_reduction_fraction'] >= cfg['minimum_nose_error_reduction_fraction']
                  for edition in results.values()]
    checks['editions_agree_on_registered_hypothesis'] = prediction[0] == prediction[1]
    checks[HYPOTHESIS] = all(prediction)
    return {'checks': checks, 'frequency_hz': cfg['frequency_hz'],
            'network_series_peak_relative': state_parity,
            'upper_branch_index_for_candidate': upper_order.tolist(), 'editions': results}


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
        capture(case, archive, out, execute)
        return analyze(case, archive, out)

    inputs = [CASE, Path(__file__), *archive.values(), *COUPLED.SHARED.candidate_sources(), velum.UPPER,
              *(Path(module.__file__) for module in (tangent, harmonic, harmonic.port, harmonic.harmonic,
                                                      velum, COUPLED, COUPLED.pcm, COUPLED.SHARED)),
              *(UPSTREAM / name for name in (velum.NETWORK, velum.VOICE, 'crates/chimera/src/voice/human_airway.rs',
                'crates/chimera/tests/airway_adversarial.rs', 'Cargo.lock'))]
    details = {'case_id': case['id'], 'case_revision': case['measurement']['revision'], 'upstream_revision': revision,
               'invoked_from': str(Path.cwd())}
    return COUPLED.SHARED.record_measurement(
        args.run_id, CASE, inputs, details, measure, command=None, input_root=velum.screen.ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
