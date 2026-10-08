"""第32回：HTS短窓ACFの重なり正規化とピーク選択を因子別に検証する。"""
from contextlib import contextmanager
import ast
import hashlib
import os
from pathlib import Path
import subprocess
from budget import ROOT, read, digest, encode
from long_horizon_budget import LongHorizonBudget as Budget

REPO=ROOT.parents[2]; NAME='hts-overlap-qualification-v1'
HERE=ROOT/'campaigns/nas-hts-overlap-qualification-20261008-v1'
LPF=ROOT/'campaigns/nas-hts-lpf-observation-20261008-v1'
OLD=ROOT/'campaigns/nas-hts-window-audit-20261008-v1'
PERIOD=ROOT/'campaigns/nas-source-period-audit-20261008-v1'
PYTHON=REPO/'research/experiments/autonomous-speech-synthesis/.venv-eval/bin/python'
SOURCE='https://www.researchgate.net/profile/Geoff-Wyvill/publication/230554927_A_smarter_way_to_find_pitch/links/561a12f108aea80367211169/A-smarter-way-to-find-pitch.pdf?origin=publication_detail'

MEASURE=r'''"""NSDFの式9を独立実装。旧ACFと2×2の固定比較を行う。"""
import numpy as np
from scipy import signal
NAMES=('bounded_all','overlap_all','bounded_key','overlap_key')
def curves(x):
    x=np.asarray(x,dtype=float).copy();x-=np.mean(x)
    r=signal.correlate(x,x,mode='full',method='fft')[len(x)-1:]
    bounded=r/np.maximum(1,np.arange(len(x),0,-1))
    e=np.r_[0.,np.cumsum(x*x)];lags=np.arange(len(x))
    denominator=e[len(x)-lags]+e[-1]-e[lags]
    overlap=np.divide(2*r,denominator,out=np.zeros_like(r),where=denominator>0)
    return bounded,overlap
def estimate(x,fs=24000):
    out={name:(0.,0.) for name in NAMES};x=np.asarray(x,dtype=float)
    if len(x)<fs*.010 or not np.isfinite(x).all():return out
    centered=x-x.mean()
    if np.sqrt(np.mean(centered*centered))<1e-5:return out
    bounded,overlap=curves(x);lo=int(fs/800);hi=min(len(x)-2,int(fs/70))
    if hi<=lo or bounded[0]<=0:return out
    for norm,curve in [('bounded',bounded),('overlap',overlap)]:
        peaks,_=signal.find_peaks(curve[lo:hi]);peaks+=lo;peaks=peaks[curve[peaks]>0]
        if not len(peaks):continue
        # keyは初期正領域を除き、正の各連続領域で最大の局所ピークのみを残す。
        positive=curve>0;starts=np.flatnonzero(positive&~np.r_[False,positive[:-1]])
        ends=np.flatnonzero(positive&~np.r_[positive[1:],False])+1
        key=[]
        for a,z in zip(starts,ends):
            if a==0:continue
            candidates=peaks[(peaks>=a)&(peaks<z)]
            if len(candidates):key.append(int(candidates[np.argmax(curve[candidates])]))
        for picking,available in [('all',peaks),('key',np.asarray(key,dtype=int))]:
            if not len(available):continue
            best=max(curve[available]);candidates=available[curve[available]>=.93*best];lag=int(candidates[0])
            delta=.5*(curve[lag-1]-curve[lag+1])/(curve[lag-1]-2*curve[lag]+curve[lag+1])
            hz=float(fs/(lag+np.clip(delta,-.5,.5)))
            confidence=float(np.clip(curve[lag]/curve[0],0,1))
            out[norm+'_'+picking]=(hz if confidence>=.6 else 0.,confidence)
    return out
def local(audio,times,width):
    output={name:np.zeros(len(times)) for name in NAMES};confidence={name:np.zeros(len(times)) for name in NAMES}
    half=round(width*24/2)
    for i,t in enumerate(times):
        center=round(float(t)*24000);a,z=center-half,center+half
        if a<0 or z>len(audio):continue
        for name,(hz,c) in estimate(audio[a:z]).items():output[name][i]=hz;confidence[name][i]=c
    return output,confidence
'''

