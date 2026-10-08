"""第30回：LPF/MLSA後の周期寄与を旧波形不変の別版観測で調べる。"""
import ast
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from budget import ROOT, read, digest, encode
from long_horizon_budget import LongHorizonBudget as Budget

REPO=ROOT.parents[2]
NAME='hts-lpf-observation-v1'
HERE=ROOT/'campaigns/nas-hts-lpf-observation-20261008-v1'
PERIOD=ROOT/'campaigns/nas-source-period-audit-20261008-v1'
SUPPORT=ROOT/'campaigns/nas-support-excitation-audit-20261008-v1'
PYTHON=REPO/'research/experiments/autonomous-speech-synthesis/.venv-eval/bin/python'

WORKER=r'''"""実パルス由来の周期寄与と残差を全固定支持で保存する。知覚資格は主張しない。"""
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
'''


def c_sources():
    primary=(PERIOD/'vendor/HTS_vocoder.c').read_text()
    assert digest(PERIOD/'vendor/HTS_vocoder.c')=='f5b97b331639af246dea3871a74bca512f40d96618702f6512d8e0fbed86cdd9'
    call='x = HTS_Vocoder_get_excitation(v, lpf);'
    assert primary.count(call)==primary.count('x *= volume;')==1
    observed=primary.replace(call,'x = tr_observe(v, lpf);').replace('x *= volume;','x *= volume;\n      tr_filter_observe(v, m, alpha, volume);')
    source=(PERIOD/'observer.c').read_text()
    source=source.replace('static double tr_observe(HTS_Vocoder *v,const double *lpf);',
        'static double *tr_lp,*tr_lp_periodic,*tr_filtered_periodic;\nstatic double tr_ring[63],tr_filter_state[512];\nstatic double tr_observe(HTS_Vocoder *v,const double *lpf);\nstatic void tr_filter_observe(HTS_Vocoder *v,size_t m,double alpha,double volume);')
    source=source.replace('double x=HTS_Vocoder_get_excitation(v,lpf);',
        'size_t index=v->excite_buff_index;\n    if (pulse) { double amplitude=sqrt(p);\n        for (size_t i=0;i<v->excite_buff_size;i++)\n            tr_ring[(index+i)%v->excite_buff_size]+=amplitude*lpf[i];\n    }\n    double periodic=tr_ring[index];tr_ring[index]=0.;\n    double x=HTS_Vocoder_get_excitation(v,lpf);')
    source=source.replace('tr_period[tr_index]=p;tr_counter[tr_index]=c;tr_pulse[tr_index]=pulse;',
        'tr_period[tr_index]=p;tr_counter[tr_index]=c;tr_pulse[tr_index]=pulse;\n        tr_lp[tr_index]=x;tr_lp_periodic[tr_index]=periodic;')
    source=source.replace('int trace_render(',
        'static void tr_filter_observe(HTS_Vocoder *v,size_t m,double alpha,double volume) {\n    size_t i=tr_index-1;double p=tr_lp_periodic[i];\n    if (p!=0.) p*=exp(v->c[0]);\n    tr_filtered_periodic[i]=HTS_mlsadf(p,v->c,m,alpha,PADEORDER,tr_filter_state)*volume;\n}\nint trace_render(')
    source=source.replace('uint8_t *pulse,size_t samples)',
        'uint8_t *pulse,double *lp,double *lp_periodic,double *filtered_periodic,size_t samples)')
    source=source.replace('!period || !counter || !pulse ||','!period || !counter || !pulse || !lp || !lp_periodic || !filtered_periodic ||')
    source=source.replace('tr_period=period;tr_counter=counter;tr_pulse=pulse;tr_capacity=samples;tr_index=0;',
        'memset(tr_ring,0,sizeof(tr_ring));memset(tr_filter_state,0,sizeof(tr_filter_state));\n    tr_lp=lp;tr_lp_periodic=lp_periodic;tr_filtered_periodic=filtered_periodic;\n    tr_period=period;tr_counter=counter;tr_pulse=pulse;tr_capacity=samples;tr_index=0;')
    source=source.replace('tr_period=NULL;tr_counter=NULL;', 'tr_lp=NULL;tr_lp_periodic=NULL;tr_filtered_periodic=NULL;\n    tr_period=NULL;tr_counter=NULL;')
    return observed,source


