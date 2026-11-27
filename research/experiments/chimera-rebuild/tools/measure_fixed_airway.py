"""固定姿勢の気道グラフを、上流の実状態・インパルス応答・独立計算に照合する。"""

import argparse
import csv
import json
from pathlib import Path
import re
import subprocess

import numpy as np

import measure_grid as grid
import measure_resample as resample
import measure_sagittal as sagittal
import measure_uniform_tube as shared
from upstream_baseline import UPSTREAM, WORKSPACE


CASES = tuple('fixed-airway-' + name for name in ('neutral', 'velum-open', 'short', 'short-64k', 'closed-lips'))
FIELDS = ('anatomical_length_cm', 'simulation_length_cm', 'cell_length_cm',
          'area_cm2', 'minimum_area_cm2', 'geometric_compliance')
UPSTREAM_HEADER = ('node', 'tube', *FIELDS, 'velum_port_cm2', 'courant', 'branch_count')


def capture_upstream(case, artifacts, execute):
    execute(['cargo', 'test', '--locked', '-p', 'chimera', '--test', 'engine',
             'an_extreme_pose_does_not_squeal_with_the_voice_off', '--', '--nocapture'],
            cwd=UPSTREAM, stdout=artifacts / 'upstream-stability-test.log')
    probe = shared.build_upstream_probe(sagittal.PROBE, artifacts, execute)
    fixed = case['fixed_airway']
    prefix = [str(probe), '--fixed-airway', str(fixed['sample_rate_hz'])]
    pose = sagittal.pose_controls(case)
    execute([*prefix, str(fixed['sample_count']), str(fixed['impulse_volume_cm3']), *pose],
            cwd=UPSTREAM, stdout=artifacts / 'upstream-trace.csv')
    execute([*prefix, '0', '0', *pose], cwd=UPSTREAM, stdout=artifacts / 'upstream-geometry.csv')


def read_upper_geometry(path):
    with path.open(newline='') as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != list(UPSTREAM_HEADER):
            raise ValueError('上流の節点CSVのヘッダーが不正です')
        rows = list(reader)
    if not rows or any(int(row['node']) != i for i, row in enumerate(rows)):
        raise ValueError('上流の節点番号は0始まりの連番である必要があります')
    values = np.array([[float(row[key]) for key in FIELDS] for row in rows])
    if not np.isfinite(values).all():
        raise ValueError('上流の節点CSVに非有限値があります')
    return rows, values


def read_trace(path, fields, count):
    with path.open() as stream:
        if stream.readline().strip().split(',') != ['sample', *fields]:
            raise ValueError(f'{path.name} の観測列が不正です')
        rows = np.loadtxt(stream, delimiter=',', ndmin=2)
    if (rows.shape != (count, len(fields) + 1) or not np.isfinite(rows).all()
            or not np.array_equal(rows[:, 0], np.arange(count))):
        raise ValueError(f'{path.name} のサンプル番号・件数・有限性が不正です')
    return rows[:, 1:]


