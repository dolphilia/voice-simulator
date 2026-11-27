"""手動発声の体型切り替えを実ブラウザ・保存ケース・固定上流で測る。"""

import argparse
import math
from pathlib import Path
import re
import shutil
import subprocess

import numpy as np
from scipy.io import wavfile

import measure_bilabial_stop as speech
import measure_worklet_manual_articulation as manual
import measure_speech_timing as timing
import measure_uniform_tube as shared
import measure_wasm_fixed as wasm
from measure_worklet_fixed import CAPTURE, ROOT, WEB, web_sources
from upstream_baseline import UPSTREAM, WORKSPACE, sha256

CASE = WORKSPACE / 'cases/worklet-manual-body-switch.json'
PROBE = WORKSPACE / 'tools/upstream_body_switch_probe.rs'


def reset_prediction(target, dt, controls):
    omega = math.tau * 11.0
    position, velocity = 0.7, 0.0
    for _ in range(controls):
        velocity += (omega**2 * (target - position) - 2 * omega * velocity) * dt
        position += velocity * dt
    elapsed = dt * controls
    return {'lip_aperture_cm': position, 'gate': -math.expm1(-elapsed / 0.025),
            'glottal_f0_hz': 110 * (205 / 110)**(-math.expm1(-elapsed / 0.06))}


