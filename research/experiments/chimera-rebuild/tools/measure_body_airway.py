"""体型別の固定気道を、上流の実状態・応答と独立した計算に照合する。"""

import argparse
import math
from pathlib import Path
import re
import subprocess

import numpy as np

import measure_fixed_airway as fixed
import measure_grid as grid
import measure_resample as resample
import measure_sagittal as sagittal
import measure_speech_timing as timing
import measure_uniform_tube as shared
import measure_vowel_transfer as transfer
from upstream_baseline import UPSTREAM, WORKSPACE, sha256

CASE = WORKSPACE / 'cases/human-body-airway.json'
BODY_DATA = WORKSPACE / 'cases/human-body-geometry.json'
TUBES = ('trachea', 'pharynx', 'oral', 'nasal', 'piriform', 'lungs', 'sinus')


def geometry(config, variant, case, setup, profile, folder, endpoints):
    cfg = config['measurement']
    rate = variant['rate_hz']
    c, rho = (cfg[key] for key in ('sound_speed_cm_s', 'air_density_g_cm3'))
    cm, cm2 = (cfg[key] for key in ('length_absolute_tolerance_cm', 'area_absolute_tolerance_cm2'))
    rel, cfl_tol = (cfg[key] for key in ('linear_element_relative_tolerance', 'courant_absolute_tolerance'))
    k, ph = (math.fsum(w * endpoints[name][key]
                       for w, name in zip(variant['weights'], ('male', 'female', 'child'), strict=True))
             for key in ('scale', 'pharynx'))
    h = c / (rate * cfg['maximum_design_courant'])
    expected_counts = [
        max(6, math.floor(12 * k / max(h, 0.9 * k))),
        max(8, math.floor(k * (8.7 * (0.55 + 0.45 * ph) - 1.6) / h)),
        max(8, math.floor(7.3 * k / h)),
        max(8, math.floor(11.4 * k / max(h, 0.5 * k))),
        min(3, max(1, math.floor(2 * k / h))),
        1, 1,
    ]
    measured = setup['fixed_airway']
    tubes = {item['name']: item for item in measured['tubes']}
    sections = measured['sections']
    names = [name for name, tube in tubes.items() for _ in range(tube['cells'])]
    candidate = np.array([[tubes[name].get(key, section.get(key)) for key in fixed.FIELDS]
                          for name, section in zip(names, sections, strict=True)], dtype=float)
    boundary = np.r_[0, np.cumsum(expected_counts)]
    expected_names = [name for name, count in zip(TUBES, expected_counts, strict=True) for _ in range(count)]
    upper_rows, upper = fixed.read_upper_geometry(folder / 'upstream-geometry.csv')
    checks = {
        'registered_and_independent_counts_topology': (
            tuple(tubes) == TUBES and names == expected_names == [row['tube'] for row in upper_rows]
            and expected_counts[:5] == variant['cells']
            and [row['node'] for row in sections] == list(range(len(names)))
            and [tubes[tube]['first_node'] for tube in TUBES] == boundary[:-1].tolist()
            and len(sections) == measured['node_count'] == len(upper)
            and measured['branch_count'] == len(sections) - 1 == int(upper_rows[0]['branch_count'])
        ),
    }
    if not checks['registered_and_independent_counts_topology']:
        return checks, {'expected_counts': expected_counts, 'observed_counts': [row['cells'] for row in tubes.values()]}, None
    if not np.isfinite(candidate).all():
        raise ValueError('固定気道の節点に非有限値があります')
    error = abs(candidate[:, :5] - upper[:, :5])
    compliance_error = abs(candidate[:, 5] - upper[:, 5]) / upper[:, 5]
    bad = np.flatnonzero(np.any(error > [cm, cm, cm, cm2, cm2], axis=1) | (compliance_error > rel))
    checks['upstream_geometry_and_compliance'] = not bad.size
    subcase = {
        **case, 'cells': dict(zip(resample.TUBES, expected_counts[1:3], strict=True)),
        'measurement': {'resample': {'closure_threshold_cm2': 1e-5}},
    }
    independent = resample.estimate_cells(profile, subcase, folder / 'independent-cells.csv',
                                         scale=k, epilarynx_cm=2.4*k*ph)
    lengths = [12*k, 0, 0, 11.4*k, 2*k, 1, (14*k**3) ** (1/3)]
    nasal_position = (np.arange(expected_counts[3]) + 0.5) / expected_counts[3]
    nasal = k**2 * np.select([nasal_position < 0.18, nasal_position < 0.75, nasal_position < 0.9],
                            [2.6, 2 - 0.6*(nasal_position - 0.18), 1.4], default=1.0)
    areas = dict(trachea=2.5*k**2, nasal=nasal, piriform=0.9*k**2, lungs=100, sinus=14*k**3/lengths[-1])
    stretched = []
    expected_geometry = []
    for i, name in enumerate(TUBES):
        n = expected_counts[i]
        if name in independent:
            cells = independent[name][0]
            actual_len = cells[-1, 1] - cells[0, 0]
            simulated = max(actual_len, n * c / (rate * cfg['maximum_courant']))
            if simulated - actual_len > cm:
                stretched.append(name)
            sections_pair = cells[:, 2:]
        else:
            actual_len = simulated = lengths[i]
            a = np.broadcast_to(areas[name], (n,))
            sections_pair = np.column_stack((a, a))
        expected_geometry.append(np.column_stack((np.tile([actual_len, simulated, simulated/n], (n, 1)), sections_pair)))
    analytic = np.vstack(expected_geometry)
    expected_compliance = np.maximum(analytic[:, 3], 0.02) * analytic[:, 2] / (rho*c*c)
    independent_geo = abs(candidate[:, :5] - analytic)
    checks['independent_lengths_areas_and_stretch'] = (
        np.all(independent_geo <= [cm, cm, cm, cm2, cm2])
        and stretched == variant.get('stretched_tubes', []))
    checks['independent_geometric_compliance'] = np.max(abs(candidate[:, 5] / expected_compliance - 1)) <= rel
    courant = c / (rate * analytic[:, 2].min())
    velum = max(0.0, case['posture']['velum_cm2']) * k**2
    checks['independent_courant_and_scaled_velum'] = (
        abs(measured['courant'] - courant) <= cfl_tol
        and abs(measured['courant'] - float(upper_rows[0]['courant'])) <= cfl_tol
        and measured['courant'] <= cfg['maximum_courant'] + cfl_tol
        and abs(measured['velum_port_cm2'] - velum) <= cm2
        and abs(measured['velum_port_cm2'] - float(upper_rows[0]['velum_port_cm2'])) <= cm2)
    data = {
        'tubes': measured['tubes'], 'stretched_tubes': stretched, 'courant': measured['courant'],
        'velum_port_cm2': measured['velum_port_cm2'], 'first_bad_node': int(bad[0]) if bad.size else None,
        'upstream_geometry_max_error': dict(zip(fixed.FIELDS[:5], error.max(axis=0).tolist(), strict=True)),
        'independent_geometry_max_error': dict(zip(fixed.FIELDS[:5], independent_geo.max(axis=0).tolist(), strict=True)),
        'upstream_compliance_max_relative_error': float(compliance_error.max()),
        'piriform_courant': c / (rate * tubes['piriform']['simulation_length_cm']/tubes['piriform']['cells']),
        'piriform_courant_if_three_cells': c / (rate * (2*k/3)),
    }
    return checks, data, expected_compliance[tubes['pharynx']['first_node']]


