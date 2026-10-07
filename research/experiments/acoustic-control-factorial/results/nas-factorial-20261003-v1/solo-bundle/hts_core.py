"""固定HMMの生成部分だけを抽出した非ニューラル実装。"""
import numpy as np
from scipy import signal

def render_hts(analysis, voice_path, speed=1.0, half_tone=0.0):
    import pyopenjtalk
    engine = pyopenjtalk.HTSEngine(str(voice_path).encode())
    try:
        engine.set_speed(float(speed))
        engine.add_half_tone(float(half_tone))
        raw = engine.synthesize(analysis['full_context_labels'])
        fs = engine.get_sampling_frequency()
    finally:
        engine.clear()
    if fs != 48000:
        raise ValueError('HTS標本化周波数が想定と異なります')
    audio = signal.resample_poly(np.asarray(raw, dtype=float) / 32768, 1, 2)
    n = min(round(0.012 * 24000), len(audio) // 2)
    env = np.sin(np.linspace(0, np.pi / 2, n)) ** 2
    audio[:n] *= env
    audio[-n:] *= env[::-1]
    return audio
