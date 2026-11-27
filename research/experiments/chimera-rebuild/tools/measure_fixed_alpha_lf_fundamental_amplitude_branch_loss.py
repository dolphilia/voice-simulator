"""固定LFの奇・偶成分と振幅則からのずれを枝圧力源で照合する。"""

import argparse
from pathlib import Path
import re
import subprocess

import numpy as np

import measure_fixed_alpha_lf_fundamental_amplitude as amplitude
import measure_fixed_alpha_lf_fundamental_branch_loss as single
from measure_fan_crossing_allocations import run_manifest, verified_path
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/fixed-alpha-lf-fundamental-amplitude-branch-loss.json'
READ = amplitude.READ
PAIR = amplitude.PAIR
JOBS = amplitude.JOBS
TRACE = single.TRACE
BRANCH = single.branch
MEAN = BRANCH.MEAN
FUNDAMENTAL = single.fundamental
EVIDENCE = ('branch-states.npz', 'branch-contributions.csv', 'candidate-topology.json',
            'candidate-topology-case.json', *(f'{job}{suffix}.json' for job in JOBS.values() for suffix in ('', '-onset')))


def archive_inputs(study):
    archives = {}
    for key in ('reference', 'branch_reference'):
        spec = study[key]
        run, header = record = run_manifest(spec['run'], spec['case'], study['upstream_revision'])
        manifest = run / 'manifest.json'
        if header['status'] != 'pass' or sha256(manifest) != spec['sha256']:
            raise ValueError(f'前提の保存実行が登録値と一致しません ({run.name})')
        archives[f'{key}-manifest.json'] = manifest
        if key == 'branch_reference':
            archives['reference-branch-states.npz'] = verified_path(record, 'artifacts/branch-states.npz')
            continue
        row, = [item for item in header['inputs'] if item['path'].endswith(f'/cases/{spec["case"]}.json')]
        definition = run / header['source_snapshot'] / row['path']
        if sha256(definition) != row['sha256']:
            raise ValueError('振幅変更の保存ケースのハッシュが一致しません')
        earlier = amplitude.archive_inputs(READ(definition))
        archives.update({name: earlier[name] for name in ('upstream-geometry.csv', *BRANCH.IMPULSE.harmonic.NETWORK_FILES)})
        fundamental_manifest = earlier['fundamental-manifest.json']
        archives['coupled-periodic.json'] = verified_path(
            (fundamental_manifest.parent, READ(fundamental_manifest)), 'artifacts/coupled-periodic.json')
        archives['amplitude-case.json'] = definition
        archives['amplitude-summary.json'] = verified_path(record, 'summary.json')
        for name in ('replay-traces.npz', *(f'{job}.json' for job in JOBS.values())):
            archives[name] = verified_path(record, f'artifacts/{name}')
    return archives


def capture_cases(study, archive):
    cfg = study['measurement']
    start, end = cfg['window_samples']
    return {
        job + suffix: {**case, 'fixed_airway': {**case['fixed_airway'], 'trace_state_samples': window}}
        for job in JOBS.values()
        for case in (READ(archive[f'{job}.json']),)
        for suffix, window in (('', [start - 1, end]), ('-onset', cfg['early_window_samples']))
    }


def contrasts(values):
    odd, even = amplitude.parity(values, 1)
    odd_half, even_half = amplitude.parity(values, 0.5)
    return {'odd_full': odd, 'even_full': even, 'odd_half': odd_half, 'even_half': even_half,
            'odd_scaling_gap': 2 * odd_half - odd, 'even_scaling_gap': 4 * even_half - even}


