"""格子上の断面積と中心線を、固定上流と独立計算に照合する。"""

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


CASES = ('area-neutral', 'area-wide-lips', 'area-compressed-lips', 'area-closed-roof',
         'area-raised-tip', 'area-lateral')
COLUMNS = ',gap_cm,area_cm2,s_cm'
METRICS_CM = ('length_cm', 'pharynx_length_cm', 'teeth_s_cm', 'lip_s_cm')


def independent_profile(parts, raw, pose, *, scale=1.0, epilarynx_cm=2.4, full_lip_width=4.6):
    regions = raw[:, 0]
    mids = raw[:, 5:7]
    x = mids[:, 0]
    gap = raw[:, -1]
    tip = parts['tip'][0]
    incisor_x = parts['palate'][-1, 0]
    lip_width = (1.1 + (full_lip_width - 1.1) * np.clip(pose['lip_spread'], 0, 1)) * scale
    ahead = grid.smoothstep((x - tip[0]) / (0.4 * scale))
    lip_weight = np.clip((x - incisor_x) / (0.45 * scale), 0, 1)
    power = np.power(gap, 1.4)
    dental = 2 * power
    ellipse = np.pi * gap * lip_width / 4
    initial = np.select(
        [regions == 1, regions == 2, regions == 3],
        [dental, (2.6 - ahead) * power, (1 - lip_weight) * dental + lip_weight * ellipse],
    )

    limited = initial.copy()
    for i in range(1, len(limited) - 1):
        limited[i] = min(limited[i], 1.35 * max(limited[i - 1], limited[i + 1]))
    lateral = max(0, pose.get('lateral', 0))
    selected = (regions >= 2) & (np.sum((mids - tip)**2, axis=1) < (1.4 * scale)**2)
    area = np.where(selected, np.maximum(limited, 0.35 * lateral * scale**2), limited)
    distance = epilarynx_cm + np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(mids, axis=0), axis=1))]
    oral = np.flatnonzero(regions == 2)
    front = np.flatnonzero(regions == 3)
    split = int(oral[0]) if oral.size else -1
    summary = {
        'length_cm': float(distance[-1]), 'lip_s_cm': float(distance[-1]),
        'pharynx_length_cm': float(distance[split if split >= 0 else 12]),
        'teeth_s_cm': float(distance[front[0] if front.size else -1]),
        'lip_area_cm2': float(area[-1]), 'split_index': split,
    }
    return area, distance, summary, initial, limited, ahead


def upper_metadata(path):
    with path.open(newline='') as file:
        row, = csv.DictReader(file)
    return {name: float(value) for name, value in row.items()}


def compare_metadata(candidate, reference, cm_tol, cm2_tol):
    dist_errors = {key: abs(candidate[key] - reference[key]) for key in METRICS_CM}
    area_error = abs(candidate['lip_area_cm2'] - reference['lip_area_cm2'])
    split_same = candidate['split_index'] == reference['split_index']
    return {
        'distance_errors_cm': dist_errors, 'lip_area_error_cm2': area_error, 'split_index_equal': split_same,
        'status': max(dist_errors.values()) < cm_tol and area_error < cm2_tol and split_same,
    }


