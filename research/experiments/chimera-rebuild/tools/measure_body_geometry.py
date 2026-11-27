"""各体型の輪郭とセルを、固定上流と独立した幾何・補間計算に照合する。"""

import argparse
import csv
import json
import math
from pathlib import Path
import re
import subprocess

import numpy as np

import measure_grid as grid
import measure_resample as resample
import measure_sagittal as sagittal
import measure_speech_timing as timing
import measure_uniform_tube as shared
from upstream_baseline import UPSTREAM, WORKSPACE, sha256

CASE = WORKSPACE / 'cases/human-body-geometry.json'
NAMES = ('male', 'female', 'child')


def read_record(path):
    with path.open(newline='') as file:
        row, = csv.DictReader(file)
    return row


def upstream_body(path):
    row = read_record(path)
    names = ('scale', 'pharynx', 'tongue_radius', 'lip_width', 'fold_length', 'open_phase')
    shape = ('default_f0_hz', 'tongue_radius_cm', 'lip_width_cm', 'velum_port_cm2', 'epilarynx_length_cm')
    return {'weights': [float(row[name]) for name in NAMES], 'preset': row['preset'] or None,
            'nearest': row['nearest'], 'parameters': {name: float(row[name]) for name in names},
            **{name: float(row[name]) for name in shape}}


def independent_body(variant, pose, cfg):
    body = variant['body']
    if isinstance(body, str):
        weights = [float(name == body) for name in NAMES]
    else:
        female, child = (min(max(body.get(axis, 0), 0), 1) for axis in ('female', 'child'))
        adult_female = (1 - child) * female
        weights = [1 - child - adult_female, adult_female, child]
    reference = [cfg['reference_endpoints'][name] for name in NAMES]
    geom = {key: math.fsum(weight * param[key] for weight, param in zip(weights, reference, strict=True))
            for key in reference[0] if key != 'f0_hz'}
    first = max(range(len(weights)), key=weights.__getitem__)
    k = geom['scale']
    spread = min(max(pose['lip_spread'], 0), 1)
    return {
        'weights': weights, 'preset': NAMES[first] if weights[first] == 1 else None, 'nearest': NAMES[first],
        'parameters': geom,
        'default_f0_hz': math.prod(param['f0_hz'] ** weight for weight, param in zip(weights, reference, strict=True)),
        'tongue_radius_cm': k * geom['tongue_radius'],
        'lip_width_cm': k * ((1 - spread) * 1.1 + spread * geom['lip_width']),
        'velum_port_cm2': max(pose['velum_cm2'], 0) * k**2,
        'epilarynx_length_cm': 2.4 * k * geom['pharynx'],
    }


def analytic_landmarks(pose, parts, body):
    scale, short = (body['parameters'][key] for key in ('scale', 'pharynx'))

    def transform(x, y):
        return scale * complex(x if x <= 0.5 else 0.5 + 0.86 * (x - 0.5),
                               y if y >= 7 else 7 + (y - 7) * short)

    condyle = transform(-2.5, 10.5)
    radius = abs(transform(6.95, 7.75) - condyle)
    rotate = np.exp(-1j * np.clip(pose['jaw_cm'], -0.2, 3.0) * scale / radius)
    incisors = [condyle + rotate * (transform(x, y) - condyle)
                for x, y in ((6.45, 6.55), (6.72, 7.15), (6.95, 7.75), (7.12, 7.45))]
    center = transform(*pose['tongue_body_cm'])
    tip = transform(*pose['tongue_tip_cm'])
    distance = abs(tip - center)
    minimum_radius = 1.05 * body['tongue_radius_cm']
    if 0 < distance < minimum_radius:
        tip = center + minimum_radius * (tip - center) / distance
    rear = center + body['tongue_radius_cm'] * np.exp(1j * math.radians(200))
    expected = {
        'lower_teeth': (parts['lower_teeth'], incisors),
        'anchors': (
            np.stack([parts['palate'][0], parts['palate'][-1], parts['nasal_cavity'][0], parts['nasal_cavity'][-1],
                      parts['tongue_center'][0], parts['tip'][0], parts['tongue'][8], parts['glottis'][0]]),
            [transform(1, 9.6), transform(7.12, 7.95), transform(1, 9.75), transform(8, 10.1),
             center, tip, rear, transform(0, 0) + 1j * pose['larynx_cm'] * scale],
        ),
    }
    return {name: float(np.max(abs(points[:, 0] + 1j * points[:, 1] - analytic)))
            for name, (points, analytic) in expected.items()}


