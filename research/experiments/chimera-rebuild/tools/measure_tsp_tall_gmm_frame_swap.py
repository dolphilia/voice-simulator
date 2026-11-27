"""GMM-HMMへ渡す5つの特徴行を入れ替え、通常MFAで境界を比較する。"""

import argparse
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory

import numpy as np

import measure_tsp_again_initial_tip_mfa as single
import measure_tsp_phone_boundaries as mfa
import measure_tsp_stressed_vowel_formants as formants
import measure_tsp_tall_gmm_paths as gmm
from measure_tsp_f2_bandwidth_held_out import saved_case
from measure_uniform_tube import record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/tsp-tall-gmm-frame-swap.json'
PROBE = WORKSPACE / 'tools/probe_mfa_tall_gmm_frame_swap.py'
CONTROLS = ('compressed', 'float32')


def row_masks(cfg):
    start, stop = cfg['tall_range']
    rows = np.arange(cfg['feature_shape'][0])
    masks = {'none': np.zeros(rows.shape, dtype=bool), 'all': np.ones(rows.shape, dtype=bool),
             'tall': (rows >= start) & (rows < stop), 'outside_tall': (rows < start) | (rows >= stop)}
    return {mode: masks[source] for mode, source in cfg['rows_from_float32'].items()}


def two_path_margins(masks, paths, scale):
    scores = formants.read(paths['previous_scores'])
    observed = gmm.read_npz(paths['previous_acoustics'])
    left, right = CONTROLS
    contrasts = {mode: observed[f'{mode}_on_{right}_acoustic'] - observed[f'{mode}_on_{left}_acoustic'] for mode in CONTROLS}
    graph_advantage = scores[left][left]['graph_cost'] - scores[left][right]['graph_cost']
    return {mode: scale * math.fsum(np.where(mask, contrasts[right], contrasts[left])) + graph_advantage
            for mode, mask in masks.items()}


def observe_mfa_inputs(cmvn_case, config, paths, matrices, out, execute):
    root = Path(config['environment_root'])
    model, _ = mfa.versions(root, config, out, execute)
    metadata = formants.read(paths['decoder_metadata'])
    features_file = out / 'decoder-inputs.npz'
    np.savez_compressed(features_file, **matrices)
    corpus = out / 'corpus'
    tags = {mode: f"{cmvn_case['utterance']}-{mode}" for mode in matrices}
    dictionary = out / 'synth.dict'
    transfers = {dictionary: paths['dictionary']}
    for tag in tags.values():
        folder = corpus / tag
        folder.mkdir(parents=True)
        for ext in ('wav', 'lab'):
            transfers[folder / f'{tag}.{ext}'] = paths[ext]
    for destination, original in transfers.items():
        shutil.copyfile(original, destination)
    probe_case = out / 'corpus-case.json'
    probe_case.write_text(json.dumps({'utterance': cmvn_case['utterance'], 'measurement': {
        'conditions': {mode: {'audio': mode, 'statistics': mode} for mode in matrices}}}, indent=2) + '\n')
    target = out / 'aligned'
    with TemporaryDirectory(prefix='gmm-swap-', dir=out.parent / 'tmp') as scratch:
        entry = [str(root / 'env/bin/python'), str(PROBE), str(probe_case), str(features_file), str(out), scratch]
        mfa.mfa_run(root, config, corpus, dictionary, model, target, Path(scratch) / 'mfa', execute, entry=entry)
    tiers = {name: mfa.tiers(target / tag / f'{tag}.json') for name, tag in tags.items()}
    decoder = {mode: gmm.read_npz(out / mode / 'decoder.npz') for mode in matrices}
    native = {mode: formants.read(out / mode / 'decoder.json') for mode in matrices}
    feat_modes = formants.read(out / 'archive-formats.json')
    checks = {
        'same_pcm_transcript_and_dictionary': all(sha256(copy) == sha256(source) for copy, source in transfers.items()),
        'all_upstream_feature_archives_are_compressed': feat_modes == dict.fromkeys(matrices, {'input': 'CM', 'final': 'CM'}),
        'decoder_received_exact_feature_rows': all(row['features'].tobytes() == matrices[mode].tobytes()
                                                   for mode, row in decoder.items()),
        'same_graph_effective_model_and_settings': all(
            sha256(out / mode / 'graph.fst') == sha256(paths['graph'])
            and row['effective_model_sha256'] == metadata['effective_model_sha256']
            and row['weight_options'] == metadata['weight_options'] for mode, row in native.items()),
    }
    return tiers, decoder, native, checks


def identify_paths(observed, references):
    return {
        mode: next((reference for reference, prior in references.items() if all(
            np.array_equal(row[key], prior[key]) for key in ('transition_ids', 'words'))), 'other')
        for mode, row in observed.items()}


