"""アフリカゾウの固定発声、口端と鼻先の放射経路を照合する。"""

import argparse
import json
from math import exp
from pathlib import Path
import re
import subprocess

import numpy as np
import scipy
from scipy.signal import lfilter

from measure_seal_sustain_pcm import columns
from measure_songbird_sustain_pcm import waveform
from measure_songbird_syrinx import CLI, compare, read
import measure_uniform_tube as shared
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/elephant-fixed-voice.json'
PROBE = WORKSPACE / 'tools/upstream_elephant_probe.rs'
COMPONENTS = ('wall_cm3_s', 'oral_cm3_s', 'nasal_cm3_s')
COMMON = (
    'frame', 'gate', 'pitch_hz', 'pressure_cm_h2o', 'trunk', 'chaos',
    'lung_pressure_dyn_cm2', 'lung_flow_cm3_s', 'trachea_end_pressure_dyn_cm2', 'pharynx_pressure_dyn_cm2',
    'glottis_drive_dyn_cm2', 'glottis_area_cm2', 'glottis_flow_cm3_s', 'glottis_phase', 'glottis_f0_hz',
    'oral_tip_area_cm2', 'velum_area_cm2', 'velum_flow_cm3_s', 'nasal_base_pressure_dyn_cm2',
    'trunk_inlet_pressure_dyn_cm2', 'trunk_tip_pressure_dyn_cm2', 'trunk_valve_area_cm2',
    'trunk_valve_flow_cm3_s', *COMPONENTS, 'radiation_cm3_s2',
)
CANDIDATE = (*COMMON, 'decimated', 'dc_removed', 'pcm_f32')
UPPER = (*COMMON, 'shadow_area_error_cm2', 'pcm_f32')
CALL_FIELDS = ('call_id', 'control_clock_seconds', 'target_pitch_hz', 'target_pressure_cm_h2o',
               'target_trunk', 'target_chaos')
VALVE_FIELDS = ('mode', 'lip_pitch_hz', 'target_mode', 'target_lip_pitch_hz', 'glottis_abduction_cm2',
                'glottis_amplitude_cm2', 'glottal_noise_gain', 'reed_drive_dyn_cm2', 'reed_opening_cm2')


def tolerance(name, tolerances):
    units = (('_dyn_cm2', 'pressure'), ('_cm3_s2', 'radiation'), ('_cm3_s', 'flow'), ('_area_cm2', 'area'))
    special = {'glottis_phase': 'phase', 'glottis_f0_hz': 'f0', 'pcm_f32': 'pcm',
               'lip_pitch_hz': 'f0', 'reed_opening_cm2': 'area',
               'glottis_abduction_cm2': 'area', 'glottis_amplitude_cm2': 'area'}
    return tolerances[next((value for suffix, value in units if name.endswith(suffix)),
                           special.get(name, 'control'))]


def expected_geometry(case, spec):
    rate, frames = case['sample_rate_hz'], case['frames']
    dx = spec['sound_speed_cm_s'] / (rate * spec['cfl'])
    counts = {tube: max(3, min(maximum, int(length / (dx * coarse))))
              for tube, (length, _, coarse, maximum) in spec['tubes'].items()}
    trunk = counts['trunk']
    start, slope = spec['trunk_profile_cm2']
    mouth, mouth_change = spec['oral_tip_area_affine_cm2']
    velum, velum_change = spec['velum_area_affine_cm2']
    route = case['shape']['trunk']
    shortest = min(spec['tubes'][tube][0] / count for tube, count in counts.items())
    return {'internal_rate_hz': rate, 'decimation_factor': 1, 'control_frames': spec['control_frames'], 'rows': frames,
            'geometry': {f'{tube}_cells': count for tube, count in counts.items()} | {
                'courant': spec['sound_speed_cm_s'] / (rate * shortest),
                'oral_tip_area_cm2': mouth + mouth_change * route, 'velum_area_cm2': velum + velum_change * route,
                'trunk_valve_area_cm2': 0.0, 'trunk_inlet_area_cm2': start + slope * 0.5 / trunk,
                'trunk_tip_area_cm2': start + slope * (trunk - 0.5) / trunk,
            }}


def geometry_error(observed, expected, tolerance):
    return max(geometry_error(observed[key], value, tolerance) if isinstance(value, dict)
               else abs(observed[key] - value) / tolerance for key, value in expected.items())


