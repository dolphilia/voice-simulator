"""第25回：保存HTS実パルスと短窓の対応を診断する。旧ゲートは不変。"""
from paths import *
import argparse,io,os,subprocess,sys
import json
def verify():
    c=read(HERE/'execution-contract.json')
    assert digest(HERE/'registration.json')==c['registration_sha256']
    assert digest(HERE/'protocol.json')==c['protocol_sha256']
    for n,h in c['source_hashes'].items():assert digest(HERE/n)==h,n
    for n,h in c['inputs'].items():assert digest(REPO/n)==h,n
def imports():
    import tempfile
    assert Path(tempfile.gettempdir()).resolve()==Path(os.environ['TMPDIR']).resolve()
    sys.path[:0]=[str(PERIOD/'runtime-bundle'),str(PERIOD/'runtime-bundle/packages-v2')]
    import numpy as np
    from scipy.io import wavfile
    import short_acf
    return np,wavfile,short_acf
def ground(np,period,pulse,times,width_ms):
    # 複数の実パルス間隔による窓内平均発生率。駆動LF0/知覚pitchへ読み替えない。
    kinds=np.zeros(len(times),dtype=np.uint8);target=np.full(len(times),np.nan)
    counts=np.zeros(len(times),dtype=np.int32);positions=np.flatnonzero(pulse)
    half=round(width_ms*48/2)
    for i,t in enumerate(times):
        c=round(float(t)*48000);a,z=c-half,c+half
        if a<0 or z>len(period):continue
        segment=period[a:z]
        if (segment==0).all():kinds[i]=2;continue
        if not (segment>0).all():kinds[i]=1;continue
        left,right=np.searchsorted(positions,[a,z]);selected=positions[left:right];counts[i]=len(selected)
        if len(selected)<4:kinds[i]=3;continue
        target[i]=48000*(len(selected)-1)/(selected[-1]-selected[0])
        spread=12*np.log2(segment.max()/segment.min())
        kinds[i]=4 if spread<=1. else 5
    return kinds,target,counts
def local_acf(np,short,audio,times,width_ms):
    half=round(width_ms*24/2);values=np.zeros(len(times));confidence=np.zeros(len(times))
    for i,t in enumerate(times):
        c=round(float(t)*24000);a,z=c-half,c+half
        if a<0 or z>len(audio):continue
        hz,conf=short.estimate_f0(audio[a:z],24000,minimum=70,maximum=800)
        confidence[i]=conf
        if hz is not None and conf>=.6:values[i]=hz
    return values,confidence
def score(np,values,kinds,target,kind):
    positive=kinds==kind;negative=kinds==2;accepted=(values>=70)&(values<=800)
    errors=np.full(len(values),np.inf)
    chosen=positive&accepted
    errors[chosen]=abs(12*np.log2(values[chosen]/target[chosen]))
    p=int(positive.sum());n=int(negative.sum());correct=int((positive&accepted&(errors<=1.)).sum())
    coverage=correct/p if p else 0.;false=int((negative&accepted).sum());uv=false/n if n else 1.
    median=float(np.median(errors[positive])) if p else None
    finite_median=median if median is not None and np.isfinite(median) else None
    return dict(positive_windows=p,negative_windows=n,correct_positive=correct,
        missing_positive=int((positive&~accepted).sum()),coverage=coverage,
        median_error_semitones=finite_median,negative_false_accept=false,negative_false_accept_rate=uv,
        inadequate_positive=p<3,inadequate_negative=n<3,
        passed=bool(p>=3 and n>=3 and coverage>=.9 and finite_median is not None and finite_median<=1. and uv<=.05),
        total_clock_points=len(kinds),exclusions={name:int((kinds==i).sum()) for i,name in enumerate(['edge','boundary','source_unvoiced','insufficient_pulses','stable','dynamic'])},
        source_pulse_rate_diagnostic_only=True,independent_vote=False,perceived_pitch_truth=False)
def fixtures(np):
    # 音声を生成しない時計配列の陽性・無声・境界・パルス不足検査。
    period=np.full(9600,218.);pulse=(np.arange(9600)%218==0).astype(np.uint8)
    times=np.array([.1]);k,h,n=ground(np,period,pulse,times,60)
    assert k[0]==4 and abs(h[0]-48000/218)<1e-12 and n[0]>=4
    p=period.copy();p[:]=0;k,h,n=ground(np,p,pulse*0,times,60);assert k[0]==2 and np.isnan(h[0])
    p=period.copy();p[:4800]=0;k,h,n=ground(np,p,pulse,times,60);assert k[0]==1
    k,h,n=ground(np,period,pulse*0,times,20);assert k[0]==3
    p=np.linspace(150.,400.,9600);k,h,n=ground(np,p,pulse,times,60);assert k[0]==5
    return dict(clock_array_fixtures_pass=True,no_waveform_generated=True)
