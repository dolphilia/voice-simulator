"""二声のCHTL圧力と三次元の輪をCLI・固定上流・実ブラウザで照合する。"""

import argparse
import json
from math import floor, hypot, log10, pi, sin, cos
from pathlib import Path
import re
import shutil
import struct
import subprocess

import numpy as np
from PIL import Image

import measure_uniform_tube as shared
from measure_duet_heads import POSTURE, UPPER_WASM
from measure_duet_words import prior
from measure_wasm_fixed import read_json
from measure_worklet_fixed import ROOT, WEB, web_sources
from upstream_baseline import UPSTREAM, WORKSPACE, sha256

CASE = WORKSPACE / 'cases/duet-head-pressure.json'
DEMO = WEB / 'public/shows/duet-clock'
CAPTURE = WEB / 'tools/capture-duet-head-pressure.mjs'
GRID = ('region', 'inner_x_cm', 'inner_y_cm', 'outer_x_cm', 'outer_y_cm', 'mid_x_cm', 'mid_y_cm',
        'ray_cm', 'gap_cm', 'area_cm2', 's_cm')
UPPER_COLUMNS = (1, 2, 3, 4, 8, 9, 10)
UPPER_DISTANCES = (0, 1, 2, 3, 4, 6)


def track(path, rate):
    data = path.read_bytes()
    version, frequency, hop, frames, width, axes, pharynx, oral, scope = struct.unpack_from('<9I', data, 4)
    if (data[:4] != b'CHTL' or version != 1 or frequency != rate or not hop or not frames
            or axes != len(POSTURE) or width != 11 + axes + 3 * (pharynx + oral) + 2 * scope
            or len(data) != 48 + 4 * width * frames):
        raise ValueError(f'CHTLの形式が登録条件と一致しません ({path.name})')
    values = np.frombuffer(data, dtype='<f4', offset=48).astype(float).reshape(frames, width)
    count = pharynx + oral
    return {'hop': hop, 'body': dict(zip(('female', 'child'), struct.unpack_from('<2f', data, 40), strict=True)),
            'lengths': values[:, :2], 'artic': values[:, 11:11 + axes], 'areas': values[:, 11 + axes:11 + axes + count],
            'pressure': values[:, 11 + axes + count:11 + axes + 2 * count],
            'flow': values[:, 11 + axes + 2 * count:11 + axes + 3 * count], 'pharynx': pharynx, 'oral': oral}


def positions(lengths, pharynx, oral):
    a, b = lengths
    return np.r_[(np.arange(pharynx) + .5) * a / pharynx, a + (np.arange(oral) + .5) * b / oral]


def cli_grid(source, row, voice, spec, artifacts, execute):
    posture = dict(zip(POSTURE, source['artic'][row].tolist(), strict=True))
    posture['tongue_body_cm'] = [posture.pop('tb_x'), posture.pop('tb_y')]
    posture['tongue_tip_cm'] = [posture.pop('tt_x'), posture.pop('tt_y')]
    name = f'pressure-voice-{voice}-row-{row}'
    case, output = (artifacts / f'{name}.{suffix}' for suffix in ('json', 'csv'))
    case.write_text(json.dumps({'id': name, 'upstream_revision': spec['upstream_revision'],
        'hypothesis': spec['hypothesis'], 'body': source['body'], 'posture': posture,
        'measurement': {'frames': 1}}, ensure_ascii=False) + '\n')
    execute([str(WORKSPACE / 'target/release/vocal-cli'), 'area', str(case), str(output)])
    data = np.genfromtxt(output, delimiter=',', names=True)
    return np.column_stack([data[column] for column in GRID])


def color(rms, setting):
    low, high = setting['pressure_limits_dyn_cm2']
    level = max(0., min(1., log10(rms / low) / log10(high / low))) ** setting['intensity_exponent'] if rms > 0 else 0.
    for (left, a), (right, b) in zip(setting['palette'], setting['palette'][1:]):
        if level <= right:
            blend = (level - left) / (right - left)
            channels = [floor((1 - blend) * int(a[i:i+2], 16) + blend * int(b[i:i+2], 16) + .5)
                        for i in (1, 3, 5)]
            return level, int.from_bytes(bytes(channels), 'big')
    raise ValueError('圧力の色の上限が登録条件にありません')


