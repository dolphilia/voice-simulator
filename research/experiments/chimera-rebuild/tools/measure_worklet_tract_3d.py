"""固定姿勢の三次元断面をCLI、上流の格子、描画頂点の独立計算に照合する。"""

import argparse
import csv
import json
import re
import shutil
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image

import measure_grid as grid
import measure_sagittal as sagittal
import measure_uniform_tube as shared
import measure_wasm_fixed as wasm
from measure_worklet_fixed import CAPTURE, ROOT, WEB, web_sources
from upstream_baseline import UPSTREAM, WORKSPACE, sha256

CASE = WORKSPACE / 'cases/worklet-tract-3d.json'
AREA_COLUMNS = ',gap_cm,area_cm2,s_cm'
GRID_COLUMNS = grid.HEADER.split(',')[1:] + AREA_COLUMNS[1:].split(',')


def differences(actual, reference, limit):
    delta = np.abs(actual - reference)
    excess = np.argwhere(delta > limit)
    return {'maximum_absolute_error': float(delta.max()), 'tolerance': limit,
            'first_outside_tolerance': excess[0].tolist() if len(excess) else None, 'passed': not len(excess)}


def measure_rings(data, raw, spec):
    sections, n = spec['expected_sections'], spec['ring_segments']
    vertices = np.asarray(data['vertices'], dtype=float).reshape(sections, n, 3)
    if not np.isfinite(vertices).all():
        raise ValueError('三次元断面に非有限の頂点があります')
    direction = raw[:, 3:5] - raw[:, 1:3]
    ray_length = np.linalg.norm(direction, axis=1)[:, None]
    np.divide(direction, ray_length, out=direction, where=ray_length > 0)
    radius = raw[:, 8] / 2
    expected_center = raw[:, 3:5] - direction * radius[:, None]
    centers = vertices.mean(axis=1)
    span = np.linalg.norm(vertices[:, 0] - vertices[:, n // 2], axis=1)
    width = np.linalg.norm(vertices[:, n // 4] - vertices[:, 3 * n // 4], axis=1)
    plane_axis = np.column_stack((-direction[:, 1], direction[:, 0], np.zeros(sections)))
    local = vertices - centers[:, None, :]
    plane = (local * plane_axis[:, None, :]).sum(axis=2)
    cross = np.cross(local, np.roll(local, -1, axis=1)).sum(axis=1)
    area = np.linalg.norm(cross, axis=1) / 2
    ratio = n * np.sin(2 * np.pi / n) / (2 * np.pi)
    cm, cm2 = spec['vertex_geometry_tolerance_cm'], spec['polygon_area_tolerance_cm2']
    comparisons = {
        'center_cm': differences(centers, np.column_stack((expected_center, np.zeros(sections))), cm),
        'gap_cm': differences(span, raw[:, 8], cm),
        'outer_point_cm': differences(vertices[:, 0, :2], raw[:, 3:5], cm),
        'sagittal_plane_cm': differences(plane, 0, cm),
        'ellipse_area_cm2': differences(area / ratio, raw[:, 9], cm2),
    }
    return comparisons, {'ring_count': sections, 'vertex_count': sections * n,
                         'last_center_cm': centers[-1].tolist(), 'last_width_cm': float(width[-1]),
                         'last_area_cm2': float(raw[-1, 9]), 'last_polygon_area_cm2': float(area[-1]),
                         'last_distance_cm': float(raw[-1, 10]), 'polygon_area_ratio': float(ratio)}


def screenshot_signal(path, *, closure=False):
    with Image.open(path) as image:
        colors = np.asarray(image.convert('RGB'), dtype=np.int16)[6:-6, 6:-6]
    if closure:
        return int(np.count_nonzero((colors[:, :, 0] - colors[:, :, 1] > 35)
                                   & (colors[:, :, 1] - colors[:, :, 2] > 15)))
    return int(np.count_nonzero(np.max(abs(colors - colors[0, 0]), axis=2) > 30))


def read_motion_grid(path, frames, sections):
    with path.open() as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != ['frame', 'ray', *GRID_COLUMNS]:
            raise ValueError(f'{path.name} の測定線の列が一致しません')
        rows = [(int(row['frame']), int(row['ray']), [float(row[field]) for field in GRID_COLUMNS])
                for row in reader]
    if len(rows) != len(frames) * sections or any(
            (frame, index) != (int(frames[i // sections]), i % sections)
            for i, (frame, index, _) in enumerate(rows)):
        raise ValueError(f'{path.name} のフレーム番号または測定線番号が一致しません')
    return np.asarray([values for _, _, values in rows]).reshape(len(frames), sections, len(GRID_COLUMNS))


def compare_motion(case, report, frames, lips, cli_path, upstream_path, artifacts):
    spec = case['measurement']
    profile = report['tract'].get('grid')
    sections = spec['expected_sections']
    if profile is None or profile['columns'] != GRID_COLUMNS:
        raise ValueError('ブラウザ出力に測定線が無いか、列が一致しません')
    observed = profile['frames']
    if [row['frame'] for row in observed] != frames.tolist() or len(observed) != spec['expected_profile_rows']:
        raise ValueError('音響セルと同じフレームに測定線がありません')
    raw = np.asarray([row['rows'] for row in observed])
    if raw.shape != (len(frames), sections, len(GRID_COLUMNS)) or not np.isfinite(raw).all():
        raise ValueError('ブラウザの測定線の行数または有限性が条件外です')
    native, upper = [read_motion_grid(path, frames, sections) for path in (cli_path, upstream_path)]
    if not np.isfinite(native).all() or not np.isfinite(upper).all():
        raise ValueError('CLIまたは上流の測定線に非有限値があります')
    difference = differences(raw, upper, spec['grid_absolute_tolerance'])
    if difference['first_outside_tolerance'] is not None:
        i, ray, column = difference['first_outside_tolerance']
        difference['first_mismatch'] = {'frame': int(frames[i]), 'ray': ray, 'column': GRID_COLUMNS[column],
                                        'candidate': float(raw[i, ray, column]), 'upstream': float(upper[i, ray, column])}
    samples = {}
    for trial in spec['frames']:
        frame = trial['expected_observed_frame']
        i = int(np.searchsorted(frames, frame))
        if i >= len(frames) or frames[i] != frame:
            raise ValueError('事前登録された出力フレームがありません')
        samples[trial['id']] = {'frame': frame, 'elapsed_ms': (frame + 1) / report['sampleRate'] * 1000,
                                'geometry_gap_cm': float(raw[i, -1, 8]),
                                'geometry_area_cm2': float(raw[i, -1, 9]),
                                'lip_minimum_acoustic_area_cm2': float(lips[i])}
    closed = samples['closed']
    views = wasm.read_json(artifacts / 'tract-3d-dynamic-display.json')
    clock_ok = [v['width'] for v in views] == spec['viewport_widths_css_px']
    renderer_ok = pixels_ok = payload_ok = rings_ok = marker_ok = True
    geometry = []
    for viewport in views:
        width = viewport['width']
        clock_ok &= viewport['absent'] and [entry['id'] for entry in viewport['frames']] == list(samples)
        for selected in viewport['frames']:
            name = selected['id']
            frame = samples[name]['frame']
            i = int(np.searchsorted(frames, frame))
            trial = next(item for item in spec['frames'] if item['id'] == name)
            clock_ok &= selected['selectedFrame'] == trial['selected_output_frame'] and selected['acousticFrame'] == frame
            renderer = selected['renderer']
            renderer_ok &= (renderer['ready'] and renderer['sameContext']
                            and 0 < renderer['width'] <= width and renderer['height'] >= 200)
            images = []
            for view in ('angled', 'side'):
                base = artifacts / f'tract-3d-{width}-{name}-{view}'
                data = wasm.read_json(base.with_suffix('.json'))
                payload_ok &= bool(
                    data['frame'] == frame and data['columns'] == GRID_COLUMNS
                    and data['ringSegments'] == spec['ring_segments']
                    and data['elapsedSeconds'] == (frame + 1) / report['sampleRate']
                    and data['lipMinimumAcousticAreaCm2'] == lips[i]
                    and np.array_equal(data['rows'], raw[i]))
                checks, numbers = measure_rings(data, raw[i], spec)
                rings_ok &= all(result['passed'] for result in checks.values())
                image = base.with_suffix('.png')
                images.append(sha256(image))
                signal = screenshot_signal(image)
                pixels_ok &= signal > 200
                closure_pixels = screenshot_signal(image, closure=True) if name == 'closed' else None
                marker_ok &= closure_pixels is None or closure_pixels > 7
                geometry.append({'width': width, 'phase': name, 'view': view, 'visible_pixels': signal,
                                 'closure_marker_pixels': closure_pixels,
                                 **numbers, 'vertex_comparisons': checks})
            pixels_ok &= images[0] != images[1]
    return {
        'grid_clock_and_columns': report['body'] == case['measurement']['body'],
        'grid_native_exact': np.array_equal(raw, native),
        'grid_upstream': difference['passed'],
        'closure_geometry_and_acoustic_cells': (
            closed['geometry_gap_cm'] <= spec['maximum_closed_gap_cm']
            and closed['geometry_area_cm2'] <= spec['maximum_closed_geometric_area_cm2']
            and closed['lip_minimum_acoustic_area_cm2'] <= spec['maximum_closed_acoustic_area_cm2']
            and all(min(samples[phase]['geometry_area_cm2'], samples[phase]['lip_minimum_acoustic_area_cm2'])
                    >= spec['minimum_open_area_cm2'] for phase in ('before', 'after'))),
        '3d_selection_and_missing_state': clock_ok,
        '3d_renderer_context_retained': renderer_ok,
        '3d_visible_projections': pixels_ok,
        '3d_closed_lip_marker': marker_ok,
        '3d_saved_observations': payload_ok,
        '3d_vertices_independent_geometry': rings_ok,
    }, {'section_count': sections, 'samples': samples, 'upstream_grid': difference, 'views': geometry}


def measure(case, fixed, bun, artifacts, execute):
    spec = case['measurement']
    execute(['cargo', 'test', '--locked', '-p', 'chimera', '--test', 'golden_geometry'],
            cwd=UPSTREAM, stdout=artifacts / 'upstream-geometry-test.log')
    probe = shared.build_upstream_probe(sagittal.PROBE, artifacts, execute)
    sources = {}
    for variant in spec['variants']:
        label = variant['id']
        posture = fixed['posture'] | {k: variant[k] for k in ('lip_aperture_cm',) if k in variant}
        replay = fixed | {'posture': posture}
        input_ = artifacts / f'{label}-case.json'
        input_.write_text(json.dumps(replay, ensure_ascii=False, indent=2) + '\n')
        cli, upper = (artifacts / f'{label}-{key}.csv' for key in ('cli', 'upstream'))
        execute(['cargo', 'run', '--locked', '--release', '-p', 'vocal-cli', '--', 'area', str(input_), str(cli)])
        execute([str(probe), '--area', *sagittal.pose_controls(replay)], cwd=UPSTREAM, stdout=upper)
        sources[label] = [grid.read_grid(path, columns=AREA_COLUMNS) for path in (cli, upper)]
    execute([*bun, 'run', 'build'], cwd=WEB, stdout=artifacts / 'browser-build.log')
    module = artifacts / 'vocal_wasm.wasm'
    shutil.copyfile(WORKSPACE / wasm.WASM, module)
    execute(['node', str(CAPTURE), str(artifacts), str(CASE)])
    browser = wasm.read_json(artifacts / 'browser-run.json')
    checks, views = {}, {}
    snapshots = {}
    expected_runs = {(width, v['id']) for width in spec['viewport_widths_css_px'] for v in spec['variants']}
    checks['all_browser_variants_and_views'] = {(r['width'], r['variant']) for r in browser['runs']} == expected_runs
    for run in browser['runs']:
        width, label = run['width'], run['variant']
        name = f'{width}-{label}'
        expected, upper = sources[label]
        paths = [artifacts / f'{name}-{view}' for view in ('angled', 'side')]
        current, side = [wasm.read_json(path.with_suffix('.json')) for path in paths]
        raw = np.asarray(current['rows'], dtype=float)
        if (current['columns'] != GRID_COLUMNS or
                not raw.shape == expected.shape == upper.shape == (spec['expected_sections'], len(GRID_COLUMNS))
                or not np.isfinite(raw).all()):
            raise ValueError(f'{name} の測定線または列の定義に差があります')
        tol = spec['grid_absolute_tolerance']
        cli_grid = differences(raw, expected, tol)
        upper_grid = differences(raw, upper, tol)
        distance = raw[0, 10] + np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(raw[:, 5:7], axis=0), axis=1))]
        path_match = differences(raw[:, 10], distance, tol)
        comparison, summary = measure_rings(current, expected, spec)
        selected = raw[spec['selected_section_indices']][:, [10, 8, 9]]
        browser_selected = differences(np.asarray(run['selected']), selected, tol)
        pngs = [path.with_suffix('.png') for path in paths]
        signals = [screenshot_signal(path) for path in pngs]
        renderer = run['renderer']
        view_checks = {
            'fixed_upstream_grid': upper_grid['passed'],
            'native_cli_grid': cli_grid['passed'],
            'distance_independent': path_match['passed'],
            'same_geometry_after_camera_change': current == side,
            'renderer_and_viewport': renderer['ready'] and 0 < renderer['width'] <= width
            and renderer['height'] > 0 and renderer['backingWidth'] >= renderer['width'],
            'visible_render_and_changed_projection': min(signals) > 50 and sha256(pngs[0]) != sha256(pngs[1]),
            'section_readout': browser_selected['passed'],
            'id_wasm_and_controls': current['caseId'] == case['id'] and current['variant'] == label
            and current['ringSegments'] == spec['ring_segments'] and run['closes'] and not run['errors']
            and run['servedWasmSha256'] == sha256(module),
            **{f'vertex_{key}': item['passed'] for key, item in comparison.items()},
        }
        if label in snapshots:
            view_checks['geometry_matches_other_viewport'] = snapshots[label][0] == current
        snapshots[label] = (current, summary)
        checks.update({f'{name}.{key}': value for key, value in view_checks.items()})
        views[name] = {'cli_grid': cli_grid, 'upstream_grid': upper_grid, 'independent_distance': path_match,
                       'geometry': comparison, 'dimensions': renderer, 'selected_section_values': run['selected'],
                       'screenshot_signal_pixels': signals, **summary}
    standard, narrow = [snapshots[v['id']][1] for v in spec['variants']]
    reduction = standard['last_area_cm2'] - narrow['last_area_cm2']
    rise = narrow['last_center_cm'][1] - standard['last_center_cm'][1]
    checks['lip_aperture_changes_area'] = reduction >= spec['minimum_exit_area_reduction_cm2']
    checks['lip_aperture_moves_center_up'] = rise >= spec['minimum_exit_center_rise_cm']
    return {'checks': checks, 'browser': browser['version'], 'views': views,
            'exit_area_reduction_cm2': reduction, 'exit_center_rise_cm': rise}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', args.run_id):
        parser.error('実行IDは英数字で始めてください')
    case = wasm.read_json(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(
            ['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True):
        raise SystemExit('変更のない固定上流版が必要です')
    fixed = WORKSPACE / 'cases' / case['fixed_voice_case']
    bun = ['bun'] if shutil.which('bun') else ['npx', '--yes', '--package=bun@1.4.4', '--', 'bun']
    inputs = [CASE, fixed, Path(__file__).resolve(), sagittal.PROBE, *web_sources(), *shared.candidate_sources(),
              *(Path(m.__file__) for m in (grid, sagittal, shared, wasm)),
              *(WORKSPACE / 'tools' / name for name in ('measure_worklet_fixed.py', 'upstream_baseline.py'))]
    upper = ('src/ui/App.tsx', 'src/ui/components/AnatomyView3D.tsx', 'src/ui/render/anatomy3d.ts',
             'src/ui/analysis.ts', 'crates/chimera/src/anatomy/human.rs', 'crates/chimera/tests/golden_geometry.rs')
    details = {'case_id': case['id'], 'revision': case['revision'], 'upstream_revision': revision,
               'invoked_from': str(Path.cwd()), 'input_root': '$REPOSITORY',
               'node': subprocess.check_output(['node', '--version'], text=True).strip(),
               'bun': subprocess.check_output([*bun, '--version'], text=True).strip(),
               'upstream_source_sha256': {name: sha256(UPSTREAM / name) for name in upper}}
    return shared.record_measurement(args.run_id, CASE, inputs, details,
                                     lambda out, run: measure(case, wasm.read_json(fixed), bun, out, run),
                                     command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
