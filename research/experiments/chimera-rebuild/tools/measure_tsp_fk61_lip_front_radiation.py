"""唇前端を揃えたFK61_01で残る初期放射とPCMの差を追う。"""

import argparse
from itertools import combinations
import json
import os
from pathlib import Path
import subprocess

import numpy as np

import measure_tsp_fk61_lip_onset as lip
import measure_tsp_fk61_pcm_first_difference as pcm
import measure_tsp_stressed_vowel_formants as tsp
import tsp_fk61_lip_front_radiation_observation as observer
from measure_duet_child_glottal_noise_origin import bit_equal
from measure_duet_child_output_gain import COLUMNS
from measure_fixed_voice_release_lip_load import replay as solve_lip
from measure_tsp_f2_bandwidth_held_out import saved_case
from measure_tsp_fine_variation import FIELDS, signal_difference
from measure_uniform_tube import candidate_sources, record_measurement
from tsp_fk61_lip_front_observation import apply_trial
from upstream_baseline import UPSTREAM, WORKSPACE


CASE = WORKSPACE / 'cases/tsp-fk61-lip-front-radiation.json'
MODES = ('upstream', 'candidate', 'trial')
COMPONENTS = ('wall_cm3_s', 'lip_cm3_s', 'nose_cm3_s')
RADIATION = 'radiation_derivative_cm3_s2'
CELL_VARS = ('spill_cm3_s', 'pole2_cm3_s', 'initial_inflow_cm3_s', 'before_wall_cm3_s',
             'wall_cm3_s', 'old_pressure_dyn_cm2', 'new_pressure_dyn_cm2')


def read_nodes(path, first, stop, *, cell_indices=None):
    data = np.loadtxt(path, delimiter=',', ndmin=2)
    rows = stop - first
    if data.size == 0 or data.shape[1] != len(observer.FIELDS) or len(data) % rows or not np.isfinite(data).all():
        raise ValueError(f'節点の計測列または標本数が不正です ({path.name})')
    cells = data.reshape(rows, -1, len(observer.FIELDS))
    count = cells.shape[1]
    expected_nodes = np.arange(count) if cell_indices is None else np.asarray(cell_indices)
    if (not np.array_equal(cells[:, :, 0], np.broadcast_to(np.arange(first, stop)[:, None], (rows, count)))
            or len(expected_nodes) != count or not np.all(cells[:, :, 1] == expected_nodes)
            or not np.all((cells[:, :, 2] == 1).sum(axis=1) == 1)):
        raise ValueError(f'節点の時計または口端を同定できません ({path.name})')
    return dict(zip(observer.FIELDS, cells.transpose(2, 0, 1), strict=True))


def radiation_from_components(components, rate, fixed):
    total = (components[COMPONENTS[0]] + components[COMPONENTS[1]]) + components[COMPONENTS[2]]
    delta = np.diff(total, prepend=0.0)
    return total, delta * rate if fixed else delta / (1 / rate)


def first_by_cell(reference, other, first):
    differences = {}
    for key in CELL_VARS:
        locations = np.argwhere(reference[key] != other[key])
        if len(locations):
            i = locations[0, 0]
            cells = locations[locations[:, 0] == i, 1]
            differences[key] = {'sample': int(first + i), 'cells': cells.tolist(),
                                'peak_error': float(np.max(np.abs(reference[key] - other[key])))}
        else:
            differences[key] = None
    return differences


def component_swaps(states, expected_pcm, coefficients, gain, config, frame):
    results = {}
    size = frame + 1
    rate = config['internal_sample_rate_hz']
    for source, target in (('upstream', 'trial'), ('trial', 'upstream')):
        attempts = []
        for n in range(1, len(COMPONENTS) + 1):
            for fields in combinations(COMPONENTS, n):
                components = {key: states[source if key in fields else target][key] for key in COMPONENTS}
                _, radiation = radiation_from_components(components, rate, target == 'upstream')
                _, samples = pcm.replay(radiation, coefficients[target], gain, config)
                reference = expected_pcm[source][:size]
                attempts.append({'components': list(fields), 'matches_pcm_through_frame': bool(bit_equal(samples[:size], reference)),
                                 'first_difference': signal_difference(reference, samples[:size])['first_unequal_sample'],
                                 'sample_at_frame': float(samples[frame])})
        results[target] = attempts
    return results


