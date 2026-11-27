"""左右の空気嚢ポートと気管支セル0の圧力収支を固定上流に照合する。"""

import argparse
from pathlib import Path
import subprocess
import sys

from measure_songbird_airway import C, PROBE, RHO, SIDES
from measure_songbird_chirps_beak_load import ROOT
from measure_songbird_chirps_beak_tip_inflow_44100 import registered_artifacts
from measure_songbird_chirps_bronchus_end_balance_44100 import (
    balance_columns, capture_bronchus_traces, locate_pressure_residual, pressure_balance,
)
from measure_songbird_chirps_bronchus_interior_balance_44100 import CASE as UPPER_CASE
from measure_songbird_chirps_left_syrinx_half_inertance_44100 import configure
from measure_songbird_chirps_left_syrinx_port_44100 import stored_trace
from measure_songbird_chirps_oec_neck_44100 import diagnose, evaluate, port_impedance
from measure_songbird_chirps_oec_pressure_44100 import CONDITIONS
from measure_songbird_chirps_right_bronchus_linear_44100 import (
    INTERIOR_MOMENTUM_LABELS, INTERIOR_MOMENTUM_PATCH,
)
from measure_songbird_chirps_right_syrinx_half_inertance_44100 import restore_patches
from measure_songbird_chirps_terminal_numerator_44100 import first_offset, same_bits
from measure_songbird_chirps_trachea_interior_momentum_44100 import capture_prefix_matches
from measure_speech_timing import read, write
from measure_uniform_tube import candidate_sources, record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/songbird-chirps-bronchus-inlet-balance-44100.json'
PRIOR_CASE = WORKSPACE / 'cases/songbird-chirps-right-bronchus-interior-momentum-44100.json'
SAC = 'sac_pressure_dyn_cm2'
LABEL = INTERIOR_MOMENTUM_LABELS[1]


def replay(trace, start, side, case, *, upstream, multiply_momentum=False):
    geometry, port = case['geometry'], case['port']
    area, length = geometry['area_cm2'], geometry['length_cm'] / geometry['cells']
    rate = case['sample_rate_hz']
    dt = 1 / rate
    gain = dt / (area * length / (RHO * C * C))
    inertance, resistance, forward_loss, reverse_loss = port_impedance(
        port['area_cm2'], (geometry['sac_area_cm2'], area), (geometry['sac_length_cm'], length),
        port, upstream=upstream)
    normalized_inertance = inertance * rate if upstream else inertance / dt
    pressure, outflow, _, inflow, _, _ = balance_columns(side, 0)
    rows = []
    for previous, current in zip(trace[start - 1:-1], trace[start:], strict=True):
        old_flow = float(previous[inflow])
        current_sac = float(current[SAC])
        old_pressure = float(previous[pressure])
        history = ((inertance * old_flow) * rate if upstream or multiply_momentum
                   else normalized_inertance * old_flow)
        terms = {'pressure_difference': current_sac - old_pressure, 'noise_pressure': 0.0,
                 'normalized_momentum': history, 'normalized_inertance': normalized_inertance,
                 'resistance': resistance, 'forward_loss': forward_loss, 'reverse_loss': reverse_loss}
        state = {'sac_pressure': current_sac, 'cell_pressure': old_pressure, 'previous_flow': old_flow,
                 'previous_inertance': inertance, 'current_inertance': inertance}
        inputs = {'previous_pressure': old_pressure, 'inflow': float(current[inflow]),
                  'outflow': float(current[outflow])}
        rows.append({'previous_state': state, 'terms': terms, 'result': evaluate(terms),
                     'observed': inputs['inflow'], 'pressure_inputs': inputs,
                     'pressure': pressure_balance(inputs, gain), 'observed_pressure': float(current[pressure])})
    return rows, gain


def compare(traces, start, name, side, case, checks):
    pressure, outflow, sac, inflow, area, length = balance_columns(side, 0)
    geometry = case['geometry']
    rows = {}
    for label, trace in traces.items():
        series, gain = replay(trace, start, side, case, upstream=label == 'upstream')
        rows[label] = series
        prefix = f'{name}/{side}/{label}'
        checks[f'{prefix}/geometry_matches'] = bool(
            (trace[area] == geometry['area_cm2']).all()
            and (trace[length] == geometry['length_cm'] / geometry['cells']).all())
        checks[f'{prefix}/sac_matches_existing_observation'] = same_bits(trace[sac], trace[SAC])
        checks[f'{prefix}/outlet_matches_cell_1_inflow'] = same_bits(trace[outflow], trace[balance_columns(side, 1)[3]])
        checks[f'{prefix}/pressure_bit_replayed'] = all(
            row['pressure'].hex() == row['observed_pressure'].hex() for row in series)
        checks[f'{prefix}/port_flow_bit_replayed'] = all(
            row['result']['flow'].hex() == row['observed'].hex() for row in series)
        if name == 'no_tracking':
            checks[f'{prefix}/unexcited'] = all((trace[field] == 0).all() for field in (pressure, outflow, sac, inflow))
        onset = trace[start - 1]
        checks[f'{prefix}/initially_at_rest'] = all(float(onset[field]) == 0 for field in (pressure, inflow))
    candidate, upstream = traces['candidate'], traces['upstream']
    offsets = {field: first_offset(candidate[field][start:], upstream[field][start:])
               for field in (pressure, outflow, sac, inflow)}
    pressure_residual = locate_pressure_residual(rows, offsets[pressure], gain)
    port_residual = diagnose(rows['candidate'], rows['upstream'], offsets[inflow], case['sample_rate_hz'],
                             pressure_keys=('sac_pressure', 'cell_pressure'))
    if side == 'right':
        expected = case['expected_right_pressure_offsets'][name]
        prefix = f'{name}/{side}'
        checks[f'{prefix}/registered_pressure_offset'] = offsets[pressure] == expected
        if expected is not None:
            checks[f'{prefix}/port_residual_no_later_than_pressure'] = (
                offsets[inflow] is not None and offsets[inflow] <= expected)
            c, u = (pressure_residual[key]['pressure_inputs'] if pressure_residual else {}
                    for key in ('candidate', 'upstream'))
            checks[f'{prefix}/previous_pressure_and_outflow_identical'] = bool(c and u) and all(
                c[field].hex() == u[field].hex() for field in ('previous_pressure', 'outflow'))
            checks[f'{prefix}/inflow_only_reproduces_pressure'] = (
                pressure_residual is not None and pressure_residual['single_substitutions']['inflow']['matches_upstream'])
    return {'first_differences': offsets, 'first_pressure_residual': pressure_residual,
            'first_port_residual': port_residual, 'pressure_gain': gain}, rows


