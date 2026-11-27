"""同じ周期声門流量を固定 /i/ へ与え、口端の差を枝圧力から再構成する。"""

import argparse
import csv
from pathlib import Path
import re
import subprocess

import numpy as np

import measure_fixed_alpha_lf_fundamental_amplitude_branch_loss as parity
from measure_fan_crossing_allocations import run_manifest, verified_path
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/fixed-vowel-i-lf-branch-loss.json'
ROOT = WORKSPACE.parents[2]
READ, BRANCH, MEAN = parity.READ, parity.BRANCH, parity.MEAN
JOBS, TRACE = parity.JOBS, parity.TRACE
EVIDENCE = (*parity.EVIDENCE, 'upstream-geometry.csv')


def archive_inputs(study):
    sources = {}
    for key in ('alpha', 'pose', 'network'):
        spec = study[f'{key}_reference']
        run, header = sources[key] = run_manifest(spec['run'], spec['case'], study['upstream_revision'])
        if header['status'] != 'pass' or sha256(run / 'manifest.json') != spec['manifest_sha256']:
            raise ValueError(f'登録済みの参照実行と一致しません ({run.name})')
    alpha_run, alpha = sources['alpha']
    row, = (item for item in alpha['inputs'] if item['path'].endswith('/upstream-geometry.csv'))
    alpha_geometry = ROOT / row['path']
    if sha256(alpha_geometry) != row['sha256']:
        raise ValueError('固定 /ɑ/ の幾何と保存した入力が一致しません')
    network_run, network = sources['network']
    row, = (item for item in network['inputs'] if item['path'] == 'cases/vowel-transfer-i.json')
    network_case = network_run / network['source_snapshot'] / row['path']
    if sha256(network_case) != row['sha256']:
        raise ValueError('固定 /i/ の線形要素と保存した姿勢の照合に失敗しました')
    return {
        **{f'{key}-manifest.json': run / 'manifest.json' for key, (run, _) in sources.items()},
        'alpha-summary.json': verified_path(sources['alpha'], 'summary.json'),
        'alpha-contributions.csv': verified_path(sources['alpha'], 'artifacts/branch-contributions.csv'),
        'alpha-geometry.csv': alpha_geometry,
        'i-pose.json': verified_path(sources['pose'], 'artifacts/pose.json'),
        'network-case.json': network_case,
        **{name: verified_path(sources['network'], f'artifacts/{name}')
           for name in BRANCH.IMPULSE.harmonic.NETWORK_FILES},
        **{f'{job}.json': verified_path((alpha_run, alpha), f'artifacts/{job}.json') for job in JOBS.values()},
    }


def capture_definitions(study, archive):
    posture = READ(archive['i-pose.json'])['posture']
    cases = {job: {**case, 'posture': posture}
             for job, case in parity.capture_cases(study, archive).items()}
    cfg = study['measurement']
    lo, hi = cfg['frequencies_hz']
    topology = {**cases[JOBS[0]], 'transfer': {'start_hz': lo, 'end_hz': hi, 'points': 2}}
    topology.pop('fixed_airway_periodic_flow')
    return topology, cases


def add_location(rows, sections):
    path = sorted({(row['from'], row['to']) for row in rows if row['on_oral_path']})
    distance, expected = 0., path[0][0]
    boundaries = {}
    for left, right in path:
        if left != expected:
            raise ValueError('咽頭入口から口端への枝が連続していません')
        width = float(sections[left]['cell_length_cm'])
        boundaries[left, right] = distance + width / 2
        distance += (width + float(sections[right]['cell_length_cm'])) / 2
        expected = right
    for row in rows:
        left, right = row['from'], row['to']
        row.update({'from_tube': sections[left]['tube'], 'to_tube': sections[right]['tube'],
                    'distance_from_inlet_cm': boundaries.get((left, right))})


