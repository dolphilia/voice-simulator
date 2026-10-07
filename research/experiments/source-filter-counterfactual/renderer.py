"""旧状態エンジンと新MLPG wrapperを接続する。ニューラル推論は使わない。"""
import ctypes as C
from pathlib import Path
import numpy as np
from scipy import signal
from local_renderer import StateEngine,copy_audio,nsamples

ROOT=Path(__file__).resolve().parent
lib=C.CDLL(str(ROOT/'counter.dylib'))
P,S,D=C.c_void_p,C.c_size_t,C.c_double

def bind(name,result,args):
    f=getattr(lib,name);f.restype=result;f.argtypes=args;return f

prepare=bind('counter_prepare',C.c_int,[P])
frames=bind('counter_frames',S,[P]);length=bind('counter_length',S,[P,S])
copy=bind('counter_copy',C.c_int,[P,S,C.POINTER(D),S])
wave=bind('counter_wave',C.c_int,[P,C.c_int])
output_streams=bind('counter_output_streams',S,[P])
output=bind('counter_output',D,[P,S,S,S])
settings=bind('counter_settings',C.c_int,[P,C.POINTER(D),S])
MODES={'baseline':0,'flat_spectrum':1,'simple_excitation':2}


def inputs(parameters,mode):
    if mode not in MODES:raise ValueError('対照方式が範囲外です')
    if len(parameters)!=3:raise ValueError('3ストリームを要求します')
    rows=[np.asarray(p,dtype=float) for p in parameters]
    if any(p.ndim!=2 or not p.size or not np.isfinite(p).all() for p in rows):raise ValueError('有限の非空2次元列を要求します')
    if len({len(p) for p in rows})!=1 or rows[1].shape[1]!=1 or rows[0].shape[1]<=1 or rows[2].shape[1]%2!=1:raise ValueError('列の時間・次数が不一致です')
    x=[p.copy() for p in rows]
    if mode!='baseline':x[0][:,1:]=0
    if mode=='simple_excitation':x=x[:2]
    return x


def tests():
    p=[np.arange(12.).reshape(4,3),np.full((4,1),np.log(220)),np.ones((4,3))]
    base=inputs(p,'baseline');flat=inputs(p,'flat_spectrum');simple=inputs(p,'simple_excitation')
    assert np.array_equal(flat[0][:,0],p[0][:,0]) and not flat[0][:,1:].any()
    assert all(np.array_equal(a,b) for a,b in zip(base,p)) and np.array_equal(flat[1],p[1]) and np.array_equal(flat[2],p[2])
    assert len(simple)==2 and np.array_equal(simple[0],flat[0]) and np.array_equal(simple[1],p[1])
    rejected=0
    for bad,mode in [(p,'bad'),(p[:2],'baseline'),([p[0][:-1],p[1],p[2]],'baseline'),([p[0]*np.nan,p[1],p[2]],'baseline')]:
        try:inputs(bad,mode)
        except ValueError:rejected+=1
        else:raise AssertionError('不正な対照を拒否しません')
    assert not prepare(None) and not wave(None,0) and not wave(None,3)
    return {'flat_preserves_c0_lf0_lpf':True,'simple_only_removes_lpf_after_flat':True,'source_arrays_not_modified':True,
        'invalid_modes_shapes_finite_null_rejected':rejected+3,'new_render_calls':0,'ai_calls':0}


class CounterEngine(StateEngine):
    def parameters(self):
        if not prepare(self.pointer):raise RuntimeError('MLPG生成・形状検査に不通過')
        arrays=[]
        for s in range(3):
            x=np.empty((frames(self.pointer),length(self.pointer,s)),dtype=np.float64)
            if not copy(self.pointer,s,x.ctypes.data_as(C.POINTER(D)),x.size):raise RuntimeError('MLPG列の読出し失敗')
            arrays.append(x)
        return arrays
    def get_settings(self):
        x=np.empty(9,dtype=float);assert settings(self.pointer,x.ctypes.data_as(C.POINTER(D)),9)
        return dict(zip(('stage','use_log_gain','sampling_frequency','fperiod','alpha','beta','volume','audio_buff_size','stop'),x.tolist()))
    def synthesize(self,parameters,mode):
        expected=inputs(parameters,mode)
        if not wave(self.pointer,MODES[mode]):raise RuntimeError('対照波形生成失敗')
        assert output_streams(self.pointer)==len(expected)
        for s,x in enumerate(expected):
            generated=np.array([[output(self.pointer,s,f,j) for j in range(x.shape[1])] for f in range(len(x))])
            assert np.array_equal(generated,x),'Vocoderへ渡すパラメータが固定した対照と不一致'
        # 変更したPSSをC側で元へ復元したことも検査する。
        for s,x in enumerate(parameters):
            actual=np.empty_like(x);assert copy(self.pointer,s,actual.ctypes.data_as(C.POINTER(D)),actual.size)
            assert np.array_equal(actual,x)
        audio=np.empty(nsamples(self.pointer),dtype=float)
        copy_audio(self.pointer,audio.ctypes.data_as(C.POINTER(D)),len(audio))
        audio=signal.resample_poly(audio/32768,1,2)
        n=min(round(.012*24000),len(audio)//2);env=np.sin(np.linspace(0,np.pi/2,n))**2
        audio[:n]*=env;audio[-n:]*=env[::-1]
        return audio
