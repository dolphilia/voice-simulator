"""画面で実際に適用したビート操作をCLIと固定上流で再実行する。"""

import argparse
import json
from pathlib import Path
import re
import shutil

import numpy as np
from scipy.io import wavfile

import measure_beatbox_pattern as pattern
import measure_wasm_fixed as wasm
from measure_worklet_beatbox import CAPTURE, WEB, compare_states, record_experiment
from upstream_baseline import UPSTREAM, WORKSPACE, sha256

CASE = WORKSPACE / 'cases/worklet-live-beatbox.json'


def read_trace(path, columns, frames):
    data = np.genfromtxt(path, delimiter=',', names=True, usecols=['frame', *columns])
    if not np.array_equal(data['frame'], np.arange(frames)) or not all(
            np.isfinite(data[name]).all() for name in data.dtype.names):
        raise ValueError('比較時系列のフレーム数または有限性が条件と一致しません')
    return data


def compare_reservations(config, replayed, upstream, frames):
    iterations, events = pattern.transport.predict(config, frames)
    rate = config['beatbox_pattern']['voice']['output_sample_rate_hz']
    limits = config['measurement']
    tol = limits['seconds_absolute_tolerance']
    quantum = limits['scheduler_block_frames']
    reserved = [row for cycle in iterations for row in cycle['reservations']]
    actual = replayed['reservations']
    plans, max_error = pattern.timing.compare([row['step'] for row in actual], [row['step'] for row in reserved], tol)
    clock_differences = []
    for observed, expected in zip(actual, reserved):
        boundary = abs(expected['clock_seconds'] + limits['horizon_seconds'] - expected['step']['hit_seconds']) <= tol
        delta = observed['frame'] - expected['frame']
        if (delta != 0 and (not boundary or delta != quantum)
                or abs(observed['clock_seconds'] - observed['frame']/rate) > tol):
            clock_differences.append({'expected': expected, 'observed_frame': observed['frame']})
    event_diff, _ = pattern.timing.compare(replayed['transport_events'], events, tol)
    upper_time = [{key: row[key] for key in ('frame', 'clock_seconds')} for row in events]
    upper_diff, _ = pattern.timing.compare(upstream['transport_events'], upper_time, tol)
    for batch in upstream['hits']:
        for gesture in batch['gestures']:
            gesture['targets'] = {pattern.bilabial.KEYS[key]: value for key, value in gesture['targets'].items()}
    batches = [{key: row[key] for key in ('frame', 'clock_seconds', 'gestures')}
               for row in actual if row['gestures'] is not None]
    hit_diff, _ = pattern.timing.compare(batches, upstream['hits'], tol)
    canceled = [row['step']['hit_seconds'] for cycle in iterations if cycle['end'] < frames
                for row in cycle['reservations'] if row['step']['sound'] is not None
                and row['step']['hit_seconds'] >= cycle['end']/rate]
    return dict(plan_difference=plans, max_absolute_error_seconds=max_error, clock_differences=clock_differences,
                event_difference=event_diff, upstream_event_difference=upper_diff, upstream_hit_difference=hit_diff,
                canceled_hits_seconds=canceled, event_clocks=events), iterations


def observe_pcm(pcm, trace, points, rate, stop, restart, spec):
    times = (np.arange(len(pcm)) + 1) / rate
    samples = (points + 1) / rate

    def window(clock, frame, key):
        low, high = spec[key]
        return (clock >= frame/rate + low) & (clock < frame/rate + high)

    def rms(values):
        return float(np.sqrt(np.mean(values.astype('f8')**2)))

    return {
        'early_stop_pcm_peak': float(abs(pcm[window(times, stop, 'early_stop_window_offsets_seconds')]).max()),
        'quiet_stop_pcm_rms': rms(pcm[window(times, stop, 'quiet_stop_window_offsets_seconds')]),
        'quiet_stop_gate_max': float(trace['gate'][window(samples, stop, 'quiet_stop_window_offsets_seconds')].max()),
        'restart_voice_pcm_rms': rms(pcm[window(times, restart, 'restart_voice_window_offsets_seconds')]),
    }


