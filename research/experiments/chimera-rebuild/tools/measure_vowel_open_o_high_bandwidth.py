"""固定母音 /ɔ/ の高域ピークを、掃引上限と刻みを変えて照合する。"""

import argparse
import json
from pathlib import Path
import re
import subprocess

import numpy as np
from scipy.optimize import brentq, minimize_scalar

import measure_vowel_transfer as vowel
from measure_fan_crossing_allocations import run_manifest, verified_path
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/vowel-open-o-high-bandwidth.json'
ROOT = WORKSPACE.parents[2]
NETWORK_FILES = ('upstream-linear-nodes.csv', 'upstream-linear-branches.csv',
                 'upstream-vowel-settings.csv', 'upstream-pose.csv')


def baseline_inputs(study):
    spec = study['baseline']
    run, manifest = run_manifest(spec['run'], spec['case'], study['upstream_revision'])
    path = run / 'manifest.json'
    if manifest['status'] != 'pass' or sha256(path) != spec['manifest_sha256']:
        raise ValueError('元の固定姿勢の実行が登録した記録と一致しません')
    entry, = (item for item in manifest['inputs'] if item['path'] == f'cases/{spec["case"]}.json')
    definition = run / manifest['source_snapshot'] / entry['path']
    if sha256(definition) != entry['sha256']:
        raise ValueError('元の固定姿勢のケースを照合できません')
    outputs = {name: verified_path((run, manifest), f'artifacts/{name}')
               for name in (*NETWORK_FILES, 'trace.csv', 'upstream-trace.csv', 'settings.json')}
    outputs['summary'] = verified_path((run, manifest), 'summary.json')
    return definition, (path, *outputs.values()), outputs


def sweeps(grid):
    count = grid['original_intervals']
    extent = grid['extended_intervals']
    start, end = grid['start_hz'], grid['original_end_hz']
    extended_end = start * (end / start) ** (extent / count)
    return {label: {'start_hz': start, 'end_hz': upper, 'points': intervals * density + 1}
            for name, (upper, intervals) in (('original', (end, count)), ('extended', (extended_end, extent)))
            for label, density in ((name, 1), (name + '_dense', grid['refinement_factor']))}


def record_sweeps(study, base_case, out, execute):
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera', '--test', 'golden_analysis',
             'analysis_matches_typescript', '--', '--nocapture'],
            cwd=UPSTREAM, stdout=out / 'upstream-analysis-test.log')
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'vocal-core', '--test', 'uniform_tube'],
            stdout=out / 'research-uniform-tube-test.log')
    upper = vowel.shared.build_upstream_probe(vowel.PROBE, out, execute, extra_libraries=('serde_json',),
                                              cargo_args=('--offline',))
    cli = ['cargo', 'run', '--locked', '--offline', '--release', '-p', 'vocal-cli', '--']
    original = base_case['transfer']
    if sweeps(study['grid'])['original'] != original:
        raise ValueError('元の周波数範囲または点数が登録した基準と一致しません')
    cfg = base_case['measurement']['transfer']
    for name, grid in sweeps(study['grid']).items():
        directory = out / name
        directory.mkdir()
        definition = directory / 'input.json'
        definition.write_text(json.dumps(base_case | {'transfer': grid}, ensure_ascii=False, indent=2) + '\n')
        execute([*cli, 'inspect', str(definition)], stdout=directory / 'settings.json')
        execute([*cli, 'transfer', str(definition), str(directory / 'trace.csv')])
        args = [cfg['ipa'], base_case['fixed_airway']['sample_rate_hz'], grid['start_hz'], grid['end_hz'],
                grid['points'], cfg['peak_search_min_hz'], base_case['posture']['velum_cm2'], directory]
        execute([str(upper), *map(str, args)], cwd=UPSTREAM)


def source_elements(outputs):
    read = vowel.read_numeric_csv
    nodes = read(outputs['upstream-linear-nodes.csv'], ('node', *vowel.NODE_FIELDS))
    if not np.array_equal(nodes[:, 0], np.arange(len(nodes))):
        raise ValueError('基準の節点番号が連続していません')
    edges = read(outputs['upstream-linear-branches.csv'], vowel.BRANCH_FIELDS)
    (inject, left, right, lips, nose, _), = read(outputs['upstream-vowel-settings.csv'], vowel.SUMMARY_FIELDS)
    source = {'inject': int(inject), 'cut': (int(left), int(right)), 'lips': int(lips), 'nose': int(nose)}
    return nodes[:, 1:], edges, source


