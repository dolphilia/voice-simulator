from __future__ import annotations

import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from phonation_onset.audio import sha256_file, write_audio, write_json
from phonation_onset.listening_wizard import (
    FakePlayer,
    ListeningWizard,
    WIZARD_SCHEMA_VERSION,
    analyze_wizard_session,
    parse_yes_no,
    prepare_wizard_session,
    question_route,
)


class InputQueue:
    def __init__(self, values: list[str]) -> None:
        self.values = iter(values)

    def __call__(self, _: str) -> str:
        return next(self.values)


def make_audio(path: Path, amplitude: float = 0.1) -> None:
    sample_rate = 16000
    time_axis = np.arange(1600) / sample_rate
    write_audio(path, sample_rate, amplitude * np.sin(2.0 * np.pi * 180.0 * time_axis))


def make_tiny_session(path: Path) -> None:
    (path / "audio").mkdir(parents=True)
    (path / "calibration").mkdir()
    for relative, amplitude in (
        ("audio/W01-A.wav", 0.08),
        ("audio/W01-B.wav", 0.1),
        ("calibration/volume-check.wav", 0.08),
        ("calibration/practice-A.wav", 0.03),
        ("calibration/practice-B.wav", 0.1),
    ):
        make_audio(path / relative, amplitude)
    blinded = {
        "schema_version": WIZARD_SCHEMA_VERSION,
        "session_id": "tiny",
        "presentation_count": 1,
        "break_every_presentations": 5,
        "calibration_audio": "calibration/volume-check.wav",
        "practice_audio": {"A": "calibration/practice-A.wav", "B": "calibration/practice-B.wav"},
        "presentations": [{
            "presentation_id": "W01",
            "audio": {"A": "audio/W01-A.wav", "B": "audio/W01-B.wav"},
            "questions": [
                {"id": "more_human", "kind": "comparison", "prompt": "どちらが人の発声に近いですか"},
                {"id": "more_natural_onset", "kind": "comparison", "prompt": "どちらの開始が自然ですか"},
                {"id": "vowel_identity", "kind": "side_yes_no", "prompt": "目的母音に聞こえますか"},
            ],
        }],
    }
    private = {
        "schema_version": WIZARD_SCHEMA_VERSION,
        "session_id": "tiny",
        "presentations": [{
            "presentation_id": "W01", "pair_id": "pair-1", "hypothesis": "H1", "duplicate_of": None,
            "questions": blinded["presentations"][0]["questions"],
            "A": {"condition": "first", "stimulus_id": "a"},
            "B": {"condition": "second", "stimulus_id": "b"},
        }],
    }
    write_json(path / "blinded-session.json", blinded)
    write_json(path / "private-session-key.json", private)
    audio_hashes = {
        relative: sha256_file(path / relative)
        for relative in (
            "audio/W01-A.wav", "audio/W01-B.wav", "calibration/volume-check.wav",
            "calibration/practice-A.wav", "calibration/practice-B.wav",
        )
    }
    write_json(path / "lock.json", {
        "schema_version": WIZARD_SCHEMA_VERSION,
        "files": {
            "blinded-session.json": sha256_file(path / "blinded-session.json"),
            "private-session-key.json": sha256_file(path / "private-session-key.json"),
        },
        "audio": audio_hashes,
    })


