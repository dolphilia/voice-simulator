"""口腔の中心線と前制御ブロックから、体積流量の平滑履歴を追う。"""

import argparse
import csv
import math
from pathlib import Path

import numpy as np

import measure_tsp_fk61_control5632_oral_geometry as geometry


inlet, terminal, tsp = geometry.inlet, geometry.terminal, geometry.tsp
oral, six, load = inlet.oral, inlet.six, inlet.load
CASE = geometry.radiation.WORKSPACE / 'cases/tsp-fk61-control5504-oral-history.json'
GRID_FIELDS = ('x_cm', 'y_cm', 'arc_cm', 'region', 'junction')
GROUPS = ('filter_seed', 'area', 'start_length', 'lip_arc', 'junction_arc')
PRIOR_FILES = geometry.SAVED_FILES[:-1]
SAVED_FILES = (*PRIOR_FILES, *(f'{mode}-centerline.csv' for mode in geometry.MODES), 'trajectories.npz')


def prepare(root, fixed, window, execute, *, measure):
    source = geometry.observer.prepare(root, fixed, window, execute, measure=measure)
    insert = geometry.observer.insert_before
    if fixed:
        airway = root / 'crates/chimera/src/voice/human_airway.rs'
        anchor = '        for i in 0..self.n_or {\n            self.net.research_oral_ramp("ramp-target"'
        grid = '''        for (index, ray) in f.grid.iter().enumerate() {
            self.net.research_oral_ramp("centerline", sample, index,
                &[ray.mid.x, ray.mid.y, ray.s, ray.region as f64,
                    u8::from(ray.s == f.pharynx_length).into()]);
        }
'''
    else:
        tract = root / 'crates/vocal-core/src/airway/tract_control.rs'
        insert(tract, '    pub fn body_scale(&self) -> f64 {', '''    pub(crate) fn research_area_samples(&self) -> &[AreaSample] {
        &self.area_samples
    }

''')
        airway = root / 'crates/vocal-core/src/airway/human.rs'
        anchor = '        for node in tube_targets[1].0.nodes.clone() {\n            let [area, minimum]'
        grid = '''        for (index, area_sample) in targets.research_area_samples().iter().enumerate() {
            let ray = area_sample.contact.ray;
            self.network.research_oral_ramp("centerline", sample, index,
                &[ray.mid.x, ray.mid.y, area_sample.s_cm, ray.region as u8 as f64,
                    u8::from(area_sample.s_cm == targets.raw.pharynx.length_cm).into()]);
        }
'''
    insert(airway, anchor, grid)
    return source


def split_observations(out, mode):
    geometry.split_observations(out, mode, geometry.RAMP_FIELDS | {'centerline': GRID_FIELDS})


def read_centerlines(path, boundaries):
    frames = {}
    with path.open(newline='') as file:
        reader = csv.reader(file)
        if tuple(next(reader)) != ('sample', 'node', *GRID_FIELDS):
            raise ValueError(f'中心線の列が異なります ({path.name})')
        for sample, index, *values in reader:
            frame = frames.setdefault(int(sample), [])
            if index == '0':
                # 接触補正で再計算された場合は最後の中心線を使う。
                frame.clear()
            values = tuple(map(float, values))
            if int(index) != len(frame) or len(values) != len(GRID_FIELDS) or not all(map(math.isfinite, values)):
                raise ValueError(f'中心線の順序または値が異なります ({path.name}, {sample}, {index})')
            frame.append(values)
    if frames.keys() != set(boundaries) or any(sum(ray[-1] == 1 for ray in frame) != 1 for frame in frames.values()):
        raise ValueError(f'中心線または咽頭端の欠測があります ({path.name})')
    return frames


