"""Firefoxで先行音を処理中のContextへ歌唱ノードを追加する。"""

import argparse
import os
from pathlib import Path
import shutil
from statistics import median
import subprocess
import sys

import numpy as np

import measure_worklet_live_song_render_phases as phases
import measure_worklet_shared_context as shared


song = phases.song
cross = phases.cross
native = phases.registration.native
CASE = song.WORKSPACE / 'cases/worklet-live-song-shared-context.json'
AUDIOIPC_CASE = song.WORKSPACE / 'cases/worklet-live-song-audioipc.json'
AUDIOIPC_DIAGNOSTIC_CASE = song.WORKSPACE / 'cases/worklet-live-song-audioipc-diagnostic.json'
AUDIOIPC_SYSTEM_CASE = song.WORKSPACE / 'cases/worklet-live-song-audioipc-system-trace.json'
AUDIOIPC_DIRECT_CASE = song.WORKSPACE / 'cases/worklet-live-song-audioipc-system-direct.json'
AUDIOIPC_PAIR_CASE = song.WORKSPACE / 'cases/worklet-live-song-audioipc-system-pair.json'
AUDIOIPC_GATED_CASE = song.WORKSPACE / 'cases/worklet-live-song-audioipc-system-gated.json'
AUDIOIPC_CENTERED_CASE = song.WORKSPACE / 'cases/worklet-live-song-audioipc-system-centered.json'
AUDIOIPC_NOTIFIED_CASE = song.WORKSPACE / 'cases/worklet-live-song-audioipc-system-notified.json'
AUDIOIPC_SYSCALLS_CASE = song.WORKSPACE / 'cases/worklet-live-song-audioipc-system-calls.json'
AUDIOIPC_SERIES_CASE = song.WORKSPACE / 'cases/worklet-live-song-audioipc-system-calls-series.json'
AUDIOIPC_AUDIO_CLIENT_CASE = song.WORKSPACE / 'cases/worklet-live-song-audioipc-audio-client.json'
PROCESS_TAP_CASE = song.WORKSPACE / 'cases/worklet-live-song-process-tap.json'
PROCESS_TAP_CAPTURE = Path(__file__).with_name('measure_worklet_live_song_process_tap.py').resolve()
CUBEB_OUTPUT_CASE = song.WORKSPACE / 'cases/worklet-live-song-cubeb-output.json'
PAIRED_OUTPUT_CASE = song.WORKSPACE / 'cases/worklet-live-song-paired-output.json'
SPLIT_PREPARATION_CASE = song.WORKSPACE / 'cases/worklet-live-song-split-preparation.json'
DEFERRED_PREPARATION_CASE = song.WORKSPACE / 'cases/worklet-live-song-deferred-split-preparation.json'
FAST_RETURN_CASE = song.WORKSPACE / 'cases/worklet-live-song-fast-return-time.json'
SPLIT_OPTIONS = {'split192': 'split-192', 'deferred192': 'split-192-deferred'}
SYSTEM_PAIR_CAPTURE = Path(__file__).with_name('capture_worklet_system_pair.py').resolve()
MARKER_PROCESSOR = 'chimera-shared-context-marker'
SONG_PROCESSOR = 'chimera-fixed-voice'


def enclosing_intervals(inner, outer):
    if len(inner) == 0 or len(outer) == 0:
        return None
    if not (np.isfinite(inner).all() and np.isfinite(outer).all()
            and (inner[:, 1] >= inner[:, 0]).all() and (outer[:, 1] >= outer[:, 0]).all()
            and (outer[:-1, 1] <= outer[1:, 0]).all()):
        return None
    positions = np.searchsorted(outer[:, 1], inner[:, 1])
    if (len(set(positions)) != len(positions) or (positions >= len(outer)).any()
            or (outer[positions, 0] > inner[:, 0]).any()):
        return None
    return positions


def reference_callback_times(thread, marker_calls, marker_outer, frames):
    stamps = [(int(label), time) for label, time in phases.console_timestamps(thread, 'chimera-marker:')]
    captured = set(frames)
    selected = [(frame, time) for frame, time in stamps if frame in captured]
    if [frame for frame, _ in selected] != frames:
        return None
    times = np.asarray([time for _, time in selected])
    positions = np.searchsorted(marker_calls[:, 0], times, side='right') - 1
    if ((positions < 0).any() or (times > marker_calls[positions, 1]).any()
            or not (np.diff(positions) == 1).all()):
        return None
    return marker_outer[positions, 0]


def split_preparation_timing(thread, voice, report, quantum, spec, first_quantum):
    marks = list(phases.console_timestamps(thread, 'chimera-song-preparation-split:'))
    blocks = spec['frames'] // spec['block_frames']
    indices = [first_quantum + i * spec['quantum_spacing'] for i in range(blocks)]
    realtime = report['realtime']
    silent = realtime['startupCallbacks'] + realtime['leadCallbacks']
    windows = []
    for step, index in enumerate(indices):
        frame = realtime['startupFirstContextFrame'] + index * quantum
        rendered = (step + 1) * spec['block_frames']
        pair = marks[2 * step:2 * step + 2]
        if index >= silent or [name for name, _ in pair] != [f'{frame}:start', f'{frame}:end:{rendered}']:
            break
        start, end = (point for _, point in pair)
        if not voice[index, 0] <= start <= end <= voice[index, 1]:
            break
        windows.append({'context_frame': frame, 'frames_prepared': rendered, 'start_ms': start,
                        'end_ms': end, 'duration_ms': end - start})
    lead = report['firstContextFrame'] - realtime['startupFirstContextFrame']
    return len(marks) == 2 * blocks and len(windows) == blocks, {'windows': windows, 'markers': marks,
                                                               'frames_before_song': lead}


