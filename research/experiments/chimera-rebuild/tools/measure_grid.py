"""半極座標の測定線を上流フレームと独立な線分補間に照合する。"""

import argparse
import json
from pathlib import Path
import re
import subprocess

import numpy as np

import measure_sagittal as sagittal
import measure_uniform_tube as shared
from upstream_baseline import UPSTREAM, WORKSPACE


CASES = ('grid-neutral', 'grid-open-jaw', 'grid-shifted-tongue', 'grid-closed-roof', 'grid-labiodental')
HEADER = 'index,region,inner_x_cm,inner_y_cm,outer_x_cm,outer_y_cm,mid_x_cm,mid_y_cm,ray_cm'


def intersections(points, origin, direction, limit):
    """線分両端の符号付き高さを補間し、交点を測定線に投影する。"""
    direction = np.asarray(direction)
    local = points - origin
    heights = local @ np.array([-direction[1], direction[0]])
    changes = (heights[1:] >= 0) != (heights[:-1] >= 0)
    delta = np.diff(heights)
    eligible = np.flatnonzero(changes & (np.abs(delta) >= 1e-15))
    u = -heights[eligible] / delta[eligible]
    points_on_line = local[eligible] + u[:, None] * np.diff(local, axis=0)[eligible]
    along = points_on_line @ direction
    within = (along >= 0) & (along <= limit)
    return along[within][:64], (delta[eligible][within] < 0)[:64]


def smoothstep(x):
    t = np.clip(x, 0, 1)
    return t**2 * (3 - 2 * t)


def independent_grid(case, parts):
    inner, outer = parts['inner'], parts['outer']
    lab = np.clip(case['posture']['labiodental'], 0, 1)
    upper_x, _ = parts['upper_lip'][6]
    lower_x, lower_y = parts['lower_lip'][6]
    rays = []
    rear_fallback = 0
    extra_tissue = 0
    lip_extensions = 0
    no_outer_hit = 0

    def add(origin, direction, region, limit, *, fan=False):
        nonlocal rear_fallback, extra_tissue, lip_extensions, no_outer_hit
        origin, direction = np.asarray(origin), np.asarray(direction)
        outside, _ = intersections(outer, origin, direction, limit)
        if not outside.size:
            no_outer_hit += 1
            return
        roof = float(outside.min())
        far = roof + 1.5
        inside, exit_tissue = intersections(inner, origin, direction, far)
        if fan:
            order = np.argsort(inside, kind='stable')
            inside, exit_tissue = inside[order], exit_tissue[order]
            if inside.size and exit_tissue[0]:
                floor = float(inside[0])
                cursor = 1
            else:
                back, _ = intersections(inner, origin, -direction, 2.5)
                floor = -float(back.min()) if back.size else -2.5
                cursor = 0
                rear_fallback += 1
            tissue = 0.0
            while cursor < inside.size and inside[cursor] < roof:
                if exit_tissue[cursor]:
                    cursor += 1
                else:
                    exit_at = inside[cursor + 1] if cursor + 1 < inside.size else far
                    tissue += min(exit_at, roof) - inside[cursor]
                    cursor += 2
            extra_tissue += int(tissue > 1e-10)
            floor += tissue
        else:
            valid = inside[inside < far]
            floor = float(valid.max()) if valid.size else max(0.0, roof - 3.5)

        outer_hit = origin + roof * direction
        inner_hit = origin + min(floor, roof) * direction
        gap = max(0.0, roof - floor)
        if region == 3 and origin[0] > lower_x:
            forward = origin[0] - lower_x
            face_y = min(lower_y - 4 * forward / 3, outer_hit[1])
            blend = smoothstep((lab - 0.7) / 0.3) * smoothstep(forward / 0.1)
            rebuilt_y = (1 - blend) * face_y + blend * (outer_hit[1] - 3.5)
            inner_hit = np.array([origin[0], rebuilt_y])
            gap = outer_hit[1] - rebuilt_y
            lip_extensions += 1
        rays.append([region, *inner_hit, *outer_hit, *((inner_hit + outer_hit) / 2), gap])

    first_height = parts['glottis'][0, 1] + 2.52
    for height in np.linspace(first_height, 6.95, 12, endpoint=False):
        add([4.6, height], [-1.0, 0.0], 1, 9.0)
    center_a = np.array([0.5 + 2.1 * 0.86, 6.95])
    center_b = np.array([0.5 + 4.5 * 0.86, 6.85])
    for index, degrees in enumerate(np.linspace(180, 36, 31)):
        blend = smoothstep((index / 30 - 0.45) / 0.55)
        origin = (1 - blend) * center_a + blend * center_b
        angle = np.deg2rad(degrees)
        add(origin, [np.cos(angle), np.sin(angle)], 1 if degrees > 150 else 2, 8.0, fan=True)
    front_start = parts['palate'][-1, 0] + 0.03
    front_end = max(front_start + 0.3, min(upper_x, lower_x) - 0.04)
    for x in np.linspace(front_start, front_end, 6):
        add([x, 4.0], [0.0, 1.0], 3, 8.0)

    return np.asarray(rays), {
        'fan_reverse': rear_fallback, 'fan_with_extra_tissue': extra_tissue,
        'front_extensions': lip_extensions, 'no_outer_hit': no_outer_hit,
    }


