"""固定母音の線形要素、口端・鼻端・壁面の応答、ピークを照合する。"""

import argparse
import csv
import json
from pathlib import Path
import re
import subprocess

import numpy as np

import measure_sagittal as sagittal
import measure_uniform_tube as shared
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


PROBE = WORKSPACE / 'tools/upstream_vowel_probe.rs'
TABLE = UPSTREAM / 'crates/chimera/src/phonetics/vowelTargets.generated.json'
CASES = tuple(p.stem for p in sorted((WORKSPACE / 'cases').glob('vowel-transfer-*.json')))
NODE_FIELDS = ('compliance', 'fixed_pressure', 'wall_area_cm2', 'wall_mass', 'wall_resistance',
               'wall_stiffness', 'wall_radiation_fraction', 'radiation_inertance', 'radiation_resistance')
BRANCH_FIELDS = ('left', 'right', 'open', 'inertance', 'resistance')
SUMMARY_FIELDS = ('inject', 'cut_left', 'cut_right', 'lips', 'nose', 'minimum_cm2')
POSE_FIELDS = ('jaw_cm', 'tb_x_cm', 'tb_y_cm', 'tt_x_cm', 'tt_y_cm', 'tongue_root_cm', 'tip_curl', 'dorsum',
               'lip_aperture_cm', 'lip_protrusion_cm', 'lip_spread', 'labiodental', 'velum_cm2', 'larynx_cm')
UPSTREAM_FIELDS = ('frequency_hz', 'flow_magnitude', 'pressure_db')
CANDIDATE_FIELDS = ('frequency_hz', 'total_real', 'total_imaginary', 'flow_magnitude', 'pressure_db',
                    'lips_real', 'lips_imaginary', 'nose_real', 'nose_imaginary', 'wall_real', 'wall_imaginary')
PEAK_FIELDS = ('frequency_hz', 'bandwidth_hz', 'flow_level_db')
COMPONENTS = ('lips', 'nose', 'wall', 'total')


def capture_upstream(case, artifacts, execute):
    execute(['cargo', 'test', '--locked', '-p', 'chimera', '--test', 'golden_analysis',
             'analysis_matches_typescript', '--', '--nocapture'],
            cwd=UPSTREAM, stdout=artifacts / 'upstream-analysis-test.log')
    probe = shared.build_upstream_probe(PROBE, artifacts, execute, extra_libraries=('serde_json',))
    cfg = case['measurement']['transfer']
    sweep = case['transfer']
    args = [cfg['ipa'], case['fixed_airway']['sample_rate_hz'], sweep['start_hz'], sweep['end_hz'],
            sweep['points'], cfg['peak_search_min_hz'], case['posture']['velum_cm2'], artifacts]
    execute([str(probe), *map(str, args)], cwd=UPSTREAM)


def read_numeric_csv(path, header, *, optional_bandwidth=False):
    with path.open(newline='') as stream:
        reader = csv.reader(stream)
        if tuple(next(reader, [])) != header:
            raise ValueError(f'{path.name} のヘッダーが不正です')
        data = np.array([[float(value) if value else np.nan for value in row] for row in reader], dtype=float)
    if data.ndim != 2 or data.shape[1] != len(header):
        raise ValueError(f'{path.name} の列数が不正です')
    required = data[:, [0, 2]] if optional_bandwidth else data
    if not np.isfinite(required).all() or np.isinf(data).any():
        raise ValueError(f'{path.name} の数値が不正です')
    return data


def ordered_branches(branches):
    return branches[np.lexsort((branches[:, 1], branches[:, 0]))]


def relative_errors(candidate, upper):
    scale = abs(upper).max(axis=0)
    return abs(candidate - upper) / np.where(scale > 0.0, scale, 1.0)


