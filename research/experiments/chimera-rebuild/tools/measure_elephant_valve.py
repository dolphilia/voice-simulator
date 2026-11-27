"""ゾウの入口弁を単体と気道内で、固定上流および独立計算に照合する。"""

import argparse
import json
from math import exp, pi
from pathlib import Path
import re
import subprocess

import numpy as np
import scipy
from scipy.signal import lfilter

import measure_elephant_fixed_voice as fixed
from measure_songbird_syrinx import compare, read
import measure_uniform_tube as shared
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/elephant-valve.json'
STANDALONE_FIELDS = ('frame', 'drive_dyn_cm2', 'height_cm', 'speed_cm_s', 'opening_cm2')
STANDALONE_UPPER = ('frame', 'drive_dyn_cm2', 'opening_cm2')


def reed_reference(drive, pitch, active, rate, parameters, bounds):
    dt = 1 / rate
    omega = 2 * pi * pitch
    coupling = -omega**2 * dt
    damping = 1 - 2 * parameters['damping_ratio'] * omega * dt
    velocity_increment = (parameters['surface_per_mass_cm2_g'] * drive + omega**2 * parameters['rest_gap_cm']) * dt
    height = speed = 0.0
    low, high = bounds
    states = np.empty((len(drive), 2))
    for index, (slope, remaining, forcing, enabled) in enumerate(zip(coupling, damping, velocity_increment, active, strict=True)):
        if enabled:
            # 状態行列を高さ・速度へ一度に適用する。
            height, speed = ((1 + dt * slope) * height + dt * remaining * speed + dt * forcing,
                             slope * height + remaining * speed + forcing)
            if height < low:
                height, speed = low, max(0.0, speed)
            elif height > high:
                height, speed = high, min(0.0, speed)
        states[index] = (height, speed)
    height, speed = states.T
    return {'height_cm': height, 'speed_cm_s': speed, 'opening_cm2': np.maximum(height, 0) * parameters['width_cm']}


def standalone(config, spec, artifacts, probe, execute):
    case = config['lip_reed']
    folder = artifacts / 'isolated-reed'
    folder.mkdir()
    settings = folder / 'case.json'
    settings.write_text(json.dumps({'lip_reed': case}, indent=2) + '\n')
    trace, upper = folder / 'reed.csv', folder / 'upstream.csv'
    execute([*fixed.CLI, 'render', str(settings), str(trace)])
    execute([str(probe), str(settings)], cwd=UPSTREAM, stdout=upper)
    frames, rate, params = (case[key] for key in ('frames', 'sample_rate_hz', 'parameters'))
    candidate = fixed.columns(trace, frames, STANDALONE_FIELDS)
    reference = fixed.columns(upper, frames, STANDALONE_UPPER)
    steps = case['pressure_steps']
    step_index = np.searchsorted([s['frame'] for s in steps], np.arange(frames), side='right') - 1
    drive = np.asarray([s['dyn_cm2'] for s in steps])[step_index]
    pitch = np.full(frames, params['pitch_hz'])
    independent = reed_reference(drive, pitch, np.ones(frames, dtype=bool), rate, params, spec['height_bounds_cm'])
    comparisons = {name: compare(candidate[name], value, spec['reed_tolerances'][name])
                   for name, value in independent.items()}
    opening = compare(candidate['opening_cm2'], reference['opening_cm2'], spec['reed_tolerances']['opening_cm2'])
    start, stop = spec['settled_window_frames']
    equilibrium = float(params['rest_gap_cm'] + params['surface_per_mass_cm2_g'] * drive[start] / (2 * pi * params['pitch_hz'])**2)
    mean_height = float(np.mean(candidate['height_cm'][start:stop]))
    h, v = candidate['height_cm'], candidate['speed_cm_s']
    low, high = spec['height_bounds_cm']
    checks = {'pressure_steps': np.array_equal(candidate['drive_dyn_cm2'], drive) and
                               np.array_equal(reference['drive_dyn_cm2'], drive),
              'frames': np.array_equal(candidate['frame'], np.arange(frames)),
              'upstream_opening': opening['passed'],
              'equilibrium': abs(mean_height - equilibrium) <= spec['settled_height_tolerance_cm'],
              'bottom_collision': bool(np.any((h == low) & (v == 0) & (candidate['opening_cm2'] == 0))),
              'top_collision': bool(np.any((h == high) & (v == 0))),
              'all_within_bounds': bool(np.all((h >= low) & (h <= high)))}
    checks.update({f'independent.{k}': value['passed'] for k, value in comparisons.items()})
    collisions = {label: fixed.first_nonzero((h == bound) & (v == 0))
                  for label, bound in (('lower', low), ('upper', high))}
    return {'checks': checks, 'upstream_opening': opening, 'independent': comparisons,
            'equilibrium_cm': float(equilibrium), 'mean_settled_height_cm': mean_height, 'collision_frames': collisions}