WORKER=r'''"""保存224波形の全clock・固定支持・LPF寄与を保持する測定資格診断。"""
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
            assert np.array_equal(times,legacy['times'])
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
'''

@contextmanager
def job(b,kind,label,count,size,seconds):
    token=b.reserve(NAME,kind,label,count,size,expected_seconds=seconds)
    try:yield token
    except BaseException as e:b.finish(token,repr(e));raise
    else:b.finish(token)

def prepare():
    b=Budget();b.recover();assert not b.snapshot()['jobs']
    ast.parse(MEASURE);ast.parse(WORKER)
    records=read(LPF/'protocol.json')['records'];assert len(records)==224
    diagnostics={x['id']:x for x in read(LPF/'diagnostic-manifest.json')['rows']}
    legacy={x['id']:x for x in read(OLD/'diagnostic-manifest.json')['rows']}
    for item in records:
        row=diagnostics[item['id']];item['lpf_diagnostic']=row['path'];item['lpf_diagnostic_sha256']=row['sha256']
        d=read(REPO/row['path']);item['lpf_arrays']=d['arrays_path'];item['lpf_arrays_sha256']=d['arrays_sha256']
        if item['cohort']=='nas-mcp-postfilter':
            prior=read(REPO/legacy[item['id'].split('/',1)[1]]['path']);item['legacy_arrays']=prior['arrays'];item['legacy_arrays_sha256']=prior['arrays_sha256']
    limits=dict(seconds=14400,bytes=1500000000,write_bytes=2200000000,render=30,dsp=14000,ai=0,teacher=0,train=0,inverse=0,download=0,setup=40,audit=60)
    reg=dict(campaign=NAME,status='registered_before_output',question='短窓ACFの端部エネルギー正規化と正領域keyピーク選択は、HTS実パルス平均発生率との対応をどこで改善/悪化させるか',
        factors=dict(normalization=['旧r/(N-lag)','NSDF式9:2r/(重なり両側の二乗和)'],peak_picking=['旧全局所ピーク','初期正領域を除き各正領域最大の局所ピーク']),
        constants=dict(width_ms=[20,40,60],frequency_hz=[70,800],RMS_minimum=1e-5,confidence_minimum=.6,peak_relative=.93,parabola_clip=[-.5,.5],no_smoothing_or_truth_conditioning=True),
        input='既存HTS224件。LPF純観測/源時計/WAVhash/全固定支持を引継ぐ。既存128件は3幅の旧ACF完全一致を対照検査。',
        ground='旧関数byte不変。窓内4パルス以上の平均発生率。stable/dynamic/edge/boundary/unvoiced/insufficientを保持。',
        gates=dict(each_wave_positive_and_negative_minimum=3,coverage=.9,median_error_semitones=1.,unvoiced_false_accept=.05,missing_is_failure=True),
        qualification='この既存コホート内の源パルス平均率診断のみ。未知日本語/瞬時F0/知覚pitch/WORLD/旧ゲート/最終品質へ拡張しない。境界は単一率truthを設定しない。',
        source=dict(paper='McLeod and Wyvill, ICMC 2005, A smarter way to find pitch',url=SOURCE,equations=[6,9],retrieved='2026-10-08',formula_independent_implementation=True,full_MPM_replication_not_claimed=True,existing_cutoff_kept_not_tuned=True),
        limits=limits,estimates=dict(DSP_per_wave=31,DSP_total=6944,fixture_DSP=100,maximum_with10_batch_retries=12004,render=4,batch_size=16,batch_timeout=300,fixture_timeout=120,worst_seconds=8300,external_arrays_and_diagnostics_peak=500000000,temporary_peak=16000000,metadata_Git_closeout_included=True),
        technical_retry_per_job=2,technical_retry_campaign=10,parallel_max=2,RAM_gb=8,new_AI_teacher_train_inverse_download=0,protected_confirmation_opened=False,quality_goal_completed=False)
    b.start_campaign(NAME,str(HERE.relative_to(ROOT)),limits,hashlib.sha256(encode(reg)).hexdigest())
    with job(b,'setup','全224入力・数式と因子・費用を固定',1,3000000,300) as j:
        b.save(HERE/'registration.json',reg,j);b.save(HERE/'protocol.json',dict(records=records),j)
        b.write(HERE/'measure.py',MEASURE.encode(),j);b.write(HERE/'analysis.py',WORKER.encode(),j)
        b.write(HERE/'short_acf.py',(OLD/'short_acf.py').read_bytes(),j)
        old=(OLD/'analysis.py').read_text();nodes=ast.parse(old).body;parts=[ast.get_source_segment(old,n) for n in nodes if isinstance(n,ast.FunctionDef) and n.name in ('ground','score')]
        assert len(parts)==2;b.write(HERE/'score_ground.py',('\n\n'.join(parts)+'\n').encode(),j)
    runtime={str((PERIOD/'runtime-bundle'/n).relative_to(REPO)):h for n,h in read(PERIOD/'runtime-bundle/manifest.json')['files'].items()}
    b.save(HERE/'execution-contract.json',dict(registration_sha256=digest(HERE/'registration.json'),protocol_sha256=digest(HERE/'protocol.json'),source_hashes={p.name:digest(p) for p in HERE.glob('*.py')},runtime_hashes=runtime,controller_sha256=digest(Path(__file__)),all_conditions_fixed_before_output=True))
    with b.locked():
        s=b._load();s['continuation_checkpoint_history'].append(s['continuation_checkpoint']);s['continuation_checkpoint']=dict(id='hts-overlap-prepared',active_campaign=NAME,next='登録commit/push→数値fixture→224短窓2×2比較→集計/封印',git_save_pending=True,quality_goal_completed=False,protected_confirmation_opened=False);b._write_state(s)
    b.save(ROOT/'progress-0047.json',dict(active_campaign=NAME,new_scientific_outputs=0,quality_goal_completed=False,budget=b.reconcile()))
    print(b.reconcile(),flush=True)

