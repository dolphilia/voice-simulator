"""保存した一様管の口端流量を、固定距離の理想開口の軸上音圧へ変換する。"""

import argparse
import gzip
import json
import math
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

import numpy as np
from scipy.integrate import quad
from scipy.signal import lfilter

import measure_lip_crossing_thickness as stored
import measure_uniform_tube as shared
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/uniform-axial-observation.json'
CLI = ['cargo', 'run', '--locked', '--release', '-p', 'vocal-cli', '--']
COLUMNS = ('sample', 'mouth_flow_m3_s', 'disk_pressure_pa',
           'far_backward_pressure_pa', 'far_centered_pressure_pa')
RUNS = WORKSPACE / 'runs'


def load_saved_run(name, expected, revision, wanted):
    folder = RUNS / name
    manifest = folder / 'manifest.json'
    info = stored.read(manifest)
    if (info['case_id'] != expected or info['upstream_revision'] != revision
            or info.get('error') or info.get('storage_error')):
        raise ValueError(f'基準実行の条件を照合できません ({name})')
    hashes = {row['path']: row for row in info['outputs']}
    paths = {key: folder / key for key in wanted}
    for key, path in paths.items():
        if path.stat().st_size != hashes[key]['bytes'] or sha256(path) != hashes[key]['sha256']:
            raise ValueError(f'基準成果のハッシュを照合できません ({name}/{key})')
    return paths, manifest


def geometry(case, distance, rate):
    data = {key: value for key, value in case['geometry'].items() if key != 'distances_m'}
    return {**data, 'distance_m': distance, 'sample_rate_hz': rate}


def propagation(settings):
    area = settings['aperture_area_cm2'] * 1e-4
    distance = settings['distance_m']
    rate = settings['sample_rate_hz']
    density = settings['air_density_kg_m3']
    speed = settings['sound_speed_m_s']
    radius = np.sqrt(area / np.pi)
    tau_center = distance / speed
    extra = (area / np.pi) / (np.hypot(distance, radius) + distance) / speed
    return area, radius, distance, rate, density, speed, tau_center, extra


def exact_transfer(settings, frequencies, padding):
    area, _, r, fs, rho, c, travel, edge_delay = propagation(settings)
    w = 2 * np.pi * frequencies
    angle = w / fs
    along_axis = np.exp(-1j * w * (travel + padding / fs))
    disk = rho * c / area * along_axis * (-np.expm1(-1j * w * edge_delay))
    far_backward = rho / (2 * np.pi * r) * along_axis * fs * (-np.expm1(-1j * angle))
    far_centered = far_backward * np.exp(0.5j * angle)
    return np.column_stack((disk, far_backward, far_centered))


def rayleigh_quadrature(settings, frequencies, padding):
    area, radius, distance, fs, rho, c, _, _ = propagation(settings)
    values = []
    for f in frequencies:
        w = 2 * np.pi * f

        def integrand(s):
            radius_to_observer = np.hypot(s, distance)
            return np.exp(-1j * w * radius_to_observer / c) * (s / radius_to_observer)

        value = quad(integrand, 0, radius, complex_func=True, epsabs=1e-14, epsrel=1e-13)[0]
        values.append(1j * w * rho / area * value * np.exp(-1j * w * padding / fs))
    return np.asarray(values)


def apply_delay(signal, delay):
    # 8次元のモーメント連立方程式を解いて、Rustの積の形と独立に補間を組む。
    first_lag = math.floor(delay) - 3
    offsets = np.arange(8) + (first_lag - delay)
    weights = np.linalg.solve(np.vander(offsets, N=8, increasing=True).T, np.eye(8)[0])
    filtered = np.convolve(signal, weights)[:len(signal) - first_lag]
    return np.r_[np.zeros(first_lag), filtered]


def independent_wave(settings, flow, padding):
    area, _, r, fs, rho, c, travel, edge_delay = propagation(settings)
    delay = fs * travel + padding
    center = apply_delay(flow, delay)
    edge = apply_delay(flow, delay + fs * edge_delay)
    advance = apply_delay(flow, delay - 0.5)
    factor = rho * fs / (2 * np.pi * r)
    return np.column_stack((rho * c / area * (center - edge),
                            factor * np.diff(center, prepend=0),
                            factor * np.diff(advance, prepend=0)))


