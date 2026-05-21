from __future__ import annotations

import argparse
import csv
import json
import math
from datetime import date
from pathlib import Path
from statistics import median


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT_PATH = REPO_ROOT / "research/data/processed/analysis/utau-vowel-formants.csv"
DEFAULT_JSON_PATH = REPO_ROOT / "research/data/processed/exports/vowel-presets.generated.json"
DEFAULT_TS_PATH = REPO_ROOT / "research/data/processed/exports/vowel-presets.generated.ts"
DEFAULT_COMPARISON_PATH = REPO_ROOT / "research/data/processed/analysis/utau-vowel-presets-comparison.csv"

VOWELS = ("a", "i", "u", "e", "o")
MIN_CONFIDENCE = 0.667

CURRENT_WEB_PRESETS = {
    "a": [(730, 90, 1.0), (1090, 110, 0.55), (2440, 160, 0.35)],
    "i": [(270, 60, 1.0), (2290, 100, 0.5), (3010, 120, 0.3)],
    "u": [(300, 70, 1.0), (870, 90, 0.6), (2240, 140, 0.3)],
    "e": [(530, 80, 1.0), (1840, 100, 0.55), (2480, 150, 0.35)],
    "o": [(570, 80, 1.0), (840, 90, 0.6), (2410, 150, 0.3)],
}


def read_rows(path: Path) -> list[dict[str, str]]:
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


def values_for(rows: list[dict[str, str]], key: str) -> list[float]:
    values = []
    for row in rows:
        value = parse_float(row.get(key, ""))
        if value is not None:
            values.append(value)
    return values


def gain_from_db(relative_db: float | None) -> float:
    if relative_db is None:
        return 0.35
    gain = 10.0 ** (relative_db / 20.0)
    return max(0.12, min(1.0, gain))


def rounded_int(value: float, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, int(round(value))))


def build_presets(rows: list[dict[str, str]]) -> tuple[dict[str, dict], list[dict[str, str]]]:
    presets: dict[str, dict] = {}
    comparison_rows: list[dict[str, str]] = []

    for vowel in VOWELS:
        vowel_rows = [row for row in rows if row["vowel"] == vowel]
        reliable_rows = [
            row
            for row in vowel_rows
            if (parse_float(row.get("confidence", "")) or 0.0) >= MIN_CONFIDENCE
        ]

        formants = []
        for index in range(1, 4):
            frequency_values = values_for(reliable_rows, f"f{index}_hz")
            bandwidth_values = values_for(reliable_rows, f"b{index}_hz")
            gain_values = values_for(reliable_rows, f"g{index}_db")

            frequency = rounded_int(median(frequency_values), 120, 5000)
            bandwidth = rounded_int(median(bandwidth_values), 35, 600)
            gain = round(gain_from_db(median(gain_values) if gain_values else None), 3)

            formants.append(
                {
                    "frequency": frequency,
                    "bandwidth": bandwidth,
                    "gain": gain,
                }
            )

            current_frequency, current_bandwidth, current_gain = CURRENT_WEB_PRESETS[vowel][index - 1]
            comparison_rows.append(
                {
                    "vowel": vowel,
                    "formant": f"F{index}",
                    "source_count": str(len(vowel_rows)),
                    "reliable_count": str(len(reliable_rows)),
                    "generated_frequency": str(frequency),
                    "current_frequency": str(current_frequency),
                    "frequency_delta": str(frequency - current_frequency),
                    "generated_bandwidth": str(bandwidth),
                    "current_bandwidth": str(current_bandwidth),
                    "bandwidth_delta": str(bandwidth - current_bandwidth),
                    "generated_gain": f"{gain:.3f}",
                    "current_gain": f"{current_gain:.3f}",
                    "gain_delta": f"{gain - current_gain:.3f}",
                }
            )

        presets[vowel] = {
            "id": vowel,
            "label": f"/{vowel}/",
            "formants": formants,
            "source": {
                "sampleCount": len(vowel_rows),
                "reliableSampleCount": len(reliable_rows),
                "minConfidence": MIN_CONFIDENCE,
            },
        }

    return presets, comparison_rows


def write_json(path: Path, presets: dict[str, dict], source_path: Path) -> None:
    payload = {
        "metadata": {
            "generatedOn": date.today().isoformat(),
            "source": source_path.relative_to(REPO_ROOT).as_posix(),
            "method": "Median per vowel/formant from rows with confidence >= 0.667. Gains are converted from relative dB to linear amplitude.",
            "reviewNote": "Generated values are research outputs and should be listening-tested before replacing web defaults.",
        },
        "vowels": presets,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_ts(path: Path, presets: dict[str, dict], source_path: Path) -> None:
    lines = [
        "// Generated by research/scripts/export_vowel_presets.py.",
        "// Research output: listening-test before replacing production vowel defaults.",
        f"// Source: {source_path.relative_to(REPO_ROOT).as_posix()}",
        "",
        'export type GeneratedVowelId = "a" | "i" | "u" | "e" | "o";',
        "",
        "export type GeneratedFormant = {",
        "  frequency: number;",
        "  bandwidth: number;",
        "  gain: number;",
        "};",
        "",
        "export type GeneratedVowelProfile = {",
        "  id: GeneratedVowelId;",
        "  label: string;",
        "  formants: [GeneratedFormant, GeneratedFormant, GeneratedFormant];",
        "};",
        "",
        "export const GENERATED_UTAU_VOWEL_PROFILES: Record<GeneratedVowelId, GeneratedVowelProfile> = {",
    ]

    for vowel in VOWELS:
        profile = presets[vowel]
        lines.extend(
            [
                f"  {vowel}: {{",
                f'    id: "{vowel}",',
                f'    label: "{profile["label"]}",',
                "    formants: [",
            ]
        )
        for formant in profile["formants"]:
            lines.append(
                "      "
                + "{ "
                + f'frequency: {formant["frequency"]}, '
                + f'bandwidth: {formant["bandwidth"]}, '
                + f'gain: {formant["gain"]:.3f} '
                + "},"
            )
        lines.extend(["    ],", "  },"])

    lines.extend(["};", "", 'export const GENERATED_UTAU_VOWEL_ORDER: GeneratedVowelId[] = ["a", "i", "u", "e", "o"];', ""])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def write_comparison_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export Web-ready vowel presets from UTAU formant analysis.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT_PATH, help="Input formant analysis CSV.")
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON_PATH, help="Generated JSON output path.")
    parser.add_argument("--ts", type=Path, default=DEFAULT_TS_PATH, help="Generated TypeScript output path.")
    parser.add_argument("--comparison", type=Path, default=DEFAULT_COMPARISON_PATH, help="Comparison CSV output path.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rows = read_rows(args.input)
    presets, comparison_rows = build_presets(rows)
    write_json(args.json, presets, args.input)
    write_ts(args.ts, presets, args.input)
    write_comparison_csv(args.comparison, comparison_rows)

    print(f"Wrote JSON presets to {args.json}")
    print(f"Wrote TypeScript presets to {args.ts}")
    print(f"Wrote comparison CSV to {args.comparison}")


if __name__ == "__main__":
    main()
