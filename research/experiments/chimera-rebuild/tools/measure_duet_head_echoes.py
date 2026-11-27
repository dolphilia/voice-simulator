"""デュエットの輪郭の残像を、固定上流の描画と独立した時刻・頂点の計算に照合する。"""

import argparse
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

CASE = WORKSPACE / 'cases/duet-head-echoes.json'
CAPTURE = WEB / 'tools/capture-duet-head-echoes.mjs'
DEMO = WEB / 'public/shows/duet-clock'
UPPER_WASM = UPSTREAM / 'target/wasm32-unknown-unknown/release/chimera_wasm.wasm'


def oracle(records, spec):
    display = spec['display']
    history, last, previous = [], -1.0, None
    spacing, retention, threshold = (display[key] / 1000 for key in
        ('minimum_capture_interval_ms', 'retention_ms', 'max_offset_ms_exclusive'))
    for row in records:
        if previous and (row['epoch'] != previous['epoch'] or row.get('rewound', False)):
            history, last = [], -1.0
        previous = row
        now = row['now']
        if row['playing'] and now - last >= spacing:
            last = now
            history = [item for item in history if now - item['now'] <= retention] + [row]
        selected = []
        for age in display['target_ages_ms']:
            target = now - age / 1000
            fit = sorted(((abs(item['now'] - target), item['now'], item) for item in history),
                         key=lambda item: item[:2])
            selected.append(fit[0][2] if row['playing'] and fit and fit[0][0] < threshold else None)
        yield selected


def controlled_checks(spec, voices):
    display = spec['display']
    clock_limit = display['clock_step_limit_ms'] / 1000
    tolerance = spec['state_tolerance_seconds']
    frames = spec['controlled_clock']
    records = []
    now = 0.0
    for i, (elapsed, sample, playing, epoch) in enumerate(frames):
        now += min(clock_limit, elapsed / 1000)
        records.append({'sample': sample, 'playing': playing, 'epoch': epoch, 'now': now, 'step': i})
    predicted = list(oracle(records, spec))
    checks = {}
    details = []
    for voice, rows in enumerate(voices, 1):
        picked = 0
        exact_max = 0.0
        upstream_draw_max = 0.0
        clocks = len(rows) == len(frames)
        slots_match, opacity_match, parts_match = True, True, True
        open_draws, closed_draws = 0, 0
        for i, (row, slots, clock) in enumerate(zip(rows, predicted, records, strict=True)):
            clocks &= abs(row['upperTime'] - clock['now']) <= tolerance and abs(row['candidateTime'] - clock['now']) <= tolerance
            upper = row['upper'] if row['playing'] else [None, None, None]
            slots_match &= len(upper) == len(row['candidate']) == len(slots)
            for key, (up, candidate, wanted) in enumerate(zip(upper, row['candidate'], slots, strict=True)):
                if not wanted:
                    slots_match &= up is None and candidate is None
                    continue
                if up is None or candidate is None:
                    slots_match = False
                    continue
                old = rows[wanted['step']]
                slots_match &= (up['sample'] == candidate['pose']['sample'] == wanted['sample']
                    and up['index'] == candidate['pose']['index'] == old['index']
                    and up['epoch'] == candidate['pose']['epoch'] == wanted['epoch']
                    and abs(up['time'] - candidate['time']) <= tolerance and abs(up['time'] - wanted['now']) <= tolerance)
                is_open = len(up['lines']) == 5
                parts_match &= len(up['lines']) in (4, 5) and is_open == old['expectedOpening']
                open_draws += is_open
                closed_draws += not is_open
                opacity = display['opacities'][key]
                opacity_match &= abs(candidate['opacity'] - opacity) <= tolerance and all(
                    abs(line['alpha'] - opacity) <= tolerance for line in up['lines'])
                coordinates = np.asarray(up['lines'][0]['vertices']).reshape(-1, 3)
                direct = np.asarray(old['directTongue']).reshape(-1, 2)
                shape = np.asarray(candidate['pose']['tongue']).reshape(-1, 2)
                exact_max = max(exact_max, float(np.max(np.abs(shape - direct))))
                upstream_draw_max = max(upstream_draw_max, float(np.max(np.abs(coordinates[:, :2] - direct))))
                parts_match &= bool((coordinates[:, 2] == 0).all())
                picked += 1
        checks[f'voice_{voice}_visual_clock_and_cap'] = clocks
        checks[f'voice_{voice}_upstream_selection_and_alpha'] = slots_match and opacity_match and picked >= 20
        checks[f'voice_{voice}_mouth_outline_only_when_open'] = parts_match and open_draws > 0 and closed_draws > 0
        checks[f'voice_{voice}_wasm_tongue_matches_direct_upstream'] = exact_max <= spec['coordinate_tolerance_cm']
        details.append({'voice': voice, 'compared_selections': picked, 'open_draws': open_draws, 'closed_draws': closed_draws,
            'max_direct_to_candidate_cm': exact_max, 'max_direct_to_upper_drawn_cm': upstream_draw_max})
    return checks, details


