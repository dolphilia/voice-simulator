"""矢状面の輪郭と調音制御の割り当てを、固定した発話と幾何データで比較する。"""

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

import measure_uniform_tube as shared
from measure_fan_crossing_allocations import (
    LIVE_FILES, compare_live, csv_comparison, run_manifest, verified_path,
)
from measure_wasm_fixed import read_json
from upstream_baseline import UPSTREAM, WORKSPACE, sha256

CASE = WORKSPACE / 'cases/contour-buffer-reuse.json'
TOOLS = WORKSPACE / 'tools'


def measure_profile(case, artifacts, execute):
    log = artifacts / 'stage-allocations.log'
    execute(['cargo', 'test', '--locked', '--release', '-p', 'vocal-core',
             'profile_geometry_allocations', '--', '--nocapture'], stdout=log)
    prefix = 'tract_stage_allocations='
    lines = [line.removeprefix(prefix) for line in log.read_text().splitlines()
             if line.startswith(prefix)]
    if len(lines) != 1:
        raise ValueError(f'区間別の計測行が {len(lines)} 件です')
    rows = json.loads(lines[0])
    setup = case['inputs']
    expected_ticks = setup['profile_control_frames']
    fields = case['measurement']['profile_fields']
    checks = {
        'registered_profile_samples': [row['control_frame'] for row in rows] == expected_ticks
        and [row['internal_sample'] for row in rows] ==
        [tick * setup['control_internal_samples'] for tick in expected_ticks],
        'allocations_counted': all(row['control_step'] >= sum(row[field] for field in fields) > 0
                                  for row in rows),
    }
    return checks, rows


def reference_run(fixture, case_id, revision):
    run = run_manifest(fixture['run'], case_id, revision)
    if sha256(run[0] / 'manifest.json') != fixture['sha256'] or run[1]['status'] != 'pass':
        raise ValueError(f'{fixture["run"]} の基準マニフェストを照合できません')
    return run


def measure_baseline(case, artifacts, execute):
    checks, rows = measure_profile(case, artifacts, execute)
    totals = {field: sum(row[field] for row in rows)
              for field in case['measurement']['profile_fields']}
    checks['contour_largest_stage'] = totals['contour'] > max(
        value for field, value in totals.items() if field != 'contour')
    return {'checks': checks, 'profile': rows, 'stage_totals': totals}


