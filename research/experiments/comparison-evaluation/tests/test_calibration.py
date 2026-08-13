from __future__ import annotations

import sys
import unittest
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SOURCE))

from comparison_eval.calibration import calibrate_perceptual_mapping, validate_perceptual_mapping


class CalibrationTests(unittest.TestCase):
    def test_mapping_recovers_monotonic_relationship_without_activation(self) -> None:
        listening = {"task_aggregates": {f"t{i}": {"naturalness": 1.0 + 4.0 * i / 9.0} for i in range(10)}}
        benchmark = {"results": [{"task": {"task_id": f"t{i}"}, "scorecard": {"categories": {"source_voice_quality": {"target_similarity": 100.0 * i / 9.0, "human_likeness": 100.0 * i / 9.0}}}} for i in range(10)]}
        result = calibrate_perceptual_mapping(listening, benchmark)
        self.assertFalse(result["activated"])
        self.assertEqual(result["task_count"], 10)
        self.assertTrue(any(item["spearman"] > 0.99 for item in result["correlations"]))
        holdout = validate_perceptual_mapping(result, listening, benchmark)
        self.assertTrue(holdout["eligible_for_adoption"])
        self.assertFalse(holdout["activated"])


if __name__ == "__main__":
    unittest.main()
