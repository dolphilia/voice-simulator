from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

SOURCE = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SOURCE))

from comparison_eval.features import estimate_formants, spectral_summary
from comparison_eval.fixtures import add_noise_at_snr, apply_spectral_tilt, delay, seeded_noise, synthetic_vowel, time_stretch
from comparison_eval.metrics import compare_audio


def values(metrics):
    return {metric.name: metric.value for metric in metrics}


class MetricBehaviorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.reference = synthetic_vowel(140.0, 0.65, 48000)

    def test_identity_is_zero_or_perfect(self) -> None:
        result = values(compare_audio(self.reference, self.reference, 48000))
        self.assertLess(result["log_mel_rmse_db"], 1e-9)
        self.assertLess(result["multi_resolution_log_stft"], 1e-9)
        self.assertAlmostEqual(result["waveform_correlation"], 1.0, places=9)

    def test_gain_is_removed_from_timbre_but_reported(self) -> None:
        metrics = compare_audio(self.reference, self.reference * 0.35, 48000)
        result = values(metrics)
        self.assertLess(result["log_mel_rmse_db"], 1e-9)
        self.assertGreater(result["level_delta_db"], 8.0)
        level = next(metric for metric in metrics if metric.name == "level_delta_db")
        self.assertLess(level.signed_value, 0.0)

    def test_delay_is_aligned_for_timbre(self) -> None:
        result = values(compare_audio(self.reference, delay(self.reference, 720), 48000, "whole"))
        self.assertGreater(result["onset_delta_ms"], 10.0)
        self.assertLess(result["log_mel_rmse_db"], 2.0)

    def test_noise_increases_spectral_distance(self) -> None:
        clean = values(compare_audio(self.reference, self.reference, 48000))
        noisy = values(compare_audio(self.reference, add_noise_at_snr(self.reference, 8.0), 48000))
        self.assertGreater(noisy["log_mel_rmse_db"], clean["log_mel_rmse_db"] + 5.0)
        self.assertGreater(noisy["spectral_flatness_delta"], clean["spectral_flatness_delta"])

    def test_polarity_is_spectral_invariant(self) -> None:
        result = values(compare_audio(self.reference, -self.reference, 48000))
        self.assertLess(result["log_mel_rmse_db"], 1e-9)
        self.assertAlmostEqual(result["waveform_correlation"], -1.0, places=8)

    def test_time_stretch_changes_duration_monotonically(self) -> None:
        short = values(compare_audio(self.reference, time_stretch(self.reference, 1.1), 48000, "whole"))
        long = values(compare_audio(self.reference, time_stretch(self.reference, 1.3), 48000, "whole"))
        self.assertGreater(long["duration_delta_ms"], short["duration_delta_ms"])

    def test_known_formant_shift_has_expected_direction(self) -> None:
        low = synthetic_vowel(140.0, 0.7, 48000, ((500.0, 80.0), (1000.0, 100.0), (2400.0, 180.0)))
        high = synthetic_vowel(140.0, 0.7, 48000, ((700.0, 80.0), (1300.0, 100.0), (2600.0, 180.0)))
        low_formants, _, _, _ = estimate_formants(low, 48000)
        high_formants, _, _, _ = estimate_formants(high, 48000)
        self.assertGreater(high_formants[0], low_formants[0])
        self.assertGreater(high_formants[1], low_formants[1])
        metrics = compare_audio(low, high, 48000)
        self.assertGreater(next(metric for metric in metrics if metric.name == "f1_delta_hz").signed_value, 0.0)

    def test_spectral_tilt_changes_slope_monotonically(self) -> None:
        darker = apply_spectral_tilt(self.reference, 48000, -4.0)
        brighter = apply_spectral_tilt(self.reference, 48000, 4.0)
        self.assertLess(spectral_summary(darker, 48000)["spectral_slope_db_khz"], spectral_summary(brighter, 48000)["spectral_slope_db_khz"])

    def test_band_noise_centroid_is_inside_known_band(self) -> None:
        noise = seeded_noise(0.5, 48000, seed=7, low_hz=3000.0, high_hz=9000.0)
        centroid = spectral_summary(noise, 48000)["spectral_centroid_hz"]
        self.assertGreater(centroid, 3000.0)
        self.assertLess(centroid, 9000.0)


if __name__ == "__main__":
    unittest.main()
