from __future__ import annotations

import math

import numpy as np
from scipy import fft, signal
from scipy.linalg import solve_toeplitz

from .models import Estimate
from .signal import remove_dc, rms


def hz_to_mel(hz: np.ndarray | float) -> np.ndarray | float:
    return 2595.0 * np.log10(1.0 + np.asarray(hz) / 700.0)


def mel_to_hz(mel: np.ndarray | float) -> np.ndarray | float:
    return 700.0 * (np.power(10.0, np.asarray(mel) / 2595.0) - 1.0)


def hz_to_bark(hz: float) -> float:
    return float(13.0 * math.atan(0.00076 * hz) + 3.5 * math.atan((hz / 7500.0) ** 2))


def frame_audio(audio: np.ndarray, frame_size: int, hop_size: int) -> np.ndarray:
    if frame_size <= 0 or hop_size <= 0 or audio.size < frame_size:
        return np.empty((0, max(frame_size, 0)), dtype=np.float64)
    starts = range(0, audio.size - frame_size + 1, hop_size)
    return np.vstack([audio[start : start + frame_size] for start in starts])


def stft_log_power(audio: np.ndarray, sample_rate: int, frame_size: int, hop_size: int) -> tuple[np.ndarray, np.ndarray]:
    frames = frame_audio(audio, frame_size, hop_size)
    freqs = np.fft.rfftfreq(frame_size, 1.0 / sample_rate)
    if frames.size == 0:
        return freqs, np.empty((0, freqs.size), dtype=np.float64)
    window = np.hanning(frame_size)
    power = np.square(np.abs(np.fft.rfft(frames * window, axis=1)))
    return freqs, 10.0 * np.log10(np.maximum(power, 1e-24))


def mel_filterbank(sample_rate: int, fft_size: int, n_mels: int = 40, low_hz: float = 50.0, high_hz: float | None = None) -> np.ndarray:
    high = min(sample_rate / 2.0, high_hz or sample_rate / 2.0)
    mel_points = np.linspace(float(hz_to_mel(low_hz)), float(hz_to_mel(high)), n_mels + 2)
    hz_points = np.asarray(mel_to_hz(mel_points))
    bin_freqs = np.fft.rfftfreq(fft_size, 1.0 / sample_rate)
    bank = np.zeros((n_mels, bin_freqs.size), dtype=np.float64)
    for index in range(n_mels):
        left, center, right = hz_points[index : index + 3]
        left_mask = (bin_freqs >= left) & (bin_freqs <= center)
        right_mask = (bin_freqs >= center) & (bin_freqs <= right)
        if center > left:
            bank[index, left_mask] = (bin_freqs[left_mask] - left) / (center - left)
        if right > center:
            bank[index, right_mask] = (right - bin_freqs[right_mask]) / (right - center)
    norms = np.sum(bank, axis=1, keepdims=True)
    return bank / np.maximum(norms, 1e-12)


def log_mel_spectrogram(
    audio: np.ndarray,
    sample_rate: int,
    frame_size: int = 1024,
    hop_size: int = 256,
    n_mels: int = 40,
    high_hz: float = 12000.0,
) -> np.ndarray:
    frames = frame_audio(audio, frame_size, hop_size)
    if frames.size == 0:
        return np.empty((0, n_mels), dtype=np.float64)
    window = np.hanning(frame_size)
    power = np.square(np.abs(np.fft.rfft(frames * window, axis=1)))
    bank = mel_filterbank(sample_rate, frame_size, n_mels, high_hz=high_hz)
    mel_power = power @ bank.T
    return 10.0 * np.log10(np.maximum(mel_power, 1e-24))


def mfcc(log_mel: np.ndarray, n_coefficients: int = 13) -> np.ndarray:
    if log_mel.size == 0:
        return np.empty((0, n_coefficients), dtype=np.float64)
    return fft.dct(log_mel, type=2, axis=1, norm="ortho")[:, :n_coefficients]