def control(case, spec):
    stride, rate, frames = spec['control_frames'], case['sample_rate_hz'], case['frames']
    reference = fixed.control_reference(case, spec)
    shape = case['shape']
    for key in ('mode', 'lip_pitch_hz'):
        initial = shape[key]
        targets = np.full(frames, initial)
        for event in case['events']:
            if key in event.get('params', {}):
                targets[event['frame']:] = event['params'][key]
        goal = targets[::stride]
        if key == 'lip_pitch_hz':
            goal = np.log(goal)
            initial = np.log(initial)
        seconds = spec['mode_smoothing_seconds' if key == 'mode' else 'lip_pitch_smoothing_seconds']
        keep = exp(-stride / rate / seconds)
        states, _ = lfilter([1 - keep], [1, -keep], goal, zi=[keep * initial])
        if key == 'lip_pitch_hz':
            states = np.exp(states)
        reference[key] = np.repeat(states, stride)[:frames]
        reference['target_' + key] = targets
    return reference


def compare_state(trace, case, spec):
    mode = trace['mode']
    active = mode > spec['threshold_mode']
    pressure = trace['nasal_base_pressure_dyn_cm2'] - trace['trunk_inlet_pressure_dyn_cm2']
    drive = np.where(active, np.r_[0.0, pressure[:-1]] * mode, 0.0)
    reed = reed_reference(drive, trace['lip_pitch_hz'], active, case['sample_rate_hz'],
                          spec['reed_parameters'], spec['height_bounds_cm'])
    opening = trace['reed_opening_cm2']
    bypass = spec['trunk_valve_area_cm2'] * (1 - mode)
    expected_port = np.where(active, np.maximum(opening, bypass), spec['trunk_valve_area_cm2'])
    area, pressure_limit = (spec['tolerances'][key] for key in ('area', 'pressure'))
    comparisons = {
        'reed_drive': compare(trace['reed_drive_dyn_cm2'], drive, pressure_limit),
        'effective_port': compare(trace['trunk_valve_area_cm2'], expected_port, area),
        'glottis_abduction': compare(trace['glottis_abduction_cm2'], spec['rest_glottis_abduction_cm2']
                                     + spec['added_glottis_abduction_cm2'] * mode, area),
        'glottis_amplitude': compare(trace['glottis_amplitude_cm2'], spec['rumble_glottis_amplitude_cm2'] * (1 - mode), area),
        'glottal_noise_gain': compare(trace['glottal_noise_gain'], spec['rumble_glottis_noise_gain'] * (1 - mode),
                                      spec['tolerances']['control']),
    }
    comparisons.update({field: compare(trace['reed_' + field], value, spec['reed_tolerances'][field])
                        for field, value in reed.items()})
    return comparisons


