"""共通R–L終端の一様管で、セル長と時間刻みの影響を分離する。"""

import argparse
import copy
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

import numpy as np
from scipy.signal import lfilter

import measure_axial_observer as saved
import measure_lip_crossing_thickness as stored
import measure_uniform_tube as shared
import measure_uniform_waveguide as matched
from upstream_baseline import UPSTREAM, WORKSPACE


CASE = WORKSPACE / 'cases/uniform-grid-rate-sensitivity.json'


def label(condition):
    return f"{condition['rate_hz'] // 1000}k-{condition['cells']}cells"


def grid(model, condition):
    geometry = model['geometry']
    rate, cells = condition['rate_hz'], condition['cells']
    delay = rate * geometry['length_cm'] / geometry['sound_speed_cm_s']
    if not float(delay).is_integer():
        raise ValueError('波動管の片道遅延が整数サンプルの条件を使ってください')
    return {'rate_hz': rate, 'fdtd_cells': cells, 'waveguide_delay_samples': int(delay)}


def magnitude_db(a, b):
    return 20 * np.log10(np.abs(a / b))


def twoport_models(model, selected, frequencies):
    geometry = model['geometry']
    n, fs = selected['fdtd_cells'], selected['rate_hz']
    dx = geometry['length_cm'] / n
    density, c, area = (geometry[key] for key in ('density_g_cm3', 'sound_speed_cm_s', 'area_cm2'))
    _, lr, rr = matched.finish_load(model)
    half_angle = np.pi * frequencies / fs
    difference_half = 2j * fs * np.sin(half_angle)
    branch = density * dx / area * difference_half
    shunt = area * dx / (density * c**2) * difference_half
    mouth = 1 / rr + 1 / (lr * 2j * fs * np.tan(half_angle))
    sampled_mouth = mouth * np.cos(half_angle)

    half = np.repeat(np.eye(2, dtype=complex)[None, :, :], len(frequencies), axis=0)
    inverse_half = half.copy()
    compliance = half.copy()
    half[:, 0, 1] = branch / 2
    inverse_half[:, 0, 1] = -branch / 2
    compliance[:, 1, 0] = shunt
    centered = np.linalg.matrix_power(half @ compliance @ half, n)

    def transmit(chain, admittance):
        return admittance / (chain[:, 1, 0] + chain[:, 1, 1] * admittance)

    return {
        'centered_cells': transmit(centered, mouth),
        'centered_cells_with_midpoint': transmit(centered, sampled_mouth),
        'outlet_half_removed': transmit(centered @ inverse_half, sampled_mouth),
        'standard_fdtd': transmit(inverse_half @ centered @ inverse_half, sampled_mouth),
        'outlet_half_restored': transmit(inverse_half @ centered, sampled_mouth),
    }


def cli_case(template, condition, model, count):
    case = copy.deepcopy(template)
    case['id'] = f"uniform-grid-rate-sensitivity-{label(condition)}"
    case['tube'].update(cells=condition['cells'], sample_rate_hz=condition['rate_hz'], viscous_scale=0.0)
    case['measurement'].update(sample_count=count, tail_sample_count=round(
        condition['rate_hz'] * model['measurement']['tail_seconds']))
    return case


def capture(condition, model, template, cfg, path, paths, execute, probe):
    rate = condition['rate_hz']
    count = round(rate * cfg['duration_seconds'])
    if 'reuse' in condition:
        original = condition['reuse']
        reference_case = stored.read(paths[f'artifacts/{original}/case.json'])
        wanted = cli_case(template, condition, model, count)
        if any(reference_case[key] != wanted[key] for key in ('tube', 'impulse', 'measurement')):
            raise ValueError(f'既存の時系列の入力条件が一致しません ({original})')
        return tuple(matched.load_trace(paths[f'artifacts/{original}/{name}.csv.gz'], count)
                     for name in ('fdtd', 'upstream'))
    case_path = path / 'case.json'
    case_path.write_text(json.dumps(cli_case(template, condition, model, count), ensure_ascii=False, indent=2) + '\n')
    execute([*matched.CLI, 'inspect', str(case_path)], stdout=path / 'settings.json')
    with TemporaryDirectory(prefix='grid-raw-', dir=path) as scratch:
        scratch = Path(scratch)
        native, upper = (scratch / f'{name}.csv' for name in ('fdtd', 'upstream'))
        execute([*matched.CLI, 'render', str(case_path), str(native)])
        parameters = [rate, count, model['inlet']['sample'], model['inlet']['impulse_volume_cm3'],
                      condition['cells'], model['geometry']['length_cm'], model['geometry']['area_cm2'], 0.0]
        execute([str(probe), 'fdtd', *map(str, parameters)], stdout=upper)
        series = tuple(matched.load_trace(source, count) for source in (native, upper))
    return series


