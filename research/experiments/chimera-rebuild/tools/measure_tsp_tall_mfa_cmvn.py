"""MFAでFK61_02のCMVN統計だけを入れ替え、特徴量とtallの境界を比較する。"""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
from zipfile import ZipFile

import numpy as np

import measure_tsp_again_initial_tip_mfa as single
import measure_tsp_matched_speech_mfa as aligned
import measure_tsp_phone_boundaries as mfa
import measure_tsp_stressed_vowel_formants as formants
from measure_uniform_tube import record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/tsp-tall-mfa-cmvn.json'
PROBE = WORKSPACE / 'tools/probe_mfa_cmvn.py'
STAGES = ('uncompressed', 'input', 'normalized', 'final')
PAIRS = {'own_stats': ('control', 'old_preroll'),
         'both_control_stats': ('control', 'preroll_control_stats'),
         'both_preroll_stats': ('control_preroll_stats', 'old_preroll'),
         'statistics_only': ('control', 'control_preroll_stats')}


def feature_differences(left, right, bounds):
    delta = np.abs(left.astype(float) - right)
    different = np.flatnonzero(np.any(delta != 0, axis=1))
    begin, end = bounds
    return {'first_frame': int(different[0]) if different.size else None,
            'last_frame': int(different[-1]) if different.size else None,
            'changed_frames': int(different.size), 'maximum': float(delta.max()),
            'local_maximum': float(delta[begin:end].max())}


def read_features(path, cfg):
    with np.load(path, allow_pickle=False) as archive:
        matrices = {key: archive[key] for key in archive.files}
    expected = {f'{mode}_{stage}': (cfg['feature_frames'], cfg['coefficients'])
                for mode in cfg['conditions'] for stage in STAGES}
    expected |= {f'{mode}_{name}': (2, cfg['coefficients'] + 1)
                 for mode in cfg['conditions'] for name in ('own_stats', 'used_stats')}
    if matrices.keys() != expected.keys() or any(
            values.shape != expected[key] or not np.isfinite(values).all() for key, values in matrices.items()):
        raise ValueError('採取した特徴量・統計の配列が登録した寸法と一致しません')
    return matrices


def independent_calculation(matrices, cfg):
    outcomes = {}
    for mode, selection in cfg['conditions'].items():
        data = matrices[f'{mode}_input']
        own = matrices[f'{mode}_own_stats']
        used = matrices[f'{mode}_used_stats']
        total = data.sum(axis=0, dtype=np.float64)
        square_total = np.square(data, dtype=cfg['statistics_square_dtype']).sum(axis=0, dtype=np.float64)
        expected = np.column_stack((np.stack((total, square_total)), (len(data), 0)))
        predicted = data.astype(float) - used[0, :-1] / used[0, -1]
        outcomes[mode] = {
            'statistics_max_error': float(np.max(np.abs(own - expected))),
            'normalization_max_error': float(np.max(np.abs(matrices[f'{mode}_normalized'] - predicted))),
            'uses_registered_statistics': np.array_equal(used, matrices[f"{selection['statistics']}_own_stats"]),
            'raw_audio_features_equal': all(np.array_equal(matrices[f'{mode}_{stage}'],
                matrices[f"{selection['audio']}_{stage}"]) for stage in ('uncompressed', 'input')),
        }
    return outcomes