def spectra(cfg, projection, bins, traces, waves, model):
    nodes, _, _, _, _, _, connected, _, _ = model
    count = projection.shape[1]
    errors = []

    def coefficient(signal, *, scale=None):
        direct = projection @ signal / count
        fft = np.fft.rfft(signal, axis=0)[bins] / count
        if scale is None:
            scale = float(abs(fft).max())
        errors.append(float(abs(direct - fft).max() / max(scale, np.finfo(float).tiny)))
        return direct

    offset = len(TRACE) + len(nodes)
    backwards = np.stack([data[1:, offset:][:, connected] < 0 for data in traces.values()])
    all_reverse = backwards.all(axis=0)
    changes_direction = backwards.any(axis=0) & ~all_reverse
    keyset = ('flow_product', 'flow_difference_squared', 'reverse_same_direction', 'reverse_changes_direction')
    inputs = {0: np.zeros(len(bins), dtype=complex)}
    losses = {key: {0: np.zeros((len(bins), len(connected)), dtype=complex)}
              for key in ('theoretical', 'observed', *keyset)}
    pressure_errors, split_errors = [], []
    for scale in JOBS:
        if scale == 0:
            continue
        wave_delta = waves[scale] - waves[0]
        inputs[scale] = coefficient(wave_delta, scale=float(abs(wave_delta).max()))
        theoretical, observed, parts, pressure_error = single.loss_changes(cfg, (traces[0], traces[scale]), model)
        reverse = parts.pop('reverse_correction')
        parts['reverse_same_direction'] = np.where(all_reverse, reverse, 0)
        parts['reverse_changes_direction'] = np.where(changes_direction, reverse, 0)
        for name, signal in {'theoretical': theoretical, 'observed': observed, **parts}.items():
            losses[name][scale] = coefficient(signal)
        pressure_errors.append(pressure_error)
        split_errors.append(FUNDAMENTAL.peak_relative(sum(parts.values()), theoretical))
    measured_columns = np.r_[[TRACE.index('flow_lips'), TRACE.index('flow_walls')],
                             np.arange(len(TRACE), offset)]
    measured = {name: coefficient(data) for name, data in contrasts(
        {scale: trace[1:, measured_columns] for scale, trace in traces.items()}).items()}
    statistics = {'kinetic_pressure_error': max(pressure_errors), 'split_pressure_error': max(split_errors),
                  'dft_error': max(errors), 'all_reverse_samples_by_branch': all_reverse.sum(axis=0).tolist(),
                  'direction_change_samples_by_branch': changes_direction.sum(axis=0).tolist()}
    return contrasts(inputs), {key: contrasts(value) for key, value in losses.items()}, measured, statistics


def solve_contributions(cfg, model, inputs, losses, measured):
    nodes, topology, _, source, compliance, active, connected, main, linear = model
    part_names = tuple(key for key in losses if key not in ('theoretical', 'observed'))
    rows, detail = [], []
    for i, frequency in enumerate(cfg['frequencies_hz']):
        lip, wall, pressure = BRANCH.responses(frequency, cfg['internal_rate_hz'], nodes, linear, compliance, active,
                                               connected, source, np.ones(len(connected)))
        for name, observed in measured.items():
            lip_observed, wall_observed = observed[i, :2]
            pressure_observed = observed[i, 2:]
            excitation = inputs[name][i]
            theoretical = losses['theoretical'][name][i]
            observed_loss = losses['observed'][name][i]
            lip_parts = {key: lip[1:] * losses[key][name][i] for key in part_names}
            lip_branches = lip[1:] * theoretical
            sums = {key: values.sum() for key, values in lip_parts.items()}
            excitation_lip = lip[0] * excitation
            prediction = lip_branches.sum() + excitation_lip
            ratios = {key: float((value * lip_observed.conjugate()).real / abs(lip_observed)**2)
                      for key, value in sums.items()}
            rows.append({
                'frequency_hz': frequency, 'contrast': name, 'observed_lip_cm3_s': PAIR(lip_observed),
                'reconstructed_lip_cm3_s': PAIR(prediction), 'input_contribution_cm3_s': PAIR(excitation_lip),
                'source_parts_cm3_s': {key: PAIR(value) for key, value in sums.items()},
                'source_parts_projected_share': ratios,
                'reverse_projected_share': ratios['reverse_same_direction'] + ratios['reverse_changes_direction'],
                'lip_relative_error': relative_complex_error(prediction, lip_observed),
                'wall_relative_error': relative_complex_error(wall[0] * excitation + wall[1:] @ theoretical, wall_observed),
                'pressure_relative_error': FUNDAMENTAL.peak_relative(
                    pressure[:, 0] * excitation + pressure[:, 1:] @ theoretical, pressure_observed),
                'observed_loss_lip_relative_error': relative_complex_error(
                    lip[1:] @ observed_loss + excitation_lip, lip_observed),
                'decomposition_relative_error': float(abs(sum(sums.values()) - lip_branches.sum()) / abs(lip_observed)),
                'input_contribution_relative_to_lip': float(abs(excitation_lip) / abs(lip_observed)),
            })
            for rank, k in enumerate(np.argsort(-abs(lip_branches), kind='stable'), start=1):
                left, right = topology[connected[k], :2].astype(int)
                value = lip_branches[k]
                detail.append({
                    'frequency_hz': frequency, 'contrast': name, 'rank_by_magnitude': rank, 'branch': int(connected[k]),
                    'from': int(left), 'to': int(right), 'on_oral_path': bool(main[k]),
                    'lip_real_cm3_s': float(value.real), 'lip_imag_cm3_s': float(value.imag),
                    'projected_share': float((value * lip_observed.conjugate()).real / abs(lip_observed)**2),
                    **{f'{key}_{part}_cm3_s': float(getattr(values[k], part))
                       for key, values in lip_parts.items() for part in ('real', 'imag')},
                })
    return rows, detail


def relative_complex_error(predicted, observed):
    return float(abs(predicted - observed) / abs(observed))