def fourth_resonance(filtered, rate, count, window, measure_size):
    start, end = np.rint(np.array(window) * measure_size / rate).astype(int)
    output = np.abs(np.fft.rfft(filtered[:, 4], n=measure_size))[start:end + 1]
    inlet = np.abs(np.fft.rfft(filtered[:, 1], n=measure_size))[start:end + 1]
    if measure_size < count or np.any(inlet == 0):
        raise ValueError('共鳴を測る周波数窓の入力に有効な帯域がありません')
    power_db = 20 * np.log10(output / inlet)
    best = int(np.argmax(power_db))
    if not 0 < best < len(power_db) - 1:
        raise ValueError('登録した第4共鳴の窓内に極大がありません')
    a, b, c = power_db[best - 1:best + 2]
    phase = 0.5 * (a - c) / (a - 2 * b + c)
    return float((start + best + phase) * rate / measure_size)


def project_spectrum(signal, kernel, transform):
    data = signal.copy()
    data[:, 1:] = lfilter(kernel, [1.0], data[:, 1:], axis=0)
    excitation = transform @ data[:, 1]
    return data, (transform @ data[:, 2:]) / excitation[:, None]


def verify_existing(records, frequencies, prior):
    errors = {}
    for key, name in (('96k', '96k-40cells'), ('192k', '192k-80cells')):
        rows = prior['cases'][key]['complex']['rows']
        wanted = np.array([complex(*r['fdtd']) for r in rows])
        locations = [int(np.flatnonzero(frequencies == r['frequency_hz'])[0]) for r in rows]
        actual = np.array([complex(*records[name]['frequency_rows'][i]['fdtd']) for i in locations])
        errors[key] = matched.exact_error(actual, wanted)
    return errors


def inspect_unstable(template, condition, model, cfg, artifacts, execute):
    directory = artifacts / 'unstable-control'
    directory.mkdir()
    count = round(condition['rate_hz'] * cfg['duration_seconds'])
    case = cli_case(template, condition, model, count)
    path = directory / 'case.json'
    target = directory / 'unexpected.csv'
    path.write_text(json.dumps(case, ensure_ascii=False, indent=2) + '\n')
    try:
        execute([*matched.CLI, 'render', str(path), str(target)], stdout=directory / 'cli.stdout')
    except subprocess.CalledProcessError:
        log = (artifacts / 'cargo.log').read_text()
        return not target.exists() and 'クーラン数' in log
    return False


def comparison_rows(config, measured, twoport, wg, frequencies):
    def pair(z):
        return [float(z.real), float(z.imag)]

    return [
        {
            'frequency_hz': int(f), 'fdtd': pair(measured[i]), 'waveguide': pair(wg[i]),
            'standard_delta_db': float(magnitude_db(measured[i], wg[i])),
            'standard_delta_degrees': float(np.angle(measured[i] / wg[i], deg=True)),
            'twoport': {key: pair(data[i]) for key, data in twoport.items()},
            'twoport_delta_db': {key: float(magnitude_db(data[i], wg[i])) for key, data in twoport.items()},
            'within_old_amplitude_limit': bool(abs(magnitude_db(measured[i], wg[i]))
                                               <= config['criteria']['old_amplitude_limit_db']),
        } for i, f in enumerate(frequencies)
    ]


