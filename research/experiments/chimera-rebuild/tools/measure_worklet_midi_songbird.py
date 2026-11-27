"""実ブラウザの鳴禽MIDIを、固定上流と独立した制御更新に照合する。"""

import argparse
import json
import math
from pathlib import Path
import re
import shutil
import subprocess

import numpy as np
from scipy.io import wavfile

import measure_uniform_tube as shared
from measure_wasm_fixed import read_json
from measure_worklet_fixed import ROOT, WEB, web_sources
from upstream_baseline import UPSTREAM, WORKSPACE, sha256

CASE = WORKSPACE / 'cases/worklet-midi-songbird.json'
CAPTURE = WEB / 'tools/capture-midi-songbird.mjs'
PROBE = WORKSPACE / 'tools/upstream_songbird_voice_probe.rs'
CONTROL_FIELDS = ('gate', 'gate_target', 'pitch_hz', 'target_pitch_hz', 'sac_pressure_dyn_cm2')
SYRINX_FIELDS = ('left_opening', 'right_opening', 'left_port_area_cm2', 'right_port_area_cm2',
                 'left_port_flow_cm3_s', 'right_port_flow_cm3_s')
TRACE_FIELDS = ('frame', 'internal_sample', *CONTROL_FIELDS, *SYRINX_FIELDS, 'pcm_f32')


def midi_targets(notes, limits):
    # MIDIの半音単位で、対象の音域をピアノの鍵盤に対して中心合わせする。
    low, high = [69 + 12 * math.log2(edge / 440) for edge in limits]
    octaves = math.floor(((low + high) / 2 - 60) / 12 + .5)
    folded = {}
    for note in notes:
        shifted = note + 12 * octaves
        if shifted > high:
            shifted -= 12 * math.ceil((shifted - high) / 12)
        if shifted < low:
            shifted += 12 * math.ceil((low - shifted) / 12)
        folded[note] = 440 * 2 ** ((min(shifted, high) - 69) / 12)
    return octaves, folded


def read_trace(path, fields=TRACE_FIELDS):
    with path.open() as stream:
        header = stream.readline().rstrip().split(',')
        missing = set(fields) - set(header)
        if missing:
            raise ValueError(f'{path.name} に観測列がありません ({", ".join(sorted(missing))})')
        return np.loadtxt(stream, delimiter=',', usecols=[header.index(field) for field in fields],
                          dtype=[(field, 'f8') for field in fields])


def independent_controls(voice, folded, block):
    frames = voice['frames']
    events = iter(voice['events'])
    event = next(events, None)
    expected = {name: np.empty(frames) for name in ('pitch_hz', 'target_pitch_hz', 'gate', 'gate_target')}
    gate, gate_target = 0., 0.
    pitch = pitch_target = voice['controls']['pitch_hz']
    log_pitch = math.log(pitch)
    dt = block / voice['sample_rate_hz']
    for frame in range(0, frames, block):
        while event is not None and event['frame'] <= frame:
            note = event['held_midi']['note']
            gate_target = float(note is not None)
            if note is not None:
                pitch_target = folded[note]
            event = next(events, None)
        keep = math.exp(-dt / .008)
        log_pitch = keep * log_pitch + (1 - keep) * math.log(pitch_target)
        gate = gate_target + (gate - gate_target) * math.exp(-dt / (.004 if gate_target > gate else .012))
        for name, value in zip(expected, (math.exp(log_pitch), pitch_target, gate, gate_target), strict=True):
            expected[name][frame:frame + block] = value
    return expected


def rms(values):
    return float(np.sqrt(np.mean(values.astype(float)**2)))