def compare(config, fixed_path, artifacts, execute, bun):
    m = config['measurement']
    rate, internal, quantum, ctl = (
        m[k] for k in ('output_rate_hz', 'internal_rate_hz', 'quantum_frames', 'control_interval_output_frames'))
    execute([*bun, 'run', 'build'], cwd=WEB, stdout=artifacts / 'browser-build.log')
    binary = artifacts / 'vocal_wasm.wasm'
    shutil.copyfile(WORKSPACE / wasm.WASM, binary)
    execute(['node', str(CAPTURE), str(artifacts), str(CASE)])
    report, site = (timing.read(artifacts / name) for name in ('browser.json', 'browser-run.json'))
    fx = timing.read(fixed_path)
    path = artifacts / 'browser-case.json'
    export = timing.read(path)
    change, = report['bodyChanges']
    switch, stop = change['frame'], report['stopFrame']
    expected = manual.expected_replay(
        {**config, 'measurement': {**m, 'render_quantum_frames': quantum, 'minimum_hold_frames': quantum}}, fx, report)
    expected_events = expected['articulators']['events']
    expected_events.insert(-1, {'frame': switch // ctl, 'body': m['body_switch']['body']})
    comparable = ('upstream_revision', 'body', 'posture', 'voice', 'articulators', 'measurement')
    execute(['cargo', 'test', '--locked', '-p', 'chimera', '--test', 'engine', '--test', 'body_mix'],
            cwd=UPSTREAM, stdout=artifacts / 'upstream-tests.log')
    probe = shared.build_upstream_probe(PROBE, artifacts, execute, extra_libraries=('serde_json',))
    upper_pcm, upper_trace = (artifacts / name for name in ('upstream.f32', 'upstream.csv'))
    execute([str(probe), str(path), str(upper_pcm), str(upper_trace)], cwd=UPSTREAM)
    cli = ['cargo', 'run', '--locked', '--release', '-p', 'vocal-cli', '--']
    native_trace = artifacts / 'native-trace.csv'
    execute([*cli, 'inspect', str(path)], stdout=artifacts / 'native-inspect.json')
    execute([*cli, 'render', str(path), str(native_trace)])
    renders = manual.pcm.render_blocks(path, {'block_frames': m['host_block_frames']}, artifacts, execute)
    first_wave, first_pcm_csv = next(iter(renders.values()))
    cli_rate, native = wavfile.read(first_wave)
    browser_rate, audio = wavfile.read(artifacts / 'browser.wav')
    upper = np.fromfile(upper_pcm, dtype='<f4')
    frames = report['outputFrames']
    if any(wave.shape != (frames,) or wave.dtype != np.float32 for wave in (audio, native, upper)):
        raise ValueError('ブラウザ・CLI・上流の波形長または型を確認できません')
    factor = internal // rate
    native_track = manual.motion.load_track(native_trace, np.arange(frames * factor), ctl * factor)
    dense_native = {field: values[factor - 1::factor] for field, values in native_track.items()}
    dense_upper = speech.load_trace(upper_trace, frames)
    points = np.arange(quantum - 1, frames, quantum)
    columns = report['columns']
    rows = np.asarray(report['observations'], dtype=float)
    if rows.shape != (len(points), len(columns)) or not np.isfinite(rows).all():
        raise ValueError('ブラウザの観測点数・有限性が登録条件と一致しません')
    states = dict(zip(columns, rows.T, strict=True))
    fields = m['observed_fields']
    sampled = np.column_stack([states[field] for field in fields])
    cli_matrix = np.column_stack([dense_native[field][points] for field in fields])
    upper_matrix = np.column_stack([dense_upper[field][points] for field in fields])
    geom = ('lip_aperture_cm', 'lip_minimum_cm2', 'tongue_body_x_cm', 'tongue_body_y_cm', 'oral_minimum_cm2')
    geometric_errors = {field: float(abs(states[field] - dense_upper[field][points]).max()) for field in geom}
    scalar_indices = [i for i, field in enumerate(fields) if field not in geom]
    upstream_state = wasm.compare_states(sampled[:, scalar_indices], upper_matrix[:, scalar_indices],
        [fields[i] for i in scalar_indices], points, m['upstream_state_peak_relative_tolerance'])
    cli_pcm = wasm.compare_pcm(audio, native, 0)
    upper_comparison = wasm.compare_pcm(audio, upper, m['upstream_pcm_absolute_tolerance'])
    target = m['gestures'][0]['value_cm']
    first = int(np.searchsorted(points, switch))
    predicted = reset_prediction(target, ctl / rate, quantum // ctl)
    measured = {key: float(states[key][first]) for key in predicted}
    independent_errors = {key: abs(measured[key] - value) for key, value in predicted.items()}
    settled = (points >= stop - m['settled_window_frames']) & (points < stop)
    if not settled.any():
        raise ValueError('停止前の定常窓がありません')
    checks = {
        'browser_assets_and_format': site['servedWasmSha256'] == sha256(binary) and not site['errors']
            and site['controlsReset'] and cli_rate == browser_rate == report['workletSampleRate'] == rate,
        'saved_case_exact': site['caseFilename'] == 'worklet-articulation-case.json'
            and all(export[key] == expected[key] for key in comparable),
        'switch_frame_and_cells': change['body'] == m['body_switch']['body']
            and change['cells'] == m['expected_new_cells']
            and switch % quantum == 0 and report['articulation'][-1]['frame'] < switch < stop
            and [dense_upper[key][switch] for key in ('pharynx_cells', 'oral_cells')] == m['expected_new_cells']
            and [dense_upper[key][switch - 1] for key in ('pharynx_cells', 'oral_cells')] == [18, 18],
        'upper_voice_clock_restarts_and_target_is_retained': 0 < dense_upper['voice_clock_seconds'][switch] <= ctl / rate
            and dense_upper['voice_clock_seconds'][switch - 1] > 0.1
            and dense_upper['lip_target_cm'][switch - 1] == dense_upper['lip_target_cm'][switch] == target,
        'clock_contiguous': np.array_equal(states['context_frame']-states['context_frame'][0], points-quantum+1)
            and np.array_equal(states['frames_rendered'], points + 1) and np.all(states['quantum_frames'] == quantum),
        'records_use_control_interval': report['controlIntervalOutputFrames'] == ctl,
        'pcm_bit_equal_and_states_exact': cli_pcm['first_bit_difference_frame'] is None
            and np.array_equal(sampled, cli_matrix),
        'independent_reset_and_recapture': all(value <= m['independent_state_absolute_tolerance']
            for value in independent_errors.values()),
        'lip_target_recovered': abs(float(states['lip_aperture_cm'][first-1])-target)
            <= m['before_switch_settled_position_tolerance_cm']
            and float(abs(states['lip_aperture_cm'][settled]-target).max()) <= m['after_switch_settled_position_tolerance_cm'],
        'new_default_f0': float(abs(states['glottal_f0_hz'][settled]-205).max()) <= m['after_switch_settled_pitch_tolerance_hz'],
        'upper_pcm_and_states': upper_comparison['first_frame_over_tolerance'] is None
            and max(geometric_errors.values()) <= m['upstream_geometry_absolute_tolerance']
            and all(state['status'] for state in upstream_state.values()),
        'host_partition_invariance': all(sha256(wave) == sha256(first_wave) and sha256(trace) == sha256(first_pcm_csv)
            for wave, trace in renders.values()),
    }
    first_post_switch = {}
    for field in fields:
        a, b = dense_native[field][switch:], dense_upper[field][switch:]
        delta = a-b
        index = wasm.first_index(delta != 0)
        if index is not None:
            first_post_switch[field] = {'frame': switch+index, 'candidate_minus_upstream': float(delta[index])}
    return {'checks': {key: bool(value) for key, value in checks.items()}, 'frames': frames, 'change': change,
            'first_observation_frame': int(points[first]), 'switch_pcm_before_after': [float(audio[switch-1]), float(audio[switch])],
            'measured_after_switch': measured, 'predicted_after_switch': predicted, 'prediction_errors': independent_errors,
            'prior': {key: float(states[key][first-1]) for key in measured},
            'settled': {key: float(np.median(states[key][settled])) for key in measured},
            'cli_pcm': cli_pcm, 'upstream_pcm': upper_comparison, 'upstream_geometry_errors': geometric_errors,
            'upstream_state_comparison': upstream_state, 'first_post_switch_differences': first_post_switch,
            'browser': site, 'saved_events': export['articulators']['events']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    run_id = parser.parse_args().run_id
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', run_id):
        parser.error('実行IDは英数字で始めてください')
    config = timing.read(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != config['upstream_revision'] or subprocess.check_output(
            ['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True):
        raise SystemExit('変更のない固定上流版が必要です')
    fixed_path = WORKSPACE / 'cases' / config['fixed_voice_case']
    bun = ['bun'] if shutil.which('bun') else ['npx', '--yes', '--package=bun@1.4.4', '--', 'bun']
    modules = (manual, manual.motion, manual.pcm, speech, shared, timing, wasm)
    inputs = [CASE, PROBE, fixed_path, Path(__file__).resolve(), *shared.candidate_sources(), *web_sources(),
              *(Path(module.__file__) for module in modules), WORKSPACE / 'tools/upstream_baseline.py',
              WORKSPACE / 'tools/measure_worklet_fixed.py', WORKSPACE / 'tools/measure_articulation.py']
    upper_sources = ('crates/chimera/src/engine.rs', 'crates/chimera/src/voice/human_voice.rs',
                     'crates/chimera/src/control/articulators.rs', 'crates/chimera/tests/engine.rs')
    meta = {'case_id': config['id'], 'upstream_revision': revision, 'input_root': '$REPOSITORY',
            'upper_source_sha256': {name: sha256(UPSTREAM / name) for name in upper_sources},
            'node': subprocess.check_output(['node', '--version'], text=True).strip(),
            'bun': subprocess.check_output([*bun, '--version'], text=True).strip()}
    return shared.record_measurement(run_id, CASE, inputs, meta,
                                     lambda out, run: compare(config, fixed_path, out, run, bun),
                                     command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
