from __future__ import annotations

import argparse
import csv
import unicodedata
import wave
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT_DIR = REPO_ROOT / "research/data/raw/reference/utau-samples"
DEFAULT_OUTPUT_PATH = REPO_ROOT / "research/data/processed/analysis/utau-sample-index.csv"

VOWEL_LABELS = {
    "あ": "a",
    "い": "i",
    "う": "u",
    "え": "e",
    "お": "o",
}


@dataclass(frozen=True)
class OtoEntry:
    wav_filename: str
    alias: str


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


def parse_oto_ini(path: Path) -> dict[str, list[OtoEntry]]:
    if not path.exists():
        return {}

    entries_by_wav: dict[str, list[OtoEntry]] = {}
    for line in read_cp932_text(path).splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        wav_filename, rest = line.split("=", 1)
        alias = rest.split(",", 1)[0].strip()
        wav_filename = wav_filename.strip()
        entries_by_wav.setdefault(wav_filename, []).append(
            OtoEntry(wav_filename=wav_filename, alias=alias)
        )

    return entries_by_wav


def normalized_text(value: str) -> str:
    return unicodedata.normalize("NFC", value)


def wav_label_from_filename(path: Path) -> str:
    stem = normalized_text(path.stem)
    if stem.endswith("_wav"):
        stem = stem[:-4]
    return stem


def classify_sample(subset: str, filename_label: str, aliases: list[str]) -> str:
    normalized_subset = normalized_text(subset).lower()
    normalized_filename = normalized_text(filename_label).lower()
    normalized_aliases = [normalized_text(alias).strip().lower() for alias in aliases]

    if "息" in normalized_subset or "breath" in normalized_subset:
        return "breath"
    if "台詞" in normalized_subset or "dialogue" in normalized_subset:
        return "dialogue"

    if normalized_filename.startswith("_") or any(" " in alias for alias in normalized_aliases):
        return "vcv"

    labels = [normalized_filename, *normalized_aliases]
    if any(label in VOWEL_LABELS for label in labels):
        return "vowel"

    if len(normalized_filename) <= 3:
        return "cv"

    return "unknown"


def find_frq_file(wav_path: Path) -> Path | None:
    candidates = [
        wav_path.with_name(f"{wav_path.stem}_wav.frq"),
        wav_path.with_suffix(".frq"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def read_wav_metadata(path: Path) -> tuple[int, int, float]:
    with wave.open(str(path), "rb") as wav:
        channels = wav.getnchannels()
        sample_rate = wav.getframerate()
        frames = wav.getnframes()

    duration_sec = frames / sample_rate if sample_rate > 0 else 0.0
    return sample_rate, channels, duration_sec


def relative_to_repo(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def build_index(input_dir: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    oto_cache: dict[Path, dict[str, list[OtoEntry]]] = {}
    character_cache: dict[Path, str] = {}

    for wav_path in sorted(input_dir.rglob("*")):
        if not wav_path.is_file() or wav_path.suffix.lower() != ".wav":
            continue

        try:
            relative_parts = wav_path.relative_to(input_dir).parts
        except ValueError:
            continue
        if len(relative_parts) < 3:
            continue

        speaker_dir = relative_parts[0]
        subset = relative_parts[1]
        subset_dir = input_dir / speaker_dir / subset

        if subset_dir not in oto_cache:
            oto_cache[subset_dir] = parse_oto_ini(subset_dir / "oto.ini")
        if subset_dir not in character_cache:
            character_cache[subset_dir] = parse_character_name(subset_dir)

        filename_label = wav_label_from_filename(wav_path)
        oto_entries = oto_cache[subset_dir].get(wav_path.name, [])
        aliases = [entry.alias for entry in oto_entries]
        non_empty_aliases = [alias for alias in aliases if alias]
        primary_alias = non_empty_aliases[0] if non_empty_aliases else ""

        try:
            sample_rate, channels, duration_sec = read_wav_metadata(wav_path)
            error = ""
        except (EOFError, wave.Error) as exc:
            sample_rate = 0
            channels = 0
            duration_sec = 0.0
            error = str(exc)

        rows.append(
            {
                "speaker_dir": speaker_dir,
                "character_name": character_cache[subset_dir],
                "subset": subset,
                "filename": wav_path.name,
                "path": relative_to_repo(wav_path),
                "label": filename_label,
                "primary_alias": primary_alias,
                "alias_count": str(len(aliases)),
                "kind": classify_sample(subset, filename_label, aliases),
                "sample_rate": str(sample_rate),
                "channels": str(channels),
                "duration_sec": f"{duration_sec:.6f}",
                "has_frq": "true" if find_frq_file(wav_path) else "false",
                "has_oto": "true" if (subset_dir / "oto.ini").exists() else "false",
                "error": error,
            }
        )

    return rows


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    fieldnames = [
        "speaker_dir",
        "character_name",
        "subset",
        "filename",
        "path",
        "label",
        "primary_alias",
        "alias_count",
        "kind",
        "sample_rate",
        "channels",
        "duration_sec",
        "has_frq",
        "has_oto",
        "error",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a CSV index for local UTAU voice samples."
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=DEFAULT_INPUT_DIR,
        help="UTAU sample directory to scan.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help="CSV output path.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_dir = args.input_dir.resolve()
    output_path = args.output.resolve()

    if not input_dir.exists():
        raise SystemExit(f"Input directory does not exist: {input_dir}")

    rows = build_index(input_dir)
    write_csv(output_path, rows)
    print(f"Wrote {len(rows)} rows to {output_path}")


if __name__ == "__main__":
    main()
