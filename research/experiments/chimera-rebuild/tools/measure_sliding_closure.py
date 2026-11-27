"""加圧下で移動する閉鎖と再開口を、上流と区間別の観測で比較する。"""

import argparse
import json
from pathlib import Path
import re
import subprocess

import numpy as np

import measure_junction as reference
import measure_uniform_tube as shared
from upstream_baseline import UPSTREAM, WORKSPACE


CASE = WORKSPACE / 'cases/sliding-closure.json'
UPSTREAM_TEST = ('airway_adversarial',
                 'a_realistic_sliding_closure_with_trapped_pressure_releases_without_spikes')


def area_ramps(case):
    motion = case['sliding_constriction']
    tubes = case['network']['tubes']
    tube_index = motion['tube']
    rest = np.asarray(tubes[tube_index]['areas_cm2'])
    first_node = sum(len(tube['areas_cm2']) for tube in tubes[:tube_index])
    block = motion['block_samples']
    samples = case['measurement']['sample_count']
    starts = np.arange(0, samples, block)
    ends = np.minimum(starts + block, samples)
    knot_samples, depths = np.asarray(motion['depth']).T
    depth = np.interp(ends, knot_samples, depths)
    knot_samples, centers = np.asarray(motion['center_cells']).T
    center = np.interp(ends, knot_samples, centers)
    distance = (np.arange(len(rest)) - center[:, None]) / motion['width_cells']
    targets = rest * np.clip(1.0 - depth[:, None] * np.exp(-np.square(distance)), 0.0, None)
    return [
        {'start_sample': int(start), 'sample_count': int(end - start), 'block_samples': int(end - start),
         'targets': [{'node': first_node + cell, 'area_cm2': float(area)}
                     for cell, area in enumerate(row)]}
        for start, end, row in zip(starts, ends, targets, strict=True)
    ]


def event_metrics(cfg, columns, pressures, areas):
    derivative = np.abs(columns['radiation_flow_derivative_cm3_s2'])
    metrics = {'peak_open_cell_pressure_dyn_cm2': float(
        np.max(np.abs(pressures[areas > cfg['open_cell_area_gt_cm2']])))}
    for name in ('open', 'slide', 'release'):
        lo, hi = cfg[f'{name}_peak_window_samples']
        metrics[f'peak_{name}_radiation_derivative_cm3_s2'] = float(np.max(derivative[lo + 1:hi]))
    metrics['peak_all_radiation_derivative_cm3_s2'] = float(
        np.max(derivative[cfg['open_peak_window_samples'][0] + 1:]))
    return metrics


