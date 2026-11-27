"""左気管支の直列枝で線形慣性または持ち越し運動量を上流順に切り替える。"""

import argparse
from pathlib import Path
import subprocess
import sys

from measure_songbird_airway import RHO, SIDES
from measure_songbird_chirps_beak_inlet_rate_propagation_44100 import NETWORK, SONGBIRD, render_variants
from measure_songbird_chirps_beak_load import ROOT
from measure_songbird_chirps_beak_tip_inflow_44100 import registered_artifacts
from measure_songbird_chirps_bronchus_end_balance_44100 import balance_columns, compare_end, replay_end
from measure_songbird_chirps_bronchus_inlet_balance_44100 import CASE as UPPER_CASE
from measure_songbird_chirps_left_syrinx_half_inertance_44100 import configure, pressure_residual
from measure_songbird_chirps_left_syrinx_momentum_44100 import replay_ports
from measure_songbird_chirps_left_syrinx_port_44100 import CASE as PORT_CASE, FLOW, TRACHEA, stored_trace
from measure_songbird_chirps_oec_neck_44100 import diagnose
from measure_songbird_chirps_oec_pressure_44100 import CONDITIONS
from measure_songbird_chirps_right_syrinx_half_inertance_44100 import restore_patches
from measure_songbird_chirps_right_syrinx_linear_time_44100 import (
    CASE as PRIOR_CASE, PATCH as PRIOR_PATCH, acoustic_differences,
)
from measure_songbird_chirps_terminal_numerator_44100 import same_bits
from measure_songbird_chirps_trachea_interior_momentum_44100 import apply_edits
from measure_speech_timing import read, write
from measure_uniform_tube import candidate_sources, record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/songbird-chirps-left-bronchus-linear-44100.json'
MOMENTUM_CASE = WORKSPACE / 'cases/songbird-chirps-left-bronchus-momentum-44100.json'
INTERIOR_CASE = WORKSPACE / 'cases/songbird-chirps-left-bronchus-interior-linear-44100.json'
PATCH = 'left-bronchus-linear'
MOMENTUM_PATCH = 'left-bronchus-momentum'
INTERIOR_PATCH = 'left-bronchus-interior-linear'
INTERIOR_MOMENTUM_PATCH = 'left-bronchus-interior-momentum'


def edit_left_bronchus_linear(workspace, patch):
    apply_edits(workspace, patch, {
        NETWORK: (
            ('            inlet, inlet_flow_cm3_s, prescribed, 0..0, None, None, None, None, 0..0, None, None, None, None, None, None,',
             '            inlet, inlet_flow_cm3_s, prescribed, 0..0, None, None, None, None, 0..0, None, None, None, None, None, None, None,'),
            ('        wall_surface_node: Option<usize>,',
             '        wall_surface_node: Option<usize>,\n        left_bronchus_end_branch: Option<usize>,'),
            ('            let bronchus_inertance = (bronchus_end || bronchus_inlet).then(|| {',
             '''            let left_bronchus_end = left_bronchus_end_branch == Some(index);
            let bronchus_inertance = (bronchus_end || bronchus_inlet || left_bronchus_end).then(|| {'''),
            ('''                bronchus_inertance,
                bronchus_inertance.filter(|_| bronchus_inlet).map(|inertia| inertia * self.dt.recip()),''',
             '''                bronchus_inertance.filter(|_| !left_bronchus_end),
                bronchus_inertance
                    .filter(|_| bronchus_inlet || left_bronchus_end)
                    .map(|inertia| inertia * self.dt.recip()),'''),
        ),
        SONGBIRD: (
            ('            Some(self.trachea.first + 10),',
             '''            Some(self.trachea.first + 10),
            Some(self.bronchi[0].first_branch + self.bronchi[0].count - 2),'''),
        ),
    })


def edit_left_bronchus_momentum(workspace, patch):
    apply_edits(workspace, patch, {NETWORK: (
        ('                bronchus_inertance.filter(|_| !left_bronchus_end),',
         '                bronchus_inertance,'),
    )})


