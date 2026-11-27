"""アリゲーターのコールを実時間ブラウザとCLI・固定上流で照合する共通手順。"""

import numpy as np

import measure_alligator_bellow as call
import measure_wasm_fixed as wasm
from measure_seal_sustain_pcm import columns
from measure_songbird_syrinx import CLI
from measure_worklet_alligator_fixed_voice import FRAME_FIELDS, OBSERVATION_FIELDS, SAMPLE_FIELDS, browser_samples
from measure_worklet_seal_sustain import capture_health, capture_observations, compare_at
from measure_worklet_songbird import read_wave
from upstream_baseline import WORKSPACE


OFFICIAL = 'official-prefix-48000'
CALL_FIELDS = ('call_id', 'control_clock_seconds', *call.PARAMETERS, *call.TARGETS)


def compare_variant(label, baseline, config, source, artifacts, execute, browser, module, *,
                    call_name, boundary_checks, observe, extra_measurement=None, official_variant=OFFICIAL):
    spec = {}
    parents = source['inherits_measurement']
    for name in (parents,) if isinstance(parents, str) else parents:
        spec.update(wasm.read_json(WORKSPACE / 'cases' / name)['measurement'])
    spec.update(source['measurement'])
    measurement = config['measurement']
    variant = next(item for item in spec['variants'] if item['id'] == label)
    base = source['alligator_voice']
    case = base | {key: variant[key] for key in ('sample_rate_hz', 'frames', 'events') if key in variant}
    case['shape'] = base['shape'] | variant.get('shape', {})
    rate, frames = case['sample_rate_hz'], case['frames']
    factor = 2 if rate <= 60000 else 1
    upper_dir = baseline / 'artifacts' / label
    replay = artifacts / f'{label}-case.json'
    if (wasm.read_json(upper_dir / 'case.json')['alligator_voice'] != case
            or wasm.read_json(replay) != {'id': f"{config['id']}-{label}",
                                         'upstream_revision': config['upstream_revision'], 'alligator_voice': case}):
        raise ValueError(f'{label} の固定上流・登録・ブラウザ書き出しの入力が一致しません')

    wave, trace = (artifacts / f'{label}-native.{suffix}' for suffix in ('wav', 'csv'))
    execute([*CLI, 'render-pcm', str(replay), str(wave), str(trace),
             str(measurement['expected_render_quantum_frames'])])
    native, audio = (read_wave(path, rate, frames) for path in (wave, artifacts / f'{label}.wav'))
    noise_fields = call.NOISE_FIELDS if case.get('observe_noise') else ()
    candidate = columns(trace, frames * factor, (*call.CANDIDATE, *noise_fields))
    upper = columns(upper_dir / 'upstream.csv', frames * factor, (*call.UPPER, *noise_fields))
    cli_pcm = wasm.compare_pcm(audio, native, measurement['cli_pcm_absolute_tolerance'])
    comparison, upper_pcm = call.examine(candidate, upper, audio, case, variant, spec, boundary_checks)
    if extra_measurement:
        name, measure = extra_measurement
        extra_checks, comparison[name] = measure(candidate, upper, audio, case, variant, spec)
        comparison['checks'].update(extra_checks)
    if label == official_variant:
        call.compare_official(comparison, case, audio, upper_pcm, baseline / 'artifacts/official-cli/alligator.wav',
                              spec, call_name)

    noise_columns = tuple(f'{key}_{phase}' for phase in range(2) for key in noise_fields)
    observation_fields = (*OBSERVATION_FIELDS, *CALL_FIELDS, *noise_columns)
    report, points, clock, observed = capture_observations(label, measurement, artifacts, frames, observation_fields)
    last = (points + 1) * factor - 1
    tol = measurement['cli_state_absolute_tolerance']
    states = {key: compare_at(observed[key], candidate[key][last], tol, points)
              for key in (*FRAME_FIELDS, *CALL_FIELDS)}
    sample_fields = (*SAMPLE_FIELDS, *noise_fields)
    samples, state = browser_samples(observed, points, factor, sample_fields)
    states.update({key: compare_at(state[key], candidate[key][samples], tol, samples, coordinate='internal_sample')
                   for key in sample_fields})
    health, timing = capture_health(config, report, browser, module, rate, frames, factor)
    checks = {
        **comparison['checks'],
        'browser_cli_pcm_bits': cli_pcm['first_bit_difference_frame'] is None,
        'browser_cli_states': all(value['passed'] for value in states.values()),
        'observation_clock': np.array_equal(clock[:, 0], points) and np.array_equal(clock[:, 1], last),
        'unused_internal_slots_zero': factor == 2 or all(np.all(observed[f'{key}_1'] == 0) for key in sample_fields),
        **health,
    }
    extra_checks, extra = observe(case, variant, spec, points, observed, samples, state, audio)
    checks.update(extra_checks)
    return {
        **comparison, **timing, 'checks': checks, 'frames': frames, 'rate_hz': rate, 'factor': factor,
        'browser_observations': len(points), 'cli_pcm': cli_pcm, 'cli_states': states, **extra,
    }
