"""デュエットの流量・投影・描画履歴を固定上流と独立計算に照合する。"""

import argparse
from math import floor, log1p
from pathlib import Path
import re
import shutil
import subprocess

import numpy as np

import measure_uniform_tube as shared
from measure_duet_head_pressure import DEMO, UPPER_WASM, gap, positions, track
from measure_duet_heads import cli_geometry
from measure_duet_words import prior
from measure_wasm_fixed import read_json
from measure_worklet_fixed import ROOT, WEB, web_sources
from upstream_baseline import UPSTREAM, WORKSPACE, sha256

CASE = WORKSPACE / 'cases/duet-head-airflow.json'
CAPTURE = WEB / 'tools/capture-duet-head-airflow.mjs'


def section_values(grid, scale):
    records = np.asarray(grid)
    inner, outer = records[:, 1:3], records[:, 3:5]
    vectors = outer - inner
    norms = np.linalg.norm(vectors, axis=1)
    directions = np.empty_like(vectors)
    direction = np.array([-1., 0.])
    for row, norm in enumerate(norms):
        if norm > 1e-4:
            direction = vectors[row] / norm
        directions[row] = direction
    radius = records[:, 8] / 2
    width = np.zeros_like(radius)
    np.divide(records[:, 9], np.pi * radius, out=width, where=radius > .005)
    center = outer - directions * radius[:, None]
    return records[:, 10], np.column_stack((center, directions, radius, np.minimum(3.5 * scale, width)))


def project(particle, distances, sections, glottis, scale, inset):
    s, u, v = (particle[key] for key in ('s', 'u', 'v'))
    if s <= distances[0]:
        shift = max(0., s / max(.01, distances[0])) * (sections[0, :2] - glottis)
        x, y = glottis + shift
        return [x + .3 * scale * u, y, .45 * scale * v]
    if s >= distances[-1]:
        return None
    x, y, dx, dy, a, b = (np.interp(s, distances, column) for column in sections.T)
    return [x + dx * a * u * inset, y + dy * a * u * inset, b * v * inset]


def speed_at(s, nodes, areas, flow, setting):
    node = np.abs(nodes - s).argmin()
    velocity = float(flow[node]) / max(setting['area_floor_cm2'], float(areas[node]))
    speed = float(np.sign(velocity) * setting['speed_scale_cm_s'] * log1p(abs(velocity) / setting['velocity_scale_cm_s']))
    return velocity, speed


def difference(a, b):
    if a is None or b is None:
        return 0. if a is b else 1e6
    return gap(a, b)


