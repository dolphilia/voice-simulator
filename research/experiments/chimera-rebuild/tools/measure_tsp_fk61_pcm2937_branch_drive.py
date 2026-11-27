"""FK61_01の枝42→43の加速項・損失・履歴を切り分けてPCMへ戻す。"""

import argparse
from fractions import Fraction
import math
import os
from pathlib import Path
import subprocess

import numpy as np

import measure_tsp_fk61_pcm2937_terminal_load as load


terminal, radiation, tsp = load.terminal, load.radiation, load.tsp
CASE = radiation.WORKSPACE / 'cases/tsp-fk61-pcm2937-branch-drive.json'
MODES = load.FOCUS_MODES
PRESSURES = ('left_pressure', 'right_pressure')
PRIOR = ('previous_flow', 'previous_momentum')
INERTANCE = ('inertance', 'previous_inertance')
LOSSES = ('resistance', 'forward_loss', 'reverse_loss')
POINT_GROUPS = {'pressure': PRESSURES, 'prior_flow': PRIOR, 'inertance': INERTANCE,
                'losses': LOSSES, 'turbulence': ('noise_pressure',)}
SEQUENCE_GROUPS = ('pressure', 'initial_branch', 'inertance', 'losses', 'turbulence')
CAPTURE_FILES = ('prefix.npz', 'pcm-digests.json', *(f'{mode}-{tag}' for mode in MODES for tag in
                 ('nodes.csv', 'lip.f64le', 'branch.csv', 'wall.csv', 'compliance.csv')))


def edge_history(events, measure, fixed, exchanges=(), reference=None):
    start, stop = measure['local_internal_samples']
    rate = measure['internal_sample_rate_hz']
    initial = (reference if 'initial_branch' in exchanges else events)[start]['series']
    carried = {key: initial[key] for key in (*PRIOR, 'previous_inertance')}
    steps = {}
    for n in range(start, stop):
        branch = events[n]['series'] | carried
        if reference is not None:
            source = reference[n]['series']
            for group in ('pressure', 'losses', 'turbulence'):
                if group in exchanges:
                    branch.update({key: source[key] for key in POINT_GROUPS[group]})
            if 'inertance' in exchanges:
                branch['inertance'] = source['inertance']
        flow = terminal.branch_flow(branch, rate, fixed)
        steps[n] = branch | {'flow': flow}
        carried = {'previous_inertance': branch['inertance'], 'previous_flow': flow,
                   'previous_momentum': branch['inertance'] * flow}
    return steps


def exact_terms(row, rate, upper):
    """差分の解析式用に積と和の途中の丸めを省いた量を得る。"""
    item = {key: Fraction(value) for key, value in row.items()}
    carries_momentum = item['inertance'] >= item['previous_inertance']
    if upper and carries_momentum:
        momentum = item['previous_momentum']
    else:
        momentum = min(item['inertance'], item['previous_inertance']) * item['previous_flow']
    return {'pressure_gap': item['left_pressure'] - item['right_pressure'],
            'history_pressure': momentum * rate, 'noise_pressure': item['noise_pressure'],
            'inertance_per_step': item['inertance'] * rate, 'resistance': item['resistance'],
            'quadratic_loss': item['reverse_loss'], 'flow': item['flow'],
            'carries_momentum': carries_momentum}


def decomposition(upper, trial, rate):
    ref, base = exact_terms(upper, rate, True), exact_terms(trial, rate, False)
    if ref['flow'] >= 0 or base['flow'] >= 0:
        raise ValueError('登録した負向きの枝流量を確認できません')
    flow = base['flow']
    delta = {key: ref[key] - base[key] for key in ('pressure_gap', 'history_pressure', 'noise_pressure',
                                                   'inertance_per_step', 'resistance', 'quadratic_loss')}
    denominator = (ref['inertance_per_step'] + ref['resistance']
                   + ref['quadratic_loss'] * (abs(ref['flow']) + abs(flow)))
    numerators = {key: delta[key] for key in ('pressure_gap', 'history_pressure', 'noise_pressure')}
    numerators.update(inertance=-delta['inertance_per_step'] * flow, resistance=-delta['resistance'] * flow,
                      quadratic_loss=-delta['quadratic_loss'] * flow * abs(flow))
    theoretical = sum(numerators.values()) / denominator
    observed = ref['flow'] - flow
    residual = float(observed - theoretical)
    return {'flow_delta_cm3_s': float(observed), 'pressure_deltas_dyn_cm2': {key: float(value) for key, value in numerators.items()},
            'flow_terms_cm3_s': {key: float(value / denominator) for key, value in numerators.items()},
            'unrounded_total_cm3_s': float(theoretical), 'residual_cm3_s': residual,
            'absolute_residual_ulps': abs(residual) / math.ulp(float(flow)),
            'carries_momentum': {'upstream': ref['carries_momentum'], 'trial': base['carries_momentum']}}


