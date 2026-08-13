from __future__ import annotations

import csv
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "research/scripts"))

import audio_utils


class LegacyRegressionTests(unittest.TestCase):
    def test_saved_self_comparison_contract(self) -> None:
        path = ROOT / "research/data/processed/analysis/waveform-comparison-batch-summary-selftest.csv"
        with path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        self.assertGreaterEqual(len(rows), 2)
        for row in rows:
            self.assertEqual(float(row["waveform_rmse_median"]), 0.0)
            self.assertEqual(float(row["normalized_cross_correlation_median"]), 1.0)
            self.assertEqual(float(row["log_spectral_distance_db_median"]), 0.0)

    def test_legacy_identity_functions_remain_exact(self) -> None:
        import numpy as np
        audio = np.sin(np.linspace(0.0, 20.0, 2000))
        self.assertEqual(audio_utils.waveform_rmse(audio, audio), 0.0)
        self.assertAlmostEqual(audio_utils.normalized_cross_correlation(audio, audio), 1.0)


if __name__ == "__main__":
    unittest.main()
