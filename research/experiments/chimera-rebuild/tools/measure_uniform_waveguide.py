"""固定一様管のFDTDと波動管を指定流量・並列R–L終端で照合する。"""

import argparse
import ctypes
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
from scipy.linalg import solve_banded
from scipy.signal import firwin, lfilter

import measure_lip_crossing_thickness as stored
import measure_uniform_tube as shared
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/uniform-waveguide-matched.json'
LONG = WORKSPACE / 'cases/uniform-waveguide-matched-long.json'
BANDLIMITED = WORKSPACE / 'cases/uniform-waveguide-matched-bandlimited.json'
PROBE = WORKSPACE / 'tools/upstream_uniform_waveguide_probe.rs'
LEGACY = (WORKSPACE.parent / 'autonomous-research-cycle/campaigns'
          / 'nas-waveguide-tract-mechanism-20261008-v1/waveguide_tract.c')
CLI = ['cargo', 'run', '--locked', '--release', '-p', 'vocal-cli', '--']
COLUMNS = ('sample', 'inlet_flow_cm3_s', 'inlet_pressure_dyn_cm2', 'outlet_pressure_dyn_cm2',
           'radiation_flow_cm3_s', 'radiation_flow_derivative_cm3_s2')


def load_trace(path, count):
    columns, data = shared.read_trace(path, count, len(COLUMNS))
    if tuple(columns) != COLUMNS:
        raise ValueError(f'観測列を照合できません ({path.name})')
    return data


def finish_load(config):
    geometry = config['geometry']
    area, density, speed = (geometry[key] for key in ('area_cm2', 'density_g_cm3', 'sound_speed_cm_s'))
    radius = np.sqrt(area / np.pi)
    characteristic = density * speed / area
    inertia = 8 * density / (3 * np.pi**2 * radius)
    resistance = 128 * density * speed / (9 * np.pi**2 * area)
    return characteristic, float(inertia), resistance


def slowest_waveguide_pole(config, grid):
    rate, delay = (grid[key] for key in ('rate_hz', 'waveguide_delay_samples'))
    z0, lr, rr = finish_load(config)
    gain_r, gain_l = z0 / rr, z0 / (2 * rate * lr)
    # 分母の D(z) − N(z) z⁻²ᴰ を、z の多項式として解く。
    polynomial = np.zeros(2 * delay + 2)
    polynomial[0], polynomial[1] = 1 + gain_r + gain_l, -1 - gain_r + gain_l
    polynomial[-2], polynomial[-1] = -1 + gain_r + gain_l, 1 - gain_r + gain_l
    pole = max(np.roots(polynomial), key=abs)
    magnitude = abs(pole)
    return {'magnitude': float(magnitude), 'frequency_hz': float(abs(np.angle(pole)) * rate / (2 * np.pi)),
            'time_constant_seconds': float(-1 / (rate * np.log(magnitude)))}


def transfer(config, grid, frequencies, viscosity, *, outlet_series_inertance=0.0):
    rate, cells, delay = (grid[key] for key in ('rate_hz', 'fdtd_cells', 'waveguide_delay_samples'))
    geometry = config['geometry']
    area, density, speed, length = (geometry[key] for key in
                                    ('area_cm2', 'density_g_cm3', 'sound_speed_cm_s', 'length_cm'))
    z0, lr, rr = finish_load(config)
    phase = 2 * np.pi * frequencies / rate
    z = np.exp(1j * phase)
    backwards = 1 - 1 / z
    admittance = 1 / rr + 1 / (1j * 2 * rate * np.tan(phase / 2) * lr)
    reflection = (1 - z0 * admittance) / (1 + z0 * admittance)
    travel = np.exp(-1j * phase * delay)
    waveguide = travel * (1 - reflection) / (1 - reflection * travel**2)

    # 各節点の圧力を未知数にし、時間更新によらず三重対角の流量収支を解く。
    dx = length / cells
    compliance = dx * area / (density * speed**2)
    inertia = density * dx / area
    viscous_r = viscosity * np.sqrt(density * 1.86e-4 * np.pi * 700) * 2 * np.sqrt(np.pi * area) * dx / area**2
    branches = 1 / (viscous_r + inertia * rate * backwards)
    capacitors = (z - 1) * compliance * rate
    mouth_load = (z + 1) / 2 * admittance
    if outlet_series_inertance:
        series_impedance = 2j * rate * np.tan(phase / 2) * outlet_series_inertance
        mouth_load /= 1 + series_impedance * admittance
    drive = np.zeros(cells, dtype=complex)
    drive[0] = 1.0
    fdtd = np.empty((len(z), 3), dtype=complex)
    matrix = np.zeros((3, cells), dtype=complex)
    for i, (branch, capacitor, mouth) in enumerate(zip(branches, capacitors, mouth_load, strict=True)):
        matrix[0, 1:] = matrix[2, :-1] = -branch
        matrix[1, :] = capacitor + 2 * branch
        matrix[1, 0] -= branch
        matrix[1, -1] += mouth - branch
        pressure = solve_banded((1, 1), matrix, drive)
        fdtd[i] = [z[i] * pressure[0], z[i] * pressure[-1], mouth * pressure[-1]]
    return fdtd, waveguide, rate * backwards


