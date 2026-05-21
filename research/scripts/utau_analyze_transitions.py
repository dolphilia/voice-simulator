from __future__ import annotations

import argparse
import csv
import json
import math
import unicodedata
from datetime import date
from pathlib import Path
from statistics import mean, median


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OTO_PATH = REPO_ROOT / "research/data/processed/analysis/utau-oto-index.csv"
DEFAULT_OUTPUT_PATH = REPO_ROOT / "research/data/processed/analysis/utau-vowel-transitions.csv"
DEFAULT_JSON_PATH = REPO_ROOT / "research/data/processed/exports/vowel-transition-curves.generated.json"

VOWELS = ("a", "i", "u", "e", "o")

KANA_VOWEL_RULES = [
    ("ぁ", "a"),
    ("あ", "a"),
    ("か", "a"),
    ("が", "a"),
    ("さ", "a"),
    ("ざ", "a"),
    ("た", "a"),
    ("だ", "a"),
    ("な", "a"),
    ("は", "a"),
    ("ば", "a"),
    ("ぱ", "a"),
    ("ま", "a"),
    ("ゃ", "a"),
    ("や", "a"),
    ("ら", "a"),
    ("わ", "a"),
    ("い", "i"),
    ("ぃ", "i"),
    ("き", "i"),
    ("ぎ", "i"),
    ("し", "i"),
    ("じ", "i"),
    ("ち", "i"),
    ("ぢ", "i"),
    ("に", "i"),
    ("ひ", "i"),
    ("び", "i"),
    ("ぴ", "i"),
    ("み", "i"),
    ("り", "i"),
    ("う", "u"),
    ("ぅ", "u"),
    ("く", "u"),
    ("ぐ", "u"),
    ("す", "u"),
    ("ず", "u"),
    ("つ", "u"),
    ("づ", "u"),
    ("ぬ", "u"),
    ("ふ", "u"),
    ("ぶ", "u"),
    ("ぷ", "u"),
    ("む", "u"),
    ("ゅ", "u"),
    ("ゆ", "u"),
    ("る", "u"),
    ("え", "e"),
    ("ぇ", "e"),
    ("け", "e"),
    ("げ", "e"),
    ("せ", "e"),
    ("ぜ", "e"),
    ("て", "e"),
    ("で", "e"),
    ("ね", "e"),
    ("へ", "e"),
    ("べ", "e"),
    ("ぺ", "e"),
    ("め", "e"),
    ("れ", "e"),
    ("お", "o"),
    ("ぉ", "o"),
    ("こ", "o"),
    ("ご", "o"),
    ("そ", "o"),
    ("ぞ", "o"),
    ("と", "o"),
    ("ど", "o"),
    ("の", "o"),
    ("ほ", "o"),
    ("ぼ", "o"),
    ("ぽ", "o"),
    ("も", "o"),
    ("ょ", "o"),
    ("よ", "o"),
    ("ろ", "o"),
    ("を", "o"),
]


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


def format_float(value: float | None) -> str:
    return f"{value:.6f}" if value is not None and math.isfinite(value) else ""


def normalize_alias(value: str) -> str:
    return unicodedata.normalize("NFC", unicodedata.normalize("NFKC", value)).strip()


def target_vowel(label: str) -> str:
    normalized = normalize_alias(label).lower()
    for kana, vowel in KANA_VOWEL_RULES:
        if normalized.endswith(kana):
            return vowel
    return ""


def parse_vcv_alias(alias: str) -> tuple[str, str, str]:
    normalized = normalize_alias(alias)
    parts = normalized.split()
    if len(parts) != 2:
        return "", "", ""

    previous, target = parts
    previous = previous.lower()
    if previous not in VOWELS:
        return "", "", ""

    next_vowel = target_vowel(target)
    if next_vowel not in VOWELS:
        return "", "", ""

    return previous, target, next_vowel


