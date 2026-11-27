"""母音遷移の2フレーム間で、格子点がセル境界を通る前後を観測する。"""

import csv
import json

import numpy as np

import measure_sagittal as sagittal
import measure_uniform_tube as shared
from upstream_baseline import UPSTREAM, WORKSPACE


FIELDS = ('grid_s_cm', 'cell_end_cm', 'grid_area_cm2', 'mean_cm2', 'minimum_cm2')


def frame_poses(path, frames, initial):
    with path.open(newline='') as file:
        samples = {(int(row['frame']), row['articulator']): float(row['position'])
                   for row in csv.DictReader(file) if int(row['frame']) in frames}
    poses = []
    for frame in frames:
        pose = dict(initial)
        for part in ('tongue_body', 'tongue_tip'):
            pose[f'{part}_cm'] = [samples[frame, f'{part}_{axis}_cm'] for axis in ('x', 'y')]
        for key in pose:
            if (frame, key) in samples:
                pose[key] = samples[frame, key]
        poses.append(pose)
    return poses


def snapshot(area_path, resample_path, config):
    with area_path.open(newline='') as file:
        grid = list(csv.DictReader(file))[config['grid_point']]
    with resample_path.open(newline='') as file:
        cell = next(row for row in csv.DictReader(file)
                    if row['tube'] == config['tube'] and int(row['cell']) == config['cell'])
    values = np.array([float(grid['s_cm']), float(cell['end_cm']), float(grid['area_cm2']),
                       float(cell['area_cm2']), float(cell['minimum_area_cm2'])])
    if not np.isfinite(values).all():
        raise ValueError('格子点やセルの断面に非有限値があります')
    return values


def probe_boundaries(case, motion_result, artifacts, execute):
    cfg = case['measurement']['refine_minimum_boundary']
    root = artifacts / 'minimum-boundary'
    root.mkdir()
    trajectory = json.loads((WORKSPACE/'cases'/f"{case['continuity_case']}.json").read_text())
    frames = (cfg['frame_before'], cfg['frame_after'])
    if any(frame in motion_result['reapply_frames'] for frame in frames):
        raise ValueError('追加計測の区間は接触の再計算が起きない2フレームを指定してください')
    counts = trajectory['measurement']['area_control']['tube_cells']
    trajectory.pop('area_control')
    input_path = root/'articulation-input.json'
    input_path.write_text(json.dumps(trajectory, ensure_ascii=False, indent=2) + '\n')
    positions = root/'articulators.csv'
    build = root/'build.jsonl'
    execute(['cargo', 'build', '--locked', '--release', '-p', 'vocal-cli',
             '--message-format=json'], stdout=build)
    builds = [event['executable'] for line in build.read_text().splitlines()
              if (event := json.loads(line)).get('reason') == 'compiler-artifact'
              and event['target']['name'] == 'vocal-cli' and event.get('executable')]
    if len(builds) != 1:
        raise ValueError('候補CLIの実行ファイルを特定できません')
    cli, = builds
    execute([cli, 'render', str(input_path), str(positions)])
    first, last = frame_poses(positions, frames, trajectory['posture'])

    def sample(fraction, number):
        pose = {key: (np.asarray(value) + fraction*(np.asarray(last[key]) - np.asarray(value))).tolist()
                for key, value in first.items()}
        geometry = {'id': f'minimum-boundary-{number}', 'upstream_revision': case['upstream_revision'],
                    'body': case['body'], 'hypothesis': '格子点がセル境界をまたぐと最小断面の候補が変わる。',
                    'posture': pose, 'cells': counts, 'measurement': {'frames': 1}}
        query = root / f'pose-{number}.json'
        query.write_text(json.dumps(geometry, ensure_ascii=False, indent=2) + '\n')
        outputs = [root / f'{command}-{number}.csv' for command in ('area', 'resample')]
        for command, out in zip(('area', 'resample'), outputs, strict=True):
            execute([cli, command, str(query), str(out)])
        return fraction, snapshot(*outputs, cfg), geometry

    initial, final = sample(0.0, 0), sample(1.0, 1)
    left, right = initial, final
    if left[1][0] > left[1][1] or right[1][0] <= right[1][1]:
        raise ValueError('追加計測では格子点がセル終端をまたぐ区間を指定してください')
    for number in range(2, 2 + cfg['bisection_steps']):
        current = sample((left[0] + right[0]) / 2, number)
        if current[1][0] <= current[1][1]:
            left = current
        else:
            right = current

    probe = shared.build_upstream_probe(sagittal.PROBE, root, execute)
    reference_errors = []
    with (root/'boundary.csv').open('w', newline='') as file:
        writer = csv.writer(file, lineterminator='\n')
        writer.writerow(('point', 'fraction', 'engine', *FIELDS))
        for label, (fraction, candidate, geometry) in zip(
                ('initial', 'before_boundary', 'after_boundary', 'final'),
                (initial, left, right, final), strict=True):
            upper_area = root / f'upstream-area-{label}.csv'
            upper_resample = root / f'upstream-resample-{label}.csv'
            args = sagittal.pose_controls(geometry)
            execute([str(probe), '--area', *args], cwd=UPSTREAM, stdout=upper_area)
            execute([str(probe), '--resample', str(counts['pharynx']), str(counts['oral']), *args],
                    cwd=UPSTREAM, stdout=upper_resample)
            upstream = snapshot(upper_area, upper_resample, cfg)
            reference_errors.append(float(abs(candidate - upstream).max()))
            writer.writerow((label, fraction, 'candidate', *candidate))
            writer.writerow((label, fraction, 'upstream', *upstream))

    fraction = (left[0] + right[0]) / 2
    grid_change, mean_change, minimum_step = map(float, abs(right[1][2:] - left[1][2:]))
    lo_f, hi_f = cfg['boundary_fraction_interval']
    lo_step, hi_step = cfg['minimum_step_cm2_interval']
    return {'checks': {'registered_crossing_fraction': lo_f <= fraction <= hi_f,
                       'registered_minimum_step': lo_step <= minimum_step <= hi_step,
                       'grid_and_mean_stay_smooth': max(grid_change, mean_change) < cfg['smooth_area_change_lt_cm2'],
                       'fixed_upstream_boundary_measurements': max(reference_errors) < cfg['upstream_absolute_error_lt']},
            'fraction': fraction, 'bisection_width': right[0] - left[0],
            'grid_point_area_change_cm2': grid_change, 'cell_mean_area_change_cm2': mean_change,
            'cell_minimum_step_cm2': minimum_step, 'max_absolute_error_to_upstream': max(reference_errors),
            'maximum_frame_step_cm2': float(abs(final[1][4] - initial[1][4]))}
