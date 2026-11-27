"""前突した下唇の引き込みで生じる断面積の段差を、輪郭からセルまで照合する。"""

import argparse
import csv
import gzip
import io
import itertools
import json
import re
import subprocess
import tempfile
from pathlib import Path

import numpy as np

import measure_area as area
import measure_grid as grid
import measure_resample as resample
import measure_sagittal as sagittal
import measure_uniform_tube as shared
from upstream_baseline import UPSTREAM, WORKSPACE


CASE = WORKSPACE / 'cases/lip-tuck-area-continuity.json'
SWEEP = WORKSPACE / 'tools/lip_tuck_sweep.rs'
BODIES = ('male', 'female', 'child')
ENDS = ('low', 'high')
TEST = 'no_area_jumps_as_a_protruded_lower_lip_tucks'
REPORT = re.compile(r'(male|female|child) lipProt=([\d.]+) lipWidth=([\d.]+) labiodental=([\d.]+): ([\d.]+) cm²')


def native_tests(cfg, artifacts, execute):
    command = ['cargo', 'test', '--locked', '-p', 'chimera', '--test', 'geometry_continuity']
    execute(command, cwd=UPSTREAM, stdout=artifacts / 'upstream-continuity-tests.log')
    log = artifacts / 'upstream-ignored-test.log'
    exit_code = 0
    try:
        execute([*command, TEST, '--', '--ignored'], cwd=UPSTREAM, stdout=log)
    except subprocess.CalledProcessError as error:
        exit_code = error.returncode
    reported = {(BODIES.index(body), float(protrusion), float(spread), round(float(tuck), 4)): float(jump)
                for body, protrusion, spread, tuck, jump in REPORT.findall(log.read_text())}
    return exit_code == cfg['expected_upstream_test_exit'], reported


def sweep(case, probes, artifacts, execute):
    cfg, pose = case['measurement']['sweep'], case['base_posture']
    counts = [case['cells'][tube] for tube in resample.TUBES]
    size = sum(counts)
    args = list(map(str, [pose['jaw_cm'], pose['lip_aperture_cm'], *pose['tongue_tip_cm'], *counts]))
    cache = {name: {} for name in probes}
    # 各段の一時出力を使い回し、評価済みの全姿勢は圧縮CSVに一度だけ残す。
    with tempfile.TemporaryDirectory(prefix='lip-tuck-', dir=artifacts) as temporary:
        schedule = Path(temporary) / 'schedule.csv'
        result = Path(temporary) / 'cells.csv'

        def evaluate(points):
            points = sorted(set(points) - cache['upstream'].keys())
            if not points:
                return
            schedule.write_text(''.join(','.join(map(str, point)) + '\n' for point in points))
            for name, executable in probes.items():
                execute([str(executable), str(schedule), *args], stdout=result)
                with result.open(newline='') as file:
                    rows = list(csv.reader(file))
                values = np.asarray(rows, dtype=float)
                if (values.shape != (len(points), 4 + 2 * size)
                        or not np.array_equal(values[:, :4], points)
                        or not np.isfinite(values).all()):
                    raise ValueError(f'{name} の姿勢またはセル断面積を照合できません')
                cache[name].update(zip(points, values[:, 4:], strict=True))

        def jump(name, group, lo, hi):
            data = cache[name]
            delta = data[(*group, hi)][:size] - data[(*group, lo)][:size]
            cell = int(np.argmax(np.abs(delta)))
            return float(abs(delta[cell])), cell

        groups = list(itertools.product(range(len(BODIES)), case['lip_protrusions_cm'], case['lip_spreads']))
        steps = cfg['steps']
        times = [cfg['start'] + (cfg['end'] - cfg['start']) * i / steps for i in range(steps + 1)]
        threshold = cfg['threshold_cm2']
        evaluate((*group, tuck) for group in groups for tuck in times)
        brackets = {name: [(group, step, lo, hi)
                           for group in groups
                           for step, (lo, hi) in enumerate(zip(times, times[1:]), 1)
                           if jump(name, group, lo, hi)[0] > threshold]
                    for name in probes}
        coarse_count = {name: len(items) for name, items in brackets.items()}
        for _ in range(cfg['refinement_rounds']):
            evaluate((*group, (lo + hi) / 2) for items in brackets.values() for group, _, lo, hi in items)
            for name, items in brackets.items():
                brackets[name] = [(group, step, a, b)
                                  for group, step, lo, hi in items
                                  for mid in [(lo + hi) / 2]
                                  for a, b in [(lo, mid), (mid, hi)]
                                  if jump(name, group, a, b)[0] > threshold]

        for name, data in cache.items():
            with (artifacts / f'{name}-sweep.csv.gz').open('wb') as raw, \
                    gzip.GzipFile(fileobj=raw, mode='wb', filename='', mtime=0) as compressed:
                with io.TextIOWrapper(compressed, newline='') as file:
                    writer = csv.writer(file, lineterminator='\n')
                    cells = [f'{tube}_{i}' for tube, count in zip(resample.TUBES, counts, strict=True)
                             for i in range(count)]
                    writer.writerow(['body', 'lip_protrusion_cm', 'lip_spread', 'labiodental',
                                     *(f'{cell}_area_cm2' for cell in cells),
                                     *(f'{cell}_minimum_cm2' for cell in cells)])
                    for (body, *controls), values in sorted(data.items()):
                        writer.writerow([BODIES[body], *controls, *values])

        max_error = float(max(np.abs(left - cache['candidate'][point]).max()
                              for point, left in cache['upstream'].items()))
        events = {name: [{'group': group, 'coarse_step': step, 'u': [lo, hi],
                          'jump_cm2': jump(name, group, lo, hi)[0],
                          'cell': jump(name, group, lo, hi)[1]}
                         for group, step, lo, hi in items]
                  for name, items in brackets.items()}
    return cache, events, {'coarse_samples': len(groups) * len(times), 'refined_samples': len(cache['upstream']),
                           'coarse_suspicions': coarse_count, 'upstream_candidate_max_error_cm2': max_error}