def control_reference(case, spec):
    rate, stride, frames = case['sample_rate_hz'], spec['control_frames'], case['frames']
    dt = stride / rate
    attack, release = (exp(-dt / spec[f'gate_{kind}_seconds']) for kind in ('attack', 'release'))
    keep_route = exp(-dt / spec['trunk_smoothing_seconds'])
    gate = target = 0.0
    route = target_route = case['shape']['trunk']
    mouth_start, mouth_slope = spec['oral_tip_area_affine_cm2']
    velum_start, velum_slope = spec['velum_area_affine_cm2']
    out = {name: np.empty(frames) for name in ('gate', 'trunk', 'oral_tip_area_cm2', 'velum_area_cm2',
                                             'lung_pressure_dyn_cm2')}
    events = iter(case['events'])
    event = next(events, None)
    for frame in range(0, frames, stride):
        while event is not None and event['frame'] <= frame:
            target = event.get('gate', target)
            target_route = event.get('params', {}).get('trunk', target_route)
            event = next(events, None)
        keep_gate = attack if target > gate else release
        gate = keep_gate * gate + (1 - keep_gate) * target
        previous = route
        route = keep_route * route + (1 - keep_route) * target_route
        stop = min(frame + stride, frames)
        interval = slice(frame, stop)
        moving = previous + (route - previous) * np.arange(1, stop - frame + 1) / stride
        out['gate'][interval] = gate
        out['trunk'][interval] = route
        out['oral_tip_area_cm2'][interval] = mouth_start + mouth_slope * moving
        out['velum_area_cm2'][interval] = velum_start + velum_slope * moving
        out['lung_pressure_dyn_cm2'][interval] = gate * case['shape']['pressure_cm_h2o'] * spec['cm_h2o_to_dyn_cm2']
    return out


def output_reference(trace, case, spec):
    rate = case['sample_rate_hz']
    raw = np.diff(sum(trace[name] for name in COMPONENTS), prepend=0.0) * rate
    output = spec['output']
    pole = exp(-2 * np.pi * output['dc_cutoff_hz'] / rate)
    filtered = lfilter([1, -1], [1, -pole], trace['radiation_cm3_s2'] * output['gain'] * case['level'])
    threshold = output['limiter_threshold']
    margin = 1 - threshold
    magnitude = np.abs(filtered)
    pcm = np.where(magnitude > threshold, np.sign(filtered) *
                   (threshold + margin * np.tanh((magnitude - threshold) / margin)), filtered)
    drive = np.r_[0.0, (trace['trachea_end_pressure_dyn_cm2'] - trace['pharynx_pressure_dyn_cm2'])[:-1]]
    return {'radiation_cm3_s2': raw, 'decimated': trace['radiation_cm3_s2'], 'dc_removed': filtered,
            'pcm_f32': pcm.astype(np.float32), 'glottis_drive_dyn_cm2': drive}


def first_nonzero(series):
    indices = np.flatnonzero(series)
    return int(indices[0]) if indices.size else None


def rms(values):
    return float(np.sqrt(np.mean(np.square(values, dtype=float))))


def observe_routing(trace, case, variant, spec):
    rate = case['sample_rate_hz']
    timing_keys = ('gate', 'trachea_end_pressure_dyn_cm2', 'glottis_flow_cm3_s', 'velum_flow_cm3_s',
                   'nasal_base_pressure_dyn_cm2', 'trunk_valve_flow_cm3_s', 'trunk_inlet_pressure_dyn_cm2',
                   'trunk_tip_pressure_dyn_cm2', *COMPONENTS)
    timings = {key: first_nonzero(trace[key]) for key in timing_keys}
    fields = ('nasal_base_pressure_dyn_cm2', 'trunk_tip_pressure_dyn_cm2', 'trunk_valve_flow_cm3_s',
              'velum_flow_cm3_s', *COMPONENTS, 'pcm_f32')
    windows = []
    for seconds in variant['windows']:
        low, high = (round(x * rate) for x in seconds)
        windows.append({'seconds': seconds, 'rms': {name: rms(trace[name][low:high]) for name in fields}})
    checks = {'fixed_trunk_valve': bool(np.all(trace['trunk_valve_area_cm2'] == spec['trunk_valve_area_cm2']))}
    data = {'arrival_output_frames': timings, 'windows': windows}
    if windows:
        base, valve, tip, far = (timings[k] for k in ('nasal_base_pressure_dyn_cm2', 'trunk_valve_flow_cm3_s',
                                                      'trunk_tip_pressure_dyn_cm2', 'nasal_cm3_s'))
        checks['trunk_propagation_order'] = None not in (base, valve, tip, far) and base < valve < tip <= far
        checks['non_silent'] = all(window['rms']['pcm_f32'] > 0 for window in windows)
    else:
        checks['silent_output'] = not any(np.any(trace[key]) for key in (*COMPONENTS, 'lung_pressure_dyn_cm2',
                                                                        'trunk_valve_flow_cm3_s', 'pcm_f32'))
    if variant.get('route_switch'):
        request, = [event['frame'] for event in case['events'] if 'params' in event]
        stride = spec['control_frames']
        boundary = (request + stride - 1) // stride * stride
        oral, velum = (trace[key] for key in ('oral_tip_area_cm2', 'velum_area_cm2'))
        checks['areas_move_at_control'] = bool(oral[request] == oral[boundary - 1] > oral[boundary]
                                               and velum[request] == velum[boundary - 1] < velum[boundary])
        before, after = (window['rms'] for window in windows)
        checks['moves_radiation_to_trunk'] = after['oral_cm3_s'] < before['oral_cm3_s'] and after['nasal_cm3_s'] > before['nasal_cm3_s']
        checks['trunk_inflow_increases'] = after['trunk_valve_flow_cm3_s'] > before['trunk_valve_flow_cm3_s']
        points = (request, boundary - 1, boundary, boundary + stride - 1)
        data['route_change'] = {'request_frame': request, 'control_frame': boundary,
                                'values': {str(i): {'trunk': float(trace['trunk'][i]), 'oral_tip_area_cm2': float(oral[i]),
                                                    'velum_area_cm2': float(velum[i])} for i in points}}
    stops = [event['frame'] for event in case['events'] if event.get('gate') == 0.0]
    if stops:
        width = round(rate * 0.1)
        data['last_100ms_rms'] = rms(trace['pcm_f32'][-width:])
    return checks, data


