"""放射流量の後退差分だけを上流の時間換算で比較する。"""

import argparse
from pathlib import Path
import subprocess
import sys

import numpy as np

from measure_songbird_chirps_beak_inlet_rate_propagation_44100 import NETWORK, render_variants
from measure_songbird_chirps_beak_load import ROOT
from measure_songbird_chirps_beak_tip_inflow_44100 import registered_artifacts
from measure_songbird_chirps_bronchus_inlet_balance_44100 import CASE as UPPER_CASE
from measure_songbird_chirps_left_syrinx_half_inertance_44100 import configure
from measure_songbird_chirps_left_syrinx_port_44100 import stored_trace
from measure_songbird_chirps_oec_pressure_44100 import CONDITIONS
from measure_songbird_chirps_right_sac_momentum_44100 import LEFT_PATCH
from measure_songbird_chirps_right_syrinx_half_inertance_44100 import restore_patches
from measure_songbird_chirps_terminal_numerator_44100 import first_offset, same_bits
from measure_songbird_chirps_trachea_interior_momentum_44100 import apply_edits
from measure_songbird_chirps_volume_rate_propagation_44100 import DERIVATIVE, RADIATION, differences
from measure_speech_timing import read
from measure_uniform_tube import candidate_sources, record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/songbird-chirps-radiation-derivative-scale-44100.json'
BASE_CASE = WORKSPACE / 'cases/songbird-chirps-left-sac-momentum-44100.json'
LABEL = 'derivative-scale'


def edit_derivative(workspace, patch):
    apply_edits(workspace, patch, {
        NETWORK: (
            ('pub struct AirwayNetwork {\n    dt: f64,',
             'pub struct AirwayNetwork {\n    dt: f64,\n    sample_rate_hz: u32,'),
            ('        let mut network = Self {\n            dt,',
             '        let mut network = Self {\n            dt,\n            sample_rate_hz,'),
            ('        let derivative = (radiation_flow - self.previous_radiation_flow) / self.dt;',
             '''        let derivative =
            (radiation_flow - self.previous_radiation_flow) * f64::from(self.sample_rate_hz);'''),
        ),
    })


def replay_derivative(trace, rate, *, multiply):
    increment = np.diff(trace[RADIATION], prepend=0.0)
    return increment * rate if multiply else increment / (1 / rate)


def prediction(control, experiment, upper):
    initial = first_offset(experiment, control)
    return {
        'first_effect_offset': initial,
        'first_effect_hex': float(experiment[initial]).hex() if initial is not None else None,
        'changed_derivative_samples': int(np.count_nonzero(experiment.view(np.uint64) != control.view(np.uint64))),
        'first_upstream_difference_offset': first_offset(experiment, upper),
        'upstream_bitwise_matches': int(np.count_nonzero(experiment.view(np.uint64) == upper.view(np.uint64))),
    }


def diagnose(experiment, upper, start, offset, rate):
    traces = {'experiment': experiment, 'upstream': upper}
    index = start + offset
    flow = {label: {'previous': float(trace[RADIATION][index - 1]),
                    'current': float(trace[RADIATION][index])} for label, trace in traces.items()}
    own = flow['experiment']
    reference = flow['upstream']
    swaps = {
        'previous_only': (own['current'] - reference['previous']) * rate,
        'current_only': (reference['current'] - own['previous']) * rate,
    }
    tip = tuple(field for field in experiment.dtype.names if field in upper.dtype.names and field.startswith('beak_'))
    return {
        'offset': offset,
        'flow_cm3_s': flow,
        'derivative_cm3_s2': {label: float(trace[DERIVATIVE][index]) for label, trace in traces.items()},
        'derivative_with_substituted_flow_cm3_s2': swaps,
        'beak_first_differences': differences(experiment[start:], upper[start:], tip,
                                              left_label='experiment', right_label='upstream'),
    }


