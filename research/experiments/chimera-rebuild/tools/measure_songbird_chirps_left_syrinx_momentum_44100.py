"""左鳴管の持ち越し運動量または線形慣性の時間換算を切り替えて描画する。"""

import argparse
from pathlib import Path
import subprocess
import sys

from measure_songbird_chirps_beak_inlet_rate_propagation_44100 import (
    NETWORK, compare_archived_build_inputs, render_variants,
)
from measure_songbird_chirps_beak_load import ROOT
from measure_songbird_chirps_beak_tip_inflow_44100 import registered_artifacts
from measure_songbird_chirps_left_syrinx_half_inertance_44100 import (
    CASE as HALF_CASE, FIRST_TRACHEAL_FLOW, PATCH as HALF_PATCH, RIGHT_FLOW, WALL_FLOW,
    baseline_patches, configure, inlet_pressure, pressure_residual, propagate,
)
from measure_songbird_chirps_left_syrinx_port_44100 import (
    AREA, BASE_ID, BRONCHUS, CASE as PORT_CASE, FLOW, TRACHEA, replay, stored_trace,
)
from measure_songbird_chirps_oec_neck_44100 import diagnose
from measure_songbird_chirps_oec_neck_momentum_44100 import compare_traces
from measure_songbird_chirps_oec_pressure_44100 import CONDITIONS
from measure_songbird_chirps_terminal_numerator_44100 import same_bits
from measure_songbird_chirps_trachea_interior_momentum_44100 import apply_edits
from measure_songbird_chirps_volume_rate_propagation_44100 import DERIVATIVE, PRESSURE
from measure_speech_timing import read, write
from measure_uniform_tube import candidate_sources, record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/songbird-chirps-left-syrinx-momentum-44100.json'
LABELS = ('half-control', 'syrinx-momentum')
PATCH = 'left-syrinx-momentum'
LINEAR_LABELS = ('momentum-control', 'syrinx-linear')
LINEAR_PATCH = 'left-syrinx-linear'
RIGHT_BRONCHUS = 'right_bronchus_pressure_dyn_cm2'


def edit_momentum(workspace, patch):
    apply_edits(workspace, patch, {
        NETWORK: (('                    || trachea_momentum_branches.contains(&index),',
                   '''                    || trachea_momentum_branches.contains(&index)
                    || left_half_branch == Some(index),'''),),
    })


def edit_linear(workspace, patch):
    apply_edits(workspace, patch, {
        NETWORK: (('                linear_inertance_branch == Some(index) || neck_momentum_branch == Some(index),',
                   '''                linear_inertance_branch == Some(index)
                    || neck_momentum_branch == Some(index)
                    || left_half_branch == Some(index),'''),),
    })


def replay_ports(trace, start, port_case, label, checks, condition, *, multiply_momentum, multiply_linear,
                 multiply_right_half=False, multiply_right_momentum=False, multiply_right_linear=False):
    upstream = label == 'upstream'
    segments = {
        'left': replay(trace, start, port_case, upstream=upstream, multiply_left_half=True,
                       multiply_momentum=multiply_momentum, multiply_linear=multiply_linear),
        'right': replay(trace, start, port_case, upstream=upstream, multiply_left_half=multiply_right_half,
                        multiply_momentum=multiply_right_momentum, multiply_linear=multiply_right_linear, side='right'),
        'inlet_pressure': inlet_pressure(trace, start, port_case),
    }
    prefix = f'{condition}/{label}'
    for side in ('left', 'right'):
        rows = segments[side]
        checks[f'{prefix}/{side}/flow_bit_replayed'] = all(
            row['observed'].hex() == row['result']['flow'].hex() for row in rows)
        checks[f'{prefix}/{side}/closed_flow_zero'] = all(
            row['observed'] == 0.0 for row in rows if row['closed'])
    checks[f'{prefix}/inlet_pressure_bit_replayed'] = all(
        row['observed'].hex() == row['predicted'].hex() for row in segments['inlet_pressure'])
    return segments