def point_exchanges(upper, trial, rate):
    results = []
    for subset in load.subsets(tuple(POINT_GROUPS)):
        branch = trial | {key: upper[key] for group in subset for key in POINT_GROUPS[group]}
        solved = terminal.solve_branch(branch, rate, False)
        flow = float(solved['flow'])
        results.append({'groups': list(subset), 'flow_cm3_s': flow, 'drive_dyn_cm2': float(solved['drive_pressure']),
                        'shift_from_trial_cm3_s': flow - trial['flow'], 'residual_vs_upstream_cm3_s': flow - upper['flow']})
    return results


def mouth_events(events, flows):
    replacements = {}
    for n, flow in flows.items():
        event = events[n]
        node = event['nodes'][1]
        net = (node['initial_inflow_cm3_s'] + flow) - node['wall_cm3_s']
        replacements[n] = event | {'load': event['load'] | {'inflow': net}}
    return replacements


def project(events, flows, measure, prefix, config, gain, coefficients):
    start, stop = measure['witness_interval']
    states = load.load_history(mouth_events(events, flows), measure, 'trial')
    mouth = {n: states[n]['lip_flow'] for n in range(start, stop)}
    return {'edge_cm3_s': {str(n): flows[n] for n in mouth}, 'mouth_cm3_s': {str(n): value for n, value in mouth.items()},
            **load.output_replay(prefix, mouth, measure, config, gain, coefficients)}


