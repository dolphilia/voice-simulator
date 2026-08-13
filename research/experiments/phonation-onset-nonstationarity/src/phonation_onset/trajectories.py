from __future__ import annotations

import math

import numpy as np
from scipy import signal
from scipy.linalg import solve_toeplitz

from .audio import finite_or_none
from .boundaries import frames, periodicity


def _spectral(frame: np.ndarray, sample_rate: int) -> tuple[float, float, float]:
    x = (frame - np.mean(frame)) * np.hanning(frame.size)
    power = np.square(np.abs(np.fft.rfft(x)))
    frequency = np.fft.rfftfreq(frame.size, 1.0 / sample_rate)
    mask = (frequency >= 80.0) & (frequency <= min(12000.0, sample_rate * 0.48))
    selected, selected_frequency = power[mask], frequency[mask]
    total = float(np.sum(selected))
    if total <= 1e-24:
        return float("nan"), float("nan"), float("nan")
    centroid = float(np.sum(selected * selected_frequency) / total)
    flatness = float(np.exp(np.mean(np.log(np.maximum(selected, 1e-24)))) / np.mean(selected))
    slope_mask = (selected_frequency >= 500.0) & (selected_frequency <= 5000.0) & (selected > 0)
    slope = float(np.polyfit(selected_frequency[slope_mask] / 1000.0, 10.0 * np.log10(selected[slope_mask]), 1)[0]) if np.sum(slope_mask) >= 8 else float("nan")
    return centroid, flatness, slope


def _harmonic(frame: np.ndarray, sample_rate: int, f0: float, strength: float) -> tuple[float, float, float]:
    if not np.isfinite(f0) or strength < 0.2:
        return float("nan"), float("nan"), float("nan")
    x = (frame - np.mean(frame)) * np.hanning(frame.size)
    spectrum = np.abs(np.fft.rfft(x))
    frequency = np.fft.rfftfreq(frame.size, 1.0 / sample_rate)
    def near(target: float) -> float:
        mask = np.abs(frequency - target) <= max(20.0, f0 * 0.15)
        return float(np.max(spectrum[mask])) if np.any(mask) else 1e-12
    h1_h2 = 20.0 * math.log10(max(near(f0), 1e-12) / max(near(2.0 * f0), 1e-12))
    clipped = float(np.clip(strength, 1e-6, 1.0 - 1e-6))
    hnr = 10.0 * math.log10(clipped / (1.0 - clipped))
    cepstrum = np.fft.irfft(np.log(np.maximum(spectrum, 1e-12)))
    low = max(1, int(sample_rate / 500.0)); high = min(cepstrum.size - 1, int(sample_rate / 70.0))
    region = cepstrum[low : high + 1]
    cpp = float(np.max(region) - np.median(region)) if region.size else float("nan")
    return h1_h2, hnr, cpp


