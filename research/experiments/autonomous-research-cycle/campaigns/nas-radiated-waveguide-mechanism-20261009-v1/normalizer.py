"""元LFの積分形の平均と分散を解析原始関数/独立積分で固定する。"""
import sys,json,math,cmath
from pathlib import Path
from scipy.integrate import quad
here=Path(sys.argv[1]);tp,te,ta,ep,a,e0,scale=map(float,json.loads((here/'lf-coefficients.json').read_text()));w=math.pi/tp
def g(t):
 opened=lambda u:scale*e0/(a*a+w*w)*(math.exp(a*u)*(a*math.sin(w*u)-w*math.cos(w*u))+w)
 if t<=te:return opened(t)
 v=t-te;return opened(te)-scale/(ep*ta)*((1-math.exp(-ep*v))/ep-math.exp(-ep*(1-te))*v)
def integrate(f):return sum(quad(f,lo,hi,epsabs=2e-12,epsrel=2e-12)[0] for lo,hi in [(0.,te),(te,1.)])
mean=integrate(g);variance=integrate(lambda t:(g(t)-mean)**2);std=math.sqrt(variance);assert abs(g(0))<2e-12 and abs(g(1))<2e-12 and std>0
def coefficient(m):
 omega=2*math.pi*m;length=1-te;z1=complex(a,w-omega);z2=complex(a,-w-omega)
 opened=e0*((cmath.exp(z1*te)-1.)/z1-(cmath.exp(z2*te)-1.)/z2)/(2j)
 returning=-(cmath.exp(-1j*omega*te)*(1.-cmath.exp(-complex(ep,omega)*length))/complex(ep,omega)-math.exp(-ep*length)*(cmath.exp(-1j*omega*te)-cmath.exp(-1j*omega))/(1j*omega))/(ep*ta)
 return scale*(opened+returning)
rows=[]
for m in (1,3,7,30,72):
 ref=complex(integrate(lambda t:(g(t)-mean)/std*math.cos(2*math.pi*m*t)),integrate(lambda t:-(g(t)-mean)/std*math.sin(2*math.pi*m*t)))
 error=abs(ref-coefficient(m)/(2j*math.pi*m*std));assert error<5e-11;rows.append(dict(harmonic=m,error=error))
power=2*sum(abs(coefficient(m)/(2j*math.pi*m*std))**2 for m in range(1,4097));assert abs(power-1)<1e-10
print(json.dumps(dict(mean=mean,variance=variance,standard_deviation=std,mean_removed=True,global_continuous_RMS=1.,per_wave_or_F0_or_truncation_normalization=False,quadrature_rows=rows,parseval_4096_power=power,physical_glottal_volume_velocity=False)))
