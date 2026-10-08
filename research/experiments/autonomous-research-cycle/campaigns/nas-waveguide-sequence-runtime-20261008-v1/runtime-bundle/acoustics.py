"""旧評価器から独立した修正版。負の自己相関ピークをF0候補へ使わない。"""
import numpy as np
from scipy import signal


def estimate_f0(audio, fs, minimum=70, maximum=450):
    audio=np.asarray(audio,dtype=float)
    if len(audio)<fs*.045 or not np.all(np.isfinite(audio)):
        return None,0.
    estimates=[]; confidence=[]
    window=round(fs*.06); hop=round(fs*.025)
    for start in range(0,max(1,len(audio)-window+1),hop):
        x=audio[start:start+window].copy(); x-=np.mean(x)
        if np.sqrt(np.mean(x*x))<1e-5: continue
        ac=signal.correlate(x,x,mode="full",method="fft")[len(x)-1:]
        ac/=np.maximum(1,np.arange(len(x),0,-1))
        lo,hi=int(fs/maximum),min(len(x)-2,int(fs/minimum))
        if hi<=lo or ac[0]<=0:continue
        peaks,_=signal.find_peaks(ac[lo:hi])
        if not len(peaks):continue
        peaks+=lo
        peaks=peaks[ac[peaks]>0]
        if not len(peaks):continue
        best=max(ac[peaks]); candidates=peaks[ac[peaks]>=.93*best]
        lag=int(candidates[0])
        delta=.5*(ac[lag-1]-ac[lag+1])/(ac[lag-1]-2*ac[lag]+ac[lag+1])
        estimates.append(fs/(lag+np.clip(delta,-.5,.5)))
        confidence.append(float(np.clip(ac[lag]/ac[0],0,1)))
    return (float(np.median(estimates)),float(np.median(confidence))) if estimates else (None,0.)


def acoustic_features(audio,fs):
    x=np.asarray(audio,dtype=float)
    f0,confidence=estimate_f0(x,fs)
    freq,power=signal.welch(x,fs,nperseg=min(len(x),1024))
    total=float(np.sum(power))+1e-30
    bands=[float(np.sum(power[(freq>=lo)&(freq<hi)])/total) for lo,hi in [(0,500),(500,1500),(1500,3000),(3000,6000),(6000,12000)]]
    return {"f0_hz":f0,"f0_confidence":confidence,"band_energy_fractions":bands,
            "centroid_hz":float(np.dot(freq,power)/total),"rms":float(np.sqrt(np.mean(x*x)))}


def evaluate(audio,task_manifest,fs=24000):
    x=np.asarray(audio,dtype=float)
    checks={"nonempty":x.ndim==1 and len(x)>0,"finite":bool(np.all(np.isfinite(x)))}
    if not all(checks.values()):
        return {"version":"signal-v1","E0_pass":False,"checks":checks,"E1":{},"E2":{"state":"unavailable","value":None}}
    peak=float(np.max(abs(x))); rms=float(np.sqrt(np.mean(x*x)))
    values={"peak":peak,"rms":rms,"dc":float(np.mean(x)),"duration_seconds":len(x)/fs,"endpoint":float(max(abs(x[0]),abs(x[-1])))}
    expected=task_manifest.get("expected_duration_seconds")
    checks.update({"no_clipping":peak<.99,"bounded_dc":abs(values["dc"])<=.01,"not_silent":rms>=1e-5,
                   "endpoint_continuity":values["endpoint"]<=1e-6,
                   "complete_duration":expected is None or abs(values["duration_seconds"]-expected)<=2/fs})
    core=x[round(.06*fs):-round(.06*fs)] if len(x)>.2*fs else x
    features=acoustic_features(core,fs)
    e1={"features":features,"state":"diagnostic-only","scope":"非学習音響測定。音素認識・自然さを保証しない"}
    if task_manifest.get("kind")=="vowel":
        target=task_manifest["f0_hz"]
        error=None if features["f0_hz"] is None else abs(features["f0_hz"]/target-1)
        e1.update({"f0_relative_error":error,"f0_control_pass":error is not None and error<=.03 and features["f0_confidence"]>=.65})
    return {"version":"signal-v1","E0_pass":all(checks.values()),"checks":checks,"values":values,"E1":e1,
            "E2":{"state":"unavailable","value":None,"reason":"資格を確認した知覚評価を別台帳で要求"}}
