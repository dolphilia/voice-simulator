"""扇状走査線の割り当て削減と、固定基準へのビット一致を調べる。"""

import argparse
from itertools import zip_longest
from pathlib import Path
import re
import subprocess
import sys

import numpy as np
from scipy.io import wavfile

import measure_uniform_tube as shared
from measure_wasm_fixed import compare_pcm, read_json
from upstream_baseline import UPSTREAM, WORKSPACE, sha256

CASE = WORKSPACE / 'cases/fan-crossing-allocations.json'
GRID = 'crates/vocal-core/src/anatomy/grid.rs'
LIVE_FILES = ('browser.wav', 'offline.wav', 'voicing.csv', 'pcm-128.csv', 'pcm-77.csv')


def run_manifest(run_id, case_id, revision):
    root = WORKSPACE / 'runs' / run_id
    manifest = read_json(root / 'manifest.json')
    if manifest['case_id'] != case_id or manifest['upstream_revision'] != revision:
        raise ValueError(f'{run_id} のケースまたは上流版が一致しません')
    return root, manifest


def verified_path(run, path):
    root, manifest = run
    expected = next((entry['sha256'] for entry in manifest['outputs'] if entry['path'] == path), None)
    file = root / path
    if not file.is_file() or sha256(file) != expected:
        raise ValueError(f'{root.name} の保存出力 {path} を照合できません')
    return file


def csv_comparison(left, right):
    equal = sha256(left) == sha256(right)
    first = None
    if not equal:
        with left.open() as a, right.open() as b:
            first = next((i for i, pair in enumerate(zip_longest(a, b), start=1) if pair[0] != pair[1]), None)
    return {'byte_equal': equal, 'first_different_line': first}


def bit_comparison(left, right):
    a, b = (np.asarray(values, dtype='<f8') for values in (left, right))
    if a.shape != b.shape or not (np.isfinite(a).all() and np.isfinite(b).all()):
        raise ValueError('比較する観測列の形状または有限性が一致しません')
    differences = np.flatnonzero(a.view('<u8') != b.view('<u8'))
    first = list(map(int, np.unravel_index(differences[0], a.shape))) if differences.size else None
    return {'different_values': int(differences.size), 'first_index': first,
            'maximum_absolute_error': float(abs(a - b).max())}


def compare_live(reference, candidate):
    paths = {name: (verified_path(reference, f'artifacts/{name}'), verified_path(candidate, f'artifacts/{name}'))
             for name in (*LIVE_FILES, 'browser.json')}
    before, after = map(read_json, paths['browser.json'])
    a, b = (wavfile.read(path) for path in paths['browser.wav'])
    if a[0] != b[0] or a[1].dtype != np.float32 or b[1].dtype != np.float32:
        raise ValueError('保存WAVのレートまたはPCM型が一致しません')
    pcm = compare_pcm(b[1], a[1], 0)
    waves = {name: sha256(paths[name][0]) == sha256(paths[name][1]) for name in ('browser.wav', 'offline.wav')}
    columns = [('observations', before['observations'], after['observations']),
               ('tract_geometry', before['tract']['rows'], after['tract']['rows']),
               ('tract_acoustics', before['tract']['acoustics']['rows'], after['tract']['acoustics']['rows']),
               ('glottal', before['glottal']['values'], after['glottal']['values'])]
    observations = {key: bit_comparison(a, b) for key, a, b in columns}
    trace = {name: csv_comparison(*paths[name]) for name in LIVE_FILES if name.endswith('.csv')}
    schemas_equal = (before['columns'] == after['columns']
                     and before['tract']['counts'] == after['tract']['counts']
                     and before['tract']['acoustics']['columns'] == after['tract']['acoustics']['columns']
                     and before['glottal']['columns'] == after['glottal']['columns'])
    return ({
        'pcm_bitwise_unchanged': pcm['first_bit_difference_frame'] is None and all(waves.values()),
        'observations_bitwise_unchanged': schemas_equal and all(v['different_values'] == 0 for v in observations.values()),
        'dense_native_traces_unchanged': all(v['byte_equal'] for v in trace.values()),
    }, {'pcm': pcm, 'wav_byte_agreement': waves, 'observations': observations, 'dense_native_traces': trace})