def observations(trace, pcm, events, spec, rate):
    findings = []
    for event in events:
        note = event['held_midi']['note']
        key = 'steady_window_seconds_after_event' if note is not None else 'release_window_seconds_after_event'
        window = slice(*(event['frame'] + round(rate * edge) for edge in spec[key]))
        segment = trace[window]
        if not len(segment):
            raise ValueError(f'MIDIイベント {event["frame"]} の観測窓が空です')
        findings.append({
            'note': note, 'frames': [window.start, window.stop], 'pitch_hz': float(np.median(segment['pitch_hz'])),
            'gate_min': float(segment['gate'].min()), 'gate_max': float(segment['gate'].max()),
            'sac_pressure_median_dyn_cm2': float(np.median(segment['sac_pressure_dyn_cm2'])),
            'left_port_flow_rms_cm3_s': rms(segment['left_port_flow_cm3_s']),
            'right_port_flow_rms_cm3_s': rms(segment['right_port_flow_cm3_s']),
            'pcm_rms': rms(pcm[window]),
        })
    return findings


def upstream_score(voice, upper_events):
    events = []
    for event, observation in zip(voice['events'], upper_events, strict=True):
        pressed = event['held_midi']['note'] is not None
        result = {'frame': event['frame'], 'gate': float(pressed)}
        if pressed:
            result['controls'] = {**voice['controls'], 'pitch_hz': observation['pitch']}
        events.append(result)
    return {**voice, 'events': events}


def compare_browsers(browser, expected, folded, rate, spec, input_events, initial_pitch):
    upper = browser['upstream']
    states = upper['events']
    target = initial_pitch
    state_errors = []
    result = []
    held = []
    held_states = []
    for event, note, key_event in zip(states, expected, input_events, strict=True):
        key_note = key_event['note']
        if key_event['type'] == 'note-on':
            held.append(key_note)
        else:
            held.remove(key_note)
        held_states.append(held.copy())
        if note is not None:
            target = folded[note]
        state_errors.append(abs(event['pitch'] - target))
        key = 'steady_window_seconds_after_event' if note is not None else 'release_window_seconds_after_event'
        begin, end = (event['clock'] + offset for offset in spec[key])
        window = [row for row in upper['telemetry'] if begin <= row['clock'] < end]
        if not window:
            raise ValueError('固定ブラウザの持続音の観測点がありません')
        result.append({
            'note': note, 'samples': len(window), 'pitch_hz': float(np.median([row['pitch'] for row in window])),
            'gate_min': min(row['gate'] for row in window), 'gate_max': max(row['gate'] for row in window),
            'left_opening_max': max(row['left'] for row in window), 'right_opening_max': max(row['right'] for row in window),
        })
    checks = {
        'normal_browser_midi_path': upper['rate'] == rate and browser['candidate']['afterDisconnect'] == 0
            and all(browser[name]['requests'] == [{'sysex': False}] and not browser[name]['errors']
                    for name in ('candidate', 'upstream')),
        'upper_held_notes_and_pitch': [row['held'] for row in states] == held_states
            and all(row['creature'] == 'songbird' and row['keyCall'] is None and row['hold'] is False for row in states)
            and max(state_errors) <= spec['pitch_target_absolute_tolerance_hz'],
        'upper_browser_glide_and_gate': all(
            (abs(row['pitch_hz'] - folded[row['note']]) <= spec['browser_steady_pitch_absolute_tolerance_hz']
             and row['gate_min'] >= spec['steady_gate_min'])
            if row['note'] is not None else row['gate_max'] <= spec['release_gate_max']
            for row in result),
    }
    return checks, {'state_pitch_errors_hz': state_errors, 'windows': result}


