"""ゾウの squeak と初期モードの対照を実時間ブラウザで照合する。"""

from pathlib import Path

import numpy as np

import measure_elephant_fixed_voice as fixed
import measure_elephant_rumble as rumble
import measure_elephant_squeak as squeak
import measure_elephant_trumpet as trumpet
import measure_elephant_valve as valve
import measure_wasm_fixed as wasm
import measure_worklet_elephant_fixed_voice as common
from measure_worklet_seal_sustain import capture_observations, compare_at, run
from measure_worklet_songbird import read_wave
from upstream_baseline import WORKSPACE


CASE = WORKSPACE / 'cases/worklet-elephant-squeak.json'
OFFICIAL = 'official-full-48000'


def continuous_window(points, first, end):
    a, b = np.searchsorted(points, (first, end))
    if not np.array_equal(points[a:b], np.arange(first, end)):
        raise ValueError(f'{first}〜{end - 1} の連続観測が必要です')
    return slice(a, b)


def valve_area(spec, points, observed):
    mode, opening = (observed[key] for key in ('mode', 'reed_opening_cm2'))
    active = mode > spec['threshold_mode']
    open_area = spec['trunk_valve_area_cm2']
    floor = open_area * (1 - mode)
    free = active & (opening > floor)
    expected = np.where(active, np.maximum(opening, floor), open_area)
    comparison = compare_at(observed['trunk_valve_area_cm2'], expected, spec['tolerances']['area'], points)
    return active, free, comparison


def compare_official(case, variant, spec, measurement, points, observed, audio, baseline):
    settings = measurement['official_transition']
    request, control = (settings[key] for key in ('request_frame', 'first_control_frame'))
    stop = variant['end_frame']
    edge = continuous_window(points, request - 1, stop + 1)
    trace = {key: values[edge] for key, values in observed.items()}
    full = fixed.waveform(baseline / 'artifacts/official-cli/elephant.wav', case)
    segment = wasm.compare_pcm(audio[request:], full[request:], spec['tolerances']['pcm'])
    active, free, area = valve_area(spec, points[edge], trace)
    owned = trace['call_id'] == 3
    delay = control - request + 1
    pitch = trace['target_lip_pitch_hz']
    driven_frames = int(np.count_nonzero(active & owned))
    free_frames = int(np.count_nonzero(free & owned))
    checks = {
        'official_full_length': len(full) == len(audio) == spec['official_frames'],
        'official_squeak_segment': segment['first_frame_over_tolerance'] is None,
        'browser_call_ownership_transitions': np.array_equal(points[edge][owned], np.arange(request, stop)),
        'browser_lip_pitch_waits_for_control': bool(np.all(pitch[:delay] == settings['previous_lip_pitch_hz'])
                                                    and pitch[delay] == settings['first_target_lip_pitch_hz']),
        'browser_official_effective_area': area['passed'],
        'browser_official_driven_frames': driven_frames == settings['expected_driven_frames'],
        'browser_official_free_opening_frames': free_frames == settings['expected_free_opening_frames'],
    }
    first = segment['first_bit_difference_frame']
    return checks, {'segment_pcm': segment, 'segment_start_output_frame': request,
                    'segment_first_bit_difference_output_frame': None if first is None else request + first,
                    'driven_frames': driven_frames, 'free_opening_frames': free_frames,
                    'effective_area': area}


