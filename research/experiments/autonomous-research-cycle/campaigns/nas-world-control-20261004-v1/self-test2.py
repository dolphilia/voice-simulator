"""未知文の生成前に単位/変換符号/時刻/決定性を固定fixtureで点検する。"""
from paths import *
import ctypes as C,io,numpy as np
from scipy.io import wavfile
from world_renderer2 import log_amplitude,synthesize,tests,FFT,ALPHA

def main():
 b=Budget();lib=C.CDLL(str(HERE/'reference_freqt.dylib'));fn=lib.reference_freqt;fn.restype=C.c_int;fn.argtypes=[C.POINTER(C.c_double),C.c_int,C.POINTER(C.c_double),C.c_int,C.c_double]
 with b.job(NAME,'dsp','独立freqtと解析式の固定MCP fixture比較',reserve_bytes=100000) as j:
  rows=[];zero=np.zeros(35);rows.append(zero.copy());zero[1]=.2;rows.append(zero.copy());zero[:]=0;zero[2]=-.3;rows.append(zero.copy());rows.extend(np.random.default_rng(20261004).uniform(-.2,.2,(4,35)))
  selected=[]
  for rid in ['source-fresh-00','source-fresh-04']:
   x=np.load(PREVIOUS/'render/baseline'/rid/'neutral/native.npz')['spectrum']
   for k in [0,len(x)//4,len(x)//2,3*len(x)//4,len(x)-1]:rows.append(x[k].copy());selected.append({'id':rid,'index':k,'parameters_sha256':digest(PREVIOUS/'render/baseline'/rid/'neutral/native.npz')})
  errors=[]
  for x in rows:
   y=np.empty(FFT);assert fn(x.ctypes.data_as(C.POINTER(C.c_double)),len(x)-1,y.ctypes.data_as(C.POINTER(C.c_double)),FFT-1,-ALPHA)
   errors.append(float(np.max(abs(np.fft.rfft(y).real-log_amplitude(x[None,:])[0]))))
  assert max(errors)<1e-9,'MCP変換不一致：未知生成を停止'
  b.save(HERE/'conversion-audit.json',{'passed':True,'max_absolute_logamp_error':max(errors),'all_errors':errors,'fixed_frames':selected,'independent_reference_C_sha256':digest(HERE/'reference_freqt.c'),'threshold':1e-9,'logamp_not_power_comparison':True,'quality_certified':False},j)
 with b.job(NAME,'setup','変換の入力否定検査',reserve_bytes=30000) as j:b.save(HERE/'negative-tests.json',tests(),j)
 saved=np.load(PREVIOUS/'render/baseline/source-fresh-00/neutral/native.npz');lpf=np.repeat(saved['lpf'][0:1],100,axis=0);mcp=np.zeros((100,35));mcp[:,0]=np.log(1000.)
 settings=read(PREVIOUS/'render/baseline/source-fresh-00/neutral/native.json')['vocoder_settings'];summary=[]
 for f0 in [0,160,220,300]:
  outputs=[];params=[mcp,np.full((100,1),np.log(f0) if f0 else -1e10),lpf]
  for rep in range(2):
   with b.job(NAME,'render','WORLD合成固定fixture '+str(f0)+'/'+str(rep),reserve_bytes=100000) as j:
    raw,meta=synthesize(params,settings);assert len(raw)==12000 and np.isfinite(raw).all()
    out=io.BytesIO();wavfile.write(out,24000,raw.astype(np.float32));path=HERE/'self-test'/('f0-'+str(f0)+'-'+str(rep)+'.wav');b.write(path,out.getvalue(),j);outputs.append(raw)
  assert np.array_equal(outputs[0],outputs[1]),'WORLDが同入力で非決定的'
  summary.append({'f0':f0,'bit_match':True,'samples':len(raw),'raw_peak':float(np.max(abs(raw))),'conversion':meta})
 b.save(HERE/'self-test.json',{'passed':True,'fixtures':summary,'eight_render_calls':8,'quality_certified':False});print({'conversion_pass':True,'max_error':max(errors),'fixtures':4},flush=True);print(b.reconcile(),flush=True)
if __name__=='__main__':main()
