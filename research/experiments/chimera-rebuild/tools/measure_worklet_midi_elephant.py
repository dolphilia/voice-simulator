"""ゾウの持続音を通常画面の仮想MIDIから鳴らし、CLIと固定上流に照合する。"""

import argparse
import json
from math import pi, sqrt
from pathlib import Path
import re
import shutil
import subprocess

import numpy as np
import scipy

import measure_elephant_fixed_voice as fixed
import measure_uniform_tube as shared
from measure_songbird_syrinx import CLI
from measure_wasm_fixed import compare_pcm, read_json
from measure_worklet_fixed import ROOT, WEB, web_sources
from measure_worklet_midi_alligator import fixed_events, independent_controls
from measure_worklet_midi_seal import compare_browsers
from measure_worklet_midi_songbird import CAPTURE, midi_targets, read_trace, rms
from measure_worklet_seal_sustain import compare_at
from measure_worklet_songbird import read_wave
from upstream_baseline import UPSTREAM, WORKSPACE, sha256

CASE = WORKSPACE / 'cases/worklet-midi-elephant.json'
COMMON_OBSERVED = (*fixed.CALL_FIELDS, *fixed.VALVE_FIELDS)
CANDIDATE = (*fixed.CANDIDATE, *COMMON_OBSERVED, 'gate_goal', 'reed_height_cm', 'reed_speed_cm_s')
UPPER = (*fixed.UPPER, *COMMON_OBSERVED)


def lung_onset(trace, upper, start, rate, cells, spec, constants):
    """静止した線形の肺ポートと気管入口の最初の2更新を式で比較する。"""
    length, area, *_ = spec['tubes']['trachea']
    dx, dt, inv_dt = length / cells, 1 / rate, 1 / (1 / rate)
    rho, c = constants['air_density_g_cm3'], spec['sound_speed_cm_s']
    mu, omega = constants['dynamic_viscosity_poise'], 2 * pi * constants['viscosity_reference_hz']
    port = constants['port_length_cm']
    half_lung = constants['fixed_lung_cell_length_cm'] / constants['fixed_lung_cell_area_cm2']
    inertia = rho * port * (1 / area) + 0.5 * rho * (half_lung + dx / area)
    resistance = sqrt(rho * mu * omega / 2) * 2 * sqrt(pi) * port * sqrt(area) * (1 / area)**2 + 0.5 * rho * c / area
    compliance = area * dx / (rho * c * c)
    samples = slice(start, start + 2)
    p0, p1 = map(float, upper['lung_pressure_dyn_cm2'][samples])
    predicted = {}
    for label, linear in (('candidate', inertia / dt), ('upstream', inertia * inv_dt)):
        initial = p0 / (linear + resistance)
        inlet = dt / compliance * initial
        carry = linear * initial if label == 'candidate' else (inertia * initial) * inv_dt
        predicted[label] = [initial, (p1 - inlet + carry) / (linear + resistance)]
    observed = {'candidate': trace['lung_flow_cm3_s'][samples].tolist(), 'upstream': upper['lung_flow_cm3_s'][samples].tolist()}
    delta = {label: max(abs(a - b) for a, b in zip(predicted[label], observed[label], strict=True)) for label in predicted}
    return {'first_frame': start, 'inertance': inertia, 'resistance': resistance, 'inlet_compliance': compliance,
            'predicted_flow_cm3_s': predicted, 'observed_flow_cm3_s': observed, 'max_error_cm3_s': delta,
            'reproduced_rounding_difference': predicted == observed and predicted['candidate'][1] != predicted['upstream'][1]}


