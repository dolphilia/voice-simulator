"""表情の入力、動力学、描画頂点を独立計算と固定上流に照合する。"""

import argparse
from math import ceil, cos, exp, log2, pi, sin
import re
import shutil
import struct
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image

import measure_uniform_tube as shared
from measure_duet_words import prior
from measure_wasm_fixed import read_json
from measure_worklet_fixed import ROOT, WEB, web_sources
from upstream_baseline import UPSTREAM, WORKSPACE, sha256

CASE = WORKSPACE / 'cases/duet-head-expression.json'
DEMO = WEB / 'public/shows/duet-clock'
CAPTURE = WEB / 'tools/capture-duet-head-expression.mjs'
FIELDS = ('puff', 'brow', 'lid', 'lookUp', 'nod', 'tilt')


def smooth(value, lo, hi):
    x = min(1, max(0, (value - lo) / (hi - lo)))
    return 3 * x ** 2 - 2 * x ** 3


def approach(old, new, delta, tau):
    return new + (old - new) * exp(-delta / tau)


def spring(state, hz, damping, goal, delta):
    position, velocity = state
    count = max(1, ceil(delta / .008))
    h = delta / count
    stiffness = (2 * pi * hz) ** 2
    resistance = 4 * pi * hz * damping
    for _ in range(count):
        velocity = (1 - resistance * h) * velocity + h * stiffness * (goal - position)
        position += h * velocity
    return [position, velocity]


def independent(frames, seed, dt_limit):
    def random():
        nonlocal sequence
        sequence = (1664525 * sequence + 1013904223) % (2 ** 32)
        return sequence / (2 ** 32)

    for row in frames:
        if row['reset']:
            sequence = seed
            t = held = lid = brow = 0.0
            reference = short = None
            cheek = neck = roll = [0.0, 0.0]
            last_beat = -1
            next_blink, started, double = 1.5 + 2 * random(), -1.0, False
        dt = min(dt_limit, row['elapsed'])
        t += dt
        tele = row['input']
        pressure = tele['pressure'] if tele else 0
        cheek = spring(cheek, 6.5, .32, smooth(pressure, 1.5, 7), dt)
        voicing = tele and (tele['voicing'] > .45 and tele['gate'] > .3 and tele['f0'] > 30 and tele['outRms'] > .004)
        dev = wobble = 0.0
        if voicing:
            pitch = log2(tele['f0'])
            if reference is None or abs(pitch - reference) > 14 / 12:
                reference = short = pitch
            reference = approach(reference, pitch, dt, 5)
            if abs(short - pitch) > 2.5 / 12:
                short, held = pitch, 0
            short = approach(short, pitch, dt, .35)
            held += dt
            dev, wobble = 12 * (pitch - reference), 12 * (pitch - short)
        else:
            held = 0
        brow = approach(brow, min(1, max(-.7, dev / 6)), dt, .12 if voicing else .45)
        ceiling = .92 * smooth(held, .9, 1.9) * smooth(brow, .15, .55)
        lid = approach(lid, ceiling, dt, .35 if ceiling > lid else .08)
        if t >= next_blink and lid < .2:
            started = t
            double = not double and random() < .18
            next_blink = started + (.28 if double else 2 + 4.5 * random())
        blink = sin(pi * ((t - started) / .17)) ** .7 if started >= 0 and (t - started) / .17 < 1 else 0
        beat = tele['beatStep'] if tele else -1
        if min(beat, last_beat) >= 0:
            kick = 1.3 if beat < last_beat else .8 if beat // 4 != last_beat // 4 else 0
            neck = [neck[0], neck[1] - kick]
        last_beat = beat
        neck = spring(neck, 2.4, .42, .13 * brow, dt)
        side = smooth(held, .6, 2) * .07 * sin(t * 1.7) + .05 * max(-1.5, min(1.5, wobble))
        roll = spring(roll, 3.2, .3, side, dt)
        face = dict(zip(FIELDS, (max(-.35, min(1.25, cheek[0])), brow, max(lid, blink), .32 * max(brow, 0),
                                 neck[0], roll[0]), strict=True))
        state = {'time': t, 'referencePitch': reference, 'recentPitch': short, 'heldSeconds': held, 'closure': lid,
                 'lastBeat': beat, 'motions': [cheek, neck, roll]}
        yield face, state