def compare_arrays(actual, expected, tolerance):
    if actual.shape != expected.shape:
        return {'status': False, 'actual_shape': list(actual.shape), 'expected_shape': list(expected.shape)}
    error = np.abs(actual - expected)
    exceed = np.flatnonzero(np.any(error > tolerance, axis=1))
    return {'status': not bool(exceed.size), 'max_error': error.max(axis=0).tolist(),
            'first_row_over_tolerance': int(exceed[0]) if exceed.size else None}


def one_case(config, pose, variant, artifacts, execute, probe):
    folder = artifacts / f"{pose['id']}-{variant['id']}"
    folder.mkdir()
    cfg = config['measurement']
    body = variant['body']
    base = timing.read(WORKSPACE / 'cases' / pose['from_case'])
    case = {
        'id': folder.name, 'upstream_revision': config['upstream_revision'], 'hypothesis': config['hypothesis'],
        'body': body, 'posture': {**base['posture'], **pose.get('overrides', {})}, 'cells': config['cells'],
        'measurement': {'frames': 1, 'body': True, 'area': True, 'contact': True,
                        'resample': {'closure_threshold_cm2': cfg['closure_area_cm2']}},
    }
    path = folder / 'case.json'
    path.write_text(json.dumps(case, ensure_ascii=False, indent=2) + '\n')
    prefix = ['cargo', 'run', '--locked', '--release', '-p', 'vocal-cli', '--']
    execute([*prefix, 'inspect', str(path)], stdout=folder / 'inspect.json')
    for name in ('geometry', 'area', 'resample'):
        execute([*prefix, name, str(path), str(folder / f'{name}.csv')])
    label = body if isinstance(body, str) else ','.join(str(body.get(axis, 0)) for axis in ('female', 'child'))
    upper = [str(probe), '--body', label]
    controls = sagittal.pose_controls(case)
    for name, args in (('geometry', []), ('area', ['--area']), ('body', ['--body-metrics']),
                       ('contact', ['--contact-metrics']),
                       ('resample', ['--resample', *(str(case['cells'][tube]) for tube in resample.TUBES)])):
        execute([*upper, *args, *controls], cwd=UPSTREAM, stdout=folder / f'upstream-{name}.csv')

    settings = timing.read(folder / 'inspect.json')
    actual = settings['body']
    independent = independent_body(variant, case['posture'], cfg)
    tolerance = cfg['parameter_absolute_tolerance']
    upper_diff, body_error = timing.compare(actual, upstream_body(folder / 'upstream-body.csv'), tolerance)
    independent_diff, independent_error = timing.compare(actual, independent, tolerance)
    wt = cfg['weight_absolute_tolerance']
    parts = sagittal.read_points(folder / 'geometry.csv')
    reference = sagittal.read_points(folder / 'upstream-geometry.csv')
    contour_tol = cfg['contour_absolute_tolerance_cm']
    contours = {part: compare_arrays(points, reference.get(part, np.empty((0, 2))), contour_tol)
                for part, points in parts.items()}
    analytic = analytic_landmarks(case['posture'], parts, independent)
    cm, cm2 = (cfg[key] for key in ('centerline_absolute_tolerance_cm', 'area_absolute_tolerance_cm2'))
    profile = grid.read_grid(folder / 'area.csv', columns=resample.PROFILE_COLUMNS)
    upper_profile = grid.read_grid(folder / 'upstream-area.csv', columns=resample.PROFILE_COLUMNS)
    profile_results = compare_arrays(profile, upper_profile, [0, *([cm]*8), cm2, cm])
    mid = profile[:, 5:7]
    length = independent['epilarynx_length_cm'] + np.r_[0, np.cumsum(np.linalg.norm(np.diff(mid, axis=0), axis=1))]
    length_error = float(np.max(abs(length - profile[:, -1])))
    with (folder / 'upstream-contact.csv').open(newline='') as file:
        contact_error = {
            row['part']: abs(settings['contact'][row['part']]['distance_cm'] - float(row['distance_cm']))
            for row in csv.DictReader(file)
        }
    observed_cells = resample.read_cells(folder / 'resample.csv')
    reference_cells = resample.read_cells(folder / 'upstream-resample.csv')
    own_cells = resample.estimate_cells(profile, case, folder / 'independent-cells.csv',
                                        scale=independent['parameters']['scale'],
                                        epilarynx_cm=independent['epilarynx_length_cm'])
    cells = {
        name: {'upper': compare_arrays(observed_cells[name], reference_cells[name], [cm, cm, cm2, cm2]),
               'independent': compare_arrays(observed_cells[name], own_cells[name][0], [cm, cm, cm2, cm2])}
        for name in resample.TUBES
    }
    checks = {
        'registered_and_normalized_weights': (
            np.allclose(actual['weights'], variant['weights'], atol=wt, rtol=0)
            and abs(sum(actual['weights']) - 1) <= wt and min(actual['weights']) >= 0
            and actual['preset'] == variant['preset'] and actual['nearest'] == variant['nearest']
        ),
        'body_matches_upstream_and_independent_blend': upper_diff is None and independent_diff is None,
        'all_contours_match_upstream': list(parts) == list(reference) and all(row['status'] for row in contours.values()),
        'independent_jaw_rotation_and_landmarks': max(analytic.values()) <= contour_tol,
        'scaled_contact_distances': max(contact_error.values()) <= cfg['contact_distance_absolute_tolerance_cm'],
        'grid_and_area_profile_match_upstream': profile_results['status'],
        'epilarynx_and_centerline_lengths': length_error <= cm,
        'resampling_matches_upstream_and_independent_cells': all(
            result['status'] for pair in cells.values() for result in pair.values()),
    }
    return {
        'id': case['id'], 'checks': checks, 'body': actual, 'area': settings['area'],
        'body_max_error': body_error, 'independent_body_max_error': independent_error,
        'first_upstream_body_difference': upper_diff, 'first_independent_body_difference': independent_diff,
        'contours': contours, 'analytic_landmark_max_errors_cm': analytic, 'profile': profile_results,
        'centerline_max_error_cm': length_error, 'contact_distance_max_error_cm': contact_error, 'cells': cells,
    }


