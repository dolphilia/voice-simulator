"""FK61_01の測定線43で輪郭線分と光線交差を切り分ける。"""

import argparse
from fractions import Fraction
from itertools import combinations
import os
from pathlib import Path
import subprocess

import measure_tsp_fk61_lip_front_origin as front
import tsp_fk61_ray43_observation as observer
from measure_tsp_fk61_lip_front_radiation import read_trial
from measure_tsp_fk61_lip_onset import pcm_digest


area, tsp = front.area, front.tsp
CASE = front.WORKSPACE / 'cases/tsp-fk61-ray43-intersection.json'
MAX_CROSSINGS = 64


def subtract(a, b):
    return [a[0] - b[0], a[1] - b[1]]


def cross(a, b):
    return a[0] * b[1] - a[1] * b[0]


def point_at(origin, direction, distance):
    return [q + v * distance for q, v in zip(origin, direction, strict=True)]


def intersection(ray, endpoints):
    origin, direction = ray[:2], ray[2:4]
    a, b = endpoints
    qa, qb = subtract(a, origin), subtract(b, origin)
    side_a, side_b = cross(direction, qa), cross(direction, qb)
    if (side_a >= 0.0) == (side_b >= 0.0):
        return None
    edge = subtract(b, a)
    determinant = cross(direction, edge)
    if abs(determinant) < 1e-15:
        return None
    numerator = cross(qa, edge)
    return {'relative_a': qa, 'relative_b': qb, 'edge': edge, 'numerator': numerator,
            'determinant': determinant, 'distance': numerator / determinant}


def intersections(ray, contour, limit):
    ordered = []
    for i, pair in enumerate(zip(contour, contour[1:])):
        hit = intersection(ray, pair)
        if hit is None or not 0 <= hit['distance'] <= limit:
            continue
        ordered.append(hit | {'index': i, 'endpoints': list(pair)})
        if len(ordered) == MAX_CROSSINGS:
            break
    return ordered


def anatomical_segment(probe, pair):
    for name in ('lower_teeth', 'lower_lip'):
        contour = probe[name]
        for index, endpoints in enumerate(zip(contour, contour[1:])):
            if list(endpoints) == pair:
                return {'part': name, 'index': index}
    return {'part': 'inner', 'index': None}


def replay(row, site):
    probe = row['ray43']
    ray = probe['ray']
    origin, direction = ray[:2], ray[2:4]
    scale = row['area_inputs'][0]
    upper_hits = intersections(ray, probe['outer'], ray[4])
    if direction != [0.0, 1.0] or not upper_hits:
        raise ValueError(f'前方の垂直な測定線を同定できません ({site})')
    roof = min(upper_hits, key=lambda hit: hit['distance'])
    limit = roof['distance'] + 1.5 * scale
    lower_hits = intersections(ray, probe['inner'], limit)
    floor = max((hit for hit in lower_hits if hit['distance'] < limit), key=lambda hit: hit['distance'], default=None)
    if floor is None:
        raise ValueError(f'対象の測定線の下側交差がありません ({site})')
    chosen = {'lower': floor, 'upper': roof}
    d0, d1 = floor['distance'], roof['distance']
    lower = point_at(origin, direction, min(d0, d1))
    upper = point_at(origin, direction, d1)
    gap = max(0.0, d1 - d0)
    observed = row['grid'][site]
    return {'ray': ray[:5], 'chosen': chosen, 'lower_part': anatomical_segment(probe, floor['endpoints']),
            'lower_crossings': len(lower_hits), 'upper_crossings': len(upper_hits), 'inner_xy_cm': lower,
            'outer_xy_cm': upper, 'raw_gap_cm': gap, 'contact_gap_cm': observed[4], 'native_area_cm2': observed[1],
            'distance_exact_match': [d0, d1] == ray[5:],
            'before_contact_exact_match': (lower, upper, gap) == (observed[5:7], observed[7:9], observed[3])}


def exact_vertical_y(endpoints, x):
    a, b = ([Fraction(value) for value in point] for point in endpoints)
    fraction = (Fraction(x) - a[0]) / (b[0] - a[0])
    return float(a[1] + fraction * (b[1] - a[1]))


def lower_lip_controls(row):
    # この姿勢では、輪郭の最初と最後に制御点の両端がそのまま出る。
    base, *_, edge = row['ray43']['lower_lip']
    scale = row['area_inputs'][0]
    protrusion = min(1.6, max(-0.2, row['lip_controls'][1])) * scale
    return [base, [base[0] + (0.25 * scale + protrusion * 0.3), base[1] - 0.05 * scale],
            [edge[0] - 0.3 * scale, edge[1] - 0.12 * scale], edge]


