"""Chirp cascadeの押鍵直後に、くちばしの枝・節点・放射負荷を照合する。"""

import argparse
import csv
import math
from pathlib import Path
import subprocess
import sys

import numpy as np

from measure_csd_envelope_timing import verified_file
from measure_songbird_airway import FIELDS, PROBE
from measure_songbird_chirps_onset import RADIATION, first_event
from measure_songbird_syrinx import CLI, load_trace
from measure_speech_timing import read, write
from measure_uniform_tube import build_upstream_probe, candidate_sources, record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE


ROOT = WORKSPACE.parents[2]
CASE = WORKSPACE / 'cases/songbird-chirps-beak-load.json'
VARIANTS = ('archived', 'no-tracking')
SIDES = ('candidate', 'upstream')
FIELDS_PER_CELL = ('pressure_dyn_cm2', 'inflow_cm3_s', 'area_cm2')
DENSITY = 1.14e-3
SPEED = 35000.0
BULK_MODULUS = DENSITY * SPEED ** 2


def lag(values):
    return np.concatenate((np.zeros_like(values[:1]), values[:-1]), axis=0)


def beak_fields(cells):
    return tuple(f'beak_{i}_{name}' for i in range(cells) for name in FIELDS_PER_CELL)


def load_prediction(pressure, inflow, area, length, rate):
    resistance = 128 * DENSITY * SPEED / (9 * math.pi ** 2 * area)
    inertance = 8 * DENSITY / (3 * math.pi * math.sqrt(math.pi * area))
    capacitance = area * length / BULK_MODULUS
    # 記録した節点圧の中点を使い、慣性枝を積分して抵抗枝と足す。
    midpoint = (pressure + lag(pressure)) * 0.5
    inertive = np.cumsum(midpoint / (rate * inertance))
    resistive = midpoint / resistance
    flow = (inertive + lag(inertive)) * 0.5 + resistive
    balance = (inflow - flow) / (rate * capacitance)
    return flow, pressure - lag(pressure) - balance, inertive, resistive


def propagation(trace, cells, length, cavity_length, rate):
    pressure, incoming, areas = (
        np.column_stack([trace[f'beak_{n}_{field}'] for n in range(cells)]) for field in FIELDS_PER_CELL)
    left_areas = np.column_stack((trace['oec_area_cm2'], areas[:, :-1]))
    left_pressures = np.column_stack((trace['oec_pressure_dyn_cm2'], pressure[:, :-1]))
    left_lengths = np.array([cavity_length] + [length] * (cells - 1))
    geometrical = left_lengths / left_areas + length / areas
    inertance = 0.5 * DENSITY * geometrical
    viscosity = math.sqrt(math.pi * DENSITY * 1.86e-4 * 700)
    left_perimeter_factors = np.array([1.2] + [1.0] * (cells - 1))
    left = math.sqrt(math.pi) * left_perimeter_factors * left_lengths / left_areas ** 1.5
    right = math.sqrt(math.pi) * length / areas ** 1.5
    resistance = viscosity * (left + right)
    previous_inertance = np.concatenate((inertance[:1], inertance[:-1]), axis=0)
    carried = np.minimum(previous_inertance, inertance) * lag(incoming)
    drive = lag(left_pressures - pressure) + rate * carried
    opening_jump = 1 / left_areas - 1 / areas
    entrance_loss = np.where(drive >= 0, opening_jump, -opening_jump)
    kinetic = 0.5 * DENSITY * entrance_loss ** 2 * np.where(entrance_loss >= 0, 1.0, 0.1)
    linear = rate * inertance + resistance
    expected_flow = 2 * drive / (linear + np.sqrt(linear ** 2 + 4 * kinetic * np.abs(drive)))
    geometric_compliance = areas[:, :-1] * length / BULK_MODULUS
    internal_pressure_residual = pressure[:, :-1] - lag(pressure[:, :-1]) - (
        (incoming[:, :-1] - incoming[:, 1:]) / (rate * geometric_compliance))
    flow, terminal_pressure_residual, inertive, resistive = load_prediction(
        pressure[:, -1], incoming[:, -1], areas[0, -1], length, rate)
    residuals = {'series_flow': np.abs(expected_flow - incoming),
                 'interior_pressure': np.abs(internal_pressure_residual),
                 'terminal_pressure': np.abs(terminal_pressure_residual),
                 'radiated_flow': np.abs(flow - trace['radiation_flow_cm3_s'])}
    return residuals, {'inertance_flow': inertive, 'resistance_flow': resistive}


