"""固定 /ɑ/ で定常流が小信号応答に与える影響を調べる。"""

import argparse
from collections import deque
import hashlib
import json
from pathlib import Path
import re
import subprocess
from tempfile import TemporaryDirectory

import numpy as np

import measure_fixed_alpha_discrete_impulse as impulse
import measure_fixed_airway as fixed
import measure_sagittal as sagittal
import measure_uniform_tube as shared
from measure_fan_crossing_allocations import run_manifest, verified_path
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/fixed-alpha-mean-flow.json'
ARMS = ('zero', 'voiced_mean')
DRIVES = ('control', 'response')
EDITIONS = ('candidate', 'upstream')
TRACE_FIELDS = impulse.FIELDS
RESPONSE_FIELDS = ('pressure_pharynx_entry', 'pressure_lips', 'flow_lips', 'flow_walls')
EVIDENCE = ('mean-flow-traces.npz', 'capture.json', *(f'{arm}-{drive}.json' for arm in ARMS for drive in DRIVES))


def archive_inputs(study):
    sources = {}
    for arm, spec in study['references'].items():
        run, header = record = run_manifest(spec['run'], spec['case'], study['upstream_revision'])
        manifest = run / 'manifest.json'
        if header['status'] != 'pass' or sha256(manifest) != spec['sha256']:
            raise ValueError(f'基準実行のハッシュまたは判定が不一致です ({run.name})')
        sources[f'{arm}-manifest.json'] = manifest
        paths = {'impulse': ('upstream-geometry.csv', 'large-case.json', 'impulse-traces.npz'),
                 'voice': ('radiation-observations.npz',)}
        sources.update({name: verified_path(record, f'artifacts/{name}') for name in paths[arm]})
        if arm == 'impulse':
            sources['impulse-summary.json'] = verified_path(record, 'summary.json')
            item, = [row for row in header['inputs'] if row['path'].endswith(f'/cases/{spec["case"]}.json')]
            definition = run / header['source_snapshot'] / item['path']
            if sha256(definition) != item['sha256']:
                raise ValueError('保存ケースのハッシュが一致しません')
            reference = impulse.archive_inputs(impulse.harmonic.read(definition))
            sources.update({'impulse-definition.json': definition, **reference})
    return sources


def case_for(study, sources, arm, drive):
    case = impulse.harmonic.read(sources['large-case.json'])
    cfg = study['measurement']
    case['id'] = f'{study["id"]}-{arm}-{drive}'
    case['hypothesis'] = study['hypothesis']
    case['fixed_airway'] = {
        'sample_rate_hz': cfg['internal_rate_hz'],
        'sample_count': cfg['perturbation_sample'] + cfg['response_sample_count'],
        'impulse_sample': cfg['perturbation_sample'],
        'impulse_volume_cm3': cfg['perturbation_volume_cm3'] if drive == 'response' else 0,
        'steady_flow_cm3_s': cfg['mean_flow_cm3_s'][arm],
    }
    return case


def capture(study, sources, out, execute):
    cfg = study['measurement']
    onset = cfg['perturbation_sample']
    start = onset - cfg['steady_sample_count']
    count = onset + cfg['response_sample_count']
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera', '--test', 'airway_adversarial',
             'steady_flow_through_a_short_constriction_obeys_bernoulli_with_jet_loss'], cwd=UPSTREAM,
            stdout=out / 'upstream-steady-flow-test.log')
    probe = shared.build_upstream_probe(sagittal.PROBE, out, execute, cargo_args=('--offline',))
    cli = ['cargo', 'run', '--locked', '--offline', '--release', '-p', 'vocal-cli', '--']
    pose = sagittal.pose_controls(impulse.harmonic.read(sources['large-case.json']))
    traces, prefix, legacy = {}, {}, {}
    with TemporaryDirectory(prefix='mean-flow-csv-', dir=out) as temporary:
        directory = Path(temporary)
        for arm in ARMS:
            for drive in DRIVES:
                case = case_for(study, sources, arm, drive)
                path = out / f'{arm}-{drive}.json'
                path.write_text(json.dumps(case, ensure_ascii=False, indent=2) + '\n')
                edition_paths = {edition: directory / f'{arm}-{drive}-{edition}.csv' for edition in EDITIONS}
                execute([*cli, 'render', str(path), str(edition_paths['candidate'])])
                settings = case['fixed_airway']
                args = [cfg['internal_rate_hz'], count, settings['impulse_volume_cm3'],
                        onset, settings['steady_flow_cm3_s']]
                execute([str(probe), '--fixed-airway-bias', *map(str, args), *pose], cwd=UPSTREAM,
                        stdout=edition_paths['upstream'])
                for edition, csv in edition_paths.items():
                    trace = fixed.read_trace(csv, TRACE_FIELDS, count)
                    traces[f'{arm}_{drive}_{edition}'] = trace[start:].copy()
                    prefix[f'{arm}_{drive}_{edition}'] = sha_array(trace[:onset])
                    csv.unlink()
        # 開始標本を省いた従来のCLI経路を、前回の保存系列に改めて照合する。
        for edition in EDITIONS:
            csv = directory / f'original-{edition}.csv'
            if edition == 'candidate':
                execute([*cli, 'render', str(sources['large-case.json']), str(csv)])
            else:
                args = [cfg['internal_rate_hz'], cfg['response_sample_count'], cfg['perturbation_volume_cm3']]
                execute([str(probe), '--fixed-airway', *map(str, args), *pose], cwd=UPSTREAM, stdout=csv)
            trace = fixed.read_trace(csv, TRACE_FIELDS, cfg['response_sample_count'])
            legacy[edition] = sha_array(trace)
    np.savez_compressed(out / 'mean-flow-traces.npz', **traces)
    (out / 'capture.json').write_text(json.dumps({'pre_impulse_sha256': prefix, 'original_sha256': legacy},
                                                 indent=2) + '\n')


