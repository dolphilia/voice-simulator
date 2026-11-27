"""音高が下がって戻るアザラシのコールを固定上流に照合する。"""

import argparse
from math import exp, log
from pathlib import Path
import re
import subprocess

import numpy as np
import scipy

import measure_seal_trill as common
from measure_seal_zap import CASE as ZAP_CASE
import measure_uniform_tube as shared
from measure_songbird_syrinx import compare, read
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/seal-whistle.json'


def boundary_checks(trace, source, variant, spec):
    launch, = [event for event in source['events'] if event.get('play_call', {}).get('id') == 'whistle']
    request = launch['frame']
    control, end = (variant[key] for key in ('expected_start_control', 'expected_end'))
    active = trace['call_id'] == common.CALL_IDS['whistle']
    keys = spec['whistle_keys']
    tol = spec['independent_control_absolute_tolerance']
    rate = source['breath']['sample_rate_hz']
    played_pitch = launch['play_call'].get('pitch_hz') or keys['reference_pitch_hz']
    pitch_ratio = played_pitch / keys['reference_pitch_hz']
    amplitude = launch['play_call'].get('amplitude', 1.0)
    gate_changes = [item for item in source['breath']['events'] if 'gate' in item]

    def manual_gate(index):
        return next((item['gate'] for item in reversed(gate_changes) if item['frame'] <= index), 0.0)

    target = trace['target_pitch_hz']
    first_keys = np.flatnonzero(active & (np.abs(target - played_pitch) <= tol))
    ticks = np.flatnonzero(active)
    first = int(first_keys[0]) if first_keys.size else None
    actual_end = int(ticks[-1] + 1) if ticks.size and ticks[-1] + 1 < len(active) else None
    target_min = control + int(np.argmin(target[control:end]))
    smoothed_min = control + int(np.argmin(trace['pitch_hz'][control:end]))
    elapsed_min = (smoothed_min - control) / rate
    window_start, window_end = spec['smoothed_turn_window_seconds']
    hold = variant['pitch_hold_sample']
    checks = {
        'whistle_duration': np.array_equal(ticks, np.arange(request, end)),
        'first_control': first == control,
        'target_minimum_frame': target_min == variant['expected_turn'],
        'smoothed_turn_lag': smoothed_min > target_min and window_start <= elapsed_min <= window_end,
        'pitch_holds_after_last_pitch_key': bool(np.all(np.abs(target[hold:end] - keys['final_pitch_hz'] * pitch_ratio) <= tol)),
        'depth_target': bool(np.all(trace['target_pulse_depth'][control:end] == keys['pulse_depth'])),
    }
    observation = {
        'request_frame': request, 'first_control_frame': first, 'end_frame': actual_end,
        'target_minimum': {'frame': target_min, 'pitch_hz': float(target[target_min])},
        'smoothed_minimum': {'frame': smoothed_min, 'pitch_hz': float(trace['pitch_hz'][smoothed_min])},
        'minimum_delay_seconds': (smoothed_min - target_min) / rate,
        'curve_samples': {},
    }
    turn, hold_time = keys['turn_seconds'], keys['sweep_seconds']
    gate_samples = ('fall_sample', 'rise_sample', 'pitch_hold_sample', 'gate_zero_sample')
    for mark in gate_samples:
        index = variant[mark]
        elapsed = (index - control) / rate
        desired_gate = max(manual_gate(index), amplitude * (1 - elapsed / keys['release_seconds']))
        checks[f'{mark}.linear_gate'] = bool(abs(trace['gate_target'][index] - desired_gate) <= tol)
        observation['curve_samples'][mark] = {
            'frame': index, 'gate_target': float(trace['gate_target'][index]), 'target_pitch_hz': float(target[index]),
        }
        if mark in ('fall_sample', 'rise_sample'):
            if mark == 'fall_sample':
                a, b, fraction = keys['initial_pitch_hz'], keys['turn_pitch_hz'], elapsed / turn
            else:
                a, b = keys['turn_pitch_hz'], keys['final_pitch_hz']
                fraction = (elapsed - turn) / (hold_time - turn)
            wanted = pitch_ratio * exp((1 - fraction) * log(a) + fraction * log(b))
            checks[f'{mark}.exponential_pitch'] = bool(abs(target[index] - wanted) <= tol)
    if variant['id'] == 'half-pitch-44100':
        at, next_control, hand_gate = (variant[key] for key in
                                       ('manual_edit_sample', 'manual_control_sample', 'manual_gate_sample'))
        edited, = [event['controls'] for event in source['breath']['events'] if event['frame'] == at]
        pitch_return, = [event['pitch_hz'] for event in source['events'] if event['frame'] == at]
        checks['edited_targets_update'] = all(abs(trace['target_' + key][at] - edited[key]) <= tol
                                              for key in ('pulse_rate_hz', 'pressure_cm_h2o', 'duty'))
        checks['owned_targets_retained'] = bool(
            abs(target[at] - pitch_return) > tol and abs(trace['target_pulse_depth'][at] - keys['pulse_depth']) <= tol)
        checks['manual_smoothing_waits_for_control'] = bool(
            trace['pulse_rate_hz'][at - 1] == trace['pulse_rate_hz'][next_control - 1]
            and trace['pulse_rate_hz'][next_control] != trace['pulse_rate_hz'][at - 1])
        checks['manual_gate_floor'] = bool(abs(trace['gate_target'][hand_gate] - manual_gate(hand_gate)) <= tol)
        checks['owned_targets_restored'] = bool(abs(target[end] - pitch_return) <= tol
                                               and abs(trace['target_pulse_depth'][end] - edited['pulse_depth']) <= tol)
        observation['edited_targets'] = {str(index): {key: float(trace[key][index]) for key in
                                                      (*common.TARGETS, 'pulse_rate_hz', 'gate_target')}
                                         for index in (at, next_control, end)}
    return checks, observation


