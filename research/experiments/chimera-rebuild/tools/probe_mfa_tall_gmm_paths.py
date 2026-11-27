"""通常MFAが選んだ経路を採取し、同じモデルとグラフで交差採点する。"""

import hashlib
import json
import math
from pathlib import Path
import sys
from unittest.mock import patch

import numpy as np
import pywrapfst as fst
from _kalpy.fstext import VectorFst
from _kalpy.hmm import AddTransitionProbs
from _kalpy.matrix import FloatMatrix
from kalpy.gmm import align
from kalpy.gmm.utils import read_gmm_model, write_gmm_model

from probe_mfa_cmvn import run_probe
from probe_mfa_mfcc_archive import ArchiveCapture, run_uncompressed


def save(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def capture_decoder(original, out, model_path):
    def observed_decode(transition_model, acoustic_model, graph, features, **options):
        result_file = out / 'decoder.npz'
        if result_file.exists():
            raise ValueError('同じ条件で複数のGMM経路が観測されました')
        (out / 'graph.fst').write_bytes(graph.write_to_string())
        write_gmm_model(model_path, transition_model, acoustic_model)
        result = original(transition_model, acoustic_model, graph, features, **options)
        transition_ids, words, total, likelihood, successful, retried = result
        if not successful:
            raise ValueError('GMM-HMMの整列が完了していません')
        np.savez_compressed(result_file, features=features.numpy(), transition_ids=np.array(transition_ids),
                            words=np.array(words), frame_likelihood=likelihood.numpy())
        with model_path.open('rb') as model:
            digest = hashlib.file_digest(model, 'sha256').hexdigest()
        save(out / 'decoder.json', {'weight_options': options, 'reported_total': float(total),
                                    'retried': bool(retried), 'effective_model_sha256': digest})
        return result

    return observed_decode


def record(storage, case, out, model_path):
    capture = ArchiveCapture(case, out / 'features.npz')
    observed = capture_decoder(align.gmm_align_compiled, out, model_path)
    with patch.object(align, 'gmm_align_compiled', observed):
        if storage == 'float32':
            run_uncompressed(capture)
        elif storage == 'compressed':
            run_probe(capture)
        else:
            raise ValueError(f'未対応のMFCC保存形式です ({storage})')


def linear_acceptor(labels):
    graph = fst.VectorFst()
    states = [graph.add_state() for _ in range(len(labels) + 1)]
    graph.set_start(states[0])
    unit = fst.Weight.one('tropical')
    graph.set_final(states[-1], unit)
    for start, stop, label in zip(states[:-1], states[1:], labels, strict=True):
        graph.add_arc(start, fst.Arc(int(label), int(label), unit, stop))
    return graph


def graph_cost(graph, transition_ids, words):
    constrained = fst.compose(fst.compose(linear_acceptor(transition_ids), graph), linear_acceptor(words))
    if constrained.start() < 0:
        raise ValueError('固定した遷移ID・語IDを受理するグラフ経路がありません')
    cost = float(fst.shortestdistance(constrained, reverse=True)[constrained.start()])
    if not math.isfinite(cost):
        raise ValueError('固定したグラフ経路の費用が有限ではありません')
    return cost


def acoustics(acoustic_model, features, pdf_ids):
    native_features = FloatMatrix()
    native_features.from_numpy(features.copy())
    native = np.array([acoustic_model.LogLikelihood(int(pdf), native_features.Row(index))
                       for index, pdf in enumerate(pdf_ids)])
    coefficients = {}
    for pdf_id in np.unique(pdf_ids):
        gmm = acoustic_model.GetPdf(int(pdf_id))
        coefficients[pdf_id] = (gmm.gconsts().numpy().astype(float), gmm.means_invvars().numpy().astype(float),
                                gmm.inv_vars().numpy().astype(float))
    independent = []
    for pdf, value in zip(pdf_ids, features.astype(float), strict=True):
        weights, means, inv_vars = coefficients[pdf]
        components = weights + means @ value - 0.5 * (inv_vars @ (value**2))
        independent.append(np.logaddexp.reduce(components))
    return native, np.array(independent)


def cross_score(modes, out, models):
    captured, metadata = {}, {}
    for mode in modes:
        with np.load(out / mode / 'decoder.npz', allow_pickle=False) as data:
            captured[mode] = {key: data[key] for key in data.files}
        metadata[mode] = json.loads((out / mode / 'decoder.json').read_text())
    scores, observations = {}, {}
    for input_mode in modes:
        transition_model, acoustic_model = read_gmm_model(models / f'{input_mode}.mdl')
        options = metadata[input_mode]['weight_options']
        if options['careful']:
            raise ValueError('carefulによる探索グラフ変更を含む条件には対応していません')
        weighted = VectorFst.Read(str(out / input_mode / 'graph.fst'))
        AddTransitionProbs(transition_model, [], options['transition_scale'], options['self_loop_scale'], weighted)
        graph = fst.Fst.read_from_string(weighted.write_to_string()).arcsort(sort_type='ilabel')
        features = captured[input_mode]['features']
        rows = {}
        for path_mode in modes:
            path = captured[path_mode]
            ids = path['transition_ids']
            pdfs = np.array([transition_model.TransitionIdToPdf(int(tid)) for tid in ids])
            phones = np.array([transition_model.TransitionIdToPhone(int(tid)) for tid in ids])
            acoustic, independent = acoustics(acoustic_model, features, pdfs)
            cost = graph_cost(graph, ids, path['words'])
            total = options['acoustic_scale'] * acoustic.sum() - cost
            rows[path_mode] = {'graph_cost': cost, 'total_scaled_score': float(total),
                               'gmm_error': float(max(abs(acoustic - independent)))}
            label = f'{input_mode}_on_{path_mode}'
            observations[f'{label}_acoustic'] = acoustic
            observations[f'{label}_independent'] = independent
            observations[f'{label}_phone_ids'] = phones
            observations[f'{label}_pdf_ids'] = pdfs
        scores[input_mode] = rows
    np.savez_compressed(out / 'path-scores.npz', **observations)
    save(out / 'path-scores.json', scores)


def main():
    action = sys.argv.pop(1)
    if action == 'capture':
        storage, case_file, target, model_file = sys.argv[1:5]
        del sys.argv[1:5]
        record(storage, json.loads(Path(case_file).read_text()), Path(target), Path(model_file))
    elif action == 'score':
        case_file, target, models = map(Path, sys.argv[1:])
        case = json.loads(case_file.read_text())
        cross_score(case['measurement']['modes'], target, models)
    else:
        raise ValueError(f'未対応の計測操作です ({action})')


if __name__ == '__main__':
    main()
