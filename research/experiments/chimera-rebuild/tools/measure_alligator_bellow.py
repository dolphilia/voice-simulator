"""アリゲーターの bellow を照合し、同じ経路で他のコールも計測する。"""

import argparse
import json
from math import exp, log
from pathlib import Path
import re
import subprocess

import numpy as np
import scipy

import measure_alligator_fixed_voice as fixed
from measure_seal_sustain_pcm import columns, independent_output, waveform
from measure_songbird_syrinx import CLI, compare, read
from measure_turbulence import mulberry32
import measure_uniform_tube as shared
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/alligator-bellow.json'
PARAMETERS = ('pitch_hz', 'chaos', 'pressure_cm_h2o', 'mouth', 'nostrils', 'hiss')
OWNED = ('pitch_hz', 'chaos', 'mouth', 'hiss')
CALL_IDS = {'bellow': 1, 'growl': 2, 'hiss': 3, 'dance': 4}
OWNERSHIP = {
    'bellow': OWNED,
    'growl': ('pitch_hz', 'chaos', 'mouth'),
    'hiss': ('mouth', 'hiss'),
    'dance': ('pitch_hz', 'chaos', 'mouth'),
}
KEY_GROUPS = {'bellow': 'keys', 'growl': 'growl_keys', 'hiss': 'hiss_keys', 'dance': 'dance_keys'}
TARGETS = tuple('target_' + field for field in PARAMETERS)
CONTROL_FIELDS = ('oral_tip_area_cm2', 'oral_noise', *PARAMETERS, *TARGETS)
CANDIDATE = (*fixed.CANDIDATE, 'call_id', 'control_clock_seconds', 'gate_target', *CONTROL_FIELDS)
UPPER = (*fixed.UPPER, 'call_id', 'control_clock_seconds', *CONTROL_FIELDS)
NOISE_FIELDS = ('glottal_noise_level_dyn_cm2', 'glottal_noise_pressure_dyn_cm2', 'oral_noise_level_dyn_cm2')


def ideal_call(play, keys, elapsed, pitch_limits):
    call = play['id']
    release = keys['release_seconds']
    if call == 'hiss':
        ramp = min(1.0, elapsed / release)
        target = {field: (1 - ramp) * keys[f'{field}_first'] + ramp * keys[f'{field}_last']
                  for field in ('mouth', 'hiss')}
    elif call == 'dance':
        ramp = min(1.0, elapsed / release)
        ratio = (play.get('pitch_hz') or keys['reference_pitch_hz']) / keys['reference_pitch_hz']
        low, high = pitch_limits
        target = {'pitch_hz': min(high, max(low, keys['pitch_hz'] * ratio)), 'mouth': keys['mouth'],
                  'chaos': (1 - ramp) * keys['chaos_first'] + ramp * keys['chaos_last']}
    else:
        hold = keys['hold_seconds'] if call == 'bellow' else keys['pitch_hold_seconds']
        ramp = min(1.0, elapsed / hold)
        rate_ratio = (play.get('pitch_hz') or keys['reference_pitch_hz']) / keys['reference_pitch_hz']
        pitch = ((1 - ramp) * keys['pitch_first_hz'] + ramp * keys['pitch_last_hz']) * rate_ratio
        low, high = pitch_limits
        target = {'pitch_hz': min(high, max(low, pitch)), 'mouth': keys['mouth']}
        if call == 'bellow':
            target.update(chaos=(1 - ramp) * keys['chaos_first'] + ramp * keys['chaos_last'],
                          hiss=keys['hiss'])
        else:
            target['chaos'] = keys['chaos']
    if call == 'growl':
        gate = max(0.0, 1.0 - elapsed / release)
    elif call == 'dance':
        gate = np.interp(elapsed, [0, keys['hold_seconds'], release], [1, 1, 0])
    else:
        gate = np.interp(elapsed, [0, keys['gate_rise_seconds'], keys['hold_seconds'], release], [0, 1, 1, 0])
    return target, play.get('amplitude', 1.0) * gate


