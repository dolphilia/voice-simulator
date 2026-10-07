"""測定振幅を受け取らない、固定変数だけによる候補生成器。"""
import numpy as np

FS = 16000


def decode(x):
    x = np.asarray(x, dtype=np.float64)
    if x.shape not in ((10,), (12,)) or not np.all(np.isfinite(x)) or np.any((x < 0) | (x > 1)):
        raise ValueError('正規化変数が範囲外または非有限です')
    p = dict(f=(100 + 7400*x[:5]).tolist(), B=np.exp(np.log(3000)*x[5:10]).tolist(), g=1.)
    if len(x) == 12:
        p.update(fz=float(100+7400*x[10]), rho=float(.999*x[11]))
    return p


def encode(p):
    x = [(v-100)/7400 for v in p['f']] + [np.log(v)/np.log(3000) for v in p['B']]
    if 'rho' in p:
        x += [(p['fz']-100)/7400, p['rho']/.999]
    return np.asarray(x, dtype=np.float64)


def response(p, frequency):
    f = np.asarray(frequency, dtype=np.float64)
    x = encode(p)
    decode(x)
    if f.ndim != 1 or not len(f) or not np.all(np.isfinite(f)) or np.any(np.abs(f) > FS/2):
        raise ValueError('評価周波数が不正です')
    g = float(p['g'])
    if not np.isfinite(g) or g <= 0:
        raise ValueError('利得は正の有限値が必要です')
    z = np.exp(-2j*np.pi*f/FS)
    h = np.full(f.shape, g, dtype=np.complex128)
    for fi, bi in zip(p['f'], p['B'], strict=True):
        r = np.exp(-np.pi*bi/FS)
        h /= 1 - 2*r*np.cos(2*np.pi*fi/FS)*z + r*r*z*z
    if 'rho' in p:
        r = p['rho']
        h *= 1-2*r*np.cos(2*np.pi*p['fz']/FS)*z+r*r*z*z
    if not np.all(np.isfinite(h)) or np.any(np.abs(h) == 0):
        raise ValueError('応答計算が非有限またはゼロになりました')
    return h


def sorted_parameters(p):
    order = np.argsort(p['f'], kind='stable')
    return {**p, 'f': [p['f'][i] for i in order], 'B': [p['B'][i] for i in order]}


def known(zero=False):
    p = dict(f=[650.,1350.,2500.,3650.,4650.], B=[80.,100.,120.,150.,180.], g=1.)
    if zero:
        p.update(rho=.98, fz=2000.)
    return p


def starts(p5=None):
    u = np.random.Generator(np.random.PCG64(20260913)).random((3,12))
    base = encode(dict(f=[500,1500,2500,3500,4500], B=[120]*5))
    if p5 is None:
        return [base] + [row[:10].copy() for row in u]
    return [encode({**p5, 'rho':0., 'fz':2000.})] + [
        np.r_[row[:11], (.5+.499*row[11])/.999] for row in u]
