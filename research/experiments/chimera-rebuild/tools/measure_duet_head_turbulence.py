"""生成側の乱流枝を、固定上流・独立投影・実ブラウザと照合する。"""

import argparse
from math import log10
from pathlib import Path
import re
import shutil
import subprocess

import numpy as np

import measure_uniform_tube as shared
from measure_duet_head_airflow import project, section_values
from measure_duet_head_pressure import DEMO, UPPER_WASM, gap
from measure_duet_telemetry import CASE as TELEMETRY_CASE, Track, TRANSPORT_CASE
from measure_duet_words import prior
from measure_fan_crossing_allocations import verified_path
from measure_wasm_fixed import read_json
from measure_worklet_fixed import ROOT, WEB, web_sources
from upstream_baseline import UPSTREAM, WORKSPACE, sha256

CASE = WORKSPACE / 'cases/duet-head-turbulence.json'
CAPTURE = WEB / 'tools/capture-duet-head-turbulence.mjs'


def origin(layout, source, settings):
    branch = source['noiseNode']
    if branch == layout['glottis_port']:
        return settings['glottal_origin_cm']
    for name, start, key in (('pharynx', 0., 'phLen'), ('oral', source['phLen'], 'orLen')):
        span = layout[name]
        number = branch - span['base'] + 1
        if 1 <= number < span['cells']:
            return start + (number / span['cells']) * source[key]
    return None


def trace_segments(seed, grid, glottis, scale, layout, source, cfg):
    s = origin(layout, source, cfg)
    intensity = min(1., log10(source['noiseLevel']) / 3.2) if source['noiseLevel'] > 1 else 0.
    if s is None or s < 0 or intensity <= cfg['minimum_intensity']:
        return s, intensity, seed, []
    factor, prime = cfg['prng_multiplier'], cfg['prng_modulus']
    next_seed = seed * factor % prime
    index = next_seed

    def random():
        nonlocal index
        index = index * factor % prime
        return index / prime

    distances, sections = section_values(grid, scale)
    glottis = np.asarray(glottis)
    lo, hi = cfg['segment_offset_cm']
    short, long = cfg['half_length_cm']
    lines = []
    for _ in range(cfg['segments_per_frame']):
        point = project({'s': s + lo + random() * (hi - lo), 'u': 2 * random() - 1, 'v': 2 * random() - 1},
                        distances, sections, glottis, scale, .82)
        if point is None:
            continue
        x, y, z = point
        half = short + random() * (long - short)
        lines.append({'from': [x - half, y, z], 'to': [x + half, y, z], 'alpha': .15 + .7 * intensity * random()})
    return s, intensity, next_seed, lines


def segment_errors(observed, expected):
    xyz = alpha = 0.
    for a, b in zip(observed, expected):
        xyz = max(xyz, gap(a['from'], b['from']), gap(a['to'], b['to']))
        alpha = max(alpha, abs(a['alpha'] - b['alpha']))
    return len(observed) == len(expected), xyz, alpha


def controlled(result, spec):
    cfg = spec['diagnostic']
    seed = cfg['initial_seed']
    errors = np.zeros((2, 2))
    same = origins = True
    rows = []
    for item in result['trace']:
        candidate = item['candidate']
        s, intensity, after, lines = trace_segments(seed, result['grid'], result['glottis'], result['scale'],
                                                    result['layout'], item['source'], cfg)
        origins &= item['upperS'] == (-1 if s is None else s) and candidate['s'] == s
        same &= (candidate['seedBefore'] == item['upperBefore'] == seed and candidate['seedAfter'] == item['upperAfter'] == after
                 and abs(candidate['intensity'] - intensity) <= 1e-12)
        for i, draw in enumerate((candidate['segments'], item['upperSegments'])):
            size_matches, xyz, alpha = segment_errors(draw, lines)
            same &= size_matches
            errors[i] = np.maximum(errors[i], [xyz, alpha])
        rows.append({'branch': item['source']['noiseNode'], 'level': item['source']['noiseLevel'], 's_cm': s,
                     'intensity': intensity, 'segment_count': len(lines), 'seed_before': seed, 'seed_after': after})
        seed = after
    level_count = len(cfg['levels'])
    checks = {'fixed_upper_branch_positions': bool(origins),
        'same_segments_and_rng_as_fixed_upper': bool(same and np.max(errors[:, 0]) <= cfg['position_tolerance_cm']
                                                    and np.max(errors[:, 1]) <= 1e-12),
        'level_cutoff_and_unknown_branch': all(row['segment_count'] == (0 if row['intensity'] <= cfg['minimum_intensity']
                else cfg['segments_per_frame']) for row in rows[:level_count])
            and all(not row['segment_count'] and row['seed_before'] == row['seed_after'] for row in rows if row['s_cm'] is None),
        'clipping_at_lip': any(row['s_cm'] is not None and row['s_cm'] > 5
                              and 0 < row['segment_count'] < cfg['segments_per_frame'] for row in rows)}
    return checks, {'error_xyz_and_alpha': errors.tolist(), 'frames': rows}