def exact_error(candidate, reference):
    return float(np.max(np.abs(candidate - reference) / np.maximum(np.abs(reference), 1e-30)))


def series_error(candidate, reference):
    return {key: float(np.max(np.abs(candidate[:, i] - reference[:, i])) / np.max(np.abs(reference[:, i])))
            for i, key in enumerate(COLUMNS[1:], 1)}


def first_nonzero(signal):
    values = np.flatnonzero(signal)
    return int(values[0]) if len(values) else None


def main_arrival(signal, rate, expected, cfg):
    width = round(rate * cfg['gaussian_halfwidth_seconds'])
    time = np.arange(-width, width + 1) / rate
    window = np.exp(-0.5 * (time / cfg['gaussian_std_seconds'])**2)
    filtered = np.abs(np.convolve(signal, window))
    lo, hi = (expected + width + round(time * rate) for time in cfg['search_relative_seconds'])
    index = lo + int(np.argmax(filtered[lo:hi + 1]))
    a, b, c = filtered[index - 1:index + 2]
    if not lo < index < hi or not b > min(a, c):
        raise ValueError('登録した到達窓内に波束の最大点がありません')
    offset = 0.5 * (a - c) / (a - 2 * b + c)
    return float(index + offset - width)


def measure_complex(config, grid, native, wave, viscosity):
    rate = grid['rate_hz']
    frequencies = np.array(config['measurement']['complex_frequencies_hz'])
    fd_model, wg_model, difference = transfer(config, grid, frequencies, viscosity)
    transform = np.exp(-2j * np.pi / rate * np.outer(frequencies, native[:, 0]))
    excitation = transform @ native[:, 1]
    observed_fd = (transform @ native[:, 2:]) / excitation[:, None]
    observed_wg = (transform @ wave[:, 4:]) / excitation[:, None]
    ratio = observed_fd[:, 2] / observed_wg[:, 0]
    return {
        'fdtd_nodal_complex_error': exact_error(observed_fd[:, :3], fd_model),
        'waveguide_closed_form_complex_error': exact_error(observed_wg[:, 0], wg_model),
        'fdtd_derivative_complex_error': exact_error(observed_fd[:, 3], fd_model[:, 2] * difference),
        'waveguide_derivative_complex_error': exact_error(observed_wg[:, 1], wg_model * difference),
        'relative_complex_distance_high_band': float(np.max(np.abs(ratio[-3:] - 1))),
        'rows': [
            {'frequency_hz': int(f), 'fdtd': [float(h.real), float(h.imag)],
             'waveguide': [float(w.real), float(w.imag)],
             'fdtd_minus_waveguide_db': float(20 * np.log10(abs(r))),
             'fdtd_minus_waveguide_degrees': float(np.angle(r, deg=True))}
            for f, h, w, r in zip(frequencies, observed_fd[:, 2], observed_wg[:, 0], ratio, strict=True)
        ],
    }


