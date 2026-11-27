"""FK61_01のPCM2937に効く2標本で口端負荷の入力を切り分ける。"""

import argparse
from itertools import combinations
import json
import os
from pathlib import Path
import subprocess

import numpy as np

import measure_tsp_fk61_lip_front_terminal_branch as terminal
import measure_tsp_fk61_pcm2937_lip_window as window
import tsp_fk61_lower_lip_bernstein_observation as bernstein


radiation, observer = terminal.radiation, terminal.observer
lip, pcm, tsp = terminal.lip, terminal.pcm, terminal.tsp
CASE = radiation.WORKSPACE / 'cases/tsp-fk61-pcm2937-terminal-load.json'
MODES = terminal.MODES
FOCUS_MODES = ('upstream', 'trial')
LOAD_GEOMETRY = ('compliance', 'inertance', 'resistance')
INPUT_GROUPS = {'inflow': ('inflow',), 'pressure': ('old_pressure',),
                'inertance_flow': ('old_inertance_flow',), 'coefficients': LOAD_GEOMETRY}
REFERENCE_FILES = {
    'matched': ('artifacts/matched-pcm.npz',),
    'output': ('artifacts/coefficients.json',),
    'comparison': ('artifacts/upstream-prefix.npz',),
    'bernstein': ('artifacts/render.npz',),
    'window': ('summary.json',),
}


def subsets(names):
    for count in range(len(names) + 1):
        yield from combinations(names, count)


def same_bits(a, b):
    return a.shape == b.shape and a.dtype == b.dtype and a.tobytes() == b.tobytes()


def immediate(upstream, trial, rate):
    base, ref = trial['load'], upstream['load']
    results = []
    for groups in subsets(tuple(INPUT_GROUPS)):
        hybrid = base | {field: ref[field] for group in groups for field in INPUT_GROUPS[group]}
        solved = radiation.solve_lip(hybrid, rate, False)
        results.append({'groups': list(groups), **{key: solved[key] for key in terminal.LIP_STATE},
                        'shift_from_trial_cm3_s': solved['lip_flow'] - base['lip_flow'],
                        'residual_vs_upstream_cm3_s': solved['lip_flow'] - ref['lip_flow']})
    return results


def load_history(events, measure, mode, exchanges=(), reference=None):
    start, stop = measure['local_internal_samples']
    rate = measure['internal_sample_rate_hz']
    first = reference[start]['load'] if 'initial_history' in exchanges else events[start]['load']
    pressure = first['old_pressure']
    load_flow = first['old_inertance_flow']
    # 初回の流量は慣性補正後の観測値。必要なら、その標本の慣性から換算する。
    previous_l = first['inertance']
    results = {}
    for n in range(start, stop):
        native = events[n]['load']
        geometry = reference[n]['load'] if 'coefficients' in exchanges else native
        drive = reference[n]['load'] if 'inflow' in exchanges else native
        inertance = geometry['inertance']
        if 0.0 < previous_l < inertance:
            load_flow *= previous_l / inertance
        previous_l = inertance
        row = {key: geometry[key] for key in LOAD_GEOMETRY}
        row.update(inflow=drive['inflow'], old_pressure=pressure, old_inertance_flow=load_flow)
        solved = radiation.solve_lip(row, rate, mode == 'upstream')
        results[n] = row | {key: solved[key] for key in terminal.LIP_STATE}
        pressure, load_flow = solved['new_pressure'], solved['new_inertance_flow']
    return results


def inflow_terms(event):
    mouth = event['nodes'][1]
    return {'volume_source': mouth['initial_inflow_cm3_s'],
            'series_branch': event['series']['flow'], 'wall_sink': -mouth['wall_cm3_s'],
            'net': event['load']['inflow']}


def output_replay(prefix, replacements, measure, config, gain, coefficients):
    frame, clock = measure['focus_frame'], measure['internal_sample_rate_hz']
    components = dict(zip(radiation.FIELDS, prefix['trial_source'].T, strict=True))
    flow = components['lip_cm3_s'].copy()
    for n, value in replacements.items():
        flow[n] = value
    _, signal = radiation.radiation_from_components(components | {'lip_cm3_s': flow}, clock, False)
    output, samples = pcm.replay(signal, coefficients['candidate'], gain, config)
    reference = prefix['upstream_pcm'][:frame + 1]
    baseline = prefix['trial_output'][frame, window.DC]
    return {'precast': float(output[frame, 2]), 'precast_shift': float(output[frame, 2] - baseline),
            'pcm': float(samples[frame]),
            'first_difference_through_focus': radiation.signal_difference(
                reference, samples[:len(reference)])['first_unequal_sample']}


