"""左右の鳴管と気道を固定上流および枝・節点の独立計算に照合する。"""

import argparse
import json
from pathlib import Path
import re
import subprocess

import numpy as np

import measure_uniform_tube as shared
from measure_songbird_syrinx import CLI, compare, load_trace, read
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/songbird-airway.json'
PROBE = WORKSPACE / 'tools/upstream_songbird_airway_probe.rs'
FIELDS = (
    'sample', 'left_opening', 'right_opening', 'left_port_area_cm2', 'right_port_area_cm2',
    'left_flow_cm3_s', 'right_flow_cm3_s', 'left_bronchus_pressure_dyn_cm2',
    'right_bronchus_pressure_dyn_cm2', 'sac_pressure_dyn_cm2', 'trachea_pressure_dyn_cm2',
    'trachea_out_flow_cm3_s', 'trachea_wall_flow_cm3_s', 'oec_area_cm2', 'oec_pressure_dyn_cm2',
    'beak_tip_area_cm2', 'radiation_flow_cm3_s', 'radiation_derivative_cm3_s2',
)
SIDES = ('left', 'right')
RHO = 1.14e-3
C = 35000.0


def initial_geometry(rate):
    cells = np.clip(np.floor(np.asarray([0.8, 3.6, 1.3]) / (C / rate / 0.93)), 3, 120).astype(int)
    lengths = np.asarray([0.8, 3.6, 1.3]) / cells
    return cells, lengths


def fitted_boundaries(source, beak_cells):
    count, block = source['sample_count'], source['control_block_samples']
    events = [{'sample': 0, **{key: source[key] for key in ('controls', 'breath_gate')}}, *source['events']]
    expected = {key: np.zeros(count) for key in ('sac_pressure_dyn_cm2', 'oec_area_cm2', 'beak_tip_area_cm2')}
    previous = None
    for index, event in enumerate(events):
        start = event['sample']
        stop = events[index + 1]['sample'] if index + 1 < len(events) else count
        p = event['controls']
        low_pitch = p['pitch_hz'] * min(1, 2**(p['interval_semitones'] / 12))
        volume = np.clip(p['purity'] * (0.03 / 0.35) * (5570 / low_pitch)**2
                         + (1 - p['purity']) * p['oec_cm3'], 0.04, 2.5)
        targets = (volume / np.cbrt(0.4), 0.012 + p['gape'] * (0.05 + 0.22 * (1 - 0.5 / beak_cells)))
        expected['sac_pressure_dyn_cm2'][start:stop] = 1e4 * p['pressure_kpa'] * event['breath_gate']
        fraction = np.minimum(1, np.arange(1, stop - start + 1) / block)
        for key, old, target in zip(('oec_area_cm2', 'beak_tip_area_cm2'), previous or targets, targets, strict=True):
            expected[key][start:stop] = old + (target - old) * fraction
        previous = targets
    return expected


def lag(values):
    return np.concatenate(([0.0], values[:-1]))


def branch_and_junction(trace, rate, lengths, limits):
    bronchus_dx, trachea_dx, _ = lengths
    trachea_p = trace['trachea_pressure_dyn_cm2']
    # 開口面積と前サンプルの圧力・流量から、枝の運動方程式を独立に解く。
    inv_inertance = np.full(len(trace), 0.045 / (RHO * trachea_dx))
    viscosity = np.sqrt(np.pi * RHO * 1.86e-4 * 700)
    comparison = {}
    for side in SIDES:
        area = trace[f'{side}_port_area_cm2']
        flow = trace[f'{side}_flow_cm3_s']
        opened = area >= 0.0002
        active_area = np.maximum(area, 0.0002)
        inertance = RHO * (0.08 / active_area + 0.5 * (bronchus_dx / 0.02 + trachea_dx / 0.045))
        inv_inertance += np.where(opened, 1 / inertance, 0.0)
        resistance = 2 * np.sqrt(np.pi) * viscosity * 0.08 / active_area**1.5
        # 閉鎖の直後は運動量がゼロなので、前の慣性が何であっても流量は繰り越されない。
        pressure = lag(trace[f'{side}_bronchus_pressure_dyn_cm2'] - trachea_p)
        drive = pressure + np.minimum(inertance, lag(inertance)) * lag(flow) * rate
        downstream = np.where(drive >= 0, 0.045, 0.02)
        kinetic = 0.5 * RHO * (0.5 / active_area**2 + np.maximum(0, 1 / active_area - 1 / downstream)**2)
        linear = rate * inertance + resistance
        estimated = np.where(opened, 2 * drive / (linear + np.sqrt(linear**2 + 4 * kinetic * np.abs(drive))), 0.0)
        comparison[f'{side}.branch_update'] = compare(flow, estimated, limits['branch_update_absolute_tolerance_cm3_s'])
        comparison[f'{side}.opening_projection'] = compare(
            area, 0.03 * trace[f'{side}_opening'], limits['opening_absolute_tolerance'])
    c_geom = 0.045 * trachea_dx / (RHO * C**2)
    c_floor = inv_inertance / (2.4 * rate**2)
    compliance = np.maximum(c_geom, c_floor)
    net_flow = (trace['left_flow_cm3_s'] + trace['right_flow_cm3_s'] - trace['trachea_out_flow_cm3_s']
                - trace['trachea_wall_flow_cm3_s'])
    expected_pressure = lag(trachea_p) + net_flow / (rate * compliance)
    comparison['junction_update'] = compare(trachea_p, expected_pressure,
                                           limits['junction_update_absolute_tolerance_dyn_cm2'])
    delta_p = trachea_p - lag(trachea_p)
    observable = np.abs(delta_p) >= 1.0
    if np.any(observable):
        comparison['junction_compliance'] = compare(net_flow[observable] / (rate * delta_p[observable]),
                                                    compliance[observable], limits['compliance_absolute_tolerance'])
    comparison['radiation_difference'] = compare(
        trace['radiation_derivative_cm3_s2'], (trace['radiation_flow_cm3_s'] - lag(trace['radiation_flow_cm3_s'])) * rate,
        limits['acoustic_peak_relative_tolerance'] * np.max(np.abs(trace['radiation_derivative_cm3_s2']))
        + limits['acoustic_absolute_floor'])
    return comparison, {'geometric': c_geom, 'maximum_floor': float(c_floor.max()),
                        'samples_on_floor': int(np.count_nonzero(c_floor > c_geom)),
                        'samples_recovered_from_pressure': int(np.count_nonzero(observable))}