def shared_timing(profile, report, spec, phase_spec, frames, condition, split_case=None):
    checks = {}
    result = {}
    found = []
    count = report['realtime']['startupCallbacks'] + report['realtime']['leadCallbacks']
    expected = count + report['callbacks']
    for thread in native.threads(profile):
        marker, _ = native.thread_intervals(thread, phases.AUTHOR_MARKER, processor=MARKER_PROCESSOR)
        voice, _ = native.thread_intervals(thread, phases.AUTHOR_MARKER, processor=SONG_PROCESSOR)
        if len(marker) >= len(frames) and len(voice) == expected and thread['name'] == 'GraphRunner':
            found.append((thread, np.asarray(marker), np.asarray(voice)))
    checks['both_processors_on_one_graph_runner'] = len(found) == 1
    if not checks['both_processors_on_one_graph_runner']:
        return checks, result
    thread, marker, voice = found[0]
    result['thread'] = f"{thread['name']}/{thread['pid']}"
    outer, _ = native.thread_intervals(thread, phase_spec['engine_marker'])
    outer = np.asarray(outer)
    parents = enclosing_intervals(np.vstack((marker, voice)), outer)
    checks['native_intervals_aligned'] = parents is not None
    if parents is None:
        return checks, result
    marker_outer, voice_outer = outer[parents[:len(marker)]], outer[parents[len(marker):]]
    starts = reference_callback_times(thread, marker, marker_outer, frames)
    checks['reference_frames_match_native_calls'] = starts is not None
    checks['no_song_phase_markers'] = not any(phases.console_timestamps(thread, phases.PREFIX))
    setup = (spec['draw_frames'], spec['draw_block_frames'], spec['zero_frame_calls']) if condition == 'draw192' else None
    constructor_condition = 'control' if condition in SPLIT_OPTIONS else condition
    prep, result['preparation'] = phases.preparation_timing(thread, constructor_condition, float(voice[0, 0]), setup,
                                                          processor=SONG_PROCESSOR)
    checks.update(prep)
    q = spec['marker']['quantum']
    if condition in SPLIT_OPTIONS:
        first_quantum = split_case['deferred_comparison']['first_quantum_offset'] if condition == 'deferred192' else 0
        checks['split_preparation_in_silent_quanta'], result['split_preparation'] = split_preparation_timing(
            thread, voice, report, q, split_case['preparation'], first_quantum)
    budget = 1000 * q / report['sampleRate']
    active = voice_outer[count:]
    durations = active[:, 1] - active[:, 0]
    active_frames = report['firstContextFrame'] + np.arange(len(active)) * q
    result['song'] = {'first_two_outer_ms': durations[:2].tolist(), 'budget_ms': budget,
                      'over_budget_output_frames': (np.flatnonzero(durations > budget) * q).tolist(),
                      'steady_p99_ms': float(np.percentile(durations[32:], 99))}
    if starts is None or not prep['constructor_before_first_process']:
        return checks, result

    (begin, end), = native.thread_intervals(thread, phases.CONSTRUCTOR_MARKER, processor=SONG_PROCESSOR)[0]
    index = int(np.searchsorted(starts, begin, side='right')) - 1
    settings = spec['marker']
    radius, baseline_count = settings['constructor_window_radius_quanta'], settings['baseline_quanta']
    checks['constructor_bracketed_by_reference_callbacks'] = bool(index + 1 >= settings['ready_quanta']
        and index >= radius + baseline_count and index + radius + 1 < len(starts)
        and end <= starts[index + 1])
    if checks['constructor_bracketed_by_reference_callbacks']:
        gaps = np.diff(starts)
        baseline = gaps[index - radius - baseline_count:index - radius]
        result['reference'] = {'constructor_gap_ms': float(gaps[index]), 'constructor_between_frames': frames[index:index + 2],
                               'constructor_start_offset_ms': float(begin - starts[index]),
                               'constructor_end_to_next_ms': float(starts[index + 1] - end),
                               'nearby_gaps': [{'frame': frames[i], 'gap_ms': float(gaps[i])}
                                               for i in range(index - radius, index + radius + 1)],
                               'baseline_gaps': shared.release.realtime.timing_summary(baseline, budget)}

    inside = (active_frames >= frames[0] + q) & (active_frames <= frames[-1] - q)
    indices = (active_frames[inside] - frames[0]) // q
    checks['reference_and_song_context_frames_aligned'] = bool(
        inside[:34].all() and ((active_frames[inside] - frames[0]) % q == 0).all()
        and (starts[indices - 1] <= active[inside, 0]).all() and (active[inside, 0] <= starts[indices + 1]).all())
    return checks, result