def measure(case, config, paths, out, execute):
    cfg = case['measurement']
    uid = case['utterance']
    root = Path(config['environment_root'])
    model, _ = mfa.versions(root, config, out, execute)
    with ZipFile(model) as archive:
        model_features = json.loads(archive.read('english_us_arpa/meta.json'))['features']
    if any(model_features.get(key) != value for key, value in cfg['model_features'].items()):
        raise ValueError('音響モデルの特徴量設定が登録値と一致しません')
    corpus = out / 'corpus'
    dictionary = out / 'synth.dict'
    shutil.copyfile(paths['dictionary'], dictionary)
    tags = {}
    for mode, selection in cfg['conditions'].items():
        tags[mode] = tag = f'{uid}-{mode}'
        folder = corpus / tag
        folder.mkdir(parents=True)
        for ext in ('wav', 'lab'):
            shutil.copyfile(paths[f"{selection['audio']}_{ext}"], folder / f'{tag}.{ext}')
    probe_out = out / 'features.npz'
    target = out / 'aligned'
    with TemporaryDirectory(prefix='tall-cmvn-', dir=out.parent / 'tmp') as directory:
        entry = [str(root / 'env/bin/python'), str(PROBE), str(CASE), str(probe_out)]
        mfa.mfa_run(root, config, corpus, dictionary, model, target, Path(directory), execute, entry=entry)
    matrices = read_features(probe_out, cfg)
    comparison = independent_calculation(matrices, cfg)
    tiers = {name: mfa.tiers(target / tag / f'{tag}.json') for name, tag in tags.items()}
    intervals = {name: result['phones'][single.phone_at_word(result, cfg)] for name, result in tiers.items()}
    bounds = cfg['local_feature_frames']
    feature_delta = {name: {stage: feature_differences(matrices[f'{a}_{stage}'], matrices[f'{b}_{stage}'], bounds)
                            for stage in STAGES} for name, (a, b) in PAIRS.items()}
    left, right = (aligned.wave_samples(paths[f'{mode}_wav'], cfg['sample_rate_hz'], np.int16)
                   for mode in ('control', 'old_preroll'))
    begin, end = cfg['local_pcm_frames']
    checks = {
        'inputs_preserved': all(sha256(corpus / tag / f'{tag}.{ext}') == sha256(paths[f"{selection['audio']}_{ext}"])
            for mode, selection in cfg['conditions'].items() for tag in (tags[mode],) for ext in ('wav', 'lab'))
            and np.array_equal(left[begin:end], right[begin:end]),
        'ordinary_intervals_reproduced': all(tiers[mode] == mfa.tiers(paths[f'{mode}_tier']) for mode in ('control', 'old_preroll'))
            and intervals['control'][1] == cfg['control_end_seconds'] and intervals['old_preroll'][1] == cfg['preroll_end_seconds'],
        'independent_cmvn_statistics': all(row['statistics_max_error'] <= cfg['statistics_absolute_tolerance']
                                           for row in comparison.values()),
        'independent_normalization': all(row['normalization_max_error'] <= cfg['normalized_absolute_tolerance']
                                         for row in comparison.values()),
        'only_cmvn_source_exchanged': all(row['uses_registered_statistics'] and row['raw_audio_features_equal']
                                          for row in comparison.values())
            and not np.array_equal(matrices['control_own_stats'], matrices['old_preroll_own_stats']),
    }
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera-cli', 'compare::tsp::tests'],
            cwd=UPSTREAM, stdout=out / 'upstream-tsp-tests.log')
    predictions = {
        'uncompressed_mfccs_equal_near_tall': feature_delta['own_stats']['uncompressed']['local_maximum'] == 0,
        'shared_statistics_reduce_local_difference': (
            feature_delta['both_control_stats']['normalized']['local_maximum']
            < feature_delta['own_stats']['normalized']['local_maximum']),
        'control_statistics_restore_control_boundary': intervals['preroll_control_stats'][1] == cfg['control_end_seconds'],
        'preroll_statistics_move_control_boundary': intervals['control_preroll_stats'][1] == cfg['preroll_end_seconds'],
    }
    return {'checks': checks, 'predictions': predictions, 'tall_vowel_intervals': intervals,
            'tier_differences': {name: aligned.compare_intervals(tiers['control'], tier) for name, tier in tiers.items()},
            'feature_differences': feature_delta, 'independent_calculation': comparison}


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
    config = parent[1]['aligner']
    site = Path(config['environment_root']) / 'env/lib/python3.11/site-packages'
    if any(sha256(site / name) != digest for name, digest in case['environment_sources'].items()):
        parser.error('MFAまたはKalpyのソースが登録条件と一致しません')
    uid = case['utterance']
    paths = {'dictionary': formants.verified_path(parent, 'artifacts/synth.dict')}
    for mode in ('control', 'old_preroll'):
        tag = f'{uid}-{mode}'
        for ext in ('wav', 'lab'):
            paths[f'{mode}_{ext}'] = formants.verified_path(parent, f'artifacts/corpus/{tag}/{tag}.{ext}')
        paths[f'{mode}_tier'] = formants.verified_path(parent, f'artifacts/aligned/{tag}/{tag}.json')
    sources = (formants.TSP_SOURCE, 'crates/chimera-cli/src/main.rs', config['configuration'])
    inputs = [CASE, Path(__file__).resolve(), PROBE, parent[0] / 'manifest.json', *paths.values(),
              *(Path(module.__file__) for module in (formants, single, aligned, mfa)), *(UPSTREAM / name for name in sources)]
    details = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision, 'aligner': config}
    return record_measurement(args.run_id, CASE, inputs, details, lambda out, execute: measure(
        case, config, paths, out, execute), command=None, input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
