"""Chromiumの歌唱トレースで先行Workletのフレームと描画区間を照合する。"""

import json


def end(event):
    return event['ts'] + event['dur']


def contains(outer, event):
    return (outer['pid'] == event['pid'] and outer['tid'] == event['tid']
            and outer['ts'] <= event['ts'] and event['ts'] + event.get('dur', 0) <= end(outer))


def containing(events, event, name):
    matches = [outer for outer in events if contains(outer, event)]
    if len(matches) != 1:
        raise ValueError(f'Chromiumトレースで {name} の対応が一意になりません ({event["ts"]})')
    return matches[0]


def inspect_trace(path, browser, report, spec, quantum):
    events = json.loads(path.read_text())['traceEvents']
    prefix = spec['marker_prefix']
    markers = []
    for event in events:
        if event['name'] == 'TimeStamp' and event['ph'] == 'I':
            message = event.get('args', {}).get('data', {}).get('message', '')
            if message.startswith(prefix):
                markers.append((int(message.removeprefix(prefix)), event))
    markers.sort(key=lambda pair: pair[1]['ts'])
    lead = report['silentLead']['inputTrace']
    frames = lead['values'][::len(lead['columns'])]
    if not markers or [frame for frame, _ in markers] != frames:
        raise ValueError('先行Workletの記録とChromiumトレースのマーカーが一致しません')
    origin = markers[0][1]['ts']
    pid = markers[0][1]['pid']
    renderer = [event for event in events if event.get('pid') == pid]
    complete = [event for event in renderer if event['ph'] == 'X']
    by_name = {name: sorted((event for event in complete if event['name'] == name), key=lambda event: event['ts'])
               for name in (spec['graph_event'], spec['author_event'], spec['request_event'], spec['device_event'])}
    graph, author, requests, devices = (by_name[spec[key]] for key in
                                         ('graph_event', 'author_event', 'request_event', 'device_event'))
    if not devices:
        raise ValueError('レンダラーの音声出力イベントを取得できませんでした')

    anchors, links = [], []
    for frame, marker in markers:
        execution = containing(author, marker, 'Workletの作者コード実行')
        render = containing(graph, execution, 'グラフの描画')
        request = containing(requests, render, '描画要求')
        if render['args']['frames'] != quantum:
            raise ValueError(f'グラフの描画量子が {quantum} フレームと一致しません')
        anchors.append({'frame': frame, 'thread': marker['tid'], 'marker_us': marker['ts'] - origin,
                        'author_us': execution['ts'] - origin, 'graph_render_us': render['ts'] - origin,
                        'request_us': request['ts'] - origin,
                        'request_frames': request['args']['frames_requested'], 'render_frames': request['args']['frames_to_render'],
                        'request_playout_delay_ms': request['args']['playout_delay (ms)']})
        links.append((frame, render, request))

    steps = []
    for (left_frame, left, left_request), (right_frame, right, right_request) in zip(links, links[1:]):
        if right['ts'] < end(left):
            raise ValueError('先行Workletの描画区間が重なっています')
        between = [event for event in graph if end(left) <= event['ts'] < right['ts']]
        unmarked_author = [event for event in author if end(left) <= event['ts'] < right['ts']]
        step = right_frame - left_frame
        steps.append({'frames': [left_frame, right_frame], 'frame_step': step,
                      'graph_quanta_between': len(between), 'graph_frames_between': sum(r['args']['frames'] for r in between),
                      'author_calls_between': len(unmarked_author), 'same_request': left_request is right_request})

    preceding_switches = [event['ts'] for event in renderer
                           if event['name'] == 'AudioDestination::StartWithWorkletTaskRunner' and event['ph'] == 'X'
                           and event['ts'] <= origin]
    switch = max(preceding_switches) if preceding_switches else None
    first_render = links[0][1]
    prior_renders = sum(event['tid'] == first_render['tid'] and switch <= event['ts'] < first_render['ts']
                        for event in graph) if switch is not None else None
    phases = {row['phase']: row['contextFrame'] for row in report['startupTrace']['marks']}
    device_window = [event for event in devices
                     if end(event) >= links[0][2]['ts'] and event['ts'] <= end(links[-1][2])]
    checks = {'chromium_trace_without_loss': browser['traceDataLoss'] is False,
              'native_trace_alignment': bool(device_window) and all(marker['pid'] == pid for _, marker in markers)}
    detail = {'browser_engine': browser['browserEngine'], 'trace_events': len(events), 'renderer_pid': pid,
              'worklet_runner_started_us': switch - origin if switch is not None else None,
              'graph_renders_on_worklet_thread_before_first_marker': prior_renders,
              'registration_context_frame': phases['worklet_module_start'],
              'connection_context_frame': phases['silent_lead_connect'],
              'device_renders': [{'us': event['ts'] - origin, 'thread': event['tid'], 'frames': event['args']['frames']}
                                 for event in device_window],
              'anchors': anchors, 'steps': steps}
    return checks, detail