def controlled(data, spec):
    diagnostic, dynamics = spec['diagnostic'], spec['dynamics']
    nodes = positions(diagnostic['lengths_cm'], diagnostic['n_pharynx'], diagnostic['n_oral'])
    flow, area = (np.asarray(diagnostic[key], dtype=np.float32) for key in ('flow_cm3_s', 'areas_cm2'))
    distances, sections = section_values(data['grid'], data['scale'])
    glottis = np.asarray(data['glottis'])
    particles = [p.copy() for p in data['initial']]
    rng = dynamics['initial_random_seed']

    def rand():
        nonlocal rng
        rng = (rng * 1664525 + 1013904223) % (2 ** 32)
        return rng / 2 ** 32

    max_values = {'candidate': 0., 'upper': 0.}
    counts = True
    states = []
    for result in data['trace']:
        segments = []
        dt = 0. if result.get('paused') else min(dynamics['display_step_limit_seconds'], result['elapsed'])
        for index, p in enumerate(particles):
            if result.get('paused'):
                continue
            if result.get('reset'):
                p['previous'] = None
            velocity, speed = speed_at(p['s'], nodes, area, flow, dynamics)
            p['s'] += speed * dt
            p['life'] -= dynamics['life_decay_per_second'] * dt
            if p['life'] <= 0 or (not (0 <= p['s'] <= distances[-1]) and abs(velocity) >= dynamics['low_velocity_cm_s']):
                p.update(s=.8 * rand(), u=2 * rand() - 1, v=2 * rand() - 1, life=.6 + .8 * rand(), previous=None)
                continue
            point = project(p, distances, sections, glottis, data['scale'], dynamics['ring_inset'])
            if point is not None:
                if p['previous'] is not None:
                    band = min(2, floor(3 * min(1., p['life']) * min(1., abs(speed) / 6)))
                    segments.append({'particle': index, 'from': p['previous'], 'to': point, 'band': band})
                p['previous'] = point
        draw = result['draw']
        if draw is not None:
            counts &= abs(draw['dt'] - dt) <= dynamics['clock_tolerance_seconds']
            counts &= gap(nodes, draw['nodes']) <= dynamics['position_tolerance_cm']
        for label, observed, trails in (
                ('candidate', result['candidate'], draw['trails'] if draw else []),
                ('upper', result['upstreamParticles'], result['upstreamSegments'])):
            counts &= len(trails) == len(segments) and len(observed) == len(particles)
            for measured, expected in zip(observed, particles, strict=True):
                max_values[label] = max(max_values[label], *(abs(measured[key] - expected[key]) for key in ('s', 'u', 'v', 'life')),
                                        difference(measured['previous'], expected['previous']))
            for measured, expected in zip(trails, segments):
                max_values[label] = max(max_values[label], gap(measured['from'], expected['from']), gap(measured['to'], expected['to']))
                counts &= (measured['particle'] == expected['particle'] and measured['band'] == expected['band'] if label == 'candidate'
                           else abs(measured['alpha'] - (.16 + .2 * expected['band'])) < 1e-12)
        states.append({'dt_seconds': dt, 'distances_cm': [p['s'] for p in particles], 'segments': len(segments)})
    step = np.asarray(states[1]['distances_cm'][:4]) - np.asarray(states[0]['distances_cm'][:4])
    checks = {'independent_particle_states_and_segments': bool(counts and max(max_values.values()) <= dynamics['position_tolerance_cm']),
        'area_floor_forward_reverse_and_low_flow': bool(step[1] > step[0] > step[3] > 0 > step[2]),
        'closed_projection_and_degenerate_terminal': data['trace'][0]['candidate'][2]['previous'][2] == 0
            and data['trace'][0]['candidate'][-1]['previous'] is None,
        'pause_clock_cap_and_seek': states[2]['distances_cm'] == states[1]['distances_cm'] and states[2]['segments'] == 0
            and states[4]['dt_seconds'] == dynamics['display_step_limit_seconds'] and states[5]['segments'] == 0
            and states[6]['segments'] > 0}
    return checks, {'maximum_errors': max_values, 'distances_and_counts': states, 'first_interval_delta_cm': step.tolist()}


def recorded(sources, upper, spec):
    setting = spec['dynamics']
    metrics = []
    indices_match = True
    for voice, (source, frames) in enumerate(zip(sources, upper, strict=True), 1):
        for sample, frame in zip(spec['browser']['samples'], frames, strict=True):
            index = sample // source['hop']
            indices_match &= frame['sample'] == sample and frame['index'] == index
            area, flow = (source[key][index] for key in ('areas', 'flow'))
            indices_match &= gap(frame['areas'], area) == gap(frame['flow'], flow) == 0
            velocity = flow / np.maximum(setting['area_floor_cm2'], area)
            metrics.append({'sample': sample, 'voice': voice, 'row': index, 'terminal_area_cm2': float(area[-1]),
                'terminal_flow_cm3_s': float(flow[-1]), 'terminal_velocity_cm_s': float(velocity[-1]),
                'minimum_velocity_cm_s': float(velocity.min()), 'maximum_absolute_velocity_cm_s': float(np.max(abs(velocity)))})
    by_key = {(row['voice'], row['sample']): row for row in metrics}
    closed, opened = (by_key[2, at] for at in (30720, 34560))
    return {'recorded_tracks_match_independent_reader': bool(indices_match),
        'recorded_closed_and_open_jet': closed['terminal_area_cm2'] == 0 and opened['terminal_area_cm2'] > 0
            and 0 < closed['terminal_velocity_cm_s'] < opened['terminal_velocity_cm_s'],
        'recorded_signed_backflow_and_quiet_track': by_key[1, 46080]['minimum_velocity_cm_s'] < 0
            and by_key[2, 21504]['maximum_absolute_velocity_cm_s'] < setting['low_velocity_cm_s']}, metrics


