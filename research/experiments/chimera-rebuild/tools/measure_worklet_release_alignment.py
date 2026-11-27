"""96 kHzのWorkletで、呼気停止と描画回数のどちらに時間外れ値が追随するか測る。"""

import argparse
import json
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory

import numpy as np
from scipy.io import wavfile

import measure_axial_observer as saved
import measure_lip_crossing_thickness as stored
import measure_uniform_tube as shared
import measure_vowel_voice as vowel
import measure_wasm_fixed as wasm
import measure_worklet_realtime as realtime
from measure_worklet_fixed import CAPTURE, ROOT, WEB, web_sources
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/worklet-realtime-release-alignment.json'


def profile_sizes(study, profile):
    m = study['measurement']
    q = m['quantum_frames']
    return q * m['pre_roll_quanta'], q * profile['stop_quantum_index'], q * profile['capture_quanta']


def validate_registration(study, reference):
    m = study['measurement']
    original = reference['measurement']
    registered = (original['pre_roll_frames'], original['expected_stop_frame'], original['expected_output_frames'])
    if (registered != profile_sizes(study, m['profiles']['historical'])
            or m['output_rate_hz'] != original['output_rate_hz']
            or m['quantum_frames'] != original['expected_quantum_frames']
            or any(sorted(order) != sorted(m['profiles']) for order in m['capture_order'])):
        raise ValueError('元の96 kHzの区間または計測順序を照合できません')
    primary = [m['profiles'][name] for name in ('early', 'reference', 'late')]
    if len({p['capture_quanta'] for p in primary}) != 1 or not all(
            m['pre_roll_quanta'] < p['stop_quantum_index'] < p['capture_quanta'] for p in primary):
        raise ValueError('主比較では同じ長さの記録と量子境界の呼気停止が必要です')


def history(study, reference, reference_path):
    sizes = study['measurement']
    before = []
    inputs = []
    for name in study['historical_runs']:
        paths, manifest = saved.load_saved_run(name, reference['id'], study['upstream_revision'],
                                              ['summary.json', 'artifacts/browser.json'])
        entry = next(row for row in stored.read(manifest)['inputs'] if row['path'].endswith(reference_path.name))
        if entry['sha256'] != sha256(reference_path):
            raise ValueError('元のWorklet実行で用いたケースのハッシュが一致しません')
        report = stored.read(paths['artifacts/browser.json'])
        observations = np.asarray(report['observations'])
        target = sizes['historical_outlier_index']
        budget = 1000 * sizes['quantum_frames'] / sizes['output_rate_hz']
        if observations[target, 2] <= budget:
            raise ValueError('元の遅い量子を再取得できません')
        before.append({'run': name, 'reported_milliseconds': float(observations[target, 2]),
                       'zero_based_quantum': target, 'clock': report['timingClock']})
        inputs.extend((manifest, *paths.values()))
    return before, inputs


def compare_schedule(trial, report, profiles, start, stop, frames, quantum, reference):
    applied = trial.get('schedule')
    if not applied:
        return False
    current, original = applied['settings'], applied['originalSettings']
    expected_original = reference['measurement']
    return (current['quantum'] == quantum == original['quantum']
            and current['preRoll'] == start == original['preRoll']
            and current['maximumVoiced'] == stop - start and current['release'] == frames - stop
            and original['maximumVoiced'] == expected_original['maximum_voiced_frames']
            and original['release'] == expected_original['release_frames']
            and report['startFrame'] == start and report['stopFrame'] == stop
            and report['outputFrames'] == frames == profiles['capture_quanta'] * quantum
            and report['stopReason'] == 'limit')


