"""実ブラウザのアザラシMIDIを、固定上流と独立した呼気・音高の更新式に照合する。"""

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
from measure_seal_sustain_pcm import gate_reference, independent_output
from measure_wasm_fixed import read_json
from measure_worklet_fixed import ROOT, WEB, web_sources
from measure_worklet_midi_songbird import CAPTURE, midi_targets, read_trace, rms
from measure_worklet_midi_songbird_call import pitch_error_rows
from upstream_baseline import UPSTREAM, WORKSPACE, sha256

CASE = WORKSPACE / 'cases/worklet-midi-seal.json'
BASE = WORKSPACE / 'cases/seal-sustain-pcm.json'
PROBE = WORKSPACE / 'tools/upstream_seal_voice_probe.rs'
CONTROL_FIELDS = ('gate', 'pitch_hz', 'target_pitch_hz', 'lung_pressure_dyn_cm2')
ACOUSTIC_FIELDS = tuple(f'{key}_{i}' for i in (0, 1) for key in
                        ('glottis_f0_hz', 'glottis_phase', 'glottis_area_cm2', 'wall', 'oral', 'nasal', 'radiation'))
TRACE_FIELDS = ('frame', 'internal_sample', *CONTROL_FIELDS, *ACOUSTIC_FIELDS, 'pcm_f32')


def normalize(voice, browser_events):
    breath_events, pitches = [], []
    for event, observed in zip(voice['events'], browser_events, strict=True):
        frame = event['frame']
        pressed = event['held_midi']['note'] is not None
        breath_events.append({'frame': frame, 'gate': float(pressed)})
        if pressed:
            pitches.append({'frame': frame, 'pitch_hz': observed['pitch']})
    return {**voice, 'breath': {**voice['breath'], 'events': breath_events}, 'events': pitches}


def independent_controls(voice, folded, limits):
    breath = voice['breath']
    block = limits['control_frames']
    dt = block / breath['sample_rate_hz']
    gate_events = [{'frame': e['frame'], 'gate': float(e['held_midi']['note'] is not None)} for e in voice['events']]
    gate, target = gate_reference({**breath, 'events': gate_events}, limits)
    controls = breath['controls']
    # 最初の出力フレームより前に、無呼気の制御を1回行う。
    phase = (controls['pulse_rate_hz'] * dt) % 1
    pitch_target = voice['shape']['pitch_hz']
    log_pitch = math.log(pitch_target)
    retention = math.exp(-dt / .010)
    pitch, targets, pressure = (np.empty(breath['frames']) for _ in range(3))
    changes = iter(voice['events'])
    event = next(changes, None)
    for frame in range(0, breath['frames'], block):
        while event is not None and event['frame'] <= frame:
            note = event['held_midi']['note']
            if note is not None:
                pitch_target = folded[note]
            event = next(changes, None)
        log_pitch = log_pitch * retention + math.log(pitch_target) * (1 - retention)
        phase = (phase + controls['pulse_rate_hz'] * dt) % 1
        half_sine = math.sin(math.pi * phase / controls['duty']) if phase < controls['duty'] else 0
        pulse = 1 - controls['pulse_depth'] + controls['pulse_depth'] * half_sine
        part = slice(frame, frame + block)
        pressure[part] = controls['pressure_cm_h2o'] * 980.665 * gate[frame] * pulse
        pitch[part], targets[part] = math.exp(log_pitch), pitch_target
    return {'gate': gate, 'gate_target': target, 'pitch_hz': pitch, 'target_pitch_hz': targets,
            'lung_pressure_dyn_cm2': pressure}


