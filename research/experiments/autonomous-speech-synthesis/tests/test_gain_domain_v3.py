"""全相対利得領域と逆写像を点検する。音響資格を代用しない。"""
import itertools
from pathlib import Path
import sys
import unittest
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'src'))
from free_fit_gain_domain_v3 import gains_from_point,point_from_gains,voice_from_point
from autonomous_speech_synthesis.gestures import voice_config,validate_voice

class GainDomainTests(unittest.TestCase):
    def test_original_gain_domain_can_be_represented(self):
        cases=list(itertools.product((.05,.3,1.),repeat=3))
        cases.extend(np.random.default_rng(713).uniform(.05,1,(200,3)))
        for original in cases:
            original=np.asarray(original)
            recovered=gains_from_point(point_from_gains(original))
            np.testing.assert_allclose(recovered,original/max(original),atol=2e-14,rtol=2e-14)
    def test_square_maps_bijectively_and_stays_in_gain_bounds(self):
        for z in itertools.product(np.linspace(0,1,21),repeat=2):
            gain=gains_from_point(z)
            self.assertGreaterEqual(min(gain),.05-1e-14);self.assertEqual(max(gain),1.)
            np.testing.assert_allclose(point_from_gains(gain),z,atol=2e-14,rtol=2e-14)
    def test_old_omitted_relative_gains_and_voice_contract(self):
        # 旧6変数で有効なg2/g1=10を、第1利得固定・g2<=1では表せなかった。
        z=point_from_gains([.1,1.,.1]);g=gains_from_point(z)
        self.assertAlmostEqual(g[1]/g[0],10.)
        for vowel in 'aiueo':
            for corner in itertools.product((0.,1.),repeat=5):validate_voice(voice_from_point(voice_config(),vowel,corner))
        for bad in ([np.nan,.5],[.5,1.01],[.5]):
            with self.assertRaises(ValueError):gains_from_point(bad)

if __name__=='__main__':unittest.main()
