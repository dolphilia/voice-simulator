from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from scipy import signal
from scipy.io import wavfile

from .models import ValidationResult


def read_audio(path: Path) -> tuple[int, np.ndarray]:
    sample_rate, raw = wavfile.read(path)
    audio = np.asarray(raw)
    source_dtype = audio.dtype
    if np.issubdtype(source_dtype, np.integer):
        info = np.iinfo(source_dtype)
        scale = float(max(abs(info.min), abs(info.max)))
        audio = audio.astype(np.float64) / scale
    else:
        audio = audio.astype(np.float64)
    if audio.ndim == 2:
        audio = np.mean(audio, axis=1)
    elif audio.ndim != 1:
        raise ValueError(f"unsupported audio dimensions: {audio.shape}")
    return int(sample_rate), audio


def validate_audio(audio: np.ndarray, sample_rate: int, minimum_duration_sec: float = 0.04) -> ValidationResult:
    issues: list[str] = []
    if sample_rate <= 0:
        issues.append("invalid_sample_rate")
    if audio.ndim != 1:
        issues.append("not_mono_vector")
    if audio.size == 0:
        issues.append("empty_audio")
    if not np.all(np.isfinite(audio)):
        issues.append("non_finite_samples")
    duration = audio.size / sample_rate if sample_rate > 0 else 0.0
    if duration < minimum_duration_sec:
        issues.append("too_short")
    return ValidationResult(
        valid=not issues,
        sample_rate=sample_rate,
        sample_count=int(audio.size),
        duration_sec=float(duration),
        issues=tuple(issues),
    )


def remove_dc(audio: np.ndarray) -> np.ndarray:
    return audio - np.mean(audio) if audio.size else audio.copy()


def rms(audio: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(audio)))) if audio.size else 0.0


def level_normalize(audio: np.ndarray, target_dbfs: float = -20.0) -> np.ndarray:
    current = rms(audio)
    if current <= 1e-12:
        return audio.copy()
    target = 10.0 ** (target_dbfs / 20.0)
    return audio * (target / current)


def resample(audio: np.ndarray, source_rate: int, target_rate: int) -> np.ndarray:
    if source_rate == target_rate or audio.size == 0:
        return audio.copy()
    divisor = math.gcd(source_rate, target_rate)
    return signal.resample_poly(audio, target_rate // divisor, source_rate // divisor).astype(np.float64)


def active_bounds(audio: np.ndarray, threshold_ratio: float = 0.03) -> tuple[int, int]:
    if audio.size == 0:
        return 0, 0
    peak = float(np.max(np.abs(audio)))
    if peak <= 1e-12:
        return 0, audio.size
    indices = np.flatnonzero(np.abs(audio) >= peak * threshold_ratio)
    if indices.size == 0:
        return 0, audio.size
    return int(indices[0]), int(indices[-1] + 1)


def select_segment(audio: np.ndarray, sample_rate: int, kind: str) -> np.ndarray:
    start, end = active_bounds(audio)
    active = audio[start:end]
    if kind == "whole":
        return active
    if kind == "leading":
        return active[: min(active.size, int(round(0.18 * sample_rate)))]
    if kind == "stable":
        length = min(active.size, int(round(0.45 * sample_rate)))
        offset = max(0, (active.size - length) // 2)
        return active[offset : offset + length]
    raise ValueError(f"unsupported segment kind: {kind}")


def signal_integrity(audio: np.ndarray, sample_rate: int) -> dict[str, float]:
    if audio.size == 0:
        return {
            "clipping_ratio": 0.0,
            "dc_offset": 0.0,
            "peak_dbfs": -240.0,
            "rms_dbfs": -240.0,
            "silence_ratio": 1.0,
            "nyquist_band_ratio": 0.0,
        }
    finite = audio[np.isfinite(audio)]
    if finite.size == 0:
        return {
            "clipping_ratio": 1.0,
            "dc_offset": float("nan"),
            "peak_dbfs": float("nan"),
            "rms_dbfs": float("nan"),
            "silence_ratio": 1.0,
            "nyquist_band_ratio": float("nan"),
        }
    peak = float(np.max(np.abs(finite)))
    rms_value = rms(finite)
    clipping = float(np.mean(np.abs(finite) >= 0.999))
    silence_threshold = max(1e-5, peak * 0.01)
    silence = float(np.mean(np.abs(finite) < silence_threshold))
    if finite.size >= 32:
        spectrum = np.square(np.abs(np.fft.rfft(finite * np.hanning(finite.size))))
        freqs = np.fft.rfftfreq(finite.size, 1.0 / sample_rate)
        total = float(np.sum(spectrum))
        high = float(np.sum(spectrum[freqs >= sample_rate * 0.45]))
        nyquist_ratio = high / total if total > 0.0 else 0.0
    else:
        nyquist_ratio = 0.0
    return {
        "clipping_ratio": clipping,
        "dc_offset": float(np.mean(finite)),
        "peak_dbfs": 20.0 * math.log10(max(peak, 1e-12)),
        "rms_dbfs": 20.0 * math.log10(max(rms_value, 1e-12)),
        "silence_ratio": silence,
        "nyquist_band_ratio": nyquist_ratio,
    }
