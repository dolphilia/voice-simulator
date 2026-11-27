"""ゾウの rumble の制御曲線、演奏値の復帰、公式PCMを照合する。"""

import argparse
from math import exp, log
from pathlib import Path
import re
import subprocess

import numpy as np
import scipy

import measure_elephant_fixed_voice as fixed
from measure_songbird_syrinx import compare, read
import measure_uniform_tube as shared
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/elephant-rumble.json'


def control_plans(spec):
    keys = spec['rumble_keys']
    plans = {
        'rumble': {'id': 1, 'pitch_reference_hz': keys['pitch_reference_hz'],
                   'ownership_tail_seconds': keys['ownership_tail_seconds'],
                   'gate': keys['gate'], 'pitch_hz': keys['pitch_hz'],
                   'trunk': [(0.0, keys['trunk'])], 'mode': [(0.0, keys['mode'])]},
    }
    for call, identifier in (('trumpet', 2), ('squeak', 3)):
        if keys := spec.get(call + '_keys'):
            plans[call] = {'id': identifier, **keys}
    return plans


def interpolator(points, exponential):
    time, values = np.asarray(points).T
    if not any(t in exponential for t in time[1:]):
        return lambda elapsed: np.interp(elapsed, time, values)

    def evaluate(elapsed):
        right = int(np.searchsorted(time, elapsed, side='right'))
        if 0 < right < len(time) and time[right] in exponential:
            left = right - 1
            fraction = (elapsed - time[left]) / (time[right] - time[left])
            return exp((1 - fraction) * log(values[left]) + fraction * log(values[right]))
        return np.interp(elapsed, time, values)

    return evaluate


def reference_controls(case, spec):
    frames, stride = case['frames'], spec['control_frames']
    dt = stride / case['sample_rate_hz']
    attack, release = (exp(-dt / spec[f'gate_{kind}_seconds']) for kind in ('attack', 'release'))
    time = spec['smoothing_seconds'] | {'trunk': spec['trunk_smoothing_seconds']}
    columns = ('pitch_hz', 'pressure_cm_h2o', 'trunk', 'chaos')
    if case.get('observe_valve'):
        columns += ('mode', 'lip_pitch_hz')
        time.update(mode=spec['mode_smoothing_seconds'], lip_pitch_hz=spec['lip_pitch_smoothing_seconds'])
    keep = {key: exp(-dt / seconds) for key, seconds in time.items()}
    plans = control_plans(spec)
    curves = {name: {key: interpolator(plan[key], plan.get('exponential_into_seconds', []))
                     for key in ('gate', *columns) if key in plan} for name, plan in plans.items()}
    performer = case['shape'].copy()
    values, targets = performer.copy(), performer.copy()
    output = ('call_id', 'control_clock_seconds', 'gate_goal', 'gate', *columns,
              *(f'target_{key}' for key in columns), 'lung_pressure_dyn_cm2',
              'oral_tip_area_cm2', 'velum_area_cm2')
    rows = np.empty((frames, len(output)))
    live = None
    clock = manual_gate = goal = gate = 0.0
    previous_trunk = performer['trunk']
    mouth, mouth_slope = spec['oral_tip_area_affine_cm2']
    velum, velum_slope = spec['velum_area_affine_cm2']
    events = {event['frame']: event for event in case['events']}
    for frame in range(frames):
        event = events.get(frame)
        if event:
            patch = event.get('params', {})
            performer.update(patch)
            targets.update({key: value for key, value in patch.items() if live is None or key not in plans[live[0]]})
            manual_gate = event.get('gate', manual_gate)
            if play := event.get('play_call'):
                call = play['id']
                reference = plans[call]['pitch_reference_hz']
                ratio = (play.get('pitch_hz') or reference) / reference
                live = (call, clock, ratio, play.get('amplitude', 1.0))
                targets = performer.copy()
            if event.get('stop_call'):
                live = None
                targets = performer.copy()
        phase = frame % stride
        if phase == 0:
            call_gate = 0.0
            if live is not None:
                call, origin, ratio, amplitude = live
                elapsed = clock - origin
                plan = plans[call]
                horizon = plan['gate'][-1][0] + plan['ownership_tail_seconds']
                if elapsed > horizon:
                    live = None
                    targets = performer.copy()
                else:
                    for key, evaluate in curves[call].items():
                        value = evaluate(elapsed)
                        if key == 'gate':
                            call_gate = value * amplitude
                        elif key == 'pitch_hz':
                            targets[key] = np.clip(value * ratio, *spec['pitch_hz_limits'])
                        else:
                            targets[key] = value
            goal = max(manual_gate, call_gate)
            retain = attack if goal > gate else release
            gate = retain * gate + (1 - retain) * goal
            previous_trunk = values['trunk']
            for key in columns:
                old, new, retain = values[key], targets[key], keep[key]
                if key in ('pitch_hz', 'lip_pitch_hz'):
                    values[key] = exp(retain * log(old) + (1 - retain) * log(new))
                else:
                    values[key] = retain * old + (1 - retain) * new
            clock += dt
        route = previous_trunk + (values['trunk'] - previous_trunk) * (phase + 1) / stride
        call_id = plans[live[0]]['id'] if live else 0
        rows[frame] = (call_id, clock, goal, gate, *(values[key] for key in columns),
                       *(targets[key] for key in columns),
                       gate * values['pressure_cm_h2o'] * spec['cm_h2o_to_dyn_cm2'],
                       mouth + mouth_slope * route, velum + velum_slope * route)
    return dict(zip(output, rows.T, strict=True))