def worker(job):
    np,wavfile,short=imports();b=Budget();p=read(HERE/'protocol.json')
    fixture=fixtures(np);manifest=[]
    for item in p['records']:
        target=HERE/'diagnostic'/(item['id']+'.json')
        if target.exists():
            saved=read(target);assert saved['source_trace_sha256']==item['trace_sha256']
            assert digest(REPO/saved['arrays'])==saved['arrays_sha256']
            manifest.append(dict(id=item['id'],path=str(target.relative_to(REPO)),sha256=digest(target)));continue
        assert digest(REPO/item['trace_path'])==item['trace_sha256']
        assert digest(REPO/item['old_wav'])==item['old_wav_sha256']
        with np.load(REPO/item['trace_path']) as a:arrays={k:a[k].copy() for k in a.files}
        fs,audio=wavfile.read(REPO/item['old_wav']);assert fs==24000
        times=arrays['centered_acf_times'];period=arrays['period'];pulse=arrays['pulse']
        assert len(period)==2*len(audio) and np.array_equal(pulse.astype(bool),(period>0)&(arrays['counter_before']+1>=period))
        for k in ['period','pulse','counter_before']:arrays[k].flags.writeable=False
        for name in ['dio','harvest']:
            assert len(arrays[name])==len(times) and np.allclose(arrays[name+'_times'],times,rtol=0,atol=1e-12)
        results={};output=dict(times=times)
        for width in [20,40,60]:
            kinds,hz,number=ground(np,period,pulse,times,width)
            values,confidence=local_acf(np,short,audio,times,width)
            if width==60:
                assert np.array_equal(values,arrays['centered_acf']) and np.array_equal(confidence,arrays['acf_confidence']),'60ms測定互換性が不一致'
            output.update({f'w{width}_kind':kinds,f'w{width}_pulse_rate_hz':hz,f'w{width}_pulse_count':number,
                f'w{width}_bounded_acf':values,f'w{width}_acf_confidence':confidence})
            results[str(width)]={}
            for name,v in [('dio_cached',arrays['dio']),('harvest_cached',arrays['harvest']),('bounded_acf',values)]:
                results[str(width)][name]={key:score(np,v,kinds,hz,k) for key,k in [('stable',4),('dynamic',5)]}
        buffer=io.BytesIO();np.savez_compressed(buffer,**output);apath=HERE/'arrays'/(item['id']+'.npz')
        if apath.exists():
            with np.load(apath) as a:
                assert set(a.files)==set(output) and all(np.array_equal(a[k],v,equal_nan=True) for k,v in output.items())
        else:b.write(apath,buffer.getvalue(),job)
        b.write_data(target,encode(dict(id=item['id'],condition=item['condition'],method=item['method'],length=item['length'],
            source_trace_sha256=item['trace_sha256'],wave_sha256=item['old_wav_sha256'],results=results,
            arrays=str(apath.relative_to(REPO)),arrays_sha256=digest(apath),
            legacy_60ms_exact=True,old_gates_and_decisions_unchanged=True,perceived_pitch_truth=False)),job)
        manifest.append(dict(id=item['id'],path=str(target.relative_to(REPO)),sha256=digest(target)))
        print('短窓診断',len(manifest),'/128',flush=True)
    b.save(HERE/'diagnostic-manifest.json',dict(rows=manifest,fixtures=fixture,expected=128,
        new_waveforms=0,new_AI=0,reused_DIO_Harvest=True,old_60ms_exact=True,quality_goal_completed=False),job)
def summary(b):
    rows=[]
    for x in read(HERE/'diagnostic-manifest.json')['rows']:
        assert digest(REPO/x['path'])==x['sha256'];rows.append(read(REPO/x['path']))
    results={}
    for width in ['20','40','60']:
        results[width]={}
        for tracker in ['dio_cached','harvest_cached','bounded_acf']:
            results[width][tracker]={}
            for scope in ['stable','dynamic']:
                groups={}
                for condition in ['both','neutral','higher']:
                    for method in ['all','hts_native','hts_postfilter','hts_voicing','hts_voicing_postfilter']:
                        chosen=[r for r in rows if (condition=='both' or r['condition']==condition) and (method=='all' or r['method']==method)]
                        scores=[r['results'][width][tracker][scope] for r in chosen]
                        groups[condition+'/'+method]=dict(expected=len(scores),passed=sum(s['passed'] for s in scores),
                            all_pass=all(s['passed'] for s in scores),
                            positive_windows=sum(s['positive_windows'] for s in scores),
                            negative_windows=sum(s['negative_windows'] for s in scores),
                            correct_positive=sum(s['correct_positive'] for s in scores),
                            missing_positive=sum(s['missing_positive'] for s in scores),
                            negative_false_accept=sum(s['negative_false_accept'] for s in scores),
                            inadequate_positive=sum(s['inadequate_positive'] for s in scores),
                            inadequate_negative=sum(s['inadequate_negative'] for s in scores),
                            exclusions={k:sum(s['exclusions'][k] for s in scores) for k in scores[0]['exclusions']})
                results[width][tracker][scope]=dict(groups=groups,failed_ids=[r['id'] for r in rows if not r['results'][width][tracker][scope]['passed']])
    return dict(total=128,results=results,old_60ms_exact=True,old_gates_and_decisions_unchanged=True,
        all_clock_denominators_retained=True,source_pulse_mean_rate_not_instantaneous_or_perceived_pitch=True,
        zero_source_excitation_is_not_absence_of_acoustic_filter_ringing=True,
        observational_existing_corpus_only=True,prospective_or_general_qualification=False,
        protected_confirmation_opened=False,perceptual_qualification=False,quality_goal_completed=False)
