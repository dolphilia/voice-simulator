"""固定の二つのASRを各波形に一度だけ適用する。"""
import argparse
import os
import sys
import time
from math import gcd
from campaign import FactorialBudget, RESULT, ROOT, REPO, OLD, PILOT, read, save, digest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--engine', choices=['whisper', 'reazon'], required=True)
    engine = parser.parse_args().engine
    budget = FactorialBudget()
    protocol = read(RESULT/'protocol.json')
    for name, sha in protocol['asr_model_hashes'].items():
        assert digest(REPO/name) == sha
    assert digest(OLD/'diagnostics.py') == protocol['normalizer_source_sha256']
    os.environ['HF_HUB_OFFLINE'] = '1'
    sys.path.insert(0, str(OLD))
    from diagnostics import normalize_text, edit_distance
    import pyopenjtalk
    import numpy as np
    from scipy import signal
    from scipy.io import wavfile
    with budget.job('setup', '固定認識器読込 '+engine, 1_000_000):
        if engine == 'whisper':
            from faster_whisper import WhisperModel
            recognizer = WhisperModel(protocol['whisper_path'], device='cpu', compute_type='int8', cpu_threads=4,
                                      local_files_only=True)
        else:
            sys.path.insert(0, str(PILOT/'.cache/packages'))
            import sherpa_onnx
            cache = PILOT/'.cache/reazonspeech'
            recognizer = sherpa_onnx.OfflineRecognizer.from_transducer(
                encoder=str(cache/'encoder-epoch-99-avg-1.int8.onnx'), decoder=str(cache/'decoder-epoch-99-avg-1.int8.onnx'),
                joiner=str(cache/'joiner-epoch-99-avg-1.int8.onnx'), tokens=str(cache/'tokens.txt'),
                num_threads=2, sample_rate=16000, feature_dim=80, decoding_method='greedy_search', provider='cpu')
    for row in read(RESULT/'render-manifest.json')['rows']:
        target = RESULT/'asr'/engine/(row['id']+'.json')
        if target.exists():
            assert read(target)['wav_sha256'] == row.get('wav_sha256')
            continue
        if row['status'] != 'completed':
            save(target, {**row, 'engine': engine, 'status': 'missing', 'ai_calls': 0})
            continue
        wav = ROOT/row['wav']
        assert digest(wav) == row['wav_sha256']
        result = {k: row[k] for k in ('id', 'text', 'variant', 'condition', 'length', 'challenge_group', 'wav', 'wav_sha256')}
        result.update(engine=engine, status='failed', used_in_optimization=False, quality_certified=False,
                      protocol_sha256=digest(RESULT/'protocol.json'))
        started = time.monotonic()
        label = str(target.relative_to(RESULT))
        try:
            with budget.job('ai', label, 100_000):
                fs, raw = wavfile.read(wav)
                assert raw.ndim == 1
                result['duration_seconds'] = len(raw)/fs
                if engine == 'whisper':
                    segments, _ = recognizer.transcribe(str(wav), language='ja', beam_size=5, initial_prompt=None,
                        condition_on_previous_text=False, vad_filter=False)
                    hypothesis = ''.join(s.text for s in segments)
                else:
                    audio = raw.astype(np.float32)/(32768. if raw.dtype == np.int16 else 1.)
                    common = gcd(fs, 16000)
                    audio = signal.resample_poly(audio, 16000//common, fs//common).astype(np.float32)
                    stream = recognizer.create_stream()
                    stream.accept_waveform(16000, audio)
                    recognizer.decode_stream(stream)
                    hypothesis = stream.result.text
                reference = normalize_text(pyopenjtalk.g2p(row['text'], kana=True))
                predicted = normalize_text(pyopenjtalk.g2p(hypothesis, kana=True)) if hypothesis else ''
                errors = edit_distance(reference, predicted)
                result.update(status='completed', hypothesis=hypothesis, reference_kana=reference,
                    predicted_kana=predicted, errors=errors, characters=len(reference),
                    kana_cer=errors/max(1, len(reference)), seconds=time.monotonic()-started)
                save(target, result)
        except Exception as exc:
            if not any(e['event'] == 'start' and e['label'] == label for e in budget.events()):
                raise
            result.update(error=repr(exc), seconds=time.monotonic()-started)
            if not target.exists():
                save(target, result)
        print(engine, row['id'], result['status'], result.get('errors'), result.get('characters'), flush=True)


if __name__ == '__main__':
    main()
