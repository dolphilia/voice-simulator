"""固定 /i/ の2つの倍音で、輪郭・ポート・声門流量の寄与を照合する。"""

import argparse
from pathlib import Path
import re
import subprocess
from tempfile import TemporaryDirectory

import numpy as np
from scipy.signal import firwin

import measure_fixed_lf_harmonic_transfer as harmonic
import measure_fixed_vowel_i_velum_port_only as port
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/fixed-vowel-i-velum-harmonic-transfer.json'
READ, COUPLED = port.READ, port.COUPLED
vowel = harmonic.vowel
RAD = (port.RAD[1], port.RAD[2], port.RAD[0], port.RAD[3])
DERIVATIVE = port.RAD[4]
GLOTTIS = 'glottal_flow_cm3_s'
EVIDENCE = ('upstream-observation.patch', *(f'{arm}/{name}' for arm in port.CONDITIONS for name in (
    'linear-case.json', 'linear-inspect.json', 'candidate-linear.csv', 'upstream-complex.csv', 'upstream-trace.csv',
    *harmonic.NETWORK_FILES, 'small-drive-case.json', 'small-drive.csv')))


def archive_inputs(case):
    spec = case['measurement']['reference']
    record, manifest, definition = COUPLED.smoothing.verified_reference(spec, case['upstream_revision'])
    return {'manifest.json': manifest, 'case.json': definition,
            **{f'{arm}-{name}': COUPLED.verified_path(record, f'artifacts/{arm}-{name}')
               for arm in port.CONDITIONS for name in ('input.json', 'internal.csv', 'upper.f64', 'pcm.wav', 'upper.f32')}}


def small_drive(cfg):
    end = cfg['steady_window_internal_samples'][1]
    time = np.arange(end) / cfg['internal_rate_hz']
    samples = np.sin(2 * np.pi * np.outer(time, cfg['frequencies_hz'])).sum(axis=1) * cfg['small_drive_per_tone_cm3_s']
    return [format(value, '.17g') for value in samples]


def arm_inputs(archive, cfg, arm, signal):
    base = READ(archive[f'{arm}-input.json'])
    start_hz, end_hz = cfg['frequencies_hz']
    linear = {**base, 'transfer': {'start_hz': start_hz, 'end_hz': end_hz, 'points': 2},
              'measurement': {**base['measurement'], 'peak_search_min_hz': start_hz}}
    drive = {**base, 'fixed_airway': {**base['fixed_airway'], 'sample_count': len(signal)},
             'voice': {**base['voice'], 'gate': 0.0},
             'fixed_voice_probe': {**base['fixed_voice_probe'], 'prescribed_flow_cm3_s': signal}}
    return linear, drive


def capture(case, archive, out, execute):
    cfg = case['measurement']
    signal = small_drive(cfg)
    cli = ['cargo', 'run', '--locked', '--offline', '--release', '-p', 'vocal-cli', '--']
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera', '--test', 'airway',
             'fdtd_impulse_response_agrees_with_frequency_domain_model'],
            cwd=UPSTREAM, stdout=out / 'upstream-airway-test.log')
    with TemporaryDirectory(prefix='velum-transfer-', dir=out.parent) as temporary:
        scratch = Path(temporary)
        code = scratch / 'source'
        code.mkdir()
        snapshot = scratch / 'upstream.tar'
        execute(['git', 'archive', case['upstream_revision']], cwd=UPSTREAM, stdout=snapshot)
        execute(['tar', '-xf', str(snapshot), '-C', str(code)])
        (out / 'upstream-observation.patch').write_text(harmonic.patch_complex_radiation(code))
        upper = harmonic.build_upstream_probe(vowel.PROBE, scratch, execute, upstream=code,
                                              extra_libraries=('serde_json',), cargo_args=('--offline',))
        for arm in port.CONDITIONS:
            folder = out / arm
            folder.mkdir()
            linear, forced = arm_inputs(archive, cfg, arm, signal)
            linear_path = folder / 'linear-case.json'
            small_path = folder / 'small-drive-case.json'
            port.write_case(linear_path, linear)
            port.write_case(small_path, forced)
            execute([*cli, 'inspect', str(linear_path)], stdout=folder / 'linear-inspect.json')
            execute([*cli, 'transfer', str(linear_path), str(folder / 'candidate-linear.csv')])
            execute([*cli, 'render', str(small_path), str(folder / 'small-drive.csv')])
            execute([str(upper), '--case', str(linear_path), str(folder)], cwd=UPSTREAM,
                    stdout=folder / 'upstream-complex.csv')


