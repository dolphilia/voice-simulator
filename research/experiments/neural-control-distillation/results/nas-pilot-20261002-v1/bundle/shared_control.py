"""参照音声にアクセスしない、文章文脈からの共有制御。NumPyだけで動く。"""
import numpy as np
from renderer import baseline

PHONES = ['a','i','u','e','o','I','U','k','g','s','z','sh','j','t','d','ch','ts',
          'n','h','f','b','p','m','y','r','w','N','Q','pau','ky','gy','ny','hy','my','ry','by','py']
FAMILIES = ['vowel', 'stop', 'fricative', 'nasal', 'liquid', 'other', 'edge']


def family(phone):
    if phone is None:
        return 'edge'
    if phone in ('a','i','u','e','o','I','U'):
        return 'vowel'
    if phone in ('p','t','k','b','d','g','ch','ts','Q','ky','gy','by','py'):
        return 'stop'
    if phone in ('s','z','sh','j','h','f','hy'):
        return 'fricative'
    if phone in ('m','n','N','my','ny'):
        return 'nasal'
    if phone in ('r','ry'):
        return 'liquid'
    return 'other'


def features(analysis, requested_f0=220., speed=1.):
    phones = analysis['phonemes']
    d, f = baseline(analysis, requested_f0, speed)
    morphology = []
    phrases = analysis['phrases']
    for pi, phrase in enumerate(phrases):
        if phrase.get('pause'):
            morphology.append([0.,0.,1.,0.,pi/max(1,len(phrases)-1)])
            continue
        for mi, mora in enumerate(phrase['moras']):
            for index, phone in enumerate(mora['phones']):
                morphology.append([mi/max(1,len(phrase['moras'])-1),float(mora['high']),
                                   float(mi==len(phrase['moras'])-1),
                                   float(index==len(mora['phones'])-1), pi/max(1,len(phrases)-1)])
    if len(morphology) != len(phones):
        raise ValueError('文脈と音素の対応が不一致です')
    rows = []
    for i, phone in enumerate(phones):
        if phone not in PHONES:
            raise ValueError(f'共有制御の未対応音素: {phone}')
        position = i/max(1,len(phones)-1)
        onehot = [float(phone==p) for p in PHONES]
        neighbors = []
        for adjacent in (phones[i-1] if i else None, phones[i+1] if i+1<len(phones) else None):
            neighbors.extend(float(family(adjacent)==name) for name in FAMILIES)
        rows.append([1.,*onehot,*neighbors,position,position**2,float(i==0),float(i==len(phones)-1),
                     min(len(phones),60)/30.,*morphology[i],np.log(requested_f0/220.),np.log(speed),
                     *[value*position for value in onehot]])
    return np.array(rows), d, f


def decode(analysis, corrections, requested_f0=220., speed=1.):
    _, d, f = features(analysis, requested_f0, speed)
    y = np.asarray(corrections)
    if y.shape != (len(d),2) or not np.isfinite(y).all():
        raise ValueError('予測制御が不正です')
    raw_d, raw_f = d*np.exp(y[:,0]), f*np.exp(y[:,1])
    bounded_d, bounded_f = np.clip(raw_d,.025,.6), np.clip(raw_f,70,450)
    return bounded_d, bounded_f, {'duration_saturated':int(np.count_nonzero(raw_d!=bounded_d)),
                                'f0_saturated':int(np.count_nonzero(raw_f!=bounded_f))}


def predict(model, analysis, requested_f0=220., speed=1.):
    x, _, _ = features(analysis, requested_f0, speed)
    if model['type'] != 'ridge':
        raise ValueError('未対応の共有モデルです')
    y = ((x-np.array(model['x_mean']))/np.array(model['x_scale'])) @ np.array(model['coefficients'])
    y = y*np.array(model['y_scale'])+np.array(model['y_mean'])
    return decode(analysis, y, requested_f0, speed)
