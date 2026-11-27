"""気道グラフの壁更新を上流、単管、状態の収支と照合する。"""

import argparse
import json
from pathlib import Path
import re
import subprocess

import numpy as np

import measure_junction as reference
import measure_uniform_tube as shared
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE_PATH = WORKSPACE / 'cases/network-tube-soft-wall.json'


def first_nonzero(values):
    indices = np.flatnonzero(values)
    return int(indices[0]) if indices.size else None


def measure(case, trace_path, upstream_path, uniform_path):
    cfg, network, observe = (case[name] for name in ('measurement', 'network', 'observe'))
    tube, = network['tubes']
    outlet, = network['radiators']
    impulse = case['impulse']
    count = cfg['sample_count']
    columns = (5 + len(observe['pressure_nodes']) + len(observe['branches'])
               + len(network['radiators']) + 3 * len(observe['wall_nodes']))
    header, trace = shared.read_trace(trace_path, count, columns)
    upstream_header, upstream = shared.read_trace(upstream_path, count, columns)
    if header != upstream_header:
        raise ValueError('上流と候補の観測列が一致しません')
    upstream_tolerance = cfg['upstream_trace_peak_relative_error_lt']
    upstream_comparisons = {
        name: shared.compare_series(values, upstream[:, index], upstream_tolerance)
        for index, (name, values) in enumerate(zip(header, trace.T, strict=True))
        if name != 'sample'
    }

    uniform_header, uniform_trace = shared.read_trace(uniform_path, count, 12)
    uniform = dict(zip(uniform_header, uniform_trace.T, strict=True))
    states = dict(zip(header, trace.T, strict=True))
    wall = tube['wall']
    wall_radiation = states['wall_radiation_flow_cm3_s']
    mouth = states[f'radiation_{outlet}_cm3_s']
    uniform_references = {
        'inlet_flow_cm3_s': uniform['inlet_flow_cm3_s'],
        'pressure_0_dyn_cm2': uniform['inlet_pressure_dyn_cm2'],
        f'pressure_{outlet}_dyn_cm2': uniform['outlet_pressure_dyn_cm2'],
        'wall_flow_0_cm3_s': uniform['inlet_wall_flow_cm3_s'],
        f'wall_flow_{outlet}_cm3_s': uniform['outlet_wall_flow_cm3_s'],
        'branch_flow_0_1_cm3_s': uniform['inlet_branch_flow_cm3_s'],
        f'branch_flow_{outlet - 1}_{outlet}_cm3_s': uniform['outlet_branch_flow_cm3_s'],
        f'radiation_{outlet}_cm3_s': uniform['radiation_flow_cm3_s'],
        'wall_radiation_flow_cm3_s': wall['radiation_fraction'] * uniform['total_wall_flow_cm3_s'],
    }
    uniform_comparisons = {
        name: shared.compare_series(states[name], expected, cfg['uniform_trace_peak_relative_error_lt'])
        for name, expected in uniform_references.items()
    }

    fs = network['sample_rate_hz']
    dx = tube['length_cm'] / len(tube['areas_cm2'])
    tolerance = cfg['balance_peak_relative_error_lt']
    volume_balances = {}
    wall_balances = {}
    for node in observe['wall_nodes']:
        area = tube['areas_cm2'][node]
        compliance = area * dx / (1.14e-3 * 35000.0**2)
        pressure = states[f'pressure_{node}_dyn_cm2']
        prior_pressure = np.r_[0.0, pressure[:-1]]
        wall_flow = states[f'wall_flow_{node}_cm3_s']
        velocity = states[f'wall_velocity_{node}_cm_s']
        prior_velocity = np.r_[0.0, velocity[:-1]]
        displacement = states[f'wall_displacement_{node}_cm']
        prior_displacement = np.r_[0.0, displacement[:-1]]
        branch_in = (states[f'branch_flow_{node - 1}_{node}_cm3_s']
                     if node != impulse['node'] else states['inlet_flow_cm3_s'])
        branch_out = states[f'branch_flow_{node}_{node + 1}_cm3_s'] if node != outlet else mouth
        volume_balances[str(node)] = shared.compare_series(
            (pressure - prior_pressure) * fs * compliance, branch_in - branch_out - wall_flow, tolerance)
        force = (wall['mass_g_cm2'] * fs * (velocity - prior_velocity)
                 + wall['resistance_dyn_s_cm3'] * (velocity + prior_velocity) / 2
                 + wall['stiffness_dyn_cm3'] * prior_displacement)
        wall_balances[str(node)] = {
            'force': shared.compare_series(force, prior_pressure, tolerance),
            'displacement': shared.compare_series((displacement - prior_displacement) * fs,
                                                  velocity, tolerance),
            'volume_flow': shared.compare_series(wall_flow, 2 * dx * np.sqrt(np.pi * area) * velocity,
                                                 tolerance),
        }

    radiation = states['radiation_flow_cm3_s']
    derivative = states['radiation_flow_derivative_cm3_s2']
    radiation_checks = {
        'components': shared.compare_series(radiation, mouth + wall_radiation, tolerance),
        'derivative': shared.compare_series(derivative, np.diff(radiation, prepend=0.0) * fs, tolerance),
    }
    first_wall, first_mouth, first_total = map(first_nonzero, (wall_radiation, mouth, radiation))
    peak = float(np.max(np.abs(derivative)))
    tail_ratio = float(np.max(np.abs(derivative[-cfg['tail_sample_count']:])) / peak) if peak else None
    return {
        'checks': {
            'upstream_time_series': all(item['status'] for item in upstream_comparisons.values()),
            'uniform_time_series': all(item['status'] for item in uniform_comparisons.values()),
            'node_volume_balance': all(item['status'] for item in volume_balances.values()),
            'wall_balances': all(item['status'] for group in wall_balances.values()
                                 for item in group.values()),
            'radiation_balance': all(item['status'] for item in radiation_checks.values()),
            'wall_radiation_onset': first_wall == first_total == cfg['expected_first_wall_radiation_sample'],
            'mouth_radiation_onset': first_mouth == cfg['expected_first_mouth_radiation_sample'],
            'tail_decay': tail_ratio is not None and tail_ratio < cfg['tail_over_peak_lt'],
        },
        'first_wall_radiation_sample': first_wall,
        'first_mouth_radiation_sample': first_mouth,
        'first_total_radiation_sample': first_total,
        'radiation_derivative_tail_over_peak': tail_ratio,
        'peak_wall_radiation_cm3_s': float(np.max(np.abs(wall_radiation))),
        'peak_mouth_radiation_cm3_s': float(np.max(np.abs(mouth))),
        'upstream_time_series': upstream_comparisons,
        'uniform_time_series': uniform_comparisons,
        'node_volume_balance': volume_balances,
        'wall_balances': wall_balances,
        'radiation_balance': radiation_checks,
    }