def first_differences(left, right, fields):
    result = {}
    for field in fields:
        offset = first_event(left[field] - right[field])
        if offset is not None:
            result[field] = {'offset': offset, 'candidate': float(left[field][offset]),
                             'upstream': float(right[field][offset])}
    return result


def inlet_replay(candidate, upstream, offset, length, cavity_length, rate):
    pressure = 'beak_0_pressure_dyn_cm2'
    flow = 'beak_0_inflow_cm3_s'
    area = 'beak_0_area_cm2'
    old, current = candidate[offset - 1:offset + 1]
    cavity, inlet = (float(current[key]) for key in ('oec_area_cm2', area))
    dt = 1 / rate
    inertia = 0.5 * DENSITY * (cavity_length / cavity + length / inlet)
    upper_inertia = 0.5 * DENSITY * (cavity_length * (1 / cavity) + length * (1 / inlet))
    previous_inertia = 0.5 * DENSITY * (cavity_length / float(old['oec_area_cm2']) + length / inlet)
    viscosity = math.sqrt(DENSITY * 1.86e-4 * math.tau * 700 / 2)
    half_cavity = 2 * math.sqrt(math.pi * cavity) * cavity_length / cavity ** 2 * 1.2
    half_beak = 2 * math.sqrt(math.pi * inlet) * length / inlet ** 2
    resistance = 0.5 * viscosity * (half_cavity + half_beak)
    loss = 0.1 * (0.5 * DENSITY * (1 / inlet - 1 / cavity) ** 2)
    drive = (float(old['oec_pressure_dyn_cm2']) - float(old[pressure])
             + min(inertia, previous_inertia) / dt * float(old[flow]))

    def predicted(normalized_inertia):
        linear = normalized_inertia + resistance
        return 2 * drive / (linear + math.sqrt(linear ** 2 + 4 * loss * drive))

    division = predicted(inertia / dt)
    reciprocal = predicted(inertia * rate)
    same_inputs = (
        cavity > inlet and drive > 0 and inertia == upper_inertia
        and all(old[key] == upstream[offset - 1][key] for key in ('oec_pressure_dyn_cm2', pressure, flow))
        and all(current[key] == upstream[offset][key] for key in ('oec_area_cm2', area)))
    return (bool(same_inputs and division == candidate[flow][offset] and reciprocal == upstream[flow][offset]),
            {'offset': offset, 'inertance': inertia, 'normalization_by_division': inertia / dt,
             'normalization_by_reciprocal': inertia * rate, 'division_flow': division, 'reciprocal_flow': reciprocal})


def terminal_replay(inflow, capacitance_per_step, half_conductance, half_inductance_gain, grouped, *,
                    numerator_grouped=None):
    g, h = half_conductance, half_inductance_gain
    if numerator_grouped is None:
        numerator_grouped = grouped
    load = g + 0.5 * h
    left = capacitance_per_step - load if numerator_grouped else capacitance_per_step - 0.5 * h - g
    right = capacitance_per_step + load if grouped else capacitance_per_step + 0.5 * h + g
    p = u = 0.0
    result = np.empty(len(inflow), dtype=[('pressure', 'f8'), ('flow', 'f8')])
    for index, feed in enumerate(inflow):
        following = (p * left + float(feed) - u) / right
        inductive = u + h * (p + following)
        result[index] = (following, 0.5 * (u + inductive) + g * (following + p))
        p, u = following, inductive
    return result


def terminal_coefficients(area, length, rate):
    dt = 1 / rate
    capacitance = area * length / (DENSITY * SPEED * SPEED)
    g = 0.5 / (128 * DENSITY * SPEED / (9 * math.pi * math.pi * area))
    h = dt / (2 * (8 * DENSITY / (3 * math.pi * math.sqrt(math.pi * area))))
    return capacitance, g, h


