from __future__ import annotations

import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from scipy.io import wavfile

SOURCE = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SOURCE))

from comparison_eval.listening import analyze_perceptual_suite, analyze_responses, prepare_perceptual_suite, prepare_session
from comparison_eval.synthesis import render_suite


class ListeningTests(unittest.TestCase):
    def test_session_is_blind_and_repeat_is_analyzable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            audio = np.sin(np.linspace(0, 100, 8000)) * 0.2
            wavfile.write(root / "candidate.wav", 16000, audio.astype(np.float32))
            wavfile.write(root / "reference.wav", 16000, audio.astype(np.float32))
            benchmark = {"pareto_front": ["task"], "results": [{"task": {"task_id": "task", "generated_path": str(root / "candidate.wav"), "reference_path": str(root / "reference.wav"), "variant": "secret"}, "gate_failures": []}]}
            session = root / "session"
            result = prepare_session(benchmark, session, seed=1, maximum=1, duplicate_ratio=1.0)
            self.assertEqual(result["presentations"], 2)
            self.assertNotIn("secret", (session / "README.md").read_text())
            rows = list(csv.DictReader((session / "responses.csv").open()))
            for row in rows:
                for field in ("phoneme_identity", "naturalness", "clarity", "voice_quality", "target_similarity"):
                    row[field] = "4"
            with (session / "responses.csv").open("w", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=rows[0])
                writer.writeheader(); writer.writerows(rows)
            analysis = analyze_responses(session)
            self.assertTrue(analysis["complete"])
            self.assertEqual(analysis["repeat_consistency"][0]["mean_absolute_repeat_difference"], 0.0)

    def test_full_perceptual_suite_can_be_rendered_and_validated(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = Path(__file__).resolve().parents[1] / "config/synthesis-fixtures.json"
            rendered = render_suite(config, root / "rendered")
            sample = Path(rendered["records"][0]["path"])
            benchmark = {"results": [{"task": {"task_id": "original", "variant": "original", "generated_path": str(sample), "reference_path": str(sample)}, "gate_failures": []}, {"task": {"task_id": "improved", "variant": "spectral-match", "generated_path": str(sample), "reference_path": str(sample)}, "gate_failures": []}]}
            session = root / "suite"
            prepared = prepare_perceptual_suite(rendered, benchmark, session, seed=3)
            self.assertEqual(prepared["identification"], 7)
            rows = list(csv.DictReader((session / "responses.csv").open()))
            key = {item["presentation_id"]: item for item in json.loads((session / "session-key.json").read_text())["items"]}
            for row in rows:
                item = key[row["presentation_id"]]
                row["confidence"] = "4"
                row["answer"] = item.get("correct_label") or item.get("correct_answer") or "A"
            with (session / "responses.csv").open("w", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=rows[0]); writer.writeheader(); writer.writerows(rows)
            analysis = analyze_perceptual_suite(session)
            self.assertTrue(analysis["complete"])
            self.assertEqual(analysis["classification_accuracy"], 1.0)


if __name__ == "__main__":
    unittest.main()
