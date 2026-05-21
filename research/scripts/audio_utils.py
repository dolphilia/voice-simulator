from __future__ import annotations

import math
import warnings
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.io import wavfile
from scipy.io.wavfile import WavFileWarning
from scipy.linalg import solve_toeplitz
from scipy.signal import (
    correlate,
    correlation_lags,
    find_peaks,
    lfilter,
    resample_poly,
)


FORMANT_RANGES = {
    "a": [(450.0, 1100.0), (800.0, 1800.0), (1800.0, 3600.0)],
    "i": [(180.0, 550.0), (1600.0, 3200.0), (2200.0, 4200.0)],
    "u": [(180.0, 650.0), (500.0, 1600.0), (1500.0, 3600.0)],
    "e": [(300.0, 850.0), (1300.0, 2800.0), (2000.0, 3900.0)],
    "o": [(300.0, 850.0), (500.0, 1500.0), (1700.0, 3600.0)],
}


@dataclass(frozen=True)
class AlignmentResult:
    reference: np.ndarray
    generated: np.ndarray
    lag_samples: int

    @property
    def sample_count(self) -> int:
        return int(min(self.reference.size, self.generated.size))


def read_mono_float(path: Path) -> tuple[int, np.ndarray]:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", WavFileWarning)
        fs, audio = wavfile.read(path)

    audio = np.asarray(audio)
    if audio.ndim > 1:
        audio = np.mean(audio, axis=1)

    if np.issubdtype(audio.dtype, np.integer):
        max_value = float(np.iinfo(audio.dtype).max)
        audio_float = audio.astype(np.float64) / max_value
    else:
        audio_float = audio.astype(np.float64)

    return int(fs), audio_float


def remove_dc(audio: np.ndarray) -> np.ndarray:
    if audio.size == 0:
        return audio
    return audio - float(np.mean(audio))


def resample_to(audio: np.ndarray, source_rate: int, target_rate: int) -> np.ndarray:
    if source_rate == target_rate:
        return audio
    if audio.size == 0:
        return audio

    divisor = math.gcd(source_rate, target_rate)
    up = target_rate // divisor
    down = source_rate // divisor
    return resample_poly(audio, up, down).astype(np.float64, copy=False)


def trim_silence(audio: np.ndarray, threshold_ratio: float = 0.03) -> np.ndarray:
    if audio.size == 0:
        return audio

    peak = float(np.max(np.abs(audio)))
    if peak <= 0.0:
        return audio

    threshold = peak * threshold_ratio
    active = np.flatnonzero(np.abs(audio) >= threshold)
    if active.size == 0:
        return audio

    return audio[active[0] : active[-1] + 1]


def stable_middle_segment(audio: np.ndarray, fs: int, duration_sec: float = 0.45) -> np.ndarray:
    trimmed = trim_silence(audio)
    target_len = min(trimmed.size, int(round(duration_sec * fs)))
    if target_len <= 0:
        return trimmed

    center = trimmed.size // 2
    start = max(0, center - target_len // 2)
    end = min(trimmed.size, start + target_len)
    start = max(0, end - target_len)
    return trimmed[start:end]


def leading_segment(audio: np.ndarray, fs: int, duration_sec: float = 0.18) -> np.ndarray:
    trimmed = trim_silence(audio)
    target_len = min(trimmed.size, int(round(duration_sec * fs)))
    return trimmed[:target_len] if target_len > 0 else trimmed


def analysis_segment(audio: np.ndarray, fs: int, mode: str) -> np.ndarray:
    if mode == "noise":
        return leading_segment(audio, fs)
    if mode == "transition":
        return trim_silence(audio)
    return stable_middle_segment(audio, fs)


def rms(audio: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(audio)))) if audio.size else 0.0


def rms_db(audio: np.ndarray) -> float:
    return 20.0 * math.log10(max(rms(audio), 1e-12))


def peak_db(audio: np.ndarray) -> float:
    peak = float(np.max(np.abs(audio))) if audio.size else 0.0
    return 20.0 * math.log10(max(peak, 1e-12))


