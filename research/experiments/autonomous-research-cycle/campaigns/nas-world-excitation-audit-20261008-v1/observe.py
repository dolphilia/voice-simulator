"""既存768WORLD波形を再構成して同一性を条件に実励振を観測する。"""
from paths import *
import ctypes,io,sys,os
def load():
    import tempfile
    assert Path(tempfile.gettempdir()).resolve()==Path(os.environ['TMPDIR']).resolve()
    sys.path[:0]=[str(PERIOD/'runtime-bundle/packages-v2'),str(CONVERT)]
    import numpy as np
    from scipy import signal
    from scipy.io import wavfile
    import pyworld
    import world_renderer2 as world
    binary=Path(pyworld.pyworld.__file__)
    ctypes.CDLL(str(binary),mode=ctypes.RTLD_GLOBAL)
    lib=ctypes.CDLL(str(HERE/'observer.dylib'))
    ptr=ctypes.c_void_p
    lib.ObsRun.argtypes=[ptr,ctypes.c_int,ptr,ptr,ctypes.c_int,ctypes.c_double,ctypes.c_int,ctypes.c_int]+[ptr]*10
    lib.ObsRun.restype=ctypes.c_int
    return np,signal,wavfile,world,lib
def evaluate(item,modules):
    np,signal,wavfile,world,lib=modules
    for k in ['record','parameters','wave']:assert digest(REPO/item[k])==item[k+'_sha256'],(item['id'],k)
    old=read(REPO/item['record']);meta=old['meta']
    with np.load(REPO/item['parameters']) as a:
        assert all(k in a.files for k in ['mcp','lf0','lpf']),a.files
        params=[a[k].copy() for k in ['mcp','lf0','lpf']]
    assert meta['settings']['sampling_frequency']==48000 and meta['settings']['fperiod']==240 and meta['settings']['beta']==0
    (f0,sp,ap),converted=world.convert(params)
    expected=meta['conversion']
    factor=float(expected.get('AP_noise_power_factor',1.))
    assert factor in [1.,.5]
    if factor!=1.:
        assert world.ah(ap)==expected['AP_before_sha256']
        ap=ap.copy();voiced=f0>0;ap[voiced]*=np.sqrt(factor);np.clip(ap,.001,1.,out=ap)
    for k,a in [('f0',f0),('power',sp),('AP',ap)]:assert world.ah(a)==expected[k+'_sha256'],(item['id'],k)
    before=[world.ah(x) for x in [f0,sp,ap]]
    length=len(f0)*240;raw=np.zeros(length);pc=np.zeros(length);ac=np.zeros(length)
    idx=np.zeros(length,dtype=np.int32);shift=np.zeros(length);noise=np.zeros(length,dtype=np.int32)
    ratio=np.zeros(length);norm=np.zeros(length);vuv=np.zeros(length,dtype=np.uint8);emit=np.zeros(length,dtype=np.uint8)
    pointers=lambda a:np.asarray(a.ctypes.data+np.arange(len(a),dtype=np.uintp)*a.strides[0],dtype=np.uintp)
    spp=pointers(sp);app=pointers(ap)
    address=lambda a:ctypes.c_void_p(a.ctypes.data)
    count=lib.ObsRun(address(f0),len(f0),address(spp),address(app),4096,5.,48000,length,
        *[address(a) for a in [raw,idx,shift,noise,ratio,norm,vuv,emit,pc,ac]])
    assert count>0 and [world.ah(x) for x in [f0,sp,ap]]==before
    assert np.isfinite(raw).all() and np.isfinite(pc).all() and np.isfinite(ac).all()
    delta=float(np.max(abs(raw-pc-ac)));assert delta<1e-10
    idx=idx[:count];shift=shift[:count];noise=noise[:count];ratio=ratio[:count];norm=norm[:count];emit=emit[:count]
    assert np.all(np.diff(idx)>0) and np.all((shift>=0)&(shift<=1/48000))
    assert np.array_equal(noise[:-1],np.diff(idx)) and noise[-1]==0
    assert np.all(norm[(vuv[idx]==0)|(ratio>.999)]==0)
    assert np.array_equal(emit.astype(bool),(vuv[idx]>0)&(norm>0)&(noise>0))
    kept=len(params[0])*240
    def finish(x):
        y=signal.resample_poly(x[:kept],1,2);n=min(round(.012*24000),len(y)//2);env=np.sin(np.linspace(0,np.pi/2,n))**2
        y[:n]*=env;y[-n:]*=env[::-1]
        return y
    audio=(finish(raw)*meta['output_gain']).astype(np.float32);buf=io.BytesIO();wavfile.write(buf,24000,audio)
    import hashlib
    wavehash=hashlib.sha256(buf.getvalue()).hexdigest();assert wavehash==item['wave_sha256'],('旧波形不一致',item['id'],wavehash,item['wave_sha256'])
    ps=finish(pc);as_=finish(ac)
    assert len(audio)%120==0
    rms=lambda x:np.sqrt(np.mean(x.reshape(-1,120)**2,axis=1))
    traces=dict(pulse_index=idx,pulse_fraction_seconds=shift,pulse_noise_size=noise,
        pulse_AP_power_at_DC=ratio,pulse_periodic_response_norm2=norm,pulse_periodic_emitted=emit,
        sample_vuv_packed=np.packbits(vuv[:kept]),sample_count=np.array([kept]),
        periodic_component_rms_5ms=rms(ps),aperiodic_component_rms_5ms=rms(as_),wave_rms_5ms=rms(audio))
    result=dict(id=item['id'],cohort=item['cohort'],condition=item['condition'],method=item['method'],
        source_parameters_sha256=item['parameters_sha256'],old_wave_sha256=item['wave_sha256'],observed_wave_sha256=wavehash,
        wave_byte_exact=True,input_arrays_unchanged=True,component_sum_max_abs_error=delta,
        pulses=count,clock_pulses_unvoiced=int((vuv[idx]==0).sum()),
        voiced_clock_pulses=int((vuv[idx]>0).sum()),periodic_emitted=int(emit.sum()),
        voiced_AP_suppressed=int(((vuv[idx]>0)&(ratio>.999)).sum()),
        voiced_zero_periodic_other=int(((vuv[idx]>0)&(ratio<=.999)&(norm==0)).sum()),
        last_zero_noise_size=True,AP_noise_power_factor=factor,
        source_voiced_frames=int((params[1][:,0]>-1e9).sum()),
        observed_voiced_samples=int(vuv[:kept].sum()),sample_count_48k=kept,
        emitted_pulses_within_kept_audio=int(emit[idx<kept].sum()),
        LF0_not_actual_or_perceived_pitch=True,clock_pulse_not_voiced_excitation=True,
        periodic_component_energy_not_perceptual_voicing=True,old_gates_unchanged=True)
    return result,traces
def main():
    import argparse
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['compat','all']);p.add_argument('--job',required=True);a=p.parse_args()
    b=Budget();protocol=read(HERE/'protocol.json');mods=load()
    rows=protocol['records'] if a.stage=='all' else [protocol['records'][i] for i in protocol['compat_indices']]
    results=[]
    for item in rows:
        target=HERE/'diagnostic'/(item['id']+'.json')
        if a.stage=='all' and target.exists():
            r=read(target);assert digest(REPO/r['trace_path'])==r['trace_sha256'];results.append(dict(id=r['id'],path=str(target.relative_to(REPO)),sha256=digest(target)));continue
        r,traces=evaluate(item,mods)
        if a.stage=='compat':results.append(r)
        else:
            buf=io.BytesIO();mods[0].savez_compressed(buf,**traces);tp=HERE/'trace'/(item['id']+'.npz')
            if tp.exists():
                with mods[0].load(tp) as x:assert set(x.files)==set(traces) and all(mods[0].array_equal(x[k],v,equal_nan=True) for k,v in traces.items())
            else:b.write(tp,buf.getvalue(),a.job)
            r.update(trace_path=str(tp.relative_to(REPO)),trace_sha256=digest(tp));b.write_data(target,encode(r),a.job)
            results.append(dict(id=r['id'],path=str(target.relative_to(REPO)),sha256=digest(target)))
        print('WORLD観測',len(results),'/',len(rows),flush=True)
    b.save(HERE/('compatibility-audit.json' if a.stage=='compat' else 'diagnostic-manifest.json'),dict(rows=results,
        expected=len(rows),all_wave_byte_exact=True,new_AI=0,old_gates_unchanged=True,
        quality_goal_completed=False,protected_confirmation_opened=False),a.job)
if __name__=='__main__':main()
