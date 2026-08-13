from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
from scipy import signal
from scipy.io import wavfile


def read_audio(path: Path, target_rate: int | None = None) -> tuple[int, np.ndarray]:
    sample_rate, raw = wavfile.read(path)
    audio = np.asarray(raw)
    if np.issubdtype(audio.dtype, np.integer):
        info = np.iinfo(audio.dtype)
        audio = audio.astype(np.float64) / float(max(abs(info.min), abs(info.max)))
    else:
        audio = audio.astype(np.float64)
    if audio.ndim == 2:
        audio = np.mean(audio, axis=1)
    if audio.ndim != 1:
        raise ValueError(f"unsupported audio shape: {audio.shape}")
    if target_rate and sample_rate != target_rate:
        divisor = math.gcd(int(sample_rate), int(target_rate))
        audio = signal.resample_poly(audio, target_rate // divisor, int(sample_rate) // divisor)
        sample_rate = target_rate
    return int(sample_rate), np.asarray(audio, dtype=np.float64)


def write_audio(path: Path, sample_rate: int, audio: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    safe = np.nan_to_num(np.asarray(audio, dtype=np.float64))
    wavfile.write(path, sample_rate, np.clip(safe, -1.0, 1.0).astype(np.float32))


def rms(audio: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(audio)))) if audio.size else 0.0


def normalize(audio: np.ndarray, target_dbfs: float = -20.0, peak_limit_dbfs: float = -1.0) -> np.ndarray:
    current = rms(audio)
    if current <= 1e-12:
        return audio.copy()
    output = audio * ((10.0 ** (target_dbfs / 20.0)) / current)
    peak = float(np.max(np.abs(output))) if output.size else 0.0
    limit = 10.0 ** (peak_limit_dbfs / 20.0)
    if peak > limit:
        output *= limit / peak
    return output


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_json_safe(payload), ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def finite_or_none(value: float | np.floating[Any] | None) -> float | None:
    if value is None:
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def integrity(audio: np.ndarray, sample_rate: int) -> dict[str, float]:
    if audio.size == 0:
        return {"duration_sec": 0.0, "clipping_ratio": 1.0, "peak_dbfs": -240.0, "rms_dbfs": -240.0, "dc_offset": 0.0}
    peak = float(np.max(np.abs(audio)))
    level = rms(audio)
    return {
        "duration_sec": float(audio.size / sample_rate),
        "clipping_ratio": float(np.mean(np.abs(audio) >= 0.999)),
        "peak_dbfs": 20.0 * math.log10(max(peak, 1e-12)),
        "rms_dbfs": 20.0 * math.log10(max(level, 1e-12)),
        "dc_offset": float(np.mean(audio)),
    }
