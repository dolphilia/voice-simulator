"""先生出力の単位を明示して共通headroomを適用する。"""
from paths import *
import io,numpy as np
from scipy.io import wavfile
from scipy import signal
from math import gcd

def wavbytes(x,fs=24000):
 f=io.BytesIO();wavfile.write(f,fs,x);return f.getvalue()
def canonical(raw,fs):
 assert raw.ndim==1 and raw.size and np.isfinite(raw).all() and len(raw)/fs<=30
 if raw.dtype==np.int16:x=raw.astype(np.float64)/32768.
 elif raw.dtype==np.float32 or raw.dtype==np.float64:x=raw.astype(np.float64)
 else:raise ValueError('教師の未登録dtype')
 g=gcd(fs,24000);x=signal.resample_poly(x,24000//g,fs//g) if fs!=24000 else x
 peak=float(np.max(abs(x)));gain=(min(1.,.95/peak) if peak else 1.)*.25;x=(x*gain).astype(np.float32)
 assert np.isfinite(x).all() and np.max(abs(x))<1
 return x,{'original_dtype':str(raw.dtype),'original_fs':fs,'original_samples':len(raw),'output_fs':24000,'output_samples':len(x),'common_factor':.25,'gain_on_resampled_original':gain,'resampled_original_peak':peak,'output_peak':float(np.max(abs(x))),'extra_fade':False}
