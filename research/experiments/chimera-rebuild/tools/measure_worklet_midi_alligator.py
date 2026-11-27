"""アリゲーターの実ブラウザMIDI、固定版の物理状態、独立式を照合する。"""

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
from measure_worklet_midi_seal import compare_browsers
from measure_worklet_midi_songbird import CAPTURE, midi_targets, read_trace, rms
from measure_worklet_midi_songbird_call import pitch_error_rows
from upstream_baseline import UPSTREAM, WORKSPACE, sha256

CASE = WORKSPACE / 'cases/worklet-midi-alligator.json'
BASE = WORKSPACE / 'cases/alligator-fixed-voice-v2.json'
PROBE = WORKSPACE / 'tools/upstream_alligator_probe.rs'
CONTROL_FIELDS = ('gate', 'pitch_hz', 'target_pitch_hz', 'control_clock_seconds', 'call_id', 'oral_noise')
ACOUSTIC_FIELDS = ('lung_pressure_dyn_cm2', 'glottis_drive_dyn_cm2', 'glottis_area_cm2',
                   'glottis_flow_cm3_s', 'glottis_voicing', 'glottis_phase', 'glottis_f0_hz',
                   'velum_area_cm2', 'wall_cm3_s', 'oral_cm3_s', 'nasal_cm3_s', 'radiation_cm3_s2')
TRACE_FIELDS = ('sample', 'frame', 'pcm_f32', *CONTROL_FIELDS, *ACOUSTIC_FIELDS)


def fixed_events(voice, observed):
    rows = []
    for event, state in zip(voice['events'], observed, strict=True):
        held = event['held_midi']['note'] is not None
        settings = {'frame': event['frame'], 'gate': float(held)}
        if held:
            settings['params'] = {'pitch_hz': state['pitch']}
        rows.append(settings)
    return rows


def independent_controls(voice, folded, config, reference):
    stride = config['control_frames']
    dt = stride / voice['sample_rate_hz']
    gate_inputs = [{'frame': e['frame'], 'gate': float(e['held_midi']['note'] is not None)} for e in voice['events']]
    settings = {'control_frames': stride, 'attack_seconds': reference['gate_attack_seconds'],
                'release_seconds': reference['gate_release_seconds']}
    gate, gate_target = gate_reference({**voice, 'events': gate_inputs}, settings)
    pitch, pitch_target = np.zeros(voice['frames']), np.zeros(voice['frames'])
    target_hz = voice['shape']['pitch_hz']
    log_current = math.log(target_hz)
    keep = math.exp(-dt / config['pitch_smoothing_seconds'])
    cursor = iter(voice['events'])
    event = next(cursor, None)
    for frame in range(0, voice['frames'], stride):
        while event is not None and event['frame'] <= frame:
            note = event['held_midi']['note']
            if note is not None:
                target_hz = folded[note]
            event = next(cursor, None)
        log_current = keep * log_current + (1 - keep) * math.log(target_hz)
        pitch[frame:frame + stride], pitch_target[frame:frame + stride] = math.exp(log_current), target_hz
    pressure = voice['shape']['pressure_cm_h2o'] * reference['cm_h2o_to_dyn_cm2'] * gate
    return {'gate': gate, 'gate_target': gate_target, 'pitch_hz': pitch, 'target_pitch_hz': pitch_target,
            'lung_pressure_dyn_cm2': pressure}


def observe_windows(trace, pcm, events, config, rate, factor):
    rows = []
    for event in events:
        note = event['held_midi']['note']
        key = 'steady_window_seconds' if note is not None else 'release_window_seconds'
        a, b = [event['frame'] + round(t * rate) for t in config[key]]
        window = trace[a * factor:b * factor]
        if len(window) != (b - a) * factor:
            raise ValueError(f'MIDIイベント {event["frame"]} の計測窓が範囲外です')
        rows.append({'note': note, 'frames': [a, b],
                     'pitch_hz': float(np.median(window['pitch_hz'])),
                     'glottis_f0_hz': float(np.median(window['glottis_f0_hz'])),
                     'glottis_area_peak_cm2': float(window['glottis_area_cm2'].max()),
                     'gate_min': float(window['gate'].min()), 'gate_max': float(window['gate'].max()),
                     'wall_rms_cm3_s': rms(window['wall_cm3_s']), 'oral_rms_cm3_s': rms(window['oral_cm3_s']),
                     'nasal_rms_cm3_s': rms(window['nasal_cm3_s']), 'pcm_rms': rms(pcm[a:b])})
    return rows


