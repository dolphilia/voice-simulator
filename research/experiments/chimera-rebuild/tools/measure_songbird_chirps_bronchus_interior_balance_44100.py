"""左右気管支の手前セルの圧力と流入・流出を固定上流へ照合する。"""

import argparse
from pathlib import Path
import subprocess
import sys

from measure_songbird_airway import PROBE, SIDES
from measure_songbird_chirps_beak_load import ROOT
from measure_songbird_chirps_beak_tip_inflow_44100 import registered_artifacts
from measure_songbird_chirps_bronchus_end_balance_44100 import (
    CASE as END_CASE, balance_columns, capture_bronchus_traces, compare_end,
)
from measure_songbird_chirps_left_syrinx_half_inertance_44100 import configure
from measure_songbird_chirps_left_syrinx_port_44100 import stored_trace
from measure_songbird_chirps_oec_pressure_44100 import CONDITIONS
from measure_songbird_chirps_right_bronchus_linear_44100 import MOMENTUM_LABELS, MOMENTUM_PATCH
from measure_songbird_chirps_right_syrinx_half_inertance_44100 import restore_patches
from measure_songbird_chirps_terminal_numerator_44100 import same_bits
from measure_songbird_chirps_trachea_interior_momentum_44100 import capture_prefix_matches
from measure_speech_timing import read, write
from measure_uniform_tube import candidate_sources, record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/songbird-chirps-bronchus-interior-balance-44100.json'
BASELINE_CASE = WORKSPACE / 'cases/songbird-chirps-right-bronchus-momentum-44100.json'


def measure(case, saved, upper_saved, patches, snapshot, copies, out, execute):
    index = case['interior_cell']
    configurations = configure(case, saved, out)
    for path in configurations.values():
        source = read(path)
        if source['songbird_airway'].get('observe_bronchus_end_balance') is not True:
            raise ValueError('先行実行の気管支末端の観測指定が必要です')
        source['songbird_airway']['observe_bronchus_interior_cells'] = [index]
        write(path, source)
    plain = 'matched_time_without_bronchus_interior'
    candidate, upstream, binary = capture_bronchus_traces(
        {plain: saved['artifacts/matched_time.json']} | configurations, patches, snapshot, copies, out, execute)
    legacy = MOMENTUM_LABELS[1]
    checks = {
        'candidate_without_interior_observation_reproduced': sha256(candidate[plain]) == sha256(
            saved[f'artifacts/matched_time-{legacy}.csv']),
        'upstream_without_interior_observation_reproduced': sha256(upstream[plain]) == sha256(
            upper_saved['artifacts/matched_time-upstream.csv']),
    }
    results, series = {}, {}
    columns = tuple(field for side in SIDES for field in balance_columns(side, index))
    baseline = read(saved['summary.json'])['conditions']
    for name in CONDITIONS:
        start = case['condition_control_samples'][name]
        count = start + case['observation_internal_samples']
        checks[f'{name}/candidate_existing_columns_reproduced'] = capture_prefix_matches(
            candidate[name], saved[f'artifacts/{name}-{legacy}.csv'], count + 1, len(columns))
        checks[f'{name}/upstream_existing_columns_reproduced'] = capture_prefix_matches(
            upstream[name], upper_saved[f'artifacts/{name}-upstream.csv'], count + 1, len(columns))
        traces = {'candidate': stored_trace(candidate[name], count), 'upstream': stored_trace(upstream[name], count)}
        if any(trace.dtype.names[-len(columns):] != columns for trace in traces.values()):
            raise ValueError(f'気管支内部セルの観測列が一致しません ({name})')
        results[name], series[name] = {}, {}
        for side in SIDES:
            results[name][side], series[name][side] = compare_end(
                traces, start, side, name, case, checks, interior_cell=index)
            pressure, outflow, *_ = balance_columns(side, index)
            for label, trace in traces.items():
                checks[f'{name}/{side}/{label}/interior_matches_end_observation'] = (
                    same_bits(trace[pressure], trace[f'{side}_bronchus_end_upstream_pressure_dyn_cm2'])
                    and same_bits(trace[outflow], trace[f'{side}_bronchus_end_inflow_cm3_s']))
        checks[f'{name}/registered_pressure_offset_matches_archived_summary'] = (
            case['expected_right_pressure_offsets'][name] == baseline[name]['experiment_minus_upstream'].get(
                'right_bronchus_end_upstream_pressure_dyn_cm2', {}).get('offset'))
    write(out / 'bronchus-interior-balance-replay.json', series)
    return {'checks': checks, 'conditions': results, 'sample_rate_hz': case['sample_rate_hz'],
            'window': case['observation_internal_samples'], 'interior_cell': index, 'candidate_binary_sha256': binary,
            'applied_patch_sha256': [sha256(path) for path in patches]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    case, prior, end = (read(path) for path in (CASE, BASELINE_CASE, END_CASE))
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    if any(case[key] != prior[key] or case[key] != end[key] for key in (
            'upstream_revision', 'sample_rate_hz', 'output_rate_hz', 'condition_control_samples',
            'observation_internal_samples')):
        parser.error('先行実行と気管支内部の観測条件が一致しません')
    if case['geometry'] != end['geometry'] or case['interior_cell'] != case['geometry']['cells'] - 2:
        parser.error('先行の気管支の幾何と末端の一つ手前のセルを指定してください')
    trace_label = MOMENTUM_LABELS[1]
    names = ('summary.json', f'artifacts/{MOMENTUM_PATCH}.patch', *(f'artifacts/{name}{suffix}'
             for name in CONDITIONS for suffix in ('.json', f'-{trace_label}.csv')))
    manifest_path, saved = registered_artifacts(case['baseline'], prior['id'], revision, names)
    manifest = read(manifest_path)
    indexed = {row['path']: row['sha256'] for row in manifest['inputs']}
    if any(indexed.get(path.relative_to(ROOT).as_posix()) != sha256(path) for path in (BASELINE_CASE, END_CASE)):
        parser.error('先行実行で使用したケース定義が必要です')
    upper_manifest, upper = registered_artifacts(case['upstream_observation'], end['id'], revision,
                                                 tuple(f'artifacts/{name}-upstream.csv' for name in CONDITIONS))
    if any(indexed.get(path.relative_to(ROOT).as_posix()) != sha256(path) for path in upper.values()):
        parser.error('先行実行で使用した固定上流の観測CSVが必要です')
    patches = restore_patches(manifest, saved, MOMENTUM_PATCH)
    copies = [*candidate_sources(), WORKSPACE / 'data/cmudict.txt.gz', WORKSPACE / 'data/mandarin.txt.gz']
    references = [ROOT / path for path in indexed
                  if (ROOT / path).parent == WORKSPACE / 'tools' or (ROOT / path).is_relative_to(UPSTREAM)]
    inputs = [CASE, BASELINE_CASE, END_CASE, Path(__file__), PROBE, manifest_path, *saved.values(), upper_manifest,
              *upper.values(), *patches, *copies, *references]
    details = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision,
               'analysis_command': [sys.executable, *sys.argv], 'analysis_directory': str(Path.cwd())}
    snapshot = WORKSPACE / 'runs' / args.run_id / 'artifacts/source'
    return record_measurement(args.run_id, CASE, inputs, details,
                              lambda out, execute: measure(case, saved, upper, patches, snapshot, copies, out, execute),
                              command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