def read_grid(path, *, columns=''):
    header = HEADER + columns
    with path.open() as file:
        if file.readline().rstrip() != header:
            raise ValueError(f'{path.name} のヘッダーが不正です')
        rows = np.loadtxt(file, delimiter=',', ndmin=2)
    if rows.shape[1] != len(header.split(',')) or not np.isfinite(rows).all() or not np.array_equal(rows[:, 0], np.arange(len(rows))):
        raise ValueError(f'{path.name} に不正な値または点番号があります')
    return rows[:, 1:]


def compare_grid(candidate, reference, limit):
    if candidate.shape != reference.shape:
        return {'counts': [len(candidate), len(reference)], 'status': False}
    distances = np.abs(candidate[:, 1:] - reference[:, 1:])
    maxima = np.max(distances, axis=0)
    first = np.flatnonzero((candidate[:, 0] != reference[:, 0]) | np.any(distances >= limit, axis=1))
    return {
        'field_max_error_cm': dict(zip(HEADER.split(',')[2:], maxima.tolist(), strict=True)),
        'max_error_cm': float(max(maxima)),
        'first_grid_index_over_tolerance': int(first[0]) if first.size else None,
        'status': first.size == 0,
    }


def measure(case, path, artifacts, execute):
    upper = read_grid(sagittal.capture_upstream(case, artifacts, execute, mode='--grid'))
    candidate = read_grid(artifacts / 'trace.csv')
    contours = artifacts / 'contours.csv'
    execute(['cargo', 'run', '--locked', '--release', '-p', 'vocal-cli', '--', 'geometry', str(path), str(contours)])
    expected, diagnostics = independent_grid(case, sagittal.read_points(contours))
    cfg = case['measurement']['grid']
    upper_cmp = compare_grid(candidate, upper, cfg['upstream_max_error_lt_cm'])
    independent_cmp = compare_grid(candidate, expected, cfg['independent_max_error_lt_cm'])
    gap = candidate[:, -1]
    midpoint_error = float(np.max(np.abs(candidate[:, 5:7] - (candidate[:, 1:3] + candidate[:, 3:5]) / 2)))
    chord = np.linalg.norm(candidate[:, 3:5] - candidate[:, 1:3], axis=1)
    chord_error = float(np.max(np.abs(chord - gap)))
    regions = [int(np.count_nonzero(candidate[:, 0] == value)) for value in (1, 2, 3)]
    minimum_gap = float(np.min(gap))
    min_lo, min_hi = cfg['minimum_gap_interval_cm']
    checks = {
        'upstream_grid': upper_cmp['status'],
        'independent_intersections': independent_cmp['status'],
        'registered_grid_counts': regions == cfg['region_counts'],
        'nonnegative_and_midpoints': bool(np.all(gap >= 0)) and midpoint_error < cfg['independent_max_error_lt_cm'],
        'gap_matches_effective_chord': chord_error < cfg['independent_max_error_lt_cm'],
        'minimum_gap': min_lo <= minimum_gap <= min_hi,
    }
    for key, (lo, hi) in cfg['diagnostic_intervals'].items():
        checks[f'count_{key}'] = lo <= diagnostics[key] <= hi
    return {
        'checks': checks, 'upstream_grid': upper_cmp, 'independent_grid': independent_cmp,
        'region_counts': regions, 'diagnostics': diagnostics, 'max_midpoint_error_cm': midpoint_error,
        'max_chord_error_cm': chord_error, 'minimum_gap_cm': minimum_gap,
        'minimum_gap_index': int(np.argmin(gap)), 'first_pharyngeal_gap_cm': float(gap[0]),
        'front_gaps_cm': gap[candidate[:, 0] == 3].tolist(),
    }


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
    sources = [path, sagittal.PROBE, Path(__file__).resolve(), Path(sagittal.__file__), Path(shared.__file__),
               WORKSPACE / 'tools/upstream_baseline.py', *shared.candidate_sources()]
    details = {'upstream_revision': revision, 'case_id': case['id']}

    def measure_run(artifacts, execute):
        return measure(case, path, artifacts, execute)

    return shared.record_measurement(args.run_id, path, sources, details, measure_run, command='grid')


if __name__ == '__main__':
    raise SystemExit(main())
