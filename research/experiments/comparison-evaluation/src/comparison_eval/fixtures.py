from __future__ import annotations

import math

import numpy as np
from scipy import signal


DEFAULT_FORMANTS = ((730.0, 90.0), (1090.0, 120.0), (2440.0, 180.0))


def harmonic_source(f0_hz: float = 140.0, duration_sec: float = 1.0, sample_rate: int = 48000, tilt_db_octave: float = -10.0) -> np.ndarray:
    sample_count = int(round(duration_sec * sample_rate))
    time = np.arange(sample_count, dtype=np.float64) / sample_rate
    result = np.zeros(sample_count, dtype=np.float64)
    harmonic_count = max(1, int((sample_rate / 2.0) // f0_hz))
    exponent = -tilt_db_octave / 6.020599913
    for harmonic in range(1, harmonic_count + 1):
        result += np.sin(2.0 * np.pi * harmonic * f0_hz * time) / (harmonic**exponent)
    peak = float(np.max(np.abs(result)))
    return 0.7 * result / max(peak, 1e-12)


def apply_formants(audio: np.ndarray, sample_rate: int, formants: tuple[tuple[float, float], ...] = DEFAULT_FORMANTS) -> np.ndarray:
    result = audio.astype(np.float64, copy=True)
    for frequency, bandwidth in formants:
        quality = max(0.5, frequency / bandwidth)
        numerator, denominator = signal.iirpeak(frequency, quality, fs=sample_rate)
        result = signal.lfilter(numerator, denominator, result)
    peak = float(np.max(np.abs(result))) if result.size else 0.0
    return 0.7 * result / max(peak, 1e-12)


def synthetic_vowel(f0_hz: float = 140.0, duration_sec: float = 1.0, sample_rate: int = 48000, formants: tuple[tuple[float, float], ...] = DEFAULT_FORMANTS) -> np.ndarray:
    return apply_formants(harmonic_source(f0_hz, duration_sec, sample_rate), sample_rate, formants)


def seeded_noise(duration_sec: float = 1.0, sample_rate: int = 48000, seed: int = 1, low_hz: float = 3000.0, high_hz: float = 10000.0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    noise = rng.normal(size=int(round(duration_sec * sample_rate)))
    sos = signal.butter(6, (low_hz, min(high_hz, sample_rate * 0.48)), btype="bandpass", fs=sample_rate, output="sos")
    filtered = signal.sosfilt(sos, noise)
    return 0.3 * filtered / max(float(np.max(np.abs(filtered))), 1e-12)


def transition_event(sample_rate: int = 48000, duration_sec: float = 1.0) -> np.ndarray:
    first = synthetic_vowel(130.0, duration_sec, sample_rate, ((500.0, 80.0), (900.0, 110.0), (2400.0, 180.0)))
    second = synthetic_vowel(180.0, duration_sec, sample_rate, ((350.0, 70.0), (2100.0, 130.0), (2900.0, 200.0)))
    crossfade = np.linspace(0.0, 1.0, first.size)
    crossfade = 1.0 / (1.0 + np.exp(-14.0 * (crossfade - 0.5)))
    return first * (1.0 - crossfade) + second * crossfade


def add_noise_at_snr(audio: np.ndarray, snr_db: float, seed: int = 2) -> np.ndarray:
    rng = np.random.default_rng(seed)
    noise = rng.normal(size=audio.size)
    audio_rms = math.sqrt(float(np.mean(audio**2)))
    noise_rms = math.sqrt(float(np.mean(noise**2)))
    scaled = noise * (audio_rms / max(noise_rms, 1e-12)) * 10.0 ** (-snr_db / 20.0)
    return audio + scaled


def delay(audio: np.ndarray, samples: int) -> np.ndarray:
    if samples == 0:
        return audio.copy()
    if samples > 0:
        return np.pad(audio, (samples, 0))[: audio.size]
    return np.pad(audio[-samples:], (0, -samples))[: audio.size]


def time_stretch(audio: np.ndarray, ratio: float) -> np.ndarray:
    if ratio <= 0.0:
        raise ValueError("ratio must be positive")
    return signal.resample(audio, max(1, int(round(audio.size * ratio)))).astype(np.float64)


def apply_spectral_tilt(audio: np.ndarray, sample_rate: int, delta_db_octave: float, pivot_hz: float = 500.0) -> np.ndarray:
    if audio.size == 0:
        return audio.copy()
    spectrum = np.fft.rfft(audio)
    frequencies = np.fft.rfftfreq(audio.size, 1.0 / sample_rate)
    octaves = np.log2(np.maximum(frequencies, pivot_hz / 16.0) / pivot_hz)
    gain = np.power(10.0, delta_db_octave * octaves / 20.0)
    result = np.fft.irfft(spectrum * gain, n=audio.size)
    return result * (np.sqrt(np.mean(audio**2)) / max(np.sqrt(np.mean(result**2)), 1e-12))
