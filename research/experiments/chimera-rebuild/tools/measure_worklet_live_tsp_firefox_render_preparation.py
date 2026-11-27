"""Firefoxの確認用07で発声前の準備と先頭量子を比較する。"""

import argparse
from bisect import bisect_left
import os
from pathlib import Path
import shutil
from statistics import median
import subprocess

import numpy as np
from scipy.io import wavfile

import measure_lip_crossing_thickness as stored
from measure_csd_envelope_timing import verified_file
from measure_speech_timing import read
from measure_tsp_listening import hydrate_run, snapshot_case
from measure_uniform_tube import candidate_sources, record_measurement
from measure_wasm_fixed import WASM, compare_pcm
from measure_worklet_firefox_native_clock import thread_intervals, threads
from measure_worklet_fixed import ROOT, WEB, web_sources
from measure_worklet_live_song_render_phases import CONSTRUCTOR_MARKER, console_timestamps, preparation_timing
from measure_worklet_live_tsp_firefox_native_clock import measure_trial, native_rows
from measure_worklet_live_tsp_firefox_render_phases import measure_phases
from measure_worklet_tsp_device_preparation import (
    capture_cubeb, compare_device, device_hypothesis, device_inputs, measure_onset_requests, summarize_onset_requests,
)
from measure_worklet_tsp_device_io import TOOL as DEVICE_IO_TOOL, capture_io, inspect_io
from measure_worklet_tsp_device_tap import (
    capture_tap, controls as tap_controls, inspect_tap, onset_anchor_checks,
    summarize_draw_tap, summarize_tap_control, summarize_tap_onset, tap_inputs,
)
from upstream_baseline import UPSTREAM, WORKSPACE, sha256

CASE = WORKSPACE / 'cases/worklet-live-tsp-firefox-render-preparation.json'
SPLIT_CASE = WORKSPACE / 'cases/worklet-live-tsp-firefox-split-preparation.json'
DEVICE_CASE = WORKSPACE / 'cases/worklet-live-tsp-firefox-device-preparation.json'
VARIABLE_DEVICE_CASE = WORKSPACE / 'cases/worklet-live-tsp-firefox-device-preparation-v2.json'
DEVICE_ONSET_CASE = WORKSPACE / 'cases/worklet-live-tsp-firefox-device-onset.json'
DEVICE_IO_CASE = WORKSPACE / 'cases/worklet-live-tsp-firefox-device-io.json'
DEVICE_TAP_CASE = WORKSPACE / 'cases/worklet-live-tsp-firefox-device-tap.json'
DEVICE_TAP_ONSET_CASE = WORKSPACE / 'cases/worklet-live-tsp-firefox-device-tap-onset.json'
DEVICE_TAP_DRAW_CASE = WORKSPACE / 'cases/worklet-live-tsp-firefox-device-tap-draw.json'


def split_timing(thread, live, calls, waits, spec):
    marks = list(console_timestamps(thread, 'chimera-speech-preparation-split:'))
    if spec is None:
        return {'no_split_markers': not marks}, {'markers': marks}
    block_frames = spec['draw_block_frames']
    final_frames = spec.get('final_block_frames', block_frames)
    total = (spec['draw_frames'] - final_frames) // block_frames + 1
    quantum = live['blocks'][0][1]
    windows = []
    offsets = spec.get('quantum_offsets', range(0, total * spec['quantum_spacing'], spec['quantum_spacing']))
    for step, offset in enumerate(offsets):
        index = live['startupCallbacks'] + offset
        frame = live['armedContextFrame'] + offset * quantum
        rendered = step * block_frames + (final_frames if step == total - 1 else block_frames)
        pair = marks[2 * step:2 * step + 2]
        if (index >= len(waits) or frame >= live['scheduledContextFrame']
                or [name for name, _ in pair] != [f'{frame}:start', f'{frame}:end:{rendered}']):
            break
        start, end = (t for _, t in pair)
        if not calls[index][0] <= start <= end <= calls[index][1]:
            break
        windows.append({'context_frame': frame, 'call_index': index, 'frames_prepared': rendered,
                        'start_ms': start, 'end_ms': end, 'preparation_ms': end - start, 'outer_ms': waits[index]})
    return {'split_matches_lead_quanta': len(marks) == 2 * total and len(windows) == total}, {
        'markers': marks, 'windows': windows}


