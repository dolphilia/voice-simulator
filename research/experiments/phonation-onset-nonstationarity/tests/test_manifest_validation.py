from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from phonation_onset.manifest import load_manifest, validate_manifest


class ManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.path = Path(__file__).resolve().parents[1] / "config/datasets.csv"

    def test_repository_manifest_is_valid(self) -> None:
        self.assertEqual(validate_manifest(self.path), [])

    def test_holdout_is_excluded_by_default_selection(self) -> None:
        records = load_manifest(self.path, {"onset-development"})
        self.assertEqual(len(records), 6)
        self.assertFalse(any(record.split == "onset-holdout" for record in records))


if __name__ == "__main__":
    unittest.main()

