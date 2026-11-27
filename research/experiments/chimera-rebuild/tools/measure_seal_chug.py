"""アザラシの低いパルス音を固定上流と独立した声門周期の計算に照合する。"""

import argparse
from pathlib import Path
import re
import subprocess

import numpy as np
import scipy

from measure_glottal_cycle import cycle_factors
import measure_seal_trill as common
from measure_seal_whistle import CASE as WHISTLE_CASE
from measure_seal_zap import CASE as ZAP_CASE
from measure_songbird_syrinx import compare, read
import measure_uniform_tube as shared
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASES = {1: WORKSPACE / 'cases/seal-chug.json', 2: WORKSPACE / 'cases/seal-chug-v2.json'}


def cycle_checks(trace, rate, control, spec):
    cfg = spec['glottal_cycle']
    factor = 2 if rate <= 60000 else 1
    internal_rate = rate * factor
    phase = common.glottis_internal(trace, 'glottis_phase', factor)
    f0 = common.glottis_internal(trace, 'glottis_f0_hz', factor)
    wraps = np.flatnonzero(np.diff(phase) < cfg['phase_jump_for_wrap']) + 1
    wraps = wraps[wraps + 1 < len(phase)]
    measured = (f0[wraps + 1] / internal_rate) / (phase[wraps + 1] - phase[wraps])
    jitter_only = cycle_factors(cfg, len(wraps))[0][1:]
    amount = trace['roughness'][wraps // factor]
    state = cfg['initial_map_state']
    offsets = np.empty_like(amount)
    for index, roughness in enumerate(amount):
        if roughness > 0.0:
            step = cfg['map_rate_base'] + cfg['map_rate_gain'] * min(1.0, roughness)
            state = step * state * (1.0 - state)
        offsets[index] = cfg['period_gain'] * roughness * (state - 0.5)
    desired = np.clip(jitter_only + offsets, 0.55, 1.8)
    difference = compare(measured, desired, cfg['period_scale_absolute_tolerance'])
    elapsed = (wraps - control * factor) / internal_rate
    windows = {}
    for name in ('early', 'late'):
        low, high = cfg[f'{name}_window_seconds']
        segment = (measured - jitter_only)[(elapsed >= low) & (elapsed < high)]
        windows[name] = {
            'seconds': [low, high],
            'cycles': len(segment),
            'period_offset_rms': float(np.sqrt(np.mean(segment ** 2))) if segment.size else None,
        }
    early, late = (windows[name]['period_offset_rms'] for name in ('early', 'late'))
    return {
        'independent.glottal_period_scale': difference['passed'],
        'period_variation_weakens': early is not None and late is not None and early > late,
    }, {'cycles': len(wraps), 'scale_comparison': difference, 'windows': windows}


def boundary_checks(trace, source, variant, spec):
    launch, = [event for event in source['events'] if event.get('play_call', {}).get('id') == 'chug']
    request = launch['frame']
    control, end = (variant[key] for key in ('expected_start_control', 'expected_end'))
    keys = spec['chug_keys']
    tol = spec['independent_control_absolute_tolerance']
    rate = source['breath']['sample_rate_hz']
    played = launch['play_call']
    pitch = played.get('pitch_hz') or keys['reference_pitch_hz']
    amplitude = played.get('amplitude', 1.0)
    gate_changes = [item for item in source['breath']['events'] if 'gate' in item]
    active = trace['call_id'] == common.CALL_IDS['chug']
    ticks = np.flatnonzero(active)
    first_keys = np.flatnonzero(active & (np.abs(trace['target_roughness'] - keys['initial_roughness']) <= tol))
    first = int(first_keys[0]) if first_keys.size else None
    actual_end = int(ticks[-1] + 1) if ticks.size and ticks[-1] + 1 < len(active) else None
    checks = {
        'chug_duration': np.array_equal(ticks, np.arange(request, end)),
        'first_control': first == control,
        'pitch_target': bool(np.all(np.abs(trace['target_pitch_hz'][control:end] - pitch) <= tol)),
    }
    timing = ('pulse_rate_hz', 'pulse_depth', 'duty')
    for name in timing:
        checks[f'{name}_target'] = bool(np.all(np.abs(trace['target_' + name][control:end] - keys[name]) <= tol))
    observations = {'request_frame': request, 'first_control_frame': first, 'end_frame': actual_end, 'curve_samples': {}}
    for label in ('roughness_sample', 'fade_sample'):
        index = variant[label]
        elapsed = (index - control) / rate
        hold, release = keys['sweep_seconds'], keys['release_seconds']
        mixed = min(1.0, elapsed / release)
        roughness = keys['initial_roughness'] * (1 - mixed) + keys['final_roughness'] * mixed
        manual_gate = next((item['gate'] for item in reversed(gate_changes) if item['frame'] <= index), 0.0)
        gate = max(manual_gate, amplitude * min(1.0, max(0.0, (release - elapsed) / (release - hold))))
        checks[f'{label}.linear_roughness'] = bool(abs(trace['target_roughness'][index] - roughness) <= tol)
        checks[f'{label}.gate'] = bool(abs(trace['gate_target'][index] - gate) <= tol)
        observations['curve_samples'][label] = {
            'frame': index, 'elapsed_seconds': elapsed,
            **{key: float(trace[key][index]) for key in (*common.ROUGHNESS_FIELDS, 'gate_target')},
        }
    if 'manual_edit_sample' in variant:
        index = variant['manual_edit_sample']
        edited, = [event['controls'] for event in source['breath']['events'] if event['frame'] == index]
        roughness, = [event['roughness'] for event in source['events'] if event['frame'] == index]
        checks['pressure_edit_immediate'] = bool(abs(trace['target_pressure_cm_h2o'][index] - edited['pressure_cm_h2o']) <= tol)
        checks['roughness_edit_waits'] = bool(trace['target_roughness'][index] == trace['target_roughness'][index - 1]
                                              and abs(trace['target_roughness'][index] - roughness) > tol)
        restored = edited | {'roughness': roughness, 'pitch_hz': source['shape']['pitch_hz']}
        checks['manual_targets_restored'] = all(abs(trace['target_' + key][end] - value) <= tol
                                                for key, value in restored.items())
        observations['edited_targets'] = {
            str(frame): {key: float(trace[key][frame]) for key in (*common.TARGETS, *common.ROUGHNESS_FIELDS)}
            for frame in (index, end)
        }
    cycle, observations['glottal_cycle'] = cycle_checks(trace, rate, control, spec)
    return checks | cycle, observations


def measure(config, artifacts, execute):
    execute(['cargo', 'test', '--locked', '-p', 'chimera', '--test', 'golden_creatures',
             '--test', 'creature_realtime'], cwd=UPSTREAM, stdout=artifacts / 'upstream-tests.log')
    official = artifacts / 'official-cli'
    execute(['cargo', 'run', '--locked', '--release', '-p', 'chimera-cli', '--', 'render', 'creature',
             'seal', str(official), '--float'], cwd=UPSTREAM, stdout=artifacts / 'upstream-cli.log')
    official_wav = official / 'seal.wav'
    probe = shared.build_upstream_probe(common.PROBE, artifacts, execute, extra_libraries=('serde_json',))
    definition = artifacts / 'upstream-chug.json'
    execute([str(probe), '--chug-definition'], cwd=UPSTREAM, stdout=definition)
    base = config['seal_voice']
    spec = (read(common.CASE)['measurement'] | read(ZAP_CASE)['measurement']
            | read(WHISTLE_CASE)['measurement'] | config['measurement'])
    keys = spec['chug_keys']
    expected_keys = [
        {'t': 0.0, 'v': {'gate': 1.0, 'pitch': keys['initial_pitch_hz'], 'pulseRate': keys['pulse_rate_hz'],
                        'pulse': keys['pulse_depth'], 'duty': keys['duty'], 'rough': keys['initial_roughness']}},
        {'t': keys['sweep_seconds'], 'v': {'gate': 1.0}},
        {'t': keys['release_seconds'], 'v': {'gate': 0.0, 'rough': keys['final_roughness']}},
    ]
    registered = read(definition)
    checks = {'upstream_call_definition': registered['pitchRef'] == keys['reference_pitch_hz']
              and registered['keys'] == expected_keys}
    output = read(common.OUTPUT_CASE)['measurement']
    results = {}
    for variant in spec['variants']:
        name = variant['id']
        source = base | {
            'breath': base['breath'] | variant['breath'],
            'shape': base['shape'] | variant.get('shape', {}),
            'events': variant.get('events', base['events']),
        }
        folder = artifacts / name
        result = common.capture(variant, source, folder, execute, probe, spec, output,
                                official_wav, evaluate_boundaries=boundary_checks)
        if name == 'official-prefix-48000':
            segment = slice(result['observations']['request_frame'], None)
            wave_name = f"pcm-{spec['host_block_frames'][0]}.wav"
            candidate = common.waveform(folder / wave_name, source['breath'])[segment]
            reference = common.waveform(official_wav, source['breath'])[segment]
            diff = compare(candidate, reference, spec['pcm_absolute_tolerance'])
            result['checks']['official_chug_segment'] = diff['passed']
            result['official_chug_segment'] = {
                'frames': len(candidate), 'difference': diff,
                'bit_difference': int(np.count_nonzero(candidate.view('u4') != reference.view('u4'))),
            }
        results[name] = result
        checks.update({f'{name}.{key}': passed for key, passed in result['checks'].items()})
    return {'checks': checks, 'variants': results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('--revision', type=int, choices=CASES, default=2)
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', args.run_id):
        parser.error('実行IDは英数字で始めてください')
    case = CASES[args.revision]
    config = read(case)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != config['upstream_revision'] or subprocess.check_output(
            ['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True):
        raise SystemExit('変更のない固定上流版が必要です')
    baseline = WORKSPACE / 'runs/seal-whistle-before-chug-1/manifest.json'
    if read(baseline)['status'] != 'pass':
        raise SystemExit('whistleの基準ケースが不合格です')
    upstream_sources = (
        'LICENSE', 'Cargo.lock', 'crates/chimera/src/creatures/seal.rs',
        'crates/chimera/src/creatures/mammal.rs', 'crates/chimera/src/sources/glottis.rs',
        'crates/chimera/src/creatures/voice.rs', 'crates/chimera/src/creatures/types.rs',
        'crates/chimera-cli/src/render.rs', 'crates/chimera/tests/golden_creatures.rs',
        'crates/chimera/tests/creature_realtime.rs', 'crates/chimera/tests/golden/creatures.json',
    )
    details = {'case_id': config['id'], 'revision': config['revision'], 'upstream_revision': revision,
               'invoked_from': str(Path.cwd()), 'scipy': scipy.__version__,
               'upstream_source_sha256': {name: sha256(UPSTREAM / name) for name in upstream_sources}}
    tools = ('upstream_baseline.py', 'measure_songbird_syrinx.py', 'measure_songbird_sustain_pcm.py',
             'measure_seal_sustain_pcm.py', 'measure_seal_trill.py', 'measure_seal_zap.py', 'measure_seal_whistle.py',
             'measure_glottal_cycle.py', 'measure_glottal_coupling.py', 'measure_turbulence.py',
             'measure_junction.py', 'measure_pcm_output.py')
    inputs = [case, common.CASE, ZAP_CASE, WHISTLE_CASE, common.OUTPUT_CASE, common.PROBE, baseline,
              Path(__file__).resolve(), Path(shared.__file__), *(WORKSPACE / 'tools' / file for file in tools),
              WORKSPACE / 'LICENSE-CHIMERA', *shared.candidate_sources()]
    return shared.record_measurement(args.run_id, case, inputs, details,
                                     lambda artifacts, execute: measure(config, artifacts, execute), command=None)


if __name__ == '__main__':
    raise SystemExit(main())