def normalize_rms(audio: np.ndarray, target_db: float = -20.0) -> np.ndarray:
    current = rms(audio)
    if current <= 0.0:
        return audio

    target = 10.0 ** (target_db / 20.0)
    scaled = audio * (target / current)
    peak = float(np.max(np.abs(scaled))) if scaled.size else 0.0
    if peak > 0.99:
        scaled = scaled * (0.99 / peak)
    return scaled


def zero_crossing_rate(audio: np.ndarray) -> float:
    if audio.size < 2:
        return float("nan")
    signs = np.signbit(audio)
    return float(np.count_nonzero(signs[1:] != signs[:-1]) / (audio.size - 1))


def align_by_correlation(reference: np.ndarray, generated: np.ndarray) -> AlignmentResult:
    if reference.size == 0 or generated.size == 0:
        return AlignmentResult(reference=reference, generated=generated, lag_samples=0)

    ref = remove_dc(reference)
    gen = remove_dc(generated)
    corr = correlate(gen, ref, mode="full", method="fft")
    lags = correlation_lags(gen.size, ref.size, mode="full")
    lag = int(lags[int(np.argmax(corr))])

    if lag > 0:
        aligned_generated = generated[lag:]
        aligned_reference = reference[: aligned_generated.size]
    elif lag < 0:
        aligned_reference = reference[-lag:]
        aligned_generated = generated[: aligned_reference.size]
    else:
        size = min(reference.size, generated.size)
        aligned_reference = reference[:size]
        aligned_generated = generated[:size]

    size = min(aligned_reference.size, aligned_generated.size)
    return AlignmentResult(
        reference=aligned_reference[:size],
        generated=aligned_generated[:size],
        lag_samples=lag,
    )


def spectrum(audio: np.ndarray, fs: int, fft_size: int = 32768) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    if audio.size < 16:
        empty = np.array([], dtype=np.float64)
        return empty, empty, empty

    size = min(fft_size, audio.size)
    segment = audio[:size] * np.hanning(size)
    spec = np.fft.rfft(segment)
    freqs = np.fft.rfftfreq(size, 1.0 / fs)
    magnitude = np.abs(spec)
    power = np.square(magnitude)
    return freqs, magnitude, power


def band_power_ratio(freqs: np.ndarray, power: np.ndarray, low: float, high: float, total_high: float = 8000.0) -> float:
    total_mask = (freqs >= 80.0) & (freqs <= total_high)
    band_mask = (freqs >= low) & (freqs < high)
    total = float(np.sum(power[total_mask]))
    band = float(np.sum(power[band_mask]))
    return band / total if total > 0.0 else float("nan")


def spectral_centroid(freqs: np.ndarray, power: np.ndarray, low: float = 80.0, high: float = 8000.0) -> float:
    mask = (freqs >= low) & (freqs <= high)
    total = float(np.sum(power[mask]))
    return float(np.sum(freqs[mask] * power[mask]) / total) if total > 0.0 else float("nan")


def spectral_rolloff(freqs: np.ndarray, power: np.ndarray, ratio: float = 0.95, low: float = 80.0, high: float = 8000.0) -> float:
    mask = (freqs >= low) & (freqs <= high)
    masked_freqs = freqs[mask]
    masked_power = power[mask]
    total = float(np.sum(masked_power))
    if total <= 0.0 or masked_freqs.size == 0:
        return float("nan")

    cumulative = np.cumsum(masked_power)
    index = int(np.searchsorted(cumulative, total * ratio))
    index = min(index, masked_freqs.size - 1)
    return float(masked_freqs[index])


def spectral_slope_db_per_khz(freqs: np.ndarray, power: np.ndarray, low: float = 500.0, high: float = 5000.0) -> float:
    mask = (freqs >= low) & (freqs <= high) & (power > 0.0)
    if int(np.sum(mask)) < 8:
        return float("nan")

    x = freqs[mask] / 1000.0
    y = 10.0 * np.log10(np.maximum(power[mask], 1e-24))
    slope, _ = np.polyfit(x, y, 1)
    return float(slope)


