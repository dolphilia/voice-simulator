"""発話冒頭の節点42で体積速度が分かれる演算を照合する。"""

import argparse
from collections import defaultdict
import csv
from fractions import Fraction
import json
import math
import os
from pathlib import Path
import subprocess

import numpy as np

import measure_tsp_fk61_lip_front_terminal_branch as terminal
import tsp_fk61_node_volume_observation as observer


radiation, tsp, lip, pcm = terminal.radiation, terminal.tsp, terminal.lip, terminal.pcm
CASE = radiation.WORKSPACE / 'cases/tsp-fk61-node42-volume-source.json'
MODES = terminal.MODES


def split_capture(out, mode):
    path = out / f'{mode}-nodes.csv'
    text = defaultdict(list)
    for line in path.read_text().splitlines(keepends=True):
        tag, _, row = line.partition(',')
        if tag in observer.FIELDS:
            text[tag].append(row)
        else:
            text['nodes'].append(line)
    path.write_text(''.join(text['nodes']))
    for tag, fields in observer.FIELDS.items():
        (out / f'{mode}-{tag}.csv').write_text(','.join(fields) + '\n' + ''.join(text[tag]))


def read_capture(out, mode, measure):
    start, stop = measure['comparison_internal_samples']
    cells = radiation.read_nodes(out / f'{mode}-nodes.csv', start, stop)
    count = cells['node'].shape[1]
    geometry = terminal.read_records(out / f'{mode}-geometry.csv', observer.FIELDS['geometry'], 2,
                                     {(n, i) for n in range(start, stop) for i in range(count)})
    sparse = {}
    for tag in ('neighbor', 'raw', 'routed'):
        path = out / f'{mode}-{tag}.csv'
        rows = {}
        with path.open(newline='') as file:
            reader = csv.reader(file)
            if tuple(next(reader)) != observer.FIELDS[tag]:
                raise ValueError(f'体積観測の列が不正です ({path.name})')
            for line in reader:
                if len(line) != len(observer.FIELDS[tag]):
                    raise ValueError(f'体積観測の列が不正です ({path.name}, {line})')
                n, i, *values = map(float, line)
                key = (n, i, values[0]) if tag == 'routed' else (n, i)
                if n not in range(start, stop) or i not in range(count) or not all(map(math.isfinite, values)):
                    raise ValueError(f'体積観測の番号か値が不正です ({path.name}, {line})')
                if tag == 'neighbor':
                    other, = values
                    adjacent = rows.setdefault(int(i), [])
                    if n != start or other not in range(count) or other == i or other in adjacent:
                        raise ValueError(f'近隣表の対応が不正です ({path.name}, {line})')
                    adjacent.append(int(other))
                else:
                    if key in rows:
                        raise ValueError(f'体積観測が重複しています ({path.name}, {line})')
                    rows[key] = values[-1]
        sparse[tag] = rows
    return cells, geometry, sparse


def dimensions(row):
    if not row['advances']:
        return row['area'], row['minimum'], row['length'], row['volume']
    area = max(0.0, row['area'] + row['area_step'])
    minimum = min(area, max(0.0, row['minimum'] + row['minimum_step']))
    length = row['length'] + row['length_step']
    return area, minimum, length, max(area, row['area_floor']) * length


def replay(rows, neighbors, rate, fixed, overrides=None):
    """各節点を番号順に更新し、配分時の近隣断面をその時点の値で読む。"""
    before = [row['minimum'] for row in rows]
    spill = [0.0] * len(rows)
    raw, routes, evolved = {}, {}, []
    for i, row in enumerate(rows):
        area, minimum, length, volume = dimensions(row)
        evolved.append((area, minimum, length, volume))
        before[i] = minimum
        if not (row['enabled'] and row['advances']):
            continue
        change = row['volume'] - volume
        flow = change * rate if fixed else change / (1 / rate)
        raw[i] = flow
        if overrides is not None:
            flow = overrides.get(i, flow)
        threshold = row['squeeze']
        if flow == 0.0 or minimum >= threshold:
            spill[i] += flow
            continue
        ratio = minimum / threshold
        keep = ratio * ratio * (3.0 - 2.0 * ratio)
        spill[i] += flow * keep
        receivers = [j for j in neighbors.get(i, ()) if
                     before[j] >= threshold or rows[j]['target_minimum'] >= threshold]
        if receivers:
            share = flow * (1.0 - keep) / len(receivers)
            for j in receivers:
                spill[j] += share
                routes[i, j] = share
    return evolved, raw, spill, routes


