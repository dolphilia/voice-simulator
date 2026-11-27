"""最初のMFCCアーカイブの圧縮がFK61_02の境界に与える影響を比較する。"""

import argparse
import os
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory

import numpy as np

import measure_tsp_again_initial_tip_mfa as single
import measure_tsp_matched_speech_mfa as aligned
import measure_tsp_phone_boundaries as mfa
import measure_tsp_stressed_vowel_formants as formants
import measure_tsp_tall_mfa_cmvn as cmvn
from measure_tsp_f2_bandwidth_held_out import saved_case
from measure_uniform_tube import record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/tsp-tall-mfcc-input-compression.json'
PROBE = WORKSPACE / 'tools/probe_mfa_mfcc_archive.py'


def observe(storage, cfg, root, corpus, dictionary, model, config, snapshot, out, tags, execute):
    out.mkdir()
    target = out / 'aligned'
    captured = out / 'features.npz'
    with TemporaryDirectory(prefix=f'mfcc-{storage}-', dir=out.parent.parent / 'tmp') as scratch:
        entry = [str(root / 'env/bin/python'), str(PROBE), storage, str(snapshot), str(captured)]
        mfa.mfa_run(root, config, corpus, dictionary, model, target, Path(scratch), execute, entry=entry)
    matrices = cmvn.read_features(captured, cfg)
    tiers = {name: mfa.tiers(target / tag / f'{tag}.json') for name, tag in tags.items()}
    intervals = {name: tier['phones'][single.phone_at_word(tier, cfg)] for name, tier in tiers.items()}
    bounds = cfg['local_feature_frames']
    differences = {name: {stage: cmvn.feature_differences(matrices[f'{a}_{stage}'], matrices[f'{b}_{stage}'], bounds)
                          for stage in cmvn.STAGES} for name, (a, b) in cmvn.PAIRS.items()}
    return matrices, tiers, {'archive_formats': formants.read(out / 'archive-formats.json'),
                             'independent_calculation': cmvn.independent_calculation(matrices, cfg),
                             'feature_differences': differences, 'tall_vowel_intervals': intervals,
                             'vs_control': {name: aligned.compare_intervals(tiers['control'], tier)
                                            for name, tier in tiers.items()}}


def copy_corpus(parent_case, paths, out):
    corpus = out / 'corpus'
    dictionary = out / 'synth.dict'
    shutil.copyfile(paths['dictionary'], dictionary)
    tags = {mode: f"{parent_case['utterance']}-{mode}" for mode in parent_case['measurement']['conditions']}
    input_copies = {dictionary: paths['dictionary']}
    for mode, tag in tags.items():
        folder = corpus / tag
        folder.mkdir(parents=True)
        for ext in ('wav', 'lab'):
            target = folder / f'{tag}.{ext}'
            shutil.copyfile(paths[f'{mode}_{ext}'], target)
            input_copies[target] = paths[f'{mode}_{ext}']
    return corpus, dictionary, tags, input_copies


def measure(case, parent_case, config, snapshot, paths, out, execute):
    cfg = parent_case['measurement']
    root = Path(config['environment_root'])
    model, _ = mfa.versions(root, config, out, execute)
    corpus, dictionary, tags, input_copies = copy_corpus(parent_case, paths, out)
    observations = {storage: observe(storage, cfg, root, corpus, dictionary, model, config, snapshot, out / storage, tags, execute)
                    for storage in case['archive_tokens']}
    standard, standard_tiers, _ = observations['compressed']
    lossless, _, outcome = observations['float32']
    archived = cmvn.read_features(paths['features'], cfg)
    checks = {
        'identical_audio_transcript_and_dictionary': all(sha256(copy) == sha256(source)
                                                        for copy, source in input_copies.items()),
        'standard_path_reproduces_archive': (all(np.array_equal(values, archived[key]) for key, values in standard.items())
            and all(tier == mfa.tiers(paths[f'{mode}_tier']) for mode, tier in standard_tiers.items())),
        'only_first_archive_encoding_changes': all(
            report['archive_formats'] == dict.fromkeys(cfg['conditions'], case['archive_tokens'][storage])
            for storage, (_, _, report) in observations.items()),
        'float32_archive_matches_direct_mfcc': all(
            np.array_equal(lossless[f'{mode}_input'], lossless[f'{mode}_uncompressed'])
            and np.array_equal(lossless[f'{mode}_uncompressed'], standard[f'{mode}_uncompressed']) for mode in cfg['conditions']),
        'independent_statistics_and_normalization': all(
            row['statistics_max_error'] <= cfg['statistics_absolute_tolerance']
            and row['normalization_max_error'] <= cfg['normalized_absolute_tolerance']
            and row['uses_registered_statistics'] and row['raw_audio_features_equal']
            for _, _, report in observations.values() for row in report['independent_calculation'].values()),
    }
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera-cli', 'compare::tsp::tests'],
            cwd=UPSTREAM, stdout=out / 'upstream-tsp-tests.log')
    changes = outcome['feature_differences']
    boundaries = outcome['tall_vowel_intervals']
    return {'checks': checks, 'predictions': {
                'input_differences_reduce_to_first_six_frames': changes['own_stats']['input']['changed_frames'] == 6
                    and changes['own_stats']['input']['first_frame'] == 0 and changes['own_stats']['input']['last_frame'] == 5,
                'shared_statistics_remove_local_normalized_difference':
                    changes['both_control_stats']['normalized']['local_maximum'] == 0,
                'shared_statistics_restore_control_boundary': boundaries['preroll_control_stats'][1] == boundaries['control'][1]},
            'observations': {name: report for name, (_, _, report) in observations.items()}}


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
    parent_case, snapshot = saved_case(parent, cmvn.CASE)
    config = parent[1]['aligner']
    site = Path(config['environment_root']) / 'env/lib/python3.11/site-packages'
    if any(sha256(site / name) != digest for name, digest in parent_case['environment_sources'].items()):
        parser.error('MFAまたはKalpyのソースが登録条件と一致しません')
    outputs = {'features': 'features.npz', 'dictionary': 'synth.dict'}
    for mode in parent_case['measurement']['conditions']:
        tag = f"{parent_case['utterance']}-{mode}"
        for ext in ('wav', 'lab'):
            outputs[f'{mode}_{ext}'] = f'corpus/{tag}/{tag}.{ext}'
        outputs[f'{mode}_tier'] = f'aligned/{tag}/{tag}.json'
    paths = {key: formants.verified_path(parent, f'artifacts/{name}') for key, name in outputs.items()}
    helpers = (PROBE, cmvn.PROBE, *(Path(module.__file__) for module in (cmvn, formants, single, aligned, mfa)))
    inputs = [CASE, Path(__file__).resolve(), snapshot, parent[0] / 'manifest.json', *paths.values(), *helpers,
              UPSTREAM / formants.TSP_SOURCE, UPSTREAM / config['configuration']]
    details = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision, 'aligner': config}
    return record_measurement(args.run_id, CASE, inputs, details, lambda out, execute: measure(
        case, parent_case, config, snapshot, paths, out, execute), command=None, input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
