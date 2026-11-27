"""無音の出口で隣接するcubeb標本がタップの過渡を説明できるか調べる。"""

import argparse
import csv
from pathlib import Path
import sys

import numpy as np

from measure_csd_envelope_timing import verified_file
from measure_speech_timing import read
from measure_uniform_tube import record_measurement
from measure_worklet_fixed import ROOT
from measure_worklet_tsp_44100_edge_gain_transfer import stats
from upstream_baseline import WORKSPACE


CASE = WORKSPACE / 'cases/worklet-live-tsp-44100-headphone-gap-edge-neighbor-fit.json'
COMPONENTS = ('in_phase', 'out_of_phase')


def load_waveforms(path):
    groups = {}
    with path.open(newline='') as file:
        for row in csv.DictReader(file):
            groups.setdefault(row['selection'], []).append(row)
    frames = np.array([int(row['frame']) for row in next(iter(groups.values()))])
    if not np.array_equal(frames, np.arange(frames[0], frames[-1] + 1)):
        raise ValueError('保存波形の標本番号が連続していません')
    waves = {}
    for key, rows in groups.items():
        if not np.array_equal(frames, [int(row['frame']) for row in rows]):
            raise ValueError('収録間の比較窓が一致しません')
        waves[key] = {source: np.array([[float(row[f'{source}_{phase}']) for phase in COMPONENTS] for row in rows])
                      for source in ('cubeb', 'tap')}
        if not all(np.isfinite(waves[key][source]).all() for source in ('cubeb', 'tap')):
            raise ValueError('非有限値を含むPCMは解析できません')
    return frames, waves


def select_gate(frames, x, y, settings):
    start, stop = settings['gate_search']
    informative = (start <= frames) & (frames < stop) & (np.abs(x) >= settings['gate_minimum_amplitude'])
    available = np.flatnonzero(informative)
    crossing = available[(y[available] / x[available]) >= settings['gate_ratio']]
    if len(crossing) == 0:
        raise ValueError('学習波形に登録したゲートの閾値通過がありません')
    return int(frames[crossing[0]])


def design(frames, x, positions, gate, width, family):
    center = positions - frames[0]
    radius = np.arange(1, width + 1)
    if center.min() - width < 0 or center.max() + width >= len(x):
        raise ValueError('FIRの前後を収める保存波形が不足しています')
    removed = x * (frames < gate) if gate is not None else np.zeros_like(x)
    baseline = x - removed
    # h[0] = 1 - 2 * sum(h[1:]) と置いて直流利得を固定する。
    signal = baseline if family == 'filter_gated_pcm' else -removed
    matrix = signal[center[:, None] - radius] + signal[center[:, None] + radius] - 2 * signal[center, None]
    return baseline[center], matrix


def evaluate(model, tap, positions, focus, case):
    error = model - tap
    limit = {'absolute_difference_limit': case['evaluation']['maximum_zero_absolute_error']}
    report = stats(tap[focus], model[focus], positions[focus], limit)
    before = positions < case['evaluation']['edge_window'][0]
    after = positions >= case['evaluation']['after_window'][0]
    return {**report, 'maximum_before_absolute_error': float(np.max(np.abs(error[before]))),
            'maximum_after_absolute_error': float(np.max(np.abs(error[after])))}


