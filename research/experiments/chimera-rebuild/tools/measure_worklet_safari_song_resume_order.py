"""macOS Safariの実時間歌唱でWorklet登録、Context再開とノード生成を比較する。"""

import argparse
import gzip
import json
from pathlib import Path
import shutil
from statistics import median
import subprocess
import sys

import numpy as np
from scipy.io import wavfile

import measure_worklet_live_song_app_silent_lead as startup
from upstream_baseline import sha256


realtime = startup.realtime
song = realtime.song
READ = realtime.READ
CASE = song.WORKSPACE / 'cases/worklet-live-song-fast-safari-resume-order.json'
CAPTURE = song.WEB / 'tools/capture-safari-song.mjs'


def capture_trial(folder, reference, study, spec, mode, route, execute):
    folder.mkdir()
    config = {'register_before_resume': mode == 'suspended', 'startup_timeout_seconds': study['startup_timeout_seconds']}
    if 'hold_frames_by_mode' in study:
        config['hold_after_registration_frames'] = study['hold_frames_by_mode'][mode]
    if 'paused_registration' in study:
        config['paused_registration'] = {**study['paused_registration'], 'resume_after_connect': mode == 'resume_after_connect'}
    if 'mid_song_pause' in study:
        config['mid_song_pause'] = {**study['mid_song_pause'], 'perform_pause': mode == 'paused'}
    if study.get('record_song'):
        config['record_song'] = True
    if route == 'observed':
        config['output_probe'] = {'quantum': spec['quantum'], 'captureQuanta': spec['output_probe_quanta'],
                                  'holdConnectionsThroughTail': True}
    options = folder / 'capture-case.json'
    options.write_text(json.dumps(config, ensure_ascii=False, indent=2) + '\n')
    execute(['node', str(CAPTURE), str(folder), str(reference['input.json']), str(options)],
            stdout=folder / 'browser-command.log')
    rate, pcm = wavfile.read(folder / 'browser.wav')
    return READ(folder / 'browser-run.json'), READ(folder / 'browser.json'), rate, pcm


def compare_node_wait(report, observed, hold_frames, quantum):
    phases = {item['phase']: item for item in observed['phases']}
    registration = phases['add_module_complete']
    node = next(mark for mark in report['startupTrace']['marks'] if mark['phase'] == 'node_start')
    initial = registration['context']['frame']
    node_delta = node['contextFrame'] - initial
    hold_begin, hold_end = (phases.get(phase) for phase in ('registration_hold_start', 'registration_hold_complete'))
    hold_matches = hold_begin is None and hold_end is None
    actual_hold, elapsed = 0, 0
    if hold_frames:
        hold_matches = hold_begin is not None and hold_end is not None
        if hold_matches:
            actual_hold = hold_end['context']['frame'] - hold_begin['context']['frame']
            elapsed = hold_end['wallMs'] - hold_begin['wallMs']
            order = [registration['wallMs'], hold_begin['wallMs'], hold_end['wallMs'], node['wallMs']]
            hold_matches = (actual_hold >= hold_frames and node['contextFrame'] >= hold_end['context']['frame']
                            and order == sorted(order) and hold_begin['url'] == hold_end['url'] == registration['url']
                            and all(item['context']['state'] == 'running' for item in (hold_begin, hold_end)))
    live = report['realtime']
    first, second = (live[key] for key in ('startupFirstContextFrame', 'startupSecondContextFrame'))
    first_step = second - first
    checks = {'registered_then_created_with_requested_hold': hold_matches and node_delta >= hold_frames,
              'first_two_callback_labels_acquired': (first >= 0 and first % quantum == second % quantum == 0
                                                     and first_step >= quantum)}
    return checks, {'last_module': registration['url'], 'registration_completed_frame': initial,
                    'node_start_frame': node['contextFrame'], 'registration_to_node_frames': node_delta,
                    'registration_to_node_ms': node['wallMs'] - registration['wallMs'],
                    'requested_hold_frames': hold_frames, 'observed_hold_frames': actual_hold, 'hold_ms': elapsed,
                    'first_two_frames': [first, second], 'first_frame_step': first_step}


