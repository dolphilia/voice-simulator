"""固定 /i/ の中心線距離を、座標、区間のノルムと加算の順に照合する。"""

import argparse
import csv
from decimal import Decimal, localcontext
import json
import math
from pathlib import Path
import struct
import subprocess

import measure_sagittal as sagittal
import measure_uniform_tube as shared
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/fixed-voice-centerline-i.json'
MIDS = ('mid_x_cm', 'mid_y_cm')
ENDPOINTS = ('inner_x_cm', 'inner_y_cm', 'outer_x_cm', 'outer_y_cm')
DISTANCE = 's_cm'
UPSTREAM_PATHS = (
    'crates/chimera/src/anatomy/human.rs', 'crates/chimera/src/anatomy/geom.rs',
    'crates/chimera/src/math.rs', 'crates/chimera/src/voice/human_airway.rs',
    'crates/chimera/tests/golden_geometry.rs', 'crates/chimera/tests/geometry_continuity.rs', 'Cargo.lock',
)


def bits(number):
    return struct.pack('<d', number)


def same(first, second):
    return bits(first) == bits(second)


def csv_rows(path):
    with path.open(newline='') as source:
        return list(csv.DictReader(source))


def read_area(path):
    rows = [{name: float(value) for name, value in row.items()} for row in csv_rows(path)]
    if not rows or any(row['index'] != index or not all(map(math.isfinite, row.values()))
                       for index, row in enumerate(rows)):
        raise ValueError(f'測定値の連続性または有限性が不正です ({path.name})')
    return rows


def pair_report(candidate, upper):
    return {'candidate': candidate, 'upstream': upper, 'delta': candidate - upper,
            'bit_equal': same(candidate, upper)}


def first_difference(first, second):
    return next((index for index, (a, b) in enumerate(zip(first, second, strict=True))
                 if not same(a, b)), None)


def recumulate(distances, initial):
    result = [initial]
    for length in distances:
        result.append(result[-1] + length)
    return result


def decimal_arc(points, initial):
    with localcontext() as ctx:
        ctx.prec = 100
        coords = [[Decimal.from_float(value) for value in p] for p in points]
        total = Decimal.from_float(initial)
        result = [initial]
        for p, q in zip(coords[:-1], coords[1:], strict=True):
            dx, dy = (b - a for a, b in zip(p, q, strict=True))
            total += (dx * dx + dy * dy).sqrt()
            result.append(float(total))
        return result


def segment_distances(points, probe, artifacts, execute):
    path = artifacts / 'segment-coordinates.txt'
    samples = len(next(iter(points.values())))
    with path.open('w') as out:
        for coordinates in points.values():
            for first, second in zip(coordinates[:-1], coordinates[1:], strict=True):
                out.write(' '.join(map(str, (*first, *second))) + '\n')
    result = artifacts / 'segment-lengths.txt'
    execute([str(probe), '--segment-lengths', str(path)], cwd=UPSTREAM, stdout=result)
    distances = list(map(float, result.read_text().splitlines()))
    stride = samples - 1
    if len(distances) != stride * len(points) or not all(math.isfinite(x) and x > 0 for x in distances):
        raise ValueError('距離の点数・有限性・正値が設定と一致しません')
    return {name: distances[index * stride:(index + 1) * stride] for index, name in enumerate(points)}


def save_comparison(path, native, upper, segments, rebuilt):
    with path.open('w', newline='') as out:
        writer = csv.writer(out)
        writer.writerow(['index', 'region', 'candidate_mid_x_cm', 'candidate_mid_y_cm', 'upstream_mid_x_cm',
                         'upstream_mid_y_cm', 'candidate_distance_cm', 'upstream_distance_cm',
                         'candidate_s_cm', 'upstream_s_cm', 'x_swapped_s_cm', 'y_swapped_s_cm'])
        for i, (a, b) in enumerate(zip(native, upper, strict=True)):
            writer.writerow([i, int(a['region']), *(a[k] for k in MIDS), *(b[k] for k in MIDS),
                             segments['candidate'][i-1] if i else 0.0,
                             segments['upstream'][i-1] if i else 0.0, a[DISTANCE], b[DISTANCE],
                             rebuilt['upstream-x'][i], rebuilt['upstream-y'][i]])


def horizontal_crossings(points, y, origin, limit):
    hits = []
    for index, ((ax, ay), (bx, by)) in enumerate(zip(points[:-1], points[1:], strict=True)):
        if (y - ay >= 0.0) == (y - by >= 0.0):
            continue
        dx, dy = bx - ax, by - ay
        if abs(dy) < 1e-15:
            continue
        distance = ((ax - origin) * dy - (ay - y) * dx) / -dy
        if 0 <= distance <= limit:
            hits.append((distance, index))
    return hits