def aligned_feature_distance(reference: np.ndarray, generated: np.ndarray) -> float:
    rows = min(reference.shape[0], generated.shape[0]) if reference.ndim == generated.ndim == 2 else 0
    columns = min(reference.shape[1], generated.shape[1]) if rows else 0
    if rows == 0 or columns == 0:
        return float("nan")
    return float(np.sqrt(np.mean(np.square(reference[:rows, :columns] - generated[:rows, :columns]))))


def dtw_feature_distance(reference: np.ndarray, generated: np.ndarray) -> tuple[float, float]:
    if reference.ndim != 2 or generated.ndim != 2 or reference.size == 0 or generated.size == 0:
        return float("nan"), float("nan")
    columns = min(reference.shape[1], generated.shape[1])
    ref = reference[:, :columns]
    gen = generated[:, :columns]
    previous = np.full(gen.shape[0] + 1, np.inf)
    current = np.full(gen.shape[0] + 1, np.inf)
    steps_prev = np.zeros(gen.shape[0] + 1, dtype=np.int64)
    steps_cur = np.zeros(gen.shape[0] + 1, dtype=np.int64)
    previous[0] = 0.0
    for i, ref_frame in enumerate(ref, 1):
        current[0] = np.inf
        for j, gen_frame in enumerate(gen, 1):
            candidates = (previous[j], current[j - 1], previous[j - 1])
            choice = int(np.argmin(candidates))
            costs = (previous[j], current[j - 1], previous[j - 1])
            step_counts = (steps_prev[j], steps_cur[j - 1], steps_prev[j - 1])
            local = float(np.sqrt(np.mean(np.square(ref_frame - gen_frame))))
            current[j] = local + costs[choice]
            steps_cur[j] = step_counts[choice] + 1
        previous, current = current, previous
        steps_prev, steps_cur = steps_cur, steps_prev
    path_length = max(1, int(steps_prev[-1]))
    distance = float(previous[-1] / path_length)
    diagonal = max(ref.shape[0], gen.shape[0])
    warp_ratio = float(path_length / diagonal) if diagonal else float("nan")
    return distance, warp_ratio


def multi_resolution_spectral_distance(reference: np.ndarray, generated: np.ndarray, sample_rate: int) -> dict[str, float]:
    distances: list[float] = []
    result: dict[str, float] = {}
    for frame_size in (512, 1024, 2048, 4096):
        hop = frame_size // 4
        _, ref = stft_log_power(reference, sample_rate, frame_size, hop)
        _, gen = stft_log_power(generated, sample_rate, frame_size, hop)
        value = aligned_feature_distance(ref, gen)
        result[f"log_stft_rmse_{frame_size}"] = value
        if math.isfinite(value):
            distances.append(value)
    result["multi_resolution_log_stft"] = float(np.mean(distances)) if distances else float("nan")
    return result


def _parabolic_peak(values: np.ndarray, index: int) -> float:
    if index <= 0 or index >= values.size - 1:
        return float(index)
    alpha, beta, gamma = values[index - 1 : index + 2]
    denominator = alpha - 2.0 * beta + gamma
    return float(index + 0.5 * (alpha - gamma) / denominator) if abs(denominator) > 1e-20 else float(index)


def estimate_f0_frame(frame: np.ndarray, sample_rate: int, minimum_hz: float = 70.0, maximum_hz: float = 500.0) -> Estimate:
    if frame.size < 64 or rms(frame) < 1e-5:
        return Estimate(None, 0.0, "silent_or_too_short")
    x = remove_dc(frame) * np.hanning(frame.size)
    autocorr = signal.fftconvolve(x, x[::-1], mode="full")[frame.size - 1 :]
    if autocorr.size == 0 or autocorr[0] <= 1e-20:
        return Estimate(None, 0.0, "zero_autocorrelation")
    autocorr /= autocorr[0]
    minimum_lag = max(1, int(sample_rate / maximum_hz))
    maximum_lag = min(autocorr.size - 1, int(sample_rate / minimum_hz))
    if maximum_lag <= minimum_lag:
        return Estimate(None, 0.0, "invalid_lag_range")
    search = autocorr[minimum_lag : maximum_lag + 1]
    peaks, _ = signal.find_peaks(search)
    if peaks.size == 0:
        return Estimate(None, 0.0, "no_periodic_peak")
    peak_index = int(peaks[np.argmax(search[peaks])]) + minimum_lag
    strength = float(autocorr[peak_index])
    if strength < 0.2:
        return Estimate(None, max(0.0, strength), "weak_periodicity")
    refined_lag = _parabolic_peak(autocorr, peak_index)
    return Estimate(float(sample_rate / refined_lag), min(1.0, strength), "")