def arc_report(lines, targets, measure):
    report = {}
    errors = []
    node = measure['focus_node']
    for n in measure['control_boundaries']:
        endpoints = {}
        shape = {}
        for mode, frames in lines.items():
            frame = frames[n]
            split = next(i for i, row in enumerate(frame) if row[-1] == 1)
            points = [(x, y) for x, y, *_ in frame]
            measured = [row[2] for row in frame]
            start = measured[0]
            predicted = [start]
            for a, b in zip(points, points[1:]):
                predicted.append(predicted[-1] + math.dist(a, b))
            residual = max(abs(a - b) for a, b in zip(predicted, measured, strict=True))
            lip, junction = measured[-1], measured[split]
            target = targets[mode][n, node]
            endpoints[mode] = {'lip_cm': lip, 'junction_cm': junction, 'split_index': split, 'grid_points': len(frame),
                               'oral_cm': lip - junction, 'arc_residual_cm': residual}
            if residual > measure['arc_length_tolerance_cm'] or lip - junction != target['anatomical_length']:
                errors.append((n, mode, 'arc_length'))
            if target['anatomical_length'] != target['simulation_length']:
                errors.append((n, mode, 'stability_stretch'))
            shape[mode] = points, measured, [row[3] for row in frame]
        ref, trial = endpoints['upstream'], endpoints['trial']
        a_points, a_arc, a_regions = shape['upstream']
        b_points, b_arc, b_regions = shape['trial']
        comparison = None
        if a_regions == b_regions and ref['split_index'] == trial['split_index']:
            point_first = next((i for i, (a, b) in enumerate(zip(a_points, b_points, strict=True)) if a != b), None)
            arc_first = next((i for i, (a, b) in enumerate(zip(a_arc, b_arc, strict=True)) if a != b), None)
            comparison = {'first_midpoint_difference': point_first, 'first_arc_difference': arc_first}
        report[str(n)] = {'points': endpoints, 'aligned_grid': comparison,
                          'lip_delta_cm': ref['lip_cm'] - trial['lip_cm'],
                          'junction_delta_cm': ref['junction_cm'] - trial['junction_cm'],
                          'oral_delta_cm': ref['oral_cm'] - trial['oral_cm']}
    return report, errors


def history_series(data, steps, endpoints, measure, groups):
    start, stop = measure['history_internal_samples']
    upper, trial = (data[mode] for mode in ('upstream', 'trial'))
    nodes = measure['inner_nodes']
    state = upper if 'filter_seed' in groups else trial
    area_data = upper if 'area' in groups else trial
    length_start_mode = 'upstream' if 'start_length' in groups else 'trial'
    terms = endpoints[str(start)]['points']
    lip = terms['upstream' if 'lip_arc' in groups else 'trial']['lip_cm']
    junction = terms['upstream' if 'junction_arc' in groups else 'trial']['junction_cm']
    target = (lip - junction) / (len(measure['nodes']) - 1)
    mixed = dict(trial['cells'])
    for node in nodes:
        current = steps[length_start_mode][start, node]['length']
        increment = (target - current) * (1 / measure['control_internal_samples'])
        for n in range(start - 1, stop):
            if n >= start:
                current += increment
            row = area_data['cells'][n, node]
            mixed[n, node] = row | {'length_cm': current}
    paired = trial | {'cells': mixed}
    source = geometry.source_series({'trial': paired}, trial, state, nodes,
                                    measure | {'local_internal_samples': [start, stop]}, (), fixed=False)
    return source


def pcm_from_history(source, upper, trial, measure, prefix, config, gain, coefficients, baseline):
    n = measure['history_internal_samples'][1] - 1
    nodes = measure['inner_nodes']
    cells = trial['cells'] | {(n, j): trial['cells'][n, j] |
                             dict(zip(('pole1_cm3_s', 'pole2_cm3_s'), source[n, j][-2:], strict=True))
                             for j in nodes}
    filtered = geometry.source_series({'upstream': upper, 'trial': trial}, trial, trial | {'cells': cells}, nodes,
                                      measure, geometry.GEOMETRIES[-1], fixed=False)
    cells = trial['cells'] | {key: trial['cells'][key] | {'initial_inflow_cm3_s': row[-1]}
                              for key, row in filtered.items()}
    trajectory = six.replay(trial | {'cells': cells}, measure, False, reference=upper, groups=('upstream_boundary',))
    return inlet.condition(trajectory, baseline, measure, prefix, config, gain, coefficients)


