"""既知F0や駆動マスクを受け取らない局所周期性の二方式。"""
import numpy as np
FS=24000;STEP=120;FRAMES=240
SPEC={'acf':{'window_samples':720,'rms_min':.03,'correlation_min':.6,'near_max_fraction':.95,'lag_min':30,'lag_max':342},
      'harmonic':{'window_samples':480,'rms_min':.03,'explanation_min':.6,'frequencies':[70.,800.,.5],'harmonics':[1,2,3]},
      'fs':FS,'step':STEP,'frames':FRAMES,'padding':'zero','window':'numpy.hanning symmetric',
      'mean_removal_before_window':True,'harmonic_basis_windowed':False,'smoothing_or_fill':False,
      'parabolic_delta_max':1.,'qr_rank_relative_tolerance':1e-12,'ties':'最小lag／同一残差の最小F0',
      'out_of_range_interpolation':'欠損にし別ピークへの再選択をしない'}

def validate(audio):
    x=np.asarray(audio,dtype=np.float64)
    if x.shape!=(28800,) or not np.isfinite(x).all():raise ValueError('1.2秒の有限単一チャンネル配列を要求します')
    return x

def windows(x,length):
    half=length//2;pad=np.pad(x,(half,half));idx=np.arange(FRAMES)*STEP
    raw=pad[idx[:,None]+np.arange(length)]
    rms=np.sqrt(np.mean(raw**2,axis=1));y=(raw-raw.mean(axis=1)[:,None])*np.hanning(length)
    return raw,rms,y

def normalized_correlation(y):
    n=len(y);ac=np.correlate(y,y,'full')[n-1:];s=np.r_[0.,np.cumsum(y*y)]
    lag=np.arange(n);den=np.sqrt(np.maximum(0.,s[n-lag])*np.maximum(0.,s[n]-s[lag]))
    out=np.full(n,np.nan);np.divide(ac,den,out=out,where=den>0)
    return out

def select_peak(corr):
    k=np.arange(30,343)
    peaks=k[np.isfinite(corr[k])&np.isfinite(corr[k-1])&np.isfinite(corr[k+1])&(corr[k]>=corr[k-1])&(corr[k]>=corr[k+1])]
    if not len(peaks):return None
    top=float(np.max(corr[peaks]))
    if top<=0:return None
    selected=int(peaks[corr[peaks]>=top*.95][0])
    a,b,c=corr[selected-1:selected+2];den=a-2*b+c
    if not np.isfinite(den) or den==0:return None
    delta=.5*(a-c)/den;lag=selected+delta
    if not np.isfinite(delta) or abs(delta)>1 or not 70<=FS/lag<=800:return None
    return float(FS/lag),float(b),selected,float(delta)

class LocalAcf:
    name='acf'
    def measure(self,audio):
        x=validate(audio);_,rms,y=windows(x,720);f=np.zeros(FRAMES);score=np.zeros(FRAMES);reason=[];invalid=[]
        for j,v in enumerate(y):
            energy=float(v@v)
            if not np.isfinite(energy) or energy<=0:reason.append('invalid_energy');invalid.append(j);continue
            if rms[j]<.03:reason.append('low_rms');continue
            peak=select_peak(normalized_correlation(v))
            if peak is None:reason.append('no_valid_peak');continue
            value,confidence,_,_=peak;score[j]=confidence
            if confidence<.6:reason.append('low_correlation');continue
            f[j]=value;reason.append('voiced')
        return f,np.arange(FRAMES)*.005,{'rms':rms,'confidence':score,'reason':np.asarray(reason),'invalid_frames':np.asarray(invalid,dtype=int)}

class LocalHarmonic:
    name='harmonic'
    def __init__(self):
        self.freq=np.arange(70.,800.5,.5);t=(np.arange(480)-240)/FS
        phase=2*np.pi*self.freq[:,None,None]*t[None,:,None]*np.arange(1,4)[None,None,:]
        basis=np.concatenate((np.sin(phase),np.cos(phase)),axis=2)
        q,r=np.linalg.qr(basis,mode='reduced');diag=abs(np.diagonal(r,axis1=1,axis2=2))
        self.rank_ok=np.isfinite(q).all(axis=(1,2))&(diag.min(axis=1)>1e-12*diag.max(axis=1))
        if not self.rank_ok.all():raise ValueError('調波辞書に非有限・特異候補があります')
        self.q=np.ascontiguousarray(q.transpose(0,2,1).reshape(-1,480))
    def measure(self,audio):
        x=validate(audio);_,rms,y=windows(x,480);energy=np.sum(y*y,axis=1)
        invalid=np.flatnonzero(~np.isfinite(energy)|(energy<=0));active=np.flatnonzero((rms>=.03)&np.isfinite(energy)&(energy>0))
        f=np.zeros(FRAMES);score=np.zeros(FRAMES);reason=np.full(FRAMES,'low_rms',dtype='<U32');reason[invalid]='invalid_energy'
        if len(active):
            dots=(self.q@y[active].T).reshape(len(self.freq),6,len(active));explained=np.sum(dots*dots,axis=1)
            residual=energy[active][None,:]-explained
            if not np.isfinite(residual).all():raise ValueError('調波残差が非有限です')
            choice=np.argmin(residual,axis=0);best=explained[choice,np.arange(len(active))]/energy[active]
            score[active]=best;passmask=best>=.6;f[active[passmask]]=self.freq[choice[passmask]]
            reason[active]='low_explanation';reason[active[passmask]]='voiced'
        return f,np.arange(FRAMES)*.005,{'rms':rms,'confidence':score,'reason':reason,'invalid_frames':invalid}

def tests():
    # 数値配列の負例と投影恒等式だけ。音声を作らず保存信号も測らない。
    for bad in [np.empty(0),np.zeros((28800,2)),np.full(28800,np.nan)]:
        try:validate(bad)
        except ValueError:pass
        else:raise AssertionError('不正入力を拒否しません')
    assert select_peak(np.zeros(720)) is None
    corr=np.full(720,-1.);corr[119:122]=[.7,.9,.7];corr[239:242]=[.8,.92,.8]
    assert select_peak(corr)[2]==120
    corr[:]=-1.;corr[29:32]=[.95,.9,.85];assert select_peak(corr) is None
    raw,rms,y=windows(np.arange(28800,dtype=float),480)
    assert raw.shape==y.shape==(240,480) and np.all(raw[0,:240]==0) and raw[0,240]==0 and raw[1,240]==120
    a=np.array([[1.,0.],[0.,1.],[1.,1.],[2.,-1.]]);v=np.array([2.,3.,4.,5.]);q,_=np.linalg.qr(a)
    residual=v@v-np.sum((q.T@v)**2);c=np.linalg.lstsq(a,v,rcond=None)[0]
    assert abs(residual-np.sum((v-a@c)**2))<1e-10
    return {'invalid_array_cases':3,'earliest_near_max_lag_and_out_of_range_rejection':True,
        'zero_padding_center_clock':True,'qr_projection_equals_least_squares_residual':True,'new_audio_or_measurements':0}
