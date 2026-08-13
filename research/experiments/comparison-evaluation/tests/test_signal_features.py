from __future__ import annotations

import sys
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
from scipy.io import wavfile

SOURCE = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SOURCE))

from comparison_eval.features import estimate_f0_frame, f0_contour, f0_contour_metrics
from comparison_eval.fixtures import harmonic_source, synthetic_vowel
from comparison_eval.signal import read_audio, resample, validate_audio


class SignalFeatureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.expected = json.loads((Path(__file__).resolve().parents[1] / "fixtures/expected/analytic.json").read_text(encoding="utf-8"))

    def test_integer_stereo_is_scaled_before_mixing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "stereo.wav"
            wavfile.write(path, 16000, np.full((1000, 2), 16384, dtype=np.int16))
            sample_rate, audio = read_audio(path)
        self.assertEqual(sample_rate, 16000)
        self.assertAlmostEqual(float(np.mean(audio)), 0.5, places=3)

    def test_f0_estimator_recovers_known_pitch(self) -> None:
        target = self.expected["f0"]["target_hz"]
        audio = harmonic_source(target, 0.15, 48000)
        estimate = estimate_f0_frame(audio, 48000)
        self.assertIsNotNone(estimate.value)
        self.assertLess(abs(float(estimate.value) - target), self.expected["f0"]["absolute_tolerance_hz"])
        self.assertGreater(estimate.confidence, self.expected["f0"]["minimum_confidence"])

    def test_f0_contour_detects_pitch_change(self) -> None:
        reference = synthetic_vowel(130.0, 0.8, 48000)
        generated = synthetic_vowel(156.0, 0.8, 48000)
        _, ref_f0, _ = f0_contour(reference, 48000)
        _, gen_f0, _ = f0_contour(generated, 48000)
        metrics = f0_contour_metrics(ref_f0, gen_f0)
        expected = 1200.0 * np.log2(156.0 / 130.0)
        self.assertAlmostEqual(metrics["f0_contour_rmse_cents"], expected, delta=15.0)

    def test_resampling_preserves_duration(self) -> None:
        audio = harmonic_source(120.0, 0.5, 48000)
        downsampled = resample(audio, 48000, 16000)
        self.assertEqual(downsampled.size, 8000)

    def test_invalid_inputs_are_not_silently_valid(self) -> None:
        self.assertFalse(validate_audio(np.array([], dtype=np.float64), 48000).valid)
        self.assertFalse(validate_audio(np.zeros(10), 48000).valid)
        self.assertFalse(validate_audio(np.array([0.0, np.nan] * 1000), 48000).valid)


if __name__ == "__main__":
    unittest.main()
