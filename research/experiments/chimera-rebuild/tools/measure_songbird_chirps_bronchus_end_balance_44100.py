"""左右の気管支末端の圧力収支と直列枝流量を固定上流に照合する。"""

import argparse
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

from measure_songbird_airway import C, PROBE, RHO, SIDES
from measure_songbird_chirps_beak_load import ROOT
from measure_songbird_chirps_beak_tip_inflow import INPUTS, UPPER_NETWORK, UPPER_SONGBIRD, diagnose_difference, step
from measure_songbird_chirps_beak_tip_inflow_44100 import registered_artifacts
from measure_songbird_chirps_left_syrinx_half_inertance_44100 import configure
from measure_songbird_chirps_left_syrinx_port_44100 import BASE_ID, stored_trace
from measure_songbird_chirps_oec_pressure_44100 import CONDITIONS
from measure_songbird_chirps_right_syrinx_half_inertance_44100 import (
    MOMENTUM_LABELS, MOMENTUM_PATCH, restore_patches,
)
from measure_songbird_chirps_terminal_numerator_44100 import first_offset, same_bits
from measure_songbird_chirps_trachea_interior_momentum_44100 import capture_prefix_matches
from measure_songbird_chirps_volume_rate_propagation_44100 import build_and_render, stage_candidate
from measure_speech_timing import read, write
from measure_uniform_tube import build_upstream_probe, candidate_sources, record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/songbird-chirps-bronchus-end-balance-44100.json'
MOMENTUM_CASE = WORKSPACE / 'cases/songbird-chirps-right-syrinx-momentum-44100.json'
HALF_CASE = WORKSPACE / 'cases/songbird-chirps-left-syrinx-half-inertance-44100.json'
OBSERVATIONS = ('upstream_pressure_dyn_cm2', 'inflow_cm3_s', 'area_cm2', 'length_cm')
INTERIOR_OBSERVATIONS = ('pressure_dyn_cm2', 'outflow_cm3_s', *OBSERVATIONS)


def pressure_balance(inputs, gain):
    return inputs['previous_pressure'] + gain * (inputs['inflow'] - inputs['outflow'])


def balance_columns(side, interior_cell):
    if interior_cell is None:
        return (f'{side}_bronchus_pressure_dyn_cm2', f'{side}_flow_cm3_s',
                *(f'{side}_bronchus_end_{key}' for key in OBSERVATIONS))
    return tuple(f'{side}_bronchus_{interior_cell}_{key}' for key in INTERIOR_OBSERVATIONS)


def replay_end(trace, start, side, arithmetic, geometry, rate, *, linear_inertance=None, momentum_inertance=None,
               interior_cell=None):
    area = geometry['area_cm2']
    length = geometry['length_cm'] / geometry['cells']
    gain = (1 / rate) / (area * length / (RHO * C * C))
    pressure, outflow, preceding, inflow, _, _ = balance_columns(side, interior_cell)
    rows = []
    for previous, current in zip(trace[start - 1:-1], trace[start:], strict=True):
        balance = {'previous_pressure': float(previous[pressure]), 'inflow': float(current[inflow]),
                   'outflow': float(current[outflow])}
        inputs = dict(zip(INPUTS, (float(previous[preceding]), balance['previous_pressure'], float(previous[inflow]),
                                   arithmetic), strict=True))
        rows.append({'pressure_inputs': balance, 'pressure': pressure_balance(balance, gain),
                     'observed_pressure': float(current[pressure]), 'branch_inputs': inputs,
                     'branch': step(inputs, (area, area), length, rate, linear_inertance=linear_inertance,
                                    momentum_inertance=momentum_inertance)})
    return rows, gain


def locate_pressure_residual(rows, offset, gain):
    if offset is None:
        return None
    candidate, upstream = (rows[key][offset] for key in ('candidate', 'upstream'))
    actual, reference = (row['pressure_inputs'] for row in (candidate, upstream))
    swaps = {}
    for field in actual:
        pressure = pressure_balance(actual | {field: reference[field]}, gain)
        swaps[field] = {'pressure': pressure, 'matches_upstream': pressure.hex() == upstream['observed_pressure'].hex()}
    return {'offset': offset, 'candidate': candidate, 'upstream': upstream, 'single_substitutions': swaps}


