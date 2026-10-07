from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from comparison_eval.extract import extract_file

from .paths import REPOSITORY_ROOT


FEATURES = ("centroid_std_hz", "flatness_std", "rms_envelope_std_db")


def _f0_variation(bundle: dict[str, Any]) -> float | None:
    contour = np.asarray([value for value in bundle["frame_series"]["f0_hz"] if value is not None], dtype=float)
    if contour.size < 3 or float(np.mean(contour)) <= 0.0:
        return None
    return float(np.std(contour) / np.mean(contour))


def _extract(path: Path, sample_id: str, kind: str) -> dict[str, Any]:
    bundle = extract_file(path, sample_id, "sustained-vowel", "stable", {"kind": kind}).to_dict()
    return {
        **{feature: bundle["scalar"].get(feature) for feature in FEATURES},
        "estimated_f0_std_fraction": _f0_variation(bundle),
        "f0_coverage": bundle["scalar"]["voiced_ratio"],
    }


def extract_temporal_metrics(path: Path, sample_id: str, kind: str = "generated") -> dict[str, Any]:
    """A2cとA3で同じ時間構造測定契約を共有する。"""
    return _extract(path, sample_id, kind)


def _summary(values: list[float | None]) -> dict[str, float | int | None]:
    finite = np.asarray([float(value) for value in values if value is not None and np.isfinite(value)], dtype=float)
    return {
        "median": float(np.median(finite)) if finite.size else None,
        "minimum": float(np.min(finite)) if finite.size else None,
        "maximum": float(np.max(finite)) if finite.size else None,
        "available": int(finite.size),
        "total": len(values),
    }


def evaluate_time_structure(
    sensitivity: dict[str, Any],
    sensitivity_dir: Path,
    reference_group: dict[str, Any],
) -> dict[str, Any]:
    feature_names = (*FEATURES, "estimated_f0_std_fraction", "f0_coverage")
    references = []
    for item in reference_group["references"]:
        values = _extract(REPOSITORY_ROOT / item["path"], item["sample_id"], "human-reference")
        references.append({"sample_id": item["sample_id"], "speaker_id": item["speaker_id"], "values": values})
    generated = []
    for record in sensitivity["records"]:
        path = sensitivity_dir / record["relative_audio_path"]
        values = _extract(path, f"{record['setting_id']}--seed-{record['seed_offset']}", "generated")
        generated.append({"setting_id": record["setting_id"], "seed_offset": record["seed_offset"], "values": values})
    reference_summary = {name: _summary([item["values"][name] for item in references]) for name in feature_names}
    setting_summary = {}
    for setting in sorted({item["setting_id"] for item in generated}):
        rows = [item for item in generated if item["setting_id"] == setting]
        setting_summary[setting] = {name: _summary([item["values"][name] for item in rows]) for name in feature_names}
    return {
        "schema_version": "1.0.0",
        "campaign_id": sensitivity["campaign_id"],
        "reference_group_id": reference_group["reference_group_id"],
        "analysis_window": "comparison-evaluation stable segment, maximum 0.45 sec",
        "reference_summary": reference_summary,
        "setting_summary": setting_summary,
        "references": references,
        "generated": generated,
        "limitations": [
            "0.45 sec contains few cycles of the lowest control frequencies",
            "reference and generated F0 are near rather than exactly matched",
            "interval overlap is diagnostic and not a perceptual pass rule"
        ],
        "formal_aggregate_score": None,
    }


def markdown_report(result: dict[str, Any]) -> str:
    names = (*FEATURES, "estimated_f0_std_fraction")
    lines = [
        "# A2c 時間構造診断",
        "",
        "同じ0.45秒stable窓で参照群と生成条件を測定した。値は中央値［最小, 最大］であり、知覚合格範囲ではない。",
        "",
        "| condition | " + " | ".join(names) + " |",
        "|---|" + "|".join("---:" for _ in names) + "|",
    ]
    rows = {"human-reference": result["reference_summary"], **result["setting_summary"]}
    for label, features in rows.items():
        cells = []
        for name in names:
            value = features[name]
            cells.append(f"{value['median']:.5g} [{value['minimum']:.5g}, {value['maximum']:.5g}]" if value["median"] is not None else "-")
        lines.append(f"| {label} | " + " | ".join(cells) + " |")
    lines.extend(["", "低周波変動に対して0.45秒は短いため、この表だけで制御帯域を最適化しない。", ""])
    return "\n".join(lines)
