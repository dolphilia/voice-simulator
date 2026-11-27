"""発話の声道断面と時系列の選択を、CLI、固定上流、独立した描画計算で照合する。"""

import argparse
import csv
import json
from pathlib import Path
import re
import shutil
import subprocess

import numpy as np
from scipy.io import wavfile

import measure_bilabial_stop as stop
import measure_speech_timing as timing
import measure_uniform_tube as shared
import measure_wasm_fixed as wasm
from measure_fan_crossing_allocations import run_manifest, verified_path
from measure_worklet_fixed import CAPTURE, ROOT, WEB, web_sources
from upstream_baseline import UPSTREAM, WORKSPACE, sha256

CASE = WORKSPACE / 'cases/worklet-tract-profile.json'
ACOUSTICS_CASE = WORKSPACE / 'cases/worklet-tract-acoustics.json'
DYNAMIC_3D_CASE = WORKSPACE / 'cases/worklet-tract-3d-dynamic.json'
LIVE_3D_CASE = WORKSPACE / 'cases/worklet-tract-3d-live.json'
FIELDS = ('length_cm', 'area_cm2', 'minimum_area_cm2')
ACOUSTIC_FIELDS = ('pressure_dyn_cm2', 'outward_flow_cm3_s')


def cell_label(cell, pharynx_count):
    return ('pharynx', cell) if cell < pharynx_count else ('oral', cell - pharynx_count)


def read_profile(path, points, counts, fields):
    cells = sum(counts)
    values = []
    with path.open(newline='') as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != ['frame', 'tube', 'cell', *fields]:
            raise ValueError(f'{path.name} の観測列が一致しません')
        for index, row in enumerate(reader):
            sample, cell = divmod(index, cells)
            order = (row['tube'], int(row['cell']))
            if (sample >= len(points) or int(row['frame']) != points[sample]
                    or order != cell_label(cell, counts[0])):
                raise ValueError(f'{path.name} の観測時刻またはセル順が一致しません（データ行 {index + 1}）')
            values.append([float(row[key]) for key in fields])
    return np.asarray(values).reshape(len(points), cells, len(fields))


def compare_cells(actual, reference, points, counts, fields, tolerance):
    if not np.isfinite(reference).all():
        raise ValueError('基準の声道観測に非有限値があります')
    delta = abs(actual - reference)
    results = {}
    for i, (key, limit) in enumerate(zip(fields, tolerance, strict=True)):
        def earliest(mask):
            matches = np.argwhere(mask)
            if not len(matches):
                return None
            sample, cell = matches[0]
            tube, index = cell_label(int(cell), counts[0])
            return {'frame': int(points[sample]), 'tube': tube, 'cell': index,
                    'browser': float(actual[sample, cell, i]),
                    'reference': float(reference[sample, cell, i])}

        results[key] = {'maximum_absolute_error': float(delta[:, :, i].max()), 'tolerance': limit,
                        'first_difference': earliest(delta[:, :, i] != 0),
                        'first_over_tolerance': earliest(delta[:, :, i] > limit)}
    return results


def compare_display(views, options, points, geometry):
    max_length = float(geometry[:, :, 0].sum(axis=1).max())
    max_diameter = float(np.sqrt(4 * geometry[:, :, 1] / np.pi).max())
    selected = options['selected_output_frames']
    latest = np.searchsorted(points, selected, side='right') - 1
    expected = [int(points[i]) if i >= 0 else None for i in latest]
    correct_selection = (expected == options['expected_observed_frames']
                         and [v['viewportWidth'] for v in views] == options['viewport_widths_css_px'])
    results = []
    for view in views:
        width = view['viewportWidth']
        selections = view['selections']
        correct_selection &= [v['selected'] for v in selections] == selected
        for i, entry in zip(latest, selections):
            frame = int(points[i]) if i >= 0 else None
            plot = entry['plot']
            correct_selection &= (entry['observedFrame'] == frame
                                  and entry['missing'] == (i < 0) and (plot is None) == (i < 0))
            if i < 0 or plot is None:
                continue
            x0, x1 = plot['xAxis']
            y0, y1 = plot['yAxis']
            if not 0 < plot['cssWidth'] <= width or not (x0 < x1 and y0 < y1):
                raise ValueError('断面図の表示幅または軸が無効です')
            positions = x0 + (x1 - x0) * np.r_[0, np.cumsum(geometry[i, :, 0])] / max_length
            errors = {}
            for j, name in enumerate(('average', 'minimum'), start=1):
                relative_diameter = np.sqrt(4 * geometry[i, :, j] / np.pi) / max_diameter
                height = (y1 - y0) * relative_diameter
                target = np.column_stack((positions[:-1], np.diff(positions),
                                          (y0 + y1 - height) / 2, height))
                rectangles = np.asarray(plot[name], dtype=float)
                if rectangles.shape != target.shape or not np.isfinite(rectangles).all():
                    raise ValueError('断面図の矩形数または座標が条件外です')
                errors[name] = float(abs(rectangles - target).max())
            results.append({'viewport_width_css_px': width, 'plot_width_css_px': plot['cssWidth'],
                            'selected_frame': entry['selected'], 'observed_frame': frame,
                            'maximum_absolute_coordinate_error': errors})
    svg = bool(results) and all(
        max(row['maximum_absolute_coordinate_error'].values()) <= options['svg_coordinate_tolerance']
        for row in results)
    return bool(correct_selection), svg, results


