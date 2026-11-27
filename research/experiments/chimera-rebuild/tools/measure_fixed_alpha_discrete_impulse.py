"""固定 /ɑ/ の小信号インパルスを上流・研究版・離散節点方程式で照合する。"""

import argparse
import json
from pathlib import Path
import re
import subprocess
from tempfile import TemporaryDirectory

import numpy as np

import measure_fixed_airway as fixed
import measure_fixed_lf_harmonic_transfer as harmonic
import measure_sagittal as sagittal
import measure_uniform_tube as shared
import measure_vowel_transfer as vowel
from measure_fan_crossing_allocations import run_manifest, verified_path
from measure_vowel_open_o_high_bandwidth import source_elements
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/fixed-alpha-discrete-impulse.json'
FIELDS = ('pressure_pharynx_entry', 'pressure_junction', 'pressure_lips', 'pressure_nose', 'pressure_sinus',
          'flow_oral_link', 'flow_velum', 'flow_sinus_neck', 'flow_lips', 'flow_nose', 'flow_walls',
          'radiation_derivative')
ARMS = ('small', 'large')
EVIDENCE = ('impulse-traces.npz', 'settings.json', 'upstream-geometry.csv',
            *(f'{arm}-case.json' for arm in ARMS))


def archive_inputs(study):
    spec = study['reference']
    run, manifest = reference = run_manifest(spec['run'], spec['case'], study['upstream_revision'])
    header = run / 'manifest.json'
    if manifest['status'] != 'pass' or sha256(header) != spec['manifest_sha256']:
        raise ValueError('保存した複素伝達のマニフェストまたは判定が一致しません')
    paths = {'manifest.json': header, 'summary.json': verified_path(reference, 'summary.json'),
             **{name: verified_path(reference, f'artifacts/{name}')
                for name in ('linear-case.json', *harmonic.NETWORK_FILES)}}
    if short := study.get('short_window_reference'):
        run, manifest = previous = run_manifest(short['run'], short['case'], study['upstream_revision'])
        header = run / 'manifest.json'
        if manifest['status'] != 'fail' or sha256(header) != short['manifest_sha256']:
            raise ValueError('短い窓の保存判定またはマニフェストが一致しません')
        paths.update({'short_manifest.json': header, 'short_summary.json': verified_path(previous, 'summary.json'),
                      'short_traces.npz': verified_path(previous, 'artifacts/impulse-traces.npz')})
    return paths


def render_case(study, archive, arm):
    case = harmonic.read(archive['linear-case.json'])
    case.pop('transfer')
    case['id'] = f'{study["id"]}-{arm}'
    case['hypothesis'] = study['hypothesis']
    cfg = study['measurement']
    case['fixed_airway'] = {'sample_rate_hz': cfg['internal_rate_hz'], 'sample_count': cfg['sample_count'],
                           'impulse_volume_cm3': cfg['impulse_volume_cm3'][arm]}
    return case


def capture(study, archive, out, execute):
    cfg = study['measurement']
    for arm in ARMS:
        case = render_case(study, archive, arm)
        (out / f'{arm}-case.json').write_text(json.dumps(case, ensure_ascii=False, indent=2) + '\n')
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera', '--test', 'airway',
             'fdtd_impulse_response_agrees_with_frequency_domain_model'], cwd=UPSTREAM,
            stdout=out / 'upstream-time-frequency-test.log')
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera', '--test', 'airway_adversarial',
             'nearly_closed_three_way_junction_stays_stable_at_the_working_cfl'], cwd=UPSTREAM,
            stdout=out / 'upstream-junction-test.log')
    probe = shared.build_upstream_probe(sagittal.PROBE, out, execute, cargo_args=('--offline',))
    cli = ['cargo', 'run', '--locked', '--offline', '--release', '-p', 'vocal-cli', '--']
    fs, count = str(cfg['internal_rate_hz']), cfg['sample_count']
    pose = sagittal.pose_controls(harmonic.read(archive['linear-case.json']))
    execute([str(probe), '--fixed-airway', fs, '0', '0', *pose], cwd=UPSTREAM,
            stdout=out / 'upstream-geometry.csv')
    execute([*cli, 'inspect', str(out / 'small-case.json')], stdout=out / 'settings.json')
    traces = {}
    with TemporaryDirectory(prefix='impulse-csv-', dir=out) as directory:
        temporary = Path(directory)
        for arm in ARMS:
            candidate, upper = (temporary / f'{arm}-{name}.csv' for name in ('candidate', 'upstream'))
            volume = cfg['impulse_volume_cm3'][arm]
            execute([*cli, 'render', str(out / f'{arm}-case.json'), str(candidate)])
            execute([str(probe), '--fixed-airway', fs, str(count), str(volume), *pose], cwd=UPSTREAM, stdout=upper)
            traces[f'{arm}_candidate'] = fixed.read_trace(candidate, FIELDS, count)
            traces[f'{arm}_upstream'] = fixed.read_trace(upper, FIELDS, count)
    np.savez_compressed(out / 'impulse-traces.npz', **traces)