def candidate_elements(report):
    model = report['transfer']
    nodes = np.array([[node[key] for key in vowel.NODE_FIELDS] for node in model['nodes']])
    branches = np.array([(*edge['nodes'], edge['open'], edge['inertance'], edge['resistance'])
                         for edge in model['branches']])
    cut, = model['cut']
    source = {name: model[name] for name in ('inject', 'lips', 'nose')}
    return nodes, branches, {**source, 'cut': tuple(branches[cut, :2].astype(int))}


def upstream_complex(path, frequencies, source):
    raw = np.loadtxt(path, delimiter=',', ndmin=2)
    if (raw.shape[1] != 4 or not np.isfinite(raw).all() or not np.isin(raw[:, 0], frequencies).all()
            or not np.isin(raw[:, 1], (-1, source['lips'], source['nose'])).all()):
        raise ValueError('固定上流の複素放射流量の周波数または節点が不正です')
    result = []
    for frequency in frequencies:
        rows = raw[raw[:, 0] == frequency]
        values = {int(node): complex(real, imag) for _, node, real, imag in rows}
        if len(rows) != len(values) or not {-1, source['lips']} <= values.keys():
            raise ValueError('固定上流の複素放射流量の節点が欠落または重複しています')
        lips, nose, total = values[source['lips']], values.get(source['nose'], 0j), values[-1]
        result.append((lips, nose, total - lips - nose, total))
    return np.asarray(result)


def max_row_relative(actual, expected):
    scale = abs(expected).max(axis=1)
    return float((np.max(abs(actual - expected), axis=1) / np.where(scale > 0, scale, 1.)).max())


def discrete_system(frequency, fs, nodes, branches, source):
    c, fixed, area, mass, wall_r, stiffness, share, rad_l, rad_r = nodes.T
    visited_edges = []
    degree = np.zeros(len(nodes), dtype=int)
    inverse_inertance = np.zeros(len(nodes))
    for a, b, opening, inertance, resistance in branches:
        left, right = int(a), int(b)
        degree[[left, right]] += 1
        if opening and (left, right) != source['cut']:
            inverse_inertance[[left, right]] += 1 / inertance
            visited_edges.append((left, right, inertance, resistance))
    # 時間領域の分岐節点の安定化も反映する。
    effective = np.where(degree >= 3, np.maximum(c, inverse_inertance / (2.4 * fs * fs)), c)
    delay = np.exp(-2j * np.pi * frequency / fs)
    backward = (1 - delay) * fs
    midpoint = (1 + delay) / 2
    wall = np.zeros(len(nodes), dtype=complex)
    wall_live = area > 0
    wall[wall_live] = delay * area[wall_live] / (
        mass[wall_live] * backward + wall_r[wall_live] * midpoint
        + stiffness[wall_live] * delay / backward)
    end = np.zeros_like(wall)
    end_live = rad_l > 0
    end[end_live] = midpoint / rad_r[end_live] + midpoint**2 / (rad_l[end_live] * backward)
    matrix = np.diag(backward * effective + wall + end + 1e30 * fixed)
    for left, right, inertance, resistance in visited_edges:
        y = delay / (resistance + inertance * backward)
        matrix[left, left] += y
        matrix[right, right] += y
        matrix[left, right] -= y
        matrix[right, left] -= y
    return matrix, wall, end, share


def radiation_from_pressure(pressure, wall, end, share, source):
    end_flow = end * pressure
    lips, nose = (end_flow[source[name]] for name in ('lips', 'nose'))
    wall_radiation = (pressure * wall) @ share
    return lips, nose, wall_radiation, (wall_radiation + lips) + nose


def discrete_transfer(freqs, fs, nodes, branches, source):
    result = []
    for frequency in freqs:
        matrix, wall, end, share = discrete_system(frequency, fs, nodes, branches, source)
        rhs = np.zeros(len(nodes), dtype=complex)
        rhs[source['inject']] = 1.
        pressure = np.linalg.solve(matrix, rhs)
        result.append(radiation_from_pressure(pressure, wall, end, share, source))
    return np.asarray(result)


def spectra(tracks, start, stop, fs, frequencies):
    size = stop - start
    data = np.column_stack([tracks[field][start:stop] for field in (GLOTTIS, *RAD, DERIVATIVE)])
    kernel = np.exp(-2j * np.pi / fs * np.outer(frequencies, np.arange(size)))
    direct = kernel @ data / size
    bins = np.rint(frequencies * size / fs).astype(int)
    fft = np.fft.rfft(data, axis=0)[bins] / size
    boundary = fs * (tracks[RAD[-1]][stop - 1] - tracks[RAD[-1]][start - 1]) / size
    delta = fs * (1 - np.exp(-2j * np.pi * frequencies / fs))
    reconstructed = delta * fft[:, -2] + boundary
    errors = max_row_relative(direct, fft), max_row_relative(reconstructed[:, None], fft[:, -1:])
    return fft[:, :1], fft[:, 1:-1], errors