def close():
    verify();b=Budget();b.recover();assert not b.snapshot()['jobs']
    with b.job(NAME,'audit','短窓/動的対象の全分母・旧採否・費用・封印',reserve_bytes=3_000_000) as job:
        s=summary(b);b.save(HERE/'aggregate-summary.json',s,job)
        v=b.snapshot();c=v['campaigns'][NAME]
        b.save(HERE/'cost-audit.json',dict(actual_render=0,actual_AI=0,new_trackers='boundedACF20/40/60のみ。DIO/Harvestは既存再利用。',
            conservative_DSP=c['counts'].get('dsp',0),technical_retries=0,campaign=c,
            all_temporary_removed=True,quality_goal_completed=False),job)
        lines=['# HTSの実パルスと短窓・動的区間','',
            '第22回の保存済み128実励振traceと同一波形を使用し、生成・ASRを行わなかった。短窓版は最小入力長のみ45→10msに変更したACF。60ms出力/信頼度は旧値と全件一致した。','',
            'truthは窓内4パルス以上（3間隔以上）の平均発生率。瞬時F0・知覚pitchではない。無励振窓のフィルタ残響も区別し、旧ゲートを変更しない。','',
            '|窓ms|測定|安定/動的|通過/128|有声対象|対象不足|無声誤受理/分母|','|---|---|---|---:|---:|---:|---:|']
        for w,x in s['results'].items():
            for name,y in x.items():
                for scope,z in y.items():
                    g=z['groups']['both/all'];lines.append(f"|{w}|{name}|{scope}|{g['passed']}/128|{g['positive_windows']}|{g['inadequate_positive']}|{g['negative_false_accept']}/{g['negative_windows']}|")
        lines+=['','有声対象不足・edge・境界・パルス不足を分母から隠していない。既存コホート上の事後的な励振診断で、未知日本語やWORLD・全体品質の資格は得ていない。','次は既存WORLDの実励振観測を、元波形との一致を条件に事前登録する。','']
        b.write(HERE/'report.md','\n'.join(lines).encode(),job)
        files={str(p.relative_to(REPO)):digest(p) for p in HERE.rglob('*') if p.is_file()}
        b.save(HERE/'artifact-seal.json',dict(files=files,path_base='repository',experiment_completed=True,
            quality_goal_completed=False,protected_confirmation_opened=False),job)
        b.save(HERE/'completion-audit.json',dict(files_verified=len(files),seal_sha256=digest(HERE/'artifact-seal.json'),
            all_temporary_removed=True,quality_goal_completed=False),job)
    b.close_campaign(NAME)
    with b.locked():
        v=b._load();v.setdefault('continuation_checkpoint_history',[]).append(v['continuation_checkpoint'])
        v['continuation_checkpoint']=dict(id='hts-window-completed-20261008-0001',active_campaign=None,
            campaign_closed=True,quality_goal_completed=False,protected_confirmation_opened=False,
            next='commit/push→第26回WORLD実励振と旧波形の対応を事前登録',git_save_pending=True);b._write_state(v)
    b.save(ROOT/'progress-0035.json',dict(latest_completed=NAME,quality_goal_completed=False,
        protected_confirmation_opened=False,all_temporary_removed=True,next='第26回WORLD実励振観測',budget=b.reconcile()))
    print('封印完了',b.reconcile(),flush=True)
def main():
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['run','worker','close']);p.add_argument('--job');a=p.parse_args();verify()
    if a.stage=='worker':worker(a.job);return
    if a.stage=='close':close();return
    b=Budget();b.recover();assert not b.snapshot()['jobs'];protocol=read(HERE/'protocol.json')
    count=sum(not (HERE/'diagnostic'/(x['id']+'.json')).exists() for x in protocol['records']);assert count>0
    with b.job(NAME,'dsp','保存128HTSの短窓ACF・実パルス・適用分母',count=count*7+4,reserve_bytes=600_000_000) as job:
        with b.workspace(job,'測定ライブラリ初期化・外部専用cache') as (_,env):
            subprocess.run([str(PYTHON),'-B',str(HERE/'analysis.py'),'worker','--job',job],env=env,check=True,timeout=10800)
    print(b.reconcile(),flush=True)
if __name__=='__main__':main()
