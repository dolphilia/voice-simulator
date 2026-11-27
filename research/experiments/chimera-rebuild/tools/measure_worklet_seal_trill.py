"""アザラシの trill を実時間ブラウザ・CLI・固定上流で照合する。"""

from math import pi
from pathlib import Path

import numpy as np

import measure_wasm_fixed as wasm
from measure_seal_sustain_pcm import CANDIDATE, COMPONENTS, UPPER, columns, independent_output, internal, waveform
from measure_seal_trill import (
    CASE as SOURCE, CALL_FIELDS, GLOTTIS_TOLERANCES, OUTPUT_CASE, ROUGHNESS_FIELDS, boundary_checks,
    glottis_columns, glottis_internal, ideal_controls,
)
from measure_songbird_syrinx import CLI
from measure_worklet_seal_sustain import FIELDS, capture_health, capture_observations, compare_at, run
from measure_worklet_songbird import read_wave
from upstream_baseline import WORKSPACE


CASE = WORKSPACE / 'cases/worklet-seal-trill.json'
EXTRA_FIELDS = (*CALL_FIELDS, 'pulse_phase', 'call_id')
OBSERVATION_FIELDS = (*FIELDS, *EXTRA_FIELDS)


def observed_boundaries(points, observed, source, variant, spec):
    launch = source['events'][0]['frame']
    active = observed['call_id'] == 1
    transitions = np.diff(active.astype(int), prepend=0)
    starts, ends = points[transitions == 1], points[transitions == -1]
    changes = points[(points >= launch) & (observed['target_pitch_hz'] != source['shape']['pitch_hz'])]
    first_control = int(changes[0]) if changes.size else None
    end = variant['expected_end']
    checks = {
        'browser_call_start_end': starts.tolist() == [launch] and ends.tolist() == ([] if end is None else [end]),
        'browser_first_call_control': first_control == variant['expected_first_control'],
    }
    # 操作の直前と前後の制御時刻をブラウザの観測列から直接抜き出す。
    marks = {launch - 1, launch, variant['expected_first_control']}
    if end is not None:
        marks.update((end - 1, end))
    if variant['id'] == 'official-prefix-48000':
        start = variant['expected_first_control']
        end_key = start + round(spec['keys']['release_seconds'] * source['breath']['sample_rate_hz'])
        marks.update((spec['official_midpoint_frame'], end_key, end_key + spec['control_frames']))
    if variant['id'] == 'manual-restore-44100':
        marks.update(spec['manual_samples'].values())
    checks['browser_boundary_points_present'] = marks.issubset(set(points))
    rows = {
        str(frame): {key: float(observed[key][i]) for key in
                     ('call_id', 'control_clock_seconds', 'target_pitch_hz', 'pitch_hz', 'target_pulse_rate_hz',
                      'target_pressure_cm_h2o', 'gate_target', 'gate', 'lung_pressure_dyn_cm2')}
        for i, frame in enumerate(points) if frame in marks
    }
    return checks, {'launch_frames': starts.tolist(), 'first_control_frame': first_control,
                    'end_frames': ends.tolist(), 'snapshots': rows}


def evaluate_trill(points, observed, native_trace, source, variant, spec, **_capture):
    native_checks, _ = boundary_checks(native_trace, source, variant, spec)
    browser_checks, snapshots = observed_boundaries(points, observed, source, variant, spec)
    return native_checks | browser_checks, snapshots


