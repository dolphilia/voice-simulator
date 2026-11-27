"""一様管の口端半セルを時間領域で試し、独立式とエネルギーを照合する。"""

import argparse
import copy
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

import numpy as np

import measure_axial_observer as saved
import measure_grid_rate_sensitivity as grid_study
import measure_lip_crossing_thickness as stored
import measure_uniform_tube as shared
import measure_uniform_waveguide as matched
from upstream_baseline import UPSTREAM, WORKSPACE


CASE = WORKSPACE / 'cases/uniform-outlet-half-cell.json'
FIELDS = matched.COLUMNS + ('outlet_branch_flow_cm3_s', 'radiation_load_pressure_mid_dyn_cm2',
                            'half_cell_flow_cm3_s', 'radiation_inertance_flow_cm3_s', 'stored_energy_erg')


def mid(values):
    before = np.r_[0.0, values[:-1]]
    return (values + before) / 2


def difference(values):
    return np.diff(values, prepend=0.0)


def relative(left, right, scale=0.0):
    denominator = max(np.max(np.abs(left)), np.max(np.abs(right)), scale)
    return float(np.max(np.abs(left - right)) / denominator) if denominator else 0.0


def case_for_render(config, template, name, cells, half_cell):
    case = copy.deepcopy(template)
    case['id'] = f"{config['id']}-{name}"
    case['tube']['cells'] = cells
    if half_cell:
        case['tube']['outlet_half_cell'] = True
    case['measurement']['radiation_energy'] = True
    return case


def render(path, case, count, retain, execute):
    path.mkdir()
    definition = path / 'case.json'
    definition.write_text(json.dumps(case, ensure_ascii=False, indent=2) + '\n')
    execute([*matched.CLI, 'inspect', str(definition)], stdout=path / 'settings.json')
    with TemporaryDirectory(prefix='raw-endpoint-', dir=path) as temporary:
        staged = Path(temporary) / 'trace.csv'
        execute([*matched.CLI, 'render', str(definition), str(staged)])
        columns, values = shared.read_trace(staged, count, len(FIELDS))
    if tuple(columns) != FIELDS:
        raise ValueError('放射の計測列を照合できません')
    prefix = path / 'trace-prefix.csv'
    np.savetxt(prefix, values[:retain], delimiter=',', comments='', header=','.join(FIELDS),
               fmt=['%d', *(['%.17g'] * (len(FIELDS) - 1))])
    stored.compress(prefix)
    return values, stored.read(path / 'settings.json')


def check_energy(config, trace, settings):
    dt = settings['step_seconds']
    compliance = settings['cell_compliance_cm3_per_dyn_cm2']
    lr = settings['radiation_inertance_g_cm4']
    rr = settings['radiation_resistance_dyn_s_cm5']
    ls = settings.get('outlet_series_inertance_g_cm4', 0.0)
    _, drive, inlet, outlet, q, dq, near, p_load, u_series, u_radiation, total_energy = trace.T
    dissipated = dt * p_load**2 / rr
    injected = dt * mid(inlet) * drive
    terminal_energy = 0.5 * (compliance * outlet**2 + lr * u_radiation**2 + ls * u_series**2)
    balance_terminal = dt * mid(outlet) * near - dissipated
    balance_total = injected - dissipated
    flow_scale = float(np.max(np.abs(q)))
    pressure_scale = float(np.max(np.abs(mid(outlet))))
    energy_scale = float(np.max(total_energy))
    if min(flow_scale, pressure_scale, energy_scale) <= 0.0:
        raise ValueError('エネルギー照合に必要な入力応答がありません')
    equations = {
        'outlet_compliance': relative(compliance / dt * difference(outlet), near - q, flow_scale),
        'radiation_inertance': relative(lr / dt * difference(u_radiation), p_load, pressure_scale),
        'parallel_balance': relative(q, mid(u_radiation) + p_load / rr, flow_scale),
        'radiation_difference': relative(dq, difference(q) / dt, flow_scale / dt),
    }
    if ls:
        equations['series_inertance'] = relative(ls / dt * difference(u_series), mid(outlet) - p_load, pressure_scale)
        equations['series_midpoint_flow'] = relative(q, mid(u_series), flow_scale)
    else:
        equations['direct_load_pressure'] = relative(mid(outlet), p_load, pressure_scale)

    tail = round(config['measurement']['tail_seconds'] / dt)
    tail_spectrum = np.abs(np.fft.rfft(q[-tail:] * np.hanning(tail)))
    tail_dominant_hz = float(np.argmax(tail_spectrum) / (tail * dt))
    zero_drive_increase = max(0., float(np.max(difference(total_energy)[drive == 0]))) / energy_scale
    terminal_error = relative(difference(terminal_energy), balance_terminal, energy_scale)
    total_step_error = relative(difference(total_energy), balance_total, energy_scale)
    cumulative_error = relative(total_energy, np.cumsum(balance_total), energy_scale)
    tail_fraction = float(np.max(total_energy[-tail:]) / energy_scale)
    tol = config['criteria']
    checks = {
        'boundary_equations': max(equations.values()) <= tol['boundary_equations_relative_peak_max'],
        'terminal_energy_balance': terminal_error <= tol['energy_step_relative_max'],
        'whole_tube_energy_balance': total_step_error <= tol['energy_step_relative_max'],
        'whole_tube_cumulative_energy': cumulative_error <= tol['energy_cumulative_relative_max'],
        'nonnegative_and_no_growth_without_drive': float(np.min(total_energy)) >= -energy_scale * tol[
            'zero_input_energy_increase_relative_max'] and zero_drive_increase <= tol['zero_input_energy_increase_relative_max'],
        'last_tail_energy': tail_fraction <= tol['last_tail_energy_over_peak_max'],
    }
    return checks, {
        'boundary_relative_residuals': equations, 'relative_terminal_energy_error': terminal_error,
        'relative_step_energy_error': total_step_error, 'relative_cumulative_energy_error': cumulative_error,
        'peak_stored_erg': energy_scale, 'total_injected_work_erg': float(np.sum(injected)),
        'total_dissipated_erg': float(np.sum(dissipated)), 'final_energy_erg': float(total_energy[-1]),
        'zero_input_max_relative_increase': zero_drive_increase, 'tail_relative_energy': tail_fraction,
        'tail_dominant_outlet_flow_hz': tail_dominant_hz,
        'interior_cutoff_hz': float(np.arcsin(settings['courant']) / (np.pi * dt)),
        'outlet_series_inertance_g_cm4': ls,
    }