def f0_contour(audio: np.ndarray, sample_rate: int, frame_size: int = 2048, hop_size: int = 256) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    frames = frame_audio(audio, frame_size, hop_size)
    times = (np.arange(frames.shape[0]) * hop_size + frame_size / 2.0) / sample_rate
    values = np.full(frames.shape[0], np.nan)
    confidence = np.zeros(frames.shape[0])
    for index, frame in enumerate(frames):
        estimate = estimate_f0_frame(frame, sample_rate)
        confidence[index] = estimate.confidence
        if estimate.value is not None:
            values[index] = estimate.value
    return times, values, confidence


def f0_contour_metrics(reference_hz: np.ndarray, generated_hz: np.ndarray) -> dict[str, float]:
    count = min(reference_hz.size, generated_hz.size)
    if count == 0:
        return {"f0_contour_rmse_cents": float("nan"), "f0_contour_correlation": float("nan"), "voicing_f1": float("nan")}
    ref = reference_hz[:count]
    gen = generated_hz[:count]
    ref_voiced = np.isfinite(ref)
    gen_voiced = np.isfinite(gen)
    tp = int(np.sum(ref_voiced & gen_voiced))
    fp = int(np.sum(~ref_voiced & gen_voiced))
    fn = int(np.sum(ref_voiced & ~gen_voiced))
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    voicing_f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    both = ref_voiced & gen_voiced
    if not np.any(both):
        return {"f0_contour_rmse_cents": float("nan"), "f0_contour_correlation": float("nan"), "voicing_f1": voicing_f1}
    cents = 1200.0 * np.log2(gen[both] / ref[both])
    correlation = float(np.corrcoef(ref[both], gen[both])[0, 1]) if np.sum(both) >= 3 and np.std(ref[both]) > 0 and np.std(gen[both]) > 0 else float("nan")
    return {
        "f0_contour_rmse_cents": float(np.sqrt(np.mean(np.square(cents)))),
        "f0_contour_correlation": correlation,
        "voicing_f1": voicing_f1,
    }


def harmonic_metrics(audio: np.ndarray, sample_rate: int, f0_hz: float | None) -> dict[str, float]:
    if audio.size < 256 or f0_hz is None or not math.isfinite(f0_hz) or f0_hz <= 0.0:
        return {"h1_h2_db": float("nan"), "hnr_db": float("nan"), "cpp_db": float("nan")}
    x = remove_dc(audio) * np.hanning(audio.size)
    spectrum = np.abs(np.fft.rfft(x))
    freqs = np.fft.rfftfreq(x.size, 1.0 / sample_rate)

    def amplitude_near(frequency: float) -> float:
        width = max(20.0, f0_hz * 0.15)
        mask = (freqs >= frequency - width) & (freqs <= frequency + width)
        return float(np.max(spectrum[mask])) if np.any(mask) else 1e-12

    h1 = amplitude_near(f0_hz)
    h2 = amplitude_near(2.0 * f0_hz)
    h1_h2 = 20.0 * math.log10(max(h1, 1e-12) / max(h2, 1e-12))

    autocorr = signal.fftconvolve(remove_dc(audio), remove_dc(audio)[::-1], mode="full")[audio.size - 1 :]
    lag = int(round(sample_rate / f0_hz))
    periodicity = float(autocorr[lag] / max(autocorr[0], 1e-24)) if 0 < lag < autocorr.size else 0.0
    periodicity = min(0.999999, max(0.0, periodicity))
    hnr = 10.0 * math.log10(max(periodicity, 1e-12) / max(1.0 - periodicity, 1e-12))

    log_magnitude = np.log(np.maximum(spectrum, 1e-12))
    cepstrum = np.fft.irfft(log_magnitude)
    min_quefrency = max(1, int(sample_rate / 500.0))
    max_quefrency = min(cepstrum.size - 1, int(sample_rate / 70.0))
    if max_quefrency <= min_quefrency:
        cpp = float("nan")
    else:
        region = cepstrum[min_quefrency : max_quefrency + 1]
        peak = float(np.max(region))
        baseline = float(np.median(region))
        cpp = 20.0 * math.log10(max(abs(peak), 1e-12) / max(abs(baseline), 1e-12))
    return {"h1_h2_db": h1_h2, "hnr_db": hnr, "cpp_db": cpp}


