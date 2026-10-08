"""事前固定の5ms時計で既知周期を検査。既存音声は診断だけに使う。"""
import numpy as np
import pyworld
from acoustics import estimate_f0
FS=24000
def frame_acf(audio):
    times=np.arange(len(audio)//120+1)*.005;values=np.zeros(len(times));confidence=np.zeros(len(times))
    for i,t in enumerate(times):
        center=round(t*FS);start=center-720;stop=start+1440
        if start<0 or stop>len(audio):continue
        hz,score=estimate_f0(audio[start:stop],FS,minimum=70,maximum=800)
        confidence[i]=float(score)
        if hz is not None and score>=.6:values[i]=float(hz)
    return values,times,confidence
def legacy_acf(audio):
    rms=np.array([np.sqrt(np.mean(audio[i:i+240].astype(float)**2)) for i in range(0,len(audio),240)])
    active=np.flatnonzero(rms>max(1e-5,.05*rms.max()))
    return estimate_f0(audio[active[0]*240:min(len(audio),(active[-1]+1)*240)],FS,minimum=70,maximum=800) if len(active) else (None,0.)
def trackers(audio):
    x=np.ascontiguousarray(audio,dtype=np.float64)
    f,t=pyworld.dio(x,FS,f0_floor=70.,f0_ceil=800.,frame_period=5.)
    f=pyworld.stonemask(x,f,t,FS)
    h,ht=pyworld.harvest(x,FS,f0_floor=70.,f0_ceil=800.,frame_period=5.)
    a,at,confidence=frame_acf(x)
    hz,score=legacy_acf(x)
    return dict(dio=(f,t),harvest=(h,ht),centered_acf=(a,at)),dict(hz=hz,confidence=float(score),accepted=bool(hz is not None and score>=.6)),confidence
def score_track(values,times,truth):
    accepted=(values>=70)&(values<=800)
    if truth['voiced']:
        core=(times>=truth['core_start'])&(times<truth['core_end'])
        unvoiced=(times<truth['voiced_start']-.02)|(times>=truth['voiced_end']+.02)
        target=truth['f0'];errors=np.full(len(values),np.inf)
        errors[accepted]=np.abs(12*np.log2(values[accepted]/target))
        correct=core&accepted&(errors<=1.)
        selected=values[core&accepted]
        median_error=float(abs(12*np.log2(np.median(selected)/target))) if len(selected) else None
        coverage=float(correct.sum()/core.sum()) if core.any() else 0.
        passed=bool(core.sum()>=3 and correct.sum()>=3 and coverage>=.9 and median_error is not None and median_error<=1.)
    else:
        core=np.zeros(len(values),bool);unvoiced=np.ones(len(values),bool);coverage=None;median_error=None;passed=False
    boundary=~(core|unvoiced)
    return dict(core_frames=int(core.sum()),correct_core_frames=int(correct.sum()) if truth['voiced'] else 0,coverage=coverage,median_error_semitones=median_error,core_pass=passed,unvoiced_frames=int(unvoiced.sum()),false_voiced_frames=int((accepted&unvoiced).sum()),boundary_frames=int(boundary.sum()),boundary_voiced_frames=int((accepted&boundary).sum()))
def global_score(value,truth):
    error=float(abs(12*np.log2(value['hz']/truth['f0']))) if truth['voiced'] and value['accepted'] else None
    return dict(hz=value['hz'],confidence=value['confidence'],accepted=value['accepted'],error_semitones=error,core_pass=bool(truth['voiced'] and error is not None and error<=1.),negative_false_accept=bool(not truth['voiced'] and value['accepted']),support_qualification=False)
def local(values,times,duration,indices):
    bounds=np.r_[0,np.cumsum(duration)]*.005;rows=[]
    for index in indices:
        mask=(times>=bounds[index*5])&(times<bounds[(index+1)*5]);accepted=values[mask&(values>=70)&(values<=800)];n=int(mask.sum())
        rows.append(dict(index=int(index),interval_frames=n,voiced_frames=len(accepted),support_complete=bool(n>0 and len(accepted)>=3 and len(accepted)>=n*.5),median_hz=float(np.median(accepted)) if len(accepted) else None))
    return rows
