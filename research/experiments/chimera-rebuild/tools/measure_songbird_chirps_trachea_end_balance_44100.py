"""鳴禽の気管末端で、直列枝と壁の流量から節点圧を照合する。"""

import argparse
from itertools import combinations
import math
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

from measure_songbird_airway import FIELDS, PROBE
from measure_songbird_chirps_beak_load import DENSITY, ROOT, SPEED, beak_fields
from measure_songbird_chirps_beak_tip_inflow import INPUTS, UPPER_NETWORK, UPPER_SONGBIRD, diagnose_difference, step
from measure_songbird_chirps_beak_tip_inflow_44100 import registered_artifacts
from measure_songbird_chirps_oec_neck_44100 import (
    FLOW, NECK_FIELDS, PREFIX_PATCHES, TRACHEA_AREA, TRACHEA_LENGTH, TRACHEA_PRESSURE, prefix_columns_match,
)
from measure_songbird_chirps_oec_pressure_44100 import CANDIDATE_OEC, CONDITIONS, OEC
from measure_songbird_chirps_terminal_numerator_44100 import first_offset
from measure_songbird_chirps_volume_rate_propagation_44100 import build_and_render, stage_candidate
from measure_songbird_syrinx import load_trace
from measure_speech_timing import read, write
from measure_uniform_tube import build_upstream_probe, candidate_sources, record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/songbird-chirps-trachea-end-balance-44100.json'
BASE_ID = 'songbird-chirps-oec-neck-linear-44100'
PENULTIMATE, INFLOW, WALL_FLOW, WALL_DISPLACEMENT, NOISE = BALANCE_FIELDS = (
    'trachea_penultimate_pressure_dyn_cm2', 'trachea_end_inflow_cm3_s',
    'trachea_end_wall_flow_cm3_s', 'trachea_end_wall_displacement_cm', 'trachea_end_inlet_noise_pressure_dyn_cm2',
)


def pressure_update(inputs, dt, compliance):
    balance = (inputs['inflow'] - inputs['neck_outflow']) - inputs['wall_outflow']
    return inputs['previous_pressure'] + (dt / compliance) * balance


def replay(trace, start, rate, wall, side, *, multiply_inlet_momentum=False, upstream_wall_surface=False):
    dt = 1 / rate
    upper = side == 'upstream'
    area, length = (float(trace[key][0]) for key in (TRACHEA_AREA, TRACHEA_LENGTH))
    compliance = area * length / (DENSITY * SPEED * SPEED)
    mass, resistance, stiffness = (wall[key] for key in ('mass_g_cm2', 'resistance_dyn_s_cm3', 'stiffness_dyn_cm3'))
    scaled_mass = mass * rate if upper else mass / dt
    surface = (2 * math.sqrt(math.pi) * math.sqrt(area) * length if upper or upstream_wall_surface
               else 2 * math.sqrt(math.pi * area) * length)
    velocity = displacement = 0.0
    rows = []
    for offset, (previous, current) in enumerate(zip(trace[start - 1:-1], trace[start:], strict=True)):
        inputs = {name: float(row[key]) for name, row, key in (
            ('previous_pressure', previous, TRACHEA_PRESSURE),
            ('inflow', current, INFLOW), ('neck_outflow', current, FLOW), ('wall_outflow', current, WALL_FLOW))}
        previous_wall = {'velocity_cm_s': velocity, 'displacement_cm': displacement}
        velocity = ((scaled_mass - 0.5 * resistance) * velocity + inputs['previous_pressure'] -
                    stiffness * displacement) / (scaled_mass + 0.5 * resistance)
        displacement += dt * velocity
        branch_inputs = dict(zip(INPUTS, (*(float(previous[key]) for key in (PENULTIMATE, TRACHEA_PRESSURE, INFLOW)), side),
                                 strict=True))
        rows.append({'offset': offset, 'pressure_inputs': inputs, 'pressure': pressure_update(inputs, dt, compliance),
                     'previous_wall_state': previous_wall, 'wall_flow': surface * velocity, 'wall_displacement': displacement,
                     'observed_pressure': float(current[TRACHEA_PRESSURE]), 'observed_wall_flow': float(current[WALL_FLOW]),
                     'observed_wall_displacement': float(current[WALL_DISPLACEMENT]), 'inlet_inputs': branch_inputs,
                     'inlet_replay': step(branch_inputs, (area, area), length, rate,
                                          multiply_momentum=multiply_inlet_momentum)})
    return rows, {'area': area, 'length': length, 'compliance': compliance, 'surface': surface, 'scaled_mass': scaled_mass}