def measure_candidate(case, run_id, profile_reference, before_fan, after_fan,
                      geometry_references, artifacts, execute):
    checks, rows = measure_profile(case, artifacts, execute)
    old = read_json(verified_path(profile_reference, 'summary.json'))['profile']
    cfg = case['measurement']
    checks['profile_postures_unchanged'] = [
        (row['internal_sample'], row['posture']) for row in rows
    ] == [(row['internal_sample'], row['posture']) for row in old]
    checks['contour_allocation_target'] = all(
        row['contour'] == cfg['expected_contour_allocations_per_call'] for row in rows)
    checks['other_stage_counts_unchanged'] = all(
        [row[field] for row in rows] == [row[field] for row in old]
        for field in cfg['profile_fields'] if field != 'contour')

    live_id = f'{run_id}-live'
    execute([sys.executable, str(TOOLS / 'measure_worklet_ipa.py'), live_id, '--live'])
    revision = case['upstream_revision']
    candidate = run_manifest(live_id, 'worklet-live-ipa', revision)
    live_checks, live = compare_live(after_fan, candidate)
    checks.update(live_checks)
    checks['live_child_passed'] = candidate[1]['status'] == 'pass'
    summaries = [read_json(verified_path(run, 'summary.json'))['realtime']
                 for run in (before_fan, after_fan, candidate)]
    allocation = {}
    for field, window in (('total', 'all'), ('warmed', 'after_32_quanta')):
        initial, baseline, final = [summary['native_allocations'][field] for summary in summaries]
        allocation[window] = {'before_fan': initial, 'after_fan': baseline, 'after_contour': final,
                              'saved_by_contour': baseline - final,
                              'cumulative_reduction_fraction': 1 - final / initial}
    checks['cumulative_native_allocation_target'] = all(
        allocation[window]['cumulative_reduction_fraction'] >= cfg['minimum_cumulative_native_reduction_fraction']
        for window in cfg['allocation_windows'])

    children = {live_id: sha256(candidate[0] / 'manifest.json')}
    geometry = {}
    for case_id, reference in geometry_references.items():
        current_id = f'{run_id}-{case_id}'
        script = 'measure_sagittal.py' if case_id.startswith('sagittal-') else 'measure_tract_control.py'
        execute([sys.executable, str(TOOLS / script), current_id, case_id])
        current = run_manifest(current_id, case_id, revision)
        children[current_id] = sha256(current[0] / 'manifest.json')
        traces = [verified_path(run, 'artifacts/trace.csv') for run in (reference, current)]
        geometry[case_id] = {'reference_run': reference[0].name, 'candidate_run': current_id,
                             'candidate_status': current[1]['status'], **csv_comparison(*traces)}
    checks['native_geometry_traces_unchanged'] = all(
        row['candidate_status'] == 'pass' and row['byte_equal'] for row in geometry.values())
    execute(['cargo', 'test', '--locked', '-p', 'chimera', '--test', 'geometry_continuity'],
            cwd=UPSTREAM, stdout=artifacts / 'upstream-geometry-tests.log')
    return {'checks': checks, 'baseline_profile': old, 'candidate_profile': rows,
            'allocation': allocation, 'live': live, 'geometry': geometry,
            'candidate_manifests': children,
            'timing': [summary['timing'] for summary in summaries],
            'wasm_memory_growths': [summary['wasm_memory_growths'] for summary in summaries]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('--baseline', action='store_true')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', args.run_id):
        parser.error('実行IDは英数字で始めてください')
    case = read_json(CASE)
    revision = case['upstream_revision']
    if revision != subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip() or (
            subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True)):
        parser.error('変更のない固定上流版が必要です')

    setup = case['inputs']
    ref = case['reference']
    inputs = [CASE, WORKSPACE / 'cases' / setup['speech_case'], WORKSPACE / 'cases' / setup['worklet_case'],
              Path(__file__).resolve(), Path(shared.__file__), *shared.candidate_sources()]
    details = {'case_id': case['id'], 'upstream_revision': revision, 'baseline_profile': args.baseline}

    if args.baseline:
        def measure(out, execute):
            return measure_baseline(case, out, execute)
    else:
        profile = run_manifest(ref['profile_run'], case['id'], revision)
        if profile[1]['status'] != 'pass' or not profile[1]['baseline_profile']:
            parser.error('区間別の割り当て計測が通過した基準が必要です')
        profile_inputs = {item['path']: item['sha256'] for item in profile[1]['inputs']}
        if profile_inputs.get(str(CASE.relative_to(WORKSPACE))) != sha256(CASE):
            parser.error('区間別計測で登録したケースを照合できません')
        original, recent = [reference_run(ref[name], 'worklet-live-ipa', revision)
                            for name in ('before_fan', 'after_fan')]
        geometry = {key: reference_run(value, key, revision) for key, value in ref['geometry'].items()}
        inputs.extend([*(run[0] / 'manifest.json' for run in (profile, original, recent, *geometry.values())),
                       *(verified_path(run, 'summary.json') for run in (profile, original, recent)),
                       *(verified_path(recent, f'artifacts/{p}') for p in (*LIVE_FILES, 'browser.json')),
                       *(verified_path(run, 'artifacts/trace.csv') for run in geometry.values()),
                       *(TOOLS / name for name in (
                           'measure_worklet_ipa.py', 'measure_worklet_live_ipa.py', 'measure_sagittal.py',
                           'measure_tract_control.py', 'measure_fan_crossing_allocations.py',
                           'measure_wasm_fixed.py', 'upstream_baseline.py'))])
        details.update(reference_profile=ref['profile_run'], reference_live=ref['after_fan']['run'])

        def measure(out, execute):
            return measure_candidate(case, args.run_id, profile, original, recent, geometry, out, execute)

    return shared.record_measurement(args.run_id, CASE, inputs, details, measure, command=None)


if __name__ == '__main__':
    raise SystemExit(main())
