"""通常画面のTrumpetを固定上流と照合し、採用フレームを保ってMIDI音番号を交換する。"""

import argparse
import json
import math
from pathlib import Path
import re
import shutil
import subprocess

import numpy as np
import scipy

import measure_elephant_fixed_voice as fixed
import measure_elephant_rumble as rumble
import measure_elephant_trumpet as trumpet
import measure_elephant_valve as valve
import measure_uniform_tube as shared
from measure_songbird_syrinx import CLI
from measure_wasm_fixed import compare_pcm, read_json
from measure_worklet_fixed import ROOT, WEB, web_sources
from measure_worklet_midi_alligator_call import browser_evidence, play_events
from measure_worklet_midi_elephant import CANDIDATE, COMMON_OBSERVED, UPPER
from measure_worklet_midi_songbird import CAPTURE, midi_targets, read_trace, rms
from measure_worklet_seal_sustain import compare_at
from measure_worklet_songbird import read_wave
from upstream_baseline import UPSTREAM, WORKSPACE, sha256

CASE = WORKSPACE / 'cases/worklet-midi-elephant-trumpet.json'


def read_performance(trace, pcm, voice, starts, timing, config, spec):
    rate = voice['sample_rate_hz']
    sound = timing[0]['midi_call']['id']
    keys = spec[f'{sound}_keys']
    call_id = rumble.control_plans(spec)[sound]['id']
    sample_times = config[f'{sound}_curve_observation_seconds']
    stride = config['control_frames']
    ends = np.flatnonzero(np.diff(trace['call_id']) < 0) + 1
    natural_end = int(ends[0]) if len(ends) == 1 else None
    lip_goal = rumble.interpolator(keys['lip_pitch_hz'], keys.get('exponential_into_seconds', ()))
    fields = ('target_lip_pitch_hz', 'lip_pitch_hz', 'gate_goal', 'gate', 'mode', 'reed_drive_dyn_cm2',
              'reed_opening_cm2', 'trunk_valve_area_cm2', 'trunk_valve_flow_cm3_s', 'nasal_cm3_s')
    curves = []
    for i, start in enumerate(starts):
        next_call = starts[i + 1] if i + 1 < len(starts) else len(pcm)
        for seconds in sample_times:
            frame = start + math.ceil(seconds * rate / stride) * stride
            row = {'start_frame': start, 'output_frame': frame, 'requested_seconds': seconds}
            if frame < next_call and trace['call_id'][frame] == call_id:
                row.update({key: float(trace[key][frame]) for key in fields})
                row['expected_lip_pitch_hz'] = float(lip_goal((frame - start) / rate))
            elif i + 1 < len(starts) and frame >= next_call:
                row['status'] = '次のコールで置き換え'
            else:
                row['status'] = 'コールの観測範囲外'
            curves.append(row)
    releases = []
    for event in timing:
        if event['midi_call']['pressed']:
            continue
        a, b = (event['frame'] + round(t * rate) for t in config['release_window_seconds'])
        if not 0 <= a < b <= len(pcm):
            raise ValueError('離鍵後の測定窓が出力範囲外です')
        rows = trace[a:b]
        releases.append({'frames': [a, b], 'call_ids': np.unique(rows['call_id']).astype(int).tolist(),
                         'minimum_gate': float(rows['gate'].min()), 'pcm_rms': rms(pcm[a:b]),
                         'reed_opening_range_cm2': float(np.ptp(rows['reed_opening_cm2'])),
                         'valve_area_range_cm2': float(np.ptp(rows['trunk_valve_area_cm2'])),
                         'nasal_ac_rms_cm3_s': float(np.std(rows['nasal_cm3_s'])),
                         'nasal_flow_rms_cm3_s': rms(rows['nasal_cm3_s']),
                         'oral_flow_rms_cm3_s': rms(rows['oral_cm3_s'])})
    count = len(sample_times)
    checks = {
        'valve_targets_follow_same_curve_on_both_keys': all(
            abs(row['target_lip_pitch_hz'] - row['expected_lip_pitch_hz']) <= config['lip_pitch_tolerance_hz']
            for row in curves if 'status' not in row)
            and [row['status'] for row in curves if 'status' in row] == ['次のコールで置き換え']
            and all(curves[i]['target_lip_pitch_hz'] == keys['lip_pitch_hz'][0][1] for i in (0, count)),
        'held_notes_leave_glottal_pitch_at_performer_value': np.all(trace['target_pitch_hz'] == voice['shape']['pitch_hz']),
        'release_acoustics': all(row['call_ids'] == [call_id] and row['minimum_gate'] >= config['minimum_release_gate']
            and row['pcm_rms'] >= config['minimum_release_pcm_rms']
            and row['nasal_ac_rms_cm3_s'] >= config['minimum_release_nasal_ac_rms_cm3_s']
            and row['reed_opening_range_cm2'] >= config['minimum_release_reed_opening_range_cm2'] for row in releases),
        'returns_to_performer_after_restart': natural_end is not None
            and abs(natural_end - starts[-1] - (keys['gate'][-1][0] + keys['ownership_tail_seconds']) * rate)
                <= config['natural_end_tolerance_control_ticks'] * stride + 1e-8
            and np.array_equal(np.flatnonzero(trace['call_id']), np.arange(starts[0], natural_end))
            and all(np.all(trace[f'target_{key}'][natural_end:] == voice['shape'][key])
                    for key in trumpet.OWNED if key in keys),
    }
    return checks, {'curve_observations': curves, 'release_windows': releases, 'natural_end_frame': natural_end}


