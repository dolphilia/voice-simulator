"""声道セルの境界、調和平均、最小断面を固定上流と独立計算に照合する。"""

import argparse
import csv
import json
from pathlib import Path
import re
import subprocess

import numpy as np

import measure_grid as grid
import measure_sagittal as sagittal
import measure_uniform_tube as shared
from upstream_baseline import UPSTREAM, WORKSPACE


TUBES = ('pharynx', 'oral')
CASES = tuple('resample-' + name for name in (
    'neutral', 'neutral-96k', 'epilarynx', 'closed-roof', 'compressed-lips', 'raised-tip', 'lateral',
))
FIELDS = ('start_cm', 'end_cm', 'area_cm2', 'minimum_area_cm2')
HEADER = ('tube', 'cell', *FIELDS)
PROFILE_COLUMNS = ',gap_cm,area_cm2,s_cm'


def read_cells(path):
    tubes = {}
    with path.open(newline='') as file:
        reader = csv.DictReader(file)
        if reader.fieldnames != list(HEADER):
            raise ValueError(f'{path.name} のヘッダーが不正です')
        for row in reader:
            values = tubes.setdefault(row['tube'], [])
            if row['tube'] != next(reversed(tubes)) or int(row['cell']) != len(values):
                raise ValueError(f'{path.name} のセルの順番が不正です')
            values.append([float(row[field]) for field in FIELDS])
    if tuple(tubes) != TUBES or any(not np.isfinite(rows).all() for rows in tubes.values()):
        raise ValueError(f'{path.name} に管の欠落または非有限な値があります')
    return {tube: np.asarray(rows) for tube, rows in tubes.items()}


def evaluate_area(positions, distance, areas, pose, *, scale=1.0, epilarynx_cm=2.4):
    u = positions / epilarynx_cm
    vent = 0.95 * (1 - 0.75 * np.clip(pose.get('ventricular', 0.0), 0, 1))
    top = np.interp(pose.get('epilarynx', 0.0), [0, 1], [1.9, 0.35])

    def piece(x):
        outlet = np.minimum(1.2 + (top - 1.2) * (x - 0.5) / 0.5, top)
        return np.select([x < 0.3, x < 0.5], [1.3, vent], default=outlet)

    curve = piece(u)
    for centre in (0.3, 0.5):
        limits = np.array([centre - 0.03, centre + 0.03])
        curve = np.where(np.abs(u - centre) < 0.03, np.interp(u, limits, piece(limits)), curve)
    flare = np.clip((positions - 0.9 * epilarynx_cm) / (0.1 * epilarynx_cm), 0, 1)
    curve = curve * scale**2 * (1 - flare) + areas[0] * flare
    return np.where(positions <= epilarynx_cm, curve, np.interp(positions, distance, areas))


def estimate_cells(profile, case, output, *, scale=1.0, epilarynx_cm=2.4):
    region, areas, distance = profile[:, 0], profile[:, -2], profile[:, -1]
    oral_start = distance[region == 2]
    if not oral_start.size or not np.all(np.diff(distance) > 0):
        raise ValueError('比較には口腔の開始点と、厳密に増加する中心線距離が必要です')
    bounds = (0.0, oral_start[0], distance[-1])
    threshold = case['measurement']['resample']['closure_threshold_cm2']
    tubes = {}
    with output.open('w', newline='') as file:
        writer = csv.writer(file, lineterminator='\n')
        writer.writerow((*HEADER, 'midpoint_min_cm2', 'grid_min_cm2'))
        for tube, origin, end in zip(TUBES, bounds[:-1], bounds[1:], strict=True):
            count = case['cells'][tube]
            width = (end - origin) / count
            indices = np.arange(count)
            edges = origin + width * np.arange(count + 1)
            positions = origin + width * (indices[:, None] + (np.arange(8) + 0.5) / 8)
            values = evaluate_area(positions, distance, areas, case['posture'],
                                   scale=scale, epilarynx_cm=epilarynx_cm)
            # 両端を含む。末端だけは丸めで格子点を取りこぼさない幅を足す。
            knot_ends = edges[1:].copy()
            knot_ends[-1] += 1e-6
            inside = (edges[:-1, None] <= distance) & (distance <= knot_ends[:, None])
            point_minimum = np.min(np.where(inside, areas, np.inf), axis=1)
            midpoint_minimum = values.min(axis=1)
            closed = np.minimum(midpoint_minimum, point_minimum) <= threshold
            with np.errstate(divide='ignore'):
                harmonic = np.where(closed, 0.0, 8 / np.sum(1 / values, axis=1))
            minima = np.where(closed, 0.0, np.minimum.reduce([point_minimum, midpoint_minimum, harmonic]))
            rows = np.column_stack((edges[:-1], edges[1:], harmonic, minima))
            point_only = np.flatnonzero((point_minimum <= threshold) & (midpoint_minimum > threshold))
            for index, row in enumerate(rows):
                point = point_minimum[index]
                writer.writerow((tube, index, *row, midpoint_minimum[index], point if np.isfinite(point) else ''))
            tubes[tube] = (rows, point_only, midpoint_minimum)
    return tubes