def expected_rings(grid, scale, eye, setting, nodes=(), pressure=()):
    direction = np.array([-1., 0.])
    for i, data in enumerate(grid):
        inner, outer = np.array(data[1:3]), np.array(data[3:5])
        delta = outer - inner
        if (distance := hypot(*delta)) > setting['direction_threshold_cm']:
            direction = delta / distance
        if i % setting['grid_stride']:
            continue
        gap, area, along = data[8:11]
        radius = gap / 2
        width = 0. if gap <= setting['minimum_gap_cm'] else min(scale * setting['width_limit_per_body_scale'], 2 * area / (pi * gap))
        center = outer - radius * direction
        vertices = []
        for j in range(setting['segments'] + 1):
            angle = 2 * pi * j / setting['segments']
            vertices.extend([*(center + radius * cos(angle) * direction), width * sin(angle)])
        viewing_ray = eye - np.r_[center, 0.]
        normal = np.r_[direction[1], -direction[0], 0.]
        fade = 1 - .65 * (float(normal @ viewing_ray) / (hypot(*viewing_ray) or 1.)) ** 2
        if len(nodes):
            node = int(np.argmin(np.abs(nodes - along)))
            rms = pressure[node]
            level, hue = color(rms, setting)
            opacity = (.25 + .65 * level) * fade
        else:
            node = rms = level = None
            hue = int(setting['neutral_color'][1:], 16)
            opacity = .45 * fade
        yield {'row': i, 'node': node, 'rms': rms, 'level': level, 'color': hue, 'opacity': opacity,
               'vertices': np.asarray(vertices, dtype=np.float32), 'width': width}


def gap(left, right):
    a, b = np.asarray(left, dtype=float), np.asarray(right, dtype=float)
    if a.shape != b.shape or not (np.isfinite(a).all() and np.isfinite(b).all()):
        raise ValueError(f'照合する配列の形状または有限性が異なります ({a.shape}, {b.shape})')
    return float(np.max(np.abs(a - b), initial=0))


def compare_rings(expected, drawn, setting, *, provenance=False):
    xyz = opacity = level = 0.
    styles_match = len(expected) == len(drawn)
    for a, b in zip(expected, drawn):
        xyz = max(xyz, gap(a['vertices'], b['vertices']))
        opacity = max(opacity, abs(a['opacity'] - b['opacity']))
        styles_match &= a['color'] == b['color']
        if provenance:
            styles_match &= all(a[key] == b[key] for key in ('row', 'node', 'rms'))
            if a['level'] is None or b['level'] is None:
                styles_match &= a['level'] is b['level']
            else:
                level = max(level, abs(a['level'] - b['level']))
    return bool(styles_match and xyz <= setting['geometry_tolerance_cm']
                and max(level, opacity) <= setting['level_and_opacity_tolerance']), [xyz, opacity, level]


def controlled(data, spec):
    cfg, setting = spec['diagnostic'], spec['render']
    nodes = positions(cfg['lengths_cm'], cfg['n_pharynx'], cfg['n_oral'])
    expected = list(expected_rings(data['grid'], cfg['body_scale'], np.array(cfg['eye']), setting,
                                   nodes, cfg['pressure_dyn_cm2']))
    candidate, first = compare_rings(expected, data['rings'], setting, provenance=True)
    upstream, second = compare_rings(expected, data['upper'], setting)
    checks = {'control_node_positions': gap(nodes, data['nodes']) == gap(nodes, data['upperNodes']) == 0,
              'control_ring_geometry_and_style': candidate and upstream,
              'control_closure_width_cap_and_tie': expected[0]['node'] == 0 and expected[1]['width'] == expected[2]['width'] == 0
                  and expected[-1]['width'] == cfg['body_scale'] * setting['width_limit_per_body_scale'],
              'control_pressure_palette': all(abs(color(row['rms'], setting)[0] - row['level'])
                  <= setting['level_and_opacity_tolerance'] and abs(row['upperLevel'] - row['level'])
                  <= setting['level_and_opacity_tolerance'] and color(row['rms'], setting)[1] == row['color'] == row['upperColor']
                  for row in data['palette'])}
    return checks, {'candidate_errors': first, 'upper_errors': second, 'nodes_cm': nodes.tolist(),
                    'chosen_nodes': [ring['node'] for ring in expected], 'palette': data['palette']}


