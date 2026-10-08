"""実パルス由来の周期寄与と残差を全固定支持で保存する。知覚資格は主張しない。"""
from pathlib import Path
import sys,os,io,ctypes as C,json,argparse,hashlib
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1];REPO=ROOT.parents[2]
sys.path.insert(0,str(ROOT))
from budget import read,digest,encode
from long_horizon_budget import LongHorizonBudget as Budget
PERIOD=ROOT/'campaigns/nas-source-period-audit-20261008-v1'
def libraries():
    import tempfile
    assert Path(tempfile.gettempdir()).resolve()==Path(os.environ['TMPDIR']).resolve()
    sys.path[:0]=[str(PERIOD/'runtime-bundle'),str(PERIOD/'runtime-bundle/packages-v2'),str(ROOT/'campaigns/nas-support-excitation-audit-20261008-v1')]
    import numpy as np
    from scipy import signal
    from scipy.io import wavfile
    from hts_arrays import validated,ah,synthesize
    from pulse_ground import ground
    lib=C.CDLL(str(HERE/'lpf-observer.dylib'))
    fn=lib.trace_render;P=C.POINTER(C.c_double);U=C.POINTER(C.c_uint8);S=C.c_size_t
    fn.restype=C.c_int;fn.argtypes=[P,P,P,P,C.c_int,S,S,S,P,P,P,U,P,P,P,S]
    return np,signal,wavfile,validated,ah,synthesize,ground,fn,P,U