def projection(value, target):
    return float((value * np.conj(target)).real / abs(target)**2)


def describe_change(frequencies, observed, q, discrete, pcm):
    # Q00 を共通基準とし、I(X) = (X11−X10)−(X01−X00)。
    def contrast(series):
        return (series['open'] - series['shape_only']) - (series['port_only'] - series['closed'])
    full = contrast(observed)
    geometry = contrast(discrete) * q['closed']
    source = contrast({arm: discrete[arm] * (q[arm] - q['closed']) for arm in port.CONDITIONS})
    remainder = contrast({arm: observed[arm] - discrete[arm] * q[arm] for arm in port.CONDITIONS})
    pcm_change = contrast(pcm)
    rows = []
    for index, frequency in enumerate(frequencies):
        combined = full[index, -1]
        terms = {key: values[index, -1] for key, values in (
            ('linear_geometry', geometry), ('glottal_flow', source), ('finite_amplitude_remainder', remainder))}
        rows.append({
            'frequency_hz': int(frequency),
            'radiation_interaction_cm3_s': harmonic.pair(combined),
            'pcm_interaction': harmonic.pair(pcm_change[index]),
            'terms_cm3_s': {key: harmonic.pair(value) for key, value in terms.items()},
            'relative_magnitudes': {key: float(abs(value) / abs(combined)) for key, value in terms.items()},
            'projection_on_observed_interaction': {key: projection(value, combined) for key, value in terms.items()},
            'component_interactions_cm3_s': {key: harmonic.pair(val)
                                             for key, val in zip(vowel.COMPONENTS, full[index])},
        })
    return rows, max_row_relative(geometry + source + remainder, full)