def poles(old_first, old_second, coefficient, spill):
    first = old_first + coefficient * (spill - old_first)
    second = old_second + coefficient * (first - old_second)
    return first, second


def rebuild(measure, fixed, capture):
    start, stop = measure['comparison_internal_samples']
    clock = measure['internal_sample_rate_hz']
    cells, geometry, sparse = capture
    count = cells['node'].shape[1]
    rows, observed = {}, {}
    mismatches = []
    raw, routed = {}, {}
    columns = ('area_cm2', 'minimum_cm2', 'length_cm', 'volume_cm3')
    for i, n in enumerate(range(start, stop)):
        rows[n] = [geometry[n, j] for j in range(count)]
        evolved, actual, spill, routes = replay(rows[n], sparse['neighbor'], clock, fixed)
        raw.update({(n, j): value for j, value in actual.items()})
        routed.update({(n, *edge): value for edge, value in routes.items()})
        observed[n] = {'raw': actual, 'spill': spill, 'routes': routes}
        for j, row in enumerate(rows[n]):
            first, second = poles(row['old_first'], row['old_second'], row['coefficient'], spill[j])
            after = tuple(float(cells[field][i, j]) for field in columns)
            measured = tuple(float(cells[field][i, j]) for field in
                             ('old_volume_cm3', 'spill_cm3_s', 'pole1_cm3_s', 'pole2_cm3_s', 'geometry_enabled'))
            expected = (row['volume'], spill[j], first, second, row['enabled'])
            if after != evolved[j] or measured != expected:
                mismatches.append({'sample': n, 'node': j, 'observed': [*after, *measured],
                                   'calculated': [*evolved[j], *expected]})
    return rows, observed, mismatches, {'raw': raw == sparse['raw'], 'routed': routed == sparse['routed']}


def exact_flow(row, clock):
    area, _, length, _ = dimensions(row)
    past = Fraction(max(row['area_floor'], row['area'])) * Fraction(row['length'])
    present = Fraction(max(row['area_floor'], area)) * Fraction(length)
    return float((past - present) * clock)


def focused_events(measure, rows, actual):
    node, clock = (measure[k] for k in ('focus_node', 'internal_sample_rate_hz'))
    events = []
    for n in range(*measure['local_internal_samples']):
        row = rows[n][node]
        _, _, _, volume = dimensions(row)
        change = row['volume'] - volume
        exact_subtraction = Fraction(row['volume']) - Fraction(volume)
        incoming = {str(i): flow for (i, j), flow in actual[n]['routes'].items() if j == node}
        spill = actual[n]['spill'][node]
        first, second = poles(row['old_first'], row['old_second'], row['coefficient'], spill)
        events.append({'sample': n, 'old_volume_cm3': row['volume'], 'volume_cm3': volume,
                       'volume_change_cm3': change, 'subtraction_exact': Fraction(change) == exact_subtraction,
                       'raw_cm3_s': actual[n]['raw'][node], 'times_rate_cm3_s': change * clock,
                       'divide_dt_cm3_s': change / (1 / clock),
                       'difference_of_exact_products_cm3_s': exact_flow(row, clock),
                       'incoming_cm3_s_by_node': incoming, 'spill_cm3_s': spill,
                       'first_pole_cm3_s': first, 'second_pole_cm3_s': second})
    return events


