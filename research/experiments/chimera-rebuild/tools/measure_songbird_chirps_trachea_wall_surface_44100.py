"""気管セルの側面積だけを上流順に切り替え、壁流量と圧力を照合する。"""

import argparse
from functools import partial
from pathlib import Path
import subprocess
import sys

from measure_songbird_chirps_beak_inlet_rate_propagation_44100 import NETWORK, SONGBIRD, render_variants
from measure_songbird_chirps_beak_load import ROOT
from measure_songbird_chirps_beak_tip_inflow_44100 import registered_artifacts
from measure_songbird_chirps_bronchus_inlet_balance_44100 import CASE as UPPER_CASE
from measure_songbird_chirps_left_syrinx_half_inertance_44100 import configure, inlet_pressure, pressure_residual
from measure_songbird_chirps_left_syrinx_port_44100 import CASE as PORT_CASE, stored_trace
from measure_songbird_chirps_oec_pressure_44100 import CONDITIONS
from measure_songbird_chirps_right_sac_momentum_44100 import CASE as PRIOR_CASE, PATCH as PRIOR_PATCH
from measure_songbird_chirps_right_syrinx_half_inertance_44100 import restore_patches
from measure_songbird_chirps_terminal_numerator_44100 import first_offset, same_bits
from measure_songbird_chirps_trachea_interior_balance_44100 import compare_cell, interior_columns, interior_replay_view
from measure_songbird_chirps_trachea_interior_momentum_44100 import apply_edits
from measure_speech_timing import read, write
from measure_uniform_tube import candidate_sources, record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/songbird-chirps-trachea-cell10-wall-surface-44100.json'
LABEL = 'wall-surface'
INLET = 'trachea_pressure_dyn_cm2'


def edit_wall_surface(workspace, patch, *, cell):
    apply_edits(workspace, patch, {
        NETWORK: (
            ('            inlet, inlet_flow_cm3_s, prescribed, 0..0, None, None, None, None, 0..0, None, None, None, None, None,',
             '            inlet, inlet_flow_cm3_s, prescribed, 0..0, None, None, None, None, 0..0, None, None, None, None, None, None,'),
            ('        sac_momentum_branch: Option<usize>,',
             '        sac_momentum_branch: Option<usize>,\n        wall_surface_node: Option<usize>,'),
            ('                let surface = section.wall_surface();',
             '''                let surface = if wall_surface_node == Some(node) {
                    section.perimeter_factor * 2.0 * PI.sqrt()
                        * section.area_cm2.max(MIN_CELL_AREA_CM2).sqrt()
                        * section.length_cm
                } else {
                    section.wall_surface()
                };'''),
        ),
        SONGBIRD: (
            ('            Some(self.sac_ports[1]),',
             f'            Some(self.sac_ports[1]),\n            Some(self.trachea.first + {cell}),'),
        ),
    })


def compare_trachea(traces, start, prefix, case, port, checks, *, variant):
    results, selected_rows = {}, None
    indices = range(1, case['trachea_cells'] - 1)
    cell = case['trachea_cell_index']
    inlet_rows = {side: {'inlet_pressure': inlet_pressure(trace, start, port)}
                  for side, trace in traces.items()}
    for side, rows in inlet_rows.items():
        checks[f'{prefix}/{side}/inlet_pressure_bit_replayed'] = all(
            row['predicted'].hex() == row['observed'].hex() for row in rows['inlet_pressure'])
    offset = first_offset(*(trace[INLET][start:] for trace in traces.values()))
    for index in indices:
        columns = interior_columns(index)
        views = {side: interior_replay_view(trace, columns) for side, trace in traces.items()}
        results[index], rows = compare_cell(case, index, f'{prefix}/cell_{index}', views, start, checks,
                                             upstream_wall_surface=variant and index == cell)
        if index == cell:
            selected_rows = rows
    return {'inlet_pressure': pressure_residual(inlet_rows, offset, candidate_label='candidate'),
            'cells': results}, selected_rows