def summarize(config, grid, native, upper, wave, viscosity, source_delay=0):
    rate, delay = (grid[key] for key in ('rate_hz', 'waveguide_delay_samples'))
    cfg = config['measurement']
    tol = config['criteria']
    lower, higher = cfg['peak_range_hz']
    frequencies = np.fft.rfftfreq(cfg['fft_size'], 1 / rate)
    inputs = native[:, 1]
    width = frequencies[1] - frequencies[0]
    band = slice(max(0, int(lower / width) - 1), int(higher / width) + 3)
    input_spectrum = np.fft.rfft(inputs, cfg['fft_size'])[band]
    onset = first_nonzero(inputs)
    tail = round(rate * cfg['tail_seconds'])
    all_waves = {'fdtd': native, 'upstream': upper, 'waveguide': wave}
    features = {}
    for key, series in all_waves.items():
        output = series[:, 4]
        spectrum = np.abs(np.fft.rfft(output, cfg['fft_size'])[band] / input_spectrum)
        peaks = shared.peaks(frequencies[band], spectrum, lower, higher)
        indices = np.rint((peaks - frequencies[band.start]) / width).astype(int)
        features[key] = {
            'first_nonzero_sample': first_nonzero(output),
            'main_arrival_samples': main_arrival(output, rate, delay + source_delay, cfg['arrival']) - source_delay,
            'resonance_hz': peaks.tolist(),
            'peak_heights_db': (20 * np.log10(spectrum[indices])).tolist(),
            'tail_over_peak': float(np.max(np.abs(output[-tail:])) / np.max(np.abs(output))),
        }
    fd, wg = (features[key] for key in ('fdtd', 'waveguide'))
    fd_peaks, wave_peaks = map(np.array, (fd['resonance_hz'], wg['resonance_hz']))
    right_count = len(fd_peaks) == len(wave_peaks) == cfg['required_resonances']
    resonance_error = (np.abs(fd_peaks / wave_peaks - 1)).tolist() if right_count else []
    series_match = series_error(native, upper)
    complex_match = measure_complex(config, grid, native, wave, viscosity)
    rows = complex_match['rows']
    arrival_difference = (fd['main_arrival_samples'] - wg['main_arrival_samples']) / rate
    first_difference = {key: first_nonzero(native[:, i] - wave[:, i]) for i, key in enumerate(COLUMNS[1:], 1)}
    local = {
        'same_inlet_excitation': all(np.array_equal(inputs, values[:, 1]) for values in all_waves.values()),
        'causal_support': fd['first_nonzero_sample'] == onset + grid['fdtd_cells'] - 1
        and wg['first_nonzero_sample'] == onset + delay,
        'upstream_samples': max(series_match.values()) <= tol['candidate_upstream_time_series_relative_peak_max'],
        'exact_discrete_formulas': max(complex_match[k] for k in
                                      ('fdtd_nodal_complex_error', 'waveguide_closed_form_complex_error'))
        <= tol['discrete_model_complex_relative_max'],
        'independent_radiation_derivative': max(complex_match[k] for k in
                                               ('fdtd_derivative_complex_error', 'waveguide_derivative_complex_error'))
        <= tol['discrete_model_derivative_complex_relative_max'],
        'tail_decay': all(v['tail_over_peak'] <= tol['max_tail_over_peak'] for v in features.values()),
    }
    if viscosity == 0:
        local.update({
            'main_arrival': abs(arrival_difference) <= tol['max_main_arrival_difference_seconds'],
            'resonance_match': right_count and max(resonance_error) <= tol['max_resonance_relative_difference'],
            'complex_amplitude_match': max(abs(row['fdtd_minus_waveguide_db']) for row in rows)
            <= tol['max_complex_magnitude_difference_db'],
            'complex_phase_match': max(abs(row['fdtd_minus_waveguide_degrees']) for row in rows)
            <= tol['max_complex_phase_difference_degrees'],
        })
    return local, {'methods': features, 'first_sample_differences': first_difference,
                   'main_arrival_difference_seconds': arrival_difference,
                   'resonance_relative_error': resonance_error,
                   'slowest_waveguide_pole': slowest_waveguide_pole(config, grid),
                   'upstream_relative_peak_error': series_match, 'complex': complex_match}


