"""128既存HTS波形の純粋観測監査。旧波形との一致が必須。"""
from paths import *
import argparse,base64,io,json,os,subprocess,sys
from contextlib import ExitStack
def verify():
    c=read(HERE/'execution-contract.json')
    assert digest(HERE/'registration.json')==c['registration_sha256']
    assert digest(HERE/'protocol.json')==c['protocol_sha256']
    assert digest(HERE/'observer.c')==c['C_source_sha256']
    assert digest(HERE/'HTS_vocoder_observed.c')==c['observed_primary_sha256']
    for n,h in c['source_hashes'].items():assert digest(HERE/n)==h,n
    assert digest(HERE/'runtime-bundle/manifest.json')==c['runtime_manifest_sha256']
    for n,h in read(HERE/'runtime-bundle/manifest.json')['files'].items():assert digest(HERE/'runtime-bundle'/n)==h,n
def imports():
    import tempfile
    assert Path(tempfile.gettempdir()).resolve()==Path(os.environ['TMPDIR']).resolve()
    sys.path[:0]=[str(HERE/'runtime-bundle'),str(HERE/'runtime-bundle/packages-v2')]
    import numpy as np
    from scipy.io import wavfile
    import observer,period_measurement,hts_arrays,postfilter_v2
    assert callable(period_measurement.trackers)
    return np,wavfile,observer,period_measurement,hts_arrays,postfilter_v2
def preflight_worker():
    np,wavfile,obs,measure,hts,pf=imports()
    settings=dict(stage=0.,use_log_gain=0.,sampling_frequency=48000.,fperiod=240.,alpha=.55,beta=0.,volume=1.,audio_buff_size=0.,stop=0.)
    results=[]
    for pitch in [110.,220.]:
        mcp=np.zeros((100,35));mcp[:,0]=7.
        lf0=np.full((100,1),-1e10);lf0[20:80]=np.log(pitch)
        lpf=np.ones((100,1));params=[mcp,lf0,lpf]
        baseline,_=hts.synthesize(params,settings)
        data,trace,meta=obs.observe(params,settings,mcp[0],False)
        out=io.BytesIO();wavfile.write(out,24000,(baseline*.25).astype(np.float32))
        assert data==out.getvalue()
        assert np.allclose(trace['period'][20*240:80*240],48000/pitch,rtol=0,atol=1e-12)
        assert not np.any(trace['period'][:20*240]) and not np.any(trace['period'][80*240:])
        from acoustics import evaluate
        assert evaluate(baseline*.25,{},24000)['E0_pass']
        for name,wave in [('reference',out.getvalue()),('observed',data)]:
            results.append(dict(name=str(int(pitch))+'-'+name,sha256=__import__('hashlib').sha256(wave).hexdigest(),wav_base64=base64.b64encode(wave).decode()))
    return dict(results=results,actual_render=4,E0_calls=2,constant_period_and_unvoiced_truth_pass=True,
        phase_recurrence_exact=True,byte_exact=True,fixture_not_quality_evidence=True)
