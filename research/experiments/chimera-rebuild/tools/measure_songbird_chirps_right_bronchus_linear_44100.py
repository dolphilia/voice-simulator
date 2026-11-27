"""右気管支の最後の直列枝で線形係数または持ち越しの慣性を切り替える。"""

import argparse
from pathlib import Path
import subprocess
import sys

from measure_songbird_airway import RHO, SIDES
from measure_songbird_chirps_beak_inlet_rate_propagation_44100 import (
    NETWORK, SONGBIRD, compare_archived_build_inputs, render_variants,
)
from measure_songbird_chirps_beak_load import ROOT
from measure_songbird_chirps_beak_tip_inflow_44100 import registered_artifacts
from measure_songbird_chirps_bronchus_end_balance_44100 import (
    CASE as BALANCE_CASE, OBSERVATIONS, balance_columns, compare_end, replay_end,
)
from measure_songbird_chirps_left_syrinx_half_inertance_44100 import (
    CASE as HALF_CASE, FIRST_TRACHEAL_FLOW, RIGHT_FLOW, WALL_FLOW, configure, pressure_residual, propagate,
)
from measure_songbird_chirps_left_syrinx_momentum_44100 import RIGHT_BRONCHUS, replay_ports
from measure_songbird_chirps_left_syrinx_port_44100 import AREA, BRONCHUS, CASE as PORT_CASE, FLOW, TRACHEA, stored_trace
from measure_songbird_chirps_oec_neck_44100 import diagnose
from measure_songbird_chirps_oec_neck_momentum_44100 import compare_traces
from measure_songbird_chirps_oec_pressure_44100 import CONDITIONS
from measure_songbird_chirps_right_syrinx_half_inertance_44100 import find_recorded_patches, restore_patches
from measure_songbird_chirps_terminal_numerator_44100 import same_bits
from measure_songbird_chirps_trachea_interior_momentum_44100 import apply_edits
from measure_songbird_chirps_volume_rate_propagation_44100 import DERIVATIVE, PRESSURE, RADIATION
from measure_speech_timing import read, write
from measure_uniform_tube import candidate_sources, record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/songbird-chirps-right-bronchus-linear-44100.json'
INTERIOR_CASE = WORKSPACE / 'cases/songbird-chirps-bronchus-interior-balance-44100.json'
INTERIOR_LINEAR_CASE = WORKSPACE / 'cases/songbird-chirps-right-bronchus-interior-linear-44100.json'
LABELS = ('bronchus-control', 'bronchus-linear')
PATCH = 'right-bronchus-linear'
MOMENTUM_LABELS = ('linear-control', 'bronchus-momentum')
MOMENTUM_PATCH = 'right-bronchus-momentum'
INTERIOR_LABELS = ('interior-control', 'interior-linear')
INTERIOR_PATCH = 'right-bronchus-interior-linear'
INTERIOR_MOMENTUM_LABELS = ('interior-linear-control', 'interior-momentum')
INTERIOR_MOMENTUM_PATCH = 'right-bronchus-interior-momentum'
RIGHT_INFLOW = 'right_bronchus_end_inflow_cm3_s'
RIGHT_UPSTREAM_PRESSURE = 'right_bronchus_end_upstream_pressure_dyn_cm2'