def compare_legacy(config, probe, artifacts, execute):
    cfg = config['measurement']['legacy']
    rate, count, cells, rg, rm = (cfg[key] for key in
                                 ('rate_hz', 'samples', 'sections', 'inlet_reflection', 'outlet_reflection'))
    source = artifacts / 'legacy-waveguide.dylib'
    compiler = ['xcrun', '--sdk', 'macosx', 'clang'] if sys.platform == 'darwin' else ['clang']
    execute([*compiler, '-O2', '-shared', '-fPIC', str(LEGACY), '-lm', '-o', str(source)])
    kernel = ctypes.CDLL(str(source)).tube_render
    pointer = np.ctypeslib.ndpointer(dtype=np.float64, flags='C_CONTIGUOUS')
    kernel.argtypes = [pointer, pointer, ctypes.c_size_t, ctypes.c_size_t,
                       ctypes.c_double, ctypes.c_double, pointer, pointer]
    kernel.restype = ctypes.c_int
    args = [str(probe), 'legacy', *map(str, (rate, count, 0, 1.0, cells, rg, rm))]
    output = artifacts / 'legacy-rust.csv'
    execute(args, stdout=output)
    rust = load_trace(output, count)
    area = np.full((count, cells), config['geometry']['area_cm2'])
    reference, energy = np.empty(count), np.empty(count)
    if not kernel(np.ascontiguousarray(rust[:, 1]), area, count, cells, rg, rm, reference, energy):
        raise ValueError('既存の波動管C実装が入力を拒否しました')
    np.savetxt(artifacts / 'legacy-c.csv', np.column_stack((np.arange(count), reference, energy)),
               delimiter=',', header='sample,outlet_normalized_pressure,normalized_energy', comments='')
    error = float(np.max(np.abs(reference - rust[:, 3])) / np.max(np.abs(reference)))
    return error, error <= config['criteria']['legacy_relative_peak_max']


def render_condition(config, base, grid, viscosity, folder, probe, execute):
    folder.mkdir()
    case = {**base, 'id': f"{config['id']}-{folder.name}"}
    rate, cells, delay = (grid[key] for key in ('rate_hz', 'fdtd_cells', 'waveguide_delay_samples'))
    g, cfg = config['geometry'], config['measurement']
    length, area, speed = (g[key] for key in ('length_cm', 'area_cm2', 'sound_speed_cm_s'))
    if not np.isclose(delay, rate * length / speed, rtol=0, atol=1e-12):
        raise ValueError('物理寸法と波動管の遅延が一致しません')
    count = round(rate * cfg['seconds'])
    case['tube'] = {'length_cm': length, 'area_cm2': area, 'cells': cells,
                    'sample_rate_hz': rate, 'viscous_scale': viscosity}
    at, volume = (config['inlet'][key] for key in ('sample', 'impulse_volume_cm3'))
    case['impulse'] = {'sample': at, 'volume_cm3': volume}
    case['measurement'] = {**base['measurement'], 'sample_count': count,
                           'tail_sample_count': round(rate * cfg['tail_seconds'])}
    path = folder / 'case.json'
    path.write_text(json.dumps(case, indent=2, ensure_ascii=False) + '\n')
    inspect = folder / 'settings.json'
    execute([*CLI, 'inspect', str(path)], stdout=inspect)
    native, upper, wave = (folder / f'{tag}.csv' for tag in ('fdtd', 'upstream', 'waveguide'))
    execute([*CLI, 'render', str(path), str(native)])
    common = [rate, count, at, volume]
    args = [cells, length, area, viscosity]
    execute([str(probe), 'fdtd', *map(str, (*common, *args))], stdout=upper)
    z0, lr, rr = finish_load(config)
    settings = stored.read(inspect)
    for key, value in (('radiation_inertance_g_cm4', lr), ('radiation_resistance_dyn_s_cm5', rr)):
        if not np.isclose(settings[key], value, rtol=1e-14, atol=0):
            raise ValueError(f'並列R–Lの共通係数を照合できません ({key})')
    if (settings['branch_resistance_dyn_s_cm5'] == 0) != (viscosity == 0):
        raise ValueError('管内粘性の設定を照合できません')
    execute([str(probe), 'waveguide', *map(str, (*common, delay, z0, lr, rr))], stdout=wave)
    local, result = summarize(config, grid, *(load_trace(p, count) for p in (native, upper, wave)), viscosity)
    for trace in (native, upper, wave):
        stored.compress(trace)
    return local, result


def measure(config, base, base_path, prior, artifacts, execute):
    execute(['cargo', 'test', '--locked', '-p', 'chimera', '--test', 'airway'],
            cwd=UPSTREAM, stdout=artifacts / 'upstream-airway-test.log')
    probe = shared.build_upstream_probe(PROBE, artifacts, execute)
    error, legacy_match = compare_legacy(config, probe, artifacts, execute)
    checks = {'legacy_body': legacy_match}
    results = {}
    for name, grid, viscosity in conditions(config):
        local, result = render_condition(config, base, grid, viscosity, artifacts / name, probe, execute)
        checks.update({f'{name}/{test}': passed for test, passed in local.items()})
        results[name] = result
    old_trace = artifacts / 'baseline-rerun.csv'
    execute([*CLI, 'render', str(base_path), str(old_trace)])
    checks['baseline_default_unchanged'] = sha256(old_trace) == sha256(prior / 'artifacts/trace.csv')
    stored.compress(old_trace)
    improvement = refined_improvement(results)
    checks['refinement_reduces_high_band_error'] = improvement >= config['criteria']['refine_high_band_at_least']
    z0, lr, rr = finish_load(config)
    return {'checks': checks, 'cases': results, 'legacy_relative_peak_error': error,
            'refinement_high_band_fraction_reduced': improvement,
            'one_way_seconds': config['geometry']['length_cm'] / config['geometry']['sound_speed_cm_s'],
            'characteristic_impedance_dyn_s_cm5': z0,
            'radiation_inertance_g_cm4': lr, 'radiation_resistance_dyn_s_cm5': rr}