def edit_left_interior_linear(workspace, patch):
    apply_edits(workspace, patch, {
        NETWORK: (
            ('            inlet, inlet_flow_cm3_s, prescribed, 0..0, None, None, None, None, 0..0, None, None, None, None, None, None, None,',
             '            inlet, inlet_flow_cm3_s, prescribed, 0..0, None, None, None, None, 0..0, None, None, None, None, None, None, None, None,'),
            ('        left_bronchus_end_branch: Option<usize>,',
             '        left_bronchus_end_branch: Option<usize>,\n        left_bronchus_inlet_branch: Option<usize>,'),
            ('''            let bronchus_inertance = (bronchus_end || bronchus_inlet || left_bronchus_end).then(|| {
                let half = |section: Section| section.length_cm * section.area_cm2.max(1e-6).recip();
                0.5 * AIR_DENSITY * (half(self.sections[left]) + half(self.sections[right]))
            });''',
             '''            let left_bronchus_inlet = left_bronchus_inlet_branch == Some(index);
            let bronchus_inertance =
                (bronchus_end || bronchus_inlet || left_bronchus_end || left_bronchus_inlet).then(|| {
                    let half = |section: Section| section.length_cm * section.area_cm2.max(1e-6).recip();
                    0.5 * AIR_DENSITY * (half(self.sections[left]) + half(self.sections[right]))
                });'''),
            ('''                bronchus_inertance,
                bronchus_inertance
                    .filter(|_| bronchus_inlet || left_bronchus_end)''',
             '''                bronchus_inertance.filter(|_| !left_bronchus_inlet),
                bronchus_inertance
                    .filter(|_| bronchus_inlet || left_bronchus_end || left_bronchus_inlet)'''),
        ),
        SONGBIRD: (
            ('            Some(self.bronchi[0].first_branch + self.bronchi[0].count - 2),',
             '''            Some(self.bronchi[0].first_branch + self.bronchi[0].count - 2),
            Some(self.bronchi[0].first_branch),'''),
        ),
    })


def edit_left_interior_momentum(workspace, patch):
    apply_edits(workspace, patch, {NETWORK: (
        ('                bronchus_inertance.filter(|_| !left_bronchus_inlet),',
         '                bronchus_inertance,'),
    )})


MODES = {
    'linear': (PRIOR_CASE, PRIOR_PATCH, PATCH, edit_left_bronchus_linear),
    'momentum': (CASE, PATCH, MOMENTUM_PATCH, edit_left_bronchus_momentum),
    'interior_linear': (MOMENTUM_CASE, MOMENTUM_PATCH, INTERIOR_PATCH, edit_left_interior_linear),
    'interior_momentum': (INTERIOR_CASE, INTERIOR_PATCH, INTERIOR_MOMENTUM_PATCH, edit_left_interior_momentum),
}


def compare_bronchus_ends(case, traces, start, name, checks, inertance, variant_label, *, term):
    linear = inertance * case['sample_rate_hz']
    results, series = {}, {}
    for label in ('control', variant_label):
        results[label], series[label] = {}, {}
        for side in SIDES:
            right = side == 'right'
            variant = label == variant_label
            results[label][side], series[label][side] = compare_end(
                {'candidate': traces[label], 'upstream': traces['upstream']}, start, side, f'{name}/{label}',
                case, checks, candidate_linear_inertance=linear if right or term != 'linear' or variant else None,
                candidate_momentum_inertance=(
                    inertance if right or term.startswith('interior_') or (term == 'momentum' and variant) else None),
                verify_registered_pressure=False)
    return results, series


