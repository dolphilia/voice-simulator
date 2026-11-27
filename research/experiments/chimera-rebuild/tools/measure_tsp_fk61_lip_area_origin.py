"""FK61_01の測定線から口端セル、気道の登録値までを照合する。"""

import argparse
from bisect import bisect_right
import gzip
import json
import math
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

import numpy as np

import measure_tsp_stressed_vowel_formants as tsp
import tsp_fk61_lip_area_observation as observer
from measure_duet_child_glottal_noise_origin import bit_equal
from measure_tsp_f2_bandwidth_held_out import saved_case
from measure_tsp_fine_variation import DICT, LOCAL, PROBE
from measure_tsp_fk61_lip_onset import (
    CONFIG, EMBEDDED_DICTIONARY, TRACE_TOOL, copy_inputs, normal_pcm, pcm_digest, read_trace,
)
from measure_tsp_fk61_pcm_first_difference import MODES, archived_pcm
from measure_uniform_tube import build_upstream_probe, candidate_sources, record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE


CASE = WORKSPACE / 'cases/tsp-fk61-lip-area-origin.json'
GRID_COLUMNS = ('s_cm', 'area_cm2', 'region', 'ray_gap_cm', 'contact_gap_cm', 'inner_x_cm', 'inner_y_cm',
                'outer_x_cm', 'outer_y_cm', 'mid_x_cm', 'mid_y_cm')
TESTS = {
    'upstream': ('chimera', 'golden_geometry'),
    'candidate': ('vocal-core', 'geometry_ramp'),
}


def capture(study, spec, config, archived, out, execute):
    measure = study['measurement']
    text = tsp.read(spec)['speech_voice']['input']['text']
    f0 = config['body']['female']['base_f0_hz']
    snapshots, proof = {}, {}
    with TemporaryDirectory(prefix='fk61-lip-area-', dir=out.parent / 'tmp') as directory:
        tmp = Path(directory)
        upper = tmp / 'upstream'
        upper.mkdir()
        archive = tmp / 'fixed.tar'
        execute(['git', 'archive', study['upstream_revision']], cwd=UPSTREAM, stdout=archive)
        execute(['tar', '-xf', str(archive), '-C', str(upper)])
        dictionary = tmp / 'dictionary.tsv'
        dictionary.write_bytes(gzip.decompress(DICT.read_bytes()))
        candidate = tmp / 'candidate'
        copy_inputs([*candidate_sources(), EMBEDDED_DICTIONARY, LOCAL, TRACE_TOOL, observer.SNAPSHOT], candidate)
        copy_inputs([PROBE, observer.SNAPSHOT], upper)
        for name in MODES:
            fixed = name == 'upstream'
            root = upper if fixed else candidate
            original = UPSTREAM if fixed else WORKSPACE
            flags = ('--offline', '--target-dir', str(tmp / f'{name}-target'))
            ordinary = normal_pcm(name, original, flags, spec, text, tmp / f'{name}.wav', measure, execute)
            package, test = TESTS[name]
            execute(['cargo', 'test', '--locked', '--release', '-p', package, *flags, '--test', test],
                    cwd=original, stdout=out / f'{name}-tests.log')
            source = observer.prepare(root, fixed, measure['completed_frames'])
            exe = build_upstream_probe(source, tmp, execute, upstream=root,
                                      package='chimera' if fixed else 'vocal-core', lto='fat' if fixed else 'off',
                                      extra_libraries=('serde_json',), cargo_args=flags,
                                      rustc_args=('--cfg', 'lip_upstream') if fixed else ())
            trace, pcm, stages = (tmp / f'{name}.{suffix}' for suffix in ('source', 'pcm', 'stages'))
            args = [str(exe), str(spec), str(dictionary)]
            if fixed:
                args.extend(map(str, (trace, pcm, tmp / 'plan.json')))
            else:
                args.extend(['0', str(measure['initial_f0_hz']), str(f0), *map(str, (trace, pcm, stages))])
            jsonl = out / f'{name}.jsonl'
            execute(args, stdout=jsonl)
            observed = np.fromfile(pcm, dtype='<f4')
            proof[name] = {'ordinary': pcm_digest(ordinary), 'probe': pcm_digest(observed),
                           'archived': pcm_digest(archived[name]),
                           'equal': bool(bit_equal(ordinary, observed) and bit_equal(ordinary, archived[name]))}
            snapshots[name] = read_snapshots(jsonl, measure['completed_frames'])
    (out / 'pcm-digests.json').write_text(json.dumps(proof, indent=2) + '\n')
    (out / 'grid-columns.json').write_text(json.dumps(GRID_COLUMNS, indent=2) + '\n')
    return snapshots, proof


