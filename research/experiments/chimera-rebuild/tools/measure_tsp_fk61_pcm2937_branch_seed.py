"""FK61_01の枝42→43で旧流量と旧慣性を交換する開始点を動かす。"""

import argparse
from fractions import Fraction
import math
import os
from pathlib import Path
import subprocess

import numpy as np

import measure_tsp_fk61_pcm2937_branch_drive as drive


load, terminal, radiation, tsp = drive.load, drive.terminal, drive.radiation, drive.tsp
CASE = radiation.WORKSPACE / 'cases/tsp-fk61-pcm2937-branch-seed.json'
SEED_FIELDS = ('previous_flow', 'previous_inertance')
CONDITIONS = tuple(load.subsets(SEED_FIELDS))


def initial_branch(trial, upper, fields):
    seed = trial | {key: upper[key] for key in fields}
    seed['previous_momentum'] = seed['previous_inertance'] * seed['previous_flow']
    return seed


def response(seed, baseline, steps, rate):
    """枝の陰的な流量式を観測軌道の周りで微分し、初期状態の差を伝搬する。"""
    current = Fraction(baseline['inertance'])
    l_base = min(current, Fraction(baseline['previous_inertance']))
    l_changed = min(current, Fraction(seed['previous_inertance']))
    u_base = Fraction(baseline['previous_flow'])
    u_changed = Fraction(seed['previous_flow'])
    # 開始標本では、履歴項の差を積の丸めなしで先に求める。
    source = float((l_changed * u_changed - l_base * u_base) * rate)
    first = next(iter(steps))
    shifts = {}
    for n, row in steps.items():
        u = row['flow']
        inertia = row['inertance'] * rate
        loss = row['forward_loss'] if u >= 0.0 else row['reverse_loss']
        denominator = inertia + row['resistance'] + 2.0 * loss * abs(u)
        if n > first:
            source = min(row['inertance'], row['previous_inertance']) * rate * shifts[n - 1]
        shifts[n] = source / denominator
    return shifts


def sweep_row(upper, trial, baseline, seed_sample, fields, measure, prefix, config, gain, coefficients):
    seed = initial_branch(trial[seed_sample]['series'], upper[seed_sample]['series'], fields)
    local = measure | {'local_internal_samples': [seed_sample, measure['local_internal_samples'][1]]}
    seeded_events = trial | {seed_sample: trial[seed_sample] | {'series': seed}}
    replay = drive.edge_history(seeded_events, local, False)
    trajectory = {n: row['flow'] for n, row in replay.items()}
    natural_flow = {n: branch['flow'] for n, branch in baseline.items()}
    predictions = response(seed, baseline[seed_sample], {n: baseline[n] for n in replay},
                           measure['internal_sample_rate_hz'])
    shifts = {n: value - natural_flow[n] for n, value in trajectory.items()}
    errors = {n: abs(shift - predictions[n]) / math.ulp(natural_flow[n]) for n, shift in shifts.items()}
    worst = max(errors, key=errors.get)
    begin, end = measure['witness_interval']
    sound = drive.project(trial, natural_flow | trajectory, measure, prefix, config, gain, coefficients)
    return {'start_sample': seed_sample, 'groups': list(fields),
            'initial_state': {key: seed[key] for key in (*SEED_FIELDS, 'previous_momentum')},
            'edge_shift_at_witness_cm3_s': {str(n): shifts[n] for n in range(begin, end)},
            'linear_shift_at_witness_cm3_s': {str(n): predictions[n] for n in range(begin, end)},
            'maximum_linear_error': {'sample': worst, 'absolute_ulps': errors[worst]},
            'branch_samples_with_changed_flow': [n for n, value in shifts.items() if value != 0.0],
            **sound}