def peak_frequency(freqs: np.ndarray, power: np.ndarray, low: float = 500.0, high: float = 12000.0) -> float:
    mask = (freqs >= low) & (freqs <= high)
    if not np.any(mask):
        return float("nan")

    masked_freqs = freqs[mask]
    masked_power = power[mask]
    return float(masked_freqs[int(np.argmax(masked_power))])


def spectral_flatness(freqs: np.ndarray, power: np.ndarray, low: float = 500.0, high: float = 12000.0) -> float:
    mask = (freqs >= low) & (freqs <= high) & (power > 0.0)
    if not np.any(mask):
        return float("nan")

    values = power[mask]
    geometric = math.exp(float(np.mean(np.log(np.maximum(values, 1e-24)))))
    arithmetic = float(np.mean(values))
    return geometric / arithmetic if arithmetic > 0.0 else float("nan")


def log_spectral_distance_db(reference_power: np.ndarray, generated_power: np.ndarray) -> float:
    size = min(reference_power.size, generated_power.size)
    if size == 0:
        return float("nan")

    ref_db = 10.0 * np.log10(np.maximum(reference_power[:size], 1e-24))
    gen_db = 10.0 * np.log10(np.maximum(generated_power[:size], 1e-24))
    return float(np.sqrt(np.mean(np.square(ref_db - gen_db))))


def spectral_convergence(reference_magnitude: np.ndarray, generated_magnitude: np.ndarray) -> float:
    size = min(reference_magnitude.size, generated_magnitude.size)
    if size == 0:
        return float("nan")

    ref = reference_magnitude[:size]
    gen = generated_magnitude[:size]
    denom = float(np.linalg.norm(ref))
    return float(np.linalg.norm(ref - gen) / denom) if denom > 0.0 else float("nan")


def frame_log_spectra(
    audio: np.ndarray,
    fs: int,
    frame_size: int = 1024,
    hop_size: int = 256,
    high: float = 8000.0,
) -> np.ndarray:
    if audio.size < frame_size or frame_size <= 0 or hop_size <= 0:
        return np.empty((0, 0), dtype=np.float64)

    window = np.hanning(frame_size)
    freqs = np.fft.rfftfreq(frame_size, 1.0 / fs)
    mask = freqs <= high
    frames: list[np.ndarray] = []

    for start in range(0, audio.size - frame_size + 1, hop_size):
        frame = audio[start : start + frame_size] * window
        power = np.square(np.abs(np.fft.rfft(frame)))
        frames.append(10.0 * np.log10(np.maximum(power[mask], 1e-24)))

    return np.vstack(frames) if frames else np.empty((0, 0), dtype=np.float64)


def mean_frame_log_spectral_distance(reference: np.ndarray, generated: np.ndarray) -> float:
    frame_count = min(reference.shape[0], generated.shape[0])
    bin_count = min(reference.shape[1], generated.shape[1]) if frame_count else 0
    if frame_count == 0 or bin_count == 0:
        return float("nan")

    diff = reference[:frame_count, :bin_count] - generated[:frame_count, :bin_count]
    per_frame = np.sqrt(np.mean(np.square(diff), axis=1))
    return float(np.mean(per_frame))


def dtw_distance(reference: np.ndarray, generated: np.ndarray) -> float:
    if reference.size == 0 or generated.size == 0:
        return float("nan")

    frame_count_ref = reference.shape[0]
    frame_count_gen = generated.shape[0]
    bin_count = min(reference.shape[1], generated.shape[1])
    if frame_count_ref == 0 or frame_count_gen == 0 or bin_count == 0:
        return float("nan")

    ref = reference[:, :bin_count]
    gen = generated[:, :bin_count]
    previous = np.full(frame_count_gen + 1, np.inf, dtype=np.float64)
    current = np.full(frame_count_gen + 1, np.inf, dtype=np.float64)
    previous[0] = 0.0

    for ref_index in range(1, frame_count_ref + 1):
        current[0] = np.inf
        ref_frame = ref[ref_index - 1]
        for gen_index in range(1, frame_count_gen + 1):
            cost = float(np.sqrt(np.mean(np.square(ref_frame - gen[gen_index - 1]))))
            current[gen_index] = cost + min(
                previous[gen_index],
                current[gen_index - 1],
                previous[gen_index - 1],
            )
        previous, current = current, previous

    path_scale = max(frame_count_ref, frame_count_gen)
    return float(previous[frame_count_gen] / path_scale) if path_scale > 0 else float("nan")