def source_at(track, row):
    data = track.values[row]
    return {name: float(data[index]) for name, index in (('phLen', 0), ('orLen', 1), ('noiseLevel', 7), ('noiseNode', 8))}


def recorded(spec, tracks, layouts, upper):
    cfg = spec['diagnostic']
    match = True
    rows = []
    for voice, (track, layout, upper_data) in enumerate(zip(tracks, layouts, upper, strict=True), 1):
        for sample, frame in zip(spec['browser']['samples'], upper_data['frames'], strict=True):
            current = sample // track.hop
            source = source_at(track, current)
            match &= current == frame['index'] and sample == frame['sample'] and all(frame[key] == v for key, v in source.items())
            s = origin(layout, source, cfg)
            reference = origin(upper_data['layout'], source, cfg)
            match &= frame['s'] == (-1 if reference is None else reference)
            rows.append({'voice': voice, 'sample': sample, 'row': current, **source, 'candidate_s_cm': s, 'upper_s_cm': reference})
    by_key = {(row['voice'], row['sample']): row for row in rows}
    pairs = [by_key[1, 30720], by_key[2, 34560]]
    mouth = [by_key[1, 46080], by_key[2, 49920]]
    checks = {'same_recording_decoded_by_upper_and_python': bool(match),
        'mislocated_glottal_branch_without_provenance': all(row['candidate_s_cm'] == cfg['glottal_origin_cm']
            and row['upper_s_cm'] is None for row in pairs),
        'oral_branch_and_quiet_recording': all(row['candidate_s_cm'] is not None and row['candidate_s_cm'] > row['phLen']
            and row['candidate_s_cm'] == row['upper_s_cm'] for row in mouth)
            and by_key[2, 21504]['noiseLevel'] == 0}
    return checks, rows


def browser_checks(spec, log, tracks, layouts):
    cfg, opts = spec['diagnostic'], spec['browser']
    source_ok = drawing_ok = True
    max_xyz = max_alpha = 0.
    visibility = []
    states = [*log['paused'], log['started'], *(row['observed'] for row in log['live']), log['restored'], log['held']]
    for state in states:
        counts = []
        for head, track, layout in zip(state['heads'], tracks, layouts, strict=True):
            clock = head['clock']
            index = min(track.rows - 1, int(clock['time'] * track.rate / track.hop + 1e-6))
            source_ok &= clock['epoch'] == state['epoch'] and head['index'] == index and head['sample'] == index * track.hop
            if not clock['playing']:
                drawing_ok &= head['frame'] is None and not head['alpha'] and not head['vertices']
                counts.append(0)
                continue
            source = source_at(track, index)
            frame = head['frame']
            if frame is None:
                drawing_ok = False
                counts.append(0)
                continue
            source_ok &= head['source'] == source
            s, intensity, seed, expected = trace_segments(frame['seedBefore'], head['grid'], head['glottis'], head['scale'],
                                                           layout, source, cfg)
            drawing_ok &= frame['s'] == s and frame['seedAfter'] == seed and abs(frame['intensity'] - intensity) <= 1e-12
            matched, xyz, alpha = segment_errors(frame['segments'], expected)
            drawing_ok &= matched
            max_xyz, max_alpha = max(max_xyz, xyz), max(max_alpha, alpha)
            points = [x for line in frame['segments'] for point in (line['from'], line['to']) for x in point]
            opacities = [line['alpha'] for line in frame['segments'] for _ in range(2)]
            drawing_ok &= gap(head['vertices'], np.float32(points)) == gap(head['alpha'], np.float32(opacities)) == 0
            counts.append(len(expected))
        visibility.append({'sample': state['sample'], 'segments': counts})
    seeks = [*filter(lambda sample: sample not in opts['live_seeks'], opts['samples']), *opts['live_seeks']]
    exact = all(row['target'] == target == row['observed']['sample'] and
                 all(head['clock']['playing'] for head in row['observed']['heads'])
                 for row, target in zip(log['live'], seeks, strict=True))
    live_counts = {row['target']: [len(head['frame']['segments']) if head['frame'] else -1 for head in row['observed']['heads']]
                   for row in log['live']}
    required = opts.get('required_live_sources', [
        {'sample': 30720, 'voice': 1, 'visible': True}, {'sample': 34560, 'voice': 2, 'visible': True},
        {'sample': 46080, 'voice': 1, 'visible': True}, {'sample': 49920, 'voice': 2, 'visible': True},
        {'sample': 21504, 'voice': 2, 'visible': False},
    ])
    visible = all((n := live_counts[item['sample']][item['voice'] - 1]) >= 0 and (n > 0) == item['visible']
                  for item in required)
    return {'no_browser_or_shader_errors': not log['errors'], 'source_follows_registered_seeks': bool(source_ok and exact),
        'segments_match_independent_projection_and_gpu_buffers': bool(drawing_ok and max_xyz <= cfg['position_tolerance_cm']
                                                                     and max_alpha <= 1e-12),
        'glottal_oral_and_quiet_frames': visible,
        'pause_and_toggle': [state['sample'] for state in log['paused']] == opts['samples']
            and all(head['frame'] is None and not head['vertices'] for head in log['hidden']['heads'])
            and all(head['frame'] is not None for head in log['restored']['heads'])}, {
                'width': log['width'], 'max_vertex_error_cm': max_xyz, 'max_alpha_error': max_alpha,
                'live_segments_by_sample': live_counts, 'frames': visibility}


