"""既存HTS入力の純粋周期観測。保存波形を生成材料へ戻さない。"""
import ctypes as C,hashlib,io
from pathlib import Path
import numpy as np
from scipy import signal
from scipy.io import wavfile
from hts_arrays import validated,ah
P=C.POINTER(C.c_double);U=C.POINTER(C.c_uint8);S=C.c_size_t
_lib=C.CDLL(str(Path(__file__).resolve().parent/'observer.dylib'))
_fn=_lib.trace_render;_fn.restype=C.c_int
_fn.argtypes=[P,P,P,P,C.c_int,S,S,S,P,P,P,U,S]
def observe(params,settings,native_initial,use_native_initial):
    x=validated(params,settings);before=[ah(a) for a in x]
    first=np.ascontiguousarray(native_initial,dtype=np.float64)
    assert first.shape==(35,) and np.isfinite(first).all()
    first_hash=ah(first)
    n=len(x[0])*240
    raw=np.empty(n);period=np.empty(n);counter=np.empty(n);pulse=np.empty(n,dtype=np.uint8)
    if not _fn(*(a.ctypes.data_as(P) for a in x),first.ctypes.data_as(P),int(use_native_initial),
        len(x[0]),35,x[2].shape[1],raw.ctypes.data_as(P),period.ctypes.data_as(P),
        counter.ctypes.data_as(P),pulse.ctypes.data_as(U),n):
        raise RuntimeError('純粋周期観測の内部検査に不通過')
    assert [ah(a) for a in x]==before and ah(first)==first_hash
    expected=(period>0)&(counter+1>=period)
    assert np.array_equal(pulse.astype(bool),expected)
    idx=np.arange(n-1);same_frame=idx%240!=239;voiced=period[:-1]>0
    predicted=counter[:-1]+1-pulse[:-1]*period[:-1]
    assert np.array_equal(counter[1:][same_frame&voiced],predicted[same_frame&voiced])
    assert np.array_equal(counter[1:][same_frame&~voiced],counter[:-1][same_frame&~voiced])
    boundary=np.arange(239,n-1,240)
    continuous=(x[1][:-1,0]>0)&(x[1][1:,0]>0)
    assert counter[0]==period[0]
    assert np.array_equal(counter[boundary+1][continuous],predicted[boundary][continuous])
    assert np.array_equal(counter[boundary+1][~continuous],period[boundary+1][~continuous])
    audio=signal.resample_poly(raw/32768.,1,2)
    fade=min(round(.012*24000),len(audio)//2);envelope=np.sin(np.linspace(0,np.pi/2,fade))**2
    audio[:fade]*=envelope;audio[-fade:]*=envelope[::-1]
    out=io.BytesIO();wavfile.write(out,24000,(audio*.25).astype(np.float32));data=out.getvalue()
    return data,dict(period=period,counter_before=counter,pulse=pulse),dict(
        sha256=hashlib.sha256(data).hexdigest(),actual_render=1,
        sample_clock=48000,sample_count=n,pulse_count=int(pulse.sum()),
        no_state_writes_by_observer=True,one_original_excitation_call_per_sample=True,
        phase_recurrence_exact=True,input_streams_unchanged=True,source_period_only=True,
        perceived_pitch_truth_claimed=False)
def ground(period,times):
    rows=[];freq=np.zeros(len(period));mask=period>0;freq[mask]=48000/period[mask]
    for t in times:
        c=round(float(t)*48000);a,b=c-1440,c+1440
        typ='edge';hz=None
        if a>=0 and b<=len(period) and (period[a:b]>0).all():
            f=freq[a:b];spread=float(12*np.log2(f.max()/f.min()))
            if spread<=1.:typ='positive';hz=float(np.median(f))
            else:typ='dynamic'
        elif c>=960 and c+960<=len(period) and (period[c-960:c+960]==0).all():
            typ='negative'
        elif a>=0 and b<=len(period):typ='boundary'
        rows.append(dict(time=float(t),kind=typ,source_hz=hz))
    return rows
def score(values,times,period):
    gt=ground(period,times);positive=np.array([r['kind']=='positive' for r in gt])
    negative=np.array([r['kind']=='negative' for r in gt]);accepted=(values>=70)&(values<=800)
    target=np.array([r['source_hz'] or 1. for r in gt]);errors=np.full(len(values),np.inf)
    errors[accepted]=np.abs(12*np.log2(values[accepted]/target[accepted]))
    correct=positive&accepted&(errors<=1.);p=int(positive.sum());n=int(negative.sum())
    coverage=float(correct.sum()/p) if p else 0.;false=int((negative&accepted).sum())
    uv=float(false/n) if n else 1.
    med=float(np.median(errors[positive])) if p else None
    return dict(positive_frames=p,negative_frames=n,correct_positive=int(correct.sum()),
        accepted_positive=int((positive&accepted).sum()),positive_missing=int((positive&~accepted).sum()),
        coverage=coverage,median_error_semitones=med if med is not None and np.isfinite(med) else None,
        negative_false_accept=false,negative_false_accept_rate=uv,
        exclusions={k:sum(r['kind']==k for r in gt) for k in ['edge','dynamic','boundary']},
        passed=bool(p>=3 and n>=3 and coverage>=.9 and med is not None and med<=1. and uv<=.05),
        excitation_period_diagnostic_only=True,perceived_pitch_truth=False)