def prepare():
    b=Budget();b.recover();state=b.snapshot();assert not state['jobs']
    if NAME in state['campaigns']:raise RuntimeError('登録済み。最新契約の未実施stageから再開する')
    assert not b.review_due(state)['due']
    observed,source=c_sources();ast.parse(WORKER)
    records=[];traces={}
    for row in read(PERIOD/'diagnostic-manifest.json')['rows']:
        d=read(REPO/row['path']);assert digest(REPO/row['path'])==row['sha256']
        traces['nas-mcp-postfilter/'+d['id']]=(d['trace_path'],d['trace_sha256'])
    for row in read(SUPPORT/'new-hts-manifest.json')['rows']:
        d=read(REPO/row['path']);assert digest(REPO/row['path'])==row['sha256']
        traces[d['id']]=(d['trace_path'],d['trace_sha256'])
    for item in read(SUPPORT/'protocol.json')['records']:
        if not item['method'].startswith('hts'):continue
        item=dict(item);item['native_initial']=str(Path(item['parameters']).with_name('native.npz'))
        item['native_initial_sha256']=digest(REPO/item['native_initial'])
        item['source_trace'],item['source_trace_sha256']=traces[item['id']]
        item['use_native_initial']=item['cohort']=='nas-mcp-postfilter' and 'postfilter' in item['method']
        assert all(digest(REPO/item[k])==item[k+'_sha256'] for k in ('record','parameters','wave','native_initial','source_trace'))
        records.append(item)
    assert len(records)==224
    limits=dict(seconds=14400,bytes=1500000000,write_bytes=1800000000,render=1000,dsp=6000,ai=0,teacher=0,train=0,inverse=0,download=0,setup=40,audit=60)
    reg=dict(campaign=NAME,status='registered_before_output',question='確認済み224実パルスがLPF/MLSA/最終24k波形へ周期寄与としてどれだけ残るか。旧固定支持欠測94区間との関係を観測する。',
        causal_factor='LPFのパルス寄与と独立shadowフィルタ状態。主生成の乱数/係数/状態/出力は書き換えない。',
        controls='旧224WAVの全bytehashと旧period/counter/pulseの全配列完全一致。fixtureのLPF0/1を旧配列入口と比較。',
        input_split='既存2コホート全HTS224件。新規選別なし。探索済み事後診断。P5未開封。',
        fixed_support='旧全支持を保持し、欠測94を分母から除かない。短窓20/40/60msの全5ms時計と境界/edge/不足を保持。',
        gates=dict(old_wave_bytehash_all_exact=True,old_source_clock_all_exact=True,fixture_zero_unit_LPF_pass=True,energy_identity_relative_tolerance=1e-12),
        normalization='固定48k primary/24k resample_poly/12ms fade/0.25利得/float32。周期寄与にも同じ線形後処理。正規化係数の探索なし。',
        missing='未観測/失敗は全分母に保持。旧DIO/ASR/資格を変更しない。',
        energy='周期寄与と(出力−周期寄与)の残差、cross項を区別。エネルギー単純加算/知覚pitchの資格へ広げない。',
        source_license='既存の対応HTS BSD noticeを同梱。新規依存/取得0。',
        limits=limits,estimates=dict(actual_render=232,conservative_render=1000,actual_DSP=1804,conservative_DSP=6000,
        data_outputs=200000000,retry_outputs=900000000,temporary_peak=16000000,total_peak=1116000000,includes_cleanup_aggregate_seal_Git=True),
        technical_retry_per_job=2,technical_retry_campaign=10,ram_gb=8,parallel_max=2,
        independent_generation_requalification=False,new_ASR=0,perceptual_qualification=False,quality_goal_completed=False,protected_confirmation_opened=False)
    b.start_campaign(NAME,str(HERE.relative_to(ROOT)),limits,hashlib.sha256(encode(reg)).hexdigest())
    with b.job(NAME,'setup','LPF観測の全224入力・因果要因・費用を固定',reserve_bytes=3000000) as j:
        b.save(HERE/'registration.json',reg,j);b.save(HERE/'protocol.json',dict(records=records,registration_sha256=digest(HERE/'registration.json')),j)
        b.write(HERE/'analysis.py',WORKER.encode(),j)
        b.write(HERE/'observer.c',source.encode(),j);b.write(HERE/'HTS_vocoder_observed.c',observed.encode(),j)
        for n in ('HTS_hidden.h','HTS_engine.h'):b.write(HERE/'vendor'/n,(PERIOD/'vendor'/n).read_bytes(),j)
        b.write(HERE/'HTS-BSD-NOTICE.txt',(PERIOD/'runtime-bundle/HTS-BSD-NOTICE.txt').read_bytes(),j)
        b.save(HERE/'source-change-audit.json',dict(primary_sha256=digest(PERIOD/'vendor/HTS_vocoder.c'),
            source_commit='214e26dfb7f728ff9db39c14a59db709abcc121d',primary_replaced_sites=2,
            main_excitation_call_exactly_once=True,shadow_ring_and_MLSA_state_only=True,
            original_vocoder_state_not_written=True,periodic_energy_not_perceived_pitch_truth=True),j)
    clang=Path('/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/clang')
    sdk=Path('/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk')
    cmd=[str(clang),'-dynamiclib','-O2','-fno-modules','-undefined','dynamic_lookup','-isysroot',str(sdk),'-I'+str(HERE/'vendor'),'-I'+str(HERE),str(HERE/'observer.c'),'-o',str(HERE/'lpf-observer.dylib')]
    with b.job(NAME,'setup','LPF観測C build・所有一時回収',reserve_bytes=20000000) as j:
        with b.workspace(j,'clang中間物・cache',16000000,32000000) as (path,env):
            env['CLANG_MODULE_CACHE_PATH']=str(path/'clang-modules')
            with b.external_output(HERE/'lpf-observer.dylib',200000,j):
                result=subprocess.run(cmd,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=True,timeout=120)
        b.save(HERE/'build-audit.json',dict(command=cmd,stderr=result.stderr,binary_sha256=digest(HERE/'lpf-observer.dylib'),temporary_removed=True),j)
    input_hashes={str((PERIOD/n).relative_to(REPO)):digest(PERIOD/n) for n in ('vendor/HTS_vocoder.c','observer.c','artifact-seal.json','runtime-bundle/manifest.json')}
    for name,h in read(PERIOD/'runtime-bundle/manifest.json')['files'].items():input_hashes[str((PERIOD/'runtime-bundle'/name).relative_to(REPO))]=h
    input_hashes[str((SUPPORT/'pulse_ground.py').relative_to(REPO))]=digest(SUPPORT/'pulse_ground.py')
    b.save(HERE/'execution-contract.json',dict(registration_sha256=digest(HERE/'registration.json'),protocol_sha256=digest(HERE/'protocol.json'),
        source_hashes={str(p.relative_to(HERE)):digest(p) for p in HERE.rglob('*') if p.is_file() and p.name not in ('registration.json','protocol.json')},
        input_hashes=input_hashes,bootstrap_sha256=digest(Path(__file__)),all_conditions_fixed_before_output=True,quality_goal_completed=False))
    with b.locked():
        s=b._load();s['continuation_checkpoint_history'].append(s['continuation_checkpoint']);s['continuation_checkpoint']=dict(id='hts-lpf-prepared',active_campaign=NAME,next='登録commit/push→fixture→全224観測→集計/封印/commit/push',quality_goal_completed=False,protected_confirmation_opened=False,git_save_pending=True);b._write_state(s)
    b.save(ROOT/'progress-0043.json',dict(active_campaign=NAME,registered_before_output=True,quality_goal_completed=False,next='fixture→全224観測→集計/封印',budget=b.reconcile()))
    print(b.reconcile(),flush=True)


