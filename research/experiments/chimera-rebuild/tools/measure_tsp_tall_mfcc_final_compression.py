"""最終MFCCの圧縮がFK61_02の特徴量と境界に与える影響を比較する。"""

import argparse
import os
from pathlib import Path
import subprocess

import numpy as np

import measure_tsp_matched_speech_mfa as aligned
import measure_tsp_phone_boundaries as mfa
import measure_tsp_stressed_vowel_formants as formants
import measure_tsp_tall_mfa_cmvn as cmvn
import measure_tsp_tall_mfcc_input_compression as mfcc
from measure_tsp_f2_bandwidth_held_out import saved_case
from measure_uniform_tube import record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/tsp-tall-mfcc-final-compression.json'
BASELINE = 'float32'
LOSSLESS = 'float32_both'


def measure(case, cmvn_case, config, snapshot, paths, out, execute):
    cfg = cmvn_case['measurement']
    root = Path(config['environment_root'])
    model, _ = mfa.versions(root, config, out, execute)
    corpus, dictionary, tags, input_copies = mfcc.copy_corpus(cmvn_case, paths, out)
    observations = {storage: mfcc.observe(storage, cfg, root, corpus, dictionary, model, config, snapshot,
                                          out / storage, tags, execute) for storage in case['archive_tokens']}
    standard, standard_tiers, _ = observations[BASELINE]
    lossless, lossless_tiers, outcome = observations[LOSSLESS]
    archived = cmvn.read_features(paths['features'], cfg)
    checks = {
        'identical_audio_transcript_and_dictionary': all(sha256(copy) == sha256(source)
                                                        for copy, source in input_copies.items()),
        'compressed_final_reproduces_archive': (
            all(np.array_equal(values, archived[key]) for key, values in standard.items())
            and all(tier == mfa.tiers(paths[f'{mode}_tier']) for mode, tier in standard_tiers.items())),
        'only_final_archive_encoding_changes': all(
            report['archive_formats'] == dict.fromkeys(cfg['conditions'], case['archive_tokens'][storage])
            for storage, (_, _, report) in observations.items()),
        'everything_until_final_archive_matches': all(
            np.array_equal(values, lossless[key]) for key, values in standard.items() if not key.endswith('_final')),
        'lossless_final_matches_normalized_features': all(
            np.array_equal(lossless[f'{mode}_final'], lossless[f'{mode}_normalized']) for mode in cfg['conditions']),
        'independent_statistics_and_normalization': all(
            row['statistics_max_error'] <= cfg['statistics_absolute_tolerance']
            and row['normalization_max_error'] <= cfg['normalized_absolute_tolerance']
            and row['uses_registered_statistics'] and row['raw_audio_features_equal']
            for _, _, report in observations.values() for row in report['independent_calculation'].values()),
    }
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera-cli', 'compare::tsp::tests'],
            cwd=UPSTREAM, stdout=out / 'upstream-tsp-tests.log')
    contrast = outcome['feature_differences']['both_control_stats']['final']
    count = case['measurement']['expected_preroll_difference_frames']
    boundaries = outcome['tall_vowel_intervals']
    return {'checks': checks, 'predictions': {
                'shared_stats_final_difference_is_local_to_preroll': (
                    contrast['changed_frames'] == count and contrast['first_frame'] == 0
                    and contrast['last_frame'] == count - 1 and contrast['local_maximum'] == 0),
                'shared_stats_tall_boundaries_match': boundaries['control'][1] == boundaries['preroll_control_stats'][1],
                'tall_control_returns_to_legacy_boundary':
                    boundaries['control'][1] == case['measurement']['legacy_control_end_seconds']},
            'observations': {name: report for name, (_, _, report) in observations.items()},
            'final_archive_effect': {mode: cmvn.feature_differences(standard[f'{mode}_final'], lossless[f'{mode}_final'],
                                                                   cfg['local_feature_frames']) for mode in cfg['conditions']},
            'tier_changes_when_final_encoding_changes': {
                mode: aligned.compare_intervals(standard_tiers[mode], lossless_tiers[mode]) for mode in cfg['conditions']}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    if os.environ.get('CHIMERA_RUN_STORAGE') != 'rtl9210b':
        parser.error('MFAの作業領域は CHIMERA_RUN_STORAGE=rtl9210b を指定してください')
    case = formants.read(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    parent = formants.open_run(case['parent'], revision)
    parent_case, parent_snapshot = saved_case(parent, mfcc.CASE)
    normalizer = formants.open_run(parent_case['parent'], revision)
    cmvn_case, cmvn_snapshot = saved_case(normalizer, cmvn.CASE)
    config = parent[1]['aligner']
    site = Path(config['environment_root']) / 'env/lib/python3.11/site-packages'
    if config != normalizer[1]['aligner'] or any(
            sha256(site / name) != digest for name, digest in cmvn_case['environment_sources'].items()):
        parser.error('MFAの条件またはソースが登録値と一致しません')
    outputs = {'features': f'{BASELINE}/features.npz', 'dictionary': 'synth.dict'}
    for mode in cmvn_case['measurement']['conditions']:
        tag = f"{cmvn_case['utterance']}-{mode}"
        for ext in ('wav', 'lab'):
            outputs[f'{mode}_{ext}'] = f'corpus/{tag}/{tag}.{ext}'
        outputs[f'{mode}_tier'] = f'{BASELINE}/aligned/{tag}/{tag}.json'
    paths = {key: formants.verified_path(parent, f'artifacts/{name}') for key, name in outputs.items()}
    helpers = (mfcc.PROBE, cmvn.PROBE, *(Path(module.__file__) for module in (mfcc, cmvn, formants, aligned, mfa)))
    inputs = [CASE, Path(__file__).resolve(), parent_snapshot, cmvn_snapshot,
              parent[0] / 'manifest.json', normalizer[0] / 'manifest.json', *paths.values(), *helpers,
              UPSTREAM / formants.TSP_SOURCE, UPSTREAM / config['configuration']]
    details = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision, 'aligner': config}
    return record_measurement(args.run_id, CASE, inputs, details, lambda out, execute: measure(
        case, cmvn_case, config, cmvn_snapshot, paths, out, execute), command=None, input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    main()
