"""アザラシの肺・声門の結合を内部サンプルごとに照合する。"""

import argparse
import json
from math import pi, sqrt
from pathlib import Path
import re
import subprocess

import numpy as np

import measure_uniform_tube as shared
from measure_songbird_syrinx import CLI, compare, read
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/seal-airway.json'
PROBE = WORKSPACE / 'tools/upstream_seal_airway_probe.rs'
PRESSURES = ('lung_pressure_dyn_cm2', 'trachea_inlet_pressure_dyn_cm2', 'trachea_end_pressure_dyn_cm2',
             'pharynx_pressure_dyn_cm2', 'glottis_drive_dyn_cm2')
FLOWS = ('lung_flow_cm3_s', 'glottis_flow_cm3_s', 'velum_flow_cm3_s', 'nasal_radiation_cm3_s')
RADIATION = 'radiation_derivative_cm3_s2'
FIELDS = ('sample', *PRESSURES[:1], *FLOWS[:1], *PRESSURES[1:], 'glottis_area_cm2', FLOWS[1],
          'glottis_voicing', 'glottis_f0_hz', *FLOWS[2:], RADIATION)
SHADOW = 'shadow_area_error_cm2'


def read_trace(path, rows, fields):
    header, trace = shared.read_trace(path, rows, len(fields))
    if tuple(header) != fields:
        raise ValueError(f'{path.name} の列名が一致しません')
    return dict(zip(fields, trace.T, strict=True))


def compare_traces(candidate, upstream, limits):
    tolerances = {key: limits['direct_pressure_absolute_tolerance_dyn_cm2'] for key in PRESSURES}
    tolerances.update({key: limits['direct_flow_absolute_tolerance_cm3_s'] for key in FLOWS})
    tolerances['glottis_area_cm2'] = limits['direct_area_absolute_tolerance_cm2']
    tolerances['glottis_f0_hz'] = limits['direct_f0_absolute_tolerance_hz']
    tolerances[RADIATION] = limits['direct_radiation_derivative_absolute_tolerance_cm3_s2']
    return {key: compare(candidate[key], upstream[key], tolerance) for key, tolerance in tolerances.items()}


def first_signal(trace, key, threshold):
    positions = np.flatnonzero(np.abs(trace[key]) > threshold)
    return int(positions[0]) if positions.size else None


def first_port_step(pressure, rate, trachea_cells, spec):
    """静止状態で固定圧が変わる一ステップの直列素子と気管入口の圧縮。"""
    rho, sound = spec['density_g_cm3'], spec['sound_speed_cm_s']
    area, length = spec['trachea_area_cm2'], spec['lung_port_length_cm']
    trachea_dx = spec['trachea_length_cm'] / trachea_cells
    half_sections = 0.5 * (spec['lung_length_cm'] / spec['lung_area_cm2'] + trachea_dx / area)
    inertance = rho * (length / area + half_sections)
    viscosity = sqrt(rho * spec['dynamic_viscosity_poise'] * pi * spec['viscosity_frequency_hz'])
    resistance = viscosity * (2 * sqrt(pi * area)) * length / area**2 + rho * sound / (2 * area)
    flow = pressure / (rate * inertance + resistance)
    compliance = area * trachea_dx / (rho * sound**2)
    return flow, flow / (rate * compliance)