def rear_ray(cfg, height, inner, outer):
    origin = cfg['origin_x_cm']
    roof, roof_segment = min(horizontal_crossings(outer, height, origin, cfg['outer_limit_cm']))
    limit = roof + cfg['inner_limit_extra_cm']
    floor, floor_segment = max((hit for hit in horizontal_crossings(inner, height, origin, limit)
                                if hit[0] < limit))
    left, right = origin - min(floor, roof), origin - roof
    return {'inner_x_cm': left, 'outer_x_cm': right, 'mid_x_cm': left + (right - left) * 0.5,
            'inner_segment': floor_segment, 'outer_segment': roof_segment}


def determine_rear_points(cfg, pose, native, upper, artifacts):
    contours = {}
    for name in ('candidate', 'upstream'):
        parts = sagittal.read_points(artifacts / f'{name}-contours.csv')
        contours[name] = {key: [tuple(map(float, row)) for row in parts[key]]
                          for key in ('inner', 'outer', 'epiglottis')}
    own, ref = contours['candidate'], contours['upstream']
    ax, ay = own['inner'][0]
    _, upper_y = ref['inner'][0]
    inner_base = [(ax, upper_y), *own['inner'][1:]]
    groups = {
        'candidate': (own['inner'], own['outer']),
        'upstream': (ref['inner'], ref['outer']),
        'epiglottis-base-y': (inner_base, own['outer']),
        'posterior-outline': (own['inner'], ref['outer']),
        'epiglottis-base-y-and-posterior-outline': (inner_base, ref['outer']),
    }
    count = cfg['count']
    ray_rows = {
        key: [rear_ray(cfg, row['mid_y_cm'], *parts) for row in (upper if key == 'upstream' else native)[:count]]
        for key, parts in groups.items()
    }
    ray_matches = all(same(value, base[key]) for name, source in (('candidate', native), ('upstream', upper))
                      for base, replay in zip(source[:count], ray_rows[name], strict=True)
                      for key, value in replay.items() if key.endswith('_cm'))
    base = cfg['template_epiglottis_base_y_cm']
    lar = pose['posture']['larynx_cm']
    evidence = {
        'epiglottis_base_y_cm': pair_report(ay, upper_y),
        'first_ray_inner_x_cm': {group: rows[0]['inner_x_cm'] for group, rows in ray_rows.items()},
        'rays_at_first_accumulated_difference': {
            group: rows[cfg['first_accumulated_difference']-1:cfg['first_accumulated_difference']+1]
            for group, rows in ray_rows.items()},
    }
    checks = {
        'horizontal_rays_reconstructed_from_contours': ray_matches,
        'epiglottis_base_rounding_reproduced': (
            same(base + lar, ay) and same(7.0 - (7.0 - base) * 1.0 + lar, upper_y)
            and all(data['inner'][0] == data['epiglottis'][0] for data in contours.values())),
        'epiglottis_base_y_recovers_first_inner_x': same(
            ray_rows['epiglottis-base-y'][0]['inner_x_cm'], upper[0]['inner_x_cm']),
    }
    points = {key: [(row['mid_x_cm'], initial['mid_y_cm'])
                    for row, initial in zip(rows, native[:count], strict=True)]
              for key, rows in ray_rows.items() if key not in ('candidate', 'upstream')}
    return checks, evidence, points


