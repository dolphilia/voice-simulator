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
DEFAULT_OUTPUT_PATH = REPO_ROOT / "research/data/processed/analysis/utau-speaker-scale.csv"
DEFAULT_JSON_PATH = REPO_ROOT / "research/data/processed/exports/speaker-presets.generated.json"

CANONICAL_SUBSETS = {"単独音", "単独音A", "単独音B", "単独音_PLANE"}
FORMANT_KEYS = ("f1_hz", "f2_hz", "f3_hz")
MIN_CONFIDENCE = 0.667
MIN_TRACT_SCALE = 0.7
MAX_TRACT_SCALE = 1.4


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


def format_float(value: float) -> str:
    return f"{value:.6f}" if math.isfinite(value) else ""


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def reliable_canonical_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    selected = []
    for row in rows:
        confidence = parse_float(row.get("confidence", "")) or 0.0
        if row.get("subset") in CANONICAL_SUBSETS and confidence >= MIN_CONFIDENCE:
            selected.append(row)
    return selected


def canonical_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [row for row in rows if row.get("subset") in CANONICAL_SUBSETS]


def build_reference(rows: list[dict[str, str]]) -> dict[tuple[str, str], float]:
    reference: dict[tuple[str, str], float] = {}
    for vowel in ("a", "i", "u", "e", "o"):
        vowel_rows = [row for row in rows if row["vowel"] == vowel]
        for key in FORMANT_KEYS:
            values = [
                value
                for row in vowel_rows
                if (value := parse_float(row.get(key, ""))) is not None
            ]
            if values:
                reference[(vowel, key)] = median(values)
    return reference


def voice_id(row: dict[str, str]) -> str:
    return f"{row['speaker_dir']}::{row['subset']}"


def group_rows(rows: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    groups: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        groups.setdefault(voice_id(row), []).append(row)
    return groups


def estimate_group_scale(group: list[dict[str, str]], reference: dict[tuple[str, str], float]) -> dict[str, str]:
    ratios: list[float] = []
    ratios_by_formant = {key: [] for key in FORMANT_KEYS}
    reliable_sample_count = 0

    for row in group:
        confidence = parse_float(row.get("confidence", "")) or 0.0
        if confidence < MIN_CONFIDENCE:
            continue
        reliable_sample_count += 1

        vowel = row["vowel"]
        for key in FORMANT_KEYS:
            value = parse_float(row.get(key, ""))
            ref = reference.get((vowel, key))
            if value is None or ref is None or ref <= 0.0:
                continue
            ratio = value / ref
            ratios.append(ratio)
            ratios_by_formant[key].append(ratio)

    frequency_scale = median(ratios) if ratios else float("nan")
    tract_scale_raw = 1.0 / frequency_scale if frequency_scale and math.isfinite(frequency_scale) else float("nan")
    tract_scale_clamped = (
        clamp(tract_scale_raw, MIN_TRACT_SCALE, MAX_TRACT_SCALE)
        if math.isfinite(tract_scale_raw)
        else float("nan")
    )

    first = group[0]
    notes = []
    if len(ratios) < 9:
        notes.append("few_valid_formants")
    if math.isfinite(tract_scale_raw) and tract_scale_raw != tract_scale_clamped:
        notes.append("tract_scale_clamped")

    return {
        "voice_id": voice_id(first),
        "speaker_dir": first["speaker_dir"],
        "character_name": first["character_name"],
        "subset": first["subset"],
        "sample_count": str(len(group)),
        "reliable_sample_count": str(reliable_sample_count),
        "valid_ratio_count": str(len(ratios)),
        "frequency_scale_median": format_float(frequency_scale),
        "tract_scale_raw": format_float(tract_scale_raw),
        "tract_scale": format_float(tract_scale_clamped),
        "f1_scale_median": format_float(median(ratios_by_formant["f1_hz"])) if ratios_by_formant["f1_hz"] else "",
        "f2_scale_median": format_float(median(ratios_by_formant["f2_hz"])) if ratios_by_formant["f2_hz"] else "",
        "f3_scale_median": format_float(median(ratios_by_formant["f3_hz"])) if ratios_by_formant["f3_hz"] else "",
        "notes": ";".join(notes),
    }


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    if not rows:
        raise ValueError("no rows to write")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, rows: list[dict[str, str]], source_path: Path) -> None:
    payload = {
        "metadata": {
            "generatedOn": date.today().isoformat(),
            "source": source_path.relative_to(REPO_ROOT).as_posix(),
            "method": "Median of per-formant frequency ratios against canonical vowel/formant medians. Web tractScale is 1 / frequencyScale because the prototype divides formant frequency by tractScale.",
            "minConfidence": MIN_CONFIDENCE,
            "canonicalSubsets": sorted(CANONICAL_SUBSETS),
            "reviewNote": "Generated speaker scales are research outputs and should be listening-tested before adding UI presets.",
        },
        "speakers": [
            {
                "id": row["voice_id"],
                "speakerDir": row["speaker_dir"],
                "characterName": row["character_name"],
                "subset": row["subset"],
                "sampleCount": int(row["sample_count"]),
                "reliableSampleCount": int(row["reliable_sample_count"]),
                "validRatioCount": int(row["valid_ratio_count"]),
                "frequencyScale": float(row["frequency_scale_median"]),
                "tractScale": float(row["tract_scale"]),
                "rawTractScale": float(row["tract_scale_raw"]),
                "notes": row["notes"],
            }
            for row in rows
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Estimate speaker-level tractScale candidates from UTAU vowel formants.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT_PATH, help="Input vowel formant CSV.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH, help="Speaker scale CSV output.")
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON_PATH, help="Speaker preset JSON output.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rows = read_rows(args.input)
    selected = reliable_canonical_rows(rows)
    if not selected:
        raise SystemExit("No reliable canonical rows found. Run phase 1 first.")

    reference = build_reference(selected)
    groups = group_rows(canonical_rows(rows))
    output_rows = [estimate_group_scale(group, reference) for _, group in sorted(groups.items())]
    write_csv(args.output, output_rows)
    write_json(args.json, output_rows, args.input)

    print(f"Used {len(selected)} reliable canonical vowel rows")
    print(f"Wrote speaker scale CSV to {args.output}")
    print(f"Wrote speaker preset JSON to {args.json}")


if __name__ == "__main__":
    main()
