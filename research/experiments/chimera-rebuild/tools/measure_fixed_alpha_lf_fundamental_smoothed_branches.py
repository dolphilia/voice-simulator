"""選んだ2枝のゼロ流量付近の損失を平滑化し、口端の振幅則を測る。"""

import argparse
from pathlib import Path
import re
import subprocess

import numpy as np

import measure_fixed_alpha_lf_fundamental_amplitude_branch_loss as parity_loss
import measure_fixed_alpha_loss_tangent as tangent
import measure_fixed_vowel_i_lf_branch_loss as vowel_i_loss
from measure_fan_crossing_allocations import run_manifest, verified_path
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/fixed-alpha-lf-fundamental-smoothed-branches.json'
READ = parity_loss.READ
PAIR = parity_loss.PAIR
JOBS = parity_loss.JOBS
BRANCH = parity_loss.BRANCH
TRACE = parity_loss.TRACE
FUNDAMENTAL = parity_loss.FUNDAMENTAL
MEAN = BRANCH.MEAN
EVIDENCE = tangent.EVIDENCE


def verified_reference(spec, revision):
    run, header = record = run_manifest(spec['run'], spec['case'], revision)
    manifest = run / 'manifest.json'
    if header['status'] != 'pass' or sha256(manifest) != spec['sha256']:
        raise ValueError(f'保存実行が登録値と一致しません ({run.name})')
    row, = [item for item in header['inputs'] if item['path'].endswith(f'/cases/{spec["case"]}.json')]
    definition = run / header['source_snapshot'] / row['path']
    if sha256(definition) != row['sha256']:
        raise ValueError(f'保存ケースのハッシュが一致しません ({run.name})')
    return record, manifest, definition


def archive_inputs(study):
    record, manifest, definition = verified_reference(study['reference'], study['upstream_revision'])
    baseline = READ(definition)
    if 'network_reference' in baseline:
        prior = vowel_i_loss.archive_inputs(baseline)
        prior['upstream-geometry.csv'] = verified_path(record, 'artifacts/upstream-geometry.csv')
    else:
        original = parity_loss.archive_inputs(baseline)
        names = ('upstream-geometry.csv', *BRANCH.IMPULSE.harmonic.NETWORK_FILES,
                 'coupled-periodic.json', 'lf-periodic.json')
        prior = {name: original[name] for name in names}
    render = {f'artifacts/{job}.json': verified_path(record, f'artifacts/{job}.json') for job in JOBS.values()}
    archive = {**prior, **render,
               'artifacts/coupled.json': render[f'artifacts/{JOBS[0]}.json'],
               'reference-manifest.json': manifest, 'reference-case.json': definition,
               'reference-summary.json': verified_path(record, 'summary.json'),
               'reference-states.npz': verified_path(record, 'artifacts/branch-states.npz'),
               'reference-topology.json': verified_path(record, 'artifacts/candidate-topology.json'),
               'reference-topology-case.json': verified_path(record, 'artifacts/candidate-topology-case.json')}
    if spec := study.get('width_reference'):
        width_run, width_manifest, width_case = verified_reference(spec, study['upstream_revision'])
        archive.update({'width-reference-manifest.json': width_manifest, 'width-reference-case.json': width_case,
                        'width-reference-summary.json': verified_path(width_run, 'summary.json'),
                        'width-reference-states.npz': verified_path(width_run, 'artifacts/tangent-observations.npz'),
                        'width-reference-trace-hashes.json': verified_path(width_run, 'artifacts/trace-hashes.json')})
    return archive


def measured_loss(cfg, states, model, selected):
    nodes, topology, geometry, _, _, _, connected, main, _ = model
    flow, actual, quadratic, affine = tangent.kinetic_terms(
        states, nodes, topology[connected], connected, geometry, cfg['internal_rate_hz'],
        cfg['reference_flow_cm3_s'] * main)
    width = cfg['smoothing_width_cm3_s']
    ramp = 1 - np.maximum(1 - abs(flow) / width, 0.)**3
    smooth = np.where(selected, quadratic * ramp, quadratic)
    return flow, actual, quadratic, smooth, affine