def rounding_replay(case, traces, cells, length):
    rate = case['sample_rate_hz']
    reference = case['rounding_replay']
    candidate, upstream = (traces[side] for side in SIDES)
    inlet_ok, inlet = inlet_replay(candidate, upstream, reference['first_inlet_flow_delta'], length,
                                  math.cbrt(case['cavity_initial_volume_cm3']), rate)
    prefix = f'beak_{cells - 1}_'
    feed = prefix + 'inflow_cm3_s'
    area = float(candidate[prefix + 'area_cm2'][0])
    dt = 1 / rate
    capacitance, g, h = terminal_coefficients(area, length, rate)
    divided = terminal_replay(candidate[feed], capacitance / dt, g, h, True)
    multiplied = terminal_replay(upstream[feed], capacitance * rate, g, h, False)
    scaled_only = terminal_replay(candidate[feed], capacitance * rate, g, h, True)
    group_only = terminal_replay(candidate[feed], capacitance / dt, g, h, False)
    reset = terminal_replay(candidate[feed], capacitance * rate, g, h, False)
    tip_pressure = prefix + 'pressure_dyn_cm2'
    flow = 'radiation_flow_cm3_s'
    terminal_diffs = {
        'first_actual_pressure_difference': first_event(candidate[tip_pressure] - upstream[tip_pressure]),
        'first_actual_feed_difference': first_event(candidate[feed] - upstream[feed]),
        'first_pressure_difference_with_only_scale': first_event(scaled_only['pressure'] - upstream[tip_pressure]),
        'first_flow_difference_with_only_scale': first_event(scaled_only['flow'] - upstream[flow]),
        'first_pressure_difference_with_both': first_event(reset['pressure'] - upstream[tip_pressure]),
        'first_flow_difference_with_both': first_event(reset['flow'] - upstream[flow]),
    }
    checks = {'first_inlet_flow_replayed_by_normalization': inlet_ok,
              'terminal_candidate_replayed': np.array_equal(divided['pressure'], candidate[tip_pressure])
              and np.array_equal(divided['flow'], candidate[flow]),
              'terminal_upstream_replayed': np.array_equal(multiplied['pressure'], upstream[tip_pressure])
              and np.array_equal(multiplied['flow'], upstream[flow]),
              'terminal_pressure_and_feed_first_differences':
                  terminal_diffs['first_actual_pressure_difference'] == reference['first_tip_pressure_delta']
                  and terminal_diffs['first_actual_feed_difference'] == reference['first_tip_inflow_delta'],
              'terminal_scale_only_removes_first_flow_difference':
                  terminal_diffs['first_flow_difference_with_only_scale'] == reference['first_tip_inflow_delta']
                  and np.array_equal(group_only['flow'], candidate[flow]),
              'terminal_both_changes_match_until_feed_changes':
                  terminal_diffs['first_pressure_difference_with_both']
                  == terminal_diffs['first_flow_difference_with_both'] == reference['first_tip_inflow_delta']}
    return checks, {'inlet': inlet, 'terminal': terminal_diffs}


