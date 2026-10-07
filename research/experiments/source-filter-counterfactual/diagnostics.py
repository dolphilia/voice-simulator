"""固定区間のDIOと駆動LF0を対照する非学習診断。"""
import numpy as np
from campaign import PILOT,BUNDLE
import sys
sys.path.insert(0,str(PILOT/'.cache/packages'));import pyworld
sys.path.insert(0,str(BUNDLE))
from acoustics import evaluate,estimate_f0
from acoustic_control import measure_wide


def local(f0,times,lf0,duration,indices):
    bounds=np.r_[0,np.cumsum(duration)]*.005;out=[]
    for index in indices:
        lo,hi=bounds[index*5],bounds[(index+1)*5]
        mask=(times>=lo)&(times<hi);v=mask&(f0>=70)&(f0<=800)
        gt=np.arange(len(lf0))*.005;gm=(gt>=lo)&(gt<hi)
        known=gm&(lf0>=np.log(70))&(lf0<=np.log(800))&np.isfinite(lf0)
        tick=np.rint(times/.005).astype(int);valid=(tick>=0)&(tick<len(lf0))
        ref=np.full(len(times),-1e10);ref[valid]=lf0[tick[valid]]
        refv=valid&(ref>=np.log(70))&(ref<=np.log(800));pair=v&refv
        error=np.abs((np.log(f0[pair])-ref[pair])*12/np.log(2))
        n=int(mask.sum());count=int(v.sum())
        out.append({'index':int(index),'interval_frames':n,'dio_voiced_frames':count,'dio_voiced_fraction':count/n if n else None,
            'support_complete':n>0 and count>=3 and count>=n*.5,
            'generated_lf0_voiced_frames':int(known.sum()),'generated_lf0_interval_frames':int(gm.sum()),
            'dio_median_hz':float(np.median(f0[v])) if count else None,
            'generated_lf0_median_hz':float(np.exp(np.median(lf0[known]))) if known.any() else None,
            'paired_frames':int(pair.sum()),'median_abs_half_tone_error':float(np.median(error)) if len(error) else None,
            'over_one_half_tone_frames':int((error>1).sum()),
            'lf0_voiced_dio_missing_frames':int((mask&refv&~v).sum()),'lf0_unvoiced_dio_voiced_frames':int((v&~refv).sum())})
    return out


def measure(audio,lf0,duration,support,focus):
    f0,t=pyworld.dio(audio.astype(float),24000,f0_floor=70.,f0_ceil=800.,frame_period=5.)
    f0=pyworld.stonemask(audio.astype(float),f0,t,24000)
    indices=sorted(set(support)|set(focus));rows=local(f0,t,lf0,duration,indices)
    try:wide=measure_wide(audio)
    except ValueError as exc:
        value,confidence=estimate_f0(audio,24000,minimum=70,maximum=800)
        wide={'f0_hz':value,'confidence':confidence,'diagnostic_error':str(exc),'active_seconds':None}
    return {'local':rows,'missing_support':[r['index'] for r in rows if r['index'] in support and not r['support_complete']],
        'global_acf':wide,'dio_median_hz':float(np.median(f0[f0>0])) if (f0>0).any() else None,
        'dio_voiced_fraction':float(np.mean(f0>0)),'E0':evaluate(audio,{},24000),'f0':f0,'times':t}


def tests():
    times=np.arange(6)*.005;lf0=np.full(5,np.log(220));f0=np.full(6,220.)
    result=local(f0,times,lf0,[1]*5,[0])[0];assert result['support_complete'] and result['paired_frames']==5
    f0[:3]=0;result=local(f0,times,lf0,[1]*5,[0])[0];assert not result['support_complete'] and result['lf0_voiced_dio_missing_frames']==3
    return {'fixed_50_percent_and_three_frames_preserved':True,'missing_not_removed_from_diagnostic':True,'new_render_or_estimations':0}
