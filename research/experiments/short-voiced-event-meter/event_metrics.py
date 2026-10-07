"""全音素・既知有声域・端の量を混ぜない固定計測。"""
import numpy as np
LIMITS={'missing_rate':.10,'median_abs_half_tone_error':.5,'over_one_half_tone_rate':.05,'false_voiced_rate':.10,'boundary_error_seconds':.01}


def runs(mask):
    mask=np.asarray(mask,dtype=bool);change=np.diff(np.r_[False,mask,False].astype(int))
    return [[int(a),int(b)] for a,b in zip(np.flatnonzero(change==1),np.flatnonzero(change==-1))]


def grid(f0,times,frames):
    f0=np.asarray(f0,dtype=float);times=np.asarray(times,dtype=float)
    if f0.ndim!=1 or times.shape!=f0.shape or not len(f0) or not np.isfinite(f0).all() or not np.isfinite(times).all() or (f0<0).any() or (np.diff(times)<=0).any():
        raise ValueError('F0・時刻は非空・有限・同形・単調な一次元配列を要求します')
    if times[0]<0 or times[-1]>frames*.005+1e-8:raise ValueError('時刻が信号範囲外です')
    ticks=np.rint(times/.005).astype(int);aligned=abs(times-ticks*.005)<=1e-8
    valid=aligned&(ticks>=0)&(ticks<frames)
    if len(np.unique(ticks[valid]))!=valid.sum():raise ValueError('同じ格子点への重複観測を拒否します')
    out=np.full(frames,np.nan);out[ticks[valid]]=f0[valid]
    return out,{'off_grid_observations':int((~aligned).sum()),'missing_grid_frames':int(np.isnan(out).sum()),'input_observations':len(times)}


def coverage(values,known,reference):
    values=np.asarray(values,dtype=float);known=np.asarray(known,dtype=bool);reference=np.asarray(reference,dtype=float)
    if not(len(values)==len(known)==len(reference)) or known.ndim!=1 or not known.any():raise ValueError('非空の固定有声域を要求します')
    detected=np.isfinite(values)&(values>=70)&(values<=800);pair=known&detected
    err=abs(12*np.log2(values[pair]/reference[pair]))
    unvoiced=~known
    return {'known_voiced_frames':int(known.sum()),'detected_known_voiced_frames':int(pair.sum()),
        'missing_known_voiced_frames':int((known&~detected).sum()),'missing_rate':float(np.mean(~detected[known])),
        'median_abs_half_tone_error':float(np.median(err)) if len(err) else None,
        'over_one_half_tone_rate':float(np.mean(err>1)) if len(err) else None,
        'known_unvoiced_frames':int(unvoiced.sum()),'false_voiced_frames':int((unvoiced&np.isfinite(values)&(values>0)).sum()),
        'false_voiced_rate':float(np.mean(np.isfinite(values[unvoiced])&(values[unvoiced]>0))) if unvoiced.any() else None,
        'errors_half_tones':err.tolist()}


def evaluate(row,f0,times):
    values,detail=grid(f0,times,row['duration_frames']);n=len(values);idx=np.arange(n)
    known=(idx>=row['event_start_frame'])&(idx<row['event_end_frame'])
    ref=np.full(n,row['f0_hz']);stats=coverage(values,known,ref)
    detected=np.isfinite(values)&(values>=70)&(values<=800)
    whole=detected[row['target_start_frame']:row['target_end_frame']];expected=int(known.sum())
    region=(idx>=row['target_start_frame']-10)&(idx<row['target_end_frame']+10)
    events=runs(detected&region);positions=np.flatnonzero(detected&region)
    if len(positions):
        begin,end=positions[0]*.005,(positions[-1]+1)*.005
        boundary={'missing':False,'observed_start_seconds':float(begin),'observed_end_seconds':float(end),
            'start_error_seconds':float(abs(begin-row['event_start_frame']*.005)),
            'end_error_seconds':float(abs(end-row['event_end_frame']*.005))}
    else:boundary={'missing':True,'start_error_seconds':None,'end_error_seconds':None}
    invalid=np.isfinite(values)&(values>0)&~detected
    checks={key:stats[key] is not None and stats[key]<=limit+1e-12 for key,limit in LIMITS.items() if key!='boundary_error_seconds'}
    checks['boundaries']=not boundary['missing'] and max(boundary['start_error_seconds'],boundary['end_error_seconds'])<=.01+1e-12
    checks['complete_finite_grid']=detail['missing_grid_frames']==0 and detail['off_grid_observations']==0 and not invalid.any()
    return {'voiced_core':stats,'whole_phone':{'known_occupancy':expected/24,'observed_occupancy':float(np.mean(whole)),
        'observed_voiced_frames':int(whole.sum()),'interval_frames':24,'original_50_percent_pass':bool(whole.sum()>=3 and whole.sum()>=12),
        'perfect_recovery_50_percent_pass':expected>=12},'boundary':boundary,'grid':detail,
        'observed_event_runs':events,'event_run_count':len(events),'out_of_range_frames':int(invalid.sum()),
        'checks':checks,'passed':all(checks.values()),'quality_certified':False}


def aggregate(records,expected=12):
    complete=[r for r in records if r['status']=='completed'];passed=[r for r in complete if r['metrics']['passed']]
    return {'expected':expected,'completed':len(complete),'passed':len(passed),
        'all_passed':bool(records) and len(records)==len(complete)==len(passed)==expected,
        'failed':[{'id':r['id'],'status':r['status'],'checks':r.get('metrics',{}).get('checks',{})} for r in records if r['status']!='completed' or not r['metrics']['passed']]}


def tests(row):
    row={**row,'event_start_frame':96,'event_end_frame':107,'expected_driving_voiced_frames':11}
    t=np.arange(241)*.005;f=np.zeros(241);f[96:107]=row['f0_hz'];good=evaluate(row,f,t)
    assert good['passed'] and not good['whole_phone']['original_50_percent_pass'] and good['voiced_core']['known_voiced_frames']==11
    for bad in [np.zeros(241),f*2,np.full(241,row['f0_hz']),np.roll(f,3)]:assert not evaluate(row,bad,t)['passed']
    shifted=t.copy();shifted[100]+=1e-6;off=evaluate(row,f,shifted);assert not off['passed'] and off['grid']['off_grid_observations']==1 and off['voiced_core']['missing_known_voiced_frames']==1
    for values,tt in [(f[:-1],t),(np.full(241,np.nan),t),(f,np.zeros(241))]:
        try:evaluate(row,values,tt)
        except ValueError:pass
        else:raise AssertionError('不正な計測入力を拒否しません')
    one={'id':'fixture','status':'completed','metrics':good}
    assert aggregate([one],1)['all_passed'] and not aggregate([],1)['all_passed'] and not aggregate([one,{'id':'missing','status':'missing'}],2)['all_passed']
    return {'known_11_frames_recover_even_when_whole_phone_50_percent_rejects':True,
        'missing_octave_false_voice_delayed_offgrid_rejected':True,'invalid_input_cases':3,
        'empty_missing_aggregate_rejected':True,'new_render_or_estimations':0}
