"""音素・アクセントから16特徴で局所半音残差を計算する共有関数。"""
import re
import numpy as np
from centered_projection import project
FEATURES = ['bias', 'a', 'i', 'u', 'e', 'o', 'nasal', 'previous_stop', 'previous_fricative',
            'previous_nasal', 'high', 'mora_position', 'phrase_position', 'after_accent', 'previous_high', 'next_high']
ELIGIBLE = {'a', 'i', 'u', 'e', 'o', 'N', 'm', 'n', 'my', 'ny'}


def describe(row):
    rows = []
    for i, label in enumerate(row['full_context_labels']):
        phone = re.search(r'\-([^+]+)\+', label).group(1)
        a = re.search(r'/A:(-?\d+)\+(\d+)\+(\d+)', label)
        f = re.search(r'/F:(\d+)_(\d+)#[^@]*@(\d+)_(\d+)', label)
        if not a or not f:
            rows.append({'label_index': i, 'phone': phone, 'high': False, 'x': [0.]*16})
            continue
        count, accent, index, remaining = map(int, f.groups())
        position = int(a.group(2))
        high = position <= accent if accent == 1 else position >= 2 and (accent == 0 or position <= accent)
        rows.append({'label_index': i, 'phone': phone, 'high': high,
            'mora_position': position/max(1, count), 'phrase_position': index/max(1, index+remaining-1),
            'after_accent': accent > 0 and position > accent})
    for i, r in enumerate(rows):
        if 'x' in r:
            continue
        previous = rows[i-1] if i else {'phone': 'sil', 'high': False}
        following = rows[i+1] if i+1 < len(rows) else {'high': False}
        p = previous['phone']
        r['x'] = [1., *[float(r['phone'] == v) for v in ('a', 'i', 'u', 'e', 'o')],
            float(r['phone'] in ('N', 'm', 'n', 'my', 'ny')),
            float(p in ('p', 't', 'k', 'b', 'd', 'g', 'ch', 'ts', 'cl', 'ky', 'gy')),
            float(p in ('s', 'z', 'sh', 'j', 'h', 'f', 'hy')), float(p in ('N', 'm', 'n', 'my', 'ny')),
            float(r['high']), r['mora_position'], r['phrase_position'], float(r['after_accent']),
            float(previous['high']), float(following['high'])]
    assert all(len(r['x']) == 16 for r in rows)
    return rows


def linear_predict(model, x):
    if model['type'] != 'local-ridge' or model['features'] != FEATURES:
        raise ValueError('固定16特徴の局所回帰を要求します')
    return ((np.asarray(x)-np.array(model['x_mean']))/np.array(model['x_scale']))@np.array(model['coefficients'])


def deltas(row, snapshot, predictor):
    descriptions = describe(row)
    eligible = [d for d in descriptions if d['phone'] in ELIGIBLE and
                any(snapshot['msd'][j] > .5 for j in range(d['label_index']*5, (d['label_index']+1)*5))]
    values = np.asarray(predictor(np.array([d['x'] for d in eligible])), dtype=float) if eligible else np.array([])
    if values.shape != (len(eligible),) or not np.isfinite(values).all():
        raise ValueError('局所予測の形状または有限性が不正です')
    values = project(values)
    result = np.zeros(len(snapshot['duration']))
    phones = []
    for d, value in zip(eligible, values):
        for j in range(d['label_index']*5, (d['label_index']+1)*5):
            if snapshot['msd'][j] > .5:
                result[j] = value
        phones.append({'label_index': d['label_index'], 'phone': d['phone'], 'half_tone': float(value)})
    assert np.max(abs(result)) <= 3.+1e-12 and (not len(values) or abs(values.mean()) < 1e-12)
    return result, phones