def browser_checks(log, sources, spec, glottis):
    options, setting = spec['browser'], spec['dynamics']
    states = [*log['paused'], log['started'], *(x for step in log['live'] for x in step['frames']),
              *log['held'], log['resumed'], log['hidden'], log['restored']]
    source_match = rendered = True
    glottis_error = positions_error = motion_error = 0.
    pairs_checked = 0
    for state in states:
        for voice, (source, head) in enumerate(zip(sources, state['heads'], strict=True), 1):
            clock = head['clock']
            row = min(len(source['areas']) - 1, int(clock['time'] * options['sample_rate_hz'] / source['hop'] + 1e-6))
            source_match &= (head['index'] == row and head['sample'] == row * source['hop'] and state['epoch'] == clock['epoch']
                             and len(head['particles']) == setting['particle_count'])
            if (voice, row) in glottis:
                glottis_error = max(glottis_error, gap(head['glottis'], glottis[voice, row]))
            if clock['playing'] and head['enabled']:
                nodes = positions(source['lengths'][row], source['pharynx'], source['oral'])
                positions_error = max(positions_error, gap(nodes, head['nodes']))
                source_match &= gap(source['flow'][row], head['flow']) == gap(source['areas'][row], head['areas']) == 0
            else:
                source_match &= not any(head[field] for field in ('nodes', 'flow', 'areas', 'trails'))
            expected = [[], [], []]
            for trail in head['trails']:
                expected[trail['band']].extend(trail['from'] + trail['to'])
            rendered &= all(gap(np.float32(f), a) == 0 for f, a in zip(expected, head['vertices'], strict=True))
    first_frames, trail_counts = True, []
    for recorded_seek, target in zip(log['live'], options['live_seeks'], strict=True):
        first, second = recorded_seek['frames']
        first_frames &= recorded_seek['target'] == target == first['sample'] and first['epoch'] == second['epoch']
        first_frames &= all(head['clock']['playing'] and not head['trails'] for head in first['heads'])
        counts = [len(head['trails']) for head in second['heads']]
        trail_counts.append(counts)
        for old, new in zip(first['heads'], second['heads'], strict=True):
            dt = new['dt']
            first_frames &= 0 < dt <= setting['display_step_limit_seconds']
            nodes = np.asarray(new['nodes'])
            for trail in new['trails']:
                i = trail['particle']
                previous, current = old['particles'][i], new['particles'][i]
                _, speed = speed_at(previous['s'], nodes, new['areas'], new['flow'], setting)
                motion_error = max(motion_error, abs(previous['s'] + speed * dt - current['s']),
                    abs(previous['life'] - dt * setting['life_decay_per_second'] - current['life']),
                    difference(previous['previous'], trail['from']), difference(current['previous'], trail['to']))
                pairs_checked += 1
    resume_links = 0
    for held, resumed in zip(log['held'][-1]['heads'], log['resumed']['heads'], strict=True):
        for trail in resumed['trails']:
            motion_error = max(motion_error, difference(held['particles'][trail['particle']]['previous'], trail['from']))
            resume_links += 1
    paused = log['held'][0] == log['held'][1] and [s['sample'] for s in log['paused']] == options['samples']
    return {'no_browser_errors': not log['errors'], 'per_voice_source_and_cli_glottis': bool(source_match
            and max(glottis_error, positions_error) <= setting['position_tolerance_cm']),
        'finite_segments_in_drawing_buffers': bool(rendered and all(all(item) for item in trail_counts)),
        'first_live_seek_clears_previous_trails': bool(first_frames),
        'independent_steps_and_resume': bool(pairs_checked > 0 and resume_links > 0 and motion_error <= setting['position_tolerance_cm']),
        'paused_hold_and_airflow_toggle': paused and all(not h['clock']['playing'] for h in log['held'][-1]['heads'])
            and all(not h['enabled'] and not h['trails'] for h in log['hidden']['heads'])
            and all(h['enabled'] and not h['trails'] for h in log['restored']['heads'])}, {
        'width': log['width'], 'max_wasm_glottis_cm': glottis_error, 'max_node_cm': positions_error,
        'max_particle_step_error': motion_error, 'segments_following_seeks': trail_counts,
        'checked_segments_following_seeks': pairs_checked, 'previous_segments_preserved_on_resume': resume_links}