def read_trace(directory):
    return (vowel.read_numeric_csv(directory / 'trace.csv', vowel.CANDIDATE_FIELDS),
            vowel.read_numeric_csv(directory / 'upstream-trace.csv', vowel.UPSTREAM_FIELDS))


def threshold_crossings(frequencies, db, center, level):
    left = np.flatnonzero(db[:center] <= level)
    right = np.flatnonzero(db[center+1:] <= level) + center + 1
    brackets = (None if not left.size else (int(left[-1]), int(left[-1]+1)),
                None if not right.size else (int(right[0]-1), int(right[0])))
    roots = []
    for bracket in brackets:
        if bracket is None:
            roots.append(None)
        else:
            a, b = bracket
            weight = (level - db[a]) / (db[b] - db[a])
            roots.append(float(frequencies[a] + weight * (frequencies[b] - frequencies[a])))
    return roots, [None if bracket is None else frequencies[list(bracket)].tolist() for bracket in brackets]


def target_peaks(frequencies, magnitudes, cfg, registration):
    db = 20 * np.log10(magnitudes + 1e-30)
    centers = np.flatnonzero((frequencies[1:-1] >= cfg['peak_search_min_hz'])
                             & (db[1:-1] > db[:-2]) & (db[1:-1] >= db[2:])) + 1
    rows = vowel.peak_rows(frequencies, magnitudes, cfg['peak_search_min_hz'])
    targets = {}
    for name, (low, high) in registration['target_peak_windows_hz'].items():
        hits = np.flatnonzero((rows[:, 0] >= low) & (rows[:, 0] <= high))
        if len(hits) != 1:
            raise ValueError(f'登録したピークの対応が一意になりません ({name}, {hits.tolist()})')
        (frequency, width, level), = rows[hits]
        center, = centers[hits]
        threshold = float(level) - registration['peak_drop_db']
        roots, brackets = threshold_crossings(frequencies, db, center, threshold)
        targets[name] = {'frequency_hz': float(frequency), 'level_db': float(level), 'threshold_db': threshold,
                         'left_hz': roots[0], 'right_hz': roots[1], 'bandwidth_hz': float(width) if np.isfinite(width) else None,
                         'crossing_brackets_hz': brackets,
                         'peak_grid_bracket_hz': frequencies[center-1:center+2:2].tolist()}
    return targets, rows


def continuous_peaks(frequencies, dense_db, targets, elements, drop):
    def level(frequency):
        response = vowel.independent_response(np.array([frequency]), *elements)
        return float(20 * np.log10(abs(response[0, 3]) + 1e-30))

    continuous = {}
    for name, row in targets.items():
        peak = minimize_scalar(lambda f: -level(f), bounds=row['peak_grid_bracket_hz'], method='bounded',
                               options={'xatol': 1e-8})
        if not peak.success:
            raise ValueError(f'連続周波数のピークを求められません ({name})')
        peak_hz, peak_db = float(peak.x), -float(peak.fun)
        threshold = peak_db - drop
        index = int(np.argmin(abs(frequencies - peak_hz)))
        _, brackets = threshold_crossings(frequencies, dense_db, index, threshold)
        roots = [None if pair is None else brentq(lambda f: level(f) - threshold, *pair) for pair in brackets]
        left, right = roots
        continuous[name] = {'frequency_hz': peak_hz, 'level_db': peak_db, 'threshold_db': threshold,
                            'left_hz': left, 'right_hz': right,
                            'bandwidth_hz': right - left if left is not None and right is not None else None,
                            'root_residual_db': [None if f is None else abs(level(f) - threshold) for f in roots]}
    lo, hi = (continuous[name]['frequency_hz'] for name in ('lower', 'upper'))
    between = np.flatnonzero((frequencies > lo) & (frequencies < hi))
    at = between[np.argmin(dense_db[between])]
    valley = minimize_scalar(level, bounds=(frequencies[at-1], frequencies[at+1]), method='bounded',
                             options={'xatol': 1e-8})
    if not valley.success:
        raise ValueError('ピーク間の谷を求められません')
    return continuous, {'frequency_hz': float(valley.x), 'level_db': float(valley.fun)}


