"""アザラシの短い下行音と切り替えを固定上流に照合する。"""

import argparse
from math import exp
from pathlib import Path
import re
import subprocess

import numpy as np
import scipy

import measure_seal_trill as common
import measure_uniform_tube as shared
from measure_songbird_syrinx import compare, read
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/seal-zap.json'


def boundary_checks(trace, source, variant, spec):
    launch, = [event for event in source['events'] if event.get('play_call', {}).get('id') == 'zap']
    request = launch['frame']
    control, end = (variant[key] for key in ('expected_zap_control', 'expected_zap_end'))
    zap = trace['call_id'] == common.CALL_IDS['zap']
    ticks = np.flatnonzero(zap)
    keys = spec['zap_keys']
    tolerance = spec['independent_control_absolute_tolerance']
    rate = source['breath']['sample_rate_hz']
    pitch = launch['play_call'].get('pitch_hz') or keys['initial_pitch_hz']
    pitch = float(np.clip(pitch, *spec['pitch_limits_hz']))
    matched = np.flatnonzero(zap & (np.abs(trace['target_pitch_hz'] - pitch) <= tolerance))
    actual_control = int(matched[0]) if matched.size else None
    checks = {'zap_duration': np.array_equal(ticks, np.arange(request, end)),
              'zap_first_control': actual_control == control,
              'zap_depth_target_zero': bool(np.all(trace['target_pulse_depth'][control:end] == 0))}
    actual_end = int(ticks[-1] + 1) if ticks.size and ticks[-1] + 1 < len(zap) else None
    result = {'zap_request_frame': request, 'zap_first_control_frame': actual_control, 'zap_end_frame': actual_end,
              'end_elapsed_seconds_from_frames': (end - control) / rate,
              'end_elapsed_seconds_from_accumulated_clock': float(
                  trace['control_clock_seconds'][end - 1] -
                  (trace['control_clock_seconds'][control - 1] if control else 0))}

    def near(key, index, value):
        return bool(abs(trace[key][index] - value) <= tolerance)

    if variant['id'] == 'official-prefix-48000':
        index = variant['curves_sample']
        elapsed = (index - control) / rate
        expected_pitch = pitch * (keys['final_pitch_hz'] / keys['initial_pitch_hz'])**(elapsed / keys['sweep_seconds'])
        expected_gate = 1 - elapsed / keys['release_seconds']
        dt = spec['control_frames'] / rate
        expected_depth = trace['pulse_depth'][control - 1] * exp(
            -(elapsed + dt) / spec['smoothing_seconds']['pulse_depth'])
        checks['gate_ignores_pitch_only_key'] = near('gate_target', index, expected_gate)
        checks['pitch_exponential'] = near('target_pitch_hz', index, expected_pitch)
        checks['depth_decay'] = near('pulse_depth', index, expected_depth)
        checks['depth_restored_after_end'] = near('target_pulse_depth', end, source['breath']['controls']['pulse_depth'])
        result['curves_sample'] = {key: float(trace[key][index]) for key in
                                   ('target_pitch_hz', 'gate_target', 'pulse_depth', 'target_pulse_depth')}
    elif variant['id'] == 'switch-44100':
        edit, edit_control = (variant[key] for key in ('edit_during_zap', 'edit_control'))
        first, latest = (event['controls'] for event in source['breath']['events'] if 'controls' in event)
        pitch_hand = next(event['pitch_hz'] for event in source['events'] if 'pitch_hz' in event)
        checks['switches_from_trill'] = bool(trace['call_id'][request - 1] == common.CALL_IDS['trill'])
        checks['restores_trill_targets_at_request'] = near('target_pitch_hz', request, pitch_hand) and all(
            near('target_' + key, request, value) for key, value in first.items())
        checks['switch_leaves_smoothed_state_until_boundary'] = all(
            trace[key][request - 1] == trace[key][control - 1] for key in (*common.PARAMETERS, 'pulse_phase', 'gate'))
        checks['zap_keeps_performer_timing'] = (near('target_pulse_rate_hz', control, first['pulse_rate_hz'])
                                                and near('target_duty', control, first['duty']))
        checks['manual_edits_during_zap'] = (all(near('target_' + key, edit, latest[key]) for key in
                                                ('pulse_rate_hz', 'duty', 'pressure_cm_h2o'))
                                             and near('target_pulse_depth', edit, 0.0))
        checks['manual_timing_smooths_at_control'] = bool(
            trace['pulse_rate_hz'][edit] == trace['pulse_rate_hz'][edit_control - 1]
            and trace['pulse_rate_hz'][edit_control] != trace['pulse_rate_hz'][edit])
        checks['manual_depth_restored'] = near('target_pulse_depth', end, latest['pulse_depth'])
        result['handoff'] = {str(index): {key: float(trace[key][index]) for key in
                            ('call_id', 'target_pitch_hz', 'pitch_hz', 'target_pulse_rate_hz', 'pulse_rate_hz',
                             'target_duty', 'target_pulse_depth', 'pulse_depth', 'gate_target', 'pulse_phase')}
                             for index in (request - 1, request, control, edit, edit_control, end)}
    else:
        expected_pressure = (source['breath']['controls']['pressure_cm_h2o'] * spec['cm_h2o_to_dyn_cm2']
                             * trace['gate'])
        difference = compare(trace['lung_pressure_dyn_cm2'], expected_pressure,
                             spec['zero_depth_pressure_absolute_tolerance_dyn_cm2'])
        phase_wraps = int(np.count_nonzero(np.diff(trace['pulse_phase'][control:end]) < 0))
        checks['zero_depth_unmodulated_pressure'] = difference['passed']
        checks['zero_depth_phase_advances'] = phase_wraps > 0 and bool(np.all(trace['pulse_depth'] == 0))
        result['phase_wraps_during_zap'] = phase_wraps
        result['pressure_vs_unmodulated'] = difference
    return checks, result