def vertical_crossings(points, x, low, high, *, strict_high=False):
    # 補間は交差パラメータの行列式を使わず、線分をxで内分してyを求める。
    left, right = points[:-1], points[1:]
    crosses = (left[:, 0] <= x) != (right[:, 0] <= x)
    edges = np.flatnonzero(crosses & (np.abs(right[:, 0] - left[:, 0]) >= 1e-15))
    a, b = left[edges], right[edges]
    frac = (x - a[:, 0]) / (b[:, 0] - a[:, 0])
    y = a[:, 1] + frac * (b[:, 1] - a[:, 1])
    return [(int(index), float(height)) for index, height in zip(edges, y, strict=True)
            if low <= height and (height < high if strict_high else height <= high)]


def front_rays(parts, profile, tuck, scale):
    incisor_x = parts['palate'][-1, 0]
    lip_x, lip_y = parts['lower_lip'][6]
    x_start = incisor_x + 0.03 * scale
    x_end = max(x_start + 0.3 * scale, min(lip_x, parts['upper_lip'][6, 0]) - 0.04 * scale)
    indices = np.flatnonzero(profile[:, 0] == 3)
    if len(indices) != 6:
        raise ValueError('前方測定線の本数が6ではありません')
    rows = []
    for index, x in zip(indices, np.linspace(x_start, x_end, 6), strict=True):
        outer = vertical_crossings(parts['outer'], x, 4 * scale, 12 * scale)
        roof_segment, roof = min(outer, key=lambda hit: hit[1])
        inner = vertical_crossings(parts['inner'], x, 4 * scale, roof + 1.5 * scale, strict_high=True)
        floor_segment, hit_floor = max(inner, key=lambda hit: hit[1], default=(None, max(4 * scale, roof - 3.5 * scale)))
        forward = x - lip_x
        if forward > 0:
            face = min(lip_y - forward * 4 / 3, roof)
            openness = grid.smoothstep((tuck - 0.7) / 0.3) * grid.smoothstep(forward / (0.1 * scale))
            hit_floor = face + (roof - 3.5 * scale - face) * openness
        floor = min(hit_floor, roof)
        raw = roof - floor
        rows.append({'grid_index': int(index), 'x_cm': float(x), 'lower_lip_edge_x_cm': float(lip_x),
                     'floor_y_cm': float(floor), 'roof_y_cm': roof, 'floor_segment': floor_segment,
                     'roof_segment': roof_segment, 'inner_crossings': inner, 'outer_crossings': outer,
                     'lip_extension': bool(forward > 0), 'ray_cm': float(raw),
                     'gap_cm': float(profile[index, -3]), 'area_cm2': float(profile[index, -2]),
                     's_cm': float(profile[index, -1]),
                     'ray_error_cm': float(np.max(np.abs(profile[index, [1, 2, 4, 7]]
                                                       - [x, floor, roof, raw])))})
    return rows


