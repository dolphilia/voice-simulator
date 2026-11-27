"""固定 /i/ の2,310 Hzで平均流量による口蓋帆ポート抵抗を検査する。"""

import argparse
from pathlib import Path
import re
import subprocess

import numpy as np

import measure_fixed_vowel_i_velum_harmonic_transfer as previous
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/fixed-vowel-i-velum-mean-flow-tangent.json'
READ, COUPLED = previous.READ, previous.COUPLED
velum = previous.port.velum
vowel, pair = previous.vowel, previous.harmonic.pair
EVIDENCE = ('natural-case.json', 'natural.csv', 'natural.wav', 'linear-case.json', 'linear-inspect.json', 'linear.csv')


def archive_inputs(case):
    cfg = case['measurement']
    spec = cfg['reference']
    record = COUPLED.run_manifest(spec['run'], spec['case'], case['upstream_revision'])
    run, header = record
    manifest = run / 'manifest.json'
    summary = COUPLED.verified_path(record, 'summary.json')
    failed = {name for name, value in READ(summary)['checks'].items() if not value}
    if header['status'] != 'fail' or sha256(manifest) != spec['sha256'] or failed != {'measurable_finite_amplitude_remainder'}:
        raise ValueError('事前仮説の不合格を含む前回の記録が一致しません')
    entry, = (row for row in header['inputs'] if row['path'].endswith(f'/cases/{spec["case"]}.json'))
    definition = run / header['source_snapshot'] / entry['path']
    if sha256(definition) != entry['sha256']:
        raise ValueError('保存された比較ケースが一致しません')
    arm = cfg['condition']
    underlying = previous.archive_inputs(READ(definition))
    return {
        'reference-manifest.json': manifest, 'reference-case.json': definition, 'reference-summary.json': summary,
        **{f'archive-{name}': underlying[f'{arm}-{name}'] for name in ('input.json', 'internal.csv', 'upper.f64', 'pcm.wav')},
        **{f'archive-{name}': COUPLED.verified_path(record, f'artifacts/{arm}/{name}')
           for name in ('linear-case.json', 'linear-inspect.json', 'candidate-linear.csv', *previous.harmonic.NETWORK_FILES)},
    }


def capture(archive, out, execute):
    cli = ['cargo', 'run', '--locked', '--offline', '--release', '-p', 'vocal-cli', '--']
    for output, recorded in (('natural-case.json', 'input.json'), ('linear-case.json', 'linear-case.json')):
        (out / output).write_bytes(archive[f'archive-{recorded}'].read_bytes())
    natural = out / 'natural-case.json'
    linear = out / 'linear-case.json'
    execute([*cli, 'render', str(natural), str(out / 'natural.csv')])
    execute([*cli, 'render-pcm', str(natural), str(out / 'natural.wav'), '--no-trace', '128'])
    execute([*cli, 'inspect', str(linear)], stdout=out / 'linear-inspect.json')
    execute([*cli, 'transfer', str(linear), str(out / 'linear.csv')])
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera', '--test', 'airway_adversarial',
             'steady_flow_through_a_short_constriction_obeys_bernoulli_with_jet_loss'],
            cwd=UPSTREAM, stdout=out / 'upstream-pressure-loss-test.log')


def port_parameters(geometry):
    tubes = {tube['name']: tube for tube in geometry['tubes']}
    pharynx = tubes['pharynx']
    a = pharynx['first_node'] + pharynx['cells'] - 1
    b = tubes['nasal']['first_node']
    sections = geometry['sections']
    area = geometry['velum_port_cm2']
    rho = 1.14e-3
    contraction = 0.3 * rho / (2 * area**2)
    coefficients = tuple(contraction + 0.8 * rho / 2 * max(0., 1 / area - 1 / sections[node]['area_cm2'])**2
                         for node in (b, a))
    return (a, b), coefficients


def branch_waveform(tracks, first, end, fs, frequency, coefficients, inertance, resistance):
    flow = tracks[velum.PORT[1]]
    pressure = tracks[velum.PORT[2]] - tracks[velum.PORT[3]]
    segment = flow[first:end]
    drop = np.where(segment >= 0., *coefficients) * segment * abs(segment)
    length = end - first
    basis = np.exp(-2j * np.pi * frequency / fs * np.arange(length)) / length
    flow_hat = basis @ segment
    pressure_hat = basis @ pressure[first:end]
    nonlinear_hat = basis @ drop
    delay = np.exp(-2j * np.pi * frequency / fs)
    impedance = resistance + inertance * (1 - delay) * fs
    # 有限窓の端を越える前標本の値を陽に補う。
    edge_flow = (flow[end - 1] - flow[first - 1]) / length
    edge_pressure = (pressure[end - 1] - pressure[first - 1]) / length
    terms = (impedance * flow_hat, nonlinear_hat, inertance * fs * edge_flow,
             -delay * pressure_hat, edge_pressure)
    return {'mean': float(segment.mean()), 'rms': float(np.sqrt(np.mean(segment**2))),
            'forward_samples': int(np.sum(segment > 0.)), 'reverse_samples': int(np.sum(segment < 0.)),
            'zero_samples': int(np.sum(segment == 0.)), 'flow_hat': flow_hat, 'nonlinear_hat': nonlinear_hat,
            'drive_hat': basis @ tracks[previous.GLOTTIS][first:end],
            'radiation_hat': basis @ np.column_stack([tracks[key][first:end] for key in previous.RAD]),
            'pressure_residual': float(abs(sum(terms)) / max(map(abs, terms)))}