def compare_rows(candidate, target, limits):
    if candidate.shape != target.shape:
        return {'status': False, 'candidate_count': len(candidate), 'reference_count': len(target)}
    errors = np.abs(candidate - target)
    failures = np.flatnonzero(np.any(errors >= limits, axis=1))
    return {
        'status': not failures.size,
        'max_error': dict(zip(FIELDS, errors.max(axis=0).tolist(), strict=True)),
        'first_cell_over_tolerance': int(failures[0]) if failures.size else None,
    }


def measure(case, path, artifacts, execute):
    upper = read_cells(sagittal.capture_upstream(case, artifacts, execute, mode='--resample'))
    candidate = read_cells(artifacts / 'trace.csv')
    profile_path = artifacts / 'area-profile.csv'
    execute(['cargo', 'run', '--locked', '--release', '-p', 'vocal-cli', '--', 'area',
             str(path), str(profile_path)])
    profile = grid.read_grid(profile_path, columns=PROFILE_COLUMNS)
    upper_profile = grid.read_grid(artifacts / 'upstream-area.csv', columns=PROFILE_COLUMNS)
    cfg = case['measurement']['resample']
    cm = cfg['position_error_lt_cm']
    cm2 = cfg['area_error_lt_cm2']
    checks = {'upstream_grid_shape_and_regions':
              profile.shape == upper_profile.shape and np.array_equal(profile[:, 0], upper_profile[:, 0])}
    result = {'checks': checks, 'tubes': {}}
    if checks['upstream_grid_shape_and_regions']:
        gap_error, area_error, distance_error = np.max(np.abs(profile[:, -3:] - upper_profile[:, -3:]), axis=0)
        checks['upstream_input_profile'] = bool(gap_error < cm and area_error < cm2 and distance_error < cm)
        result['input_profile_max_error'] = {
            'gap_cm': float(gap_error), 'area_cm2': float(area_error), 's_cm': float(distance_error),
        }
    else:
        checks['upstream_input_profile'] = False
    analytic = estimate_cells(profile, case, artifacts / 'independent-cells.csv')
    settings = json.loads((artifacts / 'settings.json').read_text())['resample']
    checks['contiguous_tubes_from_glottis'] = bool(
        abs(candidate['pharynx'][0, 0]) < cm
        and abs(candidate['oral'][0, 0] - candidate['pharynx'][-1, 1]) < cm
        and abs(candidate['oral'][-1, 1] - profile[-1, -1]) < cm
    )
    for tube in TUBES:
        actual = candidate[tube]
        expected, close_only, midpoint_min = analytic[tube]
        limits = [cm, cm, cm2, cm2]
        upstream_cmp = compare_rows(actual, upper[tube], limits)
        analytic_cmp = compare_rows(actual, expected, limits)
        start, end, area, minimum = actual.T
        closed = np.flatnonzero(area == 0.0).tolist()
        length = float(end[-1] - start[0])
        minimum_of_tube = float(minimum.min())
        length_lo, length_hi = cfg['length_intervals_cm'][tube]
        min_lo, min_hi = cfg['minimum_intervals_cm2'][tube]
        checks.update({f'{tube}_{name}': passed for name, passed in {
            'registered_cell_count': len(actual) == len(upper[tube]) == case['cells'][tube]
                                     == settings[f'{tube}_cells'],
            'upstream_cells': upstream_cmp['status'],
            'independent_cells': analytic_cmp['status'],
            'positive_contiguous_equal_width': bool(
                np.all(end > start) and np.all(np.abs(start[1:] - end[:-1]) < cm)
                and np.all(np.abs(end - start - length / len(actual)) < cm)),
            'length': length_lo <= length <= length_hi and abs(length - settings[f'{tube}_length_cm']) < cm,
            'minimum': min_lo <= minimum_of_tube <= min_hi,
            'minimum_no_larger_than_mean': bool(np.all((minimum >= 0.0) & (minimum <= area))),
            'registered_closed_cells': closed == cfg['closed_indices'][tube],
            'registered_grid_point_only_closures': close_only.tolist() == cfg['point_closure_only_indices'][tube]
                                                   and set(close_only).issubset(closed),
        }.items()})
        result['tubes'][tube] = {
            'cell_count': len(actual), 'length_cm': length, 'minimum_area_cm2': minimum_of_tube,
            'minimum_harmonic_area_cm2': float(area.min()),
            'largest_mean_minus_minimum_cm2': float((area - minimum).max()),
            'closed_indices': closed,
            'point_closure_only_indices': close_only.tolist(),
            'point_closure_midpoint_minima_cm2': midpoint_min[close_only].tolist(),
            'upstream': upstream_cmp, 'independent': analytic_cmp,
        }
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

    def measure_run(artifacts, execute):
        return measure(case, path, artifacts, execute)

    sources = [path, sagittal.PROBE, Path(__file__).resolve(), Path(sagittal.__file__),
               Path(grid.__file__), Path(shared.__file__), WORKSPACE / 'tools/upstream_baseline.py',
               *shared.candidate_sources()]
    details = {'upstream_revision': revision, 'case_id': case['id']}
    return shared.record_measurement(args.run_id, path, sources, details, measure_run, command='resample')


if __name__ == '__main__':
    raise SystemExit(main())
