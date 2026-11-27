"""CoreMIDIの仮想送信元から標準Web MIDIと手動発声までを照合する。"""

import argparse
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory

import numpy as np

from measure_glottal_pitch import independent_pitch
from measure_tsp_listening import hydrate_run
from measure_uniform_tube import candidate_sources, record_measurement
from measure_wasm_fixed import compare_pcm, read_json
from measure_worklet_fixed import ROOT, WEB, web_sources
from measure_worklet_midi import reference_controls
from measure_worklet_songbird import read_wave
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/worklet-midi-coremidi.json'
UNPLUG = WORKSPACE / 'cases/worklet-midi-coremidi-unplug.json'
SHARED_NOTE = WORKSPACE / 'cases/worklet-midi-coremidi-shared-note.json'
PASSIVE = WORKSPACE / 'cases/worklet-midi-coremidi-passive.json'
LIVE = WORKSPACE / 'cases/worklet-realtime-voice.json'
FIXED = WORKSPACE / 'cases/vowel-voice-i.json'
CAPTURE = WEB / 'tools/capture-midi-coremidi.mjs'
HELPER = WORKSPACE / 'tools/capture_coremidi_source.swift'
UPPER_TEST = UPSTREAM / 'tests/live-control.test.ts'


def route_checks(row, data, note_format, unplug):
    native = row['native']
    before = row.get('before', {})
    live = row.get('connected', {})
    disconnected = row.get('disconnected', {})
    note = data['note_on'][1]
    expected = [None, note, note, None, None] if note_format == 'number' else ['なし', str(note), str(note), 'なし', 'なし']
    packets = [data['note_on']] if unplug else [data['note_on'], data['note_off']]
    encoded = [((0x20 | data['group']) << 24) | int.from_bytes(bytes(msg), 'big') for msg in packets]
    sends = [entry for entry in native if entry['action'] == 'send']
    last_probe = disconnected or row.get('removed') or row.get('atError') or {}
    messages = last_probe.get('messages', [])
    ports = live.get('ports', [])
    native_times = [int(entry['timestampHostTicks']) for entry in sends]
    event_times = [msg['eventMs'] for msg in messages]
    return {
        'native_source_lifecycle': [entry['action'] for entry in native] == ['add', *['send'] * len(packets), 'remove']
        and native[0]['listed'] and not native[-1]['listed'] and native[0]['endpoint'] == native[-1]['endpoint']
        and row['helper'] == {'code': 0, 'stderr': ''},
        'native_ump_and_host_times': [entry['word'] for entry in sends] == encoded
        and all(next_time > time for time, next_time in zip([0, *native_times], native_times)),
        'standard_web_midi_and_hot_add': row.get('permission') == 'granted' and not before.get('ports') and before.get('requests') == [{
            'options': {'sysex': False}, 'outcome': 'granted', 'sysexEnabled': False, 'initialProbeInputs': 0,
        }] and bool(native) and len(ports) == 1 and ports[0]['name'] == native[0]['name'] and ports[0]['type'] == 'input'
        and ports[0]['connection'] == 'open' and ports[0]['state'] == 'connected'
        and any(p['trusted'] and p['id'] == ports[0]['id'] and p['state'] == 'connected' for p in live['topology']),
        'trusted_midi_bytes': [message['bytes'] for message in messages] == packets
        and bool(ports) and all(message['trusted'] and message['port']['id'] == ports[0]['id']
                                and message['handlerMs'] >= message['eventMs'] for message in messages)
        and all(next_time > time for time, next_time in zip([0, *event_times], event_times)),
        'app_held_sequence': [row.get(k, {}).get('note') for k in ('silent', 'on', 'held', 'off', 'released')] == expected,
        'app_listener_cleanup': live.get('subscriptions') == 1 and disconnected.get('subscriptions') == 0,
        'no_page_or_capture_errors': not row.get('error') and not row['pageErrors'],
    }


