from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
from scipy import signal

from .audio import finite_or_none


@dataclass(frozen=True)
class BoundaryResult:
    acoustic_activity_onset_sec: float
    periodicity_onset_sec: float
    stable_pitch_onset_sec: float
    stable_source_onset_sec: float
    stable_vowel_onset_sec: float
    activity_end_sec: float
    confidence: float
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {key: finite_or_none(value) if isinstance(value, float) else list(value) if isinstance(value, tuple) else value for key, value in asdict(self).items()}


def frames(audio: np.ndarray, size: int, hop: int) -> np.ndarray:
    if size <= 0 or hop <= 0 or audio.size < size:
        return np.empty((0, max(size, 0)), dtype=np.float64)
    count = 1 + (audio.size - size) // hop
    return np.lib.stride_tricks.sliding_window_view(audio, size)[::hop][:count].copy()


def periodicity(frame: np.ndarray, sample_rate: int, minimum_hz: float = 70.0, maximum_hz: float = 500.0) -> tuple[float, float]:
    if frame.size < 64 or float(np.sqrt(np.mean(frame**2))) < 1e-6:
        return float("nan"), 0.0
    x = (frame - np.mean(frame)) * np.hanning(frame.size)
    corr = signal.fftconvolve(x, x[::-1], mode="full")[frame.size - 1 :]
    if corr[0] <= 1e-20:
        return float("nan"), 0.0
    corr /= corr[0]
    low = max(1, int(sample_rate / maximum_hz))
    high = min(corr.size - 1, int(sample_rate / minimum_hz))
    if high <= low:
        return float("nan"), 0.0
    index = int(np.argmax(corr[low : high + 1])) + low
    strength = float(np.clip(corr[index], 0.0, 1.0))
    return float(sample_rate / index), strength


def _first_run(mask: np.ndarray, length: int, start: int = 0) -> int | None:
    if mask.size < length:
        return None
    run = np.convolve(mask.astype(np.int16), np.ones(length, dtype=np.int16), mode="valid")
    choices = np.flatnonzero((run >= length) & (np.arange(run.size) >= start))
    return int(choices[0]) if choices.size else None


def detect_boundaries(audio: np.ndarray, sample_rate: int, frame_ms: float = 40.0, hop_ms: float = 5.0) -> tuple[BoundaryResult, dict[str, list[float | None]]]:
    frame_size = max(128, int(round(frame_ms * sample_rate / 1000.0)))
    hop = max(1, int(round(hop_ms * sample_rate / 1000.0)))
    block = frames(audio, frame_size, hop)
    if block.size == 0:
        empty = BoundaryResult(*(float("nan"),) * 6, confidence=0.0, reasons=("too_short",))
        return empty, {"time_sec": [], "rms_db": [], "f0_hz": [], "periodicity": []}
    time = (np.arange(block.shape[0]) * hop + frame_size / 2.0) / sample_rate
    levels = np.sqrt(np.mean(block**2, axis=1))
    rms_db = 20.0 * np.log10(np.maximum(levels, 1e-12))
    f0 = np.full(block.shape[0], np.nan)
    strength = np.zeros(block.shape[0])
    for index, frame in enumerate(block):
        f0[index], strength[index] = periodicity(frame, sample_rate)

    noise_frames = max(1, min(block.shape[0] // 5, int(round(0.1 / (hop / sample_rate)))))
    noise_db = float(np.median(rms_db[:noise_frames]))
    peak_db = float(np.max(rms_db))
    activity_threshold = max(noise_db + 12.0, peak_db - 35.0)
    activity = rms_db >= activity_threshold
    activity_index = _first_run(activity, 3)
    activity_indices = np.flatnonzero(activity)
    end_index = int(activity_indices[-1]) if activity_indices.size else block.shape[0] - 1
    reasons: list[str] = []
    if activity_index is None:
        activity_index = 0
        reasons.append("activity_not_found")

    periodic_mask = activity & (strength >= 0.35)
    periodic_index = _first_run(periodic_mask, 3, activity_index)
    if periodic_index is None:
        periodic_index = activity_index
        reasons.append("periodicity_not_found")

    tail_start = max(periodic_index, int(block.shape[0] * 0.55))
    tail = f0[tail_start:]
    tail_strength = strength[tail_start:]
    valid_tail = np.isfinite(tail) & (tail_strength >= 0.35)
    stable_f0 = float(np.median(tail[valid_tail])) if np.any(valid_tail) else float("nan")
    if np.isfinite(stable_f0):
        cents = np.full_like(f0, np.inf)
        valid = np.isfinite(f0) & (f0 > 0)
        cents[valid] = np.abs(1200.0 * np.log2(f0[valid] / stable_f0))
        pitch_mask = periodic_mask & (cents <= 80.0)
        pitch_index = _first_run(pitch_mask, 5, periodic_index)
    else:
        pitch_index = None
    if pitch_index is None:
        pitch_index = periodic_index
        reasons.append("stable_pitch_not_found")

    stable_level = float(np.median(rms_db[max(tail_start, pitch_index) :]))
    source_mask = periodic_mask & (np.abs(rms_db - stable_level) <= 4.0)
    source_index = _first_run(source_mask, 5, pitch_index)
    if source_index is None:
        source_index = pitch_index
        reasons.append("stable_source_not_found")

    # formant追跡の確度が低い場合にも境界を捏造しない。初期版では音源安定後30 msを
    # stable-vowel候補とし、後段のformant軌道で信頼度を監査する。
    vowel_index = min(block.shape[0] - 1, max(source_index, source_index + int(round(0.03 / (hop / sample_rate)))))
    order_ok = activity_index <= periodic_index <= pitch_index <= source_index <= vowel_index <= end_index
    if not order_ok:
        reasons.append("boundary_order_adjusted")
        ordered = np.maximum.accumulate([activity_index, periodic_index, pitch_index, source_index, vowel_index])
        activity_index, periodic_index, pitch_index, source_index, vowel_index = map(int, ordered)
        end_index = max(end_index, vowel_index)
    confidence = max(0.0, 1.0 - 0.18 * len(reasons))
    result = BoundaryResult(
        float(time[activity_index]), float(time[periodic_index]), float(time[pitch_index]),
        float(time[source_index]), float(time[vowel_index]), float(min(time[-1], time[end_index])),
        confidence, tuple(reasons),
    )
    series = {
        "time_sec": time.astype(float).tolist(),
        "rms_db": rms_db.astype(float).tolist(),
        "f0_hz": [finite_or_none(value) for value in f0],
        "periodicity": strength.astype(float).tolist(),
    }
    return result, series

