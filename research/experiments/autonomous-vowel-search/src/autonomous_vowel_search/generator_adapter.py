from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import numpy as np
from scipy.io import wavfile

from synthetic_vowel_baseline.synthesis import render_corrected_variation_candidates

from . import GENERATOR_ADAPTER_VERSION
from .io import read_json, sha256_file
from .paths import BASELINE_ROOT


def base_contract() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    return (
        read_json(BASELINE_ROOT / "config/experiment.json"),
        read_json(BASELINE_ROOT / "config/voice-quality-experiment.json"),
        read_json(BASELINE_ROOT / "config/voice-quality-correction.json"),
    )


def render_b9(parameters: dict[str, float], seed_offset: int, f0_hz: float | None = None) -> dict[str, Any]:
    spec, quality, correction = (deepcopy(item) for item in base_contract())
    if f0_hz is not None:
        spec["f0_hz"] = float(f0_hz)
    quality["spectral_tilt"]["cutoff_hz"] = float(parameters["spectral_tilt_lowpass_hz"])
    correction["control_lowpass_hz"] = float(parameters["variation_lowpass_hz"])
    correction["amplitude_std_db"] = float(parameters["amplitude_std_db"])
    correlation = float(parameters["f0_amplitude_correlation"])
    if not -1.0 <= correlation <= 1.0:
        raise ValueError("F0・振幅相関は[-1,1]である必要があります")
    correction["pitch_amplitude_correlation"] = correlation
    correction["seed_offset"] = int(seed_offset)
    correction["conditions"] = [{
        "condition": "adapter-b9",
        "f0_std_fraction": float(parameters["f0_std_fraction"]),
        "meaning": "autonomous-vowel-search adapter render",
    }]
    candidate = render_corrected_variation_candidates(spec, quality, correction)[0]
    candidate["adapter_version"] = GENERATOR_ADAPTER_VERSION
    candidate["parameters"] = {key: float(value) for key, value in parameters.items()}
    candidate["seed_offset"] = int(seed_offset)
    candidate["sample_rate"] = int(spec["sample_rate"])
    candidate["f0_hz"] = float(spec["f0_hz"])
    return candidate


def write_render(path: Path, candidate: dict[str, Any]) -> str:
    if path.exists():
        raise FileExistsError(f"既存音声は上書きしません: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    audio = np.asarray(candidate["audio"], dtype=np.float64)
    wavfile.write(path, int(candidate["sample_rate"]), np.clip(audio, -1.0, 1.0).astype(np.float32))
    return sha256_file(path)
