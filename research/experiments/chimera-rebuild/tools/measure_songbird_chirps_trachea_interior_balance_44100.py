"""気管の内部セルで、両側の直列枝と壁の流量から圧力を照合する。"""

import argparse
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

from numpy.lib.recfunctions import rename_fields, repack_fields

from measure_songbird_airway import FIELDS, PROBE
from measure_songbird_chirps_beak_load import ROOT, beak_fields
from measure_songbird_chirps_beak_tip_inflow import UPPER_NETWORK, UPPER_SONGBIRD
from measure_songbird_chirps_beak_tip_inflow_44100 import registered_artifacts
from measure_songbird_chirps_oec_neck_44100 import (
    FLOW, NECK_FIELDS, TRACHEA_AREA, TRACHEA_LENGTH, TRACHEA_PRESSURE, prefix_columns_match,
)
from measure_songbird_chirps_oec_pressure_44100 import CANDIDATE_OEC, CONDITIONS, OEC
from measure_songbird_chirps_terminal_numerator_44100 import first_offset, same_bits
from measure_songbird_chirps_trachea_end_balance_44100 import (
    BALANCE_FIELDS, INFLOW, NOISE, PENULTIMATE, WALL_DISPLACEMENT, WALL_FLOW, inlet_diagnosis, pressure_substitutions, replay,
)
from measure_songbird_chirps_volume_rate_propagation_44100 import build_and_render, stage_candidate
from measure_songbird_syrinx import load_trace
from measure_speech_timing import read, write
from measure_uniform_tube import build_upstream_probe, candidate_sources, record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/songbird-chirps-trachea-interior-balance-44100.json'
BASE_ID = 'songbird-chirps-trachea-end-momentum-44100'
TRACHEA_FIELDS = ('pressure_dyn_cm2', 'upstream_pressure_dyn_cm2', 'inflow_cm3_s', 'outflow_cm3_s', 'wall_flow_cm3_s',
                  'wall_displacement_cm', 'area_cm2', 'length_cm', 'inlet_noise_pressure_dyn_cm2')
REPLAY_FIELDS = (TRACHEA_PRESSURE, PENULTIMATE, INFLOW, FLOW, WALL_FLOW, WALL_DISPLACEMENT,
                 TRACHEA_AREA, TRACHEA_LENGTH, NOISE)


def interior_columns(index):
    return tuple(f'trachea_{index}_{key}' for key in TRACHEA_FIELDS)


def interior_replay_view(trace, columns):
    aliases = dict(zip(columns, REPLAY_FIELDS, strict=True))
    return rename_fields(repack_fields(trace[list(columns)]), aliases)


def compare_cell(case, number, prefix, traces, start, checks, *, upstream_wall_surface=False):
    rate = case['sample_rate_hz']
    multiply = number in case.get('multiply_inlet_momentum_cells', ())
    series, parameters = {}, {}
    for side, cell in traces.items():
        key = f'{prefix}/{side}'
        series[side], parameters[side] = replay(cell, start, rate, case['trachea_wall'], side,
                                               multiply_inlet_momentum=multiply,
                                               upstream_wall_surface=upstream_wall_surface)
        checks[f'{key}/fixed_tracheal_section_and_zero_noise'] = (
            all((cell[field] == cell[field][0]).all() for field in (TRACHEA_AREA, TRACHEA_LENGTH))
            and bool((cell[NOISE] == 0).all()))
        checks[f'{key}/starts_from_rest'] = all((cell[field][:start] == 0).all() for field in REPLAY_FIELDS[:6])
        for field in ('pressure', 'wall_flow', 'wall_displacement'):
            checks[f'{key}/{field}_bit_replayed'] = all(
                row[field].hex() == row[f'observed_{field}'].hex() for row in series[side])
        checks[f'{key}/inlet_flow_bit_replayed'] = all(
            row['inlet_replay']['inflow'].hex() == row['pressure_inputs']['inflow'].hex() for row in series[side])
    candidate, upper = (traces[side][start:] for side in ('candidate', 'upstream'))
    offsets = {suffix: first_offset(candidate[field], upper[field])
               for suffix, field in zip(TRACHEA_FIELDS, REPLAY_FIELDS, strict=True)}
    result = {'first_differences': offsets, 'parameters': parameters,
              'first_pressure_residual': pressure_substitutions(
                  series, offsets['pressure_dyn_cm2'], rate, parameters['candidate']['compliance']),
              'first_inlet_flow_residual': inlet_diagnosis(
                  series, offsets['inflow_cm3_s'], rate, parameters['candidate'], multiply_momentum=multiply)}
    return result, series


