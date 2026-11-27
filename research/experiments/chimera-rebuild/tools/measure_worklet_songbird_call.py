"""鳴禽のコールを実時間ブラウザ・CLI・固定上流で照合する共通処理。"""

import argparse
import math
import os
from pathlib import Path
import re
import shutil
import subprocess

import numpy as np

import measure_uniform_tube as shared
import measure_wasm_fixed as wasm
from measure_songbird_flute import CALL_FIELDS, control_reference, trace
from measure_songbird_sustain_pcm import CASE as SUSTAIN, FIELDS, internal
from measure_songbird_syrinx import compare
from measure_worklet_fixed import CAPTURE, ROOT, WEB, web_sources
from measure_worklet_realtime import timing_summary
from measure_worklet_songbird import read_wave
from upstream_baseline import UPSTREAM, WORKSPACE, sha256

BASE_FIELDS = (
    'gate', 'sac_pressure_dyn_cm2', 'left_opening', 'right_opening',
    'left_port_area_cm2', 'right_port_area_cm2', 'left_port_flow_cm3_s', 'right_port_flow_cm3_s',
)
CALL_COLUMNS = ('control_clock_seconds', 'call_id', 'gate_target')
AREA_FLOW = BASE_FIELDS[4:]
NATIVE_FIELDS = (*FIELDS, *CALL_FIELDS, 'gate_target', 'call_id', *AREA_FLOW)


def rising_frames(frames, signal, threshold):
    high = signal >= threshold
    return frames[high & ~np.r_[False, high[:-1]]]


