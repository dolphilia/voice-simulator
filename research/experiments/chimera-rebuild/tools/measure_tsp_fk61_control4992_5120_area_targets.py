"""二つの制御境界で口腔断面積の再標本化・速度制限・補間を分けて測る。"""

import argparse
from bisect import bisect_right
import csv
from fractions import Fraction
import math
from pathlib import Path

import numpy as np

import measure_tsp_fk61_onset_to_control5504_volume_history as onset


history, geometry, inlet, oral, six, load, tsp = (
    onset.history, onset.geometry, onset.inlet, onset.oral, onset.six, onset.load, onset.tsp)
CASE = geometry.radiation.WORKSPACE / 'cases/tsp-fk61-control4992-5120-area-targets.json'
RAW_FIELDS = ('area', 'minimum', 'old_area', 'old_minimum', 'dt', 'scale2', 'lips_from')
GRID_FIELDS = ('arc_cm', 'area_cm2')
PRIOR_FILES = onset.SAVED_FILES[:-1]
SAVED_FILES = (*PRIOR_FILES, *(f'{mode}-{tag}.csv' for mode in geometry.MODES
                              for tag in ('area-raw', 'area-grid')), 'trajectories.npz')


def prepare(root, fixed, window, execute, *, measure):
    source = history.prepare(root, fixed, window, execute, measure=measure)
    insert = geometry.observer.insert_before
    samples = ' | '.join(map(str, measure['area_focus_blocks']))
    indices = [j - measure['nodes'][1] for j in measure['area_focus_nodes']]
    focus = ', '.join(map(str, indices))
    if fixed:
        airway = root / 'crates/chimera/src/voice/human_airway.rs'
        insert(airway, '            clamp_arr(&mut self.or_areas, &base[1], &mut self.or_min, &base[3], lips_from);',
               f'''            if let Some(sample) = self.net.research_oral_boundary().filter(|n| matches!(*n, {samples})) {{
                for index in [{focus}] {{
                    self.net.research_oral_ramp("area-raw", sample, self.oral.node(index),
                        &[self.or_areas[index], self.or_min[index], base[1][index], base[3][index],
                            dt, k2, lips_from as f64]);
                }}
                for (index, row) in f.grid.iter().enumerate() {{
                    self.net.research_oral_ramp("area-grid", sample, index, &[row.s, row.area]);
                }}
            }}
''')
    else:
        tract = root / 'crates/vocal-core/src/airway/tract_control.rs'
        insert(tract, '    area_samples: Vec<AreaSample>,',
               f'    pub(crate) research_rate_basis: [[f64; 4]; {len(indices)}],\n')
        insert(tract, '        area_samples: profile.samples,',
               f'        research_rate_basis: [[0.0; 4]; {len(indices)}],\n')
        insert(tract, '            limit_tube(\n                &mut self.limited.oral,', f'''            for (i, index) in [{focus}].into_iter().enumerate() {{
                if let Some(old) = baseline.oral.cells.get(index) {{
                    self.research_rate_basis[i] = [old.area_cm2, old.minimum_area_cm2, dt, area_scale];
                }}
            }}
''')
        airway = root / 'crates/vocal-core/src/airway/human.rs'
        marker = '        for node in tube_targets[1].0.nodes.clone() {\n            let [area, minimum]'
        insert(airway, marker, f'''        if matches!(sample, {samples}) {{
            for (i, index) in [{focus}].into_iter().enumerate() {{
                let cell = &targets.raw.oral.cells[index];
                let [old_area, old_min, dt, scale2] = targets.research_rate_basis[i];
                self.network.research_oral_ramp("area-raw", sample, tube_targets[1].0.nodes.start + index,
                    &[cell.area_cm2, cell.minimum_area_cm2, old_area, old_min, dt, scale2, targets.lips_from as f64]);
            }}
            for (index, row) in targets.research_area_samples().iter().enumerate() {{
                self.network.research_oral_ramp("area-grid", sample, index, &[row.s_cm, row.area_cm2]);
            }}
        }}
''')
    return source


def split_observations(out, mode):
    geometry.split_observations(out, mode, geometry.RAMP_FIELDS | {'centerline': history.GRID_FIELDS,
                                                                   'area-raw': RAW_FIELDS, 'area-grid': GRID_FIELDS})


def read_rows(path, fields):
    records = {}
    with path.open(newline='') as file:
        reader = csv.reader(file)
        if tuple(next(reader)) != ('sample', 'node', *fields):
            raise ValueError(f'観測列が異なります ({path.name})')
        for sample, node, *data in reader:
            # 同一境界で接触補正があれば最後の確定値を使う。
            values = tuple(map(float, data))
            if len(values) != len(fields) or not all(map(math.isfinite, values)):
                raise ValueError(f'観測列の値が異なります ({path.name}, {sample}, {node})')
            records[int(sample), int(node)] = dict(zip(fields, values, strict=True))
    return records


