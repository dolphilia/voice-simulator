"""TSP確認用07の語末 /p/ と後続 /s/ を同じ出力フレームで照合する。"""

import argparse
from pathlib import Path
import subprocess
import sys

import numpy as np
from scipy.io import wavfile

from measure_csd_envelope_timing import verified_file
from measure_speech_timing import compare, read
from measure_tsp_coat_to import DICT, PROBE, overlap, render_and_trace, runs
from measure_tsp_listening import ROOT, hydrate_run
from measure_uniform_tube import candidate_sources, record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/tsp-soap-saves-transition.json'
VOICES = ('upstream', 'candidate')


def plan_comparison(case, candidate, upper):
    spec, limits = case['speech'], case['measurement']
    native = [seg for phrase in candidate['speech']['phrases'] for seg in phrase['timing']['segments']]
    actual = [[seg['segment']['ipa'], seg['start_seconds'], seg['end_seconds']] for seg in native]
    expected = [[seg['ipa'], seg['t0'], seg['t1']] for seg in upper['segments']]
    tolerance = limits['plan_tolerance_seconds']
    mismatch, error = compare(actual, expected, tolerance)
    stop, fricative = (next(seg for seg in native if seg['input_index'] == index)
                       for index in spec['phone_input_indexes'])
    if [seg['segment']['ipa'] for seg in (stop, fricative)] != ['p', 's']:
        raise ValueError('指定した位置に /p/ と /s/ がありません')
    p0, p1 = stop['start_seconds'], stop['end_seconds']
    s0, s1 = fricative['start_seconds'], fricative['end_seconds']
    target = p0 + min(spec['stop_after_vowel_delay_seconds'], max(0, p1 - p0 - spec['minimum_stop_seconds']))
    independent = [[target - spec['lip_closure_lead_seconds'],
                    max(target + spec['minimum_hold_seconds'], p1 - spec['lip_release_lead_seconds'])],
                   [s0 - spec['fricative_lead_seconds'], max(s0 + spec['minimum_hold_seconds'], s1)]]
    observed = {}
    for tag, plan, keys in (('upstream', upper, ('lipAp', 'ttY')),
                             ('candidate', candidate, ('lip_aperture_cm', 'tongue_tip_y_cm'))):
        selected = []
        for phone, key, bounds in zip(('p', 's'), keys, ((p0, p1), (s0, s1)), strict=True):
            item, = (row for row in plan['gestures'] if row['label'] == phone and key in row['targets']
                     and row['strength'] == 40 and bounds[0] - 0.05 < row['t0'] < bounds[1])
            selected.append([item['t0'], item['t1']])
        observed[tag] = selected
    p_match = all(compare(value, independent, tolerance)[0] is None for value in observed.values())
    return {'first_segment_difference': mismatch, 'segment_time_max_error_seconds': error,
            'phone_seconds': [[p0, p1], [s0, s1]], 'predicted_gesture_seconds': independent,
            'measured_gesture_seconds': observed, 'gesture_equations_match': p_match}


def selected_columns(path, wanted):
    with path.open() as stream:
        fields = stream.readline().strip().split(',')
    indices = [fields.index(name) for name in wanted]
    values = np.loadtxt(path, delimiter=',', skiprows=1, usecols=indices, dtype=[(name, 'f8') for name in wanted])
    if any(not np.isfinite(values[name]).all() for name in wanted):
        raise ValueError(f'CSVの観測値が非有限です ({path.name})')
    return values


def peak(signal, bounds):
    a, b = bounds
    magnitudes = np.abs(signal[a:b])
    index = a + int(np.argmax(magnitudes))
    independently_chosen = max(range(a, b), key=lambda frame: abs(float(signal[frame])))
    return {'frame': index, 'peak_abs': float(abs(signal[index])), 'crosscheck': independently_chosen == index}