def analyse(case, pose, native, upper, split, probe, artifacts, execute):
    cfg = case['measurement']
    original = {'candidate': native, 'upstream': upper}
    points = {label: [tuple(row[key] for key in MIDS) for row in rows] for label, rows in original.items()}
    a, b = points['candidate'], points['upstream']
    points['upstream-x'] = [(xb, ya) for (_, ya), (xb, _) in zip(a, b, strict=True)]
    points['upstream-y'] = [(xa, yb) for (xa, _), (_, yb) in zip(a, b, strict=True)]
    changed = [i for i in range(split + 1) if any(not same(x, y) for x, y in zip(a[i], b[i], strict=True))]
    points.update({f'point-{i}': [*a[:i], b[i], *a[i+1:]] for i in changed})
    ray_cfg = case['rear_ray_replay']
    ray_checks, ray_evidence, rear_points = determine_rear_points(ray_cfg, pose, native, upper, artifacts)
    points.update({name: [*prefix, *a[len(prefix):]] for name, prefix in rear_points.items()})
    segments = segment_distances(points, probe, artifacts, execute)
    initial = cfg['initial_distance_cm']
    rebuilt = {label: recumulate(lengths, initial) for label, lengths in segments.items()}
    observed = {name: [row[DISTANCE] for row in rows] for name, rows in original.items()}
    expected = {label: decimal_arc(points[label], initial) for label in original}
    errors = {name: max(abs(x-y) for x, y in zip(expected[name], observed[name], strict=True))
              for name in original}
    rebuilt_diff = {name: first_difference(rebuilt[name], observed[name]) for name in original}
    first = {key: first_difference([a[key] for a in native], [b[key] for b in upper])
             for key in (*ENDPOINTS, *MIDS, DISTANCE)}
    segment = first_difference(segments['candidate'], segments['upstream'])
    first['segment_end_index'] = None if segment is None else segment + 1
    first_s = first[DISTANCE]
    checks = {
        **ray_checks,
        'coordinates_reproduce_midpoints': all(
            same(row[mid], row[inner] + (row[outer] - row[inner]) * 0.5)
            for rows in original.values() for row in rows
            for inner, outer, mid in zip(ENDPOINTS[:2], ENDPOINTS[2:], MIDS, strict=True)),
        'common_distance_reproduces_observed_arc_bits': all(index is None for index in rebuilt_diff.values()),
        'independent_decimal_distance': max(errors.values()) <= cfg['maximum_independent_arc_error_cm'],
        'coordinate_precedes_distance_difference': bool(changed) and segment is not None and first_s is not None
        and changed[0] <= segment + 1 <= first_s <= split,
        'midpoint_distance_within_tolerance': max(math.dist(x, y) for x, y in zip(a, b, strict=True))
        <= cfg['maximum_midpoint_distance_cm'],
    }
    save_comparison(artifacts / 'centerline-comparison.csv', native, upper, segments, rebuilt)
    event = ray_cfg['first_accumulated_difference']
    ray_evidence['accumulated_at_event_cm'] = {key: rebuilt[key][event] for key in ('candidate', 'upstream', *rear_points)}
    observation = {'first_difference_by_column': first, 'first_replay_difference': rebuilt_diff,
                   'independent_maximum_errors_cm': errors, 'changed_midpoints_through_split': changed,
                   'rear_ray_replay': ray_evidence,
                   'split_replays_cm': {key: distances[split] for key, distances in rebuilt.items()},
                   'single_point_substitution_matches_upstream_split': [
                        i for i in changed if same(rebuilt[f'point-{i}'][split], observed['upstream'][split])],
                   'first_distances': None if first_s is None else {
                        'index': first_s,
                        'previous_s_cm': pair_report(observed['candidate'][first_s-1], observed['upstream'][first_s-1]),
                        'segment_cm': pair_report(segments['candidate'][first_s-1], segments['upstream'][first_s-1]),
                        's_cm': pair_report(observed['candidate'][first_s], observed['upstream'][first_s])}}
    return checks, observation


def verified_artifact(run_id, expected_sha, name):
    folder = WORKSPACE / 'runs' / run_id
    manifest = folder / 'manifest.json'
    saved = json.loads(manifest.read_text())
    artifact = folder / name
    entry = next((entry for entry in saved['outputs'] if entry['path'] == name), None)
    if (saved['status'] != 'pass' or expected_sha != sha256(manifest)
            or entry is None or entry['sha256'] != sha256(artifact)):
        raise ValueError(f'保存済み参照のハッシュが不一致です ({run_id}/{name})')
    return manifest, artifact


