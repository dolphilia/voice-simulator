"""ゾウのRumbleを通常画面の仮想MIDIで鳴らし、再発音を固定上流に照合する。"""

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
import measure_elephant_rumble as rumble
import measure_uniform_tube as shared
from measure_songbird_syrinx import CLI
from measure_wasm_fixed import compare_pcm, read_json
from measure_worklet_fixed import ROOT, WEB, web_sources
from measure_worklet_midi_alligator_call import browser_evidence, play_events
from measure_worklet_midi_elephant import CANDIDATE, COMMON_OBSERVED, UPPER, lung_onset
from measure_worklet_midi_songbird import CAPTURE, midi_targets, read_trace, rms
from measure_worklet_seal_sustain import compare_at
from measure_worklet_songbird import read_wave
from upstream_baseline import UPSTREAM, WORKSPACE, sha256

CASE = WORKSPACE / 'cases/worklet-midi-elephant-call.json'
HELD = WORKSPACE / 'cases/worklet-midi-elephant.json'


def third_lung_sample(trace, upper, onset, rate, cells, spec, constants, wall):
    """直列枝と壁の流量を含めて、初期3サンプル目の肺流量を求める。"""
    start = onset['first_frame']
    length, area, *_ = spec['tubes']['trachea']
    dx, dt = length / cells, 1 / rate
    inv_area, inv_dt = 1 / area, 1 / dt
    rho, mu = constants['air_density_g_cm3'], constants['dynamic_viscosity_poise']
    visc = sqrt(rho * mu * (2 * pi * constants['viscosity_reference_hz']) / 2)
    inertia, resistance, compliance = (onset[key] for key in ('inertance', 'resistance', 'inlet_compliance'))
    port = {'candidate': inertia / dt, 'upstream': inertia * inv_dt}
    radius_perimeter = 2 * sqrt(pi)
    series = {
        'candidate': (0.5 * rho * (dx / area + dx / area) / dt
                      + visc * (2 * sqrt(pi * area) * dx / area**2)),
        'upstream': (0.5 * rho * (2 * dx * inv_area) * inv_dt
                     + visc * (radius_perimeter * dx * sqrt(area) * inv_area * inv_area)),
    }
    surfaces = {'candidate': 2 * sqrt(pi * area) * dx, 'upstream': radius_perimeter * sqrt(area) * dx}
    observed = {'candidate': float(trace['lung_flow_cm3_s'][start + 2]),
                'upstream': float(upper['lung_flow_cm3_s'][start + 2])}
    lung_pressure = float(upper['lung_pressure_dyn_cm2'][start + 2])
    predicted = {}
    for label, port_per_step in port.items():
        first, second = onset['predicted_flow_cm3_s'][label]
        first_inlet_pressure = dt / compliance * first
        duct = first_inlet_pressure / series[label]
        wall_flow = surfaces[label] * (first_inlet_pressure
            / (wall['mass_g_cm2'] * inv_dt + 0.5 * wall['resistance_dyn_s_cm3']))
        inlet_pressure = first_inlet_pressure + dt / compliance * (second - duct - wall_flow)
        carry = port_per_step * second if label == 'candidate' else (inertia * second) * inv_dt
        flow = (lung_pressure - inlet_pressure + carry) / (port_per_step + resistance)
        predicted[label] = {'flow_cm3_s': flow, 'inlet_pressure_dyn_cm2': inlet_pressure,
                            'duct_flow_cm3_s': duct, 'wall_flow_cm3_s': wall_flow,
                            'carried_pressure_dyn_cm2': carry}
    candidate, source = predicted['candidate'], predicted['upstream']
    substituted = (lung_pressure - candidate['inlet_pressure_dyn_cm2'] + source['carried_pressure_dyn_cm2']) / (
        port['candidate'] + resistance)
    errors = {label: abs(predicted[label]['flow_cm3_s'] - flow) for label, flow in observed.items()}
    return {'frame': start + 2, 'predicted': predicted, 'observed_flow_cm3_s': observed,
            'max_error_cm3_s': errors, 'candidate_with_upstream_carry_cm3_s': substituted,
            'reproduced_rounding_difference': max(errors.values()) == 0 and observed['candidate'] != observed['upstream'],
            'changed_carry_reproduces_upstream': substituted == observed['upstream']}


