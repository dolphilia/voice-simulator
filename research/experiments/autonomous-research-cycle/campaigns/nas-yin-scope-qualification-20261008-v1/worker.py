"""出力前固定した人工条件を生成し、全件・全分母を保持する。"""
import sys,json,hashlib,os,tempfile
from pathlib import Path
here=Path(__file__).resolve().parent;assert Path(tempfile.gettempdir()).resolve()==Path(os.environ['TMPDIR']).resolve()
sys.path.insert(0,str(here))
import numpy as np
from scipy import signal
from yin_style import difference,estimate,FS,FMIN
def sha(a):return hashlib.sha256(np.ascontiguousarray(a,dtype=np.float64).tobytes()).hexdigest()
def independent(x):
    maximum=int(FS/FMIN);width=len(x)-maximum;d=[0.]
    for lag in range(1,maximum+1):d.append(sum((float(x[j])-float(x[j+lag]))**2 for j in range(width)))
    c=[1.];total=0.
    for lag in range(1,len(d)):
        total+=d[lag];c.append(d[lag]*lag/total if total>0 else 1.)
    return np.array(d),np.array(c)
rng=np.random.default_rng(1050050);mechanism=[]
for name in ('zeros','DC','impulse','noise','sine','harmonic'):
    n=960;t=np.arange(n)/FS
    if name=='zeros':x=np.zeros(n)
    elif name=='DC':x=np.ones(n)*.3
    elif name=='impulse':x=np.zeros(n);x[17]=1.
    elif name=='noise':x=rng.normal(0.,.1,n)
    elif name=='sine':x=.2*np.sin(2*np.pi*220*t)
    else:x=.1*np.sin(2*np.pi*440*t)+.08*np.sin(2*np.pi*660*t)
    d,c,w=difference(x);di,ci=independent(x);de=float(np.max(np.abs(d-di))/max(float(np.max(di)),1e-12));ce=float(np.max(np.abs(c-ci)))
    assert de<=1e-12 and ce<=1e-12;mechanism.append(dict(name=name,input_sha256=sha(x),relative_difference_error=de,CMND_absolute_error=ce,passed=True))
rows=[]
def record(x,group,window,phase,truth,**meta):
    before=sha(x);out=estimate(x);assert sha(x)==before
    error=None if out['hz'] is None or truth is None else float(12*np.log2(out['hz']/truth))
    if group in ('static','dynamic'):passed=out['hz'] is not None and abs(error)<=.5
    else:passed=out['hz'] is None
    rows.append(dict(id=len(rows),group=group,window_ms=window,phase=phase,truth_hz=truth,input_sha256=before,samples=len(x),output=out,error_semitones=error,passed=passed,**meta))
def harmonics(phase,missing=False):
    return sum(np.sin(k*phase)/k for k in range(2 if missing else 1,9))*.2
for window in (20,40,80):
    n=round(FS*window/1000);t=np.arange(n)/FS
    for hz in (80.,110.,160.,220.,280.,350.,400.):
        for form in ('sine','harmonic','missing_fundamental','DC_offset','noise20dB'):
            for phase in (0.,np.pi/3,1.7):
                p=2*np.pi*hz*t+phase
                if form=='sine':x=.2*np.sin(p)
                elif form=='harmonic':x=harmonics(p)
                elif form=='missing_fundamental':x=harmonics(p,True)
                elif form=='DC_offset':x=.2*np.sin(p)+.4
                else:
                    clean=harmonics(p);noise=rng.normal(0.,1.,n);noise*=np.sqrt(np.mean(clean**2)/100./np.mean(noise**2));x=clean+noise
                record(x,'static',window,float(phase),hz,form=form)
    centered=(np.arange(n)-(n-1)/2)/FS
    for hz in (80.,160.,280.,400.):
        for slope in (-24.,-6.,6.,24.):
            k=np.log(2)*slope/12.;base=2*np.pi*hz*np.expm1(k*centered)/k
            for form in ('sine','missing_fundamental'):
                for phase in (0.,np.pi/3,1.7):
                    p=base+phase;x=.2*np.sin(p) if form=='sine' else harmonics(p,True)
                    record(x,'dynamic',window,float(phase),hz,form=form,slope_semitones_per_second=slope,
                        reference_sample_center=(n-1)/2,truth_kind='解析位相導関数の窓中央音響周波数。知覚truthではない。')
    for hz in (110.,280.):
        for form in ('sine','missing_fundamental'):
            for edge in ('onset','offset'):
                for fraction in (.125,.5,.875):
                    for phase in (0.,np.pi/3,1.7):
                        p=2*np.pi*hz*t+phase;x=.2*np.sin(p) if form=='sine' else harmonics(p,True)
                        count=round(n*fraction);mask=np.arange(n)>=n-count if edge=='onset' else np.arange(n)<count;x=x*mask
                        record(x,'boundary',window,float(phase),None,form=form,edge=edge,voiced_fraction=fraction,segment_frequency_hz=hz,
                            truth_kind='窓全体の周期truthなし。境界で推定保留できるかを全件判定し、部分有声Hzを窓全体truthへ転用しない。')
    for form in ('silence','DC','white_noise','lowpass_noise'):
        for seed in (105001,105002,105003):
            local=np.random.default_rng(seed)
            if form=='silence':x=np.zeros(n)
            elif form=='DC':x=np.full(n,.3)
            elif form=='white_noise':x=local.normal(0.,.1,n)
            else:x=signal.lfilter(*signal.butter(2,1000.,fs=FS),local.normal(0.,.1,n))
            record(x,'unvoiced',window,None,None,form=form,seed=seed)
assert len(rows)==855 and len(mechanism)==6
print(json.dumps(dict(rows=rows,mechanism=mechanism,render=861,dsp=867,counts=dict(static=315,dynamic=288,boundary=216,unvoiced=36,mechanism_signals=6,mechanism_DSP=12),
    render_is_artificial_not_speech=True,quality_certified=False),ensure_ascii=False,allow_nan=False))
