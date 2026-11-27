"""ゾウの trumpet の弁・放射・コールの切り替えを実時間ブラウザで照合する。"""

from pathlib import Path

import numpy as np

import measure_elephant_fixed_voice as fixed
import measure_elephant_rumble as rumble
import measure_elephant_trumpet as trumpet
import measure_elephant_valve as valve
import measure_wasm_fixed as wasm
import measure_worklet_elephant_fixed_voice as common
from measure_worklet_seal_sustain import compare_at, run
from measure_worklet_songbird import read_wave
from upstream_baseline import WORKSPACE


CASE = WORKSPACE / 'cases/worklet-elephant-trumpet.json'
OFFICIAL = 'official-trumpet-48000'


def compare_reed(case, spec, window, points, observed):
    first, last = window
    selected = (points >= first) & (points < last)
    if not np.array_equal(points[selected], np.arange(first, last)):
        raise ValueError('弁の独立計算には連続した観測が必要です')
    trace = {key: values[selected] for key, values in observed.items()}
    checks = {
        'initial_reed_at_rest': trace['mode'][0] <= spec['threshold_mode']
        and all(trace[key][0] == 0 for key in ('reed_height_cm', 'reed_speed_cm_s', 'reed_opening_cm2')),
    }
    differences = valve.compare_state(trace, case, spec)
    for key, diff in differences.items():
        checks[f'browser_reed_reference.{key}'] = diff['passed']
        for name in ('first_difference', 'first_over_tolerance'):
            index = diff.pop(f'{name}_sample')
            diff[f'{name}_output_frame'] = None if index is None else first + index
    return checks, differences


def compare_floor(case, variant, spec, points, observed, audio):
    first, last = variant['first_control'], variant['end_frame']
    owned = (points >= first) & (points < last)
    active = owned & (observed['mode'] > spec['threshold_mode'])
    owned_frames = points[owned]
    selected = points[active]
    floor = spec['trunk_valve_area_cm2'] * (1 - observed['mode'][active])
    margin = floor - observed['reed_opening_cm2'][active]
    area = compare_at(observed['trunk_valve_area_cm2'][active], floor, spec['tolerances']['area'], selected)
    rate = case['sample_rate_hz']
    windows = []
    for seconds in variant['windows_seconds']:
        start, end = (first + round(t * rate) for t in seconds)
        window = (points >= start) & (points < end)
        windows.append({'seconds': seconds, 'observations': int(window.sum()), 'frames': end - start,
                        'opening_peak_to_peak_cm2': float(np.ptp(observed['reed_opening_cm2'][window])),
                        'nasal_ac_rms_cm3_s': float(np.std(observed['nasal_cm3_s'][window])),
                        'pcm_rms': fixed.rms(audio[start:end])})
    early = windows[0]
    checks = {
        'browser_floor_covers_every_owned_sample': np.array_equal(owned_frames, np.arange(first, last)),
        'browser_floor_exceeds_free_opening': margin.size > 0 and bool(np.all(margin > 0)),
        'browser_floor_matches_effective_area': area['passed'],
        'browser_opening_varies_and_trunk_radiates': early['frames'] == early['observations']
        and early['opening_peak_to_peak_cm2'] > 0 and early['nasal_ac_rms_cm3_s'] > 0,
    }
    details = {'active_frames': len(selected), 'floor_selected_frames': int(np.count_nonzero(margin > 0)),
               'minimum_margin_cm2': float(np.min(margin)), 'minimum_margin_frame': int(selected[np.argmin(margin)]),
               'maximum_opening_cm2': float(np.max(observed['reed_opening_cm2'][active])),
               'maximum_mode': float(np.max(observed['mode'][active])),
               'floor_to_effective_area': area, 'radiation_windows': windows}
    return checks, details


