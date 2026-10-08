"""生成3streamをHTS pulse/noise MLSAへ直接渡す非ニューラル配列入口。"""
import ctypes as C
from pathlib import Path
import hashlib
import numpy as np
from scipy import signal
import local_renderer  # 対応版pyopenjtalk HTS symbolsをRTLD_GLOBALで初期化
_lib=C.CDLL(str(Path(__file__).resolve().parent/'hts_arrays.dylib'))
_fn=_lib.hts_arrays_render
P=C.POINTER(C.c_double);S=C.c_size_t
_fn.restype=C.c_int;_fn.argtypes=[P,P,P,S,S,S,P,S]
def ah(x): return hashlib.sha256(np.asarray(x,dtype='<f8').tobytes()).hexdigest()
def validated(params,settings):
    if len(params)!=3: raise ValueError('生成3stream必須')
    x=[np.ascontiguousarray(v,dtype=np.float64) for v in params]
    if any(v.ndim!=2 or not v.size or not np.isfinite(v).all() for v in x):
        raise ValueError('有限非空の2D配列を要求')
    if len({len(v) for v in x})!=1 or not 1<=len(x[0])<=6000 or x[0].shape[1]!=35 or x[1].shape[1]!=1 or not 1<=x[2].shape[1]<=63 or x[2].shape[1]%2!=1:
        raise ValueError('固定Meiの同フレームMCP35/LF01/奇数LPFを要求')
    voiced=x[1][:,0]>0
    if np.any(x[1][~voiced]!=-1e10) or np.any((np.exp(x[1][voiced,0])<70)|(np.exp(x[1][voiced,0])>800)):
        raise ValueError('LF0 sentinelまたは有声F0範囲が不正')
    expected=dict(stage=0.,use_log_gain=0.,sampling_frequency=48000.,fperiod=240.,alpha=.55,beta=0.,volume=1.,audio_buff_size=0.,stop=0.)
    if settings!=expected: raise ValueError('固定Mei設定だけを許可')
    return x
def synthesize(params,settings):
    x=validated(params,settings);before=[ah(v) for v in x]
    raw=np.empty(len(x[0])*240,dtype=np.float64)
    if not _fn(*(v.ctypes.data_as(P) for v in x),len(x[0]),35,x[2].shape[1],raw.ctypes.data_as(P),len(raw)):
        raise RuntimeError('HTS配列vocoderの入力/有限性検査に不通過')
    assert [ah(v) for v in x]==before
    audio=signal.resample_poly(raw/32768.,1,2)
    n=min(round(.012*24000),len(audio)//2);env=np.sin(np.linspace(0,np.pi/2,n))**2
    audio[:n]*=env;audio[-n:]*=env[::-1]
    assert len(audio)==len(x[0])*120 and np.isfinite(audio).all()
    return audio,dict(renderer='HTS-pulse-noise-MLSA',input_parameter_hashes=before,input_streams_unchanged=True,
        frames_original=len(x[0]),fs=48000,output_fs=24000,sample_count_24k=len(audio),alpha=.55,beta=0.,volume=1.,stage=0,use_log_gain=False,
        clock='native全フレームを順次生成。先頭複製/末尾frame切りなし。',
        source='対応版HTS_Vocoder_initialize/synthesize/clear',saved_waveform_analysis_used=False,
        neural_model=False,utterance_lookup=False)
