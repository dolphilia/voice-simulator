"""dance の低域と周期変動を固定上流と粗さ0の対照に照合する。"""

import argparse
from pathlib import Path
import re
import subprocess

import numpy as np
import scipy
from scipy.signal import periodogram

import measure_alligator_bellow as common
from measure_seal_sustain_pcm import columns
from measure_songbird_syrinx import read
import measure_uniform_tube as shared
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/alligator-dance.json'
SPECTRAL_FIELDS = ('glottis_area_cm2', 'trachea_end_pressure_dyn_cm2', 'pharynx_pressure_dyn_cm2',
                   'wall_cm3_s', 'oral_cm3_s', 'nasal_cm3_s')


def switch_checks(trace, case, variant, factor, request, first, end, spec):
    events = {item['frame']: item for item in case['events']}
    earlier = events[variant['before_switch_edit']]['params']
    edited = variant['during_dance_edit']
    latest = events[edited]['params']
    changed = edited * factor
    before, after = request * factor, first * factor
    tolerance = spec['control_absolute_tolerance']
    return {
        'hiss_was_owned': bool(abs(trace['target_hiss'][before - 1] - earlier['hiss']) > tolerance),
        'hiss_restored_between_controls': bool(np.all(np.abs(trace['target_hiss'][before:after]
                                                             - earlier['hiss']) <= tolerance)),
        'still_smoothed_until_control': bool(np.all(trace['hiss'][before:after] == trace['hiss'][before - 1])),
        'dance_leaves_hiss_free': bool(abs(trace['target_hiss'][after] - earlier['hiss']) <= tolerance
                                      and trace['hiss'][after] < trace['hiss'][after - 1]),
        'unowned_targets_update_immediately': all(abs(trace['target_' + field][changed] - latest[field]) <= tolerance
                                                 for field in ('hiss', 'pressure_cm_h2o')),
        'dance_owns_pitch_chaos_mouth': all(trace['target_' + field][changed] == trace['target_' + field][changed - 1]
                                           and abs(trace['target_' + field][changed] - latest[field]) > tolerance
                                           for field in common.OWNERSHIP['dance']),
        'manual_targets_return': all(abs(trace['target_' + field][end * factor] - value) <= tolerance
                                     for field, value in latest.items()),
    }


