"""復号した歌唱動画の声道断面を、固定上流とCLIの同じ出力フレームへ照合する。"""

import json

import numpy as np
from PIL import Image
from scipy.spatial import cKDTree

import measure_bilabial_stop as stop
import measure_uniform_tube as shared
import measure_wasm_fixed as wasm
from measure_worklet_tract_3d import GRID_COLUMNS, differences, read_motion_grid
from measure_worklet_tract_profile import FIELDS, compare_cells, read_profile
from upstream_baseline import UPSTREAM, sha256


def reference_grids(source, points, spec, counts, artifacts, execute):
    probe = shared.build_upstream_probe(stop.PROBE, artifacts, execute, extra_libraries=('serde_json',))
    inputs = wasm.read_json(source)
    inputs['song_voice']['tract_profile_frames'] = points.tolist()
    results = {}
    for group in ('grid', 'cells'):
        inputs['song_voice']['tract_profile_grid'] = group == 'grid'
        settings = artifacts / f'tract-{group}-case.json'
        settings.write_text(json.dumps(inputs, ensure_ascii=False, indent=2) + '\n')
        native, upper = [artifacts / f'tract-{group}-{name}.csv' for name in ('cli', 'upstream')]
        execute(['cargo', 'run', '--locked', '--release', '-p', 'vocal-cli', '--',
                 'render', str(settings), str(native)])
        pcm = artifacts / f'tract-{group}-upstream-pcm.f32'
        plan = artifacts / f'tract-{group}-upstream-plan.json'
        execute([str(probe), str(settings), str(upper), str(pcm), str(plan)], cwd=UPSTREAM)
        if group == 'grid':
            arrays = [read_motion_grid(path, points, spec['expected_sections']) for path in (native, upper)]
        else:
            arrays = [read_profile(path, points, counts, FIELDS) for path in (native, upper)]
        results[group] = (*arrays, pcm)
    return results


def decode_crop(clip, rect, name, frame_count, artifacts, execute):
    x, y, width, height = rect
    path = artifacts / f'decoded-{name}.rgb'
    execute(['ffmpeg', '-v', 'error', '-i', str(clip), '-map', '0:v:0',
             '-vf', f'crop={width}:{height}:{x}:{y},format=rgb24', '-fps_mode', 'passthrough',
             '-enc_time_base', '1:1000000', '-threads', '1', '-c:v', 'rawvideo', '-f', 'rawvideo', str(path)])
    if path.stat().st_size != frame_count * width * height * 3:
        raise ValueError('復号画像と映像PTSの個数が一致しません')
    return np.memmap(path, dtype=np.uint8, mode='r', shape=(frame_count, height, width, 3))


