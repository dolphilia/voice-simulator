"""FirefoxのWorklet登録に、画面とHTTPの時計を重ねる。"""

import argparse
import gzip
import json
from pathlib import Path
import shutil
import subprocess
from urllib.parse import urlsplit

import numpy as np
from scipy.io import wavfile

import measure_worklet_firefox_native_clock as native
import measure_worklet_live_song_cross_browser as cross
import measure_worklet_song as song
import measure_worklet_song_module_evaluation as evaluation


CASE = song.WORKSPACE / 'cases/worklet-song-firefox-registration-native.json'
ANCHORS = ('worklet_module_start', 'worklet_module_ready', 'worklet_ready_received')
REGISTER = 'AudioWorkletGlobalScope::RegisterProcessor'
CONTROL = 'AudioNodeTrack::SendRunnable'
FETCH_TASKS = ('Worklet::StartModuleLoadRunnable', 'Worklet::StartFetchRunnable', 'Worklet::FetchCompleteRunnable')
ORDERS = ('serial', 'parallel')


def markers(thread):
    table = thread['markers']
    schema = table['schema']
    names = thread['stringTable']
    data = schema['data']
    for row in table['data']:
        yield (names[row[schema['name']]], row[schema['startTime']], row[schema['endTime']],
               row[schema['phase']], (row[data] or {}) if data < len(row) else {})


def processes(profile):
    yield profile
    for child in profile.get('processes', ()):
        yield from processes(child)


def find_anchors(profile):
    for process in processes(profile):
        for thread in process['threads']:
            if thread['name'] != 'GeckoMain':
                continue
            groups = {phase: [] for phase in ANCHORS}
            for name, start, _, phase, payload in markers(thread):
                label = payload.get('name', '')
                key = label.removeprefix('chimera:') if name == 'UserTiming' and isinstance(label, str) else ''
                if phase == 0 and label != key and key in groups:
                    groups[key].append(start)
            if any(groups.values()):
                yield process, thread, groups


def fetch_evidence(profile, content, entry, lower, upper):
    named = []
    network = []
    for process in processes(profile):
        for thread in process['threads']:
            for name, start, end, phase, payload in markers(thread):
                task = payload.get('name', name)
                in_window = process is content and (task in FETCH_TASKS or name in FETCH_TASKS) and (
                    any(t is not None and lower <= t <= upper for t in (start, end)))
                matching_url = payload.get('type') == 'Network' and urlsplit(payload.get('URI', '') or '').path == entry
                if not (in_window or matching_url):
                    continue
                row = {'pid': thread['pid'], 'thread': thread['name'], 'content_process': process is content,
                       'process_type': process['meta']['processType'], 'marker': name, 'phase': phase,
                       'start_ms': start, 'end_ms': end, 'process_start_epoch_ms': process['meta']['startTime'],
                       'payload': payload}
                if in_window:
                    named.append({**row, 'task': task})
                if matching_url:
                    network.append(row)
    return {'named_tasks': named, 'target_network_markers': network}


def content_network_timing(rows, event_times, native_begin, registration_control, tolerance):
    active = [row for row in rows if row['content_process'] and row['thread'] == 'GeckoMain']
    start = [row for row in active if row['payload']['status'] == 'STATUS_START']
    stop = [row for row in active if row['payload']['status'] == 'STATUS_STOP']
    if len(start) != 1 or len(stop) != 1 or stop[0]['payload'].get('id') != start[0]['payload'].get('id'):
        return None
    start, stop = start[0], stop[0]
    data = stop['payload']
    if not {'requestStart', 'responseEnd'} <= data.keys():
        return None
    opened, requested, response_end, content_stop = start['end_ms'], data['requestStart'], data['responseEnd'], stop['end_ms']
    if not native_begin <= opened <= requested <= response_end <= content_stop or data.get('responseStatus') != 200:
        return None
    request_error = event_times['http_request_received'] - requested
    response_error = response_end - event_times['http_response_sent']
    return {'add_module_to_channel_open_ms': opened - native_begin,
            'channel_open_to_request_start_ms': requested - opened,
            'request_to_response_end_ms': response_end - requested,
            'response_end_to_content_stop_ms': content_stop - response_end,
            'content_stop_to_register_control_ms': registration_control - content_stop if registration_control is not None else None,
            'content_stop_to_first_statement_ms': event_times['worklet_first_statement'] - content_stop,
            'request_start_to_server_ms': request_error, 'server_send_to_response_end_ms': response_error,
            'http_clocks_fit': abs(request_error) <= tolerance and abs(response_error) <= tolerance}


