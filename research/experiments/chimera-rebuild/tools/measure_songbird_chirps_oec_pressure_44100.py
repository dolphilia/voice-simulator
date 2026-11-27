"""鳴禽の口腔食道腔で、体積速度源と枝の流量から節点圧を再計算する。"""

import argparse
import csv
from itertools import combinations
import math
from pathlib import Path
import subprocess
import sys

from measure_songbird_airway import FIELDS, PROBE
from measure_songbird_chirps_beak_load import ROOT, SIDES, DENSITY, SPEED, beak_fields
from measure_songbird_chirps_beak_tip_inflow import UPPER_NETWORK, UPPER_SONGBIRD
from measure_songbird_chirps_beak_tip_inflow_44100 import registered_artifacts
from measure_songbird_syrinx import CLI, load_trace
from measure_speech_timing import read, write
from measure_uniform_tube import build_upstream_probe, candidate_sources, record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE


CASE = WORKSPACE / 'cases/songbird-chirps-oec-pressure-44100.json'
CONDITIONS = ('matched_time', 'native_block', 'no_tracking')
OEC = ('oec_length_cm', 'oec_neck_inflow_cm3_s', 'oec_beak_outflow_cm3_s', 'oec_neck_precedes_beak')
CANDIDATE_OEC = ('oec_filtered_injection_cm3_s', 'oec_compliance_cm5_per_dyn')
VOLUME_FIELDS = ('volume', 'volume_drop', 'raw', 'first_pole', 'injection')
PRESSURE_INPUTS = ('injection', 'neck', 'beak', 'neck_first', 'compliance', 'previous_pressure')


def pressure_step(inputs, dt):
    injection, neck, beak, neck_first, compliance, previous = (inputs[field] for field in PRESSURE_INPUTS)
    balance = (injection + neck) - beak if neck_first else (injection - beak) + neck
    return balance, previous + (dt / compliance) * balance


def observe(trace, start, rate, cutoff, side, *, multiply_volume=False):
    dt = 1 / rate
    angular = math.tau * cutoff
    coefficient = 1 - math.exp(-angular / rate if side == 'upstream' else -angular * dt)
    initial = trace[start - 1]
    length = float(initial['oec_length_cm'])
    volume = float(initial['oec_area_cm2']) * length
    first = second = pressure = 0.0
    result = []
    for offset, row in enumerate(trace[start:]):
        current = float(row['oec_area_cm2']) * length
        drop = volume - current
        raw_divided, raw_multiplied = drop / dt, drop * rate
        raw = raw_multiplied if side == 'upstream' or multiply_volume else raw_divided
        first_before, second_before = first, second
        first += coefficient * (raw - first)
        second += coefficient * (first - second)
        inputs = {'injection': second, 'neck': float(row['oec_neck_inflow_cm3_s']),
                  'beak': float(row['oec_beak_outflow_cm3_s']), 'neck_first': bool(row['oec_neck_precedes_beak']),
                  'compliance': current / (DENSITY * SPEED * SPEED), 'previous_pressure': pressure}
        balance, pressure = pressure_step(inputs, dt)
        result.append({'offset': offset, 'volume': current, 'volume_drop': drop, 'raw': raw,
                       'raw_divided': raw_divided, 'raw_multiplied': raw_multiplied, 'coefficient': coefficient,
                       'first_pole_before': first_before, 'second_pole_before': second_before, 'first_pole': first,
                       **inputs, 'balance': balance, 'pressure': pressure,
                       'observed_pressure': float(row['oec_pressure_dyn_cm2'])})
        volume = current
    return result


def prefix_matches(path, reference, columns):
    with path.open(newline='') as actual, reference.open(newline='') as expected:
        return all(row[:columns] == original for row, original in zip(csv.reader(actual), csv.reader(expected), strict=True))


def first_differences(candidate, upstream):
    fields = (*VOLUME_FIELDS, 'coefficient', 'neck', 'beak', 'compliance', 'balance', 'observed_pressure')
    found = {}
    for left, right in zip(candidate, upstream, strict=True):
        for field in fields:
            if field not in found and left[field] != right[field]:
                found[field] = {'offset': left['offset'], 'candidate': left[field], 'upstream': right[field],
                                'candidate_hex': left[field].hex(), 'upstream_hex': right[field].hex()}
    return found


def substitutions(candidate, upstream, rate):
    dt = 1 / rate
    changed = [key for key in PRESSURE_INPUTS if candidate[key] != upstream[key]]
    observations = []
    for size in range(1, len(changed) + 1):
        for keys in combinations(changed, size):
            swapped = candidate | {key: upstream[key] for key in keys}
            balance, pressure = pressure_step(swapped, dt)
            observations.append({'swapped_inputs': keys, 'balance': balance, 'pressure': pressure,
                                 'pressure_hex': pressure.hex(), 'matches_upstream': pressure == upstream['observed_pressure']})

    alpha = candidate['coefficient']
    first_prior, second_prior = (candidate[key] for key in ('first_pole_before', 'second_pole_before'))
    first = first_prior + alpha * (candidate['raw_multiplied'] - first_prior)
    second = second_prior + alpha * (first - second_prior)
    _, pressure = pressure_step(candidate | {'injection': second}, dt)
    return observations, {'raw_multiplied': candidate['raw_multiplied'], 'filtered_injection': second,
                          'pressure': pressure, 'pressure_hex': pressure.hex(),
                          'matches_upstream': pressure == upstream['observed_pressure']}


