"""口腔断面積・セル長を個別に交換し、体積源とPCMへの影響を追う。"""

import argparse
from collections import Counter
from fractions import Fraction
from functools import partial
import json
import math
import os
from pathlib import Path
import subprocess

import numpy as np

import measure_tsp_fk61_control5632_oral_inlet as inlet
import tsp_fk61_oral_geometry_observation as observer


oral, six, load, terminal, radiation, tsp = inlet.oral, inlet.six, inlet.load, inlet.terminal, inlet.radiation, inlet.tsp
lip, pcm = inlet.lip, inlet.pcm
CASE = radiation.WORKSPACE / 'cases/tsp-fk61-control5632-oral-geometry.json'
MODES = inlet.MODES
GEOMETRIES = ((), ('area',), ('length',), ('area', 'length'))
RAMP_FIELDS = {'ramp-target': observer.TARGET_FIELDS, 'ramp-step': observer.STEP_FIELDS}
SAVED_FILES = (*inlet.SAVED_FILES, *(f'{mode}-{tag}.csv' for mode in MODES for tag in RAMP_FIELDS),
               'trajectories.npz')


def split_observations(out, mode, fields_by_tag=RAMP_FIELDS):
    path = out / f'{mode}-nodes.csv'
    rows = {tag: [] for tag in fields_by_tag}
    ordinary = []
    for line in path.read_text().splitlines(keepends=True):
        tag, _, row = line.partition(',')
        if tag in rows:
            rows[tag].append(row)
        else:
            ordinary.append(line)
    path.write_text(''.join(ordinary))
    for tag, grid in rows.items():
        fields = ('sample', 'node', *fields_by_tag[tag])
        (out / f'{mode}-{tag}.csv').write_text(','.join(fields) + '\n' + ''.join(grid))
    terminal.split_capture(out, mode)


def read_targets(path, expected):
    records, hits = {}, Counter()
    header, *lines = path.read_text().splitlines()
    if tuple(header.split(',')) != ('sample', 'node', *observer.TARGET_FIELDS):
        raise ValueError(f'形状目標の観測列が異なります ({path.name})')
    for line in lines:
        sample, node, *values = line.split(',')
        key = (int(sample), int(node))
        hits[key] += 1
        row = dict(zip(observer.TARGET_FIELDS, map(float, values), strict=True))
        if not all(map(math.isfinite, row.values())):
            raise ValueError(f'形状目標に非有限値があります ({path.name}, {key})')
        records[key] = row
    if records.keys() != expected:
        raise ValueError(f'形状目標の観測点が異なります ({path.name})')
    # 接触補正があった制御境界では再設定も保存し、最後の値で検算する。
    return records, {str(count): rows for count, rows in sorted(Counter(hits.values()).items())}


def verify_ramps(data, steps, targets, measure, *, indexed_area=False):
    errors = []
    active = {}
    indexed = {}
    count = measure['control_internal_samples']
    first = measure['comparison_internal_samples'][0]
    for (n, node), before in steps.items():
        after = data['cells'][n, node]
        if target := targets.get((n, node)):
            active[node] = {key: (target[key] - before[key]) * (1 / count)
                            for key in ('area', 'minimum', 'length')}
            if indexed_area and n in measure['area_focus_blocks'] and node in measure['area_focus_nodes']:
                indexed[node] = (n, before['area'])
            else:
                indexed.pop(node, None)
            if target['length'] != target['simulation_length'] / (len(measure['nodes']) - 1):
                errors.append((n, node, 'target_length'))
        if node in active and any(before[f'{key}_step'] != value for key, value in active[node].items()):
            errors.append((n, node, 'increments'))
        area = max(0.0, before['area'] + before['area_step'])
        if node in indexed:
            block_start, start_area = indexed[node]
            area = max(0.0, start_area + (n - block_start + 1) * before['area_step'])
        minimum = min(area, max(0.0, before['minimum'] + before['minimum_step']))
        length = before['length'] + before['length_step']
        if (area, minimum, length) != (after['area_cm2'], after['minimum_cm2'], after['length_cm']):
            errors.append((n, node, 'geometry'))
        if n > first:
            previous = data['cells'][n - 1, node]
            if tuple(before[key] for key in ('area', 'minimum', 'length')) != (
                previous['area_cm2'], previous['minimum_cm2'], previous['length_cm']
            ):
                errors.append((n, node, 'previous_geometry'))
    return errors


