from __future__ import annotations

import math

import numpy as np
from scipy import signal

from .features import (
    aligned_feature_distance,
    dtw_feature_distance,
    estimate_formants,
    envelope_timing,
    f0_contour,
    f0_contour_metrics,
    hz_to_bark,
    harmonic_metrics,
    log_mel_spectrogram,
    mfcc,
    multi_resolution_spectral_distance,
    spectral_summary,
)
from .models import MetricResult
from .signal import active_bounds, level_normalize, remove_dc, rms, select_segment


def _metric(name: str, value: float, unit: str, category: str, direction: str = "lower") -> MetricResult:
    available = math.isfinite(value)
    return MetricResult(name, value if available else None, unit, category, direction, available=available, confidence=1.0 if available else 0.0, reason="" if available else "not_estimable")


def _delta_metric(name: str, signed_value: float, unit: str, category: str) -> MetricResult:
    result = _metric(name, abs(signed_value), unit, category)
    return MetricResult(**{**result.to_dict(), "signed_value": signed_value if math.isfinite(signed_value) else None})


def _align(reference: np.ndarray, generated: np.ndarray) -> tuple[np.ndarray, np.ndarray, int]:
    if reference.size == 0 or generated.size == 0:
        return reference, generated, 0
    correlation = signal.correlate(remove_dc(generated), remove_dc(reference), mode="full", method="fft")
    lags = signal.correlation_lags(generated.size, reference.size, mode="full")
    lag = int(lags[int(np.argmax(np.abs(correlation)))])
    if lag > 0:
        generated = generated[lag:]
    elif lag < 0:
        reference = reference[-lag:]
    size = min(reference.size, generated.size)
    return reference[:size], generated[:size], lag