def compare_browsers(browser, timeline, notes, folded, spec, rate, creature="seal"):
    fixed = browser['upstream']
    if len(fixed['events']) != len(timeline):
        raise ValueError('固定上流のMIDIイベントの個数が一致しません')
    pressed = []
    held_states = []
    rows = []
    target = None
    for raw, note, event in zip(timeline, notes, fixed['events'], strict=True):
        if raw['type'] == 'note-on':
            pressed.append(raw['note'])
        else:
            pressed.remove(raw['note'])
        held_states.append(pressed.copy())
        if note is not None:
            target = folded[note]
        label = 'steady_window_seconds' if note is not None else 'release_window_seconds'
        low, high = [event['clock'] + t for t in spec[label]]
        data = [i for i in fixed['telemetry'] if low <= i['clock'] < high]
        if not data:
            raise ValueError('固定上流のテレメトリの測定窓が空です')
        rows.append({'note': note, 'target_error_hz': abs(event['pitch'] - target),
                     'pitch_median_hz': float(np.median([x['pitch'] for x in data])),
                     'gate_min': min(x['gate'] for x in data), 'gate_max': max(x['gate'] for x in data),
                     'glottis_max': max(x['glottis'] for x in data), 'count': len(data)})
    checks = {
        'normal_midi_through_both_browser_uis': rate == fixed['rate'] and browser['candidate']['afterDisconnect'] == 0
            and all(browser[key]['requests'] == [{'sysex': False}] and not browser[key]['errors']
                    for key in ('candidate', 'upstream')),
        'fixed_browser_tracks_held_keys_and_targets': [e['held'] for e in fixed['events']] == held_states
            and all(e['creature'] == creature and e['keyCall'] is None and not e['hold'] for e in fixed['events'])
            and max(x['target_error_hz'] for x in rows) <= spec['target_pitch_tolerance_hz'],
        'fixed_browser_steady_gate_and_release': all(
            (row['gate_min'] >= spec['steady_gate_minimum'] and row['glottis_max'] > 0
             and abs(row['pitch_median_hz'] - folded[row['note']]) <= spec['browser_pitch_tolerance_hz'])
            if row['note'] is not None else row['gate_max'] <= spec['browser_release_gate_maximum'] for row in rows),
    }
    return checks, rows


def summarize_windows(trace, pcm, events, spec, rate):
    rows = []
    for event in events:
        note = event['held_midi']['note']
        label = 'steady_window_seconds' if note is not None else 'release_window_seconds'
        a, b = [event['frame'] + round(t * rate) for t in spec[label]]
        window = trace[a:b]
        if len(window) != b - a:
            raise ValueError(f'MIDIイベント {event["frame"]} の計測窓が範囲外です')
        rows.append({'note': note, 'frames': [a, b], 'pitch_hz': float(np.median(window['pitch_hz'])),
                     'glottis_f0_hz': float(np.median(window['glottis_f0_hz_0'])),
                     'glottis_peak_cm2': float(window['glottis_area_cm2_0'].max()),
                     'gate_min': float(window['gate'].min()), 'gate_max': float(window['gate'].max()),
                     'pressure_max_dyn_cm2': float(window['lung_pressure_dyn_cm2'].max()),
                     'pcm_rms': rms(pcm[a:b])})
    return rows


