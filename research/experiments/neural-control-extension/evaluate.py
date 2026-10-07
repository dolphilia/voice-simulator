"""固定設定の二つのASRで内容を診断する。自然さの認定はしない。"""
import argparse
import json
import os
import sys
import time
from math import gcd
import numpy as np
from scipy.io import wavfile
from scipy import signal
from campaign import ExtensionBudget, ROOT, PILOT, RESULT, save, digest
OLD = ROOT.parent/'autonomous-speech-synthesis'
sys.path.insert(0, str(OLD))
from diagnostics import normalize_text, edit_distance


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--engine', choices=['whisper', 'reazon'], required=True)
    parser.add_argument('--source', choices=['render', 'teacher', 'relative', 'bounded'], default='render')
    args = parser.parse_args()
    budget = ExtensionBudget()
    os.environ['HF_HUB_OFFLINE'] = '1'
    import pyopenjtalk
    with budget.job('setup', '追加比較ASR読込: '+args.engine, 1000000):
        if args.engine == 'whisper':
            from faster_whisper import WhisperModel
            recognizer = WhisperModel('base', device='cpu', compute_type='int8', cpu_threads=4,
                                      download_root=str(OLD/'.cache/ai/whisper'), local_files_only=True)
        else:
            sys.path.insert(0, str(PILOT/'.cache/packages'))
            import sherpa_onnx
            cache = PILOT/'.cache/reazonspeech'
            recognizer = sherpa_onnx.OfflineRecognizer.from_transducer(
                encoder=str(cache/'encoder-epoch-99-avg-1.int8.onnx'), decoder=str(cache/'decoder-epoch-99-avg-1.int8.onnx'),
                joiner=str(cache/'joiner-epoch-99-avg-1.int8.onnx'), tokens=str(cache/'tokens.txt'),
                num_threads=2, sample_rate=16000, feature_dim=80, decoding_method='greedy_search', provider='cpu')
    for path in sorted((RESULT/args.source).rglob('*.json')):
        row = json.loads(path.read_text())
        if 'wav' not in row:
            continue
        if args.source == 'relative' and row['condition'] != 'challenge':
            continue
        wav = ROOT/row['wav']
        sha = digest(wav)
        if sha != row['wav_sha256']:
            raise ValueError('入力波形のハッシュ不一致')
        target = RESULT/'asr'/args.engine/args.source/path.relative_to(RESULT/args.source)
        if target.exists():
            if json.loads(target.read_text())['wav_sha256'] != sha:
                raise ValueError('評価済み波形の変更')
            continue
        with budget.job('ai', str(target.relative_to(RESULT)), 500000):
            start = time.monotonic()
            if args.engine == 'whisper':
                segments, _ = recognizer.transcribe(str(wav), language='ja', beam_size=5, initial_prompt=None,
                                                     condition_on_previous_text=False, vad_filter=False)
                hypothesis = ''.join(s.text for s in segments)
            else:
                fs, audio = wavfile.read(wav)
                audio = audio.astype(np.float32)/(32768. if audio.dtype == np.int16 else 1.)
                if audio.ndim != 1:
                    raise ValueError('単一チャンネルを要求します')
                common = gcd(fs, 16000)
                audio = signal.resample_poly(audio, 16000//common, fs//common).astype(np.float32)
                stream = recognizer.create_stream()
                stream.accept_waveform(16000, audio)
                recognizer.decode_stream(stream)
                hypothesis = stream.result.text
            reference = normalize_text(pyopenjtalk.g2p(row['text'], kana=True))
            predicted = normalize_text(pyopenjtalk.g2p(hypothesis, kana=True)) if hypothesis else ''
            errors = edit_distance(reference, predicted)
            save(target, {'id': row['id'], 'text': row['text'], 'variant': row['variant'], 'condition': row['condition'],
                          'wav': row['wav'], 'wav_sha256': sha, 'engine': args.engine, 'hypothesis': hypothesis,
                          'reference_kana': reference, 'predicted_kana': predicted, 'errors': errors,
                          'characters': len(reference), 'kana_cer': errors/max(1, len(reference)),
                          'seconds': time.monotonic()-start, 'used_in_optimization': False, 'perception_qualification': False})
        print(args.engine, row['id'], row['condition'], row['variant'], errors, len(reference), flush=True)


if __name__ == '__main__':
    main()