def compliance_floor(nodes, branches, source, rate):
    endpoints = branches[:, :2].astype(int)
    degree = np.bincount(endpoints.ravel(), minlength=len(nodes))
    active = branches[:, 2].astype(bool) & (endpoints != source['cut']).any(axis=1)
    incident = endpoints[active]
    inverse_inertance = 1 / branches[active, 3]
    inverse_sum = np.bincount(incident.ravel(), weights=np.repeat(inverse_inertance, 2), minlength=len(nodes))
    floor = np.where(degree >= 3, inverse_sum / (2.4 * rate**2), 0.0)
    return np.maximum(floor, nodes[:, 0]), active


def lip_distance(branches, source, active):
    edges = branches[active, :2].astype(int)
    edges = np.vstack((edges, edges[:, ::-1]))
    frontier = {source['inject']}
    seen = set(frontier)
    distance = 0
    while frontier and source['lips'] not in frontier:
        frontier = {int(right) for left, right in edges if left in frontier} - seen
        seen.update(frontier)
        distance += 1
    return distance if frontier else None


def discrete_elements(frequency, rate, nodes, links, compliance):
    """更新後の圧力を未知量として、流量収支の係数と枝のインピーダンスを返す。"""
    _, fixed_pressure, area, mass, resistance, stiffness, _, rad_l, rad_r = nodes.T
    left, right = links[:, :2].astype(int).T
    inertance, drag = links[:, 3:5].T
    wall_nodes, openings = area > 0, rad_l > 0
    delay = np.exp(-2j * np.pi * frequency / rate)
    difference = rate * (1 - delay)
    midpoint = (1 + delay) / 2
    impedance = drag + inertance * difference
    branch = delay / impedance
    wall = np.zeros(len(nodes), dtype=complex)
    r = resistance[wall_nodes] / 2
    m = mass[wall_nodes] * rate
    k = stiffness[wall_nodes]
    wall[wall_nodes] = area[wall_nodes] * delay / (m + r - (m - r) * delay + k * delay / difference)
    opening = np.zeros_like(wall)
    opening[openings] = midpoint * (1 / rad_r[openings] + midpoint / (rad_l[openings] * difference))
    matrix = np.diag(compliance * difference + wall + opening)
    np.add.at(matrix, (left, left), branch)
    np.add.at(matrix, (right, right), branch)
    np.add.at(matrix, (left, right), -branch)
    np.add.at(matrix, (right, left), -branch)
    matrix[fixed_pressure.astype(bool), :] = 0
    matrix[fixed_pressure.astype(bool), fixed_pressure.astype(bool)] = 1
    return matrix, impedance, wall, opening


def discrete_response(frequencies, rate, nodes, branches, source, compliance, active):
    """圧力を標本更新後に揃えた複素流量収支を直接解く。"""
    fraction = nodes[:, 6]
    links = branches[active]
    drive = np.zeros(len(nodes))
    drive[source['inject']] = 1.0
    output = []
    for frequency in frequencies:
        matrix, _, wall, opening = discrete_elements(frequency, rate, nodes, links, compliance)
        pressure = np.linalg.solve(matrix, drive)
        lip = source['lips']
        output.append((pressure[source['inject']], pressure[lip], pressure[lip] * opening[lip],
                       np.dot(pressure * wall, fraction)))
    return np.asarray(output)