def geometry_comparison(case, settings, upper_rows, upper, profile, artifacts):
    cfg = case['measurement']['fixed_airway']
    limits = np.array([cfg['anatomical_and_cell_length_error_lt_cm']] * 3 + [cfg['area_error_lt_cm2']] * 2)
    tubes = {tube['name']: tube for tube in settings['tubes']}
    sections = settings['sections']
    names = [name for name, tube in tubes.items() for _ in range(tube['cells'])]
    if (len(names) != len(sections) or [row['node'] for row in sections] != list(range(len(sections)))
            or list(tubes) != list(dict.fromkeys(row['tube'] for row in upper_rows))):
        raise ValueError('再実装の管名、順序、または節点番号が不正です')
    candidate = np.array([[tubes[name][key] if key in tubes[name] else section[key] for key in FIELDS]
                          for name, section in zip(names, sections, strict=True)])
    if not np.isfinite(candidate).all():
        raise ValueError('再実装の節点に非有限値があります')
    checks = {
        'registered_nodes_branches_and_tube_placement': bool(
            names == [row['tube'] for row in upper_rows]
            and len(sections) == len(upper_rows) == settings['node_count'] == cfg['node_count']
            and settings['branch_count'] == cfg['branch_count'] == int(upper_rows[0]['branch_count'])
            and all(names.index(name) == spec['first_node'] for name, spec in tubes.items())
        ),
    }
    if not checks['registered_nodes_branches_and_tube_placement']:
        return checks, {}, None

    error = abs(candidate[:, :5] - upper[:, :5])
    compliance_error = abs(candidate[:, 5] - upper[:, 5]) / upper[:, 5]
    rejected = np.flatnonzero((error >= limits).any(axis=1) |
                              (compliance_error >= cfg['compliance_relative_error_lt']))
    checks['upstream_section_geometry'] = not rejected.size
    checks['upstream_velum_and_courant'] = (
        abs(settings['velum_port_cm2'] - float(upper_rows[0]['velum_port_cm2'])) < limits[-1]
        and abs(settings['courant'] - float(upper_rows[0]['courant'])) < cfg['courant_abs_error_lt'])
    checks['velum_aperture_from_pose'] = settings['velum_port_cm2'] == max(case['posture']['velum_cm2'], 0.0)

    rate = case['fixed_airway']['sample_rate_hz']
    dx_design = 35000 / (0.93 * rate)
    counts = {tube: max(8, int(length / dx_design)) for tube, length in (('pharynx', 7.1), ('oral', 7.3))}
    analytic = resample.estimate_cells(profile, {
        **case, 'cells': counts, 'measurement': {'resample': {'closure_threshold_cm2': 1e-5}},
    }, artifacts / 'independent-cells.csv')
    analytic_dx = {}
    stretched = []
    per_tube = {}
    for name, count in counts.items():
        rows = analytic[name][0]
        measured = candidate[np.asarray(names) == name]
        anatomy = float(rows[-1, 1] - rows[0, 0])
        floor = float(count * (35000 / rate) / 0.97)
        simulation = max(anatomy, floor)
        analytic_dx[name] = simulation / count
        if floor - anatomy >= limits[0]:
            stretched.append(name)
        expected = np.column_stack((np.tile([anatomy, simulation, analytic_dx[name]], (count, 1)),
                                    rows[:, 2:]))
        lo, hi = cfg['length_intervals_cm'][name]
        checks[f'{name}_independent_geometry'] = bool(
            len(measured) == count == cfg[f'{name}_cells']
            and (abs(measured[:, :5] - expected) < limits).all())
        checks[f'{name}_registered_anatomical_length'] = lo <= measured[0, 0] <= hi
        per_tube[name] = {
            'cells': len(measured), 'anatomical_length_cm': float(measured[0, 0]),
            'simulation_length_cm': float(measured[0, 1]), 'cell_length_cm': float(measured[0, 2]),
            'unadjusted_courant': float(count * 35000 / (rate * measured[0, 0])),
        }
    checks['registered_stretched_tubes'] = stretched == cfg['stretched_tubes']
    oral = candidate[np.asarray(names) == 'oral']
    closed = np.flatnonzero(oral[:, 4] == 0.0).tolist()
    checks['registered_closed_oral_cells'] = closed == cfg['closed_oral_cells']
    shortest = min(analytic_dx.values())
    for name in ('trachea', 'nasal', 'piriform', 'sinus'):
        shortest = min(shortest, candidate[names.index(name), 2])
    expected_courant = 35000 / (rate * shortest)
    checks['independent_stable_courant'] = (abs(settings['courant'] - expected_courant) < cfg['courant_abs_error_lt']
                                          and expected_courant <= 0.97 + cfg['courant_abs_error_lt'])
    compliance = np.maximum(0.02, candidate[:, 3]) * candidate[:, 2] / (0.00114 * 35000**2)
    independent_compliance_error = abs(candidate[:, 5] - compliance) / compliance
    checks['independent_geometric_compliance'] = bool(
        independent_compliance_error.max() < cfg['compliance_relative_error_lt'])
    data = {
        'tubes': per_tube, 'velum_port_cm2': settings['velum_port_cm2'], 'courant': settings['courant'],
        'stretched_tubes': stretched, 'closed_oral_cells': closed,
        'upstream_max_absolute_error': dict(zip(FIELDS[:5], error.max(axis=0).tolist(), strict=True)),
        'upstream_compliance_max_relative_error': float(compliance_error.max()),
        'independent_compliance_max_relative_error': float(independent_compliance_error.max()),
        'first_node_over_tolerance': int(rejected[0]) if rejected.size else None,
    }
    return checks, data, float(compliance[tubes['pharynx']['first_node']])


