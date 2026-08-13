from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import numpy as np

from .extract import extract_file
from .metrics import compare_audio
from .scorecard import add_human_likeness, build_scorecard
from .signal import read_audio, resample, signal_integrity


def load_tasks(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    required = {"task_id", "generated_path", "reference_path", "profile", "label", "reference_split", "variant"}
    missing = required - set(rows[0] if rows else [])
    if missing:
        raise ValueError(f"missing task columns: {', '.join(sorted(missing))}")
    return rows


def run_task(task: dict[str, str], root: Path, segment: str, baseline: dict[str, Any] | None = None, categories: set[str] | None = None, gates_config: dict[str, float] | None = None) -> dict[str, Any]:
    reference_path = (root / task["reference_path"]).resolve()
    generated_path = (root / task["generated_path"]).resolve()
    ref_rate, reference = read_audio(reference_path)
    gen_rate, generated = read_audio(generated_path)
    sample_rate = min(ref_rate, gen_rate)
    reference = resample(reference, ref_rate, sample_rate)
    generated = resample(generated, gen_rate, sample_rate)
    metrics = compare_audio(reference, generated, sample_rate, segment)
    if categories:
        metrics = [metric for metric in metrics if metric.category in categories]
    card = build_scorecard(metrics, task["profile"], reference_path.name, generated_path.name)
    if baseline:
        bundle = extract_file(generated_path, task["task_id"], task["profile"], segment, {"label": task["label"]}).to_dict()
        add_human_likeness(card, bundle, baseline, task["label"])
    integrity = signal_integrity(generated, sample_rate)
    gates = []
    gates_config = gates_config or {}
    if integrity["clipping_ratio"] >= gates_config.get("clipping_ratio_fail", 0.01):
        gates.append("clipping")
    if integrity["silence_ratio"] >= gates_config.get("silence_ratio_fail", 0.99):
        gates.append("silence")
    return {"task": task, "scorecard": card, "signal_integrity": integrity, "gate_failures": gates}


def pareto_front(results: list[dict[str, Any]]) -> list[str]:
    vectors: dict[str, dict[str, float]] = {}
    for result in results:
        values = {name: item["target_similarity"] for name, item in result["scorecard"]["categories"].items() if item.get("target_similarity") is not None}
        vectors[result["task"]["task_id"]] = values
    front = []
    for candidate, values in vectors.items():
        dominated = False
        for other, other_values in vectors.items():
            shared = set(values) & set(other_values)
            if other != candidate and shared and all(other_values[key] >= values[key] for key in shared) and any(other_values[key] > values[key] for key in shared):
                dominated = True
                break
        if not dominated:
            front.append(candidate)
    return front


def summarize_variants(results: list[dict[str, Any]]) -> dict[str, Any]:
    collected: dict[str, dict[str, dict[str, list[float]]]] = {}
    for result in results:
        variant = result["task"].get("variant", "unknown")
        for category, entry in result["scorecard"]["categories"].items():
            for score_type in ("target_similarity", "human_likeness"):
                value = entry.get(score_type)
                if value is not None:
                    collected.setdefault(variant, {}).setdefault(category, {}).setdefault(score_type, []).append(float(value))
    return {
        variant: {
            category: {score_type: {"median": float(np.median(values)), "minimum": min(values), "maximum": max(values), "count": len(values)} for score_type, values in score_types.items()}
            for category, score_types in categories.items()
        }
        for variant, categories in collected.items()
    }


def markdown_report(results: list[dict[str, Any]], pareto: list[str], variant_summary: dict[str, Any] | None = None) -> str:
    categories = sorted({category for result in results for category in result["scorecard"]["categories"]})
    lines = ["# 比較評価ベンチマーク", "", "カテゴリ得点は診断用で、試聴校正前の総合点ではない。", "", "| task | variant | split | gate | " + " | ".join(categories) + " |", "| --- | --- | --- | --- | " + " | ".join("---:" for _ in categories) + " |"]
    for result in results:
        task, card = result["task"], result["scorecard"]
        cells = []
        for category in categories:
            entry = card["categories"].get(category, {})
            target = entry.get("target_similarity")
            human = entry.get("human_likeness")
            cells.append((f"T {target:.1f}" if target is not None else "T -") + (f" / H {human:.1f}" if human is not None else " / H -"))
        lines.append(f"| {task['task_id']} | {task['variant']} | {task['reference_split']} | {', '.join(result['gate_failures']) or 'pass'} | " + " | ".join(cells) + " |")
    lines.extend(["", "## Pareto候補", "", *[f"- {task_id}" for task_id in pareto], "", "改善と悪化がカテゴリ間で併存する場合、その候補を一律に優位とは扱わない。", "", "## 主な方向差", ""])
    for result in results:
        diagnostics = []
        for category, entry in result["scorecard"]["categories"].items():
            for item in entry.get("directional_diagnostics", [])[:1]:
                direction = "高い／遅い" if item["signed_value"] > 0 else "低い／早い"
                diagnostics.append(f"{category}: {item['metric']} {item['signed_value']:+.2f} {item['unit']}（生成側が{direction}）")
        if diagnostics:
            lines.append(f"- {result['task']['task_id']}: " + "; ".join(diagnostics))
    lines.append("")
    if variant_summary:
        lines.extend(["## 方式別中央値", "", "| variant | category | target | human-likeness |", "| --- | --- | ---: | ---: |"])
        for variant, categories_data in variant_summary.items():
            for category, scores in categories_data.items():
                target = scores.get("target_similarity", {}).get("median")
                human = scores.get("human_likeness", {}).get("median")
                lines.append(f"| {variant} | {category} | {target:.1f} | {human:.1f} |" if target is not None and human is not None else f"| {variant} | {category} | {target:.1f} | - |" if target is not None else f"| {variant} | {category} | - | {human:.1f} |")
        lines.append("")
    return "\n".join(lines)


def compare_benchmarks(previous: dict[str, Any], current: dict[str, Any], tolerance: float = 1.0) -> dict[str, Any]:
    old = {item["task"]["task_id"]: item for item in previous.get("results", [])}
    regressions = []
    for result in current.get("results", []):
        task_id = result["task"]["task_id"]
        if task_id not in old:
            continue
        for category, entry in result["scorecard"]["categories"].items():
            before = old[task_id]["scorecard"]["categories"].get(category, {}).get("target_similarity")
            after = entry.get("target_similarity")
            if before is not None and after is not None and after < before - tolerance:
                regressions.append({"task_id": task_id, "category": category, "before": before, "after": after, "delta": after - before})
    return {"regressions": regressions, "passed": not regressions}