def compare_condition(config, model, condition, native, upper, wave, kernel, path, frequencies):
    cfg, tol = config['measurement'], config['criteria']
    selected = grid(model, condition)
    rate = selected['rate_hz']
    transform = np.exp((-2j * np.pi / rate) * np.outer(frequencies, native[:, 0]))
    filtered, observed = project_spectrum(native, kernel, transform)
    wave_filtered, wave_observed = project_spectrum(wave, kernel, transform)
    theory, guide, derivative = matched.transfer(model, selected, frequencies, viscosity=0.0)
    twoport = twoport_models(model, selected, frequencies)
    native_flow, observed_guide = observed[:, 2], wave_observed[:, 2]
    upstream_error = matched.series_error(native, upper)
    nodal_error = matched.exact_error(observed, np.column_stack((theory, theory[:, 2] * derivative)))
    wave_error = matched.exact_error(observed_guide, guide)
    abcd_error = matched.exact_error(twoport['standard_fdtd'], theory[:, 2])
    inlet_error = matched.exact_error(twoport['standard_fdtd'], twoport['outlet_half_removed'])
    n = len(native)
    window = cfg['fourth_resonance_window_hz']
    fft_points = model['measurement']['fft_size']
    natural = {
        'fdtd': fourth_resonance(filtered, rate, n, window, fft_points),
        'waveguide': fourth_resonance(wave_filtered, rate, n, window, fft_points),
    }
    prefix = round(rate * cfg['retained_prefix_seconds'])
    if 'reuse' not in condition:
        for name, trace in (('native', native), ('upstream', upper)):
            csv = path / f'{name}-prefix.csv'
            np.savetxt(csv, trace[:prefix], delimiter=',', comments='', header=','.join(matched.COLUMNS),
                       fmt=['%d', *(['%.17g'] * 5)])
            stored.compress(csv)

    checks = {
        'same_finite_impulse': np.array_equal(native[:, 1], upper[:, 1]) and np.array_equal(native[:, 1], wave[:, 1]),
        'upstream': max(upstream_error.values()) <= tol['upstream_trace_relative_peak_max'],
        'nodal': nodal_error <= tol['bandlimited_samples_vs_nodal_complex_relative_max'],
        'waveguide': wave_error <= tol['waveguide_vs_formula_relative_max'],
        'abcd': abcd_error <= tol['abcd_vs_nodal_complex_relative_max'],
        'inlet_half_inertance': inlet_error <= tol['inlet_half_inertance_fixed_flow_complex_relative_max'],
        'support': matched.first_nonzero(native[:, 4]) == condition['cells'] - 1,
    }
    return checks, {
        'grid': selected, 'first_inlet_pressure_dyn_cm2': float(native[0, 2]),
        'first_outlet_flow_sample': matched.first_nonzero(native[:, 4]),
        'first_outlet_flow_difference_sample': matched.first_nonzero(native[:, 4] - wave[:, 4]),
        'fourth_resonance_hz': natural, 'upstream_relative_peak': upstream_error,
        'bandlimited_nodal_relative_error': nodal_error, 'waveguide_relative_error': wave_error,
        'abcd_nodal_relative_error': abcd_error, 'inlet_half_inertance_relative_error': inlet_error,
        'frequency_rows': comparison_rows(config, native_flow, twoport, observed_guide, frequencies),
    }


def contrast(config, records):
    def primary(rate, cells):
        rows = records[label({'rate_hz': rate, 'cells': cells})]['frequency_rows']
        return next(row for row in rows if row['frequency_hz'] == config['measurement']['primary_hz'])

    a, b, c, d, e = (primary(rate, cells) for rate, cells in
                       ((96000, 20), (192000, 20), (96000, 40), (192000, 40), (192000, 80)))
    av, bv, cv, dv, ev = (row['standard_delta_db'] for row in (a, b, c, d, e))
    space = abs(dv) - abs(ev)
    time = abs(dv - cv)
    abcd = c['twoport_delta_db']
    remaining = abs(abcd['outlet_half_restored'])
    reduction = 1 - remaining / abs(abcd['standard_fdtd'])
    tol = config['criteria']
    return {
        'time_change_is_small': time <= tol['time_only_change_max_db_at_3250'],
        'space_improves': space >= tol['space_only_improvement_min_db_at_3250'],
        'space_dominates_time': space >= tol['space_to_time_change_ratio_min_at_3250'] * time,
        'outlet_half_inertance_explains_difference': reduction >= tol['outlet_half_inertance_residual_reduction_min_at_3250'],
    }, {
        'factorial_average_time_effect_db': ((bv - av) + (dv - cv)) / 2,
        'factorial_average_spatial_effect_db': ((cv - av) + (dv - bv)) / 2,
        'factorial_interaction_db': (dv - cv) - (bv - av),
        'time_only_change_abs_db_at_40_cells': time,
        'space_only_improvement_db_at_192k': space,
        'outlet_half_inertance_residual_reduction': reduction,
        '96k_40cells_twoport_deltas_db': {
            'cell_propagation': abcd['centered_cells'],
            'mouth_midpoint': abcd['centered_cells_with_midpoint'] - abcd['centered_cells'],
            'removing_outlet_half_inertance': abcd['outlet_half_removed'] - abcd['centered_cells_with_midpoint'],
            'removing_inlet_half_inertance': abcd['standard_fdtd'] - abcd['outlet_half_removed'],
            'restored_outlet_residual': abcd['outlet_half_restored'],
        },
    }


