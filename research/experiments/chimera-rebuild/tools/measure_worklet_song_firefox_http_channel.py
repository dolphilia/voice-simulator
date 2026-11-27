"""歌唱WorkletのHTTPチャネルをFirefoxの親子プロセス間で照合する。"""

import argparse
import gzip
import io
import json
import os
from pathlib import Path
import re
import shutil
from statistics import median
import subprocess
import sys
from urllib.parse import urlsplit

import numpy as np
from scipy.io import wavfile

import measure_worklet_song_firefox_registration_native as registration


song = registration.song
CASE = song.WORKSPACE / 'cases/worklet-song-firefox-http-channel.json'
INPUTS = ('browser-run.json', 'browser.json.gz', 'browser.wav.gz', 'firefox-profile.json.gz')
REFERENCE = ('summary.json', 'artifacts/1-chromium/browser.json.gz', 'artifacts/reference/pcm-128.wav',
             'artifacts/reference/upstream-pcm.f32.gz', 'artifacts/vocal_wasm.wasm')
TRANSACTION_CLOCK = ('requestStart', 'responseStart', 'responseEnd')
FLOW_MARKERS = ('nsHttpChannel::BeginConnect', 'nsHttpChannel::OnCacheEntryAvailable', 'nsHttpChannel::OnStopRequest',
                'nsHttpChannel::OnStartRequest')
URL_MARKERS = ('Receive AsyncOpen in Parent', 'ProcessNewTransaction', 'DispatchTransaction')


def only(values, label):
    matches = list(values)
    if len(matches) != 1:
        raise ValueError(f'{label} の一致数は {len(matches)} 件です')
    return matches[0]


def main_thread(profile):
    return only((t for t in profile['threads'] if t['name'] == 'GeckoMain'), 'GeckoMain')


def network(records, path):
    return [row for row in records if row[4].get('type') == 'Network'
            and urlsplit(row[4].get('URI') or '').path == path]


def endpoints(rows):
    return tuple(only((x for x in rows if x[4]['status'] == name), name) for name in ('STATUS_START', 'STATUS_STOP'))


