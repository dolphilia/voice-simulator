from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path
from statistics import mean, median

import numpy as np
from scipy.io import wavfile
from scipy.signal import find_peaks, lfilter


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INDEX_PATH = REPO_ROOT / "research/data/processed/analysis/utau-sample-index.csv"
DEFAULT_OUTPUT_PATH = REPO_ROOT / "research/data/processed/analysis/utau-voice-quality.csv"
DEFAULT_SUMMARY_PATH = REPO_ROOT / "research/data/processed/analysis/utau-voice-quality-summary.csv"

VOWEL_MAP = {
    "あ": "a",
    "い": "i",
    "う": "u",
    "え": "e",
    "お": "o",
}


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def read_mono_float(path: Path) -> tuple[int, np.ndarray]:
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


def rms_db(audio: np.ndarray) -> float:
    rms = float(np.sqrt(np.mean(np.square(audio)))) if audio.size else 0.0
    return 20.0 * math.log10(max(rms, 1e-12))


def estimate_f0_autocorr(audio: np.ndarray, fs: int) -> float:
    if audio.size < fs // 30:
        return float("nan")

    x = audio - np.mean(audio)
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


def spectrum(audio: np.ndarray, fs: int) -> tuple[np.ndarray, np.ndarray]:
    fft_size = min(32768, audio.size)
    if fft_size < 16:
        return np.array([], dtype=np.float64), np.array([], dtype=np.float64)

    segment = audio[:fft_size] * np.hanning(fft_size)
    spec = np.fft.rfft(segment)
    freqs = np.fft.rfftfreq(fft_size, 1.0 / fs)
    power = np.square(np.abs(spec))
    return freqs, power


def band_power_ratio(freqs: np.ndarray, power: np.ndarray, low: float, high: float) -> float:
    total_mask = (freqs >= 80.0) & (freqs <= 8000.0)
    band_mask = (freqs >= low) & (freqs < high)
    total = float(np.sum(power[total_mask]))
    band = float(np.sum(power[band_mask]))
    return band / total if total > 0.0 else float("nan")


def spectral_centroid(freqs: np.ndarray, power: np.ndarray) -> float:
    mask = (freqs >= 80.0) & (freqs <= 8000.0)
    total = float(np.sum(power[mask]))
    return float(np.sum(freqs[mask] * power[mask]) / total) if total > 0.0 else float("nan")


def spectral_rolloff(freqs: np.ndarray, power: np.ndarray, ratio: float = 0.95) -> float:
    mask = (freqs >= 80.0) & (freqs <= 8000.0)
    masked_freqs = freqs[mask]
    masked_power = power[mask]
    total = float(np.sum(masked_power))
    if total <= 0.0:
        return float("nan")

    cumulative = np.cumsum(masked_power)
    index = int(np.searchsorted(cumulative, total * ratio))
    index = min(index, masked_freqs.size - 1)
    return float(masked_freqs[index])


def spectral_slope_db_per_khz(freqs: np.ndarray, power: np.ndarray) -> float:
    mask = (freqs >= 500.0) & (freqs <= 5000.0) & (power > 0.0)
    if int(np.sum(mask)) < 8:
        return float("nan")

    x = freqs[mask] / 1000.0
    y = 10.0 * np.log10(np.maximum(power[mask], 1e-24))
    slope, _ = np.polyfit(x, y, 1)
    return float(slope)


