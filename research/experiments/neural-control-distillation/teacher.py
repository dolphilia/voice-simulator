"""Kokoroの公式model実装をCPUで実行し、研究用の音声と制御を保存する。"""
import argparse
import importlib
import json
import os
from pathlib import Path
import sys
import time
import types
from budget import Budget, ROOT, RESULT, save, digest


def load_teacher():
    packages = ROOT / '.cache/packages'
    sys.path.insert(0, str(packages))
    os.environ['HF_HUB_OFFLINE'] = '1'
    # __init__による未使用の英語pipelineのimportだけを避ける。
    # 公式model/modules/istftnetのコード・重み・演算は変更しない。
    package = types.ModuleType('kokoro')
    package.__path__ = [str(packages / 'kokoro')]
    sys.modules['kokoro'] = package
    from kokoro.model import KModel
    from misaki.ja import JAG2P
    import torch
    from loguru import logger
    logger.disable('kokoro')
    torch.set_num_threads(4)
    model = KModel(repo_id='hexgrad/Kokoro-82M',
                   config=str(ROOT / '.cache/teacher/config.json'),
                   model=str(ROOT / '.cache/teacher/kokoro-v1_0.pth')).cpu().eval()
    # 上流のstrict=Falseへのfallbackで未読込の重みが残っていないか、全tensorを照合する。
    checkpoint = torch.load(ROOT / '.cache/teacher/kokoro-v1_0.pth', map_location='cpu', weights_only=True)
    load_audit = {}
    for name, state in checkpoint.items():
        if all(key.startswith('module.') for key in state):
            state = {key[7:]: value for key, value in state.items()}
        actual = getattr(model, name).state_dict()
        missing = sorted(set(state)-set(actual))
        extra = sorted(set(actual)-set(state))
        changed = [key for key in state.keys() & actual.keys() if not torch.equal(state[key], actual[key])]
        identity = []
        for key in extra:
            module_name, field = key.rsplit('.', 1)
            module = getattr(model, name).get_submodule(module_name)
            if isinstance(module, torch.nn.InstanceNorm1d) and field in ('weight', 'bias'):
                expected = torch.ones_like(actual[key]) if field == 'weight' else torch.zeros_like(actual[key])
                if torch.equal(actual[key], expected):
                    identity.append(key)
        # 公式0.9.4はONNX対応のためInstanceNormに恒等affineを追加している。
        # その1/0以外の欠損・変更を許容しない。
        if missing or changed or set(extra) != set(identity):
            raise ValueError(f'教師の重み読込が完全一致しません: {name}, missing={missing}, extra={extra}, changed={changed}')
        load_audit[name] = {'checkpoint_tensors_equal': len(state), 'added_identity_affine': identity}
    model.load_audit = load_audit
    voice = torch.load(ROOT / '.cache/teacher/voices/jf_alpha.pt', map_location='cpu', weights_only=True)
    return model, voice, JAG2P()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--count', type=int, default=24)
    parser.add_argument('--repair-pronunciation', action='store_true')
    args = parser.parse_args()
    import numpy as np
    import torch
    from scipy.io import wavfile
    budget = Budget()
    start = time.monotonic()
    with budget.job('setup', '教師読み込み・前段検査', 5_000_000):
        model, voice, g2p = load_teacher()
    load_seconds = time.monotonic() - start
    rows = json.loads((RESULT / 'splits.json').read_text())['rows']
    for row in rows[:args.count]:
        if args.repair_pronunciation and row['id'] != 'selection-02':
            continue
        target = RESULT / ('teacher-corrected' if args.repair_pronunciation else 'teacher') / (row['id'] + '.json')
        if target.exists():
            continue
        with budget.job('teacher', row['id'], 5_000_000) as ticket:
            phonemes, tokens = g2p(row['text'])
            original_phonemes = phonemes
            if args.repair_pronunciation:
                if not phonemes.startswith('bako '):
                    raise ValueError('事前に記録した誤読と一致しません')
                phonemes = 'h' + phonemes[1:]
            unknown = sorted(set(phonemes) - set(model.vocab))
            if unknown:
                raise ValueError(f'教師辞書の未対応記号: {unknown}')
            torch.manual_seed(20261002)
            captured = {}
            def capture(module, inputs):
                captured['f0_pred'] = inputs[1].detach().cpu().numpy().ravel()
                captured['noise_pred'] = inputs[2].detach().cpu().numpy().ravel()
            hook = model.decoder.register_forward_pre_hook(capture)
            t = time.monotonic()
            try:
                output = model(phonemes, voice[len(phonemes)-1], speed=1., return_output=True)
            finally:
                hook.remove()
            audio = output.audio.numpy()
            seconds = time.monotonic() - t
            if audio.ndim != 1 or not np.isfinite(audio).all() or np.max(abs(audio)) >= 1:
                raise ValueError('教師波形の有限値・振幅検査に不通過')
            target.parent.mkdir(parents=True, exist_ok=True)
            wav = target.with_suffix('.wav')
            controls = target.with_suffix('.npz')
            wavfile.write(wav, 24000, audio.astype(np.float32))
            np.savez_compressed(controls, **captured)
            save(target, {'id': row['id'], 'split': row['split'], 'text': row['text'],
                 'phonemes': phonemes, 'predicted_duration_frames': output.pred_dur.tolist(),
                 'original_frontend_phonemes': original_phonemes,
                 'pronunciation_repair': '辞書の箱/バコをハコへ修正。旧音声は保存' if args.repair_pronunciation else None,
                 'wav': str(wav.relative_to(ROOT)), 'wav_sha256': digest(wav),
                 'neural_controls': str(controls.relative_to(ROOT)), 'controls_sha256': digest(controls),
                 'sample_rate': 24000, 'duration_seconds': len(audio)/24000,
                 'inference_seconds': seconds, 'load_seconds': load_seconds,
                 'seed': 20261002, 'speed': 1., 'voice': 'jf_alpha', 'ticket': ticket['id'],
                 'frontend': 'misaki 0.9.4 cutlet + unidic-lite 1.0.8',
                 'research_only': True, 'human_recording': False,
                 'controls_are_neural_predictions_not_measured_ground_truth': True})
            print(json.dumps({'id': row['id'], 'phonemes': phonemes, 'duration': len(audio)/24000,
                              'seconds': seconds}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