def spectral_compare(model, config, trace, wave_response, settings, transform, kernel, frequencies):
    _, observed = grid_study.project_spectrum(trace, kernel, transform)
    idx = settings['case']['tube']
    grid = grid_study.grid(model, {'cells': idx['cells'], 'rate_hz': idx['sample_rate_hz']})
    ls = settings.get('outlet_series_inertance_g_cm4', 0.0)
    predicted, _, derivative = matched.transfer(model, grid, frequencies, viscosity=0.0, outlet_series_inertance=ls)
    observed_basic = observed[:, :4]
    exact = np.column_stack((predicted, predicted[:, 2] * derivative))
    rel = matched.exact_error(observed_basic, exact)
    is_valid = rel <= config['criteria']['time_series_vs_midpoint_frequency_relative_max']
    spectral = [
        {'hz': int(f), 'amplitude_difference_db': float(grid_study.magnitude_db(h, w)),
         'phase_difference_degrees': float(np.angle(h / w, deg=True)),
         'fdtd_flow_transfer': [float(h.real), float(h.imag)],
         'predicted_flow_transfer': [float(p.real), float(p.imag)]}
        for f, h, p, w in zip(frequencies, observed_basic[:, 2], predicted[:, 2], wave_response, strict=True)
    ]
    return is_valid, {'native_vs_midpoint_formula_relative_error': rel, 'frequency_rows': spectral}


def original_conditions(config, model, template):
    rate = config['geometry']['rate_hz']
    measurement = config['measurement']
    tube = template['tube']
    count = round(measurement['duration_seconds'] * rate)
    if (template['upstream_revision'] != config['upstream_revision']
            or tube['sample_rate_hz'] != rate
            or any(tube[k] != config['geometry'][k] for k in ('length_cm', 'area_cm2', 'cells', 'viscous_scale'))
            or template['impulse'] != {'sample': measurement['impulse_sample'], 'volume_cm3': measurement['impulse_volume_cm3']}
            or template['measurement']['sample_count'] != count
            or model['geometry']['length_cm'] != tube['length_cm'] or model['geometry']['area_cm2'] != tube['area_cm2']):
        raise ValueError('口端位置を変える前の基準条件を照合できません')
    return rate, count, tube['cells']


def compare_predictive_results(config, results, previous):
    f = config['measurement']['primary_hz']
    tol = config['criteria']
    prior_row = next(row for row in previous['cases']['96k-40cells']['frequency_rows'] if row['frequency_hz'] == f)
    direct, series = (next(row for row in results[name]['frequency_rows'] if row['hz'] == f)
                      for name in ('direct', 'series'))
    originally = direct['amplitude_difference_db']
    observed = series['amplitude_difference_db']
    prior = prior_row['twoport_delta_db']['outlet_half_restored']
    improvement = 1 - abs(observed) / abs(originally)
    max_series = max(abs(x['amplitude_difference_db']) for x in results['series']['frequency_rows'])
    results['series']['reduction_at_primary'] = improvement
    checks = {
        '3250_reduction': improvement >= tol['reduction_min_at_3250'],
        'prior_half_cell_prediction': abs(observed - prior) <= tol['midpoint_vs_prior_half_cell_prediction_db_max_at_3250'],
        '16_frequency_amplitude': max_series <= tol['max_abs_amplitude_difference_db_at_16_frequencies'],
    }
    return checks, {'hz': f, 'direct_db': originally, 'series_db': observed, 'previous_twoport_db': prior,
                    'observed_vs_previous_db': observed - prior, 'series_max_abs_difference_db': max_series}