def compare_initial_modes(case, variant, spec, measurement, points, observed, audio, artifacts):
    match = spec['matched_initial_mode']
    settings = measurement['initial_mode_control']
    label = match['standard']
    standard = wasm.read_json(artifacts / f'{label}-case.json')['elephant_voice']
    fields = (*common.STATE_FIELDS, 'target_trunk', *common.CALL_OBSERVATION_FIELDS, *common.VALVE_OBSERVATION_FIELDS)
    _, standard_points, _, standard_obs = capture_observations(label, measurement, artifacts, standard['frames'], fields)
    rate, start = case['sample_rate_hz'], variant['first_control']
    early_start, early_end = (start + round(rate * sec) for sec in match['early_window_seconds'])
    audio_start, audio_end = (start + round(rate * sec) for sec in match['audio_window_seconds'])
    areas, counts, onsets, area_results, nasal_windows = [], [], [], [], []
    for sample_points, states in ((standard_points, standard_obs), (points, observed)):
        early = continuous_window(sample_points, early_start, early_end)
        trace = {key: values[early] for key, values in states.items()}
        _, free, area_result = valve_area(spec, sample_points[early], trace)
        selected = sample_points[early][free]
        areas.append(float(trace['trunk_valve_area_cm2'][0]))
        counts.append(len(selected))
        onsets.append(int(selected[0]) if len(selected) else None)
        area_results.append(area_result)
        nasal = continuous_window(sample_points, audio_start, audio_end)
        nasal_windows.append(states['nasal_cm3_s'][nasal])
    coordinate = np.arange(audio_start, audio_end)
    reference = read_wave(artifacts / f'{label}.wav', rate, standard['frames'])
    pairs = {
        'nasal_cm3_s': compare_at(nasal_windows[1], nasal_windows[0], 0, coordinate),
        'pcm_f32': compare_at(audio[audio_start:audio_end].astype(float),
                              reference[audio_start:audio_end].astype(float), 0, coordinate),
    }
    checks = {
        'browser_initial_modes_matched_inputs': standard['shape']['mode'] == 0 and case['shape']['mode'] == 1
        and (standard | {'shape': standard['shape'] | {'mode': 1}, 'frames': match['comparison_frames']}) == case,
        'browser_initial_one_restricts_port': 0 < areas[1] < areas[0]
        and all(area < upper for area, upper in zip(areas, settings['first_control_area_upper_bound_cm2'], strict=True)),
        'browser_mode_contrast_areas': all(result['passed'] for result in area_results),
        'browser_mode_contrast_free_opening_counts': counts == settings['expected_early_free_opening_frames'],
        'browser_mode_contrast_first_opening': onsets == settings['expected_first_early_free_opening_frame'],
        'browser_mode_contrast_changes_radiation_and_pcm': all(d['maximum_absolute_error'] > 0 for d in pairs.values()),
    }
    return checks, {'first_control_frame': start, 'first_control_area_cm2': areas,
                    'early_interval_output_frames': [early_start, early_end], 'free_opening_frames': counts,
                    'first_free_opening_output_frame': onsets, 'effective_area': area_results,
                    'audio_interval_output_frames': [audio_start, audio_end], 'differences': pairs}


def compare_variant(label, baseline, config, source, artifacts, execute, browser, module):
    measurement = config['measurement']

    def observe(case, variant, spec, points, observed, audio):
        frames = variant['curve_frames']
        missing = np.setdiff1d(frames, points)
        if missing.size:
            raise ValueError(f'{label} の指定フレームを観測できませんでした {missing.tolist()}')
        locations = np.searchsorted(points, frames)
        fields = ('call_id', 'control_clock_seconds', 'gate', 'gate_goal', 'mode', 'lip_pitch_hz',
                  'chaos', 'pressure_cm_h2o', 'target_mode', 'target_lip_pitch_hz', 'target_chaos',
                  'target_pressure_cm_h2o', 'reed_drive_dyn_cm2', 'reed_opening_cm2', 'trunk_valve_area_cm2', 'nasal_cm3_s')
        snapshots = {str(frame): {key: float(observed[key][at]) for key in fields}
                     for frame, at in zip(frames, locations, strict=True)}
        checks, details = {}, {'browser_curve_frames': snapshots}
        match = spec['matched_initial_mode']
        if label in (match['standard'], match['initial_one']):
            window, = measurement['observation_windows_output_frames'][label]
            initial = continuous_window(points, *window)
            trace = {key: values[initial] for key, values in observed.items()}
            reed = valve.compare_state(trace, case, spec)
            checks.update({f'browser_reed_reference.{key}': result['passed'] for key, result in reed.items()})
            details['browser_reed_reference'] = reed
        if label == match['initial_one']:
            added, details['browser_initial_mode_comparison'] = compare_initial_modes(
                case, variant, spec, measurement, points, observed, audio, artifacts)
            checks.update(added)
        if label == OFFICIAL:
            added, details['browser_official_squeak'] = compare_official(
                case, variant, spec, measurement, points, observed, audio, baseline)
            checks.update(added)
        return checks, details

    return common.compare_variant(label, baseline, config, source, artifacts, execute, browser, module,
                                  control_model=rumble.reference_controls, native_observe=squeak.observe,
                                  browser_observe=observe, official_variant=OFFICIAL)


if __name__ == '__main__':
    sources = (*(Path(mod.__file__).resolve() for mod in (common, fixed, rumble, trumpet, squeak, valve)), valve.CASE)
    raise SystemExit(run(CASE, squeak.CASE, compare_variant, 'elephant_squeak_render_does_not_allocate',
                         (44100,), __doc__, creature='elephant', official_variant=OFFICIAL, extra_sources=sources,
                         upstream_files=('crates/chimera/src/creatures/types.rs',
                                         'crates/chimera/src/sources/valves.rs', 'crates/chimera-cli/src/render.rs')))
