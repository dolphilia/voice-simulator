from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from comparison_eval.benchmark import run_task

from .io import sha256_file
from .paths import REPOSITORY_ROOT


CATEGORIES = {"signal_integrity", "pitch_voicing", "resonance", "spectral_timbre", "source_voice_quality"}


def validate_reference_group(group: dict[str, Any]) -> list[str]:
    errors = []
    allowed = set(group["selection"]["allowed_splits"])
    lower, upper = group["selection"]["f0_interval_hz"]
    speakers = set()
    for reference in group["references"]:
        path = REPOSITORY_ROOT / reference["path"]
        if reference["split"] == "holdout" or reference["split"] not in allowed:
            errors.append(f"{reference['sample_id']}: forbidden split")
        if not lower <= reference["estimated_f0_hz"] <= upper:
            errors.append(f"{reference['sample_id']}: F0 outside selection interval")
        if not path.is_file():
            errors.append(f"{reference['sample_id']}: missing audio")
        elif sha256_file(path) != reference["sha256"]:
            errors.append(f"{reference['sample_id']}: hash mismatch")
        speakers.add(reference["speaker_id"])
    if len(speakers) < 2:
        errors.append("reference group must contain multiple speakers")
    return errors


def _summary(values: list[float]) -> dict[str, float | int | None]:
    finite = np.asarray([value for value in values if np.isfinite(value)], dtype=float)
    return {
        "median": float(np.median(finite)) if finite.size else None,
        "minimum": float(np.min(finite)) if finite.size else None,
        "maximum": float(np.max(finite)) if finite.size else None,
        "available": int(finite.size),
        "total": len(values),
    }


def evaluate_sensitivity_references(
    sensitivity: dict[str, Any],
    sensitivity_dir: Path,
    group: dict[str, Any],
) -> dict[str, Any]:
    errors = validate_reference_group(group)
    if errors:
        raise ValueError("; ".join(errors))
    results = []
    for record in sensitivity["records"]:
        generated = sensitivity_dir / record["relative_audio_path"]
        for reference in group["references"]:
            task = {
                "task_id": f"{record['setting_id']}--seed-{record['seed_offset']}--{reference['sample_id']}",
                "generated_path": str(generated),
                "reference_path": str(REPOSITORY_ROOT / reference["path"]),
                "profile": "sustained-vowel",
                "label": "あ",
                "reference_split": reference["split"],
                "variant": record["setting_id"],
            }
            item = run_task(task, REPOSITORY_ROOT, "stable", None, CATEGORIES, {
                "clipping_ratio_fail": 0.01,
                "silence_ratio_fail": 0.99,
            })
            item["speaker_id"] = reference["speaker_id"]
            item["seed_offset"] = record["seed_offset"]
            results.append(item)
    settings = sorted({item["task"]["variant"] for item in results})
    categories = sorted({category for item in results for category in item["scorecard"]["categories"]})
    aggregate = {}
    for setting in settings:
        rows = [item for item in results if item["task"]["variant"] == setting]
        aggregate[setting] = {
            category: _summary([
                float(item["scorecard"]["categories"][category]["target_similarity"])
                for item in rows
                if category in item["scorecard"]["categories"] and item["scorecard"]["categories"][category].get("target_similarity") is not None
            ])
            for category in categories
        }
    return {
        "schema_version": "1.0.0",
        "campaign_id": sensitivity["campaign_id"],
        "reference_group_id": group["reference_group_id"],
        "reference_count": len(group["references"]),
        "speaker_count": len({item["speaker_id"] for item in group["references"]}),
        "comparison_count": len(results),
        "individual_results": results,
        "setting_category_summary": aggregate,
        "holdout_opened": False,
        "formal_aggregate_score": None,
        "interpretation": "category-specific development diagnostics; not human-likeness or independent confirmation",
    }


def markdown_report(result: dict[str, Any]) -> str:
    categories = sorted(next(iter(result["setting_category_summary"].values())).keys())
    lines = [
        "# A2b 複数参照診断",
        "",
        f"参照群 `{result['reference_group_id']}` の{result['speaker_count']}話者・{result['reference_count']}音を用いた。holdoutは開いていない。",
        "",
        "各セルはtarget similarityの中央値／最悪値である。カテゴリを横断する総合点は作らない。",
        "",
        "| setting | " + " | ".join(categories) + " |",
        "|---|" + "|".join("---:" for _ in categories) + "|",
    ]
    for setting, values in result["setting_category_summary"].items():
        cells = []
        for category in categories:
            item = values[category]
            cells.append(f"{item['median']:.1f}/{item['minimum']:.1f}" if item["median"] is not None else "-")
        lines.append(f"| {setting} | " + " | ".join(cells) + " |")
    lines.extend(["", "この表は探索診断であり、自然さや人声性の順位ではない。", ""])
    return "\n".join(lines)

