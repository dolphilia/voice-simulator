"""確認用12発話でPCM変換前後の誤差順位を測る。"""

import argparse
from itertools import combinations
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

import numpy as np
from scipy.stats import rankdata

import measure_tsp_fk61_02_full_pcm_rounding as matched_pcm
from measure_tsp_mk61_02_full_pcm_rounding import error_ratios


prefix, radiation, tsp = matched_pcm.prefix, matched_pcm.radiation, matched_pcm.tsp
CASE = radiation.WORKSPACE / 'cases/tsp-held-out-pcm-rounding.json'
SOURCE_FIELDS = ('glottal_flow_cm3_s', *radiation.COMPONENTS, 'total_cm3_s', radiation.RADIATION)


def retained_files(study):
    return tuple(f"{row['recording_id']}/{filename}" for row in study['measurement']['cases']
                 for filename in matched_pcm.SAVED_FILES)


def utterance_measurement(measure, row):
    frames = row['frames']
    opening = measure['opening_frames']
    peak = row['expected_pcm_peak_frame']
    return row | {
        key: measure[key] for key in ('sample_rate_hz', 'internal_sample_rate_hz', 'block_frames',
                                     'initial_f0_hz', 'quiet_pcm_threshold', 'multi_ulp_minimum_quiet_share')
    } | {'prefix_frames': frames, 'pcm_outlier_to_exclude': peak,
         'focus_frames': [row['expected_pcm_first_difference'], peak],
         'segments': {'opening': [0, opening], 'later': [opening, frames]}}


def captures(study, config, specs, out, execute):
    measure = study['measurement']
    with TemporaryDirectory(prefix='tsp-rounding-corpus-', dir=out.parent / 'tmp') as directory:
        scratch = Path(directory)
        prepared = prefix.prepare_capture(study, None, scratch, out, execute, conditions=matched_pcm.CONDITIONS)
        for row in measure['cases']:
            uid = row['recording_id']
            dest = out / uid
            dest.mkdir()
            with TemporaryDirectory(prefix=f'{uid}-', dir=scratch) as work:
                prefix.capture_utterance(utterance_measurement(measure, row), config, specs[uid], prepared,
                                         Path(work), dest, execute, filename=matched_pcm.SAVED_FILES[0],
                                         source_fields=SOURCE_FIELDS)


def ranking(rows, statistic):
    values = {signal: np.array([row['comparison']['full'][signal][statistic] for row in rows.values()])
              for signal in ('precast', 'pcm')}
    precast, pcm = (rankdata(-values[key], method='average') for key in values)
    orders = np.array([(precast[i] - precast[j]) * (pcm[i] - pcm[j]) for i, j in combinations(range(len(rows)), 2)])
    return {
        'ranks': {uid: {'precast': float(a), 'pcm': float(b)} for uid, a, b in zip(rows, precast, pcm, strict=True)},
        'spearman': float(np.corrcoef(precast, pcm)[0, 1]) if np.ptp(precast) and np.ptp(pcm) else None,
        'inversions': int(np.count_nonzero(orders < 0)), 'concordant_pairs': int(np.count_nonzero(orders > 0)),
        'pairs_tied_in_either_metric': int(np.count_nonzero(orders == 0)),
    }