def error(a, b):
    if isinstance(a, dict):
        return max(error(a[k], b[k]) for k in a)
    if isinstance(a, list):
        return max(error(x, y) for x, y in zip(a, b, strict=True))
    if a is None or b is None:
        return 0.0 if a is b else float('inf')
    return float(abs(a - b))


def controls(spec, records):
    rows = []
    by_group = {}
    for group in spec['controls']:
        source = group['source']
        data = {'f0': 110, 'voicing': 1, 'gate': 1, 'outRms': .1, 'beatStep': -1, **(source or {})}
        pressure = float(np.float32(data.pop('pressure_cmh2o', 0) * spec['cg_per_cmh2o'])) / spec['cg_per_cmh2o']
        for i in range(group['frames']):
            rows.append({'reset': i == 0 and (not rows or group.get('reset', False)),
                'elapsed': group['elapsed'], 'input': dict(data, pressure=pressure) if source is not None else None})
    independent_error, fixed_error, pressure_error = 0.0, 0.0, 0.0
    for r, observation, (face, state) in zip(records, rows, independent(rows, spec['seed'],
            spec['expression_step_limit_seconds']), strict=True):
        fixed_error = max(fixed_error, error(r['face'], r['expected']), error(r['state'], r['upperState']))
        independent_error = max(independent_error, error(r['face'], face), error(r['state'], state))
        pressure_error = max(pressure_error, abs(r['pressure'] - r['upperPressure']),
                             abs(r['pressure'] - (observation['input'] or {}).get('pressure', 0)))
        by_group.setdefault(r['group'], []).append(r['face'])
    groups = {name: {metric: max(value[metric] for value in sequence) for metric in FIELDS} for name, sequence in by_group.items()}
    checks = {'upper_values_and_springs': fixed_error <= spec['state_tolerance'],
        'pressure_node_and_unit': pressure_error <= spec['state_tolerance'],
        'independent_dynamics': independent_error <= spec['state_tolerance'],
        'pressure_step_and_release': groups['rising_pressure']['puff'] > .4 and groups['full_pressure_slow_frame']['puff'] > .95
            and abs(by_group['release'][-1]['puff']) < .03,
        'weak_pitch_and_sustained_high_pitch': abs(groups['weak_high_pitch']['brow']) < .01
            and groups['high_note']['brow'] > .6 and by_group['high_note'][-1]['lid'] > .6,
        'skip_beat_and_wrap_bar': min(item['nod'] for item in by_group['continue_beat']) < -.02
            and by_group['wrap_bar'][0]['nod'] < by_group['continue_beat'][-1]['nod'],
        'seek_reseeds_pitch_and_springs': abs(groups['seek_reset']['brow']) < 1e-8 and abs(groups['seek_reset']['nod']) < 1e-8}
    return checks, {'upper_max_error': fixed_error, 'independent_max_error': independent_error, 'pressure_error_cmh2o': pressure_error,
                    'groups': groups}