def measured_transition(case, state, pcm, phone_tiers, low):
    limits = case['measurement']
    first, stop = limits['frame_range']
    rate = limits['output_rate_hz']
    phones = [[round(row[0] * rate), round(row[1] * rate), row[2]] for row in phone_tiers
              if first <= round(row[0] * rate) and round(row[1] * rate) <= stop]
    (p, s), = [(p, s) for p, s in zip(phones, phones[1:]) if (p[2], s[2]) == ('P', 'S')]
    phone_frames = [p[:2], s[:2]]
    area = state['lip_minimum_cm2']
    intervals = {
        str(threshold): runs(area[first:stop] <= threshold, first)
        for threshold in (limits['lip_closed_area_cm2'], limits['lip_area_sensitivity_cm2'])
    }
    closed = intervals[str(limits['lip_closed_area_cm2'])]
    count = sum(overlap(closed, bounds) for bounds in low)
    direct = sum(int(np.count_nonzero(area[a:b] <= limits['lip_closed_area_cm2'])) for a, b in low)
    low_count = sum(b-a for a, b in low)
    closure = max((r for r in closed if overlap([r], p[:2])), key=lambda row: overlap([row], p[:2]), default=None)
    reopening = closure[1] if closure and closure[1] < stop else None
    events = {}
    if reopening is not None:
        bounds = [reopening, min(stop, reopening + limits['reopening_pcm_window_frames'])]
        events = {'bounds': bounds, 'pcm': peak(pcm, bounds),
                  'radiation': peak(state['radiation_derivative_cm3_s2'], bounds)}
    active = (state['teeth_noise_source'] >= 0) & (state['teeth_noise_level'] > 0)
    after_p = runs(active[p[0]:stop], p[0])
    frication = next((r for r in after_p if r[1] - r[0] >= limits['sustained_teeth_frames']
                      and overlap([r], s[:2])), None)
    start = frication[0] if frication else None
    return {
        'mfa_phone_frames': phone_frames, 'lip_threshold_intervals': intervals,
        'primary_lip_closure': closure, 'reopening_frame': reopening, 'reopening_peaks': events,
        'registered_low_energy_frames': low, 'low_energy_covered_by_closed_lips': count,
        'low_energy_closed_fraction': count / low_count, 'direct_overlap_agrees': count == direct,
        'teeth_active_spans': after_p, 'first_sustained_teeth_span_touching_mfa_s': frication,
        'teeth_level_peak_during_mfa_s': float(np.max(state['teeth_noise_level'][s[0]:s[1]])),
        'teeth_forward_pressure_peak_during_mfa_s_dyn_cm2': float(
            np.max(np.abs(state['teeth_noise_forward_pressure'][s[0]:s[1]]))),
        'teeth_start_minus_reopening_frames': start - reopening if start is not None and reopening is not None else None,
    }