def raw_source(path, count):
    with gzip.open(path, 'rt') as f:
        header = f.readline().strip().split(',')
        names = ('sample', 'radiation_flow_cm3_s', 'radiation_flow_derivative_cm3_s2')
        data = np.loadtxt(f, delimiter=',', max_rows=count, usecols=tuple(header.index(key) for key in names))
    if data.shape != (count, 3) or not np.isfinite(data).all() or not np.array_equal(data[:, 0], np.arange(count)):
        raise ValueError(f'登録区間の口端流量を読み出せません ({path.name})')
    return data[:, 1], data[:, 2]


def prep_source(raw, kernel, taper_points):
    flow = lfilter(kernel, [1.], raw)
    phase = np.linspace(0, np.pi, taper_points)
    flow[-taper_points:] *= (1 + np.cos(phase)) / 2
    return flow


def peak_relative(a, b):
    return float(np.max(np.abs(a - b)) / np.max(np.abs(b)))


def complex_error(a, b):
    return float(np.max(np.abs(a / b - 1)))


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')


def onset(values):
    return int(np.flatnonzero(values)[0])


def run_observer(settings, source_path, config_path, temporary, execute):
    write_json(config_path, settings)
    execute([*CLI, 'observe-axis', str(config_path), str(source_path), str(temporary)])
    with temporary.open() as stream:
        if tuple(stream.readline().strip().split(',')) != COLUMNS:
            raise ValueError('音圧の出力列を照合できません')
        return np.loadtxt(stream, delimiter=',', ndmin=2)


def compare(settings, result, flow_cgs, case):
    _, _, _, rate, _, _, travel, edge_delay = propagation(settings)
    cfg = case['measurement']
    tol = case['criteria']
    pad = cfg['interpolation']['causal_padding_samples']
    frequencies = np.asarray(cfg['frequencies_hz'])
    q_first, q_last, q_step = cfg['quadrature_grid_hz']
    quad_freq = np.arange(q_first, q_last + q_step, q_step)
    analytic = exact_transfer(settings, frequencies, pad)
    relative_quad_error = complex_error(rayleigh_quadrature(settings, quad_freq, pad),
                                       exact_transfer(settings, quad_freq, pad)[:, 0])
    tail = math.floor((travel + edge_delay) * rate + pad) + 6
    count = flow_cgs.size + tail
    if result.shape != (count, len(COLUMNS)) or not np.isfinite(result).all():
        raise ValueError('音圧系列の長さまたは有限性が登録条件と一致しません')
    indices, mouth = result[:, 0], result[:, 1]
    pressure = result[:, 2:]
    flow = np.pad(flow_cgs * 1e-6, (0, tail))
    separate = independent_wave(settings, flow, pad)
    transform = np.exp((-2j * np.pi / rate) * np.outer(frequencies, indices))
    q_hat = transform @ flow
    h = (transform @ pressure) / q_hat[:, None]
    relative_h = h / analytic
    model_error = np.max(np.abs(relative_h - 1), axis=0)
    phase_raw = np.angle(h[-1, 1] / h[-1, 0], deg=True)
    phase_centered = np.angle(h[-1, 2] / h[-1, 0], deg=True)
    main_onset = onset(flow)
    first = [onset(row) for row in pressure.T]
    offsets = [sample - main_onset for sample in first]
    q_error = peak_relative(mouth, flow)
    p_error = [peak_relative(p, expected) for p, expected in zip(pressure.T, separate.T, strict=True)]
    corrected_vs_disk = complex_error(h[:, 2], h[:, 0])
    checks = {
        'sample_count_and_time_grid': bool(np.array_equal(indices, np.arange(count))),
        'volume_conversion': q_error <= tol['volume_conversion_peak_relative_max'],
        'causality_and_drained_filter': all(math.ceil(travel * rate) <= n <= math.ceil(travel * rate) + 2 for n in offsets)
        and bool(np.all(pressure[-1] == 0)),
        'independent_time_filter': max(p_error) <= tol['independent_sample_filter_peak_relative_max'],
        'exact_vs_rayleigh_integral': relative_quad_error <= tol['exact_vs_quadrature_relative_complex_max'],
        'disk_vs_continuous': bool(model_error[0] <= tol['native_disk_vs_continuous_relative_complex_max']),
        'far_vs_discrete': bool(max(model_error[1:]) <= tol['far_raw_vs_discrete_relative_complex_max']),
        'compensated_far_vs_disk': corrected_vs_disk <= tol['far_corrected_vs_disk_relative_complex_max'],
        'half_sample_phase_effect': abs(float(phase_raw)) >= tol['raw_phase_error_min_degrees_at_4000_hz']
        and abs(float(phase_centered)) <= tol['far_corrected_phase_residual_max_degrees_at_4000_hz'],
    }
    return checks, {
        'distance_m': settings['distance_m'], 'sample_rate_hz': rate, 'propagation_seconds': travel,
        'rim_minus_center_seconds': edge_delay,
        'first_pressure_sample': dict(zip(COLUMNS[2:], first, strict=True)),
        'processing_padding_samples': pad, 'mouth_first_sample': main_onset,
        'mouth_max_m3_s': float(np.max(np.abs(flow))), 'volume_conversion_relative_error': q_error,
        'peak_pressure_pa': np.max(np.abs(pressure), axis=0).tolist(),
        'independent_time_filter_relative_peak_error': p_error,
        'quadrature_max_complex_relative_error': relative_quad_error,
        'complex_model_max_relative_error': model_error.tolist(),
        'corrected_vs_disk_max_relative_error': corrected_vs_disk,
        'phase_at_4000_hz_raw_vs_disk_degrees': float(phase_raw),
        'phase_at_4000_hz_corrected_vs_disk_degrees': float(phase_centered),
        'frequencies': [
            {'hz': int(f), 'mouth_m3_s': [float(q.real), float(q.imag)],
             'disk': [float(row[0].real), float(row[0].imag)],
             'far_backward': [float(row[1].real), float(row[1].imag)],
             'far_centered': [float(row[2].real), float(row[2].imag)]}
            for f, q, row in zip(frequencies, q_hat, h, strict=True)
        ],
    }


