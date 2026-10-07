from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = ROOT.parents[2]
for source in (
    ROOT / "src",
    REPOSITORY_ROOT / "research/experiments/synthetic-vowel-baseline/src",
    REPOSITORY_ROOT / "research/experiments/comparison-evaluation/src",
):
    sys.path.insert(0, str(source))

from autonomous_vowel_search.configuration import validate_campaign, validate_targets
from autonomous_vowel_search.generator_adapter import render_b9, write_render
from autonomous_vowel_search.inventory import build_ledger, validate_ledger
from autonomous_vowel_search.io import read_json
from autonomous_vowel_search.measurement_adapter import evaluate_constraints, measure, measurement_state
from autonomous_vowel_search.reference_evaluation import validate_reference_group
from autonomous_vowel_search.onset import onset_diagnostics, render_gain_onset
from autonomous_vowel_search.search import freeze_settings
from autonomous_vowel_search.robustness import select_diverse_candidates
from autonomous_vowel_search.listening_package import freeze_listening_package


class CoreTests(unittest.TestCase):
    def test_search_settings_are_frozen_unique_and_in_bounds(self) -> None:
        config = read_json(ROOT / "config/search-campaign-a220-v1.json")
        first = freeze_settings(config)
        second = freeze_settings(config)
        self.assertEqual(first, second)
        self.assertEqual(len(first), 64)
        self.assertEqual(len({row["setting_id"] for row in first}), 64)
        self.assertEqual(sum(row["method"] == "structured" for row in first), 32)
        self.assertEqual(sum(row["method"] == "stratified-random" for row in first), 32)
        for row in first:
            for name, (lower, upper) in config["search_axes"].items():
                self.assertGreaterEqual(row["parameters"][name], lower)
                self.assertLessEqual(row["parameters"][name], upper)

    def test_robustness_selection_is_deterministic_and_keeps_anchor(self) -> None:
        result = read_json(ROOT / "results/avs-a220-search-v1/a3-search/evaluation.json")
        first = select_diverse_candidates(result, 8)
        self.assertEqual(first, select_diverse_candidates(result, 8))
        self.assertEqual(len(first), 8)
        self.assertEqual(len({row["candidate_id"] for row in first}), 8)
        self.assertIn("structured-00", {row["candidate_id"] for row in first})

    def test_listening_package_is_deterministic_and_has_hidden_duplicate(self) -> None:
        source = read_json(ROOT / "results/avs-a220-search-v1/a4-robustness/evaluation.json")
        source_dir = ROOT / "results/avs-a220-search-v1/a4-robustness"
        package = freeze_listening_package(source, source_dir)
        self.assertEqual(package, freeze_listening_package(source, source_dir))
        self.assertEqual(package["presentation_count"], 6)
        self.assertEqual(package["status"], "not_queued")
        self.assertEqual(sum(item["duplicate_of"] is not None for item in package["presentations"]), 1)
        self.assertIn("y", package["answer_contract"]["binary"])
        self.assertIn("n", package["answer_contract"]["binary"])

    @classmethod
    def setUpClass(cls) -> None:
        cls.campaign = read_json(ROOT / "config/campaign-a220-v1.json")
        cls.targets = read_json(ROOT / "config/acoustic-targets-v1.json")

    def test_configs_are_valid_and_seed_sets_are_disjoint(self) -> None:
        self.assertEqual(validate_campaign(self.campaign), [])
        self.assertEqual(validate_targets(self.targets), [])

    def test_canonical_b9_hash_and_constraints(self) -> None:
        candidate = render_b9(self.campaign["baseline_parameters"], 401)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "b9.wav"
            digest = write_render(path, candidate)
            self.assertEqual(digest, "7538817f9140c07ced4bccd899d10c542c1b9b69cc8b222b7eb0dce27755a3b7")
            result = measure(path, candidate, "b9")
            self.assertTrue(evaluate_constraints(result, self.targets)["passed"])
            self.assertEqual(result["states"]["f0_hz"], "available")
            self.assertAlmostEqual(result["values"]["f0_hz"], 220.0, delta=4.0)

    def test_different_pilot_seeds_are_not_identical(self) -> None:
        first, second = self.campaign["seed_sets"]["pilot"][:2]
        a = render_b9(self.campaign["baseline_parameters"], first)["audio"]
        b = render_b9(self.campaign["baseline_parameters"], second)["audio"]
        self.assertGreater(float(np.sqrt(np.mean(np.square(a - b)))), 0.0001)

    def test_missing_states_are_not_passes(self) -> None:
        self.assertEqual(measurement_state(None), "unavailable")
        self.assertEqual(measurement_state(float("nan")), "unavailable")
        self.assertEqual(measurement_state(1.0, supported=False), "unsupported")
        self.assertEqual(measurement_state(1.0), "available")

    def test_inventory_contains_required_baselines_and_valid_evidence(self) -> None:
        rows = build_ledger()
        schema = json.loads((ROOT / "config/candidate-ledger-schema-v1.json").read_text(encoding="utf-8"))
        self.assertEqual(validate_ledger(rows, schema), [])
        conditions = {row["condition"] for row in rows}
        self.assertTrue({"B6-tilted-saw-cascade", "B7-tilted-varied-saw-cascade", "B9-corrected-subtle-variation", "B10-corrected-matched-variation", "G40-b9-gain-attack"} <= conditions)
        b9 = next(row for row in rows if row["condition"] == "B9-corrected-subtle-variation")
        self.assertEqual(b9["adoption_status"], "listener-qualified")
        self.assertTrue(b9["engineering_checks"]["hash_verified"])
        self.assertTrue(b9["evidence_files"])

    def test_development_reference_group_excludes_holdout_and_verifies_hashes(self) -> None:
        group = read_json(ROOT / "config/development-reference-group-a220-v1.json")
        self.assertEqual(validate_reference_group(group), [])
        self.assertGreaterEqual(len({item["speaker_id"] for item in group["references"]}), 2)
        self.assertNotIn("holdout", {item["split"] for item in group["references"]})

    def test_onset_adapter_reproduces_g40_and_rise_time_tracks_duration(self) -> None:
        config = read_json(ROOT / "config/onset-campaign-a220-v1.json")
        measurements = []
        with tempfile.TemporaryDirectory() as directory:
            for duration in (0.0, 40.0, 80.0):
                candidate = render_gain_onset(duration, 401)
                path = Path(directory) / f"g{int(duration)}.wav"
                digest = write_render(path, candidate)
                if duration == 40.0:
                    self.assertEqual(digest, config["canonical_regression"]["wav_sha256"])
                measurements.append(onset_diagnostics(candidate["audio"], candidate["sample_rate"], 0.15))
        self.assertLess(measurements[0]["rms_10_to_90_ms"], measurements[1]["rms_10_to_90_ms"])
        self.assertLess(measurements[1]["rms_10_to_90_ms"], measurements[2]["rms_10_to_90_ms"])


if __name__ == "__main__":
    unittest.main()