def acoustic_tolerance(field, signal, limits):
    if field.endswith('_opening'):
        return limits['opening_absolute_tolerance']
    if field.endswith('_cm2') and 'pressure' not in field:
        return limits['geometry_absolute_tolerance_cm2']
    return limits['acoustic_absolute_floor'] + np.max(np.abs(signal)) * limits['acoustic_peak_relative_tolerance']


def compare_trace(left, right, limits):
    results = {key: compare(left[key], right[key], acoustic_tolerance(key, right[key], limits))
               for key in FIELDS[1:]}
    first = min(((entry['first_difference_sample'], FIELDS.index(key), key)
                 for key, entry in results.items() if entry['first_difference_sample'] is not None), default=None)
    return results, None if first is None else {'sample': first[0], 'field': first[2]}


def rms(values):
    return float(np.sqrt(np.mean(values**2)))


def radiation_tones(trace, source, segment, limits):
    signal = trace['radiation_derivative_cm3_s2'][segment]
    amplitude = np.abs(np.fft.rfft(np.hanning(signal.size) * (signal - np.mean(signal))))
    hz = np.fft.rfftfreq(signal.size, 1 / source['sample_rate_hz'])
    p = source['controls']
    tones = {}
    for side, target in zip(SIDES, (p['pitch_hz'], p['pitch_hz'] * 2**(p['interval_semitones'] / 12)), strict=True):
        indices = np.flatnonzero(np.abs(hz - target) < limits['tone_half_band_hz'])
        peak = indices[np.argmax(amplitude[indices])]
        tones[side] = {'target_hz': target, 'peak_bin_hz': float(hz[peak]),
                       'relative_amplitude': float(amplitude[peak] / amplitude.max())}
    return tones


def capture(name, source, artifacts, execute, probe, limits, checks):
    out = artifacts / name
    out.mkdir()
    case = out / 'case.json'
    case.write_text(json.dumps({'songbird_airway': source}, indent=2) + '\n')
    settings, native, upper = (out / name for name in ('settings.json', 'candidate.csv', 'upstream.csv'))
    execute([*CLI, 'inspect', str(case)], stdout=settings)
    execute([*CLI, 'render', str(case), str(native)])
    execute([str(probe), str(case)], cwd=UPSTREAM, stdout=upper)
    count, rate = source['sample_count'], source['sample_rate_hz']
    left, right = (load_trace(path, FIELDS, count) for path in (native, upper))
    cells, lengths = initial_geometry(rate)
    geometry = read(settings)['geometry']
    observed_cells = [geometry[f'{key}_cells{s}'] for key, s in (('bronchus', '_per_side'), ('trachea', ''), ('beak', ''))]
    checks[f'{name}.cell_counts'] = bool(np.array_equal(observed_cells, cells))
    checks[f'{name}.cfl'] = bool(abs(geometry['courant'] - C / (rate * min(lengths))) < 1e-12)
    checks[f'{name}.lengths'] = bool(abs(geometry['trachea_cell_length_cm'] - lengths[1]) < 1e-12
                                     and abs(geometry['oec_length_cm'] - np.cbrt(0.4)) < 1e-12)
    agreement, first = compare_trace(left, right, limits)
    for field, result in agreement.items():
        checks[f'{name}.upstream.{field}'] = result['passed']
    independent, compliance = {}, {}
    for label, trace in (('candidate', left), ('upstream', right)):
        series, compliance[label] = branch_and_junction(trace, rate, lengths, limits)
        series.update({
            field: compare(trace[field], expected, limits['geometry_absolute_tolerance_cm2'])
            for field, expected in fitted_boundaries(source, int(cells[2])).items()
        })
        for field, result in series.items():
            checks[f'{name}.{label}.{field}'] = result['passed']
        independent[label] = series
    return left, {'geometry': geometry, 'samples': count, 'first_upstream_difference': first,
                  'upstream': agreement, 'independent': independent, 'junction_compliance': compliance}