def geometry_checks(study, archive, out, nodes, branches, source, checks):
    settings = harmonic.read(out / 'settings.json')
    case = render_case(study, archive, 'small')
    checks['same_fixed_posture_rate_and_amplitudes'] = (
        all(harmonic.read(out / f'{arm}-case.json') == render_case(study, archive, arm) for arm in ARMS)
        and settings['case'] == case
        and case['fixed_airway']['sample_rate_hz'] == harmonic.read(archive['linear-case.json'])['fixed_airway']['sample_rate_hz']
        and case['posture']['velum_cm2'] < 0
        and study['measurement']['impulse_volume_cm3']['large'] == 100 * study['measurement']['impulse_volume_cm3']['small'])
    rows, upper = fixed.read_upper_geometry(out / 'upstream-geometry.csv')
    airway = settings['fixed_airway']
    candidate = np.array([[row[name] for name in fixed.FIELDS[2:]] for row in airway['sections']])
    tol = study['measurement']['geometry_abs_error_lt']
    checks['geometry_matches_upstream_and_archived_linear_elements'] = (
        candidate.shape == upper[:, 2:].shape and len(rows) == len(nodes) == airway['node_count']
        and len(branches) == airway['branch_count'] == int(rows[0]['branch_count'])
        and np.array_equal(upper[:, -1], nodes[:, 0])
        and bool(np.all(abs(candidate - upper[:, 2:]) < tol))
        and airway['velum_port_cm2'] == float(rows[0]['velum_port_cm2']) == 0)
    return float(abs(candidate - upper[:, 2:]).max())