def _formants(frame: np.ndarray, sample_rate: int) -> tuple[list[float], list[float], float]:
    if frame.size < 128 or float(np.sqrt(np.mean(frame**2))) < 1e-5:
        return [float("nan")] * 3, [float("nan")] * 3, 0.0
    order = min(frame.size // 4, max(10, int(sample_rate / 1000) + 2))
    x = signal.lfilter([1.0, -0.97], [1.0], frame - np.mean(frame)) * np.hamming(frame.size)
    corr = signal.fftconvolve(x, x[::-1], mode="full")[frame.size - 1 : frame.size + order]
    if corr.size < order + 1 or corr[0] <= 0:
        return [float("nan")] * 3, [float("nan")] * 3, 0.0
    corr[0] *= 1.0001
    try:
        coefficients = solve_toeplitz((corr[:order], corr[:order]), -corr[1 : order + 1])
        roots = np.roots(np.concatenate(([1.0], coefficients)))
    except (ValueError, np.linalg.LinAlgError):
        return [float("nan")] * 3, [float("nan")] * 3, 0.0
    candidates: list[tuple[float, float]] = []
    for root in roots[np.imag(roots) >= 0]:
        value = math.atan2(float(np.imag(root)), float(np.real(root))) * sample_rate / (2 * math.pi)
        radius = abs(root)
        if 90 <= value <= 5000 and 0 < radius < 1:
            bandwidth = -0.5 * sample_rate * math.log(radius) / math.pi
            if 20 <= bandwidth <= 900:
                candidates.append((value, bandwidth))
    candidates.sort()
    chosen = candidates[:3]
    values = [x[0] for x in chosen] + [float("nan")] * (3 - len(chosen))
    bandwidths = [x[1] for x in chosen] + [float("nan")] * (3 - len(chosen))
    return values, bandwidths, len(chosen) / 3.0


def extract_trajectory(audio: np.ndarray, sample_rate: int, frame_ms: float = 40.0, hop_ms: float = 5.0) -> dict[str, list[float | None]]:
    size = max(128, int(round(frame_ms * sample_rate / 1000.0)))
    hop = max(1, int(round(hop_ms * sample_rate / 1000.0)))
    blocks = frames(audio, size, hop)
    time = (np.arange(blocks.shape[0]) * hop + size / 2.0) / sample_rate
    columns: dict[str, list[float | None]] = {name: [] for name in (
        "time_sec", "rms_db", "f0_hz", "periodicity", "h1_h2_db", "hnr_db", "cpp_proxy",
        "spectral_centroid_hz", "spectral_flatness", "spectral_slope_db_khz",
        "f1_hz", "f2_hz", "f3_hz", "b1_hz", "b2_hz", "b3_hz", "formant_confidence",
    )}
    for index, frame in enumerate(blocks):
        f0, strength = periodicity(frame, sample_rate)
        h1_h2, hnr, cpp = _harmonic(frame, sample_rate, f0, strength)
        centroid, flatness, slope = _spectral(frame, sample_rate)
        formants, bandwidths, confidence = _formants(frame, sample_rate)
        values = (
            time[index], 20.0 * math.log10(max(float(np.sqrt(np.mean(frame**2))), 1e-12)), f0, strength,
            h1_h2, hnr, cpp, centroid, flatness, slope,
            *formants, *bandwidths, confidence,
        )
        for key, value in zip(columns, values, strict=True):
            columns[key].append(finite_or_none(value))
    return columns


def _numeric(values: list[float | None], indices: np.ndarray) -> np.ndarray:
    array = np.asarray([np.nan if item is None else item for item in values], dtype=float)
    return array[indices]


def summarize_trajectory(trajectory: dict[str, list[float | None]], stable_start_sec: float) -> dict[str, dict[str, float | None]]:
    times = np.asarray(trajectory["time_sec"], dtype=float)
    if times.size == 0:
        return {}
    onset_indices = np.flatnonzero(times <= stable_start_sec)
    stable_indices = np.flatnonzero(times >= stable_start_sec + 0.05)
    if stable_indices.size == 0:
        stable_indices = np.flatnonzero(times >= np.quantile(times, 0.65))
    result: dict[str, dict[str, float | None]] = {}
    for key, values in trajectory.items():
        if key == "time_sec":
            continue
        onset = _numeric(values, onset_indices); stable = _numeric(values, stable_indices)
        finite_onset, finite_stable = onset[np.isfinite(onset)], stable[np.isfinite(stable)]
        start = float(np.median(finite_onset[: max(1, min(3, finite_onset.size))])) if finite_onset.size else float("nan")
        end = float(np.median(finite_stable)) if finite_stable.size else float("nan")
        result[key] = {
            "onset_median": finite_or_none(float(np.median(finite_onset)) if finite_onset.size else None),
            "stable_median": finite_or_none(end),
            "start_to_stable_delta": finite_or_none(end - start),
            "stable_std": finite_or_none(float(np.std(finite_stable)) if finite_stable.size else None),
            "coverage": float((finite_onset.size + finite_stable.size) / max(1, onset.size + stable.size)),
        }
    return result

