"""固定LFの基本波変更が生む高次倍音の差を、枝の圧力損失から再構成する。"""

import argparse
import csv
import io
from pathlib import Path
import re
import subprocess

import numpy as np

import measure_fixed_alpha_branch_loss as branch
import measure_fixed_alpha_lf_fundamental as fundamental
import measure_fixed_alpha_loss_tangent as tangent
from measure_fan_crossing_allocations import run_manifest, verified_path
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/fixed-alpha-lf-fundamental-branch-loss.json'
READ = branch.READ
PAIR = branch.IMPULSE.harmonic.pair
TRACE = branch.TRACE
BASE, MATCHED = fundamental.JOBS[1:]
ARMS = {'lf': BASE, 'matched': MATCHED}
EVIDENCE = ('branch-states.npz', 'branch-contributions.csv', 'candidate-topology.json',
            'candidate-topology-case.json', *(f'{key}{suffix}.json' for key in ARMS for suffix in ('', '-onset')))


def archive_inputs(study):
    spec = study['reference']
    run, header = record = run_manifest(spec['run'], spec['case'], study['upstream_revision'])
    manifest = run / 'manifest.json'
    if header['status'] != 'pass' or sha256(manifest) != spec['sha256']:
        raise ValueError('基本波変更の保存実行が登録値と一致しません')
    row, = [item for item in header['inputs'] if item['path'].endswith(f'/cases/{spec["case"]}.json')]
    definition = run / header['source_snapshot'] / row['path']
    if sha256(definition) != row['sha256']:
        raise ValueError('基本波変更の保存ケースのハッシュが一致しません')
    old = fundamental.archive_inputs(READ(definition))
    inputs = {name: old[name] for name in ('upstream-geometry.csv', *branch.IMPULSE.harmonic.NETWORK_FILES)}
    inputs.update({'fundamental-manifest.json': manifest, 'fundamental-case.json': definition,
                   'fundamental-summary.json': verified_path(record, 'summary.json')})
    for name in ('replay-traces.npz', *(f'{job}.json' for job in fundamental.JOBS)):
        inputs[name] = verified_path(record, f'artifacts/{name}')
    return inputs


def capture_cases(study, archive):
    cfg = study['measurement']
    start, end = cfg['window_samples']
    return {
        key + suffix: {**case, 'fixed_airway': {**case['fixed_airway'], 'trace_state_samples': window}}
        for key, job in ARMS.items()
        for case in (READ(archive[f'{job}.json']),)
        for suffix, window in (('', [start - 1, end]), ('-onset', cfg['early_window_samples']))
    }


def contribution_csv(rows):
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode()


def onset(cfg, base, changed, scale, nodes, topology, source, connected, remainder):
    threshold = cfg['first_difference_peak_relative_threshold']
    delta = abs(changed - base)
    scale = np.where(scale > 0, scale, 1.0)

    def first(difference, peaks, names, start):
        rows = np.argwhere(difference > peaks * threshold)
        if rows.size == 0:
            return None
        offset = rows[0, 0]
        return {'sample': int(start + offset),
                'sites': [names[col] for col in rows[rows[:, 0] == offset, 1]]}

    start = cfg['early_window_samples'][0]
    i = len(TRACE)
    j = i + len(nodes)
    addresses = [topology[index, :2].astype(int).tolist() for index in connected]
    result = {'pressure': first(delta[:, i:j], scale[i:j], list(range(len(nodes))), start),
              'branch_flow': first(delta[:, j:][:, connected], scale[j:][connected], addresses, start),
              'pressure_remainder': first(abs(remainder), np.full(len(connected), abs(remainder).max()),
                                         addresses, start + 1)}
    first_pressure, first_branch = result['pressure'], result['branch_flow']
    causal = (first_pressure == {'sample': cfg['activation_sample'], 'sites': [source['inject']]}
              and first_branch is not None and first_branch['sample'] == cfg['activation_sample'] + 1
              and all(source['inject'] in edge for edge in first_branch['sites']))
    return result, causal


