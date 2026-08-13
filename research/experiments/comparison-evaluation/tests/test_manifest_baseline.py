from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SOURCE))

from comparison_eval.baseline import envelope_score, pair_classes, robust_summary
from comparison_eval.manifest import deterministic_split, load_manifest, validate_manifest


class ManifestBaselineTests(unittest.TestCase):
    def test_group_split_is_deterministic(self) -> None:
        self.assertEqual(deterministic_split("speaker-a"), deterministic_split("speaker-a"))
        self.assertIn(deterministic_split("speaker-a"), {"development", "calibration", "holdout"})

    def test_manifest_detects_source_leakage(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a.wav").touch()
            (root / "b.wav").touch()
            manifest = root / "samples.csv"
            manifest.write_text(
                "sample_id,relative_path,kind,profile,label,speaker_id,source_recording_id,split,license\n"
                "a,a.wav,human,sustained-vowel,a,s1,source,development,internal\n"
                "b,b.wav,human,sustained-vowel,a,s1,source,holdout,internal\n",
                encoding="utf-8",
            )
            errors = validate_manifest(manifest, load_manifest(manifest))
        self.assertTrue(any("leaks" in error for error in errors))

    def test_robust_summary_resists_outlier(self) -> None:
        summary = robust_summary([1.0, 1.1, 0.9, 1.05, 100.0])
        self.assertLess(float(summary["median"]), 1.2)
        score, confidence = envelope_score(1.0, summary)
        self.assertIsNotNone(score)
        self.assertGreater(float(score), 85.0)
        self.assertGreater(confidence, 0.0)

    def test_pair_classes_separate_speaker_and_label(self) -> None:
        records = [
            {"sample_id": "1", "kind": "human", "speaker_id": "a", "label": "a"},
            {"sample_id": "2", "kind": "human", "speaker_id": "a", "label": "i"},
            {"sample_id": "3", "kind": "human", "speaker_id": "b", "label": "a"},
        ]
        classes = pair_classes(records)
        self.assertIn(("1", "2"), classes["same_speaker_different_label"])
        self.assertIn(("1", "3"), classes["different_speaker_same_label"])


if __name__ == "__main__":
    unittest.main()