def measure(case, saved, upper, patches, snapshot, copies, out, execute):
    configurations = configure(case, saved, out)
    for path in configurations.values():
        source = read(path)
        bird = source['songbird_airway']
        if bird['observe_bronchus_interior_cells'] != [1]:
            raise ValueError('先行のセル1観測を指定してください')
        bird['observe_bronchus_interior_cells'].append(0)
        write(path, source)
    plain = 'matched_time_without_bronchus_inlet'
    candidates, upstream, binary = capture_bronchus_traces(
        {plain: saved['artifacts/matched_time.json']} | configurations, patches, snapshot, copies, out, execute)
    checks = {
        'candidate_without_inlet_reproduced': sha256(candidates[plain]) == sha256(
            saved[f'artifacts/matched_time-{LABEL}.csv']),
        'upstream_without_inlet_reproduced': sha256(upstream[plain]) == sha256(
            upper['artifacts/matched_time-upstream.csv']),
    }
    columns = tuple(column for side in SIDES for column in balance_columns(side, 0))
    results, series = {}, {}
    baseline = read(saved['summary.json'])['conditions']
    for name in CONDITIONS:
        start = case['condition_control_samples'][name]
        count = start + case['observation_internal_samples']
        files = {'candidate': (candidates[name], saved[f'artifacts/{name}-{LABEL}.csv']),
                 'upstream': (upstream[name], upper[f'artifacts/{name}-upstream.csv'])}
        traces = {}
        for label, (path, archived) in files.items():
            checks[f'{name}/{label}/existing_columns_reproduced'] = capture_prefix_matches(
                path, archived, count + 1, len(columns))
            trace = traces[label] = stored_trace(path, count)
            if trace.dtype.names[-len(columns):] != columns:
                raise ValueError(f'セル0の観測列が一致しません ({name}/{label})')
        results[name], series[name] = {}, {}
        for side in SIDES:
            results[name][side], series[name][side] = compare(traces, start, name, side, case, checks)
        key = balance_columns('right', 1)[2]
        archived = baseline[name]['experiment_minus_upstream'].get(key)
        checks[f'{name}/registered_offset_matches_archived_summary'] = (
            case['expected_right_pressure_offsets'][name] == (archived['offset'] if archived else None))
    write(out / 'bronchus-inlet-balance-replay.json', series)
    return {'checks': checks, 'conditions': results, 'sample_rate_hz': case['sample_rate_hz'],
            'window': case['observation_internal_samples'], 'candidate_binary_sha256': binary,
            'applied_patch_sha256': [sha256(path) for path in patches]}


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
        parser.error('先行実行とセル0の観測条件が一致しません')
    if upper_case['geometry'] != {key: case['geometry'][key] for key in upper_case['geometry']}:
        parser.error('先行実行と気管支の幾何が一致しません')
    names = ('summary.json', f'artifacts/{INTERIOR_MOMENTUM_PATCH}.patch', *(f'artifacts/{name}{suffix}'
             for name in CONDITIONS for suffix in ('.json', f'-{LABEL}.csv')))
    manifest_path, saved = registered_artifacts(case['baseline'], prior['id'], revision, names)
    upper_manifest, upper = registered_artifacts(case['upstream_observation'], upper_case['id'], revision,
                                                 tuple(f'artifacts/{name}-upstream.csv' for name in CONDITIONS))
    manifest = read(manifest_path)
    indexed = {row['path']: row['sha256'] for row in manifest['inputs']}
    if any(indexed.get(path.relative_to(ROOT).as_posix()) != sha256(path)
           for path in (PRIOR_CASE, UPPER_CASE, upper_manifest, *upper.values())):
        parser.error('先行実行で使用したケース定義と固定上流CSVが必要です')
    patches = restore_patches(manifest, saved, INTERIOR_MOMENTUM_PATCH)
    copies = [*candidate_sources(), WORKSPACE / 'data/cmudict.txt.gz', WORKSPACE / 'data/mandarin.txt.gz']
    references = [ROOT / path for path in indexed
                  if (ROOT / path).parent == WORKSPACE / 'tools' or (ROOT / path).is_relative_to(UPSTREAM)]
    inputs = [CASE, PRIOR_CASE, UPPER_CASE, Path(__file__), PROBE, manifest_path, *saved.values(), upper_manifest,
              *upper.values(), *patches, *copies, *references]
    details = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision,
               'analysis_command': [sys.executable, *sys.argv], 'analysis_directory': str(Path.cwd())}
    snapshot = WORKSPACE / 'runs' / args.run_id / 'artifacts/source'
    return record_measurement(args.run_id, CASE, inputs, details,
                              lambda out, execute: measure(case, saved, upper, patches, snapshot, copies, out, execute),
                              command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
