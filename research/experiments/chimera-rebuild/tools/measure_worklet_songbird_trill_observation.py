"""鳴禽trillの観測点を変え、PCM・内部状態・量子処理時間を対照する。"""

from itertools import combinations
from pathlib import Path

import numpy as np

import measure_wasm_fixed as wasm
import measure_worklet_songbird_call as common
import measure_worklet_songbird_trill as trill
from measure_worklet_realtime import timing_summary
from measure_worklet_songbird import read_wave
from upstream_baseline import WORKSPACE, sha256


CASE = WORKSPACE / 'cases/worklet-songbird-trill-observation.json'


def expected_render_calls(points, input_, quantum):
    frames = input_['frames']
    ends = np.unique(np.r_[np.arange(quantum, frames, quantum), frames, points + 1,
                           [event['frame'] for event in input_['events'] if event['frame'] > 0]])
    return np.bincount((ends - 1) // quantum)


def compare_trial(trial, artifacts, expected, profile, config, reference_audio, native_trace, fields, module_hash):
    artifact_id = trial['artifactId']
    replay = wasm.read_json(artifacts / f'{artifact_id}-case.json')
    report = wasm.read_json(artifacts / f'{artifact_id}.json')
    input_ = expected['songbird_voice']
    rate, frames = (input_[key] for key in ('sample_rate_hz', 'frames'))
    m = config['measurement']
    quantum = m['expected_render_quantum_frames']
    points = np.union1d(np.arange(profile['offset'], frames, profile['stride']),
                        [frames - 1, *m['extra_output_frames']])
    factor = 4
    timing = np.asarray(report['timing'], dtype=float)
    observations = np.asarray(report['observations'], dtype=float)
    calls = np.asarray(report['renderCalls'])
    expected_calls = expected_render_calls(points, input_, quantum)
    if (report['timingColumns'] != ['context_frame', 'quantum_frames', 'process_ms']
            or timing.shape != (len(expected_calls), 3) or not np.isfinite(timing).all() or (timing[:, 2] < 0).any()
            or report['columns'] != ['output_frame', 'internal_sample', *fields]
            or observations.shape != (len(points), len(fields) + 2) or not np.isfinite(observations).all()):
        raise ValueError(f'{artifact_id} の観測点・計時列を確認できません')
    budget = quantum * 1000 / rate
    warmup = m['health']['exclude_startup_blocks']
    measured = timing_summary(timing[warmup:, 2], budget)
    measurement = measured | {
        'p95_within_budget': measured['p95_ms'] < budget * m['health']['maximum_processing_p95_budget_ratio'],
        'clock': report['timingClock'],
    }
    audio = read_wave(artifacts / f'{artifact_id}.wav', rate, frames)
    pcm = wasm.compare_pcm(audio, reference_audio, m['cli_pcm_absolute_tolerance'])
    reference_states = np.column_stack([native_trace[field][points] for field in fields])
    cli_states = {field: common.compare(values, expected_values, m['browser_state_absolute_tolerance'])
                  for field, values, expected_values in zip(fields, observations[:, 2:].T, reference_states.T, strict=True)}
    for item in cli_states.values():
        index = item.pop('first_difference_sample')
        item['first_difference_output_frame'] = None if index is None else int(points[index])
        index = item.pop('first_over_tolerance_sample')
        item['first_over_tolerance_output_frame'] = None if index is None else int(points[index])
    checks = {
        'same_replay_input': replay == expected,
        'same_wasm_and_valid_downloads': (trial['servedWasmSha256'] == module_hash and trial['controlsReset']
                                          and not trial['errors'] and round(trial['audioDuration'] * rate) == frames),
        'browser_rate_and_context': (report['sampleRate'] == report['workletSampleRate'] == rate
                                     and report['outputFrames'] == frames and report['factor'] == factor
                                     and report['caseId'] == config['id'] and report['contextState'] == 'running'),
        'observation_schedule': (len(points) == profile['observations'] and np.array_equal(observations[:, 0], points)
                                 and np.array_equal(observations[:, 1], (points + 1) * factor - 1)),
        'audio_quanta_contiguous': bool(np.all(timing[:, 1] == quantum) and np.all(np.diff(timing[:, 0]) == quantum)),
        'render_calls_at_expected_boundaries': np.array_equal(calls, expected_calls)
        and int(calls.sum()) == profile['render_calls'],
        'cli_pcm_bits': pcm['first_bit_difference_frame'] is None,
        'cli_states': all(item['passed'] for item in cli_states.values()),
    }
    steps = {'observations': len(points), 'calls': int(calls.sum()), 'calls_after_startup': int(calls[warmup:].sum()),
             'first_quantum_calls': int(calls[0]), 'replay_comparison': checks, 'render_budget_ms': budget,
             'timing': measurement, 'cli_pcm': pcm, 'cli_states': cli_states,
             'startup_discontinuities': report['startupDiscontinuities']}
    return steps, points, observations


def compare_experiment(baseline, config, source, sustain, definitions, artifacts, execute, browser, module, evaluate):
    m = config['measurement']
    label, = m['variants']
    profiles = {profile['id']: profile for profile in m['observation_profiles']}
    expected_order = [(i, profile, f'{i}-{profile}') for i, order in enumerate(m['capture_order'], 1) for profile in order]
    trials = browser['trials']
    if [(r['round'], r['profile'], r['artifactId']) for r in trials] != expected_order:
        raise ValueError('比較の実行順が登録条件と一致しません')
    first = trials[0]
    reference = common.compare_variant(label, baseline, config, source, sustain, definitions,
                                       artifacts, execute, first, module, evaluate, capture_id=first['artifactId'])
    expected = wasm.read_json(artifacts / f"{first['artifactId']}-case.json")
    rate, frames = reference['rate_hz'], reference['frames']
    audio = read_wave(artifacts / f'{label}-native.wav', rate, frames)
    params = tuple(sustain['measurement']['parameter_time_constants_seconds'])
    fields = (*common.BASE_FIELDS, *common.CALL_COLUMNS, *params, *(f'target_{key}' for key in params))
    native_trace = common.trace(artifacts / f'{label}-native.csv', frames, common.NATIVE_FIELDS)
    module_hash = sha256(module)
    checks = {f'fixed_reference.{key}': passed for key, passed in reference['checks'].items()
              if key != 'realtime_processing_budget_p95'}
    reports, shared = {}, {}
    first_observations = {}
    for trial in trials:
        profile, artifact_id = trial['profile'], trial['artifactId']
        data, points, states = compare_trial(trial, artifacts, expected, profiles[profile],
                                             config, audio, native_trace, fields, module_hash)
        reports[artifact_id] = {'round': trial['round'], 'profile': profile, **data}
        checks.update({f'{artifact_id}.{name}': value for name, value in data['replay_comparison'].items()})
        first_points, first_states = first_observations.setdefault(profile, (points, states))
        checks[f'{artifact_id}.repeat_observations'] = np.array_equal(points, first_points) and np.array_equal(states, first_states)
    checks['same_timing_clock'] = len({r['timing']['clock'] for r in reports.values()}) == 1
    for (first_id, second_id), count in zip(combinations(profiles, 2), m['expected_shared_observations'], strict=True):
        first_points, first_states = first_observations[first_id]
        second_points, second_states = first_observations[second_id]
        both, i, j = np.intersect1d(first_points, second_points, assume_unique=True, return_indices=True)
        pair = f'{first_id}__{second_id}'
        matching = np.array_equal(first_states[i], second_states[j])
        shared[pair] = {'observations': len(both), 'same_states': matching}
        checks[f'{pair}.shared_states'] = len(both) == count and matching
    performance = {}
    for profile in profiles:
        timings = [r['timing'] for r in reports.values() if r['profile'] == profile]
        performance[profile] = {
            'p95_by_round_ms': [t['p95_ms'] for t in timings],
            'p99_by_round_ms': [t['p99_ms'] for t in timings],
            'over_budget_blocks_by_round': [t['over_budget_blocks'] for t in timings],
            'trials_within_p95_budget': sum(t['p95_within_budget'] for t in timings),
        }
    return {'checks': checks, 'trials': reports, 'fixed_reference': reference, 'shared_observations': shared,
            'performance_by_profile': performance}


if __name__ == '__main__':
    raise SystemExit(common.run(CASE, trill.SOURCE, 'definitions.json', trill.evaluate, Path(__file__).resolve(),
                                __doc__, compare_experiment=compare_experiment, extra_sources=(Path(trill.__file__),)))