def ipc_messages(parent, child, channel_id, offset, times, spec):
    info = {'profile_has_ipc': False, 'continue_async_open': [], 'constructor_candidates': [], 'IPC': []}
    opened, parent_received, parent_stop, child_stop = times
    ids = {main_thread(p)['pid'] for p in (parent, child)}
    events = []
    stop_logs = []
    for process in (parent, child):
        for thread in process['threads']:
            for name, start, _, _, payload in registration.markers(thread):
                if payload.get('type') == 'IPC' and payload.get('otherPid') in ids:
                    info['profile_has_ipc'] = True
                    if payload.get('messageType') in ('PNecko::Msg_PHttpChannelConstructor', 'PHttpBackgroundChannel::Msg_OnStopRequest'):
                        events.append({'pid': thread['pid'], 'thread': thread['name'],
                                       'time_ms': start + (offset if process is child else 0),
                                       **{k: payload[k] for k in ('messageSeqno', 'messageType', 'side', 'direction', 'phase', 'otherPid')}})
                if process is child and name == 'nsHttp' and payload.get('type') == 'Log':
                    msg = payload.get('message')
                    message = thread['stringTable'][msg] if type(msg) is int else str(msg)
                    opening = re.search(rf'HttpChannelChild::ContinueAsyncOpen this=(\S+) gid={channel_id}\b', message)
                    stopping = re.search(r'HttpChannelChild::ProcessOnStopRequest \[this=([^\s,\]]+)[,\]]', message)
                    if opening:
                        info['continue_async_open'].append({'pid': thread['pid'], 'thread': thread['name'],
                                                           'time_ms': start + offset, 'channel_object': opening[1]})
                    if stopping:
                        stop_logs.append({'pid': thread['pid'], 'thread': thread['name'],
                                          'time_ms': start + offset, 'channel_object': stopping[1]})
    logs = info['continue_async_open']
    if len(logs) != 1:
        return info
    log = logs[0]
    logged = log['time_ms']
    distance = spec['maximum_constructor_marker_distance_ms']
    found = [row for row in events if row['side'] == 'child' and row['phase'] == 'endpoint'
             and row['direction'] == 'sending' and row['thread'] == log['thread'] and row['pid'] == log['pid']
             and row['messageType'] == 'PNecko::Msg_PHttpChannelConstructor'
             and logged <= row['time_ms'] <= min(parent_received, logged + distance)]
    info['constructor_candidates'] = found

    def related(match):
        return sorted((e for e in events if e['messageSeqno'] == match['messageSeqno']
                       and e['messageType'] == match['messageType'] and {e['pid'], e['otherPid']} == ids),
                      key=lambda e: e['time_ms'])

    if len(found) == 1:
        info['IPC'] = related(found[0])
        info['timing_ms'] = {'child_http_open_to_constructor_send': found[0]['time_ms'] - opened}
        receivers = [e for e in info['IPC'] if e['direction'] == 'receiving']
        transfer = [e for e in receivers if e['phase'] == 'transferEnd']
        endpoint = [e for e in receivers if e['phase'] == 'endpoint' and e['side'] == 'parent']
        if len(transfer) == len(endpoint) == 1 and found[0]['time_ms'] <= transfer[0]['time_ms'] <= endpoint[0]['time_ms'] <= parent_received:
            info['timing_ms'].update({'constructor_send_to_peer_transfer_end': transfer[0]['time_ms'] - found[0]['time_ms'],
                                      'peer_transfer_end_to_parent_handler': endpoint[0]['time_ms'] - transfer[0]['time_ms'],
                                      'parent_handler_to_http_receive': parent_received - endpoint[0]['time_ms']})
    matching_stop_logs = [row for row in stop_logs if row['channel_object'] == log['channel_object']
                          and parent_stop <= row['time_ms'] <= child_stop]
    info['process_stop'] = matching_stop_logs
    if len(matching_stop_logs) == 1:
        stopped = matching_stop_logs[0]
        matches = [e for e in events if e['messageType'] == 'PHttpBackgroundChannel::Msg_OnStopRequest'
                   and e['direction'] == 'receiving' and e['phase'] == 'endpoint' and e['side'] == 'child'
                   and e['pid'] == stopped['pid'] and e['thread'] == stopped['thread']
                   and 0 <= stopped['time_ms'] - e['time_ms'] <= distance]
        info['stop_candidates'] = matches
        if len(matches) == 1:
            info['stop_IPC'] = related(matches[0])
            info['stop_timing_ms'] = {'parent_stop_marker_to_child_ipc_handler': matches[0]['time_ms'] - parent_stop,
                                      'child_ipc_handler_to_process_stop': stopped['time_ms'] - matches[0]['time_ms'],
                                      'child_process_stop_to_child_stop_marker': child_stop - stopped['time_ms']}
    return info