def reference_deltas(candidate, upper, reference):
    names = {
        'gate': 'gate', 'lung_pressure_dyn_cm2': 'pressure_dyn_cm2', 'glottis_drive_dyn_cm2': 'pressure_dyn_cm2',
        'glottis_area_cm2': 'area_cm2', 'glottis_flow_cm3_s': 'flow_cm3_s', 'glottis_voicing': 'voicing',
        'glottis_phase': 'phase', 'glottis_f0_hz': 'f0_hz', 'velum_area_cm2': 'area_cm2',
        'wall_cm3_s': 'flow_cm3_s', 'oral_cm3_s': 'flow_cm3_s', 'nasal_cm3_s': 'flow_cm3_s',
        'radiation_cm3_s2': 'radiation_cm3_s2', 'pitch_hz': 'f0_hz', 'target_pitch_hz': 'f0_hz',
        'call_id': 'gate', 'control_clock_seconds': 'gate', 'oral_noise': 'gate',
    }
    return {k: pitch_error_rows(candidate[k], upper[k], reference['tolerances'][names[k]],
                                coordinate='internal_sample') for k in names}


def worklet_deltas(candidate, observed, points, factor):
    deltas = {}
    for key in (*CONTROL_FIELDS, 'gate_target', 'decimated', 'dc_removed'):
        indexes = (points + 1) * factor - 1
        deltas[key] = float(max(abs(observed[key] - candidate[key][indexes])))
    for phase in range(factor):
        for key in ACOUSTIC_FIELDS:
            name = f'{key}_{phase}'
            deltas[name] = float(max(abs(observed[name] - candidate[key][points * factor + phase])))
    return deltas