def summarize(trials, spec):
    rounds = len(spec['condition_order'])
    data = {row['trial']: row['timing'] for row in trials if row.get('timing_checks_passed')}
    if len(data) != 2 * rounds:
        return {'aligned_trials': len(data)}
    pairs, groups = [], {}
    for i in range(1, rounds + 1):
        control, draw = (data[f'{i}-{c}'] for c in ('control', 'draw192'))
        pairs.append({'constructor_gap_increase_ms': draw['reference']['constructor_gap_ms'] - control['reference']['constructor_gap_ms'],
                      'constructor_increase_ms': draw['preparation']['constructor_ms'] - control['preparation']['constructor_ms']})
    for condition in ('control', 'draw192'):
        rows = [data[f'{i}-{condition}'] for i in range(1, rounds + 1)]
        voices = [row['song'] for row in rows]
        groups[condition] = {'first_two_within_budget': sum(1 for voice in voices
                                  if all(ms <= voice['budget_ms'] for ms in voice['first_two_outer_ms'])),
                             'all_quanta_within_budget': sum(1 for voice in voices if not voice['over_budget_output_frames']),
                             'median_constructor_gap_ms': median(row['reference']['constructor_gap_ms'] for row in rows),
                             'median_constructor_ms': median(row['preparation']['constructor_ms'] for row in rows),
                             'median_first_song_quantum_ms': median(voice['first_two_outer_ms'][0] for voice in voices)}
    increase = median(pair['constructor_gap_increase_ms'] for pair in pairs)
    return {'aligned_trials': len(data), 'paired_differences': pairs, 'groups': groups,
            'median_paired_constructor_gap_increase_ms': increase,
            'predictions': {'reference_gap_increase': increase >= spec['minimum_paired_constructor_gap_increase_ms'],
                            'draw_first_two_within_budget': groups['draw192']['first_two_within_budget'] >=
                                spec['minimum_draw_trials_first_two_within_budget']}}


def fast_return_times(trials, case, reference):
    from measure_firefox_cubeb_return_time import predict_return, score

    limits = reference['reference_return_margin_ms']
    period = 1000 * case['expected_request_frames'] / case['sample_rate_hz']
    rows = []
    for trial in trials:
        core = trial.get('coreaudio', {})
        if not core.get('valid'):
            continue
        stream = core['streams'][core['matched_streams'][0]]
        if len(stream['center_intervals']) != 1:
            continue
        center, = stream['center_intervals']
        slack = center['scheduled_host_minus_return_ms']
        rows.append({'trial': trial['trial'], 'condition': trial['condition'], **center,
                     'gap': center['sample_time_gap_frames'] > 0, 'period_prediction': center['callback_ms'] > period,
                     'return_prediction': predict_return(slack, limits['largest_with_gap'], limits['smallest_contiguous'])})
    return {'trials': rows, 'reference_return_margin_ms': limits,
            'comparison': {name: score(rows, name) for name in ('period_prediction', 'return_prediction')}}


def set_song_schedule(live, fixed):
    quantum = fixed['measurement']['expected_render_quantum_frames']
    song_frames = fixed['measurement']['output_frames']
    active_callbacks = (song_frames + quantum - 1) // quantum
    schedule = live['measurement']
    schedule.update(expected_active_callbacks=active_callbacks,
                    expected_last_quantum_padded_frames=active_callbacks * quantum - song_frames,
                    minimum_timing_blocks=min(schedule['minimum_timing_blocks'],
                                              active_callbacks - schedule['timing_exclude_first_blocks']))