def analyze(study, config, gain, coefficients, out, previous, proof):
    measure = study['measurement']
    rate, size = measure['internal_sample_rate_hz'], measure['prefix_frames']
    first, stop = measure['comparison_internal_samples']
    start, end = measure['witness_interval']
    focus = measure['focus_internal_samples']
    events = {mode: terminal.read_mode(out, mode, measure) for mode in MODES}
    upper, trial = (events[mode] for mode in FOCUS_MODES)
    prefix_matches, observed_flow = {}, {}
    with np.load(out / 'prefix.npz', allow_pickle=False) as stored:
        prefix = dict(stored)
    for mode, label in zip(FOCUS_MODES, ('comparison', 'bernstein'), strict=True):
        with np.load(previous[label], allow_pickle=False) as earlier:
            prefix_matches[mode] = {
                field: same_bits(prefix[f'{mode}_{field}'], earlier[field][:limit])
                for field, limit in (('source', size * 2), ('output', size), ('pcm', size))
            }
    static = {}
    for mode in MODES:
        static[mode] = terminal.disagreements(events[mode], {}, measure, mode == 'upstream')
        mouth = prefix[f'{mode}_source'][first:stop, radiation.FIELDS.index('lip_cm3_s')]
        observed_flow[mode] = same_bits(mouth, np.array([event['load']['lip_flow'] for event in events[mode].values()]))
    history = {mode: load_history(events[mode], measure, mode) for mode in MODES}
    history_mismatches = {
        mode: {str(n): {key: [values[key], events[mode][n]['load'][key]] for key in values
                        if values[key].hex() != events[mode][n]['load'][key].hex()}
               for n, values in history[mode].items()}
        for mode in MODES
    }
    history_mismatches = {mode: {n: row for n, row in rows.items() if row} for mode, rows in history_mismatches.items()}
    point_data = {}
    hypothesis_tests = {name: [] for name in study['hypotheses']}
    for n in focus:
        inputs = {mode: events[mode][n]['load'] for mode in FOCUS_MODES}
        terms = {mode: inflow_terms(events[mode][n]) for mode in FOCUS_MODES}
        terms_delta = {key: terms['upstream'][key] - terms['trial'][key] for key in terms['upstream']}
        point = immediate(upper[n], trial[n], rate)
        effects = {tuple(row['groups']): abs(row['shift_from_trial_cm3_s']) for row in point}
        hypothesis_tests['history_exceeds_instantaneous_inflow'].append(
            effects['pressure', 'inertance_flow'] > effects['inflow',])
        hypothesis_tests['load_coefficients_smallest'].append(
            effects['coefficients',] < min(effects[key,] for key in ('inflow', 'pressure', 'inertance_flow')))
        hypothesis_tests['branch_larger_than_other_inflow_terms'].append(
            abs(terms_delta['series_branch']) > max(abs(terms_delta[key]) for key in ('volume_source', 'wall_sink')))
        point_data[str(n)] = {
            'load': inputs, 'inflow_terms_cm3_s': terms, 'inflow_deltas_upstream_minus_trial_cm3_s': terms_delta,
            'lip_delta_upstream_minus_trial_cm3_s': inputs['upstream']['lip_flow'] - inputs['trial']['lip_flow'],
            'single_step_exchanges': point,
        }

    interventions = []
    for exchange in subsets(('initial_history', 'inflow', 'coefficients')):
        sequence = load_history(trial, measure, 'trial', exchange, upper)
        flows = {n: sequence[n]['lip_flow'] for n in range(start, end)}
        interventions.append({'groups': list(exchange),
                              'lip_cm3_s': {str(n): flow for n, flow in flows.items()},
                              **output_replay(prefix, flows, measure, config, gain, coefficients)})
    baseline = output_replay(prefix, {}, measure, config, gain, coefficients)
    witness = output_replay(prefix, {n: upper[n]['load']['lip_flow'] for n in range(start, end)},
                            measure, config, gain, coefficients)
    prior = tsp.read(previous['window'])
    frame = measure['focus_frame']
    checks = {
        'ordinary_probe_and_archived_pcm_match': all(
            row['bit_equal'] and row['ordinary']['frames'] == measure['frames']
            and row['ordinary'] == row['probe'] == row['archived'] for row in proof.values()
        ) and set(proof) == set(MODES),
        'reference_prefix_and_terminal_flow_bit_exact': (
            all(all(row.values()) for row in prefix_matches.values()) and all(observed_flow.values())),
        'native_branch_wall_node_and_load_replay': not any(static.values()),
        'load_history_replays_native_states': not any(history_mismatches.values()),
        'both_pcm_controls_replay': (
            baseline['precast'] == prefix['trial_output'][frame, window.DC]
            and baseline['pcm'] == prefix['trial_pcm'][frame]
            and baseline['first_difference_through_focus'] == frame
            and interventions[0]['precast'] == baseline['precast']
            and [start, end] in prior['shortest_intervals']
            and witness['precast'] == prior['controls']['first_shortest']['precast']
            and witness['pcm'] == prior['controls']['first_shortest']['pcm']
            and witness['first_difference_through_focus'] is None),
    }
    return {'checks': {name: bool(ok) for name, ok in checks.items()},
            'prefix_matches': prefix_matches, 'observed_flow': observed_flow,
            'static_mismatches': {mode: {str(n): row for n, row in rows.items()} for mode, rows in static.items()},
            'history_mismatches': history_mismatches, 'focus': point_data,
            'hypotheses_by_sample': {name: {str(n): ok for n, ok in zip(focus, verdicts, strict=True)}
                                     for name, verdicts in hypothesis_tests.items()},
            'pcm_controls': {'baseline': baseline, 'witness': witness}, 'history_exchanges': interventions}


