from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import numpy as np

from .generator_adapter import render_b9, write_render
from .measurement_adapter import evaluate_constraints, measure
from .sensitivity import _numeric_summary
from .time_structure import extract_temporal_metrics


BEHAVIOR_FEATURES = ("estimated_f0_std_fraction", "rms_envelope_std_db", "centroid_std_hz")


def select_diverse_candidates(search: dict[str, Any], maximum: int) -> list[dict[str, Any]]:
    eligible = [row for row in search["settings"] if row["engineering_pass_rate"] == 1.0]
    by_id = {row["setting_id"]: row for row in eligible}
    required = [setting_id for setting_id in ("structured-00", "structured-04", "random-27") if setting_id in by_id]
    matrix = np.asarray([
        [row["behavior_features"][name]["median"] for name in BEHAVIOR_FEATURES]
        for row in eligible
    ], dtype=float)
    lower = np.min(matrix, axis=0)
    span = np.maximum(np.max(matrix, axis=0) - lower, 1e-12)
    normalized = {row["setting_id"]: (matrix[index] - lower) / span for index, row in enumerate(eligible)}
    selected = list(dict.fromkeys(required))
    while len(selected) < min(maximum, len(eligible)):
        remaining = [row for row in eligible if row["setting_id"] not in selected]
        scored = []
        for row in remaining:
            distance = min(float(np.linalg.norm(normalized[row["setting_id"]] - normalized[item])) for item in selected)
            scored.append((distance, row["setting_id"]))
        selected.append(sorted(scored, key=lambda item: (-item[0], item[1]))[0][1])
    return [{
        "candidate_id": setting_id,
        "selection_reason": "anchor-or-calibration" if setting_id in required else "greedy-maximin-behavior-diversity",
        "source_method": by_id[setting_id]["method"],
        "source_behavior_cell": by_id[setting_id]["behavior_cell"],
        "parameters": by_id[setting_id]["parameters"],
    } for setting_id in selected]


def _f0_aware_constraints(measured: dict[str, Any], targets: dict[str, Any], expected_f0: float, tolerance: float) -> dict[str, Any]:
    result = evaluate_constraints(measured, targets)
    checks = [check for check in result["checks"] if check["target_id"] != "control-f0-mean"]
    value = measured["values"].get("rendered_f0_mean_hz")
    passed = value is not None and abs(float(value) - expected_f0) <= expected_f0 * tolerance
    checks.append({
        "target_id": "control-f0-mean-scaled",
        "feature": "rendered_f0_mean_hz",
        "value": value,
        "expected": expected_f0,
        "relative_tolerance": tolerance,
        "state": "available" if value is not None else "unavailable",
        "passed": passed,
    })
    return {"passed": all(check["passed"] for check in checks), "checks": checks}


def run_robustness(output_dir: Path, search: dict[str, Any], config: dict[str, Any], targets: dict[str, Any]) -> dict[str, Any]:
    started = time.perf_counter()
    policy = config["robustness"]
    selected = select_diverse_candidates(search, int(policy["maximum_candidates"]))
    expected_renders = len(selected) * len(policy["seed_offsets"]) * len(policy["f0_values_hz"])
    if expected_renders > int(policy["maximum_renders"]):
        raise ValueError("A4生成数が凍結予算を超えます")
    records = []
    for candidate_spec in selected:
        for f0_hz in policy["f0_values_hz"]:
            for seed in policy["seed_offsets"]:
                candidate = render_b9(candidate_spec["parameters"], int(seed), float(f0_hz))
                path = output_dir / "audio" / f"{candidate_spec['candidate_id']}--f0-{int(f0_hz)}--seed-{seed}.wav"
                digest = write_render(path, candidate)
                measured = measure(path, candidate, path.stem)
                temporal = extract_temporal_metrics(path, path.stem)
                records.append({
                    "candidate_id": candidate_spec["candidate_id"],
                    "f0_hz": f0_hz,
                    "seed_offset": seed,
                    "wav_sha256": digest,
                    "relative_audio_path": str(path.relative_to(output_dir)),
                    "engineering_checks": _f0_aware_constraints(
                        measured, targets, float(f0_hz), float(policy["rendered_f0_relative_tolerance"])
                    ),
                    "values": temporal,
                })
    summaries = []
    for selected_item in selected:
        rows = [row for row in records if row["candidate_id"] == selected_item["candidate_id"]]
        by_f0 = {}
        for f0_hz in policy["f0_values_hz"]:
            subset = [row for row in rows if row["f0_hz"] == f0_hz]
            by_f0[str(int(f0_hz))] = {
                "engineering_pass_rate": sum(row["engineering_checks"]["passed"] for row in subset) / len(subset),
                "features": {name: _numeric_summary([row["values"].get(name) for row in subset]) for name in BEHAVIOR_FEATURES},
            }
        summaries.append({**selected_item, "conditions": by_f0})
    return {
        "schema_version": "1.0.0",
        "campaign_id": config["campaign_id"],
        "status": "a4-robustness-complete",
        "selection_contract": "anchor plus greedy maximin behavior diversity; no naturalness rank",
        "selected": selected,
        "render_count": len(records),
        "elapsed_sec": time.perf_counter() - started,
        "records": records,
        "candidate_summaries": summaries,
        "formal_aggregate_score": None,
        "perceptual_claim_allowed": False,
    }


def markdown_report(result: dict[str, Any]) -> str:
    lines = [
        "# A4 未使用seed・F0頑健性",
        "",
        f"- 候補数: {len(result['selected'])}",
        f"- 生成数: {result['render_count']}",
        f"- 実行時間: {result['elapsed_sec']:.2f}秒",
        "",
        "| 候補 | 選定理由 | 160 Hz | 220 Hz | 300 Hz |",
        "|---|---|---:|---:|---:|",
    ]
    for item in result["candidate_summaries"]:
        rates = [item["conditions"][f0]["engineering_pass_rate"] for f0 in ("160", "220", "300")]
        lines.append(f"| {item['candidate_id']} | {item['selection_reason']} | {rates[0]:.2f} | {rates[1]:.2f} | {rates[2]:.2f} |")
    lines.extend(["", "通過率は信号・制御の成立だけを示し、母音同一性や人声性を示さない。", ""])
    return "\n".join(lines)