def measure(config, artifacts, execute):
    execute(['cargo', 'test', '--locked', '-p', 'chimera', '--test', 'golden_creatures',
             '--test', 'creature_realtime'], cwd=UPSTREAM, stdout=artifacts / 'upstream-tests.log')
    official = artifacts / 'official-cli'
    execute(['cargo', 'run', '--locked', '--release', '-p', 'chimera-cli', '--', 'render', 'creature',
             'seal', str(official), '--float'], cwd=UPSTREAM, stdout=artifacts / 'upstream-cli.log')
    official_wav = official / 'seal.wav'
    probe = shared.build_upstream_probe(common.PROBE, artifacts, execute, extra_libraries=('serde_json',))
    definition_path = artifacts / 'upstream-whistle.json'
    execute([str(probe), '--whistle-definition'], cwd=UPSTREAM, stdout=definition_path)
    base = config['seal_voice']
    spec = read(common.CASE)['measurement'] | read(ZAP_CASE)['measurement'] | config['measurement']
    keys = spec['whistle_keys']
    definition = read(definition_path)
    checks = {'upstream_call_definition': definition['pitchRef'] == keys['reference_pitch_hz'] and definition['keys'] == [
        {'t': 0.0, 'v': {'gate': 1.0, 'pitch': keys['initial_pitch_hz'], 'pulse': keys['pulse_depth']}},
        {'t': keys['turn_seconds'], 'v': {'pitch': keys['turn_pitch_hz']}, 'curve': 'exp'},
        {'t': keys['sweep_seconds'], 'v': {'pitch': keys['final_pitch_hz']}, 'curve': 'exp'},
        {'t': keys['release_seconds'], 'v': {'gate': 0.0}},
    ]}
    output = read(common.OUTPUT_CASE)['measurement']
    results = {}
    for variant in spec['variants']:
        name = variant['id']
        source = base | {'breath': base['breath'] | variant['breath'], 'events': variant.get('events', base['events'])}
        folder = artifacts / name
        result = common.capture(variant, source, folder, execute, probe, spec, output,
                                official_wav, evaluate_boundaries=boundary_checks)
        if name == 'official-prefix-48000':
            start = result['observations']['request_frame']
            frame_range = slice(start, result['frames'])
            candidate = common.waveform(folder / f"pcm-{spec['host_block_frames'][0]}.wav", source['breath'])[frame_range]
            reference = common.waveform(official_wav, source['breath'])[frame_range]
            suffix = compare(candidate, reference, spec['pcm_absolute_tolerance'])
            result['checks']['official_whistle_segment'] = suffix['passed']
            result['official_whistle_segment'] = {'frames': len(candidate), 'difference': suffix, 'bit_difference':
                                                  int(np.count_nonzero(candidate.view('u4') != reference.view('u4')))}
        results[name] = result
        checks.update({f'{name}.{key}': passed for key, passed in result['checks'].items()})
    return {'checks': checks, 'variants': results}


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
    baseline = WORKSPACE / 'runs/seal-zap-before-whistle-1/manifest.json'
    if read(baseline)['status'] != 'pass':
        raise SystemExit('zapの基準ケースが不合格です')
    names = ('LICENSE', 'Cargo.lock', 'crates/chimera/src/creatures/seal.rs',
             'crates/chimera/src/creatures/voice.rs', 'crates/chimera/src/creatures/types.rs',
             'crates/chimera-cli/src/render.rs', 'crates/chimera/tests/golden_creatures.rs',
             'crates/chimera/tests/creature_realtime.rs', 'crates/chimera/tests/golden/creatures.json')
    details = {'case_id': config['id'], 'revision': config['revision'], 'upstream_revision': revision,
               'invoked_from': str(Path.cwd()), 'scipy': scipy.__version__,
               'upstream_source_sha256': {name: sha256(UPSTREAM / name) for name in names}}
    deps = ('upstream_baseline.py', 'measure_songbird_syrinx.py', 'measure_songbird_sustain_pcm.py',
            'measure_seal_sustain_pcm.py', 'measure_seal_trill.py', 'measure_seal_zap.py')
    inputs = [CASE, common.CASE, ZAP_CASE, common.OUTPUT_CASE, common.PROBE, baseline, Path(__file__).resolve(),
              Path(shared.__file__), *(WORKSPACE / 'tools' / file for file in deps),
              WORKSPACE / 'LICENSE-CHIMERA', *shared.candidate_sources()]
    return shared.record_measurement(args.run_id, CASE, inputs, details,
                                     lambda artifacts, execute: measure(config, artifacts, execute), command=None)


if __name__ == '__main__':
    raise SystemExit(main())
