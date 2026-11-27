"""デュエットの初期舌先だけを合わせ、気道の無発声時の過渡を測る。"""

import argparse
from copy import deepcopy
import json
import math
from pathlib import Path
import re
import subprocess
from tempfile import TemporaryDirectory

import numpy as np
from scipy.io import wavfile

import measure_duet_child_glottal_noise_origin as noise
from measure_bilabial_stop import load_trace
from measure_duet_telemetry import candidate_render
from measure_fan_crossing_allocations import run_manifest, verified_path
from measure_uniform_tube import candidate_sources, record_measurement
from measure_wasm_fixed import read_json
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


FIELDS = ('lip_area_cm2', 'pharynx_area_cm2', 'glottal_flow_cm3_s', 'radiation_derivative_cm3_s2')
BODY_PRESETS = {'male': {'female': 0, 'child': 0}, 'female': {'female': 1, 'child': 0},
                'child': {'female': 0, 'child': 1}}


def body_coefficients(body):
    return BODY_PRESETS[body] if isinstance(body, str) else body


def resting_tip(posture, model):
    cx, cy = model['rotation_center_cm']
    px, py = model['unrotated_tip_cm']
    tx, ty = posture['tongue_body_cm']
    bx, by = model['reference_tongue_body_cm']
    wx, wy = model['tongue_body_coupling']
    theta = -posture['jaw_cm'] / model['jaw_rotation_scale_cm']
    dx, dy = px - cx, py - cy
    return [cx + dx * math.cos(theta) - dy * math.sin(theta) + wx * (tx - bx),
            cy + dx * math.sin(theta) + dy * math.cos(theta) + wy * (ty - by)]


def startup_trace(path, count):
    trace = np.genfromtxt(path, names=True, delimiter=',')
    if (len(trace) != count + 1 or not np.array_equal(trace['sample'], np.arange(count + 1))
            or any(not np.isfinite(trace[key]).all() for key in trace.dtype.names)):
        raise ValueError('初期観測のサンプル番号または有限性が不正です')
    return trace


