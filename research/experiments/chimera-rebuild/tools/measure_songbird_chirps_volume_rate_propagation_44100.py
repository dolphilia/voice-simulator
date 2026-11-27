"""体積速度換算の1行だけを切り替え、鳴禽の腔圧から放射までを比較する。"""

import argparse
from difflib import unified_diff
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory

import numpy as np

from measure_songbird_airway import FIELDS
from measure_songbird_chirps_beak_load import ROOT, beak_fields, first_differences
from measure_songbird_chirps_beak_tip_inflow import UPPER_NETWORK, UPPER_SONGBIRD, compare_steps, diagnose_difference
from measure_songbird_chirps_beak_tip_inflow_44100 import registered_artifacts
from measure_songbird_chirps_oec_pressure_44100 import CANDIDATE_OEC, CONDITIONS, OEC, observe, substitutions
from measure_songbird_syrinx import load_trace
from measure_speech_timing import read, write
from measure_uniform_tube import candidate_sources, record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/songbird-chirps-volume-rate-propagation-44100.json'
PRESSURE = 'oec_pressure_dyn_cm2'
RADIATION = 'radiation_flow_cm3_s'
DERIVATIVE = 'radiation_derivative_cm3_s2'
INJECTION = 'oec_filtered_injection_cm3_s'


def stage_candidate(snapshot, source_files, workspace):
    known = {}
    for source in source_files:
        relative = source.relative_to(WORKSPACE)
        saved = snapshot / source.relative_to(ROOT)
        output = workspace / relative
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(saved, output)
        known[relative] = sha256(saved)
    return known


def build_and_render(workspace, target, configurations, paths, execute):
    build = ['cargo', 'build', '--release', '--locked', '--offline', '-p', 'vocal-cli',
             '--manifest-path', str(workspace / 'Cargo.toml'), '--target-dir', str(target)]
    execute(build)
    cli = target / 'release/vocal-cli'
    for name, config in configurations.items():
        execute([str(cli), 'render', str(config), str(paths[name])])
    return sha256(cli)


def render_pair(case, configurations, snapshot, source_files, out, execute):
    patch = case['variant']
    paths = {kind: {name: out / f'{name}-{kind}.csv' for name in CONDITIONS}
             for kind in ('control', 'multiply')}
    with TemporaryDirectory(prefix='volume-rate-', dir=out.parent) as temporary:
        scratch = Path(temporary)
        workspace = scratch / 'candidate'
        known = stage_candidate(snapshot, source_files, workspace)
        target = scratch / 'target'
        original_path = workspace / patch['path']
        original = original_path.read_text()
        if original.count(patch['original']) != 1:
            raise ValueError('体積速度の換算式が1箇所に定まりません')
        control_binary = build_and_render(workspace, target, configurations, paths['control'], execute)
        changed = original.replace(patch['original'], patch['replacement'], 1)
        original_path.write_text(changed)
        patch_file = out / 'volume-rate.patch'
        patch_file.write_text(''.join(unified_diff(original.splitlines(keepends=True), changed.splitlines(keepends=True),
                                                  'a/' + patch['path'], 'b/' + patch['path'])))
        changed_paths = [path.as_posix() for path, digest in known.items() if sha256(workspace / path) != digest]
        experimental_binary = build_and_render(workspace, target, configurations, paths['multiply'], execute)
    return paths, {'changed_paths': changed_paths, 'patch_sha256': sha256(patch_file),
                   'control_binary_sha256': control_binary, 'multiply_binary_sha256': experimental_binary}


def pressure_at_first_difference(variant, upstream, offset, rate):
    if offset is None:
        return None
    post_variant, post_upstream = variant[offset], upstream[offset]
    swaps, _ = substitutions(post_variant, post_upstream, rate)
    return {'offset': offset, 'multiply': post_variant, 'upstream': post_upstream, 'substitutions': swaps}


def bitwise_derivative(trace, first, rate, *, multiply):
    flow = trace[RADIATION]
    difference = flow[first:] - flow[first - 1:-1]
    recovered = rate * difference if multiply else difference / (1 / rate)
    return np.array_equal(recovered.view(np.uint64), trace[DERIVATIVE][first:].view(np.uint64))


