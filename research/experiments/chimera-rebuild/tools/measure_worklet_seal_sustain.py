"""アザラシの持続音・停止を実時間ブラウザとCLI・固定上流で照合する。"""

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
from measure_seal_sustain_pcm import (
    CASE as SOURCE, CANDIDATE, COMPONENTS, UPPER, audio_observations, columns,
    gate_reference, independent_output, internal,
)
from measure_songbird_sustain_pcm import waveform
from measure_songbird_syrinx import CLI, compare
from measure_worklet_fixed import CAPTURE, ROOT, WEB, web_sources
from measure_worklet_realtime import timing_summary
from measure_worklet_songbird import read_wave
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/worklet-seal-sustain.json'
FIELDS = CANDIDATE[2:-1]


def compare_at(candidate, reference, tolerance, points, *, coordinate='output_frame'):
    result = compare(candidate, reference, tolerance)
    first = result.pop('first_difference_sample')
    excess = result.pop('first_over_tolerance_sample')
    return {
        **result,
        'tolerance': tolerance,
        f'first_difference_{coordinate}': None if first is None else int(points[first]),
        f'first_over_tolerance_{coordinate}': None if excess is None else int(points[excess]),
    }


def capture_observations(label, measurement, artifacts, frames, fields):
    report = wasm.read_json(artifacts / f'{label}.json')
    if report['columns'] != ['output_frame', 'internal_sample', *fields]:
        raise ValueError('動物音声の観測列が登録条件と一致しません')
    stride = measurement.get('observation_stride_by_variant', {}).get(label, measurement['observation_stride_frames'])
    windows = measurement.get('observation_windows_output_frames', {}).get(label, [])
    points = np.union1d(np.arange(measurement['observation_offset_frames'], frames, stride),
                        [frames - 1, *measurement['extra_output_frames'][label],
                         *(frame for start, end in windows for frame in range(start, end))])
    observation = np.asarray(report['observations'], dtype=float)
    if observation.shape != (len(points), 2 + len(fields)) or not np.isfinite(observation).all():
        raise ValueError('動物音声の観測点数または有限性が条件外です')
    states = dict(zip(fields, observation[:, 2:].T, strict=True))
    return report, points, observation[:, :2], states


def capture_health(config, report, browser, module, rate, frames, factor):
    m = config['measurement']
    quantum = m['expected_render_quantum_frames']
    blocks = np.asarray(report['timing'], dtype=float)
    if (report['timingColumns'] != ['context_frame', 'quantum_frames', 'process_ms']
            or blocks.shape != (math.ceil(frames / quantum), 3) or not np.isfinite(blocks).all()
            or (blocks[:, 2] < 0).any()):
        raise ValueError('動物音声の描画量子の観測数または有限性が条件外です')
    budget = quantum * 1000 / rate
    timing = timing_summary(blocks[m['health']['exclude_startup_blocks']:, 2], budget)
    checks = {
        'browser_rate_and_context': (report['sampleRate'] == report['workletSampleRate'] == rate
                                     and report['factor'] == factor and report['outputFrames'] == frames
                                     and report['caseId'] == config['id'] and report['contextState'] == 'running'),
        'audio_quanta_contiguous': bool(np.all(blocks[:, 1] == quantum) and np.all(np.diff(blocks[:, 0]) == quantum)),
        'realtime_processing_budget_p95': bool(timing and timing['p95_ms']
                                               < budget * m['health']['maximum_processing_p95_budget_ratio']),
        'downloads_and_served_wasm': (browser['servedWasmSha256'] == sha256(module) and not browser['errors']
                                      and browser['controlsReset'] and round(browser['audioDuration'] * rate) == frames),
    }
    return checks, {'render_budget_ms': budget, 'timing': timing, 'timing_clock': report['timingClock'],
                    'startup_discontinuities': report['startupDiscontinuities']}


