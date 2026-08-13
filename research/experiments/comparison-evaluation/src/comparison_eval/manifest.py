from __future__ import annotations

import csv
import hashlib
from dataclasses import dataclass
from pathlib import Path


REQUIRED_COLUMNS = ("sample_id", "relative_path", "kind", "profile", "label", "speaker_id", "source_recording_id", "split", "license")
KINDS = {"human", "generated", "analytic"}
SPLITS = {"development", "calibration", "holdout"}


@dataclass(frozen=True)
class ManifestRecord:
    sample_id: str
    relative_path: str
    kind: str
    profile: str
    label: str
    speaker_id: str
    source_recording_id: str
    split: str
    license: str
    metadata: dict[str, str]


def load_manifest(path: Path) -> list[ManifestRecord]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        missing = [column for column in REQUIRED_COLUMNS if column not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"missing columns: {', '.join(missing)}")
        records = []
        for row in reader:
            values = {column: (row.get(column) or "").strip() for column in REQUIRED_COLUMNS}
            metadata = {key: value for key, value in row.items() if key not in REQUIRED_COLUMNS and value not in (None, "")}
            records.append(ManifestRecord(**values, metadata=metadata))
        return records


def validate_manifest(path: Path, records: list[ManifestRecord]) -> list[str]:
    errors: list[str] = []
    seen: set[str] = set()
    group_split: dict[str, str] = {}
    for index, record in enumerate(records, 2):
        prefix = f"row {index} ({record.sample_id or 'no-id'})"
        if not all(getattr(record, column) for column in REQUIRED_COLUMNS):
            errors.append(f"{prefix}: empty required field")
        if record.sample_id in seen:
            errors.append(f"{prefix}: duplicate sample_id")
        seen.add(record.sample_id)
        if record.kind not in KINDS:
            errors.append(f"{prefix}: invalid kind {record.kind}")
        if record.split not in SPLITS:
            errors.append(f"{prefix}: invalid split {record.split}")
        audio_path = (path.parent / record.relative_path).resolve()
        if not audio_path.is_file():
            errors.append(f"{prefix}: file not found {record.relative_path}")
        for group_kind, group in (("speaker", record.speaker_id), ("source", record.source_recording_id)):
            key = f"{group_kind}:{group}"
            previous = group_split.setdefault(key, record.split)
            if previous != record.split:
                errors.append(f"{prefix}: {group_kind} group leaks across splits ({previous}, {record.split})")
    return errors


def deterministic_split(group_id: str, salt: str = "voice-simulator-v1") -> str:
    bucket = int(hashlib.sha256(f"{salt}:{group_id}".encode()).hexdigest()[:8], 16) % 100
    return "development" if bucket < 60 else "calibration" if bucket < 80 else "holdout"
