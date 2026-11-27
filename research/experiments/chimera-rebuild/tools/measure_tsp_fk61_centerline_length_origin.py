"""測定線31の中心点を距離の計算だけで交換し、口腔長への伝わり方を測る。"""

import argparse
from decimal import Decimal, localcontext
from fractions import Fraction
import math
import os
from pathlib import Path
import subprocess

import numpy as np

import measure_tsp_fk61_lip_area_origin as area
import measure_tsp_fk61_lip_front_origin as front
import measure_tsp_stressed_vowel_formants as tsp
from measure_tsp_f2_bandwidth_held_out import saved_case
from measure_tsp_fk61_lip_onset import CONFIG, pcm_digest
from measure_tsp_fk61_pcm_first_difference import archived_pcm
from measure_uniform_tube import candidate_sources, record_measurement
from tsp_fk61_centerline_observation import CenterlineObservation
from upstream_baseline import UPSTREAM, WORKSPACE


CASE = WORKSPACE / 'cases/tsp-fk61-centerline-length-origin.json'
MODES = front.MODES


def distance_reference(points):
    with localcontext() as ctx:
        ctx.prec = 90
        for a, b in zip(points, points[1:]):
            dx = Decimal.from_float(b[0]) - Decimal.from_float(a[0])
            dy = Decimal.from_float(b[1]) - Decimal.from_float(a[1])
            yield (dx * dx + dy * dy).sqrt()


def replay_lengths(row, rate):
    samples = row['grid']
    centerline = row['centerline']
    if len(samples) != len(centerline) or not samples or centerline[0][2] != 0.0 or not all(
            math.isfinite(x) for v in centerline for x in v):
        raise ValueError('中心線の観測値が登録条件を満たしません')
    points = [v[:2] for v in centerline]
    steps = [v[2] for v in centerline]
    axial = [samples[0][0]]
    errors = [0.0]
    for step, exact in zip(steps[1:], distance_reference(points), strict=True):
        axial.append(axial[-1] + step)
        errors.append(float(abs(Decimal.from_float(step) - exact) / Decimal.from_float(math.ulp(step))))
    junction = next(index for index, g in enumerate(samples) if g[2] == 2.0)
    length = axial[-1] - axial[junction]
    count = row['oral_cells']
    target = max(length, count * ((35_000.0 / rate) / 0.97)) / count
    return {'axial': axial, 'steps': steps, 'points': points, 'step_error_ulp': errors, 'junction': junction,
            'oral_length_cm': length, 'target_cm': target,
            'cumulative_matches': axial == [v[0] for v in samples],
            'bounds_and_oral_length_target_match': (axial[junction] == row['origin_cm'] and axial[-1] == row['end_cm']
                                                    and target == row['target'][2])}


def first_unequal(a, b):
    return next((i for i, (x, y) in enumerate(zip(a, b, strict=True)) if x != y), None)


def midpoint_report(index, traces):
    upper, local = (traces[name]['axial'][index] for name in ('upstream', 'candidate'))
    low, high = sorted((upper, local))
    midpoint = (Fraction(low) + Fraction(high)) / 2
    sums = {name: Fraction(row['axial'][index - 1]) + Fraction(row['steps'][index]) for name, row in traces.items()}
    offsets = {name: value - midpoint for name, value in sums.items()}
    return {
        'adjacent_float64_values': low != high and math.nextafter(low, high) == high,
        'midpoint': str(midpoint), 'offsets_cm': {name: float(value) for name, value in offsets.items()},
        'straddles': offsets['upstream'] * offsets['candidate'] < 0,
        'rounded_sums_match': all(float(value) == traces[name]['axial'][index] for name, value in sums.items()),
    }


def compare_length_ramps(before, after, control_samples):
    values, report = {}, {}
    for name in MODES:
        start = before['candidate' if name == 'trial' else name]['current'][2]
        target = after[name]['target'][2]
        step = (target - start) * (1.0 / control_samples)
        lengths = [start]
        for _ in range(control_samples):
            lengths.append(lengths[-1] + step)
        values[name] = lengths
        report[name] = {'initial_cm': start, 'increment_cm': step, 'target_cm': target,
                        'first_two_cm': lengths[1:3], 'final_cm': lengths[-1],
                        'matches_observation_after_two': lengths[2] == after[name]['current'][2]}
    return {'control_samples': control_samples, 'model': report,
            'same_length_each_predicted_sample': all(v == values['upstream'] for v in values.values())}


