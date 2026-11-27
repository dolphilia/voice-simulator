"""FK61_01の枝41→42・42→43の初差を冒頭から探す。"""

import argparse
from functools import partial
import json
import os
from pathlib import Path
import subprocess

import numpy as np

import measure_tsp_fk61_pcm2937_branch_drive as drive
from tsp_fk61_lip_front_radiation_observation import FIELDS as NODE_FIELDS


load, terminal, radiation, tsp = drive.load, drive.terminal, drive.radiation, drive.tsp
lip, pcm = load.lip, load.pcm
CASE = radiation.WORKSPACE / 'cases/tsp-fk61-branch-first-difference.json'
MODES = terminal.MODES
EDGE_NAMES = ('boundary', 'series')
NODE_VARIABLES = ('old_volume_cm3', 'volume_cm3', 'area_cm2', 'minimum_cm2', 'length_cm', 'spill_cm3_s',
                  'pole2_cm3_s', 'initial_inflow_cm3_s', 'before_wall_cm3_s', 'wall_cm3_s',
                  'inflow_cm3_s', 'old_pressure_dyn_cm2', 'new_pressure_dyn_cm2')
SAVED_FILES = ('prefix.npz', 'pcm-digests.json', *(f'{mode}-{tag}' for mode in MODES for tag in
               ('nodes.csv', 'lip.f64le', 'branch.csv', 'wall.csv', 'compliance.csv')))


def first_change(a, b, offset=0):
    left, right = np.asarray(a), np.asarray(b)
    if left.shape != right.shape or left.ndim != 1:
        raise ValueError('初差を照合する系列の長さまたは形が異なります')
    indices = np.flatnonzero(left != right)
    if len(indices) == 0:
        return None
    i = int(indices[0])
    return {'sample': i + offset, 'upstream': float(left[i]), 'comparison': float(right[i]),
            'upstream_minus_comparison': float(left[i] - right[i])}


def edge_chronology(left, right, measure, edge):
    first, stop = measure['comparison_internal_samples']
    ref, other = ([data[n][edge] for n in range(first, stop)] for data in (left, right))
    fields = {key: first_change([row[key] for row in ref], [row[key] for row in other], first) for key in ref[0]}
    fields['pressure_difference'] = first_change(*[
        [row['left_pressure'] - row['right_pressure'] for row in data] for data in (ref, other)], first)
    return fields


def snapshot(upper, trial, measure, edge, chronology):
    event = chronology['flow']
    if event is None:
        raise ValueError(f'比較区間内に枝の流量差がありません ({edge})')
    n = event['sample']
    first, stop = measure['comparison_internal_samples']
    radius = measure['earlier_sample_radius']
    rate = measure['internal_sample_rate_hz']
    a, b = upper[n][edge], trial[n][edge]
    exchanges = drive.point_exchanges(a, b, rate)
    return {
        'sample': n,
        'observed': {str(i): {'upstream': upper[i][edge], 'trial': trial[i][edge]}
                     for i in range(max(first, n - radius), min(stop, n + radius + 1))},
        'same_input_rounding': {
            'upper_input_with_trial_order_cm3_s': terminal.branch_flow(a, rate, False),
            'trial_input_with_upper_order_cm3_s': terminal.branch_flow(b, rate, True),
        },
        'exchanges': exchanges,
    }