def endpoint(case, event, tuck, cache, probes, folder, execute):
    body, protrusion, spread = event['group']
    body_name = BODIES[body]
    pose = {**case['base_posture'], 'lip_protrusion_cm': protrusion, 'lip_spread': spread, 'labiodental': tuck}
    case_data = {key: case[key] for key in ('id', 'upstream_revision', 'hypothesis', 'cells', 'measurement')}
    case_data.update(body=body_name, posture=pose)
    folder.mkdir(parents=True)
    case_path = folder / 'posture.json'
    cli_case = {**case_data, 'measurement': {'frames': case['measurement']['frames']}}
    case_path.write_text(json.dumps(cli_case, ensure_ascii=False, indent=2) + '\n')
    params = case['body_parameters'][body_name]
    scale = params['scale']
    epilarynx = 2.4 * scale * params['pharynx']
    independent, parts_by_name, profiles, rays = {}, {}, {}, {}
    for name in probes:
        paths = {command: folder / f'{name}-{command}.csv' for command in ('geometry', 'area', 'resample')}
        for command, path in paths.items():
            if name == 'candidate':
                execute(['cargo', 'run', '--locked', '--release', '-q', '-p', 'vocal-cli', '--',
                         command, str(case_path), str(path)])
            else:
                flags = {'geometry': [], 'area': ['--area'],
                         'resample': ['--resample', *(str(case['cells'][tube]) for tube in resample.TUBES)]}
                execute([str(probes[name]), '--body', body_name,
                         *flags[command], *sagittal.pose_controls(case_data)], cwd=UPSTREAM, stdout=path)
        parts = parts_by_name[name] = sagittal.read_points(paths['geometry'])
        profile = profiles[name] = grid.read_grid(paths['area'], columns=area.COLUMNS)
        observations = rays[name] = front_rays(parts, profile, tuck, scale)
        computed = profile.copy()
        # この観測区間では唇の接触上限が解除されると予測し、前方の生の隙間から面積を再計算する。
        computed[[row['grid_index'] for row in observations], -3] = [row['ray_cm'] for row in observations]
        areas, positions, *_ = area.independent_profile(
            parts, computed[:, :-2], pose, scale=scale, epilarynx_cm=epilarynx,
            full_lip_width=params['lip_width_cm_at_full_spread_before_scaling'])
        computed[:, -2:] = np.column_stack((areas, positions))
        expected = resample.estimate_cells(computed, case_data, folder / f'{name}-independent-cells.csv',
                                          scale=scale, epilarynx_cm=epilarynx)
        actual = resample.read_cells(paths['resample'])
        cells = np.concatenate([actual[tube] for tube in resample.TUBES])
        bulk = cache[name][(body, protrusion, spread, tuck)]
        independent[name] = {
            'ray_cm': max(row['ray_error_cm'] for row in observations),
            'contact_delta_cm': max(abs(row['ray_cm'] - row['gap_cm']) for row in observations),
            'profile_s_cm': float(abs(computed[:, -1] - profile[:, -1]).max()),
            'profile_area_cm2': float(abs(computed[:, -2] - profile[:, -2]).max()),
            'cell_boundary_cm': max(float(abs(expected[tube][0][:, :2] - actual[tube][:, :2]).max())
                                    for tube in resample.TUBES),
            'cell_area_cm2': max(float(abs(expected[tube][0][:, 2:] - actual[tube][:, 2:]).max())
                                 for tube in resample.TUBES),
            'bulk_entry_cm2': float(abs(np.r_[cells[:, 2], cells[:, 3]] - bulk).max()),
        }
    errors = abs(profiles['upstream'] - profiles['candidate'])
    contour_error = max(float(abs(parts_by_name['upstream'][part] - parts_by_name['candidate'][part]).max())
                        for part in ('inner', 'outer', 'lower_lip', 'upper_lip'))
    comparison = {'profile_area_cm2': float(errors[:, -2].max()),
                  'geometry_cm': max(contour_error, float(np.delete(errors, -2, axis=1).max()))}
    return {'rays': rays, 'independent_errors': independent, 'upstream_candidate_errors': comparison}, parts_by_name


