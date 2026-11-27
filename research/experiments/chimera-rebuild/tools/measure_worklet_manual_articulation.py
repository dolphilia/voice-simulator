"""舌と唇の実時間操作を、適用された時刻で再実行する。"""

import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess

import numpy as np
from scipy.io import wavfile

import measure_articulation as articulation
import measure_pcm_output as pcm
import measure_uniform_tube as shared
import measure_voiced_vowel_motion as motion
import measure_wasm_fixed as wasm
from measure_worklet_fixed import CAPTURE, ROOT, WEB, web_sources
from measure_worklet_realtime import independent_gate, timing_summary
from upstream_baseline import UPSTREAM, WORKSPACE, sha256

CASE = WORKSPACE / 'cases/worklet-manual-articulation.json'
EXPORT_CASE = WORKSPACE / 'cases/worklet-manual-case-export.json'
EXPORT_PROBE = WEB / 'tools/check-manual-replay.ts'
AXES = ('tongue_body_x_cm', 'tongue_body_y_cm', 'lip_aperture_cm')


def expected_replay(case, fixed, report):
    m = case['measurement']
    rate, internal = m['output_rate_hz'], m['internal_rate_hz']
    start, stop = report['startFrame'], report['stopFrame']
    actions = report['articulation']
    frames = report['outputFrames']
    interval = m['control_interval_output_frames']
    quantum = m['render_quantum_frames']
    event_times = [start, *(event['frame'] for event in actions), stop]
    if (len(actions) != len(m['gestures']) or not 0 < start < stop < frames
            or any(not isinstance(frame, int) or frame % quantum for frame in [*event_times, frames])
            or any(right - left < m['minimum_hold_frames']
                   for left, right in zip(event_times, event_times[1:]))):
        raise ValueError(f'操作の順序・適用フレーム・保持区間が登録条件と一致しません ({event_times})')
    targets = dict(zip(AXES, [*fixed['posture']['tongue_body_cm'], fixed['posture']['lip_aperture_cm']], strict=True))
    for expected, action in zip(m['gestures'], actions, strict=True):
        targets[expected['axis']] = expected['value_cm']
        if targets != action['targets']:
            raise ValueError(f'ブラウザが適用した目標が登録値と一致しません ({action})')
    return {
        'id': case['id'], 'upstream_revision': case['upstream_revision'], 'hypothesis': case['hypothesis'],
        'body': fixed['body'], 'posture': fixed['posture'], 'voice': {**fixed['voice'], 'gate': 0},
        'articulators': {
            'sample_rate_hz': internal, 'control_block_samples': interval * (internal // rate),
            'tip_free': True, 'base_weight': 1.0,
            'events': [
                {'frame': start // interval, 'gate': 1},
                *({'frame': event['frame'] // interval, 'targets': event['targets']} for event in actions),
                {'frame': stop // interval, 'gate': 0},
            ],
        },
        'measurement': {'frames': frames // interval},
    }


def check_export_boundary(config, fixed_path, artifacts, execute, bun, cli):
    execute([*bun, str(EXPORT_PROBE), str(EXPORT_CASE), str(fixed_path), str(artifacts)], cwd=WEB)
    limits = config['boundary']
    expected = [{'frame': frame, 'gate': gate}
                for frame, gate in zip(limits['expected_control_frames'], (1, 0), strict=True)]
    targets = [dict(zip(AXES, limits[name], strict=True)) for name in ('targets_at_start_cm', 'targets_at_stop_cm')]
    combined = [{**event, 'targets': target} for event, target in zip(expected, targets, strict=True)]
    outcomes = {}
    for basename, events in (('boundary-case', combined), ('no-motion-case', expected)):
        path = artifacts / f'{basename}.json'
        inspected = artifacts / f'{basename}-inspect.json'
        execute([*cli, 'inspect', str(path)], stdout=inspected)
        case = wasm.read_json(path)
        settings = wasm.read_json(inspected)
        outcomes[basename] = {'events': case['articulators']['events'], 'output_frames': settings['voice']['frames'],
                              'passed': (case['articulators']['events'] == events
                                         and case['measurement']['frames'] == limits['expected_total_control_frames']
                                         and settings['voice']['frames'] == limits['output_frames']
                                         and settings['case'] == case)}
    outcomes['unaligned_stop'] = wasm.read_json(artifacts / 'export-boundary-result.json')
    error = outcomes['unaligned_stop']['unalignedError']
    checks = {
        'export_same_boundary_events': outcomes['boundary-case']['passed'],
        'export_without_motion': outcomes['no-motion-case']['passed'],
        'export_rejects_unaligned_frame': bool(error and '制御境界' in error),
    }
    return checks, outcomes


def compare_position(rows, points, replay, report, m, artifacts):
    ctl = m['control_interval_output_frames']
    dt = ctl / m['output_rate_hz']
    _, independent = articulation.independent_trace(replay, dt, artifacts / 'independent-articulation.csv')
    errors = {}
    for key in AXES:
        trajectory = independent[points // ctl, articulation.KEYS.index(key), 0]
        errors[key] = float(abs(rows[key] - trajectory).max())

    actions = report['articulation']
    transitions = []
    window = m['settled_window_frames']
    for i, action in enumerate(actions):
        key = m['gestures'][i]['axis']
        start = action['frame']
        stop = actions[i + 1]['frame'] if i + 1 < len(actions) else report['stopFrame']
        before = int(np.searchsorted(points, start)) - 1
        first = before + 1
        target = action['targets'][key]
        settled = (points >= stop - window) & (points < stop)
        settled_error = float(abs(rows[key][settled] - target).max())
        transitions.append({
            'axis': key, 'target_cm': target, 'frame': start,
            'last_prior_position_cm': float(rows[key][before]),
            'first_observed_position_cm': float(rows[key][first]),
            'first_observed_frame': int(points[first]),
            'settled_position_cm': float(np.median(rows[key][settled])),
            'settled_maximum_error_cm': settled_error,
            'passed': bool(target < rows[key][first] < rows[key][before]
                           and settled_error <= m['settled_position_tolerance_cm']),
        })
    lip_event = next(event for event in transitions if event['axis'] == 'lip_aperture_cm')
    index = int(np.searchsorted(points, lip_event['frame']))
    settled_lips = (points >= report['stopFrame'] - window) & (points < report['stopFrame'])
    lip_before = float(rows['lip_minimum_cm2'][index - 1])
    lip_after = float(np.median(rows['lip_minimum_cm2'][settled_lips]))
    area = {'before_cm2': lip_before, 'settled_cm2': lip_after, 'decrease_cm2': lip_before - lip_after}
    return transitions, errors, area


def compare(case, fixed_path, live, artifacts, execute, bun, export_case=None):
    fixed = wasm.read_json(fixed_path)
    m = case['measurement']
    rate, internal, quantum = (m[k] for k in ('output_rate_hz', 'internal_rate_hz', 'render_quantum_frames'))
    execute([*bun, 'run', 'build'], cwd=WEB, stdout=artifacts / 'browser-build.log')
    binary = artifacts / 'vocal_wasm.wasm'
    shutil.copyfile(WORKSPACE / wasm.WASM, binary)
    execute(['node', str(CAPTURE), str(artifacts), str(CASE)])
    report = wasm.read_json(artifacts / 'browser.json')
    browser = wasm.read_json(artifacts / 'browser-run.json')
    browser_rate, audio = wavfile.read(artifacts / 'browser.wav')
    expected = expected_replay(case, fixed, report)
    export_checks, export_info = {}, {}
    if export_case is None:
        replay_path = artifacts / 'replay-case.json'
        replay_path.write_text(json.dumps(expected, ensure_ascii=False, indent=2) + '\n')
        replay = expected
    else:
        (artifacts / 'expected-replay.json').write_text(json.dumps(expected, ensure_ascii=False, indent=2) + '\n')
        replay_path = artifacts / 'browser-case.json'
        replay = wasm.read_json(replay_path)
        expected_settings = {key: value for key, value in expected.items() if key not in ('id', 'hypothesis')}
        settings = {key: value for key, value in replay.items() if key not in ('id', 'hypothesis')}
        config = export_case['measurement']
        export_checks = {
            'export_downloaded_case': (browser.get('caseFilename') == config['expected_download_filename']
                                       and replay.get('id') == config['expected_export_id'] and bool(replay.get('hypothesis'))),
            'export_matches_independent_settings': settings == expected_settings,
            'export_uses_wasm_control_interval': report.get('controlIntervalOutputFrames') == config['control_interval_output_frames'],
        }
        export_info = {'filename': browser.get('caseFilename'), 'input_sha256': sha256(replay_path),
                       'events': replay['articulators']['events'], 'total_control_frames': replay['measurement']['frames'],
                       'control_interval_output_frames': report.get('controlIntervalOutputFrames')}
    frames = len(audio)
    if audio.ndim != 1 or audio.dtype != np.float32 or frames != report['outputFrames'] or not np.isfinite(audio).all():
        raise ValueError('WAVの形式・フレーム数・有限性が登録条件と一致しません')
    start, stop = report['startFrame'], report['stopFrame']
    trace_path = artifacts / 'native-trace.csv'
    command = ['cargo', 'run', '--locked', '--release', '-p', 'vocal-cli', '--']
    execute([*command, 'inspect', str(replay_path)], stdout=artifacts / 'native-inspect.json')
    execute([*command, 'render', str(replay_path), str(trace_path)])
    block_frames = m['host_block_frames']
    part = pcm.render_blocks(replay_path, {'block_frames': block_frames}, artifacts, execute)
    cli_rate, native = wavfile.read(part[block_frames[0]][0])
    upper, upper_partitions = motion.capture_upstream(replay, {'host_block_sizes': block_frames}, artifacts, execute)
    if export_case is not None:
        boundary_checks, outcomes = check_export_boundary(export_case['measurement'], fixed_path, artifacts, execute, bun, command)
        export_checks.update(boundary_checks)
        export_info['boundary'] = outcomes
        export_checks['export_used_without_modification'] = sha256(replay_path) == export_info['input_sha256']
    factor = internal // rate
    period = replay['articulators']['control_block_samples']
    all_samples = np.arange(frames * factor)
    output_samples = all_samples[factor - 1::factor]
    native_trace = motion.load_track(trace_path, all_samples, period)
    upper_trace = motion.load_track(artifacts / 'upstream-trace.csv', output_samples, period)

    fields = m['observed_fields']
    columns = report['columns']
    points = np.arange(quantum - 1, frames, quantum)
    rows = np.asarray(report['observations'], dtype=float)
    if (rows.shape != (len(points), len(columns)) or not np.isfinite(rows).all()
            or any(field not in columns for field in fields)):
        raise ValueError('ブラウザの観測列・点数・有限性が登録条件と一致しません')
    state = dict(zip(columns, rows.T, strict=True))
    context_base = state['context_frame'][0]
    sampled = np.column_stack([state[key] for key in fields])
    cli_state = wasm.compare_states(sampled, np.column_stack([native_trace[key][output_samples[points]] for key in fields]),
                                    fields, points, m['candidate_trace_peak_relative_tolerance'])
    geometry = (*AXES, 'lip_minimum_cm2', 'oral_minimum_cm2')
    acoustic = [key for key in fields if key not in geometry]
    upper_geometry = {key: motion.compare(state[key], upper_trace[key][points], m['upstream_geometry_absolute_tolerance'])
                      for key in geometry}
    for evidence in upper_geometry.values():
        first = evidence.pop('first_sample_over_tolerance')
        evidence['first_frame_over_tolerance'] = int(points[first]) if first is not None else None
    upper_state = wasm.compare_states(np.column_stack([state[key] for key in acoustic]),
                                      np.column_stack([upper_trace[key][points] for key in acoustic]),
                                      acoustic, points, m['upstream_state_peak_relative_tolerance'])
    cli_pcm = wasm.compare_pcm(audio, native, 0)
    upper_pcm = wasm.compare_pcm(audio, upper, m['upstream_pcm_absolute_tolerance'])
    transitions, position_errors, area = compare_position(state, points, replay, report, m, artifacts)
    before = audio[start + (stop - start) // 8:report['articulation'][0]['frame']]
    final_peak = float(abs(audio[-live['final_silence_window_frames']:]).max())
    gate = independent_gate(points, start, stop, rate, live)
    gate_error = float(abs(state['gate'] - gate).max())
    checks = {
        'real_browser_and_wasm': (report['contextState'] == 'running' and browser['controlsReset']
                                 and not browser['errors'] and browser['servedWasmSha256'] == sha256(binary)),
        'rates_and_frames': (browser_rate == cli_rate == report['sampleRate'] == rate
                             and fixed['fixed_airway']['sample_rate_hz'] == internal
                             and start == live['pre_roll_frames'] and frames == stop + live['release_frames']
                             and report['stopReason'] == 'manual'),
        'render_clock': bool(np.array_equal(state['frames_rendered'], points + 1)
                             and np.array_equal(state['context_frame'], context_base + points + 1 - quantum)
                             and np.all(state['quantum_frames'] == quantum)),
        'cli_pcm_bit_equal': cli_pcm['first_bit_difference_frame'] is None,
        'cli_states': all(evidence['status'] for evidence in cli_state.values()),
        'upstream_pcm': upper_pcm['first_frame_over_tolerance'] is None,
        'upstream_states': all(evidence['status'] for evidence in (*upper_geometry.values(), *upper_state.values())),
        'host_partition_invariance': upper_partitions and all(sha256(a) == sha256(b) for a, b in zip(*part.values(), strict=True)),
        'positions_follow_targets': all(event['passed'] for event in transitions),
        'independent_positions': max(position_errors.values()) <= m['independent_position_tolerance_cm'],
        'lip_area_decreases': area['decrease_cm2'] >= m['minimum_lip_area_decrease_cm2'],
        'independent_gate': gate_error <= m['independent_gate_absolute_tolerance'],
        'voice_and_release': bool(before.size and np.sqrt(np.mean(before.astype(float)**2)) >= live['minimum_steady_rms']
                                  and final_peak <= live['final_silence_peak_max']),
        **export_checks,
    }
    if export_case is not None and export_case['measurement']['require_cli_pcm_bit_equality']:
        export_info['first_cli_pcm_bit_difference'] = cli_pcm['first_bit_difference_frame']
    budget = 1000 * quantum / rate
    memory_frame = report['firstWasmMemoryGrowthFrame']
    maximum_block = int(np.argmax(state['process_ms']))
    return {
        'checks': checks, 'browser': browser['version'], 'rate_hz': rate, 'frames': frames,
        'start_frame': start, 'stop_frame': stop, 'transitions': transitions,
        'frames_observed': len(points), 'cli_pcm': cli_pcm, 'cli_states': cli_state,
        'upstream_pcm': upper_pcm, 'upstream_geometry': upper_geometry, 'upstream_states': upper_state,
        'first_cli_upstream_track_difference': motion.first_exact_difference(native_trace, upper_trace, fields, output_samples),
        'independent_position_maximum_errors_cm': position_errors, 'independent_gate_maximum_error': gate_error,
        'lip_area': area, 'final_pcm_peak': final_peak, 'timing_clock': report['timingClock'],
        'quantum_budget_ms': budget, 'voiced_timing': timing_summary(state['process_ms'][(points >= start) & (points < stop)], budget),
        'wasm_memory_growths': report['wasmMemoryGrowths'], 'stable_wasm_buffers': report['stableWasmBuffers'],
        'first_wasm_memory_growth_frame': memory_frame,
        'first_wasm_memory_growth_block_ms': float(state['process_ms'][memory_frame // quantum]) if memory_frame is not None else None,
        'maximum_processing_block': {'frame': maximum_block * quantum, 'ms': float(state['process_ms'][maximum_block])},
        **({'case_export': export_info} if export_case is not None else {}),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('--case-export', action='store_true', help='画面から保存したケースをCLIに直接渡す')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', args.run_id):
        parser.error('実行IDは英数字で始めてください')
    case = wasm.read_json(CASE)
    export_case = wasm.read_json(EXPORT_CASE) if args.case_export else None
    if export_case is not None and (export_case['manual_case'] != CASE.name
                                    or export_case['upstream_revision'] != case['upstream_revision']):
        raise SystemExit('書き出しケースが参照する基準を確認してください')
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(
            ['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True):
        raise SystemExit('変更のない固定上流版が必要です')
    fixed = WORKSPACE / 'cases' / case['fixed_voice_case']
    live = WORKSPACE / 'cases' / case['realtime_case']
    bun = ['bun'] if shutil.which('bun') else ['npx', '--yes', '--package=bun@1.4.4', '--', 'bun']
    inputs = [CASE, fixed, live, Path(__file__).resolve(), articulation.PROBE, *web_sources(), *shared.candidate_sources(),
              *(Path(tool.__file__) for tool in (articulation, motion, pcm, shared, wasm)),
              *(WORKSPACE / 'tools' / name for name in ('upstream_baseline.py', 'measure_worklet_realtime.py',
                 'measure_worklet_fixed.py', 'measure_junction.py', 'measure_vowel_voice.py'))]
    sources = ['src/ui/components/AnatomyView.tsx', 'src/ui/store.ts', 'src/audio/AudioEngine.ts',
               'src/worklet/processor.ts', 'crates/chimera-wasm/src/lib.rs', 'crates/chimera/src/engine.rs',
               'crates/chimera/src/control/articulators.rs', 'crates/chimera/src/voice/human_voice.rs',
               'crates/chimera/tests/engine.rs', 'tools/e2e.ts']
    registered = CASE
    if export_case is not None:
        registered = EXPORT_CASE
        inputs.extend([EXPORT_CASE, EXPORT_PROBE])
        sources.extend(['crates/chimera-cli/src/render.rs', 'src/show/tele.ts'])
    metadata = {'case_id': (export_case or case)['id'], 'upstream_revision': revision, 'upstream_noise_scale': 0,
                'input_root': '$REPOSITORY', 'node': subprocess.check_output(['node', '--version'], text=True).strip(),
                'bun': subprocess.check_output([*bun, '--version'], text=True).strip(),
                'upstream_source_sha256': {name: sha256(UPSTREAM / name) for name in sources}}
    return shared.record_measurement(
        args.run_id, registered, inputs, metadata,
        lambda out, run: compare(case, fixed, wasm.read_json(live)['measurement'], out, run, bun, export_case),
        command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