def analyze_edition(cfg, projection, bins, traces, early, waves, model):
    nodes, topology, _, source, _, _, connected, _, _ = model
    inputs, losses, measured, stats = spectra(cfg, projection, bins, traces, waves, model)
    rows, detail = solve_contributions(cfg, model, inputs, losses, measured)
    early_changes, early_law, causal = {}, [], []
    for scale in JOBS:
        if scale == 0:
            continue
        delta, _, _, pressure_error = single.loss_changes(cfg, (early[0], early[scale]), model)
        first, order_ok = single.onset(cfg, early[0], early[scale], abs(traces[0]).max(axis=0),
                                       nodes, topology, source, connected, delta)
        early_changes[str(scale)] = first
        early_law.append(pressure_error)
        causal.append(order_ok)
    closure = ('lip_relative_error', 'wall_relative_error', 'pressure_relative_error',
               'observed_loss_lip_relative_error', 'decomposition_relative_error', 'input_contribution_relative_to_lip')
    conditions = {
        'first_changes_follow_causal_update': all(causal),
        'kinetic_balance': max(stats['kinetic_pressure_error'], *early_law) < cfg['kinetic_balance_peak_relative_error_lt'],
        'source_decomposition_and_dft': max(stats['split_pressure_error'], stats['dft_error'])
        < cfg['spectral_identity_relative_error_lt'],
        'all_complex_differences_reconstructed':
            all(row[key] < cfg['complex_reconstruction_relative_error_lt'] for row in rows for key in closure),
    }
    result = {'frequency_contrasts': rows, 'first_changes': early_changes, 'statistics': stats,
              'early_kinetic_pressure_error': max(early_law)}
    return conditions, result, detail


def branch_model(cfg, archive, geometry):
    nodes, topology, source = BRANCH.IMPULSE.source_elements(archive)
    rate = cfg['internal_rate_hz']
    compliance, active = BRANCH.IMPULSE.compliance_floor(nodes, topology, source, rate)
    connected = BRANCH.connected_links(topology, active, source['inject'])
    path = MEAN.airway_path(topology, active, source)
    main = np.isin(connected, path[:, 2])
    linear = topology.copy()
    linear[path[:, 2], 4] += 2 * MEAN.drag_on_path(path, geometry) * cfg['reference_flow_cm3_s']
    return (nodes, topology, geometry, source, compliance, active, connected, main, linear), path