def compare_paused_registration(report, observed, mode, settings):
    phases = {item['phase']: item for item in observed['phases']}
    marks = {item['phase']: item for item in report['startupTrace']['marks']}
    frozen = phases['paused_registration_suspended']
    position = frozen['context']['frame']
    modules = [item for item in observed['phases'] if item['phase'] in ('add_module_request', 'add_module_complete')]
    requested, restarted = (phases[key] for key in ('paused_registration_resume_requested', 'paused_registration_resumed'))
    node, connected = (marks[key] for key in ('node_start', 'connected'))
    sequence = [frozen['wallMs'], *(item['wallMs'] for item in modules), requested['wallMs'], restarted['wallMs']]
    paused_state = {'frame': position, 'state': 'suspended'}
    checks = {'worklet_registered_at_nonzero_suspended_frame': (len(modules) >= 2 and sequence == sorted(sequence)
              and position >= settings['minimum_advance_frames'] and all(item['context'] == paused_state
              for item in (frozen, *modules, requested))),
              'context_restarted_after_registration': restarted['context']['state'] == 'running'}
    if mode == 'resume_after_connect':
        graph = phases['paused_registration_graph_connected']
        checks['node_connected_before_restart'] = (node['contextState'] == connected['contextState'] == 'suspended'
            and node['contextFrame'] == connected['contextFrame'] == position and graph['context'] == paused_state
            and modules[-1]['wallMs'] <= node['wallMs'] <= graph['wallMs'] <= connected['wallMs'] <= requested['wallMs'])
    else:
        advanced = phases['paused_registration_advanced']
        checks['restarted_and_advanced_before_node'] = (node['contextState'] == connected['contextState'] == 'running'
            and restarted['wallMs'] <= advanced['wallMs'] <= node['wallMs'] <= connected['wallMs']
            and position + settings['advance_after_resume_frames'] <= advanced['context']['frame'] <= node['contextFrame'])
    live = report['realtime']
    first, second = (live[key] for key in ('startupFirstContextFrame', 'startupSecondContextFrame'))
    return checks, {'paused_frame': position, 'node_frame': node['contextFrame'], 'connection_frame': connected['contextFrame'],
                    'first_two_frames': [first, second], 'startup_callbacks': live['startupCallbacks'],
                    'armed_frame': live['armedContextFrame']}


def compare_mid_song_pause(report, observed, mode, settings):
    phases = {item['phase']: item for item in observed['phases']}
    live = report['realtime']
    start_frame = live['scheduledContextFrame']
    target = start_frame + settings['target_output_frame']
    reached = phases['mid_song_target_reached']
    reached_frame = reached['context']['frame']
    blocks = live['blocks']
    before, after = max(zip(blocks, blocks[1:]), key=lambda pair: pair[1][4] - pair[0][4])
    checks = {'scheduled_notice_and_observed_target': (observed['scheduledFrame'] == start_frame
              and phases['mid_song_reservation_received']['wallMs'] <= reached['wallMs']
              and reached['context']['state'] == 'running'
              and target <= reached_frame <= target + settings['target_tolerance_frames'])}
    result = {'target_frame': target, 'target_reached_frame': reached_frame,
              'longest_callback_gap_ms': after[4] - before[4], 'longest_gap_frames': [before[0], after[0]]}
    pause_phases = ('mid_song_suspend_requested', 'mid_song_suspended', 'mid_song_resume_requested', 'mid_song_resumed')
    if mode == 'paused':
        request, stopped, restart, restarted = (phases[key] for key in pause_phases)
        position = stopped['context']['frame']
        order = [event['wallMs'] for event in (reached, request, stopped, restart, restarted)]
        states = [event['context']['state'] for event in (request, stopped, restart, restarted)]
        hold_ms = restart['wallMs'] - stopped['wallMs']
        checks['suspend_and_resume_completed_during_song'] = (order == sorted(order)
            and states == ['running', 'suspended', 'suspended', 'running'] and hold_ms >= settings['hold_ms'] - 1
            and reached_frame <= request['context']['frame'] <= position < blocks[-1][0])
        result.update(paused_frame=position, resumed_request_frame=restart['context']['frame'],
                      pause_output_frame=position - start_frame, hold_ms=hold_ms)
    else:
        checks['continuous_control_without_pause'] = not any(key in phases for key in pause_phases)
    return checks, result