def loss_changes(cfg, traces, model):
    nodes, topology, geometry, _, _, _, connected, main, _ = model
    links = topology[connected]
    rate = cfg['internal_rate_hz']
    bias = cfg['reference_flow_cm3_s'] * main
    old, new = [tangent.kinetic_terms(trace, nodes, links, connected, geometry, rate, bias) for trace in traces]
    u0, observed0, quadratic0, affine0 = old
    u1, observed1, quadratic1, affine1 = new
    delta = (quadratic1 - affine1) - (quadratic0 - affine0)
    measured = (observed1 - affine1) - (observed0 - affine0)
    addresses = np.column_stack((links[:, :2].astype(int), np.arange(len(links))))
    kf = branch.MEAN.drag_on_path(addresses, geometry)
    kr = branch.MEAN.drag_on_path(addresses[:, [1, 0, 2]], geometry)
    change = u1 - u0
    terms = {'flow_product': 2 * kf * (u0 - bias) * change,
             'flow_difference_squared': kf * change**2,
             'reverse_correction': -(kf + kr) * (np.where(u1 < 0, u1**2, 0) - np.where(u0 < 0, u0**2, 0))}
    pressure_error = max(fundamental.peak_relative(actual, quadratic)
                         for actual, quadratic in ((observed0, quadratic0), (observed1, quadratic1)))
    return delta, measured, terms, pressure_error


def spectral_changes(cfg, spectra, traces, model, selected):
    nodes, topology, _, source, compliance, active, connected, main, linear = model
    columns = [TRACE.index('flow_lips'), TRACE.index('flow_walls')]
    output = traces[1][1:] - traces[0][1:]
    pressure = output[:, len(TRACE):len(TRACE) + len(nodes)]
    delta, observed, terms, balance = loss_changes(cfg, traces, model)
    projection, bins, input_delta = spectra
    count = len(output)
    errors = []

    def coefficient(signal):
        direct = projection @ signal / count
        fft = np.fft.rfft(signal, axis=0)[bins] / count
        errors.append(fundamental.peak_relative(direct, fft))
        return direct

    excitation = projection @ input_delta / count
    outlets = coefficient(output[:, columns])
    observed_pressure = coefficient(pressure)
    residual = coefficient(delta)
    inferred = coefficient(observed)
    parts = {name: coefficient(term) for name, term in terms.items()}
    rows, contributions = [], []
    for i, frequency in enumerate(cfg['frequencies_hz']):
        def solve(force):
            return branch.responses(frequency, cfg['internal_rate_hz'], nodes, linear, compliance,
                                    active, connected, source, force)

        lip, wall, node = solve(residual[i])
        measurement = outlets[i, 0]
        flow_part = lip[0] * excitation[i]
        estimate = lip[1:].sum() + flow_part
        predicted_wall = wall[1:].sum() + wall[0] * excitation[i]
        predicted_pressure = node[:, 1:].sum(axis=1) + node[:, 0] * excitation[i]
        by_part = {name: solve(force[i])[0][1:] for name, force in parts.items()}
        measured_lip, _, _ = solve(inferred[i])
        parts_sum = {name: value.sum() for name, value in by_part.items()}
        shares = (lip[1:] * measurement.conjugate()).real / abs(measurement)**2
        order = np.argsort(-abs(lip[1:]), kind='stable')
        rows.append({
            'frequency_hz': frequency, 'measured_lip_change_cm3_s': PAIR(measurement),
            'input_lip_contribution_cm3_s': PAIR(flow_part), 'branch_sum_cm3_s': PAIR(lip[1:].sum()),
            'oral_path_contribution_cm3_s': PAIR(lip[1:][main].sum()),
            'side_branch_contribution_cm3_s': PAIR(lip[1:][~main].sum()),
            'by_pressure_component_cm3_s': {name: PAIR(value) for name, value in parts_sum.items()},
            'pharyngeal_projected_share': float(shares[selected].sum()),
            'lip_relative_error': float(abs(estimate - measurement) / abs(measurement)),
            'wall_relative_error': float(abs(predicted_wall - outlets[i, 1]) / abs(outlets[i, 1])),
            'pressure_relative_error': fundamental.peak_relative(predicted_pressure, observed_pressure[i]),
            'observed_loss_lip_relative_error': float(abs(measured_lip[1:].sum() + flow_part - measurement) / abs(measurement)),
            'pressure_component_lip_relative_error': float(abs(sum(parts_sum.values()) - lip[1:].sum()) / abs(measurement)),
            'input_contribution_relative_to_lip_change': float(abs(flow_part) / abs(measurement)),
        })
        for rank, k in enumerate(order, start=1):
            left, right = topology[connected[k], :2].astype(int)
            contribution = lip[k + 1]
            contributions.append({
                'frequency_hz': frequency, 'rank_by_magnitude': rank, 'branch': int(connected[k]),
                'from': int(left), 'to': int(right), 'on_oral_path': bool(main[k]),
                'pressure_real_dyn_cm2': float(residual[i, k].real),
                'pressure_imag_dyn_cm2': float(residual[i, k].imag),
                'lip_real_cm3_s': float(contribution.real), 'lip_imag_cm3_s': float(contribution.imag),
                'projected_share': float(shares[k]),
                **{f'{name}_lip_{part}_cm3_s': float(getattr(value[k], part))
                   for name, value in by_part.items() for part in ('real', 'imag')},
            })
    return rows, contributions, balance, max(errors), fundamental.peak_relative(sum(terms.values()), delta)