def compare_acoustic_display(views, points, counts, geometry, states, tolerance):
    scale = np.maximum(1, abs(states).max(axis=(0, 1)))
    length_limit = geometry[:, :, 0].sum(axis=1).max()
    indices = [counts[0] - 1, counts[0], sum(counts) - 1]
    units = (' dyn/cm²', ' cm³/s')
    results = []
    readouts_match = True
    for view in views:
        for item in view['selections']:
            frame = item['observedFrame']
            if frame is None:
                readouts_match &= 'acoustics' not in item and 'cellReadouts' not in item
                continue
            i = int(np.searchsorted(points, frame))
            if i == len(points) or points[i] != frame:
                raise ValueError('圧力・流量の表示時刻が観測と一致しません')
            x0, x1 = item['plot']['xAxis']
            edges = x0 + (x1 - x0) * np.r_[0, np.cumsum(geometry[i, :, 0])] / length_limit
            positions = ((edges[:-1] + edges[1:]) / 2, edges[1:])
            errors = {}
            for axis, name in enumerate(('pressure', 'flow')):
                display = item['acoustics'][name]
                top, bottom = display['range']
                center, radius = (top + bottom) / 2, (bottom - top) / 2
                target = np.column_stack((positions[axis], center - radius * states[i, :, axis] / scale[axis]))
                plotted = np.asarray(display['points'], dtype=float)
                if plotted.shape != target.shape or not np.isfinite(plotted).all() or radius <= 0:
                    raise ValueError('圧力・流量の点数または描画座標が条件外です')
                errors[name] = max(float(abs(plotted - target).max()), abs(display['zero'] - center))
            readouts = item['cellReadouts']
            readouts_match &= [reading['index'] for reading in readouts] == indices
            for reading in readouts:
                for axis, name in enumerate(('pressure', 'flow')):
                    value = reading[name]
                    numeric = float(value.removesuffix(units[axis]))
                    expected = states[i, reading['index'], axis]
                    readouts_match &= bool(value.endswith(units[axis])
                                           and np.isclose(numeric, expected, rtol=5.1e-5, atol=0))
            results.append({'width_css_px': view['viewportWidth'], 'frame': frame,
                            'maximum_absolute_coordinate_error': errors})
    return (bool(results) and all(max(r['maximum_absolute_coordinate_error'].values()) <= tolerance
                                  for r in results), readouts_match, results)


