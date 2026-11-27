"""咽頭セル7の初期面積の差を、第1制御ブロックの体積源・枝・節点へ追う。"""

import argparse
from collections import defaultdict
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

import numpy as np

import measure_csd_en001a_pharynx_cell7_source as source
import measure_tsp_fk61_node42_volume_source as volume
from measure_tsp_fk61_lip_front_terminal_branch import (
    BRANCH_INPUTS, BULK_MODULUS, branch_flow, read_records, step_wall,
)
import tsp_fk61_lip_front_radiation_observation as observe_cells
import tsp_fk61_node_volume_observation as observe_volume
import tsp_fk61_terminal_branch_observation as observe_branches


prior, tsp, radiation = source.prior, source.tsp, source.radiation
CASE = radiation.WORKSPACE / 'cases/csd-en001a-pharynx-cell7-first-block.json'
MODES = source.MODES
CONDITIONS = ('native', 'initial_only')
FILES = (*source.FILES, *(f'{name}_{condition}-block.csv' for name in MODES for condition in CONDITIONS))
GROUPS = ('volume', 'compliance', 'branches', 'walls', 'boundary')


def patch_block(root, fixed, measure, *, nodes=None, modify=None):
    if fixed:
        paths = ('crates/chimera/src/airway/network.rs',)
    else:
        paths = ('crates/vocal-core/src/airway/network.rs', 'crates/vocal-core/src/airway/network/geometry.rs')
    originals = {name: (root / name).read_text() for name in paths}
    window = measure['comparison_internal_samples']
    focus = measure['focus_node']
    if nodes is None:
        nodes = tuple(range(focus - 1, focus + 2))
    observe_cells.observe(root, fixed, window)
    if modify is not None:
        modify(root, fixed)
    observe_branches.observe(root, fixed, branch_left_indices=tuple(range(nodes[0] - 1, nodes[-1] + 1)),
                             wall_indices=nodes, compliance_indices=nodes)
    observe_volume.observe(root, fixed, window)
    return ''.join(prior.diff(text, root / name, name) for name, text in originals.items())


def split_trace(path, dest):
    headers = observe_volume.FIELDS | observe_branches.FIELDS
    tables = defaultdict(list)
    with path.open() as rows:
        for row in rows:
            tag, _, values = row.partition(',')
            if tag in headers:
                tables[tag].append(values)
            elif tag.isdecimal():
                tables['nodes'].append(row)
            else:
                raise ValueError(f'体積・気道の観測行を判別できません ({path.name})')
    (dest / 'capture-nodes.csv').write_text(''.join(tables['nodes']))
    for tag, fields in headers.items():
        (dest / f'capture-{tag}.csv').write_text(','.join(fields) + '\n' + ''.join(tables[tag]))


def read_events(path, measure, fixed, *, nodes=None):
    start, stop = measure['comparison_internal_samples']
    focus = measure['focus_node']
    if nodes is None:
        nodes = tuple(range(focus - 1, focus + 2))
    edge_left = tuple(range(nodes[0] - 1, nodes[-1] + 1))
    with TemporaryDirectory(prefix='csd-block-read-') as directory:
        scratch = Path(directory)
        split_trace(path, scratch)
        cells, geometry, sparse = volume.read_capture(scratch, 'capture', measure)
        read = lambda kind, indices, keys: read_records(
            scratch / f'capture-{kind}.csv', observe_branches.FIELDS[kind], indices, keys)
        branches = read('branch', 3, {(n, i, i+1) for n in range(start, stop) for i in edge_left})
        walls = read('wall', 2, {(n, i) for n in range(start, stop) for i in nodes})
        compliance = read('compliance', 2, {(n, i) for n in range(start, stop) for i in nodes})
    _, _, mismatches, volume_checks = volume.rebuild(measure, fixed, (cells, geometry, sparse))
    events = []
    for row, n in enumerate(range(start, stop)):
        events.append({
            'cells': [{field: float(cells[field][row, i]) for field in (
                'area_cm2', 'volume_cm3', 'spill_cm3_s', 'pole2_cm3_s', 'initial_inflow_cm3_s', 'before_wall_cm3_s',
                'old_pressure_dyn_cm2', 'inflow_cm3_s', 'wall_cm3_s', 'new_pressure_dyn_cm2')}
                | {'raw_cm3_s': sparse['raw'][n, i]} for i in nodes],
            'branches': [branches[n, i, i+1] for i in edge_left],
            'walls': [walls[n, i] for i in nodes],
            'compliance': [compliance[n, i]['value'] for i in nodes],
        })
    return events, volume_checks | {'geometry_and_poles': not mismatches}