def measure(case, spec, source, artifacts, execute, bun, case_path, performance):
    execute([*bun, 'test', 'tests/creature-abi.test.ts'], cwd=UPSTREAM, stdout=artifacts / 'upstream-abi.log')
    execute(['cargo', 'test', '--locked', '-p', 'chimera', '--test', 'creature_realtime', '--test', 'golden_creatures'],
            cwd=UPSTREAM, stdout=artifacts / 'upstream-tests.log')
    execute([*bun, 'run', 'build'], cwd=WEB, stdout=artifacts / 'browser-build.log')
    execute(['node', str(CAPTURE), str(artifacts), str(case_path), str(UPSTREAM)], cwd=WEB)
    payload_path = artifacts / 'midi-elephant-case.json'
    payload = read_json(payload_path)
    voice = payload['elephant_voice']
    frames, rate = voice['frames'], voice['sample_rate_hz']
    wav = artifacts / 'midi-elephant.wav'
    pcm = read_wave(wav, rate, frames)
    report = read_json(artifacts / 'midi-elephant.json')
    browser = read_json(artifacts / 'midi-elephant-browser.json')
    fixture, config = case['input'], case['measurement']
    sound, timeline, events = fixture['call_id'], fixture['events'], voice['events']
    notes = [row['note'] for row in timeline if row['type'] == 'note-on']
    octaves, folded = midi_targets(set(notes), fixture['pitch_range_hz'])
    pitches = [folded[note] for note in notes]
    checks, browser_data = browser_evidence(browser, timeline, pitches, sound, rate, config, creature='elephant')
    starts = [row['frame'] for row in events if row['midi_call']['pressed']]
    observed_pitches = [row['pitch'] for row in browser_data['calls']]
    swap = dict(zip(notes, reversed(notes), strict=True))
    swapped = [row | {'midi_call': row['midi_call'] | {'note': swap[row['midi_call']['note']]}} for row in events]
    swapped_case = artifacts / 'swapped-midi-elephant-case.json'
    swapped_case.write_text(json.dumps(payload | {'elephant_voice': voice | {'events': swapped}}) + '\n')
    execute([*CLI, 'inspect', str(payload_path)], stdout=artifacts / 'cli-inspect.json')
    for prefix, path in (('cli', payload_path), ('swapped-cli', swapped_case)):
        execute([*CLI, 'render-pcm', str(path), str(artifacts / f'{prefix}.wav'), str(artifacts / f'{prefix}.csv'), '109'])
    probe = shared.build_upstream_probe(fixed.PROBE, artifacts, execute, extra_libraries=('serde_json',))
    definition_path = artifacts / f'{sound}-definition.json'
    execute([str(probe), f'--{sound}-definition'], cwd=UPSTREAM, stdout=definition_path)
    definition = read_json(definition_path)
    for prefix, order in (('upstream', observed_pitches), ('swapped-upstream', reversed(observed_pitches))):
        upstream_case = artifacts / f'{prefix}-case.json'
        upstream_case.write_text(json.dumps(payload | {'elephant_voice': voice | {'events': play_events(starts, order, sound)}}) + '\n')
        execute([str(probe), str(upstream_case)], cwd=UPSTREAM, stdout=artifacts / f'{prefix}.csv')

    candidate = read_trace(artifacts / 'cli.csv', CANDIDATE)
    upper = read_trace(artifacts / 'upstream.csv', (*UPPER, 'reed_telemetry'))
    limits = spec['tolerances']
    coord = np.arange(frames)
    native = {key: compare_at(candidate[key], upper[key], fixed.tolerance(key, limits), coord)
              for key in (*fixed.COMMON[1:], *COMMON_OBSERVED)}
    upper_pcm = upper['pcm_f32'].astype(np.float32)
    native_pcm = compare_pcm(pcm, upper_pcm, limits['pcm'])
    shadow_area = float(np.max(upper['shadow_area_error_cm2']))
    input_shape = {'mode': 0.0, 'lip_pitch_hz': 470.0, **voice['shape']}
    independent_case = voice | {'shape': input_shape, 'events': play_events(starts, pitches, sound)}
    expected = rumble.reference_controls(independent_case, spec) | fixed.output_reference(candidate, voice, spec)
    extra_limits = {'decimated': limits['radiation'], 'dc_removed': limits['dc'],
                    'lip_pitch_hz': config['lip_pitch_tolerance_hz'], 'target_lip_pitch_hz': config['lip_pitch_tolerance_hz']}
    independent = {key: compare_at(pcm if key == 'pcm_f32' else candidate[key], expected[key],
                                  extra_limits.get(key, fixed.tolerance(key, limits)), coord) for key in expected}
    reed = valve.compare_state(candidate, independent_case, spec)
    upper_port = np.where(upper['mode'] > spec['threshold_mode'],
                         np.maximum(upper['reed_opening_cm2'], spec['trunk_valve_area_cm2'] * (1 - upper['mode'])),
                         spec['trunk_valve_area_cm2'])
    upper_valve = {
        'effective_port': compare_at(upper['trunk_valve_area_cm2'], upper_port, limits['area'], coord),
        'reed_telemetry': compare_at(upper['reed_telemetry'], np.minimum(1, upper['reed_opening_cm2'] / 1.2),
                                    limits['control'], coord),
    }
    observed = dict(zip(report['columns'], np.asarray(report['observations']).T, strict=True))
    points = observed['output_frame'].astype(int)
    worklet = {key: compare_at(series, candidate[key][points], config['worklet_tolerance'], points)
               for key, series in observed.items() if key not in ('output_frame', 'internal_sample')}
    tape = np.asarray(report['timing'])
    adopted = np.array([row['frame'] for row in events])
    errors = list((adopted - adopted[0]) / rate - [row['seconds'] - timeline[0]['seconds'] for row in timeline])
    midi = report['midiEvents']
    expected_events = [{'id': sound, 'note': event['note'], 'pressed': event['type'] == 'note-on'} for event in timeline]
    stride, quantum = config['observation_stride_frames'], config['quantum_frames']
    hashes = {name: [sha256(artifacts / name), sha256(artifacts / f'swapped-{name}')]
              for name in ('cli.wav', 'cli.csv', 'upstream.csv')}
    physical_checks, observations = performance(candidate, pcm, independent_case, starts, events, config, spec)
    checks.update(physical_checks)
    checks.update({
        'fixed_call_definition': definition['id'] == sound and trumpet.definition_matches(definition, spec[f'{sound}_keys']),
        'voice_shape_and_midi_quantum': input_shape == source['elephant_voice']['shape']
            and octaves == config['octave_shift']
            and [row['midi_call'] for row in events] == expected_events
            and [{'id': row['call'], 'note': row['note'], 'pressed': row['pressed']} for row in midi] == expected_events
            and [row['frame'] for row in midi] == adopted.tolist()
            and all(row['contextFrame'] == tape[0, 0] + row['frame'] and row['frame'] % quantum == 0 for row in midi)
            and max(map(abs, errors)) <= config['maximum_relative_input_error_seconds'],
        'continuous_audio_clock_and_finite_states': rate == fixture['sample_rate_hz'] == report['workletSampleRate']
            and report['factor'] == 1 and frames == round(fixture['capture_seconds'] * rate)
            and np.array_equal(points, np.minimum(np.arange(stride - 1, frames + stride - 1, stride), frames - 1))
            and np.array_equal(observed['internal_sample'], points) and np.all(np.diff(tape[:, 0]) == quantum)
            and all(np.array_equal(trace['frame'], coord) for trace in (candidate, upper))
            and all(np.isfinite(trace[key]).all() for trace in (candidate, upper) for key in trace.dtype.names)
            and all(np.isfinite(series).all() for series in observed.values()),
        'replay_samples_and_observations_match': wav.read_bytes() == (artifacts / 'cli.wav').read_bytes()
            and np.array_equal(pcm.view('u4'), candidate['pcm_f32'].astype(np.float32).view('u4'))
            and all(row['passed'] for row in worklet.values()),
        'fixed_upstream_pcm_and_state': native_pcm['first_frame_over_tolerance'] is None
            and all(row['passed'] for row in native.values()) and shadow_area <= limits['area'],
        'independent_controls_and_output': all(row['passed'] for row in independent.values()),
        'independent_reed_and_upstream_valve': all(row['passed'] for row in (reed | upper_valve).values()),
        'swapping_midi_notes_preserves_every_sample': notes != list(reversed(notes))
            and all(original == control for original, control in hashes.values()),
    })
    return {'checks': {key: bool(value) for key, value in checks.items()}, 'sample_rate_hz': rate, 'frames': frames,
            'chromium': browser['chromium'], 'events': events, 'midi_targets_hz': folded, 'browser': browser_data,
            'relative_event_errors_seconds': errors, 'observations': observations, 'worklet_observations': len(points),
            'worklet_deltas': worklet, 'upstream_deltas': native, 'upstream_pcm': native_pcm,
            'upstream_pcm_different_bits': int(np.count_nonzero(pcm.view('u4') != upper_pcm.view('u4'))),
            'upstream_shadow_area_error_cm2': shadow_area, 'independent_deltas': independent,
            'independent_reed_deltas': reed, 'upstream_valve_deltas': upper_valve, 'counterfactual_hashes': hashes}


