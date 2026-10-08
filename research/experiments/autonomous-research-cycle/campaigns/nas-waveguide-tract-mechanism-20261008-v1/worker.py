"""静的な圧力波と周波数行列、動的な正規化波、因果性、無入力エネルギーを照合。"""
import sys,json,math,os,tempfile
from pathlib import Path
here=Path(__file__).resolve().parent;sys.path.insert(0,str(here/'runtime-bundle'))
assert Path(tempfile.gettempdir()).resolve()==Path(os.environ['TMPDIR']).resolve()
import numpy as np
from waveguide_tract import render,tests,ah
RG=.75;RL=-.85;FS=48000.;SPEED=343.;N=24;T=8192
rng=np.random.default_rng(1067081)
def pressure_reference(x,A):
 # R=rho*c/A。rho*cは単位定数1として圧力↔正規化波を変換する。
 size=len(A);r=np.zeros(size);l=np.zeros(size);out=[];energy=[]
 for drive in x:
  out.append((1.+RL)*r[-1]*math.sqrt(A[-1]));nr=np.empty(size);nl=np.empty(size)
  nr[0]=drive/math.sqrt(A[0])+RG*l[0];nl[-1]=RL*r[-1]
  for j in range(size-1):
   # 独立に圧力連続/流量連続の式から求めた非正規化係数。
   R1=1./A[j];R2=1./A[j+1];k=(R2-R1)/(R1+R2)
   nr[j+1]=(1.+k)*r[j]-k*l[j+1];nl[j]=k*r[j]+(1.-k)*l[j+1]
  r=nr;l=nl;energy.append(float(np.sum(A*(r*r+l*l))))
 return np.array(out),np.array(energy)
def normalized_reference(x,areas):
 size=areas.shape[1];r=[0.]*size;l=[0.]*size;out=[];energy=[]
 for n,drive in enumerate(x):
  out.append((1.+RL)*r[-1]);nr=[0.]*size;nl=[0.]*size;nr[0]=drive+RG*l[0];nl[-1]=RL*r[-1]
  for j in range(size-1):
   k=(float(areas[n,j])-float(areas[n,j+1]))/(float(areas[n,j])+float(areas[n,j+1]));theta=math.asin(k)
   # sqrt演算と異なる回転表現で独立に計算。
   nr[j+1]=math.cos(theta)*r[j]-math.sin(theta)*l[j+1];nl[j]=math.sin(theta)*r[j]+math.cos(theta)*l[j+1]
  r=nr;l=nl;energy.append(sum(v*v for v in r)+sum(v*v for v in l))
 return np.array(out),np.array(energy)
def pressure_matrix(A):
 size=len(A);M=np.zeros((size*2,size*2));B=np.zeros(size*2);C=np.zeros(size*2)
 M[0,size]=RG;M[-1,size-1]=RL;B[0]=1./math.sqrt(A[0]);C[size-1]=(1.+RL)*math.sqrt(A[-1])
 for j in range(size-1):
  R1=1./A[j];R2=1./A[j+1];k=(R2-R1)/(R1+R2)
  M[j+1,j]=1.+k;M[j+1,size+j+1]=-k;M[size+j,j]=k;M[size+j,size+j+1]=1.-k
 return M,B,C
