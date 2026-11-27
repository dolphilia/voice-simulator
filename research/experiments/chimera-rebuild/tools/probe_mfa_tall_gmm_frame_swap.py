"""通常MFAがGMMへ渡す特徴行列を指定した行列へ差し替える。"""

import json
from pathlib import Path
import sys
from unittest.mock import patch

import numpy as np
from _kalpy.matrix import FloatMatrix
from kalpy.gmm import align

from probe_mfa_cmvn import run_probe
from probe_mfa_mfcc_archive import ArchiveCapture
from probe_mfa_tall_gmm_paths import capture_decoder


def run(case, matrices, out, scratch):
    capture = ArchiveCapture(case, out / 'features.npz')
    original = align.GmmAligner.align_utterance
    native = align.gmm_align_compiled
    baseline = matrices['compressed']

    def replace_features(aligner, graph, features, utterance_id, *args, **kwargs):
        key = str(utterance_id)
        modes = {utt: mode for mode, (utt, _) in capture.ids.items()}
        mode = modes.get(key)
        if mode not in matrices:
            raise ValueError(f'登録した特徴行列がありません ({key})')
        received = features.numpy()
        if received.shape != baseline.shape or received.dtype != baseline.dtype or received.tobytes() != baseline.tobytes():
            raise ValueError(f'MFAの通常の入力特徴量が圧縮開始の対照と一致しません ({mode})')
        replacement = FloatMatrix()
        replacement.from_numpy(matrices[mode].copy())
        target = out / mode
        target.mkdir()
        model_file = scratch / f'{mode}.mdl'
        observed = capture_decoder(native, target, model_file)
        try:
            with patch.object(align, 'gmm_align_compiled', observed):
                return original(aligner, graph, replacement, utterance_id, *args, **kwargs)
        finally:
            model_file.unlink(missing_ok=True)

    with patch.object(align.GmmAligner, 'align_utterance', replace_features):
        run_probe(capture)


def main():
    case, matrices, out, scratch = (Path(sys.argv.pop(1)) for _ in range(4))
    with np.load(matrices, allow_pickle=False) as record:
        data = {key: record[key] for key in record.files}
    run(json.loads(case.read_text()), data, out, scratch)


if __name__ == '__main__':
    main()