def simulate(events, rate, fixed, *, donor=None, swaps=()):
    """外側2枝の流量を境界値として、連続する節点と内側の枝を反復する。"""
    use_all = len(swaps) == len(GROUPS)
    first = donor[0] if use_all else events[0]
    pressure = [cell['old_pressure_dyn_cm2'] for cell in first['cells']]
    walls = [(row['previous_velocity'], row['previous_displacement']) for row in first['walls']]
    memory = [{key: row[key] for key in ('previous_inertance', 'previous_flow', 'previous_momentum')}
              for row in first['branches'][1:-1]]
    dt = 1 / rate
    predictions = []
    for n, event in enumerate(events):
        trial = event if donor is None else donor[n]
        injection = (trial if 'volume' in swaps else event)['cells']
        compliance = (trial if 'compliance' in swaps else event)['compliance']
        branches = (trial if 'branches' in swaps else event)['branches'][1:-1]
        wall_inputs = (trial if 'walls' in swaps else event)['walls']
        boundary = (trial if 'boundary' in swaps else event)['branches']
        flows = [boundary[0]['flow']]
        for i, (base, chosen) in enumerate(zip(event['branches'][1:-1], branches, strict=True)):
            branch = base | {key: chosen[key] for key in BRANCH_INPUTS if key != 'noise_pressure'} | memory[i]
            branch |= {'left_pressure': pressure[i], 'right_pressure': pressure[i+1]}
            if use_all:
                branch['noise_pressure'] = chosen['noise_pressure']
            flow = branch_flow(branch, rate, fixed)
            flows.append(flow)
            l = branch['inertance']
            memory[i] = {'previous_inertance': l, 'previous_flow': flow, 'previous_momentum': l * flow}
        flows.append(boundary[-1]['flow'])
        rows = []
        for i, (wall_input, (velocity, displacement)) in enumerate(zip(wall_inputs, walls, strict=True)):
            wall = step_wall(wall_input | {'previous_velocity': velocity, 'previous_displacement': displacement,
                                          'pressure': pressure[i]}, rate, fixed)
            walls[i] = (wall['velocity'], wall['displacement'])
            before_wall = (injection[i]['initial_inflow_cm3_s'] + flows[i]) - flows[i+1]
            inflow = before_wall - wall['flow']
            pressure[i] += (dt / compliance[i]) * inflow
            rows.append({'before_wall': before_wall, 'inflow': inflow, 'pressure': pressure[i], 'wall': wall})
        predictions.append({'rows': rows, 'inner': flows[1:-1]})
    return predictions


def validate_replay(events, modeled, rate, fixed, *, compliance_overrides=None):
    overrides = {} if compliance_overrides is None else compliance_overrides
    for n, (row, result) in enumerate(zip(events, modeled, strict=True)):
        branches = row['branches']
        values = [entry['flow'] for entry in branches]
        if result['inner'] != values[1:-1] or values != [branch_flow(entry, rate, fixed) for entry in branches]:
            return False
        nodes = zip(row['cells'], row['walls'], row['compliance'], result['rows'], strict=True)
        for i, (cell, wall, c, solved) in enumerate(nodes):
            if (c != overrides.get((n, i), cell['volume_cm3'] / BULK_MODULUS) or
                    cell['wall_cm3_s'] != wall['flow'] or
                    solved['before_wall'] != cell['before_wall_cm3_s'] or solved['inflow'] != cell['inflow_cm3_s']
                    or solved['pressure'] != cell['new_pressure_dyn_cm2']
                    or solved['wall'] != {key: wall[key] for key in ('velocity', 'displacement', 'flow')}):
                return False
    return True