def observe_rumble(trace, case, variant, spec):
    launch, = [event for event in case['events'] if 'play_call' in event]
    request = launch['frame']
    start, end = variant['first_control'], variant['end_frame']
    stride, rate = spec['control_frames'], case['sample_rate_hz']
    tol = spec['tolerances']['control']
    active = np.flatnonzero(trace['call_id'])
    checks = {
        'ownership_period': np.array_equal(active, np.arange(request, end)),
        'route_held': bool(np.all(trace['target_trunk'][start:end] == spec['rumble_keys']['trunk'])),
        'fixed_trunk_valve': bool(np.all(trace['trunk_valve_area_cm2'] == spec['trunk_valve_area_cm2'])),
    }
    columns = ('call_id', 'control_clock_seconds', 'gate_goal', 'gate', 'pitch_hz', 'target_pitch_hz',
               'glottis_f0_hz', 'trunk', 'target_trunk', 'pressure_cm_h2o', 'target_pressure_cm_h2o',
               'lung_pressure_dyn_cm2', 'chaos', 'target_chaos', 'velum_area_cm2', 'oral_tip_area_cm2')
    report = {'request_frame': request, 'first_control_frame': start,
              'end_frame': int(active[-1]) + 1 if active.size else None,
              'frames': {str(i): {key: float(trace[key][i]) for key in columns} for i in variant['curve_frames']}}
    if variant.get('decline_windows_seconds'):
        windows = []
        for seconds in variant['decline_windows_seconds']:
            a, b = (start + round(rate * t) for t in seconds)
            interval = slice(a, b)
            windows.append({'seconds': seconds,
                            'mean_f0_hz': float(np.mean(trace['glottis_f0_hz'][interval])),
                            'nasal_rms_cm3_s': fixed.rms(trace['nasal_cm3_s'][interval]),
                            'pcm_rms': fixed.rms(trace['pcm_f32'][interval])})
        report['decline_windows'] = windows
        early, late = windows
        checks['instantaneous_f0_declines'] = late['mean_f0_hz'] < early['mean_f0_hz']
        checks['nasal_radiation_present'] = all(w['nasal_rms_cm3_s'] > 0 for w in windows)
        checks['voice_releases'] = bool(trace['gate_goal'][end] == 0 and 0 < trace['gate'][end] < 1)
    if any(event.get('stop_call') for event in case['events']):
        edit, = [event for event in case['events'] if 'params' in event]
        change = edit['frame']
        values = edit['params']
        gate_on, gate_off = [event for event in case['events'] if 'gate' in event]
        boundary = lambda frame: (frame + stride - 1) // stride * stride
        checks['unowned_targets_update_at_request'] = all(
            trace['target_' + key][change] == values[key] and trace[key][change] == trace[key][change - 1]
            for key in ('pressure_cm_h2o', 'chaos'))
        checks['owned_targets_survive_manual_edit'] = all(
            trace['target_' + key][change - 1] == trace['target_' + key][change] != values[key]
            for key in ('pitch_hz', 'trunk'))
        checks['manual_gate_wins_at_control'] = bool(
            abs(trace['gate_goal'][boundary(gate_on['frame'])] - gate_on['gate']) <= tol
            and abs(trace['gate_goal'][boundary(gate_off['frame'])] - launch['play_call']['amplitude']) <= tol)
        checks['manual_targets_return_at_stop'] = all(trace['target_' + key][end] == values[key] for key in values)
        checks['smoothed_values_wait_for_control'] = all(trace[key][end] == trace[key][end - 1] for key in columns
                                                        if key in ('gate', 'pitch_hz', 'trunk'))
        checks['gate_releases_after_stop'] = bool(trace['gate_goal'][boundary(end)] == 0
                                                and trace['gate'][boundary(end)] < trace['gate'][end])
    return checks, report


