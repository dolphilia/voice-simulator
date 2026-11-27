"""固定ビートパターンをブラウザの入口から描画し、CLI・固定上流と照合する。"""

import argparse
from fractions import Fraction
import math
from pathlib import Path
import re
import shutil
import subprocess

import numpy as np
import scipy
from scipy.io import wavfile

import measure_beatbox_pattern as pattern
import measure_uniform_tube as shared
import measure_wasm_fixed as wasm
from measure_worklet_fixed import CAPTURE, ROOT, WEB, web_sources
from upstream_baseline import UPSTREAM, WORKSPACE, sha256

CASE = WORKSPACE / 'cases/worklet-beatbox-pattern.json'


def compare_states(actual, expected, frames, limits):
    results = {}
    for name, observed in actual.items():
        reference = expected[name][frames]
        error = abs(observed - reference)
        tolerance = max(limits['state_absolute_floor'],
                        limits['state_peak_relative_tolerance'] * float(abs(reference).max()))
        first = wasm.first_index(error > tolerance)
        results[name] = {
            'maximum_absolute_error': float(error.max()), 'tolerance': tolerance,
            'first_frame_over_tolerance': int(frames[first]) if first is not None else None,
        }
    return results


def measure_capture(artifacts, config, limits, record, binary, cli, native, reference, upstream):
    stride = record['stride']
    report = wasm.read_json(artifacts / f'browser-{stride}.json')
    rate, audio = wavfile.read(artifacts / f'browser-{stride}.wav')
    frames = limits['output_frames']
    quantum = limits['expected_render_quantum_frames']
    if audio.shape != (frames,) or audio.dtype != np.float32:
        raise ValueError('ブラウザのPCMの型またはフレーム数が不正です')
    pcm_cli = wasm.compare_pcm(audio, native, limits['upstream_pcm_absolute_tolerance'])
    pcm_upstream = wasm.compare_pcm(audio, upstream, limits['upstream_pcm_absolute_tolerance'])
    observed = np.asarray(report['observations'], dtype='f8')
    points = np.minimum(np.arange(stride, frames + stride, stride), frames) - 1
    columns = report['columns']
    fields = limits['observed_fields']
    required = [*fields, 'beat_step', 'beat_next_step']
    if (observed.shape != (len(points), len(columns)) or not np.isfinite(observed).all()
            or columns[:2] != ['context_frame', 'frames_rendered']
            or not set(required).issubset(columns)):
        raise ValueError('ブラウザの観測点数・観測列・有限性が登録条件に一致しません')
    values = {name: observed[:, columns.index(name)] for name in required}
    acoustic = {name: values[name] for name in fields}
    cli_states = compare_states(acoustic, cli, points, limits)
    upper_states = compare_states({name: data for name, data in acoustic.items() if name in reference.dtype.names},
                                  reference, points, limits)

    # 64フレームごとに進む描画後の制御時計と、累積誤差で隣り合う一制御区間を許容する。
    seconds = Fraction(15) / Fraction(str(config['bpm']))
    horizon = Fraction(1, 5)
    swing = Fraction(str(config['swing']))
    control_end = (points // 64 + 1) * 64
    end = Fraction(frames, rate)
    hit_times = []
    step = 0
    while (hit := horizon + (step + step % 2 * swing / 2) * seconds) <= end:
        hit_times.append(float(hit))
        step += 1
    stamps = np.asarray(hit_times)
    tolerance = 1e-12
    playhead = values['beat_step']
    ahead = np.searchsorted(stamps, control_end / rate + tolerance, side='right') - 1
    behind = np.searchsorted(stamps, control_end / rate - tolerance, side='right') - 1
    slots = len(config['pattern'].replace('|', ' ').split())
    ahead = np.where(ahead >= 0, ahead % slots, -1)
    behind = np.where(behind >= 0, behind % slots, -1)
    invalid = wasm.first_index((playhead != ahead) & (playhead != behind))
    transitions = np.flatnonzero(np.r_[True, playhead[1:] != playhead[:-1]])
    changes = [[int(points[i]), int(playhead[i])] for i in transitions]
    expected_table = [[str(frame), str(slot) if slot >= 0 else '開始待ち'] for frame, slot in changes]
    times = (np.arange(frames) + 1) / rate
    pitches = []
    for (begin, end), note in zip(limits['pitch_windows_seconds'], limits['expected_midi_notes'], strict=True):
        frequency, correlation = pattern.hum.pcm_pitch(audio[(times >= begin) & (times < end)], rate, note)
        pitches.append({'midi_note': note, 'pcm_f0_hz': frequency, 'pcm_pitch_correlation': correlation,
                        'expected_f0_hz': pattern.hum.f0_hz(note)})

    checks = {
        'served_registered_input_and_binary': (
            report['beat'] == dict(pattern=config['pattern'], bpm=config['bpm'], swing=config['swing'],
                                   initialPitchHz=config['initial_f0_hz'], noiseScale=config['noise_scale'])
            and report['voice']['body'] == 'male' and report['voice']['posture'] == config['posture']
            and report['voice']['voice'] == config['voice']
            and report['voice']['fixed_airway']['sample_rate_hz'] == limits['internal_rate_hz']
            and report['observationStride'] == stride and record['servedWasmSha256'] == sha256(binary)
        ),
        'output_quantum_and_observation_clock': (
            rate == report['sampleRate'] == report['workletSampleRate'] == limits['output_rate_hz']
            and report['framesRendered'] == report['outputFrames'] == frames and report['outputChannels'] == 1
            and report['shortestQuantum'] == report['longestQuantum'] == quantum
            and report['callbacks'] == math.ceil(frames / quantum)
            and report['discontinuities'] == report['firstContextFrame'] == 0
            and np.array_equal(observed[:, 0], points) and np.array_equal(observed[:, 1], points + 1)
        ),
        'pcm_matches_cli_and_upstream': (
            (not limits['require_cli_pcm_bit_equality'] or pcm_cli['first_bit_difference_frame'] is None)
            and pcm_upstream['first_frame_over_tolerance'] is None
            and float(abs(audio).max()) >= limits['minimum_pcm_peak']
        ),
        'sampled_states_match_cli_and_upstream': all(
            row['first_frame_over_tolerance'] is None for row in (*cli_states.values(), *upper_states.values())
        ),
        'playhead_including_rests_matches_reference': (
            invalid is None and [slot for _, slot in changes] == limits['expected_slots_in_window']
            and np.array_equal(playhead, cli['beat_step'][points])
            and np.array_equal(playhead, reference['beat_step'][points])
            and np.array_equal(values['beat_next_step'], cli['beat_next_step'][points])
        ),
        'playhead_table_uses_observations': expected_table == record['playheadTable'],
        'two_pcm_pitches_match_registered_notes': all(
            abs(note['pcm_f0_hz'] - note['expected_f0_hz'])
            <= note['expected_f0_hz'] * limits['pitch_relative_tolerance']
            and note['pcm_pitch_correlation'] >= limits['minimum_pcm_pitch_correlation']
            for note in pitches
        ),
    }
    return {
        'stride_frames': stride, 'observations': len(points), 'checks': checks, 'pcm_cli': pcm_cli,
        'pcm_upstream': pcm_upstream, 'cli_states': cli_states, 'upstream_states': upper_states,
        'playhead_changes': changes, 'pitches': pitches, 'first_unexpected_playhead_frame':
        int(points[invalid]) if invalid is not None else None,
        'wasm_memory_growths': report['wasmMemoryGrowths'],
    }


def measure(source, case, artifacts, execute, bun):
    config = wasm.read_json(source)
    limits = case['measurement']
    execute([*bun, 'run', 'build'], cwd=WEB, stdout=artifacts / 'browser-build.log')
    binary = artifacts / 'vocal_wasm.wasm'
    shutil.copyfile(WORKSPACE / wasm.WASM, binary)
    execute(['node', str(CAPTURE), str(artifacts), str(CASE), str(source)])
    native_result = pattern.measure(source, config, artifacts, execute)
    execute(['cargo', 'test', '--locked', '--release', '-p', 'chimera-wasm', '--test', 'realtime'],
            cwd=UPSTREAM, stdout=artifacts / 'upstream-wasm-tests.log')
    frames = limits['output_frames']
    cli = pattern.bilabial.load_trace(artifacts / 'trace.csv', frames)
    reference = pattern.bilabial.load_trace(artifacts / 'upstream-trace.csv', frames)
    _, native = wavfile.read(artifacts / 'pcm-128.wav')
    upstream = np.fromfile(artifacts / 'upstream-engine-128.f32', dtype='<f4')
    browser = wasm.read_json(artifacts / 'browser-run.json')
    captures = [measure_capture(artifacts, config['beatbox_pattern'], limits, record, binary,
                                cli, native, reference, upstream) for record in browser['captures']]
    checks = {
        'native_passes_registered_conditions': all(native_result['checks'].values()),
        'browser_accepts_corrected_pattern': (
            bool(browser['rejected']) and not browser['errors']
            and all(record['recovered'] for record in browser['captures'])
        ),
        'observation_partitions_have_identical_wave': (
            [capture['stride_frames'] for capture in captures] == limits['observation_stride_frames']
            and len({sha256(artifacts / f'browser-{item["stride_frames"]}.wav') for item in captures}) == 1
        ),
    }
    for capture in captures:
        checks.update({f"{key}_{capture['stride_frames']}": value for key, value in capture['checks'].items()})
    return {'checks': checks, 'browser_version': browser['version'], 'wasm_bytes': binary.stat().st_size,
            'frames': frames, 'native': native_result, 'captures': captures}


def record_experiment(run_id, case_path, measure_run, extra_sources=()):
    case = wasm.read_json(case_path)
    source = WORKSPACE / 'cases' / case['beatbox_pattern_case']
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or revision != wasm.read_json(source)['upstream_revision'] or (
            subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True)):
        raise SystemExit('変更のない固定上流版が必要です')
    bun = ['bun'] if shutil.which('bun') else ['npx', '--yes', '--package=bun@1.4.4', '--', 'bun']
    modules = (pattern, pattern.bilabial, pattern.crash, pattern.hat, pattern.hum, pattern.inward, pattern.kick,
               pattern.pop, pattern.rimshot, pattern.snare, pattern.click, pattern.timing, pattern.transport, shared, wasm)
    inputs = [case_path, source, pattern.BASELINE, pattern.hum.CASE, pattern.PROBE, pattern.kick.ORAL_PROBE,
              Path(__file__), *shared.candidate_sources(), *web_sources(),
              *extra_sources,
              *(Path(module.__file__) for module in modules), *pattern.rimshot.REFERENCE_SOURCES,
              *(WORKSPACE / 'tools' / name for name in ('upstream_baseline.py', 'measure_worklet_fixed.py',
                   'measure_pcm_output.py', 'measure_vowel_voice.py', 'measure_junction.py'))]
    upper = ('src/ui/store.ts', 'src/audio/AudioEngine.ts', 'src/worklet/processor.ts', 'src/wasm/wire.ts',
             'tests/wasm-engine.test.ts', 'crates/chimera-wasm/src/lib.rs',
             'crates/chimera-wasm/tests/realtime.rs', 'crates/chimera/src/engine.rs',
             'crates/chimera/src/control/beat_player.rs', 'crates/chimera/src/phonetics/beatbox.rs',
             'crates/chimera/src/voice/human_voice.rs', 'crates/chimera/tests/beatbox.rs',
             'crates/chimera/tests/engine.rs', 'crates/chimera/src/voice/human_airway.rs',
             'crates/chimera/src/anatomy/human.rs', 'crates/chimera/src/airway/network.rs',
             'crates/chimera/src/control/articulators.rs', 'crates/chimera/src/math.rs',
             'crates/chimera/src/phonetics/consonantTargets.generated.json')
    metadata = {'case_id': case['id'], 'upstream_revision': revision, 'input_root': '$REPOSITORY',
                'scipy': scipy.__version__,
                'node': subprocess.check_output(['node', '--version'], text=True).strip(),
                'bun': subprocess.check_output([*bun, '--version'], text=True).strip(),
                'upstream_source_sha256': {path: sha256(UPSTREAM / path) for path in upper}}
    return shared.record_measurement(run_id, case_path, inputs, metadata,
                                     lambda out, run: measure_run(source, case, out, run, bun),
                                     command=None, input_root=ROOT)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', args.run_id):
        parser.error('実行IDは英数字で始めてください')
    return record_experiment(args.run_id, CASE, measure)


if __name__ == '__main__':
    raise SystemExit(main())