def waveform_comparison(case, artifacts, inlet_compliance):
    cfg = case['measurement']['fixed_airway']
    fixed = case['fixed_airway']
    fields = cfg['observe']
    actual = read_trace(artifacts / 'trace.csv', fields, fixed['sample_count'])
    upper = read_trace(artifacts / 'upstream-trace.csv', fields, fixed['sample_count'])
    upper_peaks = abs(upper).max(axis=0)
    errors = abs(actual - upper)
    scale = np.where(upper_peaks > 0, upper_peaks, 1.0)
    relative = errors.max(axis=0) / scale
    tolerance = cfg['component_relative_error_lt']
    violations = np.flatnonzero(np.where(upper_peaks > 0, errors >= scale * tolerance, errors > 0).any(axis=1))
    columns = dict(zip(fields, actual.T, strict=True))
    peaks = {name: float(abs(series).max()) for name, series in columns.items()}
    mouth, nose = peaks['flow_lips'], peaks['flow_nose']
    arrivals = {}
    for end in ('lips', 'nose'):
        nonzero = np.flatnonzero(columns[f'flow_{end}'])
        arrivals[end] = int(nonzero[0]) if nonzero.size else None
    tail_ratio = float(abs(columns['radiation_derivative'][cfg['tail_start_sample']:]).max()
                       / max(np.finfo(float).tiny, peaks['radiation_derivative']))
    sum_flow = columns['flow_lips'] + columns['flow_nose'] + columns['flow_walls']
    derivative = np.diff(sum_flow, prepend=0.0) * fixed['sample_rate_hz']
    derivative_error = float(abs(derivative - columns['radiation_derivative']).max())
    expected_pressure = fixed['impulse_volume_cm3'] / inlet_compliance
    nasal_open = case['posture']['velum_cm2'] > 0
    checks = {
        'upstream_impulse_series': not violations.size,
        'initial_pressure_from_injected_volume': bool(
            abs(columns['pressure_pharynx_entry'][0] - expected_pressure) < tolerance * abs(expected_pressure)),
        'registered_first_radiation_sample': arrivals == cfg['first_radiation_sample'],
        'nasal_branch_matches_velum_state': (
            nose > mouth * cfg['nasal_to_oral_peak_gt_when_open'] and peaks['flow_velum'] > 0
            and peaks['flow_sinus_neck'] > 0 if nasal_open else nose == peaks['flow_velum'] == peaks['flow_sinus_neck'] == 0.0),
        'nonzero_wall_radiation': peaks['flow_walls'] > 0,
        'rad_derivative_of_component_sum': derivative_error < tolerance * peaks['radiation_derivative'],
        'radiation_decays_after_impulse': tail_ratio < cfg['radiation_derivative_tail_peak_ratio_lt'],
    }
    return checks, {
        'peak_absolute': peaks, 'first_radiation_sample': arrivals, 'tail_over_peak': tail_ratio,
        'upstream_peak_relative_error': dict(zip(fields, relative.tolist(), strict=True)),
        'max_absolute_derivative_balance_error': derivative_error,
        'first_sample_over_tolerance': int(violations[0]) if violations.size else None,
    }


def measure(case, path, artifacts, execute):
    capture_upstream(case, artifacts, execute)
    settings = json.loads((artifacts / 'settings.json').read_text())['fixed_airway']
    upper_rows, upper = read_upper_geometry(artifacts / 'upstream-geometry.csv')
    profile_path = artifacts / 'area-profile.csv'
    execute(['cargo', 'run', '--locked', '--release', '-p', 'vocal-cli', '--', 'area',
             str(path), str(profile_path)])
    profile = grid.read_grid(profile_path, columns=resample.PROFILE_COLUMNS)
    checks, geometry, inlet_compliance = geometry_comparison(case, settings, upper_rows, upper, profile, artifacts)
    result = {'checks': checks, 'geometry': geometry}
    if inlet_compliance is not None:
        waveform_checks, result['impulse'] = waveform_comparison(case, artifacts, inlet_compliance)
        checks.update(waveform_checks)
    result['checks'] = {name: bool(passed) for name, passed in checks.items()}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('case', choices=CASES)
    args = parser.parse_args()
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]*', args.run_id):
        parser.error('実行IDは英数字で始め、英数字、ハイフン、アンダースコアで指定してください')
    path = WORKSPACE / 'cases' / f'{args.case}.json'
    case = json.loads(path.read_text())
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'],
                                                                        cwd=UPSTREAM, text=True):
        raise ValueError('変更のない固定上流版が必要です')

    def measure_run(artifacts, execute):
        return measure(case, path, artifacts, execute)

    sources = [path, sagittal.PROBE, Path(__file__).resolve(), Path(sagittal.__file__), Path(grid.__file__),
               Path(resample.__file__), Path(shared.__file__), WORKSPACE / 'tools/upstream_baseline.py',
               *shared.candidate_sources()]
    details = {'upstream_revision': revision, 'case_id': case['id']}
    return shared.record_measurement(args.run_id, path, sources, details, measure_run)


if __name__ == '__main__':
    raise SystemExit(main())