def motion_error(trace, start, target, study):
    block = study['control_output_samples']
    count = study['trace_output_samples']
    dt = block / study['sample_rate_hz']
    omega = math.tau * study['resting_tip_formula']['tip_natural_frequency_hz']
    x, v = np.asarray(start), np.zeros(2)
    positions, velocities = [x], [v]
    for _ in range((count + block - 1) // block):
        v = v + dt * (omega**2 * (target - x) - 2 * omega * v)
        x = x + dt * v
        positions.append(x)
        velocities.append(v)
    control_index = (np.arange(count + 1) + block - 1) // block
    def error(a, b, expected):
        return float(np.max(np.abs(np.column_stack((trace[a], trace[b])) - expected)))

    return {
        'position_cm': error('tip_x_cm', 'tip_y_cm', np.asarray(positions)[control_index]),
        'velocity_cm_s': error('tip_vx_cm_s', 'tip_vy_cm_s', np.asarray(velocities)[control_index]),
        'target_cm': error('tip_target_x_cm', 'tip_target_y_cm', np.vstack((start, np.tile(target, (count, 1))))),
    }


def linear_ramp_error(trace, block):
    endpoints = range(0, len(trace) - 1, block)
    def error(values, start):
        stop = min(start + block, len(values) - 1)
        expected = np.linspace(values[start], values[stop], stop - start + 1)
        return float(np.max(np.abs(values[start:stop + 1] - expected)))

    return {field: max(error(trace[field], start) for start in endpoints) for field in FIELDS[:2]}


def difference(candidate, upstream, wave, upper, count, tolerances):
    def peak_and_first(delta, sample_offset):
        peak = int(np.argmax(delta))
        changed = np.flatnonzero(delta)
        return {'peak': float(delta[peak]), 'peak_sample': peak + sample_offset,
                'first_unequal_sample': int(changed[0]) + sample_offset if changed.size else None}

    data = {}
    for field in FIELDS:
        delta = np.abs(candidate[field] - upstream[field])
        data[field] = {'at_initialization': float(delta[0]), **peak_and_first(delta, 0)}
    diff = np.abs(wave[:count].astype(float) - upper[:count])
    data['startup_pcm'] = peak_and_first(diff, 1)
    data['area_within_tolerance'] = all(data[field]['peak'] <= tolerances['area_cm2'] for field in FIELDS[:2])
    data['flow_within_tolerance'] = data['glottal_flow_cm3_s']['peak'] <= tolerances['flow_cm3_s']
    data['pcm_within_tolerance'] = data['startup_pcm']['peak'] <= tolerances['pcm_absolute']
    if 'radiation_cm3_s2' in tolerances:
        data['radiation_within_tolerance'] = data[FIELDS[3]]['peak'] <= tolerances['radiation_cm3_s2']
    return data


def measure(study, references, out, execute):
    voice_index = study.get('voice_index', 1)
    base_path, upper_path = references[f'candidate-{voice_index}.json'], references[f'upper-{voice_index}-input.json']
    base = read_json(base_path)
    song = base['song_voice']
    upper_input = read_json(upper_path)
    saved = song['posture']
    target = resting_tip(saved, study['resting_tip_formula'])
    alternative = deepcopy(base)
    alternative['song_voice']['posture']['tongue_tip_cm'] = target
    alternative_path = out / 'resting-tip.json'
    alternative_path.write_text(json.dumps(alternative, ensure_ascii=False, indent=2) + '\n')
    count = study['trace_output_samples']
    block = study['control_output_samples']
    tolerances = study['tolerances']
    waves = []
    for index, path in enumerate((base_path, alternative_path), 1):
        wave, _ = candidate_render(path, index, out, execute)
        rate, samples = wavfile.read(wave)
        if rate != study['sample_rate_hz']:
            raise ValueError('出力レートが登録と一致しません')
        waves.append(samples)
    execute(['cargo', 'test', '--locked', '-p', 'chimera', '--test', 'geometry_continuity', '--test', 'engine', '--test', 'body_mix'],
            cwd=UPSTREAM, stdout=out / 'upstream-tests.log')
    startup, raw, pcm, plans = {}, {}, {}, {}
    with TemporaryDirectory(prefix='duet-tip-probe-', dir=out.parent) as directory:
        scratch = Path(directory)
        local, upper = noise.build_observers(study['upstream_revision'], out, execute, scratch)
        for key, exe, data_path in (('case_tip', local, base_path), ('resting_tip', local, alternative_path), ('upstream', upper, upper_path)):
            reference = key == 'upstream'
            dict_path = scratch / ('upper.dict' if reference else 'local.dict')
            trace, wave, init = [out / f'{key}-{suffix}' for suffix in ('detail.csv', 'pcm.f32le', 'startup.csv')]
            plan = out / f'{key}-gestures.json'
            execute([str(exe), str(data_path), str(dict_path), str(count), *(['without_all_three'] if reference else []),
                     str(trace), str(wave), str(init)], stdout=plan)
            startup[key] = startup_trace(init, count)
            raw[key] = load_trace(trace, count)
            pcm[key] = np.fromfile(wave, dtype='<f4')
            plans[key] = plan

    def same_prefix(now, name):
        previous = np.genfromtxt(references[name], names=True, delimiter=',', max_rows=count)
        return np.array_equal(raw[now], previous)

    original = saved['tongue_tip_cm']
    upper_start = [float(startup['upstream'][axis][0]) for axis in ('tip_x_cm', 'tip_y_cm')]
    positions = (original, target, upper_start)
    motion = {key: motion_error(t, initial, np.asarray(target), study)
              for (key, t), initial in zip(startup.items(), positions, strict=True)}
    ramps = {key: linear_ramp_error(t, block) for key, t in startup.items()}
    archived = {key: np.fromfile(references[name], dtype='<f4') for key, name in
                (('case_tip', 'candidate.f32le'), ('upstream', 'without_all_three.f32le'))}
    checks = {
        'registered_body_rates_and_frames': body_coefficients(song['body']) == body_coefficients(upper_input['body'])
        == body_coefficients(study.get('body', 'child'))
        and song['internal_sample_rate_hz'] == study['internal_sample_rate_hz']
        and upper_input['sample_rate_hz'] == study['sample_rate_hz']
        and all(len(wave) == study.get('expected_pcm_frames', len(archived['case_tip'])) for wave in pcm.values()),
        'original_cli_and_probe_match_prior_pcm': all(noise.bit_equal(pcm[k], ref) for k, ref in archived.items())
        and noise.bit_equal(waves[0], archived['case_tip']),
        'both_candidate_probes_match_ordinary_cli_pcm': all(noise.bit_equal(wave, pcm[key]) for key, wave in
            zip(('case_tip', 'resting_tip'), waves, strict=True)),
        'original_and_upstream_traces_match_prior': same_prefix('case_tip', 'candidate.csv')
        and same_prefix('upstream', 'without_all_three.csv'),
        'only_initial_tip_changed': original != target and alternative == (base | {'song_voice': song |
            {'posture': saved | {'tongue_tip_cm': target}}}),
        'plans_unchanged': sha256(plans['case_tip']) == sha256(plans['resting_tip']) == sha256(references['candidate-gestures.json'])
        and sha256(plans['upstream']) == sha256(references['without_all_three-gestures.json']),
        'resting_tip_matches_geometry_formula': max(abs(x - y) for x, y in zip(target, upper_start, strict=True)) <= tolerances['tip_cm'],
        'independent_tip_motion': all(max(errors['position_cm'], errors['target_cm']) <= tolerances['tip_cm'] and
            errors['velocity_cm_s'] <= tolerances['tip_velocity_cm_s'] for errors in motion.values()),
        'independent_linear_area_ramp': all(error <= tolerances['area_cm2'] for errors in ramps.values() for error in errors.values()),
        'zero_initial_branch_flow': all(t['glottal_flow_cm3_s'][0] == 0 for t in startup.values()),
        'no_gate_or_noise_in_startup_window': all(np.all(t['gate'] == 0) and np.all(t['max_level'] == 0) for t in raw.values()),
    }
    comparison = {key: difference(startup[key], startup['upstream'], pcm[key], pcm['upstream'], count, tolerances)
                  for key in ('case_tip', 'resting_tip')}
    predictions = {key: not old and comparison['resting_tip'][key]
                   for key, old in comparison['case_tip'].items() if key.endswith('_within_tolerance')}
    if 'radiation_cm3_s2' in tolerances:
        predictions['no_radiated_or_pcm_transient_at_rest'] = all(
            not np.any(startup[key][field]) for key in ('resting_tip', 'upstream') for field in FIELDS[2:]
        ) and all(not np.any(pcm[key][:count]) for key in ('resting_tip', 'upstream'))
    points = {key: [{column: float(trace[column][at]) for column in trace.dtype.names}
                    for at in study['checkpoints_output_samples']] for key, trace in startup.items()}
    hits = np.flatnonzero(waves[0].view(np.uint32) != waves[1].view(np.uint32))
    wav_delta = np.abs(waves[0].astype(float) - waves[1])
    first_block_ramps = {key: linear_ramp_error(t[:block + 1], block) for key, t in startup.items()}
    return {'checks': checks, 'predictions': predictions, 'case_tip_cm': original, 'calculated_rest_tip_cm': target,
            'upstream_initial_tip_cm': upper_start, 'tip_motion_max_errors': motion,
            'initial_ramp_errors_cm2': first_block_ramps, 'block_ramp_errors_cm2': ramps,
            'startup_vs_upstream': comparison, 'snapshots': points,
            'candidate_pcm': {'frames': len(waves[0]), 'first_bit_difference_frame': int(hits[0]) if hits.size else None,
                              'start_max_difference': float(wav_delta[:count].max()),
                              'after_start_max_difference': float(wav_delta[count:].max())}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('--case', choices=('child', 'mixed'), default='child', help='比較する声部')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', args.run_id):
        parser.error('実行IDに使用できる文字を確認してください')
    case = WORKSPACE / f'cases/duet-{args.case}-initial-tip.json'
    study = read_json(case)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != study['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    voice_index = study.get('voice_index', 1)
    gesture_suffix = study.get('reference_gesture_suffix', '-gestures.json')
    gesture_paths = {f'{variant}-gestures.json': f'{variant}{gesture_suffix}'
                     for variant in ('candidate', 'without_all_three')}
    dependencies = (('input', 'duet-head-turbulence-body', (f'candidate-{voice_index}.json', f'upper-{voice_index}-input.json')),
                    ('reference', study.get('reference_case_id', 'duet-child-glottal-noise-origin'), ('candidate.csv', 'without_all_three.csv',
                     'candidate.f32le', 'without_all_three.f32le', 'candidate-gestures.json', 'without_all_three-gestures.json')))
    references, manifests = {}, []
    for key, case_id, files in dependencies:
        run = run_manifest(study[f'{key}_run'], case_id, revision)
        manifest = run[0] / 'manifest.json'
        if run[1]['status'] != 'pass' or sha256(manifest) != study[f'{key}_manifest_sha256']:
            parser.error(f'先行実行 {run[0].name} が登録と一致しません')
        references.update({name: verified_path(run, f'artifacts/{gesture_paths.get(name, name)}') for name in files})
        manifests.append(manifest)
    inputs = [case, Path(__file__).resolve(), Path(noise.__file__), noise.PATCH, noise.OUTPUT_PATCH, *noise.PROBES, *noise.DICTIONARIES,
              noise.TOOLS / 'duet_child_noise_trace.rs', *manifests, *references.values(), *candidate_sources(),
              *(UPSTREAM / name for name in ('crates/chimera/src/anatomy/human.rs', 'crates/chimera/src/control/articulators.rs',
                'crates/chimera/src/voice/human_voice.rs', 'crates/chimera/src/airway/network.rs',
                'crates/chimera/tests/geometry_continuity.rs', 'crates/chimera/tests/engine.rs', 'crates/chimera/tests/body_mix.rs')),
              *(noise.TOOLS / name for name in ('measure_uniform_tube.py', 'measure_duet_telemetry.py', 'measure_bilabial_stop.py',
                'measure_fan_crossing_allocations.py', 'measure_wasm_fixed.py', 'upstream_baseline.py'))]
    metadata = {'case_id': study['id'], 'case_revision': study['revision'], 'upstream_revision': revision}
    return record_measurement(args.run_id, case, inputs, metadata,
                              lambda out, execute: measure(study, references, out, execute), command=None, input_root=noise.ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
