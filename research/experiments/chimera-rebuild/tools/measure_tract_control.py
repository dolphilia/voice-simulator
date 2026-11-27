"""可動声道の制御目標を固定上流と独立した断面変化率の計算に照合する。"""

import argparse
import csv
import json
from itertools import groupby
from pathlib import Path
import re
import subprocess

import numpy as np

import measure_uniform_tube as shared
from measure_articulation import PROBE, write_upstream_events
from upstream_baseline import UPSTREAM, WORKSPACE


CASES = tuple(f'tract-slew-{name}' for name in ('vowels', 'lips', 'contact', 'contact-off', 'ten-vowels'))
COLUMNS = (
    'raw_area_cm2', 'raw_minimum_cm2', 'area_cm2', 'minimum_cm2', 'anatomical_length_cm',
    'simulation_length_cm', 'teeth_s_cm', 'lip_cell', 'tip_distance_cm', 'body_distance_cm', 'velum_cm2',
)
HEADER = ('frame', 'pass', 'tube', 'cell', *COLUMNS)
LENGTH_COLUMNS = ('anatomical_length_cm', 'simulation_length_cm', 'teeth_s_cm', 'tip_distance_cm',
                  'body_distance_cm')


def read_trace(path, cells, frames):
    with path.open(newline='') as file:
        reader = csv.reader(file)
        if tuple(next(reader, [])) != HEADER:
            raise ValueError(f'{path.name} のヘッダーが不正です')
        passes = {}
        expected = [('pharynx', i) for i in range(cells['pharynx'])]
        expected += [('oral', i) for i in range(cells['oral'])]
        for (frame, stage), group in groupby(reader, key=lambda row: (int(row[0]), row[1])):
            rows = list(group)
            if [(row[2], int(row[3])) for row in rows] != expected or (frame, stage) in passes:
                raise ValueError(f'{path.name} のセルまたは観測時点が不正です ({frame}, {stage})')
            data = np.asarray([row[4:] for row in rows], dtype=float)
            if data.shape != (len(expected), len(COLUMNS)) or not np.isfinite(data).all():
                raise ValueError(f'{path.name} の観測値が不正です ({frame}, {stage})')
            passes[frame, stage] = data
    itinerary = [(-1, 'seed')]
    for frame in range(frames):
        itinerary.append((frame, 'apply'))
        if (frame, 'reapply') in passes:
            itinerary.append((frame, 'reapply'))
    if itinerary != list(passes):
        raise ValueError(f'{path.name} の観測時点が不足または順序が不正です')
    return passes, expected


def bounded_target(raw, previous, lips, dt):
    u = np.clip((previous - .03) / .37, 0, 1)
    closing_speed = np.where(previous < .03, 5 * np.sqrt(previous / .03),
                             5 + 40 * (3 * u**2 - 2 * u**3))
    v = np.clip((previous - .03) / .03, 0, 1)
    opening_speed = np.where(lips[:, None], 7 + 38 * (3 * v**2 - 2 * v**3), 45)
    lower = previous - dt * (closing_speed + 40 * previous)
    upper = previous + dt * (opening_speed + 40 * raw)
    result = np.clip(raw, lower, upper)
    result[:, 1] = np.clip(result[:, 1], 0, result[:, 0])
    return result


def independent_trace(passes, cells, dt, sample_rate, path, *, body_scale=1.0):
    geometry_error = np.zeros(2)
    lip_matches = True
    wrong_baseline_peak = 0.0
    area_scale = body_scale**2

    def limits(raw, previous, lips):
        # 基準体型の面積単位で速度制限を評価してから、観測の面積単位に戻す。
        return bounded_target(raw / area_scale, previous / area_scale, lips, dt) * area_scale

    ph_count = sum(tube == 'pharynx' for tube, _ in cells)
    oral_count = len(cells) - ph_count
    counts = np.repeat([ph_count, oral_count], [ph_count, oral_count])
    with path.open('w', newline='') as file:
        writer = csv.writer(file, lineterminator='\n')
        writer.writerow(HEADER)
        last = passes[-1, 'seed'][:, :2]
        for (frame, stage), data in passes.items():
            anatomical, simulation, teeth, lip_cell = data[:, 4:8].T
            oral_start = anatomical[0]
            cell_dx = anatomical[ph_count] / oral_count
            first_lip = max(0, int((teeth[0] - oral_start) / cell_dx))
            lips = np.r_[np.zeros(ph_count, dtype=bool), np.arange(oral_count) >= first_lip]
            lip_matches = lip_matches and np.array_equal(lip_cell, lips)
            expected_length = np.maximum(anatomical, counts * (35000.0 / sample_rate / .97))
            geometry_error[0] = max(geometry_error[0], abs(simulation - expected_length).max())
            raw = data[:, :2]
            if stage == 'seed':
                computed = raw
            elif stage == 'apply':
                baseline = last
                computed = limits(raw, baseline, lips)
                first_pass = computed
            else:
                computed = limits(raw, baseline, lips)
                wrong = limits(raw, first_pass, lips)
                wrong_baseline_peak = max(wrong_baseline_peak, float(abs(wrong - computed).max()))
            last = computed
            geometry_error[1] = max(geometry_error[1], abs(data[:, 2:4] - computed).max())
            for (tube, cell), row, target, length, lip in zip(
                    cells, data, computed, expected_length, lips, strict=True):
                writer.writerow((frame, stage, tube, cell, *row[:2], *target, row[4], length,
                                 row[6], int(lip), *row[8:]))
    return {
        'simulation_length_error_cm': float(geometry_error[0]),
        'limited_area_error_cm2': float(geometry_error[1]),
        'lip_cells_match_from_teeth_distance': lip_matches,
        'using_first_pass_as_baseline_max_error_cm2': wrong_baseline_peak,
    }


