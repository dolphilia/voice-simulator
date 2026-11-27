"""三次元頭部に入力された調音行と、実際に描いた頂点を照合する。"""

import argparse
import csv
import json
import re
import shutil
import struct
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image

import measure_uniform_tube as shared
from measure_duet_words import prior
from measure_fan_crossing_allocations import verified_path
from measure_wasm_fixed import read_json
from measure_worklet_fixed import ROOT, WEB, web_sources
from upstream_baseline import UPSTREAM, WORKSPACE, sha256

CASE = WORKSPACE / 'cases/duet-heads.json'
DEMO = WEB / 'public/shows/duet-clock'
CAPTURE = WEB / 'tools/capture-duet-heads.mjs'
UPPER_WASM = UPSTREAM / 'target/wasm32-unknown-unknown/release/chimera_wasm.wasm'
AXES = ('jaw', 'tbX', 'tbY', 'ttX', 'ttY', 'ttCurl', 'root', 'lipAp', 'lipProt', 'lipWidth',
        'labiodental', 'velum', 'larynx', 'epilarynx', 'ventricular', 'lateral', 'dorsum')
POSTURE = ('jaw_cm', 'tb_x', 'tb_y', 'tt_x', 'tt_y', 'tip_curl', 'tongue_root_cm',
           'lip_aperture_cm', 'lip_protrusion_cm', 'lip_spread', 'labiodental', 'velum_cm2',
           'larynx_cm', 'epilarynx', 'ventricular', 'lateral', 'dorsum')


def tracks():
    for voice in (1, 2):
        data = (DEMO / f'voice-{voice}.tele').read_bytes()
        v, rate, hop, count, width, axes, *_ = struct.unpack_from('<9I', data, 4)
        if data[:4] != b'CHTL' or v != 1 or axes != len(AXES) or len(data) != 48 + 4 * width * count:
            raise ValueError('照合に使うテレメトリの形式が異なります')
        body = dict(zip(('female', 'child'), struct.unpack_from('<2f', data, 40), strict=True))
        rows = [list(struct.unpack_from('<17f', data, 48 + 4 * (width * i + 11))) for i in range(count)]
        yield {'rate': rate, 'hop': hop, 'body': body, 'rows': rows}


def cli_geometry(voice, index, track, spec, artifacts, execute):
    pose = dict(zip(POSTURE, track['rows'][index], strict=True))
    pose['tongue_body_cm'] = [pose.pop('tb_x'), pose.pop('tb_y')]
    pose['tongue_tip_cm'] = [pose.pop('tt_x'), pose.pop('tt_y')]
    name = f'voice-{voice + 1}-row-{index}'
    source, output = (artifacts / f'{name}.{suffix}' for suffix in ('json', 'csv'))
    source.write_text(json.dumps({'id': name, 'upstream_revision': spec['upstream_revision'],
        'hypothesis': spec['hypothesis'], 'body': track['body'], 'posture': pose, 'measurement': {'frames': 1}},
        ensure_ascii=False) + '\n')
    execute([str(WORKSPACE / 'target/release/vocal-cli'), 'geometry', str(source), str(output)])
    result = {}
    with output.open() as stream:
        for row in csv.DictReader(stream):
            result.setdefault(row['part'], []).append([float(row['x_cm']), float(row['y_cm'])])
    return result


def observations(log):
    yield from log['paused']
    for action in log['live']:
        yield action['first']
        yield action['advanced']
    yield from log['held']


def image_difference(log, artifacts, before, after, voice):
    images = [np.asarray(Image.open(artifacts / log['screenshots'][str(at)][voice - 1]).convert('RGB'), dtype=np.int16)
              for at in (before, after)]
    return int(np.any(np.abs(images[0] - images[1]) >= 12, axis=2).sum())


def maximum_delta(reference, points):
    xy = np.asarray(points).reshape(-1, 2)
    return float(np.max(np.abs(xy - reference))) if len(xy) == len(reference) else None


