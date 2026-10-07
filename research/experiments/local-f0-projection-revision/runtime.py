"""ニューラル・教師・発話別検索を使わない局所F0研究版の入口。"""
import argparse
import hashlib
import json
from pathlib import Path
import resource
import sys
import time
import numpy as np
from scipy.io import wavfile
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from japanese_frontend import analyze
from local_renderer import StateEngine
from local_control import deltas, linear_predict
from acoustics import evaluate
from acoustic_control import measure_wide


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--text', required=True)
    p.add_argument('--model', choices=['direct_non_neural', 'distilled_non_neural'], required=True)
    p.add_argument('--pitch-reference', type=float, default=220.)
    p.add_argument('--speed', type=float, default=1.)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    if args.output.exists():
        raise FileExistsError('既存出力を上書きしません')
    if not np.isfinite([args.pitch_reference, args.speed]).all() or not 140 <= args.pitch_reference <= 320 or not .75 <= args.speed <= 1.3:
        raise ValueError('研究版の指定範囲外です')
    manifest = json.loads((ROOT/'manifest.json').read_text())
    for name, sha in manifest['files'].items():
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest() == sha
    import pyopenjtalk
    import pyopenjtalk.htsengine
    required = manifest['required_runtime']
    assert pyopenjtalk.__version__ == required['pyopenjtalk_version']
    assert hashlib.sha256(Path(pyopenjtalk.htsengine.__file__).read_bytes()).hexdigest() == required['hts_binary_sha256']
    started = time.monotonic()
    row = analyze(args.text)
    model = json.loads((ROOT/(args.model+'.json')).read_text())
    settings = {'speed': args.speed, 'half_tone': float(12*np.log2(args.pitch_reference/220))}
    with StateEngine(row, ROOT/'mei_normal.htsvoice', **settings) as engine:
        before = engine.snapshot()
        correction, phones = deltas(row, before, lambda x: linear_predict(model, x))
        engine.modify(correction)
        after = engine.snapshot()
        assert before['duration'] == after['duration'] and before['msd'] == after['msd']
        assert before['means'][0] == after['means'][0] and before['means'][2] == after['means'][2]
        assert all(a[1:] == z[1:] for a, z in zip(before['means'][1], after['means'][1]))
        audio, _ = engine.generate()
    peak = float(np.max(abs(audio)))
    gain = min(1., .95/peak) if peak else 1.
    audio = (audio*gain).astype(np.float32)
    e = evaluate(audio, {}, 24000)
    forbidden = [n for n in sys.modules if n.split('.')[0] in ('torch', 'tensorflow', 'transformers',
        'onnxruntime', 'faster_whisper', 'ctranslate2', 'sherpa_onnx')]
    if not e['E0_pass'] or forbidden:
        raise RuntimeError('実行依存・信号の検査に不通過')
    wavfile.write(args.output, 24000, audio)
    print(json.dumps({'text': args.text, 'model': args.model, 'settings': settings, 'phone_residuals': phones,
        'measurement': measure_wide(audio), 'synthesis_calls': 1, 'E0_pass': True, 'runtime_neural': False,
        'forbidden_imports': forbidden, 'maximum_abs_half_tone': float(np.max(abs(correction))),
        'sha256_float32': hashlib.sha256(audio.astype('<f4').tobytes()).hexdigest(),
        'seconds': time.monotonic()-started, 'max_rss_bytes_macos': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        'quality_certified': False, 'content_evaluated': False}, ensure_ascii=False))


if __name__ == '__main__':
    main()