def differences(left, right, fields, *, left_label, right_label):
    return {field: {'offset': item['offset'], left_label: item['candidate'], right_label: item['upstream']}
            for field, item in first_differences(left, right, fields).items()}


def first_residual_beak_branch(remaining, variant, upstream, first, cells, length, rate):
    branches = [(remaining[field]['offset'], cell)
                for cell in range(1, cells) if (field := f'beak_{cell}_inflow_cm3_s') in remaining]
    if not branches:
        return None, True
    offset, cell = min(branches)
    traces = {'candidate': variant, 'upstream': upstream}
    areas, rows = compare_steps(traces, first, len(variant), cell, length, rate)
    verified = all(row['replayed'][side]['inflow'].hex() == row['observed'][side].hex()
                   for row in rows for side in traces)
    return {'entering_cell': cell, 'observed_first_offset': offset, **diagnose_difference(rows, areas, length, rate)}, verified


def derivative_with_upstream_scale(variant, upstream, first, rate):
    flow = variant[RADIATION]
    recovered = (flow[first:] - flow[first - 1:-1]) * rate
    reference = upstream[DERIVATIVE][first:]
    differences = np.flatnonzero(recovered.view(np.uint64) != reference.view(np.uint64))
    return {'first_difference_offset': int(differences[0]) if differences.size else None,
            'bitwise_matches': len(recovered) - int(differences.size)}