def independent_pressure(points, breath, config, limits, gate):
    controls = breath['controls']
    step = points // limits['control_frames'] + 1 + config['startup_phase_control_steps']
    phase = np.remainder(step * controls['pulse_rate_hz'] * limits['control_frames']
                         / breath['sample_rate_hz'], 1.0)
    duty, depth = (controls[key] for key in ('duty', 'pulse_depth'))
    half_sine = np.where(phase < duty, np.sin(np.pi * phase / duty), 0.0)
    base = controls['pressure_cm_h2o'] * config['pressure_cmh2o_to_dyn_cm2'] * gate[points]
    return base * (1.0 - depth + depth * half_sine)


def compare_variant(label, baseline, config, source, artifacts, execute, browser, module):
    limits, m = source['measurement'], config['measurement']
    variant = next(item for item in limits['variants'] if item['id'] == label)
    base = source['seal_voice']
    breath = base['breath'] | variant['breath']
    input_ = base | {'breath': breath, 'level': variant.get('level', base['level'])}
    rate, frames = (breath[key] for key in ('sample_rate_hz', 'frames'))
    quantum = m['expected_render_quantum_frames']
    factor = 2 if rate <= 60000 else 1
    upstream_dir = baseline / 'artifacts' / label
    replay_path = artifacts / f'{label}-case.json'
    if (wasm.read_json(upstream_dir / 'case.json')['seal_voice'] != input_
            or wasm.read_json(replay_path) != {
                'id': f'worklet-seal-{label}', 'upstream_revision': config['upstream_revision'],
                'seal_voice': input_,
            }):
        raise ValueError(f'{label} の固定上流・登録・ブラウザ書き出しの入力が一致しません')

    wave_path, trace_path = (artifacts / f'{label}-native.{suffix}' for suffix in ('wav', 'csv'))
    execute([*CLI, 'render-pcm', str(replay_path), str(wave_path), str(trace_path), str(quantum)])
    native = read_wave(wave_path, rate, frames)
    audio = read_wave(artifacts / f'{label}.wav', rate, frames)
    native_trace = columns(trace_path, frames, CANDIDATE)
    upper = columns(upstream_dir / 'upstream.csv', frames, UPPER)
    upper_pcm = upper['pcm_f32'].astype(np.float32)
    cli_pcm = wasm.compare_pcm(audio, native, m['cli_pcm_absolute_tolerance'])
    upstream_pcm = wasm.compare_pcm(audio, upper_pcm, limits['pcm_absolute_tolerance'])
    upstream_pcm['different_bits'] = int(np.count_nonzero(audio.view('u4') != upper_pcm.view('u4')))

    report, points, clock, states = capture_observations(label, m, artifacts, frames, FIELDS)
    cli_states = {key: compare_at(values, native_trace[key][points], m['cli_state_absolute_tolerance'], points)
                  for key, values in states.items()}
    tolerance = {'gate': limits['gate_absolute_tolerance'],
                 'lung_pressure_dyn_cm2': limits['pressure_absolute_tolerance_dyn_cm2'],
                 'radiation_0': limits['radiation_absolute_tolerance_cm3_s2'],
                 'radiation_1': limits['radiation_absolute_tolerance_cm3_s2']}
    upstream_states = {
        key: compare_at(values, upper[key][points],
                        tolerance.get(key, limits['component_absolute_tolerance_cm3_s']), points)
        for key, values in states.items() if key in upper
    }

    raw = internal(native_trace, factor)
    upper_raw = internal(upper, factor)
    gate, target = gate_reference(breath, limits)
    pressure = independent_pressure(points, breath, m, limits, gate)
    decimated, filtered, pcm = independent_output(raw['radiation'], rate, factor, input_['level'], limits)
    independent = {
        'gate': compare_at(states['gate'], gate[points], limits['gate_absolute_tolerance'], points),
        'gate_target': compare_at(states['gate_target'], target[points], 0.0, points),
        'lung_pressure_dyn_cm2': compare_at(states['lung_pressure_dyn_cm2'], pressure,
                                            m['independent_pressure_absolute_tolerance_dyn_cm2'], points),
        'decimated': compare_at(states['decimated'], decimated[points],
                                limits['radiation_absolute_tolerance_cm3_s2'], points),
        'dc_removed': compare_at(states['dc_removed'], filtered[points], limits['dc_absolute_tolerance'], points),
        'pcm': compare(audio, pcm, limits['pcm_absolute_tolerance']),
    }
    wave_checks, wave_stats = audio_observations(variant, breath, native_trace, audio, raw, limits)
    actual_control = points[np.flatnonzero(np.diff(states['gate_target'], prepend=0.0))].tolist()
    observed_raw = internal(states, factor)
    indices = (points[:, None] * factor + np.arange(factor)).ravel()
    observed_onsets = {key: wasm.first_index(values != 0.0) for key, values in observed_raw.items()}
    observed_onsets = {key: None if index is None else int(indices[index])
                       for key, index in observed_onsets.items()}
    # 境界直前の内部サンプルにも観測点があることを確認する。
    onsets_match = all(observed_onsets[key] == wave_stats['onsets'][key]
                       for key in COMPONENTS)
    onset_predecessors = all(index - 1 in indices for index in observed_onsets.values()
                             if index is not None)

    health, timing = capture_health(config, report, browser, module, rate, frames, factor)
    expected_internal = (points + 1) * factor - 1
    checks = {
        'browser_cli_pcm_bits': cli_pcm['first_bit_difference_frame'] is None,
        'fixed_upstream_pcm': upstream_pcm['first_frame_over_tolerance'] is None,
        'cli_states': all(value['passed'] for value in cli_states.values()),
        'fixed_upstream_states': all(value['passed'] for value in upstream_states.values()),
        'independent': all(value['passed'] for value in independent.values()),
        'observed_gate_boundaries': actual_control == wave_stats['gate_control_frames'],
        'observed_radiation_onsets': onsets_match and onset_predecessors,
        'unused_internal_slots_zero': factor == 2 or all(np.all(states[f'{key}_1'] == 0) for key in COMPONENTS),
        'observation_clock': (np.array_equal(clock[:, 0], points)
                              and np.array_equal(clock[:, 1], expected_internal)
                              and all(np.array_equal(trace['internal_sample'][points], expected_internal)
                                      for trace in (upper, native_trace))),
        **health,
        **wave_checks,
    }
    official_pcm = None
    if label == 'official-prefix-48000':
        official = waveform(baseline / 'artifacts/official-cli/seal.wav', breath)[:frames]
        official_pcm = wasm.compare_pcm(audio, official, limits['pcm_absolute_tolerance'])
        checks['official_demo_prefix'] = official_pcm['first_frame_over_tolerance'] is None
    precursor_differences = {
        'output_frames': {key: wasm.first_index(native_trace[key] != upper[key])
                          for key in ('gate', 'lung_pressure_dyn_cm2')},
        'internal_samples': {key: wasm.first_index(raw[key] != upper_raw[key]) for key in COMPONENTS},
    }
    return {
        'checks': checks, 'rate_hz': rate, 'frames': frames, 'factor': factor, 'observations': len(points),
        'requested_gate_frames': [event['frame'] for event in breath['events']],
        'observed_gate_frames': actual_control, 'observed_onsets': observed_onsets, **wave_stats,
        'upstream_difference_precursors': precursor_differences,
        'cli_pcm': cli_pcm, 'upstream_pcm': upstream_pcm, 'official_pcm': official_pcm,
        'cli_states': cli_states, 'upstream_states': upstream_states, 'independent': independent,
        **timing,
    }