def spectral_summary(audio: np.ndarray, sample_rate: int) -> dict[str, float]:
    if audio.size < 32:
        return {name: float("nan") for name in ("spectral_centroid_hz", "spectral_rolloff_hz", "spectral_slope_db_khz", "spectral_flatness", "zero_crossing_rate")}
    spectrum = np.square(np.abs(np.fft.rfft(remove_dc(audio) * np.hanning(audio.size))))
    frequencies = np.fft.rfftfreq(audio.size, 1.0 / sample_rate)
    mask = (frequencies >= 80.0) & (frequencies <= min(12000.0, sample_rate * 0.48))
    power = spectrum[mask]
    freqs = frequencies[mask]
    total = float(np.sum(power))
    centroid = float(np.sum(freqs * power) / total) if total > 0 else float("nan")
    cumulative = np.cumsum(power)
    rolloff_index = min(freqs.size - 1, int(np.searchsorted(cumulative, total * 0.95))) if total > 0 and freqs.size else 0
    rolloff = float(freqs[rolloff_index]) if freqs.size else float("nan")
    slope_mask = (freqs >= 500.0) & (freqs <= 5000.0) & (power > 0.0)
    slope = float(np.polyfit(freqs[slope_mask] / 1000.0, 10.0 * np.log10(power[slope_mask]), 1)[0]) if np.sum(slope_mask) >= 8 else float("nan")
    flatness = float(np.exp(np.mean(np.log(np.maximum(power, 1e-24)))) / np.mean(power)) if total > 0 else float("nan")
    zcr = float(np.mean(np.signbit(audio[1:]) != np.signbit(audio[:-1])))
    return {"spectral_centroid_hz": centroid, "spectral_rolloff_hz": rolloff, "spectral_slope_db_khz": slope, "spectral_flatness": flatness, "zero_crossing_rate": zcr}


def temporal_spectral_summary(audio: np.ndarray, sample_rate: int, frame_size: int = 1024, hop_size: int = 256) -> dict[str, float]:
    series = temporal_spectral_series(audio, sample_rate, frame_size, hop_size)
    if not series["time_sec"]:
        return {"centroid_mean_hz": float("nan"), "centroid_std_hz": float("nan"), "flatness_mean": float("nan"), "flatness_std": float("nan"), "rms_envelope_std_db": float("nan")}
    centroids = np.asarray(series["centroid_hz"])
    flatness = np.asarray(series["flatness"])
    rms_db = np.asarray(series["rms_db"])
    return {"centroid_mean_hz": float(np.mean(centroids)), "centroid_std_hz": float(np.std(centroids)), "flatness_mean": float(np.mean(flatness)), "flatness_std": float(np.std(flatness)), "rms_envelope_std_db": float(np.std(rms_db))}


