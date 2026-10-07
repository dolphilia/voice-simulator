"""次案用の有効差分。現在の合成・最適化には接続しない。"""
import numpy as np


def valid(record,length):
    if record is None or record.get('status')!='completed' or not all(record.get(k) for k in ('support_complete','E0_pass','internal_unchanged')):
        return False
    x=np.asarray(record.get('wave_shape',[]),dtype=float)
    return x.shape==(length,) and np.isfinite(x).all()


def column(current,plus,minus,width=.25):
    baseline=np.asarray(current.get('wave_shape',[]),dtype=float)
    if baseline.ndim!=1 or not len(baseline) or not valid(current,len(baseline)) or not np.isfinite(width) or width<=0:
        raise ValueError('有効な既定支持域と正の差分幅を要求します')
    p,m=valid(plus,len(baseline)),valid(minus,len(baseline))
    if p and m:return (np.asarray(plus['wave_shape'])-np.asarray(minus['wave_shape']))/(2*width),'central'
    if p:return (np.asarray(plus['wave_shape'])-baseline)/width,'forward'
    if m:return (baseline-np.asarray(minus['wave_shape']))/width,'backward'
    return None,'unavailable'


def shrink(current,proposed,factor):
    a,b=np.asarray(current,dtype=float),np.asarray(proposed,dtype=float)
    if a.shape!=(4,) or b.shape!=(4,) or not np.isfinite([a,b]).all() or np.max(abs([a,b]))>3 or factor not in (.5,.25):
        raise ValueError('固定4係数・有限・±3・縮尺1/2か1/4を要求します')
    return a+factor*(b-a)


def tests():
    def record(x):return {'status':'completed','support_complete':True,'E0_pass':True,'internal_unchanged':True,'wave_shape':x}
    c=record([0.,1.,2.]);p=record([.25,1.5,2.75]);m=record([-.25,.5,1.25]);failed={'status':'failed','support_complete':False}
    for plus,minus,method in [(p,m,'central'),(p,failed,'forward'),(failed,m,'backward')]:
        derivative,used=column(c,plus,minus);assert used==method and np.array_equal(derivative,[1,2,3])
    value,method=column(c,failed,failed);assert value is None and method=='unavailable'
    value,method=column(c,c,c);assert np.array_equal(value,[0,0,0]) and method=='central'
    assert np.array_equal(shrink([0]*4,[.5]*4,.5),[.25]*4)
    assert np.array_equal(shrink([0]*4,[.5]*4,.25),[.125]*4)
    rejected=0
    for f in (lambda:column(failed,p,m),lambda:column(c,p,m,width=0),lambda:shrink([0]*4,[3.1]*4,.5),lambda:shrink([0]*4,[.5]*4,.75)):
        try:f()
        except ValueError:rejected+=1
    assert rejected==4
    return {'exact_linear_derivative_central_forward_backward':True,'both_invalid_is_not_zero_derivative':True,
        'valid_flat_derivative_distinguished':True,'fixed_shrink_factors':True,'invalid_inputs_rejected':4,
        'current_runtime_modified':False,'new_render_calls':0,'new_ai_calls':0,'new_shared_model_fits':0}

if __name__=='__main__':print(tests())
