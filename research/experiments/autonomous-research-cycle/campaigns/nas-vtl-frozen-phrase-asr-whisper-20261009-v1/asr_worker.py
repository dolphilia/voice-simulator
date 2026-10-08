"""固定モデル・固定正規化による48音声の評価。結果はpipeへ返す。"""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from math import gcd
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1];REPO=ROOT.parents[2]
SUITE=ROOT/'campaigns/nas-vtl-frozen-phrase-suite-20261009-v1'
OLD=REPO/'research/experiments/autonomous-speech-synthesis'
PILOT=REPO/'research/experiments/neural-control-distillation'
sys.path.insert(0,str(ROOT))
from budget import read,digest



def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--engine', choices=['whisper', 'reazon'], required=True)
    name = parser.parse_args().engine
    assert Path(tempfile.gettempdir()).resolve() == Path(os.environ['TMPDIR']).resolve()
    engine = read(SUITE / 'engine-contract.json')
    sys.path[:0] = [str(OLD), str(PILOT / '.cache/packages')]
    from diagnostics import normalize_text, edit_distance
    import numpy as np
    import pyopenjtalk
    from scipy import signal
    from scipy.io import wavfile
    if name == 'whisper':
        from faster_whisper import WhisperModel
        recognizer = WhisperModel(engine['whisper_path'], device='cpu', compute_type='int8',
                                 cpu_threads=4, local_files_only=True)
    else:
        import sherpa_onnx
        cache = PILOT / '.cache/reazonspeech'
        recognizer = sherpa_onnx.OfflineRecognizer.from_transducer(
            encoder=str(cache / 'encoder-epoch-99-avg-1.int8.onnx'),
            decoder=str(cache / 'decoder-epoch-99-avg-1.int8.onnx'),
            joiner=str(cache / 'joiner-epoch-99-avg-1.int8.onnx'), tokens=str(cache / 'tokens.txt'),
            num_threads=2, sample_rate=16000, feature_dim=80,
            decoding_method='greedy_search', provider='cpu')
    rows = []
    for item in read(HERE / 'render-manifest.json')['rows']:
        record = read(REPO / item['record'])
        if record['wav'] is None:
            result={k:record[k] for k in ('id','text','length','challenge_group','condition','variant','wav','wav_sha256')}
            result.update(status='missing_generation',engine=name,ai_calls=0,hypothesis=None,reference_kana=normalize_text(pyopenjtalk.g2p(record['text'],kana=True)),predicted_kana=None,errors=None,characters=len(normalize_text(pyopenjtalk.g2p(record['text'],kana=True))),protocol_sha256=digest(SUITE/'protocol.json'),engine_contract_sha256=digest(SUITE/'engine-contract.json'))
            rows.append(result)
            continue
        assert digest(REPO / record['wav']) == record['wav_sha256']
        fs, raw = wavfile.read(REPO / record['wav'])
        assert raw.ndim == 1 and len(raw) / fs <= 30
        started = time.monotonic()
        if name == 'whisper':
            segments, _ = recognizer.transcribe(str(REPO / record['wav']), language='ja',
                beam_size=5, initial_prompt=None, condition_on_previous_text=False, vad_filter=False)
            hypothesis = ''.join(s.text for s in segments)
        else:
            audio = raw.astype(np.float32) / (32768. if raw.dtype == np.int16 else 1.)
            divisor = gcd(fs, 16000)
            audio = signal.resample_poly(audio, 16000 // divisor, fs // divisor).astype(np.float32)
            stream = recognizer.create_stream()
            stream.accept_waveform(16000, audio)
            recognizer.decode_stream(stream)
            hypothesis = stream.result.text
        ref = normalize_text(pyopenjtalk.g2p(record['text'], kana=True))
        pred = normalize_text(pyopenjtalk.g2p(hypothesis, kana=True)) if hypothesis else ''
        result = {k: record[k] for k in (
            'id', 'text', 'length', 'challenge_group', 'condition', 'variant', 'wav', 'wav_sha256')}
        result.update(status='completed', engine=name, ai_calls=1, hypothesis=hypothesis,
            reference_kana=ref, predicted_kana=pred, errors=edit_distance(ref, pred),
            characters=len(ref), duration_seconds=len(raw) / fs, seconds=time.monotonic() - started,
            protocol_sha256=digest(SUITE / 'protocol.json'),
            engine_contract_sha256=digest(SUITE / 'engine-contract.json'),
            evaluator_sha256=digest(Path(__file__)), quality_certified=False,
            used_in_optimization=False)
        rows.append(result)
        if len(rows) % 16 == 0:
            print(name, len(rows), '/48', file=sys.stderr, flush=True)
    assert len(rows) == 48
    print(json.dumps(dict(rows=rows, ai_calls=sum(x['ai_calls'] for x in rows), reused=0), ensure_ascii=False, allow_nan=False))


if __name__ == '__main__':
    main()
