"""体型を切り替えた実時間発話の断面と音響セルを照合する。"""

import argparse
import json
from math import exp, log, pi
from pathlib import Path
import re
import shutil
import subprocess

import numpy as np
from scipy.io import wavfile

import measure_bilabial_stop as stop
import measure_grid as grid
import measure_sagittal as sagittal
import measure_speech_timing as timing
import measure_uniform_tube as shared
import measure_wasm_fixed as wasm
from measure_duet_words import prior
from measure_worklet_fixed import CAPTURE, ROOT, WEB, web_sources
from measure_worklet_tract_3d import AREA_COLUMNS, GRID_COLUMNS, read_motion_grid
from measure_worklet_tract_profile import ACOUSTIC_FIELDS, ACOUSTICS_CASE, FIELDS, read_profile
from upstream_baseline import UPSTREAM, WORKSPACE, sha256

CASE = WORKSPACE / 'cases/worklet-tract-3d-body.json'
IPA_CASE = WORKSPACE / 'cases/worklet-ipa-voice.json'
CLI = WORKSPACE / 'target/release/vocal-cli'
DRAW_CASE = WORKSPACE / 'cases/worklet-tract-3d.json'


def maximum(a, b):
    x, y = np.asarray(a), np.asarray(b)
    if x.shape != y.shape or not (np.isfinite(x).all() and np.isfinite(y).all()):
        raise ValueError(f'比較配列の形または有限性が一致しません ({x.shape}, {y.shape})')
    return float(np.max(np.abs(x - y), initial=0))


def geometry_difference(candidate, reference, points, limit):
    error = maximum(candidate, reference)
    exceed = np.argwhere(np.abs(candidate - reference) > limit)
    hit = None
    if len(exceed):
        i, ray, axis = (int(x) for x in exceed[0])
        hit = {'frame': int(points[i]), 'ray': ray, 'column': GRID_COLUMNS[axis],
               'candidate': float(candidate[i, ray, axis]), 'reference': float(reference[i, ray, axis])}
    return {'maximum_absolute_difference': error, 'first_outside_tolerance': hit}


def exact_body_postures(path, body, points, probe, output, execute):
    records = np.genfromtxt(path, delimiter=',', names=True)
    if not np.array_equal(records['frame'], points) or len(records.dtype.names) != 18:
        raise ValueError('同一姿勢の照合に必要な17軸と観測フレームが揃いません')
    variant = body if isinstance(body, str) else f"{body['female']},{body['child']}"
    result = []
    for point, record in zip(points, records, strict=True):
        pose = {key: float(record[key]) for key in records.dtype.names[1:]}
        pose['tongue_body_cm'] = [pose.pop('tongue_body_x_cm'), pose.pop('tongue_body_y_cm')]
        pose['tongue_tip_cm'] = [pose.pop('tongue_tip_x_cm'), pose.pop('tongue_tip_y_cm')]
        data = output / f'upstream-pose-{point}.csv'
        execute([str(probe), '--body', variant, '--area', *sagittal.pose_controls({'posture': pose})],
                cwd=UPSTREAM, stdout=data)
        result.append(grid.read_grid(data, columns=AREA_COLUMNS))
    return np.asarray(result)