def read_frame_codes(images, bits):
    frames, height, width, channels = images.shape
    if width % bits != 0:
        raise ValueError('識別欄の幅がセル数の整数倍ではありません')
    cells = images.reshape(frames, height, bits, width // bits, channels)
    white = cells[:, 4:-4, :, 4:-4, :].mean(axis=(1, 3, 4)) > 128
    return (white @ (2 ** np.arange(bits, dtype=np.int64))) - 1


def projected_lip(row, matrix, width, height, segments):
    inner, outer = row[1:3], row[3:5]
    gap, area = row[8:10]
    delta = outer - inner
    length = np.linalg.norm(delta)
    if gap == 0:
        points = np.array([[*outer, 0.0, 1.0]])
    else:
        if length == 0:
            raise ValueError('開いた測定線の向きを求められません')
        normal = delta / length
        theta = np.arange(segments) * 2 * np.pi / segments
        a = gap / 2
        sagittal = outer + (a * (np.cos(theta) - 1))[:, None] * normal
        points = np.column_stack((sagittal, area / (np.pi * a) * np.sin(theta), np.ones(segments)))
    clip = points @ matrix.T
    ndc = clip[:, :2] / clip[:, 3:]
    pixels = (ndc * [1.0, -1.0] + 1) * [width / 2, height / 2]
    if gap == 0:
        return pixels
    # GPUの線分を、隣の頂点に向かう画面上の分点で近似する。
    roots = pixels[:, None, :]
    steps = np.linspace(0, 1, 9, endpoint=False)[None, :, None]
    return (roots + (np.roll(pixels, -1, axis=0)[:, None, :] - roots) * steps).reshape(-1, 2)


def compare_projection(image, row, matrix, spec):
    red, green, blue = image.astype(np.int16).transpose(2, 0, 1)
    orange = (red - green >= spec['highlight_minimum_r_minus_g']) & (red - blue >= spec['highlight_minimum_r_minus_b'])
    pixels = np.argwhere(orange)[:, ::-1] + 0.5
    height, width = orange.shape
    expected = projected_lip(row, matrix, width, height, spec['ring_segments'])
    if len(pixels):
        observed_to_expected = cKDTree(expected).query(pixels)[0]
        expected_to_observed = cKDTree(pixels).query(expected)[0]
        q = spec['distance_percentile']
        error = float(max(np.percentile(observed_to_expected, q), np.percentile(expected_to_observed, q)))
    else:
        error = None
    return {
        'orange_pixels': len(pixels), 'screen_curve_distance_px': error,
        'passed': error is not None and len(pixels) >= spec['minimum_highlight_pixels']
        and error <= spec['maximum_highlight_distance_px'],
    }


def compare_recorded_tract(registered, source, report, clip, media, fixed_pcm, artifacts, execute):
    spec = registered['measurement']
    record = report['recording']
    visual = record.get('tract')
    profile = report.get('tract')
    if not visual or not profile or not profile.get('grid'):
        raise ValueError('録画の声道断面が保存されていません')
    rate, total = report['sampleRate'], report['outputFrames']
    stride = spec['stride_output_frames']
    points = np.minimum(np.arange(stride, total + stride, stride), total) - 1
    counts = profile['counts']
    grid = profile['grid']
    rows = np.asarray([item['rows'] for item in grid['frames']])
    cells = np.asarray([item[1:] for item in profile['rows']]).reshape(len(points), sum(counts), len(FIELDS))
    if rows.shape != (len(points), spec['expected_sections'], len(GRID_COLUMNS)) or not (
            np.isfinite(rows).all() and np.isfinite(cells).all()):
        raise ValueError('録画用の測定値の形状または有限性を確認できません')
    refs = reference_grids(source, points, spec, counts, artifacts, execute)
    native, upper, grid_pcm = refs['grid']
    cli_cells, upper_cells, cell_pcm = refs['cells']
    cell_tol = (spec['cell_length_tolerance_cm'], *([spec['cell_area_tolerance_cm2']] * 2))
    grid_cmp = differences(rows, upper, spec['grid_absolute_tolerance'])
    native_cells = compare_cells(cells, cli_cells, points, counts, FIELDS, cell_tol)
    fixed_cells = compare_cells(cells, upper_cells, points, counts, FIELDS, cell_tol)

    probe = wasm.read_json(artifacts / f'{clip.stem}-ffprobe.json')
    pts = np.array([float(f['best_effort_timestamp_time']) for f in probe['frames'] if f['media_type'] == 'video'])
    code = decode_crop(clip, spec['code_rect_px'], 'tract-code', len(pts), artifacts, execute)
    images = decode_crop(clip, spec['image_rect_px'], 'tract-image', len(pts), artifacts, execute)
    ids = read_frame_codes(code, spec['code_bits'])
    matrix = np.array(visual.get('projection', [])).reshape(4, 4, order='F')
    if not np.isfinite(matrix).all():
        raise ValueError('録画の投影行列に非有限値があります')
    raw_index = {int(frame): i for i, frame in enumerate(points)}
    composed = {item['frame']: item for item in visual['composed']}
    c0 = record['scheduledContextFrame']
    age = [(c['composedContextFrame'] - (c['contextFrame'] + 1)) / rate for c in composed.values()]
    frames = []
    phase_examples = {}
    frame_codes = []
    for i, (frame, timestamp) in enumerate(zip(ids.tolist(), pts.tolist(), strict=True)):
        if frame < 0:
            continue
        frame_codes.append(frame)
        index = raw_index.get(frame)
        if index is None or frame not in composed:
            frames.append({'video_frame': i, 'frame': frame, 'first_difference': 'frame_identifier'})
            continue
        row = native[index, -1]
        geometry = compare_projection(images[i], row, matrix, spec)
        absolute_time = timestamp - media['lag_seconds']
        entry = {'video_frame': i, 'frame': frame, 'pts_seconds': timestamp,
                 'video_minus_aligned_source_seconds': absolute_time - (frame + 1) / rate,
                 'expected_last_gap_cm': float(row[8]), 'expected_last_area_cm2': float(row[9]), **geometry}
        frames.append(entry)
        for phase, (lo, hi) in spec['comparison_windows'].items():
            if phase not in phase_examples and lo <= frame <= hi and geometry['passed']:
                phase_examples[phase] = entry
                Image.fromarray(np.asarray(images[i])).save(artifacts / f'decoded-tract-{phase}.png')
    summary = report['tractLive']
    mismatches = [f for f in frames if not f.get('passed')]
    coded = [f for f in frames if 'video_minus_aligned_source_seconds' in f]
    timing_errors = [f['video_minus_aligned_source_seconds'] for f in coded]
    exact_cells = all(value['first_difference'] is None for value in native_cells.values())
    tagged_indices = np.flatnonzero(ids >= 0)
    if 'second_vowel' in phase_examples:
        index = phase_examples['second_vowel']['video_frame']
        execute(['ffmpeg', '-v', 'error', '-i', str(clip), '-vf', f'select=eq(n\\,{index})',
                 '-frames:v', '1', str(artifacts / 'recording-preview.png')])
    return {
        'tract_capture_clock': (len(points) == spec['expected_samples']
            and [p['frame'] for p in grid['frames']] == points.tolist()
            and [row[0] for row in profile['rows']] == points.tolist()
            and grid['columns'] == GRID_COLUMNS and summary['sent'] + summary['skipped'] == len(points)),
        'tract_grid_cli_exact': np.array_equal(rows, native),
        'tract_grid_fixed_upper': grid_cmp['passed'],
        'tract_acoustic_cells': exact_cells and all(
            value['first_over_tolerance'] is None for value in fixed_cells.values()),
        'tract_upper_probes_keep_pcm': all(sha256(wave) == sha256(fixed_pcm) for wave in (grid_pcm, cell_pcm)),
        'tract_composition_clock': bool(composed) and list(composed) == sorted(composed)
            and len(composed) == len(visual['composed']) and not visual['unsupported']
            and record['recordingStartContextFrame'] < c0
            and all(f in raw_index and c['contextFrame'] == c0 + f for f, c in composed.items())
            and min(age) >= 0 and max(age) <= spec['maximum_composition_age_seconds'],
        'tract_video_frame_identifiers': len(set(frame_codes)) >= spec['minimum_decoded_unique_frames']
            and frame_codes == sorted(frame_codes) and len(coded) == len(frames)
            and all(x >= 0 for x in ids[tagged_indices[0]:tagged_indices[-1] + 1])
            and frame_codes[-1] >= total - 2 * stride and ids[-1] == -1
            and visual['imageRect'] == spec['image_rect_px'] and visual['codeRect'] == spec['code_rect_px']
            and visual['codeBits'] == spec['code_bits'] and visual['ringSegments'] == spec['ring_segments'],
        'tract_video_audio_frame_sync': bool(timing_errors)
            and max(map(abs, timing_errors)) <= spec['maximum_video_source_time_error_seconds'],
        'tract_decoded_geometry_in_four_intervals': not mismatches
            and set(phase_examples) == set(spec['comparison_windows'])
            and all(example['expected_last_gap_cm'] == 0 if phase.endswith('closure')
                    else example['expected_last_gap_cm'] > 0 for phase, example in phase_examples.items()),
    }, {
        'stored_frames': len(points), 'transmission': summary, 'composed_count': len(composed),
        'recording_lead_seconds': (c0 - record['recordingStartContextFrame']) / rate,
        'decoded_with_code': len(frames), 'unique_decoded_frames': len(set(frame_codes)),
        'composition_age_max_seconds': max(age, default=None),
        'video_minus_source_range_seconds': [min(timing_errors), max(timing_errors)] if timing_errors else None,
        'maximum_curve_distance_px': max((f['screen_curve_distance_px'] for f in coded
                                          if f['screen_curve_distance_px'] is not None), default=None),
        'first_decoded_difference': mismatches[0] if mismatches else None,
        'first_decoded_by_phase': phase_examples, 'frames': frames, 'upstream_grid': grid_cmp,
        'cli_cells': native_cells, 'upstream_cells': fixed_cells,
    }
