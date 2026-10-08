"""音素内の生成LF0補完と絶対校正。保存波形・発話IDは参照しない。"""
import re
import numpy as np
from calibration import calibrated_lf0
ELIGIBLE={'a','i','u','e','o','N','m','n','my','ny','r','ry','w','y'}
METHODS={'native':(False,1.),'calibrated':(False,1.),'voicing':(True,1.),
         'aperiodicity':(False,.5),'combined':(True,.5)}

def fill_lf0(lf0, labels, duration):
    x=np.asarray(lf0)
    d=np.asarray(duration)
    if x.ndim!=2 or x.shape[1]!=1 or not len(x) or not np.isfinite(x).all():
        raise ValueError('有限の非空LF0 Nx1が必要')
    if d.ndim!=1 or len(d)!=len(labels)*5 or not np.isfinite(d).all() or np.any(d<1) or np.any(d!=np.round(d)) or int(d.sum())!=len(x):
        raise ValueError('音素5状態の整数durationとLF0フレームが一致する必要')
    voiced=x[:,0]>0
    assert np.array_equal(voiced,x[:,0]>-1e9)
    y=x.copy();bounds=np.r_[0,np.cumsum(d)].astype(int);changed=[];intervals=[]
    for i,label in enumerate(labels):
        match=re.search(r'\-([^+]+)\+',label)
        if match is None: raise ValueError('音素ラベルの形式が不正')
        phone=match.group(1);start,end=bounds[i*5],bounds[(i+1)*5]
        local=np.arange(start,end);indices=local[voiced[start:end]]
        eligible=phone in ELIGIBLE and len(indices)>=3
        added=local[~voiced[start:end]] if eligible else np.array([],dtype=int)
        if len(added):
            y[added,0]=np.interp(added,indices,x[indices,0])
            changed.extend(int(k) for k in added)
        intervals.append(dict(index=i,phone=phone,native_voiced_frames=len(indices),
            frames=int(end-start),eligible=eligible,filled_frames=len(added)))
    assert y[voiced].tobytes()==x[voiced].tobytes()
    assert np.array_equal(np.flatnonzero((y[:,0]>0)&~voiced),np.asarray(changed,dtype=int))
    return y,dict(filled_frames=len(changed),filled_frame_indices=changed,intervals=intervals,
                  rule_uses_generated_parameters_only=True)

def transform(method, native, labels, duration, pitch):
    if method not in METHODS: raise ValueError('未登録の方式')
    fill,factor=METHODS[method];params=[v.copy() for v in native]
    original=params[1].copy();voiced=original[:,0]>0
    detail=dict(filled_frames=0,filled_frame_indices=[],intervals=[])
    if fill: params[1],detail=fill_lf0(params[1],labels,duration)
    before=params[1].copy()
    control=dict(log_shift=0.,native_generated_log_median=float(np.median(before[before[:,0]>0,0])),waveform_pitch_verified=False)
    if method!='native': params[1],control=calibrated_lf0(before,pitch)
    error=(params[1][voiced,0]-np.median(params[1][voiced,0]))-(original[voiced,0]-np.median(original[voiced,0]))
    relative=float(np.max(abs(error)))
    unfilled=(~voiced)&(before[:,0]<=0)
    valid=(relative<=2e-15 and params[1][unfilled].tobytes()==original[unfilled].tobytes()
           and np.array_equal(params[0],native[0]) and np.array_equal(params[2],native[2])
           and (fill or np.array_equal(params[1][:,0]>0,voiced)))
    assert valid
    control.update(fill_enabled=fill,fill=detail,AP_noise_power_factor=factor,
                   original_voiced_contour_preserved=True,unfilled_sentinel_preserved=True)
    return params,control,relative,bool(valid)

def ap_noise_power(f0, power, ap, factor):
    if factor not in [1.,.5]: raise ValueError('登録済みAP係数のみ許可')
    if len(f0)!=len(ap) or power.shape!=ap.shape or ap.ndim!=2:
        raise ValueError('WORLD配列の形状不一致')
    if not np.isfinite(ap).all() or np.any(ap<=0) or np.any(ap>1):
        raise ValueError('AP振幅が不正')
    if factor==1.: return ap
    result=ap.copy();mask=f0>0
    result[mask]=np.maximum(.001,result[mask]*np.sqrt(factor))
    assert result[~mask].tobytes()==ap[~mask].tobytes()
    return result