def resample(arcs, areas, section, count, index):
    start, end = section
    length = (end - start) / count
    left = start + length * index
    right = start + length * (index + 1)
    grid_min = min((a for s, a in zip(arcs, areas, strict=True) if left <= s <= right), default=math.inf)
    interpolated = []
    for tap in range(8):
        s = start + length * (index + (tap + 0.5) / 8)
        upper = bisect_right(arcs, s)
        if not 0 < upper < len(arcs):
            raise ValueError('口腔内の評価点が格子範囲を外れました')
        fraction = (s - arcs[upper - 1]) / max(1e-9, arcs[upper] - arcs[upper - 1])
        a, b = areas[upper - 1:upper + 1]
        interpolated.append(a + (b - a) * fraction)
    minimum = min(grid_min, *interpolated)
    if minimum <= 1e-5:
        return (0.0, 0.0)
    # 上流と同じ加算順序を明示する。Python の sum は版によって補償和になる。
    inverse_sum = 0.0
    for value in interpolated:
        inverse_sum += 1 / value
    area = 8 / inverse_sum
    return area, min(minimum, area)


def limited(target, old, dt, scale, lip, fixed):
    open_rate, seal_rate, lo, hi, lip_rate = (base * scale for base in (45.0, 5.0, 0.03, 0.4, 7.0))
    if target > old:
        if lip:
            t = min(1.0, max(0.0, (old - lo) / lo))
            open_rate = lip_rate + (open_rate - lip_rate) * (t * t * (3 - 2 * t))
        cap = (open_rate + 40 * target) * dt
        if fixed:
            return old + cap if target - old > cap else target
        return min(target, old + cap)
    if old < lo:
        rate = seal_rate * math.sqrt(max(0.0, old) / lo)
    else:
        t = min(1.0, max(0.0, (old - lo) / (hi - lo)))
        rate = seal_rate + (open_rate - seal_rate) * t * t * (3 - 2 * t)
    cap = (rate + 40 * old) * dt
    if fixed:
        return old - cap if target - old < -cap else target
    return max(target, old - cap)


def measure_stages(out, ramps, measure):
    blocks, nodes = measure['area_focus_blocks'], measure['area_focus_nodes']
    count = len(measure['nodes']) - 1
    offset = measure['nodes'][1]
    stages, stage_errors, substitutions = {}, [], {}
    for mode in geometry.MODES:
        rows = read_rows(out / f'{mode}-area-raw.csv', RAW_FIELDS)
        grids = read_rows(out / f'{mode}-area-grid.csv', GRID_FIELDS)
        centerline = history.read_centerlines(out / f'{mode}-centerline.csv', measure['control_boundaries'])
        if set(rows) != {(n, j) for n in blocks for j in nodes}:
            raise ValueError('速度制限前に採取した標本または節点が異なります')
        stages[mode] = {}
        for n in blocks:
            line = centerline[n]
            sorted_grid = [grids[n, index] for index in range(len(line))]
            arcs = [g['arc_cm'] for g in sorted_grid]
            areas = [g['area_cm2'] for g in sorted_grid]
            section = next(ray[2] for ray in line if ray[-1] == 1), arcs[-1]
            if arcs != [ray[2] for ray in line]:
                stage_errors.append((mode, n, 'grid'))
            substitutions[mode, n] = (arcs, areas, section)
            for j in nodes:
                row = rows[n, j]
                ramp = ramps[mode][n, j]
                area, minimum = resample(arcs, areas, section, count, j - offset)
                if (area, minimum) != (row['area'], row['minimum']):
                    stage_errors.append((mode, n, j, 'resample'))
                lip = j - offset >= row['lips_from']
                fixed = mode == 'upstream'
                predicted = limited(row['area'], row['old_area'], row['dt'], row['scale2'], lip, fixed)
                predicted_min = limited(row['minimum'], row['old_minimum'], row['dt'], row['scale2'], lip, fixed)
                if (predicted, max(0.0, min(predicted, predicted_min))) != (ramp['area'], ramp['minimum']):
                    stage_errors.append((mode, n, j, 'slew_limit'))
                stages[mode][f'{n}:{j}'] = row | {'limited_area': ramp['area'], 'limited_minimum': ramp['minimum']}
    effects = {}
    for n in blocks:
        upper = substitutions['upstream', n]
        trial = substitutions['trial', n]
        for j in nodes:
            fn = lambda arguments: resample(*arguments, count, j - offset)[0]
            orig = fn(trial)
            if len(upper[0]) != len(trial[0]):
                raise ValueError('上流と試験版で口腔の格子数が異なります')
            effects[f'{n}:{j}'] = {
                name: fn(tuple(upper[i] if i == take else trial[i] for i in range(3))) - orig
                for take, name in enumerate(('grid_arcs', 'grid_areas', 'oral_bounds'))}
    return stages, effects, stage_errors