def main(case_path=CASE, performance=read_performance, *, driver=Path(__file__), description=__doc__):
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument('run_id')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', args.run_id):
        parser.error('実行IDは英数字で始めてください')
    case = read_json(case_path)
    sound = case['input']['call_id']
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(
            ['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True):
        parser.error('固定上流の取得状態を確認してください')
    source_path = WORKSPACE / 'cases' / case['source_case']
    source = read_json(source_path)
    baseline = WORKSPACE / 'runs' / case['measurement']['baseline_run'] / 'manifest.json'
    evidence = read_json(baseline)
    if (evidence['status'], evidence['upstream_revision'], evidence['case_id']) != (
            'pass', revision, f'worklet-elephant-{sound}'):
        parser.error(f'ゾウの{sound}の基準実行を確認してください')
    ancestors = [WORKSPACE / 'cases' / name for name in source['inherits_measurement']]
    spec = {}
    reference_hashes = {entry['path']: entry['sha256'] for entry in evidence['inputs']}
    for path in (*ancestors, source_path):
        if reference_hashes.get(path.relative_to(ROOT).as_posix()) != sha256(path):
            parser.error(f'{path.name} が固定コールの基準と一致しません')
        item = read_json(path)
        spec.update(item['measurement'])
        if 'lip_reed' in item:
            spec['reed_parameters'] = item['lip_reed']['parameters']
    if spec['control_frames'] != case['measurement']['control_frames']:
        parser.error('基準とMIDIの制御刻みを確認してください')
    bun = ['bun'] if shutil.which('bun') else ['npx', '--offline', '--yes', '--package=bun@1.4.4', '--', 'bun']
    upstream_paths = ('src/ui/store.ts', 'src/ui/midi.ts', 'src/ui/components/BestiaryPanel.tsx',
        'src/audio/AudioEngine.ts', 'src/worklet/processor.ts', 'crates/chimera/src/creatures/elephant.rs',
        'crates/chimera/src/creatures/voice.rs', 'crates/chimera/src/creatures/mammal.rs',
        'crates/chimera/src/sources/valves.rs', 'crates/chimera/src/airway/network.rs',
        'tests/creature-abi.test.ts', 'crates/chimera/tests/golden_creatures.rs', 'crates/chimera/tests/creature_realtime.rs')
    tool_paths = ('measure_elephant_fixed_voice.py', 'measure_elephant_rumble.py', 'measure_elephant_trumpet.py',
        'measure_elephant_valve.py', 'measure_seal_sustain_pcm.py', 'measure_songbird_syrinx.py', 'measure_wasm_fixed.py',
        'measure_worklet_midi_alligator_call.py', 'measure_worklet_midi_elephant.py',
        'measure_worklet_midi_songbird.py', 'measure_worklet_seal_sustain.py', 'measure_worklet_songbird.py')
    inputs = list(dict.fromkeys([case_path, source_path, *ancestors, baseline, fixed.PROBE, CAPTURE,
        Path(__file__), driver, *web_sources(),
        *shared.candidate_sources(), *(UPSTREAM / name for name in upstream_paths),
        *(WORKSPACE / 'tools' / name for name in tool_paths)]))
    details = {'case_id': case['id'], 'revision': case['revision'], 'upstream_revision': revision,
               'baseline_manifest_sha256': sha256(baseline), 'invoked_from': str(Path.cwd()), 'scipy': scipy.__version__}
    return shared.record_measurement(args.run_id, case_path, inputs, details,
        lambda artifacts, execute: measure(case, spec, source, artifacts, execute, bun, case_path, performance),
        command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