def run(stage):
    b=Budget();b.recover();assert not b.snapshot()['jobs']
    if stage=='fixture':
        assert not (HERE/'fixture-audit.json').exists()
        with b.job(NAME,'render','LPF0/1・2Hz・旧入口の8fixture',count=8,reserve_bytes=12000000) as r:
            with b.job(NAME,'dsp','fixtureの3段階energy同一性',count=12,reserve_bytes=1000000) as d:
                with b.workspace(r,'fixtureライブラリ初期化') as (path,env):
                    result=subprocess.run([str(PYTHON),'-B',str(HERE/'analysis.py'),'fixture'],env=env,stdout=subprocess.PIPE,text=True,check=True,timeout=300)
                b.save(HERE/'fixture-audit.json',json.loads(result.stdout),d)
    else:
        assert read(HERE/'fixture-audit.json')['passed']
        count=sum(not (HERE/'diagnostic'/(x['id']+'.json')).exists() for x in read(HERE/'protocol.json')['records']);assert count>0
        with b.job(NAME,'render','224旧HTSのLPF/MLSA周期純観測',count=count,reserve_bytes=20000000) as r:
            with b.job(NAME,'dsp','全支持と3窓3段階のenergy診断',count=count*8,reserve_bytes=300000000) as d:
                with b.workspace(r,'純観測ライブラリ初期化') as (path,env):
                    subprocess.run([str(PYTHON),'-B',str(HERE/'analysis.py'),'worker','--job',d],env=env,check=True,timeout=10800)
    print(b.reconcile(),flush=True)


