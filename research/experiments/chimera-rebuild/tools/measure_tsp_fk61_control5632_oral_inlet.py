"""口腔の入口から口端までを連成し、咽頭からの流量の寄与を測る。"""

import argparse
import json
import os
from pathlib import Path
import subprocess

import numpy as np

import measure_tsp_fk61_control5632_upstream_drive as six


oral, load, terminal, radiation, tsp = six.oral, six.load, six.terminal, six.radiation, six.tsp
lip, pcm = six.lip, six.pcm
CASE = radiation.WORKSPACE / 'cases/tsp-fk61-control5632-oral-inlet.json'
INLET = (27, 28)
EDGE37 = (37, 38)
MODES, SAVED_FILES = six.MODES, six.SAVED_FILES


def shared_capture(current, past):
    """前回計測した枝・壁・節点は列と標本番号を照合する。"""
    tags = ('cells', 'branch', 'wall', 'compliance', 'loads')
    return {tag: all(json.dumps(current[tag][key]) == json.dumps(old) for key, old in past[tag].items())
            for tag in tags}


def inlet_branch_order(data, measure):
    first, stop = measure['comparison_internal_samples']
    # CSVの行順は、観測器が枝の更新順に書いた順番を保っている。
    oral_edges = list(zip(measure['nodes'][1:-1], measure['nodes'][2:], strict=True))
    expected = [(n, *edge) for n in range(first, stop) for edge in (*oral_edges, INLET)]
    return list(data['branch']) == expected


def condition(trajectory, native, measure, prefix, config, gain, coefficients):
    report, array = six.summary_and_array(trajectory, native, measure, prefix, config, gain, coefficients)
    for n in measure['comparison_samples']:
        row, ordinary = trajectory[n], native[n]
        report['checkpoints'][str(n)].update(
            branch27_shift_cm3_s=row['flow'][INLET] - ordinary['flow'][INLET],
            branch37_shift_cm3_s=row['flow'][EDGE37] - ordinary['flow'][EDGE37])
    additional = [(row['flow'][INLET], row['flow'][EDGE37]) for row in trajectory.values()]
    return report, np.column_stack((array, additional))


def observations(data, measure):
    upper, trial = (data[mode] for mode in ('upstream','trial'))
    first, stop = measure['local_internal_samples']
    edges = list(zip(measure['nodes'][:-1], measure['nodes'][1:], strict=True))
    points = {}
    for n in measure['comparison_samples']:
        points[str(n)] = {
            'branches_cm3_s': {f'{a}->{b}': upper['branch'][n,a,b]['flow'] - trial['branch'][n,a,b]['flow']
                               for a,b in edges},
            'volume_sources_cm3_s': {str(j): upper['cells'][n,j]['initial_inflow_cm3_s']
                                     - trial['cells'][n,j]['initial_inflow_cm3_s'] for j in measure['nodes'][1:]},
        }
    onset = {f'{a}->{b}': next((n for n in range(first,stop)
                                 if abs(upper['branch'][n,a,b]['flow'] - trial['branch'][n,a,b]['flow']) >= 1e-12), None)
             for a,b in edges}
    return points, onset


