"""文章入力の非ニューラル生成。同じ生成LF0制御をWORLDとHTSに渡す。"""
import argparse
import base64
import hashlib
import io
import json
import math
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import numpy as np
from scipy.io import wavfile
from japanese_frontend import analyze
from timing_engine import Engine
from shape_arrays import synthesize as shape_synthesize
from controls_v2 import transform
METHODS=['native','half_contour','flat_contour']
from contour import apply_contour
from calibration import calibrated_lf0
from acoustics import evaluate


def ah(value):
    return hashlib.sha256(np.asarray(value, dtype='<f8').tobytes()).hexdigest()


def verify():
    for name, expected in json.loads((ROOT / 'manifest.json').read_text())['files'].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected, name


def generate(text, method, speed, pitch, full=False):
    if method not in list(METHODS):
        raise ValueError('未登録の方式')
    row = analyze(text)
    with Engine(row, ROOT / 'mei_normal.htsvoice', speed=speed,
                half_tone=12 * math.log2(pitch / 220)) as engine:
        before = engine.snapshot()
        variance = engine.variance()
        settings = engine.get_settings()
        native = engine.parameters()
        params,control,relative_error,invariants=transform('calibrated',native,row['full_context_labels'],before['duration'],pitch)
        params,contour=apply_contour(params,pitch,method)
        voiced=params[1][:,0]>0
        assert control['AP_noise_power_factor']==1.
        raw,conversion=shape_synthesize(params,settings,method)
        assert engine.snapshot() == before and np.array_equal(engine.variance(), variance)
        assert engine.get_settings() == settings
    audio = (raw * .25).astype(np.float32)
    e0 = evaluate(audio, {}, 24000)
    # 波形は保存し、不通過も分母に残す。E0の不通過は条件の変更で救済しない。
    forbidden = [n for n in sys.modules if n.split('.')[0] in (
        'torch', 'tensorflow', 'transformers', 'faster_whisper', 'ctranslate2',
        'onnxruntime', 'sherpa_onnx')]
    assert not forbidden
    output = io.BytesIO()
    wavfile.write(output, 24000, audio)
    data = output.getvalue()
    meta = dict(sha256=hashlib.sha256(data).hexdigest(), synthesis_calls=1, E0_calls=1,
                E0=e0, E0_pass=e0['E0_pass'], invariants_pass=bool(invariants and contour['passed']),
                relative_LF0_max_abs_error=contour['target_max_abs_error'], calibration_relative_LF0_max_abs_error=relative_error, contour_target_max_abs_error=contour['target_max_abs_error'], contour=contour, control=control,
                duration=before['duration'], msd=before['msd'], settings=settings,
                state_sha256=hashlib.sha256(json.dumps(before, sort_keys=True).encode()).hexdigest(),
                variance_sha256=ah(variance), native_parameter_hashes=[ah(v) for v in native],
                output_parameter_hashes=[ah(v) for v in params],
                output_gain=.25, conversion=conversion, forbidden_imports=forbidden,
                runtime_neural=False, teacher_audio=0, utterance_tables=0,
                generated_lf0_median_hz=float(np.exp(np.median(params[1][voiced, 0]))))
    return (data, meta, params, row) if full else (data, meta)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--text', required=True)
    parser.add_argument('--method', choices=list(METHODS), required=True)
    parser.add_argument('--speed', type=float, required=True)
    parser.add_argument('--pitch', type=float, required=True)
    args = parser.parse_args()
    verify()
    data, meta = generate(args.text, args.method, args.speed, args.pitch)
    print(json.dumps(dict(meta=meta, wav_base64=base64.b64encode(data).decode()), allow_nan=False))


if __name__ == '__main__':
    main()
