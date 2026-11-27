"""ビートボックスのMIDI低音とハムのセルを、固定上流と同じフレームで照合する。"""

import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess

import numpy as np
from scipy.io import wavfile

from measure_beatbox_pattern import PROBE
import measure_uniform_tube as shared
from measure_vowel_voice import independent_yin
from measure_wasm_fixed import read_json
from measure_worklet_fixed import ROOT, WEB, web_sources
from upstream_baseline import UPSTREAM, WORKSPACE

CASE = WORKSPACE / 'cases/worklet-midi-beatbox.json'
CAPTURE = WEB / 'tools/capture-midi-beatbox.mjs'
WINDOW_NOTES = {'after_on_40': 40, 'after_on_47': 47, 'after_off_47': 40, 'sequenced_hum_absolute': 47}
BASE_KEYS = ('before_first_key_relative', 'after_on_40', 'after_on_47', 'after_off_47', 'after_off_40')


def frequency(note):
    return 440 * 2 ** ((note - 69) / 12)


def cents(hz, target):
    return float(1200 * np.log2(hz / target)) if hz > 0 else None


def below_cents(value, limit):
    return value is not None and abs(value) <= limit


def rms(values):
    return float(np.sqrt(np.mean(values.astype(float)**2)))


def window_bounds(keys, settings):
    anchors = dict(zip(BASE_KEYS, [keys[0], *keys], strict=True))
    return {name: tuple(edge + anchors.get(name, 0) for edge in offsets)
            for name, offsets in settings['windows_seconds'].items()}


def window_series(times, data, start, end):
    series = data[(times >= start) & (times < end)]
    if len(series) == 0:
        raise ValueError(f'{start:.4f}〜{end:.4f}秒の観測がありません')
    return series


def observe_native(trace, pcm, rate, windows):
    data = {}
    signal = {
        'pitch': 'glottal_f0_hz', 'smoothed': 'smoothed_f0_hz', 'lip': 'lip_minimum_cm2',
        'aperture': 'lip_aperture_cm', 'nasal': 'nose_flow_cm3_s', 'oral': 'lip_flow_cm3_s',
        'velum': 'velum_port_area_cm2', 'gate': 'gate',
    }
    times = (trace['frame'] + 1) / rate
    for name, (start, end) in windows.items():
        pitch, smoothed, lip, aperture, nasal, oral, velum, gate = (
            window_series(times, trace[field], start, end) for field in signal.values())
        channel = pcm[round(start * rate):round(end * rate)]
        result = {'f0_hz': float(np.median(pitch)), 'smoothed_f0_hz': float(np.median(smoothed)),
                  'lip_maximum_cm2': float(lip.max()), 'lip_aperture_median_cm': float(np.median(aperture)),
                  'nose_rms_cm3_s': rms(nasal), 'lip_rms_cm3_s': rms(oral),
                  'velum_minimum_cm2': float(velum.min()), 'velum_maximum_cm2': float(velum.max()),
                  'gate_minimum': float(gate.min()), 'gate_maximum': float(gate.max()), 'pcm_rms': rms(channel)}
        if note := WINDOW_NOTES.get(name):
            target = frequency(note)
            hz, score = independent_yin(channel.astype(float), rate,
                {'pitch_min_hz': 65, 'pitch_max_hz': 220, 'yin_threshold': .15})
            result.update(note=note, target_hz=target, f0_cents=cents(result['f0_hz'], target),
                          pcm_f0_hz=hz, pcm_yin_score=score, pcm_f0_cents=cents(hz, target) if hz else None)
        data[name] = result
    return data


def observe_browser(source, settings):
    series = source['telemetry']
    clock, f0, lip, velum, gate = (np.array([row[key] for row in series]) for key in
                                   ('clock', 'f0', 'lipArea', 'velum', 'gate'))
    windows = window_bounds([row['clock'] for row in source['events'] if 'note' in row], settings)
    result = {}
    for label, (begin, end) in windows.items():
        f, l, v, g = (window_series(clock, array, begin, end) for array in (f0, lip, velum, gate))
        pitch = float(np.median(f))
        result[label] = {'telemetry_count': len(f), 'f0_hz': pitch,
                         'f0_cents': cents(pitch, frequency(WINDOW_NOTES[label])) if label in WINDOW_NOTES else None,
                         'lip_maximum_cm2': float(l.max()), 'velum_minimum_cm2': float(v.min()),
                         'velum_maximum_cm2': float(v.max()), 'gate_maximum': float(g.max())}
    return result