def compare_end(traces, start, side, condition, case, checks, *, candidate_linear_inertance=None,
                candidate_momentum_inertance=None, verify_registered_pressure=True, interior_cell=None):
    geometry, rate = case['geometry'], case['sample_rate_hz']
    suffix = f'{condition}/{side}'
    rows = {}
    area, length = geometry['area_cm2'], geometry['length_cm'] / geometry['cells']
    fields = balance_columns(side, interior_cell)
    area_field, length_field = fields[-2:]
    for arithmetic, trace in traces.items():
        candidate = arithmetic == 'candidate'
        rows[arithmetic], gain = replay_end(
            trace, start, side, arithmetic, geometry, rate,
            linear_inertance=candidate_linear_inertance if candidate else None,
            momentum_inertance=candidate_momentum_inertance if candidate else None, interior_cell=interior_cell)
        name = f'{suffix}/{arithmetic}'
        checks[f'{name}/geometry_matches'] = bool((trace[area_field] == area).all() and (trace[length_field] == length).all())
        checks[f'{name}/pressure_bit_replayed'] = all(
            row['pressure'].hex() == row['observed_pressure'].hex() for row in rows[arithmetic])
        checks[f'{name}/inlet_flow_bit_replayed'] = all(
            row['branch']['inflow'].hex() == row['pressure_inputs']['inflow'].hex() for row in rows[arithmetic])
    fields = fields[:4]
    if condition == 'no_tracking':
        checks[f'{suffix}/unexcited'] = all((trace[key] == 0).all() for trace in traces.values() for key in fields)
    candidate, upper = traces.values()
    offsets = {key: first_offset(candidate[key][start:], upper[key][start:]) for key in fields}
    pressure = locate_pressure_residual(rows, offsets[fields[0]], gain)
    if side == 'right' and verify_registered_pressure:
        expected = case['expected_right_pressure_offsets'][condition]
        checks[f'{suffix}/registered_pressure_offset'] = offsets[fields[0]] == expected
        if expected is not None:
            c, u = (pressure[key]['pressure_inputs'] if pressure else {} for key in ('candidate', 'upstream'))
            checks[f'{suffix}/registered_pressure_and_port_inputs_identical'] = bool(c and u) and all(
                c[field].hex() == u[field].hex() for field in ('previous_pressure', 'outflow'))
            checks[f'{suffix}/inflow_only_reproduces_pressure_difference'] = (
                pressure is not None and pressure['single_substitutions']['inflow']['matches_upstream'])
    branch_samples = []
    for offset, (left, right) in enumerate(zip(rows['candidate'], rows['upstream'], strict=True)):
        versions = {'candidate': left, 'upstream': right}
        branch_samples.append({'offset': offset, 'inputs': {key: row['branch_inputs'] for key, row in versions.items()},
                               'replayed': {key: row['branch'] for key, row in versions.items()},
                               'observed': {key: row['pressure_inputs']['inflow'] for key, row in versions.items()}})
    branch = diagnose_difference(branch_samples, (area, area), length, rate,
                                 candidate_linear_inertance=candidate_linear_inertance,
                                 candidate_momentum_inertance=candidate_momentum_inertance)
    return {'first_differences': offsets, 'pressure_gain': gain, 'first_pressure_residual': pressure,
            'first_branch_residual': branch}, rows


def capture_bronchus_traces(configurations, patches, snapshot, copies, out, execute):
    candidate_paths = {name: out / f'{name}-candidate.csv' for name in configurations}
    with TemporaryDirectory(prefix='bronchus-balance-', dir=out.parent) as temporary:
        scratch = Path(temporary)
        workspace = scratch / 'candidate'
        stage_candidate(snapshot, copies, workspace)
        for patch in patches:
            execute(['git', 'apply', '--check', str(patch)], cwd=workspace)
            execute(['git', 'apply', str(patch)], cwd=workspace)
        binary = build_and_render(workspace, scratch / 'target', configurations, candidate_paths, execute)
    probe = build_upstream_probe(PROBE, out, execute, extra_libraries=('serde_json',), cargo_args=('--offline',))
    upper_paths = {name: out / f'{name}-upstream.csv' for name in configurations}
    for name, path in configurations.items():
        execute([str(probe), str(path)], cwd=UPSTREAM, stdout=upper_paths[name])
    return candidate_paths, upper_paths, binary


