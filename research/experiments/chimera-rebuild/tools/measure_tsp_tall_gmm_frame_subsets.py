"""164〜168番の全32部分集合を入れ替えてtallの境界を照合する。"""

import argparse
from itertools import combinations
import os
from pathlib import Path
import subprocess

import numpy as np

import measure_tsp_again_initial_tip_mfa as single
import measure_tsp_phone_boundaries as mfa
import measure_tsp_stressed_vowel_formants as formants
import measure_tsp_tall_gmm_frame_swap as swap
import measure_tsp_tall_gmm_paths as gmm
from measure_tsp_f2_bandwidth_held_out import saved_case
from measure_uniform_tube import record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/tsp-tall-gmm-frame-subsets.json'


def subsets(frames):
    result = {'compressed': ()}
    for count in range(1, len(frames) + 1):
        for group in combinations(frames, count):
            result['frames_' + '_'.join(map(str, group))] = group
    return result


def summarize_subsets(results, late_boundary):
    moved = [row for row in results if row['end_seconds'] == late_boundary]
    counts = {}
    for row in results:
        total = counts.setdefault(str(len(row['frames'])), {'conditions': 0, 'late_boundary': 0})
        total['conditions'] += 1
        total['late_boundary'] += int(row['end_seconds'] == late_boundary)
    minimum = min((len(row['frames']) for row in moved), default=None)
    minimum_sets = [row['frames'] for row in moved if len(row['frames']) == minimum]
    moving_sets = [set(row['frames']) for row in moved]
    inclusion_minimal = [row['frames'] for row in moved
                         if not any(other < set(row['frames']) for other in moving_sets)]
    return {'by_size': counts, 'minimum_count': minimum, 'minimum_frame_sets': minimum_sets,
            'inclusion_minimal_frame_sets': inclusion_minimal}