def image_delta(paths, artifacts, before, after):
    with Image.open(artifacts / paths[before]) as a, Image.open(artifacts / paths[after]) as b:
        first, second = (np.asarray(image.convert('RGB'), dtype=np.int16) for image in (a, b))
    if first.shape != second.shape:
        raise ValueError(f'比較画像の大きさが異なります ({first.shape}, {second.shape})')
    return int(np.any(abs(first - second) >= 8, axis=2).sum())


def browser_metrics(spec, viewport, sources, native, artifacts, execute):
    setting, options = spec['render'], spec['browser']
    rate = options['sample_rate_hz']
    states = [*viewport['paused'], viewport['started'], *viewport['live'], *viewport['held'], viewport['restored']]
    maximum = np.zeros(3)
    max_native = max_node = 0.
    rings_match = rows_match = True
    for state in states:
        for voice, (head, source) in enumerate(zip(state['heads'], sources, strict=True), 1):
            clock = head['clock']
            index = min(len(source['pressure']) - 1, floor(clock['time'] * rate / source['hop'] + 1e-6))
            rows_match &= (head['index'] == index and head['sample'] == index * source['hop']
                           and clock['epoch'] == state['epoch'] and abs(clock['time'] * rate - state['sample']) <= .500001)
            playing = clock['playing']
            nodes = positions(source['lengths'][index], source['pharynx'], source['oral']) if playing else []
            max_node = max(max_node, gap(nodes, head['nodes']))
            key = (voice, index)
            if key not in native:
                native[key] = cli_grid(source, index, voice, spec, artifacts, execute)
            max_native = max(max_native, gap(native[key], head['grid']))
            expected = list(expected_rings(native[key], head['scale'], np.array(head['eye']), setting,
                                           nodes, source['pressure'][index] if playing else []))
            matched, delta = compare_rings(expected, head['rings'], setting, provenance=True)
            rings_match &= matched
            maximum = np.maximum(maximum, delta)
    live = viewport['live']
    active = next(state for state in live if state['sample'] == options['photo_sample'])
    stationary = next(state for state in viewport['paused'] if state['sample'] == options['photo_sample'])
    same_pose = all(a['grid'] == b['grid'] and a['eye'] == b['eye']
                    for a, b in zip(active['heads'], stationary['heads'], strict=True))
    pressure_colors = image_delta(viewport['photos'], artifacts, 'paused', 'playing')
    toggle_colors = image_delta(viewport['photos'], artifacts, 'paused', 'hidden')
    checks = {'no_page_error': not viewport['errors'], 'track_rows': bool(rows_match),
        'cli_grid_matches_browser': max_native <= setting['geometry_tolerance_cm'],
        'node_positions': max_node <= setting['position_tolerance_cm'], 'actual_vertices_opacity_color': rings_match,
        'started_and_exact_live_seeks': all(head['clock']['playing'] for head in viewport['started']['heads'])
            and all(state['sample'] == target and all(head['clock']['playing'] for head in state['heads'])
                    for state, target in zip(live, options['live_seeks'], strict=True)),
        'paused_samples_and_hold': [state['sample'] for state in viewport['paused']] == spec['samples']
            and all(not head['clock']['playing'] for state in [*viewport['paused'], *viewport['held']]
                    for head in state['heads']) and viewport['held'][0] == viewport['held'][1],
        'same_pose_pressure_pixels': same_pose and pressure_colors >= options['minimum_picture_changed_pixels'],
        'toggle_hides_and_restores': viewport['hidden']['sample'] == viewport['restored']['sample'] == options['photo_sample']
            and all(not head['rings'] for head in viewport['hidden']['heads'])
            and viewport['restored']['heads'][options['photo_voice'] - 1]['rings'] == stationary['heads'][options['photo_voice'] - 1]['rings']
            and toggle_colors >= options['minimum_picture_changed_pixels'],
        'two_voices_distinguished': all(head['nodes'] for head in active['heads'])
            and active['heads'][0]['nodes'] != active['heads'][1]['nodes']
            and [ring['color'] for ring in active['heads'][0]['rings']] != [ring['color'] for ring in active['heads'][1]['rings']]}
    return checks, {'width': viewport['width'], 'frames_per_voice': len(states), 'cli_grid_max_cm': max_native,
                    'node_max_cm': max_node, 'vertex_opacity_level_errors': maximum.tolist(),
                    'pressure_changed_pixels': pressure_colors, 'toggle_changed_pixels': toggle_colors,
                    'same_photo_pose': same_pose}