def frequency(config, setup, folder):
    cfg = config['measurement']
    spec = config['transfer']
    model = setup['transfer']
    nodes = np.asarray([[row[key] for key in transfer.NODE_FIELDS] for row in model['nodes']], dtype=float)
    edges = np.asarray([[*row['nodes'], row['open'], row['inertance'], row['resistance']]
                        for row in model['branches']], dtype=float)
    upper_nodes = transfer.read_numeric_csv(folder / 'upstream-linear-nodes.csv', ('node', *transfer.NODE_FIELDS))
    upper_edges = transfer.read_numeric_csv(folder / 'upstream-linear-branches.csv', transfer.BRANCH_FIELDS)
    upper_info, = transfer.read_numeric_csv(folder / 'upstream-vowel-settings.csv', transfer.SUMMARY_FIELDS)
    source = {key: model[key] for key in ('inject', 'lips', 'nose')}
    source['cut'] = tuple(edges[model['cut'][0], :2].astype(int))
    upper_source = {'inject': int(upper_info[0]), 'lips': int(upper_info[3]), 'nose': int(upper_info[4]),
                    'cut': tuple(map(int, upper_info[1:3]))}
    edges, upper_edges = map(transfer.ordered_branches, (edges, upper_edges))
    if nodes.shape != upper_nodes[:, 1:].shape or edges.shape != upper_edges.shape:
        raise ValueError('線形要素の数が固定上流版と異なります')
    tol = cfg['linear_element_relative_tolerance']
    node_error = transfer.relative_errors(nodes, upper_nodes[:, 1:])
    edge_error = transfer.relative_errors(edges[:, 3:], upper_edges[:, 3:])
    edge_bad = np.any(edges[:, :3] != upper_edges[:, :3], axis=1) | np.any(edge_error > tol, axis=1)
    node_bad = np.any(node_error > tol, axis=1)
    actual = transfer.read_numeric_csv(folder / 'transfer.csv', transfer.CANDIDATE_FIELDS)
    upper = transfer.read_numeric_csv(folder / 'upstream-trace.csv', transfer.UPSTREAM_FIELDS)
    if len(actual) != len(upper) or len(actual) != spec['points']:
        raise ValueError('周波数応答の点数が登録条件と異なります')
    freq = actual[:, 0]
    estimated = transfer.independent_response(freq, upper_nodes[:, 1:], upper_edges, upper_source)
    components = np.column_stack([actual[:, i] + 1j*actual[:, i+1] for i in (5, 7, 9, 1)])
    complex_error = transfer.relative_errors(components, estimated)
    np.savetxt(folder / 'independent-response.csv',
               np.column_stack([freq, *[part for column in estimated.T for part in (column.real, column.imag)]]),
               delimiter=',', comments='',
               header='frequency_hz,' + ','.join(f'{name}_{part}' for name in transfer.COMPONENTS
                                                 for part in ('real', 'imaginary')))
    magnitude_error = abs(actual[:, 3] - upper[:, 1]) / upper[:, 1].max()
    db_error = abs(actual[:, 4] - upper[:, 2])
    r_tol, p_tol = (cfg[key] for key in ('response_peak_relative_tolerance', 'pressure_db_absolute_tolerance'))
    first_bad = np.flatnonzero((magnitude_error > r_tol) | (db_error > p_tol) | np.any(complex_error > r_tol, axis=1))
    peaks = transfer.peak_rows(freq, actual[:, 3], spec['peak_search_min_hz'])
    upper_peaks = transfer.read_numeric_csv(folder / 'upstream-peaks.csv', transfer.PEAK_FIELDS, optional_bandwidth=True)
    checks = {
        'upstream_linear_elements_and_injection': (
            source == upper_source and np.array_equal(upper_nodes[:, 0], np.arange(len(nodes)))
            and not node_bad.any() and not edge_bad.any()),
        'registered_frequency_grid': (
            np.max(abs(freq - upper[:, 0])) <= cfg['frequency_absolute_tolerance_hz']
            and np.max(abs(freq - np.geomspace(spec['start_hz'], spec['end_hz'], spec['points'])))
            <= cfg['frequency_absolute_tolerance_hz']),
        'upstream_transfer_magnitude_and_pressure': magnitude_error.max() <= r_tol and db_error.max() <= p_tol,
        'independent_complex_response_lips_nose_wall': np.max(complex_error) <= r_tol,
        'upstream_resonance_peaks': (
            len(peaks) >= 2 and peaks.shape == upper_peaks.shape
            and abs(peaks[:, 0] - upper_peaks[:, 0]).max() <= cfg['peak_frequency_absolute_tolerance_hz']),
    }
    return checks, {
        'linear_nodes_max_relative_error': float(node_error.max()),
        'linear_branches_max_relative_error': float(edge_error.max()),
        'first_bad_node': shared_first(node_bad), 'first_bad_sorted_branch': shared_first(edge_bad),
        'first_bad_frequency_hz': float(freq[first_bad[0]]) if first_bad.size else None,
        'magnitude_peak_relative_error': float(magnitude_error.max()), 'pressure_db_error': float(db_error.max()),
        'complex_peak_relative_errors': dict(zip(transfer.COMPONENTS, complex_error.max(axis=0).tolist(), strict=True)),
        'peaks_hz': peaks[:, 0].tolist(), 'upper_peaks_hz': upper_peaks[:, 0].tolist(),
        'nose_to_lips_peak_ratio': float(abs(components[:, 1]).max()/abs(components[:, 0]).max()),
    }


