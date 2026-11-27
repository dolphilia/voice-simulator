"""ゾウの rumble を実時間ブラウザで照合し、呼気開始前の放射を調べる。"""

import json
from pathlib import Path

import numpy as np

import measure_elephant_fixed_voice as fixed
import measure_elephant_rumble as rumble
import measure_wasm_fixed as wasm
import measure_worklet_elephant_fixed_voice as common
from measure_seal_sustain_pcm import columns
from measure_songbird_syrinx import CLI
from measure_worklet_seal_sustain import run
from measure_worklet_songbird import read_wave
from upstream_baseline import WORKSPACE


CASE = WORKSPACE / 'cases/worklet-elephant-rumble.json'
OFFICIAL = 'official-rumble-48000'


def compare_prebreath(case, spec, points, observed, audio, measurement, artifacts, execute):
    config = measurement['prebreath_control']
    frames = config['frames']
    rate = case['sample_rate_hz']
    first, last = config['interval_output_frames']
    if not np.array_equal(points[:frames + 1], np.arange(frames + 1)):
        raise ValueError('呼気開始前とその直後を連続観測してください')
    launch, = [event for event in case['events'] if 'play_call' in event]
    keys = spec['rumble_keys']
    pitch = keys['pitch_hz'][0][1] * (launch['play_call']['pitch_hz'] / keys['pitch_reference_hz'])
    control = case | {'frames': frames, 'events': [{'frame': launch['frame'], 'params': {'pitch_hz': pitch}}]}
    settings = artifacts / 'fixed-shape-prebreath-case.json'
    settings.write_text(json.dumps({'elephant_voice': control}, indent=2) + '\n')
    wave, csv = (artifacts / f'fixed-shape-prebreath.{suffix}' for suffix in ('wav', 'csv'))
    execute([*CLI, 'render-pcm', str(settings), str(wave), str(csv), str(measurement['expected_render_quantum_frames'])])
    constant = columns(csv, frames, (*fixed.CANDIDATE, *fixed.CALL_FIELDS, 'gate_goal'))
    fixed_audio = read_wave(wave, rate, frames)
    interval = slice(first, last)
    peak = float(np.max(np.abs(audio[interval])))
    first_lung = fixed.first_nonzero(observed['lung_pressure_dyn_cm2'][:frames + 1])
    areas = ('oral_tip_area_cm2', 'velum_area_cm2')
    first_geometry = {key: fixed.first_nonzero(observed[key][:frames] - constant[key]) for key in areas}
    onsets = {key: fixed.first_nonzero(observed[key][:frames]) for key in (*fixed.COMPONENTS, 'radiation_cm3_s2')}
    onsets['pcm_f32'] = fixed.first_nonzero(audio[:frames])
    checks = {
        'prebreath_shared_pitch_and_lung_pressure': all(
            np.array_equal(observed[key][:frames], constant[key])
            for key in ('pitch_hz', 'glottis_f0_hz', 'gate', 'lung_pressure_dyn_cm2')),
        'prebreath_pressure_starts_after_first_geometry_block': first_lung == config['first_lung_pressure_frame'],
        'prebreath_geometry_moves_on_control': all(frame == config['first_geometry_frame']
                                                  for frame in first_geometry.values()),
        'prebreath_browser_radiates': (peak >= config['minimum_pcm_peak']
                                       and onsets['oral_cm3_s'] is not None and first <= onsets['oral_cm3_s'] < last
                                       and onsets['pcm_f32'] is not None and first <= onsets['pcm_f32'] < last),
        'prebreath_fixed_geometry_is_silent': not np.any(fixed_audio)
        and not any(np.any(constant[key]) for key in (*fixed.COMPONENTS, 'radiation_cm3_s2')),
    }
    return checks, {'interval_output_frames': [first, last], 'first_lung_pressure_frame': first_lung,
                    'first_geometry_difference': first_geometry, 'first_nonzero_output_frame': onsets,
                    'browser_peak_pcm': peak, 'browser_rms': fixed.rms(audio[interval]),
                    'fixed_geometry_peak_pcm': float(np.max(np.abs(fixed_audio)))}


def compare_variant(label, baseline, config, source, artifacts, execute, browser, module):
    measurement = config['measurement']

    def observe(case, variant, spec, points, observed, audio):
        frames = variant['curve_frames']
        locations = np.searchsorted(points, frames)
        if not np.array_equal(points[locations], frames):
            raise ValueError('開始・停止前後の指定フレームがブラウザ観測にありません')
        fields = ('call_id', 'gate', 'gate_goal', 'trunk', 'target_trunk', 'pitch_hz', 'target_pitch_hz',
                  'target_pressure_cm_h2o', 'target_chaos', 'oral_tip_area_cm2', 'velum_area_cm2')
        snapshots = {str(frame): {key: float(observed[key][at]) for key in fields}
                     for frame, at in zip(frames, locations, strict=True)}
        checks, details = {}, {'browser_curve_frames': snapshots}
        if label == OFFICIAL:
            first = variant['first_control']
            official = fixed.waveform(baseline / 'artifacts/official-cli/elephant.wav', case)[:len(audio)]
            details['official_rumble_segment'] = wasm.compare_pcm(audio[first:], official[first:],
                                                                  spec['tolerances']['pcm'])
            checks['official_rumble_segment'] = details['official_rumble_segment']['first_frame_over_tolerance'] is None
        if windows := variant.get('decline_windows_seconds'):
            rate, first = case['sample_rate_hz'], variant['first_control']
            means = []
            for low, high in windows:
                mask = (points >= first + round(low * rate)) & (points < first + round(high * rate))
                means.append(float(np.mean(observed['glottis_f0_hz'][mask])))
            checks['browser_observed_f0_declines'] = means[1] < means[0]
            details['browser_decline_windows'] = {'seconds': windows, 'mean_f0_hz': means}
        if label == measurement['prebreath_control']['variant']:
            added, details['prebreath'] = compare_prebreath(
                case, spec, points, observed, audio, measurement, artifacts, execute)
            checks.update(added)
        return checks, details

    return common.compare_variant(label, baseline, config, source, artifacts, execute, browser, module,
                                  control_model=rumble.reference_controls, native_observe=rumble.observe_rumble,
                                  browser_observe=observe, official_variant=OFFICIAL)


if __name__ == '__main__':
    sources = (Path(common.__file__), Path(rumble.__file__), Path(fixed.__file__))
    raise SystemExit(run(CASE, rumble.CASE, compare_variant, 'elephant_rumble_render_does_not_allocate',
                         (44100,), __doc__, creature='elephant', official_variant=OFFICIAL, extra_sources=sources,
                         upstream_files=('crates/chimera/src/creatures/types.rs',
                                         'crates/chimera/src/airway/network.rs', 'crates/chimera-cli/src/render.rs')))
