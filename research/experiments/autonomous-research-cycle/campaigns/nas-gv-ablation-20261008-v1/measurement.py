"""固定時計のDIO支持と、独立な全体ACF測定。欠測を分母に残す。"""
import numpy as np
import pyworld
from acoustics import estimate_f0

ELIGIBLE = {'a', 'i', 'u', 'e', 'o', 'N', 'm', 'n', 'my', 'ny'}


def local(f0, times, duration, indices):
    bounds = np.r_[0, np.cumsum(duration)] * .005
    rows = []
    for index in indices:
        mask = (times >= bounds[index * 5]) & (times < bounds[(index + 1) * 5])
        values = f0[mask & (f0 >= 70) & (f0 <= 800)]
        n = int(mask.sum())
        rows.append(dict(index=index, interval_frames=n, voiced_frames=len(values),
            support_complete=n > 0 and len(values) >= 3 and len(values) >= n * .5,
            median_hz=float(np.median(values)) if len(values) else None))
    return rows


def measure(audio, duration, eligible, support=None):
    f0, times = pyworld.dio(audio.astype(float), 24000, f0_floor=70., f0_ceil=800., frame_period=5.)
    f0 = pyworld.stonemask(audio.astype(float), f0, times, 24000)
    native_rows = local(f0, times, duration, eligible)
    if support is None:
        support = [r['index'] for r in native_rows if r['support_complete']]
    local_rows = local(f0, times, duration, support)
    missing = [r['index'] for r in local_rows if not r['support_complete']]
    hop = 240
    rms = np.array([np.sqrt(np.mean(audio[i:i + hop].astype(float) ** 2))
                    for i in range(0, len(audio), hop)])
    active = np.flatnonzero(rms > max(1e-5, .05 * rms.max()))
    hz, confidence = (None, 0.)
    if len(active):
        hz, confidence = estimate_f0(audio[active[0] * hop:min(len(audio), (active[-1] + 1) * hop)],
                                     24000, minimum=70, maximum=800)
    return dict(dio_median_hz=float(np.median(f0[f0 > 0])) if (f0 > 0).any() else None,
                acf_hz=hz, acf_confidence=confidence, support=support,
                missing_support=missing, support_complete=len(support) >= 3 and not missing,
                local=local_rows, eligible_native_intervals=native_rows), f0, times


def pitch_pass(value, target):
    def distance(hz):
        return float(abs(12 * np.log2(hz / target))) if hz is not None and hz > 0 else None
    dio, acf = distance(value['dio_median_hz']), distance(value['acf_hz'])
    return dict(dio_error_semitones=dio, acf_error_semitones=acf,
                passed=bool(dio is not None and acf is not None and dio <= 1. and acf <= 1.
                and value['acf_confidence'] >= .6 and value['support_complete']))

def secondary(audio,duration,support):
    from period_measurement import frame_acf
    x=np.ascontiguousarray(audio,dtype=np.float64)
    h,ht=pyworld.harvest(x,24000,f0_floor=70.,f0_ceil=800.,frame_period=5.)
    a,at,confidence=frame_acf(x)
    value={}
    for name,values,times in [('harvest',h,ht),('centered_acf',a,at)]:
        rows=local(values,times,duration,support)
        value[name]=dict(missing_support=[r['index'] for r in rows if not r['support_complete']],
            local=rows,median_hz=float(np.median(values[values>0])) if (values>0).any() else None,
            Japanese_non_neural_qualified=False,used_for_selection=False)
    return value,dict(harvest=h,harvest_times=ht,centered_acf=a,acf_times=at,acf_confidence=confidence)
