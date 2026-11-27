"""確認用発話FK61_02の通常レンダーで、変換前とPCMの誤差を照合する。"""

import argparse
import os
from pathlib import Path
import subprocess

import numpy as np

import measure_tsp_fk61_full_pcm_rounding as full


prefix, lip, radiation, tsp, pcm = full.prefix, full.lip, full.radiation, full.tsp, full.pcm
CASE = radiation.WORKSPACE / 'cases/tsp-fk61-02-full-pcm-rounding.json'
SAVED_FILES = full.SAVED_FILES
CONDITIONS = ('upstream_normal', 'research_normal')


def amplitude_groups(upstream, research, limit):
    ulps = np.abs(full.sample_rank(upstream) - full.sample_rank(research))
    amplitude = np.maximum(np.abs(upstream.astype(np.float64)), np.abs(research.astype(np.float64)))
    multi = ulps > 1
    groups = {}
    for name, mask in (('quiet', amplitude <= limit), ('above_quiet', amplitude > limit)):
        groups[name] = {
            'frames': int(np.count_nonzero(mask)),
            'one_ulp': int(np.count_nonzero((ulps == 1) & mask)),
            'multiple_ulp': int(np.count_nonzero(multi & mask)),
        }
    locations = np.flatnonzero(multi)
    return {'threshold': limit, 'groups': groups, 'multiple_ulp_quiet_fraction':
                float(np.mean(amplitude[locations] <= limit)) if len(locations) else None,
            'multiple_ulp_maximum_amplitude': float(amplitude[locations].max()) if len(locations) else None,
            'multiple_ulp_first_frame': int(locations[0]) if len(locations) else None}


def matched_reference(current, proof, archived, measure):
    return {
        name: proof[name]['bit_equal']
            and proof[name]['ordinary'] == proof[name]['probe'] == lip.pcm_digest(current[f'{name}_pcm'])
            and len(current[f'{name}_pcm']) == measure['frames']
            and lip.bit_equal(current[f'{name}_pcm'], archived[archive])
        for name, archive in zip(CONDITIONS, ('upstream', 'candidate'), strict=True)
    }


def analyze_observation(study, out, saved_pcm, saved_summary, config, gain, coeff, *, source_fields=radiation.FIELDS):
    measure = study['measurement']
    uid = measure['recording_id']
    with np.load(out / SAVED_FILES[0], allow_pickle=False) as stream:
        current = dict(stream)
    states = {name: dict(zip(source_fields, current[f'{name}_source'].T, strict=True)) for name in CONDITIONS}
    replay = prefix.exact_output_replays(current, states, measure, config, gain, coeff, conditions=CONDITIONS)
    archive_matches = matched_reference(current, tsp.read(out / SAVED_FILES[1]), pcm.archived_pcm(saved_pcm, uid), measure)
    upstream, research = (current[f'{name}_pcm'] for name in CONDITIONS)
    different_bits = np.flatnonzero(upstream.view('<u4') != research.view('<u4'))
    actual = {'different_bits': len(different_bits),
              'first_bit_difference': int(different_bits[0]) if len(different_bits) else None}
    poles = (coeff['upstream']['dc_pole'], coeff['candidate']['dc_pole'])
    comparison = full.compare(*CONDITIONS, current, measure, poles)
    actual['peak_frame'] = comparison['full']['pcm']['peak_frame']
    reference = saved_summary['utterances'][uid]['matched_pcm']
    expected = {'different_bits': measure['expected_pcm_different_bits'],
                'first_bit_difference': measure['expected_pcm_first_difference'],
                'peak_frame': measure['expected_pcm_peak_frame']}
    amplitude = amplitude_groups(upstream, research, measure['quiet_pcm_threshold'])
    left, right = (states[name] for name in CONDITIONS)
    internal = {field: full.metrics(right[field] - left[field])
                for field in ('glottal_flow_cm3_s', *radiation.COMPONENTS, 'total_cm3_s', radiation.RADIATION)}
    left, right = (current[f'{name}_output'] for name in CONDITIONS)
    output = {field: full.metrics(right[:, i] - left[:, i])
              for i, field in enumerate(pcm.COLUMNS[2:], start=2)}
    peak = comparison['witnesses'][str(actual['peak_frame'])]
    source_first = internal[radiation.RADIATION]['first_nonzero_frame']
    precast_first = comparison['full']['precast']['first_nonzero_frame']
    pcm_first = actual['first_bit_difference']
    ratio = measure['internal_sample_rate_hz'] // measure['sample_rate_hz']
    checks = {
        'ordinary_probe_and_archived_pcm_equal_for_each_side': all(archive_matches.values()),
        'full_trace_output_recalculated_with_limiter_inactive': all(replay.values()),
        'archived_first_peak_and_unequal_count_reproduced': actual == expected
            and actual == {key: reference[key] for key in actual},
        'full_pcm_precast_conversion_and_adjacent_midpoints': comparison['pcm_all_one_ulp_straddle']
            and all(lip.bit_equal(current[f'{name}_output'][:, full.DC].astype('<f4'), current[f'{name}_pcm'])
                    for name in CONDITIONS),
    }
    hypotheses = {
        'precast_and_pcm_peak_differ': comparison['full']['precast']['peak_frame'] != actual['peak_frame'],
        'largest_pcm_difference_is_one_ulp': peak['ulp_distance'] == 1 and peak['from_midpoint'] is not None
            and min(peak['from_midpoint']) < 0 < max(peak['from_midpoint']),
        'multi_ulp_differences_are_mainly_quiet': amplitude['multiple_ulp_quiet_fraction'] is not None
            and amplitude['multiple_ulp_quiet_fraction'] >= measure['multi_ulp_minimum_quiet_share'],
        'radiation_and_precast_differ_before_pcm': None not in (source_first, precast_first, pcm_first)
            and source_first // ratio < pcm_first and precast_first < pcm_first,
    }
    return {'checks': checks, 'hypotheses': hypotheses, 'matched_pcm': actual, 'archive_matches': archive_matches,
            'output_replay': replay, 'comparison': comparison, 'amplitude_by_ulp': amplitude,
            'radiation_and_source_differences': internal, 'output_stage_differences': output,
            'max_envelope': {name: float(np.max(current[f'{name}_output'][:, pcm.COLUMNS.index('envelope')]))
                             for name in CONDITIONS}}


