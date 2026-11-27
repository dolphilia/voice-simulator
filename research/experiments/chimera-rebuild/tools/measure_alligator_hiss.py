"""hiss の開口と乱流を上流および独立した圧力の計算に照合する。"""

import argparse
import json
from math import exp, pi
from pathlib import Path
import re
import subprocess

import numpy as np
import scipy
from scipy.signal import lfilter

import measure_alligator_bellow as common
from measure_seal_sustain_pcm import columns
from measure_songbird_syrinx import compare, read
from measure_turbulence import mulberry32
import measure_uniform_tube as shared
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/alligator-hiss.json'
GLOTTAL_LEVEL, GLOTTAL_PRESSURE, ORAL_LEVEL = common.NOISE_FIELDS


def measure_handoff(trace, case, variant, factor, request, first, end, spec):
    events = {item['frame']: item for item in case['events']}
    old = events[variant['before_switch_edit']]['params']
    new_frame = variant['during_hiss_edit']
    new = events[new_frame]['params']
    stride = spec['control_frames']
    span = slice(request * factor, first * factor)
    fresh, natural = first * factor, end * factor
    edit = new_frame * factor
    following = (new_frame + stride - 1) // stride * stride * factor
    tolerance = spec['control_absolute_tolerance']
    return {
        'growl_holds_manual_pitch': bool(abs(trace['target_pitch_hz'][request * factor - 1] - old['pitch_hz']) > tolerance),
        'growl_owned_targets_return': all(np.all(np.abs(trace['target_' + key][span] - value) <= tolerance)
                                          for key, value in old.items()),
        'hiss_ignores_play_pitch': bool(abs(trace['target_pitch_hz'][fresh] - old['pitch_hz']) <= tolerance
                                   and abs(trace['target_chaos'][fresh] - old['chaos']) <= tolerance),
        'free_targets_change_immediately': all(abs(trace['target_' + key][edit] - new[key]) <= tolerance
                                                for key in ('pitch_hz', 'chaos', 'pressure_cm_h2o')),
        'owned_targets_hold': all(trace['target_' + key][edit] == trace['target_' + key][edit - 1]
                                  and abs(trace['target_' + key][edit] - new[key]) > tolerance
                                  for key in common.OWNERSHIP['hiss']),
        'pitch_waits_until_next_control': bool(np.all(trace['pitch_hz'][edit:following] == trace['pitch_hz'][edit - 1])
                                                and trace['pitch_hz'][following] > trace['pitch_hz'][following - 1]),
        'owned_targets_return_after_call': all(abs(trace['target_' + key][natural] - new[key]) <= tolerance
                                               for key in common.OWNERSHIP['hiss']),
    }


