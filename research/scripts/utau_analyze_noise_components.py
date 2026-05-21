from __future__ import annotations

import argparse
import csv
import json
import math
import warnings
from datetime import date
from pathlib import Path
from statistics import mean, median

import numpy as np
from scipy.io import wavfile
from scipy.io.wavfile import WavFileWarning


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INDEX_PATH = REPO_ROOT / "research/data/processed/analysis/utau-sample-index.csv"
DEFAULT_OUTPUT_PATH = REPO_ROOT / "research/data/processed/analysis/utau-noise-components.csv"
DEFAULT_SUMMARY_PATH = REPO_ROOT / "research/data/processed/analysis/utau-noise-components-summary.csv"
DEFAULT_LABEL_SUMMARY_PATH = REPO_ROOT / "research/data/processed/analysis/utau-noise-components-by-label.csv"
DEFAULT_JSON_PATH = REPO_ROOT / "research/data/processed/exports/noise-component-presets.generated.json"

SIBILANT_LABELS = {"さ", "し", "す", "せ", "そ"}
H_LABELS = {"は", "ひ", "ふ", "へ", "ほ"}
TARGET_LABELS = SIBILANT_LABELS | H_LABELS
BONUS_SUBSETS = {"おまけ", "おまけA", "おまけB"}


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


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

    return fs, audio_float


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


