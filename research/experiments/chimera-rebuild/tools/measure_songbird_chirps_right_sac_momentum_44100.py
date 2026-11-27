"""片側の空気嚢ポートの持ち越し項を揃え、気管支と放射までを照合する。"""

import argparse
from pathlib import Path
import subprocess
import sys

from measure_songbird_airway import RHO, SIDES
from measure_songbird_chirps_beak_inlet_rate_propagation_44100 import NETWORK, SONGBIRD, render_variants
from measure_songbird_chirps_beak_load import ROOT
from measure_songbird_chirps_beak_tip_inflow_44100 import registered_artifacts
from measure_songbird_chirps_bronchus_end_balance_44100 import (
    balance_columns, compare_end, locate_pressure_residual,
)
from measure_songbird_chirps_bronchus_inlet_balance_44100 import CASE as PRIOR_CASE, SAC, replay
from measure_songbird_chirps_left_syrinx_half_inertance_44100 import configure
from measure_songbird_chirps_left_syrinx_port_44100 import stored_trace
from measure_songbird_chirps_oec_neck_44100 import diagnose
from measure_songbird_chirps_oec_pressure_44100 import CONDITIONS
from measure_songbird_chirps_right_syrinx_half_inertance_44100 import find_recorded_patches, restore_patches
from measure_songbird_chirps_terminal_numerator_44100 import same_bits
from measure_songbird_chirps_trachea_interior_momentum_44100 import apply_edits
from measure_songbird_chirps_volume_rate_propagation_44100 import differences
from measure_speech_timing import read, write
from measure_uniform_tube import candidate_sources, record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/songbird-chirps-right-sac-momentum-44100.json'
PATCH = 'right-sac-momentum'
LEFT_PATCH = 'left-sac-momentum'
LEFT_PRIOR_PATCH = 'left-bronchus-interior-momentum'
LEFT_PRIOR_CASE = WORKSPACE / f'cases/songbird-chirps-{LEFT_PRIOR_PATCH}-44100.json'


def edit_right_sac_momentum(workspace, patch):
    apply_edits(workspace, patch, {
        NETWORK: (
            ('            inlet, inlet_flow_cm3_s, prescribed, 0..0, None, None, None, None, 0..0, None, None, None, None,',
             '            inlet, inlet_flow_cm3_s, prescribed, 0..0, None, None, None, None, 0..0, None, None, None, None, None,'),
            ('        bronchus_inlet_branch: Option<usize>,',
             '        bronchus_inlet_branch: Option<usize>,\n        sac_momentum_branch: Option<usize>,'),
            ('                    || right_half_branch == Some(index),',
             '                    || right_half_branch == Some(index)\n                    || sac_momentum_branch == Some(index),'),
        ),
        SONGBIRD: (
            ('            Some(self.bronchi[1].first_branch),',
             '            Some(self.bronchi[1].first_branch),\n            Some(self.sac_ports[1]),'),
        ),
    })


def edit_left_sac_momentum(workspace, patch):
    apply_edits(workspace, patch, {
        NETWORK: (
            ('''            inlet, inlet_flow_cm3_s, prescribed, 0..0, None, None, None, None, 0..0, None, None, None, None, None, None, None, None,''',
             '''            inlet, inlet_flow_cm3_s, prescribed, 0..0, None, None, None, None, 0..0, None, None, None, None, &[], None, None, None,'''),
            ('        sac_momentum_branch: Option<usize>,', '        sac_momentum_branches: &[usize],'),
            ('                    || sac_momentum_branch == Some(index),',
             '                    || sac_momentum_branches.contains(&index),'),
        ),
        SONGBIRD: (
            ('            Some(self.sac_ports[1]),', '            &self.sac_ports,'),
        ),
    })


def replay_fixed_ports(traces, start, name, prior, checks, target, variant_label):
    series = {}
    for side in SIDES:
        series[side] = {}
        pressure, outflow, sac, inflow, *_ = balance_columns(side, 0)
        for label, trace in traces.items():
            aligned = (side == target and label == variant_label) or (target == 'left' and side == 'right')
            rows, gain = replay(trace, start, side, prior, upstream=label == 'upstream',
                                multiply_momentum=aligned)
            series[side][label] = rows
            prefix = f'{name}/{side}/{label}'
            checks[f'{prefix}/pressure_bit_replayed'] = all(
                row['pressure'].hex() == row['observed_pressure'].hex() for row in rows)
            checks[f'{prefix}/port_flow_bit_replayed'] = all(
                row['result']['flow'].hex() == row['observed'].hex() for row in rows)
            checks[f'{prefix}/sac_matches_boundary'] = same_bits(trace[sac], trace[SAC])
            checks[f'{prefix}/outlet_matches_cell_1_inflow'] = same_bits(
                trace[outflow], trace[balance_columns(side, 1)[3]])
            if name == 'no_tracking':
                checks[f'{prefix}/unexcited'] = all((trace[field] == 0).all() for field in (pressure, outflow, sac, inflow))
    return series, gain