def onset_counterfactuals(study, config, gain, prefix, coefficients):
    cfg = study['measurement']
    onset, frame = cfg['onset_sample'], cfg['trial_first_pcm_frame']
    rate = cfg['internal_sample_rate_hz']
    factor = rate // cfg['sample_rate_hz']
    stop = (frame + 1) * factor
    states = {name: dict(zip(FIELDS, prefix[f'{name}_source'][:stop].T, strict=True)) for name in ('upstream', 'trial')}
    reference = prefix['upstream_pcm'][:frame + 1]
    division = {}
    for name, order in (('upstream', 'candidate'), ('trial', 'upstream')):
        _, signal = radiation_from_components(states[name], rate, order == 'upstream')
        _, samples = pcm.replay(signal, coefficients['candidate' if name == 'trial' else name], gain, config)
        division[name] = {'order': order, 'onset_value_cm3_s2': float(signal[onset]),
                          'first_pcm_difference': signal_difference(reference, samples)['first_unequal_sample']}
    one_sample = []
    for sample in range(onset, stop):
        components = {key: states['trial'][key].copy() for key in COMPONENTS}
        components['lip_cm3_s'][sample] = states['upstream']['lip_cm3_s'][sample]
        _, signal = radiation_from_components(components, rate, False)
        stage, samples = pcm.replay(signal, coefficients['candidate'], gain, config)
        one_sample.append({'sample': sample, 'dc_removed_at_frame': float(stage[frame, 2]),
                           'pcm_matches_through_frame': bool(bit_equal(reference, samples))})
    return {'derivative_order_swaps': division, 'mouth_sample_swaps': one_sample}