def rms_envelope(audio: np.ndarray, fs: int, frame_size: int = 1024, hop_size: int = 256) -> tuple[np.ndarray, np.ndarray]:
    if audio.size < frame_size or frame_size <= 0 or hop_size <= 0:
        return np.array([], dtype=np.float64), np.array([], dtype=np.float64)

    values: list[float] = []
    times: list[float] = []
    for start in range(0, audio.size - frame_size + 1, hop_size):
        frame = audio[start : start + frame_size]
        values.append(rms(frame))
        times.append((start + frame_size * 0.5) / fs)

    return np.asarray(times, dtype=np.float64), np.asarray(values, dtype=np.float64)


def rms_rise_times(audio: np.ndarray, fs: int) -> tuple[float, float, float]:
    times, values = rms_envelope(audio, fs)
    if times.size == 0 or values.size == 0:
        return float("nan"), float("nan"), float("nan")

    peak = float(np.max(values))
    if peak <= 0.0:
        return float("nan"), float("nan"), float("nan")

    onset_threshold = peak * 0.1
    stable_threshold = peak * 0.9
    onset_indices = np.flatnonzero(values >= onset_threshold)
    stable_indices = np.flatnonzero(values >= stable_threshold)
    if onset_indices.size == 0:
        return float("nan"), float("nan"), float("nan")

    onset_time = float(times[int(onset_indices[0])])
    stable_after_onset = stable_indices[stable_indices >= onset_indices[0]]
    if stable_after_onset.size == 0:
        return onset_time, float("nan"), float("nan")

    stable_time = float(times[int(stable_after_onset[0])])
    return onset_time, stable_time, stable_time - onset_time


def normalized_cross_correlation(reference: np.ndarray, generated: np.ndarray) -> float:
    size = min(reference.size, generated.size)
    if size == 0:
        return float("nan")

    ref = remove_dc(reference[:size])
    gen = remove_dc(generated[:size])
    denom = float(np.linalg.norm(ref) * np.linalg.norm(gen))
    return float(np.dot(ref, gen) / denom) if denom > 0.0 else float("nan")


def waveform_rmse(reference: np.ndarray, generated: np.ndarray) -> float:
    size = min(reference.size, generated.size)
    if size == 0:
        return float("nan")
    return float(np.sqrt(np.mean(np.square(reference[:size] - generated[:size]))))


def snr_db(reference: np.ndarray, generated: np.ndarray) -> float:
    size = min(reference.size, generated.size)
    if size == 0:
        return float("nan")

    ref = reference[:size]
    diff = ref - generated[:size]
    signal_energy = float(np.sum(np.square(ref)))
    noise_energy = float(np.sum(np.square(diff)))
    return 10.0 * math.log10(signal_energy / max(noise_energy, 1e-24)) if signal_energy > 0.0 else float("nan")


def estimate_f0_autocorr(audio: np.ndarray, fs: int) -> float:
    if audio.size < fs // 30:
        return float("nan")

    x = remove_dc(audio)
    x = lfilter([1.0, -0.97], [1.0], x)
    x = x * np.hanning(x.size)
    corr = np.correlate(x, x, mode="full")[x.size - 1 :]
    if corr.size == 0 or corr[0] <= 0.0:
        return float("nan")

    min_lag = max(1, int(fs / 500.0))
    max_lag = min(corr.size - 1, int(fs / 70.0))
    if max_lag <= min_lag:
        return float("nan")

    search = corr[min_lag : max_lag + 1]
    peaks, _ = find_peaks(search)
    if peaks.size == 0:
        lag = int(np.argmax(search)) + min_lag
    else:
        lag = int(peaks[np.argmax(search[peaks])]) + min_lag

    return fs / lag if lag > 0 else float("nan")


