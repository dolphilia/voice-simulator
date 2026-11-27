"""矢状面の輪郭を固定上流と独立な回転・接線の計算に照合する。"""

import argparse
import csv
import json
from pathlib import Path
import re
import subprocess

import numpy as np

import measure_uniform_tube as shared
from upstream_baseline import UPSTREAM, WORKSPACE


PROBE = WORKSPACE / 'tools/upstream_sagittal_probe.rs'
CASES = ('sagittal-neutral', 'sagittal-open-jaw')
NATIVE_TEST = 'a_ray_grazing_a_polyline_vertex_sees_no_tissue_layer_that_is_not_there'


def read_points(path):
    parts = {}
    with path.open(newline='') as file:
        reader = csv.DictReader(file)
        if reader.fieldnames != ['part', 'index', 'x_cm', 'y_cm']:
            raise ValueError(f'{path.name} のヘッダーが不正です')
        for row in reader:
            points = parts.setdefault(row['part'], [])
            if int(row['index']) != len(points):
                raise ValueError(f'{path.name} の点番号が連続していません')
            points.append([float(row['x_cm']), float(row['y_cm'])])
    if not all(np.isfinite(points).all() for points in parts.values()):
        raise ValueError(f'{path.name} に非有限の座標があります')
    return {part: np.asarray(points) for part, points in parts.items()}


def pose_controls(case):
    p = case['posture']
    controls = [p['jaw_cm'], *p['tongue_body_cm'], *p['tongue_tip_cm'],
                *(p[k] for k in ('tongue_root_cm', 'tip_curl', 'dorsum', 'lip_aperture_cm',
                                  'lip_protrusion_cm', 'lip_spread', 'labiodental', 'velum_cm2', 'larynx_cm'))]
    if 'epilarynx' in p or 'ventricular' in p:
        controls.extend(p.get(key, 0.0) for key in ('lateral', 'epilarynx', 'ventricular'))
    elif 'lateral' in p:
        controls.append(p['lateral'])
    return list(map(str, controls))


def capture_upstream(case, artifacts, execute, *, mode=None):
    test = 'no_area_jumps_on_the_way_between_calibrated_vowels' if mode == '--resample' else NATIVE_TEST
    execute(['cargo', 'test', '--locked', '-p', 'chimera', '--test', 'geometry_continuity',
             test, '--', '--nocapture'], cwd=UPSTREAM, stdout=artifacts / 'upstream-geometry-test.log')
    probe = shared.build_upstream_probe(PROBE, artifacts, execute)
    output = artifacts / 'upstream-trace.csv'
    flags = [mode] if mode else []
    if mode == '--resample':
        flags.extend(str(case['cells'][tube]) for tube in ('pharynx', 'oral'))
    args = pose_controls(case)
    execute([str(probe), *flags, *args], cwd=UPSTREAM, stdout=output)
    if mode == '--contact':
        execute([str(probe), '--contact-metrics', *args], cwd=UPSTREAM,
                stdout=artifacts / 'upstream-contact-metrics.csv')
    if mode == '--area':
        execute([str(probe), '--area-metrics', *args], cwd=UPSTREAM,
                stdout=artifacts / 'upstream-area-metrics.csv')
    if mode == '--resample':
        execute([str(probe), '--area', *args], cwd=UPSTREAM, stdout=artifacts / 'upstream-area.csv')
    return output


def first_horizontal_crossing(points, height):
    for aa, bb in zip(points[:-1], points[1:], strict=True):
        if min(aa[1], bb[1]) <= height < max(aa[1], bb[1]):
            return float(aa[0] + (bb[0] - aa[0]) * (height - aa[1]) / (bb[1] - aa[1]))
    raise ValueError(f'高さ {height:g} cm で輪郭に交差がありません')