def sha_array(values):
    return hashlib.sha256(np.ascontiguousarray(values, dtype='<f8').tobytes()).hexdigest()


def airway_path(branches, active, source):
    connection = {}
    for index in np.flatnonzero(active):
        left, right = map(int, branches[index, :2])
        connection.setdefault(left, []).append((right, index))
        connection.setdefault(right, []).append((left, index))
    inlet, lip = source['inject'], source['lips']
    previous = {inlet: (None, None)}
    frontier = deque([inlet])
    while frontier and lip not in previous:
        node = frontier.popleft()
        for neighbor, index in connection[node]:
            if neighbor not in previous:
                previous[neighbor] = (node, index)
                frontier.append(neighbor)
    forward = []
    node = lip
    while node != inlet:
        left, index = previous[node]
        forward.append((left, node, index))
        node = left
    return np.array(forward[::-1], dtype=int)


def drag_on_path(path, geometry):
    left, right, _ = path.T
    area, minimum = geometry[:, 3:5].T
    expansion = np.maximum(1 / minimum[left] - 1 / area[right], 0)
    contraction = np.maximum(1 / minimum[right] - 1 / area[left], 0)
    return 0.00114 / 2 * (expansion**2 + 0.1 * contraction**2)


def spectra(cfg, response, inlet):
    rate = cfg['internal_rate_hz']
    frequencies = np.array(cfg['frequencies_hz'])
    count = cfg['response_sample_count']
    bins = (frequencies * count // rate).astype(int)
    if not np.array_equal(bins * rate / count, frequencies):
        raise ValueError('複素応答の対象周波数をFFTのビンに揃えてください')
    indices = [TRACE_FIELDS.index(field) for field in RESPONSE_FIELDS]
    series = response[:, indices] / inlet
    projection = np.exp(-2j * np.pi / rate * np.outer(frequencies, np.arange(count)))
    dft = projection @ series
    fft = np.fft.rfft(series, axis=0)[bins]
    end = cfg['tail_start_offset']
    trimmed = projection[:, :end] @ series[:end]
    return dft, float(abs(fft / dft - 1).max()), float(abs(trimmed / dft - 1).max())


def examine_arm(study, array, arm, path, model, inlet_state, capture_meta, previous):
    cfg = study['measurement']
    bias = cfg['mean_flow_cm3_s'][arm]
    rate = cfg['internal_rate_hz']
    inlet_flow = (bias + cfg['perturbation_volume_cm3'] * rate) - bias
    steady = cfg['steady_sample_count']
    volume = inlet_flow / rate
    compliance, first_branch_drag, steady_pressure, wall_y = inlet_state
    observed, response = {}, {}
    checks = {}
    details = {}
    all_pressures = []
    for edition in EDITIONS:
        base_key = f'{arm}_control_{edition}'
        signal_key = f'{arm}_response_{edition}'
        base, signal = (array[key] for key in (base_key, signal_key))
        expected_shape = (steady + cfg['response_sample_count'], len(TRACE_FIELDS))
        if any(data.shape != expected_shape or not np.isfinite(data).all() for data in (base, signal)):
            raise ValueError(f'保存波形の標本数または列が不正です ({arm} {edition})')
        before = capture_meta['pre_impulse_sha256']
        checks[f'{edition}/unchanged_before_impulse'] = (
            before[base_key] == before[signal_key] and np.array_equal(base[:steady], signal[:steady]))
        start = base[:steady]
        requested = {'pressure_pharynx_entry': steady_pressure, 'pressure_lips': 0.0,
                     'flow_lips': bias, 'flow_oral_link': bias, 'flow_nose': 0.0, 'flow_walls': 0.0}
        errors = {key: float(abs(start[:, TRACE_FIELDS.index(key)] - expected).max() / max(abs(expected), 1.0))
                  for key, expected in requested.items()}
        checks[f'{edition}/steady_pressure_and_flow'] = max(errors.values()) < cfg['steady_flow_and_pressure_relative_error_lt']
        difference = signal[steady:] - base[steady:]
        dft, dft_error, tail_error = spectra(cfg, difference, inlet_flow)
        model_error = float(abs(dft / model - 1).max())
        checks[f'{edition}/dft_agrees_with_fft'] = dft_error < cfg['dft_relative_error_lt']
        checks[f'{edition}/tail_convergence'] = tail_error < cfg['tail_complex_relative_error_lt']
        checks[f'{edition}/complex_response_matches_linearized_branch_drag'] = model_error < cfg['model_complex_relative_error_lt']
        initial_pressure = volume / compliance
        following_pressure = initial_pressure * (1 - (1 / first_branch_drag + wall_y) / (compliance * rate))
        measured_pressure = difference[:2, TRACE_FIELDS.index('pressure_pharynx_entry')]
        checks[f'{edition}/first_two_pressure_samples'] = (
            abs(measured_pressure / [initial_pressure, following_pressure] - 1).max()
            < cfg['initial_pressure_relative_error_lt'])
        lip = difference[:, TRACE_FIELDS.index('flow_lips')]
        checks[f'{edition}/causal_lip_response'] = not np.any(lip[:len(path)]) and np.any(lip[len(path):])
        if arm == 'zero':
            checks[f'{edition}/zero_flow_reproduces_original_impulse'] = (
                np.array_equal(difference, previous[f'large_{edition}'])
                and capture_meta['original_sha256'][edition] == sha_array(previous[f'large_{edition}']))
        observed[edition] = difference
        response[edition] = dft
        all_pressures.append(measured_pressure)
        details[edition] = {'steady_peak_errors': errors, 'dft_complex_relative_error': dft_error,
                            'tail_complex_relative_error': tail_error, 'model_complex_relative_error': model_error,
                            'first_two_pressure_differences_dyn_cm2': measured_pressure.tolist(),
                            'frequency_response': [[impulse.harmonic.pair(item) for item in row] for row in dft]}
    upstream = observed['upstream']
    peak = abs(upstream).max(axis=0)
    error = abs(observed['candidate'] - upstream) / np.where(peak > 0, peak, 1)
    tolerance = cfg['upstream_series_peak_relative_error_lt']
    first = np.flatnonzero((error >= tolerance).any(axis=1))
    checks['upstream_difference_time_series'] = not first.size
    return checks, {'edition': details, 'upstream_error_per_field': dict(zip(TRACE_FIELDS, error.max(axis=0).tolist())),
                    'earliest_index_over_tolerance': int(first[0]) if first.size else None,
                    'predicted_steady_inlet_pressure_dyn_cm2': steady_pressure}, response, all_pressures


def analyze(study, sources, out):
    cfg = study['measurement']
    rate = cfg['internal_rate_hz']
    prior = impulse.harmonic.read(sources['impulse-summary.json'])
    capture_meta = impulse.harmonic.read(out / 'capture.json')
    begin, end = cfg['voice_mean_window']
    with np.load(sources['radiation-observations.npz'], allow_pickle=False) as voice:
        source_mean = float(np.mean(voice['coupled_upstream'][begin:end, impulse.harmonic.lf.OBSERVED.index(impulse.harmonic.lf.Q)]))
    checks = {
        'registered_mean_matches_archived_voice': source_mean == cfg['mean_flow_cm3_s']['voiced_mean'],
        'input_cases_match_registered_controls': all(
            impulse.harmonic.read(out / f'{arm}-{drive}.json') == case_for(study, sources, arm, drive)
            for arm in ARMS for drive in DRIVES),
    }
    nodes, branches, source = impulse.source_elements(sources)
    _, geometry = fixed.read_upper_geometry(sources['upstream-geometry.csv'])
    effective, active = impulse.compliance_floor(nodes, branches, source, rate)
    path = airway_path(branches, active, source)
    indices = path[:, 2]
    checks['registered_oral_path_geometry'] = (
        len(path) == 35 and np.array_equal(path[:, :2], branches[indices, :2])
        and np.array_equal(geometry[:, -1], nodes[:, 0]))
    drag = drag_on_path(path, geometry)
    inlet = source['inject']
    compliance, _, wall_area, wall_mass, wall_resistance, *_ = nodes[inlet]
    wall_y = wall_area / (wall_mass * rate + wall_resistance / 2)
    first = indices[0]
    data, observed, predictions, pressure = {}, {}, {}, {}
    with np.load(out / 'mean-flow-traces.npz', allow_pickle=False) as array:
        with np.load(sources['impulse-traces.npz'], allow_pickle=False) as previous:
            for arm in ARMS:
                bias = cfg['mean_flow_cm3_s'][arm]
                linear = branches.copy()
                linear[indices, 4] += 2 * drag * bias
                model = impulse.discrete_response(cfg['frequencies_hz'], rate, nodes, linear, source, effective, active)
                state = (compliance, linear[first, 3] * rate + linear[first, 4],
                         float(np.sum(bias * branches[indices, 4] + bias**2 * drag)), wall_y)
                verdicts, data[arm], observed[arm], pressure[arm] = examine_arm(
                    study, array, arm, path, model, state, capture_meta, previous)
                checks.update({f'{arm}/{key}': value for key, value in verdicts.items()})
                predictions[arm] = model

    rows = []
    for i, f in enumerate(cfg['frequencies_hz']):
        normal, biased = (observed[arm]['candidate'][i, 2] for arm in ARMS)
        baseline, model = (predictions[arm][i, 2] for arm in ARMS)
        checks[f'{f}Hz/measurable_effect_of_mean_flow'] = (
            abs(biased / normal - 1) > cfg['observable_bias_effect_complex_relative_gt'])
        checks[f'{f}Hz/original_discrete_model_reproduced'] = (
            abs(baseline / complex(*prior['frequencies'][i]['complex_lip_flow_per_unit_input']['discrete']) - 1)
            < cfg['dft_relative_error_lt'])
        voiced = {}
        for arm in ('coupled', 'lf'):
            previous = prior['frequencies'][i]['voiced_over_discrete'][arm]
            value = baseline * (1 + previous['magnitude_relative_change']) * np.exp(
                1j * np.deg2rad(previous['phase_difference_deg']))
            voiced[arm] = {'over_zero_flow': impulse.ratio(value, normal), 'over_mean_flow': impulse.ratio(value, biased),
                           'complex_gap_fraction_retained': float(abs(value - biased) / abs(value - normal))}
        rows.append({'frequency_hz': f,
                     'lip_transfer_zero_and_voiced_mean': [impulse.harmonic.pair(normal), impulse.harmonic.pair(biased)],
                     'mean_flow_over_zero_flow_measured': impulse.ratio(biased, normal),
                     'mean_flow_over_zero_flow_predicted': impulse.ratio(model, baseline),
                     'voiced_residual': voiced})
    pressure_delta = np.asarray(pressure['voiced_mean']) - np.asarray(pressure['zero'])
    return {'checks': {key: bool(value) for key, value in checks.items()}, 'archived_mean_flow_cm3_s': source_mean,
            'oral_path_branches': indices.tolist(), 'total_kinetic_drag_on_path': float(drag.sum()),
            'response_fields': list(RESPONSE_FIELDS), 'time_domain': data,
            'biased_minus_zero_initial_pressure_dyn_cm2': pressure_delta.tolist(), 'frequencies': rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', args.run_id):
        parser.error('英数字で始まる実行IDを指定してください')
    study = impulse.harmonic.read(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != study['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    sources = archive_inputs(study)

    def measure(out, execute):
        capture(study, sources, out, execute)
        return analyze(study, sources, out)

    inputs = [CASE, Path(__file__), *sources.values(), *shared.candidate_sources(), sagittal.PROBE,
              *(Path(module.__file__) for module in (impulse, impulse.harmonic, fixed, sagittal, shared)),
              UPSTREAM / 'crates/chimera/src/airway/network.rs', UPSTREAM / 'crates/chimera/src/voice/human_airway.rs',
              UPSTREAM / 'crates/chimera/tests/airway_adversarial.rs']
    details = {'case_id': study['id'], 'case_revision': study['revision'], 'upstream_revision': revision,
               'invoked_from': str(Path.cwd())}
    return shared.record_measurement(args.run_id, CASE, inputs, details, measure, command=None,
                                     input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
