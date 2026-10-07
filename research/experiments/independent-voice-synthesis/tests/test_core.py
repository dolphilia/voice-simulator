"""独立した応答計算法、反例、予算端で誤判定を検出する。"""
import unittest
from unittest.mock import patch
import numpy as np
from scipy.signal import sosfreqz
from independent_voice_synthesis.models import response, known, FS, starts, decode, encode
from independent_voice_synthesis.objective import metrics, optimal_gain, intersection, state, route
from independent_voice_synthesis.optimization import fit, rank


class CoreTests(unittest.TestCase):
    def test_independent_sos_response(self):
        p = known(True)
        sos = []
        for f,b in zip(p['f'],p['B']):
            r = np.exp(-np.pi*b/FS)
            sos.append([1,0,0,1,-2*r*np.cos(2*np.pi*f/FS),r*r])
        sos[0][:3] = [1,-2*p['rho']*np.cos(2*np.pi*p['fz']/FS),p['rho']**2]
        f = np.arange(100.,5001.)
        _, h = sosfreqz(sos, worN=f, fs=FS)
        np.testing.assert_allclose(response(p,f), h, rtol=1e-12, atol=1e-12)

    def test_k0_and_gain(self):
        q = np.r_[3.2,np.full(99,-3.2/99)]
        self.assertGreater(metrics(q)['J'],1)
        self.assertLess(metrics(q-.25)['J'],1)
        a,m = optimal_gain(q)
        self.assertLess(m['J'],1)
        self.assertLess(abs(a),3.2)
        self.assertLess(optimal_gain(np.tile([-.6,.6],50))[1]['J'],m['J'])
        self.assertEqual(optimal_gain(np.full(5,12.)),(-12.,dict(R=0.,M=0.,J=0.)))
        self.assertIsNone(intersection(.9,0.,1.,-1.,1.))
        self.assertEqual(intersection(1.,0.,1.,-1.,1.),(0.,0.))
        self.assertEqual(intersection(2.,0.,0.,-6.,6.),(0.,0.))
        self.assertIsNone(intersection(1.,0.,0.,-6.,6.))

    def test_gain_against_dense_scalar_search(self):
        q = np.array([-4.,-.1,.5,1.,1.])
        a,m = optimal_gain(q)
        grid = np.linspace(a-.1,a+.1,1001)
        self.assertLessEqual(m['J'],min(metrics(q+v)['J'] for v in grid)+1e-8)

    def test_inclusion_and_notch(self):
        f = np.arange(100.,5001.)
        h = response(known(),f)
        np.testing.assert_allclose(response({**known(),'rho':0.,'fz':2000.},f)/h,1.,rtol=1e-12)
        points = np.array([1800.,2000.,2200.])
        delta = 20*np.log10(abs(response(known(True),points)/response(known(),points)))
        self.assertTrue(delta[1]+6 <= min(delta[0],delta[2]))

    def test_invalid(self):
        for x in ([float('nan')]*10,[-.1]*10,[1.1]*10):
            with self.assertRaises(ValueError): decode(x)
        with self.assertRaises(ValueError): metrics([np.nan])
        with self.assertRaises(ValueError): response({**known(),'g':0},[100])

    def test_start_and_round_trip(self):
        u = np.random.Generator(np.random.PCG64(20260913)).random((3,12))
        np.testing.assert_array_equal(starts()[1],u[0,:10])
        for x in starts()+starts(known()):
            np.testing.assert_allclose(encode(decode(x)),x,atol=1e-15)

    def test_budget_and_best_intermediate(self):
        f = np.arange(100.,5001.,50)
        target = 20*np.log10(abs(response(known(),f)))
        # 最終反復点だけを返す実装では、この中間候補が失われる。
        def fake(fun,x0,**kwargs):
            fun(x0)
            fun(encode(known()))
            fun(np.full(10,.9))
            fun(np.full(10,.8))
        with patch('independent_voice_synthesis.optimization.minimize',fake):
            result = fit(f,target,dict(xtol=1e-4,ftol=1e-6),3)
        self.assertEqual(result['evaluations'],12)
        self.assertLess(result['best']['J'],1e-8)
        self.assertEqual(result['best']['evaluation'],2)
        self.assertEqual(result['best']['start'],0)
        self.assertEqual(rank(result['best']),min(rank(r) for h in result['histories'] for r in h))

    def test_decisions(self):
        self.assertEqual(state(.999,.8),'pass')
        self.assertEqual(state(1.001,.8),'fail')
        self.assertEqual(state(1.,.8),'uncertain')
        for other in ('pass','fail','uncertain'):
            for flags in (False,True):
                self.assertEqual(route('pass',other,flags),'P5')
        self.assertEqual(route('fail','pass',False),'P5+P5Z')
        self.assertEqual(route('fail','pass',True),'P5-unconfirmed')
        self.assertEqual(route('uncertain','pass',False),'P5-unconfirmed')

if __name__ == '__main__':
    unittest.main()