def edit_bronchus_linear(workspace, patch):
    apply_edits(workspace, patch, {
        NETWORK: (
            ('        multiply_linear_inertance: bool,', '        multiply_linear_inertance: bool,\n        linear_inertance_override: Option<f64>,'),
            ('        let linear = inertance_per_step + self.resistance;',
             '        let linear = linear_inertance_override.unwrap_or(inertance_per_step) + self.resistance;'),
            ('            inlet, inlet_flow_cm3_s, prescribed, 0..0, None, None, None, None, 0..0, None, None,',
             '            inlet, inlet_flow_cm3_s, prescribed, 0..0, None, None, None, None, 0..0, None, None, None,'),
            ('        right_half_branch: Option<usize>,',
             '        right_half_branch: Option<usize>,\n        bronchus_linear_branch: Option<usize>,'),
            ('''            let flow = branch.step(
                self.dt,''',
             '''            let linear_inertance_override = (bronchus_linear_branch == Some(index)).then(|| {
                let half = |section: Section| section.length_cm * section.area_cm2.max(1e-6).recip();
                let inertia = 0.5 * AIR_DENSITY * (half(self.sections[left]) + half(self.sections[right]));
                inertia * self.dt.recip()
            });
            let flow = branch.step(
                self.dt,'''),
            ('''                    || left_half_branch == Some(index),
            );
            self.net_flow[left] -= flow;''',
             '''                    || left_half_branch == Some(index),
                linear_inertance_override,
            );
            self.net_flow[left] -= flow;'''),
        ),
        SONGBIRD: (
            ('            Some(self.syrinx_ports[1]),\n        );',
             '''            Some(self.syrinx_ports[1]),
            Some(self.bronchi[1].first_branch + self.bronchi[1].count - 2),
        );'''),
        ),
    })


def edit_bronchus_momentum(workspace, patch):
    apply_edits(workspace, patch, {
        NETWORK: (
            ('        linear_inertance_override: Option<f64>,', '        bronchus_inertance: Option<f64>,'),
            ('        let history = if multiply_momentum {',
             '''        let history = if let Some(inertance) = bronchus_inertance {
            (inertance * self.flow) * dt.recip()
        } else if multiply_momentum {'''),
            ('        let linear = linear_inertance_override.unwrap_or(inertance_per_step) + self.resistance;',
             '''        let linear_inertance = bronchus_inertance.map_or(inertance_per_step, |inertance| {
            inertance * dt.recip()
        });
        let linear = linear_inertance + self.resistance;'''),
            ('            let linear_inertance_override = (bronchus_linear_branch == Some(index)).then(|| {',
             '            let bronchus_inertance = (bronchus_linear_branch == Some(index)).then(|| {'),
            ('''                let inertia = 0.5 * AIR_DENSITY * (half(self.sections[left]) + half(self.sections[right]));
                inertia * self.dt.recip()''',
             '                0.5 * AIR_DENSITY * (half(self.sections[left]) + half(self.sections[right]))'),
            ('                linear_inertance_override,', '                bronchus_inertance,'),
        ),
    })


def edit_interior_linear(workspace, patch):
    apply_edits(workspace, patch, {
        NETWORK: (
            ('        bronchus_inertance: Option<f64>,',
             '        bronchus_inertance: Option<f64>,\n        inlet_linear_inertance: Option<f64>,'),
            ('        let linear = linear_inertance + self.resistance;',
             '        let linear = inlet_linear_inertance.unwrap_or(linear_inertance) + self.resistance;'),
            ('            inlet, inlet_flow_cm3_s, prescribed, 0..0, None, None, None, None, 0..0, None, None, None,',
             '            inlet, inlet_flow_cm3_s, prescribed, 0..0, None, None, None, None, 0..0, None, None, None, None,'),
            ('        bronchus_linear_branch: Option<usize>,',
             '        bronchus_linear_branch: Option<usize>,\n        bronchus_inlet_branch: Option<usize>,'),
            ('            let bronchus_inertance = (bronchus_linear_branch == Some(index)).then(|| {',
             '''            let bronchus_end = bronchus_linear_branch == Some(index);
            let bronchus_inlet = bronchus_inlet_branch == Some(index);
            let bronchus_inertance = (bronchus_end || bronchus_inlet).then(|| {'''),
            ('                bronchus_inertance,',
             '''                bronchus_inertance.filter(|_| bronchus_end),
                bronchus_inertance.filter(|_| bronchus_inlet).map(|inertia| inertia * self.dt.recip()),'''),
        ),
        SONGBIRD: (
            ('            Some(self.bronchi[1].first_branch + self.bronchi[1].count - 2),',
             '''            Some(self.bronchi[1].first_branch + self.bronchi[1].count - 2),
            Some(self.bronchi[1].first_branch),'''),
        ),
    })


