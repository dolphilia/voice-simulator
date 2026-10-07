from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .io import read_json, sha256_file
from .paths import BASELINE_ROOT


def _listening_evidence() -> list[tuple[Path, str]]:
    evidence = []
    for path in sorted((BASELINE_ROOT / "results/listening").glob("**/analysis.json")):
        evidence.append((path, path.read_text(encoding="utf-8")))
    longitudinal = BASELINE_ROOT / "results/generalization/single-listener-longitudinal-v1/aggregate.json"
    if longitudinal.is_file():
        evidence.append((longitudinal, longitudinal.read_text(encoding="utf-8")))
    return evidence


def build_ledger() -> list[dict[str, Any]]:
    evidence = _listening_evidence()
    release_path = BASELINE_ROOT / "results/baseline-release-v1/manifest.json"
    release = read_json(release_path) if release_path.is_file() else {}
    release_condition = release.get("condition")
    collected: dict[tuple[str, str], dict[str, Any]] = {}
    for manifest_path in sorted((BASELINE_ROOT / "results").glob("**/manifest.json")):
        try:
            manifest = read_json(manifest_path)
        except (json.JSONDecodeError, OSError):
            continue
        for stimulus in manifest.get("stimuli", []):
            condition = stimulus.get("condition") or stimulus.get("stimulus_id")
            digest = stimulus.get("sha256")
            if not condition or not digest:
                continue
            key = (str(condition), str(digest))
            relative = stimulus.get("relative_path")
            audio_path = (BASELINE_ROOT / relative).resolve() if relative else None
            path_ok = bool(audio_path and audio_path.is_file())
            hash_ok = bool(path_ok and sha256_file(audio_path) == digest)
            evidence_files = [
                str(path.relative_to(BASELINE_ROOT))
                for path, text in evidence
                if str(condition) in text
            ]
            entry = collected.setdefault(key, {
                "candidate_id": f"legacy-{condition}-{str(digest)[:12]}",
                "condition": condition,
                "sha256": digest,
                "relative_path": relative,
                "source_manifests": [],
                "generation": {
                    "source": stimulus.get("source"),
                    "filter": stimulus.get("filter"),
                    "parameters": stimulus.get("parameters"),
                    "diagnostics": stimulus.get("diagnostics", {}),
                    "contains_human_audio": bool(stimulus.get("contains_human_audio", manifest.get("contains_human_audio", False))),
                },
                "engineering_checks": {
                    "audio_present": path_ok,
                    "hash_verified": hash_ok,
                    "source_gate_passed": stimulus.get("gate_passed"),
                    "source_gate_failures": stimulus.get("gate_failures", []),
                },
                "proxy_results": stimulus.get("acoustic_summary", {}),
                "robustness_results": {},
                "adoption_status": "listener-qualified" if condition == release_condition else "signal-qualified" if stimulus.get("gate_passed") else "draft",
                "source_status": release.get("status") if condition == release_condition else stimulus.get("generalization_status"),
                "listening_status": "answered_exploratory" if evidence_files else "not_queued",
                "evidence_files": evidence_files,
            })
            manifest_relative = str(manifest_path.relative_to(BASELINE_ROOT))
            if manifest_relative not in entry["source_manifests"]:
                entry["source_manifests"].append(manifest_relative)
    return sorted(collected.values(), key=lambda item: (str(item["condition"]), str(item["sha256"])))


def validate_ledger(rows: list[dict[str, Any]], schema: dict[str, Any]) -> list[str]:
    errors = []
    required = set(schema["required"])
    ids: set[str] = set()
    for index, row in enumerate(rows):
        missing = required - set(row)
        if missing:
            errors.append(f"row {index}: missing {', '.join(sorted(missing))}")
        candidate_id = str(row.get("candidate_id", ""))
        if candidate_id in ids:
            errors.append(f"duplicate candidate id: {candidate_id}")
        ids.add(candidate_id)
        if row.get("listening_status") not in schema["listening_status_values"]:
            errors.append(f"{candidate_id}: invalid listening status")
        if row.get("generation", {}).get("contains_human_audio"):
            errors.append(f"{candidate_id}: generated candidate unexpectedly contains human audio")
    return errors