def compare(candidate, upstream, cells, config):
    max_errors = np.zeros(len(COLUMNS))
    first = None
    limits = [config['length_absolute_lt_cm'] if column in LENGTH_COLUMNS else
              (1.0 if column == 'lip_cell' else config['area_absolute_lt_cm2'])
              for column in COLUMNS]
    for frame, stage in sorted(candidate.keys() | upstream.keys()):
        key = frame, stage
        if key not in candidate or key not in upstream:
            if first is None:
                first = {'frame': frame, 'pass': stage, 'difference': 'missing_pass',
                         'candidate': key in candidate, 'upstream': key in upstream}
            continue
        errors = abs(candidate[key] - upstream[key])
        max_errors = np.maximum(max_errors, errors.max(axis=0))
        if first is None and len(failed := np.argwhere(errors >= limits)):
            row, column = map(int, failed[0])
            tube, cell = cells[row]
            first = {'frame': frame, 'pass': stage, 'tube': tube, 'cell': cell,
                     'column': COLUMNS[column], 'candidate': float(candidate[key][row, column]),
                     'upstream': float(upstream[key][row, column])}
    return {'max_absolute_error': dict(zip(COLUMNS, max_errors.tolist(), strict=True)),
            'first_over_tolerance': first}


def capture_upstream(case, artifacts, execute):
    checks = [
        ('airway_adversarial', 'fast_but_articulator_limited_closure_gives_bounded_piston_pressure'),
        ('speech_quality', 'the_contact_model_engages_smoothly'),
    ]
    for suite, test in checks:
        execute(['cargo', 'test', '--locked', '-p', 'chimera', '--test', suite, test, '--', '--nocapture'],
                cwd=UPSTREAM, stdout=artifacts / f'upstream-{suite}-test.log')
    probe = shared.build_upstream_probe(PROBE, artifacts, execute)
    plan = artifacts / 'upstream-events.txt'
    write_upstream_events(case, plan)
    trace = artifacts / 'upstream-trace.csv'
    mode = 'tract-with-contact' if case['area_control']['project_contacts'] else 'tract'
    execute([str(probe), str(plan), mode], cwd=UPSTREAM, stdout=trace)
    return trace


def closure_check(committed, cells, config, threshold):
    index = cells.index((config['tube'], config['cell']))
    frame = config['check_frame']
    release = config['release_command_frame']
    raw, limited = committed[:, index, [1, 3]].T

    def first(mask, start, end):
        hits = np.flatnonzero(mask[start:end])
        return int(hits[0] + start) if len(hits) else None

    return {
        'raw_close_frame': first(raw <= threshold, 0, release),
        'limited_close_frame': first(limited <= threshold, 0, release),
        'raw_reopen_frame': first(raw > threshold, release, len(raw)),
        'limited_reopen_frame': first(limited > threshold, release, len(limited)),
        'limited_to_raw_minimum_ratio': float(limited[frame] / raw[frame]) if raw[frame] else None,
    }


def measure_transitions(areas, seed, cells, targets):
    # フレーム0の前に確定した初期姿勢を含め、前フレームとの差を求める。
    steps = abs(np.diff(np.concatenate((seed[None, :, :4], areas[:, :, :4])), axis=0))
    records = []
    for transition in targets:
        start = transition['start_frame']
        stop = transition['end_frame_exclusive']
        if not 0 <= start < stop <= len(steps):
            raise ValueError('遷移の観測区間が制御フレームの範囲外です')
        record = {'from_ipa': transition['from_ipa'], 'to_ipa': transition['to_ipa'],
                  'start_frame': start, 'end_frame_exclusive': stop}
        accepted = True
        for index, kind in enumerate(('raw', 'limited')):
            values = steps[start:stop, :, 2*index:2*index+2]
            frame, cell, column = np.unravel_index(values.argmax(), values.shape)
            value = float(values[frame, cell, column])
            tube, number = cells[cell]
            record[kind] = {'step_cm2': value, 'frame': start + int(frame), 'tube': tube,
                            'cell': number, 'area': ('mean', 'minimum')[column]}
            lo, hi = transition[f'max_{kind}_step_cm2']
            accepted = accepted and lo <= value <= hi
        record['passed'] = accepted
        records.append(record)
    return records


