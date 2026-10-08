"""共有VTL物理生成と二つの舌標的だけ。研究参照/学習/評価は読み込まない。"""
import ctypes as ct,hashlib,io,math
from pathlib import Path
import numpy as np
from scipy import signal
from scipy.io import wavfile
ROOT=Path(__file__).resolve().parent
class VTL:
 def __init__(self):
  self.lib=ct.CDLL(str(ROOT/'libVocalTractLabApi.dylib'));ptr=ct.POINTER(ct.c_double)
  self.lib.vtlInitialize.argtypes=[ct.c_char_p];self.lib.vtlGetTractParams.argtypes=[ct.c_char_p,ptr];self.lib.vtlGetGlottisParams.argtypes=[ct.c_char_p,ptr];self.lib.vtlSynthesisAddTract.argtypes=[ct.c_int,ptr,ptr,ptr]
  self.lib.vtlGetTractParamInfo.argtypes=[ct.c_char_p,ct.c_char_p,ct.c_char_p,ptr,ptr,ptr]
  self.check(self.lib.vtlInitialize(str(ROOT/'JD3.speaker').encode()))
  values=[ct.c_int() for _ in range(5)];rate=ct.c_double();self.check(self.lib.vtlGetConstants(*(ct.byref(v) for v in values),ct.byref(rate)))
  self.fs,self.ntube,self.ntract,self.nglottis,self.step=[v.value for v in values];assert self.fs==44100 and self.ntract==19 and self.step==110
  names=ct.create_string_buffer(1024);desc=ct.create_string_buffer(8192);units=ct.create_string_buffer(1024);lo=(ct.c_double*self.ntract)();hi=(ct.c_double*self.ntract)();standard=(ct.c_double*self.ntract)()
  self.check(self.lib.vtlGetTractParamInfo(names,desc,units,lo,hi,standard));self.names=names.value.decode().split('\t');self.bounds={self.names[i]:[lo[i],hi[i]] for i in range(self.ntract)};assert self.names[8:10]==['TCX','TCY']
  self.constants=dict(fs=self.fs,sections=self.ntube,tract_parameters=self.ntract,glottis_parameters=self.nglottis,step=self.step,internal_rate_Hz=rate.value)
 @staticmethod
 def check(code):
  if code:raise RuntimeError('VTL API失敗: '+str(code))
 def render(self,vowel,f0,duration=.32,seed=41,dx=0.,dy=0.):
  if vowel not in 'aiueo' or duration<=0 or not 70<=f0<=400:raise ValueError('対象母音/条件外')
  tract=(ct.c_double*self.ntract)();glottis=(ct.c_double*self.nglottis)();self.check(self.lib.vtlGetTractParams(vowel.encode(),tract));self.check(self.lib.vtlGetGlottisParams(b'modal',glottis));base=[tract[8],tract[9]]
  for index,delta in [(8,dx),(9,dy)]:
   requested=tract[index]+delta;lo,hi=self.bounds[self.names[index]]
   if not lo<=requested<=hi:raise ValueError('登録舌標的がAPI範囲外')
   tract[index]=requested
  glottis[0]=f0;ct.CDLL(None).srand(ct.c_uint(seed));self.check(self.lib.vtlSynthesisReset());empty=(ct.c_double*1)();self.check(self.lib.vtlSynthesisAddTract(0,empty,tract,glottis))
  samples=round(duration*self.fs);chunks=[];calls=0
  for start in range(0,samples,self.step):
   n=min(self.step,samples-start);buffer=(ct.c_double*n)();self.check(self.lib.vtlSynthesisAddTract(n,buffer,tract,glottis));chunks.append(np.array(buffer));calls+=1
  audio=signal.resample_poly(np.concatenate(chunks)*.5,80,147);fade=min(round(.012*24000),len(audio)//2);envelope=np.sin(np.linspace(0,np.pi/2,fade))**2;audio[:fade]*=envelope;audio[-fade:]*=envelope[::-1];audio[0]=audio[-1]=0.;audio=audio.astype(np.float32)
  buf=io.BytesIO();wavfile.write(buf,24000,audio);data=buf.getvalue();meta=dict(vowel=vowel,requested_f0_Hz=f0,duration_s=duration,seed=seed,TCXY_baseline_cm=base,TCXY_requested_cm=[tract[8],tract[9]],TCXY_delta_cm=[dx,dy],parameter_bounds=self.bounds,constant=self.constants,gain=.5,source_samples=samples,render_calls=calls+3,internal_AddTract_audio_calls=calls,initial_AddTract_zero_calls=1,reset_calls=1,outer_waveform_calls=1,wav_bytes=len(data),wav_sha256=hashlib.sha256(data).hexdigest(),shared_parameters=True,neural=False,teacher_or_saved_audio_read=False,geometry_joint_constraints_not_independently_qualified=True)
  return data,meta
 def close(self):self.check(self.lib.vtlClose())