def analyze(study, config, gain, coefficients, captured, previous, proof):
    measure = study['measurement']
    starts = list(range(*measure['start_scan_internal_samples']))
    modes = drive.MODES
    events = {mode: terminal.read_mode(captured, mode, measure) for mode in modes}
    upper, trial = (events[mode] for mode in modes)
    with np.load(captured / 'prefix.npz', allow_pickle=False) as archived:
        prefix = dict(archived)
    baseline = {}
    differences = {}
    for mode in modes:
        fixed = mode == 'upstream'
        native = events[mode]
        baseline[mode] = drive.edge_history(native, measure, fixed)
        differences[mode] = {
            'branch': {
                str(n): [key for key, value in step.items() if value.hex() != native[n]['series'][key].hex()]
                for n, step in baseline[mode].items() if step != native[n]['series']
            },
            'network': {str(n): data for n, data in terminal.disagreements(
                native, terminal.model(native, measure, fixed), measure, fixed).items()},
        }
    rows = {n: {group: sweep_row(upper, trial, baseline['trial'], n, group, measure, prefix, config, gain, coefficients)
                for group in CONDITIONS} for n in starts}
    focus = str(measure['witness_interval'][0])
    ref = measure['previous_control_start']
    reference = next(row for row in previous['sequence_exchanges'] if row['groups'] == ['initial_branch'])
    branch_only = previous['pcm_controls']['branch_only']
    direct_edge = {n: (trial if n < ref else upper)[n]['series']['flow'] for n in baseline['trial']}
    direct_control = drive.project(trial, direct_edge, measure, prefix, config, gain, coefficients)
    control_keys = tuple(branch_only)
    matching_by_group = {'+'.join(group) or 'baseline': [n for n, values in rows.items()
                         if values[group]['first_difference_through_focus'] is None] for group in CONDITIONS}
    max_ulp = max(row['maximum_linear_error']['absolute_ulps'] for values in rows.values() for row in values.values())
    hypotheses = {
        'flow_only_suffices_at_every_start': matching_by_group['previous_flow'] == starts,
        'inertance_only_insufficient_at_every_start': not matching_by_group['previous_inertance'],
        'older_flow_seed_is_larger_at_witness': (
            abs(rows[starts[0]]['previous_flow',]['edge_shift_at_witness_cm3_s'][focus])
            > abs(rows[ref]['previous_flow',]['edge_shift_at_witness_cm3_s'][focus])),
        'prior_flow_is_larger_at_every_start': all(
            abs(values['previous_flow',]['precast_shift']) > abs(values['previous_inertance',]['precast_shift'])
            for values in rows.values()),
    }
    checks = {
        'source_ordinary_cli_matches_archived_pcm': all(
            proof[mode]['bit_equal'] and proof[mode]['ordinary']['frames'] == measure['frames']
            and proof[mode]['ordinary'] == proof[mode]['probe'] == proof[mode]['archived'] for mode in modes),
        'native_branch_and_full_two_node_replay': not any(
            any(error.values()) for error in differences.values()),
        'all_starts_and_both_previous_controls_replayed': (
            len(rows) == measure['start_scan_internal_samples'][1] - measure['start_scan_internal_samples'][0]
            and all(len(values) == len(CONDITIONS) for values in rows.values())
            and all(rows[ref][SEED_FIELDS][key] == reference[key] for key in control_keys)
            and direct_control == branch_only),
        'unmodified_seeds_replay_baseline_for_every_start': all(
            not values[()]['branch_samples_with_changed_flow']
            and all(values[()][key] == previous['sequence_exchanges'][0][key] for key in control_keys)
            for values in rows.values()),
        'linear_branch_sensitivity_within_ulp_budget': max_ulp <= measure['linear_prediction_max_ulps'],
    }
    return {'checks': checks, 'hypotheses': hypotheses, 'native_differences': differences,
            'matching_starts_by_group': matching_by_group, 'maximum_linear_residual_ulps': max_ulp,
            'direct_branch_control': direct_control,
            'sweep': [row for values in rows.values() for row in values.values()]}


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
    prior, source, matched, output = (tsp.open_run(study[key], revision)
                                       for key in ('branch_drive', 'terminal_load', 'matched', 'output'))
    uid = study['measurement']['recording_id']
    config, config_path = radiation.saved_case(matched, load.lip.CONFIG)
    spec = tsp.verified_path(matched, f'artifacts/{uid}/matched-case.json')
    coefficients = tsp.verified_path(output, 'artifacts/coefficients.json')
    previous = tsp.verified_path(prior, 'summary.json')
    capture = {name: tsp.verified_path(source, f'artifacts/{name}') for name in drive.CAPTURE_FILES}
    inputs = [CASE, Path(__file__).resolve(), Path(drive.__file__), Path(load.__file__), Path(terminal.__file__),
              Path(radiation.__file__), config_path, spec, coefficients, previous, *capture.values(),
              *(run[0] / 'manifest.json' for run in (prior, source, matched, output)),
              *(ws / name for name in ('tools/measure_fixed_voice_glottal_branch.py',
                 'tools/measure_fixed_voice_radiation_balance.py', 'tools/measure_fixed_voice_release_lip_load.py',
                 'tools/measure_tsp_fk61_pcm_first_difference.py', 'tools/measure_tsp_fk61_lip_onset.py',
                 'tools/tsp_fk61_terminal_branch_observation.py', 'crates/vocal-core/src/airway/network.rs',
                 'crates/vocal-core/tests/geometry_ramp.rs')),
              *(upper / name for name in ('crates/chimera/src/airway/network.rs',
                 'crates/chimera/src/voice/human_voice.rs', 'crates/chimera/tests/airway_adversarial.rs'))]

    def measure(out, execute):
        gain = tsp.read(spec)['speech_voice']['voice']['output_gain']
        return analyze(study, config, gain, tsp.read(coefficients), source[0] / 'artifacts', tsp.read(previous),
                       tsp.read(capture['pcm-digests.json']))

    details = {'case_id': study['id'], 'case_revision': study['revision'], 'upstream_revision': revision}
    return radiation.record_measurement(args.run_id, CASE, inputs, details, measure, command=None, input_root=ws.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