def compare_acoustics(case, options, profile, points, counts, geometry, native, upstream, dense, views, factor):
    acoustic_report = profile.get('acoustics', {})
    if acoustic_report.get('columns') != ['frame', *ACOUSTIC_FIELDS]:
        raise ValueError('ブラウザの圧力・流量の列が登録条件と一致しません')
    rows = np.asarray(acoustic_report.get('rows'), dtype=float)
    cells = sum(counts)
    if rows.shape != (len(points), 1 + 2 * cells) or not np.isfinite(rows).all():
        raise ValueError('ブラウザの圧力・流量の件数または有限性が条件外です')
    states = rows[:, 1:].reshape(len(points), cells, 2)
    tolerance = (case['pressure_tolerance_dyn_cm2'], case['flow_tolerance_cm3_s'])
    cli = compare_cells(states, native, points, counts, ACOUSTIC_FIELDS, (0, 0))
    upper = compare_cells(states, upstream, points, counts, ACOUSTIC_FIELDS, tolerance)
    pressure, flow = case['required_reference_columns']

    closed = np.asarray(case['closed_frames'])
    closed_indices = np.searchsorted(points, closed)
    released = case['released_frame']
    release_index = int(np.searchsorted(points, released))
    if not np.array_equal(points[closed_indices], closed) or points[release_index] != released:
        raise ValueError('登録した閉鎖・開口が観測時刻に含まれていません')
    observed = states[closed_indices, -1, :]
    internal_steps = np.diff(closed) * factor
    rates = np.asarray([case['mouth_pressure_decay_per_internal_sample'],
                        case['mouth_flow_decay_per_internal_sample']])
    predicted = observed[:-1] * rates ** internal_steps[:, None]
    relative = case['decay_relative_tolerance']
    p_ratio = float(observed[1, 0] / predicted[0, 0]) if predicted[0, 0] else None
    q_ratios = [float(a / b) if b else None for a, b in zip(observed[1:, 1], predicted[:, 1], strict=True)]
    absolute_release = float(abs(states[release_index, -1, 1]))
    svg, readouts, chart = compare_acoustic_display(
        views, points, counts, geometry, states, options['svg_coordinate_tolerance'])
    numbers = [{'frame': int(point), 'mouth_pressure_dyn_cm2': float(p), 'mouth_flow_cm3_s': float(q),
                'pressure_two_cells_behind_lips_dyn_cm2': float(states[i, -3, 0])}
               for point, i, (p, q) in zip(closed, closed_indices, observed, strict=True)]
    return {
        'acoustic_clock_and_finiteness': np.array_equal(rows[:, 0], points),
        'acoustic_state_cli': all(v['first_difference'] is None for v in cli.values()),
        'acoustic_state_upstream': all(v['first_over_tolerance'] is None for v in upper.values()),
        'acoustic_refs_at_glottis_and_mouth': (np.array_equal(states[:, 0, 0], dense[pressure][points])
                                               and np.array_equal(states[:, -1, 1], dense[flow][points])),
        'acoustic_closed_branch_and_radiator_decay': bool(
            (dense['lip_minimum_cm2'][closed[0]:closed[-1]+1] < case['pressure_decay_area_is_closed_cm2']).all()
            and (states[closed_indices, -2, 1] == 0).all()
            and p_ratio is not None and abs(p_ratio - 1) <= relative
            and all(q is not None and abs(q - 1) <= relative for q in q_ratios)),
        'acoustic_mouth_flow_restored': absolute_release >= case['released_min_absolute_mouth_flow_cm3_s'],
        'acoustic_display_projection': svg,
        'acoustic_cell_readouts': readouts,
    }, {
        'cli': cli, 'upstream': upper, 'closed_mouth': numbers,
        'mouth_pressure_decay_observed_over_prediction': p_ratio,
        'mouth_flow_decay_observed_over_prediction': q_ratios,
        'released_absolute_mouth_flow_cm3_s': absolute_release, 'display': chart,
    }