def measure(case, saved, upper_files, patches, snapshot, copies, out, execute):
    configs = configure(case, saved, out)
    paths, build = render_variants(configs, patches, snapshot, copies, out, execute,
                                   edit=edit_derivative, patch_stem=LABEL, labels=('control', LABEL))
    checks = {
        'only_network_patched': build['changed_paths'] == [NETWORK],
        'experiment_binary_differs': build['experimental_binary_sha256'] != build['control_binary_sha256'],
        'control_binary_reproduced':
            build['control_binary_sha256'] == read(saved['summary.json'])['build']['experimental_binary_sha256'],
    }
    results = {}
    rate = case['sample_rate_hz']
    window = case['observation_internal_samples']
    for name in CONDITIONS:
        start = case['condition_control_samples'][name]
        control_path = paths['control'][name]
        experiment_path = paths[LABEL][name]
        control = stored_trace(control_path, start + window)
        experiment = stored_trace(experiment_path, start + window)
        upper = stored_trace(upper_files[f'artifacts/{name}-upstream.csv'], start + window)
        expected = case['prediction'][name]
        control_derivative = control[DERIVATIVE][start:]
        actual = experiment[DERIVATIVE][start:]
        reference = upper[DERIVATIVE][start:]
        upgraded = replay_derivative(control, rate, multiply=True)[start:]
        observed = prediction(control_derivative, actual, reference)
        radiation_offset = first_offset(experiment[RADIATION][start:], upper[RADIATION][start:])
        checks.update({
            f'{name}/control_csv_reproduced': sha256(control_path) == sha256(saved[f'artifacts/{name}-{LEFT_PATCH}.csv']),
            f'{name}/all_other_columns_bitwise_identical': (
                control.dtype == experiment.dtype and all(same_bits(control[field], experiment[field])
                    for field in control.dtype.names if field != DERIVATIVE)),
            f'{name}/pre_onset_derivative_unchanged': same_bits(control[DERIVATIVE][:start], experiment[DERIVATIVE][:start]),
            f'{name}/control_derivative_replayed': same_bits(replay_derivative(control, rate, multiply=False), control[DERIVATIVE]),
            f'{name}/experimental_derivative_replayed': same_bits(replay_derivative(experiment, rate, multiply=True), experiment[DERIVATIVE]),
            f'{name}/upstream_derivative_replayed': same_bits(replay_derivative(upper, rate, multiply=True), upper[DERIVATIVE]),
            f'{name}/prediction_replayed_from_control': prediction(control_derivative, upgraded, reference) == expected,
            f'{name}/continuous_render_matches_prediction': observed == expected and same_bits(upgraded, actual),
            f'{name}/difference_first_at_flow': observed['first_upstream_difference_offset'] == radiation_offset,
        })
        residual = None
        if radiation_offset is None:
            checks[f'{name}/unexcited_and_complete_csv_unchanged'] = (
                sha256(control_path) == sha256(experiment_path) and not np.any(experiment[RADIATION]))
        else:
            residual = diagnose(experiment, upper, start, radiation_offset, rate)
            swapped = residual['derivative_with_substituted_flow_cm3_s2']
            effect = observed['first_effect_offset']
            checks[f'{name}/first_effect_matches_upstream'] = (
                effect is not None and float(actual[effect]).hex() == float(reference[effect]).hex())
            checks[f'{name}/only_current_flow_changes_at_first_residual'] = (
                swapped['previous_only'].hex() == float(actual[radiation_offset]).hex()
                and swapped['current_only'].hex() == float(reference[radiation_offset]).hex())
        results[name] = {
            **observed,
            'control_first_upstream_difference_offset': first_offset(control_derivative, reference),
            'radiation_flow_first_upstream_difference_offset': radiation_offset,
            'first_residual': residual,
        }
    return {'checks': checks, 'sample_rate_hz': rate, 'window': window, 'build': build, 'conditions': results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    case, baseline, observation = (read(path) for path in (CASE, BASE_CASE, UPPER_CASE))
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    if any(case[key] != baseline[key] or case[key] != observation[key] for key in (
            'upstream_revision', 'sample_rate_hz', 'output_rate_hz', 'condition_control_samples',
            'observation_internal_samples')):
        parser.error('先行実行と今回の比較条件が一致しません')
    names = ('summary.json', f'artifacts/{LEFT_PATCH}.patch', *(f'artifacts/{name}{suffix}'
             for name in CONDITIONS for suffix in ('.json', f'-{LEFT_PATCH}.csv')))
    base_manifest, saved = registered_artifacts(case['baseline'], baseline['id'], revision, names)
    upper_manifest, upper_files = registered_artifacts(case['upstream_observation'], observation['id'], revision,
        tuple(f'artifacts/{name}-upstream.csv' for name in CONDITIONS))
    manifest = read(base_manifest)
    indexed = {row['path']: row['sha256'] for row in manifest['inputs']}
    reference_inputs = [BASE_CASE, UPPER_CASE, upper_manifest, *upper_files.values()]
    if any(indexed.get(path.relative_to(ROOT).as_posix()) != sha256(path) for path in reference_inputs):
        parser.error('先行実行が使用したケースと固定上流CSVが必要です')
    patches = restore_patches(manifest, saved, LEFT_PATCH)
    copies = [*candidate_sources(), WORKSPACE / 'data/cmudict.txt.gz', WORKSPACE / 'data/mandarin.txt.gz']
    references = [ROOT / path for path in indexed
                  if (ROOT / path).parent == WORKSPACE / 'tools' or (ROOT / path).is_relative_to(UPSTREAM)]
    inputs = [CASE, Path(__file__).resolve(), base_manifest, *saved.values(), *reference_inputs,
              *patches, *copies, *references]
    details = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision,
               'analysis_command': [sys.executable, *sys.argv], 'analysis_directory': str(Path.cwd())}
    snapshot = WORKSPACE / 'runs' / args.run_id / 'artifacts/source'
    return record_measurement(args.run_id, CASE, inputs, details,
        lambda out, execute: measure(case, saved, upper_files, patches, snapshot, copies, out, execute),
        command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