def compare_channel(profile, request, spec):
    entry = request['path']
    parent = list(registration.markers(main_thread(profile)))
    child_process, child_network = only(((p, hits) for p in registration.processes(profile) if p is not profile
                                         and (hits := network(registration.markers(main_thread(p)), entry))),
                                        '対象チャネルがあるコンテンツプロセス')
    parent_start, parent_stop = endpoints(network(parent, entry))
    child_start, child_stop = endpoints(child_network)
    channel_id, uri, window = (parent_stop[4][key] for key in ('id', 'URI', 'innerWindowID'))
    if (not all((m[4]['id'], m[4]['URI'], m[4]['innerWindowID']) == (channel_id, uri, window)
                for m in (parent_start, child_start, child_stop))
            or any(m[4]['responseStatus'] != 200 or m[4]['requestStatus'] != 'NS_OK' for m in (parent_stop, child_stop))):
        raise ValueError('親子の成功したHTTPチャネルが一致しません')
    offsets = {name: parent_stop[4][name] - child_stop[4][name] for name in TRANSACTION_CLOCK}
    offset = median(offsets.values())
    origin_offset = child_process['meta']['startTime'] - profile['meta']['startTime']
    clocks_ok = (max(abs(offset - value) for value in offsets.values()) <= spec['maximum_shared_timing_residual_ms']
                 and abs(offset - origin_offset) <= spec['maximum_profile_origin_error_ms'])

    url_stages = {name: only((r for r in parent if r[0] == name and r[4].get('channelId') == channel_id
                              and r[4].get('url') == uri), name) for name in URL_MARKERS}
    flow = only((r for r in parent if r[0] == 'nsHttpChannel::AsyncOpenFinal'
                 and abs(r[1] - parent_start[2]) <= spec['maximum_async_open_flow_difference_ms']), '親チャネルのフロー')
    flow_id = flow[4]['flow']
    channel_flows = {name: only((r for r in parent if r[0] == name and r[4].get('flow') == flow_id), name)
                     for name in FLOW_MARKERS}
    received, process, dispatch = (url_stages[name] for name in URL_MARKERS)
    began_connect, cache_available, stop = (channel_flows[name] for name in (
        'nsHttpChannel::BeginConnect', 'nsHttpChannel::OnCacheEntryAvailable', 'nsHttpChannel::OnStopRequest'))
    c_open, p_open, tcp_request, tcp_end, p_stop, c_stop = (
        child_start[2] + offset, parent_start[2], parent_stop[4]['requestStart'], parent_stop[4]['responseEnd'],
        parent_stop[2], child_stop[2] + offset)
    ordered = (c_open <= received[1] <= p_open <= began_connect[1] <= began_connect[2] <= cache_available[1]
               <= process[1] <= dispatch[2] <= tcp_request <= tcp_end <= stop[1] <= p_stop <= stop[2]
               and p_stop <= c_stop)
    before = {'child_open_to_parent_receive_ms': received[1] - c_open, 'parent_receive_to_open_ms': p_open - received[1],
              'parent_open_to_begin_connect_ms': began_connect[1] - p_open,
              'parent_begin_connect_duration_ms': began_connect[2] - began_connect[1],
              'parent_begin_connect_end_to_cache_callback_ms': cache_available[1] - began_connect[2],
              'cache_callback_to_transaction_processing_ms': process[1] - cache_available[1],
              'transaction_processing_to_dispatch_end_ms': dispatch[2] - process[1],
              'dispatched_to_request_start_ms': tcp_request - dispatch[2]}
    after = {'response_end_to_parent_stop_entry_ms': stop[1] - tcp_end, 'parent_stop_entry_to_marker_ms': p_stop - stop[1],
             'parent_to_child_stop_markers_ms': c_stop - p_stop}
    raw = {**url_stages, **channel_flows, 'parent_async_open_final': flow,
           'nsHttpChannel::OnDataAvailable': [row for row in parent if row[0] == 'nsHttpChannel::OnDataAvailable'
                                             and row[4].get('flow') == flow_id],
           'parent_start': parent_start, 'parent_stop': parent_stop, 'child_start': child_start, 'child_stop': child_stop}
    ipc = ipc_messages(profile, child_process, channel_id, offset, (c_open, received[1], p_stop, c_stop),
                       spec['additional_capture'])
    result = {'channel_id': channel_id, 'uri': uri, 'parent_flow': flow_id, 'parent_clock_offset_ms': offset,
              'parent_clock_offset_from_origins_ms': origin_offset, 'shared_offsets_ms': offsets, 'raw_markers': raw,
              'before_send_ms': before, 'after_receive_ms': after, 'ipc_constructor': ipc}
    long = spec['long_wait_ms']
    return {'browser_clocks_align': clocks_ok, 'channel_markers_in_order': ordered}, {
        **result, 'long_before_send': tcp_request - c_open >= long, 'long_after_receive': c_stop - tcp_end >= long,
        'largest_before_send_interval': max(before, key=before.get), 'largest_after_receive_interval': max(after, key=after.get),
        'parent_before_and_after_boundary_prediction': max(before['child_open_to_parent_receive_ms'],
            after['parent_to_child_stop_markers_ms']) <= spec['expected_parent_open_and_stop_boundary_ms']}


