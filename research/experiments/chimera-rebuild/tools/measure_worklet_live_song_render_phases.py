"""Firefoxの歌唱量子を、WASM描画とJS観測に分けて計測する。"""

import argparse
from collections import Counter
import gzip
import json
from pathlib import Path
import re
import shutil
from statistics import median
import subprocess
import sys

import numpy as np
from scipy.io import wavfile

import measure_worklet_song_firefox_registration_native as registration


song = registration.song
cross = registration.cross
CASE = song.WORKSPACE / 'cases/worklet-live-song-render-phases.json'
WARMUP_CASE = song.WORKSPACE / 'cases/worklet-live-song-render-warmup.json'
FRAME_CASE = song.WORKSPACE / 'cases/worklet-live-song-render-warmup-frames.json'
INTERMEDIATE_CASE = song.WORKSPACE / 'cases/worklet-live-song-render-warmup-intermediate.json'
AUTHOR_MARKER = 'AudioWorkletNodeEngine::CallProcess'
CONSTRUCTOR_MARKER = 'AudioWorkletProcessor::ConstructProcessor'
PREFIX = 'chimera-song-phase:'
PREPARATION_PHASES = ('prepare-start', 'zero-start', 'zero-end', 'render-start', 'render-end', 'prepare-end')
PHASE = re.compile(r'(\d+):(\d+):([a-z-]+)')
REFERENCE = ('summary.json', 'artifacts/1-chromium/browser.json.gz', 'artifacts/reference/pcm-128.wav',
             'artifacts/reference/upstream-pcm.f32.gz', 'artifacts/vocal_wasm.wasm')
OFFLINE_REFERENCE = ('summary.json', 'artifacts/browser.json', 'artifacts/browser.wav', 'artifacts/pcm-128.wav',
                     'artifacts/upstream-pcm.f32', 'artifacts/vocal_wasm.wasm')


def console_timestamps(thread, prefix):
    for name, start, _, phase, payload in registration.markers(thread):
        if name != 'ConsoleTiming' or phase != 0 or payload.get('entryType') != 'timeStamp':
            continue
        label = payload.get('label')
        if type(label) is int:
            label = thread['stringTable'][label]
        if isinstance(label, str) and label.startswith(prefix):
            yield label.removeprefix(prefix), start


def trace_markers(thread):
    phases, calibration = {}, []
    for item, start in console_timestamps(thread, PREFIX):
        if item == 'calibration':
            calibration.append(start)
            continue
        match = PHASE.fullmatch(item)
        if match is None:
            raise ValueError(f'歌唱の計測マーカーの形式が不正です ({item})')
        frame, offset, kind = match.groups()
        marks = phases.setdefault(int(frame), {})
        key = (int(offset), kind)
        if key in marks:
            raise ValueError(f'同じ歌唱の計測マーカーが重複しました ({item})')
        marks[key] = start
    return phases, calibration


def marker_keys(quantum, stride):
    result = [(0, 'quantum-start')]
    for offset in range(0, quantum, stride):
        result.extend((offset, phase) for phase in ('render-start', 'wasm-start', 'wasm-end', 'render-end'))
        result.extend((offset + stride, phase) for phase in ('observation-start', 'observation-end'))
    result.append((quantum, 'quantum-end'))
    return result


def preparation_timing(thread, condition, first_author_start, expected_setup=None, *, processor=None, kind='song'):
    spans, _ = registration.native.thread_intervals(thread, CONSTRUCTOR_MARKER, processor=processor)
    marks = list(console_timestamps(thread, f'chimera-{kind}-preparation:'))
    setup_marks = list(console_timestamps(thread, f'chimera-{kind}-preparation-result:'))
    checks = {'constructor_before_first_process': len(spans) == 1 and spans[0][1] <= first_author_start}
    result = {'marker_times_ms': marks}
    if checks['constructor_before_first_process']:
        start, end = spans[0]
        result['constructor_ms'] = end - start
        values = [time for _, time in marks]
        if condition == 'control':
            checks['control_has_no_preparation_markers'] = not (marks or setup_marks)
        else:
            checks['preparation_inside_constructor'] = (tuple(name for name, _ in marks) == PREPARATION_PHASES
                and sorted(values) == values and start <= values[0] <= values[-1] <= end)
            if checks['preparation_inside_constructor']:
                prepare, zero_start, zero_end, render_start, render_end, free = values
                result.update({'preparation_ms': free - prepare, 'discarded_initialization_ms': zero_start - prepare,
                               'zero_calls_ms': zero_end - zero_start, 'discarded_render_ms': render_end - render_start,
                               'discarded_release_ms': free - render_end})
                if expected_setup is not None:
                    expected_mark = ':'.join(map(str, expected_setup))
                    result['completed_preparation_markers'] = setup_marks
                    checks['preparation_matches_requested_frames'] = (len(setup_marks) == 1
                        and setup_marks[0][0] == expected_mark and render_end <= setup_marks[0][1] <= free)
    return checks, result