def measure(config, artifacts, execute):
    execute(['cargo', 'test', '--locked', '-p', 'chimera', '--test', 'body_mix'],
            cwd=UPSTREAM, stdout=artifacts / 'upstream-tests.log')
    probe = shared.build_upstream_probe(sagittal.PROBE, artifacts, execute)
    cases = {}
    deviations = {}
    checks = {}
    for pose in config['poses']:
        rows = {}
        for variant in config['variants']:
            row = one_case(config, pose, variant, artifacts, execute, probe)
            rows[variant['id']] = row
            checks.update({f"{row['id']}/{name}": value for name, value in row['checks'].items()})
        male, child = (rows[name]['area']['pharynx_length_cm'] for name in ('male', 'child'))
        child_scale = rows['child']['body']['parameters']['scale']
        deviation = child - male * child_scale
        deviations[pose['id']] = deviation
        checks[f"{pose['id']}/pharynx_shorter_than_uniform_child_scale"] = (
            -deviation >= config['measurement']['minimum_nonuniform_pharynx_length_change_cm'])
        cases[pose['id']] = rows
    return {'checks': checks, 'cases': cases, 'child_pharynx_minus_uniform_cm': deviations}


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
    sources = [CASE, Path(__file__), sagittal.PROBE, *shared.candidate_sources(),
               *(WORKSPACE / 'cases' / pose['from_case'] for pose in config['poses']),
               *(Path(module.__file__) for module in (grid, resample, sagittal, shared, timing)),
               WORKSPACE / 'tools/upstream_baseline.py']
    upstream_paths = ('crates/chimera/src/anatomy/human.rs', 'crates/chimera/src/anatomy/geom.rs',
                      'crates/chimera/src/engine.rs', 'crates/chimera/src/math.rs',
                      'crates/chimera/src/voice/human_airway.rs', 'crates/chimera-wasm/src/api.rs',
                      'crates/chimera/tests/body_mix.rs')
    metadata = {'case_id': config['id'], 'upstream_revision': revision,
                'upstream_source_sha256': {path: sha256(UPSTREAM/path) for path in upstream_paths}}
    return shared.record_measurement(args.run_id, CASE, sources, metadata,
                                     lambda artifacts, execute: measure(config, artifacts, execute), command=None)


if __name__ == '__main__':
    raise SystemExit(main())