def analytic_seed_control(trial, upper, measure, baseline, seed_only):
    start, stop = measure['history_internal_samples']
    coefficient = trial['loads'][start]['pole_coefficient']
    if any(trial['loads'][n]['pole_coefficient'] != coefficient for n in range(start, stop)):
        raise ValueError('平滑係数が一定という対照の条件を満たしません')
    decay = (1 - coefficient) ** (stop - start)
    errors = []
    for node in measure['inner_nodes']:
        before = (start - 1, node)
        end = (stop - 1, node)
        d1, d2 = (upper['cells'][before][key] - trial['cells'][before][key] for key in ('pole1_cm3_s', 'pole2_cm3_s'))
        expected = (decay * d1, decay * (d2 + (stop - start) * coefficient * d1))
        measured = tuple(a - b for a, b in zip(seed_only[end][-2:], baseline[end][-2:], strict=True))
        errors.extend(abs(a - b) for a, b in zip(expected, measured, strict=True))
    return max(errors)


def analyze(study, out, prior, previous, config, gain, coefficients, proof):
    measure = study['measurement']
    first, stop = measure['comparison_internal_samples']
    start, handoff = measure['history_internal_samples']
    nodes = measure['nodes'][1:]
    focus = measure['focus_node']
    native = {mode: oral.read_capture(out, mode, measure) for mode in geometry.MODES}
    old_measure = measure | {'comparison_internal_samples': [5630, stop]}
    steps, targets, lines, shared, ramp_errors, native_errors = {}, {}, {}, {}, {}, {}
    for mode, data in native.items():
        target_path = out / f'{mode}-ramp-target.csv'
        step_path = out / f'{mode}-ramp-step.csv'
        targets[mode], _ = geometry.read_targets(
            target_path, {(n, j) for n in measure['control_boundaries'] for j in nodes})
        steps[mode] = terminal.read_records(step_path, ('sample', 'node', *geometry.observer.STEP_FIELDS), 2,
                                            {(n, j) for n in range(first, stop) for j in nodes})
        lines[mode] = read_centerlines(out / f'{mode}-centerline.csv', measure['control_boundaries'])
        past = oral.read_capture(prior, mode, old_measure)
        old_targets, _ = geometry.read_targets(prior / target_path.name, {(n, j) for n in (5632, 5760) for j in nodes})
        old_steps = terminal.read_records(prior / step_path.name, ('sample', 'node', *geometry.observer.STEP_FIELDS), 2,
                                          {(n, j) for n in range(5630, stop) for j in nodes})
        shared[mode] = all(inlet.shared_capture(data, past).values()) and all(
            targets[mode][key] == row for key, row in old_targets.items()) and all(
            steps[mode][key] == row for key, row in old_steps.items())
        ramp_errors[mode] = geometry.verify_ramps(data, steps[mode], targets[mode], measure)
        native_sources = geometry.source_series({'trial': data}, data, data, nodes,
                                                measure | {'local_internal_samples': [start, stop]},
                                                (), fixed=(mode == 'upstream'))
        native_errors[mode] = geometry.source_checks(data, native_sources)
    endpoints, arc_errors = arc_report(lines, targets, measure)
    upper, trial = (native[mode] for mode in ('upstream', 'trial'))
    with np.load(out / 'prefix.npz', allow_pickle=False) as archive:
        prefix = dict(archive)
    baseline = six.replay(trial, measure, False)
    seed = {group: history_series(native, steps, endpoints, measure, group) for group in load.subsets(GROUPS)}
    outputs, arrays = {}, {}
    history_keys = tuple((n, j) for n in range(start, handoff) for j in measure['inner_nodes'])
    for groups, source in seed.items():
        label = '+'.join(groups) or 'unchanged'
        states = np.asarray([source[handoff - 1, j][-2:] for j in measure['inner_nodes']])
        shift = [states[i, 1] - seed[()][handoff - 1, j][-1] for i, j in enumerate(measure['inner_nodes'])]
        row, arrays[label] = pcm_from_history(source, upper, trial, measure, prefix, config, gain, coefficients, baseline)
        arrays[f'history_{label}'] = np.asarray([source[key] for key in history_keys]).reshape(
            handoff - start, len(measure['inner_nodes']), 4)
        outputs[label] = {'second_pole_delta_l2_cm3_s': math.hypot(*shift), 'end_poles': states.tolist(), **row}
    analytic_error = analytic_seed_control(trial, upper, measure, seed[()], seed[('filter_seed',)])
    upstream_residual = max(abs(seed[GROUPS][handoff - 1, j][i] - upper['cells'][handoff - 1, j][key])
                            for j in measure['inner_nodes'] for i, key in enumerate(('pole1_cm3_s', 'pole2_cm3_s'), 2))
    length_end = upper['cells'][handoff - 1, focus]['length_cm'] - trial['cells'][handoff - 1, focus]['length_cm']
    length_goal = targets['upstream'][start, focus]['length'] - targets['trial'][start, focus]['length']
    base_case = previous['conditions']['nodes28_37:area+length:upstream']['pcm_full_interval']
    prior_full = geometry.filter_initial_state_control(
        study, out, prior, config, gain, coefficients)['trial:upstream']
    full_case = outputs['+'.join(GROUPS)]['pcm_full_interval']
    matches = [name for name, output in outputs.items() if output['pcm_full_interval']['first_difference_through_focus'] is None]
    controls = {
        'lip_arc_exceeds_split_arc_at_5504': abs(endpoints[str(start)]['lip_delta_cm'])
            > abs(endpoints[str(start)]['junction_delta_cm']),
        'summation_amplifies_5504_endpoint_difference': abs(length_end) > abs(length_goal),
        'history_geometry_exceeds_seed_at_5631': outputs['+'.join(GROUPS[1:])]['second_pole_delta_l2_cm3_s']
            > outputs['filter_seed']['second_pole_delta_l2_cm3_s'],
        'native_upstream_history_recovers_focus_pcm': '+'.join(GROUPS) in matches,
    }
    checks = {
        'ordinary_cli_and_shared_observations_match': proof == tsp.read(prior / 'pcm-digests.json')
            and all(row['bit_equal'] for row in proof.values()) and all(shared.values())
            and tsp.sha256(out / 'prefix.npz') == tsp.sha256(prior / 'prefix.npz'),
        'grid_arc_lengths_and_native_ramps_replayed': not arc_errors and not any(ramp_errors.values()),
        'native_volume_sources_and_analytic_seed_decay_match': not any(native_errors.values())
            and analytic_error <= measure['linear_filter_tolerance_cm3_s'],
        'registered_histories_and_pcm_controls_match': len(outputs) == 2 ** len(GROUPS)
            and not geometry.source_checks(trial, seed[()]) and upstream_residual <= measure['linear_filter_tolerance_cm3_s']
            and outputs['unchanged']['pcm_full_interval'] == base_case
            and all(full_case[key] == prior_full[key] for key in ('pcm', 'first_difference_through_focus')),
    }
    return {
        'checks': checks, 'hypotheses': controls, 'matches': matches, 'endpoints': endpoints,
        'ramp_errors': ramp_errors, 'arc_errors': arc_errors, 'native_errors': native_errors,
        'analytic_seed_residual_cm3_s': analytic_error, 'upstream_pole_residual_cm3_s': upstream_residual,
        'cell_length_target_delta_cm': length_goal, 'cell_length_end_delta_cm': length_end,
        'conditions': outputs,
    }, arrays | {'internal_sample': np.arange(handoff, stop),
                 'columns': np.asarray((*six.TRAJECTORY_FIELDS, 'flow27_28', 'flow37_38')),
                 'history_internal_sample': np.arange(start, handoff), 'history_nodes': np.asarray(measure['inner_nodes']),
                 'history_columns': np.asarray(('volume_cm3', 'raw_cm3_s', 'pole1_cm3_s', 'pole2_cm3_s'))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    return geometry.run_registered(parser.parse_args().run_id, CASE, analyze_run=analyze, prepare_run=prepare,
                                   split_run=split_observations, retained_files=PRIOR_FILES,
                                   extra_inputs=(Path(__file__).resolve(),
                                       geometry.radiation.UPSTREAM / 'crates/chimera/src/anatomy/geom.rs',
                                       geometry.radiation.UPSTREAM / 'crates/chimera/tests/geometry_continuity.rs'))


if __name__ == '__main__':
    raise SystemExit(main())