def same_frame_control(voice, folded, spec, artifacts, execute, command, probe):
    config = spec['same_frame_control']
    note, frame, frames = (config[key] for key in ('note', 'frame', 'frames'))
    source = {**voice, 'frames': frames, 'events': [
        {'frame': frame, 'held_midi': {'note': note}},
        {'frame': frame, 'held_midi': {'note': None}},
    ]}
    fixed_controls = {**source['controls'], 'purity': config['fixed_cavity_purity']}
    fixed = {**source, 'controls': fixed_controls}
    # 同一サンプルより前に起きた操作を固定上流の目標値へ展開する。
    # 最後に離した時点で呼気は0、音高は直前の押下の値になる。
    upper = {**source, 'events': [{
        'frame': frame, 'gate': 0.0, 'controls': {**source['controls'], 'pitch_hz': folded[note]},
    }]}

    def capture(name, settings, upstream=False):
        path = artifacts / f'{name}-case.json'
        trace = artifacts / f'{name}.csv'
        path.write_text(json.dumps({'songbird_voice': settings}) + '\n')
        if upstream:
            execute([str(probe), str(path), '--observe-syrinx'], cwd=UPSTREAM, stdout=trace)
        else:
            execute([*command, 'render', str(path), str(trace)])
        return read_trace(trace)

    trace, control, reference = (
        capture('same-frame', source), capture('same-frame-fixed-cavity', fixed), capture('same-frame-upper', upper, True),
    )
    traces = {'candidate': trace, 'fixed_cavity': control, 'upstream': reference}
    peaks = {name: float(np.max(abs(series['pcm_f32']))) for name, series in traces.items()}
    comparisons = {
        'same_frame_key_priority_keeps_pitch_and_releases_gate':
            all(max(abs(series['target_pitch_hz'][frame:] - folded[note])) <= spec['pitch_target_absolute_tolerance_hz']
                and not np.any(series['gate_target']) and not np.any(series['sac_pressure_dyn_cm2'])
                for series in traces.values()),
        'same_frame_passive_sound_matches_upstream':
            peaks['candidate'] >= config['minimum_tracking_pcm_peak']
            and max(abs(trace['pcm_f32'] - reference['pcm_f32'])) <= spec['native_pcm_absolute_tolerance']
            and not np.any(trace['pcm_f32'][:frame]),
        'same_frame_fixed_cavity_remains_silent': peaks['fixed_cavity'] == 0.0,
    }
    first_nonzero = {name: np.flatnonzero(series['pcm_f32']) for name, series in traces.items()}
    return comparisons, {
        'pcm_peaks': peaks, 'audio_start_frames': {name: int(idx[0]) if len(idx) else None
                                                for name, idx in first_nonzero.items()},
        'gate_maximum': {name: float(series['gate'].max()) for name, series in traces.items()},
        'upstream_pcm_max_delta': float(max(abs(trace['pcm_f32'] - reference['pcm_f32']))),
    }


