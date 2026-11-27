"""FK61_02の1.650秒・1.680秒経路を同じ入力とモデル上で採点する。"""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory

import numpy as np

import measure_tsp_again_initial_tip_mfa as single
import measure_tsp_phone_boundaries as mfa
import measure_tsp_stressed_vowel_formants as formants
import measure_tsp_tall_mfa_cmvn as cmvn
import measure_tsp_tall_mfcc_input_compression as mfcc
from measure_tsp_f2_bandwidth_held_out import saved_case
from measure_uniform_tube import record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/tsp-tall-gmm-paths.json'
PROBE = WORKSPACE / 'tools/probe_mfa_tall_gmm_paths.py'


def read_npz(path):
    with np.load(path, allow_pickle=False) as data:
        return {key: data[key] for key in data.files}


def compare_scores(out, modes, cfg):
    raw = {name: read_npz(out / name / 'decoder.npz') for name in modes}
    captured = {name: formants.read(out / name / 'decoder.json') for name in modes}
    rows = formants.read(out / 'path-scores.json')
    arrays = read_npz(out / 'path-scores.npz')
    lower, upper = cfg['local_feature_frames']
    comparisons, margins = {}, {}
    for name in modes:
        scale = captured[name]['weight_options']['acoustic_scale']
        own = rows[name][name]
        predicted = arrays[f'{name}_on_{name}_acoustic']
        observed = raw[name]['frame_likelihood']
        frame_units = {'unscaled': float(np.max(np.abs(predicted - observed))),
                       'scaled': float(np.max(np.abs(predicted - observed / scale)))}
        actual_total = captured[name]['reported_total']
        total_units = {key: abs(value - own['total_scaled_score'])
                       for key, value in (('unscaled', actual_total * scale), ('scaled', actual_total))}
        best_frame = min(frame_units, key=frame_units.get)
        best_total = min(total_units, key=total_units.get)
        comparisons[name] = {'frame_units': best_frame, 'total_units': best_total,
                             'frame_likelihood_error': frame_units[best_frame], 'total_scaled_score_error': total_units[best_total],
                             'cross_path_margin': {
                                 'scaled_total': rows[name][modes[1]]['total_scaled_score'] - rows[name][modes[0]]['total_scaled_score'],
                                 'scaled_graph': rows[name][modes[0]]['graph_cost'] - rows[name][modes[1]]['graph_cost']}}
        contrast = scale * (arrays[f'{name}_on_{modes[1]}_acoustic'] - arrays[f'{name}_on_{modes[0]}_acoustic'])
        margins[name] = {'scaled_acoustic_all': float(contrast.sum()),
                         'scaled_acoustic_near_tall': float(contrast[lower:upper].sum()),
                         'scaled_acoustic_outside_tall': float(contrast[:lower].sum() + contrast[upper:].sum())}
    transitions = np.flatnonzero(raw[modes[0]]['transition_ids'] != raw[modes[1]]['transition_ids'])
    phones = np.flatnonzero(arrays[f'{modes[0]}_on_{modes[0]}_phone_ids'] != arrays[f'{modes[0]}_on_{modes[1]}_phone_ids'])
    pdfs = np.flatnonzero(arrays[f'{modes[0]}_on_{modes[0]}_pdf_ids'] != arrays[f'{modes[0]}_on_{modes[1]}_pdf_ids'])
    x, y = (raw[mode]['features'] for mode in modes)
    feature_delta = cmvn.feature_differences(x, y, (lower, upper))
    checks = {
        'graph_model_and_decoder_options_match': (
            len({sha256(out / name / 'graph.fst') for name in modes}) == 1
            and len({item['effective_model_sha256'] for item in captured.values()}) == 1
            and captured[modes[0]]['weight_options'] == captured[modes[1]]['weight_options']),
        'native_and_numpy_gmm_scores_match': all(item['gmm_error'] <= cfg['frame_likelihood_tolerance']
                                                for group in rows.values() for item in group.values()),
        'recomputed_winner_frame_likelihoods_match': (
            len({item['frame_units'] for item in comparisons.values()}) == 1
            and all(item['frame_likelihood_error'] <= cfg['frame_likelihood_tolerance'] for item in comparisons.values())),
        'recomputed_winner_totals_match': (
            len({item['total_units'] for item in comparisons.values()}) == 1
            and all(item['total_scaled_score_error'] <= cfg['total_scaled_score_tolerance'] for item in comparisons.values())),
    }
    predictions = {'phone_disagreement_matches_three_tall_frames': phones.tolist() == cfg['expected_phone_difference_frames'],
                   'each_input_favors_its_selected_path': (comparisons[modes[0]]['cross_path_margin']['scaled_total'] < 0
                                                          < comparisons[modes[1]]['cross_path_margin']['scaled_total'])}
    return {'checks': checks, 'predictions': predictions, 'cross_scores': rows, 'score_comparisons': comparisons,
            'late_minus_early_acoustic': margins, 'options': captured[modes[0]]['weight_options'],
            'feature_shape': [int(value) for value in x.shape], 'decoder_feature_difference': feature_delta,
            'different_transition_frames': transitions.tolist(), 'different_phone_frames': phones.tolist(),
            'different_pdf_frames': pdfs.tolist()}