def measure(config, artifacts, execute):
    execute(['cargo', 'test', '--locked', '-p', 'chimera', '--test', 'golden_creatures',
             '--test', 'creature_realtime'], cwd=UPSTREAM, stdout=artifacts / 'upstream-tests.log')
    official = artifacts / 'official-cli'
    execute(['cargo', 'run', '--locked', '--release', '-p', 'chimera-cli', '--', 'render',
             'creature', 'seal', str(official), '--float'], cwd=UPSTREAM, stdout=artifacts / 'upstream-cli.log')
    probe = shared.build_upstream_probe(common.PROBE, artifacts, execute, extra_libraries=('serde_json',))
    definition_path = artifacts / 'upstream-zap.json'
    execute([str(probe), '--zap-definition'], cwd=UPSTREAM, stdout=definition_path)
    base, spec = config['seal_voice'], read(common.CASE)['measurement'] | config['measurement']
    keys = spec['zap_keys']
    definition = read(definition_path)
    checks = {'upstream_call_definition': definition['pitchRef'] == keys['reference_pitch_hz'] and definition['keys'] == [
        {'t': 0.0, 'v': {'gate': 1.0, 'pitch': keys['initial_pitch_hz'], 'pulse': keys['pulse_depth']}},
        {'t': keys['sweep_seconds'], 'v': {'pitch': keys['final_pitch_hz']}, 'curve': 'exp'},
        {'t': keys['release_seconds'], 'v': {'gate': 0.0}},
    ]}
    output = read(common.OUTPUT_CASE)['measurement']
    results = {}
    for variant in spec['variants']:
        name = variant['id']
        source = base | {'breath': base['breath'] | variant['breath'], 'events': variant.get('events', base['events'])}
        result = common.capture(variant, source, artifacts / name, execute, probe, spec, output,
                                official / 'seal.wav', evaluate_boundaries=boundary_checks)
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
    baseline = WORKSPACE / 'runs/seal-trill-before-zap-1/manifest.json'
    if read(baseline)['status'] != 'pass':
        raise SystemExit('trillの基準ケースが不合格です')
    names = ('LICENSE', 'Cargo.lock', 'crates/chimera/src/creatures/seal.rs',
             'crates/chimera/src/creatures/voice.rs', 'crates/chimera/src/creatures/types.rs',
             'crates/chimera-cli/src/render.rs', 'crates/chimera/tests/golden_creatures.rs',
             'crates/chimera/tests/creature_realtime.rs', 'crates/chimera/tests/golden/creatures.json')
    details = {'case_id': config['id'], 'revision': config['revision'],
               'upstream_revision': revision, 'invoked_from': str(Path.cwd()), 'scipy': scipy.__version__,
               'upstream_source_sha256': {name: sha256(UPSTREAM / name) for name in names}}
    deps = ('upstream_baseline.py', 'measure_songbird_syrinx.py', 'measure_songbird_sustain_pcm.py',
            'measure_seal_sustain_pcm.py', 'measure_seal_trill.py')
    inputs = [CASE, common.CASE, common.OUTPUT_CASE, common.PROBE, baseline, Path(__file__).resolve(),
              Path(shared.__file__), *(WORKSPACE / 'tools' / file for file in deps),
              WORKSPACE / 'LICENSE-CHIMERA', *shared.candidate_sources()]
    return shared.record_measurement(args.run_id, CASE, inputs, details,
                                     lambda artifacts, execute: measure(config, artifacts, execute), command=None)


if __name__ == '__main__':
    raise SystemExit(main())