def ideal_controls(case, spec):
    frames, rate = case['frames'], case['sample_rate_hz']
    stride = spec['control_frames']
    dt = stride / rate
    retained = {key: exp(-dt / seconds) for key, seconds in spec['smoothing_seconds'].items()}
    attack, release = (exp(-dt / spec[f'gate_{key}_seconds']) for key in ('attack', 'release'))
    manual = case['shape'].copy()
    target, state = manual.copy(), manual.copy()
    events = {event['frame']: event for event in case['events']}
    boundaries = sorted(set(range(0, frames, stride)) | events.keys())
    clock = np.r_[0.0, np.cumsum(np.full(1 + (frames - 1) // stride, dt))]
    result = {key: np.empty(frames) for key in
              (*PARAMETERS, *TARGETS, 'call_id', 'gate', 'gate_target', 'control_clock_seconds')}
    gate = gate_target = manual_gate = now = 0.0
    call = None
    for start, stop in zip(boundaries, boundaries[1:] + [frames], strict=True):
        if event := events.get(start):
            manual_gate = event.get('gate', manual_gate)
            updates = event.get('params', {})
            manual.update(updates)
            owned = OWNERSHIP[call[1]['id']] if call else ()
            target.update({key: value for key, value in updates.items() if key not in owned})
            if play := event.get('play_call'):
                block = (start + stride - 1) // stride
                call = (block, play)
                target.update(manual)
            if event.get('stop_call'):
                call = None
                target.update(manual)
        if start % stride == 0:
            block = start // stride
            now = clock[block + 1]
            commanded = 0.0
            if call:
                origin, play = call
                keys = spec[KEY_GROUPS[play['id']]]
                if clock[block] - clock[origin] > keys['release_seconds'] + keys['ownership_tail_seconds']:
                    call = None
                    target.update(manual)
                else:
                    elapsed = (block - origin) * dt
                    targets, commanded = ideal_call(play, keys, elapsed, spec['pitch_hz_limits'])
                    target.update(targets)
            for name in PARAMETERS:
                old, goal, weight = state[name], target[name], retained[name]
                state[name] = (exp(weight * log(old) + (1 - weight) * log(goal)) if name == 'pitch_hz'
                               else weight * old + (1 - weight) * goal)
            gate_target = max(manual_gate, commanded)
            weight = attack if gate_target > gate else release
            gate = weight * gate + (1 - weight) * gate_target
        span = slice(start, stop)
        for name in PARAMETERS:
            result[name][span] = state[name]
            result['target_' + name][span] = target[name]
        for name, value in (('call_id', CALL_IDS[call[1]['id']] if call else 0), ('gate', gate), ('gate_target', gate_target),
                            ('control_clock_seconds', now)):
            result[name][span] = value
    return result


def cycle_period_scales(trace, rate, wrap_threshold):
    phase, f0 = trace['glottis_phase'], trace['glottis_f0_hz']
    wraps = np.flatnonzero(np.diff(phase) < wrap_threshold) + 1
    wraps = wraps[wraps + 1 < len(phase)]
    measured = (f0[wraps + 1] / rate) / (phase[wraps + 1] - phase[wraps])
    return wraps, measured


def cycle_comparison(trace, rate, cfg, seed, start_internal, windows):
    wraps, measured = cycle_period_scales(trace, rate, cfg['phase_wrap_threshold'])
    draws = np.fromiter(mulberry32(seed, 8 * len(wraps)), float).reshape(-1, 2, 4)
    jitter_draw = (draws[:, 0, :].sum(axis=1) - 2) * 1.7320508
    chaos = trace['chaos'][wraps]
    state = cfg['initial_state']
    breakdown = np.empty_like(chaos)
    for index, amount in enumerate(chaos):
        if amount > 0.0:
            state = (cfg['rate_base'] + cfg['rate_per_chaos'] * amount) * state * (1 - state)
        breakdown[index] = cfg['period_per_chaos'] * amount * (state - 0.5)
    jitter = (cfg['jitter_base'] + cfg['jitter_per_chaos'] * chaos) * jitter_draw
    desired = np.clip(1 + jitter + breakdown, *cfg['period_scale_limits'])
    diff = compare(measured, desired, cfg['period_scale_absolute_tolerance'])
    relative_time = (wraps - start_internal) / rate
    stats = []
    for low, high in windows:
        segment = (relative_time >= low) & (relative_time < high)
        stats.append({'seconds': [low, high], 'cycles': int(segment.sum()),
                      'map_offset_rms': float(np.sqrt(np.mean(breakdown[segment]**2)))})
    return {'cycles': len(wraps), 'period_scale': diff, 'windows': stats}


def boundary_checks(trace, case, variant, factor, spec):
    launch, = [event['frame'] for event in case['events'] if 'play_call' in event]
    active = np.flatnonzero(trace['call_id'][::factor])
    first, end = variant['first_control'], variant['end']
    keys, tol = spec['keys'], spec['control_absolute_tolerance']
    checks = {'duration': np.array_equal(active, np.arange(launch, end)),
              'first_control': bool(abs(trace['target_chaos'][first * factor] - keys['chaos_first']) <= tol
                  and abs(trace['target_chaos'][first * factor - 1] - case['shape']['chaos']) <= tol)}
    marker = variant['first_curve_check'] * factor
    report = {'request_frame': launch, 'first_control_frame': first,
              'end_frame': int(active[-1]) + 1 if active.size else None,
              'curve_check': {key: float(trace[key][marker]) for key in
                              ('pitch_hz', 'chaos', 'target_pitch_hz', 'target_chaos', 'gate', 'gate_target')}}
    if 'manual_edit' in variant:
        edit, override = variant['manual_edit'], variant['gate_override']
        patch, = [event['params'] for event in case['events'] if event['frame'] == edit]
        sample, ending = edit * factor, end * factor
        checks['manual_target_immediate'] = all(abs(trace['target_' + key][sample] - patch[key]) <= tol
                                                for key in ('pressure_cm_h2o', 'nostrils'))
        checks['call_targets_retained'] = all(
            trace['target_' + key][sample] == trace['target_' + key][sample - 1]
            and abs(trace['target_' + key][sample] - patch[key]) > tol for key in OWNED)
        checks['targets_return_on_stop'] = all(abs(trace['target_' + key][ending] - patch[key]) <= tol
                                               for key in PARAMETERS)
        stride = spec['control_frames']
        next_tick = ((override + stride - 1) // stride) * stride * factor
        manual_gate, = [event['gate'] for event in case['events'] if event['frame'] == override]
        checks['manual_gate_wins'] = bool(abs(trace['gate_target'][next_tick] - manual_gate) <= tol)
        report['manual'] = {str(frame): {key: float(trace[key][frame * factor]) for key in
                                        (*TARGETS, *PARAMETERS, 'gate_target')} for frame in (edit, next_tick // factor, end)}
        report['oral_noise_change_internal_samples'] = (np.flatnonzero(np.diff(trace['oral_noise']) != 0) + 1).tolist()
    if variant['id'] == 'pitch-floor-96000':
        floor = spec['pitch_hz_limits'][0]
        checks['pitch_floor'] = bool(np.all(trace['target_pitch_hz'][first * factor:end * factor] == floor))
    return checks, report


def examine(candidate, upstream, pcm, case, variant, spec, evaluate_boundaries):
    frames, output_rate = case['frames'], case['sample_rate_hz']
    factor = 2 if output_rate <= 60000 else 1
    rate = output_rate * factor
    account = slice(factor - 1, None, factor)
    expected = ideal_controls(case, spec)
    control_tol = spec['control_absolute_tolerance']
    tolerance = spec['tolerances']
    limit = {key: tolerance['pressure_dyn_cm2'] for key in fixed.PRESSURES}
    limit.update({key: tolerance['flow_cm3_s'] for key in fixed.FLOWS})
    limit.update({key: tolerance['area_cm2'] for key in (*fixed.AREAS, 'oral_tip_area_cm2')})
    limit.update({f'glottis_{key}': tolerance[key] for key in ('phase', 'voicing', 'f0_hz')})
    limit.update({key: control_tol for key in ('gate', *PARAMETERS, *TARGETS)})
    limit.update({'call_id': 0, 'oral_noise': 0, fixed.RADIATION: tolerance['radiation_cm3_s2'],
                  'control_clock_seconds': spec['clock_absolute_tolerance_seconds']})
    direct = {key: compare(candidate[key], upstream[key], bound) for key, bound in limit.items()}
    upper_pcm = upstream['pcm_f32'][account].astype(np.float32)
    direct['pcm_f32'] = compare(pcm, upper_pcm, tolerance['pcm_f32'])
    direct['shadow_area_cm2'] = compare(upstream['shadow_area_cm2'], np.zeros(frames * factor),
                                        tolerance['shadow_area_cm2'])
    independent = {key: compare(candidate[key], np.repeat(wanted, factor),
                                0 if key == 'call_id' else limit.get(key, control_tol))
                   for key, wanted in expected.items()}
    pressure = np.repeat(expected['gate'] * expected['pressure_cm_h2o'] * spec['cm_h2o_to_dyn_cm2'], factor)
    independent['lung_pressure'] = compare(candidate['lung_pressure_dyn_cm2'], pressure, tolerance['pressure_dyn_cm2'])
    stride = spec['control_frames']
    internal_index = np.arange(frames * factor)
    block, sub = np.divmod(internal_index, stride * factor)
    fraction = (sub + 1) / (stride * factor)
    for area, control, base, scale in (('oral_tip_area_cm2', 'mouth', 0.05, 12.0),
                                       ('velum_area_cm2', 'nostrils', 0.4, 1.6)):
        targets = base + scale * expected[control][::stride]
        prev = np.r_[base + scale * case['shape'][control], targets[:-1]]
        wanted = prev[block] * (1 - fraction) + targets[block] * fraction
        independent[area] = compare(candidate[area], wanted, tolerance['area_cm2'])
    oral_cells = fixed.expected_geometry(rate, case['shape'], spec)['oral_cells']
    can_register = (oral_cells - 1.5) / oral_cells > spec['oral_tip_from']
    noise = can_register & (0.05 + 12.0 * expected['mouth'] < spec['oral_noise_threshold_cm2'])
    independent['oral_noise'] = compare(candidate['oral_noise'], np.repeat(noise, factor), 0)
    decimated, filtered, virtual = independent_output(candidate[fixed.RADIATION], output_rate, factor,
                                                      case['level'], spec['output'])
    independent['decimated'] = compare(candidate['decimated'][account], decimated, tolerance['radiation_cm3_s2'])
    independent['dc_removed'] = compare(candidate['dc_removed'][account], filtered, tolerance['dc_removed'])
    independent['pcm_f32'] = compare(pcm, virtual, tolerance['pcm_f32'])
    checks, observations = evaluate_boundaries(candidate, case, variant, factor, spec)
    cycles = cycle_comparison(candidate, rate, spec['cycle_model'], spec['seeds']['cycles'],
                              variant['first_control'] * factor, variant.get('cycle_windows', []))
    checks['independent.cycle_period_scale'] = cycles['period_scale']['passed']
    checks.update({f'upstream.{key}': item['passed'] for key, item in direct.items()})
    checks.update({f'independent.{key}': item['passed'] for key, item in independent.items()})
    checks['sample_index'] = all(np.array_equal(trace['sample'], internal_index)
                                 and np.array_equal(trace['frame'], internal_index // factor)
                                 for trace in (candidate, upstream))
    checks['wav_matches_trace'] = bool(np.array_equal(pcm, candidate['pcm_f32'][account].astype(np.float32)))
    return {'checks': checks, 'compared_frames': frames, 'internal_rate_hz': rate,
            'observations': observations, 'cyclic_variation': cycles,
            'differences': direct, 'independent': independent,
            'pcm_different_bits': int(np.count_nonzero(pcm.view('u4') != upper_pcm.view('u4')))}, upper_pcm


def prepare_probe(artifacts, execute):
    execute(['cargo', 'test', '--locked', '-p', 'chimera', '--test', 'creature_realtime',
             '--test', 'golden_creatures'], cwd=UPSTREAM, stdout=artifacts / 'upstream-tests.log')
    official_dir = artifacts / 'official-cli'
    execute(['cargo', 'run', '--locked', '--release', '-p', 'chimera-cli', '--', 'render', 'creature',
             'alligator', str(official_dir), '--float'], cwd=UPSTREAM, stdout=artifacts / 'upstream-cli.log')
    probe = shared.build_upstream_probe(fixed.PROBE, artifacts, execute, extra_libraries=('serde_json',))
    return probe, official_dir / 'alligator.wav'


def capture_variant(source, variant, spec, folder, probe, execute, evaluate_boundaries=boundary_checks,
                    extra_measurement=None):
    folder.mkdir()
    case = source | {key: variant[key] for key in ('sample_rate_hz', 'frames', 'events') if key in variant}
    case['shape'] = case['shape'] | variant.get('shape', {})
    settings, inspect, upper = (folder / key for key in ('case.json', 'inspect.json', 'upstream.csv'))
    settings.write_text(json.dumps({'alligator_voice': case}, indent=2) + '\n')
    execute([*CLI, 'inspect', str(settings)], stdout=inspect)
    execute([str(probe), str(settings)], cwd=UPSTREAM, stdout=upper)
    files = []
    for block in spec['host_block_frames']:
        wav, csv = (folder / f'pcm-{block}.{suffix}' for suffix in ('wav', 'csv'))
        execute([*CLI, 'render-pcm', str(settings), str(wav), str(csv), str(block)])
        files.append((wav, csv))
    wav, csv = files[0]
    pcm = waveform(wav, case)
    factor = 2 if case['sample_rate_hz'] <= 60000 else 1
    rows = case['frames'] * factor
    noise_fields = NOISE_FIELDS if case.get('observe_noise') else ()
    candidate_data = columns(csv, rows, (*CANDIDATE, *noise_fields))
    upper_data = columns(upper, rows, (*UPPER, *noise_fields))
    result, upper_pcm = examine(candidate_data, upper_data, pcm, case, variant, spec, evaluate_boundaries)
    if extra_measurement:
        label, evaluate = extra_measurement
        checks, result[label] = evaluate(candidate_data, upper_data, pcm, case, variant, spec)
        result['checks'].update(checks)
    result['checks']['host_block_invariance'] = all(sha256(w) == sha256(wav) and sha256(c) == sha256(csv)
                                                     for w, c in files)
    return result, case, pcm, upper_pcm


def compare_official(result, case, pcm, upper_pcm, official_path, spec, call_name):
    official = waveform(official_path, case | {'frames': spec['official_demo_frames']})[:len(pcm)]
    start = result['observations']['request_frame']
    prefix = compare(pcm, official, spec['tolerances']['pcm_f32'])
    segment = compare(pcm[start:], official[start:], spec['tolerances']['pcm_f32'])
    result['checks'].update(official_prefix=prefix['passed'])
    result['checks'][f'official_{call_name}'] = segment['passed']
    result['checks']['captured_official'] = np.array_equal(official.view('u4'), upper_pcm.view('u4'))
    result['official'] = {
        'prefix': prefix, f'{call_name}_segment': segment, f'{call_name}_frames': len(official) - start,
        'segment_different_bits': int(np.count_nonzero(pcm[start:].view('u4') != official[start:].view('u4'))),
    }


def measure(config, spec, artifacts, execute):
    probe, official = prepare_probe(artifacts, execute)
    definition = artifacts / 'bellow-definition.json'
    execute([str(probe), '--bellow-definition'], cwd=UPSTREAM, stdout=definition)
    keys, source = spec['keys'], config['alligator_voice']
    expected_keys = [
        {'t': 0.0, 'v': {'gate': 0.0, 'pitch': keys['pitch_first_hz'], 'chaos': keys['chaos_first'],
                        'mouth': keys['mouth'], 'hiss': keys['hiss']}},
        {'t': keys['gate_rise_seconds'], 'v': {'gate': 1.0}},
        {'t': keys['hold_seconds'], 'v': {'gate': 1.0, 'pitch': keys['pitch_last_hz'], 'chaos': keys['chaos_last']}},
        {'t': keys['release_seconds'], 'v': {'gate': 0.0}},
    ]
    call = read(definition)
    checks = {'upstream_bellow_keys': call['pitchRef'] == keys['reference_pitch_hz'] and call['keys'] == expected_keys}
    variants = {}
    for variant in spec['variants']:
        name = variant['id']
        result, case, pcm, upper_pcm = capture_variant(source, variant, spec, artifacts / name, probe, execute)
        if name == 'official-prefix-48000':
            compare_official(result, case, pcm, upper_pcm, official, spec, 'bellow')
        variants[name] = result
        checks.update({f'{name}.{key}': value for key, value in result['checks'].items()})
    return {'checks': checks, 'variants': variants}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', args.run_id):
        parser.error('実行IDは英数字で始めてください')
    config = read(CASE)
    fixed_case = WORKSPACE / 'cases' / config['inherits_measurement']
    spec = read(fixed_case)['measurement'] | config['measurement']
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != config['upstream_revision'] or subprocess.check_output(
            ['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True):
        raise SystemExit('変更のない固定上流版が必要です')
    baseline = WORKSPACE / 'runs/alligator-fixed-voice-before-bellow-1/manifest.json'
    if read(baseline)['status'] != 'pass':
        raise SystemExit('アリゲーターの固定発声の基準が不合格です')
    sources = ('Cargo.lock', 'LICENSE', 'crates/chimera/src/creatures/alligator.rs',
               'crates/chimera/src/creatures/voice.rs', 'crates/chimera/src/creatures/types.rs',
               'crates/chimera/src/creatures/mammal.rs', 'crates/chimera/src/sources/glottis.rs',
               'crates/chimera/src/airway/network.rs', 'crates/chimera-cli/src/render.rs',
               'crates/chimera/tests/golden_creatures.rs', 'crates/chimera/tests/creature_realtime.rs',
               'crates/chimera/tests/golden/creatures.json')
    details = {'case_id': config['id'], 'revision': config['revision'], 'upstream_revision': revision,
               'invoked_from': str(Path.cwd()), 'scipy': scipy.__version__,
               'upstream_source_sha256': {name: sha256(UPSTREAM / name) for name in sources}}
    tools = ('upstream_baseline.py', 'measure_alligator_fixed_voice.py', 'measure_seal_airway.py',
             'measure_seal_sustain_pcm.py', 'measure_songbird_sustain_pcm.py', 'measure_songbird_syrinx.py',
             'measure_turbulence.py', 'measure_junction.py')
    inputs = [CASE, fixed_case, baseline, fixed.PROBE, Path(__file__).resolve(), Path(shared.__file__),
              *(WORKSPACE / 'tools' / name for name in tools), WORKSPACE / 'LICENSE-CHIMERA', *shared.candidate_sources()]
    return shared.record_measurement(args.run_id, CASE, inputs, details,
                                     lambda artifacts, execute: measure(config, spec, artifacts, execute), command=None)


if __name__ == '__main__':
    raise SystemExit(main())