def cache_control(spec, upper, sources, native, artifacts, execute):
    control = spec['cache_control']
    voice = control['voice'] - 1
    indices = control['rows']
    track = sources[voice]
    result = upper['voices'][voice]['cacheControl']
    unrounded = result['theoreticalPaths']
    registered_axes = [track['rows'][i] for i in indices]
    native_deltas = []
    for index, paths in zip(indices, unrounded, strict=True):
        key = (voice, index)
        if key not in native:
            native[key] = cli_geometry(voice, index, track, spec, artifacts, execute)
        native_deltas.extend(maximum_delta(native[key][part], coords) for part, coords in paths.items())
    head_difference = {part: maximum_delta(np.asarray(unrounded[0][part]).reshape(-1, 2), coordinates)
                       for part, coordinates in unrounded[1].items()}
    checks = {'cache_control_three_decimals_hide_axis_change': result['rowKeys'][0] == result['rowKeys'][1]
              and result['artic'] == registered_axes and registered_axes[0] != registered_axes[1],
              'cache_control_preserves_first_pose_in_each_direction': unrounded[0] != unrounded[1]
              and result['forward'] == [unrounded[0], unrounded[0]] and result['reverse'] == [unrounded[1], unrounded[1]],
              'cache_control_direct_upstream_matches_cli': all(value is not None and
                  value <= spec['geometry_coordinate_tolerance_cm'] for value in native_deltas)}
    return checks, {'voice': voice + 1, 'rows': indices, 'samples': [i * track['hop'] for i in indices],
                    'max_direct_upstream_to_cli_cm': max(value for value in native_deltas if value is not None),
                    'coordinate_differences_between_rows_cm': head_difference}