def reference(spec, variant, browser_case, report, output, execute, probes):
    setting = spec['measurement']
    capture = report['tract']
    points = np.asarray([entry['frame'] for entry in capture['grid']['frames']])
    total = report['outputFrames']
    stride = setting['profile_stride_output_frames']
    anticipated = np.minimum(np.arange(stride, total + stride, stride), total) - 1
    if not np.array_equal(points, anticipated):
        raise ValueError('実時間で採った測定線のフレームが登録した間隔と一致しません')
    output.mkdir()
    replay = wasm.read_json(browser_case)
    rates = spec['input']
    execute([str(CLI), 'inspect', str(browser_case)], stdout=output / 'inspect.json')
    execute([str(CLI), 'render-pcm', str(browser_case), str(output / 'native.wav'), str(output / 'native-pcm.csv'), '128'])
    for name, flag in (('grid', 'tract_profile_grid'), ('acoustics', 'tract_profile_acoustics'),
                       ('posture', 'tract_profile_posture')):
        trial = {**replay, 'speech_voice': {**replay['speech_voice'], 'tract_profile_frames': points.tolist(), flag: True}}
        case = output / f'{name}-case.json'
        case.write_text(json.dumps(trial, ensure_ascii=False, indent=2) + '\n')
        execute([str(CLI), 'render', str(case), str(output / f'native-{name}.csv')])
    speech_probe, pose_probe = probes
    execute([str(speech_probe), str(output / 'grid-case.json'), str(output / 'upstream-grid.csv'),
             str(output / 'upstream-pcm.f32'), str(output / 'upstream-plan.json')], cwd=UPSTREAM)
    sections = len(capture['grid']['frames'][0]['rows'])
    native, upper = (read_motion_grid(output / f'{name}-grid.csv', points, sections) for name in ('native', 'upstream'))
    same_pose = exact_body_postures(output / 'native-posture.csv', variant['body'], points, pose_probe, output, execute)
    counts = variant['expected_cells']
    cells = read_profile(output / 'native-acoustics.csv', points, counts, (*FIELDS, *ACOUSTIC_FIELDS))
    cli = wasm.read_json(output / 'inspect.json')
    upper_audio = np.fromfile(output / 'upstream-pcm.f32', dtype='<f4')
    rate, native_pcm = wavfile.read(output / 'native.wav')
    if native_pcm.shape != (total,) or upper_audio.shape != (total,):
        raise ValueError('CLIと固定上流の音声のフレーム数が一致しません')
    speech = replay['speech_voice']
    source_ok = (speech['body'] == variant['body'] and speech['input']['text'] == spec['input']['ipa']
                 and speech['internal_sample_rate_hz'] == rates['internal_rate_hz']
                 and speech['voice']['output_sample_rate_hz'] == rate == rates['output_rate_hz'])
    limit = setting['grid_absolute_tolerance']
    upper_metric = geometry_difference(native, upper, points, limit)
    same_metric = geometry_difference(native, same_pose, points, limit)
    return {'cli': cli, 'pcm': native_pcm, 'grid': native, 'cells': cells, 'points': points, 'source_ok': source_ok,
            'upper': {'same_pose': same_metric, 'own_utterance': upper_metric,
                      'pcm': wasm.compare_pcm(native_pcm, upper_audio, 1e-6)}}


def expected_vertices(rows, count):
    vector = rows[:, 3:5] - rows[:, 1:3]
    lengths = np.linalg.norm(vector, axis=1)
    direction = np.divide(vector, lengths[:, None], where=lengths[:, None] > 0, out=np.zeros_like(vector))
    radius = rows[:, 8] / 2
    width = np.divide(rows[:, 9], pi * radius, where=radius > 0, out=np.zeros_like(radius))
    center = rows[:, 3:5] - direction * radius[:, None]
    theta = 2 * pi * np.arange(count) / count
    xy = center[:, None, :] + (radius[:, None] * np.cos(theta))[..., None] * direction[:, None, :]
    return np.concatenate((xy, (width[:, None] * np.sin(theta))[..., None]), axis=2).reshape(len(rows), -1)


