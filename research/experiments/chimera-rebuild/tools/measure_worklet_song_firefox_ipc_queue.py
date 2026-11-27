"""Workletモジュールを取得するIPCと親のタスク投入・実行を照合する。"""

import argparse
from collections import Counter
import gzip
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import measure_worklet_song_firefox_http_channel as http


registration = http.registration
song = http.song
CASE = song.WORKSPACE / 'cases/worklet-song-firefox-ipc-queue.json'
ADD_TASK = ('TaskController::AddTask', 'EventQueueInternal::PutEvent')
IPC_NAME = 'PNecko::Msg_PHttpChannelConstructor'


def read_profile(path):
    with gzip.open(path, 'rt') as stream:
        return json.load(stream)


def markers_on(profile, pid, name):
    thread = http.only((t for t in profile['threads'] if t['pid'] == pid and t['name'] == name), name)
    return thread, list(registration.markers(thread))


def flow_value(thread, payload, key):
    value = payload.get(key)
    return thread['stringTable'][value] if type(value) is int else value


def sampled_cpu(profile, thread, lower, upper):
    unit = profile['meta'].get('sampleUnits', {}).get('threadCPUDelta')
    scale = {'ns': 1_000_000, 'µs': 1000, 'ms': 1}.get(unit)
    if scale is None:
        return None
    table = thread['samples']
    schema = table['schema']
    if 'threadCPUDelta' not in schema:
        return None
    index = schema['threadCPUDelta']
    time_index = schema['time']
    pairs = []
    for previous, row in zip(table['data'], table['data'][1:]):
        start, end = previous[time_index], row[time_index]
        if len(row) > index and row[index] is not None and lower <= start < end <= upper:
            pairs.append((start, end, row[index] / scale))
    total = sum(end - start for start, end, _ in pairs)
    return {'unit': unit, 'interval_count': len(pairs), 'intervals_ms': pairs,
            'window_covered_ms': total, 'cpu_ms': sum(delta for _, _, delta in pairs) if pairs else None}


def activity(profile, thread, markers, lower, upper):
    marks = []
    opened = None
    for name, start, end, phase, data in markers:
        if name != 'Awake':
            continue
        if phase == 2:
            opened = start
        if phase == 3 and opened is not None:
            if opened < upper and end > lower:
                marks.append({'began_ms': opened, 'ended_ms': end, 'cpu_ms': data.get('CPU Time', data.get('cpuTime'))})
            opened = None
    if opened is not None and opened < upper:
        marks.append({'began_ms': opened, 'ended_ms': None, 'cpu_ms': None})
    clipped = [(max(lower, m['began_ms']), min(upper, m['ended_ms'] or upper)) for m in marks]
    inside = [m for m in marks if m['began_ms'] >= lower and m['ended_ms'] is not None and m['ended_ms'] <= upper
              and m['cpu_ms'] is not None]
    kinds = Counter(name for name, start, _, _, _ in markers if lower <= start <= upper and name not in ('IPC', 'Awake'))
    return {'awake_ms': sum(end - start for start, end in clipped), 'awake_markers': marks,
            'whole_awake_intervals_ms': sum(m['ended_ms'] - m['began_ms'] for m in inside),
            'whole_awake_cpu_ms': sum(m['cpu_ms'] for m in inside) if inside else None,
            'sampled_cpu': sampled_cpu(profile, thread, lower, upper), 'most_frequent_markers': kinds.most_common(12)}