def observation_windows(trace, pcm, events, config, rate):
    rows = []
    for event in events:
        note = event['held_midi']['note']
        key = 'steady_window_seconds' if note is not None else 'release_window_seconds'
        start, stop = (event['frame'] + round(t * rate) for t in config[key])
        if not 0 <= start < stop <= len(pcm):
            raise ValueError(f'フレーム {event["frame"]} 周辺の測定窓が範囲外です')
        window = trace[start:stop]
        wraps = np.flatnonzero(np.diff(window['glottis_phase']) < config['phase_wrap_threshold_cycles']) + 1
        rows.append({'note': note, 'frames': [start, stop],
                     'pitch_hz': float(np.median(window['pitch_hz'])),
                     'glottis_f0_hz': float(np.median(window['glottis_f0_hz'])),
                     'glottis_wrap_frames': (start + wraps).tolist(),
                     'glottis_area_peak_cm2': float(window['glottis_area_cm2'].max()),
                     'glottis_flow_rms_cm3_s': rms(window['glottis_flow_cm3_s']),
                     'gate_min': float(window['gate'].min()), 'gate_max': float(window['gate'].max()),
                     'trunk_valve_flow_rms_cm3_s': rms(window['trunk_valve_flow_cm3_s']),
                     'wall_flow_rms_cm3_s': rms(window['wall_cm3_s']),
                     'oral_flow_rms_cm3_s': rms(window['oral_cm3_s']),
                     'nasal_flow_rms_cm3_s': rms(window['nasal_cm3_s']),
                     'pcm_rms': rms(pcm[start:stop])})
    return rows


