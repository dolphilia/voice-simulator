from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from synthetic_vowel_baseline.generalization_evaluation import (  # noqa: E402
    summarize_f0_listening,
    summarize_gain_scaling_listening,
    summarize_vowel_listening,
)


class F0GeneralizationEvaluationTests(unittest.TestCase):
    def test_both_pitches_and_duplicates_must_pass(self) -> None:
        pairs = []
        presentations = []
        attempts = {}
        for pair_index, f0 in enumerate((160, 300), 1):
            sustain, onset = f"F{f0}-B9-sustain", f"F{f0}-G40-onset"
            pair_id = f"f{f0}-b9-vs-g40"
            pairs.append({
                "pair_id": pair_id, "f0_hz": float(f0), "sustain": sustain, "onset": onset,
                "acceptable_onset_choices": [onset, "SAME"],
            })
            for duplicate in range(2):
                presentation_id = f"W{pair_index}{duplicate}"
                reversed_sides = duplicate == 1
                sides = ({"A": {"condition": sustain}, "B": {"condition": onset}} if not reversed_sides
                         else {"A": {"condition": onset}, "B": {"condition": sustain}})
                presentations.append({"presentation_id": presentation_id, "pair_id": pair_id, **sides})
                onset_side = "A" if reversed_sides else "B"
                attempts[presentation_id] = [{
                    "answers": {
                        "more_natural_onset": onset_side,
                        "vowel_identity": {"A": True, "B": True},
                        "human_voice_identity": {"A": True, "B": True},
                    },
                    "artifact": {"A": False, "B": False}, "interference": False,
                }]
        spec = {"schema_version": "0.1.0", "study_id": "f0", "pairs": pairs}
        result = summarize_f0_listening(
            spec, {"presentations": presentations},
            {"completed_at": "2026-08-26T00:00:00+00:00", "attempts": attempts}, 1.0,
        )
        self.assertTrue(result["all_tested_pitches_passed"])
        self.assertEqual([item["onset_wins"] for item in result["pitches"]], [2, 2])
        attempts["W20"][0]["answers"]["human_voice_identity"]["A"] = False
        failed = summarize_f0_listening(
            spec, {"presentations": presentations},
            {"completed_at": "2026-08-26T00:00:00+00:00", "attempts": attempts}, 0.9,
        )
        self.assertFalse(failed["all_tested_pitches_passed"])

    def test_vowel_summary_accepts_same_but_requires_identity(self) -> None:
        spec = {
            "schema_version": "0.1.0", "study_id": "vowels",
            "pairs": [{"pair_id": "vi", "vowel": "i", "sustain": "IS", "onset": "IO"}],
        }
        presentations = [
            {"presentation_id": "W1", "pair_id": "vi", "A": {"condition": "IS"}, "B": {"condition": "IO"}},
            {"presentation_id": "W2", "pair_id": "vi", "A": {"condition": "IO"}, "B": {"condition": "IS"}},
        ]
        attempts = {
            "W1": [{"answers": {"more_natural_onset": "SAME", "vowel_identity": {"A": True, "B": True}, "human_voice_identity": {"A": True, "B": True}}, "artifact": {"A": False, "B": False}, "interference": False}],
            "W2": [{"answers": {"more_natural_onset": "A", "vowel_identity": {"A": True, "B": True}, "human_voice_identity": {"A": True, "B": True}}, "artifact": {"A": False, "B": False}, "interference": False}],
        }
        result = summarize_vowel_listening(spec, {"presentations": presentations}, {"attempts": attempts}, 1.0)
        self.assertTrue(result["all_tested_vowels_passed"])
        attempts["W2"][0]["answers"]["vowel_identity"]["A"] = False
        failed = summarize_vowel_listening(spec, {"presentations": presentations}, {"attempts": attempts}, 0.8)
        self.assertFalse(failed["all_tested_vowels_passed"])

    def test_gain_scaling_selection_is_preregistered(self) -> None:
        pairs = []
        presentations = []
        attempts = {}
        for pair_index, f0 in enumerate((160, 300), 1):
            fixed, cycle = f"A{f0}F", f"A{f0}C"
            pair_id = f"p{f0}"
            pairs.append({"pair_id": pair_id, "f0_hz": float(f0), "fixed": fixed, "cycle": cycle})
            for duplicate in range(2):
                pid = f"W{pair_index}{duplicate}"
                sides = {"A": {"condition": fixed}, "B": {"condition": cycle}}
                presentations.append({"presentation_id": pid, "pair_id": pair_id, **sides})
                attempts[pid] = [{
                    "answers": {"more_natural_onset": "B", "vowel_identity": {"A": True, "B": True}, "human_voice_identity": {"A": True, "B": True}},
                    "artifact": {"A": False, "B": False}, "interference": False,
                }]
        spec = {"schema_version": "0.1.0", "study_id": "scaling", "pairs": pairs}
        cycle = summarize_gain_scaling_listening(spec, {"presentations": presentations}, {"attempts": attempts}, 1.0)
        self.assertTrue(cycle["decision_valid"])
        self.assertEqual(cycle["selected_rule"], "cycle")
        attempts["W20"][0]["answers"]["more_natural_onset"] = "A"
        attempts["W21"][0]["answers"]["more_natural_onset"] = "A"
        split = summarize_gain_scaling_listening(spec, {"presentations": presentations}, {"attempts": attempts}, 1.0)
        self.assertEqual(split["selected_rule"], "pitch-dependent")
        attempts["W11"][0]["answers"]["more_natural_onset"] = "SAME"
        inconsistent = summarize_gain_scaling_listening(spec, {"presentations": presentations}, {"attempts": attempts}, 0.8)
        self.assertFalse(inconsistent["decision_valid"])
        self.assertEqual(inconsistent["selected_rule"], "inconclusive")


if __name__ == "__main__":
    unittest.main()