def differences(old, new):
    increments = [(i, b-a) for i, (a, b) in enumerate(zip(old, new, strict=True)) if a != b]
    return {'first': increments[0][0] if increments else None, 'count': len(increments),
            'peak_absolute': max((abs(x) for _, x in increments), default=0.0)}


def compare(a, b):
    middle = {key: differences([row['cells'][1][key] for row in a], [row['cells'][1][key] for row in b])
              for key in ('volume_cm3', 'raw_cm3_s', 'spill_cm3_s', 'pole2_cm3_s', 'old_pressure_dyn_cm2',
                          'before_wall_cm3_s', 'inflow_cm3_s', 'wall_cm3_s', 'new_pressure_dyn_cm2')}
    middle['compliance'] = differences([row['compliance'][1] for row in a], [row['compliance'][1] for row in b])
    edges = {key: {field: differences([row['branches'][i][field] for row in a], [row['branches'][i][field] for row in b])
                   for field in ('inertance', 'resistance', 'forward_loss', 'reverse_loss', 'noise_pressure', 'flow')}
             for i, key in ((1, 'left'), (2, 'right'))}
    return {'cell': middle, 'edges': edges}


def intervention(a, b, rate, fixed):
    native, donor = ([row['cells'][1]['new_pressure_dyn_cm2'] for row in event] for event in (a, b))
    baseline = differences(donor, native)
    trials = {}
    for fields in (*((key,) for key in GROUPS), GROUPS):
        trial = simulate(a, rate, fixed, donor=b, swaps=fields)
        pressure = [row['rows'][1]['pressure'] for row in trial]
        residual = differences(donor, pressure)
        n = baseline['first']
        trials['+'.join(fields)] = {
            'residual_to_donor': residual,
            'residual_at_first_pressure_difference_dyn_cm2': pressure[n] - donor[n] if n is not None else None,
            'all_nodes_and_branches_match_donor': validate_replay(b, trial, rate, fixed),
        }
    return trials