def compare_variant(label, baseline, config, source, artifacts, execute, browser, module, *, evaluate=evaluate_trill):
    spec, m = source['measurement'], config['measurement']
    output_spec = wasm.read_json(OUTPUT_CASE)['measurement']
    variant = next(item for item in spec['variants'] if item['id'] == label)
    base = source['seal_voice']
    breath = base['breath'] | variant['breath']
    events = variant.get('events')
    input_ = base | {'breath': breath, 'events': base['events'] if events is None else events,
                     'shape': base['shape'] | variant.get('shape', {})}
    rate, frames = (breath[key] for key in ('sample_rate_hz', 'frames'))
    factor = 2 if rate <= 60000 else 1
    quantum = m['expected_render_quantum_frames']
    upper_dir = baseline / 'artifacts' / label
    replay_path = artifacts / f'{label}-case.json'
    if (wasm.read_json(upper_dir / 'case.json')['seal_voice'] != input_
            or wasm.read_json(replay_path) != {
                'id': f"{config['id']}-{label}", 'upstream_revision': config['upstream_revision'],
                'seal_voice': input_ | {'observe_call_id': True},
            }):
        raise ValueError(f'{label} の固定上流・登録・ブラウザ書き出しの入力が一致しません')

    wave_path, trace_path = (artifacts / f'{label}-native.{suffix}' for suffix in ('wav', 'csv'))
    execute([*CLI, 'render-pcm', str(replay_path), str(wave_path), str(trace_path), str(quantum)])
    native, audio = (read_wave(path, rate, frames) for path in (wave_path, artifacts / f'{label}.wav'))
    glottis_fields = tuple(GLOTTIS_TOLERANCES) if input_.get('observe_glottis') else ()
    roughness = ROUGHNESS_FIELDS if glottis_fields else ()
    glottis = glottis_columns(glottis_fields)
    native_trace = columns(trace_path, frames, (*CANDIDATE, *EXTRA_FIELDS, *roughness, *glottis))
    upper_call_ids = ('call_id',) if input_.get('observe_call_id') else ()
    upper_glottis = glottis_columns((*glottis_fields, 'shadow_area_error')) if glottis_fields else ()
    upper = columns(upper_dir / 'upstream.csv', frames,
                    (*UPPER, *CALL_FIELDS, *upper_call_ids, *roughness, *upper_glottis))
    upper_pcm = upper['pcm_f32'].astype(np.float32)
    cli_pcm = wasm.compare_pcm(audio, native, m['cli_pcm_absolute_tolerance'])
    upper_pcm_result = wasm.compare_pcm(audio, upper_pcm, spec['pcm_absolute_tolerance'])
    upper_pcm_result['different_bits'] = int(np.count_nonzero(audio.view('u4') != upper_pcm.view('u4')))

    report, points, clock, observed = capture_observations(
        label, m, artifacts, frames, (*OBSERVATION_FIELDS, *roughness, *glottis))
    cli_states = {key: compare_at(values, native_trace[key][points], m['cli_state_absolute_tolerance'], points)
                  for key, values in observed.items()}
    pressure, control_clock = 'lung_pressure_dyn_cm2', 'control_clock_seconds'
    upper_tolerances = {
        'active_call': 0.0, 'call_id': 0.0, control_clock: spec['clock_absolute_tolerance_seconds'],
        pressure: spec['direct_pressure_absolute_tolerance_dyn_cm2'],
        **{f'{key}_{phase}': spec['radiation_absolute_tolerance_cm3_s2'] if key == 'radiation'
           else output_spec['component_absolute_tolerance_cm3_s'] for key in COMPONENTS for phase in range(2)},
        **{f'{key}_{phase}': spec[GLOTTIS_TOLERANCES[key]] for key in glottis_fields for phase in range(2)},
    }
    upper_states = {key: compare_at(values, upper[key][points],
                                    upper_tolerances.get(key, spec['direct_control_absolute_tolerance']), points)
                    for key, values in observed.items() if key in upper}

    expected = ideal_controls(input_, spec)
    phases = (observed['pulse_phase'] - expected['pulse_phase'][points] + 0.5) % 1.0 - 0.5
    independent_limits = {
        'call_id': 0.0, 'active_call': 0.0, control_clock: spec['clock_absolute_tolerance_seconds'],
        pressure: spec['independent_pressure_absolute_tolerance_dyn_cm2'],
    }
    independent = {
        key: compare_at(values, expected[key][points],
                        independent_limits.get(key, spec['independent_control_absolute_tolerance']), points)
        for key, values in observed.items() if key in expected and key != 'pulse_phase'
    }
    independent['pulse_phase_circular_difference'] = compare_at(
        phases, np.zeros_like(phases), spec['independent_phase_circular_tolerance'], points)

    pressure_diagnostics = {}
    if spec.get('independent_pressure_phase_error_budget'):
        amplitude = (expected['pressure_cm_h2o'][points] * spec['cm_h2o_to_dyn_cm2']
                     * expected['gate'][points] * expected['pulse_depth'][points])
        bound = amplitude * (pi / expected['duty'][points]) * np.abs(phases)
        error = np.abs(observed[pressure] - expected[pressure][points])
        residual = np.maximum(error - bound, 0.0)
        pressure_diagnostics = {'independent_pressure_phase_budget': {
            'raw_pressure_comparison': independent[pressure],
            'maximum_phase_contribution_dyn_cm2': float(np.max(bound)),
        }}
        independent[pressure] = compare_at(residual, np.zeros_like(residual), independent_limits[pressure], points)

    raw = internal(native_trace, factor)
    upper_raw = internal(upper, factor)
    decimated, filtered, expected_pcm = independent_output(raw['radiation'], rate, factor, input_['level'], output_spec)
    independent['decimated'] = compare_at(observed['decimated'], decimated[points],
                                         spec['radiation_absolute_tolerance_cm3_s2'], points)
    independent['dc_removed'] = compare_at(observed['dc_removed'], filtered[points],
                                          output_spec['dc_absolute_tolerance'], points)
    independent_pcm = wasm.compare_pcm(audio, expected_pcm, spec['pcm_absolute_tolerance'])

    health, timing = capture_health(config, report, browser, module, rate, frames, factor)
    boundaries, snapshots = evaluate(
        points, observed, native_trace, input_, variant, spec, artifacts=artifacts, execute=execute,
        measurement=m, audio=audio, upper_pcm=upper_pcm, factor=factor,
    )
    expected_internal = (points + 1) * factor - 1
    checks = {
        'browser_cli_pcm_bits': cli_pcm['first_bit_difference_frame'] is None,
        'fixed_upstream_pcm': upper_pcm_result['first_frame_over_tolerance'] is None,
        'cli_states': all(result['passed'] for result in cli_states.values()),
        'fixed_upstream_states': all(result['passed'] for result in upper_states.values()),
        'independent_control_and_output': (all(result['passed'] for result in independent.values())
                                           and independent_pcm['first_frame_over_tolerance'] is None),
        'observation_clock': (np.array_equal(clock[:, 0], points) and np.array_equal(clock[:, 1], expected_internal)
                              and all(np.array_equal(trace['internal_sample'][points], expected_internal)
                                      for trace in (upper, native_trace))),
        'unused_internal_slots_zero': factor == 2
        or all(np.all(observed[f'{key}_1'] == 0) for key in (*COMPONENTS, *glottis_fields)),
        **boundaries, **health,
    }
    official_pcm = None
    if label == 'official-prefix-48000':
        official = waveform(baseline / 'artifacts/official-cli/seal.wav', breath)[:frames]
        official_pcm = wasm.compare_pcm(audio, official, spec['pcm_absolute_tolerance'])
        checks['official_cli_prefix'] = official_pcm['first_frame_over_tolerance'] is None
    first_differences = {
        'output_frames': {key: wasm.first_index(native_trace[key] != upper[key])
                          for key in (*CALL_FIELDS, *upper_call_ids, *roughness, 'gate', pressure)},
        'internal_samples': {
            **{key: wasm.first_index(raw[key] != upper_raw[key]) for key in COMPONENTS},
            **{key: wasm.first_index(glottis_internal(native_trace, key, factor)
                                     != glottis_internal(upper, key, factor)) for key in glottis_fields},
        },
    }
    return {
        'checks': checks, 'rate_hz': rate, 'frames': frames, 'factor': factor, 'observations': len(points),
        'cli_pcm': cli_pcm, 'upstream_pcm': upper_pcm_result, 'official_pcm': official_pcm,
        'upstream_difference_precursors': first_differences, 'cli_states': cli_states, 'upstream_states': upper_states,
        'independent': independent, 'independent_pcm': independent_pcm, **pressure_diagnostics, **snapshots, **timing,
    }


if __name__ == '__main__':
    raise SystemExit(run(CASE, SOURCE, compare_variant, 'seal_trill_render_does_not_allocate', (44100,), __doc__,
                         extra_sources=(Path(__file__).resolve(), OUTPUT_CASE,
                                        WORKSPACE / 'tools/measure_seal_trill.py')))