def close():
    b=Budget();b.recover();assert not b.snapshot()['jobs'];manifest=read(HERE/'diagnostic-manifest.json')
    rows=[]
    for x in manifest['rows']:
        assert digest(REPO/x['path'])==x['sha256'];rows.append(read(REPO/x['path']))
    assert len(rows)==224 and all(x['old_wave_byte_exact'] and x['old_source_clock_exact'] for x in rows)
    groups={}
    for row in rows:
        key=row['cohort']+'/'+row['method'];g=groups.setdefault(key,dict(waves=0,support=0,missing=0,intervals=[]));g['waves']+=1
        for q in row['all_fixed_support_intervals']:
            g['support']+=1;g['missing']+=q['old_fixed_support_missing'];g['intervals'].append(q)
    def median(values):
        values=sorted(v for v in values if v is not None)
        if not values:return None
        n=len(values);return values[n//2] if n%2 else .5*(values[n//2-1]+values[n//2])
    for g in groups.values():
        g['by_old_missing']={}
        for missing in (False,True):
            chosen=[q for q in g['intervals'] if q['old_fixed_support_missing']==missing]
            g['by_old_missing'][str(missing)]=dict(intervals=len(chosen),
                periodic_share_median={stage:median([q[stage]['periodic_share'] for q in chosen]) for stage in ('lp','filter','final')},
                zero_periodic_intervals={stage:sum(q[stage]['periodic_power']==0 for q in chosen) for stage in ('lp','filter','final')},
                fewer_than_four_pulses=sum(q['actual_pulses']<4 for q in chosen))
        del g['intervals']
    assert sum(g['missing'] for g in groups.values())==94
    with b.job(NAME,'audit','全分母・旧94欠測・費用・観測封印',reserve_bytes=3000000) as j:
        summary=dict(total_waves=224,groups=groups,all_old_waves_and_source_clocks_exact=True,
            old_missing_support=94,old_missing_and_ASR_unchanged=True,energy_components_include_cross_term=True,
            observational_only=True,prospective_measurement_qualification=False,perceptual_qualification=False,
            protected_confirmation_opened=False,quality_goal_completed=False,
            next='全窓/支持の周期寄与を使い測定資格を別契約で検証。WORLD原実装の差を別因子で分離。')
        b.save(HERE/'aggregate-summary.json',summary,j)
        lines=['# HTS LPF/MLSA後の周期寄与の純観測','',
            '既存224件を全bytehash不変で観測し、旧period/counter/pulseも全配列一致した。主乱数・状態・係数に書込まず、周期パルスのLPF寄与と独立MLSA状態を追跡した。残差は合成出力から周期寄与を引いた値で、cross項を保持する。','',
            '|コホート/方式|波形|固定支持|旧欠測|最終周期share中央値（支持あり/旧欠測）|',
            '|---|---:|---:|---:|---|']
        for key,g in groups.items():
            a=g['by_old_missing']['False']['periodic_share_median']['final'];z=g['by_old_missing']['True']['periodic_share_median']['final']
            lines.append(f'|{key}|{g["waves"]}|{g["support"]}|{g["missing"]}|{a} / {z}|')
        lines+=['','固定支持の欠測94区間を保持した。LPF後/MLSA後/24k後の周期shareは診断であり、周期性の測定資格・知覚pitch・自然さを保証しない。20/40/60msの全時計、境界、edge、短いパルス列も配列として外部保存した。','旧二ASRと採否は更新しない。独立未知入力/日本語知覚/P5は未充足で品質未達。次はこの観測から測定有効範囲を別契約で検証し、生成改善につながる要因へ進む。','']
        b.write(HERE/'report.md','\n'.join(lines).encode(),j)
        s=b.snapshot();c=s['campaigns'][NAME]
        b.save(HERE/'cost-audit.json',dict(campaign_counts=c['counts'],seconds=s['seconds']-c['start_seconds'],write_bytes=s['write_bytes']-c['start_write_bytes'],
            all_temporary_absent=all(v['status']=='removed' and not os.path.lexists(v['path']) for v in s['temporary_work'].values()),
            new_AI_teacher_train_inverse_download=0,new_audio_saved=0,quality_goal_completed=False),j)
        b.save(HERE/'artifact-seal.json',dict(files={str(p.relative_to(REPO)):digest(p) for p in HERE.rglob('*') if p.is_file()},path_base='repository',
            experiment_completed=True,quality_goal_completed=False,protected_confirmation_opened=False),j)
    b.close_campaign(NAME)
    with b.locked():
        s=b._load();s['continuation_checkpoint'].update(id='hts-lpf-completed',active_campaign=None,next='commit/push→WORLD原実装演算差または短窓/動的測定資格の具体的契約',git_save_pending=True);b._write_state(s)
    b.save(ROOT/'progress-0044.json',dict(latest_completed=NAME,scientific_result='224旧波形完全一致・LPF/MLSA周期寄与を観測。旧欠測94保持。',
        quality_goal_completed=False,protected_confirmation_opened=False,next='WORLD原実装の演算差/短窓動的資格/知覚資格',review=b.review_due(),budget=b.reconcile()))
    print(b.reconcile(),flush=True)


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('stage',choices=('prepare','fixture','observe','close'));a=p.parse_args()
    prepare() if a.stage=='prepare' else close() if a.stage=='close' else run(a.stage)
