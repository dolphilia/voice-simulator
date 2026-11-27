"""アザラシの下行コールを上流レンダーと独立したキー計算に照合する。"""

import argparse
import json
from math import exp, log, pi, sin, sqrt
from pathlib import Path
import re
import subprocess

import numpy as np

from measure_seal_sustain_pcm import (CANDIDATE, UPPER, columns, first_nonzero, independent_output,
                                      internal, waveform)
from measure_songbird_syrinx import CLI, compare, read
import measure_uniform_tube as shared
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/seal-trill.json'
OUTPUT_CASE = WORKSPACE / 'cases/seal-sustain-pcm.json'
PROBE = WORKSPACE / 'tools/upstream_seal_voice_probe.rs'
PARAMETERS = ('pitch_hz', 'pulse_rate_hz', 'pulse_depth', 'duty', 'pressure_cm_h2o')
TARGETS = tuple('target_' + key for key in PARAMETERS)
CALL_FIELDS = ('active_call', 'control_clock_seconds', 'pitch_hz', 'target_pitch_hz',
               *PARAMETERS[1:], *TARGETS[1:])
CALL_IDS = {'trill': 1, 'zap': 2, 'whistle': 3, 'chug': 4}
ROUGHNESS_FIELDS = ('roughness', 'target_roughness')
GLOTTIS_TOLERANCES = {
    'glottis_phase': 'glottis_phase_absolute_tolerance',
    'glottis_f0_hz': 'glottis_f0_absolute_tolerance_hz',
    'glottis_area_cm2': 'glottis_area_absolute_tolerance_cm2',
}


def glottis_columns(fields):
    return tuple(f'{key}_{sub}' for sub in range(2) for key in fields)


def glottis_internal(trace, field, factor):
    return np.column_stack([trace[f'{field}_{sub}'] for sub in range(factor)]).ravel()


