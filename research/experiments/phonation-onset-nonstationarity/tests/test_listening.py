from __future__ import annotations

import argparse
import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from phonation_onset.cli import command_analyze_listening


class ListeningTests(unittest.TestCase):
    def test_duplicate_consistency_is_condition_based_when_sides_reverse(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            session = Path(directory)
            keys = [
                {"presentation_id": "T01", "pair_id": "pair", "hypothesis": "H1", "question": "q", "duplicate_of": "", "a_condition": "with", "b_condition": "without"},
                {"presentation_id": "T02", "pair_id": "pair", "hypothesis": "H1", "question": "q", "duplicate_of": "pair", "a_condition": "without", "b_condition": "with"},
            ]
            responses = [
                {"presentation_id": "T01", "more_human": "A", "more_natural_onset": "A", "more_natural_sustain": "TIE", "artifact": "NEITHER", "confidence": "4", "notes": ""},
                {"presentation_id": "T02", "more_human": "B", "more_natural_onset": "B", "more_natural_sustain": "TIE", "artifact": "NEITHER", "confidence": "4", "notes": ""},
            ]
            for path, rows in ((session / "presentation-key.csv", keys), (session / "responses.csv", responses)):
                with path.open("w", newline="", encoding="utf-8") as handle:
                    writer = csv.DictWriter(handle, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
            (session / "lock.json").write_text(json.dumps({"presentation_count": 2}), encoding="utf-8")
            output = session / "analysis.json"
            code = command_analyze_listening(argparse.Namespace(session=str(session), output=str(output)))
            self.assertEqual(code, 0)
            result = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(result["duplicate_consistency_rate"], 1.0)


if __name__ == "__main__":
    unittest.main()