def compare(case, ipa, ipa_path, source, artifacts, execute, bun, acoustics=None, dynamic=None, live=None, prior=None):
    options = case['measurement']
    expected = ipa['measurement']
    rate, internal, frames = (expected[key] for key in ('output_rate_hz', 'internal_rate_hz', 'output_frames'))
    stride = options['profile_stride_output_frames']
    points = np.minimum(np.arange(stride, frames + stride, stride), frames) - 1
    counts = options['expected_tube_cell_counts']
    acoustic_dx_min = 35000 / internal / 0.93
    independent_counts = [max(8, int((neutral - travel) / acoustic_dx_min))
                          for neutral, travel in ((8.7, 1.6), (8.3, 1.0))]

    execute([*bun, 'run', 'build'], cwd=WEB, stdout=artifacts / 'browser-build.log')
    module = artifacts / 'vocal_wasm.wasm'
    shutil.copyfile(WORKSPACE / wasm.WASM, module)
    capture_case = LIVE_3D_CASE if live else DYNAMIC_3D_CASE if dynamic else CASE
    capture_args = [str(CASE), str(DYNAMIC_3D_CASE)] if live else [str(CASE)] if dynamic else ['--acoustics'] if acoustics else []
    execute(['node', str(CAPTURE), str(artifacts), str(ipa_path), str(capture_case), *capture_args])
    report = wasm.read_json(artifacts / 'browser.json')
    browser = wasm.read_json(artifacts / 'browser-run.json')
    browser_rate, browser_pcm = wavfile.read(artifacts / 'browser.wav')

    settings = wasm.read_json(source)
    limits = settings['measurement']
    settings['speech_voice']['tract_profile_frames'] = points.tolist()
    if acoustics:
        settings['speech_voice']['tract_profile_acoustics'] = True
    native_case = artifacts / 'profile-case.json'
    native_case.write_text(json.dumps(settings, ensure_ascii=False, indent=2) + '\n')
    suites = ['geometry_continuity', 'engine']
    if acoustics:
        suites.append('airway_adversarial')
    cli, cli_csv, paths, upper_csv, upper_raw, upper_plan = stop.capture(
        native_case, limits['host_block_frames'], artifacts, execute, suites)
    native_rate, native_pcm = wavfile.read(paths[0][0])
    upstream_pcm = np.fromfile(upper_raw, dtype='<f4')
    if any(pcm.shape != (frames,) or pcm.dtype != np.float32 for pcm in (browser_pcm, native_pcm, upstream_pcm)):
        raise ValueError('ブラウザ、CLI、または上流のPCMの型・長さが条件外です')
    cli_pcm = wasm.compare_pcm(browser_pcm, native_pcm, 0)
    upper_pcm = wasm.compare_pcm(browser_pcm, upstream_pcm, limits['pcm_absolute_tolerance'])
    _, plan = stop.stop_gesture_evidence(settings, {**cli, 'speech': report['speech'],
                                                    'gestures': report['gestures']}, timing.read(upper_plan))

    profile = report.get('tract')
    if profile is None or profile['counts'] != counts:
        raise ValueError('ブラウザの声道断面が無いか、セル数が条件外です')
    rows = np.asarray(profile['rows'], dtype=float)
    if rows.shape != (len(points), 1 + sum(counts) * len(FIELDS)) or not np.isfinite(rows).all():
        raise ValueError('ブラウザの断面の観測数または有限性が条件外です')
    geometry = rows[:, 1:].reshape(len(points), sum(counts), len(FIELDS))
    if (np.any(geometry[:, :, 0] <= 0) or np.any(geometry[:, :, 1:] < 0)
            or np.any(geometry[:, :, 2] - geometry[:, :, 1] > options['area_tolerance_cm2'])):
        raise ValueError('セル長と断面積が物理的な範囲を外れています')
    tolerance = (options['length_tolerance_cm'], options['area_tolerance_cm2'], options['area_tolerance_cm2'])
    fields = (*FIELDS, *ACOUSTIC_FIELDS) if acoustics else FIELDS
    native, upstream = (read_profile(path, points, counts, fields) for path in (cli_csv, upper_csv))
    cli_geometry = compare_cells(geometry, native[:, :, :3], points, counts, FIELDS, tolerance)
    upper_geometry = compare_cells(geometry, upstream[:, :, :3], points, counts, FIELDS, tolerance)
    scalar_lip = {int(row[0]): row[report['columns'].index('lip_minimum_cm2')] for row in report['observations']}
    lips = geometry[:, -1, 2]
    closed = int(np.searchsorted(points, options['closed_profile_frame']))
    opened = int(np.searchsorted(points, options['open_profile_frame']))
    views = wasm.read_json(artifacts / 'tract-display.json')
    selection_ok, svg_ok, display = compare_display(views, options, points, geometry)
    extra_checks, extra = {}, {}
    if acoustics:
        dense_path = artifacts / 'dense-voicing.csv'
        execute(['cargo', 'run', '--locked', '--release', '-p', 'vocal-cli', '--',
                 'render', str(source), str(dense_path)])
        dense = stop.load_trace(dense_path, frames)
        extra_checks, evidence = compare_acoustics(
            acoustics['measurement'], options, profile, points, counts, geometry,
            native[:, :, 3:], upstream[:, :, 3:], dense, views, cli['decimation_factor'])
        extra['acoustics'] = evidence
    if dynamic:
        from measure_worklet_tract_3d import compare_motion

        settings['speech_voice']['tract_profile_grid'] = True
        grid_case = artifacts / 'motion-grid-case.json'
        grid_case.write_text(json.dumps(settings, ensure_ascii=False, indent=2) + '\n')
        cli_grid = artifacts / 'motion-grid-cli.csv'
        upstream_grid = artifacts / 'motion-grid-upstream.csv'
        execute(['cargo', 'run', '--locked', '--release', '-p', 'vocal-cli', '--',
                 'render', str(grid_case), str(cli_grid)])
        probe = artifacts / (stop.PROBE.stem + '.exe')
        upper_grid_pcm = artifacts / 'motion-grid-upstream-pcm.f32'
        execute([str(probe), str(grid_case), str(upstream_grid), str(upper_grid_pcm),
                 str(artifacts / 'motion-grid-upstream-plan.json')], cwd=UPSTREAM)
        extra_checks, extra['dynamic_3d'] = compare_motion(
            dynamic, report, points, lips, cli_grid, upstream_grid, artifacts)
        extra_checks['upstream_grid_capture_preserves_pcm'] = sha256(upper_grid_pcm) == sha256(upper_raw)
    if live:
        from measure_live_tract import compare_live_tract

        live_checks, extra['live_3d'] = compare_live_tract(live, prior, artifacts, browser)
        extra_checks.update(live_checks)
    return {
        'checks': {
            'browser_input_clock_and_wasm_hash': (
                not browser['errors'] and browser['servedWasmSha256'] == sha256(module)
                and report['input'] == expected['expected_ipa'] and report['caseId'] == settings['id']
                and report['sampleRate'] == report['workletSampleRate'] == browser_rate == native_rate == rate
                and report['outputFrames'] == report['framesRendered'] == cli['output_frames'] == frames
                and report['discontinuities'] == 0 and (live is not None or report['firstContextFrame'] == 0)
                and report['shortestQuantum'] == report['longestQuantum'] == expected['expected_render_quantum_frames']
                and cli['decimation_factor'] * rate == internal),
            'upstream_plan': plan['passed'],
            'cli_pcm_bit_equality': cli_pcm['first_bit_difference_frame'] is None,
            'upstream_pcm_tolerance': upper_pcm['first_frame_over_tolerance'] is None,
            'cli_host_partition_invariance': all(sha256(a) == sha256(b) for a, b in zip(*paths, strict=True)),
            'profile_clock_and_cell_counts': np.array_equal(rows[:, 0], points) and counts == independent_counts,
            'cli_geometry': all(field['first_over_tolerance'] is None for field in cli_geometry.values()),
            'upstream_geometry': all(field['first_over_tolerance'] is None for field in upper_geometry.values()),
            'lip_matches_scalar_observation': all(lip == scalar_lip.get(int(frame))
                                                  for frame, lip in zip(points, lips, strict=True)),
            'lip_closure_and_opening': bool(
                points[closed] == options['closed_profile_frame'] and points[opened] == options['open_profile_frame']
                and lips[closed] <= options['closed_lip_maximum_area_cm2']
                and lips[opened] >= options['open_lip_minimum_area_cm2']),
            'selection_and_missing_state': selection_ok,
            'svg_geometry': svg_ok,
            **extra_checks,
        },
        'browser': browser['version'], 'frames': frames, 'observation_count': len(points), 'tube_cell_counts': counts,
        'first_and_last_profile_frames': [int(points[0]), int(points[-1])],
        'cli_pcm': cli_pcm, 'upstream_pcm': upper_pcm, 'upstream_plan': plan,
        'cli_geometry': cli_geometry, 'upstream_geometry': upper_geometry,
        'lip_sections': [
            {'frame': int(points[i]), 'time_seconds': float((points[i] + 1) / rate),
             'total_length_cm': float(geometry[i, :, 0].sum()),
             'mean_area_cm2': float(geometry[i, -1, 1]), 'minimum_area_cm2': float(lips[i])}
            for i in (closed, opened)
        ],
        'display': display,
        **extra,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--acoustics', action='store_true', help='節点圧力と口側の流量も照合する')
    mode.add_argument('--dynamic-3d', action='store_true', help='同じ観測フレームの三次元断面も照合する')
    mode.add_argument('--live-3d', action='store_true', help='実時間の三次元断面と遅延時の保存を照合する')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', args.run_id):
        parser.error('実行IDは英数字で始めてください')
    case = wasm.read_json(CASE)
    acoustics = wasm.read_json(ACOUSTICS_CASE) if args.acoustics else None
    live = wasm.read_json(LIVE_3D_CASE) if args.live_3d else None
    dynamic = wasm.read_json(DYNAMIC_3D_CASE) if args.dynamic_3d or live else None
    if acoustics and (acoustics['tract_case'] != CASE.name or acoustics['upstream_revision'] != case['upstream_revision']):
        raise SystemExit('圧力・流量ケースが参照する基準を確認してください')
    ipa_path = WORKSPACE / 'cases' / case['ipa_case']
    ipa = wasm.read_json(ipa_path)
    if dynamic and (
            dynamic['tract_case'] != CASE.name or dynamic['upstream_revision'] != case['upstream_revision']
            or dynamic['measurement']['profile_stride_output_frames'] != case['measurement']['profile_stride_output_frames']
            or dynamic['measurement']['input_ipa'] != ipa['measurement']['expected_ipa']):
        raise SystemExit('三次元断面ケースが参照する基準を確認してください')
    source = WORKSPACE / 'cases' / ipa['speech_voice_case']
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if (revision != case['upstream_revision'] or revision != ipa['upstream_revision']
            or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True)):
        raise SystemExit('変更のない固定上流版が必要です')
    bun = ['bun'] if shutil.which('bun') else ['npx', '--yes', '--package=bun@1.4.4', '--', 'bun']
    upper_paths = ['src/ui/components/TubeView.tsx', 'src/worklet/processor.ts', 'src/audio/AudioEngine.ts',
                   'crates/chimera/src/voice/human_voice.rs', 'crates/chimera/src/voice/human_airway.rs',
                   'crates/chimera/src/airway/network.rs', 'crates/chimera/tests/geometry_continuity.rs',
                   'crates/chimera/tests/engine.rs']
    inputs = [CASE, ipa_path, source, Path(__file__).resolve(), stop.PROBE,
              *shared.candidate_sources(), *web_sources(),
              *(Path(tool.__file__) for tool in (stop, timing, shared, wasm)),
              *(WORKSPACE / 'tools' / name for name in ('upstream_baseline.py', 'measure_worklet_fixed.py',
                 'measure_pcm_output.py', 'measure_vowel_voice.py', 'measure_junction.py'))]
    registered = CASE
    if acoustics:
        registered = ACOUSTICS_CASE
        inputs.append(registered)
        upper_paths.append('crates/chimera/tests/airway_adversarial.rs')
    if dynamic:
        registered = DYNAMIC_3D_CASE
        inputs.extend((registered, WORKSPACE / 'tools' / 'measure_worklet_tract_3d.py',
                       WORKSPACE / 'tools' / 'measure_grid.py', WORKSPACE / 'tools' / 'measure_sagittal.py'))
        upper_paths.extend(('src/ui/components/AnatomyView3D.tsx', 'src/ui/render/anatomy3d.ts',
                            'crates/chimera/src/anatomy/human.rs', 'crates/chimera/tests/golden_geometry.rs'))
    prior = None
    if live:
        runtime_path = WORKSPACE / 'cases' / live['realtime_case']
        runtime = wasm.read_json(runtime_path)
        if (live['offline_case'] != DYNAMIC_3D_CASE.name or live['upstream_revision'] != revision
                or runtime['upstream_revision'] != revision or runtime['ipa_case'] != ipa_path.name
                or live['measurement']['stride_output_frames'] != case['measurement']['profile_stride_output_frames']):
            parser.error('実時間の三次元断面ケースが参照する基準を確認してください')
        prior = run_manifest(live['reference']['run'], dynamic['id'], revision)
        manifest = prior[0] / 'manifest.json'
        if prior[1]['status'] != 'pass' or sha256(manifest) != live['reference']['manifest_sha256']:
            parser.error('オフラインの基準マニフェストを照合できません')
        registered = LIVE_3D_CASE
        inputs.extend([registered, runtime_path, manifest, verified_path(prior, 'artifacts/browser.json'),
                       verified_path(prior, 'artifacts/browser.wav'),
                       *(WORKSPACE / 'tools' / name for name in ('measure_live_tract.py', 'measure_worklet_realtime.py',
                                                                  'measure_fan_crossing_allocations.py'))])
    metadata = {'case_id': (live or dynamic or acoustics or case)['id'], 'upstream_revision': revision, 'input_root': '$REPOSITORY',
                'node': subprocess.check_output(['node', '--version'], text=True).strip(),
                'bun': subprocess.check_output([*bun, '--version'], text=True).strip(),
                'upstream_source_sha256': {path: sha256(UPSTREAM / path) for path in upper_paths}}
    return shared.record_measurement(
        args.run_id, registered, inputs, metadata,
        lambda out, run: compare(case, ipa, ipa_path, source, out, run, bun, acoustics, dynamic, live, prior),
        command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
