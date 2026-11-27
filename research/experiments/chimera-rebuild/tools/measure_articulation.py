"""調音器の位置・速度・目標を固定上流と無次元の漸化式に照合する。"""

import argparse
import csv
import json
from pathlib import Path
import re
import subprocess

import numpy as np

import measure_uniform_tube as shared
from upstream_baseline import UPSTREAM, WORKSPACE


PROBE = WORKSPACE / 'tools/upstream_articulation_probe.rs'
CASES = tuple(f'articulation-{name}' for name in ('vowels-pinned', 'vowels-free', 'jaw-pace', 'blend-limits'))
KEYS = (
    'jaw_cm', 'tongue_body_x_cm', 'tongue_body_y_cm', 'tongue_tip_x_cm', 'tongue_tip_y_cm',
    'tip_curl', 'tongue_root_cm', 'lip_aperture_cm', 'lip_protrusion_cm', 'lip_spread',
    'labiodental', 'velum_cm2', 'larynx_cm', 'epilarynx', 'ventricular', 'lateral', 'dorsum',
)
METRICS = ('position', 'velocity_per_s', 'target', 'effective', 'base_speed', 'applied_speed', 'tip_free')
HEADER = ('frame', 'internal_start_sample', 'time_s', 'articulator', *METRICS)
LOW = np.array([-.1, 1, 4.8, 3.5, 5, 0, -1, -.4, -.2, 0, 0, -.25, -1.6, 0, 0, 0, 0])
HIGH = np.array([2.6, 4.8, 9.2, 8, 10.8, 1, 1, 2.4, 1.5, 1, 1, 1.4, 1.6, 1, 1, 1, 1])
HZ = np.array([10, 12, 12, 13, 13, 9, 9, 11, 11, 11, 10, 12, 8, 6, 6, 10, 9])
VELUM = KEYS.index('velum_cm2')
TIPS = slice(3, 5)


def initial_pose(case):
    pose = dict(case['posture'])
    for part in ('tongue_body', 'tongue_tip'):
        pose[f'{part}_x_cm'], pose[f'{part}_y_cm'] = pose[f'{part}_cm']
    return np.array([pose.get(key, 0.0) for key in KEYS], dtype=float)


def upstream_trace(case, artifacts, execute):
    execute(['cargo', 'test', '--locked', '-p', 'chimera', '--test', 'geometry_continuity',
             'no_area_jumps_on_the_way_between_calibrated_vowels', '--', '--nocapture'],
            cwd=UPSTREAM, stdout=artifacts / 'upstream-continuity-test.log')
    probe = shared.build_upstream_probe(PROBE, artifacts, execute)
    plan = artifacts / 'upstream-events.txt'
    write_upstream_events(case, plan)
    path = artifacts / 'upstream-trace.csv'
    execute([str(probe), str(plan)], cwd=UPSTREAM, stdout=path)
    return path


def write_upstream_events(case, plan):
    cfg = case['articulators']
    frames = case['measurement']['frames']
    with plan.open('w') as out:
        body = case['body']
        body_arg = body if isinstance(body, str) else ','.join(str(body.get(key, 0)) for key in ('female', 'child'))
        extra = [] if body_arg == 'male' else [body_arg]
        print(cfg['sample_rate_hz'], cfg['control_block_samples'], frames, int(cfg['tip_free']),
              cfg['base_weight'], *extra, file=out)
        print(*initial_pose(case), file=out)
        for event in cfg.get('events', []):
            frame = event['frame']
            if 'gate' in event:
                print(frame, 'gate', event['gate'], file=out)
            if 'f0_hz' in event:
                print(frame, 'f0_hz', event['f0_hz'], file=out)
            for name in ('target', 'speed'):
                for key, value in event.get(f'{name}s', {}).items():
                    print(frame, name, KEYS.index(key), value, file=out)
            if 'tip_free' in event:
                print(frame, 'tip_free', int(event['tip_free']), file=out)
            if 'blend' in event:
                print(frame, 'clear_blend', file=out)
                for key, config in event['blend'].items():
                    print(frame, 'blend', KEYS.index(key),
                          *(config[k] for k in ('value', 'weight', 'speed')), file=out)


def read_trace(path, frames, block):
    numeric = []
    times = np.empty(frames)
    with path.open(newline='') as file:
        reader = csv.reader(file)
        if tuple(next(reader, [])) != HEADER:
            raise ValueError(f'{path.name} のヘッダーが不正です')
        for index, row in enumerate(reader):
            frame, key_index = divmod(index, len(KEYS))
            if (len(row) != len(HEADER) or frame >= frames or int(row[0]) != frame
                    or int(row[1]) != frame * block or row[3] != KEYS[key_index]):
                raise ValueError(f'{path.name} の制御フレーム、部位またはサンプル番号が不正です')
            t = float(row[2])
            if key_index == 0:
                times[frame] = t
            if times[frame] != t:
                raise ValueError(f'{path.name} でフレーム内の時刻が不一致です')
            numeric.append([float(value) for value in row[4:]])
    values = np.asarray(numeric, dtype=float)
    if len(values) != frames * len(KEYS) or not np.isfinite(values).all() or not np.isfinite(times).all():
        raise ValueError(f'{path.name} のフレーム数または観測値が不正です')
    return times, values.reshape(frames, len(KEYS), len(METRICS))


