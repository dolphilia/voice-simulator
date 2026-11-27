"""growl の曲線と bellow からの手動値の復帰を照合する。"""

import argparse
from pathlib import Path
import re
import subprocess

import numpy as np
import scipy

import measure_alligator_bellow as common
from measure_songbird_syrinx import read
import measure_uniform_tube as shared
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/alligator-growl.json'


def reproduce_switch(trace, case, variant, factor, first, request, end, spec):
    edit, during = (variant[key] for key in ('before_switch_edit', 'during_growl_edit'))
    events = {item['frame']: item for item in case['events']}
    old_patch, new_patch = events[edit]['params'], events[during]['params']
    sample = request * factor
    control = first * factor
    changed = during * factor
    release = end * factor
    stride = spec['control_frames']
    next_control = ((during + stride - 1) // stride) * stride * factor
    tolerance = spec['control_absolute_tolerance']
    checks = {
        'bellow_holds_hiss_override': bool(trace['target_hiss'][edit * factor] == trace['target_hiss'][sample - 1]
                                          and abs(trace['target_hiss'][sample - 1] - old_patch['hiss']) > tolerance),
        'manual_targets_between_call_grids': all(
            np.all(np.abs(trace['target_' + key][sample:control] - value) <= tolerance)
            for key, value in old_patch.items()),
        'smoothed_values_wait_for_boundary': all(
            np.all(trace[key][sample:control] == trace[key][sample - 1]) for key in common.PARAMETERS),
        'growl_leaves_hiss_free': bool(abs(trace['target_hiss'][control] - old_patch['hiss']) <= tolerance
                                     and trace['hiss'][control] > trace['hiss'][control - 1]),
        'free_targets_change_immediately': all(
            abs(trace['target_' + field][changed] - new_patch[field]) <= tolerance
            for field in ('pressure_cm_h2o', 'hiss')),
        'growl_holds_owned_targets': all(
            trace['target_' + field][changed] == trace['target_' + field][changed - 1]
            and abs(trace['target_' + field][changed] - new_patch[field]) > tolerance
            for field in common.OWNERSHIP['growl']),
        'hiss_smoothing_at_next_boundary': bool(
            np.all(trace['hiss'][changed:next_control] == trace['hiss'][changed - 1])
            and trace['hiss'][next_control] < trace['hiss'][next_control - 1]),
        'manual_targets_return_at_natural_end': all(
            abs(trace['target_' + field][release] - value) <= tolerance for field, value in new_patch.items()),
    }
    return checks


def boundary_checks(trace, case, variant, factor, spec):
    launch, = [event for event in case['events'] if event.get('play_call', {}).get('id') == 'growl']
    request, play = launch['frame'], launch['play_call']
    first, end = (variant[key] for key in ('first_control', 'end'))
    keys, tolerance = spec['growl_keys'], spec['control_absolute_tolerance']
    stride = spec['control_frames']
    lower, upper = spec['pitch_hz_limits']
    ratio = (play.get('pitch_hz') or keys['reference_pitch_hz']) / keys['reference_pitch_hz']
    samples = trace['call_id'][::factor]
    active = np.flatnonzero(samples == common.CALL_IDS['growl'])
    current_call = slice(first * factor, end * factor)
    checks = {
        'growl_duration': np.array_equal(active, np.arange(request, end)),
        'call_starts_on_control': bool(abs(trace['target_pitch_hz'][first * factor]
                                           - np.clip(keys['pitch_first_hz'] * ratio, lower, upper)) <= tolerance),
        'chaos_holds': bool(np.all(np.abs(trace['target_chaos'][current_call] - keys['chaos']) <= tolerance)),
        'mouth_holds': bool(np.all(np.abs(trace['target_mouth'][current_call] - keys['mouth']) <= tolerance)),
    }
    if variant['id'] == 'pitch-ceiling-96000':
        checks['pitch_ceiling'] = bool(np.all(trace['target_pitch_hz'][current_call] == upper))
    if 'before_switch_edit' in variant:
        checks.update(reproduce_switch(trace, case, variant, factor, first, request, end, spec))
    rate = case['sample_rate_hz']
    tracks = ('gate', 'gate_target', 'pitch_hz', 'chaos', 'mouth', 'hiss', 'pressure_cm_h2o',
              *common.TARGETS, 'oral_tip_area_cm2', 'oral_noise', 'glottis_voicing', 'glottis_area_cm2')
    curve = {}
    for frame in variant['curve_frames']:
        index = frame * factor
        curve[str(frame)] = {key: float(trace[key][index]) for key in tracks}
        if first <= frame < end:
            elapsed = (frame // stride * stride - first) / rate
            fraction = min(1.0, elapsed / keys['pitch_hold_seconds'])
            pitch = (keys['pitch_first_hz'] * (1 - fraction) + keys['pitch_last_hz'] * fraction) * ratio
            gate = max(0.0, 1 - elapsed / keys['release_seconds']) * play.get('amplitude', 1.0)
            checks[f'curve.{frame}.pitch'] = bool(abs(trace['target_pitch_hz'][index]
                                                     - np.clip(pitch, lower, upper)) <= tolerance)
            checks[f'curve.{frame}.gate'] = bool(abs(trace['gate_target'][index] - gate) <= tolerance)
    return checks, {'request_frame': request, 'first_control_frame': first,
                    'end_frame': int(active[-1]) + 1 if active.size else None,
                    'curve_frames': curve}


def growl_definition_matches(definition, keys):
    expected_keys = [
        {'t': 0.0, 'v': {'gate': 1.0, 'pitch': keys['pitch_first_hz'], 'chaos': keys['chaos'], 'mouth': keys['mouth']}},
        {'t': keys['pitch_hold_seconds'], 'v': {'pitch': keys['pitch_last_hz']}},
        {'t': keys['release_seconds'], 'v': {'gate': 0.0}},
    ]
    return definition['pitchRef'] == keys['reference_pitch_hz'] and definition['keys'] == expected_keys


def measure(config, spec, artifacts, execute):
    probe, official = common.prepare_probe(artifacts, execute)
    definition = artifacts / 'growl-definition.json'
    execute([str(probe), '--growl-definition'], cwd=UPSTREAM, stdout=definition)
    source = config['alligator_voice']
    checks = {'upstream_growl_keys': growl_definition_matches(read(definition), spec['growl_keys'])}
    variants = {}
    for variant in spec['variants']:
        name = variant['id']
        result, case, pcm, upper_pcm = common.capture_variant(
            source, variant, spec, artifacts / name, probe, execute, evaluate_boundaries=boundary_checks)
        if name == 'official-prefix-48000':
            common.compare_official(result, case, pcm, upper_pcm, official, spec, 'growl')
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
    parents = [WORKSPACE / 'cases' / filename for filename in config['inherits_measurement']]
    spec = {}
    for case in parents:
        spec.update(read(case)['measurement'])
    spec.update(config['measurement'])
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != config['upstream_revision'] or subprocess.check_output(
            ['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True):
        raise SystemExit('変更のない固定上流版が必要です')
    baseline = WORKSPACE / 'runs/alligator-bellow-before-growl-1/manifest.json'
    baseline_manifest = read(baseline)
    if baseline_manifest['status'] != 'pass' or baseline_manifest['upstream_revision'] != revision:
        raise SystemExit('bellowの基準が確認できません')
    sources = {name: sha256(UPSTREAM / name) for name in baseline_manifest['upstream_source_sha256']}
    details = {'case_id': config['id'], 'revision': config['revision'], 'upstream_revision': revision,
               'invoked_from': str(Path.cwd()), 'scipy': scipy.__version__, 'upstream_source_sha256': sources}
    tools = ('upstream_baseline.py', 'measure_alligator_bellow.py', 'measure_alligator_fixed_voice.py',
             'measure_seal_airway.py', 'measure_seal_sustain_pcm.py', 'measure_songbird_sustain_pcm.py',
             'measure_songbird_syrinx.py', 'measure_turbulence.py', 'measure_junction.py')
    paths = [CASE, *parents, baseline, common.fixed.PROBE, Path(__file__).resolve(), Path(shared.__file__),
             *(WORKSPACE / 'tools' / name for name in tools), WORKSPACE / 'LICENSE-CHIMERA', *shared.candidate_sources()]
    return shared.record_measurement(args.run_id, CASE, paths, details,
                                     lambda artifacts, execute: measure(config, spec, artifacts, execute), command=None)


if __name__ == '__main__':
    raise SystemExit(main())