def read_snapshots(path, requested):
    payload = [json.loads(line) for line in path.read_text().splitlines()]
    if [state['completed_frames'] for state in payload] != requested:
        raise ValueError(f'登録時刻の口端観測がありません ({path.name})')
    for state in payload:
        grid = np.asarray(state['tract']['grid'])
        if (grid.ndim != 2 or grid.shape[1] != len(GRID_COLUMNS) or not np.isfinite(grid).all()
                or (np.diff(grid[:, 0]) < 0.0).any()):
            raise ValueError(f'測定線の形状または軸上順序を確認できません ({path.name})')
    return {row['completed_frames']: row['tract'] for row in payload}


def resample(bounds, grid, *, index_from_end=1):
    origin, end, count = (bounds[key] for key in ('origin_cm', 'end_cm', 'oral_cells'))
    if not 1 <= index_from_end <= count:
        raise ValueError('観測する口腔セルの番号が断面の範囲外です')
    index = count - index_from_end
    step = (end - origin) / count
    start = origin + step * index
    last = origin + step * (index + 1) + (1e-6 if index_from_end == 1 else 0.0)
    positions = [row[0] for row in grid]
    sites = [i for i, pos in enumerate(positions) if start <= pos <= last]
    midpoints = []
    for sub in range(8):
        s = origin + step * (index + (sub + 0.5) / 8)
        right = min(max(bisect_right(positions, s), 1), len(positions) - 1)
        left = right - 1
        a, b = grid[left][1], grid[right][1]
        t = min(1.0, max(0.0, (s - positions[left]) / max(positions[right] - positions[left], 1e-9)))
        midpoints.append({'s_cm': s, 'left': left, 'right': right, 'fraction': t, 'area_cm2': a + (b - a) * t})
    local_areas = [row['area_cm2'] for row in midpoints]
    minimum = min([*local_areas, *(grid[i][1] for i in sites)])
    inverse_sum = sum_ordered(1.0 / area for area in local_areas) if minimum > 1e-5 else 0.0
    average = 8 / inverse_sum if inverse_sum else 0.0
    contributors = sorted({row[key] for row in midpoints for key in ('left', 'right')} | set(sites))
    return {'cell': [average, min(minimum, average)], 'midpoints': midpoints, 'rays_used': contributors}


def sum_ordered(values):
    total = 0.0
    for value in values:
        total += value
    return total


def compare(frame, upper, candidate, tolerance):
    configs = {
        'upstream': resample(upper, upper['grid']), 'candidate': resample(candidate, candidate['grid']),
        'upper_bounds_candidate_grid': resample(upper, candidate['grid']),
        'candidate_bounds_upper_grid': resample(candidate, upper['grid']),
    }
    grids = {name: np.asarray(row['grid']) for name, row in zip(MODES, (upper, candidate), strict=True)}
    used = {name: configs[name]['rays_used'] for name in MODES}
    aligned = len(grids['upstream']) == len(grids['candidate'])
    used_indices = sorted(set(used['upstream']) | set(used['candidate']))
    if aligned:
        delta = grids['candidate'][used_indices] - grids['upstream'][used_indices]
        grid_differences = {field: float(np.max(np.abs(values))) for field, values in zip(GRID_COLUMNS, delta.T, strict=True)}
        grid_rows = [{'ray': i, **{name: grids[name][i].tolist() for name in MODES}} for i in used_indices]
    else:
        grid_differences = None
        grid_rows = {name: [grids[name][i].tolist() for i in used[name]] for name in MODES}
    return {
        'frame': frame, 'matching_cell_bounds': all(upper[key] == candidate[key] for key in ('oral_cells', 'origin_cm', 'end_cm')),
        'grid_differences_in_cell_rays': grid_differences, 'grid_rows': grid_rows,
        'raw_matches_independent': all(
            max(abs(a - b) for a, b in zip(configs[name]['cell'], row['raw'], strict=True)) <= tolerance
            for name, row in zip(MODES, (upper, candidate), strict=True)),
        'net_target_matches_limited': all(row['target'][:2] == row['limited'] for row in (upper, candidate)),
        'model': {name: {key: row[key] for key in ('raw', 'limited', 'target', 'current', 'area_inputs')}
                  for name, row in zip(MODES, (upper, candidate), strict=True)},
        'replay': configs,
    }