def shared_first(mask):
    index = np.flatnonzero(mask)
    return int(index[0]) if index.size else None


def impulse(config, case, folder, inlet_compliance, fields):
    cfg = config['measurement']
    spec = config['impulse']
    n = spec['samples']
    rate = case['fixed_airway']['sample_rate_hz']
    actual, upper = (fixed.read_trace(folder / file, fields, n) for file in ('impulse.csv', 'upstream-impulse.csv'))
    error = transfer.relative_errors(actual, upper)
    tol = cfg['impulse_peak_relative_tolerance']
    columns = dict(zip(fields, actual.T, strict=True))
    total = sum(columns[key] for key in ('flow_lips', 'flow_nose', 'flow_walls'))
    derivative = columns['radiation_derivative']
    peak = float(abs(derivative).max())
    tail = float(abs(derivative[spec['tail_start_sample']:]).max() / peak)
    balance = float(abs(np.diff(total, prepend=0) * rate - derivative).max() / peak)
    nose = float(abs(columns['flow_nose']).max())
    nose_ratio = nose / float(abs(columns['flow_lips']).max())
    expected_pressure = spec['volume_cm3'] / inlet_compliance if inlet_compliance is not None else None
    return {
        'upstream_impulse_pressure_and_flows': bool(error.max() <= tol),
        'independent_initial_pressure_and_radiation_sum': (
            expected_pressure is not None and abs(columns['pressure_pharynx_entry'][0] / expected_pressure - 1) <= tol
            and balance <= tol),
        'impulse_radiation_decays': peak > 0 and tail <= cfg['tail_peak_fraction_limit'],
    }, {
        'peak_relative_error': dict(zip(fields, error.max(axis=0).tolist(), strict=True)),
        'first_bad_sample': shared_first(np.any(error > tol, axis=1)), 'tail_peak_fraction': tail,
        'radiation_balance_peak_relative_error': balance, 'nose_to_lips_peak_ratio': nose_ratio,
        'first_lip_radiation_sample': shared_first(columns['flow_lips'] != 0),
        'first_nose_radiation_sample': shared_first(columns['flow_nose'] != 0),
    }