def pressure_substitutions(rows, offset, rate, compliance):
    if offset is None:
        return None
    candidate, upper = (rows[side][offset] for side in ('candidate', 'upstream'))
    baseline, upstream = (row['pressure_inputs'] for row in (candidate, upper))
    changed = [key for key in baseline if baseline[key].hex() != upstream[key].hex()]
    substitutions = []
    for size in range(1, len(changed) + 1):
        for keys in combinations(changed, size):
            predicted = pressure_update(baseline | {key: upstream[key] for key in keys}, 1 / rate, compliance)
            substitutions.append({'swapped_inputs': keys, 'pressure': predicted,
                                  'matches_upstream': predicted.hex() == upper['observed_pressure'].hex()})
    return {'offset': offset, 'candidate_inputs': baseline, 'upstream_inputs': upstream, 'substitutions': substitutions}


def inlet_diagnosis(rows, offset, rate, parameters, *, multiply_momentum=False):
    if offset is None:
        return None
    sides = ('candidate', 'upstream')
    row = {'offset': offset, 'inputs': {side: rows[side][offset]['inlet_inputs'] for side in sides},
           'replayed': {side: rows[side][offset]['inlet_replay'] for side in sides},
           'observed': {side: rows[side][offset]['pressure_inputs']['inflow'] for side in sides}}
    return diagnose_difference([row], (parameters['area'], parameters['area']), parameters['length'], rate,
                               multiply_momentum=multiply_momentum)