def local_output(measure, config, gain, coefficients, prefix, terminal_run, rows, neighbors, focus):
    node, frame, clock = (measure[key] for key in ('focus_node', 'trial_first_pcm_frame', 'internal_sample_rate_hz'))
    start, stop = measure['local_internal_samples']
    witness = measure['mouth_witness_sample']
    trial = terminal.read_mode(terminal_run, 'trial', measure)
    upstream = terminal.read_mode(terminal_run, 'upstream', measure)
    a = {value['sample']: value for value in focus['upstream']}
    raw = {n: value['raw_cm3_s'] for n, value in a.items()}
    conditions = {'native': {}, 'focus_raw': {measure['focus_sample']: raw[measure['focus_sample']]},
                  'raw_series': raw, 'exact_product_trial': {n: exact_flow(rows[n][node], clock) for n in raw}}
    components = dict(zip(radiation.FIELDS, prefix['trial_source'].T, strict=True))
    baseline = prefix['upstream_pcm'][:frame + 1]
    results = {}
    for name, replacement in conditions.items():
        event = trial.copy()
        first, second = rows[start][node]['old_first'], rows[start][node]['old_second']
        filtered = []
        for n in range(start, stop):
            overrides = {node: replacement[n]} if n in replacement else None
            _, _, spill, _ = replay(rows[n], neighbors, clock, False, overrides)
            first, second = poles(first, second, rows[n][node]['coefficient'], spill[node])
            filtered.append(second)
            prior = trial[n]['nodes']
            event[n] = trial[n] | {'nodes': [prior[0] | {'initial_inflow_cm3_s': second}, prior[1]]}
        predicted = terminal.model(event, measure, False)
        flow = components['lip_cm3_s'].copy()
        flow[start:stop] = [value['lip_flow'] for value in predicted.values()]
        _, derivative = radiation.radiation_from_components(components | {'lip_cm3_s': flow}, clock, False)
        stages, samples = pcm.replay(derivative, coefficients['candidate'], gain, config)
        results[name] = {'injection42_cm3_s': filtered, 'mouth_at_witness_cm3_s': float(flow[witness]),
                         'mouth_error_cm3_s': float(flow[witness] - upstream[witness]['load']['lip_flow']),
                         'first_pcm_difference_through_frame': radiation.signal_difference(
                             baseline, samples[:frame + 1])['first_unequal_sample'],
                         'dc_removed_at_frame': float(stages[frame, 2]),
                         'replays_trial_injections': filtered == [trial[n]['nodes'][0]['initial_inflow_cm3_s']
                                                                  for n in range(start, stop)],
                         'replays_trial_mouth': np.array_equal(flow, components['lip_cm3_s'])}
    return results