def raw_volume(geometry, floor, n, node, selected, *, exact=False):
    area, length = (geometry['upstream' if key in selected else 'trial']['cells'][n, node]
                    for key in ('area', 'length'))
    a, d = max(floor, area['area_cm2']), length['length_cm']
    return Fraction(a) * Fraction(d) if exact else a * d


def source_series(geometry, settings, seeds, nodes, measure, selected, *, fixed):
    first, stop = measure['local_internal_samples']
    rate = measure['internal_sample_rate_hz']
    values = {}
    for node in nodes:
        previous = seeds['cells'][first - 1, node]
        pole1, pole2 = previous['pole1_cm3_s'], previous['pole2_cm3_s']
        volume = raw_volume(geometry, settings['loads'][first]['area_floor'], first - 1, node, selected)
        for n in range(first, stop):
            parameters = settings['loads'][n]
            current = raw_volume(geometry, parameters['area_floor'], n, node, selected)
            difference = volume - current
            raw = difference * rate if fixed else difference / (1 / rate)
            pole1, pole2 = oral.poles(pole1, pole2, parameters['pole_coefficient'], raw)
            values[n, node] = (current, raw, pole1, pole2)
            volume = current
    return values


def source_checks(data, series):
    fields = ('volume_cm3', 'spill_cm3_s', 'pole1_cm3_s', 'pole2_cm3_s')
    return [key for key, row in series.items() if row != tuple(data['cells'][key][field] for field in fields)
            or row[-1] != data['cells'][key]['initial_inflow_cm3_s']]


def exact_effects(geometry, n, node, measure):
    floor = geometry['trial']['loads'][n]['area_floor']
    rate = measure['internal_sample_rate_hz']
    raw = [(raw_volume(geometry, floor, n - 1, node, selected, exact=True)
            - raw_volume(geometry, floor, n, node, selected, exact=True)) * rate for selected in GEOMETRIES]
    orig, area, length, both = raw
    return {'trial_raw': float(orig), 'area': float(area - orig), 'length': float(length - orig),
            'interaction': float(both - area - length + orig), 'combined': float(both - orig)}


def geometry_checkpoints(native, steps, targets, measure):
    focus = measure['focus_node']
    controls = {}
    for n in measure['control_boundaries']:
        pair = (n, focus)
        source_fields = ('anatomical_length', 'simulation_length', 'length', 'area')
        differences = {field: targets['upstream'][pair][field] - targets['trial'][pair][field]
                       for field in source_fields}
        start_fields = ('length', 'length_step', 'area', 'area_step')
        controls[str(n)] = {
            'target_differences': differences,
            'start_differences': {field: steps['upstream'][pair][field] - steps['trial'][pair][field]
                                  for field in start_fields},
            'target_values': {mode: targets[mode][pair] for mode in MODES},
            'pre_step_values': {mode: steps[mode][pair] for mode in MODES},
            'exact_raw_effects_cm3_s': exact_effects(native, n, focus, measure),
            'shared_length_targets': all(len({targets[mode][n, node]['length']
                                              for node in measure['nodes'][1:]}) == 1 for mode in MODES),
        }
    return controls