def first_synthesis_differences(reference, candidate, factor, *, extra_fields=()):
    fields = ('gate', 'pitch_hz', 'sac_pressure_dyn_cm2', 'left_opening', 'right_opening',
              'decimated', 'dc_removed', *extra_fields)
    frames = {field: wasm.first_index(reference[field] != candidate[field]) for field in fields}
    radiation = wasm.first_index(internal(reference, factor) != internal(candidate, factor))
    return {'output_frames': frames, 'radiation_internal_sample': radiation,
            'radiation_output_frame': radiation // factor if radiation is not None else None}


def compare_variant(label, baseline, config, source, sustain, definitions, artifacts, execute,
                    browser, module, evaluate, *, capture_id=None):
    m = config['measurement']
    variant = next(v for v in source['measurement']['variants'] if v['id'] == label)
    input_ = source['songbird_voice'] | variant['overrides']
    rate, frames = (input_[key] for key in ('sample_rate_hz', 'frames'))
    upstream_dir = baseline / 'artifacts' / label
    captured = capture_id or label
    replay_path = artifacts / f'{captured}-case.json'
    replay = wasm.read_json(replay_path)
    if wasm.read_json(upstream_dir / 'case.json')['songbird_voice'] != input_ or replay != {
        'id': f'worklet-songbird-{label}', 'upstream_revision': config['upstream_revision'],
        'songbird_voice': input_ | {'observe_call_id': True, 'observe_syrinx': True},
    }:
        raise ValueError(f'{label} の上流・登録・ブラウザ書き出しの設定が一致しません')

    quantum, stride = (m[k] for k in ('expected_render_quantum_frames', 'observation_stride_frames'))
    wave_path, trace_path = (artifacts / f'{label}-native.{suffix}' for suffix in ('wav', 'csv'))
    execute(['cargo', 'run', '--locked', '--release', '-p', 'vocal-cli', '--', 'render-pcm',
             str(replay_path), str(wave_path), str(trace_path), str(quantum)])
    native = read_wave(wave_path, rate, frames)
    audio = read_wave(artifacts / f'{captured}.wav', rate, frames)
    native_trace = trace(trace_path, frames, NATIVE_FIELDS)
    upper_id = ('call_id',) if input_.get('observe_call_id') else ()
    upper = trace(upstream_dir / 'upstream.csv', frames, (*FIELDS, *CALL_FIELDS, *upper_id))
    cli_pcm = wasm.compare_pcm(audio, native, m['cli_pcm_absolute_tolerance'])
    upstream_pcm = wasm.compare_pcm(audio, upper['pcm_f32'].astype(np.float32), m['upstream_pcm_absolute_tolerance'])
    params = tuple(sustain['measurement']['parameter_time_constants_seconds'])
    fields = (*BASE_FIELDS, *CALL_COLUMNS, *params, *(f'target_{key}' for key in params))
    report = wasm.read_json(artifacts / f'{captured}.json')
    if report['columns'] != ['output_frame', 'internal_sample', *fields]:
        raise ValueError('鳴禽コールのWorklet観測列が登録条件と一致しません')
    offset = m.get('observation_offset_frames', stride - 1)
    points = np.union1d(np.arange(offset, frames, stride), [frames - 1, *m.get('extra_output_frames', [])])
    observation = np.asarray(report['observations'], dtype=float)
    if observation.shape != (len(points), 2 + len(fields)) or not np.isfinite(observation).all():
        raise ValueError('鳴禽コールの観測点数または有限性が条件外です')
    states = dict(zip(fields, observation[:, 2:].T, strict=True))
    cli_states = wasm.compare_states(observation[:, 2:], np.column_stack([native_trace[f][points] for f in fields]),
                                    fields, points, m['cli_state_peak_relative_tolerance'])
    upper_fields = [f for f in fields if f in upper]
    upstream_states = wasm.compare_states(np.column_stack([states[f] for f in upper_fields]),
                                          np.column_stack([upper[f][points] for f in upper_fields]),
                                          upper_fields, points, m['upstream_state_peak_relative_tolerance'])
    upstream_active = bool(np.array_equal(states['call_id'] != 0, upper['active_call'][points] != 0))

    truth = control_reference(replay['songbird_voice'], definitions, sustain['measurement'])
    independent = {f: compare(states[f], truth[f][points], m[
        'independent_clock_absolute_tolerance_seconds' if f == 'control_clock_seconds' else
        'independent_control_absolute_tolerance']) for f in fields if f in truth}
    for item in independent.values():
        index = item.pop('first_over_tolerance_sample')
        item['first_over_tolerance_frame'] = int(points[index]) if index is not None else None
        index = item.pop('first_difference_sample')
        item['first_difference_frame'] = int(points[index]) if index is not None else None

    event_flags, event_metrics = evaluate(
        points, states, audio, input_, m, declared=truth, definitions=definitions,
        control=sustain['measurement'], artifacts=artifacts, execute=execute,
        native_trace=native_trace, upstream_trace=upper)

    blocks = np.asarray(report['timing'], dtype=float)
    if (report['timingColumns'] != ['context_frame', 'quantum_frames', 'process_ms']
            or blocks.shape != (math.ceil(frames / quantum), 3) or not np.isfinite(blocks).all()
            or (blocks[:, 2] < 0).any()):
        raise ValueError('鳴禽コールの描画量子の観測数または有限性が条件外です')
    budget = quantum * 1000 / rate
    timing = timing_summary(blocks[m['health']['exclude_startup_blocks']:, 2], budget)
    factor = 4 if rate <= 60000 else 2
    expected_internal = (points + 1) * factor - 1
    checks = {
        'browser_and_cli_same_pcm_bits': cli_pcm['first_bit_difference_frame'] is None,
        'fixed_upstream_pcm': upstream_pcm['first_frame_over_tolerance'] is None,
        'cli_states': all(item['status'] for item in cli_states.values()),
        'fixed_upstream_states': upstream_active and all(item['status'] for item in upstream_states.values()),
        'independent_control': all(item['passed'] for item in independent.values()),
        'observation_clock': bool(np.array_equal(observation[:, 0], points)
                                  and np.array_equal(observation[:, 1], expected_internal)
                                  and all(np.array_equal(t['internal_sample'][points], expected_internal)
                                          for t in (upper, native_trace))),
        'browser_rate_and_context': (report['sampleRate'] == report['workletSampleRate'] == rate
                                     and report['factor'] == factor and report['outputFrames'] == frames
                                     and report['caseId'] == config['id'] and report['contextState'] == 'running'),
        'audio_quanta_contiguous': bool(np.all(blocks[:, 1] == quantum) and np.all(np.diff(blocks[:, 0]) == quantum)),
        'realtime_processing_budget_p95': timing['p95_ms'] < budget * m['health']['maximum_processing_p95_budget_ratio'],
        'downloads_and_served_wasm': (browser['servedWasmSha256'] == sha256(module) and not browser['errors']
                                      and browser['controlsReset'] and round(browser['audioDuration'] * rate) == frames),
        **event_flags,
    }
    return {'checks': checks, 'rate_hz': rate, 'frames': frames, 'observations': len(points),
            'cli_pcm': cli_pcm, 'upstream_pcm': upstream_pcm, 'cli_states': cli_states, 'upstream_states': upstream_states,
            'independent_control': independent, **event_metrics, 'render_budget_ms': budget, 'timing': timing,
            'timing_clock': report['timingClock'], 'startup_discontinuities': report['startupDiscontinuities']}


def run(case_path, source_path, definition_file, evaluate, entry_path, description, *, compare_experiment=None,
        extra_sources=()):
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument('run_id')
    parser.add_argument('baseline_run_id', help='コールを固定上流と比較した実行ID')
    args = parser.parse_args()
    if any(not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', arg) for arg in vars(args).values()):
        parser.error('実行IDは英数字で始めてください')
    config, source, sustain = map(wasm.read_json, (case_path, source_path, SUSTAIN))
    inherited_sources = []
    if name := config.get('inherits_measurement'):
        parent = WORKSPACE / 'cases' / name
        parent_config = wasm.read_json(parent)
        if any(config[key] != parent_config[key] for key in ('upstream_revision', 'source_case', 'source_revision')):
            raise SystemExit('継承する観測ケースと固定上流・入力の版が一致しません')
        config['measurement'] = parent_config['measurement'] | config['measurement']
        inherited_sources.append(parent)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if config['source_case'] != source_path.name or config['upstream_revision'] != revision or subprocess.check_output(
            ['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True):
        raise SystemExit('登録ケースと変更のない固定上流版が必要です')
    baseline = WORKSPACE / 'runs' / args.baseline_run_id
    manifest_path = baseline / 'manifest.json'
    manifest = wasm.read_json(manifest_path)
    baseline_revision = config.get('source_revision', source['revision'])
    if (manifest['status'] != 'pass' or manifest['upstream_revision'] != revision
            or manifest['case_id'] != source['id'] or manifest['revision'] != baseline_revision):
        raise SystemExit('固定上流と指定のコールを照合した合格済みの実行を指定してください')
    source_hash = next((item['sha256'] for item in manifest['inputs']
                        if item['path'] == str(source_path.relative_to(WORKSPACE))), None)
    if source_hash != sha256(source_path):
        raise SystemExit('コールの原ケースが基準マニフェストと一致しません')
    definition_path = baseline / 'artifacts' / definition_file
    inputs = [definition_path, *(baseline / 'artifacts' / label / name
              for label in config['measurement']['variants'] for name in ('case.json', 'upstream.csv'))]
    hashes = {entry['path']: entry['sha256'] for entry in manifest['outputs']}
    if any(hashes.get(str(path.relative_to(baseline))) != sha256(path) for path in inputs):
        raise SystemExit('固定上流の定義・観測・入力がマニフェストと一致しません')
    raw_definitions = wasm.read_json(definition_path)
    if isinstance(raw_definitions, dict):
        raw_definitions = [raw_definitions]
    definitions = {definition['id']: definition for definition in raw_definitions}
    bun = ['bun'] if shutil.which('bun') else ['npx', '--yes', '--package=bun@1.4.4', '--', 'bun']
    sources = [case_path, source_path, SUSTAIN, entry_path, Path(__file__).resolve(), *web_sources(),
               *inherited_sources, *extra_sources,
               *shared.candidate_sources(),
               manifest_path, *inputs, *(WORKSPACE / 'tools' / name for name in (
                   'measure_uniform_tube.py', 'upstream_baseline.py', 'measure_songbird_sustain_pcm.py',
                   'measure_songbird_syrinx.py', 'measure_songbird_flute.py', 'measure_wasm_fixed.py',
                   'measure_worklet_fixed.py', 'measure_worklet_realtime.py', 'measure_worklet_songbird.py')),
               WORKSPACE / 'data/MANDARIN-PINYIN-LICENSE.txt']
    upper_files = ['src/ui/components/BestiaryPanel.tsx', 'src/audio/AudioEngine.ts', 'src/worklet/processor.ts',
                   'crates/chimera-wasm/src/lib.rs', 'crates/chimera/src/engine.rs', 'crates/chimera/src/creatures/voice.rs',
                   'crates/chimera/src/creatures/songbird.rs', 'crates/chimera/tests/golden_creatures.rs',
                   'crates/chimera/tests/creature_realtime.rs']
    details = {'case_id': config['id'], 'revision': config['revision'], 'upstream_revision': revision,
               'baseline_run_id': args.baseline_run_id, 'invoked_from': str(Path.cwd()), 'input_root': '$REPOSITORY',
               'chromium_executable': os.environ.get('CHIMERA_CHROMIUM'),
               'node': subprocess.check_output(['node', '--version'], text=True).strip(),
               'bun': subprocess.check_output([*bun, '--version'], text=True).strip(),
               'web_diff_status': subprocess.check_output(
                   ['git', 'status', '--porcelain', '--', str(WEB)], cwd=ROOT, text=True).strip(),
               'upstream_source_sha256': {name: sha256(UPSTREAM / name) for name in upper_files}}

    def measure(artifacts, execute):
        execute([*bun, 'run', 'build'], cwd=WEB, stdout=artifacts / 'browser-build.log')
        module = artifacts / 'vocal_wasm.wasm'
        shutil.copyfile(WORKSPACE / wasm.WASM, module)
        execute(['cargo', 'test', '--locked', '--release', '-p', 'vocal-wasm',
                 'songbird_call_render_does_not_allocate', '--', '--nocapture'], stdout=artifacts / 'allocation.log')
        allocation = re.search(r'songbird_call_render_allocations=(\d+)', (artifacts / 'cargo.log').read_text())
        count = int(allocation[1]) if allocation else None
        execute(['node', str(CAPTURE), str(artifacts), str(case_path)])
        browser = wasm.read_json(artifacts / 'browser-run.json')
        if compare_experiment:
            result = compare_experiment(baseline, config, source, sustain, definitions, artifacts, execute,
                                        browser, module, evaluate)
        else:
            variants = {label: compare_variant(label, baseline, config, source, sustain, definitions,
                                               artifacts, execute, browser['variants'][label], module, evaluate)
                        for label in config['measurement']['variants']}
            checks = {f'{label}.{name}': value for label, data in variants.items() for name, value in data['checks'].items()}
            result = {'checks': checks, 'variants': variants}
        result['checks']['native_render_allocation_limit'] = count is not None and count <= config['measurement']['native_allocation_limit']
        return result | {'native_allocations': count, 'browser': browser['version']}

    return shared.record_measurement(args.run_id, case_path, sources, details, measure, command=None, input_root=ROOT)