def analyze(study, config, gain, prefix, previous, coefficients, archived, geometry, cells, proof, older_lip):
    cfg = study['measurement']
    first, stop = cfg['comparison_internal_samples']
    rate = cfg['internal_sample_rate_hz']
    event_index = cfg['onset_sample'] - first
    coefficients = coefficients | {'trial': coefficients['candidate']}
    states = {name: dict(zip(FIELDS, prefix[f'{name}_source'].T, strict=True)) for name in MODES}
    output = {name: prefix[f'{name}_output'] for name in MODES}
    captured_pcm = {name: prefix[f'{name}_pcm'] for name in MODES}
    comparisons = {}
    for target in ('candidate', 'trial'):
        comparisons[target] = {key: signal_difference(states['upstream'][key], states[target][key]) for key in FIELDS}
    mouth = {name: geometry[name][event_index] for name in MODES}
    event = {name: lip.geometry(mouth[name], rate, name == 'upstream') for name in MODES}
    onset = comparisons['trial'][RADIATION]['first_unequal_sample']
    probe_frame = cfg['trial_first_pcm_frame']
    pcm_delta = {name: signal_difference(archived['upstream'], archived[name]) for name in ('candidate', 'trial')}
    rounding = pcm.midpoint_report(probe_frame, {'upstream': output['upstream'], 'candidate': output['trial']},
                                   {'upstream': captured_pcm['upstream'], 'candidate': captured_pcm['trial']})
    for key in ('precast', 'pcm', 'from_midpoint'):
        rounding[key]['trial'] = rounding[key].pop('candidate')
    replayed = {name: pcm.replay(states[name][RADIATION], coefficients[name], gain, config) for name in MODES}
    subsets = component_swaps(states, captured_pcm, coefficients, gain, config, probe_frame)
    node_differences = {name: first_by_cell(cells['upstream'], cells[name], first) for name in ('candidate', 'trial')}
    from_upper = lip.load_inputs(mouth['upstream'])
    from_trial = lip.load_inputs(mouth['trial'])
    swap_load = {name: {order: solve_lip(row, rate, order == 'upstream')['lip_flow']
                        for order in ('upstream', 'candidate')}
                 for name, row in (('upstream', from_upper), ('trial', from_trial))}
    return {
        'checks': {
            'ordinary_cli_probe_and_archive_match': all(
                proof[name]['bit_equal'] and proof[name]['ordinary'] == proof[name]['probe'] == proof[name]['archived']
                == lip.pcm_digest(archived[name]) and len(archived[name]) == cfg['frames']
                and bit_equal(captured_pcm[name], archived[name][:cfg['prefix_frames']]) for name in MODES),
            'prior_standard_observations_match_and_trial_pcm_onset_reproduced': (
                all(np.array_equal(prefix[f'{name}_source'], previous[f'{name}_state'])
                    and np.array_equal(output[name], previous[f'{name}_output']) and geometry[name] == older_lip[name]
                    for name in ('upstream', 'candidate'))
                and pcm_delta['trial']['first_unequal_sample'] == probe_frame
                and rounding['adjacent'] and rounding['straddles']),
            'independent_lip_geometry_poles_and_rl_load_replayed': all(
                lip.solve_matches(row, rate, name == 'upstream') and
                all(report[key] for key in ('matches_dimensions_and_volume', 'matches_filter', 'matches_geometry_inflow'))
                for name in MODES for row in geometry[name]
                for report in (lip.geometry(row, rate, name == 'upstream'),)),
            'wall_flux_and_network_flow_balance_replayed': all(
                np.array_equal(np.add.accumulate(cells[name]['wall_cm3_s'] * cells[name]['wall_fraction'], axis=1)[:, -1],
                               states[name]['wall_cm3_s'][first:stop])
                and np.array_equal(cells[name]['before_wall_cm3_s'] - cells[name]['wall_cm3_s'], cells[name]['inflow_cm3_s'])
                and np.array_equal(cells[name]['inflow_cm3_s'][cells[name]['is_mouth'] == 1],
                                   [row['inflow_cm3_s'] for row in geometry[name]])
                and np.array_equal(cells['upstream']['is_mouth'], cells[name]['is_mouth']) for name in MODES),
            'independent_radiation_and_output_replayed': all(
                np.array_equal(total, states[name]['total_cm3_s']) and np.array_equal(rad, states[name][RADIATION])
                and np.array_equal(output[name][:, :2].ravel(), rad)
                and np.array_equal(replayed[name][0], output[name][:, 2:])
                and bit_equal(replayed[name][1], captured_pcm[name])
                for name in MODES for total, rad in (radiation_from_components(states[name], rate, name == 'upstream'),)),
        },
        'predictions': {
            'mouth_volume_inflow_equal_at_onset': (
                event['upstream']['raw'] == event['trial']['raw']
                and mouth['upstream']['second_pole'] == mouth['trial']['second_pole']
                and from_upper['inflow'] == from_trial['inflow']),
            'residual_radiation_first_comes_from_wall_at_next_sample': (
                onset == cfg['onset_sample'] + 1 and comparisons['trial']['wall_cm3_s']['first_unequal_sample'] == onset
                and all(comparisons['trial'][name]['first_unequal_sample'] is None
                        or comparisons['trial'][name]['first_unequal_sample'] > onset for name in COMPONENTS[1:])),
            'one_radiation_component_can_recover_first_pcm_frame': any(
                len(row['components']) == 1 and row['matches_pcm_through_frame'] for row in subsets['trial']),
        },
        'first_source_differences_from_upstream': comparisons,
        'first_output_differences_from_upstream': {
            name: {key: signal_difference(output['upstream'][:, i], output[name][:, i])
                   for i, key in enumerate(COLUMNS)} for name in ('candidate', 'trial')},
        'first_node_differences_from_upstream': node_differences,
        'onset_mouth_state': mouth, 'onset_mouth_geometry': event,
        'onset_lip_solver_order_swap': swap_load, 'first_pcm_rounding': rounding,
        'pcm': pcm_delta, 'radiation_component_swaps': subsets,
    }


