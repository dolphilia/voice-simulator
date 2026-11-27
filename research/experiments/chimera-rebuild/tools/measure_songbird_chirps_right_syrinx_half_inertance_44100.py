"""右鳴管ポートの気管支側半セルの慣性または持ち越しの換算を切り替えて描画する。"""

import argparse
from pathlib import Path
import subprocess
import sys

from measure_songbird_chirps_beak_inlet_rate_propagation_44100 import (
    NETWORK, SONGBIRD, compare_archived_build_inputs, render_variants,
)
from measure_songbird_chirps_beak_load import ROOT
from measure_songbird_chirps_beak_tip_inflow_44100 import registered_artifacts
from measure_songbird_chirps_left_syrinx_half_inertance_44100 import (
    CASE as HALF_CASE, FIRST_TRACHEAL_FLOW, RIGHT_FLOW, WALL_FLOW, configure, pressure_residual, propagate,
)
from measure_songbird_chirps_left_syrinx_momentum_44100 import (
    LINEAR_LABELS, LINEAR_PATCH, RIGHT_BRONCHUS, replay_ports,
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


CASE = WORKSPACE / 'cases/songbird-chirps-right-syrinx-half-inertance-44100.json'
LINEAR_CASE = WORKSPACE / 'cases/songbird-chirps-left-syrinx-linear-44100.json'
LABELS = ('linear-control', 'right-bronchus-half')
PATCH = 'right-syrinx-half-inertance'
MOMENTUM_LABELS = ('right-half-control', 'right-momentum')
MOMENTUM_PATCH = 'right-syrinx-momentum'


def edit_right_half(workspace, patch):
    apply_edits(workspace, patch, {
        NETWORK: (
            ('            inlet, inlet_flow_cm3_s, prescribed, 0..0, None, None, None, None, 0..0, None,',
             '            inlet, inlet_flow_cm3_s, prescribed, 0..0, None, None, None, None, 0..0, None, None,'),
            ('        left_half_branch: Option<usize>,',
             '        left_half_branch: Option<usize>,\n        right_half_branch: Option<usize>,'),
            ('                    branch.update_geometry(&self.sections, viscosity, left_half_branch == Some(index));',
             '''                    branch.update_geometry(
                        &self.sections,
                        viscosity,
                        left_half_branch == Some(index) || right_half_branch == Some(index),
                    );'''),
        ),
        SONGBIRD: (
            ('            Some(self.syrinx_ports[0]),\n        );',
             '            Some(self.syrinx_ports[0]),\n            Some(self.syrinx_ports[1]),\n        );'),
        ),
    })


def edit_right_momentum(workspace, patch):
    apply_edits(workspace, patch, {
        NETWORK: (('                    || left_half_branch == Some(index),\n                linear_inertance_branch',
                   '''                    || left_half_branch == Some(index)
                    || right_half_branch == Some(index),
                linear_inertance_branch'''),),
    })


def find_recorded_patches(manifest, digests):
    by_digest = {row['sha256']: row for row in manifest['inputs'] if row['path'].endswith('.patch')}
    paths = []
    for digest in digests:
        row = by_digest.get(digest)
        if row is None:
            raise ValueError(f'先行実行の差分が見つかりません ({digest})')
        path = ROOT / row['path']
        if path.stat().st_size != row['bytes'] or sha256(path) != digest:
            raise ValueError(f'先行実行の差分が保存時と一致しません ({path.name})')
        paths.append(path)
    return paths


def restore_patches(manifest, saved, final_patch):
    build = read(saved['summary.json'])['build']
    paths = find_recorded_patches(manifest, build['preceding_patch_sha256'])
    last = saved[f'artifacts/{final_patch}.patch']
    if sha256(last) != build['inlet_patch_sha256']:
        raise ValueError(f'先行実行の最終差分が保存時と一致しません ({final_patch})')
    return [*paths, last]


def first_predicted_effect(control, start, port, *, momentum):
    rows = replay(control, start, port, upstream=False, multiply_left_half=True, multiply_momentum=momentum,
                  side='right')
    return next(({'offset': i, 'flow_hex': row['result']['flow'].hex()}
                 for i, row in enumerate(rows) if row['result']['flow'].hex() != row['observed'].hex()), None)


def measure(case, half, port, saved, upper, patches, snapshot, copies, out, execute, *, same_build_inputs=True):
    momentum = case.get('right_port_term', 'half_inertance') == 'momentum'
    labels, patch_stem, edit, archived_label = (
        (MOMENTUM_LABELS, MOMENTUM_PATCH, edit_right_momentum, LABELS[1]) if momentum
        else (LABELS, PATCH, edit_right_half, LINEAR_LABELS[1]))
    configurations = configure(case, saved, out)
    paths, build = render_variants(configurations, patches, snapshot, copies, out, execute,
                                   edit=edit, patch_stem=patch_stem, labels=labels)
    prior = read(saved['summary.json'])
    rate, window = case['sample_rate_hz'], case['observation_internal_samples']
    distances = half['distances_from_port_in_samples'] | {
        BRONCHUS: 1, FLOW: 1, RIGHT_BRONCHUS: 0, FIRST_TRACHEAL_FLOW: 1, WALL_FLOW: 1, PRESSURE: 16, DERIVATIVE: 22,
    }
    scope_check = 'only_network_selection_edited' if momentum else 'only_network_and_songbird_selection_edited'
    changed = {NETWORK} if momentum else {NETWORK, SONGBIRD}
    checks = {scope_check: set(build['changed_paths']) == changed,
              'compiled_binaries_distinct': build['control_binary_sha256'] != build['experimental_binary_sha256']}
    if same_build_inputs:
        checks['built_control_matches_archived_binary'] = (
            build['control_binary_sha256'] == prior['build']['experimental_binary_sha256'])
    else:
        build['archived_build_inputs_match'] = False
    conditions, hypotheses, series = {}, {}, {}
    for name in CONDITIONS:
        start = case['condition_control_samples'][name]
        archived = saved[f'artifacts/{name}-{archived_label}.csv']
        checks[f'{name}/control_csv_reproduced'] = sha256(paths[labels[0]][name]) == sha256(archived)
        traces = {label: stored_trace(paths[label][name], start + window) for label in labels}
        traces['upstream'] = stored_trace(upper[f'artifacts/{name}-upstream.csv'], start + window)
        control, variant, reference = traces.values()
        local = series[name] = {
            label: replay_ports(trace, start, port, label, checks, name, multiply_momentum=True, multiply_linear=True,
                                multiply_right_half=momentum or label == labels[1],
                                multiply_right_momentum=momentum and label == labels[1])
            for label, trace in traces.items()
        }
        checks[f'{name}/left_and_right_port_geometry_identical'] = all(
            same_bits(control[key], variant[key]) and same_bits(control[key], reference[key])
            for key in (AREA, 'right_port_area_cm2', 'left_opening', 'right_opening'))
        result, _ = compare_traces(
            name, traces, start, half, half['neck'], checks, momentum_labels=labels, linear_labels=labels,
            extra_observed=(FLOW, BRONCHUS, RIGHT_FLOW, RIGHT_BRONCHUS, TRACHEA, FIRST_TRACHEAL_FLOW, WALL_FLOW),
            propagation=lambda effect, _: propagate(effect, distances, source_field=RIGHT_FLOW))
        before, after, effect = (result[key] for key in ('control_minus_upstream', 'experiment_minus_upstream',
                                                        'experiment_minus_control'))
        offset = before.get(RIGHT_FLOW, {}).get('offset')
        checks[f'{name}/baseline_right_flow_offset_reproduced'] = (
            offset == case['expected_control_right_flow_offsets'][name]
            == prior['conditions'][name]['experiment_minus_upstream'].get(RIGHT_FLOW, {}).get('offset'))
        recorded = case['predicted_first_right_flow_effect'][name]
        predicted = first_predicted_effect(control, start, port, momentum=momentum)
        first = effect.get(RIGHT_FLOW, {}).get('offset')
        measured = None if first is None else {'offset': first, 'flow_hex': float(variant[RIGHT_FLOW][start + first]).hex()}
        checks[f'{name}/archived_state_prediction_reproduced'] = predicted == recorded
        hypotheses[f'{name}/first_effect_matches_prediction'] = measured == predicted
        if offset is not None:
            result['right_flow_at_baseline_offset'] = {label: rows['right'][offset] for label, rows in local.items()}
            if momentum:
                remaining = after.get(RIGHT_FLOW, {}).get('offset')
                checks[f'{name}/registered_right_flow_difference_removed'] = remaining is None or remaining > offset
        residuals = {side: diagnose(local[labels[1]][side], local['upstream'][side], after.get(key, {}).get('offset'),
                                    rate, pressure_keys=('bronchus_pressure', 'trachea_pressure'))
                     for side, key in (('left', FLOW), ('right', RIGHT_FLOW))}
        conditions[name] = result | {
            'first_right_flow_effect': {'measured': measured, 'predicted_from_control': predicted},
            'first_residual_port_flow': residuals,
            'first_residual_inlet_pressure': pressure_residual(
                local, after.get(TRACHEA, {}).get('offset'), candidate_label=labels[1]),
        }
    write(out / f'{patch_stem}-replay.json', series)
    return {'checks': checks, 'hypotheses': hypotheses, 'conditions': conditions, 'build': build,
            'sample_rate_hz': rate, 'window': window}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('--case', type=Path, default=CASE)
    args = parser.parse_args()
    case_path = args.case.resolve()
    case, half, port = (read(path) for path in (case_path, HALF_CASE, PORT_CASE))
    term = case.get('right_port_term', 'half_inertance')
    if term not in ('half_inertance', 'momentum'):
        parser.error('右ポートの変更は half_inertance または momentum を指定してください')
    momentum = term == 'momentum'
    prior_path, final_patch, prior_label = (CASE, PATCH, LABELS[1]) if momentum else (
        LINEAR_CASE, LINEAR_PATCH, LINEAR_LABELS[1])
    prior_case = read(prior_path)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    if any(case[key] != prior_case[key] for key in ('upstream_revision', 'sample_rate_hz', 'output_rate_hz',
                                                   'condition_control_samples', 'observation_internal_samples')):
        parser.error('鳴管の先行実験と条件が一致しません')
    names = ('summary.json', f'artifacts/{final_patch}.patch', *(f'artifacts/{name}{suffix}'
              for name in CONDITIONS for suffix in ('.json', f'-{prior_label}.csv')))
    manifest_path, saved = registered_artifacts(case['baseline'], prior_case['id'], revision, names)
    manifest = read(manifest_path)
    indexed = {row['path']: row['sha256'] for row in manifest['inputs']}
    if any(indexed.get(path.relative_to(ROOT).as_posix()) != sha256(path) for path in (prior_path, HALF_CASE, PORT_CASE)):
        parser.error('先行実験で使ったケース定義が必要です')
    upper_manifest, upper = registered_artifacts(half['baseline'], BASE_ID, revision,
                                                 tuple(f'artifacts/{name}-upstream.csv' for name in CONDITIONS))
    patches = restore_patches(manifest, saved, final_patch)
    copies = [*candidate_sources(), WORKSPACE / 'data/cmudict.txt.gz', WORKSPACE / 'data/mandarin.txt.gz']
    same_build_inputs = compare_archived_build_inputs(manifest_path, copies)
    references = [ROOT / name for name in indexed
                  if (ROOT / name).parent == WORKSPACE / 'tools' or (ROOT / name).is_relative_to(UPSTREAM)]
    inputs = [case_path, prior_path, HALF_CASE, PORT_CASE, Path(__file__), manifest_path, *saved.values(),
              upper_manifest, *upper.values(), *patches, *copies, *references]
    details = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision,
               'analysis_command': [sys.executable, *sys.argv], 'analysis_directory': str(Path.cwd())}
    snapshot = WORKSPACE / 'runs' / args.run_id / 'artifacts/source'
    return record_measurement(args.run_id, case_path, inputs, details,
                              lambda out, execute: measure(case, half, port, saved, upper, patches, snapshot,
                                                           copies, out, execute, same_build_inputs=same_build_inputs),
                              command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
