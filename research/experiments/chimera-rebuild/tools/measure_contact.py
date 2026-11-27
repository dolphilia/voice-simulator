"""舌・口蓋と唇の接触による補正を上流と独立計算に照合する。"""

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


CASES = ('contact-neutral', 'contact-raised-tip', 'contact-closed-roof',
         'contact-compressed-lips', 'contact-tuck-mid', 'contact-tuck-handover')


def project_segments(point, line):
    edges = np.diff(line, axis=0)
    offset = point - line[:-1]
    squares = np.sum(edges**2, axis=1)
    valid = squares >= 1e-12
    numerator = np.sum(edges * offset, axis=1)
    u = np.clip(np.divide(numerator, squares, out=np.zeros_like(squares), where=valid), 0, 1)
    distance = np.linalg.norm(offset - u[:, None] * edges, axis=1)
    return u, distance, valid


def signed_distance(point, tongue):
    _, distance, _ = project_segments(point, tongue)
    a, b = tongue[:-1], tongue[1:]
    crosses = (a[:, 1] > point[1]) != (b[:, 1] > point[1])
    a, b = a[crosses], b[crosses]
    x = a[:, 0] + (point[1] - a[:, 1]) * (b[:, 0] - a[:, 0]) / (b[:, 1] - a[:, 1])
    sign = -1 if np.count_nonzero(point[0] < x) % 2 else 1
    return sign * float(distance.min())


def fade(low, high, value):
    return 1 - grid.smoothstep((value - low) / (high - low))


def independent_contact(parts, raw, pose):
    n = len(parts['outer']) - 7
    m = n - (len(parts['palate']) - 1) - len(parts['velum']) // 2
    roof = parts['outer'][m:n]
    tongue = parts['tongue']
    closed_tongue = np.vstack((tongue, tongue[0]))
    edges = np.diff(roof, axis=0)
    lengths = np.linalg.norm(edges, axis=1)
    cumulative = np.r_[0.0, np.cumsum(lengths)]

    def on_roof(point):
        ratios, distances, valid = project_segments(point, roof)
        i = int(np.argmin(np.where(valid, distances, np.inf)))
        dx, dy = edges[i]
        side = dx * (point[1] - roof[i, 1]) - dy * (point[0] - roof[i, 0])
        return ((1 if side < 0 else -1) * distances[i],
                cumulative[i] + ratios[i] * lengths[i], np.array([dy, -dx]) / lengths[i])

    # 輪郭CSVで、舌体の32点と舌尖付近の刃・裏側の点を選ぶ。
    body = min(map(on_roof, tongue[8:40]), key=lambda result: result[0])
    tip = min(map(on_roof, tongue[41:48]), key=lambda result: result[0])
    half = 0.1 * (1 + fade(-0.06, 0.0, min(body[0], tip[0])))
    corrected = []
    for _, _, _, x, y, *_mid, ray in raw:
        point = np.array([x, y])
        distance, s, _ = on_roof(point)
        influence = fade(0.15, 0.25, abs(distance))
        d = signed_distance(point, closed_tongue)
        if influence > 0 and d <= 0.6 + half + abs(distance):
            samples = s + half * np.array([-1.0, -0.5, 0.5, 1.0])
            nearby = np.column_stack([np.interp(samples, cumulative, values) for values in roof.T])
            d = min(d, *(signed_distance(q, closed_tongue) for q in nearby))
        surface = max(0, d)
        cap = influence * fade(0.45, 0.6, d)
        blend = influence * fade(0.15, 0.6, d)
        capped = (1 - cap) * ray + cap * min(ray, surface)
        corrected.append((1 - blend) * capped + blend * surface)
    corrected = np.array(corrected)

    lab = grid.smoothstep(pose['labiodental'] / 0.5)
    front = (raw[:, 0] == 3) & (raw[:, 5] >= parts['palate'][-1, 0])
    if lab < 1:
        edge_x = min(parts['upper_lip'][6, 0], parts['lower_lip'][6, 0])
        depth = np.maximum(0, edge_x - raw[front, 5])
        aperture = pose['lip_aperture_cm'] + 0.3 * lab / (1 - lab)
        corrected[front] = np.minimum(corrected[front], np.maximum(0, aperture + depth**2 / 1.2))

    return corrected, np.array([[tip[0], *tip[2]], [body[0], *body[2]]])


def upper_metrics(path):
    with path.open(newline='') as file:
        rows = {row['part']: [float(row[k]) for k in ('distance_cm', 'normal_x', 'normal_y')]
                for row in csv.DictReader(file)}
    return np.array([rows['tip'], rows['body']])