def analyze(study, out, reference):
    m = study['measurement']
    rate = m['internal_sample_rate_hz']
    baseline = tsp.read(tsp.verified_path(reference, 'artifacts/pcm-digests.json'))
    proof = tsp.read(out / 'pcm-digests.json')
    archives = tsp.read(tsp.verified_path(reference, 'artifacts/observations.json'))
    snapshots = tsp.read(out / 'observations.json')
    measured = {}
    checks = {}
    with np.load(out / 'pcm.npz', allow_pickle=False) as pcm:
        for name in MODES:
            for condition in CONDITIONS:
                key = f'{name}_{condition}'
                held = proof[name][condition]
                checks[f'{key}_pcm_plan_and_short_observations'] = (
                    held == baseline[name][condition] and held['pcm'] == source.lip.pcm_digest(pcm[key])
                    and len(pcm[key]) == m['frames'] and snapshots[name][condition] == archives[name][condition])
                events, volume_checks = read_events(out / f'{key}-block.csv', m, name == 'upstream')
                measured[key] = events
                checks[f'{key}_volume_routing_replayed'] = all(volume_checks.values())
                checks[f'{key}_local_input_is_filtered_volume'] = all(
                    cell['initial_inflow_cm3_s'] == cell['pole2_cm3_s'] for event in events for cell in event['cells'])
                checks[f'{key}_local_pressure_walls_and_branches_replayed'] = validate_replay(
                    events, simulate(events, rate, name == 'upstream'), rate, name == 'upstream')
    sides = {}
    for name in MODES:
        a, b = (measured[f'{name}_{condition}'] for condition in CONDITIONS)
        delta = compare(a, b)
        swaps = {'native_receives_initial_only': intervention(a, b, rate, name == 'upstream'),
                 'initial_only_receives_native': intervention(b, a, rate, name == 'upstream')}
        checks[f'{name}_full_local_exchanges_replayed'] = all(
            row['+'.join(GROUPS)]['all_nodes_and_branches_match_donor'] for row in swaps.values())
        cell = delta['cell']
        forecast = m['raw_volume_prediction'][name]
        pressure_start = cell['new_pressure_dyn_cm2']['first']
        sides[name] = {'hypotheses': {
            'raw_volume_matches_first_block_prediction': all(cell['raw_cm3_s'][key] == value for key, value in forecast.items()),
            'cell_compliance_differs_at_zero': cell['compliance']['first'] == 0,
            'local_pressure_differs_before_volume_source': pressure_start is not None
                and cell['raw_cm3_s']['first'] is not None and pressure_start < cell['raw_cm3_s']['first'],
        }, 'difference': delta, 'swaps': swaps,
            'earliest_pressure_observed': [
                {key: b[n]['cells'][1][key] - a[n]['cells'][1][key]
                 for key in ('new_pressure_dyn_cm2', 'raw_cm3_s', 'pole2_cm3_s', 'inflow_cm3_s')}
                for n in range(4)]}
    return {'checks': checks, 'sides': sides}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    ws, upper = radiation.WORKSPACE, radiation.UPSTREAM
    study = tsp.read(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=upper, text=True).strip()
    if revision != study['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=upper):
        parser.error('変更のない固定上流版が必要です')
    if os.environ.get('CHIMERA_RUN_STORAGE') != 'rtl9210b':
        parser.error('試験ビルドにCHIMERA_RUN_STORAGE=rtl9210bを指定してください')
    reference, centerline, render = (tsp.open_run(study[key], revision) for key in ('cell_source', 'centerline', 'render'))
    spec = tsp.verified_path(render, 'artifacts/candidate-short-128.json')
    inputs = [CASE, Path(__file__).resolve(), spec, source.song.PROBE, source.geometry.observer.SNAPSHOT,
              *(Path(m.__file__) for m in (source, source.centerline, source.geometry, source.load, source.area,
                                         source.geometry.center, source.geometry.observer, source.load.observer,
                                         volume, volume.terminal, observe_cells, observe_branches, observe_volume)),
              *(Path(fn.__code__.co_filename) for fn in (volume.terminal.solve_branch, volume.terminal.wall_values)),
              source.load.observer.UPPER_PATCH, source.load.observer.LOCAL_PATCH,
              *source.geometry.CANDIDATE_TEST_CASES, *prior.prefix.capture_dependencies(),
              *(upper / name for name in source.geometry.UPPER_GEOMETRY),
              *(upper / 'crates/chimera/tests' / name for name in
                ('golden_geometry.rs', 'airway_adversarial.rs', 'common/mod.rs', 'golden/geometry.json')),
              *(run[0] / 'manifest.json' for run in (reference, centerline, render)),
              *(tsp.verified_path(run, f'artifacts/{name}') for run, names in (
                  (reference, ('observations.json', 'pcm-digests.json')), (centerline, ('observations.json',)))
                for name in names)]

    def measure(out, execute):
        source.capture(study, spec, centerline, out, execute,
                       block_observer=lambda root, fixed: patch_block(root, fixed, study['measurement']))
        return analyze(study, out, reference)

    details = {'case_id': study['id'], 'case_revision': study['revision'], 'upstream_revision': revision}
    return radiation.record_measurement(args.run_id, CASE, inputs, details, measure, command=None, input_root=ws.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