def law_statistics(cfg, states, model, selected):
    flow, observed, _, expected, _ = measured_loss(cfg, states, model, selected)
    work = (flow * observed)[:, selected]
    below = (abs(flow[:, selected]) < cfg['smoothing_width_cm3_s']).sum(axis=0)
    return {
        'pressure_relative_error': FUNDAMENTAL.peak_relative(observed, expected),
        'small_flow_samples_per_target': below.tolist(),
        'peak_absolute_work_erg_s': float(abs(work).max()),
        'minimum_work_erg_s': float(work.min()),
        'negative_work_samples': int((work < -cfg['negative_work_relative_tolerance'] * abs(work).max()).sum()),
    }


def spectral_effects(cfg, model, before, after, selected):
    nodes, _, _, source, compliance, active, connected, _, linear = model
    count = before[0].shape[0] - 1
    rate = cfg['internal_rate_hz']
    bins = np.array(cfg['frequencies_hz']) * count // rate
    phase = np.exp(-2j * np.pi * np.outer(bins, np.arange(count)) / count)

    def coefficient(signal):
        return phase @ signal / count

    old = {scale: coefficient(data[1:, FUNDAMENTAL.LIP]) for scale, data in before.items()}
    new = {scale: coefficient(data[1:, FUNDAMENTAL.LIP]) for scale, data in after.items()}
    forces = {'direct': {}, 'flow_response': {}, 'from_observed_loss': {}}
    observed, dft_errors = {}, []
    columns = np.r_[[FUNDAMENTAL.LIP, TRACE.index('flow_walls')], np.arange(len(TRACE), len(TRACE) + len(nodes))]
    for scale in JOBS:
        _, actual0, quadratic0, smooth0, affine0 = measured_loss(cfg, before[scale], model, selected)
        _, actual1, _, smooth1, affine1 = measured_loss(cfg, after[scale], model, selected)
        direct = smooth0 - quadratic0
        total = (smooth1 - affine1) - (quadratic0 - affine0)
        forces['direct'][scale] = coefficient(direct)
        forces['flow_response'][scale] = coefficient(total - direct)
        forces['from_observed_loss'][scale] = coefficient((actual1 - affine1) - (actual0 - affine0))
        delta = after[scale][1:, columns] - before[scale][1:, columns]
        observed[scale] = coefficient(delta)
        dft_errors.append(FUNDAMENTAL.peak_relative(observed[scale], np.fft.rfft(delta, axis=0)[bins] / count))
    data = parity_loss.contrasts(observed)
    old = parity_loss.contrasts(old)
    new = parity_loss.contrasts(new)
    forces = {name: parity_loss.contrasts(values) for name, values in forces.items()}
    rows = []
    for i, frequency in enumerate(cfg['frequencies_hz']):
        lip, wall, pressure = BRANCH.responses(frequency, rate, nodes, linear, compliance, active, connected, source,
                                               np.ones(len(connected)))
        for name, measured in data.items():
            delta_lip, delta_wall = measured[i, :2]
            direct = forces['direct'][name][i]
            feedback = forces['flow_response'][name][i]
            inferred = forces['from_observed_loss'][name][i]
            predicted = lip[1:] @ (direct + feedback)
            before_lip, after_lip = old[name][i], new[name][i]
            rows.append({
                'frequency_hz': frequency, 'contrast': name,
                'baseline_lip_cm3_s': PAIR(before_lip), 'smoothed_lip_cm3_s': PAIR(after_lip),
                'difference_lip_cm3_s': PAIR(delta_lip),
                'magnitude_ratio': float(abs(after_lip) / abs(before_lip)),
                'direct_lip_cm3_s': PAIR(lip[1:] @ direct),
                'flow_response_lip_cm3_s': PAIR(lip[1:] @ feedback),
                'lip_reconstruction_error': parity_loss.relative_complex_error(predicted, delta_lip),
                'lip_from_observed_pressure_error': parity_loss.relative_complex_error(lip[1:] @ inferred, delta_lip),
                'wall_reconstruction_error': parity_loss.relative_complex_error(wall[1:] @ (direct + feedback), delta_wall),
                'pressure_reconstruction_error': FUNDAMENTAL.peak_relative(
                    pressure[:, 1:] @ (direct + feedback), measured[i, 2:]),
            })
    return rows, max(dft_errors)


