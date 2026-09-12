from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from synthetic_vowel_baseline.synthesis import (
    render_candidates,
    render_corrected_variation_candidates,
    render_f0_generalization_candidates,
    render_gain_attack_scaling_candidates,
    render_onset_secondary_candidates,
    render_two_mass_candidate,
    render_voice_quality_candidates,
    render_vowel_generalization_candidates,
    render_waveguide_candidate,
)


class SynthesisTests(unittest.TestCase):
    def test_gain_attack_scaling_matches_reference_and_changes_extremes(self) -> None:
        spec = json.loads((ROOT / "config/experiment.json").read_text(encoding="utf-8"))
        quality = json.loads((ROOT / "config/voice-quality-experiment.json").read_text(encoding="utf-8"))
        correction = json.loads((ROOT / "config/voice-quality-correction.json").read_text(encoding="utf-8"))
        onset = json.loads((ROOT / "config/onset-secondary-experiment.json").read_text(encoding="utf-8"))
        candidates = render_gain_attack_scaling_candidates(spec, quality, correction, onset, [160.0, 220.0, 300.0], 40.0, 8.8)
        self.assertEqual(len(candidates), 6)
        by_f0 = {f0: [item for item in candidates if item["f0_hz"] == f0] for f0 in (160.0, 220.0, 300.0)}
        self.assertEqual(by_f0[160.0][1]["gain_attack_ms"], 55.0)
        self.assertAlmostEqual(by_f0[300.0][1]["gain_attack_ms"], 29.333333333333332)
        self.assertTrue(np.array_equal(by_f0[220.0][0]["audio"], by_f0[220.0][1]["audio"]))
        for f0 in (160.0, 300.0):
            difference = float(np.sqrt(np.mean((by_f0[f0][0]["audio"] - by_f0[f0][1]["audio"]) ** 2)))
            self.assertGreater(difference, 1e-4)
    def test_vowel_generalization_changes_only_tract_profile(self) -> None:
        spec = json.loads((ROOT / "config/experiment.json").read_text(encoding="utf-8"))
        quality = json.loads((ROOT / "config/voice-quality-experiment.json").read_text(encoding="utf-8"))
        correction = json.loads((ROOT / "config/voice-quality-correction.json").read_text(encoding="utf-8"))
        onset = json.loads((ROOT / "config/onset-secondary-experiment.json").read_text(encoding="utf-8"))
        vowel_spec = json.loads((ROOT / "config/vowel-generalization.json").read_text(encoding="utf-8"))
        candidates = render_vowel_generalization_candidates(spec, quality, correction, onset, vowel_spec["profiles"])
        self.assertEqual(len(candidates), 10)
        self.assertEqual([item["vowel"] for item in candidates[::2]], ["a", "i", "u", "e", "o"])
        for sustain, onset_item in zip(candidates[::2], candidates[1::2], strict=True):
            self.assertEqual(sustain["formants_hz"], onset_item["formants_hz"])
            self.assertEqual(sustain["bandwidths_hz"], onset_item["bandwidths_hz"])
            self.assertEqual(onset_item["gain_attack_ms"], 40.0)
            self.assertAlmostEqual(sustain["diagnostics"]["rendered_f0_std_fraction"], 0.0064, delta=1e-6)
            self.assertTrue(np.all(np.isfinite(sustain["audio"])))
            self.assertTrue(np.all(np.isfinite(onset_item["audio"])))
        for index, left in enumerate(candidates[::2]):
            for right in candidates[::2][index + 1:]:
                self.assertGreater(float(np.sqrt(np.mean((left["audio"] - right["audio"]) ** 2))), 1e-4)

    def test_f0_generalization_preflight_preserves_controls(self) -> None:
        spec = json.loads((ROOT / "config/experiment.json").read_text(encoding="utf-8"))
        quality = json.loads((ROOT / "config/voice-quality-experiment.json").read_text(encoding="utf-8"))
        correction = json.loads((ROOT / "config/voice-quality-correction.json").read_text(encoding="utf-8"))
        onset = json.loads((ROOT / "config/onset-secondary-experiment.json").read_text(encoding="utf-8"))
        candidates = render_f0_generalization_candidates(spec, quality, correction, onset, [160.0, 220.0, 300.0])
        self.assertEqual(len(candidates), 6)
        self.assertEqual([item["condition"] for item in candidates], [
            "F160-B9-sustain", "F160-G40-onset", "F220-B9-sustain",
            "F220-G40-onset", "F300-B9-sustain", "F300-G40-onset",
        ])
        for sustain, gain_attack in zip(candidates[::2], candidates[1::2], strict=True):
            self.assertTrue(np.all(np.isfinite(sustain["audio"])))
            self.assertTrue(np.all(np.isfinite(gain_attack["audio"])))
            self.assertAlmostEqual(sustain["diagnostics"]["rendered_f0_mean_hz"], sustain["f0_hz"], delta=1e-6)
            self.assertAlmostEqual(sustain["diagnostics"]["rendered_f0_std_fraction"], 0.0064, delta=1e-6)
            self.assertEqual(gain_attack["gain_attack_ms"], 40.0)
            self.assertGreater(float(np.sqrt(np.mean((sustain["audio"] - gain_attack["audio"]) ** 2))), 1e-4)

    def test_matrix_is_finite_distinct_and_has_matched_shape(self) -> None:
        spec = json.loads((ROOT / "config/experiment.json").read_text(encoding="utf-8"))
        candidates = render_candidates(spec)
        self.assertEqual([item["condition"] for item in candidates], [
            "B0-saw-parallel", "B1-lf-parallel", "B2-saw-cascade", "B3-lf-cascade",
        ])
        expected = int(spec["sample_rate"] * spec["duration_sec"])
        for item in candidates:
            audio = item["audio"]
            self.assertEqual(audio.size, expected)
            self.assertTrue(np.all(np.isfinite(audio)))
            self.assertAlmostEqual(float(audio[0]), 0.0, places=12)
            self.assertAlmostEqual(float(audio[-1]), 0.0, places=12)
            self.assertFalse(item["contains_human_audio"])
        for index, left in enumerate(candidates):
            for right in candidates[index + 1 :]:
                difference = float(np.sqrt(np.mean((left["audio"] - right["audio"]) ** 2)))
                self.assertGreater(difference, 1e-4)

    def test_two_mass_candidate_self_oscillates_and_is_bounded(self) -> None:
        spec = json.loads((ROOT / "config/experiment.json").read_text(encoding="utf-8"))
        spec["two_mass"] = json.loads((ROOT / "config/two-mass-experiment.json").read_text(encoding="utf-8"))
        candidate = render_two_mass_candidate(spec)
        diagnostics = candidate["diagnostics"]
        self.assertEqual(candidate["audio"].size, int(spec["sample_rate"] * spec["duration_sec"]))
        self.assertTrue(np.all(np.isfinite(candidate["audio"])))
        self.assertGreater(diagnostics["measured_f0_hz"], 180.0)
        self.assertLess(diagnostics["measured_f0_hz"], 260.0)
        self.assertGreater(diagnostics["closed_ratio"], 0.01)
        self.assertLess(diagnostics["maximum_displacement_m"], 0.005)

    def test_waveguide_candidate_is_finite_bounded_and_distinct(self) -> None:
        spec = json.loads((ROOT / "config/experiment.json").read_text(encoding="utf-8"))
        waveguide = json.loads((ROOT / "config/waveguide-experiment.json").read_text(encoding="utf-8"))
        candidate = render_waveguide_candidate(spec, waveguide)
        baseline = next(item for item in render_candidates(spec) if item["condition"] == "B2-saw-cascade")
        audio = candidate["audio"]
        self.assertEqual(audio.size, int(spec["sample_rate"] * spec["duration_sec"]))
        self.assertTrue(np.all(np.isfinite(audio)))
        self.assertLess(candidate["diagnostics"]["maximum_reflection_absolute"], 1.0)
        self.assertGreater(candidate["diagnostics"]["minimum_loss"], 0.0)
        self.assertGreater(float(np.sqrt(np.mean((audio - baseline["audio"]) ** 2))), 1e-4)

    def test_voice_quality_chain_is_finite_distinct_and_parameterized(self) -> None:
        spec = json.loads((ROOT / "config/experiment.json").read_text(encoding="utf-8"))
        quality = json.loads((ROOT / "config/voice-quality-experiment.json").read_text(encoding="utf-8"))
        candidates = render_voice_quality_candidates(spec, quality)
        self.assertEqual([item["condition"] for item in candidates], [
            "B6-tilted-saw-cascade",
            "B7-tilted-varied-saw-cascade",
            "B8-tilted-varied-aspirated-saw-cascade",
        ])
        for item in candidates:
            self.assertEqual(item["audio"].size, int(spec["sample_rate"] * spec["duration_sec"]))
            self.assertTrue(np.all(np.isfinite(item["audio"])))
            self.assertLessEqual(float(np.max(np.abs(item["audio"]))), 1.0)
        self.assertGreater(candidates[1]["diagnostics"]["rendered_f0_std_fraction"], 0.004)
        for left, right in zip(candidates, candidates[1:]):
            self.assertGreater(float(np.sqrt(np.mean((left["audio"] - right["audio"]) ** 2))), 1e-4)

    def test_legacy_voice_quality_control_exposes_seed_scale_instability(self) -> None:
        spec = json.loads((ROOT / "config/experiment.json").read_text(encoding="utf-8"))
        quality = json.loads((ROOT / "config/voice-quality-experiment.json").read_text(encoding="utf-8"))
        variants = []
        f0_scales = []
        correlations = []
        for offset in (301, 317, 353):
            item = render_voice_quality_candidates(spec, {**quality, "seed_offset": offset})[1]
            variants.append(item)
            f0_scales.append(item["diagnostics"]["rendered_f0_std_fraction"])
            correlations.append(item["diagnostics"]["rendered_control_correlation"])
            self.assertAlmostEqual(item["diagnostics"]["rendered_amplitude_std_db"], 0.67, delta=0.08)
        self.assertGreater(max(f0_scales) - min(f0_scales), 0.03)
        self.assertGreater(max(correlations) - min(correlations), 1.0)
        for index, left in enumerate(variants):
            for right in variants[index + 1 :]:
                self.assertGreater(float(np.sqrt(np.mean((left["audio"] - right["audio"]) ** 2))), 1e-4)

    def test_corrected_variation_matches_active_region_targets(self) -> None:
        spec = json.loads((ROOT / "config/experiment.json").read_text(encoding="utf-8"))
        quality = json.loads((ROOT / "config/voice-quality-experiment.json").read_text(encoding="utf-8"))
        correction = json.loads((ROOT / "config/voice-quality-correction.json").read_text(encoding="utf-8"))
        candidates = render_corrected_variation_candidates(spec, quality, correction)
        self.assertEqual(len(candidates), 2)
        for item, configured in zip(candidates, correction["conditions"], strict=True):
            diagnostics = item["diagnostics"]
            self.assertAlmostEqual(diagnostics["rendered_f0_std_fraction"], configured["f0_std_fraction"], delta=1e-6)
            self.assertAlmostEqual(diagnostics["rendered_amplitude_std_db"], correction["amplitude_std_db"], delta=1e-6)
            self.assertAlmostEqual(diagnostics["rendered_control_correlation"], correction["pitch_amplitude_correlation"], delta=0.02)
            self.assertTrue(np.all(np.isfinite(item["audio"])))

    def test_corrected_b9_seed_variants_preserve_targets_and_differ(self) -> None:
        spec = json.loads((ROOT / "config/experiment.json").read_text(encoding="utf-8"))
        quality = json.loads((ROOT / "config/voice-quality-experiment.json").read_text(encoding="utf-8"))
        correction = json.loads((ROOT / "config/voice-quality-correction.json").read_text(encoding="utf-8"))
        validation = json.loads((ROOT / "config/b9-seed-validation.json").read_text(encoding="utf-8"))
        variants = []
        for offset in validation["seed_offsets"]:
            item = render_corrected_variation_candidates(spec, quality, {**correction, "seed_offset": offset})[0]
            variants.append(item)
            self.assertAlmostEqual(item["diagnostics"]["rendered_f0_std_fraction"], 0.0064, delta=1e-6)
            self.assertAlmostEqual(item["diagnostics"]["rendered_amplitude_std_db"], 0.67, delta=1e-6)
            self.assertAlmostEqual(item["diagnostics"]["rendered_control_correlation"], 0.5, delta=0.02)
        for index, left in enumerate(variants):
            for right in variants[index + 1 :]:
                self.assertGreater(float(np.sqrt(np.mean((left["audio"] - right["audio"]) ** 2))), 1e-4)

    def test_onset_secondary_preserves_b9_and_matched_stable_rms(self) -> None:
        spec = json.loads((ROOT / "config/experiment.json").read_text(encoding="utf-8"))
        quality = json.loads((ROOT / "config/voice-quality-experiment.json").read_text(encoding="utf-8"))
        correction = json.loads((ROOT / "config/voice-quality-correction.json").read_text(encoding="utf-8"))
        onset = json.loads((ROOT / "config/onset-secondary-experiment.json").read_text(encoding="utf-8"))
        candidates = render_onset_secondary_candidates(spec, quality, correction, onset)
        canonical = render_corrected_variation_candidates(spec, quality, {**correction, "seed_offset": 401})[0]["audio"]
        np.testing.assert_array_equal(candidates[0]["audio"], canonical)
        start = int(onset["stable_normalization_start_sec"] * spec["sample_rate"])
        end = canonical.size - int(spec["edge_fade_ms"] * spec["sample_rate"] / 1000.0)
        stable_rms = [float(np.sqrt(np.mean(item["audio"][start:end] ** 2))) for item in candidates]
        for item, value in zip(candidates, stable_rms, strict=True):
            self.assertTrue(np.all(np.isfinite(item["audio"])))
            self.assertAlmostEqual(float(item["audio"][0]), 0.0, places=12)
            self.assertAlmostEqual(float(item["audio"][-1]), 0.0, places=12)
            self.assertAlmostEqual(value, stable_rms[0], delta=2e-4)
        for left, right in zip(candidates, candidates[1:]):
            self.assertGreater(float(np.sqrt(np.mean((left["audio"] - right["audio"]) ** 2))), 1e-4)

    def test_aspiration_seed_changes_o2_but_not_o1(self) -> None:
        spec = json.loads((ROOT / "config/experiment.json").read_text(encoding="utf-8"))
        quality = json.loads((ROOT / "config/voice-quality-experiment.json").read_text(encoding="utf-8"))
        correction = json.loads((ROOT / "config/voice-quality-correction.json").read_text(encoding="utf-8"))
        onset = json.loads((ROOT / "config/onset-secondary-experiment.json").read_text(encoding="utf-8"))
        validation = json.loads((ROOT / "config/onset-aspiration-validation.json").read_text(encoding="utf-8"))
        renders = [render_onset_secondary_candidates(spec, quality, correction, {**onset, "seed_offset": offset}) for offset in validation["seed_offsets"]]
        for rendered in renders[1:]:
            np.testing.assert_array_equal(rendered[1]["audio"], renders[0][1]["audio"])
        o2_values = [rendered[2]["audio"] for rendered in renders]
        for index, left in enumerate(o2_values):
            for right in o2_values[index + 1 :]:
                self.assertGreater(float(np.sqrt(np.mean((left - right) ** 2))), 1e-5)

    def test_gain_attack_duration_candidates_share_stable_region(self) -> None:
        spec = json.loads((ROOT / "config/experiment.json").read_text(encoding="utf-8"))
        quality = json.loads((ROOT / "config/voice-quality-experiment.json").read_text(encoding="utf-8"))
        correction = json.loads((ROOT / "config/voice-quality-correction.json").read_text(encoding="utf-8"))
        onset = json.loads((ROOT / "config/onset-secondary-experiment.json").read_text(encoding="utf-8"))
        duration = json.loads((ROOT / "config/gain-attack-duration-experiment.json").read_text(encoding="utf-8"))
        values = [render_onset_secondary_candidates(spec, quality, correction, {**onset, "gain_attack_ms": milliseconds})[1]["audio"] for milliseconds in duration["durations_ms"]]
        original_o1 = render_onset_secondary_candidates(spec, quality, correction, onset)[1]["audio"]
        np.testing.assert_array_equal(values[1], original_o1)
        start = int(onset["stable_normalization_start_sec"] * spec["sample_rate"])
        end = original_o1.size - int(spec["edge_fade_ms"] * spec["sample_rate"] / 1000.0)
        for value in values:
            np.testing.assert_allclose(value[start:end], original_o1[start:end], atol=1e-12)
        for left, right in zip(values, values[1:]):
            self.assertGreater(float(np.sqrt(np.mean((left - right) ** 2))), 1e-4)


if __name__ == "__main__":
    unittest.main()
