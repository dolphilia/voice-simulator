from __future__ import annotations

import math
from typing import Any

import numpy as np
from scipy import stats


def calibrate_perceptual_mapping(listening: dict[str, Any], benchmark: dict[str, Any], minimum_pairs: int = 4) -> dict[str, Any]:
    perceptual = listening.get("task_aggregates", {})
    automatic: dict[str, dict[str, dict[str, float]]] = {}
    for result in benchmark.get("results", []):
        task_id = result["task"]["task_id"]
        automatic[task_id] = {}
        for category, entry in result["scorecard"]["categories"].items():
            automatic[task_id][category] = {name: value for name, value in (("target_similarity", entry.get("target_similarity")), ("human_likeness", entry.get("human_likeness"))) if value is not None}
    task_ids = sorted(set(perceptual) & set(automatic))
    axes = sorted({axis for task_id in task_ids for axis in perceptual[task_id]})
    categories = sorted({category for task_id in task_ids for category in automatic[task_id]})
    correlations = []
    axis_diagnostics = {}
    for axis in axes:
        axis_values = [float(perceptual[task_id][axis]) for task_id in task_ids if axis in perceptual[task_id]]
        axis_diagnostics[axis] = {"count": len(axis_values), "unique_values": len(set(axis_values)), "minimum": min(axis_values) if axis_values else None, "maximum": max(axis_values) if axis_values else None}
        for category in categories:
            for score_type in ("target_similarity", "human_likeness"):
                pairs = [(float(perceptual[task_id][axis]), float(automatic[task_id][category][score_type])) for task_id in task_ids if axis in perceptual[task_id] and category in automatic[task_id] and score_type in automatic[task_id][category]]
                if len(pairs) < minimum_pairs:
                    continue
                x, y = zip(*pairs, strict=True)
                if np.std(x) == 0 or np.std(y) == 0:
                    continue
                result = stats.spearmanr(x, y)
                coefficient, p_value = float(result.statistic), float(result.pvalue)
                if math.isfinite(coefficient):
                    correlations.append({"perceptual_axis": axis, "category": category, "score_type": score_type, "spearman": coefficient, "p_value": p_value, "pair_count": len(pairs)})
    recommendations = {}
    weights = {}
    for axis in axes:
        candidates = [
            item for item in correlations
            if item["perceptual_axis"] == axis
            and item["spearman"] >= 0.3
            and item["p_value"] <= 0.1
            and item["pair_count"] >= max(8, minimum_pairs)
            and axis_diagnostics[axis]["unique_values"] >= 3
        ]
        candidates.sort(key=lambda item: (item["spearman"], -item["p_value"]), reverse=True)
        recommendations[axis] = candidates[:3]
        selected = candidates[:3]
        total = sum(item["spearman"] for item in selected)
        weights[axis] = [
            {"category": item["category"], "score_type": item["score_type"], "weight": item["spearman"] / total, "calibration_spearman": item["spearman"]}
            for item in selected
        ] if total > 0 else []
    return {
        "status": "provisional" if any(weights.values()) else "insufficient-variation",
        "activated": False,
        "task_count": len(task_ids),
        "correlations": correlations,
        "axis_diagnostics": axis_diagnostics,
        "recommended_components": recommendations,
        "provisional_weights": weights,
        "constraints": [
            "独立したholdout試聴結果なしに重みを有効化しない。",
            "自然さ、音素同一性、参照類似性を別の目的として維持する。",
            "総合判断を校正した後もカテゴリ別スコアカードを維持する。",
        ],
    }


def validate_perceptual_mapping(calibration: dict[str, Any], listening: dict[str, Any], benchmark: dict[str, Any], minimum_pairs: int = 4) -> dict[str, Any]:
    human = listening.get("task_aggregates", {})
    cards = {result["task"]["task_id"]: result["scorecard"]["categories"] for result in benchmark.get("results", [])}
    results = {}
    for axis, components in calibration.get("provisional_weights", {}).items():
        pairs = []
        explanations = []
        for task_id in sorted(set(human) & set(cards)):
            if axis not in human[task_id]:
                continue
            available = []
            for component in components:
                value = cards[task_id].get(component["category"], {}).get(component["score_type"])
                if value is not None:
                    available.append((float(value), float(component["weight"]), component))
            weight_sum = sum(weight for _, weight, _ in available)
            if not available or weight_sum <= 0:
                continue
            prediction = sum(value * weight for value, weight, _ in available) / weight_sum
            pairs.append((float(human[task_id][axis]), prediction))
            explanations.append({"task_id": task_id, "human": float(human[task_id][axis]), "predicted": prediction, "components": [item for _, _, item in available]})
        coefficient = None
        absolute_mae = None
        if len(pairs) >= minimum_pairs and np.std([pair[0] for pair in pairs]) > 0 and np.std([pair[1] for pair in pairs]) > 0:
            coefficient = float(stats.spearmanr([pair[0] for pair in pairs], [pair[1] for pair in pairs]).statistic)
        if pairs:
            absolute_mae = float(np.mean([abs(human_value - (1.0 + 4.0 * predicted / 100.0)) for human_value, predicted in pairs]))
        modeled = bool(components)
        passed = modeled and coefficient is not None and coefficient >= 0.3 and absolute_mae is not None and absolute_mae <= 1.0
        results[axis] = {"modeled": modeled, "pair_count": len(pairs), "human_unique_values": len({pair[0] for pair in pairs}), "holdout_spearman": coefficient, "absolute_mae_1_to_5": absolute_mae, "acceptance": {"minimum_spearman": 0.3, "maximum_mae": 1.0}, "passed": passed, "explanations": explanations}
    modeled_results = [item for item in results.values() if item["modeled"]]
    eligible = bool(modeled_results) and all(item["passed"] for item in modeled_results)
    return {"status": "holdout-validated" if eligible else "holdout-not-validated", "eligible_for_adoption": eligible, "activated": False, "axes": results, "note": "採用にはユーザー判断と評価バージョン更新が必要。"}
