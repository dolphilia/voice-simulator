"""歌唱画面の無音先行を開始時刻・連続性・PCMで比較する。"""

import argparse
import gzip
import os
from pathlib import Path
import shutil
from statistics import median
import subprocess
import sys

import numpy as np

import measure_worklet_live_song_teeth_lowpass_floor as realtime
import worklet_song_native_trace as native_trace
from measure_lip_crossing_thickness import compress
from upstream_baseline import sha256


song = realtime.song
READ = realtime.READ
CASE = song.WORKSPACE / 'cases/worklet-live-song-fast-app-silent-lead.json'
LEAD_TRACE_COLUMNS = ['context_frame', 'output_frames', 'input_channels', 'input_frames', 'has_nonzero_input']


def compare_startup(browser, report, clock, quanta, spec, parallel=False):
    click = browser['clickEpochMs']
    first_output = report['realtime']['firstOutputEpochMs']
    elapsed = first_output - click
    trace = report['startupTrace']
    marks = {m['phase']: m for m in trace['marks']}
    quantum = spec['quantum']
    armed = report['realtime']['armedContextFrame']
    startup_callbacks = report['realtime']['startupCallbacks']
    missing = armed - clock['startup_frame'] - startup_callbacks * quantum
    lead = report.get('silentLead')
    expected_lead = quanta > 0
    checks = {'button_and_clock': type(click) is int and type(first_output) is int and elapsed > 0,
              'cold_dictionary_and_context': trace['dictionaryState'] == 'cold' and not trace['parallelRegistration']
              and marks['context_start']['contextFrame'] is None,
              'startup_missing_frames': missing >= 0 and missing % quantum == 0
              and (missing == 0) == (clock['startup_discontinuities'] == 0),
              'app_option_matches_requested': (lead is not None) == expected_lead}
    result = {'click_epoch_ms': click, 'first_output_epoch_ms': first_output, 'click_to_first_output_ms': elapsed,
              'missing_frames_before_song': missing}
    if expected_lead and lead is not None:
        frames = lead['frames']
        ready = lead['readyContextFrame']
        checks['configured_input_quanta_before_voice'] = (lead['quantum'] == quantum
            and len(frames) == quanta and frames == list(range(ready - quantum * quanta, ready, quantum))
            and ready % quantum == 0 and clock['startup_frame'] >= ready)
        phases = [marks[name]['wallMs'] for name in ('worklet_module_ready', 'silent_lead_start',
                                                     'silent_lead_ready', 'node_start')]
        checks['lead_between_registration_and_voice'] = phases == sorted(phases)
        result.update(silent_lead=lead, silent_lead_prepare_ms=phases[2] - phases[1],
                      lead_first_quantum_to_song_frames=clock['start_frame'] - frames[0],
                      lead_ready_to_voice_frames=clock['startup_frame'] - ready)
        first_valid = lead['firstValidInputFrame']
        unobserved = ready - first_valid - quantum * lead['validInputQuanta']
        checks['valid_input_clock'] = (first_valid % quantum == 0 and first_valid <= frames[0]
                                      and lead['validInputQuanta'] >= quanta and unobserved >= 0)
        result['lead_frames_without_valid_input'] = unobserved
        planner, fixed_start, fixed_ready, lead_start, lead_ready, connect, notified = (
            marks[name]['wallMs'] for name in ('planner_ready', 'worklet_module_start', 'worklet_module_ready',
                'silent_lead_module_start', 'silent_lead_module_ready', 'silent_lead_connect', 'silent_lead_ready'))
        join = max(fixed_ready, lead_ready)
        fixed_order = fixed_start <= fixed_ready <= planner if trace.get('registerBeforeResume') else planner <= fixed_start <= fixed_ready
        checks['lead_registration_order'] = (fixed_order and planner <= lead_start and fixed_start <= lead_start <= lead_ready
            and ((lead_start < fixed_ready) if parallel else (lead_start >= fixed_ready))
            and join <= connect <= notified)
        result['registration'] = {'fixed_ms': fixed_ready - fixed_start, 'lead_ms': lead_ready - lead_start,
                                  'joint_wait_ms': join - fixed_start,
                                  'overlap_ms': max(0, min(fixed_ready, lead_ready) - lead_start),
                                  'connect_to_notification_ms': notified - connect}
    return checks, result