def curve_point(points, t, bernstein):
    if bernstein:
        u = 1.0 - t
        weights = [u * u * u, 3.0 * u * u * t, 3.0 * u * t * t, t * t * t]
        return [area.sum_ordered(weight * coordinate for weight, coordinate in zip(weights, axis, strict=True))
                for axis in zip(*points, strict=True)]
    layer = points
    for _ in range(3):
        layer = [[a + (b - a) * t for a, b in zip(left, right, strict=True)] for left, right in zip(layer, layer[1:])]
    return layer[0]


def curve_comparison(rows, index):
    reports = {}
    for mode, row in rows.items():
        seen = replay(row, index)
        part = seen['lower_part']
        control = lower_lip_controls(row)
        intervals = len(row['ray43']['lower_lip']) - 1
        if part['part'] != 'lower_lip':
            raise ValueError('ベジェ曲線の比較で下唇の線分を確認できません')
        j = part['index']
        terms = {}
        for method, weighted in (('bernstein', True), ('de_casteljau', False)):
            points = [curve_point(control, i / intervals, weighted) for i in (j, j + 1)]
            hit = intersection(seen['ray'], points)
            if hit is None:
                raise ValueError('再計算した下唇の線分で交差を確認できません')
            distance = hit['distance']
            grid = [g.copy() for g in row['grid']]
            grid[index][4] = seen['chosen']['upper']['distance'] - distance
            grid[index][1] = area.front_area(grid[index], row['area_inputs'])[0]
            terms[method] = {'endpoints': points, 'distance_cm': distance,
                             'inner_xy_cm': point_at(seen['ray'][:2], seen['ray'][2:4], distance),
                             'matches_native_endpoints': points == seen['chosen']['lower']['endpoints'],
                             'ray_area_cm2': grid[index][1],
                             'cell_cm2': area.resample(row, grid, index_from_end=2)['cell']}
        reports[mode] = {'controls': control, 'methods': terms}
    return reports


def swaps(upper, trial, trial_row, index, from_end):
    terms = ('ray', 'endpoint_a', 'endpoint_b')
    trial_floor = trial['chosen']['lower']
    upper_floor = upper['chosen']['lower']
    trial_roof = trial['chosen']['upper']
    rows = []
    for size in range(len(terms) + 1):
        for pick in combinations(terms, size):
            ray = (upper if 'ray' in pick else trial)['ray']
            endpoints = [(upper_floor if term in pick else trial_floor)['endpoints'][i]
                         for i, term in enumerate(terms[1:])]
            hit = intersection(ray, endpoints)
            roof_hit = intersection(ray, trial_roof['endpoints'])
            if hit is None or roof_hit is None:
                raise ValueError('線分または光線を交換した条件で交差を確認できません')
            t = hit['distance']
            roof_t = roof_hit['distance']
            xy = point_at(ray[:2], ray[2:4], min(t, roof_t))
            gap = max(0.0, roof_t - t)
            grid = [g.copy() for g in trial_row['grid']]
            grid[index][4] = gap
            area_value, weight = area.front_area(grid[index], trial_row['area_inputs'])
            grid[index][1] = area_value
            cell = area.resample(trial_row, grid, index_from_end=from_end)['cell']
            rows.append({'terms': list(pick), 'distance_cm': t, 'inner_xy_cm': xy, 'raw_gap_cm': gap,
                         'exact_vertical_y_cm': exact_vertical_y(endpoints, ray[0]), 'front_weight': weight,
                         'area_cm2': area_value, 'cell_cm2': cell})
    return rows