def analyze(study, out, retained, prior, proof):
    measure = study['measurement']
    first, stop = measure['comparison_internal_samples']
    old_first, old_stop = measure['overlap_internal_samples']
    overlap = measure | {'comparison_internal_samples': [old_first, old_stop]}
    node_ids = tuple(measure['nodes'])
    events = {mode: terminal.read_mode(out, mode, measure, cell_indices=node_ids) for mode in MODES}
    selected_cells = {mode: radiation.read_nodes(out / f'{mode}-nodes.csv', first, stop, cell_indices=node_ids)
                      for mode in MODES}
    with np.load(out / 'prefix.npz', allow_pickle=False) as prefix, np.load(retained / 'prefix.npz', allow_pickle=False) as old:
        prefix_equal = set(prefix.files) == set(old.files) and all(
            load.same_bits(prefix[key], old[key]) for key in prefix.files)
        mouth_from_prefix = {
            mode: load.same_bits(prefix[f'{mode}_source'][first:stop, radiation.FIELDS.index('lip_cm3_s')],
                                 np.asarray([event['load']['lip_flow'] for event in events[mode].values()]))
            for mode in MODES
        }
    overlaps, replay_errors = {}, {}
    for mode in MODES:
        fixed = mode == 'upstream'
        e = events[mode]
        reference = terminal.read_mode(retained, mode, overlap)
        previous_cells = radiation.read_nodes(retained / f'{mode}-nodes.csv', old_first, old_stop)
        overlaps[mode] = {
            'all_branch_wall_and_load_values': json.dumps({n: e[n] for n in range(old_first, old_stop)})
                                                == json.dumps(reference),
            'selected_cells': all(load.same_bits(selected_cells[mode][field][old_first-first:old_stop-first],
                                                 previous_cells[field][:, node_ids]) for field in NODE_FIELDS),
        }
        errors = terminal.disagreements(e, {}, measure, fixed)
        replay_errors[mode] = {'samples': len(errors), 'first': next(iter(errors.items()), None)}

    chronologies = {}
    for mode in ('candidate', 'trial'):
        ref, other = (selected_cells[tag] for tag in ('upstream', mode))
        chronologies[mode] = {
            'edges': {edge: edge_chronology(events['upstream'], events[mode], measure, edge) for edge in EDGE_NAMES},
            'cells': {str(node): {field: first_change(ref[field][:, index], other[field][:, index], first)
                                  for field in NODE_VARIABLES} for index, node in enumerate(node_ids)},
            'mouth': first_change(*[[e['load']['lip_flow'] for e in events[tag].values()]
                                    for tag in ('upstream', mode)], first),
        }
    upper, trial = events['upstream'], events['trial']
    edges = chronologies['trial']['edges']
    snapshots = {edge: snapshot(upper, trial, measure, edge, edges[edge]) for edge in EDGE_NAMES}
    focus = snapshots['series']['sample']
    f = snapshots['series']['observed'][str(focus)]
    effects = {tuple(item['groups']): abs(item['shift_from_trial_cm3_s']) for item in snapshots['series']['exchanges']}
    hypotheses = {
        'series_flow_diverges_by_first_mouth_difference': focus <= chronologies['trial']['mouth']['sample'],
        'prior_flow_agrees_at_first_series_difference': all(
            f['upstream'][key] == f['trial'][key] for key in ('previous_flow', 'previous_momentum')),
        'pressure_has_larger_local_effect_than_coefficients': effects['pressure',] > effects['inertance', 'losses'],
        'boundary_diverges_by_first_series_difference': snapshots['boundary']['sample'] <= focus,
    }
    checks = {
        'ordinary_probe_and_archived_pcm_match': proof == prior and all(
            row['bit_equal'] and row['ordinary']['frames'] == measure['frames']
            and row['ordinary'] == row['probe'] == row['archived'] for row in proof.values()),
        'prefix_overlap_and_mouth_observations_bit_exact': (
            prefix_equal and all(mouth_from_prefix.values()) and all(all(row.values()) for row in overlaps.values())),
        'captured_branch_wall_cell_and_load_replayed': not any(row['samples'] for row in replay_errors.values()),
        'first_branch_differences_and_previous_mouth_witness_observed': (
            first == 0 and chronologies['trial']['mouth']['sample'] == measure['known_first_lip_difference']
            and all(first < snapshots[edge]['sample'] < stop for edge in EDGE_NAMES)),
        'swaps_include_native_controls_at_first_branch_differences': all(
            len(row['exchanges']) == 2 ** len(drive.POINT_GROUPS)
            and row['exchanges'][0]['flow_cm3_s'] == row['observed'][str(row['sample'])]['trial']['flow']
            for row in snapshots.values()),
    }
    return {'checks': checks, 'hypotheses': hypotheses, 'chronologies': chronologies, 'first_branches': snapshots,
            'overlap': overlaps, 'prefix_bit_equal': prefix_equal, 'mouth_from_prefix': mouth_from_prefix,
            'replay_errors': replay_errors}


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
    matched, bernstein, prior, seed = (tsp.open_run(study[key], revision)
                                       for key in ('matched', 'bernstein', 'terminal_load', 'branch_seed'))
    uid = study['measurement']['recording_id']
    spec = tsp.verified_path(matched, f'artifacts/{uid}/matched-case.json')
    config, config_path = radiation.saved_case(matched, lip.CONFIG)
    reference_pcm = tsp.verified_path(matched, 'artifacts/matched-pcm.npz')
    trial_pcm = tsp.verified_path(bernstein, 'artifacts/render.npz')
    retained = {name: tsp.verified_path(prior, f'artifacts/{name}') for name in SAVED_FILES}
    seed_summary = tsp.verified_path(seed, 'summary.json')
    inputs = [CASE, Path(__file__).resolve(), Path(load.__file__), Path(drive.__file__), Path(terminal.__file__),
              Path(terminal.observer.__file__), Path(radiation.__file__), config_path, spec, reference_pcm, trial_pcm,
              *retained.values(), seed_summary, *(run[0] / 'manifest.json' for run in (matched, bernstein, prior, seed)),
              *radiation.candidate_sources(), lip.EMBEDDED_DICTIONARY, lip.DICT, lip.LOCAL, lip.PROBE,
              lip.TRACE_TOOL, lip.OUTPUT_PATCH, lip.SOURCE_PATCH, lip.observer.LOCAL_PATCH, lip.observer.UPPER_PATCH,
              ws / 'data/cmudict.txt.gz', ws / 'crates/vocal-core/tests/geometry_ramp.rs',
              *(ws / 'tools' / name for name in ('tsp_fk61_lip_front_observation.py', 'tsp_fk61_lip_observation.py',
                 'tsp_fk61_lip_front_radiation_observation.py', 'tsp_fk61_ray43_observation.py',
                 'tsp_fk61_node_volume_observation.py', 'tsp_fk61_lower_lip_bernstein_observation.py',
                 'measure_tsp_fk61_lip_onset.py', 'measure_fixed_voice_glottal_branch.py',
                 'measure_fixed_voice_radiation_balance.py', 'measure_fixed_voice_release_lip_load.py',
                 'measure_tsp_fine_variation.py', 'measure_uniform_tube.py')),
              *(upper / name for name in ('Cargo.lock', 'crates/chimera/src/airway/network.rs',
                 'crates/chimera/src/voice/human_voice.rs', 'crates/chimera/tests/airway.rs',
                 'crates/chimera/tests/airway_adversarial.rs'))]

    def measure(out, execute):
        archived = pcm.archived_pcm(reference_pcm, uid)
        with np.load(trial_pcm, allow_pickle=False) as original:
            archived['trial'] = original['pcm']
        prepare = partial(terminal.observer.prepare, cell_indices=tuple(study['measurement']['nodes']))
        _, proof = lip.capture(study, spec, config, archived, out, execute, trial_patch=load.patch_trial,
                               prepare=prepare, retain_prefix=True)
        (out / 'pcm-digests.json').write_text(json.dumps(proof, indent=2) + '\n')
        for mode in MODES:
            terminal.split_capture(out, mode)
        return analyze(study, out, prior[0] / 'artifacts', tsp.read(retained['pcm-digests.json']), proof)

    details = {'case_id': study['id'], 'case_revision': study['revision'], 'upstream_revision': revision}
    return radiation.record_measurement(args.run_id, CASE, inputs, details, measure, command=None, input_root=ws.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
