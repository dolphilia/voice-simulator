"""実時間Workletの開始・停止、PCM、呼気と処理時間を照合する。"""

import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess

import numpy as np
from scipy.io import wavfile
from scipy.signal import firwin, freqz, lfilter

import measure_fixed_airway as fixed_airway
import measure_pcm_output as pcm
import measure_sagittal as sagittal
import measure_uniform_tube as shared
import measure_vowel_voice as vowel
import measure_wasm_fixed as wasm
from measure_worklet_fixed import CAPTURE, ROOT, WEB, web_sources
from upstream_baseline import UPSTREAM, WORKSPACE, sha256

CASES = {
    16000: WORKSPACE / 'cases/worklet-realtime-voice-16000.json',
    32000: WORKSPACE / 'cases/worklet-realtime-voice-32000.json',
    44100: WORKSPACE / 'cases/worklet-realtime-voice-44100.json',
    48000: WORKSPACE / 'cases/worklet-realtime-voice.json',
    96000: WORKSPACE / 'cases/worklet-realtime-voice-96000.json',
}
ALLOCATION_TESTS = {
    16000: 'tests::fixed_rate_render_allocation_profile_16000',
    32000: 'tests::fixed_rate_render_allocation_profile_32000',
    44100: 'tests::fixed_rate_render_allocation_profile',
    96000: 'tests::fixed_rate_render_allocation_profile_96000',
}
PAIRED_ARTIFACTS = ('native-inspect.json', 'native-trace.csv', 'upstream-geometry.csv')


def independent_gate(points, start, stop, rate, limits):
    interval = limits['control_interval_output_frames']
    attack = limits['attack_time_constant_seconds']
    release = limits['release_time_constant_seconds']
    # 内部制御が各イベントの後に初めて動く出力フレーム番号。
    on, off = ((pos + interval - 1) // interval for pos in (start, stop))
    control = points // interval
    held = -np.expm1(-np.clip(control - on + 1, 0, off - on) * (interval / rate) / attack)
    return held * np.exp(-np.maximum(control - off + 1, 0) * (interval / rate) / release)


def timing_summary(values, budget):
    if not values.size:
        return None
    return {'blocks': int(values.size), 'median_ms': float(np.median(values)),
            'p95_ms': float(np.percentile(values, 95)), 'p99_ms': float(np.percentile(values, 99)),
            'maximum_ms': float(values.max()), 'over_budget_blocks': int(np.count_nonzero(values > budget))}


def compare_scored_capture(spec, config, artifacts, browser_run, report, audio, score_fields, stopped):
    """スコアの実時間再生を量子単位で検査し、オフラインの同時刻と照合する。"""
    m = config['measurement']
    rate, quantum, frames = (m[key] for key in ('output_rate_hz', 'expected_render_quantum_frames', 'output_frames'))
    live = report.get('realtime')
    if live is None or live['columns'] != [
        'context_frame', 'quantum_frames', 'frames_rendered', 'process_ms', 'callback_elapsed_ms',
    ]:
        raise ValueError('実時間Workletの量子観測列が登録条件と一致しません')
    blocks = np.asarray(live['blocks'], dtype=float)
    count = (frames + quantum - 1) // quantum
    if blocks.shape != (count, 5) or not np.isfinite(blocks).all():
        raise ValueError('実時間Workletの量子数または有限性が条件外です')
    context_frames, length, rendered, processing, elapsed = blocks.T
    start = live['scheduledContextFrame']
    armed = live['armedContextFrame']
    startup = live['startupFirstContextFrame']
    callbacks = np.arange(count)
    absolute_expected = start + callbacks * quantum
    expected_end = np.minimum(frames, (callbacks + 1) * quantum)
    budget = 1000 * quantum / rate
    warm = spec['timing_exclude_first_blocks']
    timing = {'all': timing_summary(processing, budget), 'warm': timing_summary(processing[warm:], budget)}
    worst = int(np.argmax(processing))
    timing['slowest_block'] = {'output_frame': worst * quantum, 'context_frame': int(context_frames[worst]),
                               'process_ms': float(processing[worst])}
    growth_frame = live['firstWasmMemoryGrowthFrame']
    growths = report['wasmMemoryGrowths']
    if growth_frame is not None and (growth_frame < 0 or growth_frame >= frames or growth_frame % quantum != 0):
        raise ValueError('WASMメモリ増加の時刻が量子境界を外れています')
    offline_rate, offline = wavfile.read(artifacts / 'offline.wav')
    comparison = wasm.compare_pcm(audio, offline, 0)
    offline_report = wasm.read_json(artifacts / 'offline.json')
    offline_browser = browser_run['offline']
    online_observations, offline_observations = (
        np.asarray(item['observations'], dtype=np.float64) for item in (report, offline_report))
    same_state = (
        report['columns'][1:] == offline_report['columns'][1:]
        and np.array_equal(online_observations.view('u8'), offline_observations.view('u8'))
        and all(report[key] == offline_report[key] for key in score_fields))
    return {
        'live_context_and_stop_control': (live['contextState'] == 'running' and stopped
                                          and offline_browser['recovered'] and not offline_browser['errors']
                                          and offline_browser['servedWasmSha256'] == browser_run['servedWasmSha256']),
        'live_start_schedule': (start == armed + spec['lead_frames'] == report['firstContextFrame']
                                and start % quantum == 0 and live['leadCallbacks'] == spec['lead_frames'] // quantum
                                and live['startupCallbacks'] >= spec['startup_contiguous_callbacks']
                                and armed >= startup + spec['startup_contiguous_callbacks'] * quantum),
        'live_context_continuity_and_partial_last_quantum': bool(
            np.array_equal(context_frames, absolute_expected) and (length == quantum).all()
            and np.array_equal(rendered, expected_end) and report['stableWasmBuffers']),
        'live_offline_pcm_and_state': (offline_rate == rate and offline.dtype == np.float32
                                       and comparison['first_bit_difference_frame'] is None and same_state),
        'live_block_timing_budget': bool(
            (processing >= 0).all() and elapsed[0] == 0 and (np.diff(elapsed) >= 0).all()
            and timing['warm'] is not None and timing['warm']['blocks'] >= spec['minimum_timing_blocks']
            and timing['warm']['p99_ms'] <= budget * spec['p99_maximum_quantum_budget_fraction']),
        'live_wasm_memory': (0 <= growths <= spec['maximum_wasm_memory_growths']
                             and (growth_frame is None) == (growths == 0)),
    }, {
        'clock': live['timingClock'], 'quantum_budget_ms': budget, 'timing': timing,
        'context_start_frame': start, 'armed_context_frame': armed,
        'startup_discontinuities': live['startupDiscontinuities'],
        'elapsed_wall_ms': live['elapsedWallMs'], 'maximum_callback_spacing_ms': float(np.diff(elapsed).max()),
        'base_latency_seconds': live['baseLatencySeconds'], 'output_latency_seconds': live['outputLatencySeconds'],
        'wasm_memory_growths': growths, 'first_wasm_memory_growth_frame': growth_frame,
        'offline_pcm': comparison, 'last_quantum_padded_frames': count * quantum - frames,
    }


def read_quantum_allocations(path, marker, frames, quantum, warm):
    row = next((line.partition(marker)[2] for line in path.read_text().splitlines()
                if marker in line), '')
    counts = json.loads(row)
    if len(counts) != (frames + quantum - 1) // quantum or any(
            not isinstance(count, int) or count < 0 for count in counts):
        raise ValueError('ネイティブの割り当て計数が量子数と一致しません')
    return {'total': sum(counts), 'warmed': sum(counts[warm:]),
            'nonzero_quanta': [{'output_frame': i * quantum, 'count': n}
                                for i, n in enumerate(counts) if n]}


