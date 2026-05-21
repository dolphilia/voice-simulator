from __future__ import annotations

import argparse
import csv
import math
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np
from scipy.io import wavfile
from scipy.signal import iirpeak, lfilter

from audio_utils import estimate_f0_autocorr, estimate_formants, normalize_rms, read_mono_float, stable_middle_segment
from compare_waveforms import REPO_ROOT, compare_pair, resolve_path, save_plot


DEFAULT_REFERENCE = REPO_ROOT / "research/data/raw/reference/utau-samples/maoto/単独音/あ.wav"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "research/data/raw/generated/vowel-match-a"
DEFAULT_ANALYSIS_CSV = REPO_ROOT / "research/data/processed/analysis/vowel-match-a-iterations.csv"
DEFAULT_COMPARISON_CSV = REPO_ROOT / "research/data/processed/analysis/vowel-match-a-comparisons.csv"
DEFAULT_PLOT_DIR = REPO_ROOT / "research/data/processed/analysis/plots/vowel-match-a"


@dataclass(frozen=True)
class SynthParams:
    f0_hz: float
    f1_hz: float
    f2_hz: float
    f3_hz: float
    b1_hz: float
    b2_hz: float
    b3_hz: float
    g1: float
    g2: float
    g3: float
    source_tilt: float
    spectral_match: float


def parse_float(value: str) -> float:
    if not value:
        return float("nan")
    try:
        parsed = float(value)
    except ValueError:
        return float("nan")
    return parsed if math.isfinite(parsed) else float("nan")


def format_float(value: float) -> str:
    return f"{value:.6f}" if math.isfinite(value) else ""