def measure(case, source, alignment, attribution, out, execute):
    spec, limits = case['speech'], case['measurement']
    render_and_trace(source, out, execute, body=spec['body'], host_block=spec['candidate_host_block'],
                     probe_flags=('--teeth',), extra_tests=('voiced_fricatives',))
    native, upper = map(read, (out / 'candidate-plan.json', out / 'upstream-plan.json'))
    plan = plan_comparison(case, native, upper)
    states, pcm, results, matches = {}, {}, {}, {}
    rate = limits['output_rate_hz']
    for name in VOICES:
        wave = out / f'{name}.wav'
        fs, pcm[name] = wavfile.read(wave)
        if fs != rate or pcm[name].ndim != 1 or pcm[name].dtype != np.float32 or not np.isfinite(pcm[name]).all():
            raise ValueError(f'清浄波形の形式または値が条件を満たしません ({name})')
        matches[name] = sha256(wave) == sha256(source / wave.name)
        state_path = f'{name}-state.csv'
        states[name] = selected_columns(out / state_path, case['retain_csv'][state_path]['columns'])
        if not np.array_equal(states[name]['frame'], np.arange(len(pcm[name]))):
            raise ValueError(f'状態の出力フレームに欠落があります ({name})')
        parts = attribution['thresholds'][str(limits['low_energy_threshold_db'])][name]['pieces']
        low = [x['frames'] for x in parts if x['word'] == 'soap' and x['phone'] == 'P']
        phones = alignment['intervals'][f"{case['recording_id']}-{name}"]['phones']
        results[name] = measured_transition(case, states[name], pcm[name], phones, low)

    probe_pcm = np.fromfile(out / 'upstream.f32', dtype='<f4')
    native_pcm = selected_columns(out / 'candidate-pcm.csv', ['frame', 'internal_sample', 'pcm_f32'])
    frames = len(pcm['candidate'])
    native_bits = native_pcm['pcm_f32'].astype('<f4').view('u4')
    candidate_bits, upper_bits = (pcm[key].view('u4') for key in ('candidate', 'upstream'))
    first_difference = np.flatnonzero(candidate_bits != upper_bits)
    row = np.arange(frames)
    return {
        'checks': {
            'ordinary_pcm_matches_archives': all(matches.values()),
            'observed_pcm_matches_ordinary_pcm': np.array_equal(probe_pcm.view('u4'), upper_bits)
            and np.array_equal(native_bits, candidate_bits),
            'output_frame_clock': len(pcm['upstream']) == native['output_frames'] == upper['output_frames'] == frames
            and np.array_equal(native_pcm['frame'], row)
            and np.array_equal(native_pcm['internal_sample'], row * native['decimation_factor'] + native['decimation_factor'] - 1)
            and native['decimation_factor'] * rate == limits['internal_rate_hz'],
            'mfa_boundaries': all(x['mfa_phone_frames'] == limits['mfa_phone_frames'] for x in results.values()),
            'independent_plan': plan['first_segment_difference'] is None and plan['gesture_equations_match'],
            'intervals_and_peak_crosschecks': all(x['direct_overlap_agrees'] and all(
                item['crosscheck'] for key, item in x['reopening_peaks'].items() if key != 'bounds') for x in results.values()),
        },
        'hypotheses': {name: {
            'low_energy_majority_closed': x['low_energy_closed_fraction'] >= limits['minimum_low_energy_closed_fraction'],
            'sustained_teeth_after_reopening': x['teeth_start_minus_reopening_frames'] is not None
            and x['teeth_start_minus_reopening_frames'] >= 0,
        } for name, x in results.items()},
        'output_frames': frames, 'pcm_first_bit_difference_frame': int(first_difference[0]) if first_difference.size else None,
        'pcm_peak_absolute_difference': float(np.max(np.abs(pcm['candidate'].astype('f8') - pcm['upstream']))),
        'plan': plan, 'observations': results,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    case = read(CASE)
    revision = case['upstream_revision']
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if head != revision or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('差分のない固定上流版が必要です')
    source = hydrate_run(case['source_run'], case['source_case'], revision)
    aligned = hydrate_run(case['alignment_run'], case['alignment_case'], revision)
    gaps = hydrate_run(case['attribution_run'], case['alignment_case'], revision)
    if gaps[1].get('alignment_run') != case['alignment_run']:
        parser.error('低エネルギー区間の配分と整列の実行が一致しません')
    uid = case['recording_id']
    source_files = [verified_file(*source, f'artifacts/{uid}/{name}')
                    for name in ('candidate.json', 'candidate.wav', 'upstream.wav')]
    alignment_file = verified_file(*aligned, 'summary.json')
    gap_file = verified_file(*gaps, 'artifacts/attribution.json')
    attribution = read(gap_file)
    if attribution['recording_id'] != uid or attribution['sample_rate_hz'] != case['measurement']['output_rate_hz']:
        parser.error('試聴素材のIDまたはレートが一致しません')
    inputs = [CASE, Path(__file__).resolve(), PROBE, DICT,
              WORKSPACE / 'tools/measure_tsp_coat_to.py', WORKSPACE / 'tools/measure_tsp_listening.py',
              WORKSPACE / 'tools/measure_csd_envelope_timing.py', WORKSPACE / 'tools/measure_speech_timing.py',
              WORKSPACE / 'tools/measure_uniform_tube.py', WORKSPACE / 'tools/upstream_baseline.py',
              *(run[0] / 'manifest.json' for run in (source, aligned, gaps)),
              *source_files, alignment_file, gap_file, *candidate_sources()]
    details = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision,
               'invoked_from': str(Path.cwd()), 'arguments': sys.argv[1:]}
    return record_measurement(
        args.run_id, CASE, inputs, details,
        lambda out, execute: measure(case, source_files[0].parent, read(alignment_file), attribution, out, execute),
        command=None, input_root=ROOT,
    )


if __name__ == '__main__':
    raise SystemExit(main())
