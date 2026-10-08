"""固定幅の累積平均正規化差分による限定YIN型測定。完全YINとは呼ばない。"""
import numpy as np
FS=24000;FMIN=70.;FMAX=800.;THRESHOLD=.1
def difference(x):
    a=np.asarray(x,dtype=np.float64);maximum=int(np.floor(FS/FMIN));width=len(a)-maximum
    if a.ndim!=1 or width<3 or not np.isfinite(a).all():raise ValueError('窓幅または有限入力が不正')
    d=np.zeros(maximum+1)
    for lag in range(1,maximum+1):d[lag]=np.sum((a[:width]-a[lag:lag+width])**2)
    c=np.ones_like(d);total=np.cumsum(d[1:]);np.divide(d[1:]*np.arange(1,maximum+1),total,out=c[1:],where=total>0.)
    return d,c,width
def estimate(x):
    a=np.asarray(x,dtype=np.float64);d,c,width=difference(a)
    if np.var(a)<1e-20:return dict(hz=None,period=None,confidence=0.,reason='無変動',difference_width=width)
    minimum=int(np.ceil(FS/FMAX));selected=None
    for lag in range(minimum,len(c)-1):
        if c[lag]<THRESHOLD:
            while lag+1<len(c)-1 and c[lag+1]<c[lag]:lag+=1
            selected=lag;break
    if selected is None:return dict(hz=None,period=None,confidence=float(1.-min(c[minimum:])),reason='固定閾値未達',difference_width=width)
    left,center,right=c[selected-1:selected+2];denominator=left-2.*center+right
    shift=0. if denominator<=0. else float(np.clip(.5*(left-right)/denominator,-1.,1.));period=selected+shift
    confidence=float(1.-center)
    # 同じ差分幅で少なくとも一周期を平均し、二つの周期区間を観測する保守規則。
    if width<period:return dict(hz=None,period=float(period),confidence=confidence,reason='差分幅が一周期未満',difference_width=width)
    hz=float(FS/period)
    if not FMIN<=hz<=FMAX:return dict(hz=None,period=float(period),confidence=confidence,reason='探索範囲外',difference_width=width)
    return dict(hz=hz,period=float(period),confidence=confidence,reason='推定',difference_width=width)