def measure(study, spec, fixed, reference, upper, wasm, artifacts, execute, bun):
    execute([*bun, 'run', 'build'], cwd=song.WEB, stdout=artifacts / 'browser-build.log')
    binary_path = artifacts / 'vocal_wasm.wasm'
    shutil.copyfile(song.WORKSPACE / song.wasm.WASM, binary_path)
    binary_hash = sha256(binary_path)
    dictionary_hashes = {True: sha256(song.DICTIONARY),
                         False: song.bytes_digest(gzip.decompress(song.DICTIONARY.read_bytes())).hexdigest()}
    upper_pcm = np.fromfile(upper, dtype='<f4')
    checks = {'wasm_matches_offline': binary_hash == sha256(wasm),
              'dictionary_matches_upstream': dictionary_hashes[True] == sha256(song.UPSTREAM_DICTIONARY)}
    trials, predictions, effects = [], {}, {}
    hold_by_mode = study.get('hold_frames_by_mode')
    paused = study.get('paused_registration')
    mid_song = study.get('mid_song_pause')
    for route in study['routes']:
        rows = []
        for number, pair_order in enumerate(study['condition_order'], 1):
            for mode in pair_order:
                label = f'{route}-{number}-{mode}'
                folder = artifacts / label
                row = {'trial': label, 'route': route, 'pair': number, 'mode': mode}
                local = {}
                try:
                    browser, report, rate, pcm = capture_trial(folder, reference, study, spec, mode, route, execute)
                    local, result, expected = realtime.compare(browser, report, rate, pcm, folder, reference, fixed,
                                                               upper_pcm, dictionary_hashes, binary_hash, spec, engine='safari')
                    row.update(result)
                    clock = result['clock']
                    launch_checks, launched = startup.compare_startup(browser, report, clock, 0, spec)
                    local.update(launch_checks)
                    row.update(launched)
                    observed = READ(folder / 'startup.json')
                    local['trusted_singing_click'] = observed['click']['trusted'] is True
                    phases = {item['phase'] for item in observed['phases']}
                    local['native_registration_and_resume_completed'] = {'add_module_complete', 'resume_complete'} <= phases
                    if paused:
                        order_checks, row['paused_registration'] = compare_paused_registration(report, observed, mode, paused)
                    else:
                        order_checks, row['resume_registration'] = startup.compare_resume_registration(
                            report, 'running' if mid_song or hold_by_mode else mode)
                    local.update(order_checks)
                    if mid_song:
                        mid_song_checks, row['mid_song_pause'] = compare_mid_song_pause(report, observed, mode, mid_song)
                        local.update(mid_song_checks)
                    if hold_by_mode:
                        wait_checks, row['node_after_registration'] = compare_node_wait(
                            report, observed, hold_by_mode[mode], spec['quantum'])
                        local.update(wait_checks)
                    if route == 'observed':
                        probe_error = folder / 'output-probe-error.json'
                        if probe_error.is_file():
                            raise ValueError(READ(probe_error)['error'])
                        probe_checks, row['output_probe'] = realtime.compare_output_probe(folder, clock, expected, spec)
                        local.update(probe_checks)
                        probe = READ(folder / 'output-probe.json')
                        local['probe_keeps_song_connected_through_tail'] = probe['deferredDisconnects'] == 1
                        if paused or hold_by_mode:
                            comparison = row['paused_registration' if paused else 'node_after_registration']
                            row['output_probe']['first_two_frames'] = probe['frames'][:2]
                            local['probe_first_two_labels_match'] = probe['frames'][:2] == comparison['first_two_frames']
                except (OSError, KeyError, StopIteration, TypeError, ValueError, subprocess.CalledProcessError) as error:
                    row['error'] = str(error)
                    local['capture_and_comparison_completed'] = False
                trace = folder / 'startup.json'
                if trace.is_file():
                    row['startup_observation'] = READ(trace)
                checks.update({f'{label}/{key}': passed for key, passed in local.items()})
                rows.append(row)
        pairs = []
        if mid_song:
            control, modified = 'continuous', 'paused'
        elif paused:
            control, modified = 'resume_before_node', 'resume_after_connect'
        else:
            control, modified = ('immediate', 'one_quantum') if hold_by_mode else ('running', 'suspended')
        timing_delta = f'{modified}_minus_{control}_ms'
        for number, group in startup.complete_pairs(rows, study['condition_order']):
            timing = {mode: row['click_to_first_output_ms'] for mode, row in group.items()}
            pair = {'pair': number, 'click_to_first_output_ms': timing, timing_delta: timing[modified] - timing[control]}
            if mid_song:
                pair['longest_callback_gap_ms'] = {mode: row['mid_song_pause']['longest_callback_gap_ms']
                                                   for mode, row in group.items()}
            pairs.append(pair)
        effects[route] = {'pairs': pairs, f'median_{timing_delta}': median(pair[timing_delta] for pair in pairs) if pairs else None}
        complete = len(pairs) == len(study['condition_order'])
        if mid_song:
            quantum = spec['quantum']
            interruptions = [row['mid_song_pause'] for row in rows if row['mode'] == modified and 'error' not in row]
            predictions[f'{route}/context_frame_frozen_until_resume_request'] = complete and all(
                row['paused_frame'] == row['resumed_request_frame'] for row in interruptions)
            predictions[f'{route}/wall_gap_at_consecutive_pause_boundary'] = complete and all(
                row['longest_gap_frames'] == [row['paused_frame'] - quantum, row['paused_frame']] for row in interruptions)
            predictions[f'{route}/pause_increases_render_interval'] = complete and all(
                pair['longest_callback_gap_ms'][modified] >= 100
                and pair['longest_callback_gap_ms'][modified] > pair['longest_callback_gap_ms'][control] for pair in pairs)
        elif paused:
            quantum = spec['quantum']
            sequence = spec['startup_contiguous_callbacks']
            predictions[f'{route}/resume_before_node_gives_consecutive_start'] = complete and all(
                row['missing_frames_before_song'] == 0 and row['clock']['first_quantum_to_start_as_predicted']
                for row in rows if row['mode'] == control)
            late = [row for row in rows if row['mode'] == modified and 'error' not in row]
            predictions[f'{route}/resume_after_connect_starts_with_stale_zero'] = complete and all(
                row['paused_registration']['first_two_frames'] == [0, row['paused_registration']['paused_frame'] + quantum]
                for row in late)
            predictions[f'{route}/resume_after_connect_resynchronizes_at_second_callback'] = complete and all(
                row['paused_registration']['startup_callbacks'] == sequence + 1
                and row['clock']['start_frame'] == row['paused_registration']['paused_frame'] + (sequence + 1) * quantum
                + spec['lead_frames'] for row in late)
        elif hold_by_mode:
            quantum = spec['quantum']
            predictions[f'{route}/holding_makes_first_step_one_quantum'] = complete and all(
                row['node_after_registration']['first_frame_step'] == quantum for row in rows if row['mode'] == modified)
            predictions[f'{route}/immediate_reproduces_first_step_gap'] = complete and any(
                row['node_after_registration']['first_frame_step'] > quantum for row in rows if row['mode'] == control)
        else:
            predictions[f'{route}/both_registration_orders_complete'] = complete and all(
                checks[f'{row["trial"]}/resume_registration_order_and_state'] for row in rows)
        predictions.update({f'{route}/{key}': value
                            for key, value in startup.preserved_startup(rows, checks, complete).items()})
        trials.extend(rows)
    return {'checks': checks, 'predictions': predictions, 'effects': effects, 'trials': trials}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('--case', type=Path, default=CASE)
    args = parser.parse_args()
    path = args.case.resolve(strict=True)
    study = READ(path)
    realtime_path = CASE.parent / study['realtime_study']
    real_case = READ(realtime_path)
    offline_path = CASE.parent / real_case['offline_study']
    offline_case = READ(offline_path)
    fixed_path = CASE.parent / offline_case['capture_case']
    fixed = READ(fixed_path)
    revision = study['upstream_revision']
    spec = real_case['measurement']
    hold_by_mode = study.get('hold_frames_by_mode')
    paused = study.get('paused_registration')
    mid_song = study.get('mid_song_pause')
    if mid_song is not None:
        modes = ['continuous', 'paused']
        target = mid_song['target_output_frame']
        if (hold_by_mode is not None or paused is not None or target <= 0 or target % spec['quantum']
                or target + mid_song['target_tolerance_frames'] >= spec['frames'] or mid_song['hold_ms'] <= 0):
            parser.error('歌唱途中の停止条件が描画範囲内に収まりません')
    elif paused is not None:
        modes = ['resume_after_connect', 'resume_before_node']
        if (hold_by_mode is not None or paused['minimum_advance_frames'] <= 0
                or paused['minimum_advance_frames'] % spec['quantum']
                or paused['advance_after_resume_frames'] != spec['quantum']):
            parser.error('停止前のフレーム数または再開後の待機条件が一致しません')
    else:
        modes = ['immediate', 'one_quantum'] if hold_by_mode is not None else ['running', 'suspended']
    if hold_by_mode is not None and hold_by_mode != {'immediate': 0, 'one_quantum': spec['quantum']}:
        parser.error('Worklet登録後の待機は0または1量子を指定してください')
    if (study['browser_engine'] != 'safari' or any(case['upstream_revision'] != revision
            for case in (real_case, offline_case, fixed)) or not study['condition_order']
            or any(sorted(pair) != modes for pair in study['condition_order'])
            or subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=song.UPSTREAM, text=True).strip() != revision
            or subprocess.check_output(['git', 'status', '--porcelain'], cwd=song.UPSTREAM, text=True)):
        parser.error('Safariの対照条件または固定上流が一致しません')
    offline = song.run_manifest(real_case['offline_run'], offline_case['id'], revision)
    upstream = song.run_manifest(offline_case['reference_run'], 'song-voice-fast-constriction-source', revision)
    if any(run[1]['status'] != 'pass' for run in (offline, upstream)):
        parser.error('オフラインと固定上流の保存基準が揃いません')
    label = study['offline_condition']
    reference = {name: song.verified_path(offline, f'artifacts/{label}/{name}') for name in (
        'input.json', 'browser.wav', 'browser.json', 'browser-case.json')}
    upper = song.verified_path(upstream, 'artifacts/upstream-pcm.f32')
    wasm = song.verified_path(offline, 'artifacts/vocal_wasm.wasm')
    bun = ['bun'] if shutil.which('bun') else ['npx', '--offline', '--yes', '--package=bun@1.4.4', '--', 'bun']
    metadata = {'case_id': study['id'], 'upstream_revision': revision, 'browser_engine': 'safari',
                'turbulence_seed': offline_case['noise_seed'],
                'analysis_directory': str(Path.cwd()), 'analysis_command': [sys.executable, *sys.argv],
                'safaridriver': subprocess.check_output(['/usr/bin/safaridriver', '--version'], text=True).strip(),
                'node': subprocess.check_output(['node', '--version'], text=True).strip(),
                'bun': subprocess.check_output([*bun, '--version'], text=True).strip()}
    inputs = [path, realtime_path, offline_path, fixed_path, Path(__file__).resolve(), CAPTURE,
              CAPTURE.with_name('safari-webdriver.mjs'), upper, wasm,
              *reference.values(), offline[0] / 'manifest.json', upstream[0] / 'manifest.json',
              *song.web_sources(), *song.shared.candidate_sources(), *(Path(module.__file__) for module in (
                  startup, realtime, song, song.wasm, song.shared, song.realtime))]
    if hold_by_mode:
        earlier = study['resume_order_reference']
        earlier_path = CASE.parent / earlier['case']
        earlier_case = READ(earlier_path)
        earlier_run = song.run_manifest(earlier['run'], earlier_case['id'], revision)
        earlier_summary = song.verified_path(earlier_run, 'summary.json')
        if (earlier_run[1]['status'] != 'pass' or any(earlier_case[key] != study[key]
                for key in ('realtime_study', 'offline_condition', 'browser_engine'))
                or not any(row['mode'] == 'running' and row['missing_frames_before_song'] > 0
                           for row in READ(earlier_summary)['trials'])):
            parser.error('Safariの再開後登録の保存基準が揃いません')
        inputs.extend([earlier_path, earlier_run[0] / 'manifest.json', earlier_summary])
    if paused:
        creation = study['creation_clock_reference']
        creation_path = CASE.parent / creation['case']
        creation_case = READ(creation_path)
        creation_run = song.run_manifest(creation['run'], creation_case['id'], revision)
        creation_summary = song.verified_path(creation_run, 'summary.json')
        creation_spec = creation_case['measurement']
        if (creation_run[1]['status'] != 'pass' or creation_spec['advanced_minimum_frames'] != paused['minimum_advance_frames']
                or creation_spec['sample_rate_hz'] != spec['sample_rate_hz'] or creation_spec['quantum_frames'] != spec['quantum']
                or not READ(creation_summary)['predictions']['advanced/processing_matches_prediction']):
            parser.error('停止中に登録したSafariの保存基準が揃いません')
        inputs.extend([creation_path, creation_run[0] / 'manifest.json', creation_summary])
    if mid_song:
        earlier = study['paused_registration_reference']
        earlier_path = CASE.parent / earlier['case']
        earlier_case = READ(earlier_path)
        earlier_run = song.run_manifest(earlier['run'], earlier_case['id'], revision)
        earlier_summary = song.verified_path(earlier_run, 'summary.json')
        if (earlier_run[1]['status'] != 'pass' or any(earlier_case[key] != study[key]
                for key in ('realtime_study', 'offline_condition', 'browser_engine'))
                or not READ(earlier_summary)['predictions']['observed/pcm_states_and_plan_identical']):
            parser.error('Safariの停止・再開と歌唱の保存基準が揃いません')
        inputs.extend([earlier_path, earlier_run[0] / 'manifest.json', earlier_summary])
    return song.shared.record_measurement(args.run_id, path, inputs, metadata,
        lambda artifacts, execute: measure(study, spec, fixed, reference, upper, wasm, artifacts, execute, bun),
        command=None, input_root=song.ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