def observe(trace, case, variant, spec):
    mode = trace['mode']
    active = mode > spec['threshold_mode']
    opening = trace['reed_opening_cm2']
    bypass = spec['trunk_valve_area_cm2'] * (1 - mode)
    comparisons = compare_state(trace, case, spec)
    checks = {f'valve_reference.{name}': result['passed'] for name, result in comparisons.items()}
    window = slice(*variant['window'])
    strength = {'opening_peak_to_peak_cm2': float(np.ptp(opening[window])),
                'nasal_rms_cm3_s': fixed.rms(trace['nasal_cm3_s'][window]),
                'pcm_rms': fixed.rms(trace['pcm_f32'][window])}
    checks['vibration_and_radiation'] = all(value > 0 for value in strength.values())
    report = {'window': variant['window'], 'strength': strength, 'valve_reference': comparisons,
              'first_active_frame': fixed.first_nonzero(active)}
    if switch := variant.get('switch'):
        warm, mid, returned = (slice(*switch[key]) for key in ('subthreshold', 'intermediate', 'returned'))
        below = (trace['trunk_valve_area_cm2'] == spec['trunk_valve_area_cm2']) & ~active
        checks['subthreshold_keeps_open_port'] = bool(np.all(below[warm]))
        checks['in_between_uses_bypass'] = bool(np.all(active[mid] & (bypass[mid] > opening[mid])))
        checks['returned_mode_freezes_reed'] = bool(np.all(below[returned]) and
            np.ptp(trace['reed_height_cm'][returned]) == np.ptp(trace['reed_speed_cm_s'][returned]) == 0)
        report['switch'] = {
            'first_return_frame': int(np.flatnonzero(active)[-1]) + 1,
            'intermediate_mode': float(mode[mid.start]),
            'intermediate_opening_cm2': float(opening[mid.start]),
            'intermediate_port_cm2': float(trace['trunk_valve_area_cm2'][mid.start]),
        }
    else:
        checks['mode_one_uses_reed_opening'] = bool(np.all(trace['trunk_valve_area_cm2'] == opening)
                                                  and np.all(trace['glottis_amplitude_cm2'] == 0))
    return checks, report


def measure(config, spec, artifacts, execute):
    probe, official = fixed.prepare(artifacts, execute)
    variants = {'isolated-reed': standalone(config, spec, artifacts, probe, execute)}
    source = config['elephant_voice']
    for variant in spec['variants']:
        case = source | {key: variant[key] for key in ('sample_rate_hz', 'frames', 'events') if key in variant}
        case['shape'] = case['shape'] | variant.get('shape', {})
        name = variant['id']
        variants[name] = fixed.capture(case, variant, spec, artifacts / name, probe, official, execute,
                                       control_model=control, observe=observe)
    return {'checks': {f'{name}.{key}': result for name, v in variants.items() for key, result in v['checks'].items()},
            'variants': variants}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', args.run_id):
        parser.error('実行IDは英数字で始めてください')
    config = read(CASE)
    reference = WORKSPACE / 'cases' / config['inherits_measurement']
    spec = read(reference)['measurement'] | config['measurement']
    spec['reed_parameters'] = config['lip_reed']['parameters']
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != config['upstream_revision'] or subprocess.check_output(
            ['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True):
        raise SystemExit('変更のない固定上流版が必要です')
    baseline = WORKSPACE / 'runs/elephant-rumble-before-valve-1/manifest.json'
    before = read(baseline)
    if before['status'] != 'pass' or before['upstream_revision'] != revision:
        raise SystemExit('ゾウの rumble の基準が確認できません')
    sources = (*before['upstream_source_sha256'], 'crates/chimera/src/sources/valves.rs',
               'crates/chimera/tests/golden/creature-units.json')
    details = {'case_id': config['id'], 'revision': config['revision'], 'upstream_revision': revision,
               'invoked_from': str(Path.cwd()), 'scipy': scipy.__version__,
               'upstream_source_sha256': {name: sha256(UPSTREAM / name) for name in sources}}
    tools = ('upstream_baseline.py', 'measure_uniform_tube.py', 'measure_seal_sustain_pcm.py',
             'measure_songbird_sustain_pcm.py', 'measure_songbird_syrinx.py', 'measure_elephant_fixed_voice.py')
    paths = [CASE, reference, fixed.PROBE, baseline, Path(__file__).resolve(), WORKSPACE / 'LICENSE-CHIMERA',
             *(WORKSPACE / 'tools' / name for name in tools), *shared.candidate_sources()]
    return shared.record_measurement(args.run_id, CASE, paths, details,
                                     lambda artifacts, execute: measure(config, spec, artifacts, execute), command=None)


if __name__ == '__main__':
    raise SystemExit(main())
