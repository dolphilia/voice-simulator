from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from synthetic_vowel_baseline.longitudinal import (  # noqa: E402
    aggregate_runs,
    hours_since_previous,
    summarize_run,
    validate_run_number,
)


class LongitudinalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.spec = {
            "schema_version": "0.1.0", "study_id": "test", "design": "single",
            "planned_runs": 3,
            "advance_gate": {"minimum_passing_runs_per_target": 2, "minimum_duplicate_consistency_rate": 0.9},
            "pairs": [{
                "pair_id": "p", "target": "T", "comparison_axis": "more_human",
                "acceptable_choices": ["T"],
            }],
        }

    def test_run_number_and_interval(self) -> None:
        self.assertEqual(validate_run_number(3, 3), 3)
        with self.assertRaises(ValueError): validate_run_number(0, 3)
        elapsed = hours_since_previous("2026-08-24T00:00:00+00:00", datetime(2026, 8, 25, 1, tzinfo=timezone.utc))
        self.assertEqual(elapsed, 25.0)

    def test_summarize_maps_blinded_sides_and_requires_both_presentations(self) -> None:
        presentations = []
        attempts = {}
        for index, reversed_sides in enumerate((False, True), 1):
            sides = ({"A": {"condition": "C"}, "B": {"condition": "T"}} if not reversed_sides
                     else {"A": {"condition": "T"}, "B": {"condition": "C"}})
            presentations.append({"presentation_id": f"W0{index}", "pair_id": "p", **sides})
            target_side = "A" if reversed_sides else "B"
            attempts[f"W0{index}"] = [{
                "answers": {"more_human": target_side, "vowel_identity": {"A": True, "B": True},
                            "human_voice_identity": {"A": True, "B": True}},
                "artifact": {"A": False, "B": False}, "interference": False,
            }]
        result = summarize_run(1, self.spec, {"presentations": presentations},
                               {"completed_at": "2026-08-25T00:00:00+00:00", "attempts": attempts}, 1.0)
        self.assertTrue(result["pairs"]["p"]["passed"])
        self.assertEqual(result["pairs"]["p"]["target_wins"], 2)

    def test_aggregate_does_not_treat_presentations_as_listeners(self) -> None:
        runs = []
        for run, passed in ((1, True), (2, True), (3, False)):
            runs.append({"run": run, "duplicate_consistency_rate": 1.0,
                         "pairs": {"p": {"passed": passed, "target_wins": 2 if passed else 0}}})
        result = aggregate_runs(self.spec, runs)
        self.assertTrue(result["advance_gate_passed"])
        self.assertEqual(result["listener_count"], 1)
        self.assertEqual(result["pairs"]["p"]["passing_runs"], 2)


if __name__ == "__main__":
    unittest.main()