def verify_trace(trace, rate, limits):
    threshold = limits['causal_first_signal_threshold']
    arrival = {key: first_signal(trace, key, threshold) for key in (*PRESSURES, *FLOWS, RADIATION)}
    checks = {
        'velum_closed': arrival['velum_flow_cm3_s'] is None,
        'nasal_silent': arrival['nasal_radiation_cm3_s'] is None,
        'drive_from_previous_state': bool(np.allclose(
            trace['glottis_drive_dyn_cm2'],
            np.r_[0.0, (trace['trachea_end_pressure_dyn_cm2'] - trace['pharynx_pressure_dyn_cm2'])[:-1]],
            rtol=0, atol=limits['direct_pressure_absolute_tolerance_dyn_cm2'])),
    }
    start = arrival['lung_pressure_dyn_cm2']
    observations = {'first_nonzero_internal_sample': arrival,
                    'peak_glottis_flow_cm3_s': float(np.max(np.abs(trace['glottis_flow_cm3_s']))),
                    'peak_glottis_voicing': float(np.max(trace['glottis_voicing'])),
                    'peak_radiation_derivative_cm3_s2': float(np.max(np.abs(trace[RADIATION])))}
    if start is None:
        checks['no_pressure_flow_or_radiation'] = all(sample is None for sample in arrival.values())
        time = (trace['sample'] + 1) / rate
        area = -limits['chink_cm2'] * np.expm1(-time / limits['chink_tau_seconds'])
        result = compare(trace['glottis_area_cm2'], area, limits['independent_chink_absolute_tolerance_cm2'])
        observations['chink_vs_closed_form'] = result
        checks['chink_vs_closed_form'] = result['passed']
    else:
        length, sound = limits['trachea_length_cm'], limits['sound_speed_cm_s']
        min_dx = sound / rate / limits['cfl']
        cells = max(3, min(60, int(length / (min_dx * limits['trachea_coarse_factor']))))
        checks['lung_flow_and_inlet_first'] = (arrival['lung_flow_cm3_s'] == start
                                              and arrival['trachea_inlet_pressure_dyn_cm2'] == start)
        checks['propagation_order'] = (arrival['trachea_end_pressure_dyn_cm2'] == start + cells - 1
                                       and arrival['glottis_drive_dyn_cm2'] == start + cells
                                       and arrival['glottis_flow_cm3_s'] == start + cells
                                       and arrival['pharynx_pressure_dyn_cm2'] == start + cells)
        flow, pressure = first_port_step(float(trace['lung_pressure_dyn_cm2'][start]), rate, cells, limits)
        actual_flow = float(trace['lung_flow_cm3_s'][start])
        actual_pressure = float(trace['trachea_inlet_pressure_dyn_cm2'][start])
        checks['initial_lung_flow'] = abs(flow - actual_flow) <= limits['independent_initial_flow_absolute_tolerance_cm3_s']
        checks['initial_inlet_pressure'] = abs(pressure - actual_pressure) <= limits['independent_initial_pressure_absolute_tolerance_dyn_cm2']
        observations['initial_step'] = {'lung_flow_cm3_s': actual_flow, 'predicted_lung_flow_cm3_s': flow,
                                        'trachea_inlet_dyn_cm2': actual_pressure, 'predicted_trachea_inlet_dyn_cm2': pressure}
    return checks, observations


def measure_variant(name, source, folder, probe, limits, execute):
    folder.mkdir()
    case, path, upper, inspect, upper_inspect = (
        folder / filename for filename in ('case.json', 'candidate.csv', 'upstream.csv', 'inspect.json', 'upstream-geometry.json'))
    case.write_text(json.dumps({'seal_airway': source}, indent=2) + '\n')
    execute([*CLI, 'inspect', str(case)], stdout=inspect)
    execute([*CLI, 'render', str(case), str(path)])
    execute([str(probe), str(case), '--inspect'], cwd=UPSTREAM, stdout=upper_inspect)
    execute([str(probe), str(case)], cwd=UPSTREAM, stdout=upper)

    breath = source['breath']
    factor = 2 if breath['sample_rate_hz'] <= 60000 else 1
    rate, rows = breath['sample_rate_hz'] * factor, breath['frames'] * factor
    candidate = read_trace(path, rows, FIELDS)
    upstream = read_trace(upper, rows, (*FIELDS, SHADOW))
    settings = read(inspect)
    reference = read(upper_inspect)
    checks = {key: settings[key] == reference[key] == expected for key, expected in
              [('rows', rows), ('internal_rate_hz', rate), ('oversample', factor)]}
    geometry = settings['geometry']
    checks['geometry'] = all(abs(value - reference['geometry'][key]) <= 1e-12 for key, value in geometry.items())
    checks['shadow_matches_real_area'] = bool(np.all(upstream[SHADOW] <= limits['direct_area_absolute_tolerance_cm2']))
    comparisons = compare_traces(candidate, upstream, limits)
    checks.update({f'upstream.{key}': row['passed'] for key, row in comparisons.items()})
    outcomes = {}
    for label, trace in (('candidate', candidate), ('upstream', upstream)):
        result, outcomes[label] = verify_trace(trace, rate, limits)
        first = outcomes[label]['first_nonzero_internal_sample']['lung_pressure_dyn_cm2']
        if name == 'nominal-48000':
            result['first_active_sample'] = first == limits['nominal_first_active_internal_sample']
        elif name == 'delayed-44100':
            result['first_active_sample'] = first == limits['delayed_first_active_internal_sample']
        elif name == 'silent-96000':
            result['remains_silent'] = first is None and bool(np.all(trace['glottis_voicing'] == 0))
        checks.update({f'{label}.{key}': passed for key, passed in result.items()})
    return candidate, {
        'checks': checks, 'rows': rows, 'internal_rate_hz': rate, 'geometry': geometry,
        'comparison': comparisons, 'observations': outcomes,
        'shadow_area_max_error_cm2': float(np.max(upstream[SHADOW])),
        'voicing_max_difference': float(np.max(np.abs(candidate['glottis_voicing'] - upstream['glottis_voicing']))),
    }