def measure(spec, stems, artifacts, execute, bun):
    execute(['cargo', 'build', '--locked', '--release', '-p', 'vocal-cli'])
    execute([*bun, 'test', 'tests/tele.test.ts', 'tests/transport.test.ts'], cwd=UPSTREAM)
    execute([*bun, 'run', 'build'], cwd=WEB)
    tracks, layouts = [], []
    show = read_json(DEMO / 'show.json')
    for i, (voice, stem) in enumerate(zip(show['voices'], stems, strict=True), 1):
        path = artifacts / f'voice-{i}-layout.json'
        execute([str(WORKSPACE / 'target/release/vocal-cli'), 'inspect', str(stem)], stdout=path)
        layouts.append(read_json(path)['noise_branches'])
        tracks.append(Track(DEMO / voice['tele']))
    execute([*bun, str(CAPTURE), str(CASE), str(UPSTREAM), str(artifacts)], cwd=WEB)
    browser = read_json(artifacts / 'browser-turbulence.json')
    controls, detail = controlled(read_json(artifacts / 'controlled-turbulence.json'), spec)
    upper = read_json(artifacts / 'recorded-turbulence.json')
    source_checks, samples = recorded(spec, tracks, layouts, upper)
    checks = {**controls, **source_checks,
              'manifest_matches_articulated_cli_layout': all(v['noise_branches'] == layout for v, layout in zip(show['voices'], layouts)),
              'legacy_show_still_plays': browser['metadata']['legacyPlayback'],
              'wrong_rate_is_rejected': 'テレメトリの形式' in browser['metadata']['badLayout']}
    viewports = []
    for path in browser['viewports']:
        tests, values = browser_checks(spec, read_json(artifacts / path), tracks, layouts)
        checks.update({f'{values["width"]}_{name}': status for name, status in tests.items()})
        viewports.append(values)
    return {'checks': checks, 'browser': browser['browser'], 'control': detail, 'recorded': samples,
            'candidate_layouts': layouts, 'upper_layouts': [v['layout'] for v in upper], 'viewports': viewports}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', args.run_id):
        parser.error('英数字で始まる実行IDが必要です')
    spec = read_json(CASE)
    rev = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if rev != spec['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True):
        parser.error('変更のない固定上流版が必要です')
    ref = spec['reference']
    airflow = prior(ref['airflow_run'], 'duet-head-airflow', rev, ref['airflow_manifest_sha256'])
    transport_ref = read_json(TELEMETRY_CASE)['reference']
    transport = prior(transport_ref['run'], read_json(TRANSPORT_CASE)['id'], rev, transport_ref['manifest_sha256'])
    stems = [verified_path(transport, f'artifacts/voice-{i}.json') for i in (1, 2)]
    if sha256(UPPER_WASM) != ref['upper_wasm_sha256'] or any(
            sha256(DEMO / f'voice-{i}.tele') != digest for i, digest in enumerate(ref['track_sha256'], 1)):
        parser.error('登録済みの上流WASM・テレメトリが必要です')
    bun = ['bun'] if shutil.which('bun') else ['npx', '--yes', '--package=bun@1.4.4', '--', 'bun']
    paths = ('src/show/tele.ts', 'src/ui/analysis.ts', 'src/ui/render/anatomy3d.ts', 'src/wasm/engine.ts',
             'crates/chimera-wasm/src/api.rs', 'crates/chimera/src/voice/human_voice.rs', 'tests/tele.test.ts', 'tests/transport.test.ts')
    details = {'case_id': spec['id'], 'upstream_revision': rev, 'upstream_wasm_sha256': ref['upper_wasm_sha256'],
               'bun': subprocess.check_output([*bun, '--version'], text=True).strip(),
               'upstream_source_sha256': {name: sha256(UPSTREAM / name) for name in paths}}
    tools = [WORKSPACE / f'tools/{name}.py' for name in ('measure_duet_head_airflow', 'measure_duet_telemetry')]
    inputs = [CASE, CAPTURE, Path(__file__), Path(shared.__file__), TELEMETRY_CASE, TRANSPORT_CASE, *tools,
              airflow[0] / 'manifest.json', transport[0] / 'manifest.json', *stems,
              *sorted(DEMO.iterdir()), *web_sources(), *shared.candidate_sources()]
    return shared.record_measurement(args.run_id, CASE, inputs, details,
        lambda artifacts, execute: measure(spec, stems, artifacts, execute, bun), command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