def independent_response(freqs, nodes, branches, source):
    # 枝間の接続を消去せず、節点の流量収支を全節点の複素連立方程式として解く。
    compliance, fixed, area, mass, resistance, stiffness, fraction, rad_l, rad_r = nodes.T
    omega = (2j * np.pi * freqs)[:, None]
    wall = np.zeros((len(freqs), len(nodes)), dtype=complex)
    active_wall = area > 0
    wall[:, active_wall] = area[active_wall] / (resistance[active_wall]
                                               + omega * mass[active_wall] + stiffness[active_wall] / omega)
    end = np.zeros_like(wall)
    active_end = rad_l > 0
    end[:, active_end] = 1 / rad_r[active_end] + 1 / (omega * rad_l[active_end])
    parts = omega * compliance + wall + end + 1e30 * fixed
    n = len(nodes)
    matrix = np.zeros((len(freqs), n, n), dtype=complex)
    diagonal = np.arange(n)
    matrix[:, diagonal, diagonal] = parts
    for a, b, open_, inertance, resistance in branches:
        left, right = int(a), int(b)
        if open_ and (left, right) != source['cut']:
            y = (1 / (resistance + omega * inertance))[:, 0]
            matrix[:, left, left] += y
            matrix[:, right, right] += y
            matrix[:, left, right] -= y
            matrix[:, right, left] -= y
    rhs = np.zeros((len(freqs), n, 1), dtype=complex)
    rhs[:, source['inject'], 0] = 1
    pressure = np.linalg.solve(matrix, rhs)[..., 0]
    ends = end * pressure
    wall_radiation = (wall * pressure) @ fraction
    lips, nose = (ends[:, source[key]] for key in ('lips', 'nose'))
    return np.column_stack((lips, nose, wall_radiation, lips + nose + wall_radiation))


def peak_rows(frequency, magnitude, minimum_frequency):
    db = 20 * np.log10(magnitude + 1e-30)
    centers = np.flatnonzero((frequency[1:-1] >= minimum_frequency)
                             & (db[1:-1] > db[:-2]) & (db[1:-1] >= db[2:])) + 1
    peaks = []
    for i in centers:
        a, b, c = db[i-1:i+2]
        denominator = a - 2*b + c
        offset = (a-c) / (2*denominator) if abs(denominator) > 1e-12 else 0.0
        f = frequency[i] + offset * (frequency[i+1] - frequency[i])
        level = b - 0.25 * (a-c) * offset
        level_3db = level - 3.0
        lower = np.flatnonzero(db[:i+1] <= level_3db)
        upper = np.flatnonzero(db[i:] <= level_3db) + i
        width = np.nan
        if lower.size and upper.size:
            lo, hi = lower[-1], upper[0]
            if lo < i < hi:
                f0 = np.interp(level_3db, db[lo:lo+2], frequency[lo:lo+2])
                f1 = np.interp(level_3db, db[hi-1:hi+1][::-1], frequency[hi-1:hi+1][::-1])
                width = f1 - f0
        peaks.append((f, width, level))
    return np.asarray(peaks, dtype=float).reshape(-1, 3)


def check_peaks(case, artifacts, frequency, magnitude, lips):
    cfg = case['measurement']['transfer']
    a = peak_rows(frequency, magnitude, cfg['peak_search_min_hz'])
    upper = read_numeric_csv(artifacts / 'upstream-peaks.csv', PEAK_FIELDS, optional_bandwidth=True)
    lips_peaks = peak_rows(frequency, abs(lips), cfg['peak_search_min_hz'])
    for name, values in (('peaks.csv', a), ('lips-peaks.csv', lips_peaks)):
        with (artifacts / name).open('w', newline='') as stream:
            writer = csv.writer(stream, lineterminator='\n')
            writer.writerow(PEAK_FIELDS)
            writer.writerows((f, bw if np.isfinite(bw) else '', db) for f, bw, db in values)
    missing = np.flatnonzero(np.isnan(a[:, 1])).tolist()
    checks = {'registered_peak_count_and_missing_bandwidth':
              len(a) == cfg['peak_count'] and missing == cfg['missing_bandwidth_indices'],
              'registered_first_peaks': len(a) >= 3 and all(
                  lo <= f <= hi for f, (lo, hi) in zip(a[:3, 0], cfg['initial_peak_intervals_hz'], strict=True))}
    diagnostics = {'peak_count': len(a), 'missing_bandwidth_indices': missing,
                   'peaks_hz': a[:, 0].tolist(), 'lips_peaks_hz': lips_peaks[:, 0].tolist(),
                   'bandwidths_hz': [float(bw) if np.isfinite(bw) else None for bw in a[:, 1]]}
    match_count = a.shape == upper.shape
    match_missing = match_count and np.array_equal(np.isnan(a[:, 1]), np.isnan(upper[:, 1]))
    checks['upstream_peak_count_and_missing_bandwidth'] = match_missing
    if match_missing:
        error = np.where(np.isnan(upper), 0, abs(a - upper))
        maxima = error.max(axis=0)
        limits = np.array([cfg['peak_frequency_and_bandwidth_error_lt_hz']]*2 + [cfg['peak_level_error_lt_db']])
        checks['upstream_peak_parameters'] = bool((maxima < limits).all())
        diagnostics['upstream_max_peak_errors'] = dict(zip(PEAK_FIELDS, maxima.tolist(), strict=True))
    return checks, diagnostics


