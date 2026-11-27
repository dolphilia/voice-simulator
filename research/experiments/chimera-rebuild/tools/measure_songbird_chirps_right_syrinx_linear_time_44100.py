"""右鳴管ポートの線形係数の時間換算を切り替え、気管入口圧を比較する。"""

import argparse
from pathlib import Path
import subprocess
import sys

from measure_songbird_chirps_beak_inlet_rate_propagation_44100 import NETWORK, render_variants
from measure_songbird_chirps_beak_load import ROOT
from measure_songbird_chirps_beak_tip_inflow_44100 import registered_artifacts
from measure_songbird_chirps_bronchus_inlet_balance_44100 import CASE as UPPER_CASE
from measure_songbird_chirps_left_syrinx_half_inertance_44100 import RIGHT_FLOW, configure, pressure_residual
from measure_songbird_chirps_left_syrinx_momentum_44100 import replay_ports
from measure_songbird_chirps_left_syrinx_port_44100 import CASE as PORT_CASE, TRACHEA, replay, stored_trace
from measure_songbird_chirps_oec_neck_44100 import diagnose
from measure_songbird_chirps_oec_pressure_44100 import CONDITIONS
from measure_songbird_chirps_right_syrinx_half_inertance_44100 import restore_patches
from measure_songbird_chirps_terminal_numerator_44100 import same_bits
from measure_songbird_chirps_trachea_interior_momentum_44100 import apply_edits
from measure_songbird_chirps_trachea_wall_surface_44100 import CASE as PRIOR_CASE, LABEL as PRIOR_PATCH
from measure_songbird_chirps_volume_rate_propagation_44100 import differences
from measure_speech_timing import read, write
from measure_uniform_tube import candidate_sources, record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/songbird-chirps-right-syrinx-linear-time-44100.json'
PATCH = 'right-syrinx-linear-time'
LABELS = ('control', PATCH)


def edit_right_linear(workspace, patch):
    apply_edits(workspace, patch, {NETWORK: (
        ('''                linear_inertance_branch == Some(index)
                    || neck_momentum_branch == Some(index)
                    || left_half_branch == Some(index),''',
         '''                linear_inertance_branch == Some(index)
                    || neck_momentum_branch == Some(index)
                    || left_half_branch == Some(index)
                    || right_half_branch == Some(index),'''),
    )})


def acoustic_differences(traces, start, variant_label=PATCH):
    control, variant, upper = (traces[label][start:] for label in ('control', variant_label, 'upstream'))
    acoustic = tuple(field for field in control.dtype.names if field.endswith(('_dyn_cm2', '_cm3_s', '_cm3_s2')))
    common = tuple(field for field in acoustic if field in upper.dtype.names)
    return {
        'control_minus_upstream': differences(control, upper, common, left_label='control', right_label='upstream'),
        'experiment_minus_upstream': differences(variant, upper, common, left_label=variant_label, right_label='upstream'),
        'experiment_minus_control': differences(variant, control, acoustic, left_label=variant_label,
                                                right_label='control'),
    }


def first_predicted_effect(trace, start, port):
    rows = replay(trace, start, port, upstream=False, multiply_left_half=True,
                  multiply_momentum=True, multiply_linear=True, side='right')
    return next(({'offset': i, 'flow_hex': row['result']['flow'].hex()} for i, row in enumerate(rows)
                 if row['result']['flow'].hex() != row['observed'].hex()), None)