def measure(case, saved, sources, patches, snapshot, copies, out, execute):
    rate, window, cells = (case[key] for key in ('sample_rate_hz', 'observation_internal_samples', 'beak_cells'))
    fields = FIELDS + beak_fields(cells) + OEC
    configurations, candidate_paths = {}, {}
    for name in CONDITIONS:
        definition = read(sources[f'{name}.json'])
        settings = definition['songbird_airway']
        event, = settings['events']
        start = case['condition_control_samples'][name]
        if (settings['sample_rate_hz'], settings['control_block_samples'], event['sample'], settings['breath_gate'],
                event['breath_gate'], settings['observe_beak'], settings['observe_oec'], settings['observe_oec_neck']) != (
                rate, start, start, 0, 0, True, True, True) or not start + window <= settings['sample_count']:
            raise ValueError(f'固定上流の観測条件と一致しません ({name})')
        settings['sample_count'] = start + window
        settings['observe_trachea_end_balance'] = True
        configurations[name] = out / f'{name}.json'
        candidate_paths[name] = out / f'{name}-candidate.csv'
        write(configurations[name], definition)
    with TemporaryDirectory(prefix='trachea-end-', dir=out.parent) as temporary:
        scratch = Path(temporary)
        workspace = scratch / 'candidate'
        stage_candidate(snapshot, copies, workspace)
        for patch in patches:
            execute(['git', 'apply', '--check', str(patch)], cwd=workspace)
            execute(['git', 'apply', str(patch)], cwd=workspace)
        binary = build_and_render(workspace, scratch / 'target', configurations, candidate_paths, execute)
    probe = build_upstream_probe(PROBE, out, execute, extra_libraries=('serde_json',), cargo_args=('--offline',))
    prior_build = read(saved['summary.json'])['build']
    checks = {'prior_patch_chain_matches': [sha256(path) for path in patches] ==
              [*prior_build['preceding_patch_sha256'], prior_build['inlet_patch_sha256']]}
    results, all_replays = {}, {}
    observed = (TRACHEA_PRESSURE, PENULTIMATE, INFLOW, FLOW, WALL_FLOW, WALL_DISPLACEMENT)
    for name, config in configurations.items():
        start = case['condition_control_samples'][name]
        upstream_path = out / f'{name}-upstream.csv'
        execute([str(probe), str(config)], cwd=UPSTREAM, stdout=upstream_path)
        traces, series, parameters = {}, {}, {}
        for side, path, archived in (
            ('candidate', candidate_paths[name], saved[f'artifacts/{name}-neck-linear.csv']),
            ('upstream', upstream_path, sources[f'{name}-upstream.csv']),
        ):
            columns = fields + (CANDIDATE_OEC if side == 'candidate' else ()) + NECK_FIELDS + BALANCE_FIELDS
            trace = traces[side] = load_trace(path, columns, start + window)
            checks[f'{name}/{side}/previous_columns_reproduced'] = prefix_columns_match(path, archived)
            checks[f'{name}/{side}/fixed_tracheal_section_and_zero_noise'] = (
                all((trace[key] == trace[key][0]).all() for key in (TRACHEA_AREA, TRACHEA_LENGTH))
                and bool((trace[NOISE] == 0).all()))
            checks[f'{name}/{side}/starts_from_rest'] = all((trace[key][:start] == 0).all() for key in observed)
            series[side], parameters[side] = replay(trace, start, rate, case['trachea_wall'], side)
            for field in ('pressure', 'wall_flow', 'wall_displacement'):
                checks[f'{name}/{side}/{field}_bit_replayed'] = all(
                    row[field].hex() == row[f'observed_{field}'].hex() for row in series[side])
            checks[f'{name}/{side}/inlet_flow_bit_replayed'] = all(
                row['inlet_replay']['inflow'].hex() == row['pressure_inputs']['inflow'].hex() for row in series[side])
        candidate, upper = (traces[side][start:] for side in ('candidate', 'upstream'))
        offsets = {key: first_offset(candidate[key], upper[key]) for key in observed}
        checks[f'{name}/first_pressure_difference_reproduced'] = offsets[TRACHEA_PRESSURE] == (
            case['expected_first_end_pressure_offsets'][name])
        if name == 'no_tracking':
            checks[f'{name}/acoustics_all_zero'] = all((trace[key] == 0).all() for trace in traces.values() for key in observed)
        results[name] = {'first_differences': offsets, 'parameters': parameters,
                         'first_pressure_residual': pressure_substitutions(
                             series, offsets[TRACHEA_PRESSURE], rate, parameters['candidate']['compliance']),
                         'first_inlet_flow_residual': inlet_diagnosis(
                             series, offsets[INFLOW], rate, parameters['candidate'])}
        all_replays[name] = series
    matched = results['matched_time']
    wall_offset = matched['first_differences'][WALL_FLOW]
    hypotheses = {'wall_flow_precedes_first_pressure_difference': wall_offset is not None and
                  wall_offset < matched['first_differences'][TRACHEA_PRESSURE],
                  'wall_flow_alone_explains_first_pressure_difference': any(
                      item['swapped_inputs'] == ('wall_outflow',) and item['matches_upstream']
                      for item in matched['first_pressure_residual']['substitutions'])}
    write(out / 'trachea-end-replay.json', all_replays)
    return {'checks': checks, 'hypotheses': hypotheses, 'sample_rate_hz': rate, 'window': window,
            'candidate_binary_sha256': binary, 'conditions': results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    case = read(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    names = ('summary.json', 'artifacts/oec-neck-linear.patch', *(f'artifacts/{name}-neck-linear.csv' for name in CONDITIONS))
    manifest, saved = registered_artifacts(case['baseline'], BASE_ID, revision, names)
    entries = read(manifest)['inputs']
    patches = (*PREFIX_PATCHES, 'oec-sum-order.patch', 'terminal-numerator.patch', 'oec-neck-momentum.patch')
    filenames = (*patches, *(f'{name}{suffix}' for name in CONDITIONS for suffix in ('.json', '-upstream.csv')))
    sources = {}
    for filename in filenames:
        row, = (row for row in entries if row['path'].endswith(f'/artifacts/{filename}'))
        path = ROOT / row['path']
        if path.stat().st_size != row['bytes'] or sha256(path) != row['sha256']:
            parser.error(f'対象の先行入力が保存時と一致しません ({filename})')
        sources[filename] = path
    chain = [*(sources[name] for name in patches), saved['artifacts/oec-neck-linear.patch']]
    copies = [*candidate_sources(), WORKSPACE / 'data/cmudict.txt.gz', WORKSPACE / 'data/mandarin.txt.gz']
    tools = [WORKSPACE / 'tools' / name for name in (
        'measure_songbird_airway.py', 'measure_songbird_chirps_beak_load.py', 'measure_songbird_chirps_beak_tip_inflow.py',
        'measure_songbird_chirps_beak_tip_inflow_44100.py', 'measure_songbird_chirps_oec_neck_44100.py',
        'measure_songbird_chirps_oec_pressure_44100.py', 'measure_songbird_chirps_terminal_numerator_44100.py',
        'measure_songbird_chirps_volume_rate_propagation_44100.py', 'measure_songbird_syrinx.py',
        'measure_speech_timing.py', 'measure_uniform_tube.py')]
    inputs = [CASE, Path(__file__), PROBE, manifest, *saved.values(), *sources.values(), *copies, *tools,
              UPPER_NETWORK, UPPER_SONGBIRD, UPSTREAM / 'crates/chimera/src/physics.rs',
              UPSTREAM / 'crates/chimera/tests/airway.rs']
    details = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision,
               'analysis_command': [sys.executable, *sys.argv], 'analysis_directory': str(Path.cwd())}
    snapshot = WORKSPACE / 'runs' / args.run_id / 'artifacts/source'
    return record_measurement(args.run_id, CASE, inputs, details,
                              lambda out, execute: measure(case, saved, sources, chain, snapshot, copies, out, execute),
                              command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