def measure(case, artifacts, execute):
    capture_upstream(case, artifacts, execute)
    cfg = case['measurement']['transfer']
    setting = json.loads((artifacts / 'settings.json').read_text())
    transfer = setting['transfer']
    upper_nodes = read_numeric_csv(artifacts / 'upstream-linear-nodes.csv', ('node', *NODE_FIELDS))
    upper_edges = read_numeric_csv(artifacts / 'upstream-linear-branches.csv', BRANCH_FIELDS)
    upper_info, = read_numeric_csv(artifacts / 'upstream-vowel-settings.csv', SUMMARY_FIELDS)
    upper_pose, = read_numeric_csv(artifacts / 'upstream-pose.csv', POSE_FIELDS)
    upper_inject, cut_left, cut_right, upper_lips, upper_nose, upper_minimum = upper_info
    nodes = np.array([[node[key] for key in NODE_FIELDS] for node in transfer['nodes']], dtype=float)
    edges = np.array([[*edge['nodes'], edge['open'], edge['inertance'], edge['resistance']]
                      for edge in transfer['branches']], dtype=float)
    source = {key: int(transfer[key]) for key in ('inject', 'lips', 'nose')}
    cut, = transfer['cut']
    source['cut'] = tuple(map(int, edges[cut, :2]))
    expected_source = {'inject': int(upper_inject), 'cut': (int(cut_left), int(cut_right)),
                       'lips': int(upper_lips), 'nose': int(upper_nose)}
    edges, upper_edges = map(ordered_branches, (edges, upper_edges))
    if (nodes.shape != upper_nodes[:, 1:].shape or edges.shape != upper_edges.shape
            or not np.isfinite(nodes).all() or not np.isfinite(edges).all()):
        raise ValueError('候補と上流の節点・枝の数が異なるか、不正な値があります')
    node_errors = relative_errors(nodes, upper_nodes[:, 1:])
    branch_errors = relative_errors(edges[:, 3:], upper_edges[:, 3:])
    tolerance = cfg['element_peak_relative_error_lt']
    element_failures = np.flatnonzero((node_errors >= tolerance).any(axis=1))
    branch_failures = np.flatnonzero((branch_errors >= tolerance).any(axis=1) | (edges[:, :3] != upper_edges[:, :3]).any(axis=1))
    pose_error = float(abs(np.array(sagittal.pose_controls(case), dtype=float) - upper_pose).max())
    fixed = setting['fixed_airway']
    pharynx, oral = (next(t for t in fixed['tubes'] if t['name'] == name) for name in ('pharynx', 'oral'))
    supraglottal = fixed['sections'][pharynx['first_node']:oral['first_node']+oral['cells']]
    minimum = min(section['minimum_area_cm2'] for section in supraglottal)
    lo, hi = cfg['minimum_area_interval_cm2']
    target = json.loads(TABLE.read_text())['male'][cfg['ipa']]

    actual = read_numeric_csv(artifacts / 'trace.csv', CANDIDATE_FIELDS)
    reference = read_numeric_csv(artifacts / 'upstream-trace.csv', UPSTREAM_FIELDS)
    if len(actual) != len(reference) or len(actual) != case['transfer']['points']:
        raise ValueError('上流・候補の周波数点数が指定と一致しません')
    freq = actual[:, 0]
    freq_error = float(abs(freq - reference[:, 0]).max())
    magnitude_error = abs(actual[:, 3] - reference[:, 1]) / reference[:, 1].max()
    db_error = abs(actual[:, 4] - reference[:, 2])
    response_limit = cfg['response_peak_relative_error_lt']
    rejected = np.flatnonzero((magnitude_error >= response_limit) | (db_error >= cfg['pressure_level_error_lt_db']))
    components = np.column_stack([actual[:, i] + 1j*actual[:, i+1] for i in (5, 7, 9, 1)])
    estimated = independent_response(freq, upper_nodes[:, 1:], upper_edges, expected_source)
    component_errors = relative_errors(components, estimated)
    np.savetxt(artifacts / 'independent-response.csv',
               np.column_stack([freq, *[part for column in estimated.T for part in (column.real, column.imag)]]),
               delimiter=',', comments='',
               header='frequency_hz,' + ','.join(f'{name}_{part}' for name in COMPONENTS for part in ('real', 'imaginary')))
    lips, nose, wall, total = components.T
    nose_over_lips = float(abs(nose).max() / abs(lips).max())
    ref_db = 20 * np.log10(2*np.pi*freq*abs(total) + 1e-30)
    checks = {
        'upstream_frozen_pose': pose_error < cfg['coordinate_error_lt_cm'],
        'upstream_calibration_table': target['formants'] == cfg['table_formants_hz']
                                      and target['target'] == cfg['target_formants_hz'],
        'upstream_injection_and_cut': source == expected_source,
        'upstream_linear_nodes': np.array_equal(upper_nodes[:, 0], np.arange(len(nodes))) and not element_failures.size,
        'upstream_linear_branches': not branch_failures.size,
        'registered_minimum_section': lo <= minimum <= hi and abs(minimum-upper_minimum) < tolerance,
        'frequency_grid': freq_error < cfg['frequency_grid_error_lt_hz'] and (np.diff(freq) > 0).all(),
        'upstream_flow_and_pressure': not rejected.size,
        'independent_complex_response': bool((component_errors < response_limit).all()),
        'components_sum_as_complex_flow': bool(abs(total-lips-nose-wall).max() < response_limit*abs(total).max()),
        'pressure_display_matches_flow_derivative': bool(abs(ref_db-actual[:, 4]).max() < cfg['pressure_level_error_lt_db']),
        'nose_flow_matches_velum': nose_over_lips > cfg['nose_to_lips_peak_gt_when_open']
                                   if case['posture']['velum_cm2'] > 0 else nose_over_lips == 0.0,
    }
    peak_checks, peaks = check_peaks(case, artifacts, freq, actual[:, 3], lips)
    checks.update(peak_checks)
    peaks['table_formants_hz'] = cfg['table_formants_hz']
    peaks['target_formants_hz'] = cfg['target_formants_hz']
    return {
        'checks': {name: bool(passed) for name, passed in checks.items()},
        'minimum_cm2': minimum, 'pose_max_error': pose_error, 'grid_max_error_hz': freq_error,
        'linear_node_max_relative_errors': dict(zip(NODE_FIELDS, node_errors.max(axis=0).tolist(), strict=True)),
        'linear_branch_max_relative_errors': dict(zip(BRANCH_FIELDS[3:], branch_errors.max(axis=0).tolist(), strict=True)),
        'first_bad_node': int(element_failures[0]) if element_failures.size else None,
        'first_bad_branch_nodes': edges[branch_failures[0], :2].astype(int).tolist() if branch_failures.size else None,
        'upstream_peak_relative_flow_error': float(magnitude_error.max()),
        'upstream_max_pressure_error_db': float(db_error.max()),
        'first_bad_frequency_hz': float(freq[rejected[0]]) if rejected.size else None,
        'independent_peak_relative_complex_errors': dict(zip(COMPONENTS, component_errors.max(axis=0).tolist(), strict=True)),
        'nose_to_lips_peak': nose_over_lips, 'peaks': peaks,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('case', choices=CASES)
    args = parser.parse_args()
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]*', args.run_id):
        parser.error('実行IDは英数字で始め、英数字、ハイフン、アンダースコアで指定してください')
    path = WORKSPACE / 'cases' / f'{args.case}.json'
    case = json.loads(path.read_text())
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'],
                                                                        cwd=UPSTREAM, text=True):
        raise ValueError('変更のない固定上流版が必要です')

    def measure_run(artifacts, execute):
        return measure(case, artifacts, execute)

    sources = [path, PROBE, Path(__file__).resolve(), Path(sagittal.__file__), Path(shared.__file__),
               WORKSPACE / 'tools/upstream_baseline.py', *shared.candidate_sources()]
    details = {'upstream_revision': revision, 'case_id': case['id'], 'upstream_vowel_table_sha256': sha256(TABLE)}
    return shared.record_measurement(args.run_id, path, sources, details, measure_run, command='transfer')


if __name__ == '__main__':
    raise SystemExit(main())