def analyze(study, config, gain, coefficients, captured, previous, proof):
    measure = study['measurement']
    rate = measure['internal_sample_rate_hz']
    first, stop = measure['local_internal_samples']
    start, end = measure['witness_interval']
    events = {mode: terminal.read_mode(captured, mode, measure) for mode in MODES}
    upper, trial = (events[mode] for mode in MODES)
    with np.load(captured / 'prefix.npz', allow_pickle=False) as stored:
        prefix = dict(stored)

    focus, hypotheses = {}, {'old_flow_largest_at_focus': {}, 'pressure_exceeds_losses_at_focus': {}}
    for n in map(str, measure['focus_internal_samples']):
        a, b = (events[mode][int(n)]['series'] for mode in MODES)
        data = point_exchanges(a, b, rate)
        effects = {row['groups'][0]: abs(row['shift_from_trial_cm3_s']) for row in data if len(row['groups']) == 1}
        hypotheses['old_flow_largest_at_focus'][n] = effects['prior_flow'] > max(
            value for group, value in effects.items() if group != 'prior_flow')
        hypotheses['pressure_exceeds_losses_at_focus'][n] = effects['pressure'] > effects['losses']
        focus[n] = {'native_input': dict(zip(MODES, (a, b), strict=True)),
                    'decomposition': decomposition(a, b, rate), 'point_exchanges': data}

    native_errors = {}
    for mode in MODES:
        fixed = mode == 'upstream'
        steps = edge_history(events[mode], measure, fixed)
        native_errors[mode] = {
            'edge_history': {str(n): [key for key in data if data[key].hex() != events[mode][n]['series'][key].hex()]
                             for n, data in steps.items()},
            'node_history': terminal.disagreements(events[mode], terminal.model(events[mode], measure, fixed), measure, fixed),
        }
    runs = []
    for subset in load.subsets(SEQUENCE_GROUPS):
        predicted = edge_history(trial, measure, False, subset, upper)
        value = project(trial, {n: row['flow'] for n, row in predicted.items()}, measure, prefix, config, gain, coefficients)
        runs.append({'groups': list(subset), **value})
    edge_only = project(trial, {n: upper[n]['series']['flow'] for n in range(first, stop)}, measure,
                        prefix, config, gain, coefficients)
    whole_inflow = load.load_history(trial, measure, 'trial', ('inflow',), upper)
    whole_control = load.output_replay(prefix, {n: whole_inflow[n]['lip_flow'] for n in range(start, end)},
                                      measure, config, gain, coefficients)
    mouth_control = load.output_replay(prefix, {n: upper[n]['load']['lip_flow'] for n in range(start, end)},
                                      measure, config, gain, coefficients)
    rows = {tuple(row['groups']): row for row in runs}
    hypotheses['only_branch_flow_can_restore_pcm'] = edge_only['first_difference_through_focus'] is None
    hypotheses['pressure_series_exceeds_initial_branch_state'] = abs(rows['pressure',]['precast_shift']) > abs(
        rows['initial_branch',]['precast_shift'])
    check = {
        'source_ordinary_cli_matches_archived_pcm': all(
            proof[mode]['bit_equal'] and proof[mode]['ordinary']['frames'] == measure['frames']
            and proof[mode]['ordinary'] == proof[mode]['probe'] == proof[mode]['archived'] for mode in MODES),
        'native_edge_and_two_nodes_replayed': all(
            not any(row['edge_history'].values()) and not row['node_history'] for row in native_errors.values()),
        'signed_branch_difference_within_ulp_budget': all(
            row['decomposition']['absolute_residual_ulps'] <= measure['branch_residual_max_ulps'] for row in focus.values()),
        'all_point_exchanges_include_native_control': all(
            row['point_exchanges'][0]['flow_cm3_s'] == row['native_input']['trial']['flow']
            and len(row['point_exchanges']) == 2 ** len(POINT_GROUPS) for row in focus.values()),
        'all_sequence_exchanges_and_pcm_controls_replayed': (
            len(runs) == 2 ** len(SEQUENCE_GROUPS)
            and all(runs[0][key] == value for key, value in previous['pcm_controls']['baseline'].items())
            and mouth_control == previous['pcm_controls']['witness']
            and all(whole_control[key] == value for key, value in next(
                row for row in previous['history_exchanges'] if row['groups'] == ['inflow']).items()
                    if key in whole_control)),
    }
    return {'checks': check, 'hypotheses': hypotheses, 'focus': focus,
            'native_errors': {mode: {key: {str(n): row for n, row in data.items() if row}
                                     for key, data in stages.items()} for mode, stages in native_errors.items()},
            'sequence_exchanges': runs,
            'pcm_controls': {'branch_only': edge_only, 'whole_inflow': whole_control, 'direct_mouth': mouth_control}}


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
        parser.error('計測にCHIMERA_RUN_STORAGE=rtl9210bを指定してください')
    parent, matched, output = (tsp.open_run(study[key], revision) for key in ('terminal_load', 'matched', 'output'))
    uid = study['measurement']['recording_id']
    config, config_path = radiation.saved_case(matched, load.lip.CONFIG)
    spec_path = tsp.verified_path(matched, f'artifacts/{uid}/matched-case.json')
    coefficients_path = tsp.verified_path(output, 'artifacts/coefficients.json')
    capture = {name: tsp.verified_path(parent, f'artifacts/{name}') for name in CAPTURE_FILES}
    previous_path = tsp.verified_path(parent, 'summary.json')
    inputs = [CASE, Path(__file__).resolve(), Path(load.__file__), Path(terminal.__file__),
              Path(radiation.__file__), config_path, spec_path, coefficients_path, previous_path, *capture.values(),
              *(run[0] / 'manifest.json' for run in (parent, matched, output)),
              *(ws / name for name in ('tools/measure_fixed_voice_glottal_branch.py',
                 'tools/measure_fixed_voice_radiation_balance.py', 'tools/measure_fixed_voice_release_lip_load.py',
                 'tools/measure_tsp_fk61_pcm_first_difference.py', 'tools/measure_tsp_fk61_lip_onset.py',
                 'tools/tsp_fk61_terminal_branch_observation.py', 'crates/vocal-core/src/airway/network.rs',
                 'crates/vocal-core/tests/geometry_ramp.rs')),
              *(upper / name for name in ('crates/chimera/src/airway/network.rs',
                 'crates/chimera/src/voice/human_voice.rs', 'crates/chimera/tests/airway_adversarial.rs'))]

    def measure(out, execute):
        gain = tsp.read(spec_path)['speech_voice']['voice']['output_gain']
        return analyze(study, config, gain, tsp.read(coefficients_path), parent[0] / 'artifacts',
                       tsp.read(previous_path), tsp.read(capture['pcm-digests.json']))

    details = {'case_id': study['id'], 'case_revision': study['revision'], 'upstream_revision': revision}
    return radiation.record_measurement(args.run_id, CASE, inputs, details, measure, command=None, input_root=ws.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