positions=(np.arange(N)+.5)/N
geometries=[np.ones(N),2.-1.8*np.exp(-.5*((positions-.25)/.09)**2),2.-1.8*np.exp(-.5*((positions-.75)/.09)**2),np.r_[np.full(N//2,.1),np.full(N//2,4.)]]
static=[];impulses={};wave_calls=0
for g,A in enumerate(geometries):
 for mode in ('impulse','noise'):
  x=np.zeros(T)
  if mode=='impulse':x[0]=1.
  else:x[:2048]=rng.normal(0.,.01,2048)
  area=np.tile(A,(T,1));before=(ah(x),ah(area));y,e=render(x,area);ref,er=pressure_reference(x,A);wave_calls+=2
  error=float(np.max(np.abs(y-ref)));energy_error=float(np.max(np.abs(e-er)));assert error<=1e-10 and energy_error<=1e-10
  assert before==(ah(x),ah(area));start=1 if mode=='impulse' else 2048
  assert np.max(np.diff(e[start:]))<=1e-10 and e[-1]<=e[start]+1e-10
  changed=x.copy();changed[4096:]+=.01;future=render(changed,area)[0];wave_calls+=1;assert np.array_equal(y[:4096],future[:4096])
  altered=area.copy();altered[4096:]=geometries[(g+1)%len(geometries)];future_shape=render(x,altered)[0];wave_calls+=1;assert np.array_equal(y[:4096],future_shape[:4096])
  if mode=='impulse':impulses[g]=y
  static.append(dict(geometry=g,driver=mode,output_max_error=error,energy_max_error=energy_error,unforced_energy_nonincreasing=True,input_and_future_area_prefix_exact=True,input_bytes_unchanged=True,output_sha256=ah(y)))
analytic=[]
for size in (8,16,24):
 x=np.zeros(T);x[0]=1.;expected=np.zeros(T);roundtrip=2*size
 for n in range(size,T,roundtrip):expected[n]=(1.+RL)*(RG*RL)**((n-size)//roundtrip)
 if size==24:y=impulses[0]
 else:y=render(x,np.ones((T,size)))[0];wave_calls+=1
 wave_calls+=1 # 解析応答列自体を保守的に生成として計上する。
 error=float(np.max(np.abs(y-expected)));assert error<=1e-12
 analytic.append(dict(sections=size,one_way_samples=size,roundtrip_samples=roundtrip,max_abs_error=error,first_three_resonances_Hz=[FS*(2*k+1)/(4*size) for k in range(3)],length_cm=SPEED*size/FS*100.))
frequency=[]
for g,A in enumerate(geometries):
 M,B,C=pressure_matrix(A);bins=np.arange(1,1025,2);omega=2*np.pi*bins/T;actual=np.fft.rfft(impulses[g])[bins]
 independent=np.array([C@np.linalg.solve(np.exp(1j*w)*np.eye(len(B))-M,B) for w in omega])
 error=float(np.max(np.abs(actual-independent)));assert error<=1e-9
 frequency.append(dict(geometry=g,bins=len(bins),maximum_complex_error=error,pressure_matrix_derived_from_continuity=True))
dynamic=[]
for mode in ('ramp','sine','step'):
 if mode=='ramp':weight=np.linspace(0.,1.,T)
 elif mode=='sine':weight=.5+.5*np.sin(2*np.pi*np.arange(T)/2048.)
 else:weight=(np.arange(T)>=2048).astype(float)
 area=(1.-weight[:,None])*geometries[1]+weight[:,None]*geometries[2]
 for source in ('impulse','noise'):
  x=np.zeros(T)
  if source=='impulse':x[0]=1.
  else:x[:2048]=rng.normal(0.,.01,2048)
  y,e=render(x,area);ref,er=normalized_reference(x,area);wave_calls+=2
  error=float(np.max(np.abs(y-ref)));energy_error=float(np.max(np.abs(e-er)));assert error<=1e-10 and energy_error<=1e-10
  start=1 if source=='impulse' else 2048;assert np.max(np.diff(e[start:]))<=1e-10
  future_area=area.copy();future_area[4096:]=1.;future=render(x,future_area)[0];wave_calls+=1;assert np.array_equal(y[:4096],future[:4096])
  dynamic.append(dict(mode=mode,driver=source,output_max_error=error,energy_max_error=energy_error,unforced_normalized_energy_nonincreasing=True,future_area_prefix_exact=True,
                      moving_wall_mechanical_work_modeled=False,normalized_state_not_physical_pressure_energy_under_geometry_changes=True,output_sha256=ah(y)))
bad=tests()
assert len(static)==8 and len(dynamic)==6 and len(frequency)==4 and wave_calls<=80
print(json.dumps(dict(passed=True,static_rows=static,analytic_uniform_rows=analytic,frequency_rows=frequency,dynamic_rows=dynamic,invalid_inputs=bad,
                     actual_valid_output_or_reference_calls=wave_calls,charged_render=80,charged_DSP=256,conservative_counts_not_returned=True,
                     geometry_fixtures_are_not_vowel_labels=True,phoneme_generation_qualified=False,real_Japanese_quality_qualified=False,perceptual_qualification=False)))