def unplug_observation(row, target):
    removed = row.get('removed', {})
    port = removed.get('removedInput')
    connected = row.get('connected', {}).get('ports', [])
    event = next((event for event in removed.get('topology', []) if event['state'] == 'disconnected'), None)
    off = row.get('off', {}).get('observedMs')
    gate_messages = row.get('output', {}).get('gateMessages', []) if row.get('output') else []
    upper_gate = next((event['observedMs'] for event in reversed(gate_messages) if event['level'] == 0), None)
    checks = {
        'trusted_removal_before_ui_release': bool(port and connected and event and event['trusted']
            and event['id'] == port['id'] == connected[0]['id'] and not event['inInputMap'] and not removed['ports']
            and off is not None and 0 < event['eventMs'] <= off),
        'removed_port_subscriptions': bool(port and removed['subscriptions'] == 0
            and (target == 'upstream' or port['propertyHandlerSet'] is False)),
    }
    if target == 'upstream':
        checks['removal_before_gate_target'] = bool(event and upper_gate is not None and event['eventMs'] <= upper_gate)
    return checks, {'event': event, 'removed_input': port, 'observed_ui_release_ms': off, 'observed_upper_gate_ms': upper_gate}


def shared_note_checks(row, source, config, target):
    shared = row.get('shared', {})
    first, second = row['native'], shared.get('native', [])
    packets = [source['note_on'], config['second_note_on']]
    sources = (first, second)
    ready = row.get('before', {})
    ports = row.get('connected', {}).get('ports', [])
    last = row.get('removed', {})
    middle = shared.get('firstRemoval', {})
    messages = last.get('messages', [])
    events = [event for event in last.get('topology', []) if event['state'] == 'disconnected']
    before = shared.get('afterFirstRemoval', {})
    after = shared.get('beforeLastRemoval', {})
    held_ms = after['observedMs'] - before['observedMs'] if before and after else None
    note = str(packets[0][1]) if target == 'candidate' else packets[0][1]
    empty = 'なし' if target == 'candidate' else None
    snapshots = (row.get('silent', {}), row.get('on', {}), shared.get('twoPressed', {}), row.get('held', {}),
                 before, after, row.get('off', {}), row.get('released', {}))
    native_ok = all([e['action'] for e in native] == ['add', 'send', 'remove']
        and native[0]['listed'] and not native[-1]['listed'] and native[0]['endpoint'] == native[-1]['endpoint']
        and native[1]['bytes'] == packet and native[1]['word'] == ((0x20 | source['group']) << 24
            | int.from_bytes(bytes(packet), 'big')) and int(native[1]['timestampHostTicks']) > 0
        for native, packet in zip(sources, packets, strict=True))
    ids = [port['id'] for port in ports]
    native_names = [native[0]['name'] for native in sources] if native_ok else []
    checks = {
        'two_native_sources': native_ok and first[0]['endpoint'] != second[0]['endpoint']
        and row.get('helper') == shared.get('helper') == {'code': 0, 'stderr': ''}
        and int(first[1]['beforeUptimeNs']) < int(second[1]['beforeUptimeNs'])
        < int(first[2]['beforeUptimeNs']) < int(second[2]['beforeUptimeNs']),
        'two_web_midi_inputs': row.get('permission') == 'granted' and not ready.get('ports')
        and ready.get('requests') == [{'options': {'sysex': False}, 'outcome': 'granted', 'sysexEnabled': False, 'initialProbeInputs': 0}]
        and len(set(ids)) == 2 and [port['name'] for port in ports] == native_names
        and all((port['state'], port['connection']) == ('connected', 'open') for port in ports),
        'two_trusted_presses': [m['bytes'] for m in messages] == packets and [m['port']['id'] for m in messages] == ids
        and all(m['trusted'] and m['eventMs'] > 0 for m in messages) and messages[0]['eventMs'] < messages[1]['eventMs'],
        'ordered_removal': len(ids) == 2 and [e['id'] for e in events] == ids and len(events) == 2
        and all(e['trusted'] and not e['inInputMap'] for e in events) and events[0]['eventMs'] < events[1]['eventMs']
        and [(port['id'], port['connection']) for port in middle.get('ports', [])] == [(ids[1], 'open')]
        and not last['ports'],
        'held_until_last_owner': all('note' in s for s in snapshots)
        and [s['note'] for s in snapshots] == [empty, note, note, note, note, note, empty, empty]
        and held_ms is not None and held_ms >= config['hold_after_first_removal_ms'],
        'subscription_counts': [p.get('subscriptions') for p in (row.get('connected', {}), middle, last)] == [2, 1, 0],
        'no_page_or_capture_errors': not row.get('error') and not row['pageErrors'],
    }
    return checks, {'input_order': ids, 'received_input_order': [m['port']['id'] for m in messages],
                    'removals': events, 'held_before_last_removal_ms': held_ms,
                    'notes': [s.get('note') for s in snapshots]}