def current_from_lip(row):
    return [row[key] for key in ('area_cm2', 'minimum', 'length_cm')]


def front_area(row, inputs):
    scale, width, teeth, _ = inputs
    weight = min(1.0, max(0.0, (row[9] - teeth) / (0.45 * scale)))
    dental = 2.0 * math.pow(row[4], 1.4)
    ellipse = (math.pi / 4.0) * row[4] * width
    return dental + (ellipse - dental) * weight, weight


def explain_initial_rays(initial, snapshots):
    # 区間や測定線位置を変えず、影響のある各面積だけを交換する事後の対照。
    if not initial['matching_cell_bounds'] or not isinstance(initial['grid_rows'], list):
        return None
    changed = [row['ray'] for row in initial['grid_rows'] if row['upstream'][1] != row['candidate'][1]]
    if not changed:
        return None
    recipes = dict.fromkeys([(index,) for index in changed] + [tuple(changed)])
    swaps = {}
    for name, donor in (MODES, MODES[::-1]):
        current = snapshots[name][0]
        other = snapshots[donor][0]
        results = []
        for indices in recipes:
            grid = [row.copy() for row in current['grid']]
            for index in indices:
                grid[index][1] = other['grid'][index][1]
            cell = resample(current, grid)['cell']
            results.append({'rays': list(indices), 'cell': cell, 'matches_donor': cell == other['raw']})
        swaps[name] = results
    models = []
    for index in changed:
        model = {'ray': index}
        for name, donor in (MODES, MODES[::-1]):
            current = snapshots[name][0]
            row = current['grid'][index]
            other = snapshots[donor][0]['grid'][index]
            if row[2] != 3 or other[2] != 3:
                continue
            result, weight = front_area(row, current['area_inputs'])
            gap_swap = row.copy()
            gap_swap[4] = other[4]
            position_swap = row.copy()
            position_swap[9] = other[9]
            model[name] = {'measured_area': row[1], 'replayed_area': result, 'lip_weight': weight,
                           'swapped_contact_gap_area': front_area(gap_swap, current['area_inputs'])[0],
                           'swapped_midpoint_x_area': front_area(position_swap, current['area_inputs'])[0]}
        models.append(model)
    return {'changed_rays': changed, 'per_ray_area_input_swaps': models, 'resampling_swaps': swaps}