def patch_trial(root):
    bernstein.ray.apply_trial(root)
    bernstein.apply_curve(root)


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
    runs = {name: tsp.open_run(study[name], revision) for name in REFERENCE_FILES}
    previous = {name: tsp.verified_path(runs[name], paths[0]) for name, paths in REFERENCE_FILES.items()}
    uid = study['measurement']['recording_id']
    spec = tsp.verified_path(runs['matched'], f'artifacts/{uid}/matched-case.json')
    config, config_path = radiation.saved_case(runs['matched'], lip.CONFIG)
    inputs = [CASE, Path(__file__).resolve(), Path(terminal.__file__), Path(observer.__file__),
              Path(bernstein.__file__), Path(window.__file__), Path(radiation.__file__),
              config_path, spec, *previous.values(), *(run[0] / 'manifest.json' for run in runs.values()),
              *radiation.candidate_sources(), lip.EMBEDDED_DICTIONARY, lip.DICT, lip.LOCAL, lip.PROBE,
              lip.TRACE_TOOL, lip.OUTPUT_PATCH, lip.SOURCE_PATCH, lip.observer.LOCAL_PATCH, lip.observer.UPPER_PATCH,
              ws / 'data/cmudict.txt.gz', ws / 'crates/vocal-core/tests/geometry_ramp.rs',
              *(ws / 'tools' / name for name in ('tsp_fk61_lip_front_observation.py', 'tsp_fk61_lip_observation.py',
                 'tsp_fk61_lip_front_radiation_observation.py', 'tsp_fk61_ray43_observation.py',
                 'tsp_fk61_node_volume_observation.py', 'measure_tsp_fk61_lip_onset.py',
                 'measure_fixed_voice_glottal_branch.py', 'measure_fixed_voice_radiation_balance.py',
                 'measure_fixed_voice_release_lip_load.py', 'measure_tsp_fk61_pcm_first_difference.py',
                 'measure_tsp_fine_variation.py', 'measure_uniform_tube.py')),
              *(upper / name for name in ('Cargo.lock', 'crates/chimera/src/airway/network.rs',
                 'crates/chimera/src/voice/human_voice.rs', 'crates/chimera/tests/airway.rs',
                 'crates/chimera/tests/airway_adversarial.rs'))]

    def measure(out, execute):
        arch = pcm.archived_pcm(previous['matched'], uid)
        with np.load(previous['bernstein'], allow_pickle=False) as base:
            arch['trial'] = base['pcm']
        _, proof = lip.capture(study, spec, config, arch, out, execute, trial_patch=patch_trial,
                               prepare=observer.prepare, retain_prefix=True)
        (out / 'pcm-digests.json').write_text(json.dumps(proof, indent=2) + '\n')
        for mode in MODES:
            terminal.split_capture(out, mode)
        gain = tsp.read(spec)['speech_voice']['voice']['output_gain']
        return analyze(study, config, gain, tsp.read(previous['output']), out, previous, proof)

    info = {'case_id': study['id'], 'case_revision': study['revision'], 'upstream_revision': revision}
    return radiation.record_measurement(args.run_id, CASE, inputs, info, measure, command=None, input_root=ws.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