def analytic_geometry(case, parts):
    cfg, pose = case['measurement'], case['posture']

    def head(template):
        x, y = np.asarray(template).T
        return np.stack((np.where(x > 0.5, 0.5 + (x - 0.5) * 0.86, x), y), axis=-1)

    def absolute_error(actual, expected):
        return float(np.max(np.linalg.norm(np.atleast_2d(actual - expected), axis=1)))

    condyle = complex(-2.5, 10.5)
    lower_template = head([[6.45, 6.55], [6.72, 7.15], [6.95, 7.75], [7.12, 7.45]])
    bone_template = head([[7.25, 6.75], [7.4, 5.4], [6.4, 4.6], [3.5, 4.4],
                          [1.2, 5.2], [-0.6, 7.4], [-1.9, 9.6]])
    tooth_radius = abs(complex(*lower_template[2]) - condyle)
    jaw_rotation = np.exp(-1j * pose['jaw_cm'] / tooth_radius)
    jaw_error = 0.0
    for name, template in (('lower_teeth', lower_template), ('jaw_bone', bone_template)):
        moved = condyle + (template[:, 0] + 1j * template[:, 1] - condyle) * jaw_rotation
        jaw_error = max(jaw_error, absolute_error(parts[name], np.c_[moved.real, moved.imag]))

    center = parts['tongue_center'][0]
    tip = parts['tip'][0]
    anchors = [
        (center, head(pose['tongue_body_cm'])),
        (tip, head(pose['tongue_tip_cm'])),
        (parts['glottis'][0], np.array([0.0, pose['larynx_cm']])),
        (parts['palate'][0], head([1.0, 9.6])),
        (parts['palate'][-1], head([7.12, 7.95])),
        (parts['nasal_cavity'][0], head([1.0, 9.75])),
        (parts['nasal_cavity'][-1], head([8.0, 10.1])),
    ]
    anchor_error = max(absolute_error(observed, expected) for observed, expected in anchors)
    arc = parts['tongue'][slice(*cfg['tongue_arc_indices'])]
    radius_error = float(np.max(np.abs(np.linalg.norm(arc - center, axis=1) - cfg['circle_radius_cm'])))
    tangent_dot = float(np.dot(arc[-1] - center, tip - arc[-1]))
    # 上唇と硬口蓋の点数を使い、口蓋垂へつなぐ後壁の端を特定する。
    velum_tip_index = len(parts['outer']) - (len(parts['palate']) - 1) - 7 - len(parts['velum']) // 2
    wall_end = parts['outer'][velum_tip_index - 1]
    velum_tip = parts['velum'][len(parts['velum']) // 2]
    join_error = max(
        abs(float(velum_tip[1] - wall_end[1]) - 0.3),
        absolute_error(parts['outer'][velum_tip_index], velum_tip),
        absolute_error(parts['velum'][-1], parts['palate'][0]),
        abs(float(parts['inner'][2, 1] - parts['epiglottis'][1, 1]) - 0.05),
    )
    y = cfg['pharynx_y_cm']
    posterior = first_horizontal_crossing(parts['outer'], y)
    anterior = first_horizontal_crossing(parts['inner'], y)
    gap = anterior - posterior
    tooth_y = float(parts['lower_teeth'][2, 1])
    lo_tooth, hi_tooth = cfg['lower_incisor_y_interval_cm']
    lo_gap, hi_gap = cfg['pharynx_gap_interval_cm']
    tolerance = cfg['analytic_coordinate_error_lt_cm']
    return {
        'jaw_rigid_rotation': jaw_error < tolerance,
        'head_coordinate_anchors': anchor_error < tolerance,
        'tongue_circle_radius': radius_error < tolerance,
        'tongue_blade_tangent': abs(tangent_dot) < cfg['tangent_dot_abs_lt_cm2'],
        'wall_joins': join_error < tolerance,
        'lower_incisor_height': lo_tooth <= tooth_y <= hi_tooth,
        'pharyngeal_gap': lo_gap <= gap <= hi_gap,
    }, {
        'jaw_max_error_cm': jaw_error, 'anchor_max_error_cm': anchor_error,
        'tongue_radius_max_error_cm': radius_error, 'tongue_tangent_dot_cm2': tangent_dot,
        'wall_join_max_error_cm': join_error, 'lower_incisor_cm': parts['lower_teeth'][2].tolist(),
        'pharynx_x_interval_cm': [posterior, anterior], 'pharynx_gap_cm': gap,
    }


def measure(case, artifacts, execute):
    upper = read_points(capture_upstream(case, artifacts, execute))
    parts = read_points(artifacts / 'trace.csv')
    cfg = case['measurement']
    expected_counts = cfg['point_counts']
    counts = {part: len(points) for part, points in parts.items()}
    upper_counts = {part: len(points) for part, points in upper.items()}
    checks = {
        'registered_point_counts': counts == upper_counts == expected_counts,
        'upstream_part_order': list(parts) == list(upper) == list(expected_counts),
    }
    result = {'checks': checks, 'point_counts': counts, 'upstream_point_counts': upper_counts}
    if counts == upper_counts:
        distances = {part: np.linalg.norm(points - upper[part], axis=1) for part, points in parts.items()}
        maxima = {part: float(np.max(values)) for part, values in distances.items()}
        maximum = max(maxima.values())
        limit = cfg['upstream_point_distance_lt_cm']
        checks['upstream_points'] = maximum < limit
        result.update(upstream_max_distance_cm=maximum, upstream_part_max_distance_cm=maxima,
                      first_point_over_tolerance={
                          part: int(failed[0]) if (failed := np.flatnonzero(values >= limit)).size else None
                          for part, values in distances.items()})
    if counts == expected_counts:
        independent, result['analytic_geometry'] = analytic_geometry(case, parts)
        checks.update(independent)
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
    if (revision != case['upstream_revision'] or
            subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True)):
        raise ValueError('変更のない固定上流版が必要です')
    sources = [path, PROBE, Path(__file__).resolve(), Path(shared.__file__),
               WORKSPACE / 'tools/upstream_baseline.py', *shared.candidate_sources()]
    details = {'upstream_revision': revision, 'case_id': case['id']}

    def measure_run(artifacts, execute):
        return measure(case, artifacts, execute)

    return shared.record_measurement(args.run_id, path, sources, details, measure_run, command='geometry')


if __name__ == '__main__':
    raise SystemExit(main())
