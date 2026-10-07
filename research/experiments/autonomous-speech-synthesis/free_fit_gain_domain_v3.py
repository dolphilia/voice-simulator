"""旧3利得の全相対領域を保つ2変数写像。音声による自己回復は未検証。"""
import numpy as np
from free_fit_bounds_v2 import voice_from_point as six_voice


def gains_from_point(point):
    """正方形からlog相対利得の六角形へ放射方向の一対一写像を作る。"""
    point=np.asarray(point,dtype=float)
    if point.shape!=(2,) or not np.all(np.isfinite(point)) or np.any((point<0)|(point>1)):
        raise ValueError('利得点は0〜1の有限な2変数です')
    raw=2*point-1;radius=np.max(abs(raw));span=max(0.,*raw)-min(0.,*raw)
    logratios=raw*np.log(20.)*radius/span if span>0 else raw
    loggains=np.r_[0.,logratios];gains=np.exp(loggains-np.max(loggains))
    return gains


def point_from_gains(gains):
    gains=np.asarray(gains,dtype=float)
    if gains.shape!=(3,) or not np.all(np.isfinite(gains)) or np.any(gains<=0) or min(gains)/max(gains)<.05-1e-12:
        raise ValueError('3利得の最大/最小比は20以内である必要があります')
    direction=np.log(gains[1:]/gains[0])/np.log(20.)
    radius=np.max(abs(direction));span=max(0.,*direction)-min(0.,*direction)
    raw=direction*span/radius if radius>0 else direction
    return np.clip((raw+1)/2,0.,1.)


def voice_from_point(base,vowel,z):
    z=np.asarray(z,dtype=float)
    if z.shape!=(5,) or not np.all(np.isfinite(z)) or np.any((z<0)|(z>1)):
        raise ValueError('声道適合点は0〜1の有限な5変数です')
    v=six_voice(base,vowel,np.r_[z[:3],.5,.5,.5])
    v['formant_gains']=gains_from_point(z[3:]).tolist()
    return v