def measure(config, model, long_paths, fir_paths, artifacts, execute):
    cfg = config['measurement']
    frequencies = np.asarray(cfg['frequencies_hz'])
    template = stored.read(long_paths['artifacts/96k/case.json'])
    execute(['cargo', 'test', '--locked', '-p', 'chimera', '--test', 'airway'],
            cwd=UPSTREAM, stdout=artifacts / 'upstream-airway-test.log')
    probe = shared.build_upstream_probe(matched.PROBE, artifacts, execute)
    checks, cases = {}, {}
    for prefix, rate in (('96k', 96000), ('192k', 192000)):
        wave = matched.load_trace(long_paths[f'artifacts/{prefix}/waveguide.csv.gz'],
                                  round(rate * cfg['duration_seconds']))
        kernel = np.loadtxt(fir_paths[f'artifacts/{prefix}-fir.csv'], skiprows=1)
        for cond in (condition for condition in config['conditions'] if condition['rate_hz'] == rate):
            name = label(cond)
            path = artifacts / name
            path.mkdir()
            trace, upper = capture(cond, model, template, cfg, path, long_paths, execute, probe)
            local, cases[name] = compare_condition(config, model, cond, trace, upper, wave, kernel, path, frequencies)
            checks.update({f'{name}/{k}': v for k, v in local.items()})
    checks['unstable_80_cells_at_96k_refused'] = inspect_unstable(template, config['unstable_control'],
                                                               model, cfg, artifacts, execute)
    prior_errors = verify_existing(cases, frequencies, stored.read(fir_paths['summary.json']))
    checks['same_previous_96k_192k_complex_values'] = max(prior_errors.values()) <= config['criteria']['prior_complex_relative_max']
    local, effects = contrast(config, cases)
    checks.update(local)
    return {'checks': checks, 'cases': cases, 'effects_at_registered_frequency': effects,
            'matched_previous_max_relative_error': prior_errors}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    config = stored.read(CASE)
    revision = config['upstream_revision']
    if (subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip() != revision
            or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True)):
        parser.error('固定上流のコミットと作業状態を確認してください')
    paths = [f'artifacts/{name}/{file}' for name in ('96k', '192k')
             for file in ('case.json', 'fdtd.csv.gz', 'upstream.csv.gz', 'waveguide.csv.gz')]
    long_paths, longer = saved.load_saved_run(config['long_run'], 'uniform-waveguide-matched-long', revision, paths)
    fir_paths, filtered = saved.load_saved_run(config['bandlimited_run'], 'uniform-waveguide-matched-bandlimited',
                                               revision, ['summary.json', 'artifacts/96k-fir.csv', 'artifacts/192k-fir.csv'])
    if stored.read(fir_paths['summary.json'])['prior_run'] != config['long_run']:
        parser.error('FIRと元系列の基準実行が一致しません')
    model = stored.read(matched.CASE)
    model['measurement'].update(stored.read(matched.LONG)['measurement'])
    if model['upstream_revision'] != revision or model['measurement']['seconds'] != config['measurement']['duration_seconds']:
        parser.error('使用する基準の計測条件が一致しません')
    inputs = [CASE, Path(__file__).resolve(), matched.CASE, matched.LONG, matched.PROBE, longer, filtered,
              *long_paths.values(), *fir_paths.values(), *shared.candidate_sources(),
              *(Path(module.__file__) for module in (matched, shared, stored, saved)),
              *(UPSTREAM / key for key in ('crates/chimera/src/airway/network.rs',
                                           'crates/chimera/src/airway/frequency.rs', 'crates/chimera/tests/airway.rs'))]
    return shared.record_measurement(args.run_id, CASE, inputs,
                                     {'case_id': config['id'], 'upstream_revision': revision},
                                     lambda a, run: measure(config, model, long_paths, fir_paths, a, run),
                                     command=None, input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