def measure(case, saved, upper, patches, snapshot, copies, out, execute):
    cell, count = case['trachea_cell_index'], case['trachea_cells']
    configs = configure(case, saved, out)
    for path in configs.values():
        settings = read(path)['songbird_airway']
        if set(settings['observe_trachea_interior_cells']) != set(range(1, count - 1)):
            raise ValueError('全内部セルの観測が必要です')
    paths, build = render_variants(configs, patches, snapshot, copies, out, execute,
                                   edit=partial(edit_wall_surface, cell=cell), patch_stem=LABEL,
                                   labels=('control', LABEL))
    baseline = read(saved['summary.json'])
    checks = {
        'patch_changes_only_network_and_songbird': set(build['changed_paths']) == {NETWORK, SONGBIRD},
        'control_binary_reproduced': build['control_binary_sha256'] == baseline['build']['experimental_binary_sha256'],
        'experiment_binary_differs': build['control_binary_sha256'] != build['experimental_binary_sha256'],
    }
    window = case['observation_internal_samples']
    port = read(PORT_CASE)
    conditions, series = {}, {}
    columns = {index: interior_columns(index) for index in range(1, count - 1)}
    wall = columns[cell][4]
    for name in CONDITIONS:
        start = case['condition_control_samples'][name]
        checks[f'{name}/control_csv_reproduced'] = sha256(paths['control'][name]) == sha256(
            saved[f'artifacts/{name}-{PRIOR_PATCH}.csv'])
        control, variant = (stored_trace(paths[key][name], start + window) for key in ('control', LABEL))
        reference = stored_trace(upper[f'artifacts/{name}-upstream.csv'], start + window)
        for label, trace in (('control', control), (LABEL, variant), ('upstream', reference)):
            for index, names in columns.items():
                area, length = names[6:8]
                checks[f'{name}/{label}/cell_{index}/registered_geometry'] = bool(
                    (trace[area] == case['trachea_area_cm2']).all()
                    and (trace[length] == case['trachea_length_cm'] / count).all())
                if index + 1 in columns:
                    following = columns[index + 1]
                    checks[f'{name}/{label}/cell_{index}/consistent_observations'] = (
                        same_bits(trace[names[3]], trace[following[2]])
                        and same_bits(trace[names[0]], trace[following[1]]))
        compared = {key: compare_trachea({'candidate': trace, 'upstream': reference}, start, f'{name}/{key}',
                                       case | {'multiply_inlet_momentum_cells': list(columns)}, port, checks,
                                       variant=key == LABEL)
                    for key, trace in (('control', control), (LABEL, variant))}
        before, after = (compared[key][0] for key in ('control', LABEL))
        series[name] = {key: value[1] for key, value in compared.items()}
        actual = first_offset(control[wall][start:], variant[wall][start:])
        predicted = case['predicted_first_wall_effect'][name]
        measured = None if actual is None else {'offset': actual, 'flow_hex': float(variant[wall][start + actual]).hex()}
        checks[f'{name}/first_wall_effect_as_registered'] = measured == predicted
        if actual is not None:
            checks[f'{name}/first_wall_difference_removed'] = (
                float(variant[wall][start + actual]).hex() == float(reference[wall][start + actual]).hex())
        fields = (INLET, 'radiation_flow_cm3_s', 'radiation_derivative_cm3_s2',
                  *(field for names in columns.values() for field in names[:6]))
        effects = {field: first_offset(control[field][start:], variant[field][start:]) for field in fields}
        if name == 'native_block':
            offsets = before['cells']
            expected = case['native_pressure_offsets']
            checks[f'{name}/registered_pressure_offsets'] = (
                before['inlet_pressure']['offset'] == expected['0'] and all(
                    offsets[int(index)]['first_differences']['pressure_dyn_cm2'] == value
                    for index, value in expected.items() if index != '0'))
            fault = offsets[cell]['first_pressure_residual']
            checks[f'{name}/only_wall_input_differs'] = [entry['swapped_inputs'] for entry in fault['substitutions']
                                                       if entry['matches_upstream']] == [('wall_outflow',)]
            checks[f'{name}/registered_pressure_difference_removed'] = (
                float(variant[columns[cell][0]][start + expected[str(cell)]]).hex()
                == float(reference[columns[cell][0]][start + expected[str(cell)]]).hex())
        if name == 'no_tracking':
            checks[f'{name}/acoustics_all_zero'] = all(
                (trace[field] == 0).all() for trace in (control, variant, reference) for field in fields)
        conditions[name] = {'control_to_upstream': before, 'experiment_to_upstream': after,
                            'first_effect': effects, 'first_wall_effect': measured}
    write(out / 'wall-surface-replay.json', series)
    return {'checks': checks, 'conditions': conditions, 'build': build, 'sample_rate_hz': case['sample_rate_hz'],
            'window': window, 'trachea_cell_index': cell}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    case, prior, upper_case = (read(path) for path in (CASE, PRIOR_CASE, UPPER_CASE))
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    if any(case[key] != prior[key] or case[key] != upper_case[key] for key in (
            'upstream_revision', 'sample_rate_hz', 'output_rate_hz', 'condition_control_samples',
            'observation_internal_samples')):
        parser.error('先行実行と気管の観測条件が一致しません')
    if not 0 < case['trachea_cell_index'] < case['trachea_cells'] - 1:
        parser.error('気管の内部セルを指定してください')
    names = ('summary.json', f'artifacts/{PRIOR_PATCH}.patch', *(f'artifacts/{name}{suffix}'
             for name in CONDITIONS for suffix in ('.json', f'-{PRIOR_PATCH}.csv')))
    manifest_path, saved = registered_artifacts(case['baseline'], prior['id'], revision, names)
    upper_manifest, upper = registered_artifacts(case['upstream_observation'], upper_case['id'], revision,
                                                 tuple(f'artifacts/{name}-upstream.csv' for name in CONDITIONS))
    manifest = read(manifest_path)
    indexed = {row['path']: row['sha256'] for row in manifest['inputs']}
    if any(indexed.get(path.relative_to(ROOT).as_posix()) != sha256(path)
           for path in (PRIOR_CASE, UPPER_CASE, upper_manifest, *upper.values())):
        parser.error('先行実行で使用したケース定義と固定上流CSVが必要です')
    patches = restore_patches(manifest, saved, PRIOR_PATCH)
    copies = [*candidate_sources(), WORKSPACE / 'data/cmudict.txt.gz', WORKSPACE / 'data/mandarin.txt.gz']
    references = [ROOT / path for path in indexed
                  if (ROOT / path).parent == WORKSPACE / 'tools' or (ROOT / path).is_relative_to(UPSTREAM)]
    references.extend(WORKSPACE / 'tools' / name for name in (
        'measure_songbird_chirps_trachea_interior_balance_44100.py',
        'measure_songbird_chirps_trachea_end_balance_44100.py'))
    references.append(PORT_CASE)
    inputs = [CASE, PRIOR_CASE, UPPER_CASE, Path(__file__), manifest_path, *saved.values(), upper_manifest,
              *upper.values(), *patches, *copies, *references]
    details = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision,
               'analysis_command': [sys.executable, *sys.argv], 'analysis_directory': str(Path.cwd())}
    snapshot = WORKSPACE / 'runs' / args.run_id / 'artifacts/source'
    return record_measurement(args.run_id, CASE, inputs, details,
                              lambda out, execute: measure(case, saved, upper, patches, snapshot, copies, out, execute),
                              command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
