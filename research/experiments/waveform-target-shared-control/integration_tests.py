"""合成を呼ばず探索制御の停止・片側差分・縮小枠を検査する。"""
import numpy as np
from inverse import Search
from objective import objective


def tests():
    def fixture(mode):
        s=Search.__new__(Search);s.target_shape=np.array([1.,-1.,1.,-1.]);s.cache={};s.attempts=[]
        def generate(c,label):
            key=tuple(np.asarray(c).tolist())
            if key in s.cache:return s.cache[key]
            shape=np.asarray(c);r={'coefficients':list(key),'attempt':label,'status':'completed',
                'support_complete':True,'E0_pass':True,'internal_unchanged':True,'wave_shape':shape.tolist(),
                'objective':objective(s.target_shape,shape,c)}
            if (mode=='one' and '-axis-1-minus' in label) or (mode=='both' and '-axis-1-' in label):
                r.update(status='failed',support_complete=False)
            if mode in ('shrink','none') and label.endswith('-update'):r['objective']=100.
            if mode=='none' and '-shrink-' in label:r['objective']=100.
            s.attempts.append(r);s.cache[key]=r;return r
        s.generate=generate;n=generate(np.zeros(4),'native');return s,n
    s,n=fixture('central');central=s.run(n,n)
    assert central['iterations'][0]['derivative_methods']==['central']*4
    s,n=fixture('one');one=s.run(n,n)
    assert one['iterations'][0]['derivative_methods'][1]=='forward' and one['iterations'][0]['accepted']
    assert np.array_equal(central['iterations'][0]['candidate_coefficients'],one['iterations'][0]['candidate_coefficients'])
    s,n=fixture('both');both=s.run(n,n)
    assert len(both['iterations'])==1 and both['wavefit']==n and both['iterations'][0]['derivative_methods'][-1]=='unavailable'
    s,n=fixture('shrink');small=s.run(n,n)
    assert small['extra_shrink_renders']<=3 and all(i['recoveries'][0]['factor']==.5 for i in small['iterations'])
    assert all(i['accepted'] for i in small['iterations'])
    s,n=fixture('none');none=s.run(n,n)
    assert len(none['iterations'])==1 and none['wavefit']==n and none['extra_shrink_renders']==2
    assert [r['factor'] for r in none['iterations'][0]['recoveries']]==[.5,.25]
    before=len(s.attempts);s.generate([0]*4,'repeat');assert len(s.attempts)==before
    return {'central_matches_old_math':True,'one_invalid_side_continues':True,'both_invalid_stops':True,
        'normal_rejection_tries_fixed_shrink':True,'no_acceptable_update_retains_previous':True,
        'duplicate_coefficients_not_rendered':True,'maximum_shrink_renders':3,'real_render_calls':0,'real_ai_calls':0}

if __name__=='__main__':print(tests())