def upper_metrics(spec, data, viewport, sources):
    setting = spec['render']
    max_node = 0.
    raw_distance = raw_area = cached_distance = cached_area = 0.
    original = shared_grid = raw_match = cache_explained = True
    reports = []
    for voice, (upper_rows, source) in enumerate(zip(data, sources, strict=True)):
        previous = None
        for upper, state in zip(upper_rows, viewport['paused'], strict=True):
            head = state['heads'][voice]
            index = head['index']
            nodes = positions(source['lengths'][index], source['pharynx'], source['oral'])
            max_node = max(max_node, gap(nodes, upper['nodes']))
            candidate = np.asarray(head['grid'])[:, UPPER_COLUMNS]
            reference = np.asarray(upper['grid'])
            raw = np.asarray(upper['rawGrid'])
            raw_match &= candidate.shape == raw.shape
            tolerance = setting['geometry_tolerance_cm']
            if candidate.shape == raw.shape:
                raw_distance = max(raw_distance, gap(candidate[:, UPPER_DISTANCES], raw[:, UPPER_DISTANCES]))
                raw_area = max(raw_area, gap(candidate[:, 5], raw[:, 5]))
            if raw.shape == reference.shape:
                distances = gap(raw[:, UPPER_DISTANCES], reference[:, UPPER_DISTANCES])
                area = gap(raw[:, 5], reference[:, 5])
            else:
                distances = area = None
            cache_reused = previous and upper['cacheKey'] == previous['cacheKey'] and upper['grid'] == previous['grid']
            if distances is not None:
                cached_distance = max(cached_distance, distances)
                cached_area = max(cached_area, area)
                cache_explained &= max(distances, area) <= tolerance or bool(cache_reused)
            else:
                cache_explained &= bool(cache_reused)
            eye, p = np.array(head['eye']), source['pressure'][index]
            expected = list(expected_rings(head['grid'], head['scale'], eye, setting, nodes, p))
            matches, shared_errors = compare_rings(expected, upper['shared'], setting)
            shared_grid &= matches
            normalized = [[0, *r[:4], 0, 0, 0, *r[4:]] for r in reference]
            expected_upper = list(expected_rings(normalized, upper['bodyScale'], eye, setting, nodes, p))
            matches, upper_errors = compare_rings(expected_upper, upper['actual'], setting)
            original &= matches and upper['sample'] == state['sample'] and upper['row'] == index
            mapped = [x['node'] for x in expected]
            upper_mapped = [x['node'] for x in expected_upper]
            reports.append({'sample': state['sample'], 'voice': voice + 1, 'row': index,
                'grid_rows': [len(candidate), len(reference)], 'cache_reused': bool(cache_reused),
                'cache_distance_cm': distances, 'cache_area_cm2': area,
                'same_node_assignments': mapped == upper_mapped, 'shared_grid_errors': shared_errors,
                'upper_grid_errors': upper_errors, 'last_three_node_pressure_dyn_cm2': p[-3:].tolist(),
                'last_cell_area_cm2': source['areas'][index][-1],
                'terminal_ring_width_cm': expected[-1]['width'],
                'last_rings': [{key: ring[key] for key in ('row', 'node', 'rms', 'level', 'width')} for ring in expected[-4:]]})
            previous = upper
    closed_at = spec['browser']['photo_sample']
    female = spec['browser']['photo_voice']
    closed, opened = [row for row in reports if row['voice'] == female and row['sample'] >= closed_at][:2]
    other = next(row for row in reports if row['voice'] != female and row['sample'] == closed_at)
    saturation = setting['pressure_limits_dyn_cm2'][-1]
    contrasting_closure = (closed['last_cell_area_cm2'] == closed['terminal_ring_width_cm'] == 0
        and closed['last_three_node_pressure_dyn_cm2'][-1] == 0
        and other['last_three_node_pressure_dyn_cm2'][-1] > 0 and other['terminal_ring_width_cm'] > 0
        and opened['terminal_ring_width_cm'] > 0 and opened['last_cell_area_cm2'] > 0
        and any(ring['rms'] >= saturation for ring in closed['last_rings'])
        and all(ring['rms'] < saturation for ring in opened['last_rings']))
    return {'upper_positions_and_actual_draw': original and max_node <= setting['position_tolerance_cm'],
            'upper_shared_grid_draw': shared_grid,
            'upper_raw_grid_and_cache': raw_match and cache_explained and max(raw_distance, raw_area) <= tolerance,
            'closure_release_and_pressure_gradient': bool(contrasting_closure)}, {
                'node_max_cm': max_node, 'raw_grid_max_distance_cm': raw_distance, 'raw_grid_max_area_cm2': raw_area,
                'cache_max_distance_cm': cached_distance, 'cache_max_area_cm2': cached_area, 'samples': reports}