def measure(case, artifacts, execute, bun):
    execute([*bun, 'test', 'tests/creature-abi.test.ts'], cwd=UPSTREAM)
    execute([*bun, 'run', 'build'], cwd=WEB, stdout=artifacts / 'browser-build.log')
    execute(['node', str(CAPTURE), str(artifacts), str(CASE), str(UPSTREAM)], cwd=WEB)
    browser = read_json(artifacts / 'midi-songbird-browser.json')
    path = artifacts / 'midi-songbird-case.json'
    report = read_json(artifacts / 'midi-songbird.json')
    voice = read_json(path)['songbird_voice']
    events = voice['events']
    spec = case['measurement']
    rate, pcm = wavfile.read(artifacts / 'midi-songbird.wav')
    notes = spec['expected_held_notes']
    events_from_report = report['midiEvents']
    expected_frames = [row['frame'] for row in events_from_report]
    quantum, stride, block = (spec[k] for k in ('quantum_frames', 'observation_stride_frames', 'control_frames'))
    frame_origin = report['timing'][0][0]
    clock_deltas = [((frame - expected_frames[0]) / rate - (item['seconds'] - case['input']['events'][0]['seconds']))
                    for item, frame in zip(case['input']['events'], expected_frames, strict=True)]
    octaves, folded = midi_targets(set(notes) - {None}, case['input']['pitch_range_hz'])
    checks, upper_browser = compare_browsers(browser, notes, folded, rate, spec, case['input']['events'],
                                             voice['controls']['pitch_hz'])

    command = ['cargo', 'run', '--locked', '--release', '-p', 'vocal-cli', '--']
    execute([*command, 'inspect', str(path)], stdout=artifacts / 'cli-inspect.json')
    execute([*command, 'render-pcm', str(path), str(artifacts / 'cli.wav'), str(artifacts / 'cli.csv'), '113'])
    fixed_path = artifacts / 'fixed-pitch-case.json'
    fixed_events = [event if event['held_midi']['note'] is None else
                    {**event, 'held_midi': {'note': spec['fixed_pitch_control_note']}} for event in events]
    fixed_path.write_text(json.dumps({'songbird_voice': {**voice, 'events': fixed_events}}) + '\n')
    execute([*command, 'render-pcm', str(fixed_path), str(artifacts / 'fixed-pitch.wav'),
             str(artifacts / 'fixed-pitch.csv'), '113'])
    upstream_path = artifacts / 'upstream-case.json'
    upstream_path.write_text(json.dumps({'songbird_voice': upstream_score(voice, browser['upstream']['events'])}) + '\n')
    probe = shared.build_upstream_probe(PROBE, artifacts, execute, extra_libraries=('serde_json',))
    execute([str(probe), str(upstream_path), '--observe-syrinx'], cwd=UPSTREAM, stdout=artifacts / 'upstream.csv')

    candidate, upper, fixed = (read_trace(artifacts / filename) for filename in ('cli.csv', 'upstream.csv', 'fixed-pitch.csv'))
    raw = np.asarray(report['observations'])
    cols = {name: i for i, name in enumerate(report['columns'])}
    points = raw[:, cols['output_frame']].astype(int)
    worklet_errors = {field: float(np.max(abs(raw[:, cols[field]] - candidate[field][points])))
                      for field in (*CONTROL_FIELDS, *SYRINX_FIELDS)}
    theory = independent_controls(voice, folded, block)
    errors = {name: float(max(abs(values - candidate[name]))) for name, values in theory.items()}
    values = observations(candidate, pcm, events, spec, rate)
    physical_comparison = {}
    for name in (*CONTROL_FIELDS, *SYRINX_FIELDS):
        delta = abs(candidate[name] - upper[name])
        limit = spec['native_state_absolute_floor'] + spec['native_state_peak_relative_tolerance'] * max(abs(upper[name]))
        exceeds = np.flatnonzero(delta > limit)
        where = int(np.argmax(delta))
        nonzero = np.flatnonzero(delta)
        physical_comparison[name] = {'max_delta': float(delta[where]), 'frame_at_max': where, 'tolerance': float(limit),
                                     'first_outside_tolerance': int(exceeds[0]) if exceeds.size else None,
                                     'first_nonzero': int(nonzero[0]) if nonzero.size else None}
    differential = [value for value in values if value['note'] is not None]
    releases = [values[index]['pcm_rms'] / values[index - 1]['pcm_rms']
                for index, note in enumerate(notes) if note is None]
    compare_start, compare_end = values[1]['frames']
    control_pcm = fixed['pcm_f32'].astype(np.float32)
    upstream_pcm = upper['pcm_f32'].astype(np.float32)
    zero_gate_checks, zero_gate = same_frame_control(voice, folded, spec, artifacts, execute, command, probe)
    checks.update({
        **zero_gate_checks,
        'frames_match_live_keys': [e['held_midi']['note'] for e in events] == notes
            and [e['frame'] for e in events] == expected_frames
            and [e['note'] for e in events_from_report] == notes
            and all(e['contextFrame'] == frame_origin + e['frame'] and e['frame'] % quantum == 0
                    for e in events_from_report)
            and max(map(abs, clock_deltas)) <= spec['relative_event_tolerance_seconds'],
        'continuous_audio_and_observations': rate == voice['sample_rate_hz'] == report['workletSampleRate']
            and len(pcm) == voice['frames'] == len(candidate) == len(upper) == len(fixed)
            and np.array_equal(points, np.minimum(np.arange(stride - 1, len(pcm) + stride - 1, stride), len(pcm) - 1))
            and np.all(np.diff(np.array(report['timing'])[:, 0]) == quantum),
        'replayed_wav_bit_exact': (artifacts / 'midi-songbird.wav').read_bytes() == (artifacts / 'cli.wav').read_bytes(),
        'worklet_replayed_state': max(worklet_errors.values()) <= 1e-12,
        'independent_pitch_mapping_and_glide': octaves == 3
            and errors['target_pitch_hz'] <= spec['pitch_target_absolute_tolerance_hz']
            and errors['pitch_hz'] <= spec['smoothed_pitch_absolute_tolerance_hz'],
        'independent_gate_trajectory': errors['gate'] <= 1e-12 and errors['gate_target'] == 0,
        'upstream_numerical_states': all(row['first_outside_tolerance'] is None for row in physical_comparison.values()),
        'upstream_pcm': float(max(abs(pcm - upstream_pcm))) <= spec['native_pcm_absolute_tolerance'],
        'both_syrinxes_active': all(min(v['left_port_flow_rms_cm3_s'], v['right_port_flow_rms_cm3_s'])
                                  >= spec['minimum_held_both_flow_rms_cm3_s'] for v in differential),
        'stable_gate_and_release': all(v['gate_min'] >= spec['steady_gate_min'] for v in differential)
            and all(v['gate_max'] <= spec['release_gate_max'] for v in values if v['note'] is None)
            and max(releases) <= spec['release_rms_max_ratio'],
        'fixed_pitch_control_keeps_pressure_and_changes_sound': np.array_equal(fixed['gate'], candidate['gate'])
            and np.array_equal(fixed['sac_pressure_dyn_cm2'], candidate['sac_pressure_dyn_cm2'])
            and not np.array_equal(fixed['left_port_flow_cm3_s'][compare_start:compare_end],
                                   candidate['left_port_flow_cm3_s'][compare_start:compare_end])
            and not np.array_equal(pcm[compare_start:compare_end], control_pcm[compare_start:compare_end]),
    })
    return {'checks': {name: bool(value) for name, value in checks.items()}, 'browser': browser['chromium'],
            'sample_rate_hz': rate, 'audio_frames': len(pcm), 'observations': len(points), 'events': events,
            'octaves': octaves, 'expected_pitch_hz': folded, 'relative_event_errors_seconds': clock_deltas,
            'worklet_trace_errors': worklet_errors, 'independent_control_errors': errors,
            'upstream_trace_differences': physical_comparison, 'upstream_pcm_max_delta': float(max(abs(pcm - upstream_pcm))),
            'candidate_windows': values, 'upstream_browser': upper_browser, 'release_to_steady_pcm_rms': releases,
            'same_frame': zero_gate,
            'fixed_pitch_comparison': {'window_frames': [compare_start, compare_end],
                                       'pcm_difference_rms': rms((pcm - control_pcm)[compare_start:compare_end])}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', args.run_id):
        parser.error('実行IDは英数字で始めてください')
    case = read_json(CASE)
    rev = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if rev != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True):
        parser.error('固定上流の取得状態を確認してください')
    baseline = WORKSPACE / 'runs' / case['measurement']['reference_manifest'] / 'manifest.json'
    record = read_json(baseline)
    if record['status'] != 'pass' or record['upstream_revision'] != rev:
        parser.error('鳴禽の持続音の基準実行を確認してください')
    bun = ['bun'] if shutil.which('bun') else ['npx', '--offline', '--yes', '--package=bun@1.4.4', '--', 'bun']
    upstream = [UPSTREAM / name for name in ('src/ui/store.ts', 'src/ui/midi.ts', 'src/ui/components/BestiaryPanel.tsx',
        'src/audio/AudioEngine.ts', 'src/worklet/processor.ts', 'crates/chimera/src/creatures/songbird.rs',
        'crates/chimera/src/creatures/voice.rs', 'crates/chimera/src/airway/network.rs', 'tests/creature-abi.test.ts')]
    inputs = [CASE, PROBE, CAPTURE, baseline, Path(__file__), *web_sources(), *shared.candidate_sources(), *upstream]
    return shared.record_measurement(args.run_id, CASE, inputs, {'case_id': case['id'], 'revision': case['revision'],
        'upstream_revision': rev,
        'baseline_manifest_sha256': sha256(baseline)}, lambda out, execute: measure(case, out, execute, bun),
        command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
