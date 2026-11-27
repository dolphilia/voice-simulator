"""保存した固定 /i/ の流量から声門上の枝損失を鼻端へ伝える。"""

import argparse
from pathlib import Path
import re
import subprocess

import numpy as np

import measure_fixed_vowel_i_velum_oral_nasal_loss as prior
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/fixed-vowel-i-velum-supraglottal-loss.json'
READ, COUPLED = prior.READ, prior.COUPLED
harmonic, velum, tangent = prior.harmonic, prior.velum, prior.tangent
EVIDENCE = ()
HYPOTHESIS = 'remaining_supraglottal_branches_remove_ninety_percent_of_nose_residual'
BASELINE_GROUPS = ('port', 'oral', 'nasal')
NEW_GROUPS = ('pharynx', 'oral_link', 'piriform', 'piriform_inlet')


def archive_inputs(case):
    info = case['measurement']['reference']
    run, header = record = COUPLED.run_manifest(
        info['run'], 'fixed-vowel-i-velum-oral-nasal-loss', case['upstream_revision'])
    manifest = run / 'manifest.json'
    if header['status'] != 'fail' or sha256(manifest) != info['manifest_sha256']:
        raise ValueError('事前登録した収録のマニフェストと一致しません')
    summary = COUPLED.verified_path(record, 'summary.json')
    if {key for key, value in READ(summary)['checks'].items() if not value} != {info['known_failed_check']}:
        raise ValueError('収録時に不成立だった仮説の判定が一致しません')
    entry, = (item for item in header['inputs'] if Path(item['path']).name == prior.CASE.name)
    definition = run / header['source_snapshot'] / entry['path']
    if sha256(definition) != entry['sha256']:
        raise ValueError('保存済みの収録条件が一致しません')
    archive = prior.archive_inputs(READ(definition))
    return {**archive, 'recording-manifest.json': manifest, 'recording-case.json': definition,
            'recording-summary.json': summary,
            **{name: COUPLED.verified_path(record, f'artifacts/{name}') for name in prior.EVIDENCE}}


def reachable_branches(branches, source):
    """声門の枝を切り、咽頭入口に接続する枝番号を求める。"""
    adjacent = {}
    for edge, (left, right, opened, _, _) in enumerate(branches):
        a, b = int(left), int(right)
        if opened and (a, b) != source['cut']:
            adjacent.setdefault(a, []).append((b, edge))
            adjacent.setdefault(b, []).append((a, edge))
    pending = [source['inject']]
    nodes, visited = set(), set()
    while pending:
        node = pending.pop()
        if node in nodes:
            continue
        nodes.add(node)
        for neighbor, edge in adjacent[node]:
            visited.add(edge)
            pending.append(neighbor)
    return visited


def selected_groups(layout, branches, source):
    groups = prior.branch_groups(layout['tubes'], ('oral', 'nasal', 'pharynx', 'piriform'),
                                 branches, tangent.port_parameters(layout)[0])
    tubes = {tube['name']: tube for tube in layout['tubes']}
    pharynx_first = tubes['pharynx']['first_node']
    pharynx_end = pharynx_first + tubes['pharynx']['cells'] - 1
    pairs = branches[:, :2].astype(int)
    from_pharynx = (pairs[:, 0] >= pharynx_first) & (pairs[:, 0] <= pharynx_end)
    groups['oral_link'] = np.flatnonzero((pairs[:, 0] == pharynx_end) & (pairs[:, 1] == tubes['oral']['first_node']))
    groups['piriform_inlet'] = np.flatnonzero(from_pharynx & (pairs[:, 1] == tubes['piriform']['first_node']))
    groups['sinus'] = np.flatnonzero(pairs[:, 1] == tubes['sinus']['first_node'])
    selected = np.concatenate(list(groups.values()))
    if (any(len(groups[key]) != 1 for key in ('oral_link', 'piriform_inlet', 'sinus'))
            or len(selected) != len(set(selected)) or set(selected) != reachable_branches(branches, source)):
        raise ValueError('声門上の固定枝と咽頭入口の接続の対応が一致しません')
    return groups, selected