def expected_opening(head, spec):
    upper, lower = (np.asarray(rim).reshape(-1, 3) for rim in head['lipRims'])
    middle = len(upper) // 2
    threshold = spec['display']['open_gap_per_body_scale_cm'] * head['scale']
    if upper[middle, 1] - lower[middle, 1] <= threshold:
        return None
    return np.vstack([upper, lower[::-1], upper[0]]).ravel().tolist()


def browser_checks(spec, data, artifacts):
    opts = spec['browser']
    tol = spec['state_tolerance_seconds']
    rate = spec['sample_rate_hz']
    tracks = [struct.unpack_from('<II', (DEMO / f'voice-{i}.tele').read_bytes(), 12) for i in (1, 2)]
    checks = {'no_uncaught_browser_errors': not data['errors']}
    detail = []
    for view in data['viewports']:
        width = view['width']
        trace = view['trace']
        markings = view['markers']
        frames = [dict(row['clock'], now=row['clock']['motionTime'], step=i,
            rewound=i > 0 and row['clock']['time'] < trace[i - 1]['clock']['time']) for i, row in enumerate(trace)]
        geometry_ok, timing_ok, opacity_ok = True, True, True
        totals = [0, 0]
        maximum_error = 0.0
        opening_draws = [0, 0]
        for row, selected in zip(trace, oracle(frames, spec), strict=True):
            for voice, head in enumerate(row['heads']):
                geometry_ok &= head['base'][4] == expected_opening(head, spec)
                totals[voice] += all(head['slots'])
                for i, (slot, expected) in enumerate(zip(head['slots'], selected, strict=True)):
                    if expected is None or slot is None:
                        timing_ok &= expected is None and slot is None
                        continue
                    source = trace[expected['step']]
                    aperture = source['heads'][voice]
                    hop, count = tracks[voice]
                    expected_index = min(count - 1, int(source['clock']['time'] * rate / hop + 1e-6))
                    timing_ok &= slot['epoch'] == row['clock']['epoch'] == source['clock']['epoch'] and (
                        slot['index'] == expected_index and slot['sample'] == expected_index * hop
                        and abs(slot['time'] - expected['now']) <= tol)
                    geometry_ok &= slot['contours'] == aperture['base']
                    opening_draws[voice] += slot['contours'][4] is not None
                    for op, part in zip(slot['opacities'], slot['contours'], strict=True):
                        if part is None:
                            opacity_ok &= op is None
                        else:
                            error = abs(op - spec['display']['opacities'][i])
                            opacity_ok &= error <= tol
                            maximum_error = max(maximum_error, error)
        checks[f'{width}_echo_selection_and_source_position'] = timing_ok and all(
            n >= opts['minimum_complete_echo_frames_per_voice'] for n in totals)
        checks[f'{width}_echo_vertices_and_opacity'] = geometry_ok and opacity_ok and all(opening_draws)

        def no_echoes(row):
            return all(not any(head['slots']) for head in row['heads'])

        seeks = [trace[i] for i in markings['liveSeeks']]
        checks[f'{width}_both_live_seeks_clear_prior_geometry'] = (
            [row['sample'] for row in seeks] == opts['live_seek_samples'] and
            all(row['clock']['playing'] and no_echoes(row) for row in seeks))
        paused = trace[markings['pause']]
        held = trace[markings['hold']]
        resumed = trace[markings['resume']]
        paused_seek = trace[markings['pausedSeek']]
        checks[f'{width}_pause_seek_resume'] = (paused == held and not paused['clock']['playing'] and no_echoes(paused)
            and paused_seek['sample'] == resumed['sample'] == opts['paused_seek_sample']
            and not paused_seek['clock']['playing'] and resumed['clock']['playing'] and no_echoes(paused_seek)
            and no_echoes(resumed) and any(not no_echoes(row) for row in trace[markings['resume'] + 1:]
                                           if row['clock']['epoch'] == resumed['clock']['epoch']))
        photos = view['photos']
        start, end = photos['playing'], photos['paused']
        active = next(row for row in trace if row['clock']['epoch'] == start['epoch'] and row['sample'] == start['sample']
                      and row['clock']['playing'])
        still = trace[markings['picturePaused']]
        images = [np.asarray(Image.open(artifacts / photos[key]['path']).convert('RGB'), dtype=np.int16)
                  for key in ('playing', 'paused')]
        changed = int(np.any(np.abs(images[0] - images[1]) >= 6, axis=2).sum())
        shift = max(float(np.max(np.abs(np.array(active['heads'][0]['base'][3]) - slot['contours'][3])))
                    for slot in active['heads'][0]['slots'] if slot)
        checks[f'{width}_equal_pose_pixel_control'] = (
            start['sample'] == end['sample'] == still['sample'] and no_echoes(still)
            and active['heads'][0]['base'] == still['heads'][0]['base']
            and shift >= opts['minimum_picture_lip_displacement_cm']
            and changed >= opts['minimum_picture_changed_pixels'])
        detail.append({'width_css_px': width, 'observed_frames': len(trace), 'all_three_ages_frames_per_voice': totals,
            'opening_draws_per_voice': opening_draws, 'photo_sample': start['sample'], 'changed_pixels': changed,
            'photo_lip_displacement_cm': shift, 'max_opacity_error': maximum_error})
    return checks, detail


