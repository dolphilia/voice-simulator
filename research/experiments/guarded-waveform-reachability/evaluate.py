"""固定の二つのASRを各波形に一度だけ適用する。"""
import argparse
import os
import sys
import time
from math import gcd
from campaign import LocalBudget, RESULT, ROOT, REPO, OLD, PILOT, WAVE, WRES, read, save, digest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--engine', choices=['whisper', 'reazon'], required=True)
    engine = parser.parse_args().engine
    budget = LocalBudget()
    protocol = {**read(RESULT/'protocol.json'), **read(RESULT/'engine-contract.json')}
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
    assert read(RESULT/'entrance-audit.json')['all_eight_matched']
    reuse=read(RESULT/'asr-reuse-contract.json')
    assert digest(RESULT/'engine-contract.json')==digest(WRES/'engine-contract.json')==reuse['old_engine_contract_sha256']
    config=protocol['reading_diagnostic']['contract']
    from pathlib import Path
    for n,sha in config['dictionary_files'].items():assert digest(Path(config['dictionary_path'])/n)==sha
    assert digest(config['library'])==config['library_sha256']
    cache = {}
    for name,sha in reuse['source_results'].items():
        source=REPO/name;assert digest(source)==sha
        previous=read(source)
        if previous['engine']!=engine or previous['status']!='completed':continue
        assert previous['protocol_sha256']==reuse['old_protocol_sha256']
        assert digest(WAVE/previous['wav'])==previous['wav_sha256']
        cache[(previous['wav_sha256'],previous['text'])]=(previous,source)

    manifest = read(RESULT/'render-manifest.json')
    assert manifest['search_completed_before_asr']
    for row in manifest['rows']:
        target = RESULT/'asr'/engine/(row['id']+'.json')
        if target.exists():
            existing = read(target)
            assert existing.get('wav_sha256') == row.get('wav_sha256')
            if existing['status'] == 'completed':
                cache[(existing['wav_sha256'], existing['text'])] = (existing, target)
            continue
        if row['status'] != 'completed':
            save(target, {**row, 'engine': engine, 'status': 'missing', 'ai_calls': 0})
            continue
        wav = ROOT/row['wav']
        assert digest(wav) == row['wav_sha256']
        result = {k: row[k] for k in ('id', 'text', 'variant', 'condition', 'length', 'challenge_group', 'wav', 'wav_sha256')}
        result.update(engine=engine, status='failed', used_in_optimization=False, quality_certified=False,
                      protocol_sha256=digest(RESULT/'protocol.json'))
        key = (row['wav_sha256'], row['text'])
        if key in cache:
            previous, previous_path = cache[key]
            result.update({k: previous[k] for k in ('duration_seconds', 'hypothesis', 'reference_kana', 'predicted_kana', 'errors', 'characters', 'kana_cer')})
            reference=normalize_text(pyopenjtalk.g2p(row['text'],kana=True))
            assert reference==previous['reference_kana']
            result.update(status='completed', ai_calls=0, reused_from=str(previous_path.relative_to(REPO)),
                reused_result_sha256=digest(previous_path),original_protocol_sha256=previous['protocol_sha256'],
                original_wav_sha256=previous['wav_sha256'],original_evaluation_contract_sha256=reuse['old_engine_contract_sha256'])
            save(target, result)
            print(engine, row['id'], '同一波形の保存結果を参照', flush=True)
            continue
        assert row['variant']=='wavefit','旧対照ASRが再利用できないため新規認識禁止'
        result['ai_calls'] = 1
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
                cache[key] = (result, target)
        except Exception as exc:
            if not any(e['event'] == 'start' and e['label'] == label for e in budget.events()):
                raise
            result.update(error=repr(exc), seconds=time.monotonic()-started)
            if not target.exists():
                save(target, result)
        print(engine, row['id'], result['status'], result.get('errors'), result.get('characters'), flush=True)


if __name__ == '__main__':
    main()