def worker(render_job,dsp_job):
    np,wavfile,obs,measure,hts,pf=imports()
    from acoustics import evaluate
    b=Budget();p=read(HERE/'protocol.json');rows=[];new=0;reused=0
    for item in p['records']:
        target=HERE/'diagnostic'/(item['id']+'.json')
        if target.exists():
            saved=read(target);assert saved['old_record_sha256']==item['old_record_sha256'] and saved['byte_exact']
            assert digest(REPO/saved['trace_path'])==saved['trace_sha256']
            rows.append(dict(id=item['id'],path=str(target.relative_to(REPO)),sha256=digest(target)));reused+=1;continue
        for key,hkey in [('old_record','old_record_sha256'),('parameters','parameters_sha256'),('native_initial','native_initial_sha256')]:
            assert digest(REPO/item[key])==item[hkey],item['id']
        old=read(REPO/item['old_record']);assert digest(REPO/old['wav'])==old['wav_sha256']
        with np.load(REPO/item['parameters']) as a:params=[a[n].copy() for n in ['mcp','lf0','lpf']]
        with np.load(REPO/item['native_initial']) as a:first=a['mcp'][0].copy()
        use='postfilter' in item['method']
        data,trace,meta=obs.observe(params,old['meta']['settings'],first,use);new+=1
        assert meta['sha256']==old['wav_sha256'],'観測で旧波形が変化したため停止'
        _,audio=wavfile.read(io.BytesIO(data));e0=evaluate(audio,{},24000);assert e0['E0_pass']==old['E0_pass']
        trackers,legacy,confidence=measure.trackers(audio)
        scores={name:obs.score(values,times,trace['period']) for name,(values,times) in trackers.items()}
        support=old['measurement']['support'];bounds=np.r_[0,np.cumsum(old['meta']['duration'])]*240
        source_support=[]
        for i in support:
            a,z=int(bounds[i*5]),int(bounds[(i+1)*5]);chunk=trace['period'][a:z];v=chunk[chunk>0]
            source_support.append(dict(index=i,source_voiced_samples=int(len(v)),source_samples=len(chunk),
                source_median_hz=float(np.median(48000/v)) if len(v) else None,
                duration_ms=(z-a)/48,primary_center_window_60ms_exclusion_possible=(z-a)<2880))
        buffer=io.BytesIO();arrays=dict(trace,acf_confidence=confidence)
        for name,(values,times) in trackers.items():arrays[name]=values;arrays[name+'_times']=times
        np.savez_compressed(buffer,**arrays);tracepath=HERE/'trace'/(item['id']+'.npz')
        if tracepath.exists():
            with np.load(tracepath) as old_arrays,np.load(io.BytesIO(buffer.getvalue())) as new_arrays:
                assert set(old_arrays.files)==set(new_arrays.files) and all(np.array_equal(old_arrays[k],new_arrays[k]) for k in old_arrays.files)
        else:b.write(tracepath,buffer.getvalue(),dsp_job)
        value=dict(id=item['id'],condition=item['condition'],method=item['method'],length=item['row']['length'],
            old_record=item['old_record'],old_record_sha256=item['old_record_sha256'],old_wav=old['wav'],
            old_wav_sha256=old['wav_sha256'],observed_wav_sha256=meta['sha256'],byte_exact=True,
            parameter_sha256=item['parameters_sha256'],native_initial_sha256=item['native_initial_sha256'],
            use_native_initial=use,E0=e0,observer_meta=meta,trackers=scores,legacy_ACF_diagnostic=legacy,
            old_pitch_gate_unchanged=old['pitch_gate'],old_fixed_support_source=source_support,
            source_GT_clock_diagnostic_only=True,source_period_is_not_perceived_pitch_truth=True,
            old_qualification_changed=False,trace_path=str(tracepath.relative_to(REPO)),trace_sha256=digest(tracepath))
        b.write_data(target,encode(value),dsp_job)
        rows.append(dict(id=item['id'],path=str(target.relative_to(REPO)),sha256=digest(target)))
        print('観測',len(rows),'/128',flush=True)
    assert len(rows)==128
    b.save(HERE/'diagnostic-manifest.json',dict(rows=rows,new_render=new,reused=reused,new_DSP=new*6,
        all_byte_exact=True,quality_goal_completed=False),dsp_job)
def main():
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['preflight','preflight-worker','observe','observe-worker'])
    p.add_argument('--render-job');p.add_argument('--dsp-job');a=p.parse_args();verify()
    if a.stage=='preflight-worker':print(json.dumps(preflight_worker(),allow_nan=False));return
    if a.stage=='observe-worker':worker(a.render_job,a.dsp_job);return
    b=Budget();b.recover()
    if a.stage=='preflight':
        assert not (HERE/'preflight-audit.json').exists()
        with ExitStack() as stack:
            j=stack.enter_context(b.job(NAME,'render','定周期2条件の観測/reference4fixture',count=4,reserve_bytes=12_000_000))
            stack.enter_context(b.job(NAME,'dsp','4fixtureのE0・hash・内部周期',count=4,reserve_bytes=100_000))
            with b.workspace(j,'fixtureライブラリ初期化') as (_,env):
                result=subprocess.run([str(PYTHON),'-B',str(HERE/'controller.py'),'preflight-worker'],env=env,stdout=subprocess.PIPE,text=True,check=True,timeout=300)
            x=json.loads(result.stdout)
            for row in x['results']:
                data=base64.b64decode(row.pop('wav_base64'),validate=True)
                assert __import__('hashlib').sha256(data).hexdigest()==row['sha256']
                b.write(HERE/'fixtures'/(row['name']+'.wav'),data,j)
            b.save(HERE/'preflight-audit.json',x,j)
    else:
        assert read(HERE/'preflight-audit.json')['byte_exact']
        count=sum(not (HERE/'diagnostic'/(x['id']+'.json')).exists() for x in read(HERE/'protocol.json')['records'])
        assert count>0,'保存済み観測は再実行しない'
        with b.job(NAME,'render','128既存HTS入力の純粋観測',count=count,reserve_bytes=12_000_000) as r:
            with b.job(NAME,'dsp','既存周期と3測定/legacy/E0/参照整合',count=count*6,reserve_bytes=300_000_000) as d:
                with b.workspace(r,'純粋観測・測定ライブラリ初期化') as (_,env):
                    subprocess.run([str(PYTHON),'-B',str(HERE/'controller.py'),'observe-worker','--render-job',r,'--dsp-job',d],
                        env=env,check=True,timeout=10800)
    print(b.reconcile(),flush=True)
if __name__=='__main__':main()
