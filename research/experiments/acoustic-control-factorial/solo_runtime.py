"""固定回帰で単独軸を制御する非ニューラル研究版。"""
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
from acoustic_control import predict, measure_wide
from controlled_axes import initial_settings, refined_settings
from japanese_frontend import analyze
from hts_core import render_hts
from acoustics import evaluate


def normalized(audio):
    peak = float(np.max(abs(audio)))
    gain = min(1., .95/peak) if peak else 1.
    return (audio*gain).astype(np.float32), peak, gain


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--text', required=True)
    parser.add_argument('--variant', choices=['direct_f0_only', 'direct_duration_only'], required=True)
    parser.add_argument('--pitch-reference', type=float, default=220.)
    parser.add_argument('--speed', type=float, default=1.)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError('既存出力を上書きしません')
    for name, sha in json.loads((ROOT/'manifest.json').read_text())['files'].items():
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest() != sha:
            raise ValueError('bundleの変更を検出しました')
    started = time.monotonic()
    row = analyze(args.text)
    requested = {'requested_f0': args.pitch_reference, 'speed': args.speed}
    model = json.loads((ROOT/'direct_non_neural.json').read_text())
    target = predict(model, row, **requested)
    calibration = measure_wide(render_hts(row, ROOT/'mei_normal.htsvoice'))
    initial = initial_settings(args.variant, requested, target, calibration)
    first, _, _ = normalized(render_hts(row, ROOT/'mei_normal.htsvoice', initial['speed'], initial['half_tone']))
    settings = refined_settings(args.variant, requested, target, initial, measure_wide(first))
    audio, peak, gain = normalized(render_hts(row, ROOT/'mei_normal.htsvoice', settings['speed'], settings['half_tone']))
    evaluation = evaluate(audio, {}, 24000)
    forbidden = [n for n in sys.modules if n.split('.')[0] in {'torch', 'tensorflow', 'transformers',
                 'onnxruntime', 'faster_whisper', 'ctranslate2', 'sherpa_onnx'}]
    if not evaluation['E0_pass'] or forbidden:
        raise RuntimeError('信号または実行依存の検査に不通過')
    wavfile.write(args.output, 24000, audio)
    print(json.dumps({'text': args.text, 'variant': args.variant, 'requested': requested,
        'target': target, 'calibration': calibration, 'initial_settings': initial, 'settings': settings,
        'measurement': measure_wide(audio), 'E0_pass': True, 'forbidden_imports': forbidden,
        'runtime_neural': False, 'synthesis_calls': 3, 'seconds': time.monotonic()-started,
        'max_rss_bytes_macos': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        'sha256_float32': hashlib.sha256(audio.astype('<f4').tobytes()).hexdigest(),
        'raw_peak': peak, 'output_gain': gain, 'quality_certified': False}, ensure_ascii=False))


if __name__ == '__main__':
    main()