def block_inputs(data, steps, ramps, measure, start, nodes, enable_start, enable_target):
    after = start + measure['control_internal_samples']
    dt = 1 / measure['internal_sample_rate_hz']
    result = []
    trial = data['trial']
    for j in nodes:
        beginning = steps['upstream' if enable_start else 'trial'][start, j]['area']
        target = ramps['upstream' if enable_target else 'trial'][start, j]['area']
        increment = (target - beginning) * (1 / measure['control_internal_samples'])
        previous = max(trial['loads'][start]['area_floor'], beginning) * trial['cells'][start - 1, j]['length_cm']
        samples = []
        for n in range(start, after):
            beginning = max(0.0, beginning + increment)
            volume = max(trial['loads'][n]['area_floor'], beginning) * trial['cells'][n, j]['length_cm']
            samples.append((previous - volume) / dt)
            previous = volume
        result.append(samples)
    return np.asarray(result).T


def boundary_roundoff(artifacts, measure):
    """同じ ULP 幅の範囲で、1回分の丸めがブロックの終端に残ることを照合する。"""
    blocks, nodes = measure['area_focus_blocks'], measure['area_focus_nodes']
    count = measure['control_internal_samples']
    details = {}
    for mode in geometry.MODES:
        steps = read_rows(artifacts / f'{mode}-ramp-step.csv', geometry.observer.STEP_FIELDS)
        targets, _ = geometry.read_targets(artifacts / f'{mode}-ramp-target.csv',
            {(n, j) for n in measure['control_boundaries'] for j in measure['nodes'][1:]})
        details[mode] = {}
        for n in blocks:
            for node in nodes:
                start = steps[n, node]['area']
                delta = steps[n, node]['area_step']
                ulps = {math.ulp(steps[k, node]['area']) for k in range(n, n + count + 1)}
                per_sample = Fraction(start + delta) - Fraction(start) - Fraction(delta)
                discrepancy = Fraction(steps[n + count, node]['area']) - Fraction(targets[n, node]['area'])
                details[mode][f'{n}:{node}'] = {'per_sample_cm2': float(per_sample), 'boundary_cm2': float(discrepancy),
                    'match': len(ulps) == 1 and per_sample * count == discrepancy}
    return details