def measure(source, case, artifacts, execute, bun):
    spec = case['measurement']
    config = wasm.read_json(source)
    limits = config['measurement']
    execute([*bun, 'run', 'build'], cwd=WEB, stdout=artifacts / 'browser-build.log')
    binary = artifacts / 'vocal_wasm.wasm'
    shutil.copyfile(WORKSPACE / wasm.WASM, binary)
    execute(['node', str(CAPTURE), str(artifacts), str(CASE), str(source)])
    report = wasm.read_json(artifacts / 'browser.json')
    browser = wasm.read_json(artifacts / 'browser-run.json')
    export = artifacts / 'browser-case.json'
    replay = wasm.read_json(export)
    # 固定上流の観測器にホスト幅と判定用の設定を渡す。CLIには保存したファイルをそのまま渡す。
    registered = {**replay, 'measurement': limits}
    comparison = artifacts / 'comparison-case.json'
    comparison.write_text(json.dumps(registered, ensure_ascii=False, indent=2) + '\n')
    settings, trace_path, outputs = pattern.capture(export, limits['host_block_frames'], artifacts, execute,
                                                      upstream_case_path=comparison)
    execute(['cargo', 'test', '--locked', '--release', '-p', 'chimera-wasm', '--test', 'realtime'],
            cwd=UPSTREAM, stdout=artifacts / 'upstream-wasm-tests.log')
    plan = wasm.read_json(settings)
    upstream_plan = wasm.read_json(artifacts / 'upstream-plan.json')
    frames = spec['output_frames']
    quantum = spec['expected_render_quantum_frames']
    stride = spec['observation_stride_frames']
    rate, pcm = wavfile.read(artifacts / 'browser.wav')
    wave, index, upper_path = outputs[0]
    native_rate, native_pcm = wavfile.read(wave)
    upper_pcm = np.fromfile(upper_path, dtype='<f4')
    if (rate != spec['output_rate_hz'] or native_rate != rate
            or any(data.shape != (frames,) or data.dtype != np.float32 for data in (pcm, native_pcm, upper_pcm))):
        raise ValueError('PCMのレート、長さまたは型が条件と一致しません')
    pcm_cli = wasm.compare_pcm(pcm, native_pcm, spec['pcm_absolute_tolerance'])
    pcm_upper = wasm.compare_pcm(pcm, upper_pcm, spec['pcm_absolute_tolerance'])
    fields = spec['observed_fields']
    native = read_trace(trace_path, [*fields, 'beat_step', 'beat_next_step'], frames)
    upper = read_trace(artifacts / 'upstream-trace.csv', [*fields, 'beat_step'], frames)
    points = np.minimum(np.arange(stride, frames + stride, stride), frames) - 1
    rows = np.asarray(report['observations'])
    names = report['columns']
    if (rows.shape != (len(points), len(names)) or not np.isfinite(rows).all()
            or names[:2] != ['output_frame', 'frames_rendered']
            or not set([*fields, 'beat_step', 'beat_next_step']).issubset(names)):
        raise ValueError('ブラウザの観測列、観測点数または有限性が条件と一致しません')
    values = {name: rows[:, i] for i, name in enumerate(names)}
    states = {key: values[key] for key in fields}
    cli_states = compare_states(states, native, points, spec)
    upper_states = compare_states(states, upper, points, spec)
    events = report['beatEvents']
    commands = [{key: value for key, value in row.items() if key not in ('frame', 'contextFrame')} for row in events]
    exported = replay['beatbox_pattern']
    operation_spec = spec['commands']
    expected_cmds = [row['operation'] for row in operation_spec]
    if commands != expected_cmds:
        raise ValueError(f'実際に適用した操作が登録条件と一致しません ({events})')
    stops = [event['frame'] for event in events if event['type'] == 'playing' and not event['playing']]
    restarts = [event['frame'] for event in events if event['type'] == 'playing' and event['playing']]
    stop, restart = stops[0], restarts[0]
    if not 0 < stop < restart < frames or restart - stop <= rate * spec['quiet_stop_window_offsets_seconds'][1]:
        raise ValueError(f'停止後の測定窓に再開が重なりました ({stop}, {restart})')
    reservation, epochs = compare_reservations(registered, plan['beatbox_pattern'], upstream_plan, frames)
    early, late, _ = pattern.transport.tracks({'episodes': epochs}, frames, rate,
                                              len(limits['expected_slot_sounds']), limits['seconds_absolute_tolerance'])
    positions = values['beat_step']
    paused = (points >= stop) & (points < restart)
    acoustics = observe_pcm(pcm, values, points, rate, stop, restart, spec)
    live = report['realtime']
    blocks = np.asarray(live['blocks'], dtype='f8')
    starts = np.arange(0, frames, quantum)
    if blocks.shape != (len(starts), 5) or not np.isfinite(blocks).all():
        raise ValueError('描画量子の採取件数または有限性が条件と一致しません')
    budget = 1000 * quantum / rate
    durations = blocks[:, 3]
    p50, p95, p99 = np.quantile(durations, [0.5, 0.95, 0.99])
    context_origin = report['firstContextFrame']
    ref = config['beatbox_pattern']
    checks = {
        'normal_ui_saved_the_served_binary': browser['readyAgain'] and not browser['errors']
        and browser['servedWasmSha256'] == sha256(binary),
        'export_matches_input_and_applied_operations': (
            all(exported[key] == value for key, value in ref.items() if key not in ('events', 'render_end_seconds'))
            and exported['render_end_seconds'] == frames/rate
            and replay['upstream_revision'] == case['upstream_revision']
            and exported['events'] == [{k: v for k, v in event.items() if k != 'contextFrame'} for event in events]
            and plan['case'] == replay
        ),
        'commands_in_registered_ranges_and_at_quantum_starts': all(
            spec_row['request_after_seconds'] <= event['frame']/rate <= spec_row['latest_apply_seconds']
            and event['frame'] % quantum == 0 and event['contextFrame'] == context_origin + event['frame']
            for spec_row, event in zip(operation_spec, events, strict=True)
        ) and all(a['frame'] < b['frame'] for a, b in zip(events, events[1:])),
        'startup_and_continuous_context_frames': (
            live['contextState'] == 'running' and live['scheduledContextFrame'] == context_origin
            and context_origin == live['armedContextFrame'] + spec['lead_frames']
            and report['discontinuities'] == 0 and report['callbacks'] == len(starts)
            and report['outputFrames'] == report['framesRendered'] == frames
            and report['workletSampleRate'] == rate and report['observationStride'] == stride
            and report['shortestQuantum'] == report['longestQuantum'] == quantum
            and np.array_equal(blocks[:, 0], starts + context_origin) and np.all(blocks[:, 1] == quantum)
            and np.array_equal(blocks[:, 2], np.minimum(starts + quantum, frames))
            and np.array_equal(rows[:, 0], points) and np.array_equal(rows[:, 1], points + 1)
        ),
        'registered_audio_callback_budget': (
            np.all(durations >= 0) and p99 <= budget * spec['max_p99_process_budget_ratio']
            and report['wasmMemoryGrowths'] <= spec['max_wasm_memory_growths_in_render']
        ),
        'same_pcm_in_browser_and_cli': not spec['require_cli_pcm_bit_equality']
        or pcm_cli['first_bit_difference_frame'] is None,
        'upstream_pcm_within_registered_tolerance': pcm_upper['first_frame_over_tolerance'] is None,
        'native_and_upstream_independent_of_host_partition': all(
            (sha256(candidate_wav), sha256(candidate_index), sha256(upstream_pcm))
            == (sha256(wave), sha256(index), sha256(upper_path))
            for candidate_wav, candidate_index, upstream_pcm in outputs[1:]
        ),
        'independent_reservations_and_upstream_gestures': all(
            not reservation[key] for key in ('plan_difference', 'clock_differences', 'event_difference',
                                            'upstream_event_difference', 'upstream_hit_difference')
        ),
        'matching_playhead_and_rest_positions': (
            np.all((positions == early[points]) | (positions == late[points]))
            and np.array_equal(positions, native['beat_step'][points])
            and np.array_equal(positions, upper['beat_step'][points])
            and np.array_equal(values['beat_next_step'], native['beat_next_step'][points])
        ),
        'matching_sampled_audio_states': all(
            row['first_frame_over_tolerance'] is None for row in (*cli_states.values(), *upper_states.values())
        ),
        'stop_cancels_pending_hits_and_restarts_from_zero': (
            len(reservation['canceled_hits_seconds']) >= spec['minimum_canceled_hits']
            and np.all(positions[paused] == -1)
            and next((step for step in positions[points >= restart] if step >= 0), None) == 0
        ),
        'residual_pcm_decays_and_restart_sounds': (
            acoustics['early_stop_pcm_peak'] >= spec['minimum_early_stop_pcm_peak']
            and acoustics['quiet_stop_pcm_rms'] <= spec['maximum_quiet_stop_pcm_rms']
            and acoustics['quiet_stop_gate_max'] <= spec['maximum_quiet_stop_gate']
            and acoustics['restart_voice_pcm_rms'] >= spec['minimum_restart_pcm_rms']
        ),
    }
    first_restart = next((int(point) for point, step in zip(points, positions) if point >= restart and step >= 0), None)
    return {'checks': {name: bool(value) for name, value in checks.items()},
            'browser_version': browser['version'], 'frames': frames, 'observation_count': len(points),
            'applied_operations': events, 'reservations': reservation, 'pcm_cli': pcm_cli, 'pcm_upstream': pcm_upper,
            'cli_states': cli_states, 'upstream_states': upper_states, 'acoustics': acoustics,
            'first_restart_playhead_frame': first_restart,
            'timing': {'clock': live['timingClock'], 'budget_ms': budget, 'process_p50_ms': float(p50),
                       'process_p95_ms': float(p95), 'process_p99_ms': float(p99),
                       'process_max_ms': float(durations.max()), 'budget_overruns': int(np.sum(durations > budget)),
                       'wasm_memory_growths': report['wasmMemoryGrowths'], 'context_origin': context_origin}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', args.run_id):
        parser.error('実行IDは英数字で始めてください')
    return record_experiment(args.run_id, CASE, measure, (Path(__file__),))


if __name__ == '__main__':
    raise SystemExit(main())
