from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from phonation_onset.stimuli import apply_microvariation, loop_with_crossfade, render_a_stimuli, seam_jump_ratio
from phonation_onset.synthesis import render_suite


class StimulusTests(unittest.TestCase):
    def test_crossfade_loop_has_expected_length_and_seams(self) -> None:
        time = np.arange(1600) / 48000
        segment = np.sin(2 * np.pi * 150 * time)
        output, seams = loop_with_crossfade(segment, 8000, 240)
        self.assertEqual(output.size, 8000)
        self.assertGreater(len(seams), 2)
        self.assertLess(seam_jump_ratio(output, seams), 6.0)

    def test_a_suite_contains_required_conditions(self) -> None:
        sample_rate = 48000; time = np.arange(sample_rate) / sample_rate
        audio = np.sin(2 * np.pi * 180 * time) * np.minimum(1.0, time / 0.12)
        control_time = np.linspace(0, 6 * np.pi, 100)
        suite = render_a_stimuli(audio, sample_rate, 0.01, 0.16, 0.95, 0.8, 0.55, [40, 80, 160, 240], 10, -20, 180 + np.sin(control_time), -20 + np.sin(control_time))
        conditions = {item["condition"] for item in suite}
        self.assertIn("A0-original", conditions)
        self.assertIn("A2-stable-only", conditions)
        self.assertIn("A3-loop-long", conditions)
        self.assertIn("A4-loop-short-40ms", conditions)
        self.assertIn("A5-loop-correlated-variation", conditions)
        self.assertIn("A6-loop-independent-variation", conditions)
        loop = next(item for item in suite if item["condition"] == "A3-loop-long")
        self.assertTrue(loop["metadata"]["onset_preserved"])
        self.assertGreater(loop["seams"][0], 0)

    def test_microvariation_preserves_length_and_changes_signal(self) -> None:
        time = np.arange(8000) / 48000
        audio = np.sin(2 * np.pi * 180 * time)
        control = np.sin(2 * np.pi * 3 * time)
        varied = apply_microvariation(audio, control, control, 48000)
        self.assertEqual(varied.size, audio.size)
        self.assertGreater(float(np.sqrt(np.mean((varied - audio) ** 2))), 1e-4)

    def test_synthesis_suite_is_fully_generated_and_finite(self) -> None:
        suite = render_suite(16000, 0.4, 180.0, (800.0, 1300.0, 2500.0), 123)
        self.assertEqual(len(suite), 8)
        for item in suite:
            self.assertFalse(item["contains_human_audio"])
            self.assertTrue(np.all(np.isfinite(item["audio"])))
            self.assertGreater(float(np.max(np.abs(item["audio"]))), 0.01)
        by_condition = {item["condition"]: item["audio"] for item in suite}
        self.assertGreater(float(np.sqrt(np.mean((by_condition["C1-gain"] - by_condition["C6-no-formant"]) ** 2))), 1e-3)
        self.assertGreater(float(np.sqrt(np.mean((by_condition["C6-no-formant"] - by_condition["C6-coupled"]) ** 2))), 1e-3)


if __name__ == "__main__":
    unittest.main()