def measure(case, artifacts, execute, bun):
    execute([*bun, 'test', 'tests/creature-abi.test.ts'], cwd=UPSTREAM)
    execute([*bun, 'run', 'build'], cwd=WEB, stdout=artifacts / 'browser-build.log')
    execute(['node', str(CAPTURE), str(artifacts), str(CASE), str(UPSTREAM)], cwd=WEB)
    browser = read_json(artifacts / 'midi-seal-browser.json')
    report = read_json(artifacts / 'midi-seal.json')
    path = artifacts / 'midi-seal-case.json'
    voice = read_json(path)['seal_voice']
    events = voice['events']
    spec = case['measurement']
    fixture = case['input']
    rate, pcm = wavfile.read(artifacts / 'midi-seal.wav')
    notes = spec['expected_held_notes']
    octaves, folded = midi_targets(set(notes) - {None}, fixture['pitch_range_hz'])
    checks, browser_windows = compare_browsers(browser, fixture['events'], notes, folded, spec, rate)
    command = ['cargo', 'run', '--locked', '--release', '-p', 'vocal-cli', '--']
    execute([*command, 'inspect', str(path)], stdout=artifacts / 'cli-inspect.json')
    execute([*command, 'render-pcm', str(path), str(artifacts / 'cli.wav'), str(artifacts / 'cli.csv'), '109'])
    upper_path = artifacts / 'upstream-case.json'
    upper_path.write_text(json.dumps({'seal_voice': normalize(voice, browser['upstream']['events'])}) + '\n')
    probe = shared.build_upstream_probe(PROBE, artifacts, execute, extra_libraries=('serde_json',))
    execute([str(probe), str(upper_path)], cwd=UPSTREAM, stdout=artifacts / 'upstream.csv')
    cli = read_trace(artifacts / 'cli.csv', (*TRACE_FIELDS, 'gate_target', 'call_id', 'decimated', 'dc_removed'))
    upper = read_trace(artifacts / 'upstream.csv', (*TRACE_FIELDS, 'shadow_area_error_0', 'shadow_area_error_1'))
    native_stats = {}
    for name in (*CONTROL_FIELDS, *ACOUSTIC_FIELDS):
        tolerance = spec['native_state_absolute_tolerance'] + spec['native_state_relative_tolerance'] * max(abs(upper[name]))
        native_stats[name] = pitch_error_rows(cli[name], upper[name], tolerance)
    upper_pcm_delta = float(max(abs(pcm - upper['pcm_f32'].astype(np.float32))))
    limits = read_json(BASE)['measurement']
    theory = independent_controls(voice, folded, limits)
    tolerances = {'gate': spec['gate_tolerance'], 'gate_target': 0, 'pitch_hz': spec['pitch_tolerance_hz'],
                  'target_pitch_hz': spec['target_pitch_tolerance_hz'],
                  'lung_pressure_dyn_cm2': spec['pressure_tolerance_dyn_cm2']}
    theory_stats = {key: pitch_error_rows(cli[key], values, tolerances[key]) for key, values in theory.items()}
    factor = report['factor']
    raw = np.column_stack([cli[f'radiation_{i}'] for i in range(factor)]).ravel()
    decimated, filtered, independently_rendered = independent_output(raw, rate, factor, voice['level'], limits)
    output_errors = {'decimated': float(max(abs(decimated - cli['decimated']))),
                     'dc_removed': float(max(abs(filtered - cli['dc_removed']))),
                     'pcm': float(max(abs(independently_rendered - pcm)))}

    observations = np.asarray(report['observations'])
    headings = {key: i for i, key in enumerate(report['columns'])}
    points = observations[:, headings['output_frame']].astype(int)
    fields = (*CONTROL_FIELDS, *ACOUSTIC_FIELDS, 'gate_target', 'call_id', 'internal_sample')
    worklet_errors = {key: float(max(abs(observations[:, headings[key]] - cli[key][points]))) for key in fields}
    adopted = np.array([e['frame'] for e in events])
    expected = fixture['events']
    delays = list((adopted - adopted[0]) / rate - [x['seconds'] - expected[0]['seconds'] for x in expected])
    origin = report['timing'][0][0]
    stride, quantum = [spec[k] for k in ('observation_stride_frames', 'quantum_frames')]
    windows = summarize_windows(cli, pcm, events, spec, rate)
    releases = [row['pcm_rms'] / windows[i - 1]['pcm_rms'] for i, row in enumerate(windows) if row['note'] is None]
    shadow_area = max(float(max(upper[f'shadow_area_error_{i}'])) for i in range(factor))
    checks.update({
        'all_live_midi_operations_share_the_render_clock': [e['held_midi']['note'] for e in events] == notes
            and [e['note'] for e in report['midiEvents']] == notes
            and [e['frame'] for e in report['midiEvents']] == adopted.tolist()
            and all(e['contextFrame'] == origin + e['frame'] and e['frame'] % quantum == 0 for e in report['midiEvents'])
            and max(map(abs, delays)) <= spec['maximum_relative_input_error_seconds'],
        'continuous_output_and_observations': rate == fixture['sample_rate_hz'] == report['workletSampleRate']
            and len(pcm) == voice['breath']['frames'] == len(cli) == len(upper)
            and np.array_equal(points, np.minimum(np.arange(stride - 1, len(pcm) + stride - 1, stride), len(pcm) - 1))
            and np.all(np.diff(np.array(report['timing'])[:, 0]) == quantum),
        'same_pcm_from_downloaded_case': (artifacts / 'midi-seal.wav').read_bytes() == (artifacts / 'cli.wav').read_bytes(),
        'same_worklet_and_cli_state': max(worklet_errors.values()) <= 1e-12 and not np.any(cli['call_id']),
        'independent_pitch_breath_and_pressure': octaves == spec['octave_shift']
            and all(row['first_outside_tolerance'] is None for row in theory_stats.values()),
        'phonation_and_release': all(
            (row['gate_min'] >= spec['steady_gate_minimum'] and row['glottis_peak_cm2'] >= spec['minimum_glottis_area_peak_cm2']
             and row['pcm_rms'] >= spec['minimum_steady_pcm_rms']) if row['note'] is not None
            else row['gate_max'] <= spec['release_gate_maximum'] for row in windows)
            and max(releases) <= spec['maximum_release_pcm_ratio'],
        'fixed_rust_acoustics_and_pcm': all(row['first_outside_tolerance'] is None for row in native_stats.values())
            and upper_pcm_delta <= spec['native_pcm_tolerance'] and shadow_area <= 1e-12,
        'independent_radiation_to_pcm': output_errors['pcm'] <= spec['native_pcm_tolerance']
            and output_errors['dc_removed'] <= limits['dc_absolute_tolerance'],
    })
    return {'checks': {key: bool(value) for key, value in checks.items()}, 'chromium': browser['chromium'],
            'audio_frames': len(pcm), 'observations': len(points), 'events': events, 'pitch_hz': folded,
            'relative_event_errors_seconds': delays, 'native_deltas': native_stats, 'worklet_deltas': worklet_errors,
            'independent_control_deltas': theory_stats, 'independent_output_deltas': output_errors,
            'fixed_glottis_shadow_area_max_error_cm2': shadow_area, 'fixed_pcm_max_delta': upper_pcm_delta,
            'candidate_windows': windows, 'fixed_browser_windows': browser_windows, 'release_pcm_ratios': releases}


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
    reference = WORKSPACE / 'runs' / case['measurement']['baseline_run'] / 'manifest.json'
    record = read_json(reference)
    if record['status'] != 'pass' or record['upstream_revision'] != revision or record['case_id'] != 'worklet-seal-sustain':
        parser.error('アザラシの持続音の基準実行を確認してください')
    bun = ['bun'] if shutil.which('bun') else ['npx', '--offline', '--yes', '--package=bun@1.4.4', '--', 'bun']
    upstream = [UPSTREAM / name for name in ('src/ui/store.ts', 'src/ui/midi.ts', 'src/ui/components/BestiaryPanel.tsx',
        'src/audio/AudioEngine.ts', 'src/worklet/processor.ts', 'crates/chimera/src/creatures/seal.rs',
        'crates/chimera/src/creatures/voice.rs', 'crates/chimera/src/airway/network.rs', 'tests/creature-abi.test.ts')]
    sources = [CASE, BASE, PROBE, CAPTURE, Path(__file__), reference, *web_sources(), *shared.candidate_sources(),
               *[WORKSPACE / 'tools' / p for p in ('measure_worklet_midi_songbird.py',
                    'measure_worklet_midi_songbird_call.py', 'measure_seal_sustain_pcm.py')], *upstream]
    return shared.record_measurement(args.run_id, CASE, sources, {'case_id': case['id'], 'revision': case['revision'],
        'upstream_revision': revision, 'baseline_manifest_sha256': sha256(reference)},
        lambda out, execute: measure(case, out, execute, bun), command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
