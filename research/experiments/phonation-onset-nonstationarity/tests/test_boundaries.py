from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from phonation_onset.boundaries import detect_boundaries, periodicity


class BoundaryTests(unittest.TestCase):
    def test_periodicity_recovers_pitch(self) -> None:
        sample_rate = 48000; time = np.arange(int(0.04 * sample_rate)) / sample_rate
        f0, strength = periodicity(np.sin(2 * np.pi * 180 * time), sample_rate)
        self.assertAlmostEqual(f0, 180.0, delta=3.0)
        self.assertGreater(strength, 0.7)

    def test_boundaries_follow_silence_ramp_and_stable_tone(self) -> None:
        sample_rate = 48000
        silence = np.zeros(int(0.10 * sample_rate))
        time = np.arange(int(0.50 * sample_rate)) / sample_rate
        envelope = np.clip(time / 0.10, 0, 1)
        tone = envelope * np.sin(2 * np.pi * 180 * time)
        boundaries, _ = detect_boundaries(np.concatenate([silence, tone]), sample_rate)
        self.assertGreater(boundaries.acoustic_activity_onset_sec, 0.07)
        self.assertLess(boundaries.acoustic_activity_onset_sec, 0.16)
        self.assertLessEqual(boundaries.acoustic_activity_onset_sec, boundaries.periodicity_onset_sec)
        self.assertLessEqual(boundaries.periodicity_onset_sec, boundaries.stable_vowel_onset_sec)
        self.assertGreater(boundaries.confidence, 0.6)

    def test_short_input_reports_low_confidence(self) -> None:
        boundaries, series = detect_boundaries(np.zeros(10), 48000)
        self.assertEqual(boundaries.confidence, 0.0)
        self.assertIn("too_short", boundaries.reasons)
        self.assertEqual(series["time_sec"], [])


if __name__ == "__main__":
    unittest.main()

