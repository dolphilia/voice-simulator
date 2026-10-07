"""候補資格・内部不変・最低文数を共有して検査する。"""
import numpy as np


def invariant(before,after,correction):
    assert before['duration']==after['duration'] and before['msd']==after['msd'] and before['layout']==after['layout']
    assert before['means'][0]==after['means'][0] and before['means'][2]==after['means'][2]
    assert all(a[1:]==b[1:] for a,b in zip(before['means'][1],after['means'][1]))
    delta=np.asarray(correction,dtype=float)
    assert delta.shape==(len(before['duration']),) and np.isfinite(delta).all() and np.max(abs(delta))<=3.
    for i,value in enumerate(delta):
        if value==0:assert before['means'][1][i]==after['means'][1][i]
        else:
            assert before['msd'][i]>.5
            assert abs(after['means'][1][i][0]-(before['means'][1][i][0]+value*np.log(2)/12))<1e-12
    return True


def qualify(native,state,candidate):
    if not all(r.get('status')=='completed' for r in (native,state,candidate)):return {'qualified':False,'reason':'保存候補が欠損'}
    diff={f:candidate['measurement'][f]/native['measurement'][f]-1 for f in ('f0_hz','dio_f0_hz','active_seconds')}
    coefficients=np.asarray(candidate['coefficients'],dtype=float)
    checks={'wave_below_native':candidate['wave_mse']<native['wave_mse'],
        'wave_at_most_statefit':candidate['wave_mse']<=state['wave_mse'],
        'global_f0':all(abs(diff[f])<=.05 for f in ('f0_hz','dio_f0_hz')),'active_duration':abs(diff['active_seconds'])<=.03,
        'support_E0_internal':all(all(r.get(k) for k in ('support_complete','E0_pass','internal_unchanged')) for r in (native,state,candidate)),
        'coefficient_bound':coefficients.shape==(4,) and np.isfinite(coefficients).all() and np.max(abs(coefficients))<=3,
        'half_tone_bound':candidate['maximum_abs_half_tone']<=3.,
        'regularized_objective_below_native':np.isfinite(candidate['objective']) and candidate['objective']<native['objective']}
    checks={k:bool(v) for k,v in checks.items()}
    return {'qualified':all(checks.values()),'checks':checks,'relative_to_native':diff}


def select(native,state,wave):
    choices=[(v,r,qualify(native,state,r)) for v,r in [('wavefit',wave),('statefit',state)]]
    valid=[x for x in choices if x[2]['qualified']]
    return min(valid,key=lambda x:x[1]['objective']) if valid else None


def enough(rows):
    return len(rows)>=12 and {r['length'] for r in rows}=={'short','long'}


def tests():
    n={'status':'completed','wave_mse':2.,'objective':2.,'measurement':{'f0_hz':200.,'dio_f0_hz':200.,'active_seconds':1.},
        'support_complete':True,'E0_pass':True,'internal_unchanged':True,'coefficients':[0]*4,'maximum_abs_half_tone':0.}
    s={**n,'wave_mse':1.,'objective':1.1};w={**s,'wave_mse':.9,'objective':1.}
    assert select(n,s,w)[0]=='wavefit' and select(n,s,{**w,'objective':1.2})[0]=='statefit'
    assert select(n,s,{**w,'objective':1.1})[0]=='wavefit'
    bad=[{**w,'support_complete':False},{**w,'coefficients':[4]*4},{**w,'maximum_abs_half_tone':3.1},
        {**w,'measurement':{**n['measurement'],'f0_hz':220.}},{**w,'objective':2.},{**w,'wave_mse':2.}]
    assert all(not qualify(n,s,r)['qualified'] for r in bad)
    assert not enough([{'length':'short'}]*12) and not enough([{'length':'short'}]*10+[{'length':'long'}])
    assert enough([{'length':'short'}]*10+[{'length':'long'}]*2)
    return {'selection_actual_wave_positive':True,'tie_prefers_wavefit':True,'candidate_negative_cases':len(bad),
        'insufficient_or_single_length_rejected':True,'generation_calls':0,'ai_calls':0,'shared_fits':0}

if __name__=='__main__':print(tests())