def bounds(trace, pcm, voice, events, starts, pitches, config, spec):
    rate = voice['sample_rate_hz']
    keys = spec['rumble_keys']
    snapshot_fields = ('call_id', 'pitch_hz', 'target_pitch_hz', 'gate', 'gate_goal', 'mode', 'target_mode',
                       'trunk', 'target_trunk', 'lung_pressure_dyn_cm2', 'glottis_f0_hz', 'glottis_phase',
                       'glottis_area_cm2', 'trunk_valve_area_cm2', 'nasal_cm3_s')
    transitions = [{'frame': frame, 'before': {k: float(trace[k][frame - 1]) for k in snapshot_fields},
                    'after': {k: float(trace[k][frame]) for k in snapshot_fields}} for frame in starts]

    def window(frame, offsets):
        start, end = (frame + round(t * rate) for t in offsets)
        if not 0 <= start < end <= len(pcm):
            raise ValueError(f'フレーム {frame} 周辺の測定窓が範囲外です')
        rows = trace[start:end]
        return {'frames': [start, end], 'gate_min': float(rows['gate'].min()), 'gate_max': float(rows['gate'].max()),
                'call_ids': np.unique(rows['call_id']).astype(int).tolist(), 'pcm_rms': rms(pcm[start:end]),
                'glottis_area_peak_cm2': float(rows['glottis_area_cm2'].max()),
                'trunk_valve_flow_rms_cm3_s': rms(rows['trunk_valve_flow_cm3_s']),
                'oral_flow_rms_cm3_s': rms(rows['oral_cm3_s']), 'nasal_flow_rms_cm3_s': rms(rows['nasal_cm3_s'])}

    releases = [window(event['frame'], config['release_window_seconds']) for event in events
                if not event['midi_call']['pressed']]
    ends = np.flatnonzero(np.diff(trace['call_id']) < 0) + 1
    end = int(ends[0]) if len(ends) == 1 else None
    tail = window(end, config['end_window_seconds']) if end is not None else None
    before, after = (transitions[-1][key] for key in ('before', 'after'))
    phase_step = (after['glottis_phase'] - before['glottis_phase']) % 1.0
    checks = {
        'release_keeps_automatic_breath_and_nasal_radiation': all(
            row['call_ids'] == [1] and row['gate_min'] >= config['minimum_release_gate']
            and row['glottis_area_peak_cm2'] >= config['minimum_release_glottis_peak_cm2']
            and row['pcm_rms'] >= config['minimum_release_pcm_rms']
            and row['nasal_flow_rms_cm3_s'] > config['minimum_nasal_to_oral_rms_ratio'] * row['oral_flow_rms_cm3_s']
            for row in releases),
        'retrigger_resets_envelope_and_preserves_smoothing': all(
            abs(row['after']['target_pitch_hz'] - keys['pitch_hz'][0][1] * pitch / keys['pitch_reference_hz'])
            <= spec['independent_pitch_tolerance_hz'] and row['after']['gate_goal'] == 0
            for row, pitch in zip(transitions, pitches, strict=True))
            and before['gate_goal'] == 1 and before['gate'] >= config['minimum_retrigger_gate_before']
            and config['minimum_retrigger_gate_after'] <= after['gate'] < before['gate']
            and before['pitch_hz'] < after['pitch_hz'] < after['target_pitch_hz']
            and 0 < phase_step <= config['maximum_retrigger_phase_step_cycles'],
        'natural_end_restores_targets_and_breath_decays': tail is not None
            and abs((end - starts[-1]) / rate - (keys['gate'][-1][0] + keys['ownership_tail_seconds']))
                <= config['control_frames'] / rate + spec['tolerances']['control']
            and np.array_equal(np.flatnonzero(trace['call_id']), np.arange(starts[0], end))
            and np.all(trace['gate_goal'][end:] == 0)
            and all(np.all(trace[f'target_{key}'][end:] == voice['shape'][key]) for key in ('pitch_hz', 'mode', 'trunk'))
            and tail['gate_max'] <= config['maximum_post_end_gate']
            and tail['pcm_rms'] <= config['maximum_post_end_pcm_ratio'] * releases[-1]['pcm_rms'],
        'rumble_preserves_fixed_valve': np.all(trace['mode'] == keys['mode'])
            and np.all(trace['trunk_valve_area_cm2'] == spec['trunk_valve_area_cm2'])
            and np.all(trace['reed_drive_dyn_cm2'] == 0),
    }
    return checks, {'start_transitions': transitions, 'retrigger_phase_step_cycles': phase_step,
                    'release_windows': releases, 'natural_end_frame': end, 'post_end_window': tail}