def mesh_error(frame):
    mesh, face = frame['mesh'], frame['face']
    s, t, z = mesh['scale'], face['tilt'], face['nod']
    side = mesh['facing']
    rotation_x = np.array([[1, 0, 0], [0, cos(t), -sin(t)], [0, sin(t), cos(t)]])
    rotation_z = np.array([[cos(z), -sin(z), 0], [sin(z), cos(z), 0], [0, 0, 1]])
    rotate = rotation_x @ rotation_z
    pivot = np.array([-2.4, 3.366, 0]) * s
    model = np.eye(4)
    model[:3, :3] = rotate
    model[:3, 3] = pivot - rotate @ pivot
    model = np.diag([side, 1, 1, 1]) @ model
    matrix = np.array(mesh['model']).reshape(4, 4, order='F')
    matrices = float(np.max(np.abs(matrix - model)))
    vertices = []
    brow, lid = face['brow'], face['lid']
    weight = (1 - (.94 / 2.3) ** 2) ** 2 * face['puff']
    for side in (-1, 1):
        vertices.append(np.array([[6.14 + .55 * weight, 8.3, side * (3.4 + 1.7 * weight)],
             [6.2, 13.0 + .3 * brow + .11 * lid * max(0, brow) - .14 * max(0, -brow), side * 2.58],
             [6.2, 12 + (.5 + .2 * max(0, brow)) * (1 - lid) - .27 * lid, side * 2.55],
             [6.2, 11.7, side * 2.55]]) * s)
    return matrices, float(np.max(np.abs(vertices - np.asarray(mesh['features']))))


def read_track(voice, spec):
    data = (DEMO / f'voice-{voice}.tele').read_bytes()
    rate, hop, count, width, axes, ph, oral = struct.unpack_from('<7I', data, 8)
    rows = []
    for i in range(count):
        offset = 48 + i * width * 4
        scalars = struct.unpack_from('<11f', data, offset)
        p, = struct.unpack_from('<f', data, offset + 4 * (11 + axes + 2 * (ph + oral) - 3))
        rows.append(dict(zip(('f0', 'voicing', 'outRms', 'gate'), (scalars[j] for j in (3, 4, 6, 9)),
                             strict=True), pressure=p / spec['cg_per_cmh2o']))
    return rate, hop, rows


def browsers(spec, data, artifacts):
    settings = spec['browser']
    limit = spec['state_tolerance']
    checks, metrics = {}, []
    for viewport in data['viewports']:
        width, markers = viewport['width'], viewport['markers']
        max_state = max_matrix = max_vertex = 0.0
        sources_match = time_follows = resets = settles = True
        peaks = []
        for voice, trace in enumerate(viewport['trace'], 1):
            rate, hop, values = read_track(voice, spec)
            for row in trace:
                if row['clock']['playing'] and row['expressive']:
                    t = row['clock']['time']
                    index = min(len(values) - 1, int(t * rate / hop + 1e-6))
                    step = -1
                    if viewport['withBeat']:
                        beat = int(np.floor((t - settings['diagnostic_downbeat_seconds']) * settings['diagnostic_bpm'] / 15))
                        step = beat % 16 if beat >= 0 else -1
                    sources_match &= index == row['index'] and error(row['input'], dict(values[index], beatStep=step)) <= limit
                else:
                    sources_match &= row['input'] is None
                matrix, vertices = mesh_error(row)
                max_matrix, max_vertex = max(max_matrix, matrix), max(max_vertex, vertices)
            active = [row for row in trace if row['expressive']]
            time_follows &= all(b['tick'] == a['tick'] + 1 for a, b in zip(active, active[1:]))
            for row, (face, state) in zip(active, independent(active, spec['seed'] + voice - 1,
                    spec['expression_step_limit_seconds']), strict=True):
                max_state = max(max_state, error(row['face'], face), error(row['state'], state))
            seeks = [next(row for row in trace if row['clock']['epoch'] == epoch) for epoch in markers['seeks']]
            for target, row in zip(settings['live_seeks'], seeks, strict=True):
                resets &= row['reset'] and row['clock']['playing'] and round(row['clock']['time'] * rate) == target
                resets &= abs(row['state']['time'] - row['elapsed']) <= limit and abs(row['face']['brow']) <= limit
            paused, settled = (next(row for row in trace if row['tick'] == markers[key][voice - 1])
                               for key in ('pause', 'settled'))
            settles &= not paused['clock']['playing'] and paused['clock'] == settled['clock']
            settles &= settled['state']['time'] > paused['state']['time'] + .1 and abs(settled['face']['puff']) < .07
            settles &= abs(settled['face']['brow']) <= abs(paused['face']['brow']) + limit
            passage = [row for row in trace if row['clock']['epoch'] == markers['start'] and row['clock']['playing']]
            peaks.append({name: max(row['face'][name] for row in passage) for name in FIELDS})
        photos = viewport['photos']
        image = [np.array(Image.open(artifacts / photos[key]['path']).convert('RGB'), dtype=np.int16) for key in ('enabled', 'disabled')]
        changed = int(np.any(np.abs(image[0] - image[1]) >= 6, axis=2).sum())
        enabled, disabled = (next(row for row in viewport['trace'][1] if row['tick'] == photos[key]['tick'])
                             for key in ('enabled', 'disabled'))
        tests = {'no_browser_errors': not viewport['errors'], 'track_pressure_pitch_and_beats': sources_match,
            'independent_frame_state': bool(time_follows and max_state <= limit),
            'head_rotation_and_visible_vertices': max_matrix <= limit and max_vertex <= spec['geometry_tolerance_cm'],
            'pressure_and_voice_pitch_change_faces': peaks[1]['puff'] >= settings['minimum_cheek_peak']
                and all(p['brow'] >= settings['minimum_pitch_brow_peak'] for p in peaks),
            'pause_decay_and_live_seek_resets': bool(resets and settles),
            'same_articulation_expression_pixel_difference': photos['enabled']['sample'] == photos['disabled']['sample']
                and enabled['index'] == disabled['index'] and not enabled['clock']['playing'] and not disabled['clock']['playing']
                and enabled['face']['puff'] > .1 and not any(disabled['face'].values())
                and changed >= settings['minimum_enabled_picture_pixel_delta']}
        checks.update({f'{width}_{key}': value for key, value in tests.items()})
        metrics.append({'width': width, 'frames': [len(trace) for trace in viewport['trace']], 'max_expression_error': max_state,
            'max_matrix_error': max_matrix, 'max_vertex_cm': max_vertex, 'peak_by_voice': peaks, 'changed_pixels': changed,
            'comparison_pose_sample': photos['enabled']['sample']})
    return checks, metrics