def conditions(config):
    coarse, fine = config['grids']
    return (('96k', coarse, 0.0), ('192k', fine, 0.0), ('96k-viscous', coarse, 1.0))


def refined_improvement(results):
    coarse, fine = (results[name]['complex']['relative_complex_distance_high_band'] for name in ('96k', '192k'))
    return 1 - fine / coarse


def tail_frequency(wave, rate, seconds):
    segment = wave[-round(rate * seconds):]
    spectrum = np.abs(np.fft.rfft(segment * np.hanning(len(segment))))
    frequencies = np.fft.rfftfreq(len(segment), 1 / rate)
    return float(frequencies[np.argmax(spectrum)])


def measure_bandlimited(config, filtered_case, input_paths, prior_summary, artifacts):
    results = {}
    checks = dict.fromkeys(('legacy_body', 'baseline_default_unchanged'))
    for name in checks:
        checks[name] = prior_summary['checks'][name]
    geometry = config['geometry']
    filter_config = filtered_case['lowpass']
    diagnostic = filtered_case['diagnostic']
    for name, grid, viscosity in conditions(config):
        rate = grid['rate_hz']
        count = round(config['measurement']['seconds'] * rate)
        half = round(filter_config['half_duration_seconds'] * rate)
        kernel = firwin(2 * half + 1, filter_config['cutoff_hz'], fs=rate,
                        window=('kaiser', filter_config['kaiser_beta']))
        np.savetxt(artifacts / f'{name}-fir.csv', kernel, header='coefficient', comments='')
        data = [load_trace(path, count) for path in input_paths[name]]
        raw_tail = tail_frequency(data[0][:, 4], rate, diagnostic['tail_seconds'])
        dx = geometry['length_cm'] / grid['fdtd_cells']
        cutoff = float(rate / np.pi * np.arcsin(geometry['sound_speed_cm_s'] / (dx * rate)))
        for trace in data:
            trace[:, 1:] = lfilter(kernel, [1], trace[:, 1:], axis=0)
        local, result = summarize(config, grid, *data, viscosity, source_delay=half)
        local['preserved_source_volume'] = bool(np.isclose(np.sum(data[0][:, 1]) / rate,
                                                           config['inlet']['impulse_volume_cm3'], rtol=1e-12, atol=0))
        if viscosity == 0:
            local['raw_tail_frequency_near_cutoff'] = abs(raw_tail - cutoff) <= diagnostic['max_cutoff_mode_frequency_difference_hz']
        checks.update({f'{name}/{test}': passed for test, passed in local.items()})
        results[name] = {
            **result, 'raw_tail_peak_hz': raw_tail, 'fdtd_cutoff_hz': cutoff,
            'fir_source_delay_samples': half,
            'fir_gain_at_fdtd_cutoff': float(abs(np.exp(-2j * np.pi * cutoff / rate * np.arange(kernel.size)) @ kernel)),
        }
    improvement = refined_improvement(results)
    checks['refinement_reduces_high_band_error'] = improvement >= config['criteria']['refine_high_band_at_least']
    return {'checks': checks, 'cases': results, 'refinement_high_band_fraction_reduced': improvement,
            'prior_run': filtered_case['prior_run']}


