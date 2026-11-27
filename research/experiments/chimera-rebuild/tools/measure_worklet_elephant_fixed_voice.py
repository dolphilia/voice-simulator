"""アフリカゾウの固定発声と放射の経路変更を実時間ブラウザで照合する。"""

import json

import numpy as np

import measure_elephant_fixed_voice as fixed
import measure_wasm_fixed as wasm
from measure_seal_sustain_pcm import columns
from measure_songbird_syrinx import CLI
from measure_worklet_seal_sustain import capture_health, capture_observations, compare_at, run
from measure_worklet_songbird import read_wave
from upstream_baseline import WORKSPACE, sha256


CASE = WORKSPACE / 'cases/worklet-elephant-fixed-voice.json'
OFFICIAL = 'official-sustain-48000'
STATE_FIELDS = fixed.CANDIDATE[1:-1]
CALL_OBSERVATION_FIELDS = ('call_id', 'control_clock_seconds', 'gate_goal', 'target_pitch_hz',
                           'target_pressure_cm_h2o', 'target_chaos')
VALVE_OBSERVATION_FIELDS = (*fixed.VALVE_FIELDS, 'reed_height_cm', 'reed_speed_cm_s')


def measurement_settings(source, baseline):
    parents = source.get('inherits_measurement', [])
    if isinstance(parents, str):
        parents = [parents]
    spec = {}
    if parents:
        manifest = wasm.read_json(baseline / 'manifest.json')
        hashes = {item['path']: item['sha256'] for item in manifest['inputs']}
        for name in parents:
            relative = f'cases/{name}'
            path = WORKSPACE / relative
            if hashes.get(relative) != sha256(path):
                raise ValueError(f'{relative} が基準マニフェストと一致しません')
            parent = wasm.read_json(path)
            spec.update(parent['measurement'])
            if 'lip_reed' in parent:
                spec['reed_parameters'] = parent['lip_reed']['parameters']
    return spec | source['measurement']


def route_target(case):
    target = np.full(case['frames'], case['shape']['trunk'])
    for event in case['events']:
        params = event.get('params', {})
        if 'trunk' in params:
            target[event['frame']:] = params['trunk']
    return target


def compare_route(case, variant, spec, points, observed, audio, measurement, artifacts, execute):
    frames, rate = case['frames'], case['sample_rate_hz']
    if not np.array_equal(points, np.arange(frames)):
        raise ValueError('放射経路の切り替えは全フレームを観測してください')
    browser_state = observed | {'pcm_f32': audio}
    routing_checks, routing = fixed.observe_routing(browser_state, case, variant, spec)
    control = measurement['route_control']
    omitted = control['omitted_event_frame']
    retained = [event for event in case['events'] if event['frame'] != omitted]
    settings = artifacts / 'fixed-oral-control-case.json'
    settings.write_text(json.dumps({'elephant_voice': case | {'events': retained}}, indent=2) + '\n')
    wave, csv = (artifacts / f'fixed-oral-control.{suffix}' for suffix in ('wav', 'csv'))
    execute([*CLI, 'render-pcm', str(settings), str(wave), str(csv), str(measurement['expected_render_quantum_frames'])])
    reference = columns(csv, frames, fixed.CANDIDATE)
    reference_audio = read_wave(wave, rate, frames)
    compared_fields = {
        'target_trunk': spec['tolerances']['control'],
        'trunk': spec['tolerances']['control'],
        'oral_tip_area_cm2': spec['tolerances']['area'],
        'velum_area_cm2': spec['tolerances']['area'],
        'nasal_base_pressure_dyn_cm2': control['pressure_threshold_dyn_cm2'],
        'trunk_inlet_pressure_dyn_cm2': control['pressure_threshold_dyn_cm2'],
        'trunk_tip_pressure_dyn_cm2': control['pressure_threshold_dyn_cm2'],
        'trunk_valve_flow_cm3_s': control['flow_threshold_cm3_s'],
        **{key: control['flow_threshold_cm3_s'] for key in fixed.COMPONENTS},
    }
    reference['target_trunk'] = np.full(frames, case['shape']['trunk'])
    deltas = {key: compare_at(observed[key], reference[key], limit, points)
              for key, limit in compared_fields.items()}
    first = {key: item['first_difference_output_frame'] for key, item in deltas.items()}
    base, valve, tip, near = (first[key] for key in ('nasal_base_pressure_dyn_cm2', 'trunk_valve_flow_cm3_s',
                                                    'trunk_tip_pressure_dyn_cm2', 'nasal_cm3_s'))
    boundary = control['first_control_frame']
    pcm = wasm.compare_pcm(audio, reference_audio, control['pcm_threshold'])
    first_pcm = pcm['first_bit_difference_frame']
    checks = {
        **{f'browser_route.{key}': passed for key, passed in routing_checks.items()},
        'comparison_route_target_changes_at_request': first['target_trunk'] == omitted,
        'comparison_route_areas_change_at_control': all(first[key] == boundary
                                                        for key in ('trunk', 'oral_tip_area_cm2', 'velum_area_cm2')),
        'comparison_route_pressure_propagates_through_trunk': (
            None not in (base, valve, tip, near) and boundary <= base < valve < tip <= near),
        'comparison_route_pcm_waits_for_control': first_pcm is not None and first_pcm >= boundary,
        'comparison_route_preserves_breath_pitch_and_valve': all(
            np.array_equal(observed[key], reference[key])
            for key in ('gate', 'pitch_hz', 'glottis_f0_hz', 'lung_pressure_dyn_cm2', 'trunk_valve_area_cm2')),
    }
    return checks, {'routing': routing, 'fixed_oral_control': {'differences': deltas, 'pcm': pcm}}