def measure(case, artifacts, upstream_trace):
    cfg, network, observe = (case[key] for key in ('measurement', 'network', 'observe'))
    nodes = observe['area_nodes']
    count = (5 + len(observe['pressure_nodes']) + len(observe['branches'])
             + len(network['radiators']) + len(nodes) + 3 * len(observe['wall_nodes']))
    header, candidate = shared.read_trace(artifacts / 'trace.csv', cfg['sample_count'], count)
    upstream_header, explicit = shared.read_trace(upstream_trace, cfg['sample_count'], count)
    if header != upstream_header:
        raise ValueError('上流と候補の観測列が一致しません')
    data, upper = (dict(zip(header, table.T, strict=True)) for table in (candidate, explicit))
    comparisons = {name: shared.compare_series(data[name], upper[name], cfg['upstream_trace_peak_relative_error_lt'])
                   for name in data if name != 'sample'}
    pressures, upper_pressures = (np.column_stack([table[f'pressure_{node}_dyn_cm2'] for node in nodes])
                                  for table in (data, upper))
    areas, upper_areas = (np.column_stack([table[f'area_{node}_cm2'] for node in nodes])
                          for table in (data, upper))
    node_index = {node: index for index, node in enumerate(nodes)}
    candidate_metrics = event_metrics(cfg, data, pressures, areas)
    upstream_metrics = event_metrics(cfg, upper, upper_pressures, upper_areas)
    native_log = (artifacts / 'upstream-network-test.log').read_text()
    record = re.search(r'peakP (\S+) \(P \S+\), slide (\S+), release (\S+), open (\S+), out (\S+)', native_log)
    if record is None:
        raise ValueError('上流テストのピークを読み取れません')
    peak_pressure, slide, release, opened, total = map(float, record.groups())
    native_peaks = {
        'peak_open_cell_pressure_dyn_cm2': peak_pressure,
        'peak_slide_radiation_derivative_cm3_s2': slide,
        'peak_release_radiation_derivative_cm3_s2': release,
        'peak_open_radiation_derivative_cm3_s2': opened,
        'peak_all_radiation_derivative_cm3_s2': total,
    }
    native_errors = {name: abs(upstream_metrics[name] - value) for name, value in native_peaks.items()}
    native_agreement = all(
        error < (cfg['reference_printed_pressure_error_lt_dyn_cm2'] if name.endswith('dyn_cm2')
                 else cfg['reference_printed_radiation_peak_relative_error_lt'] * native_peaks[name])
        for name, error in native_errors.items())

    drive, = network['pressure_nodes']
    pressure = drive['pressure_dyn_cm2']
    open_peak = candidate_metrics['peak_open_radiation_derivative_cm3_s2']
    release_peak = candidate_metrics['peak_release_radiation_derivative_cm3_s2']
    ratio_pressure = candidate_metrics['peak_open_cell_pressure_dyn_cm2'] / pressure
    ratio_slide = candidate_metrics['peak_slide_radiation_derivative_cm3_s2'] / release_peak if release_peak else None
    ratio_release = release_peak / open_peak if open_peak else None
    hold_start, hold_end = cfg['hold_window_samples']
    behind, ahead = cfg['hold_pressure_nodes']
    behind_over_drive = float(np.mean(pressures[hold_start:hold_end, node_index[behind]]) / pressure)
    ahead_over_drive = float(np.max(np.abs(pressures[hold_start:hold_end, node_index[ahead]])) / pressure)
    markers = {(sample, node): float(areas[sample, node_index[node]])
               for sample, node in cfg['closure_positions']}
    closed_branches = 0
    maximum_closed_flow = 0.0
    for a, b in observe['branches']:
        if a not in node_index or b not in node_index:
            continue
        closed = np.minimum(areas[:, node_index[a]], areas[:, node_index[b]]) < cfg['closed_area_lt_cm2']
        states = data[f'branch_flow_{a}_{b}_cm3_s'][closed]
        closed_branches += int(states.size)
        maximum_closed_flow = float(max(maximum_closed_flow, np.max(np.abs(states), initial=0.0)))

    rest_areas = np.concatenate([tube['areas_cm2'] for tube in network['tubes']])
    reopened_error = float(np.max(np.abs(areas[cfg['reopened_sample']:] - rest_areas[nodes])))
    return {
        'checks': {
            'upstream_native_peaks': native_agreement,
            'upstream_time_series': all(item['status'] for item in comparisons.values()),
            'bounded_open_cell_pressure': ratio_pressure < cfg['peak_pressure_over_drive_lt'],
            'quiet_sliding_closure': ratio_slide is not None and ratio_slide < cfg['slide_over_release_lt'],
            'bounded_release': ratio_release is not None and ratio_release < cfg['release_over_open_lt'],
            'pressure_trapped_behind_closure': behind_over_drive > cfg['hold_behind_closure_over_drive_gt'],
            'low_pressure_downstream_of_closure': ahead_over_drive < cfg['hold_ahead_of_closure_abs_over_drive_lt'],
            'closure_positions': all(area < cfg['closed_area_lt_cm2'] for area in markers.values()),
            'closed_branches_block_flow': closed_branches > 0 and maximum_closed_flow == 0.0,
            'areas_return_to_rest': reopened_error < cfg['area_absolute_error_lt_cm2'],
        },
        'candidate_peaks': candidate_metrics,
        'upstream_probe_peaks': upstream_metrics,
        'upstream_native_printed_peaks': native_peaks,
        'upstream_native_peak_absolute_differences': native_errors,
        'open_cell_pressure_over_drive': ratio_pressure,
        'slide_radiation_peak_over_release': ratio_slide,
        'release_radiation_peak_over_open': ratio_release,
        'hold_pressure_behind_over_drive': behind_over_drive,
        'hold_max_abs_pressure_ahead_over_drive': ahead_over_drive,
        'closure_marker_areas_cm2': {f'{sample}_{node}': area for (sample, node), area in markers.items()},
        'closed_branch_samples': closed_branches,
        'closed_branch_max_abs_flow_cm3_s': maximum_closed_flow,
        'maximum_reopened_area_difference_cm2': reopened_error,
        'upstream_time_series': comparisons,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]*', args.run_id):
        parser.error('実行 ID は英数字で始め、英数字、ハイフン、アンダースコアで指定してください')
    case = json.loads(CASE.read_text())
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        raise ValueError('変更のない固定上流版が必要です')

    def measure_run(artifacts, execute):
        expanded = {**case, 'area_ramps': area_ramps(case)}
        trace = reference.capture_upstream(expanded, artifacts, execute, UPSTREAM_TEST)
        return measure(case, artifacts, trace)

    inputs = [CASE, reference.PROBE, Path(__file__).resolve(), Path(reference.__file__),
              Path(shared.__file__), WORKSPACE / 'tools/upstream_baseline.py', *shared.candidate_sources()]
    return shared.record_measurement(
        args.run_id, CASE, inputs, {'upstream_revision': revision, 'case_id': case['id']}, measure_run)


if __name__ == '__main__':
    raise SystemExit(main())