def analyze(study, snapshots, prior, proof, prior_proof, trial_pcm):
    cfg = study['measurement']
    index, focus = (cfg[key] for key in ('grid_index', 'focus_frame'))
    comparisons = {str(f): {mode: replay(snapshots[mode][f], index) for mode in front.MODES}
                   for f in cfg['completed_frames']}
    a, b = (comparisons[str(focus)][mode] for mode in ('upstream', 'trial'))
    upper = snapshots['upstream'][focus]
    trial = snapshots['trial'][focus]
    interventions = swaps(a, b, trial, index, cfg['oral_cells_from_end'])
    own, exchanged = (next(row for row in interventions if row['terms'] == keys)
                      for keys in ([], ['endpoint_a', 'endpoint_b']))
    stage_names = ('endpoints', 'relative_a', 'relative_b', 'edge', 'determinant', 'numerator', 'distance')
    floor = dict(zip(('upstream', 'trial'), (a['chosen']['lower'], b['chosen']['lower']), strict=True))
    preserved = all({k: v for k, v in snapshots[mode][f].items() if k != 'ray43'} == prior[mode][f]
                    for mode in front.MODES for f in cfg['completed_frames'])
    return {
        'checks': {
            'normal_probe_and_archived_pcm_match': proof == prior_proof
                and all(proof[mode]['ordinary_equal'] for mode in front.MODES)
                and proof['trial']['probe'] == pcm_digest(trial_pcm),
            'prior_grid_and_node42_snapshots_preserved': preserved,
            'ray_polyline_and_native_distance_replayed': all(
                report['distance_exact_match'] and report['before_contact_exact_match']
                for frame in comparisons.values() for report in frame.values()),
            'area_law_and_resampling_replayed': all(
                area.front_area(snapshots[mode][focus]['grid'][index], snapshots[mode][focus]['area_inputs'])[0]
                == comparisons[str(focus)][mode]['native_area_cm2'] for mode in front.MODES)
                and own['cell_cm2'] == trial['before_lip']['raw'],
            'all_intersection_interventions_retained': len(interventions) == 8,
        },
        'predictions': {
            'same_rays_and_anatomical_segment': a['ray'] == b['ray'] and a['lower_part'] == b['lower_part'],
            'lower_endpoints_recover_native_hit': exchanged['distance_cm'] == floor['upstream']['distance']
                and exchanged['inner_xy_cm'] == a['inner_xy_cm'] and exchanged['raw_gap_cm'] == a['raw_gap_cm'],
            'difference_before_contact_and_resampling': own['raw_gap_cm'] == b['contact_gap_cm']
                and a['raw_gap_cm'] == a['contact_gap_cm'] and exchanged['area_cm2'] == a['native_area_cm2']
                and exchanged['cell_cm2'] == upper['before_lip']['raw'],
        },
        'frames': comparisons, 'focus_frame': focus,
        'lower_first_divergent_term': next((key for key in stage_names if floor['upstream'][key] != floor['trial'][key]), None),
        'interventions': interventions,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    ws, upper = front.WORKSPACE, front.UPSTREAM
    study = tsp.read(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=upper, text=True).strip()
    if revision != study['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=upper):
        parser.error('変更のない固定上流版が必要です')
    if os.environ.get('CHIMERA_RUN_STORAGE') != 'rtl9210b':
        parser.error('試験ビルドにCHIMERA_RUN_STORAGE=rtl9210bを指定してください')
    area_run, matched = (tsp.open_run(study[key], revision) for key in ('area', 'matched'))
    config, config_path = front.saved_case(matched, front.CONFIG)
    uid = study['measurement']['recording_id']
    spec = tsp.verified_path(matched, f'artifacts/{uid}/matched-case.json')
    pcm_input = tsp.verified_path(matched, 'artifacts/matched-pcm.npz')
    trial_pcm = tsp.verified_path(area_run, 'artifacts/trial-pcm.npz')
    proof = tsp.verified_path(area_run, 'artifacts/pcm-digests.json')
    previous = {mode: tsp.verified_path(area_run, f'artifacts/{mode}.jsonl') for mode in front.MODES}
    inputs = [CASE, Path(__file__).resolve(), Path(observer.__file__), Path(front.__file__), Path(area.__file__),
              config_path, spec, pcm_input, trial_pcm, proof, *previous.values(),
              *(run[0] / 'manifest.json' for run in (area_run, matched)), *front.candidate_sources(),
              front.EMBEDDED_DICTIONARY, front.CLI_DICT, front.DICT, front.LOCAL, front.PROBE, front.TRACE_TOOL,
              front.RAMP_TEST, area.observer.SNAPSHOT,
              *(ws / 'tools' / name for name in ('tsp_fk61_node42_area_observation.py', 'tsp_fk61_lip_front_observation.py',
                 'tsp_fk61_lip_area_observation.py', 'tsp_fk61_lip_observation.py', 'measure_tsp_fk61_lip_onset.py',
                 'measure_tsp_fk61_lip_front_radiation.py', 'measure_tsp_fk61_pcm_first_difference.py',
                 'measure_uniform_tube.py')),
              *(upper / name for name in ('Cargo.lock', 'crates/chimera/src/anatomy/human.rs',
                 'crates/chimera/src/anatomy/geom.rs', 'crates/chimera/src/voice/human_airway.rs',
                 'crates/chimera/src/voice/human_voice.rs', 'crates/chimera/tests/geometry_continuity.rs'))]

    def measure(out, execute):
        archived = front.archived_pcm(pcm_input, uid)
        snapshots, current_proof = front.capture(study, spec, config, archived, out, execute, observation=observer,
                                                 scratch_prefix='fk61-ray43-')
        prior = {mode: area.read_snapshots(path, study['measurement']['completed_frames'])
                 for mode, path in previous.items()}
        return analyze(study, snapshots, prior, current_proof, tsp.read(proof), read_trial(trial_pcm))

    info = {'case_id': study['id'], 'case_revision': study['revision'], 'upstream_revision': revision}
    return front.record_measurement(args.run_id, CASE, inputs, info, measure, command=None, input_root=ws.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