def compare_pitch_request(spec, artifacts):
    match = spec['matched_pitch_request']
    test, control = (match[key] for key in ('case', 'control'))
    first, second = (wasm.read_json(artifacts / f'{label}-case.json')['elephant_voice']
                     for label in (test, control))
    request, = [event['play_call'] for event in first['events'] if 'play_call' in event]
    pitch = request.pop('pitch_hz')
    frames, rate = match['frames'], second['sample_rate_hz']
    candidate, reference = (wasm.read_json(artifacts / f'{label}.json') for label in (test, control))
    candidate_rows = np.asarray(candidate['observations'][:frames])
    reference_rows = np.asarray(reference['observations'])
    coordinate = np.arange(frames)
    same_clock = all(np.array_equal(rows[:, 0], coordinate) for rows in (candidate_rows, reference_rows))
    if candidate['columns'] != reference['columns'] or not same_clock:
        raise ValueError('音高指定の対照は同じ列を先頭から連続して観測してください')
    columns = {key: compare_at(values, expected, 0, coordinate)
               for key, values, expected in zip(candidate['columns'], candidate_rows.T, reference_rows.T, strict=True)}
    audio = read_wave(artifacts / f'{test}.wav', rate, first['frames'])[:frames]
    expected = read_wave(artifacts / f'{control}.wav', rate, frames)
    pcm = wasm.compare_pcm(audio, expected, 0)
    checks = {
        'browser_pitch_pair_inputs_differ_only_by_pitch_and_length': first | {'frames': frames} == second,
        'browser_pitch_pair_observations_identical': all(item['passed'] for item in columns.values()),
        'browser_pitch_pair_pcm_bits': pcm['first_bit_difference_frame'] is None,
    }
    return checks, {'frames': frames, 'pitch_request_hz': pitch, 'columns': columns, 'pcm': pcm}


def compare_variant(label, baseline, config, source, artifacts, execute, browser, module):
    measurement = config['measurement']

    def observe(case, variant, spec, points, observed, audio):
        frames = variant['curve_frames']
        locations = np.searchsorted(points, frames)
        if not np.array_equal(points[locations], frames):
            raise ValueError('コールの切り替え・制御・終了の指定フレームがブラウザ観測にありません')
        fields = ('call_id', 'gate_goal', 'pitch_hz', 'target_pitch_hz', 'target_trunk',
                  'pressure_cm_h2o', 'target_pressure_cm_h2o', 'chaos', 'target_chaos',
                  'mode', 'target_mode', 'lip_pitch_hz', 'target_lip_pitch_hz', 'reed_opening_cm2',
                  'trunk_valve_area_cm2', 'nasal_cm3_s')
        snapshots = {str(frame): {key: float(observed[key][at]) for key in fields}
                     for frame, at in zip(frames, locations, strict=True)}
        checks, details = {}, {'browser_curve_frames': snapshots}
        if window := measurement['reed_reference_windows_output_frames'].get(label):
            added, details['browser_reed_reference'] = compare_reed(case, spec, window, points, observed)
            checks.update(added)
        if label == OFFICIAL:
            added, details['browser_area_floor'] = compare_floor(case, variant, spec, points, observed, audio)
            checks.update(added)
            start = variant['first_control']
            official = fixed.waveform(baseline / 'artifacts/official-cli/elephant.wav', case)[:len(audio)]
            details['official_trumpet_segment'] = wasm.compare_pcm(audio[start:], official[start:], spec['tolerances']['pcm'])
            checks['official_trumpet_segment'] = details['official_trumpet_segment']['first_frame_over_tolerance'] is None
        if label == spec['matched_pitch_request']['control']:
            added, details['browser_pitch_pair'] = compare_pitch_request(spec, artifacts)
            checks.update(added)
        return checks, details

    return common.compare_variant(label, baseline, config, source, artifacts, execute, browser, module,
                                  control_model=rumble.reference_controls, native_observe=trumpet.observe,
                                  browser_observe=observe, official_variant=OFFICIAL)


if __name__ == '__main__':
    sources = (*(Path(module.__file__).resolve() for module in (common, fixed, rumble, trumpet, valve)), valve.CASE)
    raise SystemExit(run(CASE, trumpet.CASE, compare_variant, 'elephant_trumpet_render_does_not_allocate',
                         (44100,), __doc__, creature='elephant', official_variant=OFFICIAL, extra_sources=sources,
                         upstream_files=('crates/chimera/src/creatures/types.rs',
                                         'crates/chimera/src/sources/valves.rs',
                                         'crates/chimera-cli/src/render.rs')))