def compare_shapes(cfg, current, candidate_detail, archive):
    alpha_report = READ(archive['alpha-summary.json'])['conditions']['candidate']['frequency_contrasts']
    keys = ('from', 'to', 'frequency_hz', 'rank_by_magnitude')
    with archive['alpha-contributions.csv'].open(newline='') as stream:
        alpha_detail = [{**row, **{key: int(row[key]) for key in keys}, 'on_oral_path': row['on_oral_path'] == 'True',
                         'projected_share': float(row['projected_share'])} for row in csv.DictReader(stream)]
    alpha_sections, _ = MEAN.fixed.read_upper_geometry(archive['alpha-geometry.csv'])
    add_location(alpha_detail, alpha_sections)
    alpha = {(row['frequency_hz'], row['contrast']): row for row in alpha_report}
    top = ('from', 'to', 'from_tube', 'to_tube', 'distance_from_inlet_cm', 'projected_share')
    comparisons = []
    for row in current['frequency_contrasts']:
        frequency, name = row['frequency_hz'], row['contrast']
        if not name.endswith('_gap'):
            continue
        comparison = {'frequency_hz': frequency, 'contrast': name}
        for vowel, stats, detail in (('alpha', alpha[frequency, name], alpha_detail),
                                     ('i', row, candidate_detail)):
            ranked = [{key: change[key] for key in top} for change in detail
                      if (change['frequency_hz'], change['contrast']) == (frequency, name)
                      and change['rank_by_magnitude'] <= cfg['top_ranked_branches']]
            comparison[vowel] = {
                'lip_magnitude_cm3_s': abs(complex(*stats['observed_lip_cm3_s'])),
                'direction_change_projected_share': stats['source_parts_projected_share']['reverse_changes_direction'],
                'ranked_branches': ranked,
            }
        comparisons.append(comparison)
    return comparisons