def boundary_checks(trace, case, variant, factor, spec):
    launch, = [event for event in case['events'] if event.get('play_call', {}).get('id') == 'hiss']
    request = launch['frame']
    first, end = (variant[key] for key in ('first_control', 'end'))
    active = np.flatnonzero(trace['call_id'][::factor] == common.CALL_IDS['hiss'])
    rate, stride = case['sample_rate_hz'], spec['control_frames']
    keys, tolerance = spec['hiss_keys'], spec['control_absolute_tolerance']
    release = keys['release_seconds']
    checks = {'hiss_duration': np.array_equal(active, np.arange(request, end))}
    if 'before_switch_edit' in variant:
        checks.update(measure_handoff(trace, case, variant, factor, request, first, end, spec))
    curve = {}
    fields = ('gate', 'gate_target', 'pitch_hz', 'chaos', 'hiss', 'mouth',
              *common.TARGETS, 'oral_tip_area_cm2', 'oral_noise', 'glottis_voicing', 'glottis_area_cm2')
    for frame in variant['curve_frames']:
        index = frame * factor
        curve[str(frame)] = {key: float(trace[key][index]) for key in fields}
        if first <= frame < end:
            elapsed = (frame // stride * stride - first) / rate
            ramp = min(1.0, elapsed / release)
            for field in ('hiss', 'mouth'):
                expected = (1 - ramp) * keys[f'{field}_first'] + ramp * keys[f'{field}_last']
                checks[f'curve.{frame}.{field}'] = bool(abs(trace['target_' + field][index] - expected) <= tolerance)
            gate = launch['play_call'].get('amplitude', 1.0) * np.interp(
                elapsed, [0, keys['gate_rise_seconds'], keys['hold_seconds'], release], [0, 1, 1, 0])
            checks[f'curve.{frame}.gate'] = bool(abs(trace['gate_target'][index] - gate) <= tolerance)
    transitions = (np.flatnonzero(np.diff(trace['oral_noise']) != 0) + 1)
    transitions = transitions[(transitions >= first * factor) & (transitions < end * factor)]
    state = trace['oral_noise'][transitions].astype(int).tolist()
    checks['oral_noise_deregisters_and_returns'] = state == [0, 1]
    switches = [{'internal_sample': int(sample), 'registered': bool(registered),
                 'oral_tip_area_cm2': float(trace['oral_tip_area_cm2'][sample]),
                 'commanded_area_cm2': 0.05 + 12 * float(trace['mouth'][sample])}
                for sample, registered in zip(transitions, state, strict=True)]
    return checks, {'request_frame': request, 'first_control_frame': first,
                    'end_frame': int(active[-1]) + 1 if active.size else None,
                    'curve_frames': curve, 'oral_noise_transitions': switches}


def noise_reference(trace, rate, cfg, spec):
    area = np.r_[0.0, trace['glottis_area_cm2'][:-1]]
    flow = np.r_[0.0, trace['glottis_flow_cm3_s'][:-1]]
    viscosity = spec['dynamic_viscosity_poise'] / spec['density_g_cm3']
    reynolds = np.divide(2 * np.abs(flow), viscosity * np.sqrt(pi * area),
                         out=np.zeros_like(flow), where=area > cfg['closed_area_cm2'])
    excess = np.maximum(0.0, reynolds**2 - cfg['critical_reynolds']**2)
    cap = cfg['saturation_reynolds']**2 - cfg['critical_reynolds']**2
    level = cfg['glottal_gain'] * np.sqrt(cfg['normalization_rate_hz'] / rate) * excess / (1 + excess / cap)

    # 声門は各サンプルで最初に引き、口腔の源がある時だけ次の乱数を消費する。
    indices = np.r_[0, np.cumsum(1 + trace['oral_noise'][:-1].astype(np.int64))]
    count = int(indices[-1]) + 1
    sequence = np.fromiter(mulberry32(spec['seeds']['airway_noise'], count), float, count=count)
    white = (2 * sequence[indices] - 1) * cfg['white_scale']
    high, low = (exp(-2 * pi * cfg[key] / rate) for key in ('highpass_hz', 'lowpass_hz'))
    bandpassed = lfilter([high, -high], [1, -high], white)
    for _ in range(2):
        bandpassed = lfilter([1 - low], [1, -low], bandpassed)
    return level, np.where(flow >= 0, level * bandpassed, -level * bandpassed)


def aspiration_intervals(first, rate, factor, limits):
    lo, hi = limits['seconds']
    start, stop = first + round(rate * lo), first + round(rate * hi)
    return slice(start, stop), slice(start * factor, stop * factor)


def rms(samples):
    return float(np.sqrt(np.mean(samples.astype(float)**2)))


def measure_noise(candidate, upstream, pcm, case, variant, spec):
    rate = case['sample_rate_hz']
    factor = 2 if rate <= 60000 else 1
    internal_rate = rate * factor
    cfg, aspiration = (spec[key] for key in ('noise_model', 'aspiration_window'))
    tolerance = cfg['absolute_tolerance_dyn_cm2']
    decimated_window, internal_window = aspiration_intervals(variant['first_control'], rate, factor, aspiration)
    direct = {field: compare(candidate[field], upstream[field], tolerance) for field in common.NOISE_FIELDS}
    level, pressure = noise_reference(candidate, internal_rate, cfg, spec)
    independent = {field: compare(candidate[field], expected, tolerance)
                   for field, expected in ((GLOTTAL_LEVEL, level), (GLOTTAL_PRESSURE, pressure))}
    pole = exp(-1.0 / (aspiration['gap_tau_seconds'] * internal_rate))
    target_gap = aspiration['gap_base_cm2'] + aspiration['gap_per_hiss_cm2'] * candidate['hiss']
    static_gap = lfilter([1 - pole], [1, -pole], target_gap)
    independent['window_static_gap'] = compare(candidate['glottis_area_cm2'][internal_window],
                                                static_gap[internal_window],
                                                aspiration['area_absolute_tolerance_cm2'])
    peak_voicing = float(np.max(candidate['glottis_voicing'][internal_window]))
    pcm_rms = rms(pcm[decimated_window])
    noise_rms = rms(candidate[GLOTTAL_PRESSURE][internal_window])
    checks = {
        'aspiration.no_oral_noise': not candidate[ORAL_LEVEL][internal_window].any()
        and not candidate['oral_noise'][internal_window].any(),
        'aspiration.glottal_pressure_audible': noise_rms > 0 and pcm_rms > 0,
        'aspiration.voicing_below_bound': peak_voicing <= aspiration['max_voicing'],
    }
    checks.update({f'upstream.{key}': item['passed'] for key, item in direct.items()})
    checks.update({f'independent.{key}': item['passed'] for key, item in independent.items()})
    return checks, {'differences': direct, 'independent': independent,
                    'aspiration': {'seconds': aspiration['seconds'], 'pcm_rms': pcm_rms,
                                   'peak_voicing': peak_voicing, 'glottal_noise_pressure_rms_dyn_cm2': noise_rms}}


def measure_muted_control(result, case, variant, spec, folder, probe, execute):
    frames = spec['mute_control']['trace_frames']
    muted_case = case | {'frames': frames, 'events': [event for event in case['events'] if event['frame'] < frames]}
    settings, output = (folder / name for name in ('mute-case.json', 'upstream-muted.csv'))
    settings.write_text(json.dumps({'alligator_voice': muted_case}, indent=2) + '\n')
    execute([str(probe), str(settings), '--mute-noise'], cwd=UPSTREAM, stdout=output)
    rate = case['sample_rate_hz']
    factor = 2 if rate <= 60000 else 1
    muted = columns(output, frames * factor, (*common.UPPER, *common.NOISE_FIELDS))
    window, _ = aspiration_intervals(variant['first_control'], rate, factor, spec['aspiration_window'])
    muted_rms = rms(muted['pcm_f32'][factor - 1::factor][window])
    regular_rms = result['noise']['aspiration']['pcm_rms']
    ratio = muted_rms / regular_rms if regular_rms else None
    result['checks']['muted.no_noise'] = not any(muted[field].any() for field in common.NOISE_FIELDS)
    result['checks']['muted.pcm_rms_reduction'] = ratio is not None and ratio <= spec['mute_control']['max_pcm_rms_ratio']
    result['noise']['muted'] = {'pcm_rms': muted_rms, 'relative_to_normal_pcm_rms': ratio}


def hiss_definition_matches(definition, keys):
    expected_keys = [
        {'t': 0.0, 'v': {'gate': 0.0, 'hiss': keys['hiss_first'], 'mouth': keys['mouth_first']}},
        {'t': keys['gate_rise_seconds'], 'v': {'gate': 1.0}},
        {'t': keys['hold_seconds'], 'v': {'gate': 1.0}},
        {'t': keys['release_seconds'], 'v': {'gate': 0.0, 'hiss': keys['hiss_last'], 'mouth': keys['mouth_last']}},
    ]
    return 'pitchRef' not in definition and definition['keys'] == expected_keys


def measure(config, spec, artifacts, execute):
    probe, official = common.prepare_probe(artifacts, execute)
    definition = artifacts / 'hiss-definition.json'
    execute([str(probe), '--hiss-definition'], cwd=UPSTREAM, stdout=definition)
    source = config['alligator_voice']
    checks = {'upstream_hiss_keys': hiss_definition_matches(read(definition), spec['hiss_keys'])}
    variants = {}
    for variant in spec['variants']:
        name = variant['id']
        folder = artifacts / name
        result, case, pcm, upper_pcm = common.capture_variant(
            source, variant, spec, folder, probe, execute, evaluate_boundaries=boundary_checks,
            extra_measurement=('noise', measure_noise))
        if name == 'official-prefix-48000':
            common.compare_official(result, case, pcm, upper_pcm, official, spec, 'hiss')
        if name == spec['mute_control']['variant']:
            measure_muted_control(result, case, variant, spec, folder, probe, execute)
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
    for case in [*parents, CASE]:
        spec.update(read(case)['measurement'])
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != config['upstream_revision'] or subprocess.check_output(
            ['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True):
        raise SystemExit('変更のない固定上流版が必要です')
    baseline = WORKSPACE / 'runs/alligator-growl-before-hiss-1/manifest.json'
    previous = read(baseline)
    if previous['status'] != 'pass' or previous['upstream_revision'] != revision:
        raise SystemExit('growlの基準が確認できません')
    sources = (*previous['upstream_source_sha256'], 'crates/chimera/src/physics.rs')
    details = {'case_id': config['id'], 'revision': config['revision'], 'upstream_revision': revision,
               'invoked_from': str(Path.cwd()), 'scipy': scipy.__version__,
               'upstream_source_sha256': {name: sha256(UPSTREAM / name) for name in sources}}
    tools = ('upstream_baseline.py', 'measure_alligator_bellow.py', 'measure_alligator_fixed_voice.py',
             'measure_seal_airway.py', 'measure_seal_sustain_pcm.py', 'measure_songbird_sustain_pcm.py',
             'measure_songbird_syrinx.py', 'measure_turbulence.py', 'measure_junction.py')
    paths = [CASE, *parents, baseline, common.fixed.PROBE, Path(__file__).resolve(), Path(shared.__file__),
             *(WORKSPACE / 'tools' / name for name in tools), WORKSPACE / 'LICENSE-CHIMERA', *shared.candidate_sources()]
    return shared.record_measurement(args.run_id, CASE, paths, details,
                                     lambda artifacts, execute: measure(config, spec, artifacts, execute), command=None)


if __name__ == '__main__':
    raise SystemExit(main())