def measure(case, saved, patches, snapshot, copies, out, execute):
    rate, window, cells, index = (case[key] for key in ('sample_rate_hz', 'observation_internal_samples',
                                                       'beak_cells', 'trachea_cell_index'))
    fields = FIELDS + beak_fields(cells) + OEC
    selection = case.get('trachea_observation_cells', [index])
    if index not in selection:
        raise ValueError('判定対象の気管セルを観測指定に含めてください')
    interior = {number: interior_columns(number) for number in selection}
    requested_fields = tuple(key for group in interior.values() for key in group)
    candidate_label = case['baseline'].get('candidate_label', 'trachea-momentum')
    configurations, candidate_paths = {}, {}
    for name in CONDITIONS:
        definition = read(saved[f'artifacts/{name}.json'])
        settings = definition['songbird_airway']
        event, = settings['events']
        start = case['condition_control_samples'][name]
        if (settings['sample_rate_hz'], settings['control_block_samples'], event['sample'],
                settings['breath_gate'], event['breath_gate'], settings['observe_beak'], settings['observe_oec'],
                settings['observe_oec_neck'], settings['observe_trachea_end_balance']) != (
                rate, start, start, 0, 0, True, True, True, True) or start + window > settings['sample_count']:
            raise ValueError(f'前回の描画条件と一致しません ({name})')
        settings['sample_count'] = start + window
        settings['observe_trachea_interior_cells'] = selection
        configurations[name] = out / f'{name}.json'
        candidate_paths[name] = out / f'{name}-candidate.csv'
        write(configurations[name], definition)
    with TemporaryDirectory(prefix='trachea-interior-', dir=out.parent) as temporary:
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
    for name, config in configurations.items():
        start = case['condition_control_samples'][name]
        upstream = out / f'{name}-upstream.csv'
        execute([str(probe), str(config)], cwd=UPSTREAM, stdout=upstream)
        traces = {number: {} for number in selection}
        for side, path, archived in (
            ('candidate', candidate_paths[name], saved[f'artifacts/{name}-{candidate_label}.csv']),
            ('upstream', upstream, saved[f'artifacts/{name}-upstream.csv']),
        ):
            columns = fields + (CANDIDATE_OEC if side == 'candidate' else ()) + NECK_FIELDS + BALANCE_FIELDS + requested_fields
            trace = load_trace(path, columns, start + window)
            for number, names in interior.items():
                traces[number][side] = interior_replay_view(trace, names)
            checks[f'{name}/{side}/previous_columns_reproduced'] = prefix_columns_match(path, archived)
            penultimate = case.get('trachea_cells', 16) - 2
            if penultimate in traces:
                cell = traces[penultimate][side]
                checks[f'{name}/{side}/outflow_matches_trachea_end_inflow'] = same_bits(cell[FLOW], trace[INFLOW])
                checks[f'{name}/{side}/local_pressure_matches_prior_penultimate_column'] = same_bits(
                    cell[TRACHEA_PRESSURE], trace[PENULTIMATE])
            for number in selection:
                if number + 1 in traces:
                    here, following = (traces[site][side] for site in (number, number + 1))
                    checks[f'{name}/{side}/cell_{number}_matches_next_cell'] = (
                        same_bits(here[FLOW], following[INFLOW])
                        and same_bits(here[TRACHEA_PRESSURE], following[PENULTIMATE]))

        site_results, site_replays = {}, {}
        for number, site in traces.items():
            prefix = name if number == index else f'{name}/cell_{number}'
            site_results[number], site_replays[number] = compare_cell(case, number, prefix, site, start, checks)
            if name == 'no_tracking':
                checks[f'{prefix}/acoustics_all_zero'] = all((trace[field] == 0).all() for trace in site.values()
                                                            for field in REPLAY_FIELDS[:6])
        results[name] = site_results.pop(index)
        checks[f'{name}/first_pressure_difference_reproduced'] = (
            results[name]['first_differences']['pressure_dyn_cm2'] == case['expected_first_pressure_offsets'][name])
        if site_results:
            results[name]['other_cells'] = site_results
        all_replays[name] = site_replays if site_results else site_replays[index]
    first = results['matched_time']['first_pressure_residual']
    hypotheses = {'inflow_alone_restores_first_pressure': first is not None and any(
        row['swapped_inputs'] == ('inflow',) and row['matches_upstream'] for row in first['substitutions'])}
    write(out / 'trachea-interior-replay.json', all_replays)
    return {'checks': checks, 'hypotheses': hypotheses, 'sample_rate_hz': rate, 'window': window,
            'trachea_cell_index': index, 'candidate_binary_sha256': binary, 'conditions': results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('--case', type=Path, default=CASE)
    args = parser.parse_args()
    case_path = args.case.resolve()
    case = read(case_path)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    baseline = case['baseline']
    final_patch = f"artifacts/{baseline.get('patch', 'trachea-end-momentum.patch')}"
    candidate_label = baseline.get('candidate_label', 'trachea-momentum')
    names = ('summary.json', final_patch, *(f'artifacts/{name}{suffix}'
                                        for name in CONDITIONS for suffix in ('.json', f'-{candidate_label}.csv', '-upstream.csv')))
    manifest, saved = registered_artifacts(baseline, baseline.get('case_id', BASE_ID), revision, names)
    entries = read(manifest)['inputs']
    patches = []
    for digest in read(saved['summary.json'])['build']['preceding_patch_sha256']:
        row, = (item for item in entries if item['path'].endswith('.patch') and item['sha256'] == digest)
        path = ROOT / row['path']
        if path.stat().st_size != row['bytes'] or sha256(path) != row['sha256']:
            parser.error(f'対象の先行差分が保存時と一致しません ({path.name})')
        patches.append(path)
    patches.append(saved[final_patch])
    copies = [*candidate_sources(), WORKSPACE / 'data/cmudict.txt.gz', WORKSPACE / 'data/mandarin.txt.gz']
    tools = [WORKSPACE / 'tools' / name for name in (
        'measure_songbird_airway.py', 'measure_songbird_chirps_beak_load.py', 'measure_songbird_chirps_beak_tip_inflow.py',
        'measure_songbird_chirps_beak_tip_inflow_44100.py', 'measure_songbird_chirps_oec_neck_44100.py',
        'measure_songbird_chirps_oec_pressure_44100.py', 'measure_songbird_chirps_terminal_numerator_44100.py',
        'measure_songbird_chirps_trachea_end_balance_44100.py', 'measure_songbird_chirps_volume_rate_propagation_44100.py',
        'measure_songbird_syrinx.py', 'measure_speech_timing.py', 'measure_uniform_tube.py')]
    inputs = [case_path, Path(__file__), PROBE, manifest, *saved.values(), *patches[:-1], *copies, *tools,
              UPPER_NETWORK, UPPER_SONGBIRD, UPSTREAM / 'crates/chimera/src/physics.rs',
              UPSTREAM / 'crates/chimera/tests/airway.rs']
    details = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision,
               'analysis_command': [sys.executable, *sys.argv], 'analysis_directory': str(Path.cwd())}
    snapshot = WORKSPACE / 'runs' / args.run_id / 'artifacts/source'
    return record_measurement(args.run_id, case_path, inputs, details,
                              lambda out, execute: measure(case, saved, patches, snapshot, copies, out, execute),
                              command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
