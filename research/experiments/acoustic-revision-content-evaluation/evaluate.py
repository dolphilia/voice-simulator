"""固定100波形を一度ずつ認識し、失敗も台帳へ残す。"""
import argparse
import os
import sys
import time
from math import gcd
import importlib.metadata
import numpy as np
from scipy.io import wavfile
from scipy import signal
from campaign import ContentBudget, OLD, PILOT, EXT, RESULT, REPO, read, save, digest
sys.path.insert(0, str(OLD))
from diagnostics import normalize_text, edit_distance


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--engine', choices=['whisper', 'reazon'], required=True)
    engine = parser.parse_args().engine
    budget = ContentBudget()
    protocol = read(RESULT/'protocol.json')
    for path, sha in protocol['model_hashes'].items():
        assert digest(REPO/path) == sha, '認識モデルのハッシュ不一致'
    assert digest(OLD/'diagnostics.py') == protocol['normalizer_source_sha256']
    os.environ['HF_HUB_OFFLINE'] = '1'
    import pyopenjtalk
    with budget.job('setup', '固定ASR読込: '+engine, 1_000_000):
        if engine == 'whisper':
            from faster_whisper import WhisperModel
            recognizer = WhisperModel(protocol['whisper_path'], device='cpu', compute_type='int8', cpu_threads=4,
                                      local_files_only=True)
        else:
            sys.path.insert(0, str(PILOT/'.cache/packages'))
            import sherpa_onnx
            cache = PILOT/'.cache/reazonspeech'
            recognizer = sherpa_onnx.OfflineRecognizer.from_transducer(
                encoder=str(cache/'encoder-epoch-99-avg-1.int8.onnx'),
                decoder=str(cache/'decoder-epoch-99-avg-1.int8.onnx'),
                joiner=str(cache/'joiner-epoch-99-avg-1.int8.onnx'), tokens=str(cache/'tokens.txt'),
                num_threads=2, sample_rate=16000, feature_dim=80, decoding_method='greedy_search', provider='cpu')
        save(RESULT/('environment-'+engine+'.json'), {'python': sys.version,
             'packages': {p: importlib.metadata.version(p) for p in
                          ['numpy', 'scipy', 'pyopenjtalk', 'faster-whisper', 'ctranslate2']},
             'sherpa_version': getattr(sys.modules.get('sherpa_onnx'), '__version__', None),
             'model_hashes': protocol['model_hashes'], 'offline': True})
    for i, row in enumerate(protocol['rows']):
        target = RESULT/'asr'/engine/(row['id']+'.json')
        if target.exists():
            assert read(target)['wav_sha256'] == row['wav_sha256']
            continue
        wav = EXT/row['wav']
        assert digest(wav) == row['wav_sha256'], '波形のハッシュ不一致'
        start = time.monotonic()
        result = {**row, 'engine': engine, 'status': 'failed', 'used_in_optimization': False,
                  'perception_qualification': False, 'protocol_sha256': digest(RESULT/'protocol.json')}
        try:
            with budget.job('ai', str(target.relative_to(RESULT)), 100_000):
                fs, raw = wavfile.read(wav)
                assert raw.ndim == 1, '単一チャンネルを要求します'
                result['duration_seconds'] = len(raw)/fs
                if engine == 'whisper':
                    segments, _ = recognizer.transcribe(str(wav), language='ja', beam_size=5,
                        initial_prompt=None, condition_on_previous_text=False, vad_filter=False)
                    hypothesis = ''.join(s.text for s in segments)
                else:
                    audio = raw.astype(np.float32)/(32768. if raw.dtype == np.int16 else 1.)
                    common = gcd(fs, 16000)
                    audio = signal.resample_poly(audio, 16000//common, fs//common).astype(np.float32)
                    stream = recognizer.create_stream()
                    stream.accept_waveform(16000, audio)
                    recognizer.decode_stream(stream)
                    hypothesis = stream.result.text
                result['hypothesis'] = hypothesis
                reference = normalize_text(pyopenjtalk.g2p(row['text'], kana=True))
                predicted = normalize_text(pyopenjtalk.g2p(hypothesis, kana=True)) if hypothesis else ''
                errors = edit_distance(reference, predicted)
                result.update(status='completed', reference_kana=reference, predicted_kana=predicted,
                    errors=errors, characters=len(reference), kana_cer=errors/max(1, len(reference)),
                    seconds=time.monotonic()-start)
                save(target, result)
        except Exception as exc:
            # 予約前の上限拒否は認識試行に数えず、処理を停止する。
            starts = [e for e in budget.events() if e['event'] == 'start' and e['label'] == str(target.relative_to(RESULT))]
            if not starts:
                raise
            result.update(status='failed', error=repr(exc), seconds=time.monotonic()-start)
            if not target.exists():
                save(target, result)
        print(engine, i+1, row['id'], result['status'], result.get('errors'), result.get('characters'), flush=True)


if __name__ == '__main__':
    main()
