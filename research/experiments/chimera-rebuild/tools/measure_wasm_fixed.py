"""固定姿勢のPCMと状態を、WASM、ネイティブCLI、固定上流に照合する。"""

import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess

import numpy as np
from scipy.io import wavfile

import measure_pcm_output as pcm
import measure_uniform_tube as shared
import measure_vowel_voice as vowel
from upstream_baseline import UPSTREAM, WORKSPACE, sha256

CASE = WORKSPACE / 'cases/wasm-fixed-voice.json'
HOST = WORKSPACE / 'tools/render_wasm_fixed.ts'
WASM = 'target/wasm32-unknown-unknown/release/vocal_wasm.wasm'
ALLOCATION_LABEL = 'レンダー中の割り当て: '


def read_json(path):
    return json.loads(path.read_text())


def first_index(values):
    where = np.flatnonzero(values)
    return int(where[0]) if where.size else None


def compare_pcm(actual, expected, tolerance):
    if actual.shape != expected.shape or not np.isfinite(actual).all() or not np.isfinite(expected).all():
        raise ValueError('PCMの長さと有限性を確認できません')
    delta = abs(actual.astype(float) - expected)
    first = first_index(actual.view('u4') != expected.view('u4'))
    return {'first_bit_difference_frame': first,
            'first_bit_difference_values': [float(actual[first]), float(expected[first])] if first is not None else None,
            'maximum_absolute_error': float(delta.max()),
            'first_frame_over_tolerance': first_index(delta > tolerance)}


def compare_states(actual, expected, fields, frames, tolerance):
    results = {}
    for i, key in enumerate(fields):
        a, b = actual[:, i], expected[:, i]
        result = shared.compare_series(a, b, tolerance)
        first = first_index(a != b)
        result['first_difference_frame'] = int(frames[first]) if first is not None else None
        excess = result.pop('first_sample_over_tolerance')
        result['first_frame_over_tolerance'] = int(frames[excess]) if excess is not None else None
        results[key] = result
    return results


def phase_pitch(observations, frame_times, rate):
    turns = np.flatnonzero(np.diff(observations) < 0)
    if len(turns) < 2:
        return None
    before, after = observations[turns], observations[turns + 1]
    span = frame_times[turns + 1] - frame_times[turns]
    times = frame_times[turns] + span * (1 - before) / (1 - before + after)
    return float(rate * (len(turns) - 1) / (times[-1] - times[0]))