def analyze(profile, channel, spec):
    events = channel['ipc_constructor']['IPC']
    arrived = http.only((e for e in events if e['direction'] == 'receiving' and e['phase'] == 'transferEnd'), '親IPCの受信')
    handled = http.only((e for e in events if e['direction'] == 'receiving' and e['phase'] == 'endpoint'
                         and e['side'] == 'parent'), '親IPCの実行')
    sent = http.only((e for e in events if e['direction'] == 'sending' and e['phase'] == 'endpoint'
                      and e['side'] == 'child'), '子IPCの送信')
    if (arrived['pid'] != handled['pid'] or arrived['pid'] != sent['otherPid'] or arrived['otherPid'] != sent['pid']
            or any(e['messageType'] != IPC_NAME or e['messageSeqno'] != sent['messageSeqno'] for e in events)
            or not sent['time_ms'] <= arrived['time_ms'] <= handled['time_ms']):
        raise ValueError('親子の作成IPCの順序または識別情報が不正です')
    lower, upper = arrived['time_ms'], handled['time_ms']
    main, parent_marks = markers_on(profile, arrived['pid'], handled['thread'])
    io_thread, io_marks = markers_on(profile, arrived['pid'], arrived['thread'])
    result = {'IPC_message': {'name': IPC_NAME, 'seqno': sent['messageSeqno'], 'child_pid': sent['pid'], 'parent_pid': handled['pid'],
                              'arrived_ms': lower, 'handled_ms': upper},
              'peer_transfer_end_to_parent_handler_ms': upper - lower,
              'long_wait': upper - lower >= spec['long_wait_ms'],
              'activity': activity(profile, main, parent_marks, lower, upper)}
    features = profile['meta']['configuration']['features']
    result['profile_features'] = features
    if 'flows' not in features:
        result['queue_evidence'] = 'プロファイルでIPCフローの収集が無効'
        return result
    content = http.only((p for p in registration.processes(profile) if p is not profile
                         and any(t['pid'] == sent['pid'] for t in p['threads'])), 'IPCを送信した子プロセス')
    child, child_marks = markers_on(content, sent['pid'], sent['thread'])
    offset = channel['parent_clock_offset_ms']
    send = [r for r in child_marks if r[0] == 'IPC' and r[4].get('type') == 'IPCFlowMarker' and r[4].get('name') == IPC_NAME
            and 0 <= sent['time_ms'] - (r[1] + offset) <= spec['maximum_send_flow_distance_ms']]
    result['child_flow_candidates'] = send
    if len(send) != 1:
        result['queue_evidence'] = '子側の送信フローを一意に対応できない'
        return result
    flow_id = flow_value(child, send[0][4], 'flow')
    receive = [r for r in io_marks if r[0] == 'IPCDispatch' and r[4].get('name') == IPC_NAME
               and flow_value(io_thread, r[4], 'flow') == flow_id]
    result['message_flow_id'] = flow_id
    result['parent_flow_candidates'] = receive
    if len(receive) != 1 or not lower <= receive[0][1] <= min(receive[0][2], upper):
        result['queue_evidence'] = '親側の投入フローを時刻順に一意に対応できない'
        return result
    _, begin, end, _, _ = receive[0]
    enqueued = [r for r in io_marks if r[0] in ADD_TASK and begin <= r[1] <= min(end, upper)]
    result['queue_candidates'] = enqueued
    result['io_to_dispatch_start_ms'] = begin - lower
    result['dispatch_duration_ms'] = end - begin
    if len(enqueued) != 1:
        result['queue_evidence'] = 'IPCDispatch内のタスク投入マーカーを一意に対応できない'
        return result
    task_flow = flow_value(io_thread, enqueued[0][4], 'flow')
    executed = [r for r in parent_marks if r[0] == 'Runnable' and flow_value(main, r[4], 'task') == task_flow and r[1] <= upper <= r[2]
                and r[1] >= enqueued[0][1]]
    posted = enqueued[0][1]
    after = upper - posted
    result.update({'queue_evidence': 'IPCフローとスレッドキューへの投入を対応', 'task_flow': task_flow,
                   'runnable_execution_candidates': executed, 'io_to_queue_ms': posted - lower, 'queue_to_handler_ms': after,
                   'post_enqueue_fraction': after / (upper - lower) if upper > lower else None})
    if result['long_wait']:
        result['prediction_met'] = (begin - lower <= spec['maximum_receive_to_dispatch_start_ms']
            and posted - lower <= spec['maximum_enqueue_delay_ms']
            and result['post_enqueue_fraction'] >= spec['minimum_post_enqueue_wait_fraction'])
    return result


