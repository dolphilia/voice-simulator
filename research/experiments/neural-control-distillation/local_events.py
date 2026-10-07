"""波形から得る局所イベント候補。VOTの正解や知覚判定とはみなさない。"""
import numpy as np
from scipy import signal


def event_candidates(audio,fs):
    x=np.asarray(audio,dtype=float)
    if x.ndim!=1 or len(x)<round(fs*.08) or not np.isfinite(x).all() or fs<8000:
        return {'status':'unavailable','reason':'単一チャンネル・80ms以上・有限値・8kHz以上を要求'}
    x=x-x.mean()
    peak=np.max(abs(x))
    if peak<1e-8:return {'status':'unavailable','reason':'無音'}
    x=x/peak
    hop=max(1,round(.001*fs));window=round(.025*fs)
    high=signal.sosfilt(signal.butter(3,1500,fs=fs,btype='highpass',output='sos'),x)
    times=[];rms=[];high_energy=[];periodicity=[]
    lo=max(1,int(fs/450));hi=int(fs/70)
    for start in range(0,len(x)-window+1,hop):
        a=x[start:start+window];a=a-a.mean()
        values=[]
        for lag in range(lo,min(hi,len(a)//2)+1):
            left,right=a[:-lag],a[lag:]
            denom=np.sqrt(np.dot(left,left)*np.dot(right,right))
            values.append(float(np.dot(left,right)/denom) if denom>1e-12 else 0.)
        times.append((start+window/2)/fs);rms.append(float(np.sqrt(np.mean(a*a))))
        high_energy.append(float(np.mean(high[start:start+window]**2)))
        periodicity.append(max(values,default=0.))
    t=np.array(times);r=np.array(rms);h=np.array(high_energy);p=np.array(periodicity)
    active=r>max(.002,.04*max(r))
    voiced=active&(p>=.75)
    # 10ms以上続く周期性候補の開始。25ms窓なので境界は最大約半窓分ぼける。
    run=max(1,round(.01*fs/hop));voiced_starts=np.flatnonzero(np.convolve(voiced.astype(int),np.ones(run,dtype=int),mode='valid')==run)
    voice=float(t[voiced_starts[0]]) if len(voiced_starts) else None
    # 最初の活動から250ms以内の高域エネルギー増加。放出の独立した正解位置ではない。
    onset=np.flatnonzero(active)
    if not len(onset):return {'status':'unavailable','reason':'活動区間不足'}
    start=float(t[onset[0]]);step=max(1,round(.005*fs/hop))
    difference=np.zeros(len(h));difference[step:]=h[step:]-h[:-step]
    mask=active&(t>=start)&(t<=start+.25)
    candidates=np.flatnonzero(mask)
    burst_index=int(candidates[np.argmax(difference[candidates])])
    burst=float(t[burst_index])
    return {'status':'diagnostic-only','activity_start_seconds':start,'burst_candidate_seconds':burst,
        'periodicity_start_seconds':voice,'candidate_vot_ms':None if voice is None else 1000*(voice-burst),
        'frame_ms':1000*window/fs,'hop_ms':1000*hop/fs,'periodic_frame_fraction':float(np.mean(voiced)),
        'burst_strength':float(difference[burst_index]),'frame_times':t.tolist(),
        'rms':r.tolist(),'high_energy':h.tolist(),'periodicity':p.tolist(),
        'qualification':'未資格。持続母音開始や雑音を破裂と混同しうる。単語単位の探索窓と日本語の独立注釈が必要'}