def resting_tip(position):
    jaw, body_x, body_y = position[:3]
    # 顎関節まわりの回転を複素積で独立に計算する。
    anchor = complex(-2.5, 10.5)
    start = complex(6.45, 7.35)
    rotated = anchor + (start - anchor) * np.exp(-1j * jaw / 9.84)
    return [rotated.real + .30 * (body_x - 2.9), rotated.imag + .35 * (body_y - 6.85)]


def independent_trace(case, dt, out_path):
    config = case['articulators']
    frames = case['measurement']['frames']
    events = {e['frame']: e for e in config['events']}
    initial = np.clip(initial_pose(case), LOW, HIGH)
    x = initial.copy()
    step_velocity = np.zeros(len(KEYS))
    target = x.copy()
    speed = np.ones(len(KEYS))
    gesture_value = np.zeros(len(KEYS))
    weight = np.zeros(len(KEYS))
    gesture_speed = np.ones(len(KEYS))
    free = config['tip_free']
    base_weight = config['base_weight']
    trajectory = []
    for frame in range(frames):
        event = events.get(frame, {})
        for key, value in event.get('targets', {}).items():
            i = KEYS.index(key)
            target[i] = np.clip(value, LOW[i], HIGH[i])
        for key, value in event.get('speeds', {}).items():
            speed[KEYS.index(key)] = value
        free = event.get('tip_free', free)
        if 'blend' in event:
            weight.fill(0.0)
            for key, blend in event['blend'].items():
                i = KEYS.index(key)
                gesture_value[i], weight[i], gesture_speed[i] = (blend[k] for k in ('value', 'weight', 'speed'))
        if free:
            target[TIPS] = resting_tip(x)

        active = weight > 0
        mixing = np.zeros(len(KEYS))
        np.divide(weight, base_weight + weight, out=mixing, where=active)
        mixing[VELUM] = min(1.0, weight[VELUM] / 2)
        effective = np.clip(target + mixing * (gesture_value - target), LOW, HIGH)
        applied = speed * np.where(active, gesture_speed, 1)
        h = 2 * np.pi * dt * HZ * applied
        step_velocity = (1 - 2 * h) * step_velocity + h**2 * (effective - x)
        x += step_velocity
        x[(effective == 0) & (abs(x) < 1e-30)] = 0
        step_velocity[abs(step_velocity / dt) < 1e-30] = 0
        trajectory.append(np.column_stack((x, step_velocity / dt, target, effective, speed, applied,
                                           np.full(len(KEYS), free))))
    data = np.asarray(trajectory)
    with out_path.open('w', newline='') as file:
        writer = csv.writer(file, lineterminator='\n')
        writer.writerow(HEADER)
        for frame, elements in enumerate(data):
            for key, row in zip(KEYS, elements, strict=True):
                writer.writerow((frame, frame * config['control_block_samples'], (frame + 1) * dt, key, *row))
    return initial, data


def check_settling(expectations, trace, initial, dt, position_tol):
    records = []
    for setting in expectations:
        key = setting['articulator']
        start, end = setting['start_frame'], setting['end_frame']
        i = KEYS.index(key)
        data = trace[start:end, i]
        before, velocity = (trace[start - 1, i, :2] if start else [initial[i], 0.0])
        target = data[0, METRICS.index('effective')]
        speed = data[0, METRICS.index('applied_speed')]
        h = 2 * np.pi * HZ[i] * speed * dt
        update = np.array([[1 - h*h, 1 - 2*h], [-h*h, 1 - 2*h]])
        state = [before - target, dt * velocity]
        closed = np.array([target + (np.linalg.matrix_power(update, j + 1) @ state)[0]
                           for j in range(len(data))])
        matrix_error = float(abs(data[:, 0] - closed).max())
        threshold = (1 - setting['fraction']) * abs(target - before)
        indices = np.flatnonzero(abs(data[:, 0] - target) <= threshold)
        settling = float((indices[0] + 1) * dt) if len(indices) else None
        peak = float(abs(data[:, 1]).max())
        lo_t, hi_t = setting['time_interval_seconds']
        lo_v, hi_v = setting['peak_velocity_interval']
        constant = (np.all(data[:, 3] == target) and np.all(data[:, 5] == speed))
        passed = constant and settling is not None and lo_t <= settling <= hi_t and lo_v <= peak <= hi_v
        records.append({'articulator': key, 'start_frame': start, 'speed': float(speed),
                        'settling_seconds': settling, 'peak_velocity_per_s': peak,
                        'matrix_power_error': matrix_error,
                        'passed': bool(passed and matrix_error < position_tol)})
    return records