def measure(study, fixed, live, source, reference, saved, artifacts, execute, bun):
    spec = study['measurement']
    capture_case = song.wasm.read_json(registration.CASE)
    capture_case['measurement']['condition_order'] = spec['condition_order']
    capture_case['measurement']['profiler_features'].extend(spec['profiler_features'])
    http_spec = song.wasm.read_json(http.CASE)['measurement']
    checks = {}
    trials = []
    for label, summary, path in saved:
        try:
            result = analyze(read_profile(path), summary['channel'], spec)
            checks[f'{label}/IPC_endpoints'] = True
            trials.append({'trial': label, 'order': summary['order'], 'queue': result})
        except (OSError, EOFError, KeyError, TypeError, ValueError) as error:
            checks[f'{label}/IPC_endpoints'] = False
            trials.append({'trial': label, 'order': summary['order'], 'error': str(error)})
    if bun is not None:
        fresh = artifacts / 'fresh'
        fresh.mkdir()

        def logging(command, cwd=song.WORKSPACE, stdout=None):
            if command[:2] == ['env', 'MOZ_PROFILER_STARTUP=1']:
                command = ['env', 'MOZ_LOG=' + spec['log_modules'], *command[1:]]
            return execute(command, cwd=cwd, stdout=stdout)

        captured = registration.measure(capture_case, fixed, live, source, reference, fresh, logging, bun)
        (fresh / 'capture-summary.json').write_text(json.dumps(captured, ensure_ascii=False, indent=2) + '\n')
        checks.update({f'capture/{key}': value for key, value in captured['checks'].items()})
        for t in captured['trials']:
            label = 'fresh/' + t['trial']
            folder = fresh / t['trial']
            try:
                profile = read_profile(folder / 'firefox-profile.json.gz')
                request = http.only(song.wasm.read_json(folder / 'browser-run.json')['workletRequests'], 'HTTP要求')
                channel_checks, channel = http.compare_channel(profile, request, http_spec)
                checks.update({f'{label}/{key}': value for key, value in channel_checks.items()})
                queue = analyze(profile, channel, spec)
                checks[f'{label}/IPC_endpoints'] = True
                trials.append({'trial': label, 'order': t['order'], 'channel': channel, 'queue': queue})
            except (OSError, EOFError, KeyError, TypeError, ValueError) as error:
                checks[f'{label}/IPC_endpoints'] = False
                trials.append({'trial': label, 'order': t['order'], 'error': str(error)})
    return {'checks': checks, 'trials': trials}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('--fresh', action='store_true', help='通常画面からIPCフロー付きで追加採取する')
    parser.add_argument('--include-queue-run', action='append', default=[], help='追加採取済みのプロファイルを再解析する')
    args = parser.parse_args()
    study, fixed, live = (song.wasm.read_json(p) for p in (CASE, song.CASE, song.LIVE_CASE))
    source = song.WORKSPACE / 'cases' / fixed['song_voice_case']
    revision = study['upstream_revision']
    if (any(case['upstream_revision'] != revision for case in (fixed, live))
            or subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=song.UPSTREAM, text=True).strip() != revision
            or subprocess.check_output(['git', 'status', '--porcelain'], cwd=song.UPSTREAM, text=True)):
        parser.error('固定上流または歌唱のケースが一致しません')
    prior = song.run_manifest(study['reference_run'], registration.cross.CASE.stem, revision)
    compared = song.run_manifest(study['ipc_comparison_run'], http.CASE.stem, revision)
    if prior[1]['status'] != 'pass' or compared[1]['status'] != 'pass' or compared[1]['reference_run'] != prior[0].name:
        parser.error('音声またはHTTPの保存済み比較が合格条件を満たしません')
    reference = {name: song.verified_path(prior, name) for name in http.REFERENCE}
    compared_summary = song.verified_path(compared, 'summary.json')
    inputs = [CASE, registration.CASE, http.CASE, song.CASE, song.LIVE_CASE, source, prior[0] / 'manifest.json',
              compared[0] / 'manifest.json', compared_summary, *reference.values(), Path(__file__).resolve()]
    inputs.extend(Path(module.__file__) for module in (http, registration, song, song.shared, song.wasm, registration.cross,
        registration.native, registration.evaluation, registration.evaluation.registration, registration.evaluation.registration.startup,
        registration.cross.clocks, registration.cross.clocks.release.stored))
    runs = {key: song.run_manifest(key, http.CASE.stem, revision) for key in study['profile_runs']}
    inputs.extend(run[0] / 'manifest.json' for run in runs.values())
    saved = []
    for t in song.wasm.read_json(compared_summary)['trials']:
        prefix, label = t['trial'].split('/')
        if prefix in runs:
            if not all(t['checks'].values()):
                parser.error(f'{t["trial"]} の音声またはHTTP照合が不合格です')
            path = song.verified_path(runs[prefix], f'artifacts/fresh/{label}/firefox-profile.json.gz')
            saved.append((t['trial'], t, path))
            inputs.append(path)
    if len(saved) != 8 or len({label for label, _, _ in saved}) != len(saved):
        parser.error('保存済みの8試行を一意に照合できません')
    for queue_id in dict.fromkeys(args.include_queue_run):
        run = song.run_manifest(queue_id, CASE.stem, revision)
        if run[1]['reference_run'] != prior[0].name:
            parser.error(f'{queue_id} の歌唱の基準が一致しません')
        run_summary = song.verified_path(run, 'summary.json')
        subset = [t for t in song.wasm.read_json(run_summary)['trials'] if t['trial'].startswith('fresh/')]
        inputs.extend((run[0] / 'manifest.json', run_summary))
        for t in subset:
            if 'channel' not in t:
                parser.error(f'{t["trial"]} に検証済みのHTTPチャネルがありません')
            path = song.verified_path(run, f'artifacts/{t["trial"]}/firefox-profile.json.gz')
            saved.append((f'{run[0].name}/{t["trial"]}', t, path))
            inputs.append(path)
    bun = None
    if args.fresh:
        bun = ['bun'] if shutil.which('bun') else ['npx', '--offline', '--yes', '--package=bun@1.4.4', '--', 'bun']
        inputs.extend([*song.web_sources(), *song.shared.candidate_sources()])
    details = {'case_id': study['id'], 'upstream_revision': revision, 'reference_run': prior[0].name,
               'ipc_comparison_run': compared[0].name, 'analysis_command': [sys.executable, *sys.argv],
               'analysis_directory': str(Path.cwd()), 'firefox_override': os.environ.get('CHIMERA_FIREFOX') if args.fresh else None}
    return song.shared.record_measurement(args.run_id, CASE, inputs, details,
        lambda artifacts, execute: measure(study, fixed, live, source, reference, saved, artifacts, execute, bun),
        command=None, input_root=song.ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