def measure(config, artifacts, execute):
    execute(['cargo', 'test', '--locked', '-p', 'chimera', '--test', 'airway_adversarial',
             '--test', 'golden_creatures', '--test', 'creature_realtime'], cwd=UPSTREAM,
            stdout=artifacts / 'upstream-tests.log')
    probe = shared.build_upstream_probe(PROBE, artifacts, execute, extra_libraries=('serde_json',))
    limits = config['measurement']
    base = config['songbird_airway']
    checks, traces, variants = {}, {}, {}
    for entry in limits['variants']:
        name, overrides = entry['id'], entry['overrides']
        source = base | overrides | {'controls': base['controls'] | overrides.get('controls', {})}
        traces[name], variants[name] = capture(name, source, artifacts, execute, probe, limits, checks)
    both = traces['both']
    segment = slice(*(round(seconds * base['sample_rate_hz']) for seconds in limits['steady_window_seconds']))
    coupling = {}
    for side, opposite in (SIDES, SIDES[::-1]):
        single = traces[side]
        opening, flow = f'{side}_opening', f'{side}_flow_cm3_s'
        checks[f'{side}.closed_side'] = bool(np.all(single[f'{opposite}_opening'] == 0)
                                            and np.all(single[f'{opposite}_flow_cm3_s'] == 0))
        checks[f'{side}.unchanged_opening'] = np.array_equal(single[opening], both[opening])
        coupling[side] = {'single_rms_cm3_s': rms(single[flow][segment]), 'both_rms_cm3_s': rms(both[flow][segment]),
                          'difference_rms_cm3_s': rms((both[flow] - single[flow])[segment]),
                          'both_negative_flow_samples': int(np.count_nonzero(both[flow][segment] < 0))}
        checks[f'{side}.active_flow'] = coupling[side]['single_rms_cm3_s'] >= limits['minimum_active_flow_rms_cm3_s']
        checks[f'{side}.coupling'] = coupling[side]['difference_rms_cm3_s'] >= limits['minimum_coupling_flow_difference_rms_cm3_s']
    quiet = traces['no-breath']
    checks['no-breath.openings_active'] = all(np.max(quiet[f'{side}_opening']) > 0.5 for side in SIDES)
    checks['no-breath.pressure_flow_radiation_zero'] = all(np.all(quiet[key] == 0)
        for key in FIELDS if key.endswith(('_dyn_cm2', '_cm3_s', '_cm3_s2')))
    tones = radiation_tones(both, base, segment, limits)
    for side, tone in tones.items():
        checks[f'both.radiated_{side}_tone'] = tone['relative_amplitude'] >= limits['minimum_tone_fraction_of_peak']
    pressure_coupling = {side: rms((both['trachea_pressure_dyn_cm2']
                                    - traces[side]['trachea_pressure_dyn_cm2'])[segment]) for side in SIDES}
    return {'checks': checks, 'variants': variants, 'coupling': coupling, 'radiation_tones': tones,
            'trachea_pressure_difference_rms_dyn_cm2': pressure_coupling}


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
    references = ('crates/chimera-cli/src/render.rs', 'crates/chimera/src/creatures/songbird.rs',
                  'crates/chimera/src/creatures/build.rs', 'crates/chimera/src/creatures/voice.rs',
                  'crates/chimera/src/airway/network.rs', 'crates/chimera/src/sources/syrinx.rs',
                  'crates/chimera/src/sources/syrinxTable.generated.json', 'crates/chimera/src/physics.rs',
                  'crates/chimera/tests/airway_adversarial.rs', 'crates/chimera/tests/golden_creatures.rs',
                  'crates/chimera/tests/creature_realtime.rs')
    metadata = {'case_id': config['id'], 'revision': config['revision'], 'upstream_revision': revision,
                'invoked_from': str(Path.cwd()),
                'upper_source_sha256': {name: sha256(UPSTREAM / name) for name in references}}
    inputs = [CASE, PROBE, Path(__file__).resolve(), Path(shared.__file__),
              WORKSPACE / 'tools/measure_songbird_syrinx.py', WORKSPACE / 'tools/upstream_baseline.py',
              *shared.candidate_sources()]
    return shared.record_measurement(args.run_id, CASE, inputs, metadata,
        lambda artifacts, execute: measure(config, artifacts, execute), command=None)


if __name__ == '__main__':
    raise SystemExit(main())