def field(rows, key):
    return np.array([complex(*row[key]) for row in rows['frequencies']])


def measure_steady_flow(case, artifacts, execute):
    # 末尾をテーパーしない入力でも、最後の応答の後に無音まで出力する。
    rate, distance, flow = 96000, 0.5, 42.0
    count = 500
    settings = geometry(case, distance, rate)
    with TemporaryDirectory(prefix='steady-flow-', dir=artifacts) as temporary:
        scratch = Path(temporary)
        source = scratch / 'mouth.csv'
        np.savetxt(source, np.column_stack((np.arange(count), np.full(count, flow))),
                   delimiter=',', comments='', header='sample,mouth_flow_cm3_s', fmt=['%d', '%.17g'])
        observed = run_observer(settings, source, scratch / 'case.json', scratch / 'pressure.csv', execute)
    pressure = observed[:, 2:]
    _, _, _, _, _, _, travel, edge_delay = propagation(settings)
    pad = case['measurement']['interpolation']['causal_padding_samples']
    max_lag = math.floor((travel + edge_delay) * rate + pad) + 5
    stationary_first = max_lag
    stationary_last = count - 1
    checked = (len(observed) == count + max_lag + 1
               and not np.any(pressure[stationary_first:stationary_last + 1])
               and np.any(pressure[stationary_last + 1:])
               and not np.any(pressure[-1]))
    return bool(checked), {
        'settings': settings, 'constant_flow_cm3_s': flow, 'input_samples': count,
        'stationary_inclusive_samples': [stationary_first, stationary_last],
        'last_pressure_sample_pa': pressure[-1].tolist(), 'last_nonzero_sample': int(np.flatnonzero(
            np.any(pressure, axis=1))[-1]),
    }


