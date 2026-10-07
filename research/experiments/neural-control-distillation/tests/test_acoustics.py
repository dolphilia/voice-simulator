"""負の自己相関と実際の有声音に対するF0測定を検査する。"""
import sys
from pathlib import Path
from unittest.mock import patch
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from acoustics import estimate_f0


class PitchTests(unittest.TestCase):
    def test_negative_peak_is_not_a_period(self):
        x = np.ones(1440)
        ac = np.full(2879,-1.)
        ac[1439] = 1.
        ac[1439+100] = -.5
        with patch('acoustics.signal.correlate',return_value=ac):
            f0, conf = estimate_f0(x*np.arange(1440),24000)
        self.assertIsNone(f0)
        self.assertEqual(conf,0.)

    def test_known_pitch_and_silence(self):
        for f in (160.,220.,280.):
            t = np.arange(9600)/24000
            y = np.sin(2*np.pi*f*t)+.2*np.sin(4*np.pi*f*t)
            measured, confidence = estimate_f0(y,24000)
            self.assertLess(abs(measured/f-1),.01)
            self.assertGreater(confidence,.65)
        self.assertEqual(estimate_f0(np.zeros(2400),24000),(None,0.))


if __name__=='__main__':
    unittest.main()