def compare_audio(reference: np.ndarray, generated: np.ndarray, sample_rate: int, segment_kind: str = "stable") -> list[MetricResult]:
    ref_start, _ = active_bounds(reference)
    gen_start, _ = active_bounds(generated)
    ref_raw = select_segment(reference, sample_rate, segment_kind)
    gen_raw = select_segment(generated, sample_rate, segment_kind)
    ref, gen, lag = _align(level_normalize(ref_raw), level_normalize(gen_raw))
    metrics: list[MetricResult] = [
        _delta_metric("duration_delta_ms", (gen_raw.size - ref_raw.size) * 1000.0 / sample_rate, "ms", "timing_transition"),
        _delta_metric("alignment_lag_ms", lag * 1000.0 / sample_rate, "ms", "timing_transition"),
        _delta_metric("onset_delta_ms", (gen_start - ref_start) * 1000.0 / sample_rate, "ms", "timing_transition"),
        _delta_metric("level_delta_db", 20.0 * math.log10(max(rms(gen_raw), 1e-12) / max(rms(ref_raw), 1e-12)), "dB", "signal_integrity"),
    ]
    if ref.size and gen.size:
        metrics.append(_metric("waveform_rmse", float(np.sqrt(np.mean((ref - gen) ** 2))), "amplitude", "waveform_phase"))
        denominator = float(np.linalg.norm(remove_dc(ref)) * np.linalg.norm(remove_dc(gen)))
        correlation = float(np.dot(remove_dc(ref), remove_dc(gen)) / denominator) if denominator else float("nan")
        metrics.append(_metric("waveform_correlation", correlation, "ratio", "waveform_phase", "higher"))
    ref_mel = log_mel_spectrogram(ref, sample_rate)
    gen_mel = log_mel_spectrogram(gen, sample_rate)
    metrics.append(_metric("log_mel_rmse_db", aligned_feature_distance(ref_mel, gen_mel), "dB", "spectral_timbre"))
    dtw_mel, warp = dtw_feature_distance(ref_mel, gen_mel)
    metrics.extend([_metric("log_mel_dtw_db", dtw_mel, "dB", "spectral_timbre"), _metric("dtw_warp_ratio_delta", abs(warp - 1.0), "ratio", "timing_transition")])
    metrics.append(_metric("mfcc_rmse", aligned_feature_distance(mfcc(ref_mel), mfcc(gen_mel)), "coefficient", "spectral_timbre"))
    metrics.extend(_metric(name, value, "dB", "spectral_timbre") for name, value in multi_resolution_spectral_distance(ref, gen, sample_rate).items())
    _, ref_f0, _ = f0_contour(ref, sample_rate)
    _, gen_f0, _ = f0_contour(gen, sample_rate)
    for name, value in f0_contour_metrics(ref_f0, gen_f0).items():
        direction = "higher" if name in {"f0_contour_correlation", "voicing_f1"} else "lower"
        metrics.append(_metric(name, value, "ratio" if direction == "higher" else "cent", "pitch_voicing", direction))
    ref_voiced, gen_voiced = ref_f0[np.isfinite(ref_f0)], gen_f0[np.isfinite(gen_f0)]
    f0_signed = 1200.0 * math.log2(float(np.median(gen_voiced)) / float(np.median(ref_voiced))) if ref_voiced.size and gen_voiced.size else float("nan")
    metrics.append(_delta_metric("f0_median_delta_cents", f0_signed, "cent", "pitch_voicing"))
    ref_f0_median = float(np.median(ref_voiced)) if ref_voiced.size else None
    gen_f0_median = float(np.median(gen_voiced)) if gen_voiced.size else None
    ref_harmonic = harmonic_metrics(ref, sample_rate, ref_f0_median)
    gen_harmonic = harmonic_metrics(gen, sample_rate, gen_f0_median)
    for name in ref_harmonic:
        metrics.append(_delta_metric(f"{name}_delta", gen_harmonic[name] - ref_harmonic[name], "dB", "source_voice_quality"))
    ref_formants, ref_bandwidths, ref_confidence, _ = estimate_formants(ref, sample_rate)
    gen_formants, gen_bandwidths, gen_confidence, _ = estimate_formants(gen, sample_rate)
    for index, (ref_value, gen_value) in enumerate(zip(ref_formants, gen_formants, strict=True), 1):
        result = _delta_metric(f"f{index}_delta_hz", gen_value - ref_value, "Hz", "resonance")
        metrics.append(MetricResult(**{**result.to_dict(), "confidence": min(ref_confidence, gen_confidence)}))
        bark = _delta_metric(f"f{index}_delta_bark", hz_to_bark(gen_value) - hz_to_bark(ref_value), "Bark", "resonance")
        metrics.append(MetricResult(**{**bark.to_dict(), "confidence": min(ref_confidence, gen_confidence)}))
    for index, (ref_value, gen_value) in enumerate(zip(ref_bandwidths, gen_bandwidths, strict=True), 1):
        result = _delta_metric(f"b{index}_delta_hz", gen_value - ref_value, "Hz", "resonance")
        metrics.append(MetricResult(**{**result.to_dict(), "confidence": min(ref_confidence, gen_confidence)}))
    ref_spectral = spectral_summary(ref, sample_rate)
    gen_spectral = spectral_summary(gen, sample_rate)
    for name in ref_spectral:
        unit = "Hz" if name.endswith("_hz") else "ratio" if name in {"spectral_flatness", "zero_crossing_rate"} else "dB/kHz"
        category = "noise_frication" if name in {"spectral_flatness", "zero_crossing_rate"} else "spectral_timbre"
        metrics.append(_delta_metric(f"{name}_delta", gen_spectral[name] - ref_spectral[name], unit, category))
    ref_timing, gen_timing = envelope_timing(ref_raw, sample_rate), envelope_timing(gen_raw, sample_rate)
    for name in ("stable_sec", "rise_sec"):
        metrics.append(_delta_metric(f"{name.removesuffix('_sec')}_delta_ms", (gen_timing[name] - ref_timing[name]) * 1000.0, "ms", "timing_transition"))
    return metrics
