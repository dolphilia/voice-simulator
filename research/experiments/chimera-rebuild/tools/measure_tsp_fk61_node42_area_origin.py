"""口端の一つ手前のセルで測定線から補間までの面積差を調べる。"""

import argparse
import csv
from fractions import Fraction
from itertools import combinations
import os
from pathlib import Path
import subprocess

import numpy as np

import measure_tsp_fk61_lip_front_origin as front
import tsp_fk61_node42_area_observation as observer
from measure_tsp_fk61_lip_onset import pcm_digest
from measure_tsp_fk61_lip_front_radiation import read_trial


area, tsp = front.area, front.tsp
CASE = front.WORKSPACE / 'cases/tsp-fk61-node42-area-origin.json'
TERMS = ('bounds', 'ray_positions', 'ray_areas')
GEOMETRY_AXES = ('area', 'minimum', 'length')


def contributions(row, index):
    result = area.resample(row, row['grid'], index_from_end=index)
    subareas = [site['area_cm2'] for site in result['midpoints']]
    exact = Fraction(8) / sum(1 / Fraction(a) for a in subareas)
    result['exact_harmonic_cm2'] = float(exact)
    result['inverse_areas_cm2_inverse'] = [1.0 / a for a in subareas]
    return result


def interventions(upstream, trial, index):
    upper = contributions(upstream, index)
    original = contributions(trial, index)
    ref = upper['cell'][0]
    reports = []
    for size in range(len(TERMS) + 1):
        for subset in combinations(TERMS, size):
            bounds = upstream if 'bounds' in subset else trial
            positions = upstream if 'ray_positions' in subset else trial
            averages = upstream if 'ray_areas' in subset else trial
            grid = [(s[0], a[1]) for s, a in zip(positions['grid'], averages['grid'], strict=True)]
            model = area.resample(bounds, grid, index_from_end=index)
            reports.append({'terms': list(subset), 'cell_cm2': model['cell'], 'mean_error_cm2': model['cell'][0] - ref})
    individual = []
    rays = sorted(set(upper['rays_used']) | set(original['rays_used']))
    for i in rays:
        grid = [(row[0], upstream['grid'][j][1] if i == j else row[1]) for j, row in enumerate(trial['grid'])]
        model = area.resample(trial, grid, index_from_end=index)
        individual.append({'ray': i, 'cell_cm2': model['cell'], 'mean_error_cm2': model['cell'][0] - ref})
    return {'combinations': reports, 'single_area': individual,
            'rays': {str(i): {name: row['grid'][i][:2] for name, row in (('upstream', upstream), ('trial', trial))}
                     for i in rays}}


def ramp(start, target, count):
    inc = [(new - old) * (1 / count) for old, new in zip(start, target, strict=True)]
    current = start.copy()
    states = []
    for _ in range(count):
        mean = max(0.0, current[0] + inc[0])
        minimum = min(mean, max(0.0, current[1] + inc[1]))
        current = [mean, minimum, current[2] + inc[2]]
        states.append(current)
    return inc, states


def read_ramp(path, measure):
    with path.open(newline='') as file:
        rows = {int(row['sample']): {key: float(value) for key, value in row.items()}
                for row in csv.DictReader(file) if float(row['node']) == measure['focus_node']}
    start, stop = measure['comparison_internal_samples']
    if list(rows) != list(range(start, stop)):
        raise ValueError(f'前回の断面観測に欠測があります ({path.name})')
    return rows


