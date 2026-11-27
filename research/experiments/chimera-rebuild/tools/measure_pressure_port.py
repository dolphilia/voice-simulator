"""固定圧力で駆動した狭窄の時系列と定常流量を比較する。"""

import argparse
from copy import deepcopy
import json
from pathlib import Path
import re
import subprocess

import numpy as np

import measure_junction as reference
import measure_uniform_tube as shared
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


def steady_elements(case):
    """観測系列を使わず、最終の断面から正流方向の損失則を計算する。"""
    rho, mu = 1.14e-3, 1.86e-4
    network = deepcopy(case['network'])
    tube = network['tubes'][0]
    goal, = case['area_ramps'][0]['targets']
    node = goal['node']
    tube['areas_cm2'][node] = goal['area_cm2']
    areas, edges, _, resistance, _, _ = reference.elements(network)
    minimums = areas.copy()
    minimums[node] = goal['minimum_area_cm2']
    loss = {}
    for (a, b), linear in zip(edges, resistance):
        expansion = max(0, 1 / minimums[a] - 1 / areas[b])
        contraction = max(0, 1 / minimums[b] - 1 / areas[a])
        loss[a, b] = (float(linear), float(rho / 2 * (expansion**2 + 0.1 * contraction**2)))

    port, = network['ports']
    a, b = port['nodes']
    area, length = port['area_cm2'], port['length_cm']
    width = port.get('slit_width_cm', 0.0)
    if width > 0:
        linear = 12 * mu * length * width**2 / area**3
    else:
        linear = np.sqrt(rho * mu * np.pi * 700) * 2 * np.sqrt(np.pi * area) * length / area**2
    kinetic = rho / 2 * (port['entrance_loss'] / area**2
                         + port['expansion_loss'] * max(0, 1 / area - 1 / areas[b])**2)
    loss[a, b] = (float(linear + port.get('extra_resistance', 0.0)), float(kinetic))
    return loss