def analyze(study, config, gain, coefficients, out, prior, proof):
    measure = study['measurement']
    focus, findings = {}, {}
    captures = {mode: read_capture(out, mode, measure) for mode in MODES}
    rows_by_mode = {}
    for mode in MODES:
        rows, observed, mismatches, checks = rebuild(measure, mode == 'upstream', captures[mode])
        rows_by_mode[mode] = rows
        findings[mode] = {'mismatches': mismatches, **checks, 'routing_assignments': len(captures[mode][2]['routed'])}
        focus[mode] = focused_events(measure, rows, observed)
    a, b = focus['upstream'], focus['trial']
    keys = ('old_volume_cm3', 'volume_cm3', 'volume_change_cm3', 'raw_cm3_s',
            'spill_cm3_s', 'first_pole_cm3_s', 'second_pole_cm3_s')
    first = {key: next((x['sample'] for x, y in zip(a, b, strict=True) if x[key] != y[key]), None) for key in keys}
    idx = measure['focus_sample'] - measure['onset_sample']
    x, y = a[idx], b[idx]
    exact_delta = y['difference_of_exact_products_cm3_s'] - x['difference_of_exact_products_cm3_s']
    native_delta = y['raw_cm3_s'] - x['raw_cm3_s']
    equal = all((out / key).read_bytes() == (prior / key).read_bytes() for key in terminal.RETAINED)
    with np.load(out / 'prefix.npz', allow_pickle=False) as prefix:
        interventions = local_output(measure, config, gain, coefficients, prefix, prior, rows_by_mode['trial'],
                                     captures['trial'][2]['neighbor'], focus)
    normal = interventions['native']
    return {
        'checks': {
            'ordinary_probe_and_saved_pcm_match': proof == tsp.read(prior / 'pcm-digests.json')
                and all(row['bit_equal'] and row['ordinary'] == row['archived'] == row['probe'] for row in proof.values()),
            'prior_nodes_lip_and_output_match': equal,
            'all_geometry_volume_and_poles_replayed': all(not result['mismatches'] and result['raw']
                                                         for result in findings.values()),
            'neighbor_routing_replayed': all(result['routed'] for result in findings.values()),
            'local_volume_filter_and_output_replayed': normal['replays_trial_injections'] and normal['replays_trial_mouth']
                and normal['first_pcm_difference_through_frame'] == measure['trial_first_pcm_frame']
                and len(interventions) == 4,
        },
        'predictions': {
            'first_difference_is_local_volume_subtraction': first['raw_cm3_s'] == first['volume_change_cm3']
                == measure['focus_sample'] and x['times_rate_cm3_s'] != y['times_rate_cm3_s'],
            'no_incoming_spill_at_focus': all(not value['incoming_cm3_s_by_node']
                and value['raw_cm3_s'] == value['spill_cm3_s'] for mode in (a, b) for value in mode[:idx + 1]),
            'exact_volume_math_reduces_focus_residual': abs(exact_delta) < abs(native_delta),
            'raw_series_swap_recovers_pcm': interventions['raw_series']['first_pcm_difference_through_frame'] is None,
        },
        'replay': findings, 'focus': focus, 'first_trial_difference': first,
        'focus_raw_error_cm3_s': {'native': native_delta, 'exact_products': exact_delta},
        'output_interventions': interventions,
    }


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
    front, output, matched, prior = (tsp.open_run(study[key], revision) for key in ('front', 'output', 'matched', 'terminal'))
    config, config_path = radiation.saved_case(matched, lip.CONFIG)
    uid = study['measurement']['recording_id']
    spec = tsp.verified_path(matched, f'artifacts/{uid}/matched-case.json')
    pcm_input = tsp.verified_path(matched, 'artifacts/matched-pcm.npz')
    trial_pcm = tsp.verified_path(front, 'artifacts/trial-pcm.npz')
    coefficients = tsp.verified_path(output, 'artifacts/coefficients.json')
    saved = [*terminal.RETAINED, 'pcm-digests.json',
             *(f'{mode}-{tag}.csv' for mode in ('upstream', 'trial') for tag in terminal.observer.FIELDS)]
    previous = [tsp.verified_path(prior, f'artifacts/{name}') for name in saved]
    inputs = [CASE, Path(__file__).resolve(), Path(observer.__file__), Path(terminal.__file__),
              config_path, spec, pcm_input, trial_pcm, coefficients, *previous,
              *(run[0] / 'manifest.json' for run in (front, output, matched, prior)), *radiation.candidate_sources(),
              lip.EMBEDDED_DICTIONARY, lip.DICT, lip.LOCAL, lip.PROBE, lip.TRACE_TOOL, lip.OUTPUT_PATCH, lip.SOURCE_PATCH,
              lip.observer.LOCAL_PATCH, lip.observer.UPPER_PATCH, ws / 'data/cmudict.txt.gz',
              ws / 'crates/vocal-core/tests/geometry_ramp.rs',
              *(ws / 'tools' / name for name in ('tsp_fk61_lip_front_observation.py', 'tsp_fk61_lip_observation.py',
                 'tsp_fk61_lip_front_radiation_observation.py', 'tsp_fk61_terminal_branch_observation.py',
                 'measure_tsp_fk61_lip_onset.py', 'measure_tsp_fk61_lip_front_radiation.py',
                 'measure_fixed_voice_glottal_branch.py', 'measure_fixed_voice_radiation_balance.py',
                 'measure_fixed_voice_release_lip_load.py', 'measure_tsp_fk61_pcm_first_difference.py',
                 'measure_tsp_fine_variation.py', 'measure_uniform_tube.py')),
              *(upper / name for name in ('Cargo.lock', 'crates/chimera/src/airway/network.rs',
                 'crates/chimera/src/voice/human_voice.rs', 'crates/chimera/tests/airway.rs',
                 'crates/chimera/tests/airway_adversarial.rs'))]

    def measure(out, execute):
        arch = pcm.archived_pcm(pcm_input, uid) | {'trial': radiation.read_trial(trial_pcm)}
        _, proof = lip.capture(study, spec, config, arch, out, execute, trial_patch=radiation.apply_trial,
                               prepare=observer.prepare, retain_prefix=True)
        (out / 'pcm-digests.json').write_text(json.dumps(proof, indent=2) + '\n')
        for mode in MODES:
            split_capture(out, mode)
        gain = tsp.read(spec)['speech_voice']['voice']['output_gain']
        return analyze(study, config, gain, tsp.read(coefficients), out, prior[0] / 'artifacts', proof)

    info = {'case_id': study['id'], 'case_revision': study['revision'], 'upstream_revision': revision}
    return radiation.record_measurement(args.run_id, CASE, inputs, info, measure, command=None, input_root=ws.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