def align_profile(profile, report, request, tolerance):
    candidates = list(find_anchors(profile))
    result = {'anchor_threads': [{'pid': thread['pid'], 'counts': {k: len(v) for k, v in groups.items()}}
                                 for _, thread, groups in candidates]}
    if len(candidates) != 1 or any(len(v) != 1 for v in candidates[0][2].values()):
        return result
    content, main, groups = candidates[0]
    begin, ready, received = (groups[name][0] for name in ANCHORS)
    marks = {mark['phase']: mark for mark in report['startupTrace']['marks']}
    origin = marks[ANCHORS[0]]
    offset = begin - origin['epochMs']
    clock_mismatches = {
        name: {'wall_ms': (groups[name][0] - begin) - (marks[name]['wallMs'] - origin['wallMs']),
               'epoch_ms': (groups[name][0] - begin) - (marks[name]['epochMs'] - origin['epochMs'])}
        for name in ANCHORS}
    intervals, _ = native.thread_intervals(main, 'AudioWorklet.addModule')
    registration = [pair for pair in intervals if abs(pair[0] - begin) <= tolerance
                    and abs(pair[1] - ready) <= tolerance]
    result.update({'anchor_clock_error_ms': clock_mismatches, 'native_add_module_intervals_ms': intervals,
                   'aligned_add_module_intervals': len(registration)})
    if len(registration) != 1:
        return result
    native_begin, native_ready = registration[0]
    module = report['workletModuleTiming']
    event_times = {
        'main_add_module': begin, 'main_promise_resumed': ready, 'main_ready_received': received,
        'http_request_received': request['startedAtEpochMs'] + offset,
        'http_response_sent': request['finishedAtEpochMs'] + offset,
        'worklet_first_statement': module['evaluationStartedAtEpochMs'] + offset,
        'js_register_call': module['registrationStartedAtEpochMs'] + offset,
        'js_register_return': module['registeredAtEpochMs'] + offset,
    }
    registers = []
    controls = []
    for thread in content['threads']:
        register_intervals, _ = native.thread_intervals(thread, REGISTER)
        registers.extend((thread, start, end) for start, end in register_intervals
                         if native_begin <= start <= end <= native_ready)
        if thread['name'] == 'GraphRunner':
            control_intervals, _ = native.thread_intervals(thread, CONTROL)
            controls.extend((thread['tid'], start, end) for start, end in control_intervals if native_begin <= start <= native_ready)
    result.update({'events_content_ms': event_times,
                   'native_register_processor_intervals': [{'tid': t['tid'], 'thread': t['name'], 'interval_ms': [start, end]}
                                                          for t, start, end in registers],
                   'graph_control_intervals': [{'tid': tid, 'interval_ms': [start, end]} for tid, start, end in controls],
                   'profile': {**{k: profile['meta'].get(k) for k in ('appBuildID', 'version', 'platform')},
                               'content_start_epoch_ms': content['meta']['startTime'],
                               'content_epoch_minus_anchor_epoch_origin_ms': content['meta']['startTime'] + offset},
                   **fetch_evidence(profile, content, request['path'], native_begin - tolerance, native_ready + tolerance)})
    if len(registers) != 1:
        return result
    graph, register_start, register_end = registers[0]
    evaluation_start = event_times['worklet_first_statement']
    register_errors = [register_start - event_times['js_register_call'], register_end - event_times['js_register_return']]
    containing = [item for item in result['graph_control_intervals'] if item['tid'] == graph['tid']
                  and item['interval_ms'][0] <= register_start <= register_end <= item['interval_ms'][1]]
    registration_control = containing[0]['interval_ms'][0] if len(containing) == 1 else None
    result.update({
        'clocks_fit': (begin < ready <= received and native_begin <= register_start <= register_end <= native_ready
                       and graph['name'] == 'GraphRunner' and evaluation_start <= register_start + tolerance
                       and all(abs(error) <= tolerance for group in clock_mismatches.values() for error in group.values())
                       and all(abs(error) <= tolerance for error in register_errors)),
        'register_clock_error_ms': register_errors,
        'add_module_boundary_error_ms': [native_begin - begin, ready - native_ready],
        'native_registration_ms': native_ready - native_begin,
        'estimated_fraction_before_first_statement': (evaluation_start - native_begin) / (native_ready - native_begin),
        'minimum_fraction_before_first_statement': (evaluation_start - tolerance - native_begin) / (native_ready - native_begin),
        'native_register_processor_ms': register_end - register_start,
        'native_register_end_to_promise_ms': native_ready - register_end,
        'controls_containing_registration': containing,
        'content_network_timing': content_network_timing(result['target_network_markers'], event_times,
                                                        native_begin, registration_control, tolerance),
    })
    return result