def measure(spec, artifacts, execute, bun):
    execute(['cargo', 'build', '--locked', '--release', '-p', 'vocal-cli'])
    execute([*bun, 'run', 'build'], cwd=WEB)
    execute([*bun, str(CAPTURE), str(CASE), str(UPSTREAM), str(artifacts)], cwd=WEB)
    browser = read_json(artifacts / 'browser-heads.json')
    upstream = read_json(artifacts / 'upstream-heads.json')
    sources = list(tracks())
    checks = {'case_tracks': all(t['rate'] == spec['sample_rate_hz'] and t['hop'] == spec['recording_hop_samples']
                                 and len(t['rows']) == n for t, n in zip(sources, spec['track_frames'], strict=True)),
              'upstream_axis_order': upstream['keys'] == list(AXES), 'no_browser_errors': not browser['errors']}
    native = {}
    deltas = {}
    viewports = []
    threshold = spec['geometry_coordinate_tolerance_cm']
    rate = spec['sample_rate_hz']
    for log in browser['viewports']:
        width = log['width']
        checks[f'{width}_paused_clock'] = all(row['frame'] == at and row['epoch'] == generation and
            not any(head['clock']['playing'] for head in row['heads']) for generation, (row, at) in
            enumerate(zip(log['paused'], spec['paused_samples'], strict=True)))
        checks[f'{width}_live_seek_first_and_advancing'] = all(
            action['requested'] == target and action['first']['frame'] == target
            and action['advanced']['frame'] >= target + spec['live_advance_samples']
            and action['first']['epoch'] == action['advanced']['epoch'] == len(spec['paused_samples']) + seq
            and all(head['clock']['playing'] for moment in ('first', 'advanced') for head in action[moment]['heads'])
            for seq, (action, target) in enumerate(zip(log['live'], spec['live_seek_samples'], strict=True)))
        checks[f'{width}_pause_retains_geometry'] = log['held'][0] == log['held'][1] and not any(
            head['clock']['playing'] for head in log['held'][0]['heads'])
        checks[f'{width}_canvases'] = all(abs(drawn - int(css * spec['pixel_ratio_limit'])) <= 1
            for canvas in log['canvas'] for drawn, css in zip(canvas['pixels'], canvas['css'], strict=True)) and (
            abs(log['canvas'][0]['y'] - log['canvas'][1]['y']) < 1 if width == spec['viewports'][0][0]
            else log['canvas'][1]['y'] > log['canvas'][0]['y'])
        checks[f'{width}_head_input_matches_oracles'] = True
        checks[f'{width}_geometry_matches_cli'] = True
        checks[f'{width}_direct_upstream_geometry_matches_cli'] = True
        checks[f'{width}_mirrored_views_display_lip_width'] = True
        max_native = 0.0
        count = 0
        for row in observations(log):
            for voice, (head, track, upper) in enumerate(zip(row['heads'], sources, upstream['voices'], strict=True)):
                index = min(len(track['rows']) - 1, row['frame'] // track['hop'])
                # 再生中の表示サンプルは四捨五入されるため、境界の前は秒から整数側を求め直す。
                if head['clock']['playing']:
                    index = min(len(track['rows']) - 1, int(row['time'] * rate / track['hop']))
                upper_indices = {item['time']: item['index'] for item in upper['selections']}
                upper_row = upper['rows'][str(upper_indices[row['time']])]
                checks[f'{width}_head_input_matches_oracles'] &= (
                    head['body'] == track['body'] == upper['body'] and head['clock']['epoch'] == row['epoch']
                    and head['clock']['time'] == row['time'] and index == head['index'] == upper_indices[row['time']]
                    and head['sample'] == index * track['hop'] and head['artic'] == track['rows'][index] == upper_row['artic'])
                key = (voice, index)
                if key not in native:
                    native[key] = cli_geometry(voice, index, track, spec, artifacts, execute)
                geometry = head['geometry']
                camera = np.array(geometry['view']).reshape(4, 4, order='F')
                projection = np.array(geometry['projection']).reshape(4, 4, order='F')
                expected_facing = 1 if voice == 0 else -1
                # 3Dの口唇中心と両端をクリップ座標へ投影する。
                mvp = projection @ camera @ np.diag([expected_facing, 1, 1, 1])
                eyes = [np.asarray(rim).reshape(-1, 3) for rim in geometry['lipRims']]
                check_view = geometry['facing'] == expected_facing and np.sign(camera[0, 2]) == -expected_facing and len(eyes) == 2
                for edge in eyes:
                    clip = mvp @ np.c_[edge[[0, 16, 32]], np.ones(3)].T
                    check_view &= edge[0, 2] < -1 < 1 < edge[-1, 2] and bool(np.all(np.abs(clip[:2] / clip[3]) < 1))
                checks[f'{width}_mirrored_views_display_lip_width'] &= bool(check_view)
                count += 1
                for part, vertices in geometry['paths'].items():
                    xyz = np.asarray(vertices).reshape(-1, 3)
                    ref = np.asarray(native[key][part])
                    checks[f'{width}_geometry_matches_cli'] &= bool(
                        np.isfinite(xyz).all() and (xyz[:, 2] == 0).all() and xyz[:, :2].shape == ref.shape)
                    if xyz[:, :2].shape != ref.shape:
                        continue
                    error = float(np.max(np.abs(xyz[:, :2] - ref)))
                    max_native = max(max_native, error)
                    checks[f'{width}_geometry_matches_cli'] &= error <= threshold
                    direct_delta = maximum_delta(ref, upper_row['rawPaths'][part])
                    checks[f'{width}_direct_upstream_geometry_matches_cli'] &= direct_delta is not None and direct_delta <= threshold
                    if key not in deltas:
                        deltas[key] = {}
                    if part not in deltas[key]:
                        points = upper_row['paths'][part]
                        deltas[key][part] = {'counts': [len(points) // 2, len(ref)], 'max_cm': maximum_delta(ref, points),
                                             'max_uncached_cm': direct_delta}
        checks[f'{width}_geometry_matches_cli'] &= all(len(head['geometry']['paths']) == 11 for record in observations(log)
                                                       for head in record['heads'])
        checks[f'{width}_returns_to_start_pose'] = [head['geometry'] for head in log['paused'][0]['heads']] == [
            head['geometry'] for head in log['paused'][-1]['heads']]
        stats = {'width': width, 'head_frames': count, 'max_cli_to_drawn_cm': max_native}
        for voice, (before, after) in enumerate(((19968, 30720), (30720, 43008)), 1):
            gap = image_difference(log, artifacts, before, after, voice)
            pa, pb = (next(item for item in log['paused'] if item['frame'] == at) for at in (before, after))
            lip = [np.asarray(moment['heads'][voice - 1]['geometry']['paths']['lower_lip']).reshape(-1, 3)
                   for moment in (pa, pb)]
            displacement = float(np.max(np.linalg.norm(lip[0] - lip[1], axis=1)))
            checks[f'{width}_voice_{voice}_articulation_moves_pixels'] = (
                gap >= spec['minimum_changed_pixels_per_head'] and displacement >= spec['minimum_lower_lip_displacement_cm'])
            stats[f'voice_{voice}'] = {'changed_pixels': gap, 'lower_lip_maximum_displacement_cm': displacement}
        viewports.append(stats)
    comparisons = [{'voice': voice + 1, 'row': index, 'captured_sample': index * sources[voice]['hop'], 'paths': paths}
                   for (voice, index), paths in sorted(deltas.items())]
    first = next((item for item in comparisons if any(
        value['max_cm'] is None or value['max_cm'] > threshold for value in item['paths'].values())), None)
    cache_checks, cache_metrics = cache_control(spec, upstream, sources, native, artifacts, execute)
    checks.update(cache_checks)
    return {'checks': checks, 'browser': browser['browser'], 'viewports': viewports,
            'fixed_upstream_first_different_row': first, 'upstream_geometry_comparison': comparisons,
            'cache_control': cache_metrics}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', args.run_id):
        parser.error('英数字で始まる実行IDが必要です')
    spec = read_json(CASE)
    ref = spec['reference']
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != spec['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True):
        parser.error('変更のない固定上流版が必要です')
    telemetry = prior(ref['telemetry_run'], 'duet-telemetry', revision, ref['telemetry_manifest_sha256'])
    words = prior(ref['words_run'], 'duet-words', revision, ref['words_manifest_sha256'])
    discovery = WORKSPACE / 'runs' / spec['cache_control']['discovery_run'] / 'manifest.json'
    for voice, digest in enumerate(ref['track_sha256'], 1):
        relative = f'voice-{voice}.tele'
        if sha256(DEMO / relative) != digest or sha256(verified_path(telemetry, f'artifacts/{relative}')) != digest:
            parser.error('テレメトリが固定基準と異なります')
    if sha256(UPPER_WASM) != ref['upstream_wasm_sha256']:
        parser.error('上流WASMが固定基準と異なります')
    bun = ['bun'] if shutil.which('bun') else ['npx', '--yes', '--package=bun@1.4.4', '--', 'bun']
    upper_paths = ['src/ui/components/DuetPage.tsx', 'src/ui/components/AnatomyView3D.tsx', 'src/ui/analysis.ts',
                   'src/ui/render/anatomy3d.ts', 'src/show/tele.ts', 'src/wasm/chimera.ts', 'tests/tele.test.ts',
                   'tests/transport.test.ts', 'crates/chimera/tests/geometry_continuity.rs']
    details = {'case_id': spec['id'], 'upstream_revision': revision, 'upstream_wasm_sha256': sha256(UPPER_WASM),
               'upstream_source_sha256': {name: sha256(UPSTREAM / name) for name in upper_paths},
               'bun': subprocess.check_output([*bun, '--version'], text=True).strip()}
    inputs = [CASE, CAPTURE, Path(__file__), Path(shared.__file__), discovery,
              *(p / 'manifest.json' for p in (telemetry[0], words[0])),
              *sorted(DEMO.iterdir()), *web_sources(), *shared.candidate_sources()]
    return shared.record_measurement(args.run_id, CASE, inputs, details,
        lambda artifacts, execute: measure(spec, artifacts, execute, bun), command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
