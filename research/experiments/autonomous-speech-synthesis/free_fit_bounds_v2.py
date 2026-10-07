"""次版用の自由適合係数写像。フォルマント順序を全探索点で保つ。"""
import copy
import numpy as np


def voice_from_point(base,vowel,z):
    point=np.asarray(z,dtype=float)
    if point.shape!=(6,) or not np.all(np.isfinite(point)) or np.any((point<0)|(point>1)):
        raise ValueError('自由適合点は有限な0〜1の6係数で指定してください')
    original=np.asarray(base['formants_hz'][vowel],dtype=float)
    lower=.85*original;upper=1.15*original
    boundaries=.5*(original[:-1]+original[1:])
    # 隣接共鳴の探索区間を2Hz離す。独立した倍率でF2/F3が逆転する問題を防ぐ。
    upper[:-1]=np.minimum(upper[:-1],boundaries-1.)
    lower[1:]=np.maximum(lower[1:],boundaries+1.)
    if np.any(lower>=upper):raise ValueError('基準フォルマントから有効な探索区間を作れません')
    voice=copy.deepcopy(base)
    voice['formants_hz'][vowel]=(lower+(upper-lower)*point[:3]).tolist()
    voice['formant_gains']=(.05+.95*point[3:]).tolist()
    return voice