def comparison_series(study, out, bins, source, compliance, checks):
    cfg = study['measurement']
    fs, count, tail_start = (cfg[key] for key in ('internal_rate_hz', 'sample_count', 'tail_start_sample'))
    freq = np.array(cfg['frequencies_hz'])
    projection = np.exp(-2j * np.pi / fs * np.outer(freq, np.arange(count)))
    phase_fields = ('pressure_pharynx_entry', 'pressure_lips', 'flow_lips', 'flow_walls')
    indices = [FIELDS.index(field) for field in phase_fields]
    throat, lip, wall = (FIELDS.index(name) for name in ('pressure_pharynx_entry', 'flow_lips', 'flow_walls'))
    h, info, normalized, active_fields = {}, {}, {}, {}
    with np.load(out / 'impulse-traces.npz', allow_pickle=False) as arrays:
        for arm in ARMS:
            upper, cli = (arrays[f'{arm}_{name}'] for name in ('upstream', 'candidate'))
            if any(series.shape != (count, len(FIELDS)) or not np.isfinite(series).all() for series in (upper, cli)):
                raise ValueError(f'インパルスCSVの標本数または列が不正です ({arm})')
            volume = cfg['impulse_volume_cm3'][arm]
            input_flow = volume * fs
            peak = abs(upper).max(axis=0)
            scale = np.where(peak > 0, peak, 1)
            waveform_error = abs(cli - upper) / scale
            over_tolerance = np.flatnonzero((waveform_error >= cfg['upstream_waveform_peak_relative_error_lt']).any(axis=1))
            checks[f'{arm}/upstream_time_series'] = not over_tolerance.size
            checks[f'{arm}/closed_velum'] = all(
                not np.any(cli[:, FIELDS.index(field)]) and not np.any(upper[:, FIELDS.index(field)])
                for field in ('pressure_nose', 'flow_velum', 'flow_sinus_neck', 'flow_nose'))
            pressure_at_zero = volume / compliance[source['inject']]
            arrivals = [np.flatnonzero(signal[:, lip])[:1].tolist() for signal in (upper, cli)]
            checks[f'{arm}/initial_pressure_and_causal_lip_flow'] = (
                all(abs(signal[0, throat] / pressure_at_zero - 1) < cfg['relative_identity_error_lt']
                    for signal in (upper, cli)) and all(first == [cfg['first_lip_sample']] for first in arrivals))
            checks[f'{arm}/radiation_is_difference_of_flows'] = all(
                abs(np.diff(signal[:, lip] + signal[:, wall], prepend=0) * fs - signal[:, -1]).max()
                < cfg['relative_identity_error_lt'] * abs(signal[:, -1]).max() for signal in (upper, cli))
            fdf = cli[:, indices] / input_flow
            h[arm] = projection @ fdf
            fft = np.fft.rfft(fdf, axis=0)[bins]
            trimmed = projection[:, :tail_start] @ fdf[:tail_start]
            tail_ratio = float(abs(cli[tail_start:, lip]).max() / abs(cli[:, lip]).max())
            tail_error = float(abs(trimmed / h[arm] - 1).max())
            checks[f'{arm}/projected_dft_matches_fft'] = bool(
                np.all(abs(fft / h[arm] - 1) < cfg['relative_identity_error_lt']))
            checks[f'{arm}/tail_convergence'] = (
                tail_ratio < cfg['tail_to_peak_lt'] and tail_error < cfg['tail_frequency_response_relative_change_lt'])
            info[arm] = {'first_lip_sample': arrivals[1][0] if arrivals[1] else None,
                         'initial_pressure_dyn_cm2': float(cli[0, throat]),
                         'tail_over_peak': tail_ratio, 'tail_frequency_response_relative_error': tail_error,
                         'upstream_waveform_peak_relative_errors': dict(zip(FIELDS, waveform_error.max(axis=0).tolist())),
                         'first_sample_over_waveform_tolerance': int(over_tolerance[0]) if over_tolerance.size else None}
            normalized[arm] = cli / input_flow
            active_fields[arm] = peak > 0
    scaling_error = abs(h['large'] / h['small'] - 1)
    checks['complex_response_scales_with_input'] = bool(
        np.all(scaling_error < cfg['amplitude_scaling_complex_relative_change_lt']))
    mask = active_fields['small'] | active_fields['large']
    scale = np.maximum(abs(normalized['small']).max(axis=0), abs(normalized['large']).max(axis=0))
    delta = abs(normalized['large'][:, mask] - normalized['small'][:, mask]) / scale[mask]
    above = np.argwhere(delta > cfg['first_amplitude_difference_peak_relative_gt'])
    first = None
    if above.size:
        start = int(above[0, 0])
        observed_fields = [field for field, selected in zip(FIELDS, mask, strict=True) if selected]
        first = {'sample': start, 'fields': [observed_fields[i] for i in above[above[:, 0] == start, 1]]}
    return h, info, first, scaling_error


def ratio(actual, reference):
    quotient = actual / reference
    return {'magnitude_relative_change': float(abs(quotient) - 1),
            'phase_difference_deg': float(np.angle(quotient, deg=True))}


def compare_short_window(study, archive, out, checks):
    short = study['short_window_reference']
    count = short['sample_count']
    failures = sorted(key for key, ok in harmonic.read(archive['short_summary.json'])['checks'].items() if not ok)
    checks['original_short_window_failures_retained'] = failures == short['expected_failed_checks']
    with np.load(archive['short_traces.npz'], allow_pickle=False) as original:
        with np.load(out / 'impulse-traces.npz', allow_pickle=False) as longer:
            checks['short_window_recording_is_identical_prefix'] = original.files == longer.files and all(
                original[key].shape == (count, len(FIELDS))
                and np.array_equal(original[key].view(np.uint64), longer[key][:count].view(np.uint64))
                for key in original.files)
    return failures