def compare_trial(study, reference, trial, artifacts, render, binary_hash):
    if 'error' in trial:
        return {'browser_capture': False}, dict(trial)
    m = study['measurement']
    t = study['criteria']
    spec = reference['measurement']
    profile = m['profiles'][trial['profile']]
    q = m['quantum_frames']
    start, stop, frames = profile_sizes(study, profile)
    folder = artifacts / trial['artifactId']
    report = stored.read(folder / 'browser.json')
    rate, audio = wavfile.read(folder / 'browser.wav')
    expected_rate, native, upper, native_state, upper_state = render
    if rate != expected_rate or audio.dtype != np.float32 or audio.shape != native.shape or len(audio) != frames:
        raise ValueError('ブラウザのPCMのレート、型またはフレーム数が条件外です')
    if not np.isfinite(audio).all():
        raise ValueError('ブラウザPCMに非有限値があります')
    fields = spec['observed_fields']
    header = ['context_frame', 'quantum_frames', 'process_ms', 'callback_elapsed_ms', 'frames_rendered', *fields]
    rows = np.asarray(report['observations'], dtype=float)
    if report['columns'] != header or rows.shape != (frames // q, len(header)) or not np.isfinite(rows).all():
        raise ValueError('処理量子の観測列を照合できません')
    indices = np.arange(len(rows))
    begins = indices * q
    last = begins + q - 1
    elapsed, wall = rows[:, 2], rows[:, 3]
    budget = 1000 * q / rate
    voiced = (begins >= start) & (begins < stop)
    released = begins >= stop
    clock_gaps = np.diff(rows[:, 0]) - q
    discontinuities = np.flatnonzero(clock_gaps)
    timing = {'voicing': realtime.timing_summary(elapsed[voiced], budget),
              'release': realtime.timing_summary(elapsed[released], budget),
              'all': realtime.timing_summary(elapsed, budget),
              'callback_gaps': realtime.timing_summary(np.diff(wall), budget)}
    gate = realtime.independent_gate(last, start, stop, rate, spec)
    gate_error = float(np.max(np.abs(gate - rows[:, 5 + fields.index('gate')])))
    pcm = wasm.compare_pcm(audio, native, 0)
    reference_pcm = wasm.compare_pcm(audio, upper, t['upstream_pcm_absolute_error_max'])
    states = [
        wasm.compare_states(rows[:, 5:], np.column_stack([table[key][last] for key in fields]),
                            fields, last, tolerance)
        for table, tolerance in ((native_state, 1e-10), (upper_state, spec['upstream_state_peak_relative_tolerance']))
    ]
    outliers = np.flatnonzero(elapsed > budget)
    checks = {
        'browser_capture': trial['controlsReset'] and not trial['errors']
        and trial['servedWasmSha256'] == binary_hash and report['contextState'] == 'running',
        'schedule': compare_schedule(trial, report, profile, start, stop, frames, q, reference),
        'rates_and_state': all(report[key] == rate for key in ('sampleRate', 'workletSampleRate', 'internalSampleRate'))
        and report['controlIntervalOutputFrames'] == spec['control_interval_output_frames'],
        'frame_continuity': not len(discontinuities) and bool(np.all(rows[:, 1] == q))
        and bool(np.array_equal(rows[:, 4], begins + q))
        and all(np.array_equal(table['internal_sample'][last], last) for table in (native_state, upper_state)),
        'stable_buffers': report['stableWasmBuffers'] and report['wasmMemoryGrowths'] == t['max_wasm_memory_growths']
        and report['firstWasmMemoryGrowthFrame'] is None,
        'native_pcm': pcm['first_bit_difference_frame'] is None,
        'upstream_pcm': reference_pcm['first_frame_over_tolerance'] is None,
        'observation_states': all(item['status'] for groups in states for item in groups.values()),
        'gate_formula': gate_error <= t['gate_absolute_error_max'],
        'voicing_p99_budget': timing['voicing']['p99_ms'] <= budget * t['voicing_p99_budget_fraction_max'],
        'nonnegative_timing': bool(np.all(elapsed >= 0) and np.all(np.diff(wall) >= 0)),
    }
    result = {**trial, 'clock': report['timingClock'], 'budget_ms': budget,
              'context_first_frame': int(rows[0, 0]), 'first_context_discontinuity_after': (
                  int(rows[discontinuities[0], 0]) if len(discontinuities) else None),
              'timing': timing, 'gate_error': gate_error, 'native_pcm': pcm, 'upstream_pcm': reference_pcm,
              'outliers': [
                  {'quantum_index': int(i), 'release_relative_index': int(i - stop // q),
                   'output_frame': int(begins[i]), 'observed_process_ms': float(elapsed[i]),
                   'callback_elapsed_ms': float(wall[i]), 'gate': float(rows[i, 5 + fields.index('gate')])}
                  for i in outliers
              ],
              'predicted_render_index_ms': float(elapsed[m['historical_outlier_index']]),
              'predicted_decay_index_ms': float(elapsed[stop // q + m['release_relative_outlier_index']]),
              'browser_pcm_sha256': sha256(folder / 'browser.wav'),
              'browser_report_sha256': sha256(folder / 'browser.json')}
    for path in (folder / 'browser.wav', folder / 'browser.json'):
        stored.compress(path)
    return checks, result


def classify(study, results):
    m = study['measurement']
    radius, required = m['window_radius_quanta'], m['minimum_shifted_hits_per_profile']
    counts = {}
    for profile in m['profiles']:
        group = [trial for trial in results if trial['profile'] == profile and 'outliers' in trial]
        counts[profile] = {'captured': len(group)}
        for key, index, target in (('render_index', 'quantum_index', m['historical_outlier_index']),
                                   ('release_age', 'release_relative_index', m['release_relative_outlier_index'])):
            counts[profile][key] = sum(
                any(abs(outlier[index] - target) <= radius for outlier in trial['outliers']) for trial in group)
    shifted = [counts[name] for name in ('early', 'late')]
    def discriminates(target, competing):
        return all(row[target] >= required and row[competing] < required for row in shifted)
    outcome = ('render_index' if discriminates('render_index', 'release_age') else
               'release_age' if discriminates('release_age', 'render_index') else 'inconclusive')
    return {'outcome': outcome, 'registered_window_hits': counts}


def measure(study, reference, source, history_before, artifacts, execute, bun):
    m = study['measurement']
    execute([*bun, 'run', 'build'], cwd=WEB, stdout=artifacts / 'browser-build.log')
    binary = artifacts / 'vocal_wasm.wasm'
    shutil.copyfile(WORKSPACE / wasm.WASM, binary)
    binary_hash = sha256(binary)
    execute(['node', str(CAPTURE), str(artifacts), str(CASE)])
    browser = stored.read(artifacts / 'browser-run.json')
    execute(['cargo', 'test', '--locked', '-p', 'chimera', '--test', 'engine'],
            cwd=UPSTREAM, stdout=artifacts / 'upstream-engine.log')
    probe = shared.build_upstream_probe(vowel.PROBE, artifacts, execute)

    requested = [(i + 1, profile) for i, order in enumerate(m['capture_order']) for profile in order]
    accepted = [(trial['round'], trial['profile']) for trial in browser['trials']]
    checks = {'all_requested_trials_recorded': accepted == requested}
    results = {}
    for name, profile in m['profiles'].items():
        start, stop, frames = profile_sizes(study, profile)
        with TemporaryDirectory(prefix=f'{name}-renderer-', dir=artifacts) as temporary:
            td = Path(temporary)
            _, blocks, rate, native, upper, tables = realtime.render_replay(
                source, reference, td, execute, start, stop, frames, upstream_probe=probe)
            checks[f'{name}/native_partition_invariance'] = all(
                sha256(blocks[m['quantum_frames']][i]) == sha256(blocks[77][i]) for i in (0, 1))
            shutil.copyfile(td / 'replay-case.json', artifacts / f'{name}-replay-case.json')
            for trial in (trial for trial in browser['trials'] if trial['profile'] == name):
                local, result = compare_trial(study, reference, trial, artifacts, (rate, native, upper, *tables), binary_hash)
                checks.update({f"{trial['artifactId']}/{key}": value for key, value in local.items()})
                results[trial['artifactId']] = result
    ordered = [results[row['artifactId']] for row in browser['trials']]
    return {'checks': checks, 'browser': browser['version'], 'earlier_measurements': history_before,
            'attribution': classify(study, ordered), 'trials': ordered}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    study = stored.read(CASE)
    revision = study['upstream_revision']
    if (subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip() != revision
            or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True)):
        parser.error('固定上流のコミットと作業状態を確認してください')
    reference_path = WORKSPACE / 'cases' / study['reference_case']
    reference = stored.read(reference_path)
    source = WORKSPACE / 'cases' / reference['fixed_voice_case']
    if reference['upstream_revision'] != revision or sha256(source) != reference['fixed_voice_sha256']:
        parser.error('上流版と固定発声の入力を照合できません')
    validate_registration(study, reference)
    historical, prior_inputs = history(study, reference, reference_path)
    bun = ['bun'] if shutil.which('bun') else ['npx', '--offline', '--yes', '--package=bun@1.4.4', '--', 'bun']
    inputs = [CASE, Path(__file__).resolve(), source, reference_path, *prior_inputs, *web_sources(),
              *shared.candidate_sources(), vowel.PROBE,
              *(Path(module.__file__) for module in (stored, saved, shared, wasm, realtime, realtime.pcm, vowel)),
              *(UPSTREAM / p for p in ('src/worklet/processor.ts', 'crates/chimera-wasm/src/lib.rs',
                 'crates/chimera/src/voice/human_voice.rs', 'crates/chimera/src/engine.rs', 'crates/chimera/tests/engine.rs'))]
    metadata = {'case_id': study['id'], 'upstream_revision': revision,
                'node': subprocess.check_output(['node', '--version'], text=True).strip(),
                'bun': subprocess.check_output([*bun, '--version'], text=True).strip()}
    return shared.record_measurement(args.run_id, CASE, inputs, metadata,
                                     lambda a, run: measure(study, reference, source, historical, a, run, bun),
                                     command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