def measure(case, normalizer, config, paths, out, execute):
    cfg = case['measurement']
    modes = cfg['modes']
    root = Path(config['environment_root'])
    model, _ = mfa.versions(root, config, out, execute)
    uid, tag = normalizer['utterance'], f"{normalizer['utterance']}-control"
    corpus = out / 'corpus'
    speaker = corpus / tag
    speaker.mkdir(parents=True)
    copied = {out / 'synth.dict': paths['dictionary'], speaker / f'{tag}.wav': paths['wav'],
              speaker / f'{tag}.lab': paths['lab']}
    for destination, original in copied.items():
        shutil.copyfile(original, destination)
    active = normalizer['measurement'] | {'conditions': {'control': {'audio': 'control', 'statistics': 'control'}}}
    probe_case = out / 'control-case.json'
    probe_case.write_text(json.dumps({'utterance': uid, 'measurement': active}, indent=2) + '\n')
    tiers = {}
    with TemporaryDirectory(prefix='gmm-paths-', dir=out.parent / 'tmp') as directory:
        scratch = Path(directory)
        for mode in modes:
            target = out / mode
            target.mkdir()
            aligned = target / 'aligned'
            entry = [str(root / 'env/bin/python'), str(PROBE), 'capture', mode, str(probe_case),
                     str(target), str(scratch / f'{mode}.mdl')]
            mfa.mfa_run(root, config, corpus, out / 'synth.dict', model, aligned, scratch / mode, execute, entry=entry)
            tiers[mode] = mfa.tiers(aligned / tag / f'{tag}.json')
        execute([str(root / 'env/bin/python'), str(PROBE), 'score', str(CASE), str(out), str(scratch)])
    observations = compare_scores(out, modes, cfg)
    ends = {mode: tier['phones'][single.phone_at_word(tier, active)][1] for mode, tier in tiers.items()}
    previous_features = {mode: read_npz(paths[f'{mode}_features']) for mode in modes}
    expected_tokens = {'compressed': {'input': 'CM', 'final': 'CM'}, 'float32': {'input': 'FM', 'final': 'CM'}}
    observations['checks'].update({
        'same_control_pcm_lab_and_dictionary': all(sha256(copy) == sha256(source) for copy, source in copied.items()),
        'archived_control_intervals_reproduced': (
            ends == cfg['expected_end_seconds'] and all(tiers[mode] == mfa.tiers(paths[f'{mode}_tier']) for mode in modes)),
        'archive_formats_and_control_features_reproduced': all(
            formants.read(out / mode / 'archive-formats.json') == {'control': expected_tokens[mode]}
            and all(value.tobytes() == previous_features[mode][key].tobytes()
                    for key, value in cmvn.read_features(out / mode / 'features.npz', active).items()) for mode in modes),
    })
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera-cli', 'compare::tsp::tests'],
            cwd=UPSTREAM, stdout=out / 'upstream-tsp-tests.log')
    return observations | {'tall_vowel_end_seconds': ends}


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
    preceding = formants.open_run(parent_case['parent'], revision)
    cmvn_case, cmvn_snapshot = saved_case(preceding, cmvn.CASE)
    config = parent[1]['aligner']
    site = Path(config['environment_root']) / 'env/lib/python3.11/site-packages'
    source_digests = cmvn_case['environment_sources'] | case['environment_sources']
    if config != preceding[1]['aligner'] or any(sha256(site / name) != digest for name, digest in source_digests.items()):
        parser.error('MFAの条件またはソースが登録値と一致しません')
    tag = f"{cmvn_case['utterance']}-control"
    outputs = {'dictionary': 'synth.dict', 'wav': f'corpus/{tag}/{tag}.wav', 'lab': f'corpus/{tag}/{tag}.lab'}
    for mode in case['measurement']['modes']:
        outputs[f'{mode}_tier'] = f'{mode}/aligned/{tag}/{tag}.json'
        outputs[f'{mode}_features'] = f'{mode}/features.npz'
    paths = {key: formants.verified_path(parent, f'artifacts/{name}') for key, name in outputs.items()}
    helpers = (PROBE, mfcc.PROBE, cmvn.PROBE, *(Path(module.__file__) for module in (mfcc, cmvn, single, formants, mfa)))
    inputs = [CASE, Path(__file__).resolve(), parent_snapshot, cmvn_snapshot, parent[0] / 'manifest.json',
              preceding[0] / 'manifest.json', *paths.values(), *helpers, UPSTREAM / formants.TSP_SOURCE,
              UPSTREAM / config['configuration']]
    details = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision, 'aligner': config}
    return record_measurement(args.run_id, CASE, inputs, details, lambda out, execute: measure(
        case, cmvn_case, config, paths, out, execute), command=None, input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
