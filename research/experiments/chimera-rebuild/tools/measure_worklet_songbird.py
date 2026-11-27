"""実時間ブラウザの鳴禽のPCMと状態をCLI、固定上流、独立計算に照合する。"""

import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess

import numpy as np
from scipy.io import wavfile

import measure_uniform_tube as shared
import measure_wasm_fixed as wasm
from measure_songbird_sustain_pcm import CASE as SOURCE, columns, control_reference
from measure_worklet_fixed import CAPTURE, ROOT, WEB, web_sources
from measure_worklet_realtime import timing_summary
from upstream_baseline import UPSTREAM, WORKSPACE, sha256

CASE = WORKSPACE / 'cases/worklet-songbird-sustain.json'


def read_wave(path, rate, frames):
    found_rate, values = wavfile.read(path)
    if found_rate != rate or values.dtype != np.float32 or values.shape != (frames,) or not np.isfinite(values).all():
        raise ValueError(f'{path.name} は登録どおりのモノラルf32 PCMではありません')
    return values


def rms(values):
    return float(np.sqrt(np.mean(np.square(values.astype(float)))))


def compare_variant(label, baseline, config, source, artifacts, execute, browser, module):
    baseline_case = baseline / 'artifacts' / label / 'case.json'
    variant = next(v for v in source['measurement']['variants'] if v['id'] == label)
    input_ = source['songbird_voice'] | variant['overrides']
    rate, frames = (input_[key] for key in ('sample_rate_hz', 'frames'))
    m = config['measurement']
    replay_path = artifacts / f'{label}-case.json'
    replay = wasm.read_json(replay_path)
    expected_replay = {
        'id': f'worklet-songbird-{label}', 'upstream_revision': config['upstream_revision'],
        'songbird_voice': input_ | {'observe_syrinx': True},
    }
    if wasm.read_json(baseline_case)['songbird_voice'] != input_ or replay != expected_replay:
        raise ValueError(f'{label} の上流・登録・ブラウザ書き出しの設定が一致しません')

    trace_path = artifacts / f'{label}-native.csv'
    wave_path = artifacts / f'{label}-native.wav'
    quantum, stride = (m[key] for key in ('expected_render_quantum_frames', 'observation_stride_frames'))
    execute(['cargo', 'run', '--locked', '--release', '-p', 'vocal-cli', '--', 'render-pcm',
             str(replay_path), str(wave_path), str(trace_path), str(quantum)])
    native = read_wave(wave_path, rate, frames)
    audio = read_wave(artifacts / f'{label}.wav', rate, frames)
    upper_trace = columns(baseline / 'artifacts' / label / 'upstream.csv', frames)
    cli_pcm = wasm.compare_pcm(audio, native, m['cli_pcm_absolute_tolerance'])
    upper_pcm = wasm.compare_pcm(audio, upper_trace['pcm_f32'].astype(np.float32), m['upstream_pcm_absolute_tolerance'])

    fields = m['observed_fields']
    report = wasm.read_json(artifacts / f'{label}.json')
    if report['columns'] != ['output_frame', 'internal_sample', *fields]:
        raise ValueError('鳴禽のWorklet観測列が登録条件と一致しません')
    points = np.minimum(np.arange(stride, frames + stride, stride), frames) - 1
    observation = np.asarray(report['observations'], dtype=float)
    names, data = shared.read_trace(trace_path, frames, len(upper_trace) + 4)
    native_trace = dict(zip(names, data.T, strict=True))
    if (observation.shape != (len(points), 2 + len(fields)) or not np.isfinite(observation).all()
            or not np.isfinite(data).all()):
        raise ValueError('鳴禽の観測点数または有限性が条件外です')
    states = observation[:, 2:]
    cli_states = wasm.compare_states(states, np.column_stack([native_trace[f][points] for f in fields]),
                                    fields, points, m['cli_state_peak_relative_tolerance'])
    upper_fields = [f for f in fields if f in upper_trace]
    upper_indices = [fields.index(f) for f in upper_fields]
    upper_states = wasm.compare_states(states[:, upper_indices], np.column_stack([upper_trace[f][points] for f in upper_fields]),
                                      upper_fields, points, m['upstream_state_peak_relative_tolerance'])

    factor = 2 if rate > 60000 else 4
    internal_samples = (points + 1) * factor - 1
    expected_gate = control_reference(input_, source['measurement'])['gate']
    gate_error = float(np.max(abs(states[:, fields.index('gate')] - expected_gate[points])))
    renew = source['measurement']['control_frames']
    requested = [event['frame'] for event in input_['events']]
    expected_on, expected_off = (((frame + renew - 1) // renew) * renew for frame in requested)
    cli_gate = native_trace['gate']
    cli_on = wasm.first_index(cli_gate > 0)
    cli_off_before = wasm.first_index(np.diff(cli_gate) < 0)
    cli_off = cli_off_before + 1 if cli_off_before is not None else None

    measured = {key: states[:, i] for i, key in enumerate(fields)}
    before, after = m['steady_window_before_release_seconds']
    steady = (round(requested[-1] - before * rate), round(requested[-1] - after * rate))
    steady_points = (points >= steady[0]) & (points < steady[1])
    sides = ('left', 'right')
    area = {side: float(np.max(abs(measured[f'{side}_port_area_cm2']
                                  - m['area_per_opening_cm2'] * measured[f'{side}_opening']))) for side in sides}
    flow = {side: rms(measured[f'{side}_port_flow_cm3_s'][steady_points]) for side in sides}
    steady_pcm = rms(audio[slice(*steady)])
    tail_pcm = rms(audio[-round(m['tail_window_seconds'] * rate):])
    tail_ratio = tail_pcm / steady_pcm if steady_pcm else None

    blocks = np.asarray(report['timing'], dtype=float)
    block_count = (frames + quantum - 1) // quantum
    if report['timingColumns'] != ['context_frame', 'quantum_frames', 'process_ms'] or blocks.shape != (block_count, 3):
        raise ValueError('鳴禽の描画量子の観測数または列が条件外です')
    budget = quantum * 1000 / rate
    valid_timing = bool(np.isfinite(blocks).all() and (blocks[:, 2] >= 0).all())
    timing_all = timing_summary(blocks[:, 2], budget) if valid_timing else None
    timing_warm = timing_summary(blocks[m['health']['exclude_startup_blocks']:, 2], budget) if valid_timing else None
    checks = {
        'browser_and_cli_same_pcm_bits': cli_pcm['first_bit_difference_frame'] is None,
        'fixed_upstream_pcm': upper_pcm['first_frame_over_tolerance'] is None,
        'cli_states': all(item['status'] for item in cli_states.values()),
        'fixed_upstream_states': all(item['status'] for item in upper_states.values()),
        'browser_rate_width_and_state': (report['sampleRate'] == report['workletSampleRate'] == rate
                                         and report['factor'] == factor and report['outputFrames'] == frames
                                         and report['caseId'] == config['id'] and report['contextState'] == 'running'),
        'observation_clock': bool(np.array_equal(observation[:, 0], points)
                                  and np.array_equal(observation[:, 1], internal_samples)
                                  and all(np.array_equal(data['internal_sample'][points], internal_samples)
                                          for data in (upper_trace, native_trace))),
        'independent_gate_and_boundaries': (gate_error <= m['independent_gate_absolute_tolerance']
                                            and cli_on == expected_on and cli_off == expected_off
                                            and any(bound % quantum for bound in (expected_on, expected_off))),
        'independent_area_and_both_flows': all(area[side] <= m['independent_area_absolute_tolerance_cm2']
                                               and flow[side] >= m['minimum_steady_port_flow_rms_cm3_s'] for side in sides),
        'release_pcm_tail': tail_ratio is not None and tail_ratio <= m['maximum_tail_to_steady_pcm_rms_ratio'],
        'audio_quanta_contiguous': bool(np.all(blocks[:, 1] == quantum) and np.all(np.diff(blocks[:, 0]) == quantum)),
        'realtime_processing_budget_p95': timing_warm is not None and (
            timing_warm['p95_ms'] < budget * m['health']['maximum_processing_p95_budget_ratio']),
        'downloads_and_served_wasm': (browser['servedWasmSha256'] == sha256(module) and not browser['errors']
                                      and browser['controlsReset'] and round(browser['audioDuration'] * rate) == frames),
    }
    return {
        'checks': checks, 'rate_hz': rate, 'internal_rate_hz': rate * factor, 'frames': frames,
        'observation_count': len(points), 'cli_pcm': cli_pcm, 'upstream_pcm': upper_pcm,
        'cli_states': cli_states, 'upstream_states': upper_states,
        'events': {'requested_frames': requested, 'gate_applied_frames': [cli_on, cli_off]},
        'independent_gate_max_abs_difference': gate_error, 'port_area_max_abs_difference_cm2': area,
        'steady_flow_rms_cm3_s': flow, 'steady_window_frames': list(steady), 'steady_pcm_rms': steady_pcm,
        'tail_pcm_rms': tail_pcm, 'tail_to_steady_pcm_rms_ratio': tail_ratio,
        'first_context_frame': int(blocks[0, 0]), 'startup_callbacks': report['startupCallbacks'],
        'startup_discontinuities': report['startupDiscontinuities'], 'timing_clock': report['timingClock'],
        'render_budget_ms': budget, 'timing_all': timing_all, 'timing_warm': timing_warm,
    }


def measure(baseline, config, source, artifacts, execute, bun):
    execute([*bun, 'run', 'build'], cwd=WEB, stdout=artifacts / 'browser-build.log')
    module = artifacts / 'vocal_wasm.wasm'
    shutil.copyfile(WORKSPACE / wasm.WASM, module)
    allocate = artifacts / 'allocation.log'
    execute(['cargo', 'test', '--locked', '--release', '-p', 'vocal-wasm',
             'songbird_sustain_render_does_not_allocate', '--', '--nocapture'], stdout=allocate)
    allocation_text = allocate.read_text() + (artifacts / 'cargo.log').read_text()
    counts = {int(rate): int(count) for rate, count in re.findall(r'songbird_render_allocations_(\d+)=(\d+)', allocation_text)}
    execute(['node', str(CAPTURE), str(artifacts), str(CASE)])
    browser = wasm.read_json(artifacts / 'browser-run.json')
    variants = {label: compare_variant(label, baseline, config, source, artifacts, execute, browser['variants'][label], module)
                for label in config['measurement']['variants']}
    checks = {f'{label}_{key}': status for label, variant in variants.items() for key, status in variant['checks'].items()}
    checks['native_render_allocation_limit'] = all(
        variant['rate_hz'] in counts and counts[variant['rate_hz']] <= config['measurement']['native_allocation_limit']
        for variant in variants.values())
    return {'checks': checks, 'variants': variants, 'native_allocations': counts, 'browser': browser['version']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('baseline_run_id', help='持続音PCMを固定上流と比較済みの実行ID')
    args = parser.parse_args()
    if any(not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]*', value) for value in vars(args).values()):
        parser.error('実行IDは英数字で始め、英数字・ハイフン・アンダースコアで指定してください')
    config, source = map(wasm.read_json, (CASE, SOURCE))
    if config['source_case'] != SOURCE.name:
        raise SystemExit('登録ケースと鳴禽の原ケースが一致しません')
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != config['upstream_revision'] or subprocess.check_output(
            ['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True):
        raise SystemExit('変更のない固定上流版が必要です')
    baseline = WORKSPACE / 'runs' / args.baseline_run_id
    manifest = wasm.read_json(baseline / 'manifest.json')
    if manifest['status'] != 'pass' or manifest['upstream_revision'] != revision or manifest['case_id'] != source['id']:
        raise SystemExit('実行IDは固定上流と持続音を照合した合格済みの実行を指定してください')
    recorded = {entry['path']: entry['sha256'] for entry in manifest['outputs']}
    paths = [baseline / 'artifacts' / label / name for label in config['measurement']['variants']
             for name in ('case.json', 'upstream.csv')]
    if any(recorded.get(str(path.relative_to(baseline))) != sha256(path) for path in paths):
        raise SystemExit('固定上流の観測または入力が実行マニフェストと一致しません')

    bun = ['bun'] if shutil.which('bun') else ['npx', '--yes', '--package=bun@1.4.4', '--', 'bun']
    sources = [CASE, SOURCE, Path(__file__).resolve(), *web_sources(), *shared.candidate_sources(),
               baseline / 'manifest.json', *paths,
               *(WORKSPACE / 'tools' / name for name in (
                   'measure_uniform_tube.py', 'upstream_baseline.py', 'measure_songbird_sustain_pcm.py',
                   'measure_wasm_fixed.py', 'measure_worklet_fixed.py', 'measure_worklet_realtime.py')),
               WORKSPACE / 'data/MANDARIN-PINYIN-LICENSE.txt']
    upstream_paths = ['src/worklet/processor.ts', 'crates/chimera-wasm/src/lib.rs', 'crates/chimera/src/engine.rs',
                      'crates/chimera/src/creatures/voice.rs', 'crates/chimera/src/creatures/songbird.rs',
                      'crates/chimera/tests/golden_creatures.rs', 'crates/chimera/tests/creature_realtime.rs']
    details = {'case_id': config['id'], 'revision': config['revision'], 'upstream_revision': revision,
               'baseline_run_id': args.baseline_run_id, 'invoked_from': str(Path.cwd()), 'input_root': '$REPOSITORY',
               'node': subprocess.check_output(['node', '--version'], text=True).strip(),
               'bun': subprocess.check_output([*bun, '--version'], text=True).strip(),
               'web_diff_status': subprocess.check_output(
                   ['git', 'status', '--porcelain', '--', str(WEB)], cwd=ROOT, text=True).strip(),
               'upstream_source_sha256': {path: sha256(UPSTREAM / path) for path in upstream_paths}}
    return shared.record_measurement(args.run_id, CASE, sources, details,
                                     lambda out, run: measure(baseline, config, source, out, run, bun),
                                     command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