def measure(path, case, source, artifacts, execute):
    limits = case['measurement']
    frames, rate, internal = (limits[k] for k in ('output_frames', 'output_rate_hz', 'internal_rate_hz'))
    blocks = limits['host_block_frames']
    data = read_json(source)
    voice = data['voice']
    execute(['cargo', 'build', '--locked', '--release', '-p', 'vocal-wasm', '--target', 'wasm32-unknown-unknown'])
    binary = artifacts / 'vocal_wasm.wasm'
    shutil.copyfile(WORKSPACE / WASM, binary)
    execute(['cargo', 'test', '--locked', '--release', '-p', 'vocal-wasm',
             'fixed_voice_render_does_not_allocate', '--', '--nocapture'], stdout=artifacts / 'native-abi-test.log')
    allocation_log = (artifacts / 'cargo.log').read_text()
    matches = re.findall(f'{ALLOCATION_LABEL}([0-9]+)', allocation_log)
    allocations = int(matches[-1]) if matches else None
    execute(['node', str(HOST), str(binary), str(source), str(path), str(artifacts)])
    host = read_json(artifacts / 'wasm-observations.json')

    execute(['cargo', 'test', '--locked', '-p', 'chimera', '--test', 'engine'],
            cwd=UPSTREAM, stdout=artifacts / 'upstream-engine.log')
    execute(['cargo', 'test', '--locked', '-p', 'chimera-wasm', '--test', 'realtime'],
            cwd=UPSTREAM, stdout=artifacts / 'upstream-realtime.log')
    probe = shared.build_upstream_probe(vowel.PROBE, artifacts, execute)
    args = [data['measurement']['voice']['ipa'], internal, rate, frames, *(voice[k] for k in
            ('pressure_cm_h2o', 'gate', 'breathiness', 'tension', 'output_gain')), artifacts]
    execute([str(probe), 'render', *map(str, args)], cwd=UPSTREAM)

    prefix = ['cargo', 'run', '--locked', '--release', '-p', 'vocal-cli', '--']
    execute([*prefix, 'inspect', str(source)], stdout=artifacts / 'settings.json')
    execute([*prefix, 'render', str(source), str(artifacts / 'native-trace.csv')])
    rendered = pcm.render_blocks(source, {'block_frames': blocks}, artifacts, execute)
    measured_rate, native = wavfile.read(rendered[blocks[0]][0])
    upper = np.fromfile(artifacts / 'upstream-voice.f32', dtype='<f4')
    if native.shape != (frames,) or native.dtype != np.float32 or measured_rate != rate:
        raise ValueError('ネイティブCLIの型、長さまたはサンプルレートが不正です')
    fields = limits['observed_fields']
    if host['fields'] != ['frames_rendered', *fields]:
        raise ValueError('WASMの観測値の配置がケースと一致しません')
    points = np.array(sorted(set(range(0, frames, limits['observation_stride_frames']))
                             | set(limits['additional_observation_frames'])))
    native_state, upper_state = (pcm.read_columns(artifacts / filename, frames)[1]
                                 for filename in ('native-trace.csv', 'upstream-trace.csv'))
    clock = internal // rate * (points + 1) - 1
    states = [np.column_stack([track[field][points] for field in fields])
              for track in (native_state, upper_state)]
    settings = read_json(artifacts / 'settings.json')['voice']
    checks = {
        'registered_clock_and_rates': (settings['sample_rate_hz'] == rate and voice['output_sample_rate_hz'] == rate
              and settings['frames'] == frames and data['fixed_airway']['sample_rate_hz'] == internal
              and all(np.array_equal(track['internal_sample'][points], clock) for track in (native_state, upper_state))),
        'import_free_wasm': not limits['require_no_wasm_imports'] or not host['imports'],
        'stable_wasm_buffers': not limits['require_stable_buffers'] or all(
            host['stable_buffers'].get(str(block)) is True for block in blocks),
        'allocation_free_native_abi': allocations is not None and allocations <= limits['maximum_native_render_allocations'],
    }
    details = {}
    left, right = limits['steady_window_frames']
    steady = (points >= left) & (points < right)
    for block, (wave, _) in rendered.items():
        wasm = np.fromfile(artifacts / f'wasm-{block}.f32', dtype='<f4')
        other_rate, other_native = wavfile.read(wave)
        n_compare = compare_pcm(wasm, native, 0)
        u_compare = compare_pcm(wasm, upper, limits['upstream_pcm_absolute_tolerance'])
        bits = compare_pcm(other_native, native, 0)
        measured = np.asarray(host['observations'][str(block)], dtype=float)
        if measured.shape != (len(points), len(fields) + 1) or not np.isfinite(measured).all():
            raise ValueError(f'WASMの観測配列が不正です ({block})')
        aligned = np.array_equal(measured[:, 0], points + 1)
        frame_data = measured[:, 1:]
        nc, uc = (compare_states(frame_data, state, fields, points, limits[key]) for state, key in zip(
            states, ('candidate_state_peak_relative_tolerance', 'upstream_state_peak_relative_tolerance'), strict=True))
        f0_cycle = phase_pitch(frame_data[steady, fields.index('glottal_phase')], points[steady], rate)
        f0_yin, _ = vowel.independent_yin(wasm[left:right].astype(float), rate, data['measurement']['voice'])
        pitch_min, pitch_max = limits['expected_steady_f0_hz']
        onset = first_index(abs(wasm) > limits['onset_threshold'])
        if wasm.shape != (frames,):
            raise ValueError(f'WASMのPCMフレームが不正です ({block})')
        checks[f'block_{block}_pcm'] = (
            other_rate == rate and bits['first_bit_difference_frame'] is None
            and (not limits['require_identical_pcm_bits'] or n_compare['first_bit_difference_frame'] is None)
            and u_compare['first_frame_over_tolerance'] is None)
        checks[f'block_{block}_states'] = aligned and all(x['status'] for x in (*nc.values(), *uc.values()))
        checks[f'block_{block}_sound'] = (
            onset == limits['expected_onset_frame'] and float(abs(wasm).max()) <= limits['maximum_pcm_peak']
            and all(f is not None and pitch_min <= f <= pitch_max for f in (f0_cycle, f0_yin)))
        details[str(block)] = {'candidate_pcm': n_compare, 'upstream_pcm': u_compare,
                               'candidate_states': nc, 'upstream_states': uc, 'native_partition': bits,
                               'onset_frame': onset, 'phase_pitch_hz': f0_cycle, 'pcm_yin_hz': f0_yin,
                               'pcm_peak': float(abs(wasm).max())}
    return {'checks': checks, 'frames': frames, 'observations_per_block_size': len(points),
            'native_abi_render_allocations': allocations, 'wasm_imports': host['imports'], 'blocks': details}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', args.run_id):
        parser.error('実行IDは英数字で始めてください')
    case = read_json(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True):
        raise SystemExit('変更のない固定上流版が必要です')
    source = WORKSPACE / 'cases' / case['fixed_voice_case']
    inputs = [CASE, source, HOST, Path(__file__).resolve(), vowel.PROBE, Path(vowel.__file__),
              Path(pcm.__file__), Path(shared.__file__), WORKSPACE / 'tools/measure_junction.py',
              WORKSPACE / 'tools/upstream_baseline.py', WORKSPACE / 'crates/vocal-wasm/host/fixed-voice.ts',
              *shared.candidate_sources()]
    upper_paths = ['crates/chimera/src/engine.rs', 'crates/chimera/src/voice/human_voice.rs',
                   'crates/chimera-wasm/src/lib.rs', 'crates/chimera-wasm/tests/realtime.rs',
                   'crates/chimera/tests/engine.rs']
    metadata = {'case_id': case['id'], 'upstream_revision': revision, 'target': 'wasm32-unknown-unknown',
                'node': subprocess.check_output(['node', '--version'], text=True).strip(),
                'upper_source_sha256': {name: sha256(UPSTREAM / name) for name in upper_paths}}
    return shared.record_measurement(args.run_id, CASE, inputs, metadata,
                                     lambda out, execute: measure(CASE, case, source, out, execute), command=None)


if __name__ == '__main__':
    raise SystemExit(main())