def analyze(study, out, saved_pcm, saved_summary, previous_summary, config, gain, coeff):
    result = analyze_observation(study, out, saved_pcm, saved_summary, config, gain, coeff)
    prior = previous_summary['comparisons']['indexed:indexed']
    result['fk61_01_indexed_comparison'] = {key: prior[key] for key in ('full', 'pcm_one_ulp', 'pcm_more_than_one_ulp')}
    return result


def run_case(case, analyze_case, description, *, entrypoint):
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument('run_id')
    args = parser.parse_args()
    ws, upper = radiation.WORKSPACE, radiation.UPSTREAM
    study = tsp.read(case)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=upper, text=True).strip()
    if revision != study['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=upper):
        parser.error('変更のない固定上流版が必要です')
    if os.environ.get('CHIMERA_RUN_STORAGE') != 'rtl9210b':
        parser.error('試験ビルドにCHIMERA_RUN_STORAGE=rtl9210bを指定してください')
    matched, output, prior = (tsp.open_run(study[key], revision) for key in ('matched', 'coefficients', 'comparison'))
    uid = study['measurement']['recording_id']
    spec = tsp.verified_path(matched, f'artifacts/{uid}/matched-case.json')
    config, config_path = radiation.saved_case(matched, lip.CONFIG)
    coeff = tsp.verified_path(output, 'artifacts/coefficients.json')
    archived = tsp.verified_path(matched, 'artifacts/matched-pcm.npz')
    saved_summary = tsp.verified_path(matched, 'summary.json')
    previous_summary = tsp.verified_path(prior, 'summary.json')
    inputs = [case, entrypoint, Path(__file__).resolve(), Path(full.__file__), spec, config_path, archived, saved_summary,
              coeff, previous_summary, *prefix.capture_dependencies(),
              *(run[0] / 'manifest.json' for run in (matched, output, prior))]

    def measure(out, execute):
        prefix.capture(study, config, spec, None, out, execute, filename=SAVED_FILES[0], conditions=CONDITIONS)
        gain = tsp.read(spec)['speech_voice']['voice']['output_gain']
        return analyze_case(study, out, archived, tsp.read(saved_summary), tsp.read(previous_summary),
                            config, gain, tsp.read(coeff))

    details = {'case_id': study['id'], 'case_revision': study['revision'], 'upstream_revision': revision}
    return radiation.record_measurement(args.run_id, case, inputs, details, measure, command=None, input_root=ws.parents[2])


def main():
    return run_case(CASE, analyze, __doc__, entrypoint=Path(__file__).resolve())


if __name__ == '__main__':
    raise SystemExit(main())