def diagnose_sweep(directory, expected_count, cfg, registration, elements, archived_settings):
    candidate, upstream = read_trace(directory)
    frequencies = candidate[:, 0]
    count = registration['samples_per_matrix_batch']
    independent = np.vstack([vowel.independent_response(frequencies[i:i+count], *elements)
                             for i in range(0, len(frequencies), count)])
    components = np.column_stack([candidate[:, i] + 1j*candidate[:, i+1] for i in (5, 7, 9, 1)])
    response_errors = vowel.relative_errors(components, independent).max(axis=0)
    magnitude_error = float(abs(candidate[:, 3] - upstream[:, 1]).max() / upstream[:, 1].max())
    pressure_error = float(abs(candidate[:, 4] - upstream[:, 2]).max())
    targets, rows = target_peaks(frequencies, candidate[:, 3], cfg, registration)
    upper_rows = vowel.read_numeric_csv(directory / 'upstream-peaks.csv', vowel.PEAK_FIELDS, optional_bandwidth=True)
    same_peak_shape = rows.shape == upper_rows.shape
    same_peak_mask = same_peak_shape and np.array_equal(np.isnan(rows), np.isnan(upper_rows))
    peak_errors = np.nan_to_num(abs(rows - upper_rows)).max(axis=0) if same_peak_mask else None
    limits = np.array([cfg['peak_frequency_and_bandwidth_error_lt_hz']] * 2 + [cfg['peak_level_error_lt_db']])
    settings = json.loads((directory / 'settings.json').read_text())
    checks = {
        'grid': len(frequencies) == expected_count == len(upstream) and bool((np.diff(frequencies) > 0).all())
        and abs(frequencies - upstream[:, 0]).max() < cfg['frequency_grid_error_lt_hz'],
        'geometry': all(settings[k] == archived_settings[k] for k in ('coordinates', 'fixed_airway', 'transfer')),
        'response': magnitude_error < cfg['response_peak_relative_error_lt']
        and pressure_error < cfg['pressure_level_error_lt_db'],
        'independent': bool((response_errors < cfg['response_peak_relative_error_lt']).all()),
        'peaks': peak_errors is not None and bool((peak_errors < limits).all()),
    }
    report = {'frequency_count': len(frequencies), 'range_hz': [float(frequencies[0]), float(frequencies[-1])],
              'targets': targets, 'peak_count': len(rows), 'missing_indices': np.flatnonzero(np.isnan(rows[:, 1])).tolist(),
              'upstream_peak_relative_magnitude_error': magnitude_error, 'upstream_max_pressure_error_db': pressure_error,
              'independent_peak_relative_errors': dict(zip(vowel.COMPONENTS, response_errors.tolist(), strict=True))}
    return checks, report, candidate, independent