def analyze(study, out, prior, previous, config, gain, coefficients, proof):
    measure = study['measurement']
    first, stop = measure['comparison_internal_samples']
    nodes = measure['nodes'][1:]
    focus = measure['focus_node']
    geometry = {mode: oral.read_capture(out, mode, measure) for mode in MODES}
    targets, target_counts, steps = {}, {}, {}
    for mode in MODES:
        targets[mode], target_counts[mode] = read_targets(
            out / f'{mode}-ramp-target.csv', {(n, node) for n in measure['control_boundaries'] for node in nodes})
        steps[mode] = terminal.read_records(out / f'{mode}-ramp-step.csv', ('sample', 'node', *observer.STEP_FIELDS), 2,
                                           {(n, node) for n in range(first, stop) for node in nodes})
    upper, trial = geometry['upstream'], geometry['trial']
    ramp_errors = {mode: verify_ramps(geometry[mode], steps[mode], targets[mode], measure) for mode in MODES}
    native = {mode: source_series({'upstream': data, 'trial': data}, data, data, nodes, measure, (), fixed=mode == 'upstream')
              for mode, data in geometry.items()}
    native_errors = {mode: source_checks(geometry[mode], rows) for mode, rows in native.items()}
    restored = source_series(geometry, upper, upper, nodes, measure, GEOMETRIES[-1], fixed=True)
    restored_errors = source_checks(upper, restored)
    baseline = six.replay(trial, measure, False)
    with np.load(prior / 'prefix.npz', allow_pickle=False) as saved:
        prefix = dict(saved)
    conditions, arrays, signed_sources = {}, {}, {}
    for scope, selected_nodes in (('node34', (focus,)), ('nodes28_37', measure['inner_nodes'])):
        for fields in GEOMETRIES:
            sources = source_series(geometry, trial, trial, selected_nodes, measure, fields, fixed=False)
            cells = trial['cells'] | {key: trial['cells'][key] | {'initial_inflow_cm3_s': row[-1]}
                                      for key, row in sources.items()}
            patched = trial | {'cells': cells}
            name = '+'.join(fields) or 'unchanged'
            signed_sources[f'{scope}:{name}'] = {
                str(n): [sources[n, node][-1] - native['trial'][n, node][-1] for node in selected_nodes]
                for n in measure['comparison_samples']}
            for boundary in ('trial', 'upstream'):
                combination = f'{scope}:{name}:{boundary}'
                trajectory = six.replay(patched, measure, False, reference=upper,
                                        groups=('upstream_boundary',) if boundary == 'upstream' else ())
                conditions[combination], arrays[combination] = inlet.condition(
                    trajectory, baseline, measure, prefix, config, gain, coefficients)
    with_upper_raw = source_series(geometry, trial, trial, (focus,), measure, GEOMETRIES[-1], fixed=True)
    with_upper_filter = source_series(geometry, upper, trial, (focus,), measure, GEOMETRIES[-1], fixed=True)
    with_trial_math = source_series(geometry, trial, trial, (focus,), measure, GEOMETRIES[-1], fixed=False)
    residuals = {
        str(n): {
            'volume_and_raw': [with_trial_math[n, focus][i] - restored[n, focus][i] for i in range(2)],
            'trial_all': with_trial_math[n, focus][-1] - restored[n, focus][-1],
            'use_upper_raw_math': with_upper_raw[n, focus][-1] - restored[n, focus][-1],
            'use_upper_filter_settings': with_upper_filter[n, focus][-1] - restored[n, focus][-1],
        }
        for n in measure['comparison_samples']
    }
    controls = geometry_checkpoints(geometry, steps, targets, measure)
    focus_sample = str(measure['witness_interval'][0])
    effect = {field: conditions[f'nodes28_37:{field}:trial']['checkpoints'][focus_sample]['branch37_shift_cm3_s']
              for field in ('area', 'length')}
    matches = [name for name, row in conditions.items() if row['pcm_full_interval']['first_difference_through_focus'] is None]
    hypotheses = {
        'length_targets_differ_at_both_boundaries': all(row['shared_length_targets']
            and row['target_differences']['length'] != 0 for row in controls.values()),
        'length_effect_larger_at_node34_raw': all(abs(row['exact_raw_effects_cm3_s']['length'])
            > abs(row['exact_raw_effects_cm3_s']['area']) for row in controls.values()),
        'length_drives_edge37_more_than_area': abs(effect['length']) > abs(effect['area']),
        'paired_geometry_and_boundary_recover_pcm': 'nodes28_37:area+length:upstream' in matches,
    }
    pcm_fields = ('pcm_two_samples', 'pcm_full_interval')
    checks = {
        'ordinary_cli_and_shared_observations_match': proof == tsp.read(prior / 'pcm-digests.json')
            and all(voice['bit_equal'] and voice['ordinary']['frames'] == measure['frames'] for voice in proof.values())
            and all(tsp.sha256(out / name) == tsp.sha256(prior / name) for name in inlet.SAVED_FILES),
        'targets_and_native_ramps_replayed': not any(ramp_errors.values()),
        'native_and_exchanged_volume_sources_replayed': not any(native_errors.values()) and not restored_errors,
        'registered_exchanges_and_native_pcm_replayed': len(conditions) == 16 and all(
            conditions[f'{scope}:unchanged:trial'][key] == previous['conditions'][0][key]
            for scope in ('node34', 'nodes28_37') for key in pcm_fields),
    }
    return {'checks': checks, 'hypotheses': hypotheses, 'target_counts': target_counts, 'ramp_errors': ramp_errors,
            'native_errors': native_errors, 'restored_errors': restored_errors, 'controls': controls,
            'source_residuals': residuals, 'signed_source_shifts': signed_sources,
            'matching_conditions': matches, 'conditions': conditions}, arrays | {
                'internal_sample': np.arange(measure['local_internal_samples'][0], stop),
                'columns': np.asarray((*six.TRAJECTORY_FIELDS, 'flow27_28', 'flow37_38'))}