def f0_delta_cents(reference_f0: float, generated_f0: float) -> float:
    if not (math.isfinite(reference_f0) and math.isfinite(generated_f0)):
        return float("nan")
    if reference_f0 <= 0.0 or generated_f0 <= 0.0:
        return float("nan")
    return float(1200.0 * math.log2(generated_f0 / reference_f0))


def lpc_coefficients(audio: np.ndarray, order: int) -> np.ndarray:
    x = remove_dc(audio)
    x = lfilter([1.0, -0.97], [1.0], x)
    x = x * np.hamming(x.size)
    autocorr = np.correlate(x, x, mode="full")[x.size - 1 : x.size + order]

    if autocorr[0] <= 0.0:
        raise ValueError("zero autocorrelation")

    autocorr[0] *= 1.0001
    solution = solve_toeplitz((autocorr[:order], autocorr[:order]), -autocorr[1 : order + 1])
    return np.concatenate(([1.0], solution))


def estimate_formants(audio: np.ndarray, fs: int, vowel: str) -> tuple[list[float], list[float], float, str]:
    if vowel not in FORMANT_RANGES:
        return [float("nan")] * 3, [float("nan")] * 3, 0.0, "unsupported_vowel"
    if audio.size < 128:
        return [float("nan")] * 3, [float("nan")] * 3, 0.0, "too_short"

    order = max(10, int(fs / 1000) + 2)
    try:
        coefficients = lpc_coefficients(audio, order)
    except (ValueError, np.linalg.LinAlgError) as exc:
        return [float("nan")] * 3, [float("nan")] * 3, 0.0, f"lpc_failed:{exc}"

    roots = np.roots(coefficients)
    roots = roots[np.imag(roots) >= 0.0]

    candidates: list[tuple[float, float]] = []
    for root in roots:
        frequency = math.atan2(float(np.imag(root)), float(np.real(root))) * fs / (2.0 * math.pi)
        if not 90.0 <= frequency <= 5000.0:
            continue

        radius = abs(root)
        if radius <= 0.0 or radius >= 1.0:
            continue

        bandwidth = -0.5 * fs * math.log(radius) / math.pi
        if 20.0 <= bandwidth <= 900.0:
            candidates.append((frequency, bandwidth))

    candidates.sort(key=lambda item: item[0])

    selected: list[tuple[float, float]] = []
    notes: list[str] = []
    used_indices: set[int] = set()
    for formant_range in FORMANT_RANGES[vowel]:
        in_range = [
            (index, item)
            for index, item in enumerate(candidates)
            if index not in used_indices and formant_range[0] <= item[0] <= formant_range[1]
        ]
        if in_range:
            index, item = min(in_range, key=lambda indexed_item: indexed_item[1][1])
            used_indices.add(index)
            selected.append(item)
        else:
            selected.append((float("nan"), float("nan")))
            notes.append(f"missing_{len(selected)}")

    valid_count = sum(1 for frequency, _ in selected if np.isfinite(frequency))
    confidence = valid_count / 3.0
    return [frequency for frequency, _ in selected], [bandwidth for _, bandwidth in selected], confidence, ";".join(notes)


def formant_mae(reference: list[float], generated: list[float]) -> float:
    pairs = [
        (ref, gen)
        for ref, gen in zip(reference, generated, strict=False)
        if math.isfinite(ref) and math.isfinite(gen)
    ]
    if not pairs:
        return float("nan")
    return float(np.mean([abs(ref - gen) for ref, gen in pairs]))


def format_float(value: float, digits: int = 6) -> str:
    return f"{value:.{digits}f}" if math.isfinite(value) else ""
