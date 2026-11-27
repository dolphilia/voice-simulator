"""左鳴管ポートの流量を再計算し、初差の項を照合する。"""

import argparse
import csv
from pathlib import Path
import subprocess
import sys

from measure_songbird_chirps_beak_load import ROOT
from measure_songbird_chirps_beak_tip_inflow import UPPER_NETWORK, UPPER_SONGBIRD
from measure_songbird_chirps_beak_tip_inflow_44100 import registered_artifacts
from measure_songbird_chirps_oec_neck_44100 import diagnose, evaluate, port_impedance
from measure_songbird_chirps_oec_pressure_44100 import CONDITIONS
from measure_songbird_chirps_terminal_numerator_44100 import first_offset, same_bits
from measure_songbird_syrinx import load_trace
from measure_speech_timing import read, write
from measure_uniform_tube import record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE


CASE = WORKSPACE / 'cases/songbird-chirps-left-syrinx-port-44100.json'
BASE_ID = 'songbird-chirps-trachea-all-momentum-44100'
AREA = 'left_port_area_cm2'
FLOW = 'left_flow_cm3_s'
BRONCHUS, TRACHEA = 'left_bronchus_pressure_dyn_cm2', 'trachea_pressure_dyn_cm2'


def replay(trace, start, case, *, upstream, multiply_left_half=False, multiply_momentum=False,
           multiply_linear=False, side='left'):
    geometry = case['geometry']
    areas = tuple(geometry[f'{end}_area_cm2'] for end in ('bronchus', 'trachea'))
    lengths = tuple(geometry[f'{end}_length_cm'] / geometry[f'{end}_cells'] for end in ('bronchus', 'trachea'))
    closed_area = geometry['closed_area_cm2']
    rate = case['sample_rate_hz']
    dt = 1 / rate
    order = {'upstream': upstream, 'multiply_left_half': multiply_left_half}
    area_key, flow_key, bronchus_key = (f'{side}_{key}' for key in (
        'port_area_cm2', 'flow_cm3_s', 'bronchus_pressure_dyn_cm2'))
    rows = []
    for prior, current in zip(trace[start - 1:-1], trace[start:], strict=True):
        area, previous_area = float(current[area_key]), float(prior[area_key])
        old_flow = float(prior[flow_key])
        observed = float(current[flow_key])
        pressure_left, pressure_right = (float(prior[key]) for key in (bronchus_key, TRACHEA))
        state = {'bronchus_pressure': pressure_left, 'trachea_pressure': pressure_right, 'previous_flow': old_flow,
                 'port_area_cm2': area, 'prior_port_area_cm2': previous_area}
        if area < closed_area:
            rows.append({'closed': True, 'previous_state': state, 'observed': observed, 'result': {'flow': 0.0}})
            continue
        inertance, resistance, forward, reverse = port_impedance(area, areas, lengths, case['port'], **order)
        old_inertance = (port_impedance(previous_area, areas, lengths, case['port'], **order)[0]
                         if previous_area >= closed_area else 0.0)
        carried = min(inertance, old_inertance)
        state.update(previous_inertance=old_inertance, current_inertance=inertance)
        momentum = (carried * old_flow) * rate if upstream or multiply_momentum else (carried / dt) * old_flow
        terms = {'pressure_difference': pressure_left - pressure_right, 'noise_pressure': 0.0,
                 'normalized_momentum': momentum,
                 'normalized_inertance': inertance * rate if upstream or multiply_linear else inertance / dt,
                 'resistance': resistance, 'forward_loss': forward, 'reverse_loss': reverse}
        rows.append({'closed': False, 'previous_state': state, 'terms': terms,
                     'result': evaluate(terms), 'observed': observed})
    return rows


def stored_trace(path, count):
    # 入力CSVは前回のマニフェストに登録されている。
    with path.open(newline='') as csv_file:
        columns = tuple(next(csv.reader(csv_file)))
    return load_trace(path, columns, count)