def temporal_spectral_series(audio: np.ndarray, sample_rate: int, frame_size: int = 1024, hop_size: int = 256) -> dict[str, list[float]]:
    frames = frame_audio(audio, frame_size, hop_size)
    if frames.size == 0:
        return {"time_sec": [], "centroid_hz": [], "flatness": [], "rms_db": []}
    frequencies = np.fft.rfftfreq(frame_size, 1.0 / sample_rate)
    power = np.square(np.abs(np.fft.rfft(frames * np.hanning(frame_size), axis=1)))
    mask = (frequencies >= 80.0) & (frequencies <= min(12000.0, sample_rate * 0.48))
    selected = power[:, mask]
    selected_freqs = frequencies[mask]
    totals = np.sum(selected, axis=1)
    centroids = np.sum(selected * selected_freqs, axis=1) / np.maximum(totals, 1e-24)
    flatness = np.exp(np.mean(np.log(np.maximum(selected, 1e-24)), axis=1)) / np.maximum(np.mean(selected, axis=1), 1e-24)
    frame_rms = np.sqrt(np.mean(frames**2, axis=1))
    rms_db = 20.0 * np.log10(np.maximum(frame_rms, 1e-12))
    times = (np.arange(frames.shape[0]) * hop_size + frame_size / 2.0) / sample_rate
    return {"time_sec": times.astype(float).tolist(), "centroid_hz": centroids.astype(float).tolist(), "flatness": flatness.astype(float).tolist(), "rms_db": rms_db.astype(float).tolist()}


def envelope_timing(audio: np.ndarray, sample_rate: int, frame_size: int = 1024, hop_size: int = 256) -> dict[str, float]:
    frames = frame_audio(audio, frame_size, hop_size)
    if frames.size == 0:
        return {"onset_sec": float("nan"), "stable_sec": float("nan"), "rise_sec": float("nan")}
    envelope = np.sqrt(np.mean(frames**2, axis=1))
    times = np.arange(frames.shape[0]) * hop_size / sample_rate
    peak = float(np.max(envelope))
    if peak <= 1e-12:
        return {"onset_sec": float("nan"), "stable_sec": float("nan"), "rise_sec": float("nan")}
    def first_crossing(ratio: float) -> float:
        indices = np.flatnonzero(envelope >= peak * ratio)
        return float(times[indices[0]]) if indices.size else float("nan")
    onset, stable = first_crossing(0.1), first_crossing(0.9)
    return {"onset_sec": onset, "stable_sec": stable, "rise_sec": stable - onset if math.isfinite(onset) and math.isfinite(stable) else float("nan")}


def estimate_formants(audio: np.ndarray, sample_rate: int) -> tuple[list[float], list[float], float, str]:
    if audio.size < 128 or rms(audio) < 1e-5:
        return [float("nan")] * 3, [float("nan")] * 3, 0.0, "silent_or_too_short"
    order = min(audio.size // 4, max(10, int(sample_rate / 1000) + 2))
    x = signal.lfilter([1.0, -0.97], [1.0], remove_dc(audio)) * np.hamming(audio.size)
    autocorr = signal.fftconvolve(x, x[::-1], mode="full")[audio.size - 1 : audio.size + order]
    if autocorr.size < order + 1 or autocorr[0] <= 0.0:
        return [float("nan")] * 3, [float("nan")] * 3, 0.0, "lpc_failed"
    autocorr[0] *= 1.0001
    try:
        solution = solve_toeplitz((autocorr[:order], autocorr[:order]), -autocorr[1 : order + 1])
        roots = np.roots(np.concatenate(([1.0], solution)))
    except (ValueError, np.linalg.LinAlgError):
        return [float("nan")] * 3, [float("nan")] * 3, 0.0, "lpc_failed"
    candidates: list[tuple[float, float]] = []
    for root in roots[np.imag(roots) >= 0.0]:
        frequency = math.atan2(float(np.imag(root)), float(np.real(root))) * sample_rate / (2.0 * math.pi)
        radius = abs(root)
        if 90.0 <= frequency <= 5000.0 and 0.0 < radius < 1.0:
            bandwidth = -0.5 * sample_rate * math.log(radius) / math.pi
            if 20.0 <= bandwidth <= 900.0:
                candidates.append((frequency, bandwidth))
    candidates.sort()
    selected = candidates[:3]
    values = [item[0] for item in selected] + [float("nan")] * (3 - len(selected))
    bandwidths = [item[1] for item in selected] + [float("nan")] * (3 - len(selected))
    confidence = len(selected) / 3.0
    return values, bandwidths, confidence, "" if len(selected) == 3 else "missing_formant"