def observe(lib,params,settings,first,use):
    np,signal,wavfile,validated,ah,_,_,fn,P,U=lib
    x=validated(params,settings);before=[ah(a) for a in x];first=np.ascontiguousarray(first,dtype=np.float64);initial_hash=ah(first)
    n=len(x[0])*240
    raw=np.empty(n);period=np.empty(n);counter=np.empty(n);pulse=np.empty(n,dtype=np.uint8)
    lp=np.empty(n);periodic_lp=np.empty(n);periodic_filtered=np.empty(n)
    assert fn(*(a.ctypes.data_as(P) for a in x),first.ctypes.data_as(P),int(use),len(x[0]),35,x[2].shape[1],raw.ctypes.data_as(P),period.ctypes.data_as(P),counter.ctypes.data_as(P),pulse.ctypes.data_as(U),lp.ctypes.data_as(P),periodic_lp.ctypes.data_as(P),periodic_filtered.ctypes.data_as(P),n)
    assert [ah(a) for a in x]==before and ah(first)==initial_hash
    assert np.array_equal(pulse.astype(bool),(period>0)&(counter+1>=period))
    def convert(a):
        y=signal.resample_poly(a/32768.,1,2);fade=min(round(.012*24000),len(y)//2);env=np.sin(np.linspace(0,np.pi/2,fade))**2
        y[:fade]*=env;y[-fade:]*=env[::-1]
        return y*.25
    audible=convert(raw);audible_periodic=convert(periodic_filtered)
    out=io.BytesIO();wavfile.write(out,24000,audible.astype(np.float32))
    arrays=dict(period=period,counter=counter,pulse=pulse,lp_total=lp,lp_periodic=periodic_lp,
                filter_total=raw,filter_periodic=periodic_filtered,final_total=audible.astype(np.float32).astype(np.float64),final_periodic=audible_periodic)
    assert all(np.isfinite(a).all() for a in arrays.values())
    return out.getvalue(),arrays
def energy(np,total,periodic):
    residual=total-periodic
    p=float(np.mean(periodic**2)) if len(total) else 0.
    n=float(np.mean(residual**2)) if len(total) else 0.
    t=float(np.mean(total**2)) if len(total) else 0.
    cross=float(2*np.mean(periodic*residual)) if len(total) else 0.
    error=abs(t-(p+n+cross));scale=max(t,p+n,1e-300)
    assert error<=1e-12*scale
    return dict(samples=len(total),total_power=t,periodic_power=p,residual_power=n,cross_power=cross,
                periodic_share=p/(p+n) if p+n else None,energy_identity_relative_error=error/scale,
                residual_is_output_minus_periodic=True,additive_energy_claim=False)
def fixture(lib):
    np,_,wavfile,_,_,synthesize,_,_,_,_=lib
    settings=dict(stage=0.,use_log_gain=0.,sampling_frequency=48000.,fperiod=240.,alpha=.55,beta=0.,volume=1.,audio_buff_size=0.,stop=0.)
    results=[]
    for hz in (110.,280.):
        for coefficient in (0.,1.):
            mcp=np.zeros((100,35));mcp[:,0]=7.
            lf0=np.full((100,1),-1e10);lf0[20:80]=np.log(hz)
            params=[mcp,lf0,np.full((100,1),coefficient)]
            baseline,_=synthesize(params,settings)
            data,a=observe(lib,params,settings,mcp[0],False)
            out=io.BytesIO();wavfile.write(out,24000,(baseline*.25).astype(np.float32));assert data==out.getvalue()
            if coefficient==0.:assert not np.any(a['lp_periodic']) and not np.any(a['filter_periodic'])
            else:
                voiced=a['period']>0
                assert np.array_equal(a['lp_total'][voiced],a['lp_periodic'][voiced])
                assert np.array_equal(a['lp_periodic'][a['pulse'].astype(bool)],np.sqrt(a['period'][a['pulse'].astype(bool)]))
            for stage in ('lp','filter','final'):energy(np,a[stage+'_total'],a[stage+'_periodic'])
            results.append(dict(hz=hz,lpf=coefficient,wave_sha256=hashlib.sha256(data).hexdigest(),old_reference_byte_exact=True))
    return dict(passed=True,results=results,actual_render=8,actual_dsp=12,zero_periodic_and_unit_lpf_truth_pass=True,
                fixture_only=True,quality_evidence=False)
def worker(job):
    lib=libraries();np=lib[0];ground=lib[6];b=Budget();manifest=[]
    protocol=read(HERE/'protocol.json')
    for item in protocol['records']:
        target=HERE/'diagnostic'/(item['id']+'.json')
        if target.exists():
            saved=read(target);assert saved['record_sha256']==item['record_sha256'] and saved['old_wave_byte_exact']
            assert digest(REPO/saved['arrays_path'])==saved['arrays_sha256'];manifest.append(dict(id=item['id'],path=str(target.relative_to(REPO)),sha256=digest(target)));continue
        for key in ('record','parameters','native_initial','wave','source_trace'):
            assert digest(REPO/item[key])==item[key+'_sha256'],item['id']
        old=read(REPO/item['record'])
        with np.load(REPO/item['parameters']) as a:
            params=[a[k].copy() for k in ('mcp','lf0','lpf')];duration=a['duration'].copy()
        with np.load(REPO/item['native_initial']) as a:first=a['mcp'][0].copy()
        data,tr=observe(lib,params,old['meta']['settings'],first,item['use_native_initial'])
        assert hashlib.sha256(data).hexdigest()==item['wave_sha256'],'旧波形完全一致不通過'
        with np.load(REPO/item['source_trace']) as a:
            assert all(np.array_equal(tr[k],a[j]) for k,j in [('period','period'),('counter','counter_before'),('pulse','pulse')])
        assert np.array_equal(duration,np.asarray(old['meta']['duration']))
        bounds=np.r_[0,np.cumsum(duration)];intervals=[]
        for index in old['measurement']['support']:
            lo,hi=int(bounds[index*5]),int(bounds[(index+1)*5])
            q=dict(index=index,start_frame=lo,end_frame=hi,duration_ms=(hi-lo)*5,
                   old_fixed_support_missing=index in old['measurement']['missing_support'],
                   actual_pulses=int(tr['pulse'][lo*240:hi*240].sum()))
            for stage,scale in [('lp',240),('filter',240),('final',120)]:
                q[stage]=energy(np,tr[stage+'_total'][lo*scale:hi*scale],tr[stage+'_periodic'][lo*scale:hi*scale])
            intervals.append(q)
        assert [q['index'] for q in intervals if q['old_fixed_support_missing']]==old['measurement']['missing_support']
        with np.load(REPO/item['dio']) as a:times=a['times'].copy()
        output=dict(times=times)
        for width in (20,40,60):
            kinds,hz,count=ground(np,tr['period'],tr['pulse'],times,width)
            output.update({f'w{width}_kind':kinds,f'w{width}_pulse_rate_hz':hz,f'w{width}_pulse_count':count})
            for stage,rate in [('lp',48000),('filter',48000),('final',24000)]:
                total=tr[stage+'_total'];periodic=tr[stage+'_periodic'];residual=total-periodic
                prefix=[np.r_[0.,np.cumsum(x*x)] for x in (total,periodic,residual)]
                half=round(width*rate/2000);centers=np.rint(times*rate).astype(int)
                lo=centers-half;hi=centers+half;valid=(lo>=0)&(hi<=len(total))
                for key,cs in zip(('total','periodic','residual'),prefix):
                    values=np.full(len(times),np.nan);values[valid]=(cs[hi[valid]]-cs[lo[valid]])/(2*half)
                    output[f'w{width}_{stage}_{key}_power']=values
        buf=io.BytesIO();np.savez_compressed(buf,**output);ap=HERE/'arrays'/(item['id']+'.npz')
        b.write(ap,buf.getvalue(),job)
        result=dict(id=item['id'],cohort=item['cohort'],condition=item['condition'],method=item['method'],
            record_sha256=item['record_sha256'],old_wave_sha256=item['wave_sha256'],old_wave_byte_exact=True,
            old_source_clock_exact=True,all_fixed_support_intervals=intervals,
            full_energy={stage:energy(np,tr[stage+'_total'],tr[stage+'_periodic']) for stage in ('lp','filter','final')},
            arrays_path=str(ap.relative_to(REPO)),arrays_sha256=digest(ap),all_clock_points=len(times),
            missing_denominator_kept=True,old_gates_and_ASR_unchanged=True,perceived_pitch_truth=False,quality_goal_completed=False)
        b.write_data(target,encode(result),job)
        manifest.append(dict(id=item['id'],path=str(target.relative_to(REPO)),sha256=digest(target)))
        if len(manifest)%16==0:print('LPF周期寄与',len(manifest),'/224',flush=True)
    assert len(manifest)==224
    b.save(HERE/'diagnostic-manifest.json',dict(rows=manifest,total=224,all_old_wave_and_source_exact=True,new_audio_saved=0,
                                             old_support_and_gates_unchanged=True,quality_goal_completed=False),job)
def verify():
    contract=read(HERE/'execution-contract.json')
    assert digest(HERE/'registration.json')==contract['registration_sha256']
    assert digest(HERE/'protocol.json')==contract['protocol_sha256']
    for n,h in contract['source_hashes'].items():assert digest(HERE/n)==h,n
    for n,h in contract['input_hashes'].items():assert digest(REPO/n)==h,n
def main():
    parser=argparse.ArgumentParser();parser.add_argument('stage',choices=('fixture','worker'));parser.add_argument('--job');args=parser.parse_args();verify()
    if args.stage=='fixture':print(json.dumps(fixture(libraries()),allow_nan=False));return
    worker(args.job)
if __name__=='__main__':main()