def measure(study, fixed, live, source, reference, artifacts, execute, bun):
    spec = study['measurement']
    execute([*bun, 'run', 'build'], cwd=song.WEB, stdout=artifacts / 'browser-build.log')
    binary = artifacts / 'vocal_wasm.wasm'
    shutil.copyfile(song.WORKSPACE / song.wasm.WASM, binary)
    binary_hash = song.sha256(binary)
    bundle, = (song.WEB / 'dist/assets').glob('fixed-processor-measured-entry-*.js')
    shutil.copyfile(bundle, artifacts / bundle.name)
    execute(['cargo', 'test', '--locked', '-p', 'chimera', *[a for n in song.song.SUITES for a in ('--test', n)]],
            cwd=song.UPSTREAM, stdout=artifacts / 'upstream-tests.log')
    stored = song.wasm.read_json(reference['summary.json'])
    baseline = json.loads(gzip.decompress(reference['artifacts/1-chromium/browser.json.gz'].read_bytes()))
    rate, pcm = wavfile.read(reference['artifacts/reference/pcm-128.wav'])
    upstream = np.frombuffer(gzip.decompress(reference['artifacts/reference/upstream-pcm.f32.gz'].read_bytes()), dtype='<f4')
    expected = cross.signature(baseline, pcm)
    if rate != fixed['measurement']['output_rate_hz'] or expected != stored['trials'][0]['hashes']:
        raise ValueError('保存済みのブラウザとCLIのPCMを照合できません')
    config = song.wasm.read_json(source)
    score = config['song_voice']['score']
    beats = np.r_[0, np.cumsum([note['beats'] for note in score['notes'][:-1]])]
    planned_beats = np.rint((score['start_seconds'] + beats * 60 / score['bpm']) * rate).astype(int).tolist()
    checks = {'same_wasm_as_reference': binary_hash == song.sha256(reference['artifacts/vocal_wasm.wasm'])}
    trials = []
    reg = evaluation.registration
    for i, orders in enumerate(spec['condition_order'], 1):
        for order in orders:
            label = f'{i}-{order}'
            folder = artifacts / label
            result = {'trial': label, 'order': order}
            local = {}
            try:
                run, report, got_rate, audio = cross.capture(folder, 'firefox', live, source, spec['unrenderable_lyrics'],
                    execute, spec, options={'trace_startup': True, 'trace_evaluation': True, 'trace_native_registration': True,
                    'observe_worklet_evaluation': True, 'single_song_capture': True, 'parallel_registration': order == 'parallel'})
                result['browser'] = run['version']
                local, result['upstream_pcm'] = reg.checks_for_capture(run, report, got_rate, audio,
                    engine='firefox', baseline=baseline, limits=fixed['measurement'], live=live['measurement'],
                    expected=expected, dictionary=stored['trials'][0]['dictionary_sha256'], binary_hash=binary_hash,
                    upstream=upstream, tolerance=config['measurement']['pcm_absolute_tolerance'],
                    planned_beats=planned_beats, rejection=spec['rejection_contains'])
                trace = report['startupTrace']
                rows = [mark for mark in trace['marks'] if mark['phase'] != ANCHORS[-1]]
                timing = reg.timing({**report, 'startupTrace': {**trace, 'marks': rows}}, order == 'parallel')
                requests = run['workletRequests']
                local['expected_bundle'] = (len(requests) == 1 and requests[0]['path'] == '/assets/' + bundle.name
                                            and requests[0]['status'] == 200)
                if local['expected_bundle']:
                    tolerance = spec['clock_tolerance_ms']
                    observed = evaluation.evaluation_timing(report, requests[0], timing['registration_ms'], tolerance)
                    local['javascript_clocks_aligned'] = observed['clocks_fit']
                    result['startup'] = timing
                    result['evaluation'] = observed
                    profile = song.wasm.read_json(folder / 'firefox-profile.json')
                    measured = align_profile(profile, report, requests[0], tolerance)
                    result['native'] = measured
                    local['native_clocks_aligned'] = measured.get('clocks_fit', False)
                    if local['native_clocks_aligned'] and local['javascript_clocks_aligned']:
                        result['prediction_met'] = (measured['minimum_fraction_before_first_statement']
                                                    >= spec['before_evaluation_fraction'])
                        result['long_wait'] = {stage: observed[stage] >= spec['long_wait_ms']
                                               for stage in ('call_to_request_ms', 'response_to_first_statement_ms')}
            except (OSError, KeyError, ValueError, subprocess.CalledProcessError) as error:
                result['error'] = str(error)
                local['capture_and_comparison_completed'] = False
            checks.update({f'{label}/{name}': value for name, value in local.items()})
            trials.append(result)
            cross.clocks.compress_outputs(folder)
    return {'checks': checks, 'reference_hashes': expected, 'trials': trials}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    study, fixed = (song.wasm.read_json(path) for path in (CASE, song.CASE))
    live_path = song.WORKSPACE / 'cases' / study['live_case']
    live = song.wasm.read_json(live_path)
    source = song.WORKSPACE / 'cases' / fixed['song_voice_case']
    revision = study['upstream_revision']
    if (live_path != song.LIVE_CASE or live['song_case'] != song.CASE.name
            or any(item['upstream_revision'] != revision for item in (fixed, live))
            or subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=song.UPSTREAM, text=True).strip() != revision
            or subprocess.check_output(['git', 'status', '--porcelain'], cwd=song.UPSTREAM, text=True)):
        parser.error('固定上流と歌唱の登録が一致しません')
    prior = song.run_manifest(study['reference_run'], cross.CASE.stem, revision)
    prior_evaluation = song.run_manifest(study['evaluation_reference_run'], evaluation.CASE.stem, revision)
    reference = {name: song.verified_path(prior, name) for name in ('summary.json', 'artifacts/1-chromium/browser.json.gz',
                 'artifacts/reference/pcm-128.wav', 'artifacts/reference/upstream-pcm.f32.gz', 'artifacts/vocal_wasm.wasm')}
    prior_timing = song.verified_path(prior_evaluation, 'summary.json')
    if any(run[1]['status'] != 'pass' for run in (prior, prior_evaluation)) or prior_evaluation[1]['reference_run'] != prior[0].name:
        parser.error('歌唱と評価時刻の基準実行が合格条件を満たしません')
    for path in (song.CASE, live_path, source):
        hashes = [item['sha256'] for item in prior[1]['inputs'] if item['path'].endswith('/' + path.name)]
        if hashes != [song.sha256(path)]:
            parser.error(f'保存済み歌唱の {path.name} と入力が一致しません')
    orders = study['measurement']['condition_order']
    if not orders or any(set(order) != set(ORDERS) or len(order) != len(ORDERS) for order in orders):
        parser.error('各ラウンドに現行順と並行登録が必要です')
    bun = ['bun'] if shutil.which('bun') else ['npx', '--offline', '--yes', '--package=bun@1.4.4', '--', 'bun']
    inputs = [CASE, live_path, song.CASE, source, prior[0] / 'manifest.json', prior_evaluation[0] / 'manifest.json',
              prior_timing, *reference.values(), *song.web_sources(), *song.shared.candidate_sources(), Path(__file__).resolve(),
              *(Path(module.__file__) for module in (native, song, cross, evaluation, evaluation.registration,
                 evaluation.registration.startup, cross.clocks, song.wasm, song.shared, cross.clocks.release.stored))]
    metadata = {'case_id': study['id'], 'upstream_revision': revision, 'reference_run': prior[0].name,
                'evaluation_reference_run': prior_evaluation[0].name,
                'node': subprocess.check_output(['node', '--version'], text=True).strip(),
                'bun': subprocess.check_output([*bun, '--version'], text=True).strip()}
    return song.shared.record_measurement(args.run_id, CASE, inputs, metadata,
        lambda artifacts, execute: measure(study, fixed, live, source, reference, artifacts, execute, bun),
        command=None, input_root=song.ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
