"""保存224波形の全clock・固定支持・LPF寄与を保持する測定資格診断。"""
from pathlib import Path
import argparse,io,os,sys,hashlib
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1];REPO=ROOT.parents[2]
sys.path.insert(0,str(ROOT))
from budget import read,digest,encode
from long_horizon_budget import LongHorizonBudget as Budget
PERIOD=ROOT/'campaigns/nas-source-period-audit-20261008-v1'
def imports():
    import tempfile
    assert Path(tempfile.gettempdir()).resolve()==Path(os.environ['TMPDIR']).resolve()
    sys.path[:0]=[str(PERIOD/'runtime-bundle/packages-v2')]
    import numpy as np
    from scipy.io import wavfile
    import measure,short_acf
    from score_ground import score,ground
    return np,wavfile,measure,short_acf,score,ground
def verify():
    c=read(HERE/'execution-contract.json')
    assert digest(HERE/'registration.json')==c['registration_sha256'] and digest(HERE/'protocol.json')==c['protocol_sha256']
    for n,h in c['source_hashes'].items():assert digest(HERE/n)==h,n
    for n,h in c['runtime_hashes'].items():assert digest(REPO/n)==h,n
    amendment=read(HERE/'execution-control-amendment-01.json')
    assert digest(HERE/'analysis_v2.py')==amendment['worker_sha256']
    assert digest(ROOT/'hts_overlap_qualification_20261008_v2.py')==amendment['controller_sha256']
def fixture(lib):
    np,_,measure,short,_,_=lib
    rng=np.random.default_rng(20261008);t=np.arange(24000)/24000
    waves=[np.zeros(len(t)),rng.normal(0,.01,len(t)),.05*np.sin(2*np.pi*220*t),.05*np.sin(2*np.pi*(110*t+85*t*t))]
    checks=[]
    for k,wave in enumerate(waves):
        for width in (20,40,60):
            x=wave[12000:12000+width*24];centered=x-x.mean();bounded,overlap=measure.curves(x)
            for lag in (0,30,100,min(342,len(x)-2)):
                left=centered[:len(x)-lag];right=centered[lag:]
                direct=2*np.dot(left,right)/(np.dot(left,left)+np.dot(right,right)) if np.any(centered) else 0.
                assert abs(overlap[lag]-direct)<1e-10
            assert np.max(abs(overlap))<=1+1e-9
            assert np.allclose(overlap,measure.curves(x[::-1])[1],rtol=0,atol=1e-9)
            result=measure.estimate(x);hz,confidence=short.estimate_f0(x,24000,70,800)
            expected=hz if hz is not None and confidence>=.6 else 0.
            assert result['bounded_all']==(expected,confidence)
            if k==0:assert all(h==0 and c==0 for h,c in result.values())
            if k==2 and width==60:
                assert all(abs(12*np.log2(h/220))<.1 and c>=.6 for h,c in result.values())
            checks.append(dict(wave=k,width=width,formula_direct_exact_within_1e10=True,legacy_bounded_exact=True))
    return dict(passed=True,checks=checks,render=4,dsp=100,fixture_only=True,quality_goal_completed=False)