def measure(config, artifacts, execute):
    probe = shared.build_upstream_probe(PROBE, artifacts, execute, extra_libraries=('serde_json',))
    limits, baseline = config['measurement'], config['seal_airway']
    traces, variants, checks = {}, {}, {}
    for item in limits['variants']:
        name, breath = item['id'], item['breath']
        source = {'breath': baseline['breath'] | breath | {
            'controls': baseline['breath']['controls'] | breath.get('controls', {})},
            'shape': baseline['shape'] | item['shape']}
        trace, result = measure_variant(name, source, artifacts / name, probe, limits, execute)
        traces[name], variants[name] = trace, result
        checks.update({f'{name}.{key}': passed for key, passed in result['checks'].items()})
    contrasts = {}
    windows = (('whole', limits['contrast_window_internal_samples']),
               ('pulse_inactive', limits['first_inactive_pulse_window_internal_samples']))
    for label, (left, right) in windows:
        interval = slice(left, right)
        contrasts[label] = {
            name: {'lung_pressure_mean_dyn_cm2': float(np.mean(traces[name]['lung_pressure_dyn_cm2'][interval])),
                   'glottis_flow_rms_cm3_s': float(np.sqrt(np.mean(traces[name]['glottis_flow_cm3_s'][interval]**2)))}
            for name in ('nominal-48000', 'depth-zero')
        }
    nominal = contrasts['pulse_inactive']['nominal-48000']
    no_pulse = contrasts['pulse_inactive']['depth-zero']
    checks['inactive_pulse_lower_mean_pressure'] = nominal['lung_pressure_mean_dyn_cm2'] < no_pulse['lung_pressure_mean_dyn_cm2']
    checks['inactive_pulse_lower_flow_rms'] = nominal['glottis_flow_rms_cm3_s'] < no_pulse['glottis_flow_rms_cm3_s']
    return {'checks': checks, 'variants': variants, 'depth_zero_comparison': contrasts}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', args.run_id):
        parser.error('実行IDは英数字で始めてください')
    config = read(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != config['upstream_revision'] or subprocess.check_output(
            ['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True):
        raise SystemExit('変更のない固定上流版が必要です')
    references = ('LICENSE', 'Cargo.lock', 'crates/chimera/src/physics.rs',
                  'crates/chimera/src/creatures/seal.rs', 'crates/chimera/src/creatures/voice.rs',
                  'crates/chimera/src/creatures/build.rs', 'crates/chimera/src/creatures/mammal.rs',
                  'crates/chimera/src/sources/glottis.rs', 'crates/chimera/src/airway/network.rs',
                  'crates/chimera-cli/src/render.rs', 'crates/chimera/tests/golden_creatures.rs')
    baseline = WORKSPACE / 'runs/seal-breath-before-airway-1/manifest.json'
    if read(baseline)['status'] != 'pass':
        raise SystemExit('固定肺圧の基準ケースが不合格です')
    details = {'case_id': config['id'], 'revision': config['revision'],
               'invoked_from': str(Path.cwd()), 'upstream_revision': revision,
               'upstream_source_sha256': {file: sha256(UPSTREAM / file) for file in references}}
    inputs = [CASE, baseline, PROBE, Path(__file__).resolve(), Path(shared.__file__),
              *(WORKSPACE / 'tools' / file for file in ('upstream_baseline.py', 'measure_songbird_syrinx.py')),
              WORKSPACE / 'LICENSE-CHIMERA', *shared.candidate_sources()]
    return shared.record_measurement(args.run_id, CASE, inputs, details,
                                     lambda artifacts, execute: measure(config, artifacts, execute), command=None)


if __name__ == '__main__':
    raise SystemExit(main())