def width_comparison(study, archive, out, conditions):
    reference = READ(archive['width-reference-case.json'])
    wide = reference['measurement']
    narrow = study['measurement']
    width = 'smoothing_width_cm3_s'
    checks = {
        'width_comparison/controlled_inputs_and_settings': (
            reference['reference'] == study['reference']
            and wide == {**narrow, width: study['width_reference'][width]}
            and narrow[width] < wide[width]
            and READ(out / 'trace-hashes.json') == READ(archive['width-reference-trace-hashes.json'])),
    }
    with (
        np.load(archive['width-reference-states.npz'], allow_pickle=False) as before,
        np.load(out / 'tangent-observations.npz', allow_pickle=False) as after,
    ):
        checks['width_comparison/bitwise_dc_agreement'] = all(
            np.array_equal(before[key].view(np.uint64), after[key].view(np.uint64))
            for key in after.files if key.startswith('dc_'))

    wide_report = READ(archive['width-reference-summary.json'])['conditions']
    predictions = study['fixed_flow_predicted_change']
    comparison = {}
    for edition, report in conditions.items():
        wide_rows = {(row['frequency_hz'], row['contrast']): row for row in wide_report[edition]['frequency_contrasts']}
        rows = {}
        for row in report['frequency_contrasts']:
            frequency, contrast = row['frequency_hz'], row['contrast']
            key = f'{frequency}/{contrast}'
            if key not in predictions:
                continue
            older = wide_rows[(frequency, contrast)]
            base = complex(*row['baseline_lip_cm3_s'])
            direct = complex(*row['direct_lip_cm3_s'])
            estimate = float(abs(base + direct) / abs(base) - 1)
            wide_change = older['magnitude_ratio'] - 1
            narrow_change = row['magnitude_ratio'] - 1
            prediction_error = abs(narrow_change - predictions[key])
            checks[f'width_comparison/{edition}/{key}/same_baseline_and_prediction'] = (
                row['baseline_lip_cm3_s'] == older['baseline_lip_cm3_s']
                and abs(estimate - predictions[key]) < study['prediction_rounding_tolerance'])
            rows[key] = {
                'wide_relative_change': wide_change, 'narrow_relative_change': narrow_change,
                'preregistered_relative_change': predictions[key], 'fixed_flow_relative_change': estimate,
                'absolute_prediction_error': prediction_error,
                'hypothesis_within_prediction_tolerance': prediction_error < study['hypothesis_prediction_error_lt'],
                'predicted_reversal_between_widths': wide_change * predictions[key] < 0,
                'observed_reversal_between_widths': wide_change * narrow_change < 0,
            }
        checks[f'width_comparison/{edition}/all_registered_contrasts'] = rows.keys() == predictions.keys()
        comparison[edition] = rows
    return checks, comparison


def fixed_flow_comparison(study, conditions):
    predictions = study['fixed_flow_prediction']
    checks, comparison = {}, {}
    for edition, report in conditions.items():
        rows = {}
        for row in report['frequency_contrasts']:
            key = f'{row["frequency_hz"]}/{row["contrast"]}'
            if key not in predictions:
                continue
            baseline = complex(*row['baseline_lip_cm3_s'])
            direct = complex(*row['direct_lip_cm3_s'])
            actual = complex(*row['difference_lip_cm3_s'])
            adjustment = complex(*row['flow_response_lip_cm3_s'])
            fixed_change = abs(baseline + direct) / abs(baseline) - 1
            measured_change = row['magnitude_ratio'] - 1
            error = abs(measured_change - predictions[key])
            share = abs(adjustment) / abs(actual)
            checks[f'fixed_flow_prediction/{edition}/{key}/registered_prediction_reproduced'] = (
                abs(fixed_change - predictions[key]) < study['prediction_rounding_tolerance'])
            rows[key] = {
                'registered_relative_change': predictions[key],
                'fixed_flow_relative_change': fixed_change,
                'measured_relative_change': measured_change,
                'absolute_prediction_error': error,
                'flow_response_relative_to_measurement': share,
                'hypothesis_direction_matches': measured_change * predictions[key] > 0,
                'hypothesis_error_within_tolerance': error < study['hypothesis_prediction_error_lt'],
                'hypothesis_flow_response_small': share < study['hypothesis_flow_response_share_lt'],
            }
        checks[f'fixed_flow_prediction/{edition}/all_registered_contrasts'] = rows.keys() == predictions.keys()
        comparison[edition] = rows
    return checks, comparison