def analyze(study, base_case, out, archived):
    registration = study['measurement']
    cfg = base_case['measurement']['transfer']
    elements = source_elements(archived)
    checks, grids, sampled = {}, {}, {}
    archived_settings = json.loads(archived['settings.json'].read_text())
    for name, grid in sweeps(study['grid']).items():
        directory = out / name
        fixed = all((directory / f).read_bytes() == archived[f].read_bytes() for f in NETWORK_FILES)
        gates, grids[name], trace, independent = diagnose_sweep(
            directory, grid['points'], cfg, registration, elements, archived_settings)
        checks.update({f'{name}/{key}': bool(value) for key, value in (gates | {'upstream_network': fixed}).items()})
        sampled[name] = trace
        if name == 'extended_dense':
            roots, valley = continuous_peaks(trace[:, 0], 20 * np.log10(abs(independent[:, 3]) + 1e-30),
                                             grids[name]['targets'], elements, registration['peak_drop_db'])
    original = sampled['original']
    prior = vowel.read_numeric_csv(archived['trace.csv'], vowel.CANDIDATE_FIELDS)
    reference = json.loads(archived['summary'].read_text())['peaks']
    ext = sampled['extended'][:len(original)]
    common_grid = float(abs(ext[:, 0] - original[:, 0]).max())
    common_flow = float(abs(ext[:, 3] - original[:, 3]).max() / original[:, 3].max())
    old_flow = float(abs(prior[:, 3] - original[:, 3]).max() / prior[:, 3].max())
    checks['historical_grid_and_missing_reproduced'] = (
        original.shape == prior.shape and abs(prior[:, 0] - original[:, 0]).max() < cfg['frequency_grid_error_lt_hz']
        and old_flow < registration['overlap_peak_relative_error_lt']
        and grids['original']['missing_indices'] == reference['missing_bandwidth_indices'] == cfg['missing_bandwidth_indices'])
    errors = {}
    for grid in ('extended', 'extended_dense'):
        errors[grid] = {name: {
            key: abs(row[key] - grids[grid]['targets'][name][key])
            if row[key] is not None and grids[grid]['targets'][name][key] is not None else None
            for key in ('left_hz', 'right_hz')} for name, row in roots.items()}
    baseline_edge = study['grid']['original_end_hz']
    lower, upper = (roots[key] for key in ('lower', 'upper'))
    area = [error for sweep in errors['extended_dense'].values() for error in sweep.values() if error is not None]
    residual = [d for row in roots.values() for d in row['root_residual_db'] if d is not None]
    checks['continuous_roots_and_dense_interpolation'] = (
        len(area) == len(residual) and all(x < registration['tolerance_to_continuous_hz'] for x in area)
        and all(x < registration['maximum_continuous_root_residual_db'] for x in residual))
    hypotheses = {
        'refining_original_grid_keeps_both_right_crossings_missing':
            all(row['right_hz'] is None for row in grids['original_dense']['targets'].values()),
        'extending_keeps_the_old_samples': common_grid < cfg['frequency_grid_error_lt_hz']
        and common_flow < registration['overlap_peak_relative_error_lt'],
        'extending_recovers_both_widths': all(row['bandwidth_hz'] is not None
                                            for row in grids['extended']['targets'].values()),
        'lower_peak_shares_its_band_with_upper': valley['level_db'] > lower['threshold_db']
        and lower['right_hz'] is not None and lower['right_hz'] > upper['frequency_hz'],
        'upper_peak_has_local_width': upper['left_hz'] is not None and upper['right_hz'] is not None
        and lower['frequency_hz'] < upper['left_hz'] and upper['right_hz'] > baseline_edge,
        'refining_extended_grid_approaches_continuous_roots': all(
            coarse is not None and fine is not None and fine < coarse
            for name in roots for key in ('left_hz', 'right_hz')
            for coarse, fine in [(errors['extended'][name][key], errors['extended_dense'][name][key])]),
    }
    return {'checks': {key: bool(value) for key, value in checks.items()},
            'hypotheses': {key: bool(value) for key, value in hypotheses.items()},
            'grids': grids, 'continuous': roots, 'interpeak_valley': valley, 'crossing_errors_hz': errors,
            'original_overlap': {'grid_error_hz': common_grid, 'relative_flow_error': common_flow,
                                 'archived_relative_flow_error': old_flow}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', args.run_id):
        parser.error('実行IDを英数字、ハイフン、アンダースコアで指定してください')
    study = json.loads(CASE.read_text())
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != study['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    definition, references, archived = baseline_inputs(study)
    base_case = json.loads(definition.read_text())

    def measure(out, execute):
        record_sweeps(study, base_case, out, execute)
        return analyze(study, base_case, out, archived)

    inputs = [CASE, definition, *references, Path(__file__), Path(vowel.__file__), Path(vowel.shared.__file__),
              vowel.PROBE, vowel.TABLE, UPSTREAM / 'crates/chimera/src/airway/frequency.rs',
              UPSTREAM / 'crates/chimera/src/airway/network.rs', UPSTREAM / 'crates/chimera-cli/src/calibrate.rs',
              UPSTREAM / 'crates/chimera/tests/golden_analysis.rs', *vowel.shared.candidate_sources()]
    details = {'case_id': study['id'], 'case_revision': study['revision'], 'upstream_revision': revision}
    return vowel.shared.record_measurement(args.run_id, CASE, inputs, details, measure, command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