def measure(case, half, port, saved, upstream_saved, patches, snapshot, copies, out, execute, *,
            same_build_inputs=True):
    linear = case.get('left_port_term', 'momentum') == 'linear'
    labels, patch_stem, edit, archived_label = (
        (LINEAR_LABELS, LINEAR_PATCH, edit_linear, LABELS[1]) if linear
        else (LABELS, PATCH, edit_momentum, 'bronchus-half'))
    configs = configure(case, saved, out)
    paths, build = render_variants(configs, patches, snapshot, copies, out, execute,
                                   edit=edit, patch_stem=patch_stem, labels=labels)
    prior = read(saved['summary.json'])
    rate, window = case['sample_rate_hz'], case['observation_internal_samples']
    target = case.get('target_condition', 'matched_time')
    distances = half['distances_from_port_in_samples'] | {
        FIRST_TRACHEAL_FLOW: 1, RIGHT_FLOW: 1, RIGHT_BRONCHUS: 1, WALL_FLOW: 1, PRESSURE: 16, DERIVATIVE: 22,
    }
    checks = {'only_network_branch_selection_edited': build['changed_paths'] == [NETWORK],
              'compiled_binaries_distinct': build['control_binary_sha256'] != build['experimental_binary_sha256'],
              'reciprocal_sample_period_equals_rate': (1 / (1 / rate)).hex() == float(rate).hex()}
    if same_build_inputs:
        checks['built_control_matches_archived_binary'] = (
            build['control_binary_sha256'] == prior['build']['experimental_binary_sha256'])
    else:
        build['archived_build_inputs_match'] = False
    results, hypotheses, series = {}, {}, {}
    for name in CONDITIONS:
        start = case['condition_control_samples'][name]
        archived = saved[f'artifacts/{name}-{archived_label}.csv']
        checks[f'{name}/control_csv_reproduced'] = sha256(paths[labels[0]][name]) == sha256(archived)
        traces = {label: stored_trace(paths[label][name], start + window) for label in labels}
        traces['upstream'] = stored_trace(upstream_saved[f'artifacts/{name}-upstream.csv'], start + window)
        local = series[name] = {label: replay_ports(
            trace, start, port, label, checks, name, multiply_momentum=linear or label == labels[1],
            multiply_linear=linear and label == labels[1]) for label, trace in traces.items()}
        control, variant, reference = traces.values()
        checks[f'{name}/left_and_right_port_geometry_identical'] = all(
            same_bits(control[key], variant[key]) and same_bits(control[key], reference[key])
            for key in (AREA, 'right_port_area_cm2', 'left_opening', 'right_opening'))
        result, _ = compare_traces(name, traces, start, half, half['neck'], checks,
                                   momentum_labels=labels, linear_labels=labels,
                                   extra_observed=(FLOW, BRONCHUS, RIGHT_FLOW, RIGHT_BRONCHUS, TRACHEA,
                                                   FIRST_TRACHEAL_FLOW, WALL_FLOW),
                                   propagation=lambda delta, _: propagate(delta, distances))
        before, after, effect = (result[key] for key in ('control_minus_upstream', 'experiment_minus_upstream',
                                                        'experiment_minus_control'))
        expected = case['expected_control_flow_offsets'][name]
        current = after.get(FLOW, {}).get('offset')
        checks[f'{name}/baseline_offset_reproduced'] = (
            expected == before.get(FLOW, {}).get('offset')
            == prior['conditions'][name]['experiment_minus_upstream'].get(FLOW, {}).get('offset'))
        if name == target:
            checks[f'{name}/registered_first_port_difference_removed'] = current is None or current > expected
            hypotheses[f'{name}/effect_begins_on_registered_sample'] = effect.get(FLOW, {}).get('offset') == expected
            if linear:
                index = start + expected
                checks[f'{name}/right_port_still_differs_from_upstream_at_registered_sample'] = (
                    float(control[RIGHT_FLOW][index]).hex() == float(variant[RIGHT_FLOW][index]).hex()
                    != float(reference[RIGHT_FLOW][index]).hex())
                result['right_port_at_registered_sample'] = {
                    label: float(trace[RIGHT_FLOW][index]) for label, trace in traces.items()}
        elif name != 'no_tracking':
            hypotheses[f'{name}/{name.split("_")[0]}_first_port_difference_remains'] = current == expected
        residuals = {side: diagnose(local[labels[1]][side], local['upstream'][side], after.get(key, {}).get('offset'),
                                    rate, pressure_keys=('bronchus_pressure', 'trachea_pressure'))
                     for side, key in (('left', FLOW), ('right', RIGHT_FLOW))}
        results[name] = result | {
            'first_residual_port_flow': residuals,
            'first_residual_inlet_pressure': pressure_residual(
                local, after.get(TRACHEA, {}).get('offset'), candidate_label=labels[1]),
        }
    write(out / f'{patch_stem}-replay.json', series)
    return {'checks': checks, 'hypotheses': hypotheses, 'conditions': results, 'build': build,
            'sample_rate_hz': rate, 'window': window}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('--case', type=Path, default=CASE)
    args = parser.parse_args()
    case_path = args.case.resolve()
    case, half, port = (read(path) for path in (case_path, HALF_CASE, PORT_CASE))
    term = case.get('left_port_term', 'momentum')
    if term not in ('momentum', 'linear'):
        parser.error('左ポートの時間換算は momentum または linear を指定してください')
    linear = term == 'linear'
    momentum = read(CASE) if linear else case
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    if any(case[key] != half[key] for key in (
            'upstream_revision', 'sample_rate_hz', 'output_rate_hz', 'condition_control_samples',
            'observation_internal_samples')):
        parser.error('左半セルの先行実験と条件が一致しません')
    names = ('summary.json', f'artifacts/{HALF_PATCH}.patch',
             *(f'artifacts/{name}{suffix}' for name in CONDITIONS for suffix in ('.json', '-bronchus-half.csv')))
    manifest, saved = registered_artifacts(momentum['baseline'], half['id'], revision, names)
    previous = read(manifest)
    indexed = {item['path']: item['sha256'] for item in previous['inputs']}
    if any(indexed.get(path.relative_to(ROOT).as_posix()) != sha256(path) for path in (HALF_CASE, PORT_CASE)):
        parser.error('先行実験で使った左半セルとポートのケース定義が必要です')
    upstream_manifest, upstream_saved = registered_artifacts(
        half['baseline'], BASE_ID, revision, ('summary.json', 'artifacts/trachea-all-momentum.patch',
                                               *(f'artifacts/{name}-upstream.csv' for name in CONDITIONS)))
    patches = [*baseline_patches(upstream_manifest, upstream_saved), saved[f'artifacts/{HALF_PATCH}.patch']]
    prior_build = read(saved['summary.json'])['build']
    if [sha256(path) for path in patches] != [*prior_build['preceding_patch_sha256'], prior_build['inlet_patch_sha256']]:
        parser.error('先行実験の差分または適用順が一致しません')
    references = [manifest, *saved.values()]
    control_manifest = manifest
    if linear:
        momentum_names = ('summary.json', f'artifacts/{PATCH}.patch', *(f'artifacts/{name}{suffix}'
                          for name in CONDITIONS for suffix in ('.json', f'-{LABELS[1]}.csv')))
        momentum_manifest, momentum_saved = registered_artifacts(case['baseline'], momentum['id'], revision, momentum_names)
        entry = next((item for item in read(momentum_manifest)['inputs']
                      if item['path'] == CASE.relative_to(ROOT).as_posix()), None)
        if entry is None or entry['sha256'] != sha256(CASE):
            parser.error('持ち越し運動量の先行実験で使ったケース定義が必要です')
        patches.append(momentum_saved[f'artifacts/{PATCH}.patch'])
        prior_build = read(momentum_saved['summary.json'])['build']
        if [sha256(path) for path in patches] != [*prior_build['preceding_patch_sha256'], prior_build['inlet_patch_sha256']]:
            parser.error('持ち越し運動量までの差分または適用順が一致しません')
        references.extend((CASE, momentum_manifest, *momentum_saved.values()))
        control_manifest = momentum_manifest
        saved = momentum_saved
    traced_tools = [ROOT / name for name in indexed
                    if (ROOT / name).parent == WORKSPACE / 'tools']
    upstream_sources = [ROOT / name for name in indexed if (ROOT / name).is_relative_to(UPSTREAM)]
    copies = [*candidate_sources(), WORKSPACE / 'data/cmudict.txt.gz', WORKSPACE / 'data/mandarin.txt.gz']
    same_build_inputs = compare_archived_build_inputs(control_manifest, copies)
    inputs = [case_path, HALF_CASE, PORT_CASE, Path(__file__), *references, upstream_manifest,
              *upstream_saved.values(), *patches, *copies, *traced_tools, *upstream_sources]
    details = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision,
               'analysis_command': [sys.executable, *sys.argv], 'analysis_directory': str(Path.cwd())}
    snapshot = WORKSPACE / 'runs' / args.run_id / 'artifacts/source'
    return record_measurement(args.run_id, case_path, inputs, details,
                              lambda out, execute: measure(case, half, port, saved, upstream_saved, patches,
                                                           snapshot, copies, out, execute,
                                                           same_build_inputs=same_build_inputs),
                              command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