def run(case_path, source_path, compare_case, allocation_test, allocation_rates, description, *, extra_sources=(),
        creature='seal', official_variant='official-prefix-48000', reference_files=(), upstream_files=()):
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument('run_id')
    parser.add_argument('baseline_run_id', help='同じケースを固定上流に照合した実行ID')
    args = parser.parse_args()
    if any(not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', arg) for arg in vars(args).values()):
        parser.error('実行IDは英数字で始めてください')
    config, source = map(wasm.read_json, (case_path, source_path))
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if (config['source_case'] != source_path.name or config['upstream_revision'] != revision
            or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True)):
        raise SystemExit('登録ケースと変更のない固定上流版が必要です')
    baseline = WORKSPACE / 'runs' / args.baseline_run_id
    manifest_path = baseline / 'manifest.json'
    manifest = wasm.read_json(manifest_path)
    if (manifest['status'] != 'pass' or manifest['upstream_revision'] != revision
            or manifest['case_id'] != source['id'] or manifest['revision'] != config['source_revision']):
        raise SystemExit('固定上流と登録ケースを照合した合格済みの実行を指定してください')
    source_hash = next((item['sha256'] for item in manifest['inputs']
                        if item['path'] == str(source_path.relative_to(WORKSPACE))), None)
    if source_hash != sha256(source_path):
        raise SystemExit('元の登録ケースが基準マニフェストと一致しません')
    variants = config['measurement']['variants']
    inputs = [baseline / 'artifacts' / label / name for label in variants for name in ('case.json', 'upstream.csv')]
    if official_variant in variants:
        inputs.append(baseline / 'artifacts/official-cli' / f'{creature}.wav')
    inputs.extend(baseline / name for name in reference_files)
    hashes = {entry['path']: entry['sha256'] for entry in manifest['outputs']}
    if any(hashes.get(str(path.relative_to(baseline))) != sha256(path) for path in inputs):
        raise SystemExit('固定上流の観測・入力がマニフェストと一致しません')
    bun = ['bun'] if shutil.which('bun') else ['npx', '--yes', '--package=bun@1.4.4', '--', 'bun']
    sources = [case_path, source_path, Path(__file__).resolve(), *extra_sources, *web_sources(), *shared.candidate_sources(),
               manifest_path, *inputs, *(WORKSPACE / 'tools' / name for name in (
                   'measure_uniform_tube.py', 'upstream_baseline.py', 'measure_seal_sustain_pcm.py',
                   'measure_songbird_sustain_pcm.py', 'measure_songbird_syrinx.py', 'measure_wasm_fixed.py',
                   'measure_worklet_fixed.py', 'measure_worklet_realtime.py', 'measure_worklet_songbird.py')),
               WORKSPACE / 'data/MANDARIN-PINYIN-LICENSE.txt']
    upper_files = ['src/ui/components/BestiaryPanel.tsx', 'src/audio/AudioEngine.ts', 'src/worklet/processor.ts',
                   'crates/chimera-wasm/src/lib.rs', 'crates/chimera/src/engine.rs',
                   *(f'crates/chimera/src/creatures/{name}.rs' for name in (creature, 'voice', 'mammal')),
                   'crates/chimera/tests/golden_creatures.rs', 'crates/chimera/tests/creature_realtime.rs', *upstream_files]
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
        allocation_log = artifacts / 'allocation.log'
        execute(['cargo', 'test', '--locked', '--release', '-p', 'vocal-wasm',
                 allocation_test, '--', '--nocapture'], stdout=allocation_log)
        allocations = dict((rate, int(count)) for rate, count in re.findall(
            rf'{re.escape(creature)}_render_allocations_(\d+)=(\d+)', (artifacts / 'cargo.log').read_text()))
        execute(['node', str(CAPTURE), str(artifacts), str(case_path)])
        browser = wasm.read_json(artifacts / 'browser-run.json')
        result = {label: compare_case(label, baseline, config, source, artifacts, execute,
                                       browser['variants'][label], module) for label in variants}
        checks = {f'{label}.{key}': flag for label, data in result.items() for key, flag in data['checks'].items()}
        allocation_limit = config['measurement']['native_allocation_limit']
        checks['native_render_allocation_limit'] = all(
            str(rate) in allocations and allocations[str(rate)] <= allocation_limit for rate in allocation_rates)
        return {'checks': checks, 'variants': result, 'native_allocations': allocations,
                'browser': browser['version'], 'measurement': config['measurement']}

    return shared.record_measurement(args.run_id, case_path, sources, details, measure, command=None, input_root=ROOT)


def main():
    return run(CASE, SOURCE, compare_variant, 'seal_sustain_render_does_not_allocate', (48000, 96000), __doc__)


if __name__ == '__main__':
    raise SystemExit(main())
