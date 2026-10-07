from __future__ import annotations

import math
from numbers import Real
from pathlib import Path
from typing import Any

import numpy as np

from comparison_eval.extract import extract_file
from comparison_eval.signal import signal_integrity

from . import MEASUREMENT_ADAPTER_VERSION


def measurement_state(value: float | None, supported: bool = True) -> str:
    if not supported:
        return "unsupported"
    if value is None or not math.isfinite(float(value)):
        return "unavailable"
    return "available"


def measure(path: Path, candidate: dict[str, Any], sample_id: str) -> dict[str, Any]:
    audio = np.asarray(candidate["audio"], dtype=np.float64)
    sample_rate = int(candidate["sample_rate"])
    bundle = extract_file(path, sample_id, "sustained-vowel", "stable", {
        "kind": "generated",
        "label": "あ",
        "generator_adapter_version": candidate["adapter_version"],
    }).to_dict()
    f0_estimate = bundle["estimates"]["f0_hz"]
    integrity = signal_integrity(audio, sample_rate)
    endpoint = max(abs(float(audio[0])), abs(float(audio[-1]))) if audio.size else None
    numeric_diagnostics = {
        key: float(value)
        for key, value in candidate.get("diagnostics", {}).items()
        if isinstance(value, Real)
    }
    values = {
        **bundle["scalar"],
        "f0_hz": f0_estimate["value"],
        "f0_confidence": f0_estimate["confidence"],
        "absolute_dc_offset": abs(float(integrity["dc_offset"])),
        "maximum_endpoint_absolute": endpoint,
        **numeric_diagnostics,
    }
    return {
        "measurement_adapter_version": MEASUREMENT_ADAPTER_VERSION,
        "feature_bundle": bundle,
        "generator_diagnostics": candidate.get("diagnostics", {}),
        "values": values,
        "states": {key: measurement_state(value) for key, value in values.items()},
    }


def evaluate_constraints(measurement: dict[str, Any], targets: dict[str, Any]) -> dict[str, Any]:
    checks = []
    for target in targets["targets"]:
        if target["role"] != "constraint":
            continue
        feature = target["feature"]
        value = measurement["values"].get(feature)
        state = measurement_state(value)
        lower, upper = (float(item) for item in target["target_interval"])
        passed = state == "available" and lower <= float(value) <= upper
        checks.append({"target_id": target["target_id"], "feature": feature, "value": value, "state": state, "passed": passed})
    return {"passed": all(item["passed"] for item in checks), "checks": checks}
