from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path
from statistics import mean, median

from compare_waveforms import (
    DEFAULT_PLOT_DIR,
    REPO_ROOT,
    compare_pair,
    comparison_id,
    infer_mode,
    resolve_path,
    save_plot,
)


DEFAULT_OUTPUT_CSV = REPO_ROOT / "research/data/processed/analysis/waveform-comparison-batch.csv"
DEFAULT_SUMMARY_CSV = REPO_ROOT / "research/data/processed/analysis/waveform-comparison-batch-summary.csv"

SUMMARY_KEYS = [
    "duration_delta_ms",
    "rms_delta_db",
    "alignment_lag_ms",
    "waveform_rmse",
    "normalized_cross_correlation",
    "log_spectral_distance_db",
    "spectral_convergence",
    "spectral_centroid_delta_hz",
    "spectral_rolloff95_delta_hz",
    "spectral_slope_delta_db_per_khz",
    "peak_frequency_delta_hz",
    "spectral_flatness_delta",
    "high_band_ratio_delta",
    "air_band_ratio_delta",
    "noise_band_ratio_delta",
    "frame_log_spectral_distance_db",
    "dtw_log_spectral_distance_db",
    "onset_delta_ms",
    "stable_delta_ms",
    "rms_rise_delta_ms",
    "f0_delta_cents",
    "formant_mae_hz",
]


def read_pairs(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def parse_float(value: str) -> float | None:
    if not value:
        return None
    try:
        parsed = float(value)
    except ValueError:
        return None
    return parsed if math.isfinite(parsed) else None


def format_float(value: float) -> str:
    return f"{value:.6f}" if math.isfinite(value) else ""


def write_rows(path: Path, rows: list[dict[str, str]]) -> None:
    if not rows:
        raise ValueError("no rows to write")

    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)

    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def group_key(row: dict[str, str]) -> tuple[str, str, str, str]:
    return (
        row.get("label", ""),
        row.get("mode", ""),
        row.get("model", ""),
        row.get("preset", ""),
    )


def summarize(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    groups: dict[tuple[str, str, str, str], list[dict[str, str]]] = {}
    for row in rows:
        groups.setdefault(group_key(row), []).append(row)

    summary_rows: list[dict[str, str]] = []
    for (label, mode, model, preset), group in sorted(groups.items()):
        output = {
            "label": label,
            "mode": mode,
            "model": model,
            "preset": preset,
            "sample_count": str(len(group)),
        }
        for metric in SUMMARY_KEYS:
            values = [value for row in group if (value := parse_float(row.get(metric, ""))) is not None]
            output[f"{metric}_median"] = format_float(median(values)) if values else ""
            output[f"{metric}_mean"] = format_float(mean(values)) if values else ""
        summary_rows.append(output)

    return summary_rows


def row_with_metadata(result: dict[str, str], pair: dict[str, str]) -> dict[str, str]:
    merged = dict(result)
    for key in ["model", "preset", "notes"]:
        merged[key] = pair.get(key, "")
    if pair.get("comparison_id"):
        merged["comparison_id"] = pair["comparison_id"]
    return merged


def default_plot_path(pair: dict[str, str], generated_path: Path, reference_path: Path, label: str) -> Path:
    identifier = pair.get("comparison_id") or comparison_id(generated_path, reference_path, label)
    return DEFAULT_PLOT_DIR / f"{identifier}.png"


def run_batch(pairs: list[dict[str, str]], sample_rate: int, write_plots: bool) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for pair in pairs:
        generated_path = resolve_path(Path(pair["generated_path"]))
        reference_path = resolve_path(Path(pair["reference_path"]))
        label = pair["label"]
        mode = infer_mode(label, pair.get("mode", "auto") or "auto")
        row, details = compare_pair(generated_path, reference_path, label, mode, sample_rate)
        row = row_with_metadata(row, pair)
        rows.append(row)

        if write_plots:
            save_plot(default_plot_path(pair, generated_path, reference_path, label), details, sample_rate)

    return rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare multiple generated/reference WAV pairs.")
    parser.add_argument("--pairs", type=Path, required=True, help="Input pair CSV.")
    parser.add_argument("--output-csv", type=Path, default=DEFAULT_OUTPUT_CSV, help="Detailed output CSV.")
    parser.add_argument("--summary-csv", type=Path, default=DEFAULT_SUMMARY_CSV, help="Grouped summary CSV.")
    parser.add_argument("--sample-rate", type=int, default=44100, help="Comparison sample rate.")
    parser.add_argument("--plots", action="store_true", help="Write one PNG plot per pair.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    pairs = read_pairs(resolve_path(args.pairs))
    if not pairs:
        raise SystemExit("No comparison pairs found.")

    rows = run_batch(pairs, args.sample_rate, args.plots)
    output_csv = resolve_path(args.output_csv)
    summary_csv = resolve_path(args.summary_csv)
    write_rows(output_csv, rows)
    write_rows(summary_csv, summarize(rows))

    print(f"Compared {len(rows)} waveform pairs")
    print(f"Wrote details to {output_csv}")
    print(f"Wrote summary to {summary_csv}")


if __name__ == "__main__":
    main()