def measure(case, cmvn_case, config, paths, out, execute):
    cfg = case['measurement']
    history = {mode: gmm.read_npz(paths[f'{mode}_decoder']) for mode in CONTROLS}
    metadata = formants.read(paths['decoder_metadata'])
    early, late = (history[mode]['features'] for mode in CONTROLS)
    if any(array.shape != tuple(cfg['feature_shape']) or array.dtype != np.float32 or not np.isfinite(array).all()
           for array in (early, late)):
        raise ValueError('保存済み特徴行列の形式が登録条件と一致しません')
    masks = row_masks(cfg)
    matrices = {mode: np.where(mask[:, None], late, early) for mode, mask in masks.items()}
    margins = two_path_margins(masks, paths, metadata['weight_options']['acoustic_scale'])
    tiers, decoder, native, checks = observe_mfa_inputs(cmvn_case, config, paths, matrices, out, execute)
    selection = {'word': 'tall', 'phones': cfg['tall_both_phones']}
    ends = {mode: tier['phones'][single.phone_at_word(tier, selection)][1] for mode, tier in tiers.items()}
    actual_paths = identify_paths(decoder, history)
    winner = {mode: ('float32' if margin > 0 else 'compressed' if margin < 0 else 'tie') for mode, margin in margins.items()}
    baseline_ends = cfg['accepted_control_end_seconds']
    checks['control_boundaries_and_path_ids_replayed'] = all(
        tiers[mode] == mfa.tiers(paths[f'{mode}_tier']) and ends[mode] == baseline_ends[mode]
        and actual_paths[mode] == mode and np.array_equal(decoder[mode]['frame_likelihood'], history[mode]['frame_likelihood'])
        for mode in CONTROLS)
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera-cli', 'compare::tsp::tests'],
            cwd=UPSTREAM, stdout=out / 'upstream-tsp-tests.log')
    tolerance = cfg['margin_agreement']
    return {'checks': checks, 'predictions': {
                'five_frames_move_boundary': ends['float32_at_tall'] == baseline_ends['float32'],
                'outside_tall_keeps_early_boundary': ends['float32_outside_tall'] == baseline_ends['compressed'],
                'two_path_margins_follow_five_rows': (
                    abs(margins['float32_at_tall'] - margins['float32']) <= tolerance
                    and abs(margins['float32_outside_tall'] - margins['compressed']) <= tolerance)},
            'tall_vowel_end_seconds': ends, 'selected_paths': actual_paths,
            'margins_for_two_fixed_paths': margins, 'winner_among_two_fixed_paths': winner,
            'selected_scaled_scores': {mode: row['reported_total'] * row['weight_options']['acoustic_scale']
                                       for mode, row in native.items()},
            'retry_counts': {mode: int(row['retried']) for mode, row in native.items()},
            'tall_range': cfg['tall_range']}


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
    previous, decoder_snapshot = saved_case(parent, gmm.CASE)
    mfcc_history = formants.open_run(previous['parent'], revision)
    mfcc_case, mfcc_snapshot = saved_case(mfcc_history, gmm.mfcc.CASE)
    normalization = formants.open_run(mfcc_case['parent'], revision)
    cmvn_case, cmvn_snapshot = saved_case(normalization, gmm.cmvn.CASE)
    config = parent[1]['aligner']
    dirs = Path(config['environment_root']) / 'env/lib/python3.11/site-packages'
    digests = previous['environment_sources'] | cmvn_case['environment_sources']
    if config != normalization[1]['aligner'] or any(sha256(dirs / name) != digest for name, digest in digests.items()):
        parser.error('MFAの条件またはソースが登録値と一致しません')
    tag = f"{cmvn_case['utterance']}-control"
    outputs = {'dictionary': 'synth.dict', 'wav': f'corpus/{tag}/{tag}.wav', 'lab': f'corpus/{tag}/{tag}.lab',
               'previous_acoustics': 'path-scores.npz', 'previous_scores': 'path-scores.json', 'graph': 'compressed/graph.fst',
               'decoder_metadata': 'compressed/decoder.json'}
    for mode in CONTROLS:
        outputs[f'{mode}_decoder'] = f'{mode}/decoder.npz'
        outputs[f'{mode}_tier'] = f'{mode}/aligned/{tag}/{tag}.json'
    paths = {name: formants.verified_path(parent, f'artifacts/{path}') for name, path in outputs.items()}
    helpers = (PROBE, gmm.PROBE, gmm.mfcc.PROBE, gmm.cmvn.PROBE,
               *(Path(module.__file__) for module in (gmm, single, formants, mfa)))
    inputs = [CASE, Path(__file__).resolve(), decoder_snapshot, mfcc_snapshot, cmvn_snapshot,
              parent[0] / 'manifest.json', mfcc_history[0] / 'manifest.json', normalization[0] / 'manifest.json',
              *paths.values(), *helpers, UPSTREAM / formants.TSP_SOURCE, UPSTREAM / config['configuration']]
    details = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision, 'aligner': config}
    return record_measurement(args.run_id, CASE, inputs, details, lambda out, execute: measure(
        case, cmvn_case, config, paths, out, execute), command=None, input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    main()