def checked_uniform_trace(case, manifest_path, cargo_sources):
    manifest = json.loads(manifest_path.read_text())
    uniform = json.loads(shared.SOFT_WALL_CASE.read_text())
    network, cfg = (case[key] for key in ('network', 'measurement'))
    tube, = network['tubes']
    uniform_tube = uniform['tube']
    if not (uniform['upstream_revision'] == case['upstream_revision']
            and uniform['id'] == cfg['uniform_case_id']
            and uniform_tube['sample_rate_hz'] == network['sample_rate_hz']
            and uniform_tube['length_cm'] == tube['length_cm']
            and [uniform_tube['area_cm2']] * uniform_tube['cells'] == tube['areas_cm2']
            and {**uniform['wall'], 'radiation_fraction': tube['wall']['radiation_fraction']} == tube['wall']
            and uniform['wall']['radiation_fraction'] == 0.0
            and {**uniform['impulse'], 'node': 0} == case['impulse']
            and uniform['measurement']['sample_count'] == cfg['sample_count']):
        raise ValueError('単管とグラフの形状、壁の物性、駆動または計測長が一致しません')
    prior_inputs = {item['path']: item['sha256'] for item in manifest['inputs']}
    trace_path = manifest_path.parent / 'artifacts/trace.csv'
    if (manifest['status'] != 'pass' or manifest['upstream_revision'] != case['upstream_revision']
            or any(prior_inputs.get(str(path.relative_to(WORKSPACE))) != sha256(path)
                   for path in [shared.SOFT_WALL_CASE, *cargo_sources])
            or not any(item['path'] == 'artifacts/trace.csv' and item['sha256'] == sha256(trace_path)
                       for item in manifest['outputs'])):
        raise ValueError('同じ候補ソースで通過した軟壁一様管の計測が必要です')
    return trace_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('--uniform-run', required=True)
    args = parser.parse_args()
    for run_id in (args.run_id, args.uniform_run):
        if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]*', run_id):
            parser.error('実行 ID は英数字で始め、英数字、ハイフン、アンダースコアで指定してください')
    case = json.loads(CASE_PATH.read_text())
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        raise ValueError('変更のない固定上流版が必要です')
    cargo_sources = shared.candidate_sources()
    manifest_path = WORKSPACE / 'runs' / args.uniform_run / 'manifest.json'
    uniform_trace = checked_uniform_trace(case, manifest_path, cargo_sources)
    inputs = [CASE_PATH, shared.SOFT_WALL_CASE, manifest_path, uniform_trace, reference.PROBE,
              Path(__file__).resolve(), Path(reference.__file__), Path(shared.__file__),
              WORKSPACE / 'tools/upstream_baseline.py', *cargo_sources]

    def measure_run(artifacts, execute):
        upstream_trace = reference.capture_upstream(case, artifacts, execute)
        return measure(case, artifacts / 'trace.csv', upstream_trace, uniform_trace)

    return shared.record_measurement(
        args.run_id, CASE_PATH, inputs, {'upstream_revision': revision, 'case_id': case['id'],
                                         'uniform_run_id': args.uniform_run}, measure_run)


if __name__ == '__main__':
    raise SystemExit(main())