def measure(case, artifacts, execute, bun):
    execute([*bun, 'test', 'tests/creature-abi.test.ts'], cwd=UPSTREAM)
    execute([*bun, 'run', 'build'], cwd=WEB, stdout=artifacts / 'browser-build.log')
    execute(['node', str(CAPTURE), str(artifacts), str(CASE), str(UPSTREAM)], cwd=WEB)
    path = artifacts / 'midi-alligator-case.json'
    voice = read_json(path)['alligator_voice']
    browser = read_json(artifacts / 'midi-alligator-browser.json')
    report = read_json(artifacts / 'midi-alligator.json')
    rate, pcm = wavfile.read(artifacts / 'midi-alligator.wav')
    fixture, config = case['input'], case['measurement']
    notes = config['expected_held_notes']
    octaves, folded = midi_targets(set(notes) - {None}, fixture['pitch_range_hz'])
    checks, browser_windows = compare_browsers(browser, fixture['events'], notes, folded, config, rate, 'alligator')

    cli = ['cargo', 'run', '--locked', '--release', '-p', 'vocal-cli', '--']
    execute([*cli, 'inspect', str(path)], stdout=artifacts / 'cli-inspect.json')
    execute([*cli, 'render-pcm', str(path), str(artifacts / 'cli.wav'), str(artifacts / 'cli.csv'), '109'])
    normalized = artifacts / 'upstream-case.json'
    normalized.write_text(json.dumps({'alligator_voice': {**voice, 'events': fixed_events(voice, browser['upstream']['events'])}})
                          + '\n')
    probe = shared.build_upstream_probe(PROBE, artifacts, execute, extra_libraries=('serde_json',))
    execute([str(probe), str(normalized)], cwd=UPSTREAM, stdout=artifacts / 'upstream.csv')

    candidate = read_trace(artifacts / 'cli.csv', (*TRACE_FIELDS, 'gate_target', 'decimated', 'dc_removed'))
    upper = read_trace(artifacts / 'upstream.csv', (*TRACE_FIELDS, 'shadow_area_cm2'))
    reference = read_json(BASE)['measurement']
    factor = report['factor']
    native = reference_deltas(candidate, upper, reference)
    native_pcm_max = float(max(abs(pcm - upper['pcm_f32'][factor - 1::factor].astype(np.float32))))
    shadow_max = float(max(upper['shadow_area_cm2']))
    theory = independent_controls(voice, folded, config, reference)
    tolerances = {'gate': config['gate_tolerance'], 'gate_target': 0, 'pitch_hz': config['smoothed_pitch_tolerance_hz'],
                  'target_pitch_hz': config['target_pitch_tolerance_hz'],
                  'lung_pressure_dyn_cm2': config['pressure_tolerance_dyn_cm2']}
    exact_control = {key: pitch_error_rows(candidate[key], np.repeat(value, factor), tolerances[key],
                                          coordinate='internal_sample') for key, value in theory.items()}
    _, dc, independent_pcm = independent_output(candidate['radiation_cm3_s2'], rate, factor, voice['level'], reference['output'])
    output = {'dc_removed': float(max(abs(dc - candidate['dc_removed'][factor - 1::factor]))),
              'pcm': float(max(abs(independent_pcm - pcm)))}

    rows = np.asarray(report['observations']).T
    observed = dict(zip(report['columns'], rows, strict=True))
    points = observed['output_frame'].astype(int)
    worklet = worklet_deltas(candidate, observed, points, factor)
    events = voice['events']
    adopted = np.array([e['frame'] for e in events])
    origin = report['timing'][0][0]
    relative_error = list((adopted - adopted[0]) / rate - [e['seconds'] - fixture['events'][0]['seconds'] for e in fixture['events']])
    windows = observe_windows(candidate, pcm, events, config, rate, factor)
    release_ratios = [row['pcm_rms'] / windows[i - 1]['pcm_rms'] for i, row in enumerate(windows) if row['note'] is None]
    stride, quantum = config['observation_stride_frames'], config['quantum_frames']
    checks.update({
        'adopted_midi_matches_case_and_clocks': [e['held_midi']['note'] for e in events] == notes
            and [e['note'] for e in report['midiEvents']] == notes
            and [e['frame'] for e in report['midiEvents']] == adopted.tolist()
            and all(e['contextFrame'] == origin + e['frame'] and e['frame'] % quantum == 0 for e in report['midiEvents'])
            and max(map(abs, relative_error)) <= config['maximum_relative_input_error_seconds'],
        'continuous_worklet_and_expected_frames': rate == fixture['sample_rate_hz'] == report['workletSampleRate']
            and len(pcm) == voice['frames'] and len(candidate) == len(upper) == len(pcm) * factor
            and np.array_equal(points, np.minimum(np.arange(stride - 1, len(pcm) + stride - 1, stride), len(pcm) - 1))
            and np.array_equal(observed['internal_sample'], (points + 1) * factor - 1)
            and np.all(np.diff(np.array(report['timing'])[:, 0]) == quantum),
        'browser_replay_keeps_pcm_and_state': (artifacts / 'midi-alligator.wav').read_bytes() == (artifacts / 'cli.wav').read_bytes()
            and max(worklet.values()) <= 1e-12,
        'independent_mapping_gate_and_lung_pressure': octaves == config['octave_shift']
            and all(row['first_outside_tolerance'] is None for row in exact_control.values()),
        'fixed_upper_acoustics_and_pcm': all(row['first_outside_tolerance'] is None for row in native.values())
            and native_pcm_max <= config['native_pcm_tolerance'] and shadow_max <= reference['tolerances']['shadow_area_cm2'],
        'phonation_keeps_gate_and_release_decays': all(
            (row['gate_min'] >= config['steady_gate_minimum'] and row['glottis_area_peak_cm2'] >= config['minimum_glottis_area_peak_cm2']
             and row['pcm_rms'] >= config['minimum_steady_pcm_rms']) if row['note'] is not None
            else row['gate_max'] <= config['release_gate_maximum'] for row in windows)
            and max(release_ratios) <= config['maximum_release_pcm_ratio'],
        'independent_radiation_to_pcm': output['pcm'] <= config['native_pcm_tolerance']
            and output['dc_removed'] <= reference['tolerances']['dc_removed'],
    })
    return {'checks': {key: bool(value) for key, value in checks.items()}, 'sample_rate_hz': rate,
            'audio_frames': len(pcm), 'observations': len(points), 'factor': factor, 'chromium': browser['chromium'],
            'events': events, 'pitch_targets_hz': folded, 'relative_event_errors_seconds': relative_error,
            'difference_sample_coordinate': 'internal_sample',
            'upstream_native_deltas': native, 'upstream_pcm_max_delta': native_pcm_max, 'shadow_area_max_delta_cm2': shadow_max,
            'worklet_observation_deltas': worklet, 'independent_control_deltas': exact_control, 'independent_output_deltas': output,
            'candidate_windows': windows, 'fixed_browser_windows': browser_windows, 'release_pcm_ratios': release_ratios}


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
    baseline = read_json(reference)
    if baseline['status'] != 'pass' or baseline['upstream_revision'] != revision        or baseline['case_id'] != 'worklet-alligator-fixed-voice':
        parser.error('アリゲーターの固定発声の基準実行を確認してください')
    bun = ['bun'] if shutil.which('bun') else ['npx', '--offline', '--yes', '--package=bun@1.4.4', '--', 'bun']
    upstream = [UPSTREAM / name for name in ('src/ui/store.ts', 'src/ui/midi.ts', 'src/ui/components/BestiaryPanel.tsx',
        'src/audio/AudioEngine.ts', 'src/worklet/processor.ts', 'crates/chimera/src/creatures/alligator.rs',
        'crates/chimera/src/creatures/voice.rs', 'crates/chimera/src/creatures/mammal.rs', 'tests/creature-abi.test.ts')]
    inputs = [CASE, BASE, PROBE, CAPTURE, Path(__file__), reference, *web_sources(), *shared.candidate_sources(), *upstream]
    inputs.extend(WORKSPACE / 'tools' / name for name in ('measure_seal_sustain_pcm.py', 'measure_worklet_midi_seal.py',
                  'measure_worklet_midi_songbird.py', 'measure_worklet_midi_songbird_call.py'))
    return shared.record_measurement(args.run_id, CASE, inputs, {'case_id': case['id'], 'revision': case['revision'],
        'upstream_revision': revision, 'baseline_manifest_sha256': sha256(reference)},
        lambda out, execute: measure(case, out, execute, bun), command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