def analyze(study, archive, out):
    cfg = study['measurement']
    nodes, topology, source = branch.IMPULSE.source_elements(archive)
    _, geometry = branch.MEAN.fixed.read_upper_geometry(archive['upstream-geometry.csv'])
    rate = cfg['internal_rate_hz']
    compliance, active = branch.IMPULSE.compliance_floor(nodes, topology, source, rate)
    connected = branch.connected_links(topology, active, source['inject'])
    path = branch.MEAN.airway_path(topology, active, source)
    main = np.isin(connected, path[:, 2])
    linear = topology.copy()
    linear[path[:, 2], 4] += 2 * branch.MEAN.drag_on_path(path, geometry) * cfg['reference_flow_cm3_s']
    model = (nodes, topology, geometry, source, compliance, active, connected, main, linear)
    cfg0 = READ(archive['fundamental-case.json'])['measurement']
    cases = capture_cases(study, archive)
    start, end = cfg['window_samples']
    count = end - start
    frequencies = np.array(cfg['frequencies_hz'])
    bins = frequencies * count // rate
    projection = np.exp(-2j * np.pi * np.outer(bins, np.arange(count)) / count)
    inputs = [fundamental.flow_series(cases[key]) for key in ARMS]
    input_delta = inputs[1] - inputs[0]
    addresses = {tuple(edge): i for i, edge in enumerate(topology[connected, :2].astype(int))}
    selected = [addresses[tuple(edge)] for edge in cfg['pharyngeal_edges']]
    checks = {
        'same_registered_pose_clock_and_waveforms': (
            all(READ(out / f'{key}.json') == case for key, case in cases.items())
            and all(cases[key]['body'] == cases['lf']['body'] and cases[key]['posture'] == cases['lf']['posture']
                    and cases[key]['fixed_airway']['sample_rate_hz'] == rate
                    and cases[key]['fixed_airway']['sample_count'] == end
                    and cases[key]['fixed_airway']['steady_flow_cm3_s'] == cfg['reference_flow_cm3_s']
                    and cases[key]['fixed_airway_periodic_flow']['start_sample'] == cfg['activation_sample']
                    and len(wave) == count for key, wave in zip(ARMS, inputs, strict=True))
            and cfg0['internal_rate_hz'] == rate and cfg0['after_onset_samples_to_keep'] == (
                cfg['early_window_samples'][1] - cfg['activation_sample'])
            and cfg['early_window_samples'][0] + 1 == cfg['activation_sample']),
        'registered_connected_and_main_path_branches': (
            len(connected) == cfg['expected_connected_branches']
            and len(path) == int(main.sum()) == cfg['expected_main_path_branches']
            and np.array_equal(path[:, :2], topology[path[:, 2], :2])),
        'coherent_bins': np.array_equal(bins * rate, frequencies * count),
    }
    mapping = branch.match_branch_indices(study, archive, out, topology, nodes, source, checks)
    offset = len(TRACE) + len(nodes)
    indices = np.r_[np.arange(offset), offset + np.array(mapping)]
    limit = cfg['complex_reconstruction_relative_error_lt']
    conditions, comparisons = {}, {}
    with (
        np.load(out / 'branch-states.npz', allow_pickle=False) as raw,
        np.load(archive['replay-traces.npz'], allow_pickle=False) as previous,
    ):
        aligned = {key: raw[key][:, indices] if key.endswith('_candidate') else raw[key] for key in raw.files}
        for key in cases:
            error = tangent.peak_error(aligned[f'{key}_candidate'], aligned[f'{key}_upstream'])
            comparisons[key] = error
            checks[f'{key}/matches_upstream_series'] = error < cfg['series_peak_relative_error_lt']
        for edition in branch.EDITIONS:
            traces, early = ([aligned[f'{key}{suffix}_{edition}'] for key in ARMS] for suffix in ('', '-onset'))
            checks[f'{edition}/archived_outlets_and_window_match'] = all(
                np.array_equal(trace[:, :len(TRACE)].view(np.uint64),
                               previous[f'{job}_{edition}'][-(count + 1):].view(np.uint64))
                and np.array_equal(on[:1].view(np.uint64), early[0][:1].view(np.uint64))
                and np.array_equal(on[1:, :len(TRACE)].view(np.uint64), previous[f'{job}_{edition}_start'].view(np.uint64))
                for job, trace, on in zip(ARMS.values(), traces, early, strict=True))
            rows, contributions, law_error, dft_error, split_error = spectral_changes(
                cfg, (projection, bins, input_delta), traces, model, selected)
            early_delta, _, _, onset_law = loss_changes(cfg, early, model)
            first, causal = onset(cfg, *early, abs(traces[0]).max(axis=0), nodes, topology, source, connected, early_delta)
            checks[f'{edition}/first_difference_follows_branched_update'] = causal
            checks[f'{edition}/kinetic_balance_in_both_windows'] = (
                max(law_error, onset_law) < cfg['kinetic_balance_peak_relative_error_lt'])
            checks[f'{edition}/pressure_components_and_dft_agree'] = (
                max(dft_error, split_error) < cfg['spectral_identity_relative_error_lt'])
            closure = ('lip_relative_error', 'wall_relative_error', 'pressure_relative_error',
                       'observed_loss_lip_relative_error', 'pressure_component_lip_relative_error',
                       'input_contribution_relative_to_lip_change')
            checks[f'{edition}/reconstructed_lip_wall_and_node_differences'] = all(
                row[key] < limit for row in rows for key in closure)
            conditions[edition] = {
                'frequencies': rows, 'first_changes': first, 'pressure_balance_error': max(law_error, onset_law),
                'dft_error': dft_error, 'pressure_component_error': split_error,
                'hypothesis_pharyngeal_share': all(row['pharyngeal_projected_share']
                    >= cfg['hypothesis_pharyngeal_projected_share_ge'] for row in rows),
            }
            if edition == 'candidate':
                candidate_rows = contributions
    return {'checks': {key: bool(value) for key, value in checks.items()}, 'conditions': conditions,
            'upstream_series_peak_relative_errors': comparisons, 'branch_contributions': candidate_rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', args.run_id):
        parser.error('英数字で始まる実行IDを指定してください')
    study = READ(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != study['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    archive = archive_inputs(study)

    def measure(out, execute):
        branch.capture_cases(archive, out, execute, branch.topology_case(study, archive), capture_cases(study, archive).items())
        result = analyze(study, archive, out)
        (out / 'branch-contributions.csv').write_bytes(contribution_csv(result['branch_contributions']))
        return result

    mean = branch.MEAN
    inputs = [CASE, Path(__file__), *archive.values(), *mean.shared.candidate_sources(), mean.sagittal.PROBE,
              *(Path(module.__file__) for module in (
                  branch, fundamental, tangent, branch.periodic, mean, mean.fixed, mean.impulse, mean.sagittal, mean.shared)),
              UPSTREAM / tangent.UPPER, UPSTREAM / 'crates/chimera/src/voice/human_voice.rs',
              UPSTREAM / 'crates/chimera/tests/airway_adversarial.rs', UPSTREAM / 'Cargo.lock']
    details = {'case_id': study['id'], 'case_revision': study['revision'], 'upstream_revision': revision,
               'invoked_from': str(Path.cwd())}
    return mean.shared.record_measurement(args.run_id, CASE, inputs, details, measure, command=None,
                                          input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