def measure(case, path, artifacts, execute):
    upper = grid.read_grid(sagittal.capture_upstream(case, artifacts, execute, mode='--area'), columns=COLUMNS)
    candidate = grid.read_grid(artifacts / 'trace.csv', columns=COLUMNS)
    cfg = case['measurement']['area']
    cm_tol, cm2_tol = cfg['point_and_distance_error_lt_cm'], cfg['area_error_lt_cm2']
    upstream_rays = grid.compare_grid(candidate[:, :-3], upper[:, :-3], cm_tol)
    if candidate.shape != upper.shape:
        return {'checks': {'upstream_grid': False}, 'upstream_grid': upstream_rays}

    contours, contact = artifacts / 'contours.csv', artifacts / 'contact-grid.csv'
    prefix = ['cargo', 'run', '--locked', '--release', '-p', 'vocal-cli', '--']
    execute([*prefix, 'geometry', str(path), str(contours)])
    execute([*prefix, 'contact', str(path), str(contact)])
    raw = grid.read_grid(contact, columns=',gap_cm')
    area, distance, expected, initial, limited, ahead = independent_profile(
        sagittal.read_points(contours), raw, case['posture'])
    np.savetxt(artifacts / 'independent-area.csv',
               np.column_stack((np.arange(len(raw)), initial, limited, area, distance)),
               delimiter=',', header='index,initial_area_cm2,limited_area_cm2,area_cm2,s_cm',
               fmt=('%d', '%.17g', '%.17g', '%.17g', '%.17g'), comments='')
    metadata = json.loads((artifacts / 'settings.json').read_text())['area']
    upper_data = upper_metadata(artifacts / 'upstream-area-metrics.csv')
    upper_meta_cmp = compare_metadata(metadata, upper_data, cm_tol, cm2_tol)
    independent_meta_cmp = compare_metadata(metadata, expected, cm_tol, cm2_tol)
    upstream_gaps = float(np.max(np.abs(candidate[:, -3] - upper[:, -3])))
    upstream_area = np.abs(candidate[:, -2] - upper[:, -2])
    independent_area = np.abs(candidate[:, -2] - area)
    upstream_s = np.abs(candidate[:, -1] - upper[:, -1])
    independent_s = np.abs(candidate[:, -1] - distance)
    first_bad = np.flatnonzero((upstream_area >= cm2_tol) | (independent_area >= cm2_tol)
                               | (upstream_s >= cm_tol) | (independent_s >= cm_tol))
    regions = [int(np.count_nonzero(candidate[:, 0] == k)) for k in (1, 2, 3)]
    minimum = float(np.min(candidate[:, -2]))
    clamps = np.flatnonzero(initial - limited > cm2_tol).tolist()
    lateral = np.flatnonzero(area - limited > cm2_tol).tolist()
    zeros = np.flatnonzero(candidate[:, -2] == 0).tolist()
    n_ahead = int(np.count_nonzero((candidate[:, 0] == 2) & (ahead > 0)))
    lip, length = metadata['lip_area_cm2'], metadata['length_cm']
    length_lo, length_hi = cfg['profile_length_interval_cm']
    minimum_lo, minimum_hi = cfg['minimum_area_interval_cm2']
    lip_lo, lip_hi = cfg['lip_area_interval_cm2']
    checks = {
        'upstream_grid': upstream_rays['status'] and upstream_gaps < cm_tol,
        'contact_grid_reused': np.array_equal(candidate[:, :-2], raw),
        'registered_region_counts': regions == cfg['region_counts'],
        'upstream_area': bool(upstream_area.max() < cm2_tol),
        'independent_area': bool(independent_area.max() < cm2_tol),
        'upstream_centreline': bool(upstream_s.max() < cm_tol) and upper_meta_cmp['status'],
        'independent_centreline': bool(independent_s.max() < cm_tol) and independent_meta_cmp['status'],
        'centreline_starts_at_epilarynx_and_increases': bool(candidate[0, -1] == 2.4 and np.all(np.diff(candidate[:, -1]) > 0)),
        'total_length': length_lo <= length <= length_hi,
        'minimum_area': minimum_lo <= minimum <= minimum_hi,
        'lip_area': lip_lo <= lip <= lip_hi,
        'zero_area_indices': zeros == cfg['zero_area_indices'],
        'oral_ahead_weights': n_ahead == cfg['oral_ahead_weight_count'],
        'isolated_area_spikes': clamps == cfg['clamped_indices'],
        'lateral_area_floor': lateral == cfg['lateral_changed_indices'],
    }
    return {
        'checks': checks, 'region_counts': regions, 'profile': metadata,
        'upstream_grid': upstream_rays, 'upstream_max_gap_error_cm': upstream_gaps,
        'upstream_max_area_error_cm2': float(upstream_area.max()),
        'independent_max_area_error_cm2': float(independent_area.max()),
        'upstream_max_sample_distance_error_cm': float(upstream_s.max()),
        'independent_max_sample_distance_error_cm': float(independent_s.max()),
        'upstream_profile_metrics': upper_meta_cmp, 'independent_profile_metrics': independent_meta_cmp,
        'first_sample_outside_tolerance': int(first_bad[0]) if first_bad.size else None,
        'minimum_area_cm2': minimum, 'zero_area_indices': zeros, 'oral_ahead_weight_count': n_ahead,
        'clamped_indices': clamps, 'lateral_changed_indices': lateral,
        'final_gap_cm': float(candidate[-1, -3]),
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

    def measure_run(artifacts, execute):
        return measure(case, path, artifacts, execute)

    sources = [path, sagittal.PROBE, Path(__file__).resolve(), Path(sagittal.__file__),
               Path(grid.__file__), Path(shared.__file__), WORKSPACE / 'tools/upstream_baseline.py',
               *shared.candidate_sources()]
    details = {'upstream_revision': revision, 'case_id': case['id']}
    return shared.record_measurement(args.run_id, path, sources, details, measure_run, command='area')


if __name__ == '__main__':
    raise SystemExit(main())
