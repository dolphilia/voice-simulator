"""既知手続き的信号の回復判定。音声の自然さや発音の判定ではない。"""
import numpy as np
LIMITS={'missing_rate':.10,'median_abs_semitone_error':.5,'gross_error_rate':.05,'false_voiced_rate':.10,'boundary_error_seconds':.03}


def segments(mask,times,step=.005):
    indices=np.flatnonzero(mask)
    if not len(indices):return []
    splits=np.split(indices,np.flatnonzero(np.diff(indices)>1)+1)
    return [{'start':float(times[g[0]]),'end':float(times[g[-1]]+step),'indices':g.tolist()} for g in splits]


def evaluate(row,f0,times):
    f0=np.asarray(f0,dtype=float);times=np.asarray(times,dtype=float)
    if f0.ndim!=1 or times.shape!=f0.shape or not len(f0) or not np.isfinite(f0).all() or not np.isfinite(times).all() or np.any(f0<0) or np.any(np.diff(times)<=0):
        raise ValueError('F0と時刻は有限・固定形状・単調な一次元配列にします')
    if np.any(times<0) or times[-1]>row['seconds']+1e-9 or not np.allclose(np.diff(times),.005,atol=1e-10,rtol=0):
        raise ValueError('時刻は契約の5ms格子と信号長に一致させます')
    truth_voiced=np.zeros(len(times),dtype=bool)
    for a,b in row['voiced_intervals']:truth_voiced|=(times>=a)&(times<b)
    borders=np.array(row['voiced_intervals']).flatten()
    away=np.min(abs(times[:,None]-borders),axis=1)>=.05-1e-12
    interior=truth_voiced&away
    detected=(f0>=70)&(f0<=800)
    invalid=(f0>0)&~detected
    base,end=row['f0_endpoints_hz'];reference=base+(end-base)*times/row['seconds']
    valid=interior&detected
    errors=abs(12*np.log2(f0[valid]/reference[valid]))
    missing=float(np.mean(~detected[interior])) if interior.any() else None
    median=float(np.median(errors)) if len(errors) else None
    gross=float(np.mean(errors>1)) if len(errors) else None
    false=float(np.mean(f0[~truth_voiced]>0)) if (~truth_voiced).any() else None
    runs=segments(detected,times);boundaries=[]
    for a,b in row['voiced_intervals']:
        overlap=[(min(b,r['end'])-max(a,r['start']),i,r) for i,r in enumerate(runs) if min(b,r['end'])>max(a,r['start'])]
        if not overlap:boundaries.append({'truth_start':a,'truth_end':b,'missing_interval':True});continue
        _,i,r=max(overlap,key=lambda x:(x[0],-x[1]))
        boundaries.append({'truth_start':a,'truth_end':b,'missing_interval':False,'observed_start':r['start'],'observed_end':r['end'],
            'start_error':abs(r['start']-a),'end_error':abs(r['end']-b),'matched_run':i})
    checks={'missing_rate':missing is not None and missing<=.10,
        'median_abs_semitone_error':median is not None and median<=.5,'gross_error_rate':gross is not None and gross<=.05,
        'false_voiced_rate':false is not None and false<=.10,
        'boundaries':all(not b['missing_interval'] and max(b['start_error'],b['end_error'])<=.03+1e-12 for b in boundaries),
        'finite_complete_valid_range':not invalid.any() and bool(interior.any())}
    return {'missing_rate':missing,'median_abs_semitone_error':median,'gross_error_rate':gross,'false_voiced_rate':false,
        'interior_truth_voiced_frames':int(interior.sum()),'detected_interior_frames':int(valid.sum()),'truth_unvoiced_frames':int((~truth_voiced).sum()),
        'out_of_range_frames':int(invalid.sum()),'boundaries':boundaries,'detected_runs':runs,
        'checks':checks,'passed':all(checks.values()),'absolute_semitone_errors':errors.tolist()}


def aggregate(rows,expected=12):
    complete=[r for r in rows if r['status']=='completed']
    passed=[r for r in complete if r['metrics']['passed']]
    return {'expected_cases':expected,'completed_cases':len(complete),'passed_cases':len(passed),
        'all_passed':len(rows)==len(complete)==len(passed)==expected,
        'failed_cases':[{'id':r['id'],'checks':r.get('metrics',{}).get('checks',{}),'status':r['status']} for r in rows if r['status']!='completed' or not r['metrics']['passed']],
        'worst_gross_error_rate':max((r['metrics']['gross_error_rate'] for r in complete if r['metrics']['gross_error_rate'] is not None),default=None)}


def choose(development):
    eligible=[name for name,summary in development.items() if summary['all_passed']]
    if not eligible:return None
    return min(eligible,key=lambda name:(development[name]['worst_gross_error_rate'],0 if name=='dio' else 1))


def tests():
    row={'seconds':1.2,'voiced_intervals':[[.1,.5],[.7,1.1]],'f0_endpoints_hz':[180.,180.]}
    t=np.arange(241)*.005;truth=np.zeros(len(t),bool)
    for a,b in row['voiced_intervals']:truth|=(t>=a)&(t<b)
    f=np.where(truth,180.,0.);assert evaluate(row,f,t)['passed']
    cases=[np.zeros(len(t)),np.where(truth,360.,0.),np.full(len(t),180.)]
    for case in cases:assert not evaluate(row,case,t)['passed']
    delayed=np.zeros(len(t))
    for a,b in row['voiced_intervals']:delayed[(t>=a+.04)&(t<b+.04)]=180.
    assert not evaluate(row,delayed,t)['checks']['boundaries']
    rejected=0
    for values,tt in [(np.full(len(t),np.nan),t),(f,t[:-1]),(f,np.zeros(len(t)))]:
        try:evaluate(row,values,tt)
        except ValueError:rejected+=1
    assert rejected==3
    good={'id':'fixture','status':'completed','metrics':evaluate(row,f,t)}
    assert aggregate([good],1)['all_passed'] and not aggregate([],1)['all_passed']
    assert not aggregate([good,{'id':'missing','status':'missing'}],2)['all_passed']
    assert choose({'dio':aggregate([good],1),'harvest':aggregate([good],1)})=='dio'
    assert choose({'dio':aggregate([],1),'harvest':aggregate([],1)}) is None
    return {'positive_exact_recovery':True,'negative_missing_octave_false_voice_boundary_cases':4,'invalid_inputs_rejected':3,
        'empty_missing_selection_rejected':True,'tie_prefers_existing_dio':True,'new_render_calls':0,'new_ai_calls':0}