def measure(spec, artifacts, execute, bun):
    execute(['cargo', 'build', '--locked', '--release', '-p', 'vocal-cli'])
    execute([*bun, 'test', 'tests/tele.test.ts', 'tests/expression.test.ts'], cwd=UPSTREAM)
    execute([*bun, 'run', 'build'], cwd=WEB)
    execute([*bun, str(CAPTURE), str(CASE), str(UPSTREAM), str(artifacts)], cwd=WEB)
    source = [track(DEMO / f'voice-{i}.tele', spec['browser']['sample_rate_hz']) for i in (1, 2)]
    browser = read_json(artifacts / 'browser-pressure.json')
    upper = read_json(artifacts / 'upstream-pressure.json')
    checks, diagnostics = controlled(upper['control'], spec)
    viewports, native = [], {}
    for viewport in browser['viewports']:
        passed, metrics = browser_metrics(spec, viewport, source, native, artifacts, execute)
        checks.update({f'{viewport["width"]}_{key}': value for key, value in passed.items()})
        viewports.append(metrics)
    passed, original = upper_metrics(spec, upper['voices'], browser['viewports'][0], source)
    checks.update(passed)
    return {'checks': checks, 'browser': browser['browser'], 'diagnostic': diagnostics,
            'viewports': viewports, 'upstream': original}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', args.run_id):
        parser.error('英数字で始まる実行IDが必要です')
    spec = read_json(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != spec['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True):
        parser.error('変更のない固定上流版が必要です')
    ref = spec['reference']
    expression = prior(ref['expression_run'], 'duet-head-expression', revision, ref['expression_manifest_sha256'])
    if sha256(UPPER_WASM) != ref['upper_wasm_sha256'] or any(
            sha256(DEMO / f'voice-{i}.tele') != digest for i, digest in enumerate(ref['track_sha256'], 1)):
        parser.error('登録済みの上流WASM・テレメトリが必要です')
    bun = ['bun'] if shutil.which('bun') else ['npx', '--yes', '--package=bun@1.4.4', '--', 'bun']
    paths = ('src/show/tele.ts', 'src/wasm/engine.ts', 'src/ui/components/DuetPage.tsx', 'src/ui/components/AnatomyView3D.tsx',
             'src/ui/analysis.ts', 'src/ui/colors.ts', 'src/ui/render/anatomy3d.ts', 'src/ui/render/beams3d.ts',
             'tests/tele.test.ts', 'tests/expression.test.ts')
    details = {'case_id': spec['id'], 'upstream_revision': revision, 'bun': subprocess.check_output([*bun, '--version'], text=True).strip(),
               'upstream_wasm_sha256': ref['upper_wasm_sha256'],
               'upstream_source_sha256': {name: sha256(UPSTREAM / name) for name in paths}}
    inputs = [CASE, CAPTURE, Path(__file__), Path(shared.__file__), Path(__file__).with_name('measure_duet_heads.py'),
              expression[0] / 'manifest.json', *sorted(DEMO.iterdir()), *web_sources(), *shared.candidate_sources()]
    return shared.record_measurement(args.run_id, CASE, inputs, details,
        lambda artifacts, execute: measure(spec, artifacts, execute, bun), command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