def compare_resume_registration(report, mode):
    trace = report['startupTrace']
    marks = {mark['phase']: mark for mark in trace['marks']}
    created, start, ready, initial, resumed, planner = (marks[name] for name in (
        'context_created', 'worklet_module_start', 'worklet_module_ready', 'resume_start', 'resume_ready', 'planner_ready'))
    if mode == 'suspended':
        stopped = marks['suspend_before_registration_ready']
        order = [created, stopped, start, ready, initial, resumed, planner]
        states_match = all(mark['contextState'] == 'suspended' for mark in (stopped, start, ready, initial))
    else:
        order = [created, initial, resumed, planner, start, ready]
        states_match = all(mark['contextState'] == 'running' for mark in (resumed, start, ready))
    times = [mark['wallMs'] for mark in order]
    checks = {'resume_registration_flag': trace['registerBeforeResume'] == (mode == 'suspended'),
              'resume_registration_order_and_state': times == sorted(times) and states_match and resumed['contextState'] == 'running'}
    node = marks['node_start']['wallMs']
    result = {'worklet_registration_frames': [start['contextFrame'], ready['contextFrame']],
              'worklet_registration_states': [start['contextState'], ready['contextState']],
              'resume_request_frames': initial['contextFrame'],
              'context_created_to_resume_request_ms': initial['wallMs'] - created['wallMs'],
              'resume_request_to_ready_ms': resumed['wallMs'] - initial['wallMs'],
              'resume_ready_to_voice_node_ms': node - resumed['wallMs'],
              'planner_ready_to_voice_node_ms': node - planner['wallMs']}
    if 'silent_lead_connect' in marks:
        result['resume_ready_to_lead_connection_ms'] = marks['silent_lead_connect']['wallMs'] - resumed['wallMs']
    return checks, result


def compare_lead_input_trace(startup, quantum, quanta):
    lead = startup['silent_lead']
    trace = lead['inputTrace']
    values = trace['values']
    width = len(LEAD_TRACE_COLUMNS)
    if (trace['columns'] != LEAD_TRACE_COLUMNS or trace['omittedCallbacks'] or not values
            or len(values) % width or len(values) > 128 * width
            or any(type(value) is not int or value < 0 for value in values)):
        raise ValueError('先行入力の全コールバックを採取できませんでした')
    rows = [values[offset:offset + width] for offset in range(0, len(values), width)]
    frames = [row[0] for row in rows]
    first_valid = lead['firstValidInputFrame']
    ready = lead['readyContextFrame']
    if frames != sorted(set(frames)) or any(frame % quantum for frame in frames) or frames[-1] + quantum != ready:
        raise ValueError('先行入力の絶対フレーム列が昇順の描画量子に揃いません')
    valid_frames = [frame for frame, output, channels, length, nonzero in rows
                    if output == length == quantum and channels > 0 and nonzero == 0]
    first_ready = next((last + quantum for first, last in zip(valid_frames, valid_frames[quanta - 1:])
                        if last - first == (quanta - 1) * quantum), None)
    expected_frames = set(range(first_valid, ready, quantum))
    missing = sorted(expected_frames.difference(frames))
    invalid = sorted(expected_frames.intersection(frames).difference(valid_frames))
    checks = {'lead_trace_matches_notifications': (bool(valid_frames) and valid_frames[0] == first_valid
              and len(valid_frames) == lead['validInputQuanta']
              and valid_frames[-quanta:] == lead['frames'] and first_ready == ready),
              'lead_trace_accounts_for_missing_input': (
                  (len(missing) + len(invalid)) * quantum == startup['lead_frames_without_valid_input'])}
    return checks, {'callbacks': len(rows), 'before_first_valid_frames': [frame for frame in frames if frame < first_valid],
                    'missing_callback_frames': missing, 'invalid_input_frames': invalid,
                    'missing_callback_samples': len(missing) * quantum, 'invalid_input_samples': len(invalid) * quantum}