def measure(case, trace_paths, fir_paths, artifacts, execute):
    cfg, tol = case['measurement'], case['criteria']
    distances = case['geometry']['distances_m']
    checks, records, comparisons = {}, {}, {}
    for source in case['sources']:
        key, rate = (source[k] for k in ('grid', 'sample_rate_hz'))
        tube = stored.read(trace_paths[f'artifacts/{key}/case.json'])['tube']
        if tube['area_cm2'] != case['geometry']['aperture_area_cm2'] or tube['sample_rate_hz'] != rate:
            raise ValueError(f'入口系列の管設定が一致しません ({key})')
        kernel = np.loadtxt(fir_paths[f'artifacts/{key}-fir.csv'], skiprows=1)
        count = round(rate * cfg['input_seconds'])
        retained = round(rate * cfg['retained_prefix_seconds'])
        observed = {}
        for method in source['methods']:
            label = f'{key}-{method}'
            folder = artifacts / label
            folder.mkdir()
            raw, native_derivative = raw_source(trace_paths[f'artifacts/{key}/{method}.csv.gz'], count)
            derivative_error = peak_relative(np.diff(raw, prepend=0) * rate, native_derivative)
            checks[f'{label}/original_derivative'] = derivative_error <= tol['stored_derivative_peak_relative_max']
            flow = prep_source(raw, kernel, round(rate * cfg['end_taper_seconds']))
            records[label] = {'original_derivative_relative_peak_error': derivative_error, 'distances': {}}
            with TemporaryDirectory(prefix='axis-', dir=artifacts) as scratch:
                scratch = Path(scratch)
                input_file = scratch / 'mouth.csv'
                np.savetxt(input_file, np.column_stack((np.arange(count), flow)),
                           delimiter=',', fmt=['%d', '%.17g'], comments='', header='sample,mouth_flow_cm3_s')
                for distance in distances:
                    directory = folder / str(distance)
                    directory.mkdir()
                    settings = geometry(case, distance, rate)
                    output = scratch / f'{distance}.csv'
                    result = run_observer(settings, input_file, directory / 'case.json', output, execute)
                    local, row = compare(settings, result, flow, case)
                    checks.update({f'{label}/{distance}/{name}': value for name, value in local.items()})
                    records[label]['distances'][str(distance)] = row
                    observed[method, distance] = result[:, 2]
                    prefix = directory / 'observation-prefix.csv'
                    np.savetxt(prefix, result[:retained], delimiter=',', comments='', header=','.join(COLUMNS),
                               fmt=['%d', *(['%.17g'] * 4)])
                    stored.compress(prefix)
            by_distance = records[label]['distances']
            magnitude_error = max(complex_error(np.abs(field(by_distance[str(a)], 'disk'))
                                                / np.abs(field(by_distance[str(b)], 'disk')),
                                                np.full(len(cfg['frequencies_hz']), b / a))
                                  for a, b in zip(distances, distances[1:]))
            checks[f'{label}/inverse_distance'] = magnitude_error <= tol['pressure_inverse_distance_all_ratios_relative_max']
            records[label]['max_inverse_distance_relative_error'] = magnitude_error

        for distance in distances:
            upper_error = peak_relative(observed['fdtd', distance], observed['upstream', distance])
            checks[f'{key}/{distance}/upstream_pressure'] = upper_error <= tol['upstream_pressure_peak_relative_max']
            comparison = {'candidate_vs_upstream_disk_peak_relative_error': upper_error}
            if 'waveguide' in source['methods']:
                native, guide = (records[f'{key}-{method}']['distances'][str(distance)]
                                 for method in ('fdtd', 'waveguide'))
                q_ratio = field(guide, 'mouth_m3_s') / field(native, 'mouth_m3_s')
                p_ratio = q_ratio * field(guide, 'disk') / field(native, 'disk')
                error = complex_error(p_ratio, q_ratio)
                checks[f'{key}/{distance}/waveguide_ratio_retained'] = error <= tol['waveguide_to_fdtd_ratio_recovered_relative_max']
                comparison['waveguide_ratio_relative_error'] = error
            comparisons[f'{key}/{distance}'] = comparison
    steady_pass, steady = measure_steady_flow(case, artifacts, execute)
    checks['steady_flow_and_complete_tail'] = steady_pass
    return {'checks': checks, 'sources': records, 'comparisons': comparisons, 'steady_flow': steady}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    case = stored.read(CASE)
    revision = case['upstream_revision']
    if (subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip() != revision
            or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True)):
        parser.error('固定上流のコミットと作業状態を確認してください')
    traces = ['summary.json']
    firs = ['summary.json']
    for source in case['sources']:
        key = source['grid']
        traces.extend((f'artifacts/{key}/case.json', *(f'artifacts/{key}/{m}.csv.gz' for m in source['methods'])))
        firs.append(f'artifacts/{key}-fir.csv')
    ts, tm = load_saved_run(case['trace_run'], 'uniform-waveguide-matched-long', revision, traces)
    fs, fm = load_saved_run(case['fir_run'], 'uniform-waveguide-matched-bandlimited', revision, firs)
    if stored.read(fs['summary.json'])['prior_run'] != case['trace_run']:
        parser.error('FIRと一様管の元系列の来歴が一致しません')
    inputs = [CASE, Path(__file__).resolve(), Path(shared.__file__), Path(stored.__file__),
              tm, fm, *ts.values(), *fs.values(), *shared.candidate_sources(),
              *(UPSTREAM / file for file in ('crates/chimera/src/airway/network.rs',
                 'crates/chimera/src/voice/human_voice.rs', 'crates/chimera/tests/airway.rs'))]
    return shared.record_measurement(args.run_id, CASE, inputs, {'case_id': case['id'], 'upstream_revision': revision},
                                     lambda artifacts, execute: measure(case, ts, fs, artifacts, execute),
                                     command=None, input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