def analysis_segment(audio: np.ndarray, fs: int, category: str) -> np.ndarray:
    trimmed = trim_silence(audio)
    if trimmed.size == 0:
        return trimmed

    if category in {"sibilant", "h_fricative", "consonant"}:
        duration = min(trimmed.size, int(round(0.18 * fs)))
        return trimmed[:duration]

    duration = min(trimmed.size, int(round(0.45 * fs)))
    center = trimmed.size // 2
    start = max(0, center - duration // 2)
    end = min(trimmed.size, start + duration)
    start = max(0, end - duration)
    return trimmed[start:end]


def rms_db(audio: np.ndarray) -> float:
    rms = float(np.sqrt(np.mean(np.square(audio)))) if audio.size else 0.0
    return 20.0 * math.log10(max(rms, 1e-12))


def spectrum(audio: np.ndarray, fs: int) -> tuple[np.ndarray, np.ndarray]:
    fft_size = min(32768, audio.size)
    if fft_size < 16:
        return np.array([], dtype=np.float64), np.array([], dtype=np.float64)

    segment = audio[:fft_size] * np.hanning(fft_size)
    spec = np.fft.rfft(segment)
    freqs = np.fft.rfftfreq(fft_size, 1.0 / fs)
    power = np.square(np.abs(spec))
    return freqs, power


def band_power(freqs: np.ndarray, power: np.ndarray, low: float, high: float) -> float:
    mask = (freqs >= low) & (freqs < high)
    return float(np.sum(power[mask]))


def band_ratio(freqs: np.ndarray, power: np.ndarray, low: float, high: float) -> float:
    total = band_power(freqs, power, 80.0, 12000.0)
    band = band_power(freqs, power, low, high)
    return band / total if total > 0.0 else float("nan")


def spectral_centroid(freqs: np.ndarray, power: np.ndarray) -> float:
    mask = (freqs >= 80.0) & (freqs <= 12000.0)
    total = float(np.sum(power[mask]))
    return float(np.sum(freqs[mask] * power[mask]) / total) if total > 0.0 else float("nan")


def peak_frequency(freqs: np.ndarray, power: np.ndarray) -> float:
    mask = (freqs >= 500.0) & (freqs <= 12000.0)
    if not np.any(mask):
        return float("nan")
    masked_freqs = freqs[mask]
    masked_power = power[mask]
    return float(masked_freqs[int(np.argmax(masked_power))])


def spectral_flatness(freqs: np.ndarray, power: np.ndarray) -> float:
    mask = (freqs >= 500.0) & (freqs <= 12000.0) & (power > 0.0)
    if not np.any(mask):
        return float("nan")
    values = power[mask]
    geometric = math.exp(float(np.mean(np.log(np.maximum(values, 1e-24)))))
    arithmetic = float(np.mean(values))
    return geometric / arithmetic if arithmetic > 0.0 else float("nan")


def zero_crossing_rate(audio: np.ndarray) -> float:
    if audio.size < 2:
        return float("nan")
    signs = np.signbit(audio)
    return float(np.count_nonzero(signs[1:] != signs[:-1]) / (audio.size - 1))


def noise_category(row: dict[str, str]) -> str:
    label = row["label"]
    subset = row["subset"]
    if label in SIBILANT_LABELS:
        return "sibilant"
    if label in H_LABELS:
        return "h_fricative"
    if "息" in label or subset == "息":
        return "breath"
    if subset == "子音":
        return "consonant"
    if subset in BONUS_SUBSETS:
        return "bonus"
    return ""


def select_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    selected = []
    for row in rows:
        category = noise_category(row)
        if (
            category
            and row.get("channels") == "1"
            and row.get("sample_rate") == "44100"
            and not row.get("error")
        ):
            selected.append(row)
    return selected


def format_float(value: float) -> str:
    return f"{value:.6f}" if math.isfinite(value) else ""


def analyze_row(row: dict[str, str]) -> dict[str, str]:
    category = noise_category(row)
    fs, audio = read_mono_float(REPO_ROOT / row["path"])
    segment = analysis_segment(audio, fs, category)
    freqs, power = spectrum(segment, fs)

    return {
        "speaker_dir": row["speaker_dir"],
        "character_name": row["character_name"],
        "subset": row["subset"],
        "category": category,
        "label": row["label"],
        "path": row["path"],
        "sample_rate": str(fs),
        "segment_duration_sec": format_float(segment.size / fs if fs > 0 else 0.0),
        "rms_db": format_float(rms_db(segment)),
        "spectral_centroid_hz": format_float(spectral_centroid(freqs, power)),
        "peak_frequency_hz": format_float(peak_frequency(freqs, power)),
        "low_band_ratio": format_float(band_ratio(freqs, power, 80.0, 1000.0)),
        "mid_band_ratio": format_float(band_ratio(freqs, power, 1000.0, 3000.0)),
        "high_band_ratio": format_float(band_ratio(freqs, power, 3000.0, 8000.0)),
        "air_band_ratio": format_float(band_ratio(freqs, power, 8000.0, 12000.0)),
        "spectral_flatness": format_float(spectral_flatness(freqs, power)),
        "zero_crossing_rate": format_float(zero_crossing_rate(segment)),
    }


def parse_float(value: str) -> float | None:
    if not value:
        return None
    try:
        parsed = float(value)
    except ValueError:
        return None
    return parsed if math.isfinite(parsed) else None


def numeric_values(rows: list[dict[str, str]], key: str) -> list[float]:
    values = []
    for row in rows:
        value = parse_float(row.get(key, ""))
        if value is not None:
            values.append(value)
    return values


def summarize(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    summary_rows = []
    metrics = [
        "rms_db",
        "spectral_centroid_hz",
        "peak_frequency_hz",
        "low_band_ratio",
        "mid_band_ratio",
        "high_band_ratio",
        "air_band_ratio",
        "spectral_flatness",
        "zero_crossing_rate",
    ]
    categories = sorted({row["category"] for row in rows})
    for category in categories:
        group = [row for row in rows if row["category"] == category]
        output = {"category": category, "sample_count": str(len(group))}
        for metric in metrics:
            values = numeric_values(group, metric)
            output[f"{metric}_median"] = format_float(median(values)) if values else ""
            output[f"{metric}_mean"] = format_float(mean(values)) if values else ""
        summary_rows.append(output)
    return summary_rows


def summarize_by_label(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    summary_rows = []
    metrics = [
        "rms_db",
        "spectral_centroid_hz",
        "peak_frequency_hz",
        "low_band_ratio",
        "mid_band_ratio",
        "high_band_ratio",
        "air_band_ratio",
        "spectral_flatness",
        "zero_crossing_rate",
    ]
    keys = sorted({(row["category"], row["label"]) for row in rows})
    for category, label in keys:
        group = [row for row in rows if row["category"] == category and row["label"] == label]
        output = {"category": category, "label": label, "sample_count": str(len(group))}
        for metric in metrics:
            values = numeric_values(group, metric)
            output[f"{metric}_median"] = format_float(median(values)) if values else ""
            output[f"{metric}_mean"] = format_float(mean(values)) if values else ""
        summary_rows.append(output)
    return summary_rows


def filter_type_for(category: str, peak_hz: float, centroid_hz: float) -> dict[str, float | str]:
    if category == "sibilant":
        return {
            "type": "bandpass",
            "centerHz": round(max(3500.0, min(9000.0, peak_hz)), 3),
            "q": 1.2,
            "mix": 0.22,
        }
    if category == "h_fricative":
        return {
            "type": "highpass",
            "cutoffHz": round(max(1200.0, min(4500.0, centroid_hz)), 3),
            "q": 0.7,
            "mix": 0.16,
        }
    if category == "breath":
        return {
            "type": "highpass",
            "cutoffHz": round(max(800.0, min(3500.0, centroid_hz)), 3),
            "q": 0.5,
            "mix": 0.1,
        }
    return {
        "type": "bandpass",
        "centerHz": round(max(1000.0, min(6000.0, peak_hz)), 3),
        "q": 1.0,
        "mix": 0.12,
    }


def build_presets(summary_rows: list[dict[str, str]], label_summary_rows: list[dict[str, str]]) -> dict:
    presets = {}
    for row in summary_rows:
        category = row["category"]
        peak = parse_float(row["peak_frequency_hz_median"]) or 2500.0
        centroid = parse_float(row["spectral_centroid_hz_median"]) or peak
        presets[category] = {
            "sampleCount": int(row["sample_count"]),
            "spectralCentroidHz": round(centroid, 3),
            "peakFrequencyHz": round(peak, 3),
            "highBandRatio": round(parse_float(row["high_band_ratio_median"]) or 0.0, 6),
            "airBandRatio": round(parse_float(row["air_band_ratio_median"]) or 0.0, 6),
            "spectralFlatness": round(parse_float(row["spectral_flatness_median"]) or 0.0, 6),
            "zeroCrossingRate": round(parse_float(row["zero_crossing_rate_median"]) or 0.0, 6),
            "filter": filter_type_for(category, peak, centroid),
        }

    label_presets = {}
    for row in label_summary_rows:
        category = row["category"]
        label = row["label"]
        if category not in {"sibilant", "h_fricative", "breath", "consonant"}:
            continue

        peak = parse_float(row["peak_frequency_hz_median"]) or 2500.0
        centroid = parse_float(row["spectral_centroid_hz_median"]) or peak
        label_presets[f"{category}:{label}"] = {
            "category": category,
            "label": label,
            "sampleCount": int(row["sample_count"]),
            "spectralCentroidHz": round(centroid, 3),
            "peakFrequencyHz": round(peak, 3),
            "highBandRatio": round(parse_float(row["high_band_ratio_median"]) or 0.0, 6),
            "airBandRatio": round(parse_float(row["air_band_ratio_median"]) or 0.0, 6),
            "filter": filter_type_for(category, peak, centroid),
        }

    return {
        "metadata": {
            "generatedOn": date.today().isoformat(),
            "source": DEFAULT_SUMMARY_PATH.relative_to(REPO_ROOT).as_posix(),
            "method": "Noise-like samples are grouped into sibilant, h_fricative, breath, consonant, and bonus categories. Initial filter candidates use median spectral centroid and peak frequency.",
            "reviewNote": "Generated values are starting points for a noise source, not final consonant synthesis parameters.",
        },
        "presets": presets,
        "labelPresets": label_presets,
    }


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    if not rows:
        raise ValueError("no rows to write")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze UTAU noise-like consonant and breath components.")
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX_PATH, help="Input sample index CSV.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH, help="Detailed CSV output.")
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY_PATH, help="Summary CSV output.")
    parser.add_argument("--label-summary", type=Path, default=DEFAULT_LABEL_SUMMARY_PATH, help="Label summary CSV output.")
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON_PATH, help="Generated filter preset JSON.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rows = select_rows(read_rows(args.index))
    analyzed_rows = [analyze_row(row) for row in rows]
    summary_rows = summarize(analyzed_rows)
    label_summary_rows = summarize_by_label(analyzed_rows)
    write_csv(args.output, analyzed_rows)
    write_csv(args.summary, summary_rows)
    write_csv(args.label_summary, label_summary_rows)
    write_json(args.json, build_presets(summary_rows, label_summary_rows))

    print(f"Analyzed {len(analyzed_rows)} noise component samples")
    print(f"Wrote details to {args.output}")
    print(f"Wrote summary to {args.summary}")
    print(f"Wrote label summary to {args.label_summary}")
    print(f"Wrote presets to {args.json}")


if __name__ == "__main__":
    main()