def ramp_checks(mode, measure, frames, prior):
    onset, count = (measure[key] for key in ('onset_sample', 'ramp_internal_samples'))
    output_frame = onset // 2
    start = frames[output_frame]['before_lip']['current']
    target = frames[output_frame + 1]['before_lip']['target']
    inc, states = ramp(start, target, count)
    _, stop = measure['comparison_internal_samples']
    mismatch = []
    for n in range(onset, stop):
        old = start if n == onset else states[n - onset - 1]
        current = states[n - onset]
        observed = prior[n]
        predicted = {f'{key}_step': step for key, step in zip(GEOMETRY_AXES, inc, strict=True)}
        predicted.update(zip(GEOMETRY_AXES, old, strict=True))
        floor = observed['area_floor']
        predicted['volume'] = max(old[0], floor) * old[2]
        if any(observed[key] != value for key, value in predicted.items()):
            mismatch.append({'sample': n, 'predicted': predicted,
                             'observed': {k: observed[k] for k in predicted}})
        if n + 1 < stop and [prior[n + 1][key] for key in GEOMETRY_AXES] != current:
            mismatch.append({'sample': n, 'end': current, 'observed_after': [prior[n + 1][key] for key in GEOMETRY_AXES]})
    sanity = {
        'registered_target_matches': target == frames[output_frame + 1]['before_lip']['limited'] + [target[2]],
        'frame1985_matches_two_steps': states[1] == frames[output_frame + 1]['before_lip']['current'],
        'end_frame_matches_full_ramp': states[-1] == frames[(onset + count) // 2]['before_lip']['current'],
    }
    rate = measure['internal_sample_rate_hz']
    old, new = (max(values[0], prior[onset]['area_floor']) * values[2] for values in states[:2])
    raw = (old - new) * rate if mode == 'upstream' else (old - new) / (1 / rate)
    return {'start': start, 'target': target, 'increments': inc, 'frame_end': states[-1],
            'raw_at_onset_plus_one_cm3_s': raw, 'mismatch': mismatch, 'checks': sanity}


def area_ramp_swaps(compare, measure, floor):
    upper, trial = (compare[name] for name in ('upstream', 'trial'))
    ref = upper['raw_at_onset_plus_one_cm3_s']
    rate, count = (measure[key] for key in ('internal_sample_rate_hz', 'ramp_internal_samples'))
    outcomes = {}
    for name, picks in (('native', ()), ('start_area', ('start',)), ('target_area', ('target',)),
                        ('start_and_target_area', ('start', 'target'))):
        start, target = ([(upper if field in picks else trial)[field][0], *trial[field][1:]]
                         for field in ('start', 'target'))
        _, state = ramp(start, target, count)
        old, new = (max(values[0], floor) * values[2] for values in state[:2])
        raw = (old - new) / (1 / rate)
        outcomes[name] = {'flow_cm3_s': raw, 'error_cm3_s': raw - ref, 'area_at_focus': [row[0] for row in state[:2]]}
    return outcomes


def analyze(study, snapshots, prior, previous, proof, prior_proof, trial_pcm, volume_summary):
    m = study['measurement']
    index = m['oral_cells_from_end']
    expected = previous['upstream']
    prior_snapshots_match = all({k:v for k,v in snapshots[name][frame].items() if k != 'before_lip'} == previous[name][frame]
                               for name in front.MODES for frame in expected)
    all_frames, comparisons = {}, {}
    for frame in m['completed_frames']:
        current = {name: snapshots[name][frame] for name in front.MODES}
        all_frames[str(frame)] = {
            name: {'native': row['before_lip'], **contributions(row, index)} for name, row in current.items()}
        comparisons[str(frame)] = interventions(current['upstream'], current['trial'], index)
    replayed = [row for frame in all_frames.values() for row in frame.values()]
    models = {name: ramp_checks(name, m, snapshots[name], prior[name]) for name in front.MODES}
    onset = m['onset_sample']
    raw_counterfactuals = area_ramp_swaps(models, m, prior['trial'][onset]['area_floor'])
    start_effects = {tuple(row['terms']): abs(row['mean_error_cm2']) for row in comparisons['0']['combinations']}
    by_ray = {row['ray']: abs(row['mean_error_cm2']) for row in comparisons['0']['single_area']}
    known_raw = {name: volume_summary['focus'][name][1]['raw_cm3_s'] for name in front.MODES}
    checks = {
        'normal_observed_pcm_and_saved_pcm_match': proof == prior_proof
            and all(proof[name]['ordinary_equal'] for name in front.MODES)
            and proof['trial']['probe'] == pcm_digest(trial_pcm),
        'prior_geometry_and_cell_index_match': prior_snapshots_match and all(
            row['native']['node'] == m['focus_node'] and
            row['native']['index'] == snapshots['upstream'][0]['oral_cells'] - index for row in replayed),
        'all_resampling_and_target_registration_replayed': all(
            row['native']['raw'] == row['cell'] and row['native']['limited'] == row['native']['target'][:2]
            for row in replayed),
        'all_ramp_steps_and_retained_geometry_replayed': all(
            not row['mismatch'] and all(row['checks'].values()) and row['raw_at_onset_plus_one_cm3_s'] == known_raw[name]
            for name, row in models.items()),
        'counterfactuals_retained': all(len(result['combinations']) == 8 and result['single_area']
                                        for result in comparisons.values())
            and raw_counterfactuals['native']['flow_cm3_s'] == known_raw['trial'],
    }
    return {
        'checks': checks,
        'predictions': {
            'same_support_at_focus': all(row['rays_used'] == [42, 43, 44, 45] for frame in ('0', '1985')
                                         for row in all_frames[frame].values()),
            'difference_precedes_rate_limit': all(row['native']['raw'] == row['native']['limited']
                for frame in ('0', '1985') for row in all_frames[frame].values())
                and all(all_frames[frame]['upstream']['cell'] != all_frames[frame]['trial']['cell']
                        for frame in ('0', '1985')),
            'ray_areas_dominate_initial_residual': start_effects[('ray_areas',)] < min(
                start_effects[('bounds',)], start_effects[('ray_positions',)], start_effects[()]),
            'ray43_most_effective_single_area': by_ray.get(43, float('inf')) == min(by_ray.values()),
        },
        'frames': all_frames, 'resampling_interventions': comparisons, 'ramp': models,
        'ramp_area_interventions': raw_counterfactuals,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    ws, upper = front.WORKSPACE, front.UPSTREAM
    study = tsp.read(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=upper, text=True).strip()
    if revision != study['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=upper):
        parser.error('変更のない固定上流版が必要です')
    if os.environ.get('CHIMERA_RUN_STORAGE') != 'rtl9210b':
        parser.error('試験ビルドにCHIMERA_RUN_STORAGE=rtl9210bを指定してください')
    front_run, volume_run, matched = (tsp.open_run(study[key], revision) for key in ('front', 'volume', 'matched'))
    config, config_path = front.saved_case(matched, front.CONFIG)
    uid = study['measurement']['recording_id']
    spec = tsp.verified_path(matched, f'artifacts/{uid}/matched-case.json')
    pcm_input = tsp.verified_path(matched, 'artifacts/matched-pcm.npz')
    trial_pcm = tsp.verified_path(front_run, 'artifacts/trial-pcm.npz')
    proof = tsp.verified_path(front_run, 'artifacts/pcm-digests.json')
    volume_summary = tsp.verified_path(volume_run, 'summary.json')
    previous = {name: tsp.verified_path(front_run, f'artifacts/{name}.jsonl') for name in front.MODES}
    geometry = {name: tsp.verified_path(volume_run, f'artifacts/{name}-geometry.csv') for name in front.MODES}
    inputs = [CASE, Path(__file__).resolve(), Path(observer.__file__), Path(front.__file__), Path(area.__file__),
              config_path, spec, pcm_input, trial_pcm, proof, volume_summary, *previous.values(), *geometry.values(),
              *(run[0] / 'manifest.json' for run in (front_run, volume_run, matched)), *front.candidate_sources(),
              front.EMBEDDED_DICTIONARY, front.CLI_DICT, front.DICT, front.LOCAL, front.PROBE, front.TRACE_TOOL,
              front.RAMP_TEST, area.observer.SNAPSHOT,
              *(ws / 'tools' / name for name in ('tsp_fk61_lip_front_observation.py', 'tsp_fk61_lip_area_observation.py',
                 'tsp_fk61_lip_observation.py', 'measure_tsp_fk61_lip_onset.py', 'measure_tsp_fk61_lip_front_radiation.py',
                 'measure_tsp_fk61_pcm_first_difference.py', 'measure_uniform_tube.py')),
              *(upper / name for name in ('Cargo.lock', 'crates/chimera/src/anatomy/human.rs',
                 'crates/chimera/src/voice/human_airway.rs', 'crates/chimera/src/voice/human_voice.rs',
                 'crates/chimera/src/airway/network.rs', 'crates/chimera/tests/geometry_continuity.rs'))]

    def measure(out, execute):
        archived = front.archived_pcm(pcm_input, uid)
        snapshots, current_proof = front.capture(study, spec, config, archived, out, execute, observation=observer,
                                                 scratch_prefix='fk61-node42-area-')
        prior = {name: read_ramp(path, study['measurement']) for name, path in geometry.items()}
        saved = {name: area.read_snapshots(path, [0, 1985]) for name, path in previous.items()}
        return analyze(study, snapshots, prior, saved, current_proof, tsp.read(proof), read_trial(trial_pcm),
                       tsp.read(volume_summary))

    info = {'case_id': study['id'], 'case_revision': study['revision'], 'upstream_revision': revision}
    return front.record_measurement(args.run_id, CASE, inputs, info, measure, command=None, input_root=ws.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