def measure(case, source, references, prior_summary, artifacts, execute):
    cfg = case['measurement']
    input_case = json.loads(source.read_text())
    input_case['measurement']['area'] = {}
    path = artifacts / 'pose.json'
    path.write_text(json.dumps(input_case, ensure_ascii=False, indent=2) + '\n')
    prefix = ['cargo', 'run', '--locked', '--release', '-p', 'vocal-cli', '--']
    for name, filename in (('area', 'candidate-area.csv'), ('geometry', 'candidate-contours.csv')):
        execute([*prefix, name, str(path), str(artifacts / filename)])
    execute([*prefix, 'inspect', str(path)], stdout=artifacts / 'candidate-inspect.json')
    execute(['cargo', 'test', '--locked', '-p', 'chimera', '--test', 'geometry_continuity', '--test', 'golden_geometry'],
            cwd=UPSTREAM, stdout=artifacts / 'upstream-geometry-tests.log')
    probe = shared.build_upstream_probe(sagittal.PROBE, artifacts, execute)
    controls = sagittal.pose_controls(input_case)
    for flags, filename in ((['--area'], 'upstream-area.csv'), (['--area-metrics'], 'upstream-area-metrics.csv'),
                            ([], 'upstream-contours.csv')):
        execute([str(probe), *flags, *controls], cwd=UPSTREAM, stdout=artifacts / filename)
    native, upper = [read_area(artifacts / f'{label}-area.csv') for label in ('candidate', 'upstream')]
    splits = [next(i for i, row in enumerate(rows) if row['region'] == 2) for rows in (native, upper)]
    split = cfg['expected_first_oral_index']
    checks = {'registered_topology': [row['region'] for row in native] == [row['region'] for row in upper]
              and splits == [split, split]}
    if not checks['registered_topology']:
        return {'checks': checks, 'splits': splits, 'counts': [len(native), len(upper)]}
    ci = json.loads((artifacts / 'candidate-inspect.json').read_text())
    upper_metrics, = csv_rows(artifacts / 'upstream-area-metrics.csv')
    candidate_length, upper_length = (rows[split][DISTANCE] for rows in (native, upper))
    measured, evidence = analyse(case, input_case, native, upper, split, probe, artifacts, execute)
    node = next(row for row in csv_rows(references['upstream_geometry'])
                if row['tube'] == 'pharynx' and row['node'] == '13')
    pressure_rows = [next(row for row in csv_rows(references[name]) if int(row['internal_sample']) == 8205)
                     for name in ('candidate_pressure', 'upstream_pressure')]
    new_tube = next(t for t in ci['fixed_airway']['tubes'] if t['name'] == 'pharynx')
    cdx, udx = candidate_length / cfg['pharynx_cells'], upper_length / cfg['pharynx_cells']
    checks.update(measured, recorded_length_difference=abs(candidate_length - upper_length)
                  == cfg['expected_pharynx_length_ulp'] * math.ulp(upper_length),
                  shape_and_pressure_reference=(
                      upper_length == float(node['anatomical_length_cm'])
                      == float(upper_metrics['pharynx_length_cm'])
                      and candidate_length == ci['area']['pharynx_length_cm'] == new_tube['anatomical_length_cm']
                      and int(upper_metrics['split_index']) == ci['area']['split_index'] == split
                      and new_tube['cells'] == cfg['pharynx_cells']
                      and [cdx, udx] == [float(row['pharynx_length_cm']) for row in pressure_rows]))
    checks['revision_1_checks_preserved'] = all(checks.get(name) is recorded
                                              for name, recorded in prior_summary['checks'].items())
    return {'checks': checks, 'sample_count': len(native), 'split_index': split,
            'pharynx_length_cm': pair_report(candidate_length, upper_length),
            'pharynx_cell_length_cm': pair_report(cdx, udx), **evidence}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    case = json.loads(CASE.read_text())
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    source = WORKSPACE / 'cases' / case['source_case']
    if sha256(source) != case['source_case_sha256']:
        parser.error('登録した姿勢のハッシュが異なります')
    references = {}
    manifests = []
    for key, origin, name in (('upstream_geometry', 'geometry', 'upstream-geometry.csv'),
                              ('candidate_pressure', 'pressure', 'candidate-pharynx-balance.csv'),
                              ('upstream_pressure', 'pressure', 'upstream-pharynx-balance.csv')):
        manifest, artifact = verified_artifact(case[f'{origin}_reference_run'],
                                              case[f'{origin}_reference_manifest_sha256'], f'artifacts/{name}')
        manifests.append(manifest)
        references[key] = artifact
    ray_cfg = case['rear_ray_replay']
    prior_manifest, prior_summary = verified_artifact(ray_cfg['prior_run'], ray_cfg['prior_manifest_sha256'],
                                                     'summary.json')
    baseline = json.loads(prior_summary.read_text())
    files = [CASE, source, *manifests, *references.values(), prior_manifest, prior_summary,
             Path(__file__).resolve(), sagittal.PROBE,
             *(Path(module.__file__) for module in (shared, sagittal)), *shared.candidate_sources()]
    details = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision,
               'upstream_source_sha256': {name: sha256(UPSTREAM / name) for name in UPSTREAM_PATHS}}
    return shared.record_measurement(args.run_id, CASE, files, details,
                                     lambda out, run: measure(case, source, references, baseline, out, run),
                                     command=None, input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
