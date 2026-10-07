import json
from pathlib import Path
import unittest
import numpy as np
from scipy.integrate import quad
from scipy.signal import resample_poly
from independent_voice_synthesis.models import known, FS
from independent_voice_synthesis.p1_connection import lf_constants,lf_derivative,lf_flow,source_coefficients,window,pressure,synthesize,presentation

CFG=json.loads((Path(__file__).resolve().parents[1]/'config/p1-connection.json').read_text())

class ConnectionTests(unittest.TestCase):
    def test_lf_continuity_area_and_spectrum(self):
        c=lf_constants(CFG)
        self.assertLess(abs(c['area_error']),1e-12)
        self.assertAlmostEqual(float(lf_flow(np.array(1.),CFG,c)),0.,places=12)
        self.assertAlmostEqual(float(lf_derivative(np.array(CFG['te']),CFG,c)),-1.,places=12)
        self.assertAlmostEqual(float(lf_derivative(np.array(1.),CFG,c)),0.,places=12)
        f,flow,derivative,_=source_coefficients(CFG)
        for i in (0,5,20):
            n=f[i]/CFG['F0_hz']
            # 周期流量の数値積分と、解析微分スペクトルの積分経路を比較。
            real=quad(lambda u: float(lf_flow(np.array(u),CFG,c))*np.cos(2*np.pi*n*u),0,1,points=[CFG['te']],epsabs=1e-12)[0]
            imag=quad(lambda u: -float(lf_flow(np.array(u),CFG,c))*np.sin(2*np.pi*n*u),0,1,points=[CFG['te']],epsabs=1e-12)[0]
            np.testing.assert_allclose(flow[i],CFG['U0_m3_per_s']*(real+1j*imag),rtol=1e-8,atol=1e-14)
        np.testing.assert_allclose(derivative,flow*(2j*np.pi*f),rtol=1e-14)

    def test_derivative_units_and_inclusion(self):
        f=np.array([1000.])
        flow=np.array([1e-4+0j])
        d=flow*2j*np.pi*f
        self.assertAlmostEqual(float(abs(d[0]/flow[0])),2*np.pi*1000)
        self.assertAlmostEqual(float(np.angle(d[0]/flow[0])),np.pi/2)
        a=pressure(known(),f,flow,CFG)
        np.testing.assert_allclose(a,pressure(known(),f,d/(2j*np.pi*f),CFG),rtol=1e-14)
        np.testing.assert_allclose(a,pressure({**known(),'rho':0.,'fz':2000.},f,flow,CFG),rtol=1e-14)

    def test_band_level_and_rate(self):
        f,flow,_,_=source_coefficients(CFG)
        c=pressure(known(),f,flow,CFG)
        self.assertTrue(np.all(c[f>=5000]==0))
        np.testing.assert_array_equal(window(np.array([0,100,200,4500,5000,8000])),[0,0,1,1,0,0])
        np.testing.assert_allclose(window(f),window(-f))
        y=synthesize(c,f,CFG)
        freq=np.fft.rfftfreq(len(y),1/FS)
        fft=abs(np.fft.rfft(y))
        self.assertLess(float(np.max(fft[freq>=5000])/np.max(fft)),1e-12)
        outputs,logs=presentation([y,10*y],CFG)
        np.testing.assert_allclose(outputs[0],outputs[1],atol=1e-14)
        self.assertLessEqual(logs[0]['final_peak'],CFG['peak_ceiling']+1e-14)
        # 完成信号だけを48kへ変換し、係数を動かさず再生時間と音高を維持。
        up=resample_poly(outputs[0],3,1)
        self.assertEqual(len(up),3*len(y))
        self.assertAlmostEqual(np.argmax(abs(np.fft.rfft(up)))/CFG['duration_seconds'],np.argmax(abs(np.fft.rfft(outputs[0])))/CFG['duration_seconds'])
        with self.assertRaises(ValueError): synthesize(c,f,{**CFG,'Fs':48000})