def measure(case, run_id, reference, geometry_references, artifacts, execute):
    cfg = case['measurement']
    revision = case['upstream_revision']
    execute(['cargo', 'test', '--locked', '-p', 'vocal-core', 'anatomy::grid'],
            stdout=artifacts / 'candidate-grid-tests.log')
    execute(['cargo', 'test', '--locked', '-p', 'chimera', '--test', 'geometry_continuity'],
            cwd=UPSTREAM, stdout=artifacts / 'upstream-geometry-tests.log')

    # 実時間の処理時間を測ってから、ほかのレンダーを順に実行する。
    live_id = f'{run_id}-live'
    execute([sys.executable, str(WORKSPACE / 'tools/measure_worklet_ipa.py'), live_id, '--live'])
    candidate = run_manifest(live_id, 'worklet-live-ipa', revision)
    checks, live = compare_live(reference, candidate)
    before, after = (read_json(verified_path(run, 'summary.json'))['realtime'] for run in (reference, candidate))
    allocation = {}
    for key, window in (('total', 'all'), ('warmed', 'after_32_quanta')):
        initial = before['native_allocations'][key]
        final = after['native_allocations'][key]
        allocation[window] = {'before': initial, 'after': final, 'reduction_fraction': 1 - final / initial}
    checks['native_allocation_reduction'] = all(
        allocation[window]['reduction_fraction'] >= cfg['minimum_native_allocation_reduction_fraction']
        for window in cfg['allocation_windows'])
    source_digests = [{item['path']: item['sha256'] for item in run[1]['inputs']} for run in (reference, candidate)]
    input_paths = source_digests[0].keys() | source_digests[1].keys()
    changed = sorted(path for path in input_paths if source_digests[0].get(path) != source_digests[1].get(path))
    grid_path = str((WORKSPACE / GRID).relative_to(WORKSPACE.parents[2]))
    checks['only_grid_source_changed'] = changed == [grid_path]

    children = {live_id: sha256(candidate[0] / 'manifest.json')}
    geometry = {}
    for case_id, prior in geometry_references.items():
        current_id = f'{run_id}-{case_id.removeprefix("tract-slew-")}'
        execute([sys.executable, str(WORKSPACE / 'tools/measure_tract_control.py'), current_id, case_id])
        current = run_manifest(current_id, case_id, revision)
        children[current_id] = sha256(current[0] / 'manifest.json')
        trace = [verified_path(run, 'artifacts/trace.csv') for run in (prior, current)]
        geometry[case_id] = {'candidate_run': current_id, 'candidate_status': current[1]['status'],
                             'reference_run': prior[0].name, **csv_comparison(*trace)}
    checks['native_geometry_traces_unchanged'] = all(
        row['candidate_status'] == 'pass' and row['byte_equal'] for row in geometry.values())
    return {'checks': checks, 'live': live, 'geometry': geometry, 'allocation': allocation,
            'candidate_manifests': children, 'changed_live_inputs': changed,
            'timing': {'reference': before['timing'], 'candidate': after['timing']},
            'wasm_memory_growths': {'reference': before['wasm_memory_growths'],
                                    'candidate': after['wasm_memory_growths']}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', args.run_id):
        parser.error('実行IDは英数字で始めてください')
    case = read_json(CASE)
    revision = case['upstream_revision']
    if revision != subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip() or (
            subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True)):
        parser.error('変更のない固定上流版が必要です')
    ref = case['reference']
    live = run_manifest(ref['live_run'], 'worklet-live-ipa', revision)
    if sha256(live[0] / 'manifest.json') != ref['live_manifest_sha256'] or live[1]['status'] != 'pass':
        parser.error('事前登録した基準のマニフェストが一致しません')
    grid = live[0] / live[1]['source_snapshot'] / (WORKSPACE / GRID).relative_to(WORKSPACE.parents[2])
    if sha256(grid) != ref['grid_source_sha256']:
        parser.error('事前登録した基準の走査コードが一致しません')
    geometry = {key: run_manifest(value, key, revision) for key, value in ref['geometry_runs'].items()}
    if any(run[1]['status'] != 'pass' for run in geometry.values()):
        parser.error('基準の幾何比較に不通過の実行があります')
    inputs = [CASE, WORKSPACE / GRID, Path(__file__).resolve(), Path(shared.__file__), grid,
              *(WORKSPACE / 'tools' / name for name in (
                  'measure_worklet_ipa.py', 'measure_worklet_live_ipa.py', 'measure_tract_control.py',
                  'measure_wasm_fixed.py', 'upstream_baseline.py')),
              live[0] / 'manifest.json',
              *(verified_path(live, name) for name in ('summary.json', *(f'artifacts/{p}' for p in (*LIVE_FILES, 'browser.json')))),
              *(run[0] / 'manifest.json' for run in geometry.values()),
              *(verified_path(run, 'artifacts/trace.csv') for run in geometry.values())]
    info = {'case_id': case['id'], 'upstream_revision': revision, 'reference': ref['live_run']}
    return shared.record_measurement(
        args.run_id, CASE, inputs, info,
        lambda out, execute: measure(case, args.run_id, live, geometry, out, execute), command=None)


if __name__ == '__main__':
    raise SystemExit(main())
