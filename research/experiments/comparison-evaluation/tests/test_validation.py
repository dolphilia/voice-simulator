from __future__ import annotations

import sys
import unittest
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SOURCE))

from comparison_eval.validation import estimation_failure_report, leave_one_speaker_out


def bundle(speaker: str, label: str, base: float, failed: bool = False):
    return {"sample_id": f"{speaker}-{label}", "profile": "sustained-vowel", "scalar": {"f1_hz": base, "f2_hz": base * 2, "f3_hz": base * 3, "spectral_slope_db_khz": base / 100, "spectral_centroid_hz": base * 4}, "estimates": {"f0_hz": {"value": None if failed else 120.0}, "formants": {"confidence": 2 / 3 if failed else 1.0}}, "metadata": {"kind": "human", "speaker_id": speaker, "label": label, "validation": {"valid": True}}}


class ValidationTests(unittest.TestCase):
    def test_loso_uses_unseen_speaker(self) -> None:
        labels = {"あ": 100.0, "い": 200.0, "う": 300.0, "え": 400.0, "お": 500.0}
        features = [bundle(speaker, label, base + offset) for speaker, offset in (("s1", 0), ("s2", 2), ("s3", -2)) for label, base in labels.items()]
        result = leave_one_speaker_out(features)
        self.assertEqual(result["speaker_count"], 3)
        self.assertEqual(result["accuracy"], 1.0)

    def test_failure_rates_are_explicit(self) -> None:
        report = estimation_failure_report([bundle("s1", "あ", 100), bundle("s1", "い", 200, True)])
        self.assertEqual(report["overall"]["f0_failure_rate"], 0.5)
        self.assertEqual(report["overall"]["formant_incomplete_rate"], 0.5)


if __name__ == "__main__":
    unittest.main()