def batch(lib,begin,end,job):
    np,wavfile,measure,_,score,ground=lib;b=Budget();rows=[]
    for item in read(HERE/'protocol.json')['records'][begin:end]:
        target=HERE/'diagnostic'/(item['id']+'.json')
        if target.exists():
            saved=read(target);assert saved['input_record_sha256']==item['record_sha256'];assert digest(REPO/saved['arrays'])==saved['arrays_sha256']
            rows.append(dict(id=item['id'],path=str(target.relative_to(REPO)),sha256=digest(target)));continue
        for key in ('record','wave','source_trace','lpf_diagnostic','lpf_arrays'):
            assert digest(REPO/item[key])==item[key+'_sha256'],item['id']
        old=read(REPO/item['record']);lpf=read(REPO/item['lpf_diagnostic'])
        fs,audio=wavfile.read(REPO/item['wave']);assert fs==24000
        with np.load(REPO/item['source_trace']) as a:period=a['period'].copy();pulse=a['pulse'].copy();counter=a['counter_before'].copy()
        assert len(period)==2*len(audio) and np.array_equal(pulse.astype(bool),(period>0)&(counter+1>=period))
        with np.load(REPO/item['lpf_arrays']) as a:previous={k:a[k].copy() for k in a.files}
        times=previous['times'];output=dict(times=times);results={};intervals=[]
        legacy=None
        if item.get('legacy_arrays'):
            assert digest(REPO/item['legacy_arrays'])==item['legacy_arrays_sha256']
            with np.load(REPO/item['legacy_arrays']) as a:legacy={k:a[k].copy() for k in a.files}
            assert len(times)==len(legacy['times'])
            assert np.array_equal(np.rint(times*24000),np.rint(legacy['times']*24000))
            assert np.array_equal(np.rint(times*48000),np.rint(legacy['times']*48000))
        duration=np.asarray(old['meta']['duration']);bounds=np.r_[0,np.cumsum(duration)]
        for width in (20,40,60):
            kinds,hz,count=ground(np,period,pulse,times,width)
            for name,values in [('kind',kinds),('pulse_rate_hz',hz),('pulse_count',count)]:
                assert np.array_equal(values,previous[f'w{width}_{name}'],equal_nan=True)
                output[f'w{width}_{name}']=values
            estimates,confidence=measure.local(audio,times,width);results[str(width)]={}
            if legacy is not None:
                assert np.array_equal(estimates['bounded_all'],legacy[f'w{width}_bounded_acf'])
                assert np.array_equal(confidence['bounded_all'],legacy[f'w{width}_acf_confidence'])
            for name,v in estimates.items():
                output[f'w{width}_{name}']=v;output[f'w{width}_{name}_confidence']=confidence[name]
                results[str(width)][name]={scope:score(np,v,kinds,hz,k) for scope,k in [('stable',4),('dynamic',5)]}
                results[str(width)][name]['other_classes']={str(k):dict(total=int((kinds==k).sum()),accepted=int(((kinds==k)&(v>=70)&(v<=800)).sum())) for k in (0,1,3)}
            for index in old['measurement']['support']:
                lo,hi=int(bounds[index*5]),int(bounds[(index+1)*5]);mask=(times>=lo*.005)&(times<hi*.005)
                eligible=mask&np.isin(kinds,(4,5));q=dict(width_ms=width,index=index,old_missing=index in old['measurement']['missing_support'],clock_points=int(mask.sum()),eligible=int(eligible.sum()),classes={str(k):int((mask&(kinds==k)).sum()) for k in range(6)})
                q['algorithms']={name:dict(accepted=int((mask&(v>=70)&(v<=800)).sum()),correct=int((eligible&(v>0)&(abs(12*np.log2(np.maximum(v,1e-30)/np.where(eligible,hz,1.)))<=1)).sum())) for name,v in estimates.items()}
                intervals.append(q)
        buf=io.BytesIO();np.savez_compressed(buf,**output);ap=HERE/'arrays'/(item['id']+'.npz');b.write(ap,buf.getvalue(),job)
        result=dict(id=item['id'],cohort=item['cohort'],condition=item['condition'],method=item['method'],input_record_sha256=item['record_sha256'],wave_sha256=item['wave_sha256'],source_trace_sha256=item['source_trace_sha256'],results=results,fixed_support=intervals,old_missing_support=old['measurement']['missing_support'],lpf_periodic_energy_not_used_for_selection=True,legacy128_all_widths_exact=legacy is not None,ground_all224_matches_LPF=True,arrays=str(ap.relative_to(REPO)),arrays_sha256=digest(ap),all_clock_denominators_retained=True,old_gates_and_ASR_unchanged=True,source_rate_not_perceived_pitch=True,quality_goal_completed=False)
        b.write_data(target,encode(result),job);rows.append(dict(id=item['id'],path=str(target.relative_to(REPO)),sha256=digest(target)))
    b.save(HERE/'batches'/f'{begin:03d}-{end:03d}.json',dict(rows=rows,expected=end-begin),job)
    print('重なり正規化',end,'/224',flush=True)
def main():
    p=argparse.ArgumentParser();p.add_argument('stage',choices=('fixture','batch'));p.add_argument('--begin',type=int);p.add_argument('--end',type=int);p.add_argument('--job');a=p.parse_args();verify();lib=imports()
    if a.stage=='fixture':print(__import__('json').dumps(fixture(lib),allow_nan=False));return
    assert read(HERE/'fixture-audit.json')['passed'];batch(lib,a.begin,a.end,a.job)
if __name__=='__main__':main()