def measure(case, path, artifacts, execute):
    upper = grid.read_grid(sagittal.capture_upstream(case, artifacts, execute, mode='--contact'), columns=',gap_cm')
    candidate = grid.read_grid(artifacts / 'trace.csv', columns=',gap_cm')
    cfg = case['measurement']['contact']
    tolerance = cfg['coordinate_max_error_lt_cm']
    upper_raw = grid.compare_grid(candidate[:, :-1], upper[:, :-1], tolerance)
    if candidate.shape != upper.shape:
        return {'checks': {'upstream_raw_grid': False}, 'upstream_raw_grid': upper_raw}

    contours = artifacts / 'contours.csv'
    raw_path = artifacts / 'raw-grid.csv'
    prefix = ['cargo', 'run', '--locked', '--release', '-p', 'vocal-cli', '--']
    execute([*prefix, 'geometry', str(path), str(contours)])
    execute([*prefix, 'grid', str(path), str(raw_path)])
    raw = grid.read_grid(raw_path)
    expected_gaps, expected_metrics = independent_contact(sagittal.read_points(contours), raw, case['posture'])
    np.savetxt(artifacts / 'independent-gaps.csv', np.column_stack((np.arange(len(raw)), expected_gaps)),
               delimiter=',', fmt=('%d', '%.17g'), header='index,gap_cm', comments='')
    metrics = json.loads((artifacts / 'settings.json').read_text())['contact']
    observables = np.array([[metrics[k]['distance_cm'], *metrics[k]['normal']] for k in ('tip','body')])
    upper_contact = upper_metrics(artifacts / 'upstream-contact-metrics.csv')
    distance_error = float(np.max(np.abs(observables[:, 0] - upper_contact[:, 0])))
    normal_error = float(np.max(np.abs(observables[:, 1:] - upper_contact[:, 1:])))
    independent_distance_error = float(np.max(np.abs(observables[:, 0] - expected_metrics[:, 0])))
    independent_normal_error = float(np.max(np.abs(observables[:, 1:] - expected_metrics[:, 1:])))
    normal_limit = cfg['normal_max_error_lt']
    gap = candidate[:, -1]
    upper_gap_error = np.abs(gap - upper[:, -1])
    independent_gap_error = np.abs(gap - expected_gaps)
    front = candidate[:, 0] == 3
    region_counts = [int(np.count_nonzero(candidate[:, 0] == region)) for region in (1, 2, 3)]
    reduction = candidate[:, -2] - gap
    closed = np.flatnonzero((gap <= cfg['closure_threshold_cm']) & (candidate[:, -2] > cfg['closure_threshold_cm']))

    def within(name, value):
        low, high = cfg[name]
        return bool(low <= value <= high)

    checks = {
        'registered_grid_counts': region_counts == cfg['region_counts'],
        'upstream_raw_grid': upper_raw['status'],
        'raw_grid_unchanged': np.array_equal(candidate[:, :-1], raw),
        'upstream_corrected_gap': bool(np.max(upper_gap_error) < tolerance),
        'independent_corrected_gap': bool(np.max(independent_gap_error) < tolerance),
        'upstream_roof_contacts': distance_error < tolerance and normal_error < normal_limit,
        'independent_roof_contacts': independent_distance_error < tolerance and independent_normal_error < normal_limit,
        'unit_contact_normals': bool(np.max(np.abs(np.linalg.norm(observables[:, 1:], axis=1) - 1)) < normal_limit),
        'minimum_corrected_gap': bool(np.all(gap >= 0)) and within('minimum_corrected_gap_interval_cm', np.min(gap)),
        'roof_side_reduction': within('maximum_nonfront_reduction_interval_cm', np.max(reduction[~front])),
        'lip_reduction': within('maximum_lip_reduction_interval_cm', np.max(reduction[front])),
        'expected_new_closures': closed.size == cfg['newly_closed_count'],
        'tip_distance': within('tip_distance_interval_cm', observables[0, 0]),
        'body_distance': within('body_distance_interval_cm', observables[1, 0]),
    }
    first_gap = np.flatnonzero((upper_gap_error >= tolerance) | (independent_gap_error >= tolerance))
    return {
        'checks': checks, 'upstream_raw_grid': upper_raw, 'region_counts': region_counts,
        'upstream_max_gap_error_cm': float(np.max(upper_gap_error)),
        'independent_max_gap_error_cm': float(np.max(independent_gap_error)),
        'first_corrected_index_over_tolerance': int(first_gap[0]) if first_gap.size else None,
        'upstream_contact_errors': {'distance_cm': distance_error, 'normal': normal_error},
        'independent_contact_errors': {'distance_cm': independent_distance_error, 'normal': independent_normal_error},
        'minimum_corrected_gap_cm': float(np.min(gap)),
        'maximum_nonfront_reduction_cm': float(np.max(reduction[~front])),
        'maximum_lip_reduction_cm': float(np.max(reduction[front])),
        'newly_closed_indices': closed.tolist(),
        'raw_front_gaps_cm': candidate[front, -2].tolist(),
        'corrected_front_gaps_cm': gap[front].tolist(),
        'roof_contacts': metrics,
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
    sources = [path, sagittal.PROBE, Path(__file__).resolve(), Path(sagittal.__file__),
               Path(grid.__file__), Path(shared.__file__), WORKSPACE / 'tools/upstream_baseline.py',
               *shared.candidate_sources()]
    details = {'upstream_revision': revision, 'case_id': case['id']}

    def measure_run(artifacts, execute):
        return measure(case, path, artifacts, execute)

    return shared.record_measurement(args.run_id, path, sources, details, measure_run, command='contact')


if __name__ == '__main__':
    raise SystemExit(main())