def forcing(frequency, fs, nodes, branches, selected, source):
    matrix, _, termination, _ = harmonic.discrete_system(frequency, fs, nodes, branches, source)
    chosen = branches[selected]
    left, right = chosen[:, :2].astype(int).T
    inertance, resistance = chosen[:, 3:].T
    impedance = resistance + inertance * fs * (1 - np.exp(-2j * np.pi * frequency / fs))
    dipoles = np.zeros((len(nodes), len(left)), dtype=complex)
    dipoles[left, np.arange(len(left))] = 1 / impedance
    dipoles[right, np.arange(len(left))] = -1 / impedance
    inlet = np.zeros(len(nodes), dtype=complex)
    inlet[source['inject']] = 1.
    nose = np.zeros_like(inlet)
    nose[source['nose']] = termination[source['nose']]
    return matrix, inlet, dipoles, nose


def inspect_edition(cfg, tracks, state, layout, nodes, branches, source, before):
    groups, selected = selected_groups(layout, branches, source)
    first, end = cfg['steady_window_internal_samples']
    frequency, fs = cfg['frequency_hz'], cfg['internal_rate_hz']
    basis = np.exp(-2j * np.pi * frequency * np.arange(end - first) / fs) / (end - first)
    drive = basis @ tracks[harmonic.GLOTTIS][1:]
    observed = (basis @ tracks['nose_flow_cm3_s'][1:]) / drive
    chosen = branches[selected]
    sinus = np.isin(selected, groups['sinus'])
    coefficients = tuple(np.where(sinus, 0., option) for option in prior.branch_coefficients(layout, chosen))
    pressure = prior.branch_pressure(frequency, fs, basis, state, layout, selected, branches, drive,
                                     coefficients=coefficients)
    matrix, inlet, dipoles, nose = forcing(frequency, fs, nodes, branches, selected, source)
    # 複素応答は内積の共役を取らず、鼻端を読む行を転置方程式で求める。
    readout = np.linalg.solve(matrix.T, nose)
    gain = readout @ dipoles
    base = readout @ inlet
    by_edge = gain * pressure['loss_per_drive']
    by_group = {key: by_edge[np.isin(selected, edges)].sum() for key, edges in groups.items()}
    before_all = base + sum(by_group[key] for key in BASELINE_GROUPS)
    end_all = base + by_edge.sum()
    direct = nose @ np.linalg.solve(matrix, inlet + dipoles @ pressure['loss_per_drive'])
    reconstructed = base + gain @ pressure['loss_from_pressure_per_drive']
    window = gain @ pressure['window_edge_per_drive']
    residual = observed - before_all
    improvement = float(1 - abs(observed - end_all) / abs(residual))
    recorded_residual = complex(*before['nose_residual_after_all_tested_losses'])
    scale = abs(observed)
    tolerance = cfg['parallel_calculation_relative_error_lt']
    checks = {
        'time_and_complex_branch_balance': bool(
            max(pressure['time_relative'].max(), pressure['spectral_relative'].max())
            < cfg['branch_balance_relative_error_lt']),
        'sinus_is_zero_loss_control': bool(
            not pressure['loss_per_drive'][sinus].any()
            and abs(pressure['loss_from_pressure_per_drive'][sinus]).max()
            < tolerance * abs(pressure['loss_per_drive']).max()),
        'adjoint_matches_direct_nose': bool(abs(end_all - direct) < tolerance * scale),
        'pressure_derived_losses_match_geometry': bool(
            abs(pressure['loss_per_drive'] - pressure['loss_from_pressure_per_drive']).max()
            < tolerance * abs(pressure['loss_per_drive']).max()
            and abs(reconstructed - end_all) < tolerance * scale),
        'previous_nose_residual_reproduced': bool(
            abs(residual - recorded_residual) < tolerance * abs(recorded_residual)),
    }
    pair = tangent.pair
    summary = {
        'branch_counts': {key: len(edges) for key, edges in groups.items()},
        'observed_nose_transfer': pair(observed),
        'nose_error_reduction_fraction': improvement,
        'nose_relative_error': {'prior': float(abs(residual) / scale), 'all_losses': float(abs(observed - end_all) / scale),
                                'including_branch_window_edges': float(abs(observed - end_all - window) / scale)},
        'nose_residual_after_all_losses': pair(observed - end_all),
        'nose_residual_including_branch_window_edges': pair(observed - end_all - window),
        'nose_transfer_change_from_branch_window_edges': pair(window),
        'nose_transfer_change_by_group': {key: pair(value) for key, value in by_group.items()},
        'projection_onto_prior_residual': {key: harmonic.projection(by_group[key], residual) for key in NEW_GROUPS},
        'max_relative_pressure_balance': {'time': float(pressure['time_relative'].max()),
                                          'complex': float(pressure['spectral_relative'].max())},
        'branches': [
            {'group': key, 'branch': int(edge), 'nodes': branches[edge, :2].astype(int).tolist(),
             'loss_pressure_per_drive': pair(pressure['loss_per_drive'][slot]),
             'nose_transfer_change': pair(by_edge[slot])}
            for key, group in groups.items() for slot, edge in enumerate(selected) if edge in group
        ],
    }
    return checks, summary