def measure(spec, artifacts, execute, bun):
    execute(['cargo', 'build', '--locked', '--release', '-p', 'vocal-cli'])
    execute([*bun, 'test', 'tests/tele.test.ts', 'tests/transport.test.ts'], cwd=UPSTREAM)
    execute([*bun, 'run', 'build'], cwd=WEB)
    execute([*bun, str(CAPTURE), str(CASE), str(UPSTREAM), str(artifacts)], cwd=WEB)
    sources = [track(DEMO / f'voice-{i}.tele', spec['browser']['sample_rate_hz']) for i in (1, 2)]
    upper = read_json(artifacts / 'recorded-airflow.json')
    checks, control = controlled(read_json(artifacts / 'controlled-airflow.json'), spec)
    checked, real = recorded(sources, upper, spec)
    checks.update(checked)
    glottis, upper_error = {}, 0.
    for voice, (frames, source) in enumerate(zip(upper, sources, strict=True), 1):
        source['rows'] = source['artic'].tolist()
        for frame in frames:
            row = frame['index']
            native = cli_geometry(voice - 1, row, source, spec, artifacts, execute)['glottis'][0]
            glottis[voice, row] = native
            upper_error = max(upper_error, gap(native, frame['glottis']))
    checks['upper_wasm_matches_cli_glottis'] = upper_error <= spec['dynamics']['position_tolerance_cm']
    browser = read_json(artifacts / 'browser-airflow.json')
    metrics = []
    for path in browser['viewports']:
        log = read_json(artifacts / path)
        checked, values = browser_checks(log, sources, spec, glottis)
        checks.update({f'{log["width"]}_{key}': value for key, value in checked.items()})
        metrics.append(values)
    return {'checks': checks, 'browser': browser['browser'], 'controlled': control, 'recorded': real,
            'upper_glottis_max_cm': upper_error, 'viewports': metrics}


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
    pressure = prior(ref['pressure_run'], 'duet-head-pressure', revision, ref['pressure_manifest_sha256'])
    if sha256(UPPER_WASM) != ref['upper_wasm_sha256'] or any(
            sha256(DEMO / f'voice-{voice}.tele') != digest for voice, digest in enumerate(ref['track_sha256'], 1)):
        parser.error('登録済みの上流WASM・テレメトリが必要です')
    bun = ['bun'] if shutil.which('bun') else ['npx', '--yes', '--package=bun@1.4.4', '--', 'bun']
    paths = ('src/show/tele.ts', 'src/wasm/engine.ts', 'src/ui/analysis.ts', 'src/ui/components/DuetPage.tsx',
             'src/ui/components/AnatomyView3D.tsx', 'src/ui/render/anatomy3d.ts', 'src/ui/render/beams3d.ts',
             'tests/tele.test.ts', 'tests/transport.test.ts')
    details = {'case_id': spec['id'], 'upstream_revision': revision, 'upstream_wasm_sha256': ref['upper_wasm_sha256'],
        'bun': subprocess.check_output([*bun, '--version'], text=True).strip(),
        'upstream_source_sha256': {path: sha256(UPSTREAM / path) for path in paths}}
    inputs = [CASE, CAPTURE, Path(__file__), Path(shared.__file__),
              *(WORKSPACE / f'tools/{name}.py' for name in ('measure_duet_head_pressure', 'measure_duet_heads')),
              pressure[0] / 'manifest.json', *sorted(DEMO.iterdir()), *web_sources(), *shared.candidate_sources()]
    return shared.record_measurement(args.run_id, CASE, inputs, details,
        lambda artifacts, execute: measure(spec, artifacts, execute, bun), command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
