from __future__ import annotations

import argparse
import csv
import math
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
os.environ.setdefault("MPLCONFIGDIR", str(REPO_ROOT / "research/.cache/matplotlib"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.io import wavfile
from scipy.linalg import solve_toeplitz
from scipy.signal import find_peaks, lfilter


DEFAULT_INDEX_PATH = REPO_ROOT / "research/data/processed/analysis/utau-sample-index.csv"
DEFAULT_OUTPUT_PATH = REPO_ROOT / "research/data/processed/analysis/utau-vowel-formants.csv"
DEFAULT_SUMMARY_PATH = REPO_ROOT / "research/data/processed/analysis/utau-vowel-formants-summary.csv"
DEFAULT_PLOT_PATH = REPO_ROOT / "research/data/processed/analysis/utau-vowel-formant-scatter.png"

VOWEL_MAP = {
    "あ": "a",
    "い": "i",
    "う": "u",
    "え": "e",
    "お": "o",
}

FORMANT_RANGES = {
    "a": [(450.0, 1100.0), (800.0, 1800.0), (1800.0, 3600.0)],
    "i": [(180.0, 550.0), (1600.0, 3200.0), (2200.0, 4200.0)],
    "u": [(180.0, 650.0), (500.0, 1600.0), (1500.0, 3600.0)],
    "e": [(300.0, 850.0), (1300.0, 2800.0), (2000.0, 3900.0)],
    "o": [(300.0, 850.0), (500.0, 1500.0), (1700.0, 3600.0)],
}


def load_index(path: Path) -> list[dict[str, str]]:
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
    if audio.size < fs // 20:
        return float("nan")

    x = audio - np.mean(audio)
    x = lfilter([1.0, -0.97], [1.0], x)
    window = np.hanning(x.size)
    x = x * window
    corr = np.correlate(x, x, mode="full")[x.size - 1 :]
    if corr.size == 0 or corr[0] <= 0:
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
        peak_values = search[peaks]
        lag = int(peaks[np.argmax(peak_values)]) + min_lag

    return fs / lag if lag > 0 else float("nan")


def lpc_coefficients(audio: np.ndarray, order: int) -> np.ndarray:
    x = audio - np.mean(audio)
    x = lfilter([1.0, -0.97], [1.0], x)
    x = x * np.hamming(x.size)
    autocorr = np.correlate(x, x, mode="full")[x.size - 1 : x.size + order]

    if autocorr[0] <= 0.0:
        raise ValueError("zero autocorrelation")

    autocorr[0] *= 1.0001
    solution = solve_toeplitz((autocorr[:order], autocorr[:order]), -autocorr[1 : order + 1])
    return np.concatenate(([1.0], solution))


def estimate_formants(audio: np.ndarray, fs: int, vowel: str) -> tuple[list[float], list[float], float, str]:
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

    formants = [frequency for frequency, _ in selected]
    bandwidths = [bandwidth for _, bandwidth in selected]
    return formants, bandwidths, confidence, ";".join(notes)


def db_at_frequency(audio: np.ndarray, fs: int, frequency: float) -> float:
    if not np.isfinite(frequency) or frequency <= 0.0 or audio.size < 8:
        return float("nan")

    fft_size = min(16384, audio.size)
    segment = audio[:fft_size] * np.hanning(fft_size)
    spectrum = np.fft.rfft(segment)
    frequencies = np.fft.rfftfreq(fft_size, 1.0 / fs)
    index = int(np.argmin(np.abs(frequencies - frequency)))
    magnitude = abs(spectrum[index])
    return 20.0 * math.log10(max(magnitude, 1e-12))


def analyze_row(row: dict[str, str]) -> dict[str, str]:
    vowel = VOWEL_MAP[row["label"]]
    wav_path = REPO_ROOT / row["path"]
    fs, audio = read_mono_float(wav_path)
    segment = stable_middle_segment(audio, fs)
    f0_hz = estimate_f0_autocorr(segment, fs)
    formants, bandwidths, confidence, notes = estimate_formants(segment, fs, vowel)
    gains = [db_at_frequency(segment, fs, frequency) for frequency in formants]
    max_gain = max([gain for gain in gains if np.isfinite(gain)], default=float("nan"))
    relative_gains = [
        gain - max_gain if np.isfinite(gain) and np.isfinite(max_gain) else float("nan")
        for gain in gains
    ]

    return {
        "speaker_dir": row["speaker_dir"],
        "character_name": row["character_name"],
        "subset": row["subset"],
        "vowel": vowel,
        "source_label": row["label"],
        "path": row["path"],
        "sample_rate": str(fs),
        "segment_duration_sec": f"{segment.size / fs:.6f}" if fs > 0 else "0.000000",
        "f0_hz": format_float(f0_hz),
        "f1_hz": format_float(formants[0]),
        "f2_hz": format_float(formants[1]),
        "f3_hz": format_float(formants[2]),
        "b1_hz": format_float(bandwidths[0]),
        "b2_hz": format_float(bandwidths[1]),
        "b3_hz": format_float(bandwidths[2]),
        "g1_db": format_float(relative_gains[0]),
        "g2_db": format_float(relative_gains[1]),
        "g3_db": format_float(relative_gains[2]),
        "rms_db": format_float(rms_db(segment)),
        "confidence": f"{confidence:.3f}",
        "notes": notes,
    }


def format_float(value: float) -> str:
    return f"{value:.3f}" if np.isfinite(value) else ""


def select_vowel_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [
        row
        for row in rows
        if row.get("kind") == "vowel"
        and row.get("label") in VOWEL_MAP
        and row.get("channels") == "1"
        and row.get("sample_rate") == "44100"
        and not row.get("error")
    ]


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    if not rows:
        raise ValueError("no rows to write")

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def numeric_values(rows: list[dict[str, str]], key: str) -> list[float]:
    values: list[float] = []
    for row in rows:
        value = row.get(key, "")
        if not value:
            continue
        try:
            values.append(float(value))
        except ValueError:
            continue
    return values


def summarize(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    summary_rows: list[dict[str, str]] = []
    for vowel in ("a", "i", "u", "e", "o"):
        group = [row for row in rows if row["vowel"] == vowel]
        output: dict[str, str] = {
            "vowel": vowel,
            "count": str(len(group)),
        }
        for key in (
            "f0_hz",
            "f1_hz",
            "f2_hz",
            "f3_hz",
            "b1_hz",
            "b2_hz",
            "b3_hz",
            "g1_db",
            "g2_db",
            "g3_db",
            "rms_db",
            "confidence",
        ):
            values = numeric_values(group, key)
            output[f"{key}_median"] = format_float(float(np.median(values))) if values else ""
            output[f"{key}_mean"] = format_float(float(np.mean(values))) if values else ""
        summary_rows.append(output)
    return summary_rows


def plot_formants(rows: list[dict[str, str]], path: Path) -> None:
    colors = {
        "a": "#d55e00",
        "i": "#0072b2",
        "u": "#009e73",
        "e": "#cc79a7",
        "o": "#e69f00",
    }
    plt.figure(figsize=(8, 6))
    for vowel, color in colors.items():
        group = [row for row in rows if row["vowel"] == vowel]
        pairs = []
        for row in group:
            try:
                f1_value = float(row["f1_hz"])
                f2_value = float(row["f2_hz"])
            except ValueError:
                continue
            pairs.append((f1_value, f2_value))

        if pairs:
            f1 = [pair[0] for pair in pairs]
            f2 = [pair[1] for pair in pairs]
            plt.scatter(f2, f1, label=f"/{vowel}/", color=color, alpha=0.8)

    plt.gca().invert_xaxis()
    plt.gca().invert_yaxis()
    plt.xlabel("F2 (Hz)")
    plt.ylabel("F1 (Hz)")
    plt.title("UTAU vowel formant scatter")
    plt.grid(True, alpha=0.25)
    plt.legend()
    path.parent.mkdir(parents=True, exist_ok=True)
    plt.tight_layout()
    plt.savefig(path, dpi=160)
    plt.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze UTAU vowel formants from indexed WAV files.")
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX_PATH, help="Input sample index CSV.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH, help="Detailed formant CSV.")
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY_PATH, help="Summary CSV.")
    parser.add_argument("--plot", type=Path, default=DEFAULT_PLOT_PATH, help="Scatter plot output PNG.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    index_rows = load_index(args.index)
    vowel_rows = select_vowel_rows(index_rows)
    if not vowel_rows:
        raise SystemExit("No vowel rows found. Run research/scripts/utau_index.py first.")

    analyzed_rows = [analyze_row(row) for row in vowel_rows]
    write_csv(args.output, analyzed_rows)
    write_csv(args.summary, summarize(analyzed_rows))
    plot_formants(analyzed_rows, args.plot)

    print(f"Analyzed {len(analyzed_rows)} vowel samples")
    print(f"Wrote details to {args.output}")
    print(f"Wrote summary to {args.summary}")
    print(f"Wrote plot to {args.plot}")


if __name__ == "__main__":
    main()