def measure(case, artifacts, reference_path, full_result):
    cfg, observe, network = (case[key] for key in ('measurement', 'observe', 'network'))
    count, tail_count = cfg['sample_count'], cfg['tail_sample_count']
    columns = (4 + len(observe['pressure_nodes']) + len(observe['branches'])
               + len(network['radiators']) + len(observe['area_nodes'])
               + len(observe['minimum_area_nodes']))
    header, candidate = shared.read_trace(artifacts / 'trace.csv', count, columns)
    reference_header, upstream = shared.read_trace(reference_path, count, columns)
    if reference_header != header:
        raise ValueError('上流と候補の観測列が一致しません')
    comparisons = {
        name: shared.compare_series(candidate[:, i], upstream[:, i],
                                    cfg['upstream_series_peak_relative_error_lt'])
        for i, name in enumerate(header) if name != 'sample'
    }

    tail = dict(zip(header, candidate[-tail_count:].T))
    node = cfg['constriction_node']
    flow_key = f'branch_flow_{node}_{node + 1}_cm3_s'
    measured_flow = float(np.mean(tail[flow_key]))
    upstream_flow = float(np.mean(upstream[-tail_count:, header.index(flow_key)]))
    drive, = network['pressure_nodes']
    port, = network['ports']
    drive_node = port['nodes'][0]
    radiator, = network['radiators']
    pressure = drive['pressure_dyn_cm2']
    goal, = case['area_ramps'][0]['targets']
    bernoulli = goal['minimum_area_cm2'] * np.sqrt(2 * pressure / 1.14e-3)
    losses = steady_elements(case)
    total_resistance = sum(linear for linear, _ in losses.values())
    total_kinetic = sum(kinetic for _, kinetic in losses.values())
    dc_flow = 2 * pressure / (total_resistance
                              + np.sqrt(total_resistance**2 + 4 * total_kinetic * pressure))

    branch_flow = {(a, b): float(np.mean(tail[f'branch_flow_{a}_{b}_cm3_s']))
                   for a, b in observe['branches']}
    radiation = float(np.mean(tail[f'radiation_{radiator}_cm3_s']))
    spread = max(abs(value - measured_flow)
                 for value in [*branch_flow.values(), radiation]) / dc_flow
    mean_pressure = {node: float(np.mean(tail[f'pressure_{node}_dyn_cm2']))
                     for node in observe['pressure_nodes']}
    total_drop = mean_pressure[drive_node] - mean_pressure[radiator]
    loss_at_flow = total_resistance * measured_flow + total_kinetic * measured_flow**2
    drop_error = abs(loss_at_flow - total_drop) / pressure
    local_drops = {}
    for (a, b), flow in branch_flow.items():
        if a not in mean_pressure or b not in mean_pressure:
            continue
        linear, kinetic = losses[a, b]
        actual = mean_pressure[a] - mean_pressure[b]
        predicted = linear * flow + kinetic * flow**2
        local_drops[f'{a}_{b}'] = {
            'measured_dyn_cm2': actual,
            'predicted_dyn_cm2': predicted,
            'error_over_drive': abs(actual - predicted) / pressure,
        }
    actual_area = float(tail[f'area_{node}_cm2'][-1])
    actual_minimum = float(tail[f'minimum_area_{node}_cm2'][-1])
    equilibrium_error = abs(measured_flow - dc_flow) / dc_flow
    bernoulli_error = abs(measured_flow - bernoulli) / bernoulli
    checks = {
        'fixed_pressure': bool(np.all(tail[f'pressure_{drive_node}_dyn_cm2'] == pressure)),
        'terminal_mean_area': abs(actual_area - goal['area_cm2']) < cfg['terminal_area_absolute_error_lt_cm2'],
        'terminal_minimum_area': abs(actual_minimum - goal['minimum_area_cm2']) < cfg['terminal_area_absolute_error_lt_cm2'],
        'bernoulli': bool(bernoulli_error < cfg['bernoulli_relative_error_lt']),
        'steady_equilibrium': bool(equilibrium_error < cfg['steady_equilibrium_relative_error_lt']),
        'steady_flow_spread': bool(spread < cfg['steady_flow_spread_relative_lt']),
        'steady_pressure_balance': drop_error < cfg['steady_pressure_balance_relative_error_lt'],
        'local_pressure_balance': all(drop['error_over_drive'] < cfg['steady_pressure_balance_relative_error_lt']
                                      for drop in local_drops.values()),
        'upstream_time_series': all(comparison['status'] for comparison in comparisons.values()),
    }
    result = {
        'checks': checks,
        'tail_samples': [count - tail_count, count - 1],
        'length_fraction': cfg['length_fraction'],
        'terminal_area_cm2': actual_area,
        'terminal_minimum_area_cm2': actual_minimum,
        'measured_flow_cm3_s': measured_flow,
        'upstream_flow_cm3_s': upstream_flow,
        'bernoulli_flow_cm3_s': float(bernoulli),
        'bernoulli_relative_error': float(bernoulli_error),
        'steady_equilibrium_cm3_s': float(dc_flow),
        'steady_equilibrium_relative_error': float(equilibrium_error),
        'steady_flow_spread_relative': float(spread),
        'steady_pressure_balance_relative_error': drop_error,
        'radiator_pressure_dyn_cm2': mean_pressure[radiator],
        'local_pressure_balance': local_drops,
        'upstream_time_series': comparisons,
    }
    if full_result is not None:
        increase = measured_flow - full_result['measured_flow_cm3_s']
        checks['shorter_constriction_increases_flow'] = increase >= cfg['minimum_flow_increase_cm3_s']
        result['flow_increase_over_full_cm3_s'] = increase
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('case', choices=['steady-constriction-full', 'steady-constriction-quarter'])
    parser.add_argument('--full-run')
    args = parser.parse_args()
    for run_id in filter(None, [args.run_id, args.full_run]):
        if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]*', run_id):
            parser.error('実行 ID は英数字で始め、英数字、ハイフン、アンダースコアで指定してください')
    if bool(args.full_run) != (args.case == 'steady-constriction-quarter'):
        parser.error('1/4セルの計測には1セル条件の通過済み実行を --full-run で指定してください')

    case_path = WORKSPACE / 'cases' / (args.case + '.json')
    case = json.loads(case_path.read_text())
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        raise ValueError('変更のない固定上流版が必要です')
    sources = [reference.PROBE, Path(__file__).resolve(), Path(reference.__file__),
               Path(shared.__file__), WORKSPACE / 'tools/upstream_baseline.py', *shared.candidate_sources()]
    inputs = [case_path, *sources]
    details = {'upstream_revision': revision, 'case_id': case['id']}
    full_result = None
    if args.full_run:
        full_run = WORKSPACE / 'runs' / args.full_run
        manifest_path, summary_path = (full_run / name for name in ('manifest.json', 'summary.json'))
        manifest = json.loads(manifest_path.read_text())
        hashes = {item['path']: item['sha256'] for item in manifest['inputs']}
        if (manifest['status'] != 'pass' or manifest['case_id'] != 'steady-constriction-full'
                or manifest['upstream_revision'] != revision
                or any(hashes.get(str(path.relative_to(WORKSPACE))) != sha256(path)
                       for path in [WORKSPACE / 'cases/steady-constriction-full.json', *sources])
                or not any(item['path'] == 'summary.json' and item['sha256'] == sha256(summary_path)
                           for item in manifest['outputs'])):
            raise ValueError('同じ実装・計測コード・上流版で通過した1セル条件が必要です')
        full_result = json.loads(summary_path.read_text())
        inputs.extend([manifest_path, summary_path])
        details['full_run'] = args.full_run

    def measure_run(artifacts, execute):
        return measure(case, artifacts, reference.capture_upstream(case, artifacts, execute), full_result)

    return shared.record_measurement(args.run_id, case_path, inputs, details, measure_run)


if __name__ == '__main__':
    raise SystemExit(main())