def analyze(study, archive, out):
    cfg = study['measurement']
    reference_case = READ(archive['reference-case.json'])
    reference_summary = READ(archive['reference-summary.json'])
    reference_cfg = reference_case['measurement']
    sections, geometry = MEAN.fixed.read_upper_geometry(archive['upstream-geometry.csv'])
    model, _ = parity_loss.branch_model(cfg, archive, geometry)
    nodes, topology, _, source, _, _, connected, _, _ = model
    branch_addresses = [tuple(edge) for edge in topology[connected, :2].astype(int)]
    smooth_edges = {tuple(edge) for edge in cfg['variants']['smoothed']}
    selected = np.array([edge in smooth_edges for edge in branch_addresses])
    count = int(np.diff(cfg['steady_window_samples'])[0])
    early_n = int(np.diff(cfg['early_window_samples'])[0])
    common = ('internal_rate_hz', 'frequencies_hz', 'reference_flow_cm3_s', 'activation_sample',
              'early_window_samples', 'amplitude_scales')
    checks = {
        'same_registered_measurement_and_dc_case': (
            all(cfg[key] == reference_cfg[key] for key in common)
            and cfg['steady_window_samples'] == reference_cfg['window_samples']
            and 0 < cfg['smoothing_width_cm3_s'] < cfg['reference_flow_cm3_s']
            and int(selected.sum()) == len(smooth_edges) == 2
            and not cfg['variants']['baseline']
            and READ(out / 'dc.json') == tangent.dc_case(study, archive)),
    }
    reference_out = archive['reference-topology.json'].parent
    if 'network_reference' in reference_case:
        inspected, cases = vowel_i_loss.capture_definitions(reference_case, archive)
        map_indices = BRANCH.align_branch_indices(
            reference_case, reference_out, topology, nodes, source, checks, inspected, cases.values())
        checks['archived_i_inputs_and_top_ranked_oral_branches'] = (
            all(READ(archive[f'artifacts/{job}.json']) == cases[job] for job in JOBS.values())
            and len(reference_summary['shape_comparison']) == 4
            and all({(row['from'], row['to']) for row in contrast['i']['ranked_branches'][:2]} == smooth_edges
                    for contrast in reference_summary['shape_comparison'])
            and all(sections[a]['tube'] == sections[b]['tube'] == 'oral' for a, b in smooth_edges))
    else:
        map_indices = BRANCH.match_branch_indices(reference_case, archive, reference_out, topology, nodes, source, checks)
    offset = len(TRACE) + len(nodes)
    indices = np.r_[np.arange(offset), offset + np.array(map_indices)]
    fields = (*TRACE, *(f'pressure_node_{i}' for i in range(len(nodes))),
              *(f'flow_branch_{i}' for i in range(len(topology))))
    fingerprints = READ(out / 'trace-hashes.json')
    conditions, summaries, agreement = {}, {}, {}
    with (
        np.load(out / 'tangent-observations.npz', allow_pickle=False) as captured,
        np.load(archive['reference-states.npz'], allow_pickle=False) as original,
    ):
        for job in JOBS.values():
            key = f'{job}_smoothed'
            error = tangent.peak_error(captured[f'{key}_candidate'][:, indices], captured[f'{key}_upstream'])
            agreement[job] = error
            checks[f'{job}/matches_upstream_series'] = error < cfg['series_peak_relative_error_lt']
        for edition in BRANCH.EDITIONS:
            order = indices if edition == 'candidate' else slice(None)
            dc_before = captured[f'dc_baseline_{edition}'][:, order]
            dc_after = captured[f'dc_smoothed_{edition}'][:, order]
            checks[f'{edition}/dc_is_bitwise_unchanged_and_outside_interval'] = (
                np.array_equal(dc_before.view(np.uint64), dc_after.view(np.uint64))
                and np.all(abs(dc_after[:, offset:][:, connected[selected]]) > cfg['smoothing_width_cm3_s']))
            summaries[edition] = tangent.dc_stationarity(cfg, fields, dc_before, dc_after)
            before, after, first, laws = {}, {}, {}, {}
            for scale, job in JOBS.items():
                old = original[f'{job}_{edition}']
                old_early = original[f'{job}-onset_{edition}']
                key = f'{job}_baseline_{edition}'
                checks[f'{edition}/{job}/unmodified_matches_archive'] = (
                    fingerprints[key] == MEAN.sha_array(old)
                    and np.array_equal(captured[key].view(np.uint64), old_early.view(np.uint64)))
                before[scale] = old[:, order]
                trace = captured[f'{job}_smoothed_{edition}'][:, order]
                after[scale] = trace[early_n:]
                base = old_early[:, order]
                early = trace[:early_n]
                eligible = np.flatnonzero((abs(base[:, offset:][:, connected[selected]]) <
                                           cfg['smoothing_width_cm3_s']).any(axis=1))
                first[scale] = tangent.first_response(cfg, base, early, abs(before[scale]).max(axis=0), fields)
                checks[f'{edition}/{job}/first_effect_is_in_registered_interval'] = (
                    bool(eligible.size) and first[scale] is not None
                    and first[scale]['sample'] >= cfg['early_window_samples'][0] + int(eligible[0])
                    and np.array_equal(base[:eligible[0]].view(np.uint64), early[:eligible[0]].view(np.uint64)))
                laws[scale] = {'early': law_statistics(cfg, early, model, selected),
                               'steady': law_statistics(cfg, after[scale], model, selected)}
                checks[f'{edition}/{job}/pressure_and_work_match_law'] = (
                    after[scale].shape == (count + 1, len(fields))
                    and all(result['pressure_relative_error'] < cfg['branch_pressure_law_peak_relative_error_lt']
                            and result['negative_work_samples'] == 0 for result in laws[scale].values())
                    and all(laws[scale]['steady']['small_flow_samples_per_target']))
            rows, dft_error = spectral_effects(cfg, model, before, after, selected)
            limit = cfg['complex_reconstruction_relative_error_lt']
            keys = ('lip_reconstruction_error', 'lip_from_observed_pressure_error',
                    'wall_reconstruction_error', 'pressure_reconstruction_error')
            checks[f'{edition}/complex_effects_reconstructed'] = dft_error < limit and all(
                row[key] < limit for row in rows for key in keys)
            ref = {(row['frequency_hz'], row['contrast']): complex(*row['observed_lip_cm3_s'])
                   for row in reference_summary['conditions'][edition]['frequency_contrasts']}
            checks[f'{edition}/archived_reference_contrasts_reproduced'] = all(
                parity_loss.relative_complex_error(complex(*row['baseline_lip_cm3_s']),
                                                   ref[(row['frequency_hz'], row['contrast'])]) < limit
                for row in rows)
            conditions[edition] = {
                'frequency_contrasts': rows, 'dft_relative_error': dft_error,
                'first_changes': {str(scale): item for scale, item in first.items()},
                'laws_by_amplitude': {str(scale): item for scale, item in laws.items()},
                'hypothesis_gap_decreases': {
                    f'{row["frequency_hz"]}/{row["contrast"]}': row['magnitude_ratio'] < 1
                    for row in rows if row['contrast'].endswith('_gap')},
            }
    result = {'conditions': conditions, 'dc_checks': summaries, 'upstream_series_peak_relative_errors': agreement}
    if 'width_reference' in study:
        width_checks, result['width_comparison'] = width_comparison(study, archive, out, conditions)
        checks.update(width_checks)
    if 'fixed_flow_prediction' in study:
        prediction_checks, result['fixed_flow_comparison'] = fixed_flow_comparison(study, conditions)
        checks.update(prediction_checks)
    return {'checks': {key: bool(value) for key, value in checks.items()}, **result}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('--case', type=Path, default=CASE)
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', args.run_id):
        parser.error('英数字で始まる実行IDを指定してください')
    case_path = args.case.resolve()
    study = READ(case_path)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != study['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    archive = archive_inputs(study)

    def measure(out, execute):
        tangent.capture(study, archive, out, execute, law='smooth', arms=tuple(JOBS.values()))
        return analyze(study, archive, out)

    inputs = [case_path, Path(__file__), *archive.values(), *MEAN.shared.candidate_sources(),
              *tangent.CANDIDATE_DATA, tangent.PROBE,
              *(Path(module.__file__) for module in (
                  parity_loss, BRANCH, FUNDAMENTAL, tangent, MEAN, MEAN.fixed, MEAN.impulse, MEAN.sagittal, MEAN.shared)),
              UPSTREAM / tangent.UPPER, UPSTREAM / 'crates/chimera/src/voice/human_voice.rs',
              UPSTREAM / 'crates/chimera/tests/airway_adversarial.rs', UPSTREAM / 'Cargo.lock']
    if 'network_reference' in READ(archive['reference-case.json']):
        inputs.append(Path(vowel_i_loss.__file__))
    details = {'case_id': study['id'], 'case_revision': study['revision'], 'upstream_revision': revision,
               'invoked_from': str(Path.cwd())}
    return MEAN.shared.record_measurement(args.run_id, case_path, inputs, details, measure, command=None,
                                          input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