def measure(case, prior, saved, patches, snapshot, copies, out, execute):
    target = case.get('sac_side', 'right')
    left = target == 'left'
    variant_label, edit = (LEFT_PATCH, edit_left_sac_momentum) if left else (PATCH, edit_right_sac_momentum)
    labels = ('control', variant_label)
    pressure, _, _, inflow, _, _ = balance_columns(target, 0)
    configs = configure(case, saved, out)
    if any(read(path)['songbird_airway']['observe_bronchus_interior_cells'] != [1, 0] for path in configs.values()):
        raise ValueError('先行実行のセル1・0の観測指定が必要です')
    paths, build = render_variants(configs, patches, snapshot, copies, out, execute,
                                   edit=edit, patch_stem=variant_label, labels=labels)
    baseline = read(saved['summary.json'])
    archived_binary = (baseline['build']['experimental_binary_sha256']
                       if left else baseline['candidate_binary_sha256'])
    checks = {
        'only_network_and_songbird_patched': set(build['changed_paths']) == {NETWORK, SONGBIRD},
        'experiment_binary_differs': build['experimental_binary_sha256'] != build['control_binary_sha256'],
        'control_binary_reproduced': build['control_binary_sha256'] == archived_binary,
    }
    results, series = {}, {}
    rate, window = case['sample_rate_hz'], case['observation_internal_samples']
    geom = prior['geometry']
    half_cell = geom['length_cm'] / geom['cells'] * (1 / geom['area_cm2'])
    interior_inertance = (0.5 * RHO) * (half_cell + half_cell)
    archived_label = LEFT_PRIOR_PATCH if left else 'candidate'
    for name in CONDITIONS:
        start = case['condition_control_samples'][name]
        source = saved[f'artifacts/{name}-{archived_label}.csv']
        checks[f'{name}/control_csv_reproduced'] = sha256(paths['control'][name]) == sha256(source)
        traces = {label: stored_trace(paths[label][name], start + window) for label in labels}
        traces['upstream'] = stored_trace(saved[f'artifacts/{name}-upstream.csv'], start + window)
        control, variant, upper = traces.values()
        acoustic = tuple(field for field in control.dtype.names if field.endswith(('_dyn_cm2', '_cm3_s', '_cm3_s2')))
        comparable = tuple(field for field in acoustic if field in upper.dtype.names)
        candidate_only = [field for field in acoustic if field not in upper.dtype.names]
        fixed = tuple(field for field in control.dtype.names if field.endswith(('_area_cm2', '_length_cm', '_opening')))
        if control.dtype.names != variant.dtype.names or not set(case['minimum_delays_from_port_samples']).issubset(comparable):
            raise ValueError('伝播を照合する観測列がありません')
        checks[f'{name}/geometry_and_boundary_identical'] = (
            all(same_bits(control[field], variant[field]) for field in fixed)
            and same_bits(control[SAC], variant[SAC]) and same_bits(variant[SAC], upper[SAC]))
        checks[f'{name}/before_onset_identical'] = all(
            same_bits(control[field][:start], variant[field][:start]) for field in acoustic)
        pair = {
            'control_minus_upstream': differences(control[start:], upper[start:], comparable,
                                                 left_label='control', right_label='upstream'),
            'experiment_minus_upstream': differences(variant[start:], upper[start:], comparable,
                                                     left_label=variant_label, right_label='upstream'),
            'experiment_minus_control': differences(variant[start:], control[start:], acoustic,
                                                    left_label=variant_label, right_label='control'),
        }
        before, after, effect = pair.values()
        registered = case['predicted_first_port_effect'][name]
        expected = registered['offset'] if registered else None
        archived = baseline['conditions'][name]
        archived_offset = (archived['experiment_minus_upstream'].get(inflow, {}).get('offset')
                           if left else archived['right']['first_differences'][inflow])
        checks[f'{name}/registered_control_offset'] = (
            before.get(inflow, {}).get('offset') == expected == archived_offset)
        predicted_rows, _ = replay(control, start, target, prior, upstream=False, multiply_momentum=True)
        predicted = next(({'offset': i, 'flow_hex': row['result']['flow'].hex()}
                          for i, row in enumerate(predicted_rows)
                          if row['result']['flow'].hex() != row['observed'].hex()), None)
        measured = effect.get(inflow)
        measured = {'offset': measured['offset'], 'flow_hex': float(measured[variant_label]).hex()} if measured else None
        checks[f'{name}/first_effect_matches_prediction'] = predicted == registered == measured
        if expected is None:
            checks[f'{name}/no_experimental_effect'] = not effect
        else:
            remaining = after.get(inflow, {}).get('offset', window)
            checks[f'{name}/registered_difference_removed'] = remaining > expected
            checks[f'{name}/effect_respects_propagation'] = all(
                value['offset'] >= expected + case['minimum_delays_from_port_samples'].get(field, 0)
                for field, value in effect.items())
        port, gain = replay_fixed_ports(traces, start, name, prior, checks, target, variant_label)
        selected = port[target]
        compare_port = {'candidate': selected[variant_label], 'upstream': selected['upstream']}
        if left:
            checks[f'{name}/left_port_coefficients_identical'] = all(
                a['terms'][key].hex() == b['terms'][key].hex()
                for a, b in zip(selected['control'], selected[variant_label], strict=True)
                for key in ('normalized_inertance', 'resistance', 'forward_loss', 'reverse_loss'))
        inner, inner_rows = compare_end({'candidate': variant, 'upstream': upper}, start, target, f'{name}/cell_1',
                                       prior, checks, candidate_linear_inertance=interior_inertance * rate,
                                       candidate_momentum_inertance=interior_inertance,
                                       verify_registered_pressure=False, interior_cell=1)
        results[name] = pair | {
            'candidate_only_observations': candidate_only,
            f'first_{target}_port_effect': {'predicted': predicted, 'measured': measured},
            f'first_residual_{target}_port': diagnose(compare_port['candidate'], compare_port['upstream'],
                                                     after.get(inflow, {}).get('offset'), rate,
                                                     pressure_keys=('sac_pressure', 'cell_pressure')),
            f'first_residual_{target}_cell_0': locate_pressure_residual(
                compare_port, after.get(pressure, {}).get('offset'), gain),
            f'{target}_cell_1_balance': inner,
        }
        series[name] = {'sac_ports': port, f'{target}_cell_1': inner_rows}
    write(out / f'{variant_label}-replay.json', series)
    return {'checks': checks, 'conditions': results, 'build': build, 'sample_rate_hz': rate, 'window': window}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('--case', type=Path, default=CASE)
    args = parser.parse_args()
    case_path = args.case.resolve()
    case = read(case_path)
    target = case.get('sac_side', 'right')
    if target not in SIDES:
        parser.error('空気嚢ポートには left または right を指定してください')
    left = target == 'left'
    prior_path = LEFT_PRIOR_CASE if left else PRIOR_CASE
    prior, observation = read(prior_path), read(PRIOR_CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    if any(case[key] != prior[key] or case[key] != observation[key] for key in (
            'upstream_revision', 'sample_rate_hz', 'output_rate_hz', 'condition_control_samples',
            'observation_internal_samples')):
        parser.error('先行実行と持ち越し項の比較条件が一致しません')
    if left and any(prior['geometry'][key] != observation['geometry'][key] for key in ('length_cm', 'cells', 'area_cm2')):
        parser.error('先行実行の気管支の幾何が一致しません')
    prior_artifacts = (f'artifacts/{LEFT_PRIOR_PATCH}.patch',) if left else ()
    traces = (f'-{LEFT_PRIOR_PATCH}.csv',) if left else ('-candidate.csv', '-upstream.csv')
    names = ('summary.json', *prior_artifacts, *(f'artifacts/{name}{suffix}' for name in CONDITIONS
                                                for suffix in ('.json', *traces)))
    manifest_path, saved = registered_artifacts(case['baseline'], prior['id'], revision, names)
    manifest = read(manifest_path)
    indexed = {row['path']: row['sha256'] for row in manifest['inputs']}
    if indexed.get(prior_path.relative_to(ROOT).as_posix()) != sha256(prior_path):
        parser.error('先行実行で使用したケース定義が必要です')
    extra_inputs = []
    if left:
        upper_manifest, upper = registered_artifacts(
            case['upstream_observation'], observation['id'], revision,
            tuple(f'artifacts/{name}-upstream.csv' for name in CONDITIONS))
        extra_inputs = [PRIOR_CASE, upper_manifest, *upper.values()]
        if any(indexed.get(path.relative_to(ROOT).as_posix()) != sha256(path) for path in extra_inputs):
            parser.error('先行実行で使用した空気嚢のケース定義と固定上流CSVが必要です')
        saved.update(upper)
        patches = restore_patches(manifest, saved, LEFT_PRIOR_PATCH)
    else:
        patches = find_recorded_patches(manifest, read(saved['summary.json'])['applied_patch_sha256'])
    copies = [*candidate_sources(), WORKSPACE / 'data/cmudict.txt.gz', WORKSPACE / 'data/mandarin.txt.gz']
    references = [ROOT / path for path in indexed
                  if (ROOT / path).parent == WORKSPACE / 'tools' or (ROOT / path).is_relative_to(UPSTREAM)]
    inputs = [case_path, prior_path, Path(__file__), manifest_path, *saved.values(), *extra_inputs,
              *patches, *copies, *references]
    details = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision,
               'analysis_command': [sys.executable, *sys.argv], 'analysis_directory': str(Path.cwd())}
    snapshot = WORKSPACE / 'runs' / args.run_id / 'artifacts/source'
    return record_measurement(args.run_id, case_path, inputs, details,
                              lambda out, execute: measure(case, observation, saved, patches, snapshot, copies, out, execute),
                              command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
