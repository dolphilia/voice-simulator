from __future__ import annotations

from typing import Any


def apply_gate(item: dict[str, Any], gates: dict[str, float]) -> tuple[bool, list[str]]:
    integrity = item["integrity"]
    failures: list[str] = []
    if integrity["clipping_ratio"] > gates["maximum_clipping_ratio"]:
        failures.append("clipping")
    if integrity["peak_dbfs"] > gates["maximum_peak_dbfs"] + 1e-6:
        failures.append("peak")
    if abs(integrity["dc_offset"]) > gates["maximum_dc_offset"]:
        failures.append("dc")
    if integrity["duration_sec"] < gates["minimum_duration_sec"]:
        failures.append("too_short")
    if integrity["duration_sec"] > gates["maximum_duration_sec"]:
        failures.append("too_long")
    if float(item.get("seam_jump_ratio", 0.0)) > gates["maximum_seam_jump_ratio"]:
        failures.append("splice")
    return not failures, failures

