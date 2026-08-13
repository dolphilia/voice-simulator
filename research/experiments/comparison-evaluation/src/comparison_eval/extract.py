from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np

from . import METRIC_PROFILE_VERSION, SCHEMA_VERSION
from .features import estimate_formants, f0_contour, harmonic_metrics, spectral_summary, temporal_spectral_series, temporal_spectral_summary
from .io import sha256_file
from .models import Estimate, FeatureBundle
from .signal import level_normalize, read_audio, select_segment, signal_integrity, validate_audio


def extract_file(path: Path, sample_id: str, profile: str, segment_kind: str = "stable", metadata: dict[str, Any] | None = None) -> FeatureBundle:
    sample_rate, audio = read_audio(path)
    validation = validate_audio(audio, sample_rate)
    segment = select_segment(audio, sample_rate, segment_kind)
    normalized = level_normalize(segment)
    times, contour, confidence = f0_contour(normalized, sample_rate)
    voiced = contour[np.isfinite(contour)]
    f0 = float(np.median(voiced)) if voiced.size else None
    f0_confidence = float(np.mean(confidence[np.isfinite(contour)])) if voiced.size else 0.0
    formants, bandwidths, formant_confidence, formant_reason = estimate_formants(normalized, sample_rate)
    temporal = temporal_spectral_series(normalized, sample_rate)
    scalar: dict[str, float | None] = signal_integrity(audio, sample_rate)
    scalar.update(spectral_summary(normalized, sample_rate))
    scalar.update(temporal_spectral_summary(normalized, sample_rate))
    scalar.update(harmonic_metrics(normalized, sample_rate, f0))
    scalar.update({
        "duration_sec": audio.size / sample_rate,
        "active_duration_sec": segment.size / sample_rate,
        "voiced_ratio": voiced.size / max(1, contour.size),
    })
    for index, (frequency, bandwidth) in enumerate(zip(formants, bandwidths, strict=True), 1):
        scalar[f"f{index}_hz"] = frequency if math.isfinite(frequency) else None
        scalar[f"b{index}_hz"] = bandwidth if math.isfinite(bandwidth) else None
    return FeatureBundle(
        sample_id=sample_id,
        path=str(path),
        sha256=sha256_file(path),
        sample_rate=sample_rate,
        profile=profile,
        scalar=scalar,
        estimates={
            "f0_hz": Estimate(f0, f0_confidence, "" if f0 is not None else "unvoiced_or_unreliable"),
            "formants": Estimate(None, formant_confidence, formant_reason),
        },
        frame_series={
            "time_sec": [float(value) for value in times],
            "f0_hz": [float(value) if math.isfinite(value) else None for value in contour],
            "f0_confidence": [float(value) for value in confidence],
            "spectral_time_sec": temporal["time_sec"],
            "spectral_centroid_hz": temporal["centroid_hz"],
            "spectral_flatness": temporal["flatness"],
            "rms_envelope_db": temporal["rms_db"],
        },
        metadata={**(metadata or {}), "validation": validation.to_dict(), "segment": segment_kind, "frame_count": int(times.size), "schema_version": SCHEMA_VERSION, "metric_profile_version": METRIC_PROFILE_VERSION},
    )
