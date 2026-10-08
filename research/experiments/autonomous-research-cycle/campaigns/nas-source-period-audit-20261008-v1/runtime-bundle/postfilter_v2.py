"""一次HTS式のMCPエネルギー補正。発話表・教師・録音を参照しない。"""
import ctypes as C
from pathlib import Path
import numpy as np
from scipy import signal
import local_renderer
from hts_arrays import validated,ah
_lib=C.CDLL(str(Path(__file__).resolve().parent/'postfilter_v2.dylib'))
P=C.POINTER(C.c_double);S=C.c_size_t
_fn=_lib.mcp_postfilter;_fn.restype=C.c_int;_fn.argtypes=[P,S,S,C.c_double,P,P,P]
_ref=_lib.pf_reference_render;_ref.restype=C.c_int;_ref.argtypes=[P,P,P,S,S,S,C.c_double,P,S]
def transform_mcp(value,beta):
    x=np.ascontiguousarray(value,dtype=np.float64)
    if x.ndim!=2 or x.shape[1]!=35 or not 1<=len(x)<=6000 or not np.isfinite(x).all() or beta not in [0.,.2]:
        raise ValueError('有限MCP Nx35と登録済みβ0/0.2だけを許可')
    original=ah(x);y=np.empty_like(x);before=np.empty(len(x));after=np.empty(len(x))
    if not _fn(x.ctypes.data_as(P),len(x),35,beta,y.ctypes.data_as(P),before.ctypes.data_as(P),after.ctypes.data_as(P)):
        raise RuntimeError('MCP一次後処理の有限性検査に不通過')
    assert ah(x)==original
    error=float(np.max(np.abs(np.log(after/before))))
    invariant=bool(error<=1e-10)
    if beta==0.:assert y.tobytes()==x.tobytes()
    return y,dict(beta=float(beta),alpha=.55,frames=len(x),max_abs_log_energy_ratio=error,
        energy_invariant_pass=invariant,input_preserved=True,zero_beta_byte_exact=bool(beta==0.),
        energy_definition='対応版HTS_b2enの有限インパルス応答エネルギー。実波形の等ラウドネス保証ではない。',
        source='HTS_Vocoder_postfilter_mcp',utterance_lookup=0,neural=False)
def reference_synthesize(params,settings,beta):
    x=validated(params,settings);before=[ah(v) for v in x];raw=np.empty(len(x[0])*240)
    if not _ref(*(v.ctypes.data_as(P) for v in x),len(x[0]),35,x[2].shape[1],beta,raw.ctypes.data_as(P),len(raw)):
        raise RuntimeError('一次HTS内部β付きfixtureが不正')
    assert [ah(v) for v in x]==before
    audio=signal.resample_poly(raw/32768.,1,2)
    n=min(round(.012*24000),len(audio)//2);env=np.sin(np.linspace(0,np.pi/2,n))**2
    audio[:n]*=env;audio[-n:]*=env[::-1]
    assert np.isfinite(audio).all()
    return audio

_pre=_lib.pf_prefiltered_render;_pre.restype=C.c_int;_pre.argtypes=[P,P,P,P,S,S,S,P,S]
def synthesize_with_native_initial(params,settings,initial_mcp):
    x=validated(params,settings);before=[ah(a) for a in x]
    first=np.ascontiguousarray(initial_mcp,dtype=np.float64)
    if first.shape!=(35,) or not np.isfinite(first).all():raise ValueError('初回native MCP35を要求')
    initial_hash=ah(first);raw=np.empty(len(x[0])*240)
    if not _pre(*(a.ctypes.data_as(P) for a in x),first.ctypes.data_as(P),len(x[0]),35,x[2].shape[1],raw.ctypes.data_as(P),len(raw)):
        raise RuntimeError('初回順序を保持したHTS入口が不正')
    assert [ah(a) for a in x]==before and ah(first)==initial_hash
    audio=signal.resample_poly(raw/32768.,1,2)
    n=min(round(.012*24000),len(audio)//2);env=np.sin(np.linspace(0,np.pi/2,n))**2
    audio[:n]*=env;audio[-n:]*=env[::-1]
    assert len(audio)==len(x[0])*120 and np.isfinite(audio).all()
    return audio,dict(renderer='HTS-pulse-noise-MLSA',input_parameter_hashes=before,input_streams_unchanged=True,
        frames_original=len(x[0]),fs=48000,output_fs=24000,sample_count_24k=len(audio),alpha=.55,beta=0.,volume=1.,stage=0,use_log_gain=False,
        initial_MCP_source='同じ文章からその場で生成したnative MCPの初回frame。一次HTS内部β処理の初回順序を保持。',
        initial_MCP_sha256=initial_hash,clock='native全frameを順次生成、先頭複製/末尾切りなし。',
        source='対応版HTS初回初期化順序とβ0全frame入口',saved_waveform_analysis_used=False,neural_model=False,utterance_lookup=False)