def input_events(case):
    spec = case['input']
    timeline = sorted([*spec['events'], {**spec['toggle_hum'], 'type': 'toggle-hum'}],
                      key=lambda event: event['seconds'])
    operations = [{'type': 'toggle_hum', 'step': event['step']} if event['type'] == 'toggle-hum'
                  else {'type': 'bass_key', 'note': event['note'], 'pressed': event['type'] == 'note-on'}
                  for event in timeline]
    return timeline, operations


def read_trace(path, fields):
    with path.open() as stream:
        header = stream.readline().rstrip().split(',')
        missing = set(fields) - set(header)
        if missing:
            raise ValueError(f'{path.name} に観測列がありません ({", ".join(sorted(missing))})')
        return np.loadtxt(stream, delimiter=',', usecols=[header.index(field) for field in fields],
                          dtype=[(field, 'f8') for field in fields])


def measure(case, artifacts, execute, bun):
    execute([*bun, 'test', 'tests/singing-live.test.ts', '-t', 'leaving Beatbox'], cwd=UPSTREAM)
    execute([*bun, 'run', 'build'], cwd=WEB, stdout=artifacts / 'browser-build.log')
    execute(['node', str(CAPTURE), str(artifacts), str(CASE), str(UPSTREAM)], cwd=WEB)
    browser = read_json(artifacts / 'midi-beatbox-browser.json')
    replay_path = artifacts / 'midi-beatbox-case.json'
    report = read_json(artifacts / 'midi-beatbox.json')
    cli = ['cargo', 'run', '--locked', '--release', '-p', 'vocal-cli', '--']
    execute([*cli, 'inspect', str(replay_path)], stdout=artifacts / 'cli-inspect.json')
    execute([*cli, 'render', str(replay_path), str(artifacts / 'cli-voice.csv')])
    execute([*cli, 'render-pcm', str(replay_path), str(artifacts / 'cli.wav'), str(artifacts / 'cli-pcm.csv'), '113'])
    spec = case['measurement']
    replay = read_json(replay_path)
    reference_case = artifacts / 'upstream-case.json'
    reference_case.write_text(json.dumps({**replay, 'measurement': {'host_block_frames': [128, 113]}}) + '\n')
    probe = shared.build_upstream_probe(PROBE, artifacts, execute, extra_libraries=('serde_json',))
    execute([str(probe), str(reference_case), str(artifacts)], cwd=UPSTREAM)
    plan = read_json(artifacts / 'cli-inspect.json')['beatbox_pattern']
    upper_plan = read_json(artifacts / 'upstream-plan.json')

    rate, pcm = wavfile.read(artifacts / 'midi-beatbox.wav')
    upper_pcm = np.fromfile(artifacts / 'upstream-probe.f32', dtype='<f4')
    fields = ('gate', 'lip_aperture_cm', 'lip_minimum_cm2', 'glottal_f0_hz', 'smoothed_f0_hz',
              'nose_flow_cm3_s', 'velum_port_area_cm2', 'beat_step', 'beat_next_step')
    common = ('frame', 'lip_flow_cm3_s', *fields[:-1])
    cli_trace = read_trace(artifacts / 'cli-voice.csv', (*common, 'beat_next_step'))
    upper_trace = read_trace(artifacts / 'upstream-trace.csv', common)
    raw = np.asarray(report['observations'])
    cols = {name: index for index, name in enumerate(report['columns'])}
    frames = raw[:, cols['frames_rendered']].astype(int)
    differences = {key: float(np.max(abs(raw[:, cols[key]] - cli_trace[key][frames - 1]))) for key in fields}

    timeline, operations = input_events(case)
    events = replay['beatbox_pattern']['events']
    adoption = [event['frame'] for event in events]
    quantum = spec['frame_quantum']
    stride = spec['observation_stride_frames']
    errors = [((frame - adoption[0]) / rate - (e['seconds'] - timeline[0]['seconds']))
              for frame, e in zip(adoption, timeline, strict=True)]
    bounds = window_bounds([e['frame'] / rate for e in events if e['type'] == 'bass_key'], spec)
    native = {'candidate': observe_native(cli_trace, pcm, rate, bounds),
              'upstream': observe_native(upper_trace, upper_pcm, rate, bounds)}
    held = list(BASE_KEYS[1:-1])
    voiced = [*held, 'sequenced_hum_absolute']
    browser_upper = browser['upstream']
    browser_windows = observe_browser(browser_upper, spec)
    upper_state = browser_upper['events']
    note = spec['hum_slot_expected_note']
    hum = [entry for entry in plan['reservations'] if entry['step'].get('midi_note') is not None
           and entry['step']['hit_seconds'] < len(pcm) / rate]
    error_by_field = {}
    for field in ('gate', 'lip_aperture_cm', 'lip_minimum_cm2', 'velum_port_area_cm2', 'glottal_f0_hz',
                  'nose_flow_cm3_s'):
        difference = abs(cli_trace[field] - upper_trace[field])
        index = int(np.argmax(difference))
        first = np.flatnonzero(difference > spec['physical_absolute_tolerance'])
        error_by_field[field] = {'maximum': float(difference[index]), 'frame_at_maximum': index,
                                 'first_outside_tolerance': int(first[0]) if first.size else None}
    flow_difference = {label: float(abs(native['candidate'][label]['nose_rms_cm3_s'] /
                                      native['upstream'][label]['nose_rms_cm3_s'] - 1)) for label in voiced}
    checks = {
        'normal_midi_entry': all(browser[name]['requests'] == [{'sysex': False}] and not browser[name]['errors']
                                 for name in ('candidate', 'upstream'))
            and browser['candidate']['listenersAfterDisconnect'] == 0,
        'recorded_events_and_quantum': [{k: v for k, v in e.items() if k != 'frame'} for e in events] == operations
            and [e['frame'] for e in plan['transport_events']] == adoption
            and [e['frame'] for e in upper_plan['transport_events']] == adoption
            and all(frame % quantum == 0 for frame in adoption)
            and max(map(abs, errors)) <= spec['latest_relative_event_error_seconds']
            and all(observed['contextFrame'] == report['realtime']['scheduledContextFrame'] + e['frame']
                    and {k: v for k, v in observed.items() if k != 'contextFrame'} == e
                    for observed, e in zip(report['beatEvents'], events, strict=True)),
        'matching_rate_and_complete_observations': rate == report['sampleRate'] == browser_upper['rate']
            == case['input']['output_rate_hz'] and len(pcm) == len(cli_trace) == len(upper_pcm)
            and np.array_equal(frames, np.minimum(np.arange(stride, len(pcm) + stride, stride), len(pcm))),
        'normal_cli_wave_replay_bit_exact': (artifacts / 'midi-beatbox.wav').read_bytes()
            == (artifacts / 'cli.wav').read_bytes(),
        'cli_worklet_state': all(value <= 1e-10 for value in differences.values()),
        'upper_keeps_last_pressed_note_in_cell': [row['held'] for row in upper_state] ==
            [[40], [40, 47], [40], [40], []]
            and [row['bassNote'] for row in upper_state] == [40, note, note, note, note]
            and [row['basePitch'] for row in upper_state] == [frequency(n) for n in (40, 47, 40, 40, 40)]
            and upper_state[3]['firstStep'] == {'id': 'm', 'note': note}
            and upper_state[-1]['lipTarget'] == spec['restored_lip_target_cm']
            and upper_state[-1]['velumTarget'] == -.15,
        'unreserved_hum_is_note_47': len(hum) == 1 and hum[0]['step']['midi_note'] == note
            and hum[0]['step']['hit_seconds'] == spec['hum_hit_seconds']
            and hum[0]['frame'] > adoption[3] and upper_plan['midi_edited_slot_notes'][0] == note,
        'upper_browser_reproduces_held_pitch_and_hum': all(
            below_cents(browser_windows[label]['f0_cents'], spec['held_pitch_tolerance_cents']) for label in voiced),
        'upper_browser_velum_opens_and_releases': all(browser_windows[label]['velum_minimum_cm2'] >= spec['open_velum_min_cm2']
            for label in held) and browser_windows['after_off_40']['velum_maximum_cm2'] <= spec['released_velum_max_cm2'],
        'same_frame_nose_flow_and_geometry': all(value <= spec['flow_rms_relative_tolerance']
            for value in flow_difference.values())
            and all(error_by_field[field]['maximum'] <= spec['physical_absolute_tolerance']
                    for field in ('lip_aperture_cm', 'lip_minimum_cm2', 'velum_port_area_cm2', 'gate')),
        'fixed_engine_partition_invariant': all(np.array_equal(
            upper_pcm.view('<u4'), np.fromfile(artifacts / f'upstream-engine-{size}.f32', dtype='<u4'))
            for size in (113, 128)),
    }
    for side, values in native.items():
        checks[f'{side}_pitch_and_independent_pcm'] = all(
            below_cents(values[key]['f0_cents'], spec['held_pitch_tolerance_cents'])
            and below_cents(values[key]['pcm_f0_cents'], spec['pcm_pitch_tolerance_cents']) for key in voiced)
        checks[f'{side}_mouth_closed_and_nose_radiates'] = all(
            values[key]['lip_maximum_cm2'] <= spec['closed_lip_max_cm2']
            and values[key]['velum_minimum_cm2'] >= spec['open_velum_min_cm2']
            and values[key]['nose_rms_cm3_s'] >= spec['held_nose_rms_min_cm3_s']
            and values[key]['lip_rms_cm3_s'] < values[key]['nose_rms_cm3_s'] for key in held)
        checks[f'{side}_held_gate_and_release'] = all(values[key]['gate_minimum'] >= spec['held_gate_min'] for key in held)
        checks[f'{side}_held_gate_and_release'] &= all(
            values[key]['gate_maximum'] <= spec['released_gate_max']
            and values[key]['velum_maximum_cm2'] <= spec['released_velum_max_cm2']
            for key in ('before_first_key_relative', 'after_off_40'))
    return {'checks': {key: bool(value) for key, value in checks.items()}, 'browser': browser['chromium'],
            'sample_rate_hz': rate, 'audio_frames': len(pcm), 'observation_count': len(frames),
            'events': events, 'event_timing_errors_seconds': errors, 'windows_seconds': bounds, 'native': native,
            'upstream_browser_states': upper_state, 'upstream_browser': browser_windows, 'hum_reservations': hum,
            'nose_rms_relative_differences': flow_difference, 'worklet_trace_differences': differences,
            'native_trace_differences': error_by_field,
            'candidate_and_upper_pcm_max_delta': float(np.max(abs(pcm - upper_pcm)))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', args.run_id):
        parser.error('実行IDは英数字で始めてください')
    case = read_json(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(
            ['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True):
        parser.error('固定上流の取得状態を確認してください')
    bun = ['bun'] if shutil.which('bun') else ['npx', '--offline', '--yes', '--package=bun@1.4.4', '--', 'bun']
    upstream = [UPSTREAM / name for name in ('src/ui/store.ts', 'src/ui/midi.ts', 'src/audio/AudioEngine.ts',
        'src/ui/components/BeatboxPanel.tsx', 'src/worklet/processor.ts', 'crates/chimera/src/control/beat_player.rs',
        'crates/chimera/src/engine.rs', 'crates/chimera/src/phonetics/beatbox.rs', 'tests/singing-live.test.ts')]
    inputs = [CASE, CAPTURE, PROBE, Path(__file__), PROBE.with_name('upstream_beatbox_oral_trace.rs'),
              PROBE.with_name('measure_vowel_voice.py'), *web_sources(), *shared.candidate_sources(), *upstream]
    return shared.record_measurement(args.run_id, CASE, inputs, {'case_id': case['id'], 'upstream_revision': revision},
        lambda out, execute: measure(case, out, execute, bun), command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