def measure(case, port, saved, upper, patches, snapshot, copies, out, execute):
    term = case.get('left_bronchus_term', 'linear')
    momentum = term in ('momentum', 'interior_momentum')
    interior_cell = 1 if term.startswith('interior_') else None
    inflow = balance_columns('left', interior_cell)[3]
    _, archived_label, variant_label, edit = MODES[term]
    labels = ('control', variant_label)
    configs = configure(case, saved, out)
    paths, build = render_variants(configs, patches, snapshot, copies, out, execute,
                                   edit=edit, patch_stem=variant_label, labels=labels)
    baseline = read(saved['summary.json'])
    scope = 'only_network_patched' if momentum else 'only_network_and_songbird_patched'
    changed = {NETWORK} if momentum else {NETWORK, SONGBIRD}
    checks = {
        scope: set(build['changed_paths']) == changed,
        'experiment_binary_differs': build['experimental_binary_sha256'] != build['control_binary_sha256'],
        'control_binary_reproduced': build['control_binary_sha256'] == baseline['build']['experimental_binary_sha256'],
    }
    rate, window = case['sample_rate_hz'], case['observation_internal_samples']
    geometry = case['geometry']
    half = geometry['length_cm'] / geometry['cells'] * (1 / geometry['area_cm2'])
    inertance = (0.5 * RHO) * (half + half)
    results, series = {}, {}
    for name in CONDITIONS:
        start = case['condition_control_samples'][name]
        checks[f'{name}/control_csv_reproduced'] = sha256(paths['control'][name]) == sha256(
            saved[f'artifacts/{name}-{archived_label}.csv'])
        traces = {label: stored_trace(paths[label][name], start + window) for label in labels}
        traces['upstream'] = stored_trace(upper[f'artifacts/{name}-upstream.csv'], start + window)
        control, variant, reference = traces.values()
        geometry_fields = tuple(field for field in control.dtype.names
                                if field.endswith(('_area_cm2', '_length_cm', '_opening')))
        acoustic = tuple(field for field in control.dtype.names if field.endswith(('_dyn_cm2', '_cm3_s', '_cm3_s2')))
        delays = case['minimum_delays_from_left_branch_samples']
        if control.dtype.names != variant.dtype.names or not set(delays).issubset(acoustic):
            raise ValueError('伝播を比較する観測列が見つかりません')
        checks[f'{name}/geometry_identical'] = all(
            same_bits(control[field], variant[field]) for field in geometry_fields)
        checks[f'{name}/before_onset_identical'] = all(
            same_bits(control[field][:start], variant[field][:start]) for field in acoustic)
        end_results, end_rows = compare_bronchus_ends(
            case, traces, start, name, checks, inertance, variant_label, term=term)
        branch_rows = {label: end_rows[label]['left'] for label in labels}
        ports = {label: replay_ports(trace, start, port, label, checks, name,
                                    multiply_momentum=True, multiply_linear=True, multiply_right_half=True,
                                    multiply_right_momentum=True, multiply_right_linear=True)
                 for label, trace in traces.items()}
        comparison = acoustic_differences(traces, start, variant_label)
        before, after, effect = comparison.values()
        expected = case['predicted_first_inflow_effect'][name]
        predicted_rows, _ = replay_end(control, start, 'left', 'candidate', geometry, rate,
                                       linear_inertance=inertance * rate,
                                       momentum_inertance=inertance if momentum else None, interior_cell=interior_cell)
        predicted = next(({'offset': i, 'flow_hex': row['branch']['inflow'].hex()}
                          for i, row in enumerate(predicted_rows)
                          if row['branch']['inflow'].hex() != row['pressure_inputs']['inflow'].hex()), None)
        first = effect.get(inflow)
        measured = {'offset': first['offset'], 'flow_hex': float(first[variant_label]).hex()} if first else None
        checks[f'{name}/first_effect_matches_prediction'] = predicted == expected == measured
        control_offset = before.get(inflow, {}).get('offset')
        old_offset = baseline['conditions'][name]['experiment_minus_upstream'].get(inflow, {}).get('offset')
        checks[f'{name}/registered_control_inflow_offset'] = (
            control_offset == old_offset == (expected['offset'] if expected else None))
        if expected is None:
            checks[f'{name}/no_experimental_effect'] = not effect
            checks[f'{name}/unexcited'] = all(
                (trace[field] == 0).all() for trace in traces.values() for field in acoustic if field in reference.dtype.names)
        else:
            origin = expected['offset']
            checks[f'{name}/initial_flow_reconciled'] = after.get(inflow, {}).get('offset', window) > origin
            checks[f'{name}/effect_respects_propagation'] = all(
                observed['offset'] >= origin + delays.get(field, 0) for field, observed in effect.items())
        results[name] = comparison | {
            'first_inflow_effect': {'predicted': predicted, 'measured': measured},
            'bronchus_end_balance': end_results,
            'first_residual_inlet_pressure': pressure_residual(
                ports, after.get(TRACHEA, {}).get('offset'), candidate_label=variant_label),
            'first_residual_left_port': diagnose(ports[variant_label]['left'], ports['upstream']['left'],
                                                 after.get(FLOW, {}).get('offset'), rate,
                                                 pressure_keys=('bronchus_pressure', 'trachea_pressure')),
        }
        series[name] = {'bronchus_end': end_rows, 'ports': ports}
        if interior_cell is not None:
            interior_results, interior_rows = {}, {}
            for label in labels:
                interior_results[label], interior_rows[label] = compare_end(
                    {'candidate': traces[label], 'upstream': reference}, start, 'left', f'{name}/{label}/interior',
                    case, checks, candidate_linear_inertance=inertance * rate if momentum or label == variant_label else None,
                    candidate_momentum_inertance=inertance if momentum and label == variant_label else None,
                    verify_registered_pressure=False, interior_cell=interior_cell)
            results[name]['left_interior_balance'] = interior_results
            series[name]['left_interior'] = interior_rows
            branch_rows = interior_rows
        if momentum:
            left_control_rows = branch_rows['control']['candidate']
            left_experiment_rows = branch_rows[variant_label]['candidate']
            checks[f'{name}/left_branch_linear_coefficient_identical'] = all(
                a['branch']['linear_coefficient'].hex() == b['branch']['linear_coefficient'].hex()
                for a, b in zip(left_control_rows, left_experiment_rows, strict=True))
    write(out / f'{variant_label}-replay.json', series)
    return {'checks': checks, 'conditions': results, 'build': build, 'sample_rate_hz': rate, 'window': window}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('--case', type=Path, default=CASE)
    args = parser.parse_args()
    case_path = args.case.resolve()
    case = read(case_path)
    term = case.get('left_bronchus_term', 'linear')
    if term not in MODES:
        parser.error(f'左気管支の比較モードを指定してください ({", ".join(MODES)})')
    prior_path, prior_patch, _, _ = MODES[term]
    prior, upper_case, port = (read(path) for path in (prior_path, UPPER_CASE, PORT_CASE))
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    if any(case[key] != prior[key] or case[key] != upper_case[key] for key in (
            'upstream_revision', 'sample_rate_hz', 'output_rate_hz', 'condition_control_samples',
            'observation_internal_samples')) or case['sample_rate_hz'] != port['sample_rate_hz']:
        parser.error('先行実行と左気管支の観測条件が一致しません')
    if any(value != upper_case['geometry'][key] or value != port['geometry'][f'bronchus_{key}']
           for key, value in case['geometry'].items()):
        parser.error('先行実行の気管支の幾何が一致しません')
    names = ('summary.json', f'artifacts/{prior_patch}.patch', *(f'artifacts/{name}{suffix}'
             for name in CONDITIONS for suffix in ('.json', f'-{prior_patch}.csv')))
    manifest_path, saved = registered_artifacts(case['baseline'], prior['id'], revision, names)
    upper_manifest, upper = registered_artifacts(case['upstream_observation'], upper_case['id'], revision,
                                                 tuple(f'artifacts/{name}-upstream.csv' for name in CONDITIONS))
    manifest = read(manifest_path)
    indexed = {row['path']: row['sha256'] for row in manifest['inputs']}
    if any(indexed.get(path.relative_to(ROOT).as_posix()) != sha256(path)
           for path in (prior_path, UPPER_CASE, PORT_CASE, upper_manifest, *upper.values())):
        parser.error('先行実行で使用したケース定義と固定上流CSVが必要です')
    patches = restore_patches(manifest, saved, prior_patch)
    copies = [*candidate_sources(), WORKSPACE / 'data/cmudict.txt.gz', WORKSPACE / 'data/mandarin.txt.gz']
    references = [ROOT / path for path in indexed
                  if (ROOT / path).parent == WORKSPACE / 'tools' or (ROOT / path).is_relative_to(UPSTREAM)]
    inputs = [case_path, prior_path, UPPER_CASE, PORT_CASE, Path(__file__), manifest_path, *saved.values(), upper_manifest,
              *upper.values(), *patches, *copies, *references]
    details = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision,
               'analysis_command': [sys.executable, *sys.argv], 'analysis_directory': str(Path.cwd())}
    snapshot = WORKSPACE / 'runs' / args.run_id / 'artifacts/source'
    return record_measurement(args.run_id, case_path, inputs, details,
                              lambda out, execute: measure(case, port, saved, upper, patches, snapshot, copies,
                                                           out, execute),
                              command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