def transition_row(row: dict[str, str]) -> dict[str, str] | None:
    previous_vowel, target_label, next_vowel = parse_vcv_alias(row["alias"])
    if not previous_vowel or not next_vowel:
        return None

    offset = parse_float(row["offset_ms"])
    consonant = parse_float(row["consonant_ms"])
    preutterance = parse_float(row["preutterance_ms"])
    overlap = parse_float(row["overlap_ms"])
    cutoff = parse_float(row["cutoff_ms"])
    if offset is None or consonant is None or preutterance is None or overlap is None:
        return None

    transition_ms = max(0.0, preutterance - overlap)
    vowel_start_ms = offset + preutterance
    transition_start_ms = offset + overlap
    consonant_start_ms = offset
    consonant_end_ms = offset + consonant

    return {
        "speaker_dir": row["speaker_dir"],
        "character_name": row["character_name"],
        "subset": row["subset"],
        "wav_filename": row["wav_filename"],
        "alias": row["alias"],
        "previous_vowel": previous_vowel,
        "target_label": target_label,
        "next_vowel": next_vowel,
        "transition": f"{previous_vowel}->{next_vowel}",
        "offset_ms": format_float(offset),
        "consonant_ms": format_float(consonant),
        "cutoff_ms": format_float(cutoff),
        "preutterance_ms": format_float(preutterance),
        "overlap_ms": format_float(overlap),
        "transition_start_ms": format_float(transition_start_ms),
        "vowel_start_ms": format_float(vowel_start_ms),
        "consonant_start_ms": format_float(consonant_start_ms),
        "consonant_end_ms": format_float(consonant_end_ms),
        "transition_ms": format_float(transition_ms),
    }


def numeric_values(rows: list[dict[str, str]], key: str) -> list[float]:
    values = []
    for row in rows:
        value = parse_float(row.get(key, ""))
        if value is not None:
            values.append(value)
    return values


def build_curves(rows: list[dict[str, str]]) -> dict:
    grouped: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        grouped.setdefault(row["transition"], []).append(row)

    transitions = {}
    for transition, group in sorted(grouped.items()):
        transition_values = numeric_values(group, "transition_ms")
        consonant_values = numeric_values(group, "consonant_ms")
        preutterance_values = numeric_values(group, "preutterance_ms")
        overlap_values = numeric_values(group, "overlap_ms")
        median_transition_ms = median(transition_values) if transition_values else 0.0

        transitions[transition] = {
            "sampleCount": len(group),
            "medianTransitionMs": round(median_transition_ms, 3),
            "meanTransitionMs": round(mean(transition_values), 3) if transition_values else 0.0,
            "medianConsonantMs": round(median(consonant_values), 3) if consonant_values else 0.0,
            "medianPreutteranceMs": round(median(preutterance_values), 3) if preutterance_values else 0.0,
            "medianOverlapMs": round(median(overlap_values), 3) if overlap_values else 0.0,
            "normalizedCurve": [
                {"t": 0.0, "fromWeight": 1.0, "toWeight": 0.0},
                {"t": 0.25, "fromWeight": 0.844, "toWeight": 0.156},
                {"t": 0.5, "fromWeight": 0.5, "toWeight": 0.5},
                {"t": 0.75, "fromWeight": 0.156, "toWeight": 0.844},
                {"t": 1.0, "fromWeight": 0.0, "toWeight": 1.0},
            ],
        }

    all_transition_values = numeric_values(rows, "transition_ms")
    return {
        "metadata": {
            "generatedOn": date.today().isoformat(),
            "source": DEFAULT_OUTPUT_PATH.relative_to(REPO_ROOT).as_posix(),
            "method": "VCV aliases of the form '<previous vowel> <target mora>' are converted to previous/next vowel transitions. transitionMs = preutteranceMs - overlapMs.",
            "recommendedDefaultTransitionMs": round(median(all_transition_values), 3)
            if all_transition_values
            else 0.0,
            "reviewNote": "Generated curves are timing references for smooth vowel interpolation, not direct acoustic resynthesis data.",
        },
        "transitions": transitions,
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
    parser = argparse.ArgumentParser(description="Analyze vowel transition timings from parsed UTAU oto.ini rows.")
    parser.add_argument("--oto", type=Path, default=DEFAULT_OTO_PATH, help="Parsed oto index CSV.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH, help="Transition CSV output.")
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON_PATH, help="Generated transition curve JSON.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    oto_rows = read_rows(args.oto)
    transition_rows = [
        parsed
        for row in oto_rows
        if (parsed := transition_row(row)) is not None
    ]
    write_csv(args.output, transition_rows)
    write_json(args.json, build_curves(transition_rows))

    print(f"Analyzed {len(transition_rows)} VCV transition rows")
    print(f"Wrote transitions to {args.output}")
    print(f"Wrote transition curves to {args.json}")


if __name__ == "__main__":
    main()