def complete_pairs(rows, order):
    for number, pair_order in enumerate(order, 1):
        group = {r['mode']: r for r in rows if r['pair'] == number and 'error' not in r}
        if set(group) == set(pair_order):
            yield number, group


def contrast(rows, checks, order):
    pairs = []
    for number, group in complete_pairs(rows, order):
        pair_order = list(group)
        elapsed = {mode: group[mode]['click_to_first_output_ms'] for mode in pair_order}
        missing = {mode: group[mode]['missing_frames_before_song'] for mode in pair_order}
        pairs.append({'pair': number, 'click_to_first_output_ms': elapsed, 'missing_frames_before_song': missing,
                      'silent_minus_ordinary_ms': elapsed['silent'] - elapsed['ordinary']})
    complete = len(pairs) == len(order)
    delta = median(row['silent_minus_ordinary_ms'] for row in pairs) if pairs else None
    total_missing = {mode: sum(row['missing_frames_before_song'][mode] for row in pairs)
                     for mode in ('ordinary', 'silent')}
    predictions = {'silent_startup_from_first_quantum': complete and all(
        r['clock']['first_quantum_to_start_as_predicted'] and r['missing_frames_before_song'] == 0
        for r in rows if r['mode'] == 'silent' and 'error' not in r),
        'silent_reduces_total_startup_gaps': complete and total_missing['silent'] < total_missing['ordinary'],
        'pcm_states_and_plan_identical': complete and all(checks[f'{r["trial"]}/{key}'] for r in rows for key in (
            'all_pcm_matches_offline', 'all_sampled_states_and_plan_match_offline'))}
    return predictions, {'pairs': pairs, 'median_silent_minus_ordinary_ms': delta, 'missing_frames_total': total_missing}


def preserved_startup(rows, checks, complete):
    return {'both_start_from_first_quantum': complete and all(
        r['clock']['first_quantum_to_start_as_predicted'] and r['missing_frames_before_song'] == 0 for r in rows),
        'pcm_states_and_plan_identical': complete and all(checks[f'{r["trial"]}/{key}'] for r in rows for key in (
            'all_pcm_matches_offline', 'all_sampled_states_and_plan_match_offline'))}


def contrast_registration(rows, checks, order):
    pairs = []
    for number, group in complete_pairs(rows, order):
        elapsed = {mode: entry['click_to_first_output_ms'] for mode, entry in group.items()}
        registration = {mode: entry['registration']['joint_wait_ms'] for mode, entry in group.items()}
        pairs.append({'pair': number, 'click_to_first_output_ms': elapsed, 'registration_ms': registration,
                      'parallel_minus_serial_ms': elapsed['parallel'] - elapsed['serial'],
                      'registration_parallel_minus_serial_ms': registration['parallel'] - registration['serial']})
    predictions = preserved_startup(rows, checks, len(pairs) == len(order))
    effects = {'pairs': pairs}
    for metric in ('parallel_minus_serial_ms', 'registration_parallel_minus_serial_ms'):
        effects[f'median_{metric}'] = median(row[metric] for row in pairs) if pairs else None
    return predictions, effects


def contrast_duration(rows, checks, order, quanta, quantum, tolerance):
    pairs = []
    expected = (quanta['eight'] - quanta['four']) * quantum
    for number, group in complete_pairs(rows, order):
        elapsed = {mode: entry['click_to_first_output_ms'] for mode, entry in group.items()}
        frames = {mode: entry['lead_first_quantum_to_song_frames'] for mode, entry in group.items()}
        lead_wait = {mode: entry['registration']['connect_to_notification_ms'] for mode, entry in group.items()}
        pairs.append({'pair': number, 'click_to_first_output_ms': elapsed, 'silent_lead_wait_ms': lead_wait,
                      'lead_first_quantum_to_song_frames': frames,
                      'four_minus_eight_ms': elapsed['four'] - elapsed['eight'],
                      'clock_reduction_frames': frames['eight'] - frames['four']})
    complete = len(pairs) == len(order)
    predictions = preserved_startup(rows, checks, complete)
    predictions['clock_reduction_within_one_quantum'] = complete and all(
        abs(pair['clock_reduction_frames'] - expected) <= tolerance * quantum for pair in pairs)
    return predictions, {'pairs': pairs, 'expected_clock_reduction_frames': expected,
                         'median_four_minus_eight_ms': median(p['four_minus_eight_ms'] for p in pairs) if pairs else None}