def recorded_editions(case, archive):
    cfg = case['measurement']
    first, end = cfg['steady_window_internal_samples']
    recorded = READ(archive['recording-case.json'])['measurement']
    fields = ('frequency_hz', 'internal_rate_hz', 'steady_window_internal_samples')
    if any(cfg[key] != recorded[key] for key in fields):
        raise ValueError('収録と解析の周波数または窓が一致しません')
    if (end - first) * cfg['frequency_hz'] % cfg['internal_rate_hz']:
        raise ValueError('事前登録した窓が観測周波数の整数周期を含みません')
    report = READ(archive['archive-linear-inspect.json'])
    layout = report['fixed_airway']
    nodes, branches, source = harmonic.candidate_elements(report)
    upper_nodes, upper_branches, upper_source = harmonic.harmonic.source_elements(
        {name: archive[f'archive-{name}'] for name in harmonic.harmonic.NETWORK_FILES})
    tracks, state = prior.candidate_state(archive['natural-network.csv'].parent, first, end, len(nodes), len(branches))
    upper_state = velum.screen.prior.binary_trace(archive['upper-network.f64'], end - first + 1,
                                                  len(upper_nodes) + len(upper_branches))
    count = READ(archive['natural-case.json'])['fixed_airway']['sample_count']
    upper_trace = velum.screen.prior.binary_trace(archive['upper.f64'], count, len(velum.FIELDS))
    upper_tracks = dict(zip(velum.FIELDS, upper_trace[first - 1:end].T))
    return layout, {
        'candidate': (tracks, state, nodes, branches, source),
        'upstream': (upper_tracks, upper_state, upper_nodes, upper_branches, upper_source),
    }


def analyze(case, archive):
    cfg = case['measurement']
    layout, recordings = recorded_editions(case, archive)
    _, _, _, branches, source = recordings['candidate']
    _, _, _, upper_branches, upper_source = recordings['upstream']
    order = prior.upstream_branch_order(branches, upper_branches)
    checks = {'aligned_directed_branch_topology_and_glottal_cut':
              source == upper_source and np.array_equal(branches[:, :3], upper_branches[order, :3])}
    before = READ(archive['recording-summary.json'])['editions']
    editions = {}
    for name, (channels, state_values, *model) in recordings.items():
        results, editions[name] = inspect_edition(cfg, channels, state_values, layout, *model, before[name])
        checks.update({f'{name}/{key}': value for key, value in results.items()})
    candidate, upstream = (editions[key] for key in ('candidate', 'upstream'))
    group_keys = tuple(candidate['nose_transfer_change_by_group'])
    deltas = [np.array([complex(*edition['nose_transfer_change_by_group'][key]) for key in group_keys])
              for edition in (candidate, upstream)]
    checks['group_changes_match_fixed_upstream'] = (
        harmonic.max_row_relative(deltas[0][None, :], deltas[1][None, :]) < cfg['edition_replay_relative_error_lt'])
    decisions = [edition['nose_error_reduction_fraction'] >= cfg['minimum_nose_error_reduction_fraction']
                 for edition in editions.values()]
    checks['both_editions_agree_on_registered_prediction'] = decisions[0] == decisions[1]
    checks[HYPOTHESIS] = all(decisions)
    return {'checks': checks, 'frequency_hz': cfg['frequency_hz'], 'editions': editions}


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
              *(Path(module.__file__) for module in (prior, tangent, harmonic, velum, COUPLED, COUPLED.SHARED)),
              *(UPSTREAM / name for name in (velum.NETWORK, velum.VOICE, 'crates/chimera/src/voice/human_airway.rs',
                'crates/chimera/tests/airway_adversarial.rs', 'Cargo.lock'))]
    details = {'case_id': case['id'], 'case_revision': case['measurement']['revision'], 'upstream_revision': revision,
               'invoked_from': str(Path.cwd())}
    return COUPLED.SHARED.record_measurement(
        args.run_id, CASE, inputs, details, measure, command=None, input_root=velum.screen.ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