def analyze(study, archive, out):
    cfg = study['measurement']
    sections, geometry = MEAN.fixed.read_upper_geometry(out / 'upstream-geometry.csv')
    model, path = parity.branch_model(cfg, archive, geometry)
    nodes, branches, _, source, _, _, connected, _, _ = model
    topology, cases = capture_definitions(study, archive)
    pose, network = READ(archive['i-pose.json']), READ(archive['network-case.json'])
    rate, (start, end) = cfg['internal_rate_hz'], cfg['window_samples']
    count = end - start
    frequencies = np.array(cfg['frequencies_hz'])
    bins = frequencies * count // rate
    projection = np.exp(-2j * np.pi * np.outer(bins, np.arange(count)) / count)
    waves = {scale: parity.FUNDAMENTAL.flow_series(cases[job]) for scale, job in JOBS.items()}
    checks = {
        'archived_pose_and_all_waveforms_reproduced': (
            pose['body'] == network['body'] == topology['body']
            and pose['posture'] == network['posture'] == topology['posture']
            and pose['fixed_airway']['sample_rate_hz'] == network['fixed_airway']['sample_rate_hz'] == rate
            and all(READ(out / f'{job}.json') == case for job, case in cases.items())
            and all(case['fixed_airway']['sample_count'] == end
                    and case['fixed_airway']['sample_rate_hz'] == rate
                    and case['fixed_airway']['steady_flow_cm3_s'] == cfg['reference_flow_cm3_s']
                    and case['fixed_airway_periodic_flow']['start_sample'] == cfg['activation_sample']
                    for case in cases.values())
            and all(len(wave) == count for wave in waves.values())
            and cfg['amplitude_scales'] == sorted(JOBS)),
        'expected_connected_branches_and_coherent_bins': (
            len(connected) == cfg['expected_connected_branches'] and len(path) == cfg['expected_main_path_branches']
            and np.array_equal(path[:, :2], branches[path[:, 2], :2])
            and np.array_equal(bins * rate, frequencies * count)),
        'upstream_geometry_matches_archived_linear_elements': (
            np.allclose(geometry[:, -1], nodes[:, 0], rtol=cfg['topology_element_relative_error_lt'], atol=0)
            and all(float(row['velum_port_cm2']) == 0 and int(row['branch_count']) == len(branches)
                    for row in sections)),
    }
    mapping = BRANCH.align_branch_indices(study, out, branches, nodes, source, checks, topology, cases.values())
    offset = len(TRACE) + len(nodes)
    indices = np.r_[np.arange(offset), offset + np.array(mapping)]
    results, series_errors = {}, {}
    with np.load(out / 'branch-states.npz', allow_pickle=False) as raw:
        aligned = {key: raw[key][:, indices] if key.endswith('_candidate') else raw[key] for key in raw.files}
        for job in cases:
            error = parity.single.tangent.peak_error(aligned[f'{job}_candidate'], aligned[f'{job}_upstream'])
            series_errors[job] = error
            checks[f'{job}/matches_upstream_series'] = error < cfg['series_peak_relative_error_lt']
        for edition in BRANCH.EDITIONS:
            traces = {scale: aligned[f'{job}_{edition}'] for scale, job in JOBS.items()}
            early = {scale: aligned[f'{job}-onset_{edition}'] for scale, job in JOBS.items()}
            checks[f'{edition}/state_before_activation_is_identical'] = all(
                np.array_equal(trace[:1].view(np.uint64), early[0][:1].view(np.uint64)) for trace in early.values())
            verdicts, results[edition], detail = parity.analyze_edition(cfg, projection, bins, traces, early, waves, model)
            checks.update({f'{edition}/{name}': value for name, value in verdicts.items()})
            if edition == 'candidate':
                candidate_detail = detail
    add_location(candidate_detail, sections)
    comparisons = compare_shapes(cfg, results['candidate'], candidate_detail, archive)
    oral_counts = {vowel: sum(any(edge['from_tube'] == edge['to_tube'] == 'oral' for edge in row[vowel]['ranked_branches'])
                             for row in comparisons) for vowel in ('alpha', 'i')}
    thresholds = {'contrasts_with_oral_branch': oral_counts,
                  'i_oral_branch_hypothesis': oral_counts['i'] >= cfg['hypothesis_contrasts_with_oral_branch_ge'],
                  'i_direction_change_hypotheses': {
                      f'{row["frequency_hz"]}/{row["contrast"]}': row['i']['direction_change_projected_share']
                      >= cfg['hypothesis_direction_change_projected_share_ge'] for row in comparisons}}
    return ({'checks': {key: bool(value) for key, value in checks.items()}, 'conditions': results,
             'branch_series_comparisons': series_errors, 'shape_comparison': comparisons,
             'hypotheses': thresholds}, candidate_detail)


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
        topology, cases = capture_definitions(study, archive)
        BRANCH.capture_cases(archive, out, execute, topology, cases.items(), save_geometry=True)
        result, rows = analyze(study, archive, out)
        (out / 'branch-contributions.csv').write_bytes(parity.single.contribution_csv(rows))
        return result

    inputs = [CASE, Path(__file__), *archive.values(), *MEAN.shared.candidate_sources(), MEAN.sagittal.PROBE,
              *(Path(module.__file__) for module in (parity, parity.amplitude, parity.single, BRANCH,
                parity.FUNDAMENTAL, parity.single.tangent, BRANCH.periodic, MEAN, MEAN.fixed,
                MEAN.impulse, MEAN.sagittal, MEAN.shared)),
              UPSTREAM / parity.single.tangent.UPPER, UPSTREAM / 'crates/chimera/src/voice/human_voice.rs',
              UPSTREAM / 'crates/chimera/tests/airway_adversarial.rs', UPSTREAM / 'Cargo.lock']
    details = {'case_id': study['id'], 'case_revision': study['revision'], 'upstream_revision': revision,
               'invoked_from': str(Path.cwd())}
    return MEAN.shared.record_measurement(args.run_id, CASE, inputs, details, measure, command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