def play_between_removals(row, config, measurement, events):
    first = row['shared']['afterFirstRemoval']
    before_last = row['shared']['beforeLastRemoval']
    window = config['upper_held_window_seconds']
    points = [point for point in row['output']['trace'] if window[0] <= point['clock'] - first['clock'] <= window[1]]
    gate_messages = [event for event in row['output']['gateMessages'] if event['observedMs'] >= row['silent']['observedMs']]
    levels = [event['level'] for event in gate_messages]
    checks = {
        'play_held_between_removals': first['gateTarget'] == before_last['gateTarget'] == 1 and bool(points)
        and all(point['gate'] >= measurement['gate_sustain_min'] and point['rms'] >= measurement['minimum_upper_voiced_rms']
                for point in points),
        'play_one_attack_one_release': levels == [1, 0] and len(events) == 2
        and gate_messages[0]['observedMs'] < events[0]['eventMs'] < events[1]['eventMs'] <= gate_messages[1]['observedMs'],
    }
    return checks, {'observation_count': len(points), 'minimum_gate': min((p['gate'] for p in points), default=None),
                    'minimum_rms': min((p['rms'] for p in points), default=None), 'gate_messages': gate_messages}


def removal_timing(row, event, configuration):
    notifications = row.get('nativeNotifications', [])
    native = row['native']
    messages = row.get('removed', {}).get('messages', [])
    if not (event and len(messages) == 1 and [e['action'] for e in notifications] == ['watching', 'notified']
            and [e['action'] for e in native] == ['add', 'send', 'remove']):
        return False, {}
    source, pressed, removed = native
    browser_on = messages[0]['eventMs']
    native_on = int(pressed['beforeUptimeNs'])
    start, end = (int(removed[key]) for key in ('beforeUptimeNs', 'afterUptimeNs'))
    callback = int(notifications[1]['uptimeNs'])
    # 2つの時計では、共通するNote Onを起点とした時間差だけを比較する。
    native_ms = (callback - start) / 1e6
    browser_ms = event['eventMs'] - browser_on - (start - native_on) / 1e6
    residual = browser_ms - native_ms
    return (row['observer'] == {'code': 0, 'stderr': ''} and start <= callback and start <= end
            and all(n['endpoint'] == source['endpoint'] for n in notifications)), {
        'dispose_call_ms': (end - start) / 1e6, 'remove_to_native_notification_ms': native_ms,
        'remove_to_browser_event_estimate_ms': browser_ms, 'browser_minus_native_estimate_ms': residual,
        'browser_and_native_agree_within_registered_tolerance': abs(residual) <= configuration['timing_partition_tolerance_ms'],
    }