def measure(config, artifacts, execute):
    cfg = config['measurement']
    endpoints = timing.read(BODY_DATA)['measurement']['reference_endpoints']
    fields = timing.read(WORKSPACE / 'cases/fixed-airway-velum-open.json')['measurement']['fixed_airway']['observe']
    execute(['cargo', 'test', '--locked', '-p', 'chimera', '--test', 'body_mix', '--test', 'engine'],
            cwd=UPSTREAM, stdout=artifacts / 'upstream-tests.log')
    build = {}
    for name, path in (('geometry', sagittal.PROBE), ('transfer', transfer.PROBE)):
        folder = artifacts / f'{name}-probe'
        folder.mkdir()
        libraries = ('serde_json',) if name == 'transfer' else ()
        build[name] = shared.build_upstream_probe(path, folder, execute, extra_libraries=libraries)
    rows = {}
    totals = {}
    for variant in config['variants']:
        label = variant['id']
        source = timing.read(WORKSPACE / 'cases' / variant['pose'])
        spec = config['transfer']
        volume, frames = (config['impulse'][key] for key in ('volume_cm3', 'samples'))
        case = {
            'id': f'human-body-airway-{label}', 'upstream_revision': config['upstream_revision'],
            'hypothesis': config['hypothesis'], 'body': variant['body'], 'posture': dict(source['posture']),
            'fixed_airway': {'sample_rate_hz': variant['rate_hz'], 'impulse_volume_cm3': volume, 'sample_count': frames},
            'transfer': {key: spec[key] for key in ('start_hz', 'end_hz', 'points')},
            'measurement': {'frames': 1, 'body': True, 'peak_search_min_hz': spec['peak_search_min_hz']},
        }
        if 'velum_cm2' in variant:
            case['posture']['velum_cm2'] = variant['velum_cm2']
        folder = artifacts / label
        folder.mkdir()
        path = folder / 'case.json'
        timing.write(path, case)
        cli = ['cargo', 'run', '--locked', '--release', '-p', 'vocal-cli', '--']
        execute([*cli, 'inspect', str(path)], stdout=folder / 'inspect.json')
        for command, output in (('area', 'area.csv'), ('render', 'impulse.csv'), ('transfer', 'transfer.csv')):
            execute([*cli, command, str(path), str(folder / output)])
        body = variant['body']
        body_arg = body if isinstance(body, str) else ','.join(str(body.get(key, 0)) for key in ('female', 'child'))
        args = [str(build['geometry']), '--body', body_arg, '--fixed-airway', str(variant['rate_hz'])]
        controls = sagittal.pose_controls(case)
        execute([*args, '0', '0', *controls], cwd=UPSTREAM, stdout=folder / 'upstream-geometry.csv')
        execute([*args, str(frames), str(volume), *controls], cwd=UPSTREAM, stdout=folder / 'upstream-impulse.csv')
        execute([str(build['transfer']), '--case', str(path), str(folder)], cwd=UPSTREAM)

        native = timing.read(folder / 'inspect.json')
        profile = grid.read_grid(folder / 'area.csv', columns=resample.PROFILE_COLUMNS)
        geo_checks, geo, compliance = geometry(config, variant, case, native, profile, folder, endpoints)
        freq_checks, freq = frequency(config, native, folder)
        impulse_checks, time = impulse(config, case, folder, compliance, fields)
        ratios = [freq['nose_to_lips_peak_ratio'], time['nose_to_lips_peak_ratio']]
        nasal_check = (min(ratios) >= cfg['open_velum_minimum_nose_to_lips_peak']
                       if case['posture']['velum_cm2'] > 0 else max(ratios) == 0)
        checks = {**geo_checks, **freq_checks, **impulse_checks, 'nasal_radiation_matches_velum': nasal_check}
        rows[label] = {'geometry': geo, 'frequency': freq, 'impulse': time}
        totals.update({f'{label}/{name}': bool(value) for name, value in checks.items()})
    f1_change = rows['child']['frequency']['peaks_hz'][0] - rows['male']['frequency']['peaks_hz'][0]
    totals['child_f1_increases_in_same_pose'] = f1_change >= cfg['minimum_f1_change_child_vs_male_hz']
    child = rows['child-open-64k']['geometry']
    totals['child_fossa_uses_two_stable_cells_at_64k'] = (
        child['piriform_courant'] < cfg['maximum_design_courant']
        and child['piriform_courant_if_three_cells'] > cfg['child_fossa_three_cell_courant_above'])
    return {'checks': totals, 'cases': rows, 'child_vs_male_f1_change_hz': f1_change}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', args.run_id):
        parser.error('実行IDは英数字で始めてください')
    config = timing.read(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != config['upstream_revision'] or subprocess.check_output(
            ['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True):
        raise SystemExit('変更のない固定上流版が必要です')
    sources = [CASE, BODY_DATA, Path(__file__).resolve(), sagittal.PROBE, transfer.PROBE, *shared.candidate_sources(),
               *(WORKSPACE / 'cases' / row['pose'] for row in config['variants']),
               WORKSPACE / 'cases/fixed-airway-velum-open.json',
               *(Path(module.__file__) for module in (fixed, grid, resample, sagittal, shared, timing, transfer)),
               WORKSPACE / 'tools/upstream_baseline.py']
    upstream = ('crates/chimera/src/voice/human_airway.rs', 'crates/chimera/src/anatomy/human.rs',
                'crates/chimera/src/airway/network.rs', 'crates/chimera/src/airway/frequency.rs',
                'crates/chimera/src/physics.rs', 'crates/chimera/src/math.rs',
                'crates/chimera-cli/src/calibrate.rs', 'crates/chimera-wasm/src/api.rs',
                'crates/chimera/tests/body_mix.rs', 'crates/chimera/tests/engine.rs')
    metadata = {'case_id': config['id'], 'upstream_revision': revision,
                'upstream_source_sha256': {path: sha256(UPSTREAM/path) for path in upstream}}
    return shared.record_measurement(args.run_id, CASE, sources, metadata,
                                     lambda artifacts, execute: measure(config, artifacts, execute), command=None)


if __name__ == '__main__':
    raise SystemExit(main())