def analyze(study, archive, out):
    cfg = study['measurement']
    freq = np.array(cfg['frequencies_hz'])
    fs, count = cfg['internal_rate_hz'], cfg['sample_count']
    bins = (freq * count // fs).astype(int)
    nodes, branches, source = source_elements(archive)
    checks = {'target_frequencies_align_to_fft_bins': bool(np.array_equal(bins * fs / count, freq))}
    geometry_error = geometry_checks(study, archive, out, nodes, branches, source, checks)
    effective, active = compliance_floor(nodes, branches, source, fs)
    checks['branch_distance_matches_registered_arrival'] = lip_distance(branches, source, active) == cfg['first_lip_sample']
    geometric = nodes[:, 0]
    response = discrete_response(freq, fs, nodes, branches, source, effective, active)
    without_floor = discrete_response(freq, fs, nodes, branches, source, geometric, active)
    continuous = vowel.independent_response(freq, nodes, branches, source)[:, 0]
    prior = harmonic.read(archive['summary.json'])['frequencies']
    checks['continuous_reference_reproduced'] = all(
        row['frequency_hz'] == f and abs(value / complex(*row['continuous_linear_lip_transfer']) - 1)
        < cfg['relative_identity_error_lt'] for row, f, value in zip(prior, freq, continuous, strict=True))
    observed, time, first_amplitude_difference, scaling_error = comparison_series(
        study, out, bins, source, effective, checks)
    remainder = abs(observed['small'] / response - 1)
    checks['small_impulse_matches_discrete_node_equations'] = bool(
        np.all(remainder < cfg['small_signal_discrete_complex_relative_error_lt']))
    rows = []
    for i, f in enumerate(freq):
        lip = response[i, 2]
        baseline = continuous[i]
        rows.append({
            'frequency_hz': int(f),
            'complex_lip_flow_per_unit_input': {
                'continuous': harmonic.pair(baseline),
                'discrete_without_junction_floor': harmonic.pair(without_floor[i, 2]),
                'discrete': harmonic.pair(lip),
                **{arm: harmonic.pair(observed[arm][i, 2]) for arm in ARMS},
            },
            'discrete_without_floor_over_continuous': ratio(without_floor[i, 2], baseline),
            'junction_floor_over_discrete_without_floor': ratio(lip, without_floor[i, 2]),
            'discrete_over_continuous': ratio(lip, baseline),
            'small_observed_over_discrete': ratio(observed['small'][i, 2], lip),
            'voiced_over_discrete': {arm: ratio(complex(*value), lip) for arm, value in
                                     zip(('coupled', 'lf'), prior[i]['observed_transfer_coupled_lf'], strict=True)},
            'small_impulse_complex_relative_error': remainder[i].tolist(),
            'large_over_small_complex_relative_error': scaling_error[i].tolist(),
        })
    previous_failures = compare_short_window(study, archive, out, checks) if 'short_window_reference' in study else []
    return {'checks': {key: bool(value) for key, value in checks.items()}, 'time_domain': time,
            'first_amplitude_difference': first_amplitude_difference, 'geometry_max_absolute_error': geometry_error,
            'short_window_failed_checks': previous_failures,
            'junctions_with_raised_compliance': np.flatnonzero(effective > geometric).tolist(),
            'complex_comparison_fields': ['pressure_pharynx_entry', 'pressure_lips', 'flow_lips', 'flow_walls'],
            'frequencies': rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', args.run_id):
        parser.error('英数字で始まる実行IDを指定してください')
    study = harmonic.read(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != study['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    archive = archive_inputs(study)

    def measure(out, execute):
        capture(study, archive, out, execute)
        return analyze(study, archive, out)

    sources = [CASE, Path(__file__), *archive.values(), *shared.candidate_sources(), sagittal.PROBE,
               *(Path(module.__file__) for module in (fixed, harmonic, sagittal, shared, vowel)),
               WORKSPACE / 'tools/measure_vowel_open_o_high_bandwidth.py',
               UPSTREAM / 'crates/chimera/src/airway/network.rs', UPSTREAM / 'crates/chimera/src/voice/human_airway.rs',
               *(UPSTREAM / f'crates/chimera/tests/{name}.rs' for name in ('airway', 'airway_adversarial'))]
    details = {'case_id': study['id'], 'case_revision': study['revision'], 'upstream_revision': revision,
               'invoked_from': str(Path.cwd())}
    return shared.record_measurement(args.run_id, CASE, sources, details, measure, command=None,
                                     input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