def capture(case, variant, spec, folder, probe, official, execute, *,
            control_model=control_reference, observe=observe_routing):
    folder.mkdir()
    frames = case['frames']
    settings = folder / 'case.json'
    settings.write_text(json.dumps({'elephant_voice': case}, indent=2) + '\n')
    execute([*CLI, 'inspect', str(settings)], stdout=folder / 'inspect.json')
    execute([str(probe), str(settings), '--inspect'], cwd=UPSTREAM, stdout=folder / 'upstream-inspect.json')
    execute([str(probe), str(settings)], cwd=UPSTREAM, stdout=folder / 'upstream.csv')
    captures = []
    for block in spec['host_block_frames']:
        wav, csv = (folder / f'pcm-{block}.{suffix}' for suffix in ('wav', 'csv'))
        execute([*CLI, 'render-pcm', str(settings), str(wav), str(csv), str(block)])
        captures.append((wav, csv))
    wave_path, trace_path = captures[0]
    call_fields = CALL_FIELDS if case.get('observe_call') else ()
    extra = (*call_fields, 'gate_goal') if call_fields else ()
    valve_fields = VALVE_FIELDS if case.get('observe_valve') else ()
    upper_extra = call_fields
    if valve_fields:
        extra = (*extra, *valve_fields, 'reed_height_cm', 'reed_speed_cm_s')
        upper_extra = (*upper_extra, *valve_fields, 'reed_telemetry')
    trace = columns(trace_path, frames, (*CANDIDATE, *extra))
    upper = columns(folder / 'upstream.csv', frames, (*UPPER, *upper_extra))
    pcm, upper_pcm = waveform(wave_path, case), upper['pcm_f32'].astype(np.float32)
    limit = spec['tolerances']
    checks, observations = observe(trace, case, variant, spec)
    checks.update({'host_block_invariance': all(sha256(wave_path) == sha256(wav) and sha256(trace_path) == sha256(csv)
                                                for wav, csv in captures),
                   'frame_order': np.array_equal(trace['frame'], np.arange(frames)),
                   'wav_matches_trace': np.array_equal(pcm.view('u4'), trace['pcm_f32'].astype(np.float32).view('u4')),
                   'upstream_shadow_matches_area': bool(np.all(upper['shadow_area_error_cm2'] <= limit['area']))})
    geometry = expected_geometry(case, spec)
    geometry_errors = {name: geometry_error(read(folder / name), geometry, limit['control'])
                       for name in ('inspect.json', 'upstream-inspect.json')}
    checks['initial_geometry'] = all(error <= 1 for error in geometry_errors.values())
    upstream = {key: compare(trace[key], upper[key], tolerance(key, limit))
                for key in (*COMMON, *call_fields, *valve_fields)}
    if valve_fields:
        current, raw = upper['mode'], upper['reed_opening_cm2']
        predicted_port = np.where(current > spec['threshold_mode'],
                                  np.maximum(raw, spec['trunk_valve_area_cm2'] * (1 - current)),
                                  spec['trunk_valve_area_cm2'])
        checks['upstream_reed_matches_telemetry'] = bool(
            np.max(np.abs(np.minimum(1, raw / 1.2) - upper['reed_telemetry'])) <= limit['control'])
        checks['upstream_reed_matches_effective_port'] = bool(
            np.max(np.abs(predicted_port - upper['trunk_valve_area_cm2'])) <= limit['area'])
    upstream['pcm_f32'] = compare(pcm.astype(float), upper_pcm.astype(float), limit['pcm'])
    reference = control_model(case, spec) | output_reference(trace, case, spec)
    independent_limits = {'decimated': limit['radiation'], 'dc_removed': limit['dc']}
    if 'independent_pitch_tolerance_hz' in spec:
        independent_limits.update({name: spec['independent_pitch_tolerance_hz'] for name in ('pitch_hz', 'target_pitch_hz')})
    independent = {key: compare(trace[key] if key != 'pcm_f32' else pcm, value,
                                independent_limits.get(key, tolerance(key, limit)))
                   for key, value in reference.items()}
    for name, series in (('upstream', upstream), ('independent', independent)):
        checks.update({f'{name}.{key}': diff['passed'] for key, diff in series.items()})
    if variant.get('official_prefix'):
        full = waveform(official, case)
        prefix = full[:frames]
        observations['official_full_frames'] = len(full)
        observations['official_prefix'] = compare(pcm.astype(float), prefix.astype(float), limit['pcm'])
        checks['official_reference_agrees_with_probe'] = np.array_equal(prefix.view('u4'), upper_pcm.view('u4'))
        checks['official_prefix'] = observations['official_prefix']['passed']
    return {'checks': checks, 'upstream': upstream, 'independent': independent, 'observations': observations,
            'geometry': geometry, 'geometry_error_over_limit': geometry_errors,
            'different_pcm_bits': int(np.count_nonzero(pcm.view('u4') != upper_pcm.view('u4')))}