def measure(config, spec, artifacts, execute):
    probe, official_path = fixed.prepare(artifacts, execute)
    def_path = artifacts / 'rumble-definition.json'
    execute([str(probe), '--rumble-definition'], cwd=UPSTREAM, stdout=def_path)
    definition, keys = read(def_path), spec['rumble_keys']
    expected = {t: {'gate': value} for t, value in keys['gate']}
    for t, value in keys['pitch_hz']:
        expected[t]['pitch'] = value
    expected[0.0].update(trunk=keys['trunk'], mode=keys['mode'])
    checks = {'upstream_rumble_definition': definition['pitchRef'] == keys['pitch_reference_hz']
              and definition['keys'] == [{'t': t, 'v': v} for t, v in expected.items()]}
    variants = {}
    source = config['elephant_voice']
    for variant in spec['variants']:
        case = source | {key: variant[key] for key in ('sample_rate_hz', 'frames', 'events') if key in variant}
        case['shape'] = case['shape'] | variant.get('shape', {})
        name = variant['id']
        folder = artifacts / name
        result = fixed.capture(case, variant, spec, folder, probe, official_path, execute,
                               control_model=reference_controls, observe=observe_rumble)
        if variant.get('official_prefix'):
            start = variant['first_control']
            pcm = fixed.waveform(folder / f"pcm-{spec['host_block_frames'][0]}.wav", case)[start:]
            official = fixed.waveform(official_path, case)[start:case['frames']]
            region = compare(pcm.astype(float), official.astype(float), spec['tolerances']['pcm'])
            result['checks']['official_rumble_segment'] = region['passed']
            result['observations']['official_rumble_segment'] = region | {
                'frames': len(pcm), 'different_pcm_bits': int(np.count_nonzero(pcm.view('u4') != official.view('u4')))}
        checks.update({f'{name}.{key}': value for key, value in result['checks'].items()})
        variants[name] = result
    return {'checks': checks, 'variants': variants}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', args.run_id):
        parser.error('実行IDは英数字で始めてください')
    config = read(CASE)
    reference = WORKSPACE / 'cases' / config['inherits_measurement']
    spec = read(reference)['measurement'] | config['measurement']
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != config['upstream_revision'] or subprocess.check_output(
            ['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True):
        raise SystemExit('変更のない固定上流版が必要です')
    baseline = WORKSPACE / 'runs/elephant-fixed-voice-before-rumble-1/manifest.json'
    before = read(baseline)
    if before['status'] != 'pass' or before['upstream_revision'] != revision:
        raise SystemExit('ゾウの固定発声の基準が確認できません')
    sources = (*before['upstream_source_sha256'], 'crates/chimera/src/creatures/types.rs')
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
