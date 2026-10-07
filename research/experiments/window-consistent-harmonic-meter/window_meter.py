"""旧調波測定の測定本体を継承し、基底への変換だけを揃える。"""
import copy
from meter_io import *

def load_parent():
    path=ALT/'local_meters.py';expected=read(ARES/'protocol.json')['source_hashes']['local_meters.py'];assert digest(path)==expected
    spec=importlib.util.spec_from_file_location('sealed_local_meters',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

parent=load_parent()
SPEC=copy.deepcopy(parent.SPEC)
SPEC['harmonic_basis_windowed']=True
SPEC['harmonic_basis_mean_removed']=True
SPEC['change']='信号と基底列に同じT=Hann×平均除去を適用'

def transform_columns(basis):
    b=np.asarray(basis,dtype=float)
    if b.ndim<2 or b.shape[-2]<2 or b.shape[-1]<1 or not np.isfinite(b).all():raise ValueError('非空・有限の基底行列を要求します')
    return (b-b.mean(axis=-2,keepdims=True))*np.hanning(b.shape[-2])[:,None]

def checked_qr(basis):
    if not np.isfinite(basis).all():raise ValueError('基底が非有限です')
    q,r=np.linalg.qr(basis,mode='reduced');diag=abs(np.diagonal(r,axis1=-2,axis2=-1))
    rank_ok=np.isfinite(q).all(axis=(-2,-1))&(diag.min(axis=-1)>1e-12*diag.max(axis=-1))
    if not np.all(rank_ok):raise ValueError('調波辞書に非有限・特異候補があります')
    return q,rank_ok

class WindowConsistentHarmonic(parent.LocalHarmonic):
    name='window_harmonic'
    def __init__(self):
        self.freq=np.arange(70.,800.5,.5);t=(np.arange(480)-240)/parent.FS
        phase=2*np.pi*self.freq[:,None,None]*t[None,:,None]*np.arange(1,4)[None,None,:]
        basis=np.concatenate((np.sin(phase),np.cos(phase)),axis=2)
        # 旧initとの差はこの一つの線形変換。measureは同じ関数を継承する。
        basis=transform_columns(basis)
        q,self.rank_ok=checked_qr(basis)
        self.q=np.ascontiguousarray(q.transpose(0,2,1).reshape(-1,480))

def tests():
    b=np.array([[1.,0.],[0.,1.],[1.,1.],[2.,-1.],[-1.,3.],[2.,4.],[3.,2.],[4.,-3.]])
    c=np.array([.4,-.7]);tb=transform_columns(b);tx=transform_columns((b@c)[:,None])[:,0]
    assert np.allclose(tx,tb@c,atol=1e-12,rtol=0)
    q,_=checked_qr(tb);v=np.array([2.,3.,4.,5.,6.,1.,2.,7.]);tv=transform_columns(v[:,None])[:,0]
    residual=tv@tv-np.sum((q.T@tv)**2);coef=np.linalg.lstsq(tb,tv,rcond=None)[0]
    assert abs(residual-np.sum((tv-tb@coef)**2))<1e-10
    for bad in [np.empty((0,2)),np.full((8,2),np.nan)]:
        try:transform_columns(bad)
        except ValueError:pass
        else:raise AssertionError('不正基底を拒否しません')
    try:checked_qr(np.zeros((8,2)))
    except ValueError:pass
    else:raise AssertionError('特異基底を拒否しません')
    for bad in [np.empty(0),np.full(28800,np.nan),np.zeros((28800,2))]:
        try:parent.validate(bad)
        except ValueError:pass
        else:raise AssertionError('不正入力を拒否しません')
    raw,_,_=parent.windows(np.arange(28800,dtype=float),480)
    assert raw.shape==(240,480) and (raw[0,:240]==0).all() and raw[1,240]==120
    assert WindowConsistentHarmonic.measure is parent.LocalHarmonic.measure
    return {'transform_linearity':True,'qr_and_lstsq_residual_equal':True,'empty_nonfinite_singular_rejected':True,
        'invalid_audio_cases':3,'integer_zero_padded_windows':True,'measurement_body_identical_function':True,'new_audio_or_measurement_calls':0}