def analyze(study, out, prior, previous, config, gain, coefficients, proof):
    measure = study['measurement']
    start, handoff = measure['attribution_internal_samples']
    _, stop = measure['handoff_internal_samples']
    blocks, focus = measure['area_focus_blocks'], measure['area_focus_nodes']
    nodes = measure['inner_nodes']
    recording = {mode: oral.read_capture(out, mode, measure) for mode in geometry.MODES}
    shared = {}
    # 先行計測は4992・5120の追加タグを持たないため、共通時刻だけを照合する。
    for mode, data in recording.items():
        old = oral.read_capture(prior, mode, measure)
        shared[mode] = all(inlet.shared_capture(data, old).values())
        for tag in ('ramp-target', 'centerline', 'ramp-step'):
            before = (prior / f'{mode}-{tag}.csv').read_text().splitlines()
            now = (out / f'{mode}-{tag}.csv').read_text().splitlines()
            if tag != 'ramp-step':
                now = [now[0], *(row for row in now[1:] if int(row.split(',', 1)[0]) not in blocks)]
            shared[mode] &= before == now
    ramps, steps, ramp_errors = {}, {}, {}
    count = measure['control_internal_samples']
    capture_start, capture_stop = measure['comparison_internal_samples']
    for mode, data in recording.items():
        ramps[mode], _ = geometry.read_targets(out / f'{mode}-ramp-target.csv',
            {(n, j) for n in measure['control_boundaries'] for j in measure['nodes'][1:]})
        steps[mode] = geometry.terminal.read_records(out / f'{mode}-ramp-step.csv',
            ('sample', 'node', *geometry.observer.STEP_FIELDS), 2,
            {(n, j) for n in range(capture_start, capture_stop) for j in measure['nodes'][1:]})
        ramp_errors[mode] = geometry.verify_ramps(data,
            {key: row for key, row in steps[mode].items() if blocks[0] <= key[0] < blocks[-1] + count},
            ramps[mode], measure | {'comparison_internal_samples': [blocks[0], blocks[-1] + count]})
    stages, effects, errors = measure_stages(out, ramps, measure)
    upper, trial = (recording[mode] for mode in ('upstream', 'trial'))
    seed = onset.cell_values(trial, start - 1, start, nodes, onset.POLES)[0]
    native = {mode: onset.cell_values(recording[mode], start, stop, nodes, ('spill_cm3_s',))[:, :, 0]
              for mode in ('upstream', 'trial')}
    alpha = trial['loads'][start]['pole_coefficient']
    baseline = six.replay(trial, measure, False)
    with np.load(prior / 'prefix.npz', allow_pickle=False) as archive:
        prefix = dict(archive)
    tests = {'unchanged': native['trial'].copy()}
    tests['unchanged'][handoff - start:] = native['upstream'][handoff - start:]
    tests['all_nodes_block_5120'] = tests['unchanged'].copy()
    tests['all_nodes_block_5120'][5120 - start:5120 + count - start] = native['upstream'][5120 - start:5120 + count - start]
    volume_matches = {}
    for n in blocks:
        frames = slice(n - start, n + count - start)
        idx = [nodes.index(j) for j in focus]
        exact = block_inputs(recording, steps, ramps, measure, n, focus, False, False)
        both = block_inputs(recording, steps, ramps, measure, n, focus, True, True)
        volume_matches[str(n)] = {
            'trial_unchanged': load.same_bits(exact, native['trial'][frames, idx]),
            'upstream_start_and_target': load.same_bits(both, native['upstream'][frames, idx]),
        }
        for selected in ((focus[0],), (focus[1],), tuple(focus)):
            cols = [nodes.index(j) for j in selected]
            for label, enable_start, enable_target in (('start', True, False), ('target', False, True), ('both', True, True)):
                source = tests['unchanged'].copy()
                source[frames, cols] = block_inputs(recording, steps, ramps, measure, n, selected, enable_start, enable_target)
                tests[f'{n}:{"+".join(map(str, selected))}:{label}'] = source
    conditions, arrays = {}, {}
    for name, data in tests.items():
        filtered = onset.replay_poles(seed, data, alpha)
        states = {(stop - 1, node): filtered[-1, i] for i, node in enumerate(nodes)}
        row, arrays[name] = history.pcm_from_history(states, upper, trial, measure | {'history_internal_samples': [handoff, stop]},
                                                       prefix, config, gain, coefficients, baseline)
        conditions[name] = row['pcm_full_interval']
    matches = [name for name, row in conditions.items() if row['first_difference_through_focus'] is None]
    magnitudes = {field: math.hypot(*(row[field] for row in effects.values()))
                  for field in ('grid_arcs', 'grid_areas', 'oral_bounds')}
    hypotheses = {
        'resampled_area_already_differs_at_focus': all(value['area'] != stages['trial'][key]['area']
                                                       for key, value in stages['upstream'].items()),
        'slew_passes_through_focus_areas': all(row['area'] == row['limited_area'] for stage in stages.values() for row in stage.values()),
        'grid_areas_exceed_coordinate_effects': magnitudes['grid_areas'] > max(magnitudes['grid_arcs'], magnitudes['oral_bounds']),
        'both_focus_cells_recover_pcm_in_5120_block': '5120:29+34:both' in matches,
    }
    checks = {
        'ordinary_cli_and_shared_observations_match': proof == tsp.read(prior / 'pcm-digests.json') and all(shared.values())
            and all(row['bit_equal'] for row in proof.values()) and tsp.sha256(out / 'prefix.npz') == tsp.sha256(prior / 'prefix.npz'),
        'resampling_slew_and_ramps_replayed': not errors and not any(ramp_errors.values()),
        'focus_volume_speeds_replayed': all(all(result.values()) for result in volume_matches.values()),
        'previous_pcm_controls_replayed': conditions['unchanged'] == previous['conditions']['unchanged']['pcm_full_interval']
            and conditions['all_nodes_block_5120'] == previous['conditions']['block_5120']['pcm_full_interval'],
    }
    return {'checks': checks, 'hypotheses': hypotheses, 'matches': matches, 'stages': stages, 'stage_errors': errors,
            'ramp_errors': ramp_errors, 'volume_matches': volume_matches, 'isolated_grid_effects_cm2': effects,
            'isolated_grid_l2_cm2': magnitudes, 'conditions': conditions}, arrays | {
                'pcm_internal_sample': np.arange(*measure['local_internal_samples']),
                'pcm_columns': np.asarray((*six.TRAJECTORY_FIELDS, 'flow27_28', 'flow37_38'))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    return geometry.run_registered(parser.parse_args().run_id, CASE, analyze_run=analyze, prepare_run=prepare,
                                   split_run=split_observations, retained_files=PRIOR_FILES,
                                   extra_inputs=(Path(__file__).resolve(), Path(history.__file__), Path(onset.__file__),
                                       geometry.radiation.UPSTREAM / 'crates/chimera/src/math.rs',
                                       geometry.radiation.UPSTREAM / 'crates/chimera/tests/geometry_continuity.rs'))


if __name__ == '__main__':
    raise SystemExit(main())