class ListeningWizardTests(unittest.TestCase):
    def test_vowel_generalization_route_names_target_without_revealing_condition(self) -> None:
        questions = question_route({"hypothesis": "vowel-generalization-i", "pair_id": "i-b9-vs-g40"})
        self.assertEqual([item["id"] for item in questions], [
            "more_natural_onset", "vowel_identity", "human_voice_identity",
        ])
        self.assertIn("/i/", questions[1]["prompt"])
        self.assertNotIn("B9", str(questions))
        self.assertNotIn("G40", str(questions))
        with self.assertRaises(ValueError):
            question_route({"hypothesis": "vowel-generalization-x", "pair_id": "invalid"})

    def test_onset_secondary_route_separates_naturalness_from_identity(self) -> None:
        questions = question_route({"hypothesis": "onset-secondary", "pair_id": "o0-vs-o1"})
        self.assertEqual([item["id"] for item in questions], [
            "more_natural_onset", "vowel_identity", "human_voice_identity",
        ])

    def test_yes_no_accepts_short_english_and_japanese(self) -> None:
        for value in ("y", "Y", "yes", "はい", "ハイ"):
            self.assertIs(parse_yes_no(value), True)
        for value in ("n", "N", "no", "いいえ", "イイエ"):
            self.assertIs(parse_yes_no(value), False)
        self.assertIsNone(parse_yes_no("maybe"))

    def test_prepare_preserves_unique_pairs_and_separates_duplicates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            legacy = root / "checkpoint"
            output = root / "checkpoint-wizard-v1"
            (legacy / "audio").mkdir(parents=True)
            hypotheses = ["H1", "H1", "H6", "H6", "H4", "H4", "H3", "H5", "control", "H6", "H4", "H6", "control"]
            rows = []
            responses = []
            for index, hypothesis in enumerate(hypotheses, 1):
                presentation_id = f"T{index:02d}"
                pair_id = f"{'synthetic--' if index in {7, 8} else ''}pair-{index}"
                make_audio(legacy / "audio" / f"{presentation_id}-A.wav", 0.05 + index * 0.001)
                make_audio(legacy / "audio" / f"{presentation_id}-B.wav", 0.08 + index * 0.001)
                rows.append({
                    "presentation_id": presentation_id, "pair_id": pair_id, "hypothesis": hypothesis,
                    "question": "q", "duplicate_of": "",
                    "a_stimulus_id": f"a-{index}", "a_condition": f"condition-a-{index}", "a_sha256": "",
                    "b_stimulus_id": f"b-{index}", "b_condition": f"condition-b-{index}", "b_sha256": "",
                })
                responses.append({
                    "presentation_id": presentation_id, "more_human": "", "more_natural_onset": "",
                    "more_natural_sustain": "", "artifact": "", "confidence": "", "notes": "",
                })
            for filename, data in (("presentation-key.csv", rows), ("responses.csv", responses)):
                with (legacy / filename).open("w", newline="", encoding="utf-8") as handle:
                    writer = csv.DictWriter(handle, fieldnames=list(data[0]))
                    writer.writeheader()
                    writer.writerows(data)
            write_json(legacy / "lock.json", {"presentation_count": 13})

            result = prepare_wizard_session(legacy, output, seed=1234)
            self.assertEqual(result["presentations"], 17)
            self.assertEqual(result["duplicates"], 4)
            blinded = json.loads((output / "blinded-session.json").read_text(encoding="utf-8"))
            private = json.loads((output / "private-session-key.json").read_text(encoding="utf-8"))
            blinded_text = json.dumps(blinded, ensure_ascii=False)
            for forbidden in ("hypothesis", "pair_id", "condition", "duplicate_of", "stimulus_id"):
                self.assertNotIn(forbidden, blinded_text)
            positions: dict[str, list[int]] = {}
            for index, item in enumerate(private["presentations"]):
                positions.setdefault(item["pair_id"], []).append(index)
            repeated = [indices for indices in positions.values() if len(indices) == 2]
            self.assertEqual(len(repeated), 4)
            self.assertTrue(all(indices[1] - indices[0] >= 5 for indices in repeated))

    def test_pause_resume_and_analysis_map_answer_to_condition(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            session = Path(directory)
            make_tiny_session(session)
            played: list[str] = []
            first_inputs = InputQueue([
                "y", "y", "y", "y", "y",  # environment and calibration
                "p", "c", "2",              # practice
                "p", "c", "y", "2",       # save the first question
                "q",                          # pause during the second question
            ])
            first = ListeningWizard(session, FakePlayer(played=played), first_inputs, lambda _: None)
            self.assertEqual(first.run(), 0)
            progress = json.loads((session / "progress.json").read_text(encoding="utf-8"))
            self.assertEqual(progress["current_index"], 0)
            self.assertEqual(progress["drafts"]["W01"]["answers"]["more_human"], "B")

            second_inputs = InputQueue([
                "y",                          # same device and volume
                "p", "c",                   # hear pair and answer
                "y", "1",                   # second question: choose A
                "y", "n",                   # vowel identity for A/B
                "n", "n",                   # no artifact on A/B
                "n",                          # no interference
                "y",                          # confirm
            ])
            second = ListeningWizard(session, FakePlayer(played=played), second_inputs, lambda _: None)
            self.assertEqual(second.run(), 0)
            responses = json.loads((session / "responses.json").read_text(encoding="utf-8"))
            self.assertEqual(responses["attempts"]["W01"][0]["answers"]["more_human"], "B")
            analysis = analyze_wizard_session(session)
            comparison = analysis["hypotheses"]["H1"]["comparisons"][0]
            self.assertEqual(comparison["answers"]["more_human"], "second")
            self.assertEqual(comparison["answers"]["vowel_identity"], {"first": True, "second": False})


if __name__ == "__main__":
    unittest.main()
