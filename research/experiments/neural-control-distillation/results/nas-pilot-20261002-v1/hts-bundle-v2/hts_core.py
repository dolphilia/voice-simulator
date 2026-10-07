"""HMM生成と信号測定。教師や参照データを参照しない。"""
import numpy as np
from scipy import signal
from acoustics import estimate_f0, acoustic_features
from shared_control import predict

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

def aggregate_settings(analysis, model, base_measurement):
    d, f, bounds = predict(model, analysis)
    desired = {'active_seconds': float(sum(d)), 'f0_hz': float(np.exp(np.sum(d * np.log(f)) / sum(d)))}
    speed = base_measurement['active_seconds'] / desired['active_seconds']
    half_tone = 12 * np.log2(desired['f0_hz'] / base_measurement['f0_hz'])
    return {'speed': float(np.clip(speed, 0.6, 1.6)), 'half_tone': float(np.clip(half_tone, -6.0, 6.0)), 'unbounded_speed': float(speed), 'unbounded_half_tone': float(half_tone), 'desired': desired, 'phone_bounds': bounds}

def measure(audio, fs=24000):
    audio = np.asarray(audio, dtype=float)
    hop = round(0.01 * fs)
    rms = np.array([np.sqrt(np.mean(audio[i:i + hop] ** 2)) for i in range(0, len(audio), hop)])
    active = np.flatnonzero(rms > max(1e-05, rms.max() * 0.05))
    if not len(active):
        raise ValueError('活動区間がありません')
    start, end = (active[0] * hop, min(len(audio), (active[-1] + 1) * hop))
    f0, conf = estimate_f0(audio[start:end], fs)
    if f0 is None or conf < 0.4:
        raise ValueError('全体F0推定の信頼度が不足しています')
    return {'f0_hz': f0, 'confidence': conf, 'active_seconds': (end - start) / fs, 'total_seconds': len(audio) / fs, 'active_start': start / fs, 'active_end': end / fs, 'acoustic': acoustic_features(audio[start:end], fs)}
