from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from .generator_adapter import render_b9, write_render
from .measurement_adapter import evaluate_constraints, measure, measurement_state


def run_smoke(
    output_dir: Path,
    campaign: dict[str, Any],
    targets: dict[str, Any],
    suite: dict[str, Any],
) -> dict[str, Any]:
    parameters = campaign["baseline_parameters"]
    canonical = render_b9(parameters, 401)
    canonical_path = output_dir / "audio/b9-canonical.wav"
    digest = write_render(canonical_path, canonical)
    measurement = measure(canonical_path, canonical, "b9-canonical")
    constraints = evaluate_constraints(measurement, targets)
    pilot = campaign["seed_sets"]["pilot"]
    variants = [render_b9(parameters, int(seed)) for seed in pilot[:2]]
    difference = float(np.sqrt(np.mean(np.square(variants[0]["audio"] - variants[1]["audio"]))))
    checks = [
        {
            "check": "canonical-b9-sha256",
            "passed": digest == suite["known_b9_sha256"],
            "expected": suite["known_b9_sha256"],
            "actual": digest,
        },
        {"check": "canonical-engineering-constraints", "passed": constraints["passed"], "details": constraints["checks"]},
        {
            "check": "different-seeds-are-distinct",
            "passed": difference >= float(suite["minimum_distinct_waveform_rms"]),
            "rms_difference": difference,
        },
        {
            "check": "missing-state-semantics",
            "passed": measurement_state(None) == "unavailable" and measurement_state(1.0, supported=False) == "unsupported",
            "unavailable": measurement_state(None),
            "unsupported": measurement_state(1.0, supported=False),
        },
    ]
    return {
        "schema_version": "1.0.0",
        "suite_id": suite["suite_id"],
        "passed": all(check["passed"] for check in checks),
        "checks": checks,
        "independent_holdout": False,
        "interpretation": "engineering regression only; not perceptual evidence",
    }