def run_bandlimited(config, revision, run_id):
    filtered_case = stored.read(BANDLIMITED)
    extension = stored.read(LONG)
    if filtered_case['upstream_revision'] != revision or not filtered_case['criteria_inherited_without_changes']:
        raise ValueError('帯域制限ケースの上流版と判定基準を確認してください')
    config['measurement'].update(extension['measurement'])
    root = WORKSPACE / 'runs' / filtered_case['prior_run']
    manifest = stored.read(root / 'manifest.json')
    if manifest['case_id'] != extension['id'] or manifest['upstream_revision'] != revision or 'error' in manifest or 'storage_error' in manifest:
        raise ValueError('読み出す3秒の計測実行を確認してください')
    for path in (CASE, LONG):
        entry = next(row for row in manifest['inputs'] if row['path'].endswith(f'/cases/{path.name}'))
        if entry['sha256'] != sha256(path):
            raise ValueError(f'3秒の計測と使用する登録内容が一致しません ({path.name})')
    outputs = {row['path']: row['sha256'] for row in manifest['outputs']}
    results = {name: [root / f'artifacts/{name}/{method}.csv.gz' for method in ('fdtd', 'upstream', 'waveguide')]
               for name, _, _ in conditions(config)}
    prior_summary = root / 'summary.json'
    saved = [prior_summary, *(path for paths in results.values() for path in paths)]
    if not all(sha256(path) == outputs[path.relative_to(root).as_posix()] for path in saved):
        raise ValueError('3秒の保存済み時系列を照合できません')
    inputs = [CASE, LONG, BANDLIMITED, Path(__file__).resolve(), Path(shared.__file__),
              Path(stored.__file__), root / 'manifest.json', *saved]
    return shared.record_measurement(
        run_id, BANDLIMITED, inputs, {'case_id': filtered_case['id'], 'upstream_revision': revision},
        lambda artifacts, _: measure_bandlimited(config, filtered_case, results, stored.read(prior_summary), artifacts),
        command=None, input_root=WORKSPACE.parents[2],
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument('--long-window', action='store_true', help='減衰を追うため3秒まで記録する')
    selection.add_argument('--bandlimited', action='store_true', help='3秒の保存系列に帯域制限入力を適用する')
    options = parser.parse_args()
    config = stored.read(CASE)
    revision = config['upstream_revision']
    if (subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip() != revision
            or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True)):
        parser.error('固定上流のコミットと作業状態を確認してください')
    if options.bandlimited:
        return run_bandlimited(config, revision, options.run_id)
    base_path = WORKSPACE / 'cases' / f"{config['baseline_case']}.json"
    base = stored.read(base_path)
    prior, inputs = stored.saved({'baseline': config['baseline_run']}, ['summary.json', 'artifacts/trace.csv'], revision)
    include = next((entry for entry in stored.read(inputs[0])['inputs'] if entry['path'] == f'cases/{base_path.name}'), None)
    if include is None or include['sha256'] != sha256(base_path):
        parser.error('既存の一様管実行とケース定義が一致しません')
    case_path = CASE
    if options.long_window:
        extension = stored.read(LONG)
        if (extension['base_case'] != config['id'] or not extension['criteria_inherited_without_changes']
                or set(extension['measurement']) != {'seconds', 'fft_size'}):
            parser.error('延長条件は元ケースの記録時間とFFT点数だけを変更できます')
        short = WORKSPACE / 'runs' / extension['prior_run']
        prior_manifest = short / 'manifest.json'
        prior_summary = short / 'summary.json'
        manifest = stored.read(prior_manifest)
        registered_input = next(row for row in manifest['inputs'] if row['path'].endswith(f'/cases/{CASE.name}'))
        registered_output = next(row for row in manifest['outputs'] if row['path'] == 'summary.json')
        if (manifest['upstream_revision'] != revision or manifest['case_id'] != config['id']
                or registered_input['sha256'] != sha256(CASE)
                or registered_output['sha256'] != sha256(prior_summary)):
            parser.error('0.5秒の比較結果を照合できません')
        config['id'] = extension['id']
        config['measurement'].update(extension['measurement'])
        inputs.extend((LONG, prior_manifest, prior_summary))
        case_path = LONG
    inputs.extend((CASE, base_path, Path(__file__).resolve(), PROBE, LEGACY,
                   Path(shared.__file__), Path(stored.__file__), *shared.candidate_sources(),
                   *(UPSTREAM / key for key in ('crates/chimera/src/airway/network.rs',
                                                'crates/chimera/src/airway/frequency.rs',
                                                'crates/chimera/tests/airway.rs'))))
    return shared.record_measurement(options.run_id, case_path, inputs,
                                     {'case_id': config['id'], 'upstream_revision': revision},
                                     lambda a, run: measure(config, base, base_path, prior, a, run),
                                     command=None, input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