def detail(case, events, cache, probe, artifacts, execute):
    cfg = case['measurement']
    report = []
    for index, event in enumerate(events, 1):
        folder = artifacts / f'event-{index:02}'
        samples, contours = {}, {}
        for end, tuck in zip(ENDS, event['u'], strict=True):
            samples[end], contours[end] = endpoint(case, event, tuck, cache, probe, folder / end, execute)
        findings = {}
        for name in probe:
            lo, hi = (samples[end]['rays'][name] for end in ENDS)
            motion = max(float(abs(contours['high'][name][part] - contours['low'][name][part]).max())
                         for part in ('inner', 'outer', 'lower_lip', 'upper_lip'))
            ray_deltas = [abs(a['floor_y_cm'] - b['floor_y_cm']) for a, b in zip(lo, hi, strict=True)]
            largest = int(np.argmax(ray_deltas))
            a, b = lo[largest], hi[largest]
            findings[name] = {'vertex_delta_cm': motion, 'front_ray': largest, 'floor_jump_cm': ray_deltas[largest],
                              'roof_delta_cm': abs(a['roof_y_cm'] - b['roof_y_cm']),
                              'grid_area_delta_cm2': b['area_cm2'] - a['area_cm2'],
                              'centreline_delta_cm': b['s_cm'] - a['s_cm'],
                              'floor_segments': [a['floor_segment'], b['floor_segment']],
                              'inner_crossing_counts': [len(a['inner_crossings']), len(b['inner_crossings'])],
                              'lip_extension_active': a['lip_extension'] or b['lip_extension']}
        report.append({**event, 'observations': samples, 'crossing_transition': findings})
    errors = [values for event in report for end in ENDS for values in (
        *event['observations'][end]['independent_errors'].values(),
        event['observations'][end]['upstream_candidate_errors'])]
    error_bounds = {units: max(value for row in errors for key, value in row.items() if key.endswith(units))
                    for units in ('_cm', '_cm2')}
    transitions = [item for event in report for item in event['crossing_transition'].values()]
    checks = {
        'independent_geometry_and_cells': error_bounds['_cm'] < cfg['position_error_lt_cm']
                                          and error_bounds['_cm2'] < cfg['area_error_lt_cm2'],
        'contours_and_roof_continuous': all(item['vertex_delta_cm'] < cfg['moving_vertex_delta_lt_cm']
                                            and item['roof_delta_cm'] < cfg['moving_vertex_delta_lt_cm']
                                            for item in transitions),
        'first_jump_is_floor_crossing': all(item['floor_jump_cm'] > cfg['visible_floor_jump_gt_cm']
                                            and item['floor_segments'][0] != item['floor_segments'][1]
                                            and not item['lip_extension_active']
                                            for item in transitions),
    }
    return report, error_bounds, checks


def distance_contrast(case, event, folder):
    pose = json.loads((folder / 'low/posture.json').read_text())['posture']
    profiles = {end: grid.read_grid(folder / end / 'upstream-area.csv', columns=area.COLUMNS) for end in ENDS}
    tube = 'oral'
    index = event['cell'] - case['cells']['pharynx']
    if index < 0:
        raise ValueError('代表例の最大差は口腔セルを想定しています')
    actual_cells = {end: resample.read_cells(folder / end / 'upstream-resample.csv')[tube][index] for end in ENDS}
    contrast = []
    for area_source, distance_source in itertools.product(ENDS, repeat=2):
        profile = profiles[area_source].copy()
        profile[:, -1] = profiles[distance_source][:, -1]
        expected = resample.estimate_cells(profile, {**case, 'posture': pose},
                                           folder / f'area-{area_source}-distance-{distance_source}.csv')
        row = expected[tube][0][index]
        contrast.append({'area_source': area_source, 'distance_source': distance_source,
                         **dict(zip(resample.FIELDS, row.tolist(), strict=True))})
    error = max(float(abs(np.array([row[key] for key in resample.FIELDS]) - actual_cells[end]).max())
                for row, end in zip([contrast[0], contrast[-1]], ENDS, strict=True))
    return {'tube': tube, 'cell': index, 'cases': contrast, 'endpoint_max_error': error}