def render_replay(source, case, artifacts, execute, start, stop, frames, *, upstream_probe=None):
    # 同じゲートイベントをCLIと上流に適用する。
    m = case['measurement']
    data = wasm.read_json(source)
    rate, internal, quantum = (m[k] for k in ('output_rate_hz', 'internal_rate_hz', 'expected_quantum_frames'))
    data['fixed_airway']['sample_rate_hz'] = internal
    data['voice']['output_sample_rate_hz'] = rate
    data['fixed_airway']['sample_count'] = frames * (internal // rate)
    data['voice']['gate'] = 0
    data['gate_events'] = [{'frame': start, 'goal': 1.0}, {'frame': stop, 'goal': 0.0}]
    replay = artifacts / 'replay-case.json'
    replay.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    commands = artifacts / 'gate-events.txt'
    commands.write_text(f'{start} 1\n{stop} 0\n')
    trace = artifacts / 'native-trace.csv'
    prefix = ['cargo', 'run', '--locked', '--release', '-p', 'vocal-cli', '--']
    execute([*prefix, 'inspect', str(replay)], stdout=artifacts / 'native-inspect.json')
    execute([*prefix, 'render', str(replay), str(trace)])
    blocks = pcm.render_blocks(replay, {'block_frames': [quantum, 77]}, artifacts, execute)
    native_rate, native = wavfile.read(blocks[quantum][0])
    references = [pcm.read_columns(trace, frames)[1]]
    if upstream_probe is None:
        execute(['cargo', 'test', '--locked', '-p', 'chimera', '--test', 'engine'],
                cwd=UPSTREAM, stdout=artifacts / 'upstream-engine.log')
        upstream_probe = shared.build_upstream_probe(vowel.PROBE, artifacts, execute)
    args = [data['measurement']['voice']['ipa'], internal, rate, frames, *(data['voice'][key] for key in
            ('pressure_cm_h2o', 'gate', 'breathiness', 'tension', 'output_gain')), artifacts, commands]
    execute([str(upstream_probe), 'render', *map(str, args)], cwd=UPSTREAM)
    upper = np.fromfile(artifacts / 'upstream-voice.f32', dtype='<f4')
    references.append(pcm.read_columns(artifacts / 'upstream-trace.csv', frames)[1])
    return data, blocks, native_rate, native, upper, references


def acoustic_evidence(audio, data, m, start, stop):
    rate = m['output_rate_hz']
    first = wasm.first_index(abs(audio) > m['onset_threshold'])
    lo, hi = (start + k for k in m['steady_window_relative_frames'])
    steady = audio[lo:hi].astype(float)
    rms = float(np.sqrt(np.mean(steady**2)))
    f0, _ = vowel.independent_yin(steady, rate, data['measurement']['voice'])
    bound = m['expected_f0_hz']
    final_peak = float(abs(audio[-m['final_silence_window_frames']:]).max())
    return {
        'voicing_and_onset': (first is not None and start + m['onset_offset_frames'][0] <= first <=
                start + m['onset_offset_frames'][1] and lo < hi <= stop and rms >= m['minimum_steady_rms']
                and f0 is not None and bound[0] <= f0 <= bound[1]),
        'release_to_silence': final_peak <= m['final_silence_peak_max'],
    }, {'pcm_onset_frame': first, 'pcm_f0_hz': f0, 'steady_rms': rms, 'final_pcm_peak': final_peak}


def compare_airway_geometry(data, m, inspected, artifacts, execute):
    cfg = m['airway']
    rate = m['internal_rate_hz']
    probe_dir = artifacts / 'geometry-probe'
    probe_dir.mkdir()
    probe = shared.build_upstream_probe(sagittal.PROBE, probe_dir, execute)
    path = artifacts / 'upstream-geometry.csv'
    execute([str(probe), '--fixed-airway', str(rate), '0', '0', *sagittal.pose_controls(data)],
            cwd=UPSTREAM, stdout=path)
    upstream, reference = fixed_airway.read_upper_geometry(path)

    tubes = {tube['name']: tube for tube in inspected['tubes']}
    names = [name for name, tube in tubes.items() for _ in range(tube['cells'])]
    sections = inspected['sections']
    if (len(names) != len(sections) or names != [row['tube'] for row in upstream]
            or [row['node'] for row in sections] != list(range(len(names)))):
        return {'airway_registered_topology': False}, {
            'candidate_tubes': names, 'upstream_tubes': [row['tube'] for row in upstream]}
    fields = fixed_airway.FIELDS[:5]
    nodes = [{**tubes[name], **section} for name, section in zip(names, sections, strict=True)]
    candidate = np.asarray([[node[key] for key in fields] for node in nodes])
    if not np.isfinite(candidate).all():
        raise ValueError('CLIの気道形状に非有限値があります')
    delta = np.abs(candidate - reference[:, :len(fields)])
    maximum_length_error = float(delta[:, :3].max())
    maximum_area_error = float(delta[:, 3:].max())

    propagation = 35000 / rate
    design_length = propagation / 0.93
    floor_length = propagation / 0.97
    estimated_cells = {
        'trachea': max(6, int(12.0 / max(design_length, 0.9))),
        'pharynx': max(8, int(7.1 / design_length)),
        'oral': max(8, int(7.3 / design_length)),
        'nasal': max(8, int(11.4 / max(design_length, 0.5))),
        'piriform': max(1, min(3, int(2.0 / design_length))),
        'lungs': 1,
        'sinus': 1,
    }
    measured_cells = {name: tube['cells'] for name, tube in tubes.items()}
    by_tube = {}
    for name, tube in tubes.items():
        if name == 'lungs':
            continue
        predicted_length = tube['anatomical_length_cm']
        if name in ('pharynx', 'oral'):
            predicted_length = max(predicted_length, estimated_cells[name] * floor_length)
        predicted_cell = predicted_length / estimated_cells[name]
        observed_cell = tube['simulation_length_cm'] / tube['cells']
        by_tube[name] = {'cells': tube['cells'], 'cell_length_cm': observed_cell,
                         'predicted_cell_length_cm': predicted_cell, 'courant': propagation / predicted_cell}
    limiting_tube = max(by_tube, key=lambda name: by_tube[name]['courant'])
    estimated_courant = by_tube[limiting_tube]['courant']
    actual_courant, upstream_courant = inspected['courant'], float(upstream[0]['courant'])
    courant_error = max(abs(estimated_courant - actual_courant), abs(estimated_courant - upstream_courant))
    checks = {
        'airway_registered_topology': (measured_cells == estimated_cells == cfg['expected_cells']
            and inspected['node_count'] == len(upstream)
            and inspected['branch_count'] == int(upstream[0]['branch_count'])),
        'airway_sections_match_upstream': (maximum_length_error <= cfg['section_length_absolute_tolerance_cm']
            and maximum_area_error <= cfg['section_area_absolute_tolerance_cm2']),
        'airway_courant_and_limiting_tube': (
            limiting_tube == cfg['expected_limiting_tube']
            and max(actual_courant, upstream_courant, estimated_courant) <= cfg['maximum_courant']
            and courant_error <= cfg['courant_absolute_tolerance']
            and all(abs(t['cell_length_cm'] - t['predicted_cell_length_cm'])
                    <= cfg['section_length_absolute_tolerance_cm'] for t in by_tube.values())),
    }
    return checks, {
        'node_count': inspected['node_count'], 'branch_count': inspected['branch_count'],
        'cells_by_tube': measured_cells, 'tube_geometry': by_tube, 'limiting_tube': limiting_tube,
        'courant': actual_courant, 'upstream_courant': upstream_courant, 'estimated_courant': estimated_courant,
        'courant_maximum_error': courant_error, 'section_length_maximum_error_cm': maximum_length_error,
        'section_area_maximum_error_cm2': maximum_area_error,
    }


def decimator_response_evidence(taps, m):
    cfg = m['decimator_response']
    sample_rate = m['internal_rate_hz']
    passband = np.linspace(0, cfg['passband_end_hz'], 1025)
    _, response = freqz(taps, worN=passband, fs=sample_rate)
    _, stop = freqz(taps, worN=cfg['stopband_probes_hz'], fs=sample_rate)
    passband_error = float(np.abs(np.abs(response) - 1).max())
    gains = np.abs(stop)
    delay = float(np.dot(np.arange(taps.size), taps) / taps.sum())
    return {
        'decimator_passband': passband_error <= cfg['passband_maximum_absolute_error'],
        'decimator_stopband': float(gains.max()) <= cfg['stopband_maximum_gain'],
        'decimator_group_delay': (abs(delay - cfg['group_delay_internal_samples'])
                                   <= m['filter_coefficients_absolute_tolerance']),
    }, {'passband_maximum_absolute_error': passband_error, 'stopband_gains': dict(zip(
        map(str, cfg['stopband_probes_hz']), gains.tolist(), strict=True)),
        'group_delay_internal_samples': delay, 'group_delay_seconds': delay / sample_rate}


def paired_rate_reference(case):
    spec = case['measurement']['paired_output_rate']
    run = WORKSPACE / 'runs' / spec['run_id']
    manifest_path = run / 'manifest.json'
    manifest = wasm.read_json(manifest_path)
    if (sha256(manifest_path) != spec['manifest_sha256'] or manifest['status'] != 'pass'
            or manifest['upstream_revision'] != case['upstream_revision']
            or manifest['case_id'] != spec['case_id'] or not manifest.get('native_only')):
        raise ValueError('比較先レートの固定マニフェストを確認できません')
    hashes = {item['path']: item['sha256'] for item in manifest['outputs']}
    for name in PAIRED_ARTIFACTS:
        path = f'artifacts/{name}'
        if sha256(run / path) != hashes.get(path):
            raise ValueError(f'比較先レートの保存済み出力を照合できません（{path}）')
    return manifest_path, run / 'artifacts'


def compare_paired_rates(m, inspected, trace, artifacts, reference):
    spec = m['paired_output_rate']
    other = wasm.read_json(reference / 'native-inspect.json')
    _, other_trace = pcm.read_columns(reference / 'native-trace.csv', spec['frames'])
    ratio, remainder = divmod(spec['output_rate_hz'], m['output_rate_hz'])
    if ratio < 2 or remainder or spec['frames'] != ratio * m['expected_output_frames']:
        raise ValueError('比較する出力のレートとフレーム数に整数倍の対応がありません')
    events = inspected['case']['gate_events']
    mapped_events = [{**event, 'frame': event['frame'] * ratio} for event in events]
    interval = m['control_interval_output_frames']
    points = np.arange(interval - 1, m['expected_output_frames'], interval)
    mapped_points = ratio * (points + 1) - 1
    gate_error = float(np.abs(trace['gate'][points] - other_trace['gate'][mapped_points]).max())
    same_airway = inspected['fixed_airway'] == other['fixed_airway']
    same_upstream = sha256(artifacts / 'upstream-geometry.csv') == sha256(reference / 'upstream-geometry.csv')
    return {
        'paired_rate_same_time_and_internal_clock': (
            other['voice']['sample_rate_hz'] == spec['output_rate_hz']
            and inspected['case']['fixed_airway'] == other['case']['fixed_airway']
            and inspected['case']['posture'] == other['case']['posture']
            and mapped_events == other['case']['gate_events']
            and np.array_equal(trace['internal_sample'][points], other_trace['internal_sample'][mapped_points])),
        'paired_rate_same_airway': same_airway and same_upstream,
        'paired_rate_gates_at_shared_control_ends': (len(points) == spec['expected_shared_gate_observations']
                                                     and gate_error <= spec['gate_absolute_tolerance']),
    }, {'reference_run': spec['run_id'], 'shared_observations': int(len(points)),
        'gate_maximum_absolute_error': gate_error, 'same_candidate_airway': same_airway,
        'same_upstream_geometry_csv': same_upstream}


def unity_output_evidence(data, m, taps, trace, pcm_path, audio):
    cfg = m['unity_output_stage']
    rate = m['output_rate_hz']
    frames = m['expected_output_frames']
    header, output = pcm.read_columns(pcm_path, frames)
    if header != pcm.OUTPUT_COLUMNS:
        raise ValueError('出力段の観測列が一致しません')
    points = np.arange(frames)
    radiation = trace['radiation_derivative_cm3_s2']
    difference = np.abs(radiation - output['decimated'])
    scaled = data['voice']['output_gain'] * radiation
    dc_pole = np.exp(-2 * np.pi * cfg['dc_corner_hz'] / rate)
    dc = lfilter([1.0], [1.0, -dc_pole], np.diff(scaled, prepend=0.0))
    dc_error = np.abs(dc - output['dc_removed'])
    envelope, held, independent_audio = pcm.independent_limiter(dc, rate)
    envelope_error = np.abs(envelope - output['limiter_envelope'])
    pcm_comparison = wasm.compare_pcm(audio, independent_audio, cfg['pcm_absolute_tolerance'])
    recorded_pcm = wasm.compare_pcm(audio, output['pcm_f32'].astype(np.float32), 0)
    return {
        'unity_tap_and_frame_alignment': (np.array_equal(taps, [1.0])
            and all(np.array_equal(values, points)
                    for values in (output['frame'], output['internal_sample'], trace['internal_sample']))),
        'unity_radiation_passthrough': float(difference.max()) == 0.0,
        'independent_unity_dc_removal': float(dc_error.max()) <= cfg['dc_absolute_tolerance'],
        'independent_unity_limiter_and_pcm': (float(envelope_error.max()) <= cfg['envelope_absolute_tolerance']
            and np.array_equal(held, output['hold_frames'])
            and pcm_comparison['first_frame_over_tolerance'] is None
            and recorded_pcm['first_bit_difference_frame'] is None),
    }, {'taps': taps.tolist(), 'dc_pole': float(dc_pole), 'group_delay_internal_samples': 0,
        'maximum_radiation_error': float(difference.max()),
        'first_radiation_difference_frame': wasm.first_index(difference != 0),
        'maximum_dc_error': float(dc_error.max()),
        'first_dc_difference_over_tolerance': wasm.first_index(dc_error > cfg['dc_absolute_tolerance']),
        'maximum_envelope_error': float(envelope_error.max()),
        'first_hold_difference': wasm.first_index(held != output['hold_frames']),
        'independent_pcm': pcm_comparison, 'recorded_pcm': recorded_pcm}


def compare_native_rate(source, case, artifacts, execute, paired_reference):
    m = case['measurement']
    start, stop, frames = (m[key] for key in ('pre_roll_frames', 'expected_stop_frame', 'expected_output_frames'))
    rate, internal = m['output_rate_hz'], m['internal_rate_hz']
    quantum = m['expected_quantum_frames']
    data, blocks, native_rate, native, upper, (trace, upper_trace) = render_replay(
        source, case, artifacts, execute, start, stop, frames)
    if any(a.dtype != np.float32 or a.shape != (frames,) or not np.isfinite(a).all() for a in (native, upper)):
        raise ValueError('候補と上流のPCMの型、長さ、有限性を確認できません')
    state_fields = m['observed_fields']
    points = np.arange(frames)
    candidate_states = np.column_stack([trace[field] for field in state_fields])
    upstream_states = np.column_stack([upper_trace[field] for field in state_fields])
    states = wasm.compare_states(candidate_states, upstream_states, state_fields, points,
                                 m['upstream_state_peak_relative_tolerance'])
    upper_pcm = wasm.compare_pcm(native, upper, m['upstream_pcm_absolute_tolerance'])
    acoustic_checks, acoustic = acoustic_evidence(native, data, m, start, stop)
    gate_delta = np.abs(independent_gate(points, start, stop, rate, m) - trace['gate'])
    gate_error = float(gate_delta.max())

    inspected = wasm.read_json(artifacts / 'native-inspect.json')
    settings = inspected['voice']
    factor = settings['decimation_factor']
    taps = np.asarray(settings['filter_coefficients'])
    expected_factor = 60000 // rate + 1
    independent_taps = (np.ones(1) if expected_factor == 1 else
                        firwin(m['expected_filter_taps'], 2 * 0.46 / expected_factor, window=('kaiser', 8.5)))
    tap_error = float(np.abs(taps - independent_taps).max()) if taps.shape == independent_taps.shape else None
    sample_indices = factor * (points + 1) - 1
    log = artifacts / 'native-allocations.log'
    execute(['cargo', 'test', '--locked', '-p', 'vocal-wasm', ALLOCATION_TESTS[rate],
             '--', '--exact', '--nocapture'], stdout=log)
    allocations = read_quantum_allocations(log, 'fixed_rate_render_allocations=', frames, quantum,
                                           m['timing_exclude_first_blocks'])
    checks = {
        'same_format_and_events': native_rate == settings['sample_rate_hz'] == rate
            and stop == start + m['maximum_voiced_frames'] and frames == stop + m['release_frames'],
        'decimation_and_control_period': (factor == expected_factor == m['expected_decimation_factor']
            and internal == factor * rate and settings['frames'] == frames
            and settings['control_block_internal_samples'] == factor * m['control_interval_output_frames']
            and all(np.array_equal(t['internal_sample'], sample_indices) for t in (trace, upper_trace))),
        'independent_decimator_coefficients': tap_error is not None and tap_error <= m['filter_coefficients_absolute_tolerance'],
        'cli_partition_invariance': all(sha256(blocks[quantum][i]) == sha256(blocks[77][i]) for i in (0, 1)),
        'upstream_pcm': upper_pcm['first_frame_over_tolerance'] is None,
        'upstream_states': all(value['status'] for value in states.values()),
        'independent_gate': gate_error <= m['independent_gate_absolute_tolerance'],
        'native_render_allocations': allocations['total'] <= m['maximum_native_render_allocations'],
        **acoustic_checks,
    }
    extra = {}
    if 'airway' in m:
        airway_checks, extra['airway'] = compare_airway_geometry(
            data, m, inspected['fixed_airway'], artifacts, execute)
        checks.update(airway_checks)
    if 'decimator_response' in m:
        response_checks, extra['decimator_response'] = decimator_response_evidence(taps, m)
        checks.update(response_checks)
    if 'unity_output_stage' in m:
        unity_checks, extra['unity_output_stage'] = unity_output_evidence(
            data, m, taps, trace, blocks[quantum][1], native)
        checks.update(unity_checks)
    if paired_reference is not None:
        paired_checks, extra['paired_output_rate'] = compare_paired_rates(
            m, inspected, trace, artifacts, paired_reference)
        checks.update(paired_checks)
    return {'checks': checks, 'frames': frames, 'rate_hz': rate, 'internal_rate_hz': internal,
            'start_frame': start, 'stop_frame': stop, 'decimation_factor': factor,
            'control_period_seconds': m['control_interval_output_frames'] / rate,
            'tap_count': len(taps), 'independent_tap_maximum_error': tap_error,
            'first_internal_sample': int(sample_indices[0]), 'last_internal_sample': int(sample_indices[-1]),
            'native_allocations': allocations, 'upstream_pcm': upper_pcm, 'upstream_states': states,
            'independent_gate_maximum_error': gate_error, **acoustic, **extra}


def compare(source, case, case_path, artifacts, execute, bun):
    execute([*bun, 'run', 'build'], cwd=WEB, stdout=artifacts / 'browser-build.log')
    binary = artifacts / 'vocal_wasm.wasm'
    shutil.copyfile(WORKSPACE / wasm.WASM, binary)
    execute(['node', str(CAPTURE), str(artifacts), str(case_path)])
    return compare_capture(source, case, artifacts, execute, binary)


def compare_capture(source, case, artifacts, execute, binary, *, replay=None):
    m = case['measurement']
    rate, internal, quantum = (m[k] for k in ('output_rate_hz', 'internal_rate_hz', 'expected_quantum_frames'))
    report = wasm.read_json(artifacts / 'browser.json')
    browser_run = wasm.read_json(artifacts / 'browser-run.json')
    browser_rate, audio = wavfile.read(artifacts / 'browser.wav')
    start, stop = report['startFrame'], report['stopFrame']
    frames = len(audio)
    if not 0 < start < stop < frames or audio.dtype != np.float32 or audio.ndim != 1:
        raise ValueError('実時間WAVの型、フレーム数または操作時刻が不正です')

    if replay is None:
        replay = render_replay(source, case, artifacts, execute, start, stop, frames)
    data, blocks, native_rate, native, upper, references = replay
    cli_pcm = wasm.compare_pcm(audio, native, 0)
    upper_pcm = wasm.compare_pcm(audio, upper, m['upstream_pcm_absolute_tolerance'])

    fields = m['observed_fields']
    if report['columns'] != ['context_frame', 'quantum_frames', 'process_ms', 'callback_elapsed_ms', 'frames_rendered', *fields]:
        raise ValueError('実時間Workletの観測列が不正です')
    rows = np.asarray(report['observations'], dtype=float)
    points = np.arange(quantum - 1, frames, quantum)
    if rows.shape != (len(points), len(fields) + 5) or not rows.size or not np.isfinite(rows).all():
        raise ValueError('実時間Workletの観測の形状・有限性が条件外です')
    context_base = int(rows[0, 0])
    internal_time = (internal // rate) * (points + 1) - 1
    series = [wasm.compare_states(rows[:, 5:], np.column_stack([table[key][points] for key in fields]),
                                  fields, points, tolerance)
              for table, tolerance in zip(references, (1e-10, m['upstream_state_peak_relative_tolerance']), strict=True)]
    predicted_gate = independent_gate(points, start, stop, rate, m)
    gate_error = float(abs(predicted_gate - rows[:, 5 + fields.index('gate')]).max())
    acoustic_checks, acoustic = acoustic_evidence(audio, data, m, start, stop)
    budget = 1000 * quantum / rate
    warmed = np.arange(len(points)) >= m['timing_exclude_first_blocks']
    processing = rows[:, 2]
    timing = {'voicing': timing_summary(processing[warmed & (points >= start) & (points < stop)], budget),
              'release': timing_summary(processing[points >= stop], budget)}
    callback_elapsed = rows[:, 3]
    gaps = np.diff(callback_elapsed)
    wall_timing = {
        'pcm_duration_ms': 1000 * frames / rate,
        'first_to_last_callback_ms': float(callback_elapsed[-1]),
        'cursor_to_last_block_ms': float(1000 * (frames - quantum) / rate),
        'callback_gaps_ms': timing_summary(gaps, budget),
        'largest_gap_start_frame': int(rows[int(np.argmax(gaps)), 0]) if gaps.size else None,
        'startup_first_context_frame': report['startupFirstContextFrame'],
        'startup_callbacks': report['startupCallbacks'],
        'startup_discontinuities': report['startupDiscontinuities'],
        'worklet_messages_ms': [report['voicingNoticeMs'], report['releaseNoticeMs'], report['elapsedWallMs']],
    }
    frame_gaps = np.diff(rows[:, 0]) - quantum
    first_gap = wasm.first_index(frame_gaps != 0)
    clock_break = None if first_gap is None else {
        'after_context_frame': int(rows[first_gap, 0]),
        'skipped_or_repeated_frames': int(frame_gaps[first_gap]),
    }
    automatic = m.get('automatic_stop', False)
    stop_correct = (
        report['stopReason'] == 'limit' and stop == m['expected_stop_frame']
        and frames == m['expected_output_frames']
    ) if automatic else (
        report['stopReason'] == 'manual' and stop - start >= m['minimum_manual_voiced_frames'])
    checks = {
        'production_context': (report['contextState'] == 'running' and browser_run['controlsReset']
                               and not browser_run['errors'] and browser_run['servedWasmSha256'] == sha256(binary)),
        'same_format_and_events': (rate == browser_rate == native_rate == report['sampleRate']
                and data['id'] == report['caseId'] and internal == data['fixed_airway']['sample_rate_hz']
                and frames == report['outputFrames'] == stop + m['release_frames']
                and start == m['pre_roll_frames'] and stop_correct),
        'no_dsp_frame_gaps': bool(context_base >= 0 and report['stableWasmBuffers']
                and np.array_equal(rows[:, 0], context_base + points + 1 - quantum)
                and np.all(rows[:, 1] == quantum) and np.array_equal(rows[:, 4], points + 1)
                and all(np.array_equal(table['internal_sample'][points], internal_time) for table in references)),
        'cli_pcm_bit_equal': cli_pcm['first_bit_difference_frame'] is None,
        'cli_partition_invariance': all(sha256(blocks[quantum][i]) == sha256(blocks[77][i]) for i in (0, 1)),
        'upstream_pcm': upper_pcm['first_frame_over_tolerance'] is None,
        'states_match': all(result['status'] for values in series for result in values.values()),
        'independent_gate': gate_error <= m['independent_gate_absolute_tolerance'],
        **acoustic_checks,
        'block_timing_budget': (bool(np.all(processing >= 0)) and timing['voicing'] is not None
                and timing['voicing']['blocks'] >= m['minimum_steady_timing_blocks']
                and timing['voicing']['p99_ms'] <= budget * m['p99_maximum_quantum_budget_fraction']
                and timing['release'] is not None),
    }
    runtime = {}
    if automatic:
        timing['all'] = timing_summary(processing, budget)
        timing['pre_roll'] = timing_summary(processing[points < start], budget)
    if 'maximum_wasm_memory_growths' in m:
        if not {'wasmMemoryGrowths', 'firstWasmMemoryGrowthFrame'} <= report.keys():
            raise ValueError('実時間WorkletのWASMメモリ観測が欠けています')
        checks['registered_context_and_internal_rates'] = (
            report['workletSampleRate'] == rate and report['internalSampleRate'] == internal
            and report['controlIntervalOutputFrames'] == m['control_interval_output_frames'])
        growths = report['wasmMemoryGrowths']
        first_growth = report['firstWasmMemoryGrowthFrame']
        checks['render_memory_growth'] = (
            type(growths) is int and 0 <= growths <= m['maximum_wasm_memory_growths']
            and (first_growth is None if growths == 0 else
                 type(first_growth) is int and 0 <= first_growth < frames and first_growth % quantum == 0))
        runtime = {'worklet_rate_hz': report['workletSampleRate'], 'internal_rate_hz': report['internalSampleRate'],
                   'control_interval_output_frames': report['controlIntervalOutputFrames'],
                   'wasm_memory_growths': growths, 'first_wasm_memory_growth_frame': first_growth}
    return {'checks': checks, 'browser': browser_run['version'], 'rate_hz': rate, 'frames': frames,
            'start_frame': start, 'stop_frame': stop, 'clock': report['timingClock'],
            'elapsed_wall_ms': report['elapsedWallMs'], 'first_context_frame': context_base,
            'first_context_clock_break': clock_break,
            'budget_ms': budget, 'timing': timing, 'wall_timing': wall_timing, **acoustic, **runtime,
            'cli_pcm': cli_pcm, 'upstream_pcm': upper_pcm, 'cli_states': series[0], 'upstream_states': series[1],
            'independent_gate_maximum_error': gate_error}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    rates = parser.add_mutually_exclusive_group()
    rates.add_argument('--output-rate', type=int, choices=CASES, default=48000, help='出力サンプルレート（Hz）')
    rates.add_argument('--rate-44100', dest='output_rate', action='store_const', const=44100,
                       help='44.1 kHzの登録条件を実行する')
    parser.add_argument('--native-only', action='store_true', help='ゲート時刻が固定されたケースをCLIで比較する')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', args.run_id):
        parser.error('実行IDは英数字で始めてください')
    if args.native_only and args.output_rate not in ALLOCATION_TESTS:
        parser.error('--native-only にはゲート時刻を登録した出力レートを指定してください')
    case_path = CASES[args.output_rate]
    case = wasm.read_json(case_path)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(
            ['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True):
        raise SystemExit('変更のない固定上流版が必要です')
    source = WORKSPACE / 'cases' / case['fixed_voice_case']
    if 'fixed_voice_sha256' in case and sha256(source) != case['fixed_voice_sha256']:
        parser.error('登録した固定姿勢の入力ハッシュが一致しません')
    source_paths = [case_path, source, Path(__file__).resolve(), vowel.PROBE,
                    *(Path(module.__file__) for module in (pcm, shared, vowel, wasm)),
                    WORKSPACE / 'tools/measure_worklet_fixed.py', WORKSPACE / 'tools/upstream_baseline.py',
                    WORKSPACE / 'tools/measure_junction.py', *shared.candidate_sources()]
    paths = ['crates/chimera/src/voice/human_voice.rs', 'crates/chimera/src/engine.rs',
             'crates/chimera/src/airway/decimator.rs', 'crates/chimera/tests/engine.rs']
    metadata = {'case_id': case['id'], 'upstream_revision': revision, 'input_root': '$REPOSITORY',
                'native_only': args.native_only}
    if 'revision' in case:
        metadata['case_revision'] = case['revision']
    if args.native_only:
        reference = None
        if 'paired_output_rate' in case['measurement']:
            manifest_path, reference = paired_rate_reference(case)
            source_paths.extend([manifest_path, *(reference / name for name in PAIRED_ARTIFACTS)])
        if 'airway' in case['measurement']:
            source_paths.extend([sagittal.PROBE, Path(sagittal.__file__), Path(fixed_airway.__file__)])
            paths.extend(['crates/chimera/src/voice/human_airway.rs', 'crates/chimera/src/airway/network.rs',
                          'crates/chimera/src/physics.rs'])

        def measure(out, run):
            return compare_native_rate(source, case, out, run, reference)
    else:
        bun = ['bun'] if shutil.which('bun') else ['npx', '--yes', '--package=bun@1.4.4', '--', 'bun']
        source_paths.extend(web_sources())
        paths.extend(['src/audio/AudioEngine.ts', 'src/worklet/processor.ts', 'crates/chimera-wasm/src/lib.rs'])
        metadata.update(
            node=subprocess.check_output(['node', '--version'], text=True).strip(),
            bun=subprocess.check_output([*bun, '--version'], text=True).strip(),
            web_diff_status=subprocess.check_output(
                ['git', 'status', '--porcelain', '--', str(WEB)], cwd=ROOT, text=True).strip(),
        )

        def measure(out, run):
            return compare(source, case, case_path, out, run, bun)
    metadata['upstream_source_sha256'] = {p: sha256(UPSTREAM / p) for p in paths}
    return shared.record_measurement(args.run_id, case_path, source_paths, metadata, measure,
                                     command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