def analyze(case, archive, out):
    cfg = case['measurement']
    fs, rate = cfg['internal_rate_hz'], cfg['output_rate_hz']
    first, end = cfg['steady_window_internal_samples']
    start_pcm, end_pcm = cfg['steady_pcm_frames']
    frequency = np.asarray(cfg['frequencies_hz'])
    signal = small_drive(cfg)
    baseline = READ(archive['case.json'])
    count = baseline['measurement']['internal_samples'][1]
    duration = (end - first) / fs
    bins = np.rint(frequency * duration).astype(int)
    tone_bins = np.rint(frequency / cfg['f0_hz']).astype(int)
    checks = {'registered_coherent_window_frequencies_and_clock': (
        np.array_equal(bins / duration, frequency)
        and np.array_equal(tone_bins * cfg['f0_hz'], frequency)
        and int(duration * cfg['f0_hz']) == duration * cfg['f0_hz']
        and [first, end] == [start_pcm * (fs // rate), end_pcm * (fs // rate)]
        and [first, end] == [value * (fs // rate) for value in baseline['measurement']['steady_output_frames']])}
    tolerance = cfg['complex_identity_peak_relative_error_lt']
    analog_bound = cfg['continuous_solver_peak_relative_error_lt']
    discrete_bound = cfg['discrete_small_drive_peak_relative_error_lt']
    q, natural, discrete = {}, {}, {}
    pcm_harmonics, results = {}, {}
    mismatch = []
    for arm in port.CONDITIONS:
        folder = out / arm
        linear, drive = arm_inputs(archive, cfg, arm, signal)
        report = READ(folder / 'linear-inspect.json')
        nodes, branches, source = candidate_elements(report)
        upper_nodes, upper_branches, upper_source = harmonic.source_elements(
            {name: folder / name for name in harmonic.NETWORK_FILES})
        checks[f'{arm}/conditions_and_linear_source'] = (
            READ(folder / 'linear-case.json') == report['case'] == linear
            and READ(folder / 'small-drive-case.json') == drive
            and all(upper_source[key] == value for key, value in source.items())
            and report['fixed_airway']['velum_port_cm2'] == linear['fixed_voice_probe']['velum_area_override_cm2'])
        cli = vowel.read_numeric_csv(folder / 'candidate-linear.csv', vowel.CANDIDATE_FIELDS)
        continuous = cli[:, [5, 7, 9, 1]] + 1j * cli[:, [6, 8, 10, 2]]
        upper = upstream_complex(folder / 'upstream-complex.csv', frequency, upper_source)
        upstream_magnitude = vowel.read_numeric_csv(folder / 'upstream-trace.csv', vowel.UPSTREAM_FIELDS)
        continuous_errors = {
            'cli_vs_dense': max_row_relative(continuous, vowel.independent_response(frequency, nodes, branches, source)),
            'upstream_vs_dense': max_row_relative(upper, vowel.independent_response(frequency, upper_nodes, upper_branches, upper_source)),
            'cli_vs_upstream': max_row_relative(continuous, upper),
        }
        checks[f'{arm}/continuous_transfer_matches_independent_solves'] = (
            np.array_equal(cli[:, 0], frequency) and np.array_equal(upstream_magnitude[:, 0], frequency)
            and max_row_relative(abs(upper[:, -1:]), upstream_magnitude[:, 1:2]) < analog_bound
            and all(error < analog_bound for error in continuous_errors.values()))
        predicted = discrete_transfer(frequency, fs, nodes, branches, source)
        discrete[arm] = predicted
        _, raw = COUPLED.pcm.read_columns(folder / 'small-drive.csv', end)
        q_small, r_small, small_identities = spectra(raw, first, end, fs, frequency)
        measured = r_small / q_small
        checks[f'{arm}/discrete_matches_small_drive'] = (
            port.SAME(raw[GLOTTIS], np.asarray(signal, dtype=float))
            and all(error < tolerance for error in small_identities)
            and max_row_relative(predicted, measured) < discrete_bound
            and np.all(abs(predicted[:, -1] - measured[:, -1]) < abs(continuous[:, -1] - measured[:, -1])))
        _, reference = COUPLED.pcm.read_columns(archive[f'{arm}-internal.csv'], count)
        upper_trace = port.velum.screen.prior.binary_trace(archive[f'{arm}-upper.f64'], count, len(port.FIELDS))
        q[arm], natural[arm], natural_identities = spectra(reference, first, end, fs, frequency)
        upper_q, upper_natural, upper_identities = spectra(dict(zip(port.FIELDS, upper_trace.T)), first, end, fs, frequency)
        checks[f'{arm}/natural_spectra_and_finite_window_derivative'] = (
            all(error < tolerance for error in (*natural_identities, *upper_identities))
            and max_row_relative(q[arm], upper_q) < tolerance
            and max_row_relative(natural[arm], upper_natural) < tolerance)
        pcm = COUPLED.read_pcm(archive[f'{arm}-pcm.wav'], count // (fs // rate), rate)
        pcm_harmonics[arm] = np.fft.rfft(pcm[start_pcm:end_pcm])[bins] / (end_pcm - start_pcm)
        observed_transfer = natural[arm] / q[arm]
        finite_error = abs(observed_transfer[:, -1] - predicted[:, -1]) / abs(observed_transfer[:, -1])
        mismatch.extend(finite_error)
        results[arm] = {'continuous_solver_errors': continuous_errors, 'discrete_small_drive_error': max_row_relative(predicted, measured),
                        'response': [{
                            'frequency_hz': int(f), 'glottal_flow_cm3_s': harmonic.pair(q[arm][i, 0]),
                            'continuous': dict(zip(vowel.COMPONENTS, map(harmonic.pair, continuous[i]))),
                            'discrete': dict(zip(vowel.COMPONENTS, map(harmonic.pair, predicted[i]))),
                            'small_drive': dict(zip(vowel.COMPONENTS, map(harmonic.pair, measured[i]))),
                            'natural': dict(zip(vowel.COMPONENTS, map(harmonic.pair, observed_transfer[i]))),
                            'natural_total_relative_error_using_discrete': float(finite_error[i]),
                        } for i, f in enumerate(frequency)]}
    interactions, identity_error = describe_change(frequency, natural, q, discrete, pcm_harmonics)
    checks['measurable_finite_amplitude_remainder'] = max(mismatch) >= cfg['finite_amplitude_total_mismatch_minimum_relative']
    checks['interaction_reconstructed_from_three_terms'] = identity_error < tolerance
    return {'checks': {key: bool(value) for key, value in checks.items()},
            'conditions': results, 'interactions': interactions, 'interaction_reconstruction_error': identity_error}


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

    dependencies = [harmonic, vowel, port, port.velum, COUPLED, COUPLED.pcm, COUPLED.fixed_lf, COUPLED.SHARED]
    inputs = [CASE, Path(__file__), vowel.PROBE, *archive.values(), *COUPLED.SHARED.candidate_sources(),
              *(Path(module.__file__) for module in dependencies),
              WORKSPACE / 'tools/measure_vowel_open_o_high_bandwidth.py',
              *(UPSTREAM / name for name in (harmonic.FREQUENCY, port.velum.NETWORK,
                'crates/chimera/tests/airway.rs', 'crates/chimera/src/voice/human_airway.rs', 'Cargo.lock'))]
    details = {'case_id': case['id'], 'case_revision': case['measurement']['revision'],
               'upstream_revision': revision, 'invoked_from': str(Path.cwd())}
    return COUPLED.SHARED.record_measurement(args.run_id, CASE, inputs, details, measure, command=None, input_root=port.velum.screen.ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