def boundary_checks(trace, case, variant, factor, spec):
    launch, = [event for event in case['events'] if event.get('play_call', {}).get('id') == 'dance']
    request, play = launch['frame'], launch['play_call']
    first, end = (variant[key] for key in ('first_control', 'end'))
    stride, rate = spec['control_frames'], case['sample_rate_hz']
    keys, tolerance = spec['dance_keys'], spec['control_absolute_tolerance']
    amp = play.get('amplitude', 1.0)
    ratio = (play.get('pitch_hz') or keys['reference_pitch_hz']) / keys['reference_pitch_hz']
    pitch = np.clip(keys['pitch_hz'] * ratio, *spec['pitch_hz_limits'])
    active = np.flatnonzero(trace['call_id'][::factor] == common.CALL_IDS['dance'])
    owned = slice(first * factor, end * factor)
    checks = {
        'dance_duration': np.array_equal(active, np.arange(request, end)),
        'pitch_holds': bool(np.all(np.abs(trace['target_pitch_hz'][owned] - pitch) <= tolerance)),
        'mouth_holds': bool(np.all(np.abs(trace['target_mouth'][owned] - keys['mouth']) <= tolerance)),
    }
    if 'before_switch_edit' in variant:
        checks.update(switch_checks(trace, case, variant, factor, request, first, end, spec))
    curve = {}
    names = ('gate', 'gate_target', 'pitch_hz', 'chaos', 'mouth', 'hiss', *common.TARGETS,
             'oral_tip_area_cm2', 'glottis_voicing')
    for frame in variant['curve_frames']:
        sample = frame * factor
        curve[str(frame)] = {key: float(trace[key][sample]) for key in names}
        if first <= frame < end:
            seconds = (frame // stride * stride - first) / rate
            gate = amp * np.interp(seconds, [0, keys['hold_seconds'], keys['release_seconds']], [1, 1, 0])
            fraction = min(1.0, seconds / keys['release_seconds'])
            chaos = keys['chaos_first'] + (keys['chaos_last'] - keys['chaos_first']) * fraction
            checks[f'curve.{frame}.gate'] = bool(abs(trace['gate_target'][sample] - gate) <= tolerance)
            checks[f'curve.{frame}.chaos'] = bool(abs(trace['target_chaos'][sample] - chaos) <= tolerance)
    return checks, {'request_frame': request, 'first_control_frame': first,
                    'end_frame': int(active[-1]) + 1 if active.size else None, 'curve_frames': curve}


def spectral_window(rate, first, seconds):
    low, high = (first + round(rate * value) for value in seconds)
    return slice(low, high)


def summarize_spectrum(series, rate, limits):
    frequency, density = periodogram(series.astype(float), fs=rate, window='hann', detrend='constant')
    low, high = limits['search_hz']
    search = (frequency >= low) & (frequency <= high)
    step = frequency[1] - frequency[0]
    bands = []
    for left, right in limits['bands_hz']:
        selected = (frequency >= left) & (frequency < right)
        bands.append({'hz': [left, right], 'rms': float(np.sqrt(np.sum(density[selected]) * step))})
    return {'peak_hz': float(frequency[search][np.argmax(density[search])]),
            'bin_hz': float(step), 'bands': bands}


def measure_spectra(candidate, upstream, pcm, case, variant, spec):
    output_rate = case['sample_rate_hz']
    factor = 2 if output_rate <= 60000 else 1
    rate = output_rate * factor
    first = variant['first_control']
    limits = spec['spectral_window']
    inside = spectral_window(rate, first * factor, limits['seconds'])
    output = spectral_window(output_rate, first, limits['seconds'])
    result = {tag: {key: summarize_spectrum(trace[key][inside], rate, limits) for key in SPECTRAL_FIELDS}
              for tag, trace in (('candidate', candidate), ('upstream', upstream))}
    result['candidate']['pcm_f32'] = summarize_spectrum(pcm[output], output_rate, limits)
    upper_pcm = upstream['pcm_f32'][factor - 1::factor].astype(np.float32)
    result['upstream']['pcm_f32'] = summarize_spectrum(upper_pcm[output], output_rate, limits)
    observed = result['candidate']['glottis_area_cm2']['peak_hz']
    low, high = variant['peak_area_hz']
    checks = {
        'spectrum.glottal_area_peak': low <= observed <= high,
        'spectrum.peak_bins_match_upstream': all(
            result['candidate'][key]['peak_hz'] == result['upstream'][key]['peak_hz']
            for key in (*SPECTRAL_FIELDS, 'pcm_f32')),
        'spectrum.low_band_propagates': all(result['candidate'][key]['bands'][0]['rms'] > 0
                                            for key in (*SPECTRAL_FIELDS, 'pcm_f32')),
    }
    return checks, {'seconds': limits['seconds'], **result}


def measure_fixed_chaos(result, case, variant, spec, folder, probe, execute):
    control = spec['fixed_chaos_control']
    frames, start = control['frames'], result['observations']['request_frame']
    quiet_chaos = case | {'frames': frames, 'shape': case['shape'] | {'chaos': control['chaos']},
                         'events': [{'frame': start, 'gate': 1.0}]}
    control_result, _, _, _ = common.capture_variant(
        quiet_chaos, {'first_control': variant['first_control']}, spec, folder / 'fixed-chaos',
        probe, execute, evaluate_boundaries=lambda *args: ({}, {}))
    result['checks'].update({f'fixed_chaos.{key}': passed for key, passed in control_result['checks'].items()})
    main_block = spec['host_block_frames'][0]
    name = f'pcm-{main_block}.csv'
    constant = columns(folder / 'fixed-chaos' / name, frames, common.CANDIDATE)
    changing = columns(folder / name, case['frames'], common.CANDIDATE)
    matching = ('gate', 'lung_pressure_dyn_cm2', 'oral_tip_area_cm2', 'velum_area_cm2', 'pitch_hz', 'glottis_f0_hz')
    result['checks']['fixed_chaos.shared_input'] = all(
        np.array_equal(constant[key], changing[key][:frames]) for key in matching)
    result['checks']['fixed_chaos.zero_roughness'] = bool(np.all(constant['chaos'] == control['chaos']))
    intervals = {}
    rate = case['sample_rate_hz']
    window = spectral_window(rate, variant['first_control'], spec['spectral_window']['seconds'])
    threshold = spec['cycle_model']['phase_wrap_threshold']
    for label, trace in (('constant', constant), ('ramp', changing)):
        indices, scales = common.cycle_period_scales(trace, rate, threshold)
        selected = scales[(indices >= window.start) & (indices < window.stop)]
        intervals[label] = {'cycles': len(selected), 'mean_scale': float(np.mean(selected)) if selected.size else None,
                            'standard_deviation': float(np.std(selected)) if selected.size else None}
    minimum = control['minimum_cycles_in_window']
    enough = all(item['cycles'] >= minimum for item in intervals.values())
    result['checks']['fixed_chaos.enough_cycles'] = enough
    result['checks']['fixed_chaos.ramp_lengthens_period'] = (
        enough and intervals['ramp']['mean_scale'] > intervals['constant']['mean_scale'])
    result['fixed_chaos'] = {'seconds': spec['spectral_window']['seconds'], 'cycles': intervals,
                             'upstream_and_independent': control_result}


def dance_definition_matches(definition, keys):
    expected_keys = [
        {'t': 0.0, 'v': {'gate': 1.0, 'pitch': keys['pitch_hz'], 'chaos': keys['chaos_first'],
                        'mouth': keys['mouth']}},
        {'t': keys['hold_seconds'], 'v': {'gate': 1.0}},
        {'t': keys['release_seconds'], 'v': {'gate': 0.0, 'chaos': keys['chaos_last']}},
    ]
    return definition['pitchRef'] == keys['reference_pitch_hz'] and definition['keys'] == expected_keys


def measure(config, spec, artifacts, execute):
    probe, official = common.prepare_probe(artifacts, execute)
    definition = artifacts / 'dance-definition.json'
    execute([str(probe), '--dance-definition'], cwd=UPSTREAM, stdout=definition)
    source = config['alligator_voice']
    checks = {'upstream_dance_keys': dance_definition_matches(read(definition), spec['dance_keys'])}
    variants = {}
    for variant in spec['variants']:
        name = variant['id']
        folder = artifacts / name
        result, case, pcm, upper_pcm = common.capture_variant(
            source, variant, spec, folder, probe, execute, evaluate_boundaries=boundary_checks,
            extra_measurement=('spectrum', measure_spectra))
        if name == 'official-full-48000':
            common.compare_official(result, case, pcm, upper_pcm, official, spec, 'dance')
            result['checks']['official_full_length'] = len(pcm) == spec['official_demo_frames']
        if name == spec['fixed_chaos_control']['variant']:
            measure_fixed_chaos(result, case, variant, spec, folder, probe, execute)
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
    baseline = WORKSPACE / 'runs/alligator-hiss-before-dance-1/manifest.json'
    previous = read(baseline)
    if previous['status'] != 'pass' or previous['upstream_revision'] != revision:
        raise SystemExit('hissの基準が確認できません')
    details = {'case_id': config['id'], 'revision': config['revision'], 'upstream_revision': revision,
               'invoked_from': str(Path.cwd()), 'scipy': scipy.__version__,
               'upstream_source_sha256': {name: sha256(UPSTREAM / name) for name in previous['upstream_source_sha256']}}
    tools = ('upstream_baseline.py', 'measure_alligator_bellow.py', 'measure_alligator_fixed_voice.py',
             'measure_seal_airway.py', 'measure_seal_sustain_pcm.py', 'measure_songbird_sustain_pcm.py',
             'measure_songbird_syrinx.py', 'measure_turbulence.py', 'measure_junction.py')
    paths = [CASE, *parents, baseline, common.fixed.PROBE, Path(__file__).resolve(), Path(shared.__file__),
             *(WORKSPACE / 'tools' / name for name in tools), WORKSPACE / 'LICENSE-CHIMERA', *shared.candidate_sources()]
    return shared.record_measurement(args.run_id, CASE, paths, details,
                                     lambda artifacts, execute: measure(config, spec, artifacts, execute), command=None)


if __name__ == '__main__':
    raise SystemExit(main())