def browser_measurement(spec, variant, prefix, trial, live, native, worklet_hash):
    setting = spec['measurement']
    report = wasm.read_json(prefix.with_suffix('.json'))
    rate, pcm = wavfile.read(prefix.with_suffix('.wav'))
    points = native['points']
    position = {int(frame): index for index, frame in enumerate(points)}
    counts = variant['expected_cells']
    tract = report['tract']
    geometry = np.array([item['rows'] for item in tract['grid']['frames']])
    cells = np.array([row[1:] for row in tract['rows']]).reshape(len(points), sum(counts), 3)
    acoustics = np.array([row[1:] for row in tract['acoustics']['rows']]).reshape(len(points), sum(counts), 2)
    count = wasm.read_json(DRAW_CASE)['measurement']['ring_segments']
    total = report['outputFrames']
    context = report['realtime']['scheduledContextFrame']
    clock_ok = (report['firstContextFrame'] == context and report['discontinuities'] == 0
                and report['shortestQuantum'] == report['longestQuantum'] == 128
                and np.array_equal(np.array(report['realtime']['blocks'])[:, 0], context + np.arange(0, total, 128)))
    browser_frames = [[item['frame'] for item in tract['grid']['frames']],
                      [row[0] for row in tract['rows']], [row[0] for row in tract['acoustics']['rows']]]
    packet_ok = True
    packet_by_frame = {}
    run = trial['run']
    for packet in (value for value in live['packets'] if value['run'] == run):
        frame = packet['frame']
        j = position[frame]
        packed = [*cells[j].ravel(), *acoustics[j].ravel(), len(geometry[j]), *geometry[j].ravel()]
        packet_ok &= (frame not in packet_by_frame and packet['counts'] == counts and packet['contextFrame'] == context + frame
                      and packet['values'][:len(packed)] == packed)
        packet_by_frame[frame] = packet
    draws = [entry for entry in live['draws'] if entry['run'] == run]
    draw_frames = [entry['frame'] for entry in draws]
    draws_ok = draw_frames == sorted(set(draw_frames)) and all(
        entry['frame'] in packet_by_frame and entry['contextFrame'] == context + entry['frame']
        and entry['lipArea'] == cells[position[entry['frame']], -1, 2] for entry in draws)
    speech = report['speech']
    spans = speech['utterances'][0]['segments']
    p = next(item for item in spans if item['segment']['ipa'] == 'p')
    start, end = p['start_seconds'] * rate, p['end_seconds'] * rate
    before = (points + 1 >= spans[0]['start_seconds'] * rate) & (points + 1 < start)
    during = (points + 1 >= start) & (points + 1 <= end)
    after = (points + 1 > end) & (points + 1 <= spans[-1]['end_seconds'] * rate)
    is_closed = ((geometry[:, -1, 8] <= setting['maximum_closed_gap_cm'])
                 & (cells[:, -1, 2] <= setting['maximum_closed_acoustic_area_cm2']))
    is_open = (geometry[:, -1, 9] >= setting['minimum_open_area_cm2']) & (cells[:, -1, 2] >= setting['minimum_open_area_cm2'])
    by_phase = {'before': before & is_open, 'closed': during & is_closed, 'after': after & is_open}
    vertex_error, marker_ok, vertex_records, draw_lookup = 0., True, {}, set(draw_frames)
    for snap in (value for value in live['vertices'] if value['run'] == run):
        phase, frame = snap['phase'], snap['frame']
        index = position[frame]
        raw = geometry[index]
        expected = expected_vertices(raw, count)
        marker = snap['marker']
        marker_error = maximum(marker, expected[-1, :3]) if marker is not None else 0.
        marker_ok &= ((marker is not None) == (raw[-1, 8] == 0)
                      and marker_error <= setting['vertex_geometry_tolerance_cm'])
        vertex_error = max(vertex_error, maximum(snap['vertices'], expected))
        marker_ok &= (snap['ringSegments'] == count and snap['contextFrame'] == context + frame and frame in draw_lookup
                      and (phase == 'first' or by_phase[phase][index]))
        vertex_records[phase] = {'frame': frame, 'gap_cm': raw[-1, 8], 'geometry_area_cm2': raw[-1, 9],
                                'minimum_acoustic_area_cm2': cells[index, -1, 2], 'marker_cm': marker}
    acoustic_limits = wasm.read_json(ACOUSTICS_CASE)['measurement']
    state_errors = [maximum(acoustics[:, :, i], native['cells'][:, :, 3+i]) for i in range(2)]
    grid_error = maximum(geometry, native['grid'])
    pitch = exp(sum(weight * log(anchor) for weight, anchor in zip(variant['weights'], (110, 205, 260), strict=True)))
    plan, delta = timing.compare(speech, {key: native['cli']['speech'][key] for key in speech}, 1e-12)
    gestures, _ = timing.compare(report['gestures'], native['cli']['gestures'], 1e-12)
    pcm_cmp = wasm.compare_pcm(pcm, native['pcm'], 0)
    checks = {'selected_body_and_cli_plan': native['source_ok'] and report['body'] == variant['body']
               and report['input'] == spec['input']['ipa'] and plan is None and gestures is None
               and abs(report['basePitchHz'] - pitch) <= 1e-12,
              'fixed_pcm_and_worklet_clock': bool(clock_ok and pcm_cmp['first_bit_difference_frame'] is None
                 and pcm.dtype == np.float32 and rate == report['sampleRate'] == report['workletSampleRate'] == spec['input']['output_rate_hz']),
              'full_grid_and_cells_match_cli': (tract['counts'] == counts and tract['grid']['columns'] == GRID_COLUMNS
                 and all(np.array_equal(row, points) for row in browser_frames)
                 and grid_error <= setting['grid_absolute_tolerance']
                 and maximum(cells, native['cells'][:, :, :3]) <= setting['grid_absolute_tolerance']
                 and state_errors[0] <= acoustic_limits['pressure_tolerance_dyn_cm2']
                 and state_errors[1] <= acoustic_limits['flow_tolerance_cm3_s']),
              'delivered_packets_and_draws_match_source': bool(packet_ok and draws_ok
                 and report['tractLive']['sent'] == len(packet_by_frame)
                 and report['tractLive']['sent'] + report['tractLive']['skipped'] == len(points)),
              'closed_during_p_and_open_on_both_sides': all(mask.any() for mask in by_phase.values()),
              'drawn_geometry_and_closed_marker': bool(marker_ok and set(vertex_records) == {'first', 'before', 'closed', 'after'}
                 and vertex_error <= setting['vertex_geometry_tolerance_cm']),
              'released_and_ran_current_body': bool(trial['released'] and draws and
                 live['runs'][run]['completedAtMs'] is not None and live['runs'][run]['contextClosedAtMs'] is not None
                 and trial['servedWasmSha256'] == worklet_hash)}
    return checks, {'counts': counts, 'grid_maximum_difference': grid_error, 'acoustics_maximum_differences': state_errors,
                    'vertex_maximum_error_cm': vertex_error, 'frames_drawn': len(draws), 'received': len(packet_by_frame),
                    'canvas_ids': sorted({entry['canvasId'] for entry in draws}), 'selected_draws': vertex_records,
                    'phase_profile_frames': {phase: points[mask].tolist() for phase, mask in by_phase.items()},
                    'plan_maximum_difference': delta, 'pcm': pcm_cmp}