def compare_variant(label, baseline, config, source, artifacts, execute, browser, module, *,
                    control_model=fixed.control_reference, native_observe=fixed.observe_routing,
                    browser_observe=None, official_variant=OFFICIAL):
    spec, measurement = measurement_settings(source, baseline), config['measurement']
    variant = next(item for item in spec['variants'] if item['id'] == label)
    base = source['elephant_voice']
    case = base | {key: variant[key] for key in ('sample_rate_hz', 'frames', 'events') if key in variant}
    case['shape'] = base['shape'] | variant.get('shape', {})
    rate, frames = case['sample_rate_hz'], case['frames']
    upper_dir = baseline / 'artifacts' / label
    replay = artifacts / f'{label}-case.json'
    if (wasm.read_json(upper_dir / 'case.json')['elephant_voice'] != case
            or wasm.read_json(replay) != {'id': f"{config['id']}-{label}",
                                         'upstream_revision': config['upstream_revision'], 'elephant_voice': case}):
        raise ValueError(f'{label} の固定上流とブラウザの入力が一致しません')
    native_wav, native_csv = (artifacts / f'{label}-native.{suffix}' for suffix in ('wav', 'csv'))
    execute([*CLI, 'render-pcm', str(replay), str(native_wav), str(native_csv),
             str(measurement['expected_render_quantum_frames'])])
    native, audio = (read_wave(path, rate, frames) for path in (native_wav, artifacts / f'{label}.wav'))
    call_fields = fixed.CALL_FIELDS if case.get('observe_call') else ()
    native_extra = (*call_fields, 'gate_goal') if call_fields else ()
    valve_fields = fixed.VALVE_FIELDS if case.get('observe_valve') else ()
    upper_extra = (*valve_fields, 'reed_telemetry') if valve_fields else ()
    valve_observations = VALVE_OBSERVATION_FIELDS if valve_fields else ()
    candidate = columns(native_csv, frames, (*fixed.CANDIDATE, *native_extra, *valve_observations))
    upper = columns(upper_dir / 'upstream.csv', frames, (*fixed.UPPER, *call_fields, *upper_extra))
    coordinate = np.arange(frames)
    limits = spec['tolerances']
    cli_pcm = wasm.compare_pcm(audio, native, measurement['cli_pcm_absolute_tolerance'])
    upstream_pcm = wasm.compare_pcm(audio, upper['pcm_f32'].astype(np.float32), limits['pcm'])
    upstream_states = {key: compare_at(candidate[key], upper[key], fixed.tolerance(key, limits), coordinate)
                       for key in (*fixed.COMMON[1:], *call_fields, *valve_fields)}
    if valve_fields:
        upstream_states['reed_telemetry'] = compare_at(np.minimum(1, upper['reed_opening_cm2'] / 1.2),
                                                       upper['reed_telemetry'], limits['control'], coordinate)

    browser_call_fields = CALL_OBSERVATION_FIELDS if call_fields or valve_fields else ()
    fields = (*STATE_FIELDS, 'target_trunk', *browser_call_fields, *valve_observations)
    report, points, clock, observed = capture_observations(label, measurement, artifacts, frames, fields)
    cli_states = {key: compare_at(observed[key], candidate[key][points], measurement['cli_state_absolute_tolerance'],
                                  points) for key in fields if key in candidate}
    checks, routing = native_observe(candidate, case, variant, spec)
    browser_reference = control_model(case, spec)
    if not call_fields:
        browser_reference['target_trunk'] = route_target(case)
    pitch_limits = {key: spec['independent_pitch_tolerance_hz']
                    for key in ('pitch_hz', 'target_pitch_hz')} if 'independent_pitch_tolerance_hz' in spec else {}
    browser_independent = {key: compare_at(observed[key], expected[points],
                                         pitch_limits.get(key, fixed.tolerance(key, limits)), points)
                           for key, expected in browser_reference.items()}
    expected_output = fixed.output_reference(candidate, case, spec)
    overrides = {'decimated': limits['radiation'], 'dc_removed': limits['dc']}
    independent = {key: compare_at(audio if key == 'pcm_f32' else candidate[key], values,
                                   overrides.get(key, fixed.tolerance(key, limits)), coordinate)
                   for key, values in expected_output.items()}
    health, timing = capture_health(config, report, browser, module, rate, frames, 1)
    checks.update({
        'browser_cli_pcm_bits': cli_pcm['first_bit_difference_frame'] is None,
        'browser_cli_states': all(result['passed'] for result in cli_states.values()),
        'fixed_upstream_pcm': upstream_pcm['first_frame_over_tolerance'] is None,
        'fixed_upstream_states': all(result['passed'] for result in upstream_states.values()),
        'upstream_shadow_areas': bool(np.all(upper['shadow_area_error_cm2'] <= limits['area'])),
        'browser_independent_controls': all(result['passed'] for result in browser_independent.values()),
        'independent_output_and_glottis_pressure': all(result['passed'] for result in independent.values()),
        'observation_clock': np.array_equal(clock[:, 0], points) and np.array_equal(clock[:, 1], points)
        and all(np.array_equal(trace['frame'], coordinate) for trace in (candidate, upper)),
        **health,
    })
    details = {}
    if arrival_names := measurement.get('arrival_fields'):
        arrivals = {}
        for key in arrival_names:
            index = fixed.first_nonzero(observed[key])
            arrivals[key] = None if index is None else int(points[index])
        details['arrival_output_frames'] = arrivals
        checks['browser_trunk_arrivals'] = list(arrivals.values()) == measurement['arrival_output_frames'][label]
    if label == measurement.get('route_control', {}).get('variant'):
        added, route_details = compare_route(case, variant, spec, points, observed, audio, measurement, artifacts, execute)
        checks.update(added)
        details.update(route_details)
    if browser_observe:
        added, observations = browser_observe(case, variant, spec, points, observed, audio)
        checks.update(added)
        details.update(observations)
    if label == official_variant:
        official = fixed.waveform(baseline / 'artifacts/official-cli/elephant.wav', case)[:frames]
        details['official_pcm'] = wasm.compare_pcm(audio, official, limits['pcm'])
        checks['official_prefix'] = details['official_pcm']['first_frame_over_tolerance'] is None
        checks['official_reference_agrees_with_probe'] = np.array_equal(
            official.view('u4'), upper['pcm_f32'].astype(np.float32).view('u4'))

    return {
        'checks': checks, 'frames': frames, 'rate_hz': rate, 'browser_observations': len(points),
        'cli_pcm': cli_pcm, 'upstream_pcm': upstream_pcm,
        'upstream_states': upstream_states, 'cli_states': cli_states, 'browser_independent': browser_independent,
        'independent_output': independent, 'native_routing': routing, **details, **timing,
    }


if __name__ == '__main__':
    raise SystemExit(run(CASE, fixed.CASE, compare_variant, 'elephant_fixed_render_does_not_allocate', (44100, 96000),
                         __doc__, extra_sources=(WORKSPACE / 'tools/measure_elephant_fixed_voice.py',),
                         creature='elephant', official_variant=OFFICIAL,
                         upstream_files=('crates/chimera/src/creatures/build.rs',
                                         'crates/chimera/src/airway/network.rs',
                                         'crates/chimera-cli/src/render.rs', 'crates/chimera/tests/engine.rs')))
