"""同一の二条件最大値を適合・利得決定・採否に使う。"""
import math
import numpy as np


def metrics(error):
    e = np.asarray(error, dtype=np.float64)
    if e.ndim != 1 or not len(e) or not np.all(np.isfinite(e)):
        raise ValueError('誤差列が空または非有限です')
    r = float(np.sqrt(np.mean(e*e)))
    m = float(np.max(np.abs(e)))
    return dict(R=r, M=m, J=max(r, m/3))


def intersection(t, mu, variance, low, high):
    rad = t*t-variance
    if rad < 0:
        return None
    radius = math.sqrt(rad)
    left, right = max(-mu-radius, -3*t-low), min(-mu+radius, 3*t-high)
    return (left, right) if left <= right else None


def optimal_gain(q):
    q = np.asarray(q, dtype=np.float64)
    metrics(q)
    mu = float(np.mean(q))
    variance = float(np.mean((q-mu)**2))
    qmin, qmax = float(np.min(q)), float(np.max(q))
    lo, hi = 0., metrics(q-mu)['J']
    if hi == 0:
        a = -mu
    else:
        # 丸めで初期上限だけが空になる場合、次の表現可能値を使う。
        while intersection(hi, mu, variance, qmin, qmax) is None:
            hi = float(np.nextafter(hi, np.inf))
        while hi-lo > 1e-8:
            mid = (lo+hi)/2
            if intersection(mid, mu, variance, qmin, qmax) is None:
                lo = mid
            else:
                hi = mid
        left, right = intersection(hi, mu, variance, qmin, qmax)
        a = min(max(-mu, left), right)
    return float(a), metrics(q+a)


def state(jfit, jcheck):
    q = max(jfit, jcheck)
    if not np.isfinite(q):
        raise ValueError('採否の値が非有限です')
    return 'pass' if q <= .999 else 'fail' if q >= 1.001 else 'uncertain'


def route(p5, p5z, flags):
    if p5 == 'pass':
        return 'P5'
    if p5 == 'fail' and not flags and p5z == 'pass':
        return 'P5+P5Z'
    return 'P5-unconfirmed'
