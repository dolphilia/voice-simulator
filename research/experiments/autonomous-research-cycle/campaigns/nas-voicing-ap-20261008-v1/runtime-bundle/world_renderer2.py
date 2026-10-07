"""HMM生成MCP/LF0/LPFからWORLDへ固定式で変換する非ニューラル合成。"""
from pathlib import Path
import sys,hashlib
import numpy as np
from scipy import signal
PACKAGE=Path(__file__).resolve().parent/'packages-v2'
sys.path.insert(0,str(PACKAGE))
import pyworld as pw
assert pw.__version__=='0.3.5'
FFT=4096;FS=48000;PERIOD=240;ALPHA=.55

def ah(x):return hashlib.sha256(np.asarray(x,dtype='<f8').tobytes()).hexdigest()
def log_amplitude(mcp):
 x=np.asarray(mcp,dtype=float)
 if x.ndim!=2 or not x.size or not np.isfinite(x).all():raise ValueError('MCPは有限の非空2D配列')
 w=np.linspace(0,np.pi,FFT//2+1);z=np.exp(-1j*w);t=(z-ALPHA)/(1-ALPHA*z);power=np.ones_like(t)
 out=np.broadcast_to(x[:,0,None],(len(x),len(w))).copy();temp=np.empty_like(out)
 for m in range(1,x.shape[1]):
  power*=t;np.multiply(x[:,m,None],power.real[None,:],out=temp);np.add(out,temp,out=out)
 return out

def convert(params):
 if len(params)!=3:raise ValueError('3stream必須')
 mcp,lf0,lpf=[np.asarray(x,dtype=float) for x in params]
 if any(x.ndim!=2 or not x.size or not np.isfinite(x).all() for x in [mcp,lf0,lpf]) or len({len(x) for x in [mcp,lf0,lpf]})!=1 or lf0.shape[1]!=1 or lpf.shape[1]%2!=1:raise ValueError('同フレーム・有限3stream・奇数LPFが必要')
 voiced=lf0[:,0]>-1e9;f0=np.zeros(len(mcp));f0[voiced]=np.exp(lf0[voiced,0]);assert np.all((f0[voiced]>=70)&(f0[voiced]<=800)),'F0範囲外：事後変更しない'
 sp=np.exp(2*log_amplitude(mcp))/(32768.**2);assert np.isfinite(sp).all() and np.min(sp)>0
 # LPFは振幅と位相を持つ。同じLPFからpowerの和とAP近似を作る。
 unique,inv=np.unique(lpf,axis=0,return_inverse=True);w=np.linspace(0,np.pi,FFT//2+1);positions=np.arange(lpf.shape[1])-(lpf.shape[1]-1)//2
 response=np.zeros((len(unique),len(w)),complex)
 for k,pos in enumerate(positions):response+=unique[:,k,None]*np.exp(-1j*w*pos)[None,:]
 periodic=abs(response)**2;noise=abs(1-response)**2;mix=periodic+noise;assert np.min(mix)>0
 ap=np.sqrt(noise/mix);np.clip(ap,.001,.999999,out=ap)
 sp[voiced]*=mix[inv[voiced]];ap=ap[inv].copy();ap[~voiced]=1.
 arrays=[np.ascontiguousarray(np.concatenate([x[:1],x],axis=0),dtype=np.float64) for x in [f0,sp,ap]]
 meta={'f0_sha256':ah(arrays[0]),'power_sha256':ah(arrays[1]),'AP_sha256':ah(arrays[2]),'frames_original':len(mcp),'frames_WORLD':len(mcp)+1,'FFT':FFT,'fs':FS,'alpha':ALPHA,'fperiod':PERIOD,'clock':'prepend first, trim last frame','AP_is_approximation':True,'saved_waveform_analysis_used':False,'power_range':[float(np.min(sp)),float(np.max(sp))],'f0_range':[float(np.min(f0[voiced])) if voiced.any() else None,float(np.max(f0))]}
 return arrays,meta

def synthesize(params,settings):
 assert settings['stage']==0 and settings['alpha']==ALPHA and settings['beta']==0 and settings['volume']==1 and settings['sampling_frequency']==FS and settings['fperiod']==PERIOD,'固定Mei設定のみ'
 (f0,sp,ap),meta=convert(params);raw=pw.synthesize(f0,sp,ap,FS,frame_period=5.)
 assert len(raw)==len(f0)*PERIOD and np.isfinite(raw).all();raw=raw[:len(params[0])*PERIOD]
 audio=signal.resample_poly(raw,1,2);n=min(round(.012*24000),len(audio)//2);env=np.sin(np.linspace(0,np.pi/2,n))**2;audio[:n]*=env;audio[-n:]*=env[::-1]
 assert len(audio)==len(params[0])*120 and np.isfinite(audio).all();meta['sample_count_24k']=len(audio)
 return audio,meta

def tests():
 p=[np.zeros((4,35)),np.full((4,1),np.log(220)),np.tile([0,1,0],(4,1))];a,meta=convert(p)
 assert len(a[0])==5 and np.allclose(a[0],220,rtol=1e-12,atol=0) and np.allclose(a[1],1/32768.**2) and np.all(a[2]==.001)
 assert np.array_equal(p[0],np.zeros((4,35)))
 for bad in [[np.empty((0,35)),p[1],p[2]],[p[0],p[1],np.zeros((4,2))],[p[0],np.full((4,1),np.nan),p[2]]]:
  try:convert(bad)
  except ValueError:pass
  else:raise AssertionError('不正streamを拒否')
 return {'flat_gain_power_units':True,'identity_LPF_AP_formula':True,'input_unchanged':True,'bad_stream_rejected':True,'actual_render_calls':0}