def analyze(study, out, archived_pcm, saved, specs, references, config, coefficients):
    measure = study['measurement']
    rows = {}
    for row in measure['cases']:
        uid = row['recording_id']
        voice = tsp.read(specs[uid])['speech_voice']
        if voice['body'] != row['body'] or voice['input']['id'] != uid:
            raise ValueError(f'保存済みの発話条件が登録と異なります ({uid})')
        definition = {'measurement': utterance_measurement(measure, row)}
        rows[uid] = matched_pcm.analyze_observation(
            definition, out / uid, archived_pcm, saved, config, voice['voice']['output_gain'],
            coefficients, source_fields=SOURCE_FIELDS)
    replicated = {}
    for uid, reference in references.items():
        measured = rows[uid]
        common_hypotheses = {key: reference['hypotheses'][key] for key in measured['hypotheses']}
        individual_observation = reference | {'hypotheses': common_hypotheses}
        replicated[uid] = all(value == individual_observation[key] for key, value in measured.items())
        if 'male_over_female' in reference:
            female = 'F' + uid[1:]
            ratios = error_ratios(measured['comparison'], rows[female]['comparison'])
            replicated[uid] &= ratios == reference['male_over_female']
    groups = {}
    for name in ('quiet', 'above_quiet'):
        groups[name] = {key: sum(row['amplitude_by_ulp']['groups'][name][key] for row in rows.values())
                        for key in ('frames', 'one_ulp', 'multiple_ulp')}
    multiple = sum(group['multiple_ulp'] for group in groups.values())
    quiet_share = groups['quiet']['multiple_ulp'] / multiple if multiple else None
    ranks = {key: ranking(rows, key) for key in ('rms', 'peak')}
    paired = {}
    for uid in rows:
        if not uid.startswith('F'):
            continue
        male = 'M' + uid[1:]
        result = {key: values['rms'] for key, values in
                  error_ratios(rows[male]['comparison'], rows[uid]['comparison']).items()}
        result['reverses_rms_order'] = (result['pcm'] - 1) * (result['precast'] - 1) < 0
        paired[f'{uid}:{male}'] = result
    ordered = sum(row['hypotheses']['precast_and_pcm_peak_differ'] for row in rows.values())
    checks = {
        'all_registered_utterances_replayed': list(rows) == list(saved['utterances'])
            and sum(row['comparison']['full']['pcm']['frames'] for row in rows.values()) == measure['total_frames'],
        **{key: all(row['checks'][key] for row in rows.values()) for key in next(iter(rows.values()))['checks']},
        'both_independent_utterance_runs_reproduced': bool(replicated) and all(replicated.values()),
    }
    hypotheses = {
        'precast_and_pcm_rms_rankings_have_inversions':
            ranks['rms']['inversions'] > 0 and any(row['reverses_rms_order'] for row in paired.values()),
        'most_utterances_have_separate_peak_frames': ordered >= measure['minimum_separate_peak_utterances'],
        'multi_ulp_differences_are_mainly_quiet_in_aggregate':
            quiet_share is not None and quiet_share >= measure['multi_ulp_minimum_quiet_share'],
    }
    return {'checks': checks, 'hypotheses': hypotheses, 'recording_ids': list(rows),
            'utterances': rows, 'ranking': ranks, 'same_text_rms_ratios': paired, 'separate_peak_frames': ordered,
            'groups_by_pcm_amplitude': groups, 'multiple_ulp_quiet_share': quiet_share,
            'independent_runs_reproduced': replicated}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    ws, upper = radiation.WORKSPACE, radiation.UPSTREAM
    study = tsp.read(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=upper, text=True).strip()
    if revision != study['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=upper):
        parser.error('変更のない固定上流版が必要です')
    if os.environ.get('CHIMERA_RUN_STORAGE') != 'rtl9210b':
        parser.error('試験ビルドにCHIMERA_RUN_STORAGE=rtl9210bを指定してください')
    matched, output = (tsp.open_run(study[key], revision) for key in ('matched', 'coefficients'))
    reproduction_runs = {uid: tsp.open_run(reference, revision) for uid, reference in study['reproductions'].items()}
    references = {uid: tsp.verified_path(run, 'summary.json') for uid, run in reproduction_runs.items()}
    specs = {row['recording_id']: tsp.verified_path(matched, f"artifacts/{row['recording_id']}/matched-case.json")
             for row in study['measurement']['cases']}
    config, config_path = radiation.saved_case(matched, prefix.lip.CONFIG)
    coeff = tsp.verified_path(output, 'artifacts/coefficients.json')
    archived = tsp.verified_path(matched, 'artifacts/matched-pcm.npz')
    saved = tsp.verified_path(matched, 'summary.json')
    inputs = [CASE, Path(__file__).resolve(), Path(matched_pcm.__file__), Path(matched_pcm.full.__file__),
              ws / 'tools/measure_tsp_mk61_02_full_pcm_rounding.py',
              *specs.values(), *references.values(), config_path, coeff, archived, saved, *prefix.capture_dependencies(),
              *(run[0] / 'manifest.json' for run in (matched, output, *reproduction_runs.values()))]

    def measure(out, execute):
        captures(study, config, specs, out, execute)
        return analyze(study, out, archived, tsp.read(saved), specs, {uid: tsp.read(path) for uid, path in references.items()},
                       config, tsp.read(coeff))

    details = {'case_id': study['id'], 'case_revision': study['revision'], 'upstream_revision': revision}
    return radiation.record_measurement(args.run_id, CASE, inputs, details, measure, command=None, input_root=ws.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