def measure(case, files, out, execute):
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera', '--test', 'airway_adversarial',
             '--test', 'creature_realtime'], cwd=UPSTREAM, stdout=out / 'upstream-tests.log')
    execute(['cargo', 'test', '--locked', '--offline', '--workspace'], stdout=out / 'candidate-tests.log')
    probe = build_upstream_probe(PROBE, out, execute, extra_libraries=('serde_json',))
    rate, cutoff = case['sample_rate_hz'], case['volume_source_cutoff_hz']
    baseline = read(files['summary.json'])
    cells = baseline['geometry']['current']['beak_cells']
    columns = FIELDS + beak_fields(cells)
    checks = {'registered_internal_rate': rate == baseline['internal_sample_rate_hz']}
    results, series = {}, {}
    for name in CONDITIONS:
        settings = read(files[f'artifacts/{name}.json'])
        definition = settings['songbird_airway']
        start, = (row['sample'] for row in definition['events'])
        count = start + case['observation_internal_samples']
        if (definition['sample_rate_hz'], definition['control_block_samples'], definition['sample_count'],
                definition['observe_beak']) != (rate, baseline['conditions'][name]['control_block_internal_samples'], count, True):
            raise ValueError('内部レート、制御刻み、観測窓が先行実行と一致しません')
        definition['observe_oec'] = True
        configured = out / f'{name}.json'
        write(configured, settings)
        candidate, upstream = (out / f'{name}-{side}.csv' for side in SIDES)
        execute([*CLI, 'render', str(configured), str(candidate)])
        execute([str(probe), str(configured)], cwd=UPSTREAM, stdout=upstream)
        rows = {}
        for side, path in zip(SIDES, (candidate, upstream), strict=True):
            saved = files[f'artifacts/{path.name}']
            fields = columns + OEC + (CANDIDATE_OEC if side == 'candidate' else ())
            trace = load_trace(path, fields, count)
            checks[f'{name}/{side}/archived_columns_unchanged'] = prefix_matches(path, saved, len(columns))
            before, during = trace[:start], trace[start:]
            checks[f'{name}/{side}/geometry_and_initial_state'] = all((
                bool((trace['oec_length_cm'] == before['oec_length_cm'][-1]).all()),
                bool((before['oec_area_cm2'] == before['oec_area_cm2'][-1]).all()),
                bool((trace['oec_area_cm2'] >= 0.12).all()),
                all(not before[field].any() for field in ('oec_pressure_dyn_cm2', OEC[1], OEC[2])),
                bool((trace[OEC[2]] == trace['beak_0_inflow_cm3_s']).all()),
                bool((trace[OEC[3]] == int(side == 'upstream')).all()),
            ))
            rows[side] = observe(trace, start, rate, cutoff, side)
            checks[f'{name}/{side}/pressure_matches_bitwise'] = all(
                row['pressure'].hex() == row['observed_pressure'].hex() for row in rows[side])
            if side == 'candidate':
                for field, exported in zip(('injection', 'compliance'), CANDIDATE_OEC, strict=True):
                    checks[f'{name}/candidate/{field}_matches_bitwise'] = all(
                        row[field].hex() == float(value).hex()
                        for row, value in zip(rows[side], during[exported], strict=True))
        series[name] = rows
        differences = first_differences(*[rows[side] for side in SIDES])
        first = differences.get('observed_pressure')
        swaps, raw_swap = [], None
        if first is not None:
            swaps, raw_swap = substitutions(*(rows[side][first['offset']] for side in SIDES), rate)
        results[name] = {'event_sample': start, 'first_differences': differences,
                         'pressure_substitutions': swaps, 'raw_conversion_only_replay': raw_swap}

    matched = results['matched_time']['first_differences']
    raw_swap = results['matched_time']['raw_conversion_only_replay']
    checks['matched_time_first_pressure_difference'] = (
        matched.get('observed_pressure', {}).get('offset') == case['matched_time_first_pressure_difference'])
    checks['no_tracking_quiet'] = all(
        all(row[field] == 0.0 for field in ('raw', 'injection', 'neck', 'beak', 'observed_pressure'))
        for rows in series['no_tracking'].values() for row in rows)
    prediction = bool(raw_swap and raw_swap['matches_upstream']
                      and matched.get('raw', {}).get('offset') == matched['observed_pressure']['offset']
                      and 'volume' not in matched)
    write(out / 'oec-pressure-steps.json', series)
    return {'checks': checks, 'hypotheses': {'raw_conversion_alone_explains_matched_time_first_pressure_difference': prediction},
            'sample_rate_hz': rate, 'conditions': results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    case = read(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    names = ['summary.json', *(f'artifacts/{name}.json' for name in CONDITIONS),
             *(f'artifacts/{name}-{side}.csv' for name in CONDITIONS for side in SIDES)]
    baseline, files = registered_artifacts(case['baseline'], 'songbird-chirps-beak-tip-inflow-44100', revision, names)
    inputs = [CASE, Path(__file__), PROBE, baseline, *files.values(), *candidate_sources(),
              *(WORKSPACE / 'tools' / file for file in ('measure_songbird_airway.py', 'measure_songbird_syrinx.py',
                                                        'measure_songbird_chirps_beak_load.py', 'measure_uniform_tube.py',
                                                        'measure_songbird_chirps_beak_tip_inflow_44100.py')),
              UPPER_NETWORK, UPPER_SONGBIRD, UPSTREAM / 'crates/chimera/src/physics.rs',
              UPSTREAM / 'crates/chimera/tests/airway_adversarial.rs', UPSTREAM / 'crates/chimera/tests/creature_realtime.rs']
    details = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision,
               'analysis_command': [sys.executable, *sys.argv], 'analysis_directory': str(Path.cwd())}
    return record_measurement(args.run_id, CASE, inputs, details,
                              lambda out, execute: measure(case, files, out, execute), command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