def measure(case, spec, constants, artifacts, execute, bun):
    execute([*bun, 'test', 'tests/creature-abi.test.ts'], cwd=UPSTREAM, stdout=artifacts / 'upstream-abi.log')
    execute(['cargo', 'test', '--locked', '-p', 'chimera', '--test', 'creature_realtime', '--test', 'golden_creatures'],
            cwd=UPSTREAM, stdout=artifacts / 'upstream-tests.log')
    execute([*bun, 'run', 'build'], cwd=WEB, stdout=artifacts / 'browser-build.log')
    execute(['node', str(CAPTURE), str(artifacts), str(CASE), str(UPSTREAM)], cwd=WEB)
    browser = read_json(artifacts / 'midi-elephant-browser.json')
    report = read_json(artifacts / 'midi-elephant.json')
    path = artifacts / 'midi-elephant-case.json'
    payload = read_json(path)
    voice = payload['elephant_voice']
    frames, rate = voice['frames'], voice['sample_rate_hz']
    wav = artifacts / 'midi-elephant.wav'
    pcm = read_wave(wav, rate, frames)
    fixture, config = case['input'], case['measurement']
    sound, timeline, events = fixture['call_id'], fixture['events'], voice['events']
    notes = [row['note'] for row in timeline if row['type'] == 'note-on']
    octaves, folded = midi_targets(set(notes), fixture['pitch_range_hz'])
    pitches = [folded[note] for note in notes]
    checks, browser_data = browser_evidence(browser, timeline, pitches, sound, rate, config, creature='elephant')
    starts = [row['frame'] for row in events if row['midi_call']['pressed']]
    expected = [{'id': sound, 'note': row['note'], 'pressed': row['type'] == 'note-on'} for row in timeline]

    execute([*CLI, 'inspect', str(path)], stdout=artifacts / 'cli-inspect.json')
    execute([*CLI, 'render-pcm', str(path), str(artifacts / 'cli.wav'), str(artifacts / 'cli.csv'), '109'])
    probe = shared.build_upstream_probe(fixed.PROBE, artifacts, execute, extra_libraries=('serde_json',))
    definition_path = artifacts / 'rumble-definition.json'
    execute([str(probe), '--rumble-definition'], cwd=UPSTREAM, stdout=definition_path)
    definition = read_json(definition_path)
    upstream_case = artifacts / 'upstream-case.json'
    upper_events = play_events(starts, [row['pitch'] for row in browser_data['calls']], sound)
    upstream_case.write_text(json.dumps({**payload, 'elephant_voice': {**voice, 'events': upper_events}}) + '\n')
    execute([str(probe), str(upstream_case)], cwd=UPSTREAM, stdout=artifacts / 'upstream.csv')
    candidate = read_trace(artifacts / 'cli.csv', CANDIDATE)
    upper = read_trace(artifacts / 'upstream.csv', UPPER)

    output_frames = np.arange(frames)
    limits = spec['tolerances']
    native = {key: compare_at(candidate[key], upper[key], fixed.tolerance(key, limits), output_frames)
              for key in (*fixed.COMMON[1:], *COMMON_OBSERVED)}
    upper_pcm = upper['pcm_f32'].astype(np.float32)
    native_pcm = compare_pcm(pcm, upper_pcm, limits['pcm'])
    shadow_area = float(np.max(upper['shadow_area_error_cm2']))
    input_shape = {'mode': 0.0, 'lip_pitch_hz': 470.0, **voice['shape']}
    timed = {**voice, 'observe_valve': False, 'shape': input_shape, 'events': play_events(starts, pitches, sound)}
    expected_states = rumble.reference_controls(timed, spec) | fixed.output_reference(candidate, voice, spec)
    control_limits = {'pitch_hz': spec['independent_pitch_tolerance_hz'],
                      'target_pitch_hz': spec['independent_pitch_tolerance_hz'],
                      'decimated': limits['radiation'], 'dc_removed': limits['dc']}
    independent = {key: compare_at(pcm if key == 'pcm_f32' else candidate[key], value,
                                   control_limits.get(key, fixed.tolerance(key, limits)), output_frames)
                   for key, value in expected_states.items()}

    observed = dict(zip(report['columns'], np.asarray(report['observations']).T, strict=True))
    points = observed['output_frame'].astype(int)
    worklet = {key: compare_at(series, candidate[key][points], config['worklet_tolerance'], points)
               for key, series in observed.items() if key not in ('output_frame', 'internal_sample')}
    timing, midi = np.asarray(report['timing']), report['midiEvents']
    adopted = np.array([row['frame'] for row in events])
    errors = list((adopted - adopted[0]) / rate - [row['seconds'] - timeline[0]['seconds'] for row in timeline])
    stride, quantum = config['observation_stride_frames'], config['quantum_frames']
    keys = spec['rumble_keys']
    expected_keys = {t: {'gate': value} for t, value in keys['gate']}
    for t, value in keys['pitch_hz']:
        expected_keys[t]['pitch'] = value
    expected_keys[0.0].update(trunk=keys['trunk'], mode=keys['mode'])
    first_pressure = fixed.first_nonzero(candidate['lung_pressure_dyn_cm2'])
    trachea_cells = read_json(artifacts / 'cli-inspect.json')['geometry']['trachea_cells']
    onset = lung_onset(candidate, upper, first_pressure, rate, trachea_cells, spec, constants)
    third = third_lung_sample(candidate, upper, onset, rate, trachea_cells, spec, constants, config['initial_tracheal_wall'])
    acoustic_checks, observations = bounds(candidate, pcm, timed, events, starts, pitches, config, spec)
    checks.update(acoustic_checks)
    checks.update({
        'fixed_envelope_matches_case_keys': definition['id'] == sound and definition['pitchRef'] == keys['pitch_reference_hz']
            and definition['keys'] == [{'t': t, 'v': v} for t, v in expected_keys.items()],
        'live_midi_events_use_audio_clock': octaves == config['octave_shift']
            and [row['midi_call'] for row in events] == expected
            and [{'id': row['call'], 'note': row['note'], 'pressed': row['pressed']} for row in midi] == expected
            and [row['frame'] for row in midi] == adopted.tolist()
            and all(row['contextFrame'] == timing[0, 0] + row['frame'] and row['frame'] % quantum == 0 for row in midi)
            and max(map(abs, errors)) <= config['maximum_relative_input_error_seconds'],
        'continuous_audio_clock_and_finite_states': rate == fixture['sample_rate_hz'] == report['workletSampleRate']
            and report['factor'] == 1 and frames == round(fixture['capture_seconds'] * rate)
            and np.array_equal(points, np.minimum(np.arange(stride - 1, frames + stride - 1, stride), frames - 1))
            and np.array_equal(observed['internal_sample'], points) and np.all(np.diff(timing[:, 0]) == quantum)
            and all(np.array_equal(trace['frame'], output_frames) for trace in (candidate, upper))
            and all(np.isfinite(trace[key]).all() for trace in (candidate, upper) for key in trace.dtype.names)
            and all(np.isfinite(series).all() for series in observed.values()),
        'replay_wav_bit_equal': wav.read_bytes() == (artifacts / 'cli.wav').read_bytes()
            and np.array_equal(pcm.view('u4'), candidate['pcm_f32'].astype(np.float32).view('u4')),
        'replay_observations_match': all(row['passed'] for row in worklet.values()),
        'fixed_upstream_states_and_pcm': all(row['passed'] for row in native.values())
            and native_pcm['first_frame_over_tolerance'] is None and shadow_area <= limits['area'],
        'independent_call_controls_and_output': all(row['passed'] for row in independent.values()),
        'independent_lung_onset_two_samples': max(onset['max_error_cm3_s'].values()) <= limits['flow'],
        'independent_lung_onset_third_sample': max(third['max_error_cm3_s'].values()) <= limits['flow'],
    })
    return {'checks': {key: bool(value) for key, value in checks.items()}, 'sample_rate_hz': rate,
            'frames': frames, 'chromium': browser['chromium'], 'events': events, 'midi_target_hz': folded,
            'relative_event_errors_seconds': errors, 'browser': browser_data, 'observations': observations,
            'worklet_observations': len(points), 'worklet_deltas': worklet, 'upstream_deltas': native,
            'upstream_pcm': native_pcm, 'upstream_pcm_different_bits': int(np.count_nonzero(pcm.view('u4') != upper_pcm.view('u4'))),
            'upstream_shadow_area_error_cm2': shadow_area, 'independent_deltas': independent,
            'lung_onset': onset, 'third_lung_sample': third}


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
    source = WORKSPACE / 'cases' / case['source_case']
    voice_case = WORKSPACE / 'cases' / config['native_tolerance_source']
    baseline = WORKSPACE / 'runs' / config['baseline_run'] / 'manifest.json'
    evidence = read_json(baseline)
    if (evidence['status'], evidence['upstream_revision'], evidence['case_id']) != (
            'pass', revision, 'worklet-elephant-rumble'):
        parser.error('ゾウのRumbleの基準実行を確認してください')
    spec = read_json(voice_case)['measurement'] | read_json(source)['measurement']
    constants = read_json(HELD)['measurement']['lung_onset']
    bun = ['bun'] if shutil.which('bun') else ['npx', '--offline', '--yes', '--package=bun@1.4.4', '--', 'bun']
    upstream_paths = ('src/ui/store.ts', 'src/ui/midi.ts', 'src/ui/components/BestiaryPanel.tsx',
        'src/audio/AudioEngine.ts', 'src/worklet/processor.ts', 'crates/chimera/src/creatures/elephant.rs',
        'crates/chimera/src/creatures/voice.rs', 'crates/chimera/src/creatures/mammal.rs',
        'crates/chimera/src/sources/glottis.rs', 'crates/chimera/src/airway/network.rs', 'crates/chimera/src/physics.rs',
        'tests/creature-abi.test.ts', 'crates/chimera/tests/golden_creatures.rs', 'crates/chimera/tests/creature_realtime.rs')
    tool_paths = ('measure_elephant_fixed_voice.py', 'measure_elephant_rumble.py', 'measure_seal_sustain_pcm.py',
        'measure_songbird_syrinx.py', 'measure_worklet_midi_alligator_call.py', 'measure_worklet_midi_elephant.py',
        'measure_worklet_midi_songbird.py', 'measure_worklet_seal_sustain.py', 'measure_worklet_songbird.py', 'measure_wasm_fixed.py')
    inputs = list(dict.fromkeys([CASE, HELD, source, voice_case, baseline, fixed.PROBE, CAPTURE, Path(__file__), *web_sources(),
        *shared.candidate_sources(), *(UPSTREAM / name for name in upstream_paths),
        *(WORKSPACE / 'tools' / name for name in tool_paths)]))
    details = {'case_id': case['id'], 'revision': case['revision'], 'upstream_revision': revision,
               'baseline_manifest_sha256': sha256(baseline), 'invoked_from': str(Path.cwd()), 'scipy': scipy.__version__}
    return shared.record_measurement(args.run_id, CASE, inputs, details,
        lambda artifacts, execute: measure(case, spec, constants, artifacts, execute, bun), command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