def measure(case, saved, upper, patches, snapshot, copies, out, execute):
    configurations = configure(case, saved, out)
    for path in configurations.values():
        contents = read(path)
        contents['songbird_airway']['observe_bronchus_end_balance'] = True
        write(path, contents)
    plain = 'matched_time_without_bronchus_observation'
    candidate_paths, upper_paths, binary = capture_bronchus_traces(
        {plain: saved['artifacts/matched_time.json']} | configurations, patches, snapshot, copies, out, execute)
    legacy = MOMENTUM_LABELS[1]
    checks = {
        'candidate_without_observation_reproduced': sha256(candidate_paths[plain]) == sha256(
            saved[f'artifacts/matched_time-{legacy}.csv']),
        'upstream_without_observation_reproduced': (
            sha256(upper_paths[plain]) == sha256(upper['artifacts/matched_time-upstream.csv'])),
    }
    results, series = {}, {}
    extra = len(SIDES) * len(OBSERVATIONS)
    for name in configurations:
        start = case['condition_control_samples'][name]
        count = start + case['observation_internal_samples']
        upper_path = upper_paths[name]
        checks[f'{name}/candidate_existing_columns_reproduced'] = capture_prefix_matches(
            candidate_paths[name], saved[f'artifacts/{name}-{legacy}.csv'], count + 1, extra)
        checks[f'{name}/upstream_existing_columns_reproduced'] = capture_prefix_matches(
            upper_path, upper[f'artifacts/{name}-upstream.csv'], count + 1, extra)
        traces = {'candidate': stored_trace(candidate_paths[name], count), 'upstream': stored_trace(upper_path, count)}
        suffix = tuple(f'{side}_bronchus_end_{field}' for side in SIDES for field in OBSERVATIONS)
        if any(trace.dtype.names[-extra:] != suffix for trace in traces.values()):
            raise ValueError(f'気管支末端の観測列が一致しません ({name})')
        results[name], series[name] = {}, {}
        for side in SIDES:
            results[name][side], series[name][side] = compare_end(traces, start, side, name, case, checks)
        checks[f'{name}/bronchus_geometry_matches_upstream'] = all(
            same_bits(traces['candidate'][field], traces['upstream'][field])
            for field in suffix if field.endswith(('_area_cm2', '_length_cm')))
    write(out / 'bronchus-end-balance-replay.json', series)
    return {'checks': checks, 'conditions': results, 'sample_rate_hz': case['sample_rate_hz'],
            'window': case['observation_internal_samples'], 'candidate_binary_sha256': binary,
            'applied_patch_sha256': [sha256(path) for path in patches]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    case, prior, half = (read(path) for path in (CASE, MOMENTUM_CASE, HALF_CASE))
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    if any(case[key] != prior[key] for key in ('upstream_revision', 'sample_rate_hz', 'output_rate_hz',
                                              'condition_control_samples', 'observation_internal_samples')):
        parser.error('先行実験と条件が異なります')
    names = ('summary.json', f'artifacts/{MOMENTUM_PATCH}.patch', *(f'artifacts/{name}{suffix}'
              for name in CONDITIONS for suffix in ('.json', f'-{MOMENTUM_LABELS[1]}.csv')))
    manifest_path, saved = registered_artifacts(case['baseline'], prior['id'], revision, names)
    manifest = read(manifest_path)
    indexed = {row['path']: row['sha256'] for row in manifest['inputs']}
    for path in (MOMENTUM_CASE, HALF_CASE):
        if indexed.get(path.relative_to(ROOT).as_posix()) != sha256(path):
            parser.error(f'先行実験で使用したケース定義が必要です ({path.name})')
    upstream_manifest, upper = registered_artifacts(
        half['baseline'], BASE_ID, revision, tuple(f'artifacts/{name}-upstream.csv' for name in CONDITIONS))
    patches = restore_patches(manifest, saved, MOMENTUM_PATCH)
    copies = [*candidate_sources(), WORKSPACE / 'data/cmudict.txt.gz', WORKSPACE / 'data/mandarin.txt.gz']
    auxiliary = [WORKSPACE / 'tools' / name for name in (
        'measure_songbird_chirps_trachea_interior_momentum_44100.py', 'measure_songbird_chirps_volume_rate_propagation_44100.py',
        'measure_songbird_chirps_right_syrinx_half_inertance_44100.py', 'measure_songbird_chirps_left_syrinx_half_inertance_44100.py',
        'measure_songbird_chirps_left_syrinx_port_44100.py', 'measure_songbird_chirps_left_syrinx_momentum_44100.py',
        'measure_songbird_chirps_beak_tip_inflow.py', 'measure_songbird_chirps_beak_tip_inflow_44100.py',
        'measure_songbird_chirps_terminal_numerator_44100.py', 'measure_songbird_airway.py', 'measure_songbird_syrinx.py',
        'measure_speech_timing.py', 'measure_uniform_tube.py', 'upstream_baseline.py')]
    inputs = [CASE, MOMENTUM_CASE, HALF_CASE, Path(__file__), PROBE, manifest_path, *saved.values(), upstream_manifest,
              *upper.values(), *patches, *copies, *auxiliary, UPPER_NETWORK, UPPER_SONGBIRD,
              UPSTREAM / 'crates/chimera/src/creatures/build.rs',
              UPSTREAM / 'crates/chimera/tests/airway_adversarial.rs',
              UPSTREAM / 'crates/chimera/tests/creature_realtime.rs']
    details = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision,
               'analysis_command': [sys.executable, *sys.argv], 'analysis_directory': str(Path.cwd())}
    snapshot = WORKSPACE / 'runs' / args.run_id / 'artifacts/source'
    return record_measurement(args.run_id, CASE, inputs, details,
                              lambda out, execute: measure(case, saved, upper, patches, snapshot, copies, out, execute),
                              command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