def measure(spec, artifacts, execute, bun):
    execute([*bun, 'test', 'tests/tele.test.ts', 'tests/transport.test.ts'], cwd=UPSTREAM)
    execute([*bun, 'run', 'build'], cwd=WEB)
    execute([*bun, str(CAPTURE), str(CASE), str(UPSTREAM), str(artifacts)], cwd=WEB)
    controlled, comparison = controlled_checks(spec, read_json(artifacts / 'controlled-echoes.json'))
    browser = read_json(artifacts / 'browser-echoes.json')
    browsers, viewports = browser_checks(spec, browser, artifacts)
    return {'checks': {**controlled, **browsers}, 'browser': browser['browser'], 'controlled_clock': comparison,
            'viewports': viewports}


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
    heads = prior(ref['heads_run'], 'duet-heads', revision, ref['heads_manifest_sha256'])
    mouth = prior(ref['mouth_run'], 'duet-mouth-words', revision, ref['mouth_manifest_sha256'])
    if sha256(UPPER_WASM) != ref['upstream_wasm_sha256'] or any(
            sha256(DEMO / f'voice-{i}.tele') != expected for i, expected in enumerate(ref['track_sha256'], 1)):
        parser.error('比較用のWASMまたはテレメトリが登録値と異なります')
    bun = ['bun'] if shutil.which('bun') else ['npx', '--yes', '--package=bun@1.4.4', '--', 'bun']
    upper_sources = ('src/ui/components/DuetPage.tsx', 'src/ui/components/AnatomyView3D.tsx', 'src/ui/render/anatomy3d.ts',
                     'src/ui/render/beams3d.ts', 'src/ui/render/vector.ts', 'src/show/tele.ts', 'src/ui/analysis.ts',
                     'tests/tele.test.ts', 'tests/transport.test.ts')
    details = {'case_id': spec['id'], 'upstream_revision': revision, 'upstream_wasm_sha256': sha256(UPPER_WASM),
        'upstream_source_sha256': {name: sha256(UPSTREAM / name) for name in upper_sources},
        'bun': subprocess.check_output([*bun, '--version'], text=True).strip()}
    inputs = [CASE, CAPTURE, Path(__file__), Path(shared.__file__), *(p / 'manifest.json' for p in (heads[0], mouth[0])),
              *sorted(DEMO.iterdir()), *web_sources(), *shared.candidate_sources()]
    return shared.record_measurement(args.run_id, CASE, inputs, details,
        lambda artifacts, execute: measure(spec, artifacts, execute, bun), command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