def measure(case, artifacts, execute):
    cfg = case['measurement']['sweep']
    expected_exit, native = native_tests(cfg, artifacts, execute)
    capture = shared.build_upstream_probe(sagittal.PROBE, artifacts, execute)
    execute(['cargo', 'build', '--locked', '--release', '-p', 'vocal-cli'])
    probes = {'upstream': shared.build_upstream_probe(SWEEP, artifacts, execute, rustc_args=('--cfg', 'fixed_upstream')),
              'candidate': shared.build_upstream_probe(SWEEP, artifacts, execute,
                                                       upstream=WORKSPACE, package='vocal-core', lto='off')}
    cache, events, coverage = sweep(case, probes, artifacts, execute)
    native_results = {(*e['group'], round(cfg['start'] + (cfg['end'] - cfg['start']) *
                                         e['coarse_step'] / cfg['steps'], 4)): round(e['jump_cm2'], 2)
                      for e in events['upstream']}
    matches = [e for e in events['upstream']
               if e['group'] == (BODIES.index(cfg['reference_event']['body']),
                                  cfg['reference_event']['lip_protrusion_cm'], cfg['reference_event']['lip_spread'])]
    anchor, area_interval = (cfg['reference_event'][key] for key in ('anchor_interval', 'cell_jump_interval_cm2'))
    comparable = ('group', 'coarse_step', 'u', 'cell')
    checks = {
        'fixed_ignored_test_failure_reproduced': expected_exit and native == native_results
            and all(sum(row[0] == body for row in native) == cfg['expected_reported_steps_per_body']
                    for body in range(len(BODIES))),
        'registered_reference_event': len(matches) == 1 and anchor[0] <= matches[0]['u'][0] <= matches[0]['u'][1] <= anchor[1]
                                      and area_interval[0] <= matches[0]['jump_cm2'] <= area_interval[1],
        'upstream_candidate_events': len(events['upstream']) == len(events['candidate']) and
            all(all(a[key] == b[key] for key in comparable)
                for a, b in zip(events['upstream'], events['candidate'])),
        'upstream_candidate_all_cells':
            coverage['upstream_candidate_max_error_cm2'] < case['measurement']['area_error_lt_cm2'],
    }
    report, errors, detail_checks = detail(case, events['upstream'], cache,
                                          {'upstream': capture, 'candidate': probes['candidate']}, artifacts, execute)
    checks.update(detail_checks)
    (artifacts / 'crossing-details.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    contrast = None
    if checks['registered_reference_event']:
        folder = artifacts / f"event-{events['upstream'].index(matches[0]) + 1:02}"
        contrast = distance_contrast(case, matches[0], folder)
    checks['distance_contrast_matches_endpoints'] = (
        contrast is not None and contrast['endpoint_max_error'] < min(case['measurement'][key]
            for key in ('area_error_lt_cm2', 'position_error_lt_cm')))
    return {'checks': checks, 'coverage': coverage, 'detail_max_errors': errors, 'events': [
        {**event, 'body': BODIES[event['group'][0]], 'lip_protrusion_cm': event['group'][1],
         'lip_spread': event['group'][2], 'crossing_transition': item['crossing_transition']}
        for event, item in zip(events['upstream'], report, strict=True)],
        'candidate_events': events['candidate'], 'distance_contrast': contrast}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    case = json.loads(CASE.read_text())
    revision = case['upstream_revision']
    if (subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip() != revision
            or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True)):
        parser.error('固定した上流版のコミットと作業状態を確認してください')
    relative_sources = ('Cargo.toml', 'Cargo.lock', 'crates/chimera/Cargo.toml', 'crates/chimera/src/anatomy/human.rs',
                        'crates/chimera/src/anatomy/geom.rs', 'crates/chimera/src/voice/human_airway.rs',
                        'crates/chimera/tests/geometry_continuity.rs')
    tools = [Path(__file__).resolve(), SWEEP, sagittal.PROBE, *map(lambda mod: Path(mod.__file__),
             (area, grid, resample, sagittal, shared))]
    inputs = [CASE, *tools, *shared.candidate_sources(), *(UPSTREAM / file for file in relative_sources)]
    return shared.record_measurement(args.run_id, CASE, inputs,
                                     {'case_id': case['id'], 'upstream_revision': revision},
                                     lambda artifacts, execute: measure(case, artifacts, execute),
                                     command=None, input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