def measure(study, fixed, live, source, reference, profiler, phase_spec, artifacts, execute, bun, *,
            log_modules=(), rust_log=None, system_trace=None, system_pair_capture=SYSTEM_PAIR_CAPTURE,
            process_tap=None, cubeb_capture=None, paired_case=None, paired_case_path=None, split_case=None,
            fast_case=None, return_reference=None):
    checks, comparison = phases.build_comparison(fixed, live, source, reference, artifacts, execute, bun)
    spec = study['measurement']
    reg = phases.registration.evaluation.registration
    trials = []
    deferred_case = split_case.get('deferred_comparison') if split_case else None
    if cubeb_capture:
        import inspect_firefox_cubeb_output as cubeb_output

        firefox_binary, cubeb_case, cubeb_frames = cubeb_capture
    for i, order in enumerate(spec['condition_order'], 1):
        for condition in order:
            label = f'{i}-{condition}'
            folder = artifacts / label
            trial = {'trial': label, 'condition': condition}
            local = {}
            try:
                options = {'shared_context_marker': spec['marker'], 'record_asset_evidence_timing': True}
                gated = system_trace and 'marker_ready_offset_ms' in system_trace
                if gated or process_tap:
                    options['trace_shared_context'] = True
                if condition == 'draw192':
                    options['render_preparation'] = str(spec['draw_frames'])
                if condition in SPLIT_OPTIONS:
                    options['render_preparation'] = SPLIT_OPTIONS[condition]
                capture_execute = execute
                if cubeb_capture or process_tap:
                    def capture_execute(command, **kwargs):
                        if cubeb_capture:
                            directory = folder / 'cubeb'
                            enabled = paired_case is not None or split_case is not None or i == cubeb_case['capture']['capture_round']
                            if enabled:
                                directory.mkdir()
                            trial['cubeb_capture'] = enabled
                            output = str(directory) if enabled else ''
                            command = ['env', f'CHIMERA_FIREFOX={firefox_binary}',
                                       f'CHIMERA_CUBEB_OUTPUT_DIR={output}',
                                       f"CHIMERA_CUBEB_OUTPUT_BLOCKS={cubeb_case['capture']['snapshot_blocks']}",
                                       *command]
                        if process_tap:
                            bridge_case = paired_case_path or PROCESS_TAP_CASE
                            command = [sys.executable, str(PROCESS_TAP_CAPTURE), '--browser-bridge', str(process_tap),
                                       str(folder), str(bridge_case), '--', *command]
                        execute(command, **kwargs)
                if log_modules:
                    def capture_execute(command, **kwargs):
                        env = ['/usr/bin/env', 'MOZ_LOG=' + ','.join(log_modules), f'MOZ_LOG_FILE={folder / "audioipc"}']
                        if rust_log:
                            env.extend([f'RUST_LOG={rust_log}', 'DEBUG=pw:browser', 'DEBUG_COLORS=0'])
                        traced = [*env, *command]
                        if system_trace and system_trace.get('all_processes'):
                            capture_kind = 'instrument' if 'instrument' in system_trace else 'template'
                            trace_args = [sys.executable, str(system_pair_capture), str(folder),
                                          f'--{capture_kind}', system_trace[capture_kind],
                                          '--time-limit', system_trace['time_limit']]
                            for name in system_trace.get('additional_instruments', ()):
                                trace_args.extend(['--instrument', name])
                            if gated:
                                trace_args.extend(['--marker-ready-offset-ms', str(system_trace['marker_ready_offset_ms'])])
                            if system_trace.get('use_darwin_notification'):
                                trace_args.append('--darwin-notification')
                            traced = [*trace_args, '--', *traced]
                        elif system_trace:
                            trace_args = ['/usr/bin/xcrun', 'xctrace', 'record', '--template', system_trace['template'],
                                          '--time-limit', system_trace['time_limit'], '--no-prompt', '--output',
                                          str(folder / 'audio-system.trace')]
                            if system_trace.get('direct_launch'):
                                program = command.index('node')
                                trace_args.extend(flag for entry in (*env[1:], *command[1:program])
                                                  for flag in ('--env', entry))
                                traced = [shutil.which('node'), *command[program+1:]]
                            traced = [*trace_args, '--launch', '--', *traced]
                        execute(traced, **kwargs)

                run, report, rate, audio = cross.capture(folder, 'firefox', live, source, '...', capture_execute, profiler,
                                                        options=options)
                local, trial['upstream_pcm'] = reg.checks_for_capture(run, report, rate, audio, **comparison)
                if fast_case:
                    lead = report['firstContextFrame'] - report['realtime']['startupFirstContextFrame']
                    trial['frames_before_song'] = lead
                    local['same_frames_before_song'] = lead == fast_case['expected_frames_before_song']
                trial['browser'] = run['version']
                local['asset_body_read_deferred'] = run['assetEvidenceTiming']['deferred'] is True
                signal_checks, trial['reference_signal'], frames = shared.marker_signal(
                    spec['marker'], folder, spec['marker']['quantum'], rate)
                local.update(signal_checks)
                profile = song.wasm.read_json(folder / 'firefox-profile.json')
                timing, trial['timing'] = shared_timing(profile, report, spec, phase_spec, frames, condition, split_case)
                local.update(timing)
                trial['timing_checks_passed'] = all(timing.values())
                if process_tap:
                    exists = (folder / 'tap.json').is_file() and (folder / 'tap.f32le').is_file()
                    local['process_tap_recorded'] = exists and (folder / 'tap.f32le').stat().st_size > 0
                if cubeb_capture and trial['cubeb_capture']:
                    last_request = deferred_case['comparison_last_request_offset'] if deferred_case else 0
                    trial['coreaudio'] = cubeb_output.inspect(folder, trial, spec['marker'], cubeb_case,
                                                              cubeb_frames, phase_spec['engine_marker'], last_request)
                    local['cubeb_output_window'] = trial['coreaudio']['valid']
                    if condition in SPLIT_OPTIONS:
                        local['split_blocks_in_separate_requests'] = trial['coreaudio'].get('split_requests_valid', False)
                if paired_case:
                    gate = song.wasm.read_json(folder / 'trace-release.json')
                    trial['paired_output'] = (cubeb_output.inspect_pair(folder, trial['coreaudio'], spec['marker'], paired_case)
                                              if gate.get('tap_ready') is True else
                                              {'valid': False, 'reason': 'tap_not_ready_before_release'})
                    local['paired_output_window'] = trial['paired_output']['valid']
            except (OSError, EOFError, KeyError, TypeError, ValueError, subprocess.CalledProcessError) as error:
                local['capture_and_comparison_completed'] = False
                trial['error'] = str(error)
            checks.update({f'{label}/{k}': v for k, v in local.items()})
            trials.append(trial)
            cross.clocks.compress_outputs(folder)
            if log_modules:
                for log in sorted(folder.glob('audioipc*.moz_log')):
                    shared.release.stored.compress(log)
    result = {'checks': checks, 'trials': trials, 'reference_hashes': comparison['expected']}
    if deferred_case:
        result['deferred_split_preparation'] = cubeb_output.summarize_deferred(trials, cubeb_case, deferred_case)
    elif split_case:
        result['split_preparation'] = cubeb_output.summarize_split(trials, cubeb_case)
    else:
        result['shared_context'] = summarize(trials, spec)
    if fast_case:
        result['fast_return_time'] = fast_return_times(trials, cubeb_case, return_reference)
        checks['all_fast_center_requests_aligned'] = len(result['fast_return_time']['trials']) == len(trials)
    if log_modules:
        result['audioipc_acquisition'] = {'endpoint_timing_evaluated': False}
    if cubeb_capture and not (paired_case or split_case):
        overhead = cubeb_output.compare_overhead(trials, cubeb_case)
        result['cubeb_capture_overhead'] = overhead
        checks.update({f'{condition}/cubeb_constructor_overhead': overhead.get(condition, {}).get('within_limit', False)
                       for condition in ('control', 'draw192')})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--audioipc-log', choices=('pilot', 'diagnostic', 'system', 'direct', 'system-pair', 'system-gated',
                                                 'system-centered', 'system-notified', 'system-calls',
                                                 'system-calls-series', 'audio-client'),
                        help='AudioIPCの端点を採取する。system-calls-seriesでは4組を実行する')
    mode.add_argument('--process-tap', type=Path, metavar='APP', help='Firefoxの出力PCMをプロセスタップで採取する')
    mode.add_argument('--pcm-marker', action='store_true', help='逆相の先行音をブラウザ内部で確認する')
    mode.add_argument('--cubeb-output', type=Path, metavar='FIREFOX', help='試験用Firefoxのcubeb出力PCMを採取する')
    extra = parser.add_mutually_exclusive_group()
    extra.add_argument('--paired-process-tap', nargs=2, metavar=('APP', 'PROBE_RUN'),
                        help='cubeb出力と、既知PCMの校正を通したアプリでのタップを同時に採る')
    extra.add_argument('--split-preparation', action='store_true', help='構築中と無音量子内の事前描画を比較する')
    extra.add_argument('--deferred-split-preparation', action='store_true', help='分割事前描画を始める量子を比較する')
    parser.add_argument('--paired-case', type=Path, help='同時採取の登録済みケースを指定する')
    parser.add_argument('--fast-song-reference', metavar='OFFLINE_RUN', help='短い音符のオフライン歌唱の基準実行を使う')
    args = parser.parse_args()
    if args.paired_process_tap and not args.cubeb_output:
        parser.error('--paired-process-tap には --cubeb-output が必要です')
    if args.paired_case and not args.paired_process_tap:
        parser.error('--paired-case には --paired-process-tap が必要です')
    if (args.split_preparation or args.deferred_split_preparation) and not args.cubeb_output:
        parser.error('分割事前描画の比較には --cubeb-output が必要です')
    if args.fast_song_reference and not args.deferred_split_preparation:
        parser.error('短い歌唱の比較には --deferred-split-preparation が必要です')
    read = song.wasm.read_json
    study, phase, fixed, live = (read(path) for path in (CASE, phases.CASE, song.CASE, song.LIVE_CASE))
    revision = study['upstream_revision']
    if (any(c['upstream_revision'] != revision for c in (phase, fixed, live))
            or subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=song.UPSTREAM, text=True).strip() != revision
            or subprocess.check_output(['git', 'status', '--porcelain'], cwd=song.UPSTREAM, text=True)):
        parser.error('固定上流または歌唱のケースが一致しません')
    spec = study['measurement']
    prepared_path = song.WORKSPACE / 'cases' / study['preparation_case']
    prepared = read(prepared_path)['measurement']
    if (study['phase_case'] != phases.CASE.name or prepared_path != phases.INTERMEDIATE_CASE
            or spec['draw_frames'] != prepared['preparation_frames']['draw192']
            or spec['draw_block_frames'] != prepared['block_frames'] or spec['zero_frame_calls'] != prepared['zero_frame_calls']
            or spec['marker']['quantum'] != fixed['measurement']['expected_render_quantum_frames']
            or len(spec['condition_order']) != 4 or any(sorted(order) != ['control', 'draw192'] for order in spec['condition_order'])):
        parser.error('先行音または事前描画のケースが一致しません')
    case_path = CASE
    log_modules = ()
    rust_log = None
    system_trace = None
    process_tap = None
    cubeb_capture = None
    paired_case = None
    paired_case_path = None
    split_case = None
    if args.cubeb_output:
        import inspect_firefox_cubeb_output as cubeb_output

        case_path = CUBEB_OUTPUT_CASE
        cubeb_case = read(case_path)
        frame_case_path = case_path.parent / cubeb_case['frame_validation_case']
        frame_case = read(frame_case_path)
        probe_case_path = case_path.parent / cubeb_case['probe_case']
        probe_case = read(probe_case_path)
        setup = cubeb_case['capture']
        if (cubeb_case['shared_context_case'] != CASE.name or
                any(item['upstream_revision'] != revision for item in (cubeb_case, frame_case, probe_case)) or
                setup['ready_quanta'] != spec['marker']['ready_quanta'] or
                setup['condition_order'] != spec['condition_order'][:2] or setup['capture_round'] != 2 or
                not 1 <= setup['snapshot_blocks'] <= 256 or
                cubeb_case['gecko_revision'] != probe_case['firefox_revision'] or
                cubeb_case['cubeb_revision'] != probe_case['cubeb_coreaudio_revision'] or
                cubeb_case['window_radius_requests'] != frame_case['measurement']['window_radius_callbacks'] or
                cubeb_case['sample_rate_hz'] != frame_case['measurement']['output_rate_hz'] or
                cubeb_case['expected_request_frames'] != probe_case['requested_frames']):
            parser.error('cubeb、共有Contextまたは出力要求のケースが一致しません')
        spec['condition_order'] = setup['condition_order']
        spec['marker']['stereo_difference'] = True
        firefox_binary = args.cubeb_output.resolve(strict=True)
        xul = firefox_binary.with_name('XUL')
        if not firefox_binary.is_file() or not xul.is_file():
            parser.error('Firefox.appのContents/MacOS/firefoxを指定してください')
        cubeb_capture = firefox_binary, cubeb_case, frame_case['measurement']
    if args.split_preparation or args.deferred_split_preparation:
        case_path = SPLIT_PREPARATION_CASE
        split_case = read(case_path)
        preparation = split_case['preparation']
        order = split_case['condition_order']
        if (split_case['upstream_revision'] != revision or split_case['cubeb_case'] != CUBEB_OUTPUT_CASE.name or
                preparation != {'frames': spec['draw_frames'], 'block_frames': spec['draw_block_frames'],
                                'zero_frame_calls': spec['zero_frame_calls'], 'quantum_spacing': 2} or
                len(order) != 2 or any(sorted(row) != ['control', 'draw192', 'split192'] for row in order)):
            parser.error('分割事前描画と共有Contextのケースが一致しません')
        spec['condition_order'] = order
    if args.deferred_split_preparation:
        case_path = DEFERRED_PREPARATION_CASE
        deferred = read(case_path)
        order = deferred['condition_order']
        if (deferred['upstream_revision'] != revision or deferred['split_case'] != SPLIT_PREPARATION_CASE.name or
                deferred['first_quantum_offset'] != preparation['quantum_spacing'] or
                deferred['comparison_last_request_offset'] != preparation['frames'] // preparation['block_frames'] or
                not 0 < deferred['comparison_last_request_offset'] < cubeb_case['window_radius_requests'] or
                len(order) != 2 or any(sorted(row) != sorted(SPLIT_OPTIONS) for row in order)):
            parser.error('第1片を遅らせる分割事前描画のケースが一致しません')
        split_case['deferred_comparison'] = deferred
        spec['condition_order'] = order
    if args.paired_process_tap:
        app_path, probe_run = args.paired_process_tap
        case_path = paired_case_path = args.paired_case.resolve(strict=True) if args.paired_case else PAIRED_OUTPUT_CASE
        paired_case = read(PAIRED_OUTPUT_CASE)
        calibration_inputs = []
        smooth_case = None
        if case_path != PAIRED_OUTPUT_CASE:
            registered = read(case_path)
            if registered.get('base_case') != PAIRED_OUTPUT_CASE.name:
                parser.error('指定された同時採取の基準ケースに対応していません')
            paired_case.update(registered)
            smooth_path = CASE.parent / paired_case['smooth_calibration_case']
            smooth_case = read(smooth_path)
            smooth_base = CASE.parent / smooth_case['base_case']
            smooth_case = read(smooth_base) | smooth_case
            if (smooth_case['upstream_revision'] != revision or smooth_case['sample_rate_hz'] != paired_case['sample_rate_hz']
                    or smooth_case['marker']['shape'] != 'smooth-binary'):
                parser.error('滑らかな試験音の較正条件が同時採取ケースと一致しません')
            calibration_inputs.extend([PAIRED_OUTPUT_CASE, smooth_path, smooth_base,
                                       Path(cubeb_output.smooth_tap_marker.__file__)])
        setup = paired_case['capture']
        tap_probe_path = cubeb_output.tap.CASE
        tap_probe_case = read(tap_probe_path)
        if (paired_case['upstream_revision'] != revision or paired_case['cubeb_case'] != CUBEB_OUTPUT_CASE.name or
                paired_case['tap_probe_case'] != tap_probe_path.name or tap_probe_case['upstream_revision'] != revision or
                paired_case['sample_rate_hz'] != cubeb_case['sample_rate_hz'] or
                paired_case['sample_rate_hz'] != tap_probe_case['sample_rate_hz'] or
                setup['condition_order'] != spec['condition_order'][:1] or setup['ready_quanta'] != spec['marker']['ready_quanta'] or
                not 0 < setup['tap_attach_quanta'] < setup['ready_quanta'] < setup['marker_capture_quanta']):
            parser.error('同時採取の条件がcubebまたは先行音のケースと一致しません')
        try:
            process_tap = Path(app_path).resolve(strict=True)
            calibration = song.run_manifest(probe_run, (smooth_case or tap_probe_case)['id'], revision)
            calibration_summary = song.verified_path(calibration, 'summary.json')
            tap_hash = song.sha256(process_tap / 'Contents/MacOS/chimera-process-tap')
            summary = read(calibration_summary)
            calibration_checks = (summary['tape'] if smooth_case else summary)['checks']
        except (OSError, KeyError, TypeError, ValueError) as error:
            parser.error(f'プロセスタップの校正を照合できません ({error})')
        required = ('sample_rate', 'buffers_complete', 'block_times_recorded', 'block_times_contiguous',
                    'pcm_finite_and_nonzero', 'known_marker_continuous')
        if (calibration[1]['status'] != 'pass' or
                calibration[1].get('tap_binary_sha256') != tap_hash or
                not all(calibration_checks.get(key) for key in required)):
            parser.error('同じアプリで既知PCMの校正に合格した実行を指定してください')
        if smooth_case:
            calibrated_case = read(song.verified_path(calibration, 'artifacts/effective-case.json'))
            if (calibrated_case != smooth_case or calibration[1].get('tap_info_sha256')
                    != song.sha256(process_tap / 'Contents/Info.plist')):
                parser.error('採取器の設定または校正実行の試験条件が一致しません')
            calibration_inputs.append(song.verified_path(calibration, 'artifacts/effective-case.json'))
            alignment = {'smooth_alignment': smooth_case, 'quiet_marker_amplitude': paired_case['quiet_marker_amplitude']}
            paired_case.update(alignment)
            cubeb_case.update(alignment)
            spec['marker'].update(smooth_marker=smooth_case['marker'], maximum_graph_zero_error=smooth_case['maximum_graph_zero_error'])
        try:
            calibration_files = [song.verified_path(calibration, f'artifacts/{file}') for file in ('tap.json', 'tap.f32le')]
        except (OSError, KeyError, ValueError) as error:
            parser.error(f'プロセスタップの校正データを確認できません ({error})')
        spec['condition_order'] = setup['condition_order']
        spec['marker'].update(trace_attach_quanta=setup['tap_attach_quanta'],
                              capture_quanta=setup['marker_capture_quanta'], defer_close_until_marker=True)
    if args.process_tap or args.pcm_marker:
        case_path = PROCESS_TAP_CASE
        pcm_case = read(case_path)
        setup = pcm_case['capture']
        if (pcm_case['shared_context_case'] != CASE.name or pcm_case['upstream_revision'] != revision
                or setup['condition_order'] != spec['condition_order'][:1]
                or setup['ready_quanta'] != spec['marker']['ready_quanta']):
            parser.error('プロセスタップと共有Contextのケースが一致しません')
        spec['condition_order'] = setup['condition_order']
        spec['marker']['stereo_difference'] = True
        if args.process_tap:
            process_tap = args.process_tap.resolve(strict=True)
            spec['marker']['capture_quanta'] = setup['marker_capture_quanta']
            spec['marker']['defer_close_until_marker'] = True
    if args.audioipc_log:
        case_path = {'diagnostic': AUDIOIPC_DIAGNOSTIC_CASE, 'system': AUDIOIPC_SYSTEM_CASE,
                     'direct': AUDIOIPC_DIRECT_CASE, 'system-pair': AUDIOIPC_PAIR_CASE,
                     'system-gated': AUDIOIPC_GATED_CASE,
                     'system-centered': AUDIOIPC_CENTERED_CASE,
                     'system-notified': AUDIOIPC_NOTIFIED_CASE,
                     'system-calls': AUDIOIPC_SYSCALLS_CASE,
                     'system-calls-series': AUDIOIPC_SERIES_CASE,
                     'audio-client': AUDIOIPC_AUDIO_CLIENT_CASE}.get(args.audioipc_log, AUDIOIPC_CASE)
        ipc = read(case_path)
        if ipc['shared_context_case'] != CASE.name or ipc['upstream_revision'] != revision:
            parser.error('AudioIPCと共有Contextのケースが一致しません')
        capture_settings = ipc.get('capture')
        if case_path == AUDIOIPC_SERIES_CASE:
            pilot = read(AUDIOIPC_SYSCALLS_CASE)
            if (ipc['capture_source_case'] != AUDIOIPC_SYSCALLS_CASE.name
                    or ipc['condition_order'] != spec['condition_order']
                    or pilot['shared_context_case'] != CASE.name or pilot['upstream_revision'] != revision):
                parser.error('AudioIPCの採取設定または4組の実行順が一致しません')
            capture_settings = pilot['capture']
        else:
            spec['condition_order'] = spec['condition_order'][:capture_settings['pilot_rounds']]
        log_modules = capture_settings['log_modules']
        rust_log = capture_settings.get('rust_log')
        system_trace = capture_settings.get('system_trace')
        if system_trace and 'marker_capture_quanta' in system_trace:
            spec['marker']['capture_quanta'] = system_trace['marker_capture_quanta']
    fast_case = return_reference = None
    baseline_case = song.CASE
    reference_names = phases.REFERENCE
    fast_inputs = []
    if args.fast_song_reference:
        import measure_firefox_cubeb_return_time as return_time

        case_path = FAST_RETURN_CASE
        fast_case = read(case_path)
        baseline_case = case_path.parent / fast_case['offline_case']
        fixed = read(baseline_case)
        order = fast_case['condition_order']
        if (any(c['upstream_revision'] != revision for c in (fast_case, fixed)) or
                fast_case['deferred_case'] != DEFERRED_PREPARATION_CASE.name or
                fixed['measurement']['expected_render_quantum_frames'] != spec['marker']['quantum'] or
                len(order) != 2 or any(sorted(row) != ['deferred192', 'draw192', 'split192'] for row in order)):
            parser.error('短い歌唱または分割事前描画のケースが一致しません')
        spec['condition_order'] = order
        split_case['deferred_comparison']['condition_order'] = order
        set_song_schedule(live, fixed)
        baseline = song.run_manifest(args.fast_song_reference, fixed['id'], revision)
        return_run = song.run_manifest(fast_case['return_reference_run'], return_time.CASE.stem, revision)
        return_path = song.verified_path(return_run, 'summary.json')
        if return_run[1]['status'] != 'pass' or return_run[1]['firefox_xul_sha256'] != song.sha256(xul):
            parser.error('返却時刻の基準実行または試験用Firefoxが一致しません')
        return_reference = read(return_path)
        reference_names = phases.OFFLINE_REFERENCE
        fast_inputs = [DEFERRED_PREPARATION_CASE, return_path, return_run[0] / 'manifest.json',
                       return_time.CASE, Path(return_time.__file__).resolve()]
    elif paired_case and 'song_reference_run' in paired_case:
        baseline = song.run_manifest(paired_case['song_reference_run'], fixed['id'], revision)
        reference_names = phases.OFFLINE_REFERENCE
        matches = [row['sha256'] for row in baseline[1]['inputs'] if row['path'].endswith('/' + fixed['song_voice_case'])]
        if matches != [song.sha256(CASE.parent / fixed['song_voice_case'])]:
            parser.error('同時採取とオフライン基準の歌唱入力が一致しません')
    else:
        baseline = song.run_manifest(phase['reference_run'], cross.CASE.stem, revision)
    prepared_run = song.run_manifest(study['preparation_reference_run'], prepared_path.stem, revision)
    shared_run = song.run_manifest(study['prior_shared_context_run'], shared.CASE.stem, revision)
    if any(manifest['status'] != 'pass' for _, manifest in (baseline, prepared_run, shared_run)):
        parser.error('先行音または歌唱の基準実行が不合格です')
    reference = {name: song.verified_path(baseline, name) for name in reference_names}
    profile_path = song.WORKSPACE / 'cases' / phase['measurement']['profiler_case']
    profiler = read(profile_path)['measurement']
    source = song.WORKSPACE / 'cases' / fixed['song_voice_case']
    bun = ['bun'] if shutil.which('bun') else ['npx', '--offline', '--yes', '--package=bun@1.4.4', '--', 'bun']
    related = (phases, shared, song, song.wasm, song.shared, cross, phases.registration, native,
               cross.clocks, phases.registration.evaluation, phases.registration.evaluation.registration,
               phases.registration.evaluation.registration.startup, cross.clocks.release.stored)
    inputs = [CASE, case_path, phases.CASE, song.CASE, baseline_case, song.LIVE_CASE, prepared_path, shared.CASE, source, profile_path,
              Path(__file__).resolve(), *reference.values(), *(Path(m.__file__) for m in related),
              *song.web_sources(), *song.shared.candidate_sources(), *fast_inputs,
              *(run[0] / 'manifest.json' for run in (baseline, prepared_run, shared_run)),
              *(song.verified_path(run, 'summary.json') for run in (prepared_run, shared_run))]
    system_pair_capture = SYSTEM_PAIR_CAPTURE
    if system_trace and system_trace.get('all_processes'):
        inputs.append(SYSTEM_PAIR_CAPTURE)
        system_pair_capture = (song.WORKSPACE / 'runs' / args.run_id / 'artifacts/source'
                               / SYSTEM_PAIR_CAPTURE.relative_to(song.ROOT))
    if log_modules and case_path != AUDIOIPC_CASE:
        inputs.append(AUDIOIPC_CASE)
    if log_modules and 'previous_gated_case' in ipc:
        inputs.extend([song.WORKSPACE / 'cases' / ipc['previous_gated_case'],
                       song.WORKSPACE / 'runs' / ipc['previous_gated_run'] / 'manifest.json'])
    if process_tap:
        inputs.extend([PROCESS_TAP_CAPTURE, PROCESS_TAP_CAPTURE.with_name('chimera_process_tap.swift'),
                       PROCESS_TAP_CAPTURE.with_name('chimera_process_tap_info.plist')])
    metadata = {'case_id': case_path.stem, 'upstream_revision': revision,
                'reference_run': baseline[0].name, 'preparation_reference_run': prepared_run[0].name,
                'analysis_command': [sys.executable, *sys.argv], 'analysis_directory': str(Path.cwd()),
                'node': subprocess.check_output(['node', '--version'], text=True).strip(),
                'bun': subprocess.check_output([*bun, '--version'], text=True).strip()}
    if log_modules:
        metadata['audioipc_log_mode'] = args.audioipc_log
        metadata['playwright_browsers_path'] = os.environ.get('PLAYWRIGHT_BROWSERS_PATH')
    if process_tap:
        metadata['tap_binary_sha256'] = song.sha256(process_tap / 'Contents/MacOS/chimera-process-tap')
    if args.pcm_marker:
        metadata['pcm_marker_only'] = True
    if cubeb_capture:
        inputs.extend([frame_case_path, probe_case_path, PROCESS_TAP_CAPTURE,
                       Path(cubeb_output.__file__).resolve(), Path(cubeb_output.tap.callback.__file__).resolve(),
                       Path(cubeb_output.cubeb.__file__).resolve(),
                       Path(__file__).with_name('chimera-cubeb-output-snapshot.patch').resolve()])
        metadata['firefox_binary'] = str(firefox_binary)
        metadata['firefox_binary_sha256'] = song.sha256(firefox_binary)
        metadata['firefox_xul_sha256'] = song.sha256(xul)
    if paired_case:
        inputs.extend([CUBEB_OUTPUT_CASE, tap_probe_path, calibration[0] / 'manifest.json', calibration_summary,
                       *calibration_files, *calibration_inputs])
        metadata['tap_calibration_run'] = probe_run
    if split_case:
        inputs.extend([CUBEB_OUTPUT_CASE, SPLIT_PREPARATION_CASE])
    return song.shared.record_measurement(args.run_id, case_path, inputs, metadata,
        lambda artifacts, execute: measure(study, fixed, live, source, reference, profiler, phase['measurement'],
                                           artifacts, execute, bun, log_modules=log_modules, rust_log=rust_log,
                                           system_trace=system_trace, system_pair_capture=system_pair_capture,
                                           process_tap=process_tap, cubeb_capture=cubeb_capture, paired_case=paired_case,
                                           paired_case_path=paired_case_path,
                                           split_case=split_case, fast_case=fast_case, return_reference=return_reference),
        command=None, input_root=song.ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
