from __future__ import annotations

from typing import Any


def validate_campaign(campaign: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if campaign.get("schema_version") != "1.0.0":
        errors.append("unsupported campaign schema")
    axes = campaign.get("parameter_axes", {})
    baseline = campaign.get("baseline_parameters", {})
    for name, axis in axes.items():
        if not axis.get("provenance"):
            errors.append(f"{name}: provenance is required")
        if axis.get("status", "").startswith("pilot"):
            bounds = axis.get("bounds", [])
            values = axis.get("pilot_values", [])
            if len(bounds) != 2 or not values:
                errors.append(f"{name}: bounds and pilot_values are required")
                continue
            if name not in baseline or not bounds[0] <= baseline[name] <= bounds[1]:
                errors.append(f"{name}: baseline is outside bounds")
            if any(value < bounds[0] or value > bounds[1] for value in values):
                errors.append(f"{name}: pilot value is outside bounds")
            if baseline.get(name) not in values:
                errors.append(f"{name}: pilot values must include baseline")
    sets = campaign.get("seed_sets", {})
    named = [set(values) for values in sets.values()]
    forbidden = set(campaign.get("known_forbidden_seed_offsets", []))
    for index, left in enumerate(named):
        if left & forbidden:
            errors.append("seed set overlaps known used seeds")
        for right in named[index + 1:]:
            if left & right:
                errors.append("seed sets overlap")
    budget = campaign.get("formal_search", {})
    if budget.get("structured_settings", 0) + budget.get("stratified_random_settings", 0) != budget.get("maximum_settings"):
        errors.append("formal search allocation does not match maximum settings")
    expected = campaign.get("robustness_budget", {}).get("maximum_candidates", 0) * len(sets.get("robustness", [])) * len(campaign.get("robustness_budget", {}).get("f0_values_hz", []))
    if expected != campaign.get("robustness_budget", {}).get("maximum_renders"):
        errors.append("robustness budget arithmetic is inconsistent")
    return errors


def validate_targets(targets: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    seen: set[str] = set()
    required = {"target_id", "feature", "unit", "target_interval", "role", "reference_group_id", "provenance", "estimator", "uncertainty", "missing_policy"}
    for index, target in enumerate(targets.get("targets", [])):
        missing = required - set(target)
        if missing:
            errors.append(f"target {index}: missing {', '.join(sorted(missing))}")
            continue
        if target["target_id"] in seen:
            errors.append(f"duplicate target id: {target['target_id']}")
        seen.add(target["target_id"])
        if target["role"] not in {"constraint", "diagnostic"}:
            errors.append(f"{target['target_id']}: invalid role")
        interval = target["target_interval"]
        if len(interval) != 2 or interval[0] > interval[1]:
            errors.append(f"{target['target_id']}: invalid interval")
    return errors

