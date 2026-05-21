from __future__ import annotations

import argparse
import csv
import unicodedata
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT_DIR = REPO_ROOT / "research/data/raw/reference/utau-samples"
DEFAULT_OUTPUT_PATH = REPO_ROOT / "research/data/processed/analysis/utau-oto-index.csv"


def read_cp932_text(path: Path) -> str:
    return path.read_text(encoding="cp932", errors="replace")


def parse_character_name(subset_dir: Path) -> str:
    for candidate in (subset_dir / "character.txt", subset_dir.parent / "character.txt"):
        if not candidate.exists():
            continue
        for line in read_cp932_text(candidate).splitlines():
            key, separator, value = line.partition("=")
            if separator and key.strip().lower() == "name":
                return value.strip()

    for candidate in sorted(subset_dir.parent.glob("*/character.txt")):
        for line in read_cp932_text(candidate).splitlines():
            key, separator, value = line.partition("=")
            if separator and key.strip().lower() == "name":
                return value.strip()

    return ""


def parse_float(value: str) -> str:
    try:
        return f"{float(value.strip()):.6f}"
    except ValueError:
        return ""


def relative_to_repo(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def normalized_text(value: str) -> str:
    return unicodedata.normalize("NFC", value)


def parse_oto_file(path: Path, input_dir: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    subset_dir = path.parent
    relative_parts = subset_dir.relative_to(input_dir).parts
    if len(relative_parts) < 2:
        return rows

    speaker_dir = relative_parts[0]
    subset = relative_parts[1]
    character_name = parse_character_name(subset_dir)

    for line_number, line in enumerate(read_cp932_text(path).splitlines(), start=1):
        raw_line = line.strip()
        if not raw_line or raw_line.startswith("#") or "=" not in raw_line:
            continue

        wav_filename, rest = raw_line.split("=", 1)
        fields = rest.split(",")
        if len(fields) < 6:
            continue

        alias = fields[0].strip()
        rows.append(
            {
                "speaker_dir": speaker_dir,
                "character_name": character_name,
                "subset": subset,
                "oto_path": relative_to_repo(path),
                "line_number": str(line_number),
                "wav_filename": normalized_text(wav_filename.strip()),
                "alias": normalized_text(alias),
                "offset_ms": parse_float(fields[1]),
                "consonant_ms": parse_float(fields[2]),
                "cutoff_ms": parse_float(fields[3]),
                "preutterance_ms": parse_float(fields[4]),
                "overlap_ms": parse_float(fields[5]),
            }
        )

    return rows


def build_index(input_dir: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for oto_path in sorted(input_dir.rglob("oto.ini")):
        rows.extend(parse_oto_file(oto_path, input_dir))
    return rows


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    if not rows:
        raise ValueError("no rows to write")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Parse UTAU oto.ini files into a UTF-8 CSV index.")
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR, help="UTAU sample root.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH, help="Output CSV path.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_dir = args.input_dir.resolve()
    if not input_dir.exists():
        raise SystemExit(f"Input directory does not exist: {input_dir}")

    rows = build_index(input_dir)
    write_csv(args.output.resolve(), rows)
    print(f"Wrote {len(rows)} oto rows to {args.output.resolve()}")


if __name__ == "__main__":
    main()
