from __future__ import annotations

import argparse
import csv
import json
import math
import os
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
os.environ.setdefault("MPLCONFIGDIR", str(REPO_ROOT / "research/.cache/matplotlib"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy import signal

from audio_utils import (
    align_by_correlation,
    analysis_segment,
    band_power_ratio,
    dtw_distance,
    estimate_f0_autocorr,
    estimate_formants,
    f0_delta_cents,
    formant_mae,
    format_float,
    frame_log_spectra,
    log_spectral_distance_db,
    mean_frame_log_spectral_distance,
    normalize_rms,
    normalized_cross_correlation,
    peak_db,
    peak_frequency,
    read_mono_float,
    remove_dc,
    resample_to,
    rms_rise_times,
    rms_db,
    snr_db,
    spectral_centroid,
    spectral_convergence,
    spectral_flatness,
    spectral_rolloff,
    spectral_slope_db_per_khz,
    spectrum,
    waveform_rmse,
    zero_crossing_rate,
)


DEFAULT_OUTPUT_CSV = REPO_ROOT / "research/data/processed/analysis/waveform-comparison.csv"
DEFAULT_OUTPUT_JSON = REPO_ROOT / "research/data/processed/analysis/waveform-comparison-summary.json"
DEFAULT_PLOT_DIR = REPO_ROOT / "research/data/processed/analysis/plots"
VOWEL_LABELS = {"a", "i", "u", "e", "o"}


def resolve_path(path: Path) -> Path:
    return path if path.is_absolute() else REPO_ROOT / path


def infer_mode(label: str, requested_mode: str) -> str:
    if requested_mode != "auto":
        return requested_mode
    return "vowel" if label in VOWEL_LABELS else "noise"


def comparison_id(generated_path: Path, reference_path: Path, label: str) -> str:
    return f"{label}_{generated_path.stem}_vs_{reference_path.stem}".replace(" ", "_")


def finite_delta(generated: float, reference: float) -> float:
    if math.isfinite(generated) and math.isfinite(reference):
        return generated - reference
    return float("nan")


def prepare_audio(path: Path, target_rate: int, mode: str) -> dict[str, Any]:
    source_rate, audio = read_mono_float(path)
    audio = remove_dc(audio)
    audio = resample_to(audio, source_rate, target_rate)
    segment = analysis_segment(audio, target_rate, mode)
    normalized = normalize_rms(segment)

    return {
        "path": path,
        "source_rate": source_rate,
        "sample_rate": target_rate,
        "audio": audio,
        "segment": segment,
        "normalized": normalized,
        "duration_sec": segment.size / target_rate if target_rate > 0 else 0.0,
        "rms_db": rms_db(segment),
        "normalized_rms_db": rms_db(normalized),
        "peak_db": peak_db(segment),
        "zero_crossing_rate": zero_crossing_rate(segment),
    }


def metrics_for_audio(audio: np.ndarray, sample_rate: int, label: str, mode: str) -> dict[str, Any]:
    freqs, magnitude, power = spectrum(audio, sample_rate)
    f0 = estimate_f0_autocorr(audio, sample_rate)
    formants, bandwidths, confidence, notes = estimate_formants(audio, sample_rate, label)
    spectral_high = 12000.0 if mode == "noise" else 8000.0

    return {
        "freqs": freqs,
        "magnitude": magnitude,
        "power": power,
        "f0_hz": f0,
        "formants": formants,
        "bandwidths": bandwidths,
        "formant_confidence": confidence,
        "formant_notes": notes,
        "spectral_centroid_hz": spectral_centroid(freqs, power, high=spectral_high),
        "spectral_rolloff95_hz": spectral_rolloff(freqs, power, high=spectral_high),
        "spectral_slope_db_per_khz": spectral_slope_db_per_khz(
            freqs,
            power,
            low=3000.0 if mode == "noise" else 500.0,
            high=spectral_high if mode == "noise" else 5000.0,
        ),
        "peak_frequency_hz": peak_frequency(freqs, power, high=spectral_high),
        "spectral_flatness": spectral_flatness(freqs, power, high=spectral_high),
        "low_band_ratio": band_power_ratio(freqs, power, 80.0, 1000.0, total_high=spectral_high),
        "mid_band_ratio": band_power_ratio(freqs, power, 1000.0, 3000.0, total_high=spectral_high),
        "high_band_ratio": band_power_ratio(freqs, power, 3000.0, 8000.0, total_high=spectral_high),
        "air_band_ratio": band_power_ratio(freqs, power, 8000.0, 12000.0, total_high=spectral_high),
        "noise_band_ratio": band_power_ratio(freqs, power, 3000.0, 12000.0, total_high=spectral_high),
    }


def compare_pair(generated_path: Path, reference_path: Path, label: str, mode: str, sample_rate: int) -> tuple[dict[str, str], dict[str, Any]]:
    generated = prepare_audio(generated_path, sample_rate, mode)
    reference = prepare_audio(reference_path, sample_rate, mode)
    alignment = align_by_correlation(reference["normalized"], generated["normalized"])

    ref_aligned = alignment.reference
    gen_aligned = alignment.generated
    ref_metrics = metrics_for_audio(ref_aligned, sample_rate, label, mode)
    gen_metrics = metrics_for_audio(gen_aligned, sample_rate, label, mode)
    transition_high = 12000.0 if mode == "noise" else 8000.0
    ref_frames = frame_log_spectra(ref_aligned, sample_rate, high=transition_high)
    gen_frames = frame_log_spectra(gen_aligned, sample_rate, high=transition_high)
    ref_onset_sec, ref_stable_sec, ref_rise_sec = rms_rise_times(ref_aligned, sample_rate)
    gen_onset_sec, gen_stable_sec, gen_rise_sec = rms_rise_times(gen_aligned, sample_rate)

    ref_formants = ref_metrics["formants"]
    gen_formants = gen_metrics["formants"]
    row: dict[str, str] = {
        "comparison_id": comparison_id(generated_path, reference_path, label),
        "label": label,
        "mode": mode,
        "generated_path": str(generated_path.relative_to(REPO_ROOT) if generated_path.is_relative_to(REPO_ROOT) else generated_path),
        "reference_path": str(reference_path.relative_to(REPO_ROOT) if reference_path.is_relative_to(REPO_ROOT) else reference_path),
        "sample_rate": str(sample_rate),
        "generated_source_rate": str(generated["source_rate"]),
        "reference_source_rate": str(reference["source_rate"]),
        "generated_duration_sec": format_float(generated["duration_sec"]),
        "reference_duration_sec": format_float(reference["duration_sec"]),
        "duration_delta_ms": format_float((generated["duration_sec"] - reference["duration_sec"]) * 1000.0),
        "generated_rms_db": format_float(generated["rms_db"]),
        "reference_rms_db": format_float(reference["rms_db"]),
        "rms_delta_db": format_float(finite_delta(generated["rms_db"], reference["rms_db"])),
        "generated_peak_db": format_float(generated["peak_db"]),
        "reference_peak_db": format_float(reference["peak_db"]),
        "peak_delta_db": format_float(finite_delta(generated["peak_db"], reference["peak_db"])),
        "generated_zero_crossing_rate": format_float(generated["zero_crossing_rate"]),
        "reference_zero_crossing_rate": format_float(reference["zero_crossing_rate"]),
        "zero_crossing_delta": format_float(finite_delta(generated["zero_crossing_rate"], reference["zero_crossing_rate"])),
        "alignment_lag_samples": str(alignment.lag_samples),
        "alignment_lag_ms": format_float(alignment.lag_samples / sample_rate * 1000.0),
        "aligned_duration_sec": format_float(alignment.sample_count / sample_rate),
        "waveform_rmse": format_float(waveform_rmse(ref_aligned, gen_aligned)),
        "normalized_cross_correlation": format_float(normalized_cross_correlation(ref_aligned, gen_aligned)),
        "snr_db": format_float(snr_db(ref_aligned, gen_aligned)),
        "log_spectral_distance_db": format_float(log_spectral_distance_db(ref_metrics["power"], gen_metrics["power"])),
        "spectral_convergence": format_float(spectral_convergence(ref_metrics["magnitude"], gen_metrics["magnitude"])),
        "generated_spectral_centroid_hz": format_float(gen_metrics["spectral_centroid_hz"]),
        "reference_spectral_centroid_hz": format_float(ref_metrics["spectral_centroid_hz"]),
        "spectral_centroid_delta_hz": format_float(
            finite_delta(gen_metrics["spectral_centroid_hz"], ref_metrics["spectral_centroid_hz"])
        ),
        "generated_spectral_rolloff95_hz": format_float(gen_metrics["spectral_rolloff95_hz"]),
        "reference_spectral_rolloff95_hz": format_float(ref_metrics["spectral_rolloff95_hz"]),
        "spectral_rolloff95_delta_hz": format_float(
            finite_delta(gen_metrics["spectral_rolloff95_hz"], ref_metrics["spectral_rolloff95_hz"])
        ),
        "generated_spectral_slope_db_per_khz": format_float(gen_metrics["spectral_slope_db_per_khz"]),
        "reference_spectral_slope_db_per_khz": format_float(ref_metrics["spectral_slope_db_per_khz"]),
        "spectral_slope_delta_db_per_khz": format_float(
            finite_delta(gen_metrics["spectral_slope_db_per_khz"], ref_metrics["spectral_slope_db_per_khz"])
        ),
        "generated_peak_frequency_hz": format_float(gen_metrics["peak_frequency_hz"]),
        "reference_peak_frequency_hz": format_float(ref_metrics["peak_frequency_hz"]),
        "peak_frequency_delta_hz": format_float(finite_delta(gen_metrics["peak_frequency_hz"], ref_metrics["peak_frequency_hz"])),
        "generated_spectral_flatness": format_float(gen_metrics["spectral_flatness"]),
        "reference_spectral_flatness": format_float(ref_metrics["spectral_flatness"]),
        "spectral_flatness_delta": format_float(finite_delta(gen_metrics["spectral_flatness"], ref_metrics["spectral_flatness"])),
        "generated_low_band_ratio": format_float(gen_metrics["low_band_ratio"]),
        "reference_low_band_ratio": format_float(ref_metrics["low_band_ratio"]),
        "low_band_ratio_delta": format_float(finite_delta(gen_metrics["low_band_ratio"], ref_metrics["low_band_ratio"])),
        "generated_mid_band_ratio": format_float(gen_metrics["mid_band_ratio"]),
        "reference_mid_band_ratio": format_float(ref_metrics["mid_band_ratio"]),
        "mid_band_ratio_delta": format_float(finite_delta(gen_metrics["mid_band_ratio"], ref_metrics["mid_band_ratio"])),
        "generated_high_band_ratio": format_float(gen_metrics["high_band_ratio"]),
        "reference_high_band_ratio": format_float(ref_metrics["high_band_ratio"]),
        "high_band_ratio_delta": format_float(finite_delta(gen_metrics["high_band_ratio"], ref_metrics["high_band_ratio"])),
        "generated_air_band_ratio": format_float(gen_metrics["air_band_ratio"]),
        "reference_air_band_ratio": format_float(ref_metrics["air_band_ratio"]),
        "air_band_ratio_delta": format_float(finite_delta(gen_metrics["air_band_ratio"], ref_metrics["air_band_ratio"])),
        "generated_noise_band_ratio": format_float(gen_metrics["noise_band_ratio"]),
        "reference_noise_band_ratio": format_float(ref_metrics["noise_band_ratio"]),
        "noise_band_ratio_delta": format_float(finite_delta(gen_metrics["noise_band_ratio"], ref_metrics["noise_band_ratio"])),
        "frame_log_spectral_distance_db": format_float(mean_frame_log_spectral_distance(ref_frames, gen_frames)),
        "dtw_log_spectral_distance_db": format_float(dtw_distance(ref_frames, gen_frames)),
        "generated_onset_sec": format_float(gen_onset_sec),
        "reference_onset_sec": format_float(ref_onset_sec),
        "onset_delta_ms": format_float(finite_delta(gen_onset_sec, ref_onset_sec) * 1000.0),
        "generated_stable_sec": format_float(gen_stable_sec),
        "reference_stable_sec": format_float(ref_stable_sec),
        "stable_delta_ms": format_float(finite_delta(gen_stable_sec, ref_stable_sec) * 1000.0),
        "generated_rms_rise_sec": format_float(gen_rise_sec),
        "reference_rms_rise_sec": format_float(ref_rise_sec),
        "rms_rise_delta_ms": format_float(finite_delta(gen_rise_sec, ref_rise_sec) * 1000.0),
        "generated_f0_hz": format_float(gen_metrics["f0_hz"]),
        "reference_f0_hz": format_float(ref_metrics["f0_hz"]),
        "f0_delta_hz": format_float(finite_delta(gen_metrics["f0_hz"], ref_metrics["f0_hz"])),
        "f0_delta_cents": format_float(f0_delta_cents(ref_metrics["f0_hz"], gen_metrics["f0_hz"])),
        "generated_formant_confidence": format_float(gen_metrics["formant_confidence"]),
        "reference_formant_confidence": format_float(ref_metrics["formant_confidence"]),
        "generated_formant_notes": gen_metrics["formant_notes"],
        "reference_formant_notes": ref_metrics["formant_notes"],
        "formant_mae_hz": format_float(formant_mae(ref_formants, gen_formants)),
    }

    for index in range(3):
        formant_number = index + 1
        row[f"generated_f{formant_number}_hz"] = format_float(gen_formants[index])
        row[f"reference_f{formant_number}_hz"] = format_float(ref_formants[index])
        row[f"f{formant_number}_delta_hz"] = format_float(finite_delta(gen_formants[index], ref_formants[index]))

    details = {
        "row": row,
        "reference_aligned": ref_aligned,
        "generated_aligned": gen_aligned,
        "reference_metrics": ref_metrics,
        "generated_metrics": gen_metrics,
        "reference_frames": ref_frames,
        "generated_frames": gen_frames,
    }
    return row, details


def write_csv(path: Path, row: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(row.keys()))
        writer.writeheader()
        writer.writerow(row)


def json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    return value


def write_json(path: Path, row: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(json_safe(row), f, ensure_ascii=False, indent=2)
        f.write("\n")


def save_plot(path: Path, details: dict[str, Any], sample_rate: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ref = details["reference_aligned"]
    gen = details["generated_aligned"]
    ref_metrics = details["reference_metrics"]
    gen_metrics = details["generated_metrics"]
    row = details["row"]

    fig, axes = plt.subplots(3, 1, figsize=(11, 9), constrained_layout=True)
    time = np.arange(min(ref.size, gen.size)) / sample_rate
    max_points = min(time.size, sample_rate)

    axes[0].plot(time[:max_points], ref[:max_points], label="reference", linewidth=0.8)
    axes[0].plot(time[:max_points], gen[:max_points], label="generated", linewidth=0.8, alpha=0.75)
    axes[0].set_title("Aligned waveform")
    axes[0].set_xlabel("Time [s]")
    axes[0].set_ylabel("Amplitude")
    axes[0].legend(loc="upper right")

    ref_freqs = ref_metrics["freqs"]
    gen_freqs = gen_metrics["freqs"]
    ref_power = ref_metrics["power"]
    gen_power = gen_metrics["power"]
    freq_limit = 8000.0 if row["mode"] != "noise" else 12000.0
    ref_mask = ref_freqs <= freq_limit
    gen_mask = gen_freqs <= freq_limit
    axes[1].plot(ref_freqs[ref_mask], 10.0 * np.log10(np.maximum(ref_power[ref_mask], 1e-24)), label="reference")
    axes[1].plot(gen_freqs[gen_mask], 10.0 * np.log10(np.maximum(gen_power[gen_mask], 1e-24)), label="generated")
    if row["mode"] == "noise":
        axes[1].axvspan(3000.0, 8000.0, color="#fbbf24", alpha=0.10, label="high band")
        axes[1].axvspan(8000.0, 12000.0, color="#38bdf8", alpha=0.10, label="air band")
    axes[1].set_title("Log spectrum")
    axes[1].set_xlabel("Frequency [Hz]")
    axes[1].set_ylabel("Power [dB]")
    axes[1].legend(loc="upper right")

    if ref.size >= 256 and gen.size >= 256:
        _, _, ref_spec = signal.spectrogram(ref, fs=sample_rate, nperseg=512, noverlap=384, scaling="spectrum")
        freqs, times, gen_spec = signal.spectrogram(gen, fs=sample_rate, nperseg=512, noverlap=384, scaling="spectrum")
        ref_spec = ref_spec[: gen_spec.shape[0], : gen_spec.shape[1]]
        gen_spec = gen_spec[: ref_spec.shape[0], : ref_spec.shape[1]]
        diff = 10.0 * np.log10(np.maximum(gen_spec, 1e-24)) - 10.0 * np.log10(np.maximum(ref_spec, 1e-24))
        image = axes[2].pcolormesh(times, freqs, diff, shading="auto", cmap="coolwarm", vmin=-30.0, vmax=30.0)
        axes[2].set_ylim(0.0, freq_limit)
        if row["mode"] == "noise":
            axes[2].axhline(3000.0, color="#fbbf24", linewidth=0.8, alpha=0.8)
            axes[2].axhline(8000.0, color="#38bdf8", linewidth=0.8, alpha=0.8)
        axes[2].set_title("Generated - reference spectrogram difference [dB]")
        axes[2].set_xlabel("Time [s]")
        axes[2].set_ylabel("Frequency [Hz]")
        fig.colorbar(image, ax=axes[2])
    else:
        axes[2].axis("off")
        axes[2].text(0.5, 0.5, "Too short for spectrogram", ha="center", va="center")

    fig.suptitle(row["comparison_id"])
    fig.savefig(path, dpi=140)
    plt.close(fig)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare a generated WAV with a reference WAV.")
    parser.add_argument("--generated", type=Path, required=True, help="Generated WAV path.")
    parser.add_argument("--reference", type=Path, required=True, help="Reference WAV path.")
    parser.add_argument("--label", required=True, help="Label such as a/i/u/e/o, shi, su, or breath.")
    parser.add_argument("--mode", choices=["auto", "vowel", "noise", "transition"], default="auto", help="Comparison mode.")
    parser.add_argument("--sample-rate", type=int, default=44100, help="Comparison sample rate.")
    parser.add_argument("--output-csv", type=Path, default=DEFAULT_OUTPUT_CSV, help="Output CSV path.")
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_JSON, help="Output JSON path.")
    parser.add_argument("--plot", type=Path, default=None, help="Output PNG path.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    generated_path = resolve_path(args.generated)
    reference_path = resolve_path(args.reference)
    mode = infer_mode(args.label, args.mode)
    plot_path = args.plot
    if plot_path is None:
        plot_path = DEFAULT_PLOT_DIR / f"{comparison_id(generated_path, reference_path, args.label)}.png"
    else:
        plot_path = resolve_path(plot_path)

    row, details = compare_pair(
        generated_path=generated_path,
        reference_path=reference_path,
        label=args.label,
        mode=mode,
        sample_rate=args.sample_rate,
    )
    write_csv(resolve_path(args.output_csv), row)
    write_json(resolve_path(args.output_json), row)
    save_plot(plot_path, details, args.sample_rate)

    print(f"Compared {row['comparison_id']}")
    print(f"Wrote CSV to {resolve_path(args.output_csv)}")
    print(f"Wrote JSON to {resolve_path(args.output_json)}")
    print(f"Wrote plot to {plot_path}")


if __name__ == "__main__":
    main()
