"""五母音の共有径/面積、明示遷移、有限Fourier LF駆動。録音/学習/HMM/lookupなし。"""
import json,math,cmath
from pathlib import Path
import numpy as np
from scipy import signal
from waveguide_tract import render,ah
HERE=Path(__file__).resolve().parent
DIAM=json.loads((HERE/'diameters.json').read_text());COEF=json.loads((HERE/'coefficients.json').read_text())
FS=34300;OUTFS=24000;CUTOFF=8000.;GAIN=.10
AREA={v:np.pi*(np.array(d[::-1],dtype=float)/20.)**2 for v,d in DIAM.items()}
def coefficient(m):
 tp,te,ta,ep,a,e0,scale=map(float,COEF);w=math.pi/tp;omega=2*math.pi*m;length=1-te
 if m==0:return 0j
 z1=complex(a,w-omega);z2=complex(a,-w-omega)
 opened=e0*((cmath.exp(z1*te)-1.)/z1-(cmath.exp(z2*te)-1.)/z2)/(2j)
 returning=-(cmath.exp(-1j*omega*te)*(1.-cmath.exp(-complex(ep,omega)*length))/complex(ep,omega)
             -math.exp(-ep*length)*(cmath.exp(-1j*omega*te)-cmath.exp(-1j*omega))/(1j*omega))/(ep*ta)
 return scale*(opened+returning)
def driver(f0,samples):
 if not math.isfinite(f0) or not 70<=f0<=400 or not 1<=samples<=96000:raise ValueError('F0/標本数が登録範囲外')
 phase=(np.arange(samples,dtype=float)*f0/FS+.125)%1.;x=np.zeros(samples);harmonics=math.floor(CUTOFF/f0)
 for m in range(1,harmonics+1):x+=2.*np.real(coefficient(m)*np.exp(2j*np.pi*m*phase))
 return x,dict(f0=f0,phase_start=.125,harmonics=harmonics,maximum_source_harmonic_hz=harmonics*f0,continuous_LF_scale_fixed=True,truncation_RMS_renormalized=False)
def areas(first,second=None,samples=20580):
 if first not in AREA or second is not None and second not in AREA:raise ValueError('登録外の母音')
 if second is None:return np.tile(AREA[first],(samples,1))
 t=np.arange(samples)/FS;q=np.clip((t-.20)/.10,0.,1.);s=q*q*(3.-2.*q)
 return (1.-s[:,None])*AREA[first]+s[:,None]*AREA[second]
def output(raw):
 y=signal.resample_poly(raw,240,343,window=('kaiser',5.))*GAIN
 n=min(round(.012*OUTFS),len(y)//2);fade=np.sin(np.linspace(0,np.pi/2,n))**2;y[:n]*=fade;y[-n:]*=fade[::-1]
 return y
def generate(first,f0=220,second=None):
 x,source=driver(f0,20580);a=areas(first,second);before=(ah(x),ah(a));y,e=render(x,a)
 assert before==(ah(x),ah(a));audio=output(y)
 return audio,dict(source=source,geometry=dict(first=first,second=second,source_fs=FS,section_length_cm=1.,sections=16,length_cm=16.,area_sha256=ah(a)),driver_sha256=ah(x),raw_sha256=ah(y),normalized_energy_max=float(e.max()),shared_gain=GAIN,per_waveform_gain=False,recorded_audio=False,neural_inference=False),y,x,a