def run(stage):
    b=Budget();b.recover();assert not b.snapshot()['jobs']
    if stage=='fixture':
        with job(b,'render','4数値音源fixture',4,20000000,120) as r:
            with job(b,'dsp','直接和/対称性/旧ACFの数値fixture',100,1000000,120) as d:
                with b.workspace(r,'数値fixture初期化') as (_,env):
                    out=subprocess.run([str(PYTHON),'-B',str(HERE/'analysis.py'),'fixture'],env=env,check=True,timeout=120,stdout=subprocess.PIPE,text=True)
                b.save(HERE/'fixture-audit.json',__import__('json').loads(out.stdout),d)
    else:
        assert read(HERE/'fixture-audit.json')['passed']
        for begin in range(0,224,16):
            end=begin+16
            if (HERE/'batches'/f'{begin:03d}-{end:03d}.json').exists():continue
            count=sum(not (HERE/'diagnostic'/(x['id']+'.json')).exists() for x in read(HERE/'protocol.json')['records'][begin:end])
            with job(b,'dsp' if count else 'audit',f'短窓2×2と全分母 {begin}:{end}',max(1,count*31),100000000,300) as d:
                with b.workspace(d,'短窓測定初期化') as (_,env):
                    subprocess.run([str(PYTHON),'-B',str(HERE/'analysis.py'),'batch','--begin',str(begin),'--end',str(end),'--job',d],env=env,check=True,timeout=300)
    print(b.reconcile(),flush=True)