def phase_timing(profile, report, limits, spec, with_phases, preparation=None, expected_setup=None):
    fit = cross.clocks.native_timing(profile, spec['engine_marker'], report, 32)
    if 'thread' not in fit:
        return {'native_intervals_aligned': False}, {'native': fit}
    thread, = [t for t in registration.native.threads(profile) if f"{t['name']}/{t['pid']}" == fit['thread']]
    outer, _ = registration.native.thread_intervals(thread, spec['engine_marker'])
    author, _ = registration.native.thread_intervals(thread, AUTHOR_MARKER)
    realtime = report['realtime']
    before = realtime['startupCallbacks'] + realtime['leadCallbacks']
    quantum = limits['expected_render_quantum_frames']
    stride = limits['observation_stride_frames']
    indices = spec['traced_quantum_indices']
    keys = marker_keys(quantum, stride)
    phases, calibration = trace_markers(thread)
    checks = {'native_intervals_aligned': True}
    result = {'native': fit, 'quanta': []}
    if preparation is not None:
        preparation_checks, result['preparation'] = preparation_timing(thread, preparation, author[0][0], expected_setup)
        checks.update(preparation_checks)
    if with_phases:
        checks['expected_trace_markers'] = (set(phases) == {n * quantum for n in indices}
                                             and all(list(marks) == keys for marks in phases.values()))
        previous_start, previous_end = author[before - 1]
        checks['calibration_in_last_lead_quantum'] = (len(calibration) == spec['calibration_markers']
            and sorted(calibration) == calibration and all(previous_start <= n <= previous_end for n in calibration))
        if len(calibration) > 1:
            steps = np.diff(calibration).tolist()
            result['calibration'] = {'marker_steps_ms': steps,
                'within_calibration_goal': max(steps) <= spec['maximum_marker_calibration_step_ms']}
    else:
        checks['no_render_phase_markers' if expected_setup else 'control_has_no_phase_markers'] = not (phases or calibration)
    for index in indices:
        frame = index * quantum
        a, b = author[before + index]
        c, d = outer[before + index]
        row = {'output_frame': frame, 'context_frame': report['firstContextFrame'] + frame,
               'outer_ms': d - c, 'author_ms': b - a}
        marks = phases.get(frame, {})
        if with_phases and list(marks) == keys:
            values = list(marks.values())
            inside = min(values) >= a and max(values) <= b and sorted(values) == values
            checks[f'phases_inside_author_call_{frame}'] = inside
            if inside:
                def elapsed(offset, phase):
                    return marks[offset, phase + '-end'] - marks[offset, phase + '-start']

                slices = [{'offset': offset, 'render_ms': elapsed(offset, 'render'), 'wasm_ms': elapsed(offset, 'wasm'),
                           'observation_ms': elapsed(offset + stride, 'observation')}
                          for offset in range(0, quantum, stride)]
                row.update({'slices': slices, 'wasm_ms': sum(part['wasm_ms'] for part in slices),
                            'render_ms': sum(part['render_ms'] for part in slices),
                            'observation_ms': sum(part['observation_ms'] for part in slices),
                            'marked_frame_ms': values[-1] - values[0], 'marker_offsets_from_native_start_ms': [
                                {'offset_frames': offset, 'phase': kind, 'offset_ms': time - a}
                                for (offset, kind), time in marks.items()]})
        result['quanta'].append(row)
    if with_phases and all('wasm_ms' in r for r in result['quanta']):
        first, second, *warm = result['quanta']
        fields = ('outer_ms', 'author_ms', 'wasm_ms', 'render_ms', 'observation_ms')
        differences = [{f: row[f] - median(w[f] for w in warm) for f in fields} for row in (first, second)]
        excess = differences[0]
        fraction = excess['wasm_ms'] / excess['outer_ms'] if excess['outer_ms'] > 0 else None
        result.update({'early_minus_mature_ms': differences, 'wasm_share_of_first_excess': fraction,
                       'prediction_met': fraction is not None and fraction >= spec['minimum_wasm_share_of_first_quantum_excess']})
    return checks, result