def measure(spec, artifacts, execute, bun):
    execute([*bun, 'test', 'tests/expression.test.ts', 'tests/tele.test.ts', 'tests/transport.test.ts'], cwd=UPSTREAM)
    execute([*bun, 'run', 'build'], cwd=WEB)
    execute([*bun, str(CAPTURE), str(CASE), str(UPSTREAM), str(artifacts)], cwd=WEB)
    controlled, results = controls(spec, read_json(artifacts / 'controlled-expression.json'))
    browser = read_json(artifacts / 'browser-expression.json')
    checks, metrics = browsers(spec, browser, artifacts)
    return {'checks': dict(controlled, **checks), 'browser': browser['browser'], 'controlled': results, 'viewports': metrics}


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
    echo = prior(ref['echo_run'], 'duet-head-echoes', revision, ref['echo_manifest_sha256'])
    if any(sha256(DEMO / f'voice-{i}.tele') != expected for i, expected in enumerate(ref['track_sha256'], 1)):
        parser.error('比較用のテレメトリが登録値と異なります')
    bun = ['bun'] if shutil.which('bun') else ['npx', '--yes', '--package=bun@1.4.4', '--', 'bun']
    names = ('src/ui/components/DuetPage.tsx', 'src/ui/components/AnatomyView3D.tsx', 'src/ui/render/expression.ts',
             'src/ui/render/anatomy3d.ts', 'tests/expression.test.ts', 'tests/tele.test.ts', 'tests/transport.test.ts')
    details = {'case_id': spec['id'], 'upstream_revision': revision,
        'upstream_source_sha256': {name: sha256(UPSTREAM / name) for name in names},
        'bun': subprocess.check_output([*bun, '--version'], text=True).strip()}
    inputs = [CASE, CAPTURE, Path(__file__), Path(shared.__file__), echo[0] / 'manifest.json',
              *sorted(DEMO.iterdir()), *web_sources(), *shared.candidate_sources()]
    return shared.record_measurement(args.run_id, CASE, inputs, details,
        lambda artifacts, execute: measure(spec, artifacts, execute, bun), command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
