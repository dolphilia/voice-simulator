"""各評価を保存する有限予算の修正Powell探索。Dcheckは入力にない。"""
import numpy as np
from scipy.optimize import minimize
from .models import decode, response, sorted_parameters, starts
from .objective import optimal_gain


class BudgetExhausted(Exception):
    pass


def rank(record):
    return tuple(record[k] for k in ('J','R','M','start','evaluation'))


def fit(frequency, observed_db, setting, budget, p5=None):
    target = np.asarray(observed_db, dtype=np.float64)
    if target.shape != np.asarray(frequency).shape or not np.all(np.isfinite(target)):
        raise ValueError('適合点の形状・値が不正です')
    histories, endings = [], []
    initial = starts(p5)
    for j, x0 in enumerate(initial):
        history = []
        def objective(x):
            if len(history) >= budget:
                raise BudgetExhausted()
            p = decode(x)
            q = 20*np.log10(np.abs(response(p, frequency)))-target
            a, score = optimal_gain(q)
            p['g'] = float(10**(a/20))
            history.append(dict(**score, start=j, evaluation=len(history)+1,
                                x=np.asarray(x).tolist(), parameters=sorted_parameters(p), gain_db=a))
            return score['J']
        options = dict(xtol=setting['xtol'], ftol=setting['ftol'], maxiter=budget,
                       maxfev=budget, direc=np.eye(len(x0)))
        try:
            result = minimize(objective, x0, method='Powell', bounds=[(0.,1.)]*len(x0), options=options)
            ending = dict(status=int(result.status), message=str(result.message), nfev=int(result.nfev))
        except BudgetExhausted:
            ending = dict(status=1, message='外側の評価上限', nfev=len(history))
        histories.append(history)
        endings.append(ending)
    best = min((r for h in histories for r in h), key=rank)
    if p5 is not None:
        # 開始点0の最初の評価が、利得もDfitだけで処理した包含候補。
        embedded = histories[0][0]
        if best['J'] > embedded['J']+1e-8:
            raise ValueError('包含候補の保存が不整合です')
    curves = [[min(r['J'] for r in h[:max(1,int(budget*q))]) for q in (.25,.5,.75,1.)] for h in histories]
    aggregate = np.min(curves, axis=0)
    counted = curves[1:] if p5 is not None else curves
    plateau = bool(aggregate[2]-aggregate[3] <= .01 and sum(c[-1] <= aggregate[-1]+.01 for c in counted) >= 2)
    x = np.asarray(best['x'])
    boundary = (x <= .005) | (x >= .995)
    if len(x) == 12 and x[11] == 0:
        boundary[10:] = False
    return dict(best=best, histories=histories, endings=endings, starts=[decode(x) for x in initial],
                budget=budget, evaluations=sum(map(len,histories)), curves=curves,
                aggregate_curve=aggregate.tolist(), plateau=plateau, boundary=bool(np.any(boundary)))