def score_candidates(frames, waves, previous, case):
    training = case['training']
    plan = case['evaluation']
    global_positions = np.arange(min(plan['before_window'][0], training['window'][0]),
                                 max(plan['after_window'][1], training['window'][1]))
    edge_lo, edge_hi = plan['edge_window']
    edge = (edge_lo <= global_positions) & (global_positions < edge_hi)
    fit_lo, fit_hi = training['window']
    fit = (fit_lo <= global_positions) & (global_positions < fit_hi)
    at_positions = global_positions - frames[0]
    train = waves[training['selection']]
    i = COMPONENTS.index(training['component'])
    x, y = (train[source][:, i] for source in ('cubeb', 'tap'))
    gate = select_gate(frames, x, y, training)
    held = plan['held_out']
    held_zero = [row for row in previous['zero_input_comparisons'][held] if row['exceeds_control_floor']]

    def matches_input(row):
        sample = row['frame'] - frames[0]
        channel = COMPONENTS.index(row['component'])
        control = waves[plan['controls'][held]]
        return (waves[held]['cubeb'][sample, channel] == 0
                and waves[held]['tap'][sample, channel] == row['tap']
                and control['tap'][sample, channel] == row['control_tap']
                and abs(row['control_tap']) <= plan['zero_signal_floor'])
    if not held_zero or any(not matches_input(row) for row in held_zero):
        raise ValueError('ゼロ入力標本と連続対照が登録済みの比較結果に一致しません')

    controls_match = all(np.array_equal(waves[event]['cubeb'], waves[control]['cubeb'])
                         for event, control in plan['controls'].items())
    duplicate_matches = all(np.array_equal(waves[plan['duplicate']][key], train[key]) for key in ('cubeb', 'tap'))
    candidates = {}
    any_improved = False
    for family in case['families']:
        for width in case['half_widths']:
            base, X = design(frames, x, global_positions, gate, width, family)
            coeff, _, rank, singular = np.linalg.lstsq(X[fit], y[at_positions][fit] - base[fit],
                                                       rcond=case['relative_singular_value_cutoff'])
            condition = float(singular[0] / singular[-1]) if singular[-1] > 0 else None
            identifiable = (rank == width and condition is not None and condition <= case['maximum_condition_number'])
            by_case, predicted_held = {}, {}
            for key, capture in waves.items():
                by_case[key] = {}
                for j, phase in enumerate(COMPONENTS):
                    signal = capture['cubeb'][:, j]
                    at = None if key in plan['controls'].values() else gate
                    floor, terms = design(frames, signal, global_positions, at, width, family)
                    predicted = floor + terms @ coeff
                    by_case[key][phase] = evaluate(predicted, capture['tap'][at_positions, j],
                                                    global_positions, edge, case)
                    if key == held:
                        predicted_held[phase] = predicted
            tests = []
            for row in held_zero:
                where, phase = row['frame'], row['component']
                prediction = float(predicted_held[phase][where - global_positions[0]])
                actual = row['tap']
                # cubebがゼロの標本は有限な固定ゲインを掛けてもゼロになる。
                error = abs(actual - prediction)
                tests.append({'frame': where, 'component': phase, 'tap': actual, 'predicted': prediction,
                              'error': error, 'fixed_gain_absolute_error': abs(actual)})
            broad = [by_case[held][phase]['relative_residual'] for phase in COMPONENTS]
            broad.append(by_case[training['selection']]['out_of_phase']['relative_residual'])
            transfer_limit = plan['maximum_relative_residual']
            zero_limit = plan['maximum_zero_absolute_error']
            passes = identifiable and all(v is not None and v <= transfer_limit for v in broad) and all(
                row['error'] <= zero_limit for row in tests)
            improved = any(row['frame'] == 39 and row['component'] == 'out_of_phase'
                           and row['error'] < row['fixed_gain_absolute_error'] for row in tests)
            any_improved |= identifiable and improved
            center = float(1 - 2 * coeff.sum())
            candidates[f'{family}/{width}'] = {
                'family': family, 'half_width': width, 'rank': int(rank), 'condition_number': condition,
                'singular_values': singular.tolist(), 'identifiable': bool(identifiable),
                'center_coefficient': center, 'positive_offset_coefficients': coeff.tolist(),
                'relative_residuals_and_absolute_errors': by_case, 'held_out_zero_input_predictions': tests,
                'improves_held_out_frame_39': bool(improved), 'passes_registered_transfer_criteria': bool(passes),
            }
    accepted = [name for name, model in candidates.items() if model['passes_registered_transfer_criteria']]
    checks = {'same_continuous_cubeb': controls_match, 'same_waveform_replay': duplicate_matches,
              'identified_candidate_improves_held_out_frame_39': bool(any_improved),
              'some_candidate_passes_transfer': bool(accepted)}
    return {'checks': checks, 'gate_frame': gate, 'gate_training_component': training['component'],
            'accepted_candidates': accepted, 'models': candidates}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    case = read(CASE)
    registration = case['waveforms']
    folder = WORKSPACE / 'runs' / registration['run']
    manifest_path = folder / 'manifest.json'
    manifest = read(manifest_path)
    if (manifest['run_id'] != registration['run'] or manifest['status'] != 'pass'
            or manifest['upstream_revision'] != case['upstream_revision']
            or any(manifest[key] != registration[key] for key in ('case_id', 'case_revision'))):
        parser.error('固定ゲインとゼロ入力を照合した実行を指定してください')
    waveforms = verified_file(folder, manifest, registration['file'])
    summary = verified_file(folder, manifest, 'summary.json')
    inputs = [CASE, Path(__file__).resolve(), manifest_path, waveforms, summary,
              WORKSPACE / 'tools/measure_worklet_tsp_44100_edge_gain_transfer.py']

    def measure(out, execute):
        frames, waves = load_waveforms(waveforms)
        return score_candidates(frames, waves, read(summary), case)

    details = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': case['upstream_revision'],
               'analysis_command': [sys.executable, *sys.argv]}
    return record_measurement(args.run_id, CASE, inputs, details, measure, command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