def contrast_resume_registration(rows, checks, order, quantum):
    pairs = []
    for number, group in complete_pairs(rows, order):
        elapsed = {mode: row['click_to_first_output_ms'] for mode, row in group.items()}
        steps = {mode: row['native_trace']['steps'][0] for mode, row in group.items()}
        pairs.append({'pair': number, 'click_to_first_output_ms': elapsed,
                      'suspended_minus_running_ms': elapsed['suspended'] - elapsed['running'],
                      'first_native_steps': steps})
    complete = len(pairs) == len(order)
    predictions = preserved_startup(rows, checks, complete)
    predictions['suspended_lead_clock_contiguous'] = complete and all(
        step['frame_step'] == quantum for row in rows if row['mode'] == 'suspended' for step in row['native_trace']['steps'])
    predictions['running_reproduces_label_gap'] = complete and any(
        step['frame_step'] > quantum and step['same_request'] and step['graph_quanta_between'] == 0
        for pair in pairs for step in (pair['first_native_steps']['running'],))
    return predictions, {'pairs': pairs, 'median_suspended_minus_running_ms':
                         median(pair['suspended_minus_running_ms'] for pair in pairs) if pairs else None}


def contrast_preregistered_lead_presence(rows, checks, order):
    _, effects = contrast(rows, checks, order)
    stage_deltas = []
    for pair, (_, group) in zip(effects['pairs'], complete_pairs(rows, order), strict=True):
        stage_ms = {mode: row['resume_registration']['planner_ready_to_voice_node_ms']
                    for mode, row in group.items()}
        delta = stage_ms['silent'] - stage_ms['ordinary']
        pair.update(planner_ready_to_voice_node_ms=stage_ms, silent_minus_ordinary_planner_to_node_ms=delta)
        stage_deltas.append(delta)
    effects['median_silent_minus_ordinary_planner_to_node_ms'] = median(stage_deltas) if stage_deltas else None
    return preserved_startup(rows, checks, len(stage_deltas) == len(order)), effects