def summarize_warmup(trials, spec):
    groups = {}
    for condition in ('control', 'zero', 'draw'):
        usable = [t['timing'] for t in trials if t['condition'] == condition and 'timing' in t
                  and 'constructor_ms' in t['timing'].get('preparation', {})
                  and (condition == 'control' or 'preparation_ms' in t['timing']['preparation'])
                  and all('wasm_ms' in row for row in t['timing']['quanta'])]
        group = {'trials': len(usable)}
        if usable:
            group.update({'median_constructor_ms': median(r['preparation']['constructor_ms'] for r in usable),
                          'first_quantum_within_budget': sum(1 for r in usable
                                                            if r['quanta'][0]['outer_ms'] <= r['native']['budget_ms']),
                          'median_quanta': [{field: median(r['quanta'][index][field] for r in usable)
                                             for field in ('outer_ms', 'wasm_ms', 'observation_ms')}
                                            for index in range(len(usable[0]['quanta']))]})
        groups[condition] = group
    result = {'groups': groups}
    if all(g['trials'] == len(spec['condition_order']) for g in groups.values()):
        control, zero, draw = (groups[c] for c in ('control', 'zero', 'draw'))
        ratios = [draw['median_quanta'][0]['wasm_ms'] / group['median_quanta'][0]['wasm_ms'] for group in (control, zero)]
        result.update({'first_wasm_draw_to_control_ratio': ratios[0], 'first_wasm_draw_to_zero_ratio': ratios[1],
                       'predictions': {'draw_vs_control': ratios[0] <= spec['maximum_draw_to_control_first_wasm_ratio'],
                                       'draw_vs_zero': ratios[1] <= spec['maximum_draw_to_zero_first_wasm_ratio'],
                                       'draw_first_quantum_budget': draw['first_quantum_within_budget'] >=
                                            spec['minimum_draw_trials_within_first_quantum_budget']}})
    return result


def summarize_frame_sweep(trials, spec):
    frames = spec['preparation_frames']
    rounds = len(spec['condition_order'])
    required = spec['minimum_trials_with_first_two_within_budget']
    groups = {}
    for condition, length in frames.items():
        rows = [t['timing'] for t in trials if t['condition'] == condition and t.get('timing_checks_passed')]
        group = {'preparation_frames': length, 'trials': len(rows)}
        groups[condition] = group
        if rows:
            group.update({
                'first_two_within_budget': sum(1 for t in rows if all(
                    q['outer_ms'] <= t['native']['budget_ms'] for q in t['quanta'][:2])),
                'all_quanta_within_budget': sum(1 for t in rows if not t['native']['native_over_budget_output_frames']),
                'median_first_two_outer_ms': [median(t['quanta'][i]['outer_ms'] for t in rows) for i in (0, 1)],
                'median_constructor_ms': median(t['preparation']['constructor_ms'] for t in rows),
                'median_steady_p99_ms': median(t['native']['native_after_warmup']['p99_ms'] for t in rows),
            })
            if length:
                group['median_discarded_render_ms'] = median(t['preparation']['discarded_render_ms'] for t in rows)
    result = {'groups': groups}
    if all(g['trials'] == rounds for g in groups.values()):
        meets_budget = {c: g['first_two_within_budget'] >= required for c, g in groups.items()}
        paired = {t['trial']: t['timing']['preparation']['constructor_ms'] for t in trials}
        shorter = 'draw192' if 'draw192' in frames else 'draw128'
        differences = [paired[f'{i}-draw256'] - paired[f'{i}-{shorter}'] for i in range(1, rounds + 1)]
        saving = median(differences)
        comparison = f'constructor_saving_{frames[shorter]}_vs_256_ms'
        expected = spec.get('expected_budget_results', {'draw64': False, 'draw128': True, 'draw256': True})
        predictions = {f'{c}_{"meets" if passes else "below"}_budget_goal': meets_budget[c] == passes
                       for c, passes in expected.items()}
        predictions[f'{shorter}_shortens_constructor'] = saving >= spec[f'minimum_{comparison}']
        result.update({'minimum_preparation_frames_meeting_budget': min(
                           (frames[c] for c, passes in meets_budget.items() if passes), default=None),
                       f'paired_{comparison}': differences, f'median_{comparison}': saving, 'predictions': predictions})
    return result