def comparison(candidate, reference, limits):
    errors = abs(candidate - reference)
    missed = np.argwhere(errors >= limits)
    first = None
    if len(missed):
        frame, key, metric = map(int, missed[0])
        first = {'frame': frame, 'articulator': KEYS[key], 'column': METRICS[metric]}
    return {'max_absolute_errors': dict(zip(METRICS, errors.max(axis=(0,1)).tolist(), strict=True)),
            'first_over_tolerance': first, 'passed': first is None}


def measure(case, artifacts, execute):
    cfg = case['articulators']
    measurement = case['measurement']
    compare = measurement['articulators']
    frames, block = measurement['frames'], cfg['control_block_samples']
    dt = block / cfg['sample_rate_hz']
    candidate_times, candidate = read_trace(artifacts / 'trace.csv', frames, block)
    upper_times, upper = read_trace(upstream_trace(case, artifacts, execute), frames, block)
    initial, independent = independent_trace(case, dt, artifacts / 'independent-trace.csv')
    position_limit, velocity_limit = compare['position_error_lt'], compare['velocity_error_lt']
    limits = np.array([position_limit, velocity_limit, *([position_limit] * 5)])
    baseline = comparison(candidate, upper, limits)
    formula = comparison(candidate, independent, limits)
    metadata = json.loads((artifacts / 'settings.json').read_text())
    clock = np.arange(1, frames + 1) * dt
    time_error = max(abs(candidate_times - clock).max(), abs(candidate_times - upper_times).max())
    positions = candidate[:, :, 0]
    prev = np.vstack((initial, positions[:-1]))
    velocity_error = float(abs((positions - prev) / dt - candidate[:, :, 1]).max())
    checkpoints = []
    for expect in compare['checkpoints']:
        index = (expect['frame'], KEYS.index(expect['articulator']), METRICS.index(expect['column']))
        value = float(candidate[index])
        lo, hi = expect['interval']
        checkpoints.append({**expect, 'value': value, 'passed': lo <= value <= hi})
    settling = check_settling(compare['settling'], candidate, initial, dt, position_limit)
    free = candidate[:, 0, 6] == 1
    free_difference = None
    if free.any():
        # 同じフレームの更新後の姿勢を使ってしまった場合の差も測る。
        post_targets = np.array([resting_tip(row) for row in positions[free]])
        free_difference = float(np.max(abs(candidate[free, TIPS, 2] - post_targets)))
    specs = metadata['articulators']
    checks = {
        'registered_frames_and_clock': metadata['frames'] == frames
            and abs(metadata['control_seconds'] - dt) < compare['time_error_lt_seconds']
            and time_error < compare['time_error_lt_seconds'],
        'registered_initial_pose_and_ranges': len(specs) == len(KEYS) and all(
            entry['articulator'] == key and [entry['minimum'], entry['maximum'], entry['natural_frequency_hz']] == [low, high, hz]
            and abs(entry['initial_position'] - x) < position_limit
            for entry, key, low, high, hz, x in zip(specs, KEYS, LOW, HIGH, HZ, initial, strict=True)),
        'upstream_full_state': baseline['passed'],
        'independent_dimensionless_recurrence': formula['passed'],
        'displacement_matches_updated_velocity': velocity_error < velocity_limit,
        'effective_targets_in_range': np.all((candidate[:, :, 3] >= LOW) & (candidate[:, :, 3] <= HIGH)),
        'registered_checkpoints': all(point['passed'] for point in checkpoints),
        'registered_settling_and_matrix_solution': all(record['passed'] for record in settling),
    }
    return {'checks': {key: bool(value) for key, value in checks.items()},
            'control_frames': frames, 'upstream': baseline, 'independent': formula,
            'time_error_seconds': float(time_error), 'finite_difference_velocity_error_per_s': velocity_error,
            'free_tip_post_update_target_max_difference_cm': free_difference,
            'checkpoints': checkpoints, 'settling': settling}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('case', choices=CASES)
    args = parser.parse_args()
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]*', args.run_id):
        parser.error('実行IDは英数字で始め、英数字・ハイフン・アンダースコアで指定してください')
    path = WORKSPACE / 'cases' / f'{args.case}.json'
    case = json.loads(path.read_text())
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'],
                                                                        cwd=UPSTREAM, text=True):
        raise ValueError('変更のない固定上流版が必要です')
    sources = [path, PROBE, Path(__file__).resolve(), Path(shared.__file__),
               WORKSPACE / 'tools/upstream_baseline.py', *shared.candidate_sources()]
    details = {'upstream_revision': revision, 'case_id': case['id']}
    return shared.record_measurement(args.run_id, path, sources, details,
                                     lambda artifacts, execute: measure(case, artifacts, execute))


if __name__ == '__main__':
    raise SystemExit(main())
