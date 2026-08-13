from __future__ import annotations

import itertools
import math
from collections import defaultdict
from typing import Any

import numpy as np
from scipy import stats


def robust_summary(values: list[float]) -> dict[str, float | int | None]:
    finite = np.asarray([value for value in values if math.isfinite(value)], dtype=np.float64)
    if finite.size == 0:
        return {"count": 0, "median": None, "mad": None, "p05": None, "p25": None, "p75": None, "p95": None}
    median = float(np.median(finite))
    return {
        "count": int(finite.size),
        "median": median,
        "mad": float(np.median(np.abs(finite - median))),
        "p05": float(np.percentile(finite, 5)),
        "p25": float(np.percentile(finite, 25)),
        "p75": float(np.percentile(finite, 75)),
        "p95": float(np.percentile(finite, 95)),
    }


def human_feature_baseline(features: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[tuple[str, str], dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for bundle in features:
        metadata = bundle.get("metadata", {})
        if metadata.get("kind") != "human":
            continue
        key = (bundle.get("profile", "unknown"), metadata.get("label", "unknown"))
        for name, value in bundle.get("scalar", {}).items():
            if isinstance(value, (int, float)) and math.isfinite(value):
                grouped[key][name].append(float(value))
        for name, estimate in bundle.get("estimates", {}).items():
            value = estimate.get("value")
            if isinstance(value, (int, float)) and math.isfinite(value):
                grouped[key][name].append(float(value))
    return {
        f"{profile}:{label}": {name: robust_summary(values) for name, values in metrics.items()}
        for (profile, label), metrics in sorted(grouped.items())
    }


def pair_classes(records: list[dict[str, Any]]) -> dict[str, list[tuple[str, str]]]:
    classes: dict[str, list[tuple[str, str]]] = defaultdict(list)
    human = [record for record in records if record.get("kind") == "human"]
    for first, second in itertools.combinations(human, 2):
        same_speaker = first.get("speaker_id") == second.get("speaker_id")
        same_label = first.get("label") == second.get("label")
        name = ("same_speaker" if same_speaker else "different_speaker") + "_" + ("same_label" if same_label else "different_label")
        classes[name].append((first["sample_id"], second["sample_id"]))
    return dict(classes)


def human_pair_baseline(features: list[dict[str, Any]]) -> dict[str, Any]:
    human = [item for item in features if item.get("metadata", {}).get("kind") == "human"]
    values: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    observations: list[dict[str, Any]] = []
    for first, second in itertools.combinations(human, 2):
        a, b = first.get("metadata", {}), second.get("metadata", {})
        if first.get("profile") != second.get("profile"):
            continue
        pair_class = ("same_speaker" if a.get("speaker_id") == b.get("speaker_id") else "different_speaker") + "_" + ("same_label" if a.get("label") == b.get("label") else "different_label")
        row: dict[str, Any] = {"pair_class": pair_class, "first": first["sample_id"], "second": second["sample_id"]}
        for name in set(first.get("scalar", {})) & set(second.get("scalar", {})):
            left, right = first["scalar"][name], second["scalar"][name]
            if isinstance(left, (int, float)) and isinstance(right, (int, float)) and math.isfinite(left) and math.isfinite(right):
                delta = abs(float(left) - float(right))
                values[pair_class][name].append(delta)
                row[name] = delta
        observations.append(row)
    summaries = {pair_class: {name: robust_summary(metric_values) for name, metric_values in metrics.items()} for pair_class, metrics in values.items()}
    same_label = defaultdict(list)
    different_label = defaultdict(list)
    for row in observations:
        destination = same_label if row["pair_class"].endswith("same_label") else different_label
        for name, value in row.items():
            if name not in {"pair_class", "first", "second"}:
                destination[name].append(value)
    separation: dict[str, Any] = {}
    for name in sorted(set(same_label) & set(different_label)):
        same, different = np.asarray(same_label[name]), np.asarray(different_label[name])
        if same.size and different.size:
            probability = float(np.mean(different[:, None] > same[None, :]))
            separation[name] = {"probability_different_is_farther": probability, "same_label_median": float(np.median(same)), "different_label_median": float(np.median(different))}
    numeric_names = sorted(set.intersection(*[set(row) for row in observations])) if observations else []
    numeric_names = [name for name in numeric_names if name not in {"pair_class", "first", "second"}]
    correlations: list[dict[str, Any]] = []
    for first_name, second_name in itertools.combinations(numeric_names, 2):
        x = [row[first_name] for row in observations]
        y = [row[second_name] for row in observations]
        coefficient = float(stats.spearmanr(x, y).statistic) if len(x) >= 3 and np.std(x) > 0 and np.std(y) > 0 else float("nan")
        if math.isfinite(coefficient) and abs(coefficient) >= 0.8:
            correlations.append({"first": first_name, "second": second_name, "spearman": coefficient})
    return {"distributions": summaries, "label_separation": separation, "strong_correlations": correlations}


def envelope_score(value: float | None, summary: dict[str, Any], z_cap: float = 6.0) -> tuple[float | None, float]:
    if value is None or summary.get("count", 0) < 2 or summary.get("median") is None:
        return None, 0.0
    scale = max(float(summary.get("mad") or 0.0) * 1.4826, 1e-9)
    z = min(z_cap, abs(value - float(summary["median"])) / scale)
    return max(0.0, 100.0 * (1.0 - z / z_cap)), min(1.0, summary["count"] / 20.0)