def ideal_controls(case, spec):
    breath = case['breath']
    rate, frames = breath['sample_rate_hz'], breath['frames']
    stride = spec['control_frames']
    dt = stride / rate
    keys = spec['keys']
    durations = spec['smoothing_seconds']
    retained = {key: exp(-dt / tau) for key, tau in durations.items()}
    manual = {'pitch_hz': case['shape']['pitch_hz'], **breath['controls']}
    parameters = PARAMETERS
    roughness_fields = ()
    if case.get('observe_glottis'):
        parameters = (*PARAMETERS, 'roughness')
        roughness_fields = ROUGHNESS_FIELDS
        manual['roughness'] = case['shape']['roughness']
        retained['roughness'] = exp(-dt / spec['roughness_smoothing_seconds'])
    goal, state = manual.copy(), manual.copy()
    base = state['pulse_rate_hz'] * dt
    compensation, phase = 0.0, base % 1
    gate = manual_gate = gate_target = clock = pressure = 0.0
    call = None
    breath_events = {item['frame']: item for item in breath['events']}
    call_events = {item['frame']: item for item in case['events']}
    times = sorted(set(range(0, frames, stride)) | breath_events.keys() | call_events.keys())
    # キーの有効区間は上流の累積時計で判定し、曲線はフレーム差で独立に求める。
    accumulated_clock = np.r_[0.0, np.cumsum(np.full((frames + stride - 1) // stride, dt))]
    result = {key: np.empty(frames) for key in
              (*CALL_FIELDS, *roughness_fields, 'call_id', 'gate', 'gate_target',
               'pulse_phase', 'lung_pressure_dyn_cm2')}
    for start, stop in zip(times, times[1:] + [frames], strict=True):
        if event := breath_events.get(start):
            manual_gate = min(1.5, max(0.0, event.get('gate', manual_gate)))
            if controls := event.get('controls'):
                manual.update(controls)
                if call is None:
                    goal.update(controls)
                else:
                    editable = ('pressure_cm_h2o',)
                    if call[1]['id'] in ('zap', 'whistle'):
                        editable += ('pulse_rate_hz', 'duty')
                    goal.update({key: controls[key] for key in editable})
        if event := call_events.get(start):
            if 'pitch_hz' in event:
                manual['pitch_hz'] = event['pitch_hz']
                if call is None:
                    goal['pitch_hz'] = manual['pitch_hz']
            if roughness_fields and 'roughness' in event:
                manual['roughness'] = min(0.8, max(0.0, event['roughness']))
                if call is None or call[1]['id'] != 'chug':
                    goal['roughness'] = manual['roughness']
            if 'play_call' in event:
                goal = manual.copy()
                call = (((start + stride - 1) // stride) * stride, event['play_call'])
            if event.get('stop_call'):
                call = None
                goal = manual.copy()
        if start % stride == 0:
            command = 0.0
            if call is not None:
                origin, inputs = call
                elapsed = (start - origin) / rate
                name = inputs['id']
                current_keys = keys if name == 'trill' else spec[f'{name}_keys']
                end_time = current_keys['release_seconds'] + current_keys['ownership_tail_seconds']
                clock_elapsed = accumulated_clock[start // stride] - accumulated_clock[origin // stride]
                if clock_elapsed > end_time:
                    call = None
                    goal = manual.copy()
                else:
                    fraction = min(1.0, elapsed / current_keys['sweep_seconds'])
                    lower_pitch, upper_pitch = current_keys['initial_pitch_hz'], current_keys['final_pitch_hz']
                    if name == 'whistle':
                        turn = current_keys['turn_seconds']
                        if elapsed < turn:
                            upper_pitch = current_keys['turn_pitch_hz']
                            fraction = elapsed / turn
                        else:
                            lower_pitch = current_keys['turn_pitch_hz']
                            fraction = min(1.0, (elapsed - turn) / (current_keys['sweep_seconds'] - turn))
                    pitch = exp((1 - fraction) * log(lower_pitch) + fraction * log(upper_pitch))
                    reference_pitch = current_keys['reference_pitch_hz']
                    pitch *= (inputs.get('pitch_hz', 0.0) or reference_pitch) / reference_pitch
                    low, high = spec['pitch_limits_hz']
                    goal['pitch_hz'] = min(high, max(low, pitch))
                    goal['pulse_depth'] = current_keys['pulse_depth']
                    if name == 'chug':
                        goal['pulse_rate_hz'] = current_keys['pulse_rate_hz']
                        goal['duty'] = current_keys['duty']
                        if roughness_fields:
                            rough_start = current_keys['initial_roughness']
                            rough_end = current_keys['final_roughness']
                            mix = min(1.0, elapsed / current_keys['release_seconds'])
                            goal['roughness'] = (1.0 - mix) * rough_start + mix * rough_end
                        edge = ((current_keys['release_seconds'] - elapsed)
                                / (current_keys['release_seconds'] - current_keys['sweep_seconds']))
                    elif name != 'trill':
                        edge = 1.0 - elapsed / current_keys['release_seconds']
                    else:
                        goal['pulse_rate_hz'] = exp((1 - fraction) * log(keys['initial_pulse_rate_hz'])
                                                   + fraction * log(keys['final_pulse_rate_hz']))
                        goal['duty'] = keys['duty']
                        edge = (keys['release_seconds'] - elapsed) / (keys['release_seconds'] - keys['sweep_seconds'])
                    command = inputs.get('amplitude', 1.0) * min(1.0, max(0.0, edge))
            for key in parameters:
                old, new, decay = state[key], goal[key], retained[key]
                if old != new:
                    state[key] = (exp(decay * log(old) + (1 - decay) * log(new))
                                  if key in ('pitch_hz', 'pulse_rate_hz') else new + (old - new) * decay)
            gate_target = max(manual_gate, command)
            decay = retained['gate_attack' if gate_target > gate else 'gate_release']
            gate = gate_target + (gate - gate_target) * decay
            delta = state['pulse_rate_hz'] * dt - compensation
            updated = base + delta
            compensation = (updated - base) - delta
            base = updated
            phase = base % 1
            duty = state['duty']
            window = sin(pi * phase / duty) if phase < duty else 0.0
            pressure = (state['pressure_cm_h2o'] * gate * spec['cm_h2o_to_dyn_cm2']
                        * (1 - state['pulse_depth'] * (1 - window)))
            clock = (start // stride + 1) * dt
        window = slice(start, stop)
        for key in parameters:
            result[key][window] = state[key]
            result['target_' + key][window] = goal[key]
        for key, value in (('active_call', call is not None), ('control_clock_seconds', clock),
                           ('call_id', CALL_IDS[call[1]['id']] if call is not None else 0),
                           ('gate', gate), ('gate_target', gate_target), ('pulse_phase', phase),
                           ('lung_pressure_dyn_cm2', pressure)):
            result[key][window] = value
    return result


def boundary_checks(trace, source, variant, spec):
    name = variant['id']
    launch = source['events'][0]['frame']
    expected_first, expected_end = (variant[key] for key in ('expected_first_control', 'expected_end'))
    active = trace['active_call'] > 0.5
    active_start = first_nonzero(active)
    disabled = np.flatnonzero(np.diff(active.astype(int)) < 0)
    end = int(disabled[0] + 1) if disabled.size else None
    before_pitch = source['shape']['pitch_hz']
    first = first_nonzero(trace['target_pitch_hz'][launch:] != before_pitch)
    initial_control = None if first is None else launch + first
    checks = {'active_at_launch': active_start == launch, 'first_control': initial_control == expected_first,
              'end': end == expected_end}
    result = {'launch_frame': launch, 'first_control_frame': initial_control, 'end_frame': end}
    limit = spec['independent_control_absolute_tolerance']
    near = lambda key, index, value: bool(abs(trace[key][index] - value) <= limit)
    if name == 'official-prefix-48000':
        index = spec['official_midpoint_frame']
        keys = spec['keys']
        checks['pitch_geometric_midpoint'] = near('target_pitch_hz', index,
                                                 sqrt(keys['initial_pitch_hz'] * keys['final_pitch_hz']))
        checks['pulse_geometric_midpoint'] = near('target_pulse_rate_hz', index,
                                                 sqrt(keys['initial_pulse_rate_hz'] * keys['final_pulse_rate_hz']))
        result['midpoint'] = {key: float(trace[key][index]) for key in ('target_pitch_hz', 'target_pulse_rate_hz')}
        if end is not None:
            initial_breath = tuple(source['breath']['controls'][key] for key in PARAMETERS[1:])
            checks['restores_default_targets'] = all(near(key, end, value) for key, value in zip(
                TARGETS, (before_pitch, *initial_breath), strict=True))
    elif name == 'manual-restore-44100':
        marks = spec['manual_samples']
        pressure_edit = marks['performer_breath_edit']
        pitch_edit = marks['performer_pitch_edit']
        stop = variant['expected_end']
        resumed = marks['after_stop_control']
        checks['transposes_only_pitch'] = (near('target_pitch_hz', expected_first, 1800.0)
                                          and near('target_pulse_rate_hz', expected_first, 42.0))
        checks['pressure_not_owned'] = near('target_pressure_cm_h2o', pressure_edit, 14.0)
        checks['holds_owned_targets'] = (not near('target_pitch_hz', pitch_edit, 1250.0)
                                         and not near('target_pulse_rate_hz', pressure_edit, 27.0)
                                         and near('target_pulse_depth', pressure_edit, 0.9)
                                         and near('target_duty', pressure_edit, 0.5))
        checks['manual_gate_maximum'] = (near('gate_target', marks['higher_manual_gate'], 0.8)
                                         and near('gate_target', marks['lower_manual_gate'], 0.6)
                                         and near('gate_target', resumed, 0.35))
        checks['restores_manual_targets'] = all(near(key, stop, value) for key, value in zip(
            TARGETS, (1250.0, 27.0, 0.2, 0.65, 14.0), strict=True))
        checks['smoothing_waits_for_control'] = (bool(trace['pitch_hz'][stop] == trace['pitch_hz'][stop - 1])
                                                and bool(trace['pitch_hz'][resumed] != trace['pitch_hz'][stop]))
        result['handoff'] = {
            str(index): {key: float(trace[key][index]) for key in
                         ('pitch_hz', 'target_pitch_hz', 'pulse_rate_hz', 'target_pulse_rate_hz', 'gate_target')}
            for index in (stop - 1, stop, resumed)
        }
    else:
        checks['pitch_clamps_after_transpose'] = near('target_pitch_hz', expected_first, 6000.0)
        checks['pulse_is_not_transposed'] = near('target_pulse_rate_hz', expected_first, 42.0)
        checks['amplitude_scales_gate'] = near('gate_target', expected_first, 1.7)
        result['first_targets'] = {key: float(trace[key][expected_first]) for key in
                                   ('target_pitch_hz', 'target_pulse_rate_hz', 'gate_target')}
    return checks, result


def capture(variant, source, folder, execute, probe, spec, output_spec, official, *,
            evaluate_boundaries=boundary_checks):
    folder.mkdir()
    path, settings, upper = (folder / name for name in ('case.json', 'inspect.json', 'upstream.csv'))
    path.write_text(json.dumps({'seal_voice': source}, indent=2) + '\n')
    execute([*CLI, 'inspect', str(path)], stdout=settings)
    execute([str(probe), str(path)], cwd=UPSTREAM, stdout=upper)
    products = []
    for block in spec['host_block_frames']:
        wav, csv = (folder / f'pcm-{block}.{suffix}' for suffix in ('wav', 'csv'))
        execute([*CLI, 'render-pcm', str(path), str(wav), str(csv), str(block)])
        products.append((wav, csv))
    wav, csv = products[0]
    breath = source['breath']
    frames, rate = breath['frames'], breath['sample_rate_hz']
    pcm = waveform(wav, breath)
    id_fields = ('call_id',) if source.get('observe_call_id') else ()
    roughness_fields = ROUGHNESS_FIELDS if source.get('observe_glottis') else ()
    glottis_fields = glottis_columns(GLOTTIS_TOLERANCES) if roughness_fields else ()
    upstream_glottis_fields = glottis_columns((*GLOTTIS_TOLERANCES, 'shadow_area_error')) if roughness_fields else ()
    candidate = columns(csv, frames, (*CANDIDATE, *CALL_FIELDS, 'pulse_phase',
                                      *id_fields, *roughness_fields, *glottis_fields))
    upstream = columns(upper, frames, (*UPPER, *CALL_FIELDS, *id_fields,
                                       *roughness_fields, *upstream_glottis_fields))
    expected = ideal_controls(source, spec)
    factor = 2 if rate <= 60000 else 1
    indexes = (np.arange(frames) + 1) * factor - 1
    info = read(settings)
    upper_pcm = upstream['pcm_f32'].astype(np.float32)
    checks = {
        'frame_count': len(pcm) == frames,
        'wav_matches_csv': np.array_equal(pcm.view('u4'), candidate['pcm_f32'].astype(np.float32).view('u4')),
        'host_block_invariance': all(sha256(w) == sha256(wav) and sha256(c) == sha256(csv) for w, c in products),
        'factor': info['decimation_factor'] == factor and info['internal_rate_hz'] == rate * factor,
        'internal_indices': np.array_equal(candidate['internal_sample'], indexes)
        and np.array_equal(upstream['internal_sample'], indexes),
    }
    clock = spec['clock_absolute_tolerance_seconds']
    tolerance = spec['direct_control_absolute_tolerance']
    pressure = 'lung_pressure_dyn_cm2'
    pcm_tol = spec['pcm_absolute_tolerance']
    raw_tol = spec['radiation_absolute_tolerance_cm3_s2']
    direct = {key: compare(candidate[key], upstream[key], tolerance)
              for key in ('gate', *PARAMETERS, *TARGETS, *roughness_fields)}
    direct.update({
        'active_call': compare(candidate['active_call'], upstream['active_call'], 0),
        'control_clock_seconds': compare(candidate['control_clock_seconds'], upstream['control_clock_seconds'], clock),
        pressure: compare(candidate[pressure], upstream[pressure], spec['direct_pressure_absolute_tolerance_dyn_cm2']),
        'pcm': compare(pcm, upper_pcm, pcm_tol),
    })
    if id_fields:
        direct['call_id'] = compare(candidate['call_id'], upstream['call_id'], 0)
    if roughness_fields:
        for field, limit in GLOTTIS_TOLERANCES.items():
            direct[field] = compare(glottis_internal(candidate, field, factor),
                                    glottis_internal(upstream, field, factor), spec[limit])
        area_error = glottis_internal(upstream, 'shadow_area_error', factor)
        direct['shadow_area_error'] = compare(area_error, np.zeros_like(area_error),
                                              spec['upper_shadow_area_absolute_tolerance_cm2'])
    if variant['id'] == 'official-prefix-48000':
        prefix = waveform(official, breath)[:frames]
        checks['probe_agrees_with_official_cli'] = np.array_equal(prefix.view('u4'), upper_pcm.view('u4'))
        direct['official_cli'] = compare(pcm, prefix, pcm_tol)
    radiation = [internal(trace, factor)['radiation'] for trace in (candidate, upstream)]
    direct['internal_radiation'] = compare(*radiation, raw_tol)
    checks.update({f'upstream.{key}': value['passed'] for key, value in direct.items()})

    independence = {}
    phase_error = (candidate['pulse_phase'] - expected['pulse_phase'] + 0.5) % 1 - 0.5
    pressure_budget = None
    pressure_diagnostics = {}
    if spec.get('independent_pressure_phase_error_budget'):
        # 半正弦パルスは静止区間と連続で、円周上での傾きは Aπ/d 以下。
        pulse_scale = (expected['pressure_cm_h2o'] * spec['cm_h2o_to_dyn_cm2']
                       * expected['gate'] * expected['pulse_depth'])
        pressure_budget = pulse_scale * (pi / expected['duty']) * np.abs(phase_error)
    for label, trace, raw, samples in zip(('candidate', 'upstream'), (candidate, upstream), radiation,
                                          (pcm, upper_pcm), strict=True):
        control_tol = spec['independent_control_absolute_tolerance']
        comparison = {key: compare(trace[key], expected[key], control_tol)
                      for key in (*PARAMETERS, *TARGETS, 'gate', *roughness_fields)}
        comparison['clock'] = compare(trace['control_clock_seconds'], expected['control_clock_seconds'], clock)
        comparison['active_call'] = compare(trace['active_call'], expected['active_call'], 0)
        if id_fields:
            comparison['call_id'] = compare(trace['call_id'], expected['call_id'], 0)
        pressure_tol = spec['independent_pressure_absolute_tolerance_dyn_cm2']
        comparison[pressure] = compare(trace[pressure], expected[pressure], pressure_tol)
        if pressure_budget is not None:
            pressure_diagnostics[label] = comparison[pressure]
            residual = np.maximum(np.abs(trace[pressure] - expected[pressure]) - pressure_budget, 0.0)
            comparison[pressure] = compare(residual, np.zeros_like(residual), pressure_tol)
        decimated, dc_removed, virtual_pcm = independent_output(raw, rate, factor, source['level'], output_spec)
        comparison['pcm'] = compare(samples, virtual_pcm, pcm_tol)
        if label == 'candidate':
            comparison['decimated'] = compare(trace['decimated'], decimated, raw_tol)
            comparison['dc_removed'] = compare(trace['dc_removed'], dc_removed, output_spec['dc_absolute_tolerance'])
            comparison['pulse_phase'] = compare(phase_error, np.zeros(frames),
                                                spec['independent_phase_circular_tolerance'])
            comparison['gate_target'] = compare(trace['gate_target'], expected['gate_target'], control_tol)
        checks.update({f'independent.{label}.{key}': value['passed'] for key, value in comparison.items()})
        independence[label] = comparison
    boundary, observations = evaluate_boundaries(candidate, source, variant, spec)
    checks.update(boundary)
    bit_difference = pcm.view('u4') != upper_pcm.view('u4')
    pressure_observations = {}
    if pressure_budget is not None:
        pressure_observations['independent_pressure_phase_budget'] = {
            'raw_pressure_comparison': pressure_diagnostics,
            'maximum_phase_contribution_dyn_cm2': float(np.max(pressure_budget)),
        }
    return {'checks': checks, 'frames': frames, 'internal_rate_hz': factor * rate,
            'observations': observations, 'upstream_comparison': direct, 'independent_comparison': independence,
            'pcm_different_bits': int(np.count_nonzero(bit_difference)),
            'first_pcm_different_bits': first_nonzero(bit_difference), **pressure_observations}


def measure(config, artifacts, execute):
    execute(['cargo', 'test', '--locked', '-p', 'chimera', '--test', 'golden_creatures',
             '--test', 'creature_realtime'], cwd=UPSTREAM, stdout=artifacts / 'upstream-tests.log')
    official = artifacts / 'official-cli'
    execute(['cargo', 'run', '--locked', '--release', '-p', 'chimera-cli', '--', 'render', 'creature',
             'seal', str(official), '--float'], cwd=UPSTREAM, stdout=artifacts / 'upstream-cli.log')
    probe = shared.build_upstream_probe(PROBE, artifacts, execute, extra_libraries=('serde_json',))
    definitions = artifacts / 'upstream-trill.json'
    execute([str(probe), '--trill-definition'], cwd=UPSTREAM, stdout=definitions)
    base, spec = config['seal_voice'], config['measurement']
    keys = spec['keys']
    definition = read(definitions)
    checks = {'upstream_call_definition': definition['pitchRef'] == keys['reference_pitch_hz'] and definition['keys'] == [
        {'t': 0.0, 'v': {'gate': 1.0, 'pitch': keys['initial_pitch_hz'], 'pulseRate': keys['initial_pulse_rate_hz'],
                         'pulse': keys['pulse_depth'], 'duty': keys['duty']}},
        {'t': keys['sweep_seconds'], 'v': {'gate': 1.0, 'pitch': keys['final_pitch_hz'],
                                         'pulseRate': keys['final_pulse_rate_hz']}, 'curve': 'exp'},
        {'t': keys['release_seconds'], 'v': {'gate': 0.0}},
    ]}
    output_spec = read(OUTPUT_CASE)['measurement']
    variants = {}
    for variant in spec['variants']:
        name = variant['id']
        source = base | {'breath': base['breath'] | variant['breath'], 'events': variant['events'] or base['events']}
        result = capture(variant, source, artifacts / name, execute, probe, spec, output_spec, official / 'seal.wav')
        variants[name] = result
        checks.update({f'{name}.{key}': passed for key, passed in result['checks'].items()})
    return {'checks': checks, 'variants': variants}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', args.run_id):
        parser.error('実行IDは英数字で始めてください')
    config = read(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != config['upstream_revision'] or subprocess.check_output(
            ['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True):
        raise SystemExit('変更のない固定上流版が必要です')
    baseline = WORKSPACE / 'runs/seal-sustain-before-trill-1/manifest.json'
    if read(baseline)['status'] != 'pass':
        raise SystemExit('持続音と停止の基準ケースが不合格です')
    names = ('LICENSE', 'Cargo.lock', 'crates/chimera/src/creatures/seal.rs',
             'crates/chimera/src/creatures/voice.rs', 'crates/chimera/src/creatures/types.rs',
             'crates/chimera-cli/src/render.rs', 'crates/chimera/tests/golden_creatures.rs',
             'crates/chimera/tests/creature_realtime.rs', 'crates/chimera/tests/golden/creatures.json')
    details = {'case_id': config['id'], 'revision': config['revision'],
               'upstream_revision': revision, 'invoked_from': str(Path.cwd()),
               'upstream_source_sha256': {name: sha256(UPSTREAM / name) for name in names}}
    deps = ('upstream_baseline.py', 'measure_songbird_syrinx.py', 'measure_songbird_sustain_pcm.py',
            'measure_seal_sustain_pcm.py')
    inputs = [CASE, OUTPUT_CASE, PROBE, baseline, Path(__file__).resolve(), Path(shared.__file__),
              *(WORKSPACE / 'tools' / file for file in deps), WORKSPACE / 'LICENSE-CHIMERA',
              *shared.candidate_sources()]
    return shared.record_measurement(args.run_id, CASE, inputs, details,
                                     lambda artifacts, execute: measure(config, artifacts, execute), command=None)


if __name__ == '__main__':
    raise SystemExit(main())