def measure(spec, artifacts, execute, bun):
    execute(['cargo', 'build', '--locked', '--release', '-p', 'vocal-cli'])
    execute(['cargo', 'test', '--locked', '-p', 'chimera', '--test', 'body_mix', '--test', 'golden_geometry',
             '--test', 'stop_spans'], cwd=UPSTREAM, stdout=artifacts / 'upstream-tests.log')
    probes = (shared.build_upstream_probe(stop.PROBE, artifacts, execute, extra_libraries=('serde_json',)),
              shared.build_upstream_probe(sagittal.PROBE, artifacts, execute))
    execute([*bun, 'run', 'build'], cwd=WEB, stdout=artifacts / 'browser-build.log')
    module = WORKSPACE / wasm.WASM
    copied_module = artifacts / 'vocal_wasm.wasm'
    shutil.copyfile(module, copied_module)
    worklet_hash = sha256(copied_module)
    execute(['node', str(CAPTURE), str(artifacts), str(IPA_CASE), str(CASE)], cwd=WEB)
    browser = wasm.read_json(artifacts / 'browser-run.json')
    widths = spec['measurement']['viewport_widths_css_px']
    if [item['width'] for item in browser['viewports']] != widths:
        raise ValueError('登録した画面幅の観測が揃いません')
    variants = {body['id']: body for body in spec['input']['bodies']}
    reference_runs = {}
    checks, sites = {}, {}
    for viewport in browser['viewports']:
        width = viewport['width']
        live = wasm.read_json(artifacts / f'{width}-bodies-live.json')['evidence']
        trials = viewport['trials']
        order = list(variants) if width == widths[0] else list(reversed(variants))
        checks[f'{width}_body_order_and_browser_errors'] = ([trial['label'] for trial in trials] == order and not viewport['errors'])
        sites[width] = {}
        for trial in trials:
            label = trial['label']
            prefix = artifacts / trial['stem']
            exported = artifacts / (trial['stem'] + '-case.json')
            if label not in reference_runs:
                reference_runs[label] = reference(spec, variants[label], exported, wasm.read_json(prefix.with_suffix('.json')),
                                                  artifacts / label, execute, probes)
            desktop_case = artifacts / f'{widths[0]}-{label}-case.json'
            flags, metrics = browser_measurement(spec, variants[label], prefix, trial, live, reference_runs[label],
                                                worklet_hash)
            flags['same_replay_across_viewports'] = sha256(exported) == sha256(desktop_case)
            checks.update({f'{width}_{label}_{key}': condition for key, condition in flags.items()})
            sites[width][label] = metrics
        first, second = (sites[width][label] for label in order)
        checks[f'{width}_switch_clears_previous_and_reuses_canvas'] = (first['counts'] != second['counts']
            and first['canvas_ids'] == second['canvas_ids'] and len(first['canvas_ids']) == 1)
    upper = {label: row['upper'] for label, row in reference_runs.items()}
    checks.update({f'{label}_upper_same_pose': info['same_pose']['first_outside_tolerance'] is None for label, info in upper.items()})
    return {'checks': checks, 'browser': browser['version'], 'viewports': sites, 'upstream': upper}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', args.run_id):
        parser.error('英数字で始まる実行IDが必要です')
    spec = wasm.read_json(CASE)
    rev = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if rev != spec['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True):
        parser.error('変更のない固定上流版が必要です')
    sources = []
    for key, case_id in (('live_geometry', 'worklet-tract-3d-live'), ('body_ipa', 'worklet-ipa-body')):
        item = spec['references'][key]
        directory, _ = prior(item['run'], case_id, rev, item['manifest_sha256'])
        sources.append(directory / 'manifest.json')
    bun = ['bun'] if shutil.which('bun') else ['npx', '--yes', '--package=bun@1.4.4', '--', 'bun']
    paths = ('src/ui/components/AnatomyView3D.tsx', 'src/ui/analysis.ts', 'crates/chimera/src/anatomy/human.rs',
             'crates/chimera/src/voice/human_airway.rs', 'crates/chimera/tests/body_mix.rs', 'crates/chimera/tests/golden_geometry.rs')
    metadata = {'case_id': spec['id'], 'upstream_revision': rev,
        'upstream_source_sha256': {path: sha256(UPSTREAM / path) for path in paths},
        'node': subprocess.check_output(['node', '--version'], text=True).strip(),
        'bun': subprocess.check_output([*bun, '--version'], text=True).strip()}
    inputs = [CASE, IPA_CASE, ACOUSTICS_CASE, DRAW_CASE, CAPTURE, WEB / 'tools/observe-live-tract.mjs', *sources,
              stop.PROBE, sagittal.PROBE, Path(__file__), *web_sources(), *shared.candidate_sources(),
              *(WORKSPACE / 'tools' / name for name in ('measure_uniform_tube.py', 'measure_sagittal.py', 'measure_grid.py',
                 'measure_worklet_tract_profile.py', 'measure_worklet_tract_3d.py', 'measure_speech_timing.py'))]
    return shared.record_measurement(args.run_id, CASE, inputs, metadata,
        lambda artifacts, execute: measure(spec, artifacts, execute, bun), command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