def measure(study, spec, fixed, fixed_path, live, offline, upper, wasm, artifacts, execute, bun):
    execute([*bun, 'run', 'build'], cwd=song.WEB, stdout=artifacts / 'browser-build.log')
    copied = artifacts / 'vocal_wasm.wasm'
    shutil.copyfile(song.WORKSPACE / song.wasm.WASM, copied)
    binary = sha256(copied)
    dictionaries = {True: sha256(song.DICTIONARY),
                    False: song.bytes_digest(gzip.decompress(song.DICTIONARY.read_bytes())).hexdigest()}
    upper_pcm = np.fromfile(upper, dtype='<f4')
    checks = {'wasm_matches_offline': binary == sha256(wasm),
              'dictionary_matches_upstream': dictionaries[True] == sha256(song.UPSTREAM_DICTIONARY)}
    order = study['condition_order']
    engine = study.get('browser_engine', 'chromium')
    duration_quanta = study.get('lead_quanta_by_mode')
    trace_lead = study.get('trace_silent_lead_input', False)
    native_spec = study.get('native_trace')
    resume_order_quanta = study.get('resume_order_lead_quanta')
    compare_presence = study.get('compare_silent_lead_presence', False)
    compare_registration = 'app_reference_run' in study and duration_quanta is None
    trials, effects, predictions = [], {}, {}
    for route in study['routes']:
        rows = []
        for number, pair_order in enumerate(order, 1):
            for mode in pair_order:
                label = f'{route}-{number}-{mode}'
                folder = artifacts / label
                options = {'single_song_capture': True, 'skip_invalid_lyrics': True,
                           'trace_startup': True, 'record_click_epoch': True}
                quanta = 0 if mode == 'ordinary' else study['silent_lead_quanta']
                if resume_order_quanta is not None:
                    quanta = 0 if mode == 'ordinary' else resume_order_quanta
                    options['register_before_resume'] = compare_presence or mode == 'suspended'
                elif duration_quanta is not None:
                    quanta = duration_quanta[mode]
                if quanta:
                    options['silent_lead_quanta'] = quanta
                    if trace_lead:
                        options['trace_silent_lead_input'] = True
                if native_spec:
                    options['native_silent_lead_trace_categories'] = native_spec['categories']
                if mode == 'parallel':
                    options['parallel_silent_lead_registration'] = True
                if route == 'observed':
                    options['output_probe'] = {'quantum': spec['quantum'], 'captureQuanta': spec['output_probe_quanta']}
                    if study.get('hold_output_probe_connections'):
                        options['output_probe']['holdConnectionsThroughTail'] = True
                row = {'trial': label, 'route': route, 'pair': number, 'mode': mode}
                local = {}
                trace_path = folder / 'trace.json'
                try:
                    browser, report, rate, pcm = realtime.cross.capture(
                        folder, engine, live, offline['input.json'], '...', execute, options=options, case_path=fixed_path)
                    local, result, reference = realtime.compare(browser, report, rate, pcm, folder, offline, fixed,
                                                                upper_pcm, dictionaries, binary, spec, engine=engine)
                    row.update(result)
                    clock = result['clock']
                    startup_checks, startup = compare_startup(browser, report, clock, quanta, spec, mode == 'parallel')
                    local.update(startup_checks)
                    row.update(startup)
                    if resume_order_quanta is not None:
                        registration_mode = 'suspended' if options['register_before_resume'] else 'running'
                        order_checks, row['resume_registration'] = compare_resume_registration(report, registration_mode)
                        local.update(order_checks)
                    if compare_presence and not quanta:
                        local['no_silent_lead_startup_marks'] = all(not mark['phase'].startswith('silent_lead_')
                            for mark in report['startupTrace']['marks'])
                    if trace_lead:
                        trace_checks, row['lead_input_trace'] = compare_lead_input_trace(startup, spec['quantum'], quanta)
                        local.update(trace_checks)
                    if native_spec:
                        native_checks, row['native_trace'] = native_trace.inspect_trace(
                            trace_path, browser, report, native_spec, spec['quantum'])
                        local.update(native_checks)
                    if route == 'observed':
                        probe_checks, probe = realtime.compare_output_probe(folder, clock, reference, spec)
                        local.update(probe_checks)
                        gaps = [g for g in probe['gaps'] if clock['startup_frame'] <= g['after_frame'] < clock['start_frame']]
                        local['independent_missing_frames'] = (sum(g['missing_frames'] for g in gaps)
                                                               == startup['missing_frames_before_song'])
                        row['output_probe'] = probe
                        if study.get('hold_output_probe_connections'):
                            deferred = READ(folder / 'output-probe.json')['deferredDisconnects']
                            local['probe_keeps_worklet_connections_through_tail'] = deferred == (2 if quanta else 1)
                            probe['deferred_disconnects'] = deferred
                except (OSError, KeyError, TypeError, ValueError, subprocess.CalledProcessError) as error:
                    row['error'] = str(error)
                    local['capture_and_comparison_completed'] = False
                finally:
                    if native_spec and trace_path.is_file():
                        compress(trace_path)
                checks.update({f'{label}/{key}': passed for key, passed in local.items()})
                rows.append(row)
        if compare_presence:
            route_predictions, effects[route] = contrast_preregistered_lead_presence(rows, checks, order)
        elif resume_order_quanta is not None:
            route_predictions, effects[route] = contrast_resume_registration(rows, checks, order, spec['quantum'])
        elif duration_quanta is not None:
            route_predictions, effects[route] = contrast_duration(rows, checks, order, duration_quanta,
                spec['quantum'], study['maximum_clock_error_quanta'])
        else:
            compare = contrast_registration if compare_registration else contrast
            route_predictions, effects[route] = compare(rows, checks, order)
        predictions.update({f'{route}/{name}': passed for name, passed in route_predictions.items()})
        trials.extend(rows)
    primary = effects['direct']
    complete = len(primary['pairs']) == len(order)
    if compare_presence:
        predictions['direct/omitting_lead_shortens_click_time'] = (
            complete and primary['median_silent_minus_ordinary_ms'] > 0)
        predictions['direct/omitting_lead_shortens_planner_to_node'] = (
            complete and primary['median_silent_minus_ordinary_planner_to_node_ms'] > 0)
    elif duration_quanta is not None:
        if not native_spec and resume_order_quanta is None:
            predictions['direct/click_time_shortens'] = complete and primary['median_four_minus_eight_ms'] < 0
    elif compare_registration:
        predictions['direct/registration_window_shortens'] = (
            complete and primary['median_registration_parallel_minus_serial_ms'] < 0)
        predictions['direct/click_time_shortens'] = complete and primary['median_parallel_minus_serial_ms'] < 0
    else:
        predictions['direct/silent_adds_click_time'] = complete and primary['median_silent_minus_ordinary_ms'] > 0
    result = {'checks': checks, 'predictions': predictions, 'effects': effects, 'trials': trials}
    if trace_lead:
        traces = [row['lead_input_trace'] for row in trials if 'lead_input_trace' in row]
        with_gaps = [trace for trace in traces if trace['missing_callback_frames'] or trace['invalid_input_frames']]
        reproduced = any(trace['missing_callback_samples'] + trace['invalid_input_samples'] == 256 for trace in with_gaps)
        if resume_order_quanta is None:
            predictions['trace_reproduces_256_frame_gap'] = reproduced
            predictions['trace_gaps_are_missing_callbacks'] = (reproduced and len(traces) == len(trials)
                                                               and all(not trace['invalid_input_frames'] for trace in traces))
        result['lead_input_trace'] = {'captured_trials': len(traces), 'trials_with_gaps': len(with_gaps),
                                      'missing_callback_samples': sum(t['missing_callback_samples'] for t in traces),
                                      'invalid_input_samples': sum(t['invalid_input_samples'] for t in traces)}
    if native_spec:
        aligned = [row['native_trace'] for row in trials if 'native_trace' in row]
        steps = [step for trace in aligned for step in trace['steps'] if step['frame_step'] > spec['quantum']]
        expected = [step for step in steps if step['frame_step'] == 3 * spec['quantum']]
        supports = [step for step in expected if step['graph_frames_between'] == 2 * spec['quantum']
                    and step['graph_quanta_between'] == 2 and step['author_calls_between'] == 0]
        adjacent = [step for step in steps if step['graph_quanta_between'] == 0 and step['author_calls_between'] == 0]
        if resume_order_quanta is None:
            predictions['native_graph_renders_without_worklet_in_gap'] = (
                bool(expected) and len(supports) == len(expected) and len(aligned) == len(trials))
        result['native_trace'] = {'aligned_trials': len(aligned), 'frame_gaps': len(steps),
                                  'gaps_matching_graph_only_prediction': len(supports),
                                  'gaps_between_adjacent_renders': len(adjacent)}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('--case', type=Path, default=CASE)
    args = parser.parse_args()
    case_path = args.case.resolve(strict=True)
    study = READ(case_path)
    cases = CASE.parent
    app_inputs = []
    compare_presence = study.get('compare_silent_lead_presence', False)
    if compare_presence and ('resume_order_lead_quanta' not in study or 'duration_study' not in study
                             or 'native_trace' in study or study.get('trace_silent_lead_input')):
        parser.error('無音先行の有無の比較では再開前登録を固定し、先行枝の専用トレースを省きます')
    if 'native_trace' in study:
        reference_path = cases / study['input_trace_study']
        reference_case = READ(reference_path)
        previous = song.run_manifest(study['input_trace_reference_run'], reference_case['id'], study['upstream_revision'])
        previous_summary = song.verified_path(previous, 'summary.json')
        if (study.get('browser_engine') != 'chromium' or not study.get('trace_silent_lead_input')
                or previous[1]['status'] != 'pass' or not READ(previous_summary)['predictions']['trace_gaps_are_missing_callbacks']):
            parser.error('無音先行の入力トレースの保存基準が揃いません')
        app_inputs.extend([reference_path, previous[0] / 'manifest.json', previous_summary])
    if 'resume_order_lead_quanta' in study:
        resume_reference_path = cases / study['resume_order_reference_study']
        resume_reference = READ(resume_reference_path)
        reference = song.run_manifest(study['resume_order_reference_run'], resume_reference['id'], study['upstream_revision'])
        summary_path = song.verified_path(reference, 'summary.json')
        summary = READ(summary_path)
        if compare_presence and resume_reference.get('compare_silent_lead_presence'):
            settings = ('duration_study', 'resume_order_lead_quanta', 'condition_order', 'hold_output_probe_connections')
            matches = (all(resume_reference[key] == study[key] for key in settings)
                       and len(summary['trials']) == 4 * len(study['condition_order'])
                       and all(summary['predictions'].get(f'{route}/{prediction}')
                               for route in ('direct', 'observed')
                               for prediction in ('both_start_from_first_quantum', 'pcm_states_and_plan_identical')))
        elif compare_presence:
            matches = (resume_reference.get('resume_order_lead_quanta') == study['resume_order_lead_quanta']
                       and resume_reference.get('browser_engine') == study.get('browser_engine')
                       and all(summary['predictions'].get(f'{route}/suspended_lead_clock_contiguous')
                               for route in ('direct', 'observed')))
        else:
            matches = summary['native_trace']['gaps_between_adjacent_renders'] > 0
        if reference[1]['status'] != 'pass' or not matches:
            parser.error('Worklet登録順の保存基準を照合できません')
        app_inputs.extend([resume_reference_path, reference[0] / 'manifest.json', summary_path])
    if 'duration_study' in study:
        duration_path = cases / study['duration_study']
        duration_case = READ(duration_path)
        if duration_case['upstream_revision'] != study['upstream_revision']:
            parser.error('無音先行の量子数を比較した保存基準が一致しません')
        app_inputs.append(duration_path)
        for run_id in study['chromium_reference_runs']:
            chromium = song.run_manifest(run_id, duration_case['id'], study['upstream_revision'])
            chromium_summary = song.verified_path(chromium, 'summary.json')
            trials = READ(chromium_summary)['trials']
            if (chromium[1]['status'] != 'pass' or len(trials) != len(duration_case['condition_order']) * 4
                    or not all(trial['browser']['engine'] == 'chromium'
                               and trial['offline_pcm']['first_bit_difference_frame'] is None for trial in trials)):
                parser.error('Chromiumの歌唱PCMの保存基準が揃いません')
            app_inputs.extend([chromium[0] / 'manifest.json', chromium_summary])
        study = {**duration_case, **study}
    modes = ['ordinary', 'silent']
    if 'app_study' in study:
        app_path = cases / study['app_study']
        app_case = READ(app_path)
        app = song.run_manifest(study['app_reference_run'], app_case['id'], study['upstream_revision'])
        if app_case['upstream_revision'] != study['upstream_revision'] or app[1]['status'] != 'pass':
            parser.error('直列の無音先行の保存基準が揃いません')
        app_inputs.extend([app_path, app[0] / 'manifest.json', song.verified_path(app, 'summary.json')])
        for run_id in study.get('previous_runs', []):
            prior_capture = song.run_manifest(run_id, study['id'], study['upstream_revision'])
            app_inputs.extend([prior_capture[0] / 'manifest.json', song.verified_path(prior_capture, 'summary.json')])
        study = {**app_case, **study}
        modes = ['parallel', 'serial']
    if 'lead_quanta_by_mode' in study:
        registration_path = cases / study['registration_study']
        registration_case = READ(registration_path)
        registration = song.run_manifest(study['registration_reference_run'], registration_case['id'], study['upstream_revision'])
        registration_result = song.verified_path(registration, 'summary.json')
        registration_summary = READ(registration_result)
        if (study['lead_quanta_by_mode'] != {'eight': study['silent_lead_quanta'], 'four': 4}
                or registration[1]['status'] != 'pass' or not registration_case['hold_output_probe_connections']
                or not any(row['mode'] == 'serial' and row['clock']['first_quantum_to_start_as_predicted']
                           for row in registration_summary['trials'])):
            parser.error('無音先行の登録順または量子数の保存基準が揃いません')
        app_inputs.extend([registration_path, registration[0] / 'manifest.json', registration_result])
        modes = ['eight', 'four']
    if 'resume_order_lead_quanta' in study:
        if study['resume_order_lead_quanta'] not in study['lead_quanta_by_mode'].values():
            parser.error('無音先行の量子数が基準と一致しません')
        modes = ['ordinary', 'silent'] if compare_presence else ['running', 'suspended']
    realtime_path = cases / study['realtime_study']
    prior_path = cases / study['lead_study']
    realtime_case, prior_case = READ(realtime_path), READ(prior_path)
    offline_path = cases / realtime_case['offline_study']
    offline_case = READ(offline_path)
    fixed_path = cases / offline_case['capture_case']
    live_path = cases / realtime_case['live_case']
    fixed, live = READ(fixed_path), READ(live_path)
    revision = study['upstream_revision']
    spec = realtime_case['measurement']
    if (any(c['upstream_revision'] != revision for c in (realtime_case, prior_case, offline_case, fixed, live))
            or study.get('browser_engine', 'chromium') not in ('chromium', 'firefox')
            or study['silent_lead_quanta'] != prior_case['marker_pcm_overrides']['short']['ready_quanta']
            or any(sorted(pair) != modes for pair in study['condition_order'])
            or subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=song.UPSTREAM, text=True).strip() != revision
            or subprocess.check_output(['git', 'status', '--porcelain'], cwd=song.UPSTREAM, text=True)):
        parser.error('固定上流または比較条件が一致しません')
    prior = song.run_manifest(study['lead_reference_run'], prior_case['id'], revision)
    offline = song.run_manifest(realtime_case['offline_run'], offline_case['id'], revision)
    upstream = song.run_manifest(offline_case['reference_run'], 'song-voice-fast-constriction-source', revision)
    if any(run[1]['status'] != 'pass' for run in (prior, offline, upstream)):
        parser.error('先行試験、オフライン、または固定上流の保存基準が揃いません')
    label = study['offline_condition']
    reference = {name: song.verified_path(offline, f'artifacts/{label}/{name}') for name in (
        'input.json', 'browser.wav', 'browser.json', 'browser-case.json')}
    upper = song.verified_path(upstream, 'artifacts/upstream-pcm.f32')
    wasm = song.verified_path(offline, 'artifacts/vocal_wasm.wasm')
    bun = ['bun'] if shutil.which('bun') else ['npx', '--offline', '--yes', '--package=bun@1.4.4', '--', 'bun']
    metadata = {'case_id': study['id'], 'upstream_revision': revision, 'turbulence_seed': offline_case['noise_seed'],
                'browser_engine': study.get('browser_engine', 'chromium'),
                'analysis_directory': str(Path.cwd()), 'analysis_command': [sys.executable, *sys.argv],
                'node': subprocess.check_output(['node', '--version'], text=True).strip(),
                'bun': subprocess.check_output([*bun, '--version'], text=True).strip()}
    if 'acquisition_revision' in study:
        metadata['acquisition_revision'] = study['acquisition_revision']
    if metadata['browser_engine'] == 'firefox' and os.environ.get('CHIMERA_FIREFOX'):
        metadata['browser_executable'] = os.environ['CHIMERA_FIREFOX']
    inputs = [case_path, *app_inputs, realtime_path, prior_path, offline_path, fixed_path, live_path, Path(__file__).resolve(),
              upper, wasm, song.verified_path(prior, 'summary.json'), *reference.values(),
              *(r[0] / 'manifest.json' for r in (prior, offline, upstream)),
              *song.web_sources(), *song.shared.candidate_sources(), *(Path(module.__file__) for module in (
                  realtime, realtime.cross, song, song.wasm, song.shared, song.realtime))]
    if 'native_trace' in study:
        inputs.extend([Path(native_trace.__file__), CASE.parent.parent / 'tools/measure_lip_crossing_thickness.py'])
    return song.shared.record_measurement(args.run_id, case_path, inputs, metadata,
        lambda artifacts, execute: measure(study, spec, fixed, fixed_path, live, reference, upper, wasm,
                                           artifacts, execute, bun), command=None, input_root=song.ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