def evaluate(study, observed, previous, archive, proof, trial_pcm):
    settings = study['measurement']
    [clock] = settings['completed_frames']
    focus = settings['focus_ray']
    rate = settings['internal_sample_rate_hz']
    snap = {name: observed[name][clock] for name in MODES}
    traces = {name: replay_lengths(row, rate) for name, row in snap.items()}
    upper, standard, trial = (traces[name] for name in MODES)
    original_difference = first_unequal(upper['axial'], standard['axial'])
    rounding = midpoint_report(focus, traces)
    changed = [i for i, (a, b) in enumerate(zip(standard['points'], trial['points'], strict=True)) if a != b]
    geometry = {name: {
        'first_cumulative_difference_to_upstream': first_unequal(upper['axial'], row['axial']),
        'first_midpoint_difference_to_upstream': first_unequal(upper['points'], row['points']),
        'recorded_steps_near_focus_cm': row['steps'][focus - 1:focus + 2],
        'accumulation_near_focus_cm': row['axial'][focus - 1:focus + 2],
        'max_step_error_ulp': max(row['step_error_ulp']),
        'oral_end_cm': row['axial'][-1], 'oral_length_cm': row['oral_length_cm'],
        'target_cm': row['target_cm'], 'junction_index': row['junction'], 'junction_cm': row['axial'][row['junction']],
    } for name, row in traces.items()}
    geometry_unchanged_fields = ('grid', 'raw', 'limited', 'target', 'current', 'origin_cm', 'end_cm', 'oral_cells', 'area_inputs')
    matched_target = trial['axial'][-1] == upper['axial'][-1] and trial['target_cm'] == upper['target_cm']
    return {
        'checks': {
            'standard_and_trial_pcm_verified': (
                all(proof[name]['ordinary_equal'] and proof[name]['ordinary'] == proof[name]['probe']
                    and proof[name]['ordinary']['frames'] == settings['frames'] for name in MODES)
                and all(proof[name]['archive_equal'] and proof[name]['ordinary'] == proof[name]['archive']
                        == pcm_digest(archive[name]) for name in archive)
                and proof['trial']['ordinary'] == pcm_digest(trial_pcm)),
            'baseline_geometry_and_single_trial_input_verified': (
                all(snap[name][key] == previous[name][clock][key] for name in archive for key in geometry_unchanged_fields)
                and all(a[1:] == b[1:] for a, b in zip(snap['candidate']['grid'], snap['trial']['grid'], strict=True))
                and changed == [focus]
                and standard['points'][focus - 1] == settings['trial_input']['previous_midpoint_cm']
                and standard['points'][focus] == settings['trial_input']['standard_midpoint_cm']
                and trial['points'][focus] == [standard['points'][focus][0], settings['trial_input']['upstream_y_cm']]),
            'independent_lengths_and_rounded_accumulations_verified': (
                all(row['cumulative_matches'] and row['bounds_and_oral_length_target_match']
                    and max(row['step_error_ulp']) <= 2.0 for row in traces.values()) and rounding['rounded_sums_match']),
        },
        'predictions': {
            'local_midpoint_propagates_through_l2_and_rounding': (
                original_difference == focus and standard['points'][focus - 1] == upper['points'][focus - 1]
                and standard['points'][focus][0] == upper['points'][focus][0]
                and standard['steps'][focus] != upper['steps'][focus] and rounding['adjacent_float64_values']
                and rounding['straddles']),
            'single_midpoint_swap_aligns_focus_accumulation': (
                trial['steps'][focus] == upper['steps'][focus] and trial['axial'][focus] == upper['axial'][focus]),
            'single_midpoint_swap_aligns_oral_length': matched_target,
        },
        'geometry': geometry, 'midpoint_at_focus': rounding,
        'changed_trial_centers': changed, 'first_cumulative_difference': original_difference,
        'pcm': {'upstream_to_candidate': front.pcm_delta(archive['upstream'], archive['candidate']),
                'upstream_to_trial': front.pcm_delta(archive['upstream'], trial_pcm),
                'candidate_to_trial': front.pcm_delta(archive['candidate'], trial_pcm)},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    study = tsp.read(CASE)
    rev = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if rev != study['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    if os.environ.get('CHIMERA_RUN_STORAGE') != 'rtl9210b':
        parser.error('試験ビルドにCHIMERA_RUN_STORAGE=rtl9210bを指定してください')
    geometry, matched = (tsp.open_run(study[key], rev) for key in ('geometry', 'matched'))
    previous_settings, previous_case = saved_case(geometry, front.CASE)
    config, config_path = saved_case(matched, CONFIG)
    uid = study['measurement']['recording_id']
    spec = tsp.verified_path(matched, f'artifacts/{uid}/matched-case.json')
    pcm = tsp.verified_path(matched, 'artifacts/matched-pcm.npz')
    evidence = {name: tsp.verified_path(geometry, f'artifacts/{name}.jsonl') for name in ('upstream', 'candidate')}
    inputs = [CASE, Path(__file__).resolve(), Path(front.__file__), Path(area.__file__),
              area.observer.SNAPSHOT, Path(area.observer.__file__), previous_case, config_path, spec, pcm, *evidence.values(),
              *(run[0] / 'manifest.json' for run in (geometry, matched)), *candidate_sources(),
              front.EMBEDDED_DICTIONARY, front.DICT, front.CLI_DICT, front.RAMP_TEST, front.LOCAL, front.PROBE,
              front.TRACE_TOOL, *(WORKSPACE / 'tools' / name for name in ('tsp_fk61_centerline_observation.py',
                  'tsp_fk61_lip_observation.py', 'measure_tsp_fk61_lip_onset.py', 'measure_uniform_tube.py')),
              *(UPSTREAM / name for name in ('Cargo.lock', 'crates/chimera/src/anatomy/human.rs',
                  'crates/chimera/src/anatomy/geom.rs', 'crates/chimera/src/math.rs',
                  'crates/chimera/tests/geometry_continuity.rs'))]

    def measure(out, execute):
        archive = archived_pcm(pcm, uid)
        observer = CenterlineObservation(study['measurement'])
        observed, proof = front.capture(study, spec, config, archive, out, execute,
                                       observation=observer, scratch_prefix='fk61-centerline-')
        baseline = {name: area.read_snapshots(path, previous_settings['measurement']['completed_frames'])
                    for name, path in evidence.items()}
        with np.load(out / 'trial-pcm.npz', allow_pickle=False) as recorded:
            return evaluate(study, observed, baseline, archive, proof, recorded['pcm'])

    info = {'case_id': study['id'], 'case_revision': study['revision'], 'upstream_revision': rev}
    return record_measurement(args.run_id, CASE, inputs, info, measure, command=None, input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
