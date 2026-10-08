"""NSDFの式9を独立実装。旧ACFと2×2の固定比較を行う。"""
import numpy as np
from scipy import signal
NAMES=('bounded_all','overlap_all','bounded_key','overlap_key')
def curves(x):
    x=np.asarray(x,dtype=float).copy();x-=np.mean(x)
    r=signal.correlate(x,x,mode='full',method='fft')[len(x)-1:]
    bounded=r/np.maximum(1,np.arange(len(x),0,-1))
    e=np.r_[0.,np.cumsum(x*x)];lags=np.arange(len(x))
    denominator=e[len(x)-lags]+e[-1]-e[lags]
    overlap=np.divide(2*r,denominator,out=np.zeros_like(r),where=denominator>0)
    return bounded,overlap
def estimate(x,fs=24000):
    out={name:(0.,0.) for name in NAMES};x=np.asarray(x,dtype=float)
    if len(x)<fs*.010 or not np.isfinite(x).all():return out
    centered=x-x.mean()
    if np.sqrt(np.mean(centered*centered))<1e-5:return out
    bounded,overlap=curves(x);lo=int(fs/800);hi=min(len(x)-2,int(fs/70))
    if hi<=lo or bounded[0]<=0:return out
    for norm,curve in [('bounded',bounded),('overlap',overlap)]:
        peaks,_=signal.find_peaks(curve[lo:hi]);peaks+=lo;peaks=peaks[curve[peaks]>0]
        if not len(peaks):continue
        # keyは初期正領域を除き、正の各連続領域で最大の局所ピークのみを残す。
        positive=curve>0;starts=np.flatnonzero(positive&~np.r_[False,positive[:-1]])
        ends=np.flatnonzero(positive&~np.r_[positive[1:],False])+1
        key=[]
        for a,z in zip(starts,ends):
            if a==0:continue
            candidates=peaks[(peaks>=a)&(peaks<z)]
            if len(candidates):key.append(int(candidates[np.argmax(curve[candidates])]))
        for picking,available in [('all',peaks),('key',np.asarray(key,dtype=int))]:
            if not len(available):continue
            best=max(curve[available]);candidates=available[curve[available]>=.93*best];lag=int(candidates[0])
            delta=.5*(curve[lag-1]-curve[lag+1])/(curve[lag-1]-2*curve[lag]+curve[lag+1])
            hz=float(fs/(lag+np.clip(delta,-.5,.5)))
            confidence=float(np.clip(curve[lag]/curve[0],0,1))
            out[norm+'_'+picking]=(hz if confidence>=.6 else 0.,confidence)
    return out
def local(audio,times,width):
    output={name:np.zeros(len(times)) for name in NAMES};confidence={name:np.zeros(len(times)) for name in NAMES}
    half=round(width*24/2)
    for i,t in enumerate(times):
        center=round(float(t)*24000);a,z=center-half,center+half
        if a<0 or z>len(audio):continue
        for name,(hz,c) in estimate(audio[a:z]).items():output[name][i]=hz;confidence[name][i]=c
    return output,confidence