def time_preparation(profile, report, clock, setup, condition, budget, split=None):
    evidence, pair = native_rows(profile, report, clock)
    if pair is None:
        return {'preparation_native_intervals': False}, {}
    selected = evidence['selected_thread']
    thread, = [t for t in threads(profile) if (t['pid'], t['tid']) == (selected['pid'], selected['tid'])]
    spans, _ = thread_intervals(thread, clock['engine_marker'])
    processor = clock.get('processor')
    calls, _ = thread_intervals(thread, clock['author_marker'], processor=processor)
    constructors, _ = thread_intervals(thread, CONSTRUCTOR_MARKER, processor=processor)
    constructor_condition = 'control' if condition == 'split' else condition
    checks, result = preparation_timing(thread, constructor_condition, calls[0][0], setup, processor=processor, kind='speech')
    if not checks['constructor_before_first_process']:
        result['constructors'] = constructors
        return checks, result

    outer, _ = pair
    build_start, build_end = constructors[0]
    result.update({'constructor_to_first_capture_end_ms': float(outer[0][1] - build_start),
                   'constructor_end_to_first_capture_ms': float(outer[0][0] - build_end),
                   'constructor_start_ms': build_start, 'first_capture_start_ms': float(outer[0][0])})
    ends = [end for _, end in spans]
    first_to_arm = report['realtime']['startupCallbacks']
    waits = []
    for start, end in calls[:evidence['startup_and_lead_quanta']]:
        left, right = spans[bisect_left(ends, end)]
        if not left <= start <= end <= right:
            raise ValueError('待機中のCallProcessが対応するProcessBlockに含まれていません')
        waits.append(right - left)
    result['waiting'] = {name: {'count': len(values), 'maximum_ms': max(values, default=None),
                                'over_budget': sum(t > budget for t in values), 'durations_ms': values}
                         for name, values in (('startup', waits[:first_to_arm]), ('lead', waits[first_to_arm:]))}
    if split is not None:
        split_checks, trace = split_timing(thread, report['realtime'], calls, waits, split if condition == 'split' else None)
        checks.update(split_checks)
        result['split'] = trace
    return checks, result


def summarize(trials, spec):
    fields = ('first_wasm_ms', 'first_outer_ms', 'second_outer_ms', 'constructor_ms',
              'constructor_to_first_capture_end_ms', 'warm_p99_outer_ms')
    split = 'quantum_spacing' in spec
    if split:
        fields += ('maximum_wait_outer_ms',)
    groups = {name: [r['cost'] for r in trials if r['condition'] == name and 'cost' in r]
              for name in dict.fromkeys(name for order in spec['condition_order'] for name in order)}
    stats = {name: {'samples': len(rows), 'within_budget_first': sum(r['first_within_budget'] for r in rows),
                    'medians': {key: median(r[key] for r in rows) for key in fields}}
             for name, rows in groups.items() if rows}
    if split:
        for name, group in stats.items():
            group['within_wait_and_first_budget'] = sum(r['wait_and_first_within_budget'] for r in groups[name])
    if any(len(rows) != len(spec['condition_order']) for rows in groups.values()):
        return stats, {}
    if 'onset_quanta' in spec:
        return stats, {}
    if split:
        draw, divided = (stats[name]['medians'] for name in ('draw', 'split'))
        saving = draw['constructor_ms'] - divided['constructor_ms']
        delay = divided['constructor_to_first_capture_end_ms'] - draw['constructor_to_first_capture_end_ms']
        return stats, {
            'median_constructor_saving_ms': saving,
            'constructor_saving_target': saving >= spec['minimum_constructor_median_saving_ms'],
            'split_within_wait_and_first_budget_target': stats['split']['within_wait_and_first_budget']
            >= spec['minimum_split_trials_within_wait_and_first_budget'],
            'median_capture_completion_delay_ms': delay,
            'no_later_capture_completion_target': delay <= 0,
        }
    draw = stats['draw']['medians']['first_wasm_ms']
    control_ratio = draw / stats['control']['medians']['first_wasm_ms']
    zero_ratio = draw / stats['zero']['medians']['first_wasm_ms']
    return stats, {
        'draw_to_control_first_wasm_ratio': control_ratio,
        'draw_to_zero_first_wasm_ratio': zero_ratio,
        'draw_to_control_target': control_ratio <= spec['maximum_draw_to_control_first_wasm_ratio'],
        'draw_to_zero_target': zero_ratio <= spec['maximum_draw_to_zero_first_wasm_ratio'],
        'draw_within_budget_target':
            stats['draw']['within_budget_first'] >= spec['minimum_draw_trials_within_first_quantum_budget'],
    }