def pressure_source_response(frequency, fs, nodes, branches, source, edge):
    matrix, wall, end, share = previous.discrete_system(frequency, fs, nodes, branches, source)
    left, right, _, inertance, resistance = branches[edge]
    left, right = int(left), int(right)
    delay = np.exp(-2j * np.pi * frequency / fs)
    impedance = resistance + inertance * (1 - delay) * fs
    rhs = np.zeros(matrix.shape[0], dtype=complex)
    rhs[source['inject']] = 1.
    pressure_baseline = np.linalg.solve(matrix, rhs)
    pair_rhs = np.zeros_like(rhs)
    pair_rhs[[left, right]] = [1 / impedance, -1 / impedance]
    pressure_loss = np.linalg.solve(matrix, pair_rhs)
    radiation = lambda pressure: np.asarray(previous.radiation_from_pressure(pressure, wall, end, share, source))
    port = lambda pressure: delay * (pressure[left] - pressure[right]) / impedance
    return radiation(pressure_baseline), radiation(pressure_loss), port(pressure_baseline), port(pressure_loss) - 1 / impedance


def describe_edition(cfg, tracks, nodes, branches, source, edge, coefficients):
    first, end = cfg['steady_window_internal_samples']
    fs, frequency = cfg['internal_rate_hz'], cfg['frequency_hz']
    inertia, resistance = branches[edge, 3:]
    observed = branch_waveform(tracks, first, end, fs, frequency, coefficients, inertia, resistance)
    baseline, pressure_gain, port_gain, port_feedback = pressure_source_response(
        frequency, fs, nodes, branches, source, edge)
    mean = observed['mean']
    r_increment = 2 * coefficients[int(mean < 0.)] * abs(mean)
    perturbed = branches.copy()
    perturbed[edge, 4] += r_increment
    tangent, = previous.discrete_transfer([frequency], fs, nodes, perturbed, source)
    # 追加抵抗の圧力源を戻し、ポートの流量への帰還を含めて同じ接線解を求める。
    tangent_pressure = r_increment * port_gain / (1 - r_increment * port_feedback)
    rank_one = baseline + pressure_gain * tangent_pressure
    observed_transfer = observed['radiation_hat'] / observed['drive_hat']
    pressure_hat = observed['nonlinear_hat'] / observed['drive_hat']
    replay = baseline + pressure_gain * pressure_hat
    base_error = abs(observed_transfer - baseline)
    tangent_error = abs(observed_transfer - tangent)
    replay_error = abs(observed_transfer - replay)
    improvement = 1 - tangent_error[1] / base_error[1]
    metrics = {}
    for key, response in (('zero_flow', baseline), ('mean_flow_tangent', tangent), ('observed_port_loss', replay)):
        metrics[key] = {
            'radiation_transfer': dict(zip(vowel.COMPONENTS, map(pair, response))),
            'relative_complex_error': dict(zip(vowel.COMPONENTS, (abs(response - observed_transfer) / abs(observed_transfer)).tolist())),
            'nose_amplitude_error_db': float(20 * np.log10(abs(response[1]) / abs(observed_transfer[1]))),
            'nose_phase_error_deg': float(np.angle(response[1] / observed_transfer[1], deg=True)),
        }
    checks = {
        'windowed_port_pressure_balance': observed['pressure_residual'] < cfg['complex_identity_relative_error_lt'],
        'mean_flow_impedance_matches_rank_one_solution':
            previous.max_row_relative(rank_one[None, :], tangent[None, :]) < cfg['complex_identity_relative_error_lt'],
        'nose_error_reduction_reaches_prediction': bool(improvement >= cfg['minimum_nose_error_reduction_fraction']),
    }
    result = {
        'flow_cm3_s': {key: observed[key] for key in ('mean', 'rms')},
        'flow_sign_samples': {key: observed[key] for key in ('forward_samples', 'reverse_samples', 'zero_samples')},
        'loss_coefficients_cgs': dict(zip(('forward', 'reverse'), coefficients)),
        'original_resistance_cgs': float(resistance), 'tangent_resistance_increment_cgs': r_increment,
        'pressure_balance_relative_residual': observed['pressure_residual'],
        'port_flow_harmonic_cm3_s': pair(observed['flow_hat']),
        'nonlinear_pressure_harmonic_dyn_cm2': pair(observed['nonlinear_hat']),
        'mean_tangent_pressure_harmonic_dyn_cm2': pair(r_increment * observed['flow_hat']),
        'natural_radiation_transfer': dict(zip(vowel.COMPONENTS, map(pair, observed_transfer))),
        'responses': metrics, 'nose_error_reduction_fraction': float(improvement),
        'nose_error_reduction_fraction_using_observed_port_loss': float(1 - replay_error[1] / base_error[1]),
        'nose_residual_after_observed_port_loss': pair(observed_transfer[1] - replay[1]),
    }
    return checks, result, observed_transfer