def build_comparison(fixed, live, source, reference, artifacts, execute, bun):
    execute([*bun, 'run', 'build'], cwd=song.WEB, stdout=artifacts / 'browser-build.log')
    binary = artifacts / 'vocal_wasm.wasm'
    shutil.copyfile(song.WORKSPACE / song.wasm.WASM, binary)
    execute(['cargo', 'test', '--locked', '-p', 'chimera', *[a for n in song.song.SUITES for a in ('--test', n)]],
            cwd=song.UPSTREAM, stdout=artifacts / 'upstream-tests.log')
    return read_comparison(fixed, live, source, reference, binary)


def read_comparison(fixed, live, source, reference, binary):
    binary_hash = song.sha256(binary)
    stored = song.wasm.read_json(reference['summary.json'])
    if 'artifacts/browser.json' in reference:
        baseline = song.wasm.read_json(reference['artifacts/browser.json'])
        rate, pcm = wavfile.read(reference['artifacts/pcm-128.wav'])
        browser_rate, browser_pcm = wavfile.read(reference['artifacts/browser.wav'])
        upstream = np.fromfile(reference['artifacts/upstream-pcm.f32'], dtype='<f4')
        expected = cross.signature(baseline, pcm)
        dictionary = stored['dictionary_sha256']
        aligned = browser_rate == rate and expected == cross.signature(baseline, browser_pcm)
    else:
        baseline = json.loads(gzip.decompress(reference['artifacts/1-chromium/browser.json.gz'].read_bytes()))
        rate, pcm = wavfile.read(reference['artifacts/reference/pcm-128.wav'])
        upstream = np.frombuffer(gzip.decompress(reference['artifacts/reference/upstream-pcm.f32.gz'].read_bytes()), dtype='<f4')
        expected = cross.signature(baseline, pcm)
        dictionary = stored['trials'][0]['dictionary_sha256']
        aligned = expected == stored['trials'][0]['hashes']
    if rate != fixed['measurement']['output_rate_hz'] or not aligned:
        raise ValueError('保存済み歌唱の基準を照合できません')
    config = song.wasm.read_json(source)
    score = config['song_voice']['score']
    beats = np.r_[0, np.cumsum([n['beats'] for n in score['notes'][:-1]])]
    planned_beats = np.rint((score['start_seconds'] + beats * 60 / score['bpm']) * rate).astype(int).tolist()
    checks = {'same_wasm_as_reference': binary_hash == song.sha256(reference['artifacts/vocal_wasm.wasm'])}
    inputs = {'engine': 'firefox', 'baseline': baseline, 'limits': fixed['measurement'], 'live': live['measurement'],
              'expected': expected, 'dictionary': dictionary, 'binary_hash': binary_hash,
              'upstream': upstream, 'tolerance': config['measurement']['pcm_absolute_tolerance'],
              'planned_beats': planned_beats, 'rejection': '音符に割り当てる歌詞の音節がありません'}
    return checks, inputs


