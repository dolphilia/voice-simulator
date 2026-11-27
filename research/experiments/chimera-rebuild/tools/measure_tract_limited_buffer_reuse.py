"""声道のセル領域の再利用を、通常CLIと歌唱ABIで検証する。"""

import argparse
from pathlib import Path
import subprocess
import sys

from measure_fan_crossing_allocations import run_manifest, verified_path
from measure_song_render_allocation_phases import analyze_phases, compare_pcm_observations, render_probe
from measure_speech_timing import read
from measure_uniform_tube import candidate_sources, record_measurement
from measure_worklet_fixed import ROOT, UPSTREAM, WORKSPACE
from upstream_baseline import sha256


CASE = WORKSPACE / 'cases/tract-limited-buffer-reuse.json'
CONTACT_PHASES = ('roof_cumulative', 'measurement_grid', 'contact_samples')


def render_geometry(folder, execute, cases):
    outputs = {}
    for source in cases:
        trace = folder / f'{source.stem}.csv'
        execute(['cargo', 'run', '--release', '--locked', '--offline', '-p', 'vocal-cli', '--',
                 'render', str(source), str(trace)])
        outputs[source.stem] = trace
    return outputs


def compare_allocation(folder, spec, settings, reference_counts):
    checks, result, report = analyze_phases(folder, settings,
                                           allocations_per_geometry_update=spec['allocations_per_geometry_update'])
    before = read(reference_counts)
    names = before['phase_names']
    observed_names = report['phase_names']
    extra = [name for name in observed_names if name not in names]
    if any(name not in CONTACT_PHASES for name in extra) or [n for n in observed_names if n not in extra] != names:
        raise ValueError('変更前と候補の計数点が一致しません')
    baseline_columns = [observed_names.index(name) for name in names]
    observed_phases = [[row[i] for i in baseline_columns] for row in report['phase_counts']]
    removed_phase = spec.get('removed_allocation_phase', 'clone_cells')
    removed_per_update = spec.get('removed_allocations_per_geometry_update', 2 if removed_phase else 0)
    expected_totals = []
    expected_phases = []
    for count, phase_counts in zip(before['total_by_quantum'], before['phase_counts'], strict=True):
        phases = dict(zip(names, phase_counts, strict=True))
        removed = phases[removed_phase]['allocations'] if removed_phase else 0
        # 乱流源の登録は apply・reapply の外で呼ばれる。
        apply_reduction = reapply_reduction = 0
        if removed_phase != 'turbulence':
            apply_reduction = removed_per_update * phases['apply']['calls']
            reapply_reduction = removed_per_update * phases['reapply']['calls']
            if removed != apply_reduction + reapply_reduction:
                raise ValueError(f'変更前の {removed_phase} が声道更新1回当たりの登録件数に一致しません')
        expected_totals.append(count - removed)
        reductions = {'control': removed, removed_phase: removed,
                      'apply': apply_reduction, 'reapply': reapply_reduction}
        if removed_phase in CONTACT_PHASES:
            reductions['contact_grid'] = removed
        expected_phases.append([row | {'allocations': row['allocations'] - reductions.get(name, 0)}
                                for name, row in phases.items()])
    allocations_removed = [old - current for old, current in
                           zip(before['total_by_quantum'], report['total_by_quantum'], strict=True)]
    checks.update(
        allocations_drop_only_at_target_phase=report['total_by_quantum'] == expected_totals,
        all_phase_counts_match_prediction=observed_phases == expected_phases,
        registered_totals_match=(result['allocations'], sum(allocations_removed))
                                == (spec['expected_allocations'], spec['expected_removed_allocations']),
        word_boundary_prediction_matched=result['word_boundary_prediction_matched'],
    )
    result['baseline_allocations'] = sum(before['total_by_quantum'])
    result['removed_allocations'] = sum(allocations_removed)
    result['removed_allocation_phase'] = removed_phase
    if 'contact_grid_allocations_per_call' in spec:
        check_contact_grid_phases(report, spec['contact_grid_allocations_per_call'], checks)
    return checks, result