def measure(config, model, long_paths, firs, previous, artifacts, execute):
    cfg = config['measurement']
    template = stored.read(long_paths['artifacts/96k/case.json'])
    rate, count, cells = original_conditions(config, model, template)
    retain = round(rate * cfg['retained_prefix_seconds'])
    frequencies = np.asarray(cfg['frequencies_hz'])
    wave = matched.load_trace(long_paths['artifacts/96k/waveguide.csv.gz'], count)
    kernel = np.loadtxt(firs['artifacts/96k-fir.csv'], skiprows=1)
    transform = np.exp(-2j * np.pi / rate * np.outer(frequencies, np.arange(count)))
    _, wave_spectrum = grid_study.project_spectrum(wave, kernel, transform)
    wave_response = wave_spectrum[:, 2]
    execute(['cargo', 'test', '--locked', '-p', 'chimera', '--test', 'airway'],
            cwd=UPSTREAM, stdout=artifacts / 'upstream-airway-test.log')
    checks, results = {}, {}
    direct = None
    for tag, n, use_series in (('direct', cells, False), ('series', cells, True),
                               ('courant-stress', config['stress_cells'], True)):
        case = case_for_render(config, template, tag, n, use_series)
        trace, settings = render(artifacts / tag, case, count, retain, execute)
        expected = 0.5 * settings['branch_inertance_g_cm4'] if use_series else 0.0
        applied = settings.get('outlet_series_inertance_g_cm4', 0.0)
        checks[f'{tag}/settings'] = expected == applied and settings['branch_resistance_dyn_s_cm5'] == 0.0
        energy_checks, energy = check_energy(config, trace, settings)
        spectral_check, spectral = spectral_compare(model, config, trace, wave_response, settings,
                                                    transform, kernel, frequencies)
        checks.update({f'{tag}/{name}': value for name, value in energy_checks.items()})
        checks[f'{tag}/midpoint_spectrum'] = spectral_check
        checks[f'{tag}/first_support'] = matched.first_nonzero(trace[:, 4]) == n - 1
        results[tag] = {'courant': settings['courant'], 'first_radiation_sample': matched.first_nonzero(trace[:, 4]),
                        **energy, **spectral}
        if tag == 'direct':
            direct = trace[:, :len(matched.COLUMNS)]
            old_trace = matched.load_trace(long_paths['artifacts/96k/fdtd.csv.gz'], count)
            upper = matched.load_trace(long_paths['artifacts/96k/upstream.csv.gz'], count)
            upper_error = matched.series_error(direct, upper)
            checks['direct_matches_pinned_upstream'] = (
                max(upper_error.values()) <= config['criteria']['direct_candidate_vs_upstream_relative_peak_max'])
            checks['direct_matches_previous_candidate'] = bool(np.array_equal(direct, old_trace))
            results[tag]['upstream_relative_error'] = upper_error
        elif tag == 'series':
            first = {key: matched.first_nonzero(trace[:, col] - direct[:, col])
                     for col, key in enumerate(matched.COLUMNS[1:], 1)}
            checks['series_first_difference_is_at_radiation_boundary'] = (
                first['inlet_flow_cm3_s'] is None
                and first['outlet_pressure_dyn_cm2'] == first['radiation_flow_cm3_s'] == cells - 1)
            results[tag]['first_differences_from_direct'] = first
    other_checks, residuals = compare_predictive_results(config, results, previous)
    checks.update(other_checks)
    return {'checks': checks, 'cases': results, 'primary_comparison': residuals}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    config = stored.read(CASE)
    revision = config['upstream_revision']
    if (subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip() != revision
            or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True)):
        parser.error('固定上流のコミットと作業状態を確認してください')
    paths = [f'artifacts/96k/{file}' for file in ('case.json', 'fdtd.csv.gz', 'upstream.csv.gz', 'waveguide.csv.gz')]
    long_paths, long_manifest = saved.load_saved_run(config['long_run'], 'uniform-waveguide-matched-long', revision, paths)
    firs, fir_manifest = saved.load_saved_run(config['bandlimited_run'], 'uniform-waveguide-matched-bandlimited',
                                              revision, ['summary.json', 'artifacts/96k-fir.csv'])
    history, grid_manifest = saved.load_saved_run(config['grid_run'], 'uniform-grid-rate-sensitivity',
                                                 revision, ['summary.json'])
    if stored.read(firs['summary.json'])['prior_run'] != config['long_run']:
        parser.error('基準波形とFIRの来歴が一致しません')
    model = stored.read(matched.CASE)
    inputs = [CASE, Path(__file__).resolve(), matched.CASE, long_manifest, fir_manifest, grid_manifest,
              *long_paths.values(), *firs.values(), *history.values(), *shared.candidate_sources(),
              *(Path(module.__file__) for module in (shared, matched, grid_study, stored, saved)),
              *(UPSTREAM / key for key in ('crates/chimera/src/airway/network.rs', 'crates/chimera/tests/airway.rs'))]
    return shared.record_measurement(args.run_id, CASE, inputs,
                                     {'case_id': config['id'], 'upstream_revision': revision},
                                     lambda a, run: measure(config, model, long_paths, firs, stored.read(history['summary.json']), a, run),
                                     command=None, input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