def filter_initial_state_control(study, artifacts, prior, config, gain, coefficients):
    """全形状交換でも残る差を、演算と平滑器の開始状態に分ける。"""
    measure = study['measurement']
    geometry = {mode: oral.read_capture(artifacts, mode, measure) for mode in ('upstream', 'trial')}
    upper, trial = geometry['upstream'], geometry['trial']
    baseline = six.replay(trial, measure, False)
    with np.load(prior / 'prefix.npz', allow_pickle=False) as saved:
        prefix = dict(saved)
    focus = str(measure['witness_interval'][0])
    results = {}
    for arithmetic, settings in geometry.items():
        for seed, initial in geometry.items():
            flow = source_series(geometry, settings, initial, measure['inner_nodes'], measure, GEOMETRIES[-1],
                                 fixed=arithmetic == 'upstream')
            cells = trial['cells'] | {key: trial['cells'][key] | {'initial_inflow_cm3_s': row[-1]}
                                      for key, row in flow.items()}
            trajectory = six.replay(trial | {'cells': cells}, measure, False, reference=upper,
                                    groups=('upstream_boundary',))
            row, _ = inlet.condition(trajectory, baseline, measure, prefix, config, gain, coefficients)
            results[f'{arithmetic}:{seed}'] = {**row['checkpoints'][focus], **row['pcm_full_interval']}
    return results