def measure(case, port, saved, upper, patches, snapshot, copies, out, execute):
    configs = configure(case, saved, out)
    paths, build = render_variants(configs, patches, snapshot, copies, out, execute, edit=edit_right_linear,
                                   patch_stem=PATCH, labels=LABELS)
    baseline = read(saved['summary.json'])
    checks = {
        'only_network_patched': build['changed_paths'] == [NETWORK],
        'experiment_binary_differs': build['experimental_binary_sha256'] != build['control_binary_sha256'],
        'control_binary_reproduced': build['control_binary_sha256'] == baseline['build']['experimental_binary_sha256'],
    }
    results, series = {}, {}
    rate, window = case['sample_rate_hz'], case['observation_internal_samples']
    for name in CONDITIONS:
        start = case['condition_control_samples'][name]
        checks[f'{name}/control_csv_reproduced'] = sha256(paths['control'][name]) == sha256(
            saved[f'artifacts/{name}-{PRIOR_PATCH}.csv'])
        traces = {label: stored_trace(paths[label][name], start + window) for label in LABELS}
        traces['upstream'] = stored_trace(upper[f'artifacts/{name}-upstream.csv'], start + window)
        control, variant, reference = traces.values()
        acoustic = tuple(field for field in control.dtype.names if field.endswith(('_dyn_cm2', '_cm3_s', '_cm3_s2')))
        geometry = tuple(field for field in control.dtype.names if field.endswith(('_area_cm2', '_length_cm', '_opening')))
        delays = case['minimum_delays_from_right_port_samples']
        if control.dtype.names != variant.dtype.names or not set(delays).issubset(acoustic):
            raise ValueError('伝播を比較する観測列が見つかりません')
        checks[f'{name}/geometry_identical'] = all(same_bits(control[field], variant[field]) for field in geometry)
        checks[f'{name}/port_areas_and_openings_match_reference'] = all(
            same_bits(variant[field], reference[field])
            for field in ('left_port_area_cm2', 'right_port_area_cm2', 'left_opening', 'right_opening'))
        checks[f'{name}/before_onset_identical'] = all(
            same_bits(control[field][:start], variant[field][:start]) for field in acoustic)
        rows = series[name] = {label: replay_ports(
            trace, start, port, label, checks, name, multiply_momentum=True, multiply_linear=True,
            multiply_right_half=True, multiply_right_momentum=True, multiply_right_linear=label == PATCH)
            for label, trace in traces.items()}
        comparison = acoustic_differences(traces, start)
        before, after, effect = comparison.values()
        for field, expected in case['control_first_offsets'][name].items():
            archived = (baseline['conditions'][name]['experiment_to_upstream']['inlet_pressure']
                        if field == TRACHEA else None)
            checks[f'{name}/{field}/registered_control_offset'] = before.get(field, {}).get('offset') == expected
            if field == TRACHEA:
                checks[f'{name}/archived_inlet_offset_reproduced'] = (
                    (archived['offset'] if archived else None) == expected)
        registered = case['predicted_first_flow_effect'][name]
        predicted = first_predicted_effect(control, start, port)
        first = effect.get(RIGHT_FLOW)
        measured = {'offset': first['offset'], 'flow_hex': float(first[PATCH]).hex()} if first else None
        checks[f'{name}/first_effect_matches_prediction'] = registered == predicted == measured
        if registered is None:
            checks[f'{name}/no_experimental_effect'] = not effect
            checks[f'{name}/unexcited'] = all(
                (trace[field] == 0).all() for trace in traces.values() for field in ('left_flow_cm3_s', RIGHT_FLOW, TRACHEA))
        else:
            offset = registered['offset']
            checks[f'{name}/flow_at_prediction_matches_upstream'] = (
                float(variant[RIGHT_FLOW][start + offset]).hex() == float(reference[RIGHT_FLOW][start + offset]).hex())
            checks[f'{name}/effect_respects_propagation'] = all(
                value['offset'] >= offset + delays.get(field, 0) for field, value in effect.items())
        old_inlet_offset = before.get(TRACHEA, {}).get('offset')
        results[name] = comparison | {
            'first_flow_effect': {'predicted': predicted, 'measured': measured},
            'inlet_at_control_offset': pressure_residual(rows, old_inlet_offset, candidate_label=PATCH),
            'first_residual_inlet': pressure_residual(rows, after.get(TRACHEA, {}).get('offset'), candidate_label=PATCH),
            'first_residual_right_port': diagnose(rows[PATCH]['right'], rows['upstream']['right'],
                                                  after.get(RIGHT_FLOW, {}).get('offset'), rate,
                                                  pressure_keys=('bronchus_pressure', 'trachea_pressure')),
        }
    write(out / f'{PATCH}-replay.json', series)
    return {'checks': checks, 'conditions': results, 'build': build, 'sample_rate_hz': rate, 'window': window}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    case, prior, upper_case, port = (read(path) for path in (CASE, PRIOR_CASE, UPPER_CASE, PORT_CASE))
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    if any(case[key] != prior[key] or case[key] != upper_case[key] for key in (
            'upstream_revision', 'sample_rate_hz', 'output_rate_hz', 'condition_control_samples',
            'observation_internal_samples')) or case['sample_rate_hz'] != port['sample_rate_hz']:
        parser.error('先行実行と右鳴管の観測条件が一致しません')
    names = ('summary.json', f'artifacts/{PRIOR_PATCH}.patch', *(f'artifacts/{name}{suffix}'
             for name in CONDITIONS for suffix in ('.json', f'-{PRIOR_PATCH}.csv')))
    manifest_path, saved = registered_artifacts(case['baseline'], prior['id'], revision, names)
    upper_manifest, upper = registered_artifacts(case['upstream_observation'], upper_case['id'], revision,
                                                 tuple(f'artifacts/{name}-upstream.csv' for name in CONDITIONS))
    manifest = read(manifest_path)
    indexed = {row['path']: row['sha256'] for row in manifest['inputs']}
    if any(indexed.get(path.relative_to(ROOT).as_posix()) != sha256(path)
           for path in (PRIOR_CASE, UPPER_CASE, PORT_CASE, upper_manifest, *upper.values())):
        parser.error('先行実行で使用したケース定義と固定上流CSVが必要です')
    patches = restore_patches(manifest, saved, PRIOR_PATCH)
    copies = [*candidate_sources(), WORKSPACE / 'data/cmudict.txt.gz', WORKSPACE / 'data/mandarin.txt.gz']
    references = [ROOT / path for path in indexed
                  if (ROOT / path).parent == WORKSPACE / 'tools' or (ROOT / path).is_relative_to(UPSTREAM)]
    inputs = [CASE, PRIOR_CASE, UPPER_CASE, PORT_CASE, Path(__file__), manifest_path, *saved.values(), upper_manifest,
              *upper.values(), *patches, *copies, *references]
    details = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision,
               'analysis_command': [sys.executable, *sys.argv], 'analysis_directory': str(Path.cwd())}
    snapshot = WORKSPACE / 'runs' / args.run_id / 'artifacts/source'
    return record_measurement(args.run_id, CASE, inputs, details,
                              lambda out, execute: measure(case, port, saved, upper, patches, snapshot, copies,
                                                           out, execute),
                              command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