def normalized_candidate_release(report, elapsed_frames):
    notes = report['midiNotes']
    quantum = read_json(LIVE)['measurement']['expected_quantum_frames']
    if (len(notes) != 2 or notes[1]['note'] is not None or notes[1]['frame'] % quantum
            or notes[1]['frame'] < quantum or notes[1]['frame'] + max(elapsed_frames) > report['outputFrames']):
        raise ValueError('Workletの解放後の比較窓を採取できませんでした')
    release_row = notes[1]['frame'] // quantum
    gate = np.asarray(report['observations'])[:, report['columns'].index('gate')]
    return gate[release_row + np.asarray(elapsed_frames) // quantum - 1] / gate[release_row - 1]


def play_release_seconds(row, elapsed):
    off = row['off']['clock']
    points = [(p['clock'] - off, p['gate']) for p in row['output']['trace']
              if elapsed[0] <= p['clock'] - off <= elapsed[1] and p['gate'] > 0]
    if len(points) < 2:
        raise ValueError('固定上流の解放後の比較窓を採取できませんでした')
    times, values = np.asarray(points).T
    slope, _ = np.polyfit(times, np.log(values), 1)
    return {'points': len(points), 'tau_seconds': float(-1 / slope) if slope < 0 else None}


def upper_checks(row, measurement, frequency):
    trace = row['output']['trace']
    gate_messages = row['output']['gateMessages']
    drift = measurement['upper_drift']
    rate = row['on']['sampleRate']
    internal = rate * (drift['minimum_internal_rate_hz'] // rate + 1)
    samples = np.rint([p['clock'] * internal for p in trace]).astype(int) - 1
    factors = independent_pitch(drift | {'sample_count': int(samples.max()) + 1}, drift | {'f0_hz': 1.0}, internal)
    trace = [p | {'base_f0': p['f0'] / float(factors[i])} for i, p in zip(samples, trace, strict=True)]

    def segment(key, bounds):
        clock = row[key]['clock']
        start, end = (clock + offset for offset in measurement[bounds])
        return [p for p in trace if start <= p['clock'] <= end]

    steady = segment('on', 'upper_steady_window_seconds')
    tail = segment('off', 'upper_release_window_seconds')
    before = [p for p in trace if p['clock'] < row['silent']['clock']]
    statistics = {
        'steady_rows': len(steady), 'tail_rows': len(tail),
        'steady_gate_min': min((r['gate'] for r in steady), default=None),
        'tail_gate_max': max((r['gate'] for r in tail), default=None),
        'steady_f0_hz': [min((r['f0'] for r in steady), default=None), max((r['f0'] for r in steady), default=None)],
        'steady_f0_without_drift_hz': [min((r['base_f0'] for r in steady), default=None),
                                       max((r['base_f0'] for r in steady), default=None)],
        'pre_note_f0_without_drift_max_error_hz': max((abs(r['base_f0'] - row['silent']['targetHz']) for r in before), default=None),
        'steady_peak_rms': max((r['rms'] for r in steady), default=None),
    }
    tolerance = measurement['steady_pitch_absolute_tolerance_hz']
    statistics['raw_f0_passes_original_tolerance'] = bool(steady and all(abs(r['f0'] - frequency) <= tolerance for r in steady))
    checks = {
        'play_target_pitch_and_gate': row['on']['mode'] == 'play' and row['on']['started']
        and row['on']['targetHz'] == frequency and row['held']['targetHz'] == frequency
        and [row[k]['gateTarget'] for k in ('silent', 'on', 'held', 'off', 'released')] == [0, 1, 1, 0, 0]
        and [g['level'] for g in gate_messages if g['clock'] is not None][-2:] == [1, 0],
        'play_finite_and_quiet_before_on': bool(before) and all(r['gate'] == 0 for r in before)
        and bool(np.isfinite([list(p.values()) for p in trace]).all()),
        'play_independent_drift_before_on': bool(before and statistics['pre_note_f0_without_drift_max_error_hz']
                                                 <= drift['pre_note_absolute_tolerance_hz']),
        'play_sustained_voice': bool(steady and statistics['steady_gate_min'] >= measurement['gate_sustain_min']
            and all(abs(r['base_f0'] - frequency) <= tolerance for r in steady)
            and statistics['steady_peak_rms'] >= measurement['minimum_upper_voiced_rms']),
        'play_release': bool(tail and statistics['tail_gate_max'] <= measurement['gate_release_max']),
    }
    return checks, {'sample_rate_hz': rate, 'internal_sample_rate_hz': internal, 'gate_messages': gate_messages, **statistics}


def candidate_checks(data, measurement, frequency, artifacts, execute, shared=None, *, live_case=LIVE, fixed_case=FIXED):
    capture = read_json(artifacts / 'candidate.json')
    replay = artifacts / 'candidate-case.json'
    live = read_json(live_case)['measurement']
    fixed = read_json(fixed_case)
    rate = live['output_rate_hz']
    interval = live['control_interval_output_frames']
    quantum = live['expected_quantum_frames']
    frames, start, stop = (capture[key] for key in ('outputFrames', 'startFrame', 'stopFrame'))
    notes = capture['midiNotes']
    if [event['note'] for event in notes] != [data['note_on'][1], None]:
        return {'midi_targets_at_worklet': False}, {'applied_notes': notes}
    on, off = (event['frame'] for event in notes)
    events = [{'frame': on // interval, 'gate': 1, 'f0_hz': frequency},
              {'frame': off // interval, 'gate': 0}, {'frame': stop // interval, 'gate': 0}]
    points = np.arange(quantum - 1, frames, quantum)
    rows = np.asarray(capture['observations'])
    columns = dict(zip(capture['columns'], rows.T, strict=True))
    reference = reference_controls(frames, interval, rate, live, measurement['candidate_glide_time_constant_seconds'],
                                   fixed['voice']['f0_hz'], events)[points // interval]
    gate_error = float(np.max(np.abs(columns['gate'] - reference[:, 0])))
    f0_error = float(np.max(np.abs(columns['smoothed_f0_hz'] - reference[:, 1])))
    wav = artifacts / 'candidate.wav'
    native = artifacts / 'candidate-cli.wav'
    if execute is not None:
        execute(['cargo', 'run', '--locked', '--release', '-p', 'vocal-cli', '--', 'render-pcm',
                 str(replay), str(native), str(artifacts / 'candidate-cli.csv'), str(quantum)])
    audio = read_wave(wav, rate, frames)
    pcm = compare_pcm(audio, read_wave(native, rate, frames), 0)
    voiced = (points >= on + rate * 0.4) & (points < off)
    if not np.any(voiced):
        return {'sustained_voice_window': False}, {'applied_notes': notes, 'cli_pcm': pcm}
    gate_min = float(columns['gate'][voiced].min())
    steady_f0_peak_error = float(abs(columns['smoothed_f0_hz'][voiced] - frequency).max())
    tail = measurement['candidate_tail_window_frames']
    initial_peak, voiced_peak, tail_peak = (float(np.max(np.abs(segment))) for segment in
                                          (audio[:on], audio[on:off], audio[-tail:]))
    checks = {
        'midi_targets_at_worklet': start <= on < off < stop and on % quantum == off % quantum == 0
        and read_json(replay)['articulators']['events'] == events and capture['stopReason'] == 'manual',
        'finite_and_continuous_worklet': len(rows) == len(points) and bool(np.isfinite(rows).all())
        and bool(np.isfinite(audio).all()) and capture['workletSampleRate'] == rate
        and capture['internalSampleRate'] == live['internal_rate_hz'] and stop + live['release_frames'] == frames
        and bool(np.all(columns['quantum_frames'] == quantum) and np.all(np.diff(columns['context_frame']) == quantum)),
        'independent_worklet_controls': gate_error <= measurement['candidate_control_gate_absolute_tolerance']
        and f0_error <= measurement['candidate_control_pitch_absolute_tolerance_hz'],
        'worklet_sustained_voice': gate_min >= measurement['gate_sustain_min']
        and steady_f0_peak_error <= measurement['steady_pitch_absolute_tolerance_hz']
        and voiced_peak >= measurement['minimum_candidate_voiced_peak'],
        'worklet_silent_before_and_after': initial_peak <= measurement['candidate_silence_peak_max']
        and tail_peak <= measurement['candidate_silence_peak_max'] and bool(np.all(columns['gate'][points < on] == 0)),
        'worklet_pcm_matches_cli': pcm['first_bit_difference_frame'] is None,
    }
    statistics = {
        'applied_notes': notes, 'output_frames': frames, 'sample_rate_hz': rate, 'observations': len(rows),
        'sustained_gate_min': gate_min, 'sustained_f0_max_error_hz': steady_f0_peak_error,
        'initial_pcm_peak': initial_peak, 'voiced_pcm_peak': voiced_peak, 'tail_pcm_peak': tail_peak,
        'control_max_errors': {'gate': gate_error, 'f0_hz': f0_error}, 'cli_pcm': pcm,
    }
    if shared:
        length = round(shared['candidate_rms_window_seconds'] * rate)
        steady_audio = audio[on + round(rate * 0.4):off]
        count = len(steady_audio) // length
        window_rms = np.sqrt(np.mean(steady_audio[:count * length].astype(float).reshape(count, length)**2, axis=1))
        checks['worklet_pcm_sustained_in_each_window'] = count > 0 and bool(np.all(window_rms >= shared['candidate_minimum_window_rms']))
        statistics['sustained_pcm_windows'] = {'frames_per_window': length, 'count': count,
                                              'minimum_rms': float(window_rms.min()) if count else None}
    return checks, statistics


def matching_passive_port(messages, received, candidate_ids, uid):
    if len(messages) != 2 or [message['bytes'] for message in messages] != [item['bytes'] for item in received]:
        return None
    press, release = messages
    port_id = press['port']['id']
    if (port_id in candidate_ids and release['port']['id'] == port_id
            and (uid not in candidate_ids or uid == port_id)
            and press['eventMs'] < release['eventMs']
            and all(message['trusted'] and message['eventMs'] <= message['handlerMs'] for message in messages)):
        return port_id
    return None


def passive_checks(browser, case, out, execute, *, live_case=LIVE, fixed_case=FIXED):
    if 'missingInput' in browser:
        return {'checks': {'selected_attached_input_present': False}, 'evidence': 'unobserved',
                'requested_input': browser['missingInput'], 'coremidi_inventory': browser['inventory']}
    row = browser['targets']['candidate']
    result = {'evidence': browser['inputKind'], 'selected_input': row.get('selectedInput'),
              'browser': browser['chromium']}
    if row.get('error'):
        return {'checks': {'capture_completed': False}, 'capture_error': row['error'], **result}
    spec = case['measurement']
    native = row['received']
    ports = row['connected']['ports']
    final = row['disconnected']
    messages = [msg for msg in final['messages'] if len(msg['bytes']) == 3 and msg['bytes'][0] & 0xf0 in (0x80, 0x90)]
    packets = [msg['bytes'] for msg in messages]
    note = spec['midi_note']
    channel = spec['midi_channel'] - 1
    received = [item for item in native if item['action'] == 'note']
    names = (row['selectedInput']['name'], row['selectedInput']['displayName'])
    candidate_ids = {port['id'] for port in ports if port['state'] == 'connected'
                     and port['connection'] == 'open' and port['name'] in names}
    browser_port_id = matching_passive_port(messages, received, candidate_ids, str(row['selectedInput']['uid']))
    hold_ms = ((int(received[1]['arrivalUptimeNs']) - int(received[0]['arrivalUptimeNs'])) / 1e6
               if len(received) == 2 else 0)
    checks = {
        'registered_input_is_open_and_received_by_native_client': row['permission'] == 'granted'
        and len(candidate_ids) == len(ports) > 0
        and native[0] == {'action': 'listening', 'endpoint': row['selectedInput']['endpoint']}
        and row['receiver'] == {'code': 0, 'stderr': ''},
        'trusted_web_midi_matches_native_receive': browser_port_id is not None,
        'note_on_and_release_match_registered_input': len(packets) == 2
        and packets[0][:2] == [0x90 | channel, note] and packets[0][2] > 0
        and (packets[1][:2] == [0x80 | channel, note] or packets[1] == [0x90 | channel, note, 0])
        and hold_ms >= spec['minimum_hold_ms'],
        'ordinary_ui_holds_and_releases': [row[name]['note'] for name in ('silent', 'on', 'held', 'off', 'released')]
        == ['なし', str(note), str(note), 'なし', 'なし'],
        'page_and_subscriptions_are_clean': not row['pageErrors'] and final['subscriptions'] == 0,
    }
    if idle := row.get('idleFixture'):
        active = row['connected']
        inputs = active['inputPorts']
        events = idle['native']
        idle_ports = [port for port in inputs if port['id'] != browser_port_id]
        checks['idle_input_is_connected_and_silent'] = (
            len(inputs) == 2 and len(idle_ports) == 1 and idle_ports[0]['name'] == events[0]['name']
            and all(port['connection'] == 'open' for port in inputs)
            and sorted(active['subscribedPortIds']) == sorted(port['id'] for port in inputs)
            and [event['action'] for event in events] == ['add', 'remove']
            and all(message['port']['id'] != idle_ports[0]['id'] for message in final['messages']))
    frequency = 440 * 2 ** ((note - 69) / 12)
    checks['equal_temperament_pitch_matches_case'] = frequency == spec['expected_pitch_hz']
    sound_checks, sound = candidate_checks(case['input'], spec, frequency, out, execute,
                                          live_case=live_case, fixed_case=fixed_case)
    return {'checks': checks | sound_checks, **result, 'native_hold_ms': hold_ms,
            'received_bytes': packets, 'web_midi_port_id': browser_port_id,
            'expected_pitch_hz': frequency, 'acoustics': sound}


def measure(case_path, case, baseline_paths, bun, out, execute, passive_input=None):
    release = case.get('release_action', 'note-off')
    shared = case.get('shared_note')
    unplug = release == 'remove-source' or shared is not None
    with TemporaryDirectory(prefix='coremidi-', dir=out.parent) as directory:
        dist, helper = (Path(directory) / name for name in ('dist', 'coremidi-source'))
        execute(['xcrun', 'swiftc', str(HELPER), '-o', str(helper)])
        execute([*bun, 'run', 'build', '--outDir', str(dist)], cwd=WEB, stdout=out / 'browser-build.log')
        command = ['node', str(CAPTURE), str(CASE), str(dist), str(UPSTREAM), str(out), str(helper)]
        if case_path != CASE:
            command.append(str(case_path))
        if passive_input is not None:
            command.append(passive_input)
        execute(command, cwd=WEB)
    browser = read_json(out / 'coremidi-browser.json')
    if passive_input is not None:
        return passive_checks(browser, case, out, execute)
    execute([*bun, 'test', str(UPPER_TEST)], cwd=UPSTREAM, stdout=out / 'upstream-midi-tests.log')
    source = case['input']
    expected_hz = 440 * 2 ** ((source['note_on'][1] - 69) / 12)
    checks = {'both_browser_entries': list(browser['targets']) == ['candidate', 'upstream']
              and browser['mode'] == case['browser']['mode'] and browser['releaseAction'] == release}
    statistics = {}
    for target, row in browser['targets'].items():
        kind = 'text' if target == 'candidate' else 'number'
        if shared:
            result, observation = shared_note_checks(row, source, shared, target)
        else:
            result = route_checks(row, source, kind, unplug)
        if row.get('error'):
            statistics[target] = {'error': row['error']}
            result['audio_observed'] = False
        else:
            if target == 'candidate':
                audio, statistics[target] = candidate_checks(source, case['measurement'], expected_hz, out, execute, shared)
            else:
                audio, statistics[target] = upper_checks(row, case['measurement'], expected_hz)
            result.update(audio)
        if shared:
            if target == 'upstream' and not row.get('error'):
                between, observation['between_removals'] = play_between_removals(
                    row, shared, case['measurement'], observation['removals'])
                result.update(between)
            statistics[target]['shared_note'] = observation
        elif unplug:
            extra, observation = unplug_observation(row, target)
            result.update(extra)
            statistics[target]['unplug'] = observation
            if 'native_notification' in case:
                result['native_removal_notification'], observation['timing'] = removal_timing(
                    row, observation['event'], case['native_notification'])
        checks.update({f'{target}/{key}': value for key, value in result.items()})
    if unplug and all(not row.get('error') for row in browser['targets'].values()):
        comparison = case['replay']
        elapsed = comparison['candidate_elapsed_frames']
        observed = normalized_candidate_release(read_json(out / 'candidate.json'), elapsed)
        baseline = normalized_candidate_release(read_json(baseline_paths['candidate.json']), elapsed)
        peak_error = float(np.max(np.abs(observed - baseline)))
        control = 'single_unplug' if shared else 'note_off'
        statistics['candidate']['release_comparison'] = {'elapsed_frames': elapsed, 'unplug': observed.tolist(),
                                                        control: baseline.tolist(), 'maximum_error': peak_error}
        checks[f'candidate/release_matches_{control}'] = peak_error <= comparison['normalized_gate_absolute_tolerance']
        baseline_upper = read_json(baseline_paths['coremidi-browser.json'])['targets']['upstream']
        seconds = comparison['upper_elapsed_seconds']
        observed = play_release_seconds(browser['targets']['upstream'], seconds)
        baseline = play_release_seconds(baseline_upper, seconds)
        statistics['upstream']['release_comparison'] = {'elapsed_seconds': seconds, 'unplug': observed, control: baseline}
        checks['upstream/release_time_constant'] = all(fit['tau_seconds'] is not None
            and abs(fit['tau_seconds'] - comparison['upper_release_seconds']) <= comparison['upper_fit_absolute_tolerance_seconds']
            for fit in (observed, baseline))
    return {'checks': checks, 'browser': browser['chromium'], 'release_action': release,
            'expected_pitch_hz': expected_hz, 'result': statistics}


def verified_baseline(baseline):
    run = WORKSPACE / 'runs' / baseline['run']
    manifest_path = run / 'manifest.json'
    manifest = read_json(manifest_path)
    if sha256(manifest_path) != baseline['manifest_sha256'] or manifest['status'] != 'pass':
        raise ValueError('対照実行が登録と一致しません')
    case_path = WORKSPACE / 'cases' / baseline['case']
    known_inputs = {row['path']: row['sha256'] for row in manifest['inputs']}
    if manifest['case_id'] != case_path.stem or any(sha256(path) != known_inputs.get(path.relative_to(ROOT).as_posix())
                                                   for path in (CASE, case_path)):
        raise ValueError('現行ケースが対照で使った条件と一致しません')
    files = {}
    for name in ('candidate.json', 'coremidi-browser.json'):
        key = f'artifacts/{name}'
        expected = next((out for out in manifest['outputs'] if out['path'] == key), None)
        path = run / key
        if not expected or path.stat().st_size != expected['bytes'] or sha256(path) != expected['sha256']:
            raise ValueError(f'対照出力が登録と一致しません ({name})')
        files[name] = path
    return manifest_path, case_path, files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--unplug', action='store_const', dest='case_path', const=UNPLUG,
                      help='押鍵中のCoreMIDI送信元削除を比較する')
    mode.add_argument('--shared-note', action='store_const', dest='case_path', const=SHARED_NOTE,
                      help='同じ音を保持した2送信元を順に削除する')
    mode.add_argument('--physical-source', type=int, metavar='UID', help='接続済みのCoreMIDI入力を受動観測する')
    mode.add_argument('--passive-fixture', action='store_const', const='fixture',
                      help='仮想入力で受動観測の経路を検証する')
    mode.add_argument('--passive-fixture-with-idle-input', action='store_const', dest='passive_fixture',
                      const='fixture-with-idle-input', help='無操作の仮想入力を追加して受動観測を検証する')
    mode.add_argument('--passive-fixture-with-same-name-input', action='store_const', dest='passive_fixture',
                      const='fixture-with-same-name-input', help='同名の無操作入力を追加して受動観測を検証する')
    parser.add_argument('--physical-device-label', help='操作者が確認した鍵盤の機種名と接続方法')
    args = parser.parse_args()
    if args.physical_device_label is not None and (
            args.physical_source is None or not args.physical_device_label.strip()):
        parser.error('鍵盤の機器情報は接続済み入力のUIDと併せて指定してください')
    passive_input = args.passive_fixture or (
        str(args.physical_source) if args.physical_source is not None else None)
    case_path = PASSIVE if passive_input is not None else args.case_path or CASE
    case = read_json(CASE)
    baseline_paths = {}
    manifests = []
    if case_path == PASSIVE:
        passive_case = read_json(PASSIVE)
        measurement = case['measurement'] | passive_case['measurement']
        case.update(passive_case, measurement=measurement)
        if case['input']['note_on'][1] != measurement['midi_note']:
            parser.error('基準のノートと受動計測の登録条件が異なります')
        baseline, _ = hydrate_run(case['baseline_run'], case['baseline_case'], case['upstream_revision'])
        manifests.append(baseline / 'manifest.json')
    elif case_path != CASE:
        case.update(read_json(case_path))
        manifest, baseline_case, baseline_paths = verified_baseline(case['baseline'])
        manifests.extend((manifest, baseline_case))
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True):
        parser.error('変更のない固定上流版が必要です')
    for name, digest in case['previous'].items():
        manifest = WORKSPACE / 'runs' / name / 'manifest.json'
        if sha256(manifest) != digest or read_json(manifest)['status'] != 'pass':
            parser.error(f'先行実行が登録と一致しません ({name})')
        manifests.append(manifest)
    bun = ['bun'] if shutil.which('bun') else ['npx', '--offline', '--yes', '--package=bun@1.4.4', '--', 'bun']
    upper_sources = ('src/ui/midi.ts', 'src/ui/store.ts', 'src/ui/components/Keys.tsx', 'src/audio/AudioEngine.ts',
                     'src/worklet/processor.ts', 'crates/chimera/src/voice/human_voice.rs', 'crates/chimera/src/math.rs',
                     'crates/chimera/src/sources/glottis.rs', 'crates/chimera-wasm/src/lib.rs')
    inputs = [case_path, CASE, LIVE, FIXED, HELPER, CAPTURE, Path(__file__).resolve(), UPPER_TEST, *manifests,
              *baseline_paths.values(),
              *(UPSTREAM / name for name in upper_sources), *web_sources(), *candidate_sources(),
              *(WORKSPACE / 'tools' / name for name in ('measure_worklet_fixed.py', 'measure_worklet_midi.py',
                'measure_worklet_songbird.py', 'measure_glottal_pitch.py', 'measure_turbulence.py',
                'measure_uniform_tube.py', 'measure_wasm_fixed.py', 'upstream_baseline.py'))]
    if args.passive_fixture:
        inputs.append(WORKSPACE / 'cases/worklet-midi-coremidi-input-aliases.json')
    if args.passive_fixture == 'fixture-with-idle-input':
        inputs.append(WORKSPACE / 'cases/worklet-midi-coremidi-idle-input.json')
    if args.passive_fixture == 'fixture-with-same-name-input':
        inputs.append(WORKSPACE / 'cases/worklet-midi-coremidi-same-name.json')
    details = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision,
               'invoked_from': str(Path.cwd()), 'node': subprocess.check_output(['node', '--version'], text=True).strip(),
               'input_selection': passive_input}
    if args.physical_device_label is not None:
        details['operator_device_label'] = args.physical_device_label.strip()
    return record_measurement(args.run_id, case_path, inputs, details,
                              lambda out, execute: measure(case_path, case, baseline_paths, bun, out, execute,
                                                           passive_input), command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