def close():
    b=Budget();b.recover();assert not b.snapshot()['jobs'];rows=[]
    for p in sorted((HERE/'batches').glob('*.json')):
        for x in read(p)['rows']:
            assert digest(REPO/x['path'])==x['sha256'];rows.append(read(REPO/x['path']))
    assert len(rows)==224 and sum(x['legacy128_all_widths_exact'] for x in rows)==128
    with job(b,'audit','全分母/因子別集計・旧欠測・費用・封印',1,5000000,300) as j:
        groups={}
        for cohort in sorted({x['cohort'] for x in rows}):
            for method in sorted({x['method'] for x in rows if x['cohort']==cohort}):
                selected=[x for x in rows if x['cohort']==cohort and x['method']==method]
                groups[cohort+'/'+method]={}
                for width in ('20','40','60'):
                    groups[cohort+'/'+method][width]={}
                    for name in ('bounded_all','overlap_all','bounded_key','overlap_key'):
                        groups[cohort+'/'+method][width][name]={}
                        for scope in ('stable','dynamic'):
                            scores=[x['results'][width][name][scope] for x in selected]
                            groups[cohort+'/'+method][width][name][scope]=dict(expected=len(scores),passed=sum(x['passed'] for x in scores),all_pass=all(x['passed'] for x in scores),failed_ids=[x['id'] for x in selected if not x['results'][width][name][scope]['passed']],totals={k:sum(x[k] for x in scores) for k in ('positive_windows','negative_windows','correct_positive','missing_positive','negative_false_accept','inadequate_positive','inadequate_negative')},classes={k:sum(x['exclusions'][k] for x in scores) for k in scores[0]['exclusions']})
        summary=dict(total=224,groups=groups,legacy128_all_widths_exact=True,ground224_matches_LPF=True,old_HTS_missing94=sum(len(x['old_missing_support']) for x in rows),boundary_not_single_rate_truth=True,all_clock_and_fixed_support_denominators_retained=True,observational_existing_corpus_only=True,prospective_or_perceptual_qualification=False,old_gates_ASR_and_decisions_unchanged=True,quality_goal_completed=False,protected_confirmation_opened=False,next='因子別の有効/不通過範囲を使い、独立な新しい源/フィルタ生成比較へ配分する。知覚資格も並行して資料条件を調べる。')
        assert summary['old_HTS_missing94']==94;b.save(HERE/'aggregate-summary.json',summary,j)
        lines=['# HTS短窓の重なり正規化とピーク選択','', '224旧波形を再生成せず、同じ源時計と全固定支持で20/40/60msを比較。旧128件の全3幅ACFと、LPF観測224件のgroundは完全一致。','', '|コホート/方式|窓ms|測定|安定通過|動的通過|無声誤受理/分母|','|---|---|---|---|---|---|']
        for group,ws in groups.items():
            for w,methods in ws.items():
                for name,scopes in methods.items():
                    a=scopes['stable'];d=scopes['dynamic'];t=a['totals'];lines.append(f'|{group}|{w}|{name}|{a["passed"]}/{a["expected"]}|{d["passed"]}/{d["expected"]}|{t["negative_false_accept"]}/{t["negative_windows"]}|')
        lines+=['','源パルス平均発生率の既存コホート診断。未知日本語・瞬時F0・知覚pitch・WORLDの資格や、旧DIO/ACF/ASR/最終品質判定を更新しない。境界に単一率truthを設定せず、edge・境界・パルス不足・無声の分母を保持。旧HTS欠測94と全固定支持を個票へ保存。','',f'正規化式の一次資料: [McLeod and Wyvill (2005)]({SOURCE})。式9を独立実装し、旧ピーク係数.93を保持した因子比較。完全なMPMの再現や日本語での知覚資格は主張しない。','',summary['next'],'']
        b.write(HERE/'report.md','\n'.join(lines).encode(),j)
        s=b.snapshot();c=s['campaigns'][NAME];b.save(HERE/'cost-audit.json',dict(counts=c['counts'],seconds=s['seconds']-c['start_seconds'],write_bytes=s['write_bytes']-c['start_write_bytes'],all_temporary_absent=all(x['status']=='removed' and not os.path.lexists(x['path']) for x in s['temporary_work'].values()),old_audio_not_regenerated=True,new_audio_saved=0),j)
        b.save(HERE/'artifact-seal.json',dict(files={str(p.relative_to(REPO)):digest(p) for p in HERE.rglob('*') if p.is_file()},path_base='repository',experiment_completed=True,quality_goal_completed=False,protected_confirmation_opened=False),j)
    b.close_campaign(NAME)
    with b.locked():
        s=b._load();s['continuation_checkpoint'].update(id='hts-overlap-completed',active_campaign=None,next=summary['next'],git_save_pending=True);b._write_state(s)
    b.save(ROOT/'progress-0048.json',dict(latest_completed=NAME,quality_goal_completed=False,next=summary['next'],review=b.review_due(),budget=b.reconcile()))
    print(b.reconcile(),flush=True)

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('stage',choices=('prepare','fixture','run','close'));a=p.parse_args()
    prepare() if a.stage=='prepare' else close() if a.stage=='close' else run(a.stage)