def prepare(artifacts, execute):
    execute(['cargo', 'test', '--locked', '-p', 'chimera', '--test', 'creature_realtime',
             '--test', 'golden_creatures', '--test', 'engine'], cwd=UPSTREAM, stdout=artifacts / 'upstream-tests.log')
    directory = artifacts / 'official-cli'
    execute(['cargo', 'run', '--locked', '--release', '-p', 'chimera-cli', '--',
             'render', 'creature', 'elephant', str(directory), '--float'], cwd=UPSTREAM, stdout=artifacts / 'upstream-cli.log')
    probe = shared.build_upstream_probe(PROBE, artifacts, execute, extra_libraries=('serde_json',))
    return probe, directory / 'elephant.wav'


def measure(config, artifacts, execute):
    spec = config['measurement']
    probe, official = prepare(artifacts, execute)
    results = {}
    source = config['elephant_voice']
    for variant in spec['variants']:
        name = variant['id']
        case = source | {key: variant[key] for key in ('sample_rate_hz', 'frames', 'events') if key in variant}
        case['shape'] = case['shape'] | variant.get('shape', {})
        results[name] = capture(case, variant, spec, artifacts / name, probe, official, execute)
    return {'checks': {f'{name}.{key}': passed for name, variant in results.items()
                       for key, passed in variant['checks'].items()}, 'variants': results}


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
    baseline = WORKSPACE / 'runs/alligator-dance-before-elephant-1/manifest.json'
    if (saved := read(baseline))['status'] != 'pass' or saved['upstream_revision'] != revision:
        raise SystemExit('アリゲーターの基準が確認できません')
    sources = ('Cargo.lock', 'LICENSE', 'crates/chimera/src/creatures/elephant.rs',
               'crates/chimera/src/creatures/mammal.rs', 'crates/chimera/src/creatures/build.rs',
               'crates/chimera/src/creatures/voice.rs', 'crates/chimera/src/sources/glottis.rs',
               'crates/chimera/src/airway/network.rs', 'crates/chimera-cli/src/render.rs',
               'crates/chimera/tests/golden_creatures.rs', 'crates/chimera/tests/golden/creatures.json',
               'crates/chimera/tests/creature_realtime.rs', 'crates/chimera/tests/engine.rs')
    details = {'case_id': config['id'], 'revision': config['revision'], 'upstream_revision': revision,
               'invoked_from': str(Path.cwd()), 'scipy': scipy.__version__,
               'upstream_source_sha256': {name: sha256(UPSTREAM / name) for name in sources}}
    tools = ('upstream_baseline.py', 'measure_uniform_tube.py', 'measure_seal_sustain_pcm.py',
             'measure_songbird_sustain_pcm.py', 'measure_songbird_syrinx.py')
    paths = [CASE, PROBE, baseline, Path(__file__).resolve(), WORKSPACE / 'LICENSE-CHIMERA',
             *(WORKSPACE / 'tools' / name for name in tools), *shared.candidate_sources()]
    return shared.record_measurement(args.run_id, CASE, paths, details,
                                     lambda artifacts, execute: measure(config, artifacts, execute), command=None)


if __name__ == '__main__':
    raise SystemExit(main())