def measure(case, source, artifacts, execute, bun):
    execute([*bun, 'test', 'tests/creature-abi.test.ts'], cwd=UPSTREAM, stdout=artifacts / 'upstream-abi.log')
    execute(['cargo', 'test', '--locked', '-p', 'chimera', '--test', 'creature_realtime', '--test', 'golden_creatures'],
            cwd=UPSTREAM, stdout=artifacts / 'upstream-tests.log')
    execute([*bun, 'run', 'build'], cwd=WEB, stdout=artifacts / 'browser-build.log')
    execute(['node', str(CAPTURE), str(artifacts), str(CASE), str(UPSTREAM)], cwd=WEB)
    browser = read_json(artifacts / 'midi-elephant-browser.json')
    report = read_json(artifacts / 'midi-elephant.json')
    replay = artifacts / 'midi-elephant-case.json'
    payload = read_json(replay)
    voice = payload['elephant_voice']
    wav = artifacts / 'midi-elephant.wav'
    frames, rate = voice['frames'], voice['sample_rate_hz']
    pcm = read_wave(wav, rate, frames)
    fixture, config, spec = case['input'], case['measurement'], source['measurement']
    notes, events = config['expected_held_notes'], voice['events']
    octaves, folded = midi_targets(set(notes) - {None}, fixture['pitch_range_hz'])
    checks, browser_windows = compare_browsers(browser, fixture['events'], notes, folded, config, rate, 'elephant')

    execute([*CLI, 'inspect', str(replay)], stdout=artifacts / 'cli-inspect.json')
    execute([*CLI, 'render-pcm', str(replay), str(artifacts / 'cli.wav'), str(artifacts / 'cli.csv'), '109'])
    upper_case = artifacts / 'upstream-case.json'
    normalized = fixed_events(voice, browser['upstream']['events'])
    upper_case.write_text(json.dumps({**payload, 'elephant_voice': {**voice, 'events': normalized}}) + '\n')
    probe = shared.build_upstream_probe(fixed.PROBE, artifacts, execute, extra_libraries=('serde_json',))
    execute([str(probe), str(upper_case)], cwd=UPSTREAM, stdout=artifacts / 'upstream.csv')
    candidate = read_trace(artifacts / 'cli.csv', CANDIDATE)
    upper = read_trace(artifacts / 'upstream.csv', UPPER)

    output_frames = np.arange(frames)
    limits = spec['tolerances']
    native_fields = (*fixed.COMMON[1:], *COMMON_OBSERVED)
    native = {key: compare_at(candidate[key], upper[key], fixed.tolerance(key, limits), output_frames)
              for key in native_fields}
    upper_pcm = upper['pcm_f32'].astype(np.float32)
    native_pcm = compare_pcm(pcm, upper_pcm, limits['pcm'])
    shadow_area = float(np.max(upper['shadow_area_error_cm2']))

    independent = independent_controls(voice, folded, config, spec)
    independent['gate_goal'] = independent.pop('gate_target')
    independent |= {key: value for key, value in fixed.control_reference(
        {**voice, 'events': normalized}, spec).items() if key in ('oral_tip_area_cm2', 'velum_area_cm2', 'trunk')}
    independent |= fixed.output_reference(candidate, voice, spec)
    independent_limits = {'gate': config['gate_tolerance'], 'gate_goal': 0.0,
                          'pitch_hz': config['smoothed_pitch_tolerance_hz'],
                          'target_pitch_hz': config['target_pitch_tolerance_hz'],
                          'lung_pressure_dyn_cm2': config['pressure_tolerance_dyn_cm2'],
                          'decimated': limits['radiation'], 'dc_removed': limits['dc']}
    theoretical = {key: compare_at(pcm if key == 'pcm_f32' else candidate[key], value,
                                  independent_limits.get(key, fixed.tolerance(key, limits)), output_frames)
                   for key, value in independent.items()}

    observed = dict(zip(report['columns'], np.asarray(report['observations']).T, strict=True))
    points = observed['output_frame'].astype(int)
    worklet = {key: compare_at(series, candidate[key][points], config['worklet_tolerance'], points)
               for key, series in observed.items() if key not in ('output_frame', 'internal_sample')}
    adopted = np.array([row['frame'] for row in events])
    midi = report['midiEvents']
    timing = np.asarray(report['timing'])
    relative_error = list((adopted - adopted[0]) / rate
                          - [row['seconds'] - fixture['events'][0]['seconds'] for row in fixture['events']])
    stride, quantum = config['observation_stride_frames'], config['quantum_frames']
    windows = observation_windows(candidate, pcm, events, config, rate)
    ratios = [row['pcm_rms'] / windows[i - 1]['pcm_rms'] for i, row in enumerate(windows)
              if row['note'] is None and windows[i - 1]['pcm_rms'] > 0]
    arrival_fields = ('gate', 'trachea_end_pressure_dyn_cm2', 'glottis_flow_cm3_s', 'nasal_base_pressure_dyn_cm2',
                      'trunk_valve_flow_cm3_s', 'trunk_tip_pressure_dyn_cm2', 'nasal_cm3_s')
    arrival = {field: fixed.first_nonzero(candidate[field]) for field in arrival_fields}
    arrivals = list(arrival.values())
    onset = lung_onset(candidate, upper, adopted[0].item(), rate,
                      read_json(artifacts / 'cli-inspect.json')['geometry']['trachea_cells'], spec, config['lung_onset'])
    checks.update({
        'adopted_midi_notes_and_clocks': octaves == config['octave_shift']
            and [row['held_midi']['note'] for row in events] == [row['note'] for row in midi] == notes
            and [row['frame'] for row in midi] == adopted.tolist()
            and all(row['contextFrame'] == timing[0, 0] + row['frame'] and row['frame'] % quantum == 0 for row in midi)
            and max(map(abs, relative_error)) <= config['maximum_relative_input_error_seconds'],
        'continuous_worklet_and_trace_clocks': rate == fixture['sample_rate_hz'] == report['workletSampleRate']
            and report['factor'] == 1 and frames == round(fixture['capture_seconds'] * rate)
            and np.array_equal(points, np.minimum(np.arange(stride - 1, frames + stride - 1, stride), frames - 1))
            and np.array_equal(observed['internal_sample'], points)
            and np.all(np.diff(timing[:, 0]) == quantum)
            and all(np.array_equal(trace['frame'], output_frames) for trace in (candidate, upper)),
        'finite_pcm_and_observations': all(np.isfinite(trace[field]).all() for trace in (candidate, upper)
                                            for field in trace.dtype.names)
            and all(np.isfinite(series).all() for series in observed.values()),
        'browser_wav_and_cli_are_bit_equal': wav.read_bytes() == (artifacts / 'cli.wav').read_bytes()
            and np.array_equal(pcm.view('u4'), candidate['pcm_f32'].astype(np.float32).view('u4')),
        'browser_state_matches_cli': all(row['passed'] for row in worklet.values()),
        'fixed_upstream_state_and_pcm': all(row['passed'] for row in native.values())
            and native_pcm['first_frame_over_tolerance'] is None and shadow_area <= limits['area'],
        'independent_controls_and_output': all(row['passed'] for row in theoretical.values()),
        'independent_lung_onset_two_samples': max(onset['max_error_cm3_s'].values()) <= limits['flow'],
        'steady_phonation_and_release_decay': all(
            (row['gate_min'] >= config['steady_gate_minimum'] and len(row['glottis_wrap_frames']) > 0
             and row['glottis_area_peak_cm2'] >= config['minimum_steady_glottis_peak_cm2']
             and row['pcm_rms'] >= config['minimum_steady_pcm_rms'])
            if row['note'] is not None else row['gate_max'] <= config['release_gate_maximum'] for row in windows)
            and len(ratios) == notes.count(None) and max(ratios) <= config['maximum_release_pcm_ratio'],
        'rumble_valve_fixed_and_nasal_radiation_dominates': np.all(candidate['mode'] == 0)
            and np.all(candidate['reed_drive_dyn_cm2'] == 0)
            and np.max(abs(candidate['trunk_valve_area_cm2'] - config['valve_area_cm2']))
                <= config['valve_area_tolerance_cm2']
            and all(row['nasal_flow_rms_cm3_s'] > config['minimum_nasal_to_oral_rms_ratio'] * row['oral_flow_rms_cm3_s']
                    for row in windows if row['note'] is not None),
        'initial_pressure_reaches_trunk_after_voice_source': None not in arrivals and arrivals[0] == adopted[0]
            and all(a < b for a, b in zip(arrivals[:-2], arrivals[1:-1])) and arrivals[-2] <= arrivals[-1],
    })
    return {'checks': {key: bool(value) for key, value in checks.items()}, 'sample_rate_hz': rate, 'frames': frames,
            'chromium': browser['chromium'], 'events': events, 'midi_targets_hz': folded,
            'relative_event_errors_seconds': relative_error, 'worklet_observations': len(points),
            'worklet_deltas': worklet, 'upstream_deltas': native, 'upstream_pcm': native_pcm,
            'upstream_pcm_different_bits': int(np.count_nonzero(pcm.view('u4') != upper_pcm.view('u4'))),
            'upstream_shadow_area_error_cm2': shadow_area, 'independent_deltas': theoretical,
            'lung_onset': onset,
            'arrival_output_frames': arrival, 'candidate_windows': windows, 'fixed_browser_windows': browser_windows,
            'release_pcm_ratios': ratios}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', args.run_id):
        parser.error('実行IDは英数字で始めてください')
    case = read_json(CASE)
    config = case['measurement']
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(
            ['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True):
        parser.error('固定上流の取得状態を確認してください')
    source_path = WORKSPACE / 'cases' / case['source_case']
    source = read_json(source_path)
    baseline = WORKSPACE / 'runs' / config['baseline_run'] / 'manifest.json'
    evidence = read_json(baseline)
    if (evidence['status'], evidence['upstream_revision'], evidence['case_id']) != (
            'pass', revision, 'worklet-elephant-fixed-voice'):
        parser.error('ゾウの固定発声の基準実行を確認してください')
    if config['control_frames'] != source['measurement']['control_frames']:
        parser.error('固定発声と持続音MIDIの制御間隔を揃えてください')
    bun = ['bun'] if shutil.which('bun') else ['npx', '--offline', '--yes', '--package=bun@1.4.4', '--', 'bun']
    upstream_paths = ('src/ui/store.ts', 'src/ui/midi.ts', 'src/ui/components/BestiaryPanel.tsx',
        'src/audio/AudioEngine.ts', 'src/worklet/processor.ts', 'crates/chimera/src/creatures/elephant.rs',
        'crates/chimera/src/creatures/voice.rs', 'crates/chimera/src/creatures/mammal.rs',
        'crates/chimera/src/sources/glottis.rs', 'crates/chimera/src/airway/network.rs',
        'tests/creature-abi.test.ts', 'crates/chimera/tests/golden_creatures.rs', 'crates/chimera/tests/creature_realtime.rs')
    tool_paths = ('measure_elephant_fixed_voice.py', 'measure_seal_sustain_pcm.py', 'measure_songbird_syrinx.py',
        'measure_worklet_midi_alligator.py', 'measure_worklet_midi_seal.py', 'measure_worklet_midi_songbird.py',
        'measure_worklet_seal_sustain.py', 'measure_worklet_songbird.py', 'measure_wasm_fixed.py')
    inputs = list(dict.fromkeys([CASE, source_path, baseline, fixed.PROBE, CAPTURE, Path(__file__), *web_sources(),
        *shared.candidate_sources(), *(UPSTREAM / name for name in upstream_paths),
        *(WORKSPACE / 'tools' / name for name in tool_paths)]))
    details = {'case_id': case['id'], 'revision': case['revision'], 'upstream_revision': revision,
               'baseline_manifest_sha256': sha256(baseline), 'invoked_from': str(Path.cwd()), 'scipy': scipy.__version__}
    return shared.record_measurement(args.run_id, CASE, inputs, details,
        lambda artifacts, execute: measure(case, source, artifacts, execute, bun), command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
