from __future__ import annotations

import numpy as np
from scipy import signal

from .audio import integrity, normalize


def _smooth_noise(count: int, sample_rate: int, cutoff_hz: float, rng: np.random.Generator) -> np.ndarray:
    noise = rng.standard_normal(count)
    sos = signal.butter(2, cutoff_hz, btype="lowpass", fs=sample_rate, output="sos")
    filtered = signal.sosfiltfilt(sos, noise)
    standard = float(np.std(filtered))
    return filtered / standard if standard > 1e-12 else np.zeros(count)


def _formant_weight(frequency: np.ndarray, formants: np.ndarray, bandwidths: np.ndarray) -> np.ndarray:
    weight = np.full(frequency.shape, 1e-4, dtype=float)
    for formant, bandwidth in zip(formants, bandwidths, strict=True):
        weight += np.exp(-0.5 * ((frequency - formant) / max(20.0, bandwidth * 0.5)) ** 2)
    return weight


def render_onset_variant(
    condition: str,
    sample_rate: int,
    duration_sec: float,
    f0_hz: float,
    formants_hz: tuple[float, float, float],
    bandwidths_hz: tuple[float, float, float] = (90.0, 120.0, 180.0),
    onset_sec: float = 0.16,
    seed: int = 20260813,
) -> np.ndarray:
    count = int(round(sample_rate * duration_sec))
    time = np.arange(count) / sample_rate
    progress = np.clip(time / max(onset_sec, 1e-4), 0.0, 1.0)
    smooth = progress * progress * (3.0 - 2.0 * progress)
    rng = np.random.default_rng(seed)
    drift = _smooth_noise(count, sample_rate, 7.0, rng)
    independent = [_smooth_noise(count, sample_rate, 7.0, np.random.default_rng(seed + index + 1)) for index in range(4)]
    coupled = condition in {"C6-no-formant", "C6-coupled"}

    use_f0 = condition in {"C2-f0", "C3-periodicity", "C4-source-quality", "C5-formant", "C6-no-formant", "C6-coupled", "C7-independent"}
    use_periodicity = condition in {"C3-periodicity", "C4-source-quality", "C5-formant", "C6-no-formant", "C6-coupled", "C7-independent"}
    use_source_quality = condition in {"C4-source-quality", "C5-formant", "C6-no-formant", "C6-coupled", "C7-independent"}
    use_formant = condition in {"C5-formant", "C6-coupled", "C7-independent"}

    f0 = np.full(count, f0_hz)
    if use_f0:
        f0 *= 0.96 + 0.04 * smooth
    if coupled:
        f0 *= 2.0 ** ((5.0 * drift) / 1200.0)
    elif condition == "C7-independent":
        f0 *= 2.0 ** ((5.0 * independent[0]) / 1200.0)
    phase = np.cumsum(2.0 * np.pi * f0 / sample_rate)

    amplitude = smooth.copy()
    if coupled:
        amplitude *= 1.0 + 0.006 * drift
    elif condition == "C7-independent":
        amplitude *= 1.0 + 0.006 * independent[1]

    final_formants = np.asarray(formants_hz, dtype=float)
    initial_formants = final_formants * np.asarray((0.92, 0.86, 0.94))
    formant_paths = initial_formants[:, None] + (final_formants - initial_formants)[:, None] * smooth[None, :] if use_formant else np.repeat(final_formants[:, None], count, axis=1)

    source = np.zeros(count)
    maximum_harmonic = min(80, int((sample_rate * 0.45) / max(f0_hz, 1.0)))
    bandwidths = np.asarray(bandwidths_hz)
    for harmonic in range(1, maximum_harmonic + 1):
        harmonic_frequency = harmonic * f0
        weights = np.full(count, 1e-4)
        for formant_path, bandwidth in zip(formant_paths, bandwidths, strict=True):
            weights += np.exp(-0.5 * ((harmonic_frequency - formant_path) / max(20.0, bandwidth * 0.5)) ** 2)
        tilt = 1.0 / harmonic
        if use_source_quality:
            tilt *= 0.65 + 0.35 * smooth
        source += tilt * weights * np.sin(harmonic * phase)

    if use_periodicity:
        irregular = (1.0 - smooth) * 0.015
        if coupled:
            irregular *= 1.0 + 0.1 * drift
        elif condition == "C7-independent":
            irregular *= 1.0 + 0.1 * independent[2]
        source += irregular * rng.standard_normal(count)
    if use_source_quality:
        breath_envelope = 0.12 * (1.0 - 0.82 * smooth)
        breath = signal.sosfilt(signal.butter(2, 1200.0, btype="highpass", fs=sample_rate, output="sos"), rng.standard_normal(count))
        if condition == "C7-independent":
            breath_envelope *= 1.0 + 0.08 * independent[3]
        source += breath_envelope * breath
    return normalize(amplitude * source, -20.0)


def render_suite(sample_rate: int, duration_sec: float, f0_hz: float, formants_hz: tuple[float, float, float], seed: int, onset_sec: float = 0.16) -> list[dict[str, object]]:
    conditions = (
        "C1-gain", "C2-f0", "C3-periodicity", "C4-source-quality",
        "C5-formant", "C6-no-formant", "C6-coupled", "C7-independent",
    )
    return [
        {
            "condition": condition,
            "audio": audio,
            "integrity": integrity(audio, sample_rate),
            "contains_human_audio": False,
            "parameters": {"sample_rate": sample_rate, "duration_sec": duration_sec, "f0_hz": f0_hz, "formants_hz": list(formants_hz), "onset_sec": onset_sec, "seed": seed},
        }
        for condition in conditions
        for audio in [render_onset_variant(condition, sample_rate, duration_sec, f0_hz, formants_hz, onset_sec=onset_sec, seed=seed)]
    ]