def analyze(case, archive, out):
    cfg = case['measurement']
    fs, frequency = cfg['internal_rate_hz'], cfg['frequency_hz']
    first, end = cfg['steady_window_internal_samples']
    before = READ(archive['reference-case.json'])['measurement']
    summary = READ(archive['reference-summary.json'])
    arm, recorded = cfg['condition'], READ(out / 'natural-case.json')
    observed_before, = [row for row in summary['conditions'][arm]['response'] if row['frequency_hz'] == frequency]
    inspect = READ(out / 'linear-inspect.json')
    layout = inspect['fixed_airway']
    nodes, edges, source = previous.candidate_elements(inspect)
    upper_nodes, upper_edges, upper_source = previous.harmonic.source_elements(
        {name: archive[f'archive-{name}'] for name in previous.harmonic.NETWORK_FILES})
    port_nodes, coefficients = port_parameters(layout)
    checks = {
        'registered_case_and_coherent_window': (
            fs == before['internal_rate_hz'] == recorded['fixed_airway']['sample_rate_hz']
            and [first, end] == before['steady_window_internal_samples']
            and frequency in before['frequencies_hz'] and 0 < first < end
            and (end - first) * frequency % fs == 0
            and all(upper_source[key] == item for key, item in source.items())
            and layout['velum_port_cm2'] == recorded['fixed_voice_probe']['velum_area_override_cm2']),
        'current_cli_reproduces_archived_normal_voice_and_linear_transfer': all(
            sha256(out / filename) == sha256(archive[f'archive-{archived}']) for filename, archived in (
                ('natural-case.json', 'input.json'), ('natural.csv', 'internal.csv'), ('natural.wav', 'pcm.wav'),
                ('linear-case.json', 'linear-case.json'), ('linear-inspect.json', 'linear-inspect.json'),
                ('linear.csv', 'candidate-linear.csv'))),
    }
    count = recorded['fixed_airway']['sample_count']
    _, candidate = COUPLED.pcm.read_columns(out / 'natural.csv', count)
    upper = velum.screen.prior.binary_trace(archive['archive-upper.f64'], count, len(velum.FIELDS))
    notes, observations = {}, {}
    for edition, tracks, e_nodes, e_branches, e_source in (
        ('candidate', candidate, nodes, edges, source),
        ('upstream', dict(zip(velum.FIELDS, upper.T)), upper_nodes, upper_edges, upper_source),
    ):
        edge, = np.flatnonzero((e_branches[:, :2] == port_nodes).all(axis=1) & (e_branches[:, 2] == 1))
        conditions, notes[edition], observations[edition] = describe_edition(
            cfg, tracks, e_nodes, e_branches, e_source, edge, coefficients)
        checks.update({f'{edition}/{key}': answer for key, answer in conditions.items()})
    tol = cfg['complex_identity_relative_error_lt']
    preserved_model = np.array([complex(*observed_before['discrete'][key]) for key in vowel.COMPONENTS])
    current_model = np.array([complex(*notes['candidate']['responses']['zero_flow']['radiation_transfer'][key])
                              for key in vowel.COMPONENTS])
    checks['unmodified_discrete_transfer_matches_previous_run'] = (
        previous.max_row_relative(preserved_model[None, :], current_model[None, :]) < tol)
    checks['fixed_upstream_and_rebuild_agree_on_hypothesis'] = (
        checks['candidate/nose_error_reduction_reaches_prediction'] == checks['upstream/nose_error_reduction_reaches_prediction']
        and previous.max_row_relative(observations['candidate'][None, :], observations['upstream'][None, :])
        < cfg['remaining_series_relative_error_lt'])
    return {'checks': checks, 'condition': arm, 'frequency_hz': frequency, 'port_nodes': list(port_nodes),
            'editions': notes}


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
        capture(archive, out, execute)
        return analyze(case, archive, out)

    inputs = [CASE, Path(__file__), *archive.values(), *COUPLED.SHARED.candidate_sources(),
              *(Path(module.__file__) for module in (previous, previous.harmonic, previous.port, vowel, velum,
                                                      COUPLED, COUPLED.pcm, COUPLED.SHARED)),
              *(UPSTREAM / name for name in (velum.NETWORK, velum.VOICE, 'crates/chimera/src/voice/human_airway.rs',
                'crates/chimera/tests/airway_adversarial.rs', 'Cargo.lock'))]
    details = {'case_id': case['id'], 'case_revision': case['measurement']['revision'], 'upstream_revision': revision,
               'invoked_from': str(Path.cwd())}
    return COUPLED.SHARED.record_measurement(
        args.run_id, CASE, inputs, details, measure, command=None, input_root=velum.screen.ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
