"""支持域を固定した局所形状損失、更新、候補受理の純粋関数。"""
import numpy as np
from centered_projection import project
INDICES = [10, 11, 12, 13]
REGULARIZATION = .1


def vector(values, length=None):
    x = np.asarray(values, dtype=float)
    if x.ndim != 1 or not len(x) or not np.isfinite(x).all() or (length is not None and len(x) != length):
        raise ValueError('非空・一次元・有限・固定長の値を要求します')
    return x


def centered_semitones(log_f0):
    x = vector(log_f0)
    return (x-x.mean())*12/np.log(2)


def coefficients(values):
    c = vector(values, 4)
    if np.max(abs(c)) > 3:
        raise ValueError('4係数を±3以内にします')
    return c


def phone_residuals(x, c):
    x = np.asarray(x, dtype=float)
    if x.ndim != 2 or x.shape[1] != 16 or not np.isfinite(x).all():
        raise ValueError('固定16特徴の有限行列を要求します')
    return project(x[:, INDICES]@coefficients(c))


def residual(teacher_shape, observed_shape, c):
    t = vector(teacher_shape)
    o = vector(observed_shape, len(t))
    return np.r_[(o-t)/np.sqrt(len(t)), np.sqrt(REGULARIZATION)*coefficients(c)]


def objective(teacher_shape, observed_shape, c):
    r = residual(teacher_shape, observed_shape, c)
    return float(r@r)


def update(jacobian, target_minus_current, current):
    error = vector(target_minus_current)
    j = np.asarray(jacobian, dtype=float)
    c = coefficients(current)
    if j.shape != (len(error), 4) or not np.isfinite(j).all():
        raise ValueError('ヤコビアンの形状・有限性が不正です')
    normal = j.T@j/len(error)+REGULARIZATION*np.eye(4)
    rhs = j.T@error/len(error)-REGULARIZATION*c
    step = np.clip(np.linalg.solve(normal, rhs), -.5, .5)
    return np.clip(c+step, -3., 3.)


def accept(previous, candidate):
    if candidate.get('status') != 'completed' or not candidate.get('support_complete') or not candidate.get('E0_pass') or not candidate.get('internal_unchanged'):
        return False
    cost = candidate.get('objective')
    return cost is not None and np.isfinite(cost) and cost < previous['objective']


def extract_local(f0, times, snapshot, indices):
    f0, times = vector(f0), vector(times)
    if len(f0) != len(times) or np.any(np.diff(times) <= 0):
        raise ValueError('DIO時刻の形状・単調性が不正です')
    boundaries = np.r_[0, np.cumsum(snapshot['duration'])]*.005
    found, missing = [], []
    for index in indices:
        lo, hi = int(index)*5, (int(index)+1)*5
        if lo < 0 or hi >= len(boundaries):
            raise ValueError('音素区間が状態列範囲外です')
        mask = (times >= boundaries[lo]) & (times < boundaries[hi])
        voiced = f0[mask & (f0 >= 70) & (f0 <= 800)]
        if len(voiced) < 3 or len(voiced) < mask.sum()*.5:
            missing.append(int(index))
        else:
            found.append({'label_index': int(index), 'wave_log_f0': float(np.log(np.median(voiced))),
                'voiced_frames': len(voiced), 'interval_frames': int(mask.sum())})
    return found, missing


def tests():
    assert np.allclose(centered_semitones(np.log([100,200])) , [-6,6])
    x=np.zeros((3,16));x[:,10]=[0,1,0]
    assert np.max(abs(phone_residuals(x,[3,0,0,0]))) <= 3
    before={'objective':1.}
    good={'status':'completed','support_complete':True,'E0_pass':True,'internal_unchanged':True,'objective':.5}
    assert accept(before,good)
    for bad in [dict(good,objective=1.),dict(good,objective=float('nan')),dict(good,status='failed'),
                dict(good,support_complete=False),dict(good,E0_pass=False),dict(good,internal_unchanged=False)]:
        assert not accept(before,bad)
    assert not accept(before,{})
    rejected=0
    for f in [lambda: vector([]), lambda: vector([np.nan]),lambda: coefficients([0,0,0,3.01]),
              lambda: residual([0,1],[0],[0]*4),lambda: phone_residuals(np.zeros((2,15)),[0]*4),
              lambda: update(np.zeros((2,3)),[1,2],[0]*4)]:
        try: f()
        except ValueError: rejected += 1
    assert rejected==6
    c=update(np.eye(4),[100]*4,[0]*4);assert np.array_equal(c,[.5]*4)
    s={'duration':[1]*10};t=np.arange(11)*.005;f=np.full(11,100.)
    found, missing=extract_local(f,t,s,[0,1]);assert len(found)==2 and not missing
    f[5:]=0;found,missing=extract_local(f,t,s,[0,1]);assert len(found)==1 and missing==[1]
    return {'acceptance_positive':True,'acceptance_negative_cases':7,'invalid_inputs_rejected':rejected,
        'fixed_support_missing_rejected':True,'bounded_step':True,'new_render_calls':0,'new_ai_calls':0,'new_fit_calls':0}

if __name__ == '__main__': print(tests())
