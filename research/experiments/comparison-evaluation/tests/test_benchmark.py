from __future__ import annotations

import sys
import unittest
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SOURCE))

from comparison_eval.benchmark import compare_benchmarks, pareto_front, summarize_variants


def result(task_id, variant, spectral, resonance):
    return {"task": {"task_id": task_id, "variant": variant}, "scorecard": {"categories": {"spectral_timbre": {"target_similarity": spectral, "human_likeness": spectral}, "resonance": {"target_similarity": resonance, "human_likeness": resonance}}}}


class BenchmarkTests(unittest.TestCase):
    def test_pareto_keeps_tradeoffs_and_removes_dominated(self) -> None:
        results = [result("a", "x", 80, 60), result("b", "y", 60, 80), result("c", "z", 50, 50)]
        self.assertEqual(set(pareto_front(results)), {"a", "b"})

    def test_diff_returns_category_regression(self) -> None:
        previous = {"results": [result("a", "x", 80, 60)]}
        current = {"results": [result("a", "x", 75, 61)]}
        diff = compare_benchmarks(previous, current, tolerance=1.0)
        self.assertFalse(diff["passed"])
        self.assertEqual(diff["regressions"][0]["category"], "spectral_timbre")

    def test_variant_summary_uses_median(self) -> None:
        summary = summarize_variants([result("a", "x", 20, 40), result("b", "x", 80, 60)])
        self.assertEqual(summary["x"]["spectral_timbre"]["target_similarity"]["median"], 50.0)


if __name__ == "__main__":
    unittest.main()