def measure(study, phase, native, baseline, paths, profiler, out, execute, bun, device, tap):
    spec = study['measurement']
    split = spec if 'quantum_spacing' in spec else None
    onset_count = spec.get('onset_quanta')
    tap_onset = 'minimum_pairs_with_first_quantum_separated' in spec
    tap_draw = 'local_pcm' in study
    tap_control = study.get('tap_control')
    system_io = study.get('system_io')
    trace_control = system_io and system_io.get('compare_thread_state')
    retained_window = system_io and system_io.get('compare_retained_window')
    attach_control = system_io and system_io.get('compare_attach_target')
    stdout_control = system_io and system_io.get('compare_stdout_release_delay_ms')
    onset_load = spec.get('onset_load')
    limits = read(baseline)['measurement']
    execute([*bun, 'run', 'build'], cwd=WEB, stdout=out / 'browser-build.log')
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera', '--test', 'engine', '--test', 'english'],
            cwd=UPSTREAM, stdout=out / 'upstream-tests.log')
    binary = out / 'vocal_wasm.wasm'
    shutil.copyfile(WORKSPACE / WASM, binary)
    checks = {'same_built_wasm': sha256(binary) == sha256(paths['vocal_wasm.wasm'])}
    upper = np.fromfile(paths['upstream.f32le'], dtype='<f4')
    dictionary_hash = read(paths['browser-run.json'])['dictionaryResponseSha256']
    if upper.shape != (limits['output_frames'],) or not np.isfinite(upper).all():
        raise ValueError('固定上流の波形の長さまたは有限性を確認できません')
    trials = []
    preplay = study.get('capture', {}).get('trace_before_playback', False)
    for pair, order in enumerate(spec['condition_order'], 1):
        for condition in order:
            folder = out / f'{pair}-{condition}'
            delay = condition == 'split-late' or onset_load is not None
            preparation_mode = ('draw' if tap_control or trace_control or retained_window or attach_control or stdout_control
                                else 'split' if delay else condition)
            browser_preparation = condition if onset_load else preparation_mode
            trial_split = split
            if onset_load:
                offsets = onset_load['quantum_offsets'][condition]
                block_frames = onset_load['block_frames']
                final_frames = onset_load.get('final_block_frames', {}).get(condition, block_frames)
                trial_split = spec | {'draw_block_frames': block_frames, 'final_block_frames': final_frames,
                                      'draw_frames': (len(offsets) - 1) * block_frames + final_frames,
                                      'quantum_offsets': offsets}
            io_settings = system_io
            if trace_control and condition == 'audio-only':
                io_settings = system_io | {'instruments': [name for name in system_io['instruments']
                                                            if name != 'Thread State Trace']}
            if retained_window and condition == 'tail-900ms':
                io_settings = system_io | {'window': retained_window}
            if attach_control and condition == 'attach-firefox':
                io_settings = system_io | {'attach_firefox': True}
            if stdout_control:
                io_settings = system_io | {'attach_firefox': True}
                if condition == f'stdout-{stdout_control}ms':
                    io_settings['stdout_release_delay_ms'] = stdout_control
            collect_tap = tap and (not preplay or study['capture'].get('wait_for_trace_before_release')) and (
                not tap_control or condition == 'tap')
            draw = trial_split or spec
            setup = (draw['draw_frames'] if preparation_mode in ('draw', 'split') else 0,
                     draw['draw_block_frames'], spec['zero_frame_calls'])
            try:
                capture = capture_io(execute, folder, io_settings) if io_settings else execute
                if tap:
                    capture = capture_tap(capture, folder, study['capture'], tap[0], collect=collect_tap)
                if device:
                    capture = capture_cubeb(capture, folder, device[0])
                result = measure_trial(native, baseline, paths, profiler, folder, capture,
                                       trace_render_phases=True, preparation=browser_preparation,
                                       marker=device[2] if device else None, delay_one_quantum=delay)
                report = read(folder / 'browser.json')
                profile = read(folder / 'firefox-profile.json')
                phases = measure_phases(profile, report, native['measurement'], phase['measurement'], True)
                result['checks'].update(phases.pop('checks'))
                budget = 1000 * limits['render_quantum_frames'] / limits['output_rate_hz']
                valid, preparation = time_preparation(
                    profile, report, native['measurement'], setup, preparation_mode, budget, trial_split)
                result['checks'].update(valid)
                result['preparation'] = preparation
                result['phases'] = phases
                upper_diff = compare_pcm(wavfile.read(folder / 'browser.wav')[1], upper,
                                         limits['upper_pcm_absolute_tolerance'])
                result['upstream'] = upper_diff
                result['checks'].update({
                    'registered_dictionary': read(folder / 'browser-run.json')['dictionaryResponseSha256'] == dictionary_hash,
                    'fixed_upstream_pcm': upper_diff['first_frame_over_tolerance'] is None,
                })
                if all(result['checks'].values()):
                    first, second, *_ = phases['quanta']
                    result['cost'] = {
                        'first_wasm_ms': first['wasm_ms'], 'first_outer_ms': first['outer_ms'],
                        'second_outer_ms': second['outer_ms'], 'first_within_budget': first['outer_ms'] <= budget,
                        'constructor_ms': preparation['constructor_ms'],
                        'constructor_to_first_capture_end_ms': preparation['constructor_to_first_capture_end_ms'],
                        'warm_p99_outer_ms': result['timing']['engine']['warmed']['p99_ms'],
                    }
                    if split is not None:
                        waiting = max(q['maximum_ms'] for q in preparation['waiting'].values())
                        result['cost'].update({'maximum_wait_outer_ms': waiting,
                                               'wait_and_first_within_budget': max(waiting, first['outer_ms']) <= budget})
                if device:
                    checks_device, captured = compare_device(folder, preparation_mode, result, native['measurement'], device)
                    result['checks'].update(checks_device)
                    result['device'] = captured
                    if onset_count:
                        aligned, requests = measure_onset_requests(folder, captured, onset_count)
                        result['checks'].update(aligned)
                        result['device_onset_requests'] = requests
                    if io_settings:
                        io_checks, io = inspect_io(folder, captured, io_settings, execute)
                        result['checks'].update(io_checks)
                        result['system_io'] = io
                        if collect_tap:
                            tap_checks, paired = inspect_tap(folder, captured, io, device[2], tap[1])
                            result['checks'].update(tap_checks)
                            result['paired_output'] = paired
                        if tap and (not preplay or collect_tap) and (tap_onset or tap_draw):
                            result['checks'].update(onset_anchor_checks(captured, requests, io, tap[1]))
                        if tap_control:
                            gate = read(folder / 'trace-release.json')
                            result['checks']['registered_tap_mode'] = (
                                gate['tap_requested'] is collect_tap and (folder / 'tap.json').is_file() == collect_tap)
            except (OSError, ValueError, subprocess.CalledProcessError) as error:
                result = {'checks': {'capture_and_comparison_completed': False}, 'error': str(error)}
            if trace_control or retained_window or attach_control or stdout_control or onset_load:
                result['trace_instruments'] = io_settings['instruments']
            if retained_window:
                result['trace_window'] = io_settings.get('window')
            if attach_control or stdout_control or onset_load:
                result['trace_attach_requested'] = io_settings.get('attach_firefox', False)
            trials.append({'pair': pair, 'condition': condition, **result})
            checks.update({f'{folder.name}/{key}': value for key, value in result['checks'].items()})
            for name in ('firefox-profile.json', 'browser.json'):
                p = folder / name
                if p.is_file():
                    stored.compress(p)
    groups, prediction = summarize(trials, spec)
    summary = {'checks': checks, 'trials': trials, 'groups': groups, 'hypothesis': prediction}
    if system_io:
        observations = [r.get('system_io', {}) for r in trials]
        gaps = [gap for r in observations for gap in r.get('gaps', ())]
        limit = system_io['maximum_client_interval_error_ms']
        summary['system_io'] = {
            'client_windows': sum('client_io' in r for r in observations),
            'server_windows': sum('server_io' in r for r in observations),
            'gaps': len(gaps),
            'gaps_within_callback_budget': sum(g['callback_ms'] <= g['budget_ms'] for g in gaps),
            'gaps_also_in_client_io': sum(g['intervening_client_cycles'] == 0
                                          and abs(g['client_minus_cubeb_entry_interval_ms']) <= limit for g in gaps),
            'gaps_with_intervening_server_writes': sum(len(g.get('server_write_cycles', ())) > 1 for g in gaps),
        }
    elif onset_count:
        summary['device_onset'], summary['device_onset_hypothesis'] = summarize_onset_requests(trials, spec)
    elif device:
        summary['device_hypothesis'] = device_hypothesis(trials, study['device'])
    if tap:
        paired = [r['paired_output'] for r in trials if r.get('paired_output', {}).get('valid')]
        checks_controls, evidence = tap_controls(tap[1])
        checks.update(checks_controls)
        summary['paired_output'] = {
            'valid_tap_windows': len(paired), 'controls': evidence,
            'gaps_with_server_pcm': sum(bool(gap['server_pcm']) for r in paired for gap in r['gaps']),
            'gaps_with_unmapped_server_pcm': sum(r['server_pcm_unmapped_gaps'] for r in paired),
        }
    if tap_onset:
        summary['tap_onset'] = summarize_tap_onset(trials, spec)
    if tap_draw:
        summary['tap_draw'] = summarize_draw_tap(trials, system_io['maximum_client_interval_error_ms'])
        if timing := study.get('construction_timing'):
            center = timing['reference_center_marker_frame']
            width = timing['maximum_center_error_frames']
            frames = [row['marker_frame'] for row in summary['tap_draw']['construction_positions'] if row['valid']]
            summary['tap_draw']['construction_positions_near_reference'] = sum(abs(frame - center) <= width for frame in frames)
    if tap_control:
        summary['tap_control'] = summarize_tap_control(trials, tap_control)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--split', action='store_true', help='待機量子に事前描画を分ける条件を比較する')
    mode.add_argument('--device', action='store_true', help='先行音とともに機器向けの出力要求を採取する')
    mode.add_argument('--device-variable', action='store_true', help='機器向けの可変長の出力要求を照合する')
    mode.add_argument('--device-onset', action='store_true', help='発話の採取開始を1量子ずらして照合する')
    mode.add_argument('--device-io', action='store_true', help='機器要求とAudio Client・Audio Serverを同時に採取する')
    mode.add_argument('--device-tap', type=Path, metavar='APP', help='I/Oと同じ試行でプロセスタップも採取する')
    mode.add_argument('--device-tap-onset', type=Path, metavar='APP',
                      help='開始を1量子ずらし、I/Oとプロセスタップを比較する')
    mode.add_argument('--device-tap-draw', type=Path, metavar='APP',
                      help='同期事前描画で構築時と発話開始時のタップPCMを照合する')
    parser.add_argument('--draw-case', type=Path, help='同期事前描画の同時採取を派生ケースで実行する')
    args = parser.parse_args()
    if args.draw_case and not args.device_tap_draw:
        parser.error('--draw-case には --device-tap-draw が必要です')
    tap_app = args.device_tap or args.device_tap_onset or args.device_tap_draw
    variable = args.device_variable or args.device_onset or args.device_io or tap_app is not None
    case = (DEVICE_TAP_DRAW_CASE if args.device_tap_draw else DEVICE_TAP_ONSET_CASE if args.device_tap_onset else
            DEVICE_TAP_CASE if args.device_tap else DEVICE_IO_CASE if args.device_io else
            DEVICE_ONSET_CASE if args.device_onset else VARIABLE_DEVICE_CASE if args.device_variable
            else DEVICE_CASE if args.device else SPLIT_CASE if args.split else CASE)
    if args.draw_case:
        case = args.draw_case.resolve()
    study = read(case)
    if args.draw_case and (case.parent != DEVICE_TAP_DRAW_CASE.parent or
                           study.get('base_case') != DEVICE_TAP_DRAW_CASE.name):
        parser.error('同期事前描画のケースを同じディレクトリから継承してください')
    if variable:
        variable_case = read(VARIABLE_DEVICE_CASE)
        base = read(VARIABLE_DEVICE_CASE.with_name(variable_case['base_case']))
        inherited = [base, variable_case]
        if tap_app:
            inherited.append(read(DEVICE_IO_CASE))
        if args.device_tap_onset or args.device_tap_draw:
            inherited.append(read(DEVICE_TAP_CASE))
        if args.draw_case:
            inherited.append(read(DEVICE_TAP_DRAW_CASE))
        resolved = {'device': {}, 'measurement': {}}
        for layer in [*inherited, study]:
            resolved = resolved | layer | {key: resolved[key] | layer.get(key, {}) for key in ('device', 'measurement')}
        study = resolved
    rev = study['upstream_revision']
    if (subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip() != rev
            or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM)):
        parser.error('差分のない固定上流版が必要です')
    phase_run = hydrate_run(study['phase_run'], study['phase_case'], rev)
    phase_case = snapshot_case(phase_run, study['phase_case'])
    phase = read(phase_case)
    native_run = hydrate_run(phase['native_run'], phase['native_case'], rev)
    native_case = snapshot_case(native_run, phase['native_case'])
    native = read(native_case)
    normal = hydrate_run(study['baseline_run'], study['baseline_case'], rev)
    baseline = snapshot_case(normal, study['baseline_case'])
    registered = read(baseline)
    upper = hydrate_run(registered['upstream_run'], registered['upstream_case'], rev)
    profiler_case = WORKSPACE / 'cases' / native['gecko_profile_case']
    spec = study['measurement']
    trace = study.get('system_io', {})
    if trace.get('compare_thread_state') and (
            not study.get('capture', {}).get('trace_before_playback')
            or set(trace['instruments']) != {'Audio Client', 'Audio Server', 'Thread State Trace'}
            or any(sorted(pair) != ['audio-only', 'thread-state'] for pair in spec['condition_order'])):
        parser.error('スレッド状態収録を切り替える対照条件が一致しません')
    if trace.get('compare_retained_window') and (
            trace['compare_retained_window'] != '900ms' or trace.get('compare_thread_state')
            or not study.get('capture', {}).get('trace_before_playback')
            or set(trace['instruments']) != {'Audio Client', 'Audio Server', 'Thread State Trace'}
            or any(sorted(pair) != ['tail-900ms', 'whole-trace'] for pair in spec['condition_order'])):
        parser.error('終了前の保持窓を切り替える対照条件が一致しません')
    capture = study.get('capture', {})
    if trace.get('compare_attach_target') and (
            trace.get('compare_thread_state') or trace.get('compare_retained_window') or trace.get('window')
            or not capture.get('trace_before_playback') or not capture.get('publish_trace_target')
            or set(trace['instruments']) != {'Audio Client', 'Audio Server', 'Thread State Trace'}
            or any(sorted(pair) != ['all-processes', 'attach-firefox'] for pair in spec['condition_order'])):
        parser.error('Firefoxへのアタッチを切り替える対照条件が一致しません')
    if trace.get('compare_stdout_release_delay_ms') and (
            type(trace['compare_stdout_release_delay_ms']) is not int
            or trace['compare_stdout_release_delay_ms'] <= 0 or trace.get('compare_attach_target')
            or trace.get('compare_thread_state') or trace.get('compare_retained_window')
            or not trace.get('observe_start_signals') or not capture.get('observe_start_signals')
            or not capture.get('trace_before_playback') or not capture.get('publish_trace_target')
            or set(trace['instruments']) != {'Audio Client', 'Audio Server', 'Thread State Trace'}
            or any(sorted(pair) != ['darwin', f"stdout-{trace['compare_stdout_release_delay_ms']}ms"]
                   for pair in spec['condition_order'])):
        parser.error('開始行から所定時間後に再生する対照条件が一致しません')
    if onset_load := spec.get('onset_load'):
        final_frames = onset_load.get('final_block_frames')
        paired = ('split-early-load', 'split-onset-load')
        conditions = {'split-early-load': [0, 2, 4, 6], 'split-onset-load': [0, 2, 4, 16]}
        expected_final = None
        if final_frames is not None:
            paired = ('split-onset-load', 'split-onset-load-224')
            conditions = {name: [0, 2, 4, 16] for name in paired}
            expected_final = {'split-onset-load': onset_load['block_frames'], 'split-onset-load-224': 224}
        if capture.get('wait_for_trace_before_release'):
            supported = {
                'split-onset-load-224': 224, 'split-onset-load-256': 256,
                'split-onset-load-288': 288, 'split-onset-load-320': 320,
            }
            paired = tuple(onset_load['quantum_offsets'])
            if len(paired) != 1 or paired[0] not in supported:
                parser.error('タップ併用の発話直前描画には登録済みの単独条件を指定してください')
            condition, = paired
            conditions = {condition: [0, 2, 4, 16]}
            expected_final = {condition: supported[condition]}
        quantum = registered['measurement']['render_quantum_frames']
        if (not args.draw_case or trace.get('stdout_release_delay_ms') != 500
                or not trace.get('attach_firefox') or not capture.get('trace_before_playback')
                or not trace.get('observe_start_signals') or not capture.get('publish_trace_target')
                or onset_load['quantum_offsets'] != conditions
                or any(sorted(pair) != list(paired) for pair in spec['condition_order'])
                or registered['measurement']['lead_frames'] // quantum != 16
                or onset_load['block_frames'] * 4 != spec['draw_frames']
                or onset_load['block_frames'] != 2 * spec['draw_block_frames']
                or final_frames != expected_final):
            parser.error('発話直前の事前描画の条件が一致しません')
    if (spec['draw_block_frames'] != registered['measurement']['observation_stride_frames']
            or spec['draw_frames'] % spec['draw_block_frames'] != 0):
        parser.error('事前描画の長さを通常の描画区間と照合できません')
    paths = {key: verified_file(*normal, f'artifacts/firefox/{key}') for key in
             ('browser-case.json', 'browser-run.json', 'browser.json', 'browser.wav')}
    paths['vocal_wasm.wasm'] = verified_file(*normal, 'artifacts/vocal_wasm.wasm')
    paths['upstream.f32le'] = verified_file(*upper, 'artifacts/upstream.f32le')
    bun = ['bun'] if shutil.which('bun') else ['npx', '--yes', '--package=bun@1.4.4', '--', 'bun']
    inputs = [case, Path(__file__).resolve(), phase_case, native_case, baseline, profiler_case,
              snapshot_case(upper, registered['upstream_case']),
              *(run[0] / 'manifest.json' for run in (phase_run, native_run, normal, upper)), *paths.values(),
              *candidate_sources(), *web_sources(),
              *(WORKSPACE / 'tools' / name for name in ('measure_uniform_tube.py',
                'measure_worklet_live_tsp_firefox_render_phases.py', 'measure_worklet_live_tsp_firefox_native_clock.py',
                'measure_worklet_live_tsp_source_defaults.py', 'measure_worklet_live_song_render_phases.py',
                'measure_worklet_song_firefox_registration_native.py', 'measure_worklet_live_ipa_cross_browser.py',
                'measure_worklet_firefox_native_clock.py', 'measure_wasm_fixed.py', 'measure_worklet_fixed.py',
                'measure_worklet_realtime.py', 'measure_tsp_listening.py', 'measure_lip_crossing_thickness.py',
                'measure_speech_timing.py', 'measure_csd_envelope_timing.py', 'upstream_baseline.py'))]
    if args.split or args.device or variable:
        previous = hydrate_run(study['preparation_run'], study['preparation_case'], rev)
        reference_case = snapshot_case(previous, study['preparation_case'])
        keys = ('draw_frames', 'draw_block_frames', 'zero_frame_calls')
        if any(spec[key] != read(reference_case)['measurement'][key] for key in keys):
            parser.error('同期と分割で事前描画の入力が一致しません')
        if spec['quantum_spacing'] * (spec['draw_frames'] // spec['draw_block_frames'] - 1) >= (
                registered['measurement']['lead_frames'] // registered['measurement']['render_quantum_frames']):
            parser.error('分割した事前描画が予定した待機量子に入りません')
        inputs += [reference_case, previous[0] / 'manifest.json', verified_file(*previous, 'summary.json')]
    details = {'case_id': study['id'], 'case_revision': study['revision'], 'upstream_revision': rev,
               'invoked_from': str(Path.cwd()), 'node': subprocess.check_output(['node', '-v'], text=True).strip(),
               'bun': subprocess.check_output([*bun, '--version'], text=True).strip(),
               'firefox_override': os.environ.get('CHIMERA_FIREFOX')}
    device = None
    tap = None
    if args.device or variable:
        try:
            device, versions, device_paths = device_inputs(study, rev)
        except (ValueError, OSError) as error:
            parser.error(str(error))
        inputs += device_paths
        details.update(versions)
        native['measurement']['processor'] = 'chimera-fixed-voice'
        if variable:
            pilot = WORKSPACE / 'runs' / study['pilot_run']
            pilot_manifest = read(pilot / 'manifest.json')
            if (pilot_manifest['case_id'], pilot_manifest['upstream_revision'], pilot_manifest['status']) != (
                    DEVICE_CASE.stem, rev, 'fail'):
                parser.error('固定フレーム数の予備採取とその判定を確認できません')
            inputs += [DEVICE_CASE, pilot / 'manifest.json', verified_file(pilot, pilot_manifest, 'summary.json')]
        if args.device_onset:
            reference = hydrate_run(study['reference_onset_run'], VARIABLE_DEVICE_CASE.stem, rev)
            inputs += [VARIABLE_DEVICE_CASE, reference[0] / 'manifest.json', verified_file(*reference, 'summary.json')]
        if args.device_io or tap_app:
            reference = hydrate_run(study['reference_onset_run'], DEVICE_ONSET_CASE.stem, rev)
            inputs += [VARIABLE_DEVICE_CASE, DEVICE_ONSET_CASE, reference[0] / 'manifest.json',
                       verified_file(*reference, 'summary.json'), DEVICE_IO_TOOL,
                       *(WORKSPACE / 'tools' / name for name in ('capture_worklet_system_pair.py',
                           'filter_worklet_audioipc_syscalls.py', 'measure_safari_audio_client_trace.py'))]
        if tap_app:
            reference = hydrate_run(study['reference_io_run'], DEVICE_IO_CASE.stem, rev)
            try:
                tap, device, versions, tap_paths = tap_inputs(study, rev, device, tap_app)
            except (ValueError, OSError) as error:
                parser.error(str(error))
            inputs += [DEVICE_IO_CASE, reference[0] / 'manifest.json', verified_file(*reference, 'summary.json'), *tap_paths]
            details.update(versions)
        if args.device_tap_onset or args.device_tap_draw:
            reference = hydrate_run(study['reference_tap_run'], DEVICE_TAP_CASE.stem, rev)
            parent = snapshot_case(reference, DEVICE_TAP_CASE.stem)
            if read(parent) != read(DEVICE_TAP_CASE):
                parser.error('同期と分割の同時採取で使ったケースが一致しません')
            inputs += [DEVICE_TAP_CASE, parent, reference[0] / 'manifest.json', verified_file(*reference, 'summary.json')]
        if args.draw_case:
            inputs.append(DEVICE_TAP_DRAW_CASE)
        if earlier_run := study.get('initial_control_run'):
            original = WORKSPACE / 'runs' / earlier_run
            manifest_path = original / 'manifest.json'
            manifest = read(manifest_path)
            if (manifest['run_id'], manifest['case_id'], manifest['upstream_revision']) != (
                    earlier_run, Path(study['initial_control_case']).stem, rev):
                parser.error('最初のタップ対照の実行記録が一致しません')
            inputs += [manifest_path, snapshot_case((original, manifest), manifest['case_id']),
                       verified_file(original, manifest, 'summary.json')]
    return record_measurement(args.run_id, case, inputs, details, lambda out, execute: measure(
        study, phase, native, baseline, paths, read(profiler_case)['measurement'], out, execute, bun, device, tap),
        command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