def measure(case, inputs, out, execute):
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera', '--test', 'airway',
             '--test', 'creature_realtime'], cwd=UPSTREAM, stdout=out / 'upstream-tests.log')
    probe = build_upstream_probe(PROBE, out, execute, extra_libraries=('serde_json',))
    rate = case['sample_rate_hz']
    length = case['beak_length_cm']
    cells = math.floor(length * rate * 0.93 / SPEED)
    start = case['event_sample']
    count = start + case['observation_internal_samples']
    fields = beak_fields(cells)
    checks, results, replay = {}, {}, {}
    for variant in VARIANTS:
        source = inputs[f'{variant}.json']
        settings = read(source)
        registered = settings['songbird_airway']
        if (registered['sample_rate_hz'], registered['events'][0]['sample'], registered['sample_count']) != (
            rate, start, count
        ):
            raise ValueError('保存済みの標本レート、入力の境界、または記録長がケースと一致しません')
        registered['observe_beak'] = True
        beak_case = out / f'{variant}.json'
        write(beak_case, settings)
        candidate, upstream = (out / f'{variant}-{side}.csv' for side in SIDES)
        execute([*CLI, 'render', str(beak_case), str(candidate)])
        execute([str(probe), str(beak_case)], cwd=UPSTREAM, stdout=upstream)
        traces = {side: load_trace(path, FIELDS + fields, count)
                  for side, path in zip(SIDES, (candidate, upstream), strict=True)}
        plain = out / f'{variant}-default.csv'
        execute([*CLI, 'render', str(source), str(plain)])
        checks[f'{variant}/default_cli_output_matches_archive'] = (
            plain.read_bytes() == inputs[f'{variant}-candidate.csv'].read_bytes())
        result, components = {}, {}
        for side, trace in traces.items():
            previous = load_trace(inputs[f'{variant}-{side}.csv'], FIELDS, count)
            checks[f'{variant}/{side}/existing_fields_match_archive'] = all(
                np.array_equal(trace[field].view(np.uint64), previous[field].view(np.uint64)) for field in FIELDS
                if field != 'sample')
            tip = trace[f'beak_{cells - 1}_area_cm2']
            checks[f'{variant}/{side}/fixed_beak_shape'] = bool(np.all(tip == tip[0]))
            residuals, components[side] = propagation(
                trace, cells, length / cells, math.cbrt(case['cavity_initial_volume_cm3']), rate)
            result[side] = {key: float(values.max()) for key, values in residuals.items()}
            for key, error in result[side].items():
                tolerance = case['pressure_absolute_tolerance_dyn_cm2' if 'pressure' in key
                                 else 'flow_absolute_tolerance_cm3_s']
                checks[f'{variant}/{side}/{key}_independent'] = error <= tolerance
            if variant == 'no-tracking':
                checks[f'{side}/no_tracking_quiet'] = all(not np.any(trace[field])
                    for field in fields + ('radiation_flow_cm3_s',) if not field.endswith('_area_cm2'))
        candidate_onset, upstream_onset = (traces[side][start:] for side in SIDES)
        diffs = first_differences(candidate_onset, upstream_onset, (*fields, 'radiation_flow_cm3_s', RADIATION))
        left_load, right_load = ({name: values[start:] for name, values in components[side].items()} for side in SIDES)
        load_diffs = first_differences(left_load, right_load, left_load)
        results[variant] = {'residuals': result, 'first_differences': diffs,
                            'first_independent_load_component_differences': load_diffs}
        if variant == 'archived':
            replay_checks, replay = rounding_replay(
                case, dict(zip(SIDES, (candidate_onset, upstream_onset), strict=True)), cells, length / cells)
            checks.update(replay_checks)
    observed = results['archived']['first_differences']
    reference = read(inputs['summary.json'])['derivative_replay']
    checks['retains_first_radiation_differences'] = (
        observed[RADIATION]['offset'] == reference['first_rounding_difference']
        and observed['radiation_flow_cm3_s']['offset'] == reference['first_flow_difference'])
    early_changes = [value['offset'] for field, value in observed.items()
                     if field in fields and not field.endswith('_area_cm2')]
    hypothesis = bool(early_changes and min(early_changes) <= reference['first_flow_difference'])
    checks['first_observed_inlet_flow_delta'] = (
        observed['beak_0_inflow_cm3_s']['offset'] == case['rounding_replay']['first_inlet_flow_delta'])
    return {'checks': checks, 'hypotheses': {'beak_pressure_or_inflow_differs_at_or_before_radiated_flow': hypothesis},
            'event_sample': start, 'beak_cells': cells, 'variants': results, 'rounding_replay': replay}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    case = read(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    run = WORKSPACE / 'runs' / case['baseline_run']
    manifest = read(run / 'manifest.json')
    if (manifest['status'], manifest['case_id'], manifest['upstream_revision']) != (
        'pass', 'songbird-chirps-onset-radiation', revision
    ):
        parser.error('一致した固定上流で検証済みの放射比較が必要です')
    names = [f'{variant}.json' for variant in VARIANTS]
    names.extend(f'{variant}-{side}.csv' for variant in VARIANTS for side in SIDES)
    inputs = {name: verified_file(run, manifest, f'artifacts/{name}') for name in names}
    inputs['summary.json'] = verified_file(run, manifest, 'summary.json')
    prior = WORKSPACE / 'runs' / case['rounding_replay']['prior_run']
    prior_manifest = read(prior / 'manifest.json')
    if (prior_manifest['status'], prior_manifest['case_id'], prior_manifest['case_revision'],
            prior_manifest['upstream_revision']) != ('pass', case['id'], 1, revision):
        parser.error('第1版のくちばしの計測が必要です')
    metadata = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision,
                'analysis_command': [sys.executable, *sys.argv], 'analysis_directory': str(Path.cwd())}
    sources = [CASE, Path(__file__), PROBE, run / 'manifest.json', *inputs.values(), *candidate_sources(),
               WORKSPACE / 'tools/measure_songbird_chirps_onset.py', WORKSPACE / 'tools/measure_songbird_syrinx.py',
               WORKSPACE / 'tools/measure_songbird_airway.py', WORKSPACE / 'tools/measure_uniform_tube.py',
               UPSTREAM / 'crates/chimera/src/airway/network.rs', UPSTREAM / 'crates/chimera/src/creatures/songbird.rs',
               prior / 'manifest.json', verified_file(prior, prior_manifest, 'summary.json')]
    return record_measurement(args.run_id, CASE, sources, metadata, lambda out, execute: measure(case, inputs, out, execute),
                              command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