def measure(case, sources, copies, snapshot, out, execute):
    configurations = {name: sources[f'artifacts/{name}.json'] for name in CONDITIONS}
    base = read(sources['summary.json'])
    rate, cutoff = case['sample_rate_hz'], case['volume_source_cutoff_hz']
    count_in_window = case['observation_internal_samples']
    cells = case['beak_cells']
    cell_length = case['beak_length_cm'] / cells
    fields = FIELDS + beak_fields(cells) + OEC
    observed = (PRESSURE, OEC[1], OEC[2],
                *(name for name in beak_fields(cells) if not name.endswith('_area_cm2')), RADIATION, DERIVATIVE)
    if 1 / (1 / rate) != rate:
        raise ValueError('実験式が登録された内部レートの乗算になりません')
    paths, build = render_pair(case, configurations, snapshot, copies, out, execute)
    checks = {'only_registered_source_file_changed': build['changed_paths'] == [case['variant']['path']],
              'experimental_binary_differs': build['control_binary_sha256'] != build['multiply_binary_sha256'],
              'source_conditions_registered': all(base['checks'].values()) and base['sample_rate_hz'] == rate}
    results, replays = {}, {}
    for name, config in configurations.items():
        definition = read(config)['songbird_airway']
        first, = (event['sample'] for event in definition['events'])
        count = first + count_in_window
        if (definition['sample_rate_hz'], definition['sample_count'], definition['observe_oec'], definition['observe_beak'],
                definition['control_block_samples']) != (rate, count, True, True, first):
            raise ValueError('前回の鳴禽ケースと登録条件が一致しません')
        original = sources[f'artifacts/{name}-candidate.csv']
        control_path, variant_path = (paths[kind][name] for kind in ('control', 'multiply'))
        control = load_trace(control_path, fields + CANDIDATE_OEC, count)
        variant = load_trace(variant_path, fields + CANDIDATE_OEC, count)
        upstream = load_trace(sources[f'artifacts/{name}-upstream.csv'], fields, count)
        checks[f'{name}/control_recreates_saved_csv'] = sha256(control_path) == sha256(original)
        checks[f'{name}/geometry_preserved'] = all(
            np.array_equal(variant[field], control[field]) and np.array_equal(variant[field], upstream[field])
            for field in (*[f'beak_{index}_area_cm2' for index in range(cells)], 'oec_area_cm2', OEC[0]))
        checks[f'{name}/usual_derivative_formula_replayed'] = (
            bitwise_derivative(control, first, rate, multiply=False)
            and bitwise_derivative(variant, first, rate, multiply=False)
            and bitwise_derivative(upstream, first, rate, multiply=True))
        recalc = observe(variant, first, rate, cutoff, 'candidate', multiply_volume=True)
        checks[f'{name}/variant_injection_and_pressure_replayed'] = all(
            row['pressure'].hex() == row['observed_pressure'].hex()
            and row['injection'].hex() == float(value).hex()
            for row, value in zip(recalc, variant[INJECTION][first:], strict=True))
        recalculated_upstream = observe(upstream, first, rate, cutoff, 'upstream')
        control_vs_upper = differences(control[first:], upstream[first:], observed,
                                       left_label='control', right_label='upstream')
        variant_vs_upper = differences(variant[first:], upstream[first:], observed,
                                       left_label='multiply', right_label='upstream')
        variant_vs_control = differences(variant[first:], control[first:], (*observed, INJECTION),
                                         left_label='multiply', right_label='control')
        offset = variant_vs_upper.get(PRESSURE, {}).get('offset')
        results[name] = {'event_sample': first, 'control_minus_upstream': control_vs_upper,
                         'multiply_minus_control': variant_vs_control, 'multiply_minus_upstream': variant_vs_upper,
                         'derivative_replayed_with_upstream_scale': derivative_with_upstream_scale(variant, upstream, first, rate),
                         'first_residual_pressure_replay': pressure_at_first_difference(recalc, recalculated_upstream, offset, rate),
                         'multiply_and_control_csv_equal': sha256(variant_path) == sha256(control_path)}
        if name == 'matched_time':
            branch, passed = first_residual_beak_branch(variant_vs_upper, variant, upstream, first, cells, cell_length, rate)
            results[name]['first_residual_interior_beak_branch'] = branch
            checks['matched_time/residual_interior_beak_branch_replayed'] = passed
        replays[name] = {'multiply': recalc, 'upstream': recalculated_upstream}
    matched = results['matched_time']
    first_pressure = case['local_pressure_difference_offset']
    first_flow = case['baseline_radiated_flow_difference_offset']
    checks['reference_pressure_and_flow_differences_reproduced'] = all(
        matched['control_minus_upstream'].get(field, {}).get('offset') == expected
        for field, expected in ((PRESSURE, first_pressure), (RADIATION, first_flow)))
    remaining = matched['multiply_minus_upstream']
    pressure_offset, radiation_offset = (remaining.get(field, {}).get('offset') for field in (PRESSURE, RADIATION))
    hypotheses = {'local_pressure_difference_removed': pressure_offset is None or pressure_offset > first_pressure,
                  'first_radiated_flow_difference_delayed': radiation_offset is None or radiation_offset > first_flow,
                  'native_block_output_unchanged': results['native_block']['multiply_and_control_csv_equal'],
                  'no_tracking_output_unchanged': results['no_tracking']['multiply_and_control_csv_equal']}
    write(out / 'pressure-replay.json', replays)
    return {'checks': checks, 'hypotheses': hypotheses, 'sample_rate_hz': rate, 'build': build,
            'conditions': results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    case = read(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    names = ['summary.json', *(f'artifacts/{name}.json' for name in CONDITIONS),
             *(f'artifacts/{name}-{side}.csv' for name in CONDITIONS for side in ('candidate', 'upstream'))]
    manifest, source_runs = registered_artifacts(case['baseline'], 'songbird-chirps-oec-pressure-44100', revision, names)
    copies = [*candidate_sources(), WORKSPACE / 'data/cmudict.txt.gz', WORKSPACE / 'data/mandarin.txt.gz']
    inputs = [CASE, Path(__file__), manifest, *source_runs.values(), *copies, UPPER_NETWORK, UPPER_SONGBIRD,
              *(WORKSPACE / 'tools' / file for file in ('measure_songbird_airway.py', 'measure_songbird_syrinx.py',
                  'measure_songbird_chirps_beak_load.py', 'measure_songbird_chirps_beak_tip_inflow.py',
                  'measure_songbird_chirps_beak_tip_inflow_44100.py', 'measure_songbird_chirps_oec_pressure_44100.py',
                  'measure_speech_timing.py', 'measure_uniform_tube.py')), UPSTREAM / 'crates/chimera/src/physics.rs']
    details = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision,
               'analysis_command': [sys.executable, *sys.argv], 'analysis_directory': str(Path.cwd())}
    snapshot = WORKSPACE / 'runs' / args.run_id / 'artifacts/source'
    return record_measurement(args.run_id, CASE, inputs, details,
                              lambda out, execute: measure(case, source_runs, copies, snapshot, out, execute),
                              command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
