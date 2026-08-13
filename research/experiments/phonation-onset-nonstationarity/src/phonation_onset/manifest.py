from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path


REQUIRED = {"sample_id", "relative_path", "speaker_id", "take_id", "vowel", "split", "source_kind", "license", "export_allowed", "notes"}
ALLOWED_SPLITS = {"onset-development", "onset-checkpoint", "onset-holdout"}


@dataclass(frozen=True)
class Record:
    sample_id: str
    path: Path
    speaker_id: str
    take_id: str
    vowel: str
    split: str
    source_kind: str
    license: str
    export_allowed: str
    notes: str


def load_manifest(path: Path, allowed_splits: set[str] | None = None) -> list[Record]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        missing = REQUIRED - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"missing manifest columns: {sorted(missing)}")
        rows = list(reader)
    records = []
    for row in rows:
        if allowed_splits is not None and row["split"] not in allowed_splits:
            continue
        records.append(Record(
            sample_id=row["sample_id"], path=(path.parent / row["relative_path"]).resolve(),
            speaker_id=row["speaker_id"], take_id=row["take_id"], vowel=row["vowel"], split=row["split"],
            source_kind=row["source_kind"], license=row["license"], export_allowed=row["export_allowed"], notes=row["notes"],
        ))
    return records


def validate_manifest(path: Path) -> list[str]:
    records = load_manifest(path)
    errors: list[str] = []
    ids: set[str] = set()
    ownership: dict[str, str] = {}
    for record in records:
        if record.sample_id in ids:
            errors.append(f"duplicate sample_id: {record.sample_id}")
        ids.add(record.sample_id)
        if record.split not in ALLOWED_SPLITS:
            errors.append(f"invalid split: {record.sample_id}: {record.split}")
        previous = ownership.setdefault(record.speaker_id, record.split)
        if previous != record.split:
            errors.append(f"speaker leakage: {record.speaker_id}: {previous} / {record.split}")
        if not record.path.is_file():
            errors.append(f"missing audio: {record.sample_id}: {record.path}")
        if record.source_kind == "human-reference" and record.export_allowed != "no":
            errors.append(f"human reference must remain non-exportable: {record.sample_id}")
    return errors