def edit_interior_momentum(workspace, patch):
    apply_edits(workspace, patch, {
        NETWORK: (('                bronchus_inertance.filter(|_| bronchus_end),',
                   '                bronchus_inertance,'),),
    })


def measure(case, balance, half, port, saved, patches, snapshot, copies, out, execute, *, same_build_inputs=True):
    term = case.get('right_bronchus_term', 'linear')
    momentum = term == 'momentum'
    interior_momentum = term == 'interior_momentum'
    interior_cell = case.get('interior_cell')
    modes = {
        'linear': (LABELS, PATCH, edit_bronchus_linear, 'candidate'),
        'momentum': (MOMENTUM_LABELS, MOMENTUM_PATCH, edit_bronchus_momentum, LABELS[1]),
        'interior_linear': (INTERIOR_LABELS, INTERIOR_PATCH, edit_interior_linear, 'candidate'),
        'interior_momentum': (INTERIOR_MOMENTUM_LABELS, INTERIOR_MOMENTUM_PATCH,
                              edit_interior_momentum, INTERIOR_LABELS[1]),
    }
    labels, patch_stem, edit, archived_label = modes[term]
    configs = configure(case, saved, out)
    if any(read(path)['songbird_airway'].get('observe_bronchus_end_balance') is not True for path in configs.values()):
        raise ValueError('先行実行の気管支末端の観測指定が必要です')
    if interior_cell is not None and any(
        read(path)['songbird_airway'].get('observe_bronchus_interior_cells') != [interior_cell]
        for path in configs.values()
    ):
        raise ValueError('先行実行の気管支内部セルの観測指定が必要です')
    paths, build = render_variants(configs, patches, snapshot, copies, out, execute,
                                   edit=edit, patch_stem=patch_stem, labels=labels)
    prior = read(saved['summary.json'])
    rate, window = case['sample_rate_hz'], case['observation_internal_samples']
    geometry = balance['geometry']
    half_l = geometry['length_cm'] / geometry['cells'] * (1 / geometry['area_cm2'])
    inertance = (0.5 * RHO) * (half_l + half_l)
    linear_inertance = inertance * rate
    same_branch = momentum or interior_momentum
    baseline_binary = prior['build']['experimental_binary_sha256'] if same_branch else prior['candidate_binary_sha256']
    scope_key = 'only_network_patched' if same_branch else 'only_network_and_songbird_patched'
    changed = {NETWORK} if same_branch else {NETWORK, SONGBIRD}
    checks = {
        scope_key: set(build['changed_paths']) == changed,
        'experiment_binary_differs': build['control_binary_sha256'] != build['experimental_binary_sha256'],
    }
    if same_build_inputs:
        checks['control_binary_reproduced'] = build['control_binary_sha256'] == baseline_binary
    else:
        build['archived_build_inputs_match'] = False
    distances = {RIGHT_UPSTREAM_PRESSURE: 0, RIGHT_BRONCHUS: 0, RIGHT_FLOW: 1, TRACHEA: 1, FLOW: 2, BRONCHUS: 2,
                 FIRST_TRACHEAL_FLOW: 2, WALL_FLOW: 2, 'trachea_end_pressure_dyn_cm2': 16,
                 'oec_neck_inflow_cm3_s': 17, PRESSURE: 17, RADIATION: 23, DERIVATIVE: 23}
    acoustic = tuple(f'{side}_bronchus_end_{field}' for side in SIDES for field in OBSERVATIONS[:2])
    dimensions = tuple(f'{side}_bronchus_end_{field}' for side in SIDES for field in OBSERVATIONS[2:])
    inflow = RIGHT_INFLOW
    if interior_cell is not None:
        right_pressure, _, right_preceding, inflow, *_ = balance_columns('right', interior_cell)
        delays = {key: delay + 1 for key, delay in distances.items()}
        distances = delays | {right_pressure: 0, right_preceding: 0, RIGHT_UPSTREAM_PRESSURE: 0, RIGHT_INFLOW: 1}
        for side in SIDES:
            fields = balance_columns(side, interior_cell)
            acoustic += fields[:4]
            dimensions += fields[4:]
    conditions, hypotheses, series = {}, {}, {}
    for name in CONDITIONS:
        start = case['condition_control_samples'][name]
        checks[f'{name}/control_csv_reproduced'] = sha256(paths[labels[0]][name]) == sha256(
            saved[f'artifacts/{name}-{archived_label}.csv'])
        traces = {label: stored_trace(paths[label][name], start + window) for label in labels}
        traces['upstream'] = stored_trace(saved[f'artifacts/{name}-upstream.csv'], start + window)
        control, variant, upper = traces.values()
        checks[f'{name}/port_and_bronchus_geometry_identical'] = all(
            same_bits(control[field], variant[field]) and same_bits(control[field], upper[field])
            for field in (*dimensions, AREA, 'right_port_area_cm2', 'left_opening', 'right_opening'))
        variant_end, port_rows = {}, {}
        series[name] = {'bronchus': variant_end, 'ports': port_rows}
        variant_interior = {}
        if interior_cell is not None:
            series[name]['interior'] = variant_interior
        end_results = {}
        residuals = {}
        for side in SIDES:
            right = side == 'right'
            control_result, _ = compare_end(
                {'candidate': control, 'upstream': upper}, start, side, f'{name}/control',
                balance, checks, candidate_linear_inertance=linear_inertance if right and term != 'linear' else None,
                candidate_momentum_inertance=inertance if right and interior_cell is not None else None,
                verify_registered_pressure=False)
            variant_result, variant_end[side] = compare_end(
                {'candidate': variant, 'upstream': upper}, start, side, f'{name}/experiment',
                balance, checks, candidate_linear_inertance=linear_inertance if right else None,
                candidate_momentum_inertance=inertance if right and term != 'linear' else None,
                verify_registered_pressure=False)
            end_results[side] = {'control': control_result, 'experiment': variant_result}
            if interior_cell is not None:
                local_control, _ = compare_end(
                    {'candidate': control, 'upstream': upper}, start, side, f'{name}/interior_control',
                    balance, checks, candidate_linear_inertance=linear_inertance if right and interior_momentum else None,
                    verify_registered_pressure=False, interior_cell=interior_cell)
                local_variant, variant_interior[side] = compare_end(
                    {'candidate': variant, 'upstream': upper}, start, side, f'{name}/interior_experiment',
                    balance, checks, candidate_linear_inertance=linear_inertance if right else None,
                    candidate_momentum_inertance=inertance if right and interior_momentum else None,
                    verify_registered_pressure=False, interior_cell=interior_cell)
                residuals[side] = {'control': local_control, 'experiment': local_variant}
        for label, trace in traces.items():
            port_rows[label] = replay_ports(trace, start, port, label, checks, name, multiply_momentum=True,
                                             multiply_linear=True, multiply_right_half=True, multiply_right_momentum=True)
        result, _ = compare_traces(
            name, traces, start, half, half['neck'], checks, momentum_labels=labels, linear_labels=labels,
            extra_observed=(*acoustic, FLOW, BRONCHUS, RIGHT_FLOW, RIGHT_BRONCHUS, TRACHEA, FIRST_TRACHEAL_FLOW, WALL_FLOW),
            propagation=lambda effect, _: propagate(effect, distances, source_field=inflow))
        before, after, effect = (result[key] for key in ('control_minus_upstream', 'experiment_minus_upstream',
                                                        'experiment_minus_control'))
        expected = case['expected_control_inflow_offsets'][name]
        if same_branch:
            site = 'bronchus_interior_balance' if interior_momentum else 'bronchus_balance'
            prior_right = prior['conditions'][name][site]['right']['experiment']
        else:
            prior_right = prior['conditions'][name]['right']
        checks[f'{name}/registered_right_inflow_offset'] = (
            before.get(inflow, {}).get('offset') == expected == prior_right['first_differences'][inflow])
        if expected is not None:
            first_remaining = after.get(inflow, {}).get('offset')
            checks[f'{name}/registered_first_inflow_difference_removed'] = (
                first_remaining is None or first_remaining > expected)
        replay_of_control, _ = replay_end(control, start, 'right', 'candidate', geometry, rate,
                                          linear_inertance=linear_inertance,
                                          momentum_inertance=inertance if same_branch else None, interior_cell=interior_cell)
        predicted = next(({'offset': i, 'flow_hex': row['branch']['inflow'].hex()}
                          for i, row in enumerate(replay_of_control)
                          if row['branch']['inflow'].hex() != row['pressure_inputs']['inflow'].hex()), None)
        first_effect = effect.get(inflow, {}).get('offset')
        measured = None if first_effect is None else {'offset': first_effect,
                                                       'flow_hex': float(variant[inflow][start + first_effect]).hex()}
        checks[f'{name}/registered_prediction_reproduced'] = predicted == case['predicted_first_inflow_effect'][name]
        hypotheses[f'{name}/first_effect_matches_prediction'] = measured == predicted
        conditions[name] = result | {
            'bronchus_balance': end_results,
            'first_right_inflow_effect': {'predicted': predicted, 'measured': measured},
            'first_residual_right_port': diagnose(port_rows[labels[1]]['right'], port_rows['upstream']['right'],
                                                  after.get(RIGHT_FLOW, {}).get('offset'), rate,
                                                  pressure_keys=('bronchus_pressure', 'trachea_pressure')),
            'first_residual_inlet_pressure': pressure_residual(
                port_rows, after.get(TRACHEA, {}).get('offset'), candidate_label=labels[1]),
        }
        if interior_cell is not None:
            conditions[name]['bronchus_interior_balance'] = residuals
    write(out / f'{patch_stem}-replay.json', series)
    return {'checks': checks, 'hypotheses': hypotheses, 'conditions': conditions, 'build': build,
            'sample_rate_hz': rate, 'window': window, 'right_linear_inertance': linear_inertance}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('--case', type=Path, default=CASE)
    args = parser.parse_args()
    case_path = args.case.resolve()
    case, balance, half, port = (read(path) for path in (case_path, BALANCE_CASE, HALF_CASE, PORT_CASE))
    term = case.get('right_bronchus_term', 'linear')
    if term not in ('linear', 'momentum', 'interior_linear', 'interior_momentum'):
        parser.error('右気管支の変更する項は linear、momentum、interior_linear、interior_momentum のいずれかを指定してください')
    momentum = term == 'momentum'
    interior_momentum = term == 'interior_momentum'
    interior_geometry = read(INTERIOR_CASE) if term.startswith('interior_') else None
    prior_path = {'linear': BALANCE_CASE, 'momentum': CASE, 'interior_linear': INTERIOR_CASE,
                  'interior_momentum': INTERIOR_LINEAR_CASE}[term]
    prior = read(prior_path)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    if any(case[key] != prior[key] for key in ('upstream_revision', 'sample_rate_hz', 'output_rate_hz',
                                               'condition_control_samples', 'observation_internal_samples')):
        parser.error('気管支末端の先行実験と条件が一致しません')
    archived_label = LABELS[1] if momentum else INTERIOR_LABELS[1]
    trace_suffixes = ('.json', f'-{archived_label}.csv') if momentum or interior_momentum else (
        '.json', '-candidate.csv', '-upstream.csv')
    names = ('summary.json', *(f'artifacts/{name}{suffix}' for name in CONDITIONS for suffix in trace_suffixes))
    if momentum or interior_momentum:
        names += (f'artifacts/{INTERIOR_PATCH if interior_momentum else PATCH}.patch',)
    manifest_path, saved = registered_artifacts(case['baseline'], prior['id'], revision, names)
    manifest = read(manifest_path)
    indexed = {row['path']: row['sha256'] for row in manifest['inputs']}
    if interior_momentum:
        prior_case_paths = (prior_path, INTERIOR_CASE, HALF_CASE)
    elif term == 'interior_linear':
        prior_case_paths = (prior_path,)
    else:
        prior_case_paths = (prior_path, BALANCE_CASE, HALF_CASE)
    if any(indexed.get(path.relative_to(ROOT).as_posix()) != sha256(path) for path in prior_case_paths):
        parser.error('先行実験で使用したケース定義が必要です')
    if interior_geometry is not None and (
        case['interior_cell'] != prior['interior_cell'] or case['interior_cell'] != interior_geometry['interior_cell']
        or case['interior_cell'] != 1 or balance['geometry'] != interior_geometry['geometry']
    ):
        parser.error('先行実験で使用した気管支の幾何とセル1の観測設定が必要です')
    if case['sample_rate_hz'] != port['sample_rate_hz'] or balance['geometry'] != {
        field: port['geometry'][f'bronchus_{field}'] for field in balance['geometry']
    }:
        parser.error('鳴管の観測設定と気管支の幾何が一致しません')
    prior_artifacts = [manifest_path, *saved.values()]
    if momentum or interior_momentum:
        patches = restore_patches(manifest, saved, INTERIOR_PATCH if interior_momentum else PATCH)
        upper_case = interior_geometry if interior_momentum else balance
        upper_manifest, upper = registered_artifacts(
            prior['baseline'], upper_case['id'], revision, tuple(f'artifacts/{name}-upstream.csv' for name in CONDITIONS))
        if any(indexed.get(path.relative_to(ROOT).as_posix()) != sha256(path) for path in upper.values()):
            parser.error('線形慣性の先行実験で使用した固定上流CSVが必要です')
        saved.update(upper)
        prior_artifacts.extend((upper_manifest, *upper.values()))
    else:
        patches = find_recorded_patches(manifest, read(saved['summary.json'])['applied_patch_sha256'])
    copies = [*candidate_sources(), WORKSPACE / 'data/cmudict.txt.gz', WORKSPACE / 'data/mandarin.txt.gz']
    same_build_inputs = compare_archived_build_inputs(manifest_path, copies)
    references = [ROOT / name for name in indexed
                  if (ROOT / name).parent == WORKSPACE / 'tools' or (ROOT / name).is_relative_to(UPSTREAM)]
    auxiliary = [WORKSPACE / 'tools' / name for name in (
        'measure_songbird_chirps_beak_inlet_rate_propagation_44100.py', 'measure_songbird_chirps_oec_neck_momentum_44100.py',
        'measure_songbird_chirps_oec_neck_44100.py', 'measure_songbird_chirps_oec_pressure_44100.py',
        'measure_songbird_chirps_beak_momentum_propagation_44100.py', 'measure_songbird_chirps_beak_load.py')]
    inputs = [case_path, prior_path, BALANCE_CASE, HALF_CASE, PORT_CASE, Path(__file__), *prior_artifacts, *patches,
              *copies, *references, *auxiliary]
    if interior_momentum:
        inputs.append(INTERIOR_CASE)
    details = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision,
               'analysis_command': [sys.executable, *sys.argv], 'analysis_directory': str(Path.cwd())}
    snapshot = WORKSPACE / 'runs' / args.run_id / 'artifacts/source'
    return record_measurement(args.run_id, case_path, inputs, details,
                              lambda out, execute: measure(case, balance, half, port, saved, patches, snapshot,
                                                           copies, out, execute, same_build_inputs=same_build_inputs),
                              command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