def analyze(study, archive, out):
    cfg = study['measurement']
    _, geometry = MEAN.fixed.read_upper_geometry(archive['upstream-geometry.csv'])
    model, path = branch_model(cfg, archive, geometry)
    nodes, topology, _, source, _, _, connected, main, _ = model
    rate = cfg['internal_rate_hz']
    previous_cfg = READ(archive['amplitude-case.json'])['measurement']
    previous_summary = READ(archive['amplitude-summary.json'])
    cases = capture_cases(study, archive)
    start, end = cfg['window_samples']
    count = end - start
    frequencies = np.array(cfg['frequencies_hz'])
    bins = frequencies * count // rate
    projection = np.exp(-2j * np.pi * np.outer(bins, np.arange(count)) / count)
    waves = {scale: FUNDAMENTAL.flow_series(cases[job]) for scale, job in JOBS.items()}
    archived_block = np.diff(previous_cfg['steady_window_samples'])[0]
    checks = {
        'same_registered_inputs_geometry_and_windows': (
            all(READ(out / f'{job}.json') == case for job, case in cases.items())
            and all(cases[job]['body'] == cases[JOBS[0]]['body'] and cases[job]['posture'] == cases[JOBS[0]]['posture']
                    and cases[job]['fixed_airway']['sample_rate_hz'] == rate
                    and cases[job]['fixed_airway']['sample_count'] == end
                    and cases[job]['fixed_airway']['steady_flow_cm3_s'] == cfg['reference_flow_cm3_s']
                    and cases[job]['fixed_airway_periodic_flow']['start_sample'] == cfg['activation_sample']
                    and len(waves[scale]) == count for scale, job in JOBS.items())
            and count == archived_block and end == previous_cfg['warmup_samples'] + previous_cfg['periodic_blocks'] * archived_block
            and cfg['activation_sample'] == previous_cfg['warmup_samples']
            and cfg['early_window_samples'] == [cfg['activation_sample'] - 1,
                                                cfg['activation_sample'] + previous_cfg['after_onset_samples_to_keep']]
            and cfg['amplitude_scales'] == previous_cfg['amplitude_scales'] == sorted(JOBS)),
        'expected_connected_branches_and_coherent_bins': (
            len(connected) == cfg['expected_connected_branches']
            and len(path) == int(main.sum()) == cfg['expected_main_path_branches']
            and np.array_equal(path[:, :2], topology[path[:, 2], :2])
            and np.array_equal(bins * rate, frequencies * count)),
    }
    # トポロジーの照合は既存の通常発声・固定LFと同じ姿勢を基準にする。
    mapping = BRANCH.match_branch_indices(study, archive, out, topology, nodes, source, checks)
    offset = len(TRACE) + len(nodes)
    indices = np.r_[np.arange(offset), offset + np.array(mapping)]
    limit = cfg['complex_reconstruction_relative_error_lt']
    comparisons, conditions = {}, {}
    with (
        np.load(out / 'branch-states.npz', allow_pickle=False) as raw,
        np.load(archive['replay-traces.npz'], allow_pickle=False) as previous,
        np.load(archive['reference-branch-states.npz'], allow_pickle=False) as old_branches,
    ):
        aligned = {key: raw[key][:, indices] if key.endswith('_candidate') else raw[key] for key in raw.files}
        for job in cases:
            error = single.tangent.peak_error(aligned[f'{job}_candidate'], aligned[f'{job}_upstream'])
            comparisons[job] = error
            checks[f'{job}/matches_upstream_series'] = error < cfg['series_peak_relative_error_lt']
        for edition in BRANCH.EDITIONS:
            traces = {scale: aligned[f'{job}_{edition}'] for scale, job in JOBS.items()}
            early = {scale: aligned[f'{job}-onset_{edition}'] for scale, job in JOBS.items()}
            checks[f'{edition}/controls_match_archived_branch_samples'] = all(
                np.array_equal(raw[f'{JOBS[scale]}{suffix}_{edition}'].view(np.uint64),
                               old_branches[f'{arm}{suffix}_{edition}'].view(np.uint64))
                for scale, arm in ((0, 'lf'), (1, 'matched')) for suffix in ('', '-onset'))
            checks[f'{edition}/archived_lip_and_wall_samples_reproduced'] = all(
                np.array_equal(traces[scale][:, :len(TRACE)].view(np.uint64),
                               previous[f'{job}_{edition}'][-(count + 1):].view(np.uint64))
                and np.array_equal(early[scale][1:, :len(TRACE)].view(np.uint64),
                                   previous[f'{job}_{edition}_start'].view(np.uint64))
                and np.array_equal(early[scale][:1].view(np.uint64), early[0][:1].view(np.uint64))
                for scale, job in JOBS.items())
            verdicts, result, detail = analyze_edition(cfg, projection, bins, traces, early, waves, model)
            checks.update({f'{edition}/{name}': value for name, value in verdicts.items()})
            rows = result['frequency_contrasts']
            previous_lip = {row['frequency_hz']: row for row in previous_summary['conditions'][edition]['outputs']['flow_lips']}
            checks[f'{edition}/archived_odd_and_even_coefficients_reproduced'] = all(
                relative_complex_error(complex(*row['observed_lip_cm3_s']),
                                       complex(*previous_lip[row['frequency_hz']][row['contrast']])) < limit
                for row in rows if row['contrast'] in previous_lip[row['frequency_hz']])
            conditions[edition] = {
                **result,
                'hypothesis_reverse_projection': {
                    f'{row["frequency_hz"]}/{row["contrast"]}':
                        row['reverse_projected_share'] >= cfg['hypothesis_reverse_projected_share_ge']
                    for row in rows if row['contrast'].endswith('_gap')},
            }
            if edition == 'candidate':
                candidate_detail = detail
    return {'checks': {key: bool(value) for key, value in checks.items()}, 'conditions': conditions,
            'branch_series_comparisons': comparisons}, candidate_detail


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
        BRANCH.capture_cases(archive, out, execute, BRANCH.topology_case(study, archive), capture_cases(study, archive).items())
        result, rows = analyze(study, archive, out)
        (out / 'branch-contributions.csv').write_bytes(single.contribution_csv(rows))
        return result

    inputs = [CASE, Path(__file__), *archive.values(), *MEAN.shared.candidate_sources(), MEAN.sagittal.PROBE,
              *(Path(module.__file__) for module in (
                  amplitude, single, BRANCH, FUNDAMENTAL, single.tangent, BRANCH.periodic,
                  MEAN, MEAN.fixed, MEAN.impulse, MEAN.sagittal, MEAN.shared)),
              UPSTREAM / single.tangent.UPPER, UPSTREAM / 'crates/chimera/src/voice/human_voice.rs',
              UPSTREAM / 'crates/chimera/tests/airway_adversarial.rs', UPSTREAM / 'Cargo.lock']
    details = {'case_id': study['id'], 'case_revision': study['revision'], 'upstream_revision': revision,
               'invoked_from': str(Path.cwd())}
    return MEAN.shared.record_measurement(args.run_id, CASE, inputs, details, measure, command=None,
                                          input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
