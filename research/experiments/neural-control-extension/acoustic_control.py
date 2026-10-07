"""波形上の発話時間とF0を予測する固定サイズの制御。VTL指令値は使わない。"""
import numpy as np

FEATURE_NAMES = ['bias','vowel_fraction','stop_fraction','fricative_fraction','nasal_fraction',
                 'liquid_fraction','palatal_fraction','unvoiced_vowel_fraction','high_mora_fraction','phrase_per_mora']


def features(row):
    phones = row['phonemes']
    if not 1 <= len(phones) <= 120:
        raise ValueError('研究版は1〜120音素を対象にします')
    moras = [m for p in row['phrases'] if not p.get('pause') for m in p['moras']]
    pauses = sum(bool(p.get('pause')) for p in row['phrases'])
    if not moras:
        raise ValueError('モーラがありません')
    sets = [('a','i','u','e','o','I','U'),('p','t','k','b','d','g','ch','ts','Q','ky','gy','by','py'),
            ('s','z','sh','j','h','f','hy'),('m','n','N','my','ny'),('r','ry'),
            ('ky','gy','ny','hy','my','ry','by','py'),('I','U')]
    x = [1., *[sum(p in s for p in phones)/len(phones) for s in sets],
         sum(bool(m['high']) for m in moras)/len(moras),
         sum(not p.get('pause') for p in row['phrases'])/len(moras)]
    return np.array(x), .2*len(moras)+.14*pauses


def decode(y, baseline_seconds, requested_f0=220., speed=1.):
    if not np.isfinite([requested_f0,speed]).all() or not 140 <= requested_f0 <= 320 or not .75 <= speed <= 1.3:
        raise ValueError('検証用の指定範囲はF0参照140–320Hz、速度0.75–1.3です')
    raw_duration = baseline_seconds*np.exp(float(y[0]))/speed
    raw_f0 = requested_f0*np.exp(float(y[1]))
    return {'active_seconds':float(np.clip(raw_duration,.1,30)), 'f0_hz':float(np.clip(raw_f0,70,600)),
            'unbounded_active_seconds':float(raw_duration),'unbounded_f0_hz':float(raw_f0),
            'target_saturated':bool(not .1 <= raw_duration <= 30 or not 70 <= raw_f0 <= 600)}


def predict(model, row, requested_f0=220., speed=1.):
    if model.get('quantity') != 'acoustic-active-duration-and-f0' or model.get('type') != 'ridge':
        raise ValueError('音響量の固定回帰モデルを要求します')
    x, baseline_seconds = features(row)
    y = ((x-np.array(model['x_mean']))/np.array(model['x_scale']))@np.array(model['coefficients'])
    y = y*np.array(model['y_scale'])+np.array(model['y_mean'])
    return decode(y,baseline_seconds,requested_f0,speed)


def measure_wide(audio, fs=24000):
    from acoustics import estimate_f0
    x = np.asarray(audio,dtype=float)
    hop = round(.01*fs)
    rms = np.array([np.sqrt(np.mean(x[i:i+hop]**2)) for i in range(0,len(x),hop)])
    active = np.flatnonzero(rms > max(1e-5,.05*rms.max()))
    if not len(active):
        raise ValueError('活動区間がありません')
    start, end = active[0]*hop, min(len(x),(active[-1]+1)*hop)
    f0, confidence = estimate_f0(x[start:end],fs,minimum=70,maximum=800)
    if f0 is None or confidence < .4:
        raise ValueError('広帯域F0の信頼度不足')
    return {'active_seconds':float((end-start)/fs),'f0_hz':f0,'confidence':confidence}


def map_to_hts(target, measured):
    speed = measured['active_seconds']/target['active_seconds']
    shift = 12*np.log2(target['f0_hz']/measured['f0_hz'])
    return {'speed':float(np.clip(speed,.5,2.)), 'half_tone':float(np.clip(shift,-12,12)),
            'unbounded_speed':float(speed),'unbounded_half_tone':float(shift),
            'saturated':bool(not .5 <= speed <= 2 or not -12 <= shift <= 12)}


def refine_hts(target, previous, measured):
    speed = previous['speed']*measured['active_seconds']/target['active_seconds']
    shift = previous['half_tone']+12*np.log2(target['f0_hz']/measured['f0_hz'])
    return {'speed':float(np.clip(speed,.5,2.)), 'half_tone':float(np.clip(shift,-12,12)),
            'unbounded_speed':float(speed),'unbounded_half_tone':float(shift),
            'saturated':bool(not .5 <= speed <= 2 or not -12 <= shift <= 12)}