def measure(case, artifacts, execute):
    frames = case['measurement']['frames']
    config = case['measurement']['area_control']
    count = config['tube_cells']
    rate = case['articulators']['sample_rate_hz']
    dt = case['articulators']['control_block_samples'] / rate
    candidate, cells = read_trace(artifacts / 'trace.csv', count, frames)
    upstream, _ = read_trace(capture_upstream(case, artifacts, execute), count, frames)
    baseline = compare(candidate, upstream, cells, config)
    independent = independent_trace(
        candidate, cells, dt, rate, artifacts / 'independent-trace.csv')
    all_data = np.concatenate(list(candidate.values()))
    committed = np.stack([candidate.get((frame, 'reapply'), candidate[frame, 'apply'])
                          for frame in range(frames)])
    reapply_frames = [frame for (frame, stage) in candidate if stage == 'reapply']
    minimum_tip = min(float(data[0, 8]) for (_, stage), data in candidate.items() if stage == 'apply')
    peak_velum = float(committed[:, 0, 10].max())
    max_effect = float(abs(committed[:, :, :2] - committed[:, :, 2:4]).max())
    expected_reapply = config['reapply_frames']
    if expected_reapply:
        first, last = expected_reapply
        expected_reapply = list(range(first, last + 1))
    checks = {
        'fixed_upstream_targets': baseline['first_over_tolerance'] is None,
        'independent_rate_limit': independent['limited_area_error_cm2'] < config['area_absolute_lt_cm2'],
        'independent_length_floor': independent['simulation_length_error_cm'] < config['length_absolute_lt_cm'],
        'independent_lip_cells': independent['lip_cells_match_from_teeth_distance'],
        'nonnegative_minimum_at_most_mean': bool(np.all((all_data[:, 3] >= 0) & (all_data[:, 3] <= all_data[:, 2]))),
        'unlimited_seed': bool(np.array_equal(candidate[-1, 'seed'][:, :2], candidate[-1, 'seed'][:, 2:4])),
        'registered_reapply_frames': reapply_frames == expected_reapply,
        'registered_limit_effect': max_effect > config['max_limit_effect_gt_cm2'],
    }
    summary = {
        'checks': checks,
        'frames': frames,
        'control_period_seconds': dt,
        'upstream': baseline,
        'independent': independent,
        'reapply_frames': reapply_frames,
        'min_unprojected_tip_distance_cm': minimum_tip,
        'peak_velum_cm2': peak_velum,
        'maximum_limit_effect_cm2': max_effect,
    }
    for key, value in [('min_unprojected_tip_distance_cm', minimum_tip), ('peak_velum_cm2', peak_velum)]:
        if key in config:
            lo, hi = config[key]
            checks[f'registered_{key}'] = lo <= value <= hi
    if 'second_pass_wrong_baseline_effect_gt_cm2' in config:
        checks['distinguishes_first_pass_baseline'] = (
            independent['using_first_pass_as_baseline_max_error_cm2']
            > config['second_pass_wrong_baseline_effect_gt_cm2']
        )
    if 'closure' in config:
        expected = config['closure']
        results = closure_check(committed, cells, expected, config['closed_below_cm2'])
        checks['registered_closure_timing_and_release'] = all(
            value is not None and expected[key][0] <= value <= expected[key][1]
            for key, value in results.items()
        )
        summary['closure'] = results
    if 'transitions' in config:
        transitions = measure_transitions(committed, candidate[-1, 'seed'], cells, config['transitions'])
        checks['registered_step_per_vowel_transition'] = all(record['passed'] for record in transitions)
        summary['transitions'] = transitions
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('case', choices=CASES)
    args = parser.parse_args()
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]*', args.run_id):
        parser.error('実行IDは英数字で始め、英数字・ハイフン・アンダースコアで指定してください')
    path = WORKSPACE / 'cases' / f'{args.case}.json'
    case = json.loads(path.read_text())
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'],
                                                                        cwd=UPSTREAM, text=True):
        raise ValueError('変更のない固定上流版が必要です')
    sources = [path, PROBE, Path(__file__).resolve(), Path(shared.__file__),
               WORKSPACE / 'tools/measure_articulation.py', WORKSPACE / 'tools/upstream_baseline.py',
               *shared.candidate_sources()]
    details = {'upstream_revision': revision, 'case_id': case['id']}
    return shared.record_measurement(args.run_id, path, sources, details,
                                     lambda artifacts, execute: measure(case, artifacts, execute))


if __name__ == '__main__':
    raise SystemExit(main())