def harmonic_source(params: SynthParams, sample_rate: int, duration_sec: float) -> np.ndarray:
    sample_count = int(round(sample_rate * duration_sec))
    time = np.arange(sample_count, dtype=np.float64) / sample_rate
    source = np.zeros(sample_count, dtype=np.float64)
    max_harmonic = max(1, int((sample_rate * 0.45) // max(params.f0_hz, 1.0)))

    for harmonic in range(1, max_harmonic + 1):
        amplitude = 1.0 / (harmonic ** params.source_tilt)
        source += amplitude * np.sin(2.0 * math.pi * params.f0_hz * harmonic * time)

    envelope = np.ones_like(source)
    attack = min(sample_count, int(round(0.025 * sample_rate)))
    release = min(sample_count, int(round(0.050 * sample_rate)))
    if attack > 1:
        envelope[:attack] = np.linspace(0.0, 1.0, attack)
    if release > 1:
        envelope[-release:] *= np.linspace(1.0, 0.0, release)

    return source * envelope


def apply_formants(source: np.ndarray, sample_rate: int, params: SynthParams) -> np.ndarray:
    output = np.zeros_like(source)
    for frequency, bandwidth, gain in [
        (params.f1_hz, params.b1_hz, params.g1),
        (params.f2_hz, params.b2_hz, params.g2),
        (params.f3_hz, params.b3_hz, params.g3),
    ]:
        frequency = float(np.clip(frequency, 90.0, sample_rate * 0.45))
        bandwidth = float(np.clip(bandwidth, 30.0, 900.0))
        q = max(0.1, frequency / bandwidth)
        b, a = iirpeak(frequency / (sample_rate * 0.5), q)
        output += gain * lfilter(b, a, source)

    return normalize_rms(output, target_db=-20.0)


def smooth_log_magnitude(log_magnitude: np.ndarray, width: int = 65) -> np.ndarray:
    if log_magnitude.size == 0 or width <= 1:
        return log_magnitude

    width = min(width, log_magnitude.size)
    if width % 2 == 0:
        width -= 1
    if width < 3:
        return log_magnitude

    kernel = np.hanning(width)
    kernel /= np.sum(kernel)
    padded = np.pad(log_magnitude, width // 2, mode="edge")
    return np.convolve(padded, kernel, mode="valid")


def apply_reference_envelope(audio: np.ndarray, reference_segment: np.ndarray, amount: float) -> np.ndarray:
    if amount <= 0.0 or audio.size < 16 or reference_segment.size < 16:
        return audio

    fft_size = int(2 ** math.ceil(math.log2(max(audio.size, reference_segment.size))))
    generated_spec = np.fft.rfft(audio, n=fft_size)
    reference_spec = np.fft.rfft(reference_segment * np.hanning(reference_segment.size), n=fft_size)
    generated_log = smooth_log_magnitude(np.log(np.maximum(np.abs(generated_spec), 1e-12)))
    reference_log = smooth_log_magnitude(np.log(np.maximum(np.abs(reference_spec), 1e-12)))
    correction = np.exp(np.clip((reference_log - generated_log) * amount, -2.0, 2.0))
    matched = np.fft.irfft(generated_spec * correction, n=fft_size)[: audio.size]
    return normalize_rms(matched, target_db=-20.0)


def synthesize(params: SynthParams, sample_rate: int, duration_sec: float, reference_segment: np.ndarray | None = None) -> np.ndarray:
    source = harmonic_source(params, sample_rate, duration_sec)
    audio = apply_formants(source, sample_rate, params)
    if reference_segment is not None:
        audio = apply_reference_envelope(audio, reference_segment, params.spectral_match)
    return audio


def write_wav(path: Path, sample_rate: int, audio: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    peak = float(np.max(np.abs(audio))) if audio.size else 0.0
    scaled = audio / peak * 0.95 if peak > 0.0 else audio
    wavfile.write(path, sample_rate, np.asarray(np.clip(scaled, -1.0, 1.0) * 32767.0, dtype=np.int16))


def reference_targets(reference_path: Path, sample_rate: int) -> tuple[float, list[float], list[float], np.ndarray]:
    source_rate, audio = read_mono_float(reference_path)
    if source_rate != sample_rate:
        raise ValueError(f"Expected {sample_rate} Hz reference for this experiment, got {source_rate} Hz")
    segment = stable_middle_segment(audio, sample_rate)
    f0 = estimate_f0_autocorr(segment, sample_rate)
    formants, bandwidths, _, _ = estimate_formants(segment, sample_rate, "a")
    return f0, formants, bandwidths, segment


def initial_params(reference_f0: float) -> SynthParams:
    return SynthParams(
        f0_hz=220.0 if not math.isfinite(reference_f0) else reference_f0,
        f1_hz=962.0,
        f2_hz=1405.0,
        f3_hz=2378.0,
        b1_hz=123.0,
        b2_hz=74.0,
        b3_hz=102.0,
        g1=0.46,
        g2=1.00,
        g3=0.23,
        source_tilt=1.0,
        spectral_match=0.0,
    )


def score(row: dict[str, str]) -> float:
    log_distance = parse_float(row["log_spectral_distance_db"])
    convergence = parse_float(row["spectral_convergence"])
    f0_cents = abs(parse_float(row["f0_delta_cents"]))
    formant_error = parse_float(row["formant_mae_hz"])
    centroid_delta = abs(parse_float(row["spectral_centroid_delta_hz"]))

    total = 0.0
    total += log_distance if math.isfinite(log_distance) else 100.0
    total += 12.0 * convergence if math.isfinite(convergence) else 12.0
    total += 0.015 * f0_cents if math.isfinite(f0_cents) else 10.0
    total += 0.004 * formant_error if math.isfinite(formant_error) else 8.0
    total += 0.0015 * centroid_delta if math.isfinite(centroid_delta) else 8.0
    return total


def adjusted_params(params: SynthParams, row: dict[str, str]) -> SynthParams:
    next_params = params

    if params.spectral_match >= 0.1:
        return replace(params, spectral_match=float(np.clip(params.spectral_match + 0.1, 0.0, 0.75)))

    f0_delta = parse_float(row["f0_delta_hz"])
    if math.isfinite(f0_delta):
        next_params = replace(next_params, f0_hz=float(np.clip(params.f0_hz - f0_delta * 0.85, 80.0, 500.0)))

    updates: dict[str, float] = {}
    for index, key in enumerate(["f1_hz", "f2_hz", "f3_hz"], start=1):
        delta = parse_float(row[f"f{index}_delta_hz"])
        current = getattr(next_params, key)
        if math.isfinite(delta):
            updates[key] = float(np.clip(current - delta * 0.55, 120.0, 4200.0))
    if updates:
        next_params = replace(next_params, **updates)

    centroid_delta = parse_float(row["spectral_centroid_delta_hz"])
    slope_delta = parse_float(row["spectral_slope_delta_db_per_khz"])
    if math.isfinite(centroid_delta):
        # Positive delta means generated is too bright.
        tilt = next_params.source_tilt + np.clip(centroid_delta / 2500.0, -0.18, 0.18)
        next_params = replace(next_params, source_tilt=float(np.clip(tilt, 0.55, 1.85)))
    if math.isfinite(slope_delta):
        g3 = next_params.g3 * (0.92 if slope_delta > 0.0 else 1.08)
        g1 = next_params.g1 * (1.04 if slope_delta > 0.0 else 0.98)
        next_params = replace(next_params, g1=float(np.clip(g1, 0.10, 1.40)), g3=float(np.clip(g3, 0.05, 1.20)))

    log_distance = parse_float(row["log_spectral_distance_db"])
    if math.isfinite(log_distance):
        match = next_params.spectral_match + (0.10 if log_distance > 35.0 else 0.04)
        next_params = replace(next_params, spectral_match=float(np.clip(match, 0.0, 0.75)))

    return next_params


def row_with_params(iteration: int, wav_path: Path, params: SynthParams, comparison: dict[str, str]) -> dict[str, str]:
    output = {
        "iteration": str(iteration),
        "generated_wav": str(wav_path.relative_to(REPO_ROOT)),
        "score": format_float(score(comparison)),
    }
    for key, value in params.__dict__.items():
        output[key] = format_float(value)
    for key in [
        "log_spectral_distance_db",
        "spectral_convergence",
        "normalized_cross_correlation",
        "f0_delta_cents",
        "formant_mae_hz",
        "spectral_centroid_delta_hz",
        "spectral_slope_delta_db_per_khz",
        "f1_delta_hz",
        "f2_delta_hz",
        "f3_delta_hz",
    ]:
        output[key] = comparison.get(key, "")
    return output


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    if not rows:
        raise ValueError("no rows to write")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a 10-iteration vowel matching experiment.")
    parser.add_argument("--reference", type=Path, default=DEFAULT_REFERENCE, help="Reference /a/ WAV.")
    parser.add_argument("--iterations", type=int, default=10, help="Number of trials.")
    parser.add_argument("--sample-rate", type=int, default=44100, help="Synthesis sample rate.")
    parser.add_argument("--duration", type=float, default=0.9, help="Generated WAV duration.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="Generated WAV directory.")
    parser.add_argument("--analysis-csv", type=Path, default=DEFAULT_ANALYSIS_CSV, help="Iteration analysis CSV.")
    parser.add_argument("--comparison-csv", type=Path, default=DEFAULT_COMPARISON_CSV, help="Detailed comparison CSV.")
    parser.add_argument("--plot-dir", type=Path, default=DEFAULT_PLOT_DIR, help="Comparison plot directory.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    reference_path = resolve_path(args.reference)
    output_dir = resolve_path(args.output_dir)
    analysis_csv = resolve_path(args.analysis_csv)
    comparison_csv = resolve_path(args.comparison_csv)
    plot_dir = resolve_path(args.plot_dir)

    reference_f0, reference_formants, reference_bandwidths, reference_segment = reference_targets(reference_path, args.sample_rate)
    params = initial_params(reference_f0)
    if all(math.isfinite(value) for value in reference_bandwidths):
        params = replace(params, b1_hz=reference_bandwidths[0], b2_hz=reference_bandwidths[1], b3_hz=reference_bandwidths[2])

    analysis_rows: list[dict[str, str]] = []
    comparison_rows: list[dict[str, str]] = []
    best_score = float("inf")
    best_params = params

    for iteration in range(1, args.iterations + 1):
        if iteration == args.iterations and math.isfinite(best_score):
            params = best_params

        wav_path = output_dir / f"trial-{iteration:02d}.wav"
        generated = synthesize(params, args.sample_rate, args.duration, reference_segment)
        write_wav(wav_path, args.sample_rate, generated)
        comparison, details = compare_pair(wav_path, reference_path, "a", "vowel", args.sample_rate)
        comparison["iteration"] = str(iteration)
        comparison_rows.append(comparison)
        analysis_rows.append(row_with_params(iteration, wav_path, params, comparison))
        save_plot(plot_dir / f"trial-{iteration:02d}.png", details, args.sample_rate)

        current_score = score(comparison)
        if current_score < best_score:
            best_score = current_score
            best_params = params

        params = adjusted_params(best_params, comparison)

    write_csv(analysis_csv, analysis_rows)
    write_csv(comparison_csv, comparison_rows)
    print(f"Reference: {reference_path}")
    print(f"Reference f0: {format_float(reference_f0)}")
    print(f"Reference formants: {', '.join(format_float(value) for value in reference_formants)}")
    print(f"Wrote generated WAVs to {output_dir}")
    print(f"Wrote iteration analysis to {analysis_csv}")
    print(f"Wrote detailed comparisons to {comparison_csv}")
    print(f"Best score: {format_float(best_score)}")


if __name__ == "__main__":
    main()