def harmonic_metrics(freqs: np.ndarray, power: np.ndarray, f0: float) -> tuple[float, float]:
    if not math.isfinite(f0) or f0 <= 0.0 or freqs.size == 0:
        return float("nan"), float("nan")

    magnitudes_db: list[float] = []
    harmonic_mask = np.zeros_like(freqs, dtype=bool)
    max_harmonic = int(min(5000.0, freqs[-1]) // f0)
    bin_width = freqs[1] - freqs[0] if freqs.size > 1 else 1.0
    half_width = max(30.0, bin_width * 2.0)

    for harmonic in range(1, max_harmonic + 1):
        target = harmonic * f0
        mask = np.abs(freqs - target) <= half_width
        if not np.any(mask):
            continue
        harmonic_mask |= mask
        magnitudes_db.append(10.0 * math.log10(max(float(np.max(power[mask])), 1e-24)))

    if len(magnitudes_db) >= 3:
        x = np.arange(1, len(magnitudes_db) + 1, dtype=np.float64)
        slope, _ = np.polyfit(x, np.asarray(magnitudes_db), 1)
        harmonic_slope = float(slope)
    else:
        harmonic_slope = float("nan")

    total_mask = (freqs >= 80.0) & (freqs <= 8000.0)
    total_energy = float(np.sum(power[total_mask]))
    harmonic_energy = float(np.sum(power[total_mask & harmonic_mask]))
    nonharmonic_ratio = (
        1.0 - harmonic_energy / total_energy if total_energy > 0.0 else float("nan")
    )
    return harmonic_slope, nonharmonic_ratio


def frame_metrics(audio: np.ndarray, fs: int) -> tuple[float, float]:
    frame_size = min(2048, audio.size)
    hop = frame_size // 2
    if frame_size < 256 or hop <= 0:
        return float("nan"), float("nan")

    f0_values: list[float] = []
    rms_values: list[float] = []
    for start in range(0, audio.size - frame_size + 1, hop):
        frame = audio[start : start + frame_size]
        frame_rms_db = rms_db(frame)
        rms_values.append(frame_rms_db)
        f0 = estimate_f0_autocorr(frame, fs)
        if math.isfinite(f0):
            f0_values.append(f0)

    if len(f0_values) >= 2:
        f0_array = np.asarray(f0_values)
        f0_std_cents = float(1200.0 * np.std(np.log2(f0_array / np.mean(f0_array))))
    else:
        f0_std_cents = float("nan")

    rms_std_db = float(np.std(rms_values)) if len(rms_values) >= 2 else float("nan")
    return f0_std_cents, rms_std_db


def format_float(value: float) -> str:
    return f"{value:.6f}" if math.isfinite(value) else ""


def analyze_row(row: dict[str, str]) -> dict[str, str]:
    wav_path = REPO_ROOT / row["path"]
    fs, audio = read_mono_float(wav_path)
    segment = stable_middle_segment(audio, fs)
    freqs, power = spectrum(segment, fs)
    f0 = estimate_f0_autocorr(segment, fs)
    harmonic_slope, nonharmonic_ratio = harmonic_metrics(freqs, power, f0)
    f0_std_cents, rms_std_db = frame_metrics(segment, fs)

    return {
        "speaker_dir": row["speaker_dir"],
        "character_name": row["character_name"],
        "subset": row["subset"],
        "vowel": VOWEL_MAP[row["label"]],
        "source_label": row["label"],
        "path": row["path"],
        "sample_rate": str(fs),
        "segment_duration_sec": format_float(segment.size / fs if fs > 0 else 0.0),
        "f0_hz": format_float(f0),
        "f0_std_cents": format_float(f0_std_cents),
        "rms_db": format_float(rms_db(segment)),
        "rms_std_db": format_float(rms_std_db),
        "spectral_centroid_hz": format_float(spectral_centroid(freqs, power)),
        "spectral_rolloff95_hz": format_float(spectral_rolloff(freqs, power)),
        "low_band_ratio": format_float(band_power_ratio(freqs, power, 80.0, 1000.0)),
        "mid_band_ratio": format_float(band_power_ratio(freqs, power, 1000.0, 3000.0)),
        "high_band_ratio": format_float(band_power_ratio(freqs, power, 3000.0, 8000.0)),
        "spectral_slope_db_per_khz": format_float(spectral_slope_db_per_khz(freqs, power)),
        "harmonic_slope_db_per_harmonic": format_float(harmonic_slope),
        "nonharmonic_energy_ratio": format_float(nonharmonic_ratio),
    }


def select_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [
        row
        for row in rows
        if row.get("kind") == "vowel"
        and row.get("label") in VOWEL_MAP
        and row.get("channels") == "1"
        and row.get("sample_rate") == "44100"
        and not row.get("error")
    ]


def numeric_values(rows: list[dict[str, str]], key: str) -> list[float]:
    values = []
    for row in rows:
        value = row.get(key, "")
        if not value:
            continue
        try:
            parsed = float(value)
        except ValueError:
            continue
        if math.isfinite(parsed):
            values.append(parsed)
    return values


def voice_id(row: dict[str, str]) -> str:
    return f"{row['speaker_dir']}::{row['subset']}"


def summarize(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    summary_rows: list[dict[str, str]] = []
    metrics = [
        "f0_hz",
        "f0_std_cents",
        "rms_db",
        "rms_std_db",
        "spectral_centroid_hz",
        "spectral_rolloff95_hz",
        "low_band_ratio",
        "mid_band_ratio",
        "high_band_ratio",
        "spectral_slope_db_per_khz",
        "harmonic_slope_db_per_harmonic",
        "nonharmonic_energy_ratio",
    ]

    groups: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        groups.setdefault(voice_id(row), []).append(row)

    for _, group in sorted(groups.items()):
        first = group[0]
        output = {
            "voice_id": voice_id(first),
            "speaker_dir": first["speaker_dir"],
            "character_name": first["character_name"],
            "subset": first["subset"],
            "sample_count": str(len(group)),
        }
        for metric in metrics:
            values = numeric_values(group, metric)
            output[f"{metric}_median"] = format_float(median(values)) if values else ""
            output[f"{metric}_mean"] = format_float(mean(values)) if values else ""
        summary_rows.append(output)

    return summary_rows


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    if not rows:
        raise ValueError("no rows to write")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze voice quality metrics for UTAU vowel samples.")
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX_PATH, help="Input sample index CSV.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH, help="Detailed voice quality CSV.")
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY_PATH, help="Subset summary CSV.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rows = select_rows(read_rows(args.index))
    if not rows:
        raise SystemExit("No vowel rows found. Run research/scripts/utau_index.py first.")

    analyzed_rows = [analyze_row(row) for row in rows]
    write_csv(args.output, analyzed_rows)
    write_csv(args.summary, summarize(analyzed_rows))

    print(f"Analyzed {len(analyzed_rows)} vowel samples")
    print(f"Wrote details to {args.output}")
    print(f"Wrote summary to {args.summary}")


if __name__ == "__main__":
    main()