def measure(case, previous, cmvn_case, config, paths, out, execute):
    registered = case['measurement']
    base = previous['measurement']
    start, stop = base['tall_range']
    if registered['frames'] != list(range(start, stop)):
        raise ValueError('交換候補の行が前回の登録と一致しません')
    groups = subsets(registered['frames'])
    history = {mode: gmm.read_npz(paths[f'{mode}_decoder']) for mode in swap.CONTROLS}
    saved_full = gmm.read_npz(paths['full_subset_decoder'])
    early, late = (history[mode]['features'] for mode in swap.CONTROLS)
    if any(array.shape != tuple(base['feature_shape']) or array.dtype != np.float32 or not np.isfinite(array).all()
           for array in (early, late)):
        raise ValueError('保存済み特徴行列の形式が登録条件と一致しません')
    coordinates = np.arange(len(early))
    masks = {mode: np.isin(coordinates, rows) for mode, rows in groups.items()}
    matrices = {mode: np.where(mask[:, None], late, early) for mode, mask in masks.items()}
    meta = formants.read(paths['decoder_metadata'])
    margins = swap.two_path_margins(masks, paths, meta['weight_options']['acoustic_scale'])
    tiers, decoder, native, checks = swap.observe_mfa_inputs(cmvn_case, config, paths, matrices, out, execute)
    selection = {'word': 'tall', 'phones': base['tall_both_phones']}
    ends = {name: tier['phones'][single.phone_at_word(tier, selection)][1] for name, tier in tiers.items()}
    actual = swap.identify_paths(decoder, history)
    winner = {mode: ('float32' if margin > 0 else 'compressed' if margin < 0 else 'tie') for mode, margin in margins.items()}
    baseline_ends = base['accepted_control_end_seconds']
    fully_swapped = next(mode for mode, rows in groups.items() if list(rows) == registered['frames'])
    controls = {'compressed': (history['compressed'], paths['compressed_tier'], 'compressed'),
                fully_swapped: (saved_full, paths['full_subset_tier'], 'float32')}
    checks.update({
        'all_registered_subsets_were_aligned': len(decoder) == len(tiers) == len(groups) == registered['subset_count'],
        'empty_and_full_subsets_replay_archived_controls': all(
            tiers[mode] == mfa.tiers(tier)
            and ends[mode] == baseline_ends[expected]
            and actual[mode] == expected
            and all(decoder[mode][key].tobytes() == raw[key].tobytes() for key in raw)
            for mode, (raw, tier, expected) in controls.items()),
    })
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera-cli', 'compare::tsp::tests'],
            cwd=UPSTREAM, stdout=out / 'upstream-tsp-tests.log')
    results = [{'mode': mode, 'frames': list(rows), 'end_seconds': ends[mode], 'selected_path': actual[mode],
                'predicted_path': winner[mode], 'margin': margins[mode], 'retried': native[mode]['retried']}
               for mode, rows in groups.items()]
    counts = summarize_subsets(results, baseline_ends['float32'])
    discrepancies = [row['frames'] for row in results if row['selected_path'] != row['predicted_path']]
    return {'checks': checks, 'predictions': {
                'minimum_sets_match_prediction': counts['minimum_frame_sets'] == registered['predicted_minimum_frame_sets'],
                'all_subsets_choose_predicted_path': not discrepancies},
            'subsets': results, 'counts': counts, 'different_from_margin_prediction': discrepancies}


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
    baseline = formants.open_run(case['parent'], revision)
    previous, swap_snapshot = saved_case(baseline, swap.CASE)
    decoder_run = formants.open_run(previous['parent'], revision)
    decoder_case, decoder_snapshot = saved_case(decoder_run, gmm.CASE)
    mfcc_run = formants.open_run(decoder_case['parent'], revision)
    mfcc_case, mfcc_snapshot = saved_case(mfcc_run, gmm.mfcc.CASE)
    normalizer = formants.open_run(mfcc_case['parent'], revision)
    cmvn_case, cmvn_snapshot = saved_case(normalizer, gmm.cmvn.CASE)
    config = baseline[1]['aligner']
    dirs = Path(config['environment_root']) / 'env/lib/python3.11/site-packages'
    digests = decoder_case['environment_sources'] | cmvn_case['environment_sources']
    if config != decoder_run[1]['aligner'] or any(sha256(dirs / name) != digest for name, digest in digests.items()):
        parser.error('MFAの条件またはソースが登録値と一致しません')
    uid = cmvn_case['utterance']
    tag = f'{uid}-compressed'
    full = f'{uid}-float32_at_tall'
    original_files = {'dictionary':'synth.dict', 'wav':f'corpus/{tag}/{tag}.wav', 'lab':f'corpus/{tag}/{tag}.lab',
                      'full_subset_decoder':'float32_at_tall/decoder.npz', 'full_subset_tier':f'aligned/{full}/{full}.json'}
    score_files = {'previous_acoustics':'path-scores.npz', 'previous_scores':'path-scores.json',
                   'graph':'compressed/graph.fst', 'decoder_metadata':'compressed/decoder.json',
                   'compressed_tier':f'compressed/aligned/{uid}-control/{uid}-control.json',
                   **{f'{mode}_decoder':f'{mode}/decoder.npz' for mode in swap.CONTROLS}}
    paths = {name: formants.verified_path(run, f'artifacts/{path}')
             for run, files in ((baseline, original_files), (decoder_run, score_files)) for name, path in files.items()}
    helpers = (swap.PROBE, gmm.PROBE, gmm.mfcc.PROBE, gmm.cmvn.PROBE,
               *(Path(module.__file__) for module in (swap, gmm, single, formants, mfa)))
    inputs = [CASE, Path(__file__).resolve(), swap_snapshot, decoder_snapshot, mfcc_snapshot, cmvn_snapshot,
              *(run[0] / 'manifest.json' for run in (baseline, decoder_run, mfcc_run, normalizer)),
              *paths.values(), *helpers, UPSTREAM / formants.TSP_SOURCE, UPSTREAM / config['configuration']]
    details = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision, 'aligner': config}
    return record_measurement(args.run_id, CASE, inputs, details, lambda out, execute: measure(
        case, previous, cmvn_case, config, paths, out, execute), command=None, input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