def analyze_trial(paths, key, order, reference_data, spec):
    run, report, pcm, profile = (paths[name] for name in INPUTS)
    run = song.wasm.read_json(run)
    report = json.loads(gzip.decompress(report.read_bytes()))
    rate, audio = wavfile.read(io.BytesIO(gzip.decompress(pcm.read_bytes())))
    with gzip.open(profile, 'rt') as stream:
        profile = json.load(stream)
    request = only(run['workletRequests'], 'ローカルHTTPの要求')
    fixed, live, baseline, expected, dictionary, binary_hash, upstream, tolerance, planned_beats = reference_data
    checks, comparison = registration.evaluation.registration.checks_for_capture(run, report, rate, audio,
        engine='firefox', baseline=baseline, limits=fixed['measurement'], live=live['measurement'],
        expected=expected, dictionary=dictionary, binary_hash=binary_hash, upstream=upstream, tolerance=tolerance,
        planned_beats=planned_beats, rejection='音符に割り当てる歌詞の音節がありません')
    checks['server_response_ok'] = request['status'] == 200
    native_checks, channel = compare_channel(profile, request, spec)
    checks.update(native_checks)
    return {'trial': key, 'order': order, 'upstream_pcm': comparison, 'checks': checks, 'channel': channel}


def measure(study, fixed, live, source, reference, archive, artifacts, execute, bun):
    spec = study['measurement']
    config = song.wasm.read_json(source)
    baseline = json.loads(gzip.decompress(reference['artifacts/1-chromium/browser.json.gz'].read_bytes()))
    rate, pcm = wavfile.read(reference['artifacts/reference/pcm-128.wav'])
    saved = song.wasm.read_json(reference['summary.json'])
    expected = registration.cross.signature(baseline, pcm)
    if expected != saved['trials'][0]['hashes']:
        raise ValueError('固定したCLIのPCMとブラウザの観測を照合できません')
    upper = np.frombuffer(gzip.decompress(reference['artifacts/reference/upstream-pcm.f32.gz'].read_bytes()), dtype='<f4')
    score = config['song_voice']['score']
    beats = np.r_[0, np.cumsum([note['beats'] for note in score['notes'][:-1]])]
    planned = np.rint((score['start_seconds'] + beats * 60 / score['bpm']) * rate).astype(int).tolist()
    reference_data = (fixed, live, baseline, expected, saved['trials'][0]['dictionary_sha256'],
                      song.sha256(reference['artifacts/vocal_wasm.wasm']), upper, config['measurement']['pcm_absolute_tolerance'], planned)
    evidence = list(archive)
    checks = {}
    if bun is not None:
        capture_case = song.wasm.read_json(registration.CASE)
        capture = spec['additional_capture']
        capture_case['measurement']['condition_order'] = capture['condition_order']
        capture_case['measurement']['profiler_features'].append(capture['profiler_feature'])
        fresh = artifacts / 'fresh'
        fresh.mkdir()

        def with_logging(command, cwd=song.WORKSPACE, stdout=None):
            if command[:2] == ['env', 'MOZ_PROFILER_STARTUP=1']:
                command = ['env', 'MOZ_LOG=' + capture['log_modules'], *command[1:]]
            return execute(command, cwd=cwd, stdout=stdout)

        captured = registration.measure(capture_case, fixed, live, source, reference, fresh, with_logging, bun)
        (fresh / 'capture-summary.json').write_text(json.dumps(captured, indent=2, ensure_ascii=False) + '\n')
        checks.update({f'capture/{key}': value for key, value in captured['checks'].items()})
        evidence.extend((f"fresh/{t['trial']}", t['order'], {name: fresh / t['trial'] / name for name in INPUTS})
                        for t in captured['trials'])
    trials = []
    for key, order, paths in evidence:
        try:
            result = analyze_trial(paths, key, order, reference_data, spec)
        except (OSError, EOFError, KeyError, TypeError, ValueError) as error:
            result = {'trial': key, 'order': order, 'error': str(error), 'checks': {'analyzed': False}}
        checks.update({f'{key}/{name}': value for name, value in result['checks'].items()})
        trials.append(result)
    return {'checks': checks, 'reference_hashes': expected, 'trials': trials}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('--fresh-ipc', action='store_true', help='IPCとHTTPログを有効にし、同じ画面から4試行を追加採取する')
    parser.add_argument('--include-ipc-run', action='append', default=[], help='追加計測の保存プロファイルも再解析する')
    args = parser.parse_args()
    study, fixed, live = (song.wasm.read_json(p) for p in (CASE, song.CASE, song.LIVE_CASE))
    source = song.WORKSPACE / 'cases' / fixed['song_voice_case']
    revision = study['upstream_revision']
    if (any(case['upstream_revision'] != revision for case in (fixed, live))
            or subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=song.UPSTREAM, text=True).strip() != revision
            or subprocess.check_output(['git', 'status', '--porcelain'], cwd=song.UPSTREAM, text=True)):
        parser.error('固定上流または歌唱のケースが一致しません')
    prior = song.run_manifest(study['reference_run'], registration.cross.CASE.stem, revision)
    if prior[1]['status'] != 'pass':
        parser.error('歌唱の基準実行が合格条件を満たしません')
    reference = {name: song.verified_path(prior, name) for name in REFERENCE}
    inputs = [CASE, registration.CASE, song.CASE, song.LIVE_CASE, source, prior[0] / 'manifest.json',
              *reference.values(), Path(__file__).resolve(), Path(registration.__file__)]
    inputs.extend(Path(module.__file__) for module in (song, song.shared, song.wasm, registration.cross, registration.native,
        registration.evaluation, registration.evaluation.registration, registration.evaluation.registration.startup,
        registration.cross.clocks, registration.cross.clocks.release.stored))
    archive = []
    for id_ in study['profile_runs']:
        run = song.run_manifest(id_, registration.CASE.stem, revision)
        summary = song.verified_path(run, 'summary.json')
        if run[1]['reference_run'] != prior[0].name:
            parser.error(f'{id_} の歌唱の基準が一致しません')
        inputs.extend((run[0] / 'manifest.json', summary))
        for trial in song.wasm.read_json(summary)['trials']:
            label = trial['trial']
            files = {name: song.verified_path(run, f'artifacts/{label}/{name}') for name in INPUTS}
            inputs.extend(files.values())
            archive.append((f'{id_}/{label}', trial['order'], files))
    if len(archive) != 18 or len({key for key, _, _ in archive}) != len(archive):
        parser.error('事前登録した18試行を一意に照合できません')
    for ipc_id in dict.fromkeys(args.include_ipc_run):
        run = song.run_manifest(ipc_id, CASE.stem, revision)
        captured = song.verified_path(run, 'artifacts/fresh/capture-summary.json')
        if not run[1]['fresh_ipc'] or run[1]['reference_run'] != prior[0].name:
            parser.error('追加のIPC計測が現在の基準と一致しません')
        inputs.extend((run[0] / 'manifest.json', captured))
        for t in song.wasm.read_json(captured)['trials']:
            label = t['trial']
            files = {name: song.verified_path(run, f'artifacts/fresh/{label}/{name}') for name in INPUTS}
            inputs.extend(files.values())
            archive.append((f'{ipc_id}/{label}', t['order'], files))
    bun = None
    if args.fresh_ipc:
        bun = ['bun'] if shutil.which('bun') else ['npx', '--offline', '--yes', '--package=bun@1.4.4', '--', 'bun']
        inputs.extend([*song.web_sources(), *song.shared.candidate_sources()])
    details = {'case_id': study['id'], 'upstream_revision': revision, 'reference_run': prior[0].name,
               'profile_runs': study['profile_runs'], 'fresh_ipc': args.fresh_ipc,
               'included_ipc_runs': args.include_ipc_run,
               'analysis_command': [sys.executable, *sys.argv], 'analysis_directory': str(Path.cwd()),
               'firefox_override': os.environ.get('CHIMERA_FIREFOX') if args.fresh_ipc else None}
    return song.shared.record_measurement(args.run_id, CASE, inputs, details,
        lambda artifacts, execute: measure(study, fixed, live, source, reference, archive, artifacts, execute, bun),
        command=None, input_root=song.ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