def measure(study, fixed, live, source, reference, profiler, artifacts, execute, bun, warmup=None, frame_sweep=None):
    spec = study['measurement']
    checks, comparison = build_comparison(fixed, live, source, reference, artifacts, execute, bun)
    expected = comparison['expected']
    trials = []
    pairs = []
    reg = registration.evaluation.registration
    measurement = frame_sweep or warmup or spec
    for number, order in enumerate(measurement['condition_order'], 1):
        pair = {}
        for condition in order:
            label = f'{number}-{condition}'
            folder = artifacts / label
            result = {'trial': label, 'condition': condition}
            local = {}
            try:
                trace = warmup is not None or condition == 'phases'
                options = {'trace_render_phases': trace, 'record_asset_evidence_timing': True}
                setup = None
                if condition in ('zero', 'draw'):
                    options['render_preparation'] = condition
                if frame_sweep is not None and frame_sweep['preparation_frames'][condition]:
                    draw_frames = frame_sweep['preparation_frames'][condition]
                    options['render_preparation'] = str(draw_frames)
                    setup = (draw_frames, frame_sweep['block_frames'], frame_sweep['zero_frame_calls'])
                run, report, got_rate, audio = cross.capture(folder, 'firefox', live, source, '...', execute, profiler,
                    options=options)
                local, result['upstream_pcm'] = reg.checks_for_capture(run, report, got_rate, audio, **comparison)
                result['browser'] = run['version']
                local['asset_body_read_deferred'] = run['assetEvidenceTiming']['deferred'] is True
                profile = song.wasm.read_json(folder / 'firefox-profile.json')
                timing_checks, result['timing'] = phase_timing(profile, report, fixed['measurement'], spec, trace,
                    condition if warmup is not None or frame_sweep is not None else None, setup)
                if frame_sweep is not None:
                    result['timing_checks_passed'] = all(timing_checks.values())
                local.update(timing_checks)
                if 'quanta' in result['timing']:
                    pair[condition] = result['timing']['quanta'][0]['outer_ms']
            except (OSError, EOFError, KeyError, TypeError, ValueError, subprocess.CalledProcessError) as error:
                local['capture_and_comparison_completed'] = False
                result['error'] = str(error)
            checks.update({f'{label}/{name}': value for name, value in local.items()})
            trials.append(result)
            cross.clocks.compress_outputs(folder)
        pairs.append(pair)
    if warmup is not None:
        return {'checks': checks, 'trials': trials, 'reference_hashes': expected, 'warmup': summarize_warmup(trials, warmup)}
    if frame_sweep is not None:
        return {'checks': checks, 'trials': trials, 'reference_hashes': expected,
                'frame_sweep': summarize_frame_sweep(trials, frame_sweep)}
    shifts = [pair['phases'] - pair['control'] for pair in pairs if len(pair) == 2]
    median_shift = median(shifts) if len(shifts) == len(pairs) else None
    return {'checks': checks, 'trials': trials, 'reference_hashes': expected, 'phase_minus_control_outer_first_ms': shifts,
            'median_outer_first_shift_ms': median_shift, 'within_observer_effect_goal': (
                abs(median_shift) <= spec['maximum_median_outer_first_quantum_shift_ms'] if median_shift is not None else None)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('--offline-reference-run', help='同じ歌唱ケースのオフライン基準実行ID')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--warmup', action='store_true', help='同じWASMインスタンスで0フレームと事前描画を比較する')
    mode.add_argument('--warmup-frames', action='store_true', help='量子内の印を外し、事前描画の長さを比較する')
    mode.add_argument('--warmup-intermediate', action='store_true', help='量子内の印を外し、192と256フレームを比較する')
    args = parser.parse_args()
    study, fixed, live = (song.wasm.read_json(path) for path in (CASE, song.CASE, song.LIVE_CASE))
    source = song.WORKSPACE / 'cases' / fixed['song_voice_case']
    revision = study['upstream_revision']
    if (any(case['upstream_revision'] != revision for case in (fixed, live))
            or subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=song.UPSTREAM, text=True).strip() != revision
            or subprocess.check_output(['git', 'status', '--porcelain'], cwd=song.UPSTREAM, text=True)):
        parser.error('固定上流または歌唱のケースが一致しません')
    if args.offline_reference_run:
        reference_run = song.run_manifest(args.offline_reference_run, song.CASE.stem, revision)
        reference_paths = OFFLINE_REFERENCE
    else:
        reference_run = song.run_manifest(study['reference_run'], cross.CASE.stem, revision)
        reference_paths = REFERENCE
    recent = song.run_manifest(study['timing_reference_run'], cross.CASE.stem, revision)
    recent_summary = song.verified_path(recent, 'summary.json')
    if reference_run[1]['status'] != 'pass' or any(
            not passed and not key.endswith('/live_block_timing_budget')
            for key, passed in song.wasm.read_json(recent_summary)['checks'].items()):
        parser.error('歌唱の基準実行または直近の音声判定が不合格です')
    reference = {name: song.verified_path(reference_run, name) for name in reference_paths}
    profile_path = song.WORKSPACE / 'cases' / study['measurement']['profiler_case']
    profiler = song.wasm.read_json(profile_path)['measurement']
    case_path = CASE
    warmup = None
    frame_sweep = None
    warmup_inputs = []
    orders = study['measurement']['condition_order']
    if args.warmup:
        case_path = WARMUP_CASE
        warmup_case = song.wasm.read_json(case_path)
        warmup = warmup_case['measurement']
        if (warmup_case['upstream_revision'] != revision or warmup_case['phase_case'] != CASE.name
                or len(warmup['condition_order']) != 3 or any(sorted(order) != ['control', 'draw', 'zero']
                    for order in warmup['condition_order'])
                or warmup['draw_block_frames'] != fixed['measurement']['observation_stride_frames']
                or warmup['draw_frames'] != 2 * fixed['measurement']['expected_render_quantum_frames']):
            parser.error('事前描画のケース、条件順またはフレーム分割が一致しません')
        phase_run = song.run_manifest(warmup_case['phase_reference_run'], study['id'], revision)
        if phase_run[1]['status'] != 'pass':
            parser.error('前回の区間計時が不合格です')
        warmup_inputs = [case_path, phase_run[0] / 'manifest.json', song.verified_path(phase_run, 'summary.json')]
    elif args.warmup_frames or args.warmup_intermediate:
        case_path = INTERMEDIATE_CASE if args.warmup_intermediate else FRAME_CASE
        frame_case = song.wasm.read_json(case_path)
        previous = song.wasm.read_json(WARMUP_CASE)['measurement']
        frame_sweep = frame_case['measurement']
        frames = frame_sweep['preparation_frames']
        orders = frame_sweep['condition_order']
        block = fixed['measurement']['observation_stride_frames']
        expected_frames = {'draw192': 3 * block, 'draw256': previous['draw_frames']} if args.warmup_intermediate else {
            'control': 0, 'draw64': block, 'draw128': fixed['measurement']['expected_render_quantum_frames'],
            'draw256': previous['draw_frames'],
        }
        positions = {condition: 4 // len(expected_frames) for condition in expected_frames}
        if (frame_case['upstream_revision'] != revision or frame_case['phase_case'] != CASE.name
                or frame_case['warmup_case'] != WARMUP_CASE.name
                or frame_sweep['block_frames'] != block
                or frame_sweep['block_frames'] != previous['draw_block_frames']
                or frame_sweep['zero_frame_calls'] != previous['zero_frame_calls']
                or frames != expected_frames or len(orders) != 4 or any(sorted(order) != sorted(frames) for order in orders)
                or any(Counter(column) != positions for column in zip(*orders))
                or len({pair for order in orders for pair in zip(order, order[1:])}) != len(frames) * (len(frames) - 1)):
            parser.error('事前描画長、条件順または参照ケースが一致しません')
        warmup_run = song.run_manifest(frame_case['warmup_reference_run'], WARMUP_CASE.stem, revision)
        if warmup_run[1]['status'] != 'pass':
            parser.error('前回の事前描画の比較が不合格です')
        warmup_inputs = [case_path, warmup_run[0] / 'manifest.json', song.verified_path(warmup_run, 'summary.json')]
        if args.warmup_intermediate:
            frame_run = song.run_manifest(frame_case['frame_reference_run'], FRAME_CASE.stem, revision)
            if frame_run[1]['status'] != 'pass':
                parser.error('64・128・256フレームの比較が不合格です')
            warmup_inputs.extend([FRAME_CASE, frame_run[0] / 'manifest.json', song.verified_path(frame_run, 'summary.json')])
    elif not orders or any(sorted(order) != ['control', 'phases'] for order in orders):
        parser.error('各組には無印と段階計時が一度ずつ必要です')
    bun = ['bun'] if shutil.which('bun') else ['npx', '--offline', '--yes', '--package=bun@1.4.4', '--', 'bun']
    inputs = [CASE, *warmup_inputs, song.CASE, song.LIVE_CASE, source, profile_path, Path(__file__).resolve(),
              reference_run[0] / 'manifest.json', recent[0] / 'manifest.json', recent_summary, *reference.values(),
              *song.web_sources(), *song.shared.candidate_sources(),
              *(Path(module.__file__) for module in (song, song.wasm, song.shared, cross, registration, registration.native,
                  cross.clocks, registration.evaluation, registration.evaluation.registration, registration.evaluation.registration.startup,
                  cross.clocks.release.stored))]
    metadata = {'case_id': case_path.stem, 'upstream_revision': revision, 'reference_run': reference_run[0].name,
                'timing_reference_run': recent[0].name, 'analysis_command': [sys.executable, *sys.argv],
                'analysis_directory': str(Path.cwd()),
                'node': subprocess.check_output(['node', '--version'], text=True).strip(),
                'bun': subprocess.check_output([*bun, '--version'], text=True).strip()}
    return song.shared.record_measurement(args.run_id, case_path, inputs, metadata,
        lambda artifacts, execute: measure(study, fixed, live, source, reference, profiler, artifacts, execute, bun,
                                           warmup, frame_sweep),
        command=None, input_root=song.ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