def analyze(study, out, prior, previous, config, gain, coefficients, proof):
    measure = study['measurement']
    first, stop = measure['local_internal_samples']
    target = str(measure['witness_interval'][0])
    data = {mode: oral.read_capture(out, mode, measure) for mode in MODES}
    upper, trial = (data[mode] for mode in ('upstream','trial'))
    with np.load(out / 'prefix.npz', allow_pickle=False) as capture, np.load(prior / 'prefix.npz', allow_pickle=False) as saved:
        same_prefix = capture.files == saved.files and all(load.same_bits(capture[key], saved[key])
                                                            for key in capture.files)
        prefix = dict(saved)
    prior_measure = measure | {'nodes': list(range(37,44)), 'pressure_nodes': list(range(38,43))}
    shared = {mode: shared_capture(data[mode], oral.read_capture(prior, mode, prior_measure)) for mode in MODES}
    branch_order = {mode: inlet_branch_order(data[mode], measure) for mode in MODES}
    local = {mode: oral.local_replay(data[mode], measure, mode == 'upstream') for mode in MODES}
    replayed = {mode: six.replay(data[mode], measure, mode == 'upstream') for mode in ('upstream','trial')}
    native = replayed['trial']
    native_errors = {mode: six.native_mismatches(data[mode], values) for mode,values in replayed.items()}
    series, conditions, per_source = {}, [], {}
    for subset in load.subsets(six.GROUPS):
        replay = six.replay(trial, measure, False, reference=upper, groups=subset)
        row, values = condition(replay, native, measure, prefix, config, gain, coefficients)
        conditions.append({'groups': list(subset), **row})
        series['+'.join(subset) or 'baseline'] = values
    for node in measure['nodes'][1:]:
        replay = six.replay(trial, measure, False, reference=upper, volume_nodes=(node,))
        per_source[str(node)], series[f'volume_{node}'] = condition(replay, native, measure, prefix,
                                                                    config, gain, coefficients)
    imposed = {}
    for name, sources, earlier_groups in (
        ('branch37', (), ['upstream_boundary']),
        ('branch37_plus_volume38_41', (38,39,40,41), ['upstream_boundary','inner_volume']),
    ):
        replay = six.replay(trial, measure, False, reference=upper, imposed_edge=EDGE37, volume_nodes=sources)
        row, series[name] = condition(replay, native, measure, prefix, config, gain, coefficients)
        earlier = next(record for record in previous['conditions'] if record['groups'] == earlier_groups)
        predicted = {key: row[key] for key in ('pcm_two_samples', 'pcm_full_interval')}
        imposed[name] = predicted | {'matches_previous_six_nodes': all(value == earlier[key]
                                                                      for key,value in predicted.items())}
    effects = {row['groups'][0]: abs(row['checkpoints'][target]['branch37_shift_cm3_s'])
               for row in conditions if len(row['groups']) == 1}
    matches = {key: [row['groups'] for row in conditions if row[key]['first_difference_through_focus'] is None]
               for key in ('pcm_two_samples','pcm_full_interval')}
    hypotheses = {
        'anterior_volume_sources_outweigh_terminal_sources_for_edge37': effects['inner_volume'] > effects['terminal_volume'],
        'pharyngeal_inflow_is_largest_single_group_at_edge37': effects['upstream_boundary'] > max(
            value for key,value in effects.items() if key!='upstream_boundary'),
        'initial_state_is_smaller_than_later_forcing': effects['initial_state'] < max(
            value for key,value in effects.items() if key!='initial_state'),
        'post_boundary_inputs_recover_pcm_in_full_interval': any(
            row and 'initial_state' not in row for row in matches['pcm_full_interval']),
    }
    checkpoints, crossing = observations(data, measure)
    prior_proof = tsp.read(prior / 'pcm-digests.json')
    checks = {
        'all_full_pcm_and_shared_observations_match': prior_proof == proof and same_prefix
            and all(voice['bit_equal'] and voice['ordinary']['frames'] == measure['frames'] for voice in proof.values())
            and all(all(parts.values()) for parts in shared.values()),
        'oral_inlet_accumulation_order_observed': all(branch_order.values()),
        'local_and_full_oral_trajectory_replayed': not any(any(row.values()) for row in local.values())
                                                   and not any(native_errors.values()),
        'direct_branch37_controls_match_previous_six_node_replay': all(
            row['matches_previous_six_nodes'] for row in imposed.values()),
        'all_registered_exchanges_and_unmodified_pcm_replayed': (
            len(conditions) == 2 ** len(six.GROUPS) and len(per_source) == len(measure['nodes']) - 1
            and all(conditions[0][key] == previous['conditions'][0][key] for key in ('pcm_two_samples','pcm_full_interval'))),
    }
    return {'checks': checks, 'hypotheses': hypotheses, 'branch_update_order': branch_order,
            'native_mismatches': native_errors, 'local_errors': local, 'shared': shared,
            'native_checkpoints': checkpoints, 'first_flow_at_least_1e_12': crossing,
            'matching_groups': matches, 'conditions': conditions, 'per_node_volume': per_source,
            'six_node_controls': imposed}, series | {
            'internal_sample': np.arange(first,stop),
            'columns': np.asarray((*six.TRAJECTORY_FIELDS,'flow27_28','flow37_38'))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    ws, upper = radiation.WORKSPACE, radiation.UPSTREAM
    study = tsp.read(CASE)
    revision = subprocess.check_output(['git','rev-parse','HEAD'], cwd=upper, text=True).strip()
    if revision != study['upstream_revision'] or subprocess.check_output(['git','status','--porcelain'], cwd=upper):
        parser.error('変更のない固定上流版が必要です')
    if os.environ.get('CHIMERA_RUN_STORAGE') != 'rtl9210b':
        parser.error('試験ビルドにCHIMERA_RUN_STORAGE=rtl9210bを指定してください')
    matched, bernstein, output, previous = (tsp.open_run(study[key], revision) for key in
                                            ('matched','bernstein','coefficients','previous_focus'))
    uid = study['measurement']['recording_id']
    spec = tsp.verified_path(matched, f'artifacts/{uid}/matched-case.json')
    config, config_path = radiation.saved_case(matched, lip.CONFIG)
    reference_pcm = tsp.verified_path(matched, 'artifacts/matched-pcm.npz')
    trial_pcm = tsp.verified_path(bernstein, 'artifacts/render.npz')
    coefficients = tsp.verified_path(output, 'artifacts/coefficients.json')
    prior = tsp.verified_path(previous, 'summary.json')
    retained = [tsp.verified_path(previous, f'artifacts/{name}') for name in SAVED_FILES]
    inputs = [CASE, Path(__file__).resolve(), Path(six.__file__), Path(six.two_cell.__file__), Path(oral.__file__),
              Path(six.drive.__file__), Path(load.__file__), Path(terminal.__file__), Path(terminal.observer.__file__),
              Path(radiation.__file__), config_path, spec, reference_pcm, trial_pcm, coefficients, prior, *retained,
              *(row[0] / 'manifest.json' for row in (matched, bernstein, output, previous)),
              *radiation.candidate_sources(), lip.EMBEDDED_DICTIONARY, lip.DICT, lip.LOCAL, lip.PROBE,
              lip.TRACE_TOOL, lip.OUTPUT_PATCH, lip.SOURCE_PATCH, lip.observer.LOCAL_PATCH, lip.observer.UPPER_PATCH,
              ws / 'data/cmudict.txt.gz', ws / 'crates/vocal-core/tests/geometry_ramp.rs',
              *(ws / 'tools' / name for name in ('tsp_fk61_lip_front_observation.py','tsp_fk61_lip_observation.py',
                 'tsp_fk61_lip_front_radiation_observation.py','tsp_fk61_ray43_observation.py',
                 'tsp_fk61_node_volume_observation.py','tsp_fk61_lower_lip_bernstein_observation.py',
                 'measure_tsp_fk61_lip_onset.py','measure_tsp_fk61_node42_volume_source.py',
                 'measure_tsp_fk61_pcm_first_difference.py','measure_fixed_voice_glottal_branch.py',
                 'measure_fixed_voice_radiation_balance.py','measure_fixed_voice_release_lip_load.py',
                 'measure_tsp_fine_variation.py','measure_uniform_tube.py')),
              *(upper / name for name in ('Cargo.lock','crates/chimera/src/airway/network.rs',
                 'crates/chimera/src/voice/human_airway.rs','crates/chimera/src/voice/human_voice.rs',
                 'crates/chimera/tests/airway.rs','crates/chimera/tests/airway_adversarial.rs'))]

    def measure(out, execute):
        archived = pcm.archived_pcm(reference_pcm, uid)
        with np.load(trial_pcm, allow_pickle=False) as stored:
            archived['trial'] = stored['pcm']
        proof = oral.capture(study, spec, config, archived, out, execute)
        gain = tsp.read(spec)['speech_voice']['voice']['output_gain']
        report, arrays = analyze(study, out, previous[0] / 'artifacts', tsp.read(prior), config,
                                 gain, tsp.read(coefficients), proof)
        np.savez_compressed(out / 'trajectories.npz', **arrays)
        return report

    details = {'case_id':study['id'], 'case_revision':study['revision'], 'upstream_revision':revision}
    return radiation.record_measurement(args.run_id, CASE, inputs, details, measure, command=None, input_root=ws.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