def read_trial(path):
    with np.load(path, allow_pickle=False) as archive:
        return archive['pcm']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    study = tsp.read(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != study['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    if os.environ.get('CHIMERA_RUN_STORAGE') != 'rtl9210b':
        parser.error('試験ビルドにCHIMERA_RUN_STORAGE=rtl9210bを指定してください')
    front, mouth, output, matched = (tsp.open_run(study[key], revision) for key in ('front', 'lip', 'output', 'matched'))
    config, config_path = saved_case(matched, lip.CONFIG)
    uid = study['measurement']['recording_id']
    spec = tsp.verified_path(matched, f'artifacts/{uid}/matched-case.json')
    pcm_input = tsp.verified_path(matched, 'artifacts/matched-pcm.npz')
    trial_pcm = tsp.verified_path(front, 'artifacts/trial-pcm.npz')
    previous = tsp.verified_path(output, 'artifacts/prefix.npz')
    coefficients = tsp.verified_path(output, 'artifacts/coefficients.json')
    older_lip = {name: tsp.verified_path(mouth, f'artifacts/{name}-lip.f64le') for name in ('upstream', 'candidate')}
    inputs = [CASE, Path(__file__).resolve(), Path(observer.__file__), Path(lip.__file__), Path(pcm.__file__), config_path,
              spec, pcm_input, trial_pcm, previous, coefficients, *older_lip.values(),
              *(run[0] / 'manifest.json' for run in (front, mouth, output, matched)), *candidate_sources(),
              lip.EMBEDDED_DICTIONARY, lip.DICT, lip.LOCAL, lip.PROBE, lip.TRACE_TOOL, lip.OUTPUT_PATCH, lip.SOURCE_PATCH,
              lip.observer.LOCAL_PATCH, lip.observer.UPPER_PATCH, WORKSPACE / 'data/cmudict.txt.gz',
              WORKSPACE / 'crates/vocal-core/tests/geometry_ramp.rs',
              *(WORKSPACE / 'tools' / name for name in ('tsp_fk61_lip_front_observation.py', 'tsp_fk61_lip_observation.py',
                   'measure_fixed_voice_release_lip_load.py', 'measure_tsp_fine_variation.py', 'measure_uniform_tube.py')),
              *(UPSTREAM / name for name in ('Cargo.lock', 'crates/chimera/src/airway/network.rs',
                   'crates/chimera/src/voice/human_voice.rs', 'crates/chimera/tests/airway.rs',
                   'crates/chimera/tests/airway_adversarial.rs'))]

    def measure(out, execute):
        arch = pcm.archived_pcm(pcm_input, uid) | {'trial': read_trial(trial_pcm)}
        geometry, proof = lip.capture(study, spec, config, arch, out, execute, trial_patch=apply_trial,
                                      prepare=observer.prepare, retain_prefix=True)
        (out / 'pcm-digests.json').write_text(json.dumps(proof, indent=2) + '\n')
        (out / 'node-columns.json').write_text(json.dumps(observer.FIELDS, indent=2) + '\n')
        first, stop = study['measurement']['comparison_internal_samples']
        cells = {name: read_nodes(out / f'{name}-nodes.csv', first, stop) for name in MODES}
        previous_geometry = {name: lip.read_trace(path, stop - first) for name, path in older_lip.items()}
        gain = tsp.read(spec)['speech_voice']['voice']['output_gain']
        with np.load(out / 'prefix.npz', allow_pickle=False) as prefix, np.load(previous, allow_pickle=False) as prior:
            return analyze(study, config, gain, prefix, prior, tsp.read(coefficients), arch, geometry,
                           cells, proof, previous_geometry)

    info = {'case_id': study['id'], 'case_revision': study['revision'], 'upstream_revision': revision}
    return record_measurement(args.run_id, CASE, inputs, info, measure, command=None, input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