def check_contact_grid_phases(report, expected, checks):
    names = report['phase_names']
    if set(expected) != set(CONTACT_PHASES) or not set(CONTACT_PHASES).issubset(names):
        raise ValueError('接触グリッドの計数点が登録条件に一致しません')
    parents = []
    children = []
    for row in report['phase_counts']:
        phases = dict(zip(names, row, strict=True))
        parents.append(phases['contact_grid'])
        children.append({name: phases[name] for name in CONTACT_PHASES})
    checks['contact_children_account_for_parent'] = all(
        sum(row['allocations'] for row in child.values()) == parent['allocations'] and
        all(row['calls'] == parent['calls'] for row in child.values())
        for parent, child in zip(parents, children, strict=True))
    checks['contact_child_counts_match_prediction'] = all(
        row['allocations'] == row['calls'] * expected[name]
        for child in children for name, row in child.items())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('--case', type=Path, default=CASE, help='比較するセル領域のケース定義')
    parser.add_argument('--geometry-baseline', action='store_true', help='変更前の断面系列を保存する')
    args = parser.parse_args()
    case_path = args.case.resolve(strict=True)
    spec = read(case_path)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if (revision != spec['upstream_revision']
            or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True)):
        parser.error('変更のない固定上流版が必要です')
    cases = [CASE.with_name(f'{name}.json') for name in spec['geometry_cases']]
    sources = [case_path, Path(__file__).resolve(), *cases, *candidate_sources()]
    details = {'case_id': spec['id'], 'case_revision': spec['revision'], 'upstream_revision': revision,
               'analysis_command': [sys.executable, *sys.argv]}
    if args.geometry_baseline:
        if args.run_id != spec['geometry_reference_run'] or spec.get('geometry_reference_case_id', spec['id']) != spec['id']:
            parser.error('登録した基準実行IDを指定してください')

        def reference(folder, execute):
            traces = render_geometry(folder, execute, cases)
            counts = {name: len(file.read_text().splitlines()) - 1 for name, file in traces.items()}
            return {'checks': {'all_geometry_traces_nonempty': all(n > 0 for n in counts.values())},
                    'geometry_rows': counts}

        return record_measurement(args.run_id, case_path, sources, details, reference, command=None, input_root=ROOT)

    probe_path = CASE.with_name(spec['allocation_case'])
    settings = read(probe_path)
    geometry = run_manifest(spec['geometry_reference_run'], spec.get('geometry_reference_case_id', spec['id']), revision)
    allocation = run_manifest(spec['allocation_reference_run'], spec.get('allocation_reference_case_id', settings['id']), revision)
    browser = run_manifest(spec.get('browser_reference_run', settings['baseline']), 'worklet-live-song', revision)
    baselines = [geometry, allocation, browser]
    if any(manifest['status'] != 'pass' for _, manifest in baselines):
        parser.error('変更前の比較がすべて合格している必要があります')
    snapshots = {source.stem: verified_path(geometry, f'artifacts/{source.stem}.csv') for source in cases}
    reference_counts = verified_path(allocation, 'artifacts/traced-counts.json')
    reference_pcm = verified_path(allocation, 'artifacts/traced.f32le')
    reference_observations = verified_path(allocation, 'artifacts/traced-observations.f64le')
    browser_summary = verified_path(browser, 'summary.json')
    browser_wave = verified_path(browser, 'artifacts/browser.wav')
    browser_observations = verified_path(browser, 'artifacts/browser.json')
    sources.extend([probe_path, *snapshots.values(), reference_counts, reference_pcm, reference_observations,
                    browser_summary, browser_wave, browser_observations, WORKSPACE / 'data/cmudict.txt.gz',
                    CASE.with_name(settings['native_fixture']), CASE.with_name(settings['song_fixture']),
                    WORKSPACE / 'tools/measure_song_render_allocation_phases.py',
                    *(root / 'manifest.json' for root, _ in baselines)])

    def measure(folder, execute):
        traces = render_geometry(folder, execute, cases)
        render_probe(folder, execute)
        checks, result = compare_allocation(folder, spec, settings, reference_counts)
        waveform_checks, observation_diff = compare_pcm_observations(
            folder, settings, read(browser_summary), browser_wave, read(browser_observations))
        checks.update(waveform_checks)
        shape = {name: sha256(file) == sha256(snapshots[name]) for name, file in traces.items()}
        checks['raw_and_limited_match_previous_cli'] = all(shape.values())
        checks['pcm_matches_unmodified_native'] = sha256(folder / 'traced.f32le') == sha256(reference_pcm)
        checks['observations_match_unmodified_native'] = (
            sha256(folder / 'traced-observations.f64le') == sha256(reference_observations))
        return result | {'checks': checks, 'geometry_byte_equal': shape, 'browser_observation_difference': observation_diff}

    return record_measurement(args.run_id, case_path, sources, details, measure, command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