def measure(case, saved, out, execute):
    rate, window = case['sample_rate_hz'], case['observation_internal_samples']
    trachea_area = case['geometry']['trachea_area_cm2']
    trachea_length = case['geometry']['trachea_length_cm'] / case['geometry']['trachea_cells']
    checks, results, replays = {}, {}, {}
    for name in CONDITIONS:
        settings = read(saved[f'artifacts/{name}.json'])['songbird_airway']
        start = case['condition_control_samples'][name]
        event, = settings['events']
        if (settings['sample_rate_hz'], settings['control_block_samples'], event['sample'],
                settings['breath_gate'], event['breath_gate']) != (rate, start, start, 0, 0) or (
                start + window > settings['sample_count']):
            raise ValueError(f'保存した鳴禽の描画条件が一致しません ({name})')
        traces, series = {}, {}
        for side, label in (('candidate', 'interior-momentum'), ('upstream', 'upstream')):
            full = stored_trace(saved[f'artifacts/{name}-{label}.csv'], settings['sample_count'])
            trace = traces[side] = full[:start + window]
            rows = series[side] = replay(trace, start, case, upstream=side == 'upstream')
            checks[f'{name}/{side}/flow_bit_replayed'] = all(
                row['observed'].hex() == row['result']['flow'].hex() for row in rows)
            checks[f'{name}/{side}/closed_flow_zero'] = all(row['observed'] == 0 for row in rows if row['closed'])
            checks[f'{name}/{side}/trachea_dimensions_match'] = bool(
                (trace['trachea_end_area_cm2'] == trachea_area).all()
                and (trace['trachea_end_cell_length_cm'] == trachea_length).all())
            if name == 'no_tracking':
                checks[f'{name}/{side}/no_excitation'] = all((trace[key] == 0).all() for key in (BRONCHUS, TRACHEA, FLOW))
        candidate, upstream = (traces[side] for side in ('candidate', 'upstream'))
        checks[f'{name}/port_area_bit_identical'] = same_bits(candidate[AREA], upstream[AREA])
        offsets = {field: first_offset(candidate[field][start:], upstream[field][start:])
                   for field in (AREA, FLOW, BRONCHUS, TRACHEA)}
        offset = offsets[FLOW]
        checks[f'{name}/matches_previous_flow_offset'] = offset == case['expected_first_flow_offsets'][name]
        results[name] = {'first_differences': offsets, 'closed_points': sum(row['closed'] for row in series['candidate']),
                         'first_flow_residual': diagnose(series['candidate'], series['upstream'], offset, rate,
                                                         pressure_keys=('bronchus_pressure', 'trachea_pressure'))}
        replays[name] = series
    hypotheses = {}
    for name, comparison in results.items():
        first = comparison['first_flow_residual']
        if first is None:
            continue
        candidate, upstream = (first[side]['previous_state'] for side in ('candidate', 'upstream'))
        hypotheses[f'{name}/previous_inputs_bit_identical'] = all(
            candidate[key].hex() == upstream[key].hex()
            for key in ('bronchus_pressure', 'trachea_pressure', 'port_area_cm2', 'previous_flow'))
        hypotheses[f'{name}/time_order_only_restores_flow'] = first['time_order_only']['matches_upstream']
    write(out / 'left-syrinx-port-replay.json', replays)
    return {'checks': checks, 'hypotheses': hypotheses, 'sample_rate_hz': rate, 'window': window, 'conditions': results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    case = read(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    names = tuple(f'artifacts/{name}{suffix}' for name in CONDITIONS
                  for suffix in ('.json', '-interior-momentum.csv', '-upstream.csv'))
    manifest, saved = registered_artifacts(case['baseline'], BASE_ID, revision, names)
    inputs = [CASE, Path(__file__), manifest, *saved.values(), UPPER_NETWORK, UPPER_SONGBIRD,
              UPSTREAM / 'crates/chimera/src/creatures/build.rs', UPSTREAM / 'crates/chimera/tests/airway_adversarial.rs',
              UPSTREAM / 'crates/chimera/tests/denormals.rs',
              *(WORKSPACE / 'crates/vocal-core/src/airway' / filename for filename in ('network.rs', 'songbird.rs')),
              *(WORKSPACE / 'tools' / filename for filename in (
                  'measure_songbird_syrinx.py', 'measure_songbird_chirps_oec_neck_44100.py',
                  'measure_songbird_chirps_beak_load.py', 'measure_songbird_chirps_beak_tip_inflow.py',
                  'measure_songbird_chirps_beak_tip_inflow_44100.py', 'measure_songbird_chirps_terminal_numerator_44100.py',
                  'measure_uniform_tube.py', 'measure_speech_timing.py'))]
    details = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision,
               'analysis_command': [sys.executable, *sys.argv], 'analysis_directory': str(Path.cwd())}
    return record_measurement(args.run_id, CASE, inputs, details, lambda out, execute: measure(case, saved, out, execute),
                              command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