def evaluate(study, snapshots, prior, digests, archive):
    measure = study['measurement']
    control = measure['control_samples']
    onset = measure['onset_sample']
    if onset % 2 or onset % control or measure['internal_sample_rate_hz'] != 2 * measure['sample_rate_hz']:
        raise ValueError('モデルの制御境界と観測時刻をそろえてください')
    rows = [compare(frame, snapshots['upstream'][frame], snapshots['candidate'][frame], measure['absolute_tolerance_cm2'])
            for frame in measure['completed_frames']]
    state = {row['frame']: row for row in rows}
    initial = state[0]
    update = state[onset // 2 + 1]['model']
    ramp = {}
    for name in MODES:
        before = state[onset // 2]['model'][name]['current']
        after = update[name]['current']
        increments = [(new - old) * (1.0 / control) for old, new in zip(before, update[name]['target'], strict=True)]
        expected = before.copy()
        matches = []
        for index in (onset, onset + 1):
            a, m, length = (x + d for x, d in zip(expected, increments, strict=True))
            expected = [max(0.0, a), min(max(0.0, a), max(0.0, m)), length]
            matches.append(expected == current_from_lip(prior[name][index]))
        ramp[name] = {'increments': increments, 'matches_old': before == current_from_lip(prior[name][onset - 1]),
                      'matches_new': after == current_from_lip(prior[name][onset + 1]),
                      'independent_steps_match': matches}
    initial_model = initial['model']
    upper_raw = initial_model['upstream']['raw']
    candidate_raw = initial_model['candidate']['raw']
    replay = initial['replay']
    return {
        'checks': {
            'archive_ordinary_and_probe_match_all_frames': all(
                digests[name]['equal'] and digests[name]['ordinary'] == digests[name]['probe'] == digests[name]['archived']
                == pcm_digest(archive[name]) and len(archive[name]) == measure['frames'] for name in MODES),
            'independent_local_resampling_matches': all(row['raw_matches_independent'] for row in rows),
            'initial_and_rate_limited_targets_match_network': (
                all(row['net_target_matches_limited'] for row in rows)
                and all(initial_model[name]['current'] == initial_model[name]['target'] for name in MODES)),
            'aligned_with_prior_two_sample_geometry_and_independent_ramp': all(
                row['matches_old'] and row['matches_new'] and all(row['independent_steps_match']) for row in ramp.values()),
        },
        'predictions': {
            'initial_raw_cell_already_differs': upper_raw[0] != candidate_raw[0],
            'shared_grid_and_bounds_explain_cell_difference': (
                initial['matching_cell_bounds'] and replay['upper_bounds_candidate_grid']['cell'] == candidate_raw
                and replay['candidate_bounds_upper_grid']['cell'] == upper_raw),
            'local_slew_does_not_change_raw_area_at_onset': all(row['raw'][0] == row['limited'][0] for row in update.values()),
        },
        'frames': rows, 'onset_ramp': ramp, 'initial_ray_diagnostics': explain_initial_rays(initial, snapshots),
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
    lip, matched = (tsp.open_run(study[key], rev) for key in ('lip', 'matched'))
    config, config_path = saved_case(matched, CONFIG)
    uid = study['measurement']['recording_id']
    spec = tsp.verified_path(matched, f'artifacts/{uid}/matched-case.json')
    stored = tsp.verified_path(matched, 'artifacts/matched-pcm.npz')
    prior = {name: tsp.verified_path(lip, f'artifacts/{name}-lip.f64le') for name in MODES}
    lip_case = tsp.verified_path(lip, 'summary.json')
    cfg, prior_case = saved_case(lip, WORKSPACE / 'cases/tsp-fk61-lip-onset.json')
    if tsp.read(lip_case)['first_lip_difference'] != study['measurement']['onset_sample']:
        parser.error('先行計測の口端流量の初差と登録時刻が一致しません')
    inputs = [CASE, Path(__file__).resolve(), Path(observer.__file__), observer.SNAPSHOT, EMBEDDED_DICTIONARY, DICT,
              LOCAL, PROBE, TRACE_TOOL, config_path, spec, stored, prior_case, lip_case, *prior.values(),
              *(r[0] / 'manifest.json' for r in (lip, matched)), *candidate_sources(),
              WORKSPACE / 'data/cmudict.txt.gz', WORKSPACE / 'crates/vocal-core/tests/geometry_ramp.rs',
              *(UPSTREAM / name for name in ('Cargo.lock', 'crates/chimera/src/airway/network.rs',
                  'crates/chimera/src/voice/human_airway.rs', 'crates/chimera/src/voice/human_voice.rs',
                  'crates/chimera/src/anatomy/human.rs', 'crates/chimera/tests/golden_geometry.rs')),
              *(WORKSPACE / 'tools' / name for name in ('measure_tsp_fk61_lip_onset.py',
                  'tsp_fk61_lip_observation.py', 'measure_tsp_fk61_pcm_first_difference.py', 'measure_uniform_tube.py'))]

    def measure(out, execute):
        archive = archived_pcm(stored, uid)
        snapshots, proof = capture(study, spec, config, archive, out, execute)
        lo, hi = cfg['measurement']['comparison_internal_samples']
        evidence = {name: dict(zip(range(lo, hi), read_trace(prior[name], hi - lo), strict=True)) for name in MODES}
        return evaluate(study, snapshots, evidence, proof, archive)

    info = {'case_id': study['id'], 'case_revision': study['revision'], 'upstream_revision': rev}
    return record_measurement(args.run_id, CASE, inputs, info, measure, command=None, input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