def run_registered(run_id, case_path, *, analyze_run=analyze, prepare_run=observer.prepare,
                   split_run=split_observations, retained_files=inlet.SAVED_FILES, extra_inputs=()):
    ws, upper = radiation.WORKSPACE, radiation.UPSTREAM
    study = tsp.read(case_path)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=upper, text=True).strip()
    if revision != study['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=upper):
        raise SystemExit('変更のない固定上流版が必要です')
    if os.environ.get('CHIMERA_RUN_STORAGE') != 'rtl9210b':
        raise SystemExit('試験ビルドにCHIMERA_RUN_STORAGE=rtl9210bを指定してください')
    matched, bernstein, output, previous = (tsp.open_run(study[key], revision) for key in
                                            ('matched', 'bernstein', 'coefficients', 'previous_focus'))
    uid = study['measurement']['recording_id']
    spec = tsp.verified_path(matched, f'artifacts/{uid}/matched-case.json')
    config, config_path = radiation.saved_case(matched, lip.CONFIG)
    reference = tsp.verified_path(matched, 'artifacts/matched-pcm.npz')
    trial = tsp.verified_path(bernstein, 'artifacts/render.npz')
    coefficients = tsp.verified_path(output, 'artifacts/coefficients.json')
    summary = tsp.verified_path(previous, 'summary.json')
    retained = [tsp.verified_path(previous, f'artifacts/{name}') for name in retained_files]
    dependencies = ('measure_tsp_fk61_control5632_mouth_flow.py', 'measure_tsp_fk61_control5632_upstream_drive.py',
                    'measure_tsp_fk61_control5632_oral_inlet.py', 'measure_tsp_fk61_oral_onset_inflow.py',
                    'measure_tsp_fk61_pcm2937_branch_drive.py', 'measure_tsp_fk61_pcm2937_terminal_load.py',
                    'measure_tsp_fk61_lip_front_radiation.py', 'measure_tsp_fk61_lip_front_terminal_branch.py',
                    'measure_tsp_fk61_node42_volume_source.py',
                    'measure_tsp_fk61_lip_onset.py', 'tsp_fk61_terminal_branch_observation.py',
                    'tsp_fk61_lip_front_radiation_observation.py', 'tsp_fk61_lip_observation.py',
                    'tsp_fk61_lower_lip_bernstein_observation.py', 'measure_fixed_voice_glottal_branch.py',
                    'measure_fixed_voice_release_lip_load.py', 'measure_fixed_voice_radiation_balance.py',
                    'measure_tsp_fk61_pcm_first_difference.py', 'measure_tsp_fine_variation.py',
                    'measure_uniform_tube.py', 'tsp_fk61_oral_geometry_observation.py')
    upstream_sources = ('Cargo.lock', 'crates/chimera/src/airway/network.rs', 'crates/chimera/src/voice/human_airway.rs',
                        'crates/chimera/src/voice/human_voice.rs', 'crates/chimera/src/anatomy/human.rs',
                        'crates/chimera/tests/airway.rs', 'crates/chimera/tests/airway_adversarial.rs')
    inputs = [case_path, Path(__file__).resolve(), config_path, spec, reference, trial, coefficients, summary, *retained,
              *(row[0] / 'manifest.json' for row in (matched, bernstein, output, previous)),
              *radiation.candidate_sources(), lip.EMBEDDED_DICTIONARY, lip.DICT, lip.LOCAL, lip.PROBE,
              lip.TRACE_TOOL, lip.OUTPUT_PATCH, lip.SOURCE_PATCH, lip.observer.LOCAL_PATCH, lip.observer.UPPER_PATCH,
              ws / 'data/cmudict.txt.gz', ws / 'crates/vocal-core/tests/geometry_ramp.rs',
              *(ws / 'tools' / name for name in dependencies), *(upper / name for name in upstream_sources),
              *extra_inputs]

    def measure(out, execute):
        archived = pcm.archived_pcm(reference, uid)
        with np.load(trial, allow_pickle=False) as stored:
            archived['trial'] = stored['pcm']
        _, proof = lip.capture(study, spec, config, archived, out, execute, trial_patch=load.patch_trial,
                               prepare=partial(prepare_run, measure=study['measurement']), retain_prefix=True)
        for mode in MODES:
            split_run(out, mode)
        (out / 'pcm-digests.json').write_text(json.dumps(proof, indent=2) + '\n')
        gain = tsp.read(spec)['speech_voice']['voice']['output_gain']
        report, arrays = analyze_run(study, out, previous[0] / 'artifacts', tsp.read(summary), config, gain,
                                     tsp.read(coefficients), proof)
        np.savez_compressed(out / 'trajectories.npz', **arrays)
        return report

    details = {'case_id': study['id'], 'case_revision': study['revision'], 'upstream_revision': revision}
    return radiation.record_measurement(run_id, case_path, inputs, details, measure, command=None,
                                        input_root=ws.parents[2])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    return run_registered(parser.parse_args().run_id, CASE)


if __name__ == '__main__':
    raise SystemExit(main())
