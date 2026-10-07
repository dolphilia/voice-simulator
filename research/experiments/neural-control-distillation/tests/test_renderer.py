"""不正制御と音素の誤写像を実合成前に拒否する。"""
import sys
from pathlib import Path
import unittest
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from renderer import validate, segments


class RendererTests(unittest.TestCase):
    def test_palatalized_duration_and_geminate(self):
        out = segments(['ky', 'a', 'Q', 't', 'a'], [.1, .1, .1, .1, .1])
        self.assertAlmostEqual(sum(d for p,d in out), .65)
        self.assertEqual([p for p,d in out], ['', 'k', 'j', 'a', 't', 't', 'a', ''])

    def test_reject_malformed_or_nonfinite(self):
        for duration, f0 in [([.1, .1], [220]), ([np.nan], [220]), ([.1], [999]), ([0], [220])]:
            with self.assertRaises(ValueError):
                validate(['a'], duration, f0)
        with self.assertRaises(ValueError):
            segments(['Q'], [.1])
        with self.assertRaises(ValueError):
            segments(['unknown'], [.1])


if __name__ == '__main__':
    unittest.main()
