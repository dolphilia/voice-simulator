"""YIN型測定を新しい人工音響周期・変動・境界で資格検証する。旧判定は改変しない。"""
import ast
import hashlib
import json
import os
import subprocess
from pathlib import Path
from budget import ROOT,read,digest,encode
from long_horizon_budget import LongHorizonBudget as Budget

REPO=ROOT.parents[2];HERE=ROOT/'campaigns/nas-yin-scope-qualification-20261008-v1';NAME='yin-scope-qualification-v1'
PYTHON=REPO/'research/experiments/autonomous-speech-synthesis/.venv-eval/bin/python'

MODULE=r'''"""固定幅の累積平均正規化差分による限定YIN型測定。完全YINとは呼ばない。"""
import numpy as np
FS=24000;FMIN=70.;FMAX=800.;THRESHOLD=.1
def difference(x):
    a=np.asarray(x,dtype=np.float64);maximum=int(np.floor(FS/FMIN));width=len(a)-maximum
    if a.ndim!=1 or width<3 or not np.isfinite(a).all():raise ValueError('窓幅または有限入力が不正')
    d=np.zeros(maximum+1)
    for lag in range(1,maximum+1):d[lag]=np.sum((a[:width]-a[lag:lag+width])**2)
    c=np.ones_like(d);total=np.cumsum(d[1:]);np.divide(d[1:]*np.arange(1,maximum+1),total,out=c[1:],where=total>0.)
    return d,c,width
def estimate(x):
    a=np.asarray(x,dtype=np.float64);d,c,width=difference(a)
    if np.var(a)<1e-20:return dict(hz=None,period=None,confidence=0.,reason='無変動',difference_width=width)
    minimum=int(np.ceil(FS/FMAX));selected=None
    for lag in range(minimum,len(c)-1):
        if c[lag]<THRESHOLD:
            while lag+1<len(c)-1 and c[lag+1]<c[lag]:lag+=1
            selected=lag;break
    if selected is None:return dict(hz=None,period=None,confidence=float(1.-min(c[minimum:])),reason='固定閾値未達',difference_width=width)
    left,center,right=c[selected-1:selected+2];denominator=left-2.*center+right
    shift=0. if denominator<=0. else float(np.clip(.5*(left-right)/denominator,-1.,1.));period=selected+shift
    confidence=float(1.-center)
    # 同じ差分幅で少なくとも一周期を平均し、二つの周期区間を観測する保守規則。
    if width<period:return dict(hz=None,period=float(period),confidence=confidence,reason='差分幅が一周期未満',difference_width=width)
    hz=float(FS/period)
    if not FMIN<=hz<=FMAX:return dict(hz=None,period=float(period),confidence=confidence,reason='探索範囲外',difference_width=width)
    return dict(hz=hz,period=float(period),confidence=confidence,reason='推定',difference_width=width)
'''

WORKER=r'''"""出力前固定した人工条件を生成し、全件・全分母を保持する。"""
import sys,json,hashlib,os,tempfile
from pathlib import Path
here=Path(__file__).resolve().parent;assert Path(tempfile.gettempdir()).resolve()==Path(os.environ['TMPDIR']).resolve()
sys.path.insert(0,str(here))
import numpy as np
from scipy import signal
from yin_style import difference,estimate,FS,FMIN
def sha(a):return hashlib.sha256(np.ascontiguousarray(a,dtype=np.float64).tobytes()).hexdigest()
def independent(x):
    maximum=int(FS/FMIN);width=len(x)-maximum;d=[0.]
    for lag in range(1,maximum+1):d.append(sum((float(x[j])-float(x[j+lag]))**2 for j in range(width)))
    c=[1.];total=0.
    for lag in range(1,len(d)):
        total+=d[lag];c.append(d[lag]*lag/total if total>0 else 1.)
    return np.array(d),np.array(c)
rng=np.random.default_rng(1050050);mechanism=[]
for name in ('zeros','DC','impulse','noise','sine','harmonic'):
    n=960;t=np.arange(n)/FS
    if name=='zeros':x=np.zeros(n)
    elif name=='DC':x=np.ones(n)*.3
    elif name=='impulse':x=np.zeros(n);x[17]=1.
    elif name=='noise':x=rng.normal(0.,.1,n)
    elif name=='sine':x=.2*np.sin(2*np.pi*220*t)
    else:x=.1*np.sin(2*np.pi*440*t)+.08*np.sin(2*np.pi*660*t)
    d,c,w=difference(x);di,ci=independent(x);de=float(np.max(np.abs(d-di))/max(float(np.max(di)),1e-12));ce=float(np.max(np.abs(c-ci)))
    assert de<=1e-12 and ce<=1e-12;mechanism.append(dict(name=name,input_sha256=sha(x),relative_difference_error=de,CMND_absolute_error=ce,passed=True))
rows=[]
def record(x,group,window,phase,truth,**meta):
    before=sha(x);out=estimate(x);assert sha(x)==before
    error=None if out['hz'] is None or truth is None else float(12*np.log2(out['hz']/truth))
    if group in ('static','dynamic'):passed=out['hz'] is not None and abs(error)<=.5
    else:passed=out['hz'] is None
    rows.append(dict(id=len(rows),group=group,window_ms=window,phase=phase,truth_hz=truth,input_sha256=before,samples=len(x),output=out,error_semitones=error,passed=passed,**meta))
def harmonics(phase,missing=False):
    return sum(np.sin(k*phase)/k for k in range(2 if missing else 1,9))*.2
for window in (20,40,80):
    n=round(FS*window/1000);t=np.arange(n)/FS
    for hz in (80.,110.,160.,220.,280.,350.,400.):
        for form in ('sine','harmonic','missing_fundamental','DC_offset','noise20dB'):
            for phase in (0.,np.pi/3,1.7):
                p=2*np.pi*hz*t+phase
                if form=='sine':x=.2*np.sin(p)
                elif form=='harmonic':x=harmonics(p)
                elif form=='missing_fundamental':x=harmonics(p,True)
                elif form=='DC_offset':x=.2*np.sin(p)+.4
                else:
                    clean=harmonics(p);noise=rng.normal(0.,1.,n);noise*=np.sqrt(np.mean(clean**2)/100./np.mean(noise**2));x=clean+noise
                record(x,'static',window,float(phase),hz,form=form)
    centered=(np.arange(n)-(n-1)/2)/FS
    for hz in (80.,160.,280.,400.):
        for slope in (-24.,-6.,6.,24.):
            k=np.log(2)*slope/12.;base=2*np.pi*hz*np.expm1(k*centered)/k
            for form in ('sine','missing_fundamental'):
                for phase in (0.,np.pi/3,1.7):
                    p=base+phase;x=.2*np.sin(p) if form=='sine' else harmonics(p,True)
                    record(x,'dynamic',window,float(phase),hz,form=form,slope_semitones_per_second=slope,
                        reference_sample_center=(n-1)/2,truth_kind='解析位相導関数の窓中央音響周波数。知覚truthではない。')
    for hz in (110.,280.):
        for form in ('sine','missing_fundamental'):
            for edge in ('onset','offset'):
                for fraction in (.125,.5,.875):
                    for phase in (0.,np.pi/3,1.7):
                        p=2*np.pi*hz*t+phase;x=.2*np.sin(p) if form=='sine' else harmonics(p,True)
                        count=round(n*fraction);mask=np.arange(n)>=n-count if edge=='onset' else np.arange(n)<count;x=x*mask
                        record(x,'boundary',window,float(phase),None,form=form,edge=edge,voiced_fraction=fraction,segment_frequency_hz=hz,
                            truth_kind='窓全体の周期truthなし。境界で推定保留できるかを全件判定し、部分有声Hzを窓全体truthへ転用しない。')
    for form in ('silence','DC','white_noise','lowpass_noise'):
        for seed in (105001,105002,105003):
            local=np.random.default_rng(seed)
            if form=='silence':x=np.zeros(n)
            elif form=='DC':x=np.full(n,.3)
            elif form=='white_noise':x=local.normal(0.,.1,n)
            else:x=signal.lfilter(*signal.butter(2,1000.,fs=FS),local.normal(0.,.1,n))
            record(x,'unvoiced',window,None,None,form=form,seed=seed)
assert len(rows)==855 and len(mechanism)==6
print(json.dumps(dict(rows=rows,mechanism=mechanism,render=861,dsp=867,counts=dict(static=315,dynamic=288,boundary=216,unvoiced=36,mechanism_signals=6,mechanism_DSP=12),
    render_is_artificial_not_speech=True,quality_certified=False),ensure_ascii=False,allow_nan=False))
'''

def register():
    b=Budget();b.recover();assert not b.snapshot()['jobs'] and not b.review_due()['due']
    previous=b.snapshot()['long_horizon']['last_review'];assert previous['scientific_completed']==18
    ast.parse(MODULE);ast.parse(WORKER)
    limits=dict(seconds=7200,bytes=300000000,write_bytes=800000000,setup=8,audit=12,render=2000,dsp=8000,ai=0,teacher=0,train=0,inverse=0,download=0)
    reg=dict(campaign=NAME,status='registered_before_output',question='累積平均正規化差分の限定YIN型測定は新人工音響周期の20/40/80ms、変動、境界、無周期のどの範囲を守れるか。',
        estimator=dict(fs=24000,fmin=70.,fmax=800.,threshold=.1,difference_width='N-floor(fs/70)。全lagで同一幅。',selection='最初の閾値未満谷まで下降し3点放物線補間。閾値未達は保留。',minimum_observation='差分幅Wが選択した補間周期以上。満たさなければ保留。',fallback=False,full_YIN_step6_local_search_implemented=False),
        fixtures=dict(windows_ms=[20,40,80],phases=[0.,'pi/3',1.7],static_f0=[80,110,160,220,280,350,400],static_forms=['sine','harmonic1to8','missing2to8','DC_offset','noise20dB'],dynamic_center_f0=[80,160,280,400],dynamic_slopes_semitones_per_second=[-24,-6,6,24],dynamic_forms=['sine','missing2to8'],boundary_f0=[110,280],boundary_forms=['sine','missing2to8'],boundary_edges=['onset','offset'],boundary_voiced_fraction=[.125,.5,.875],unvoiced_forms=['silence','DC','white_noise','lowpass_noise'],unvoiced_seeds=[105001,105002,105003],random_seed=1050050),
        gates=dict(independent_difference_relative=1e-12,independent_CMND_absolute=1e-12,pitch_error_semitones=.5,static='各窓×各form×各F0の全phaseで推定あり/誤差以内を全件要求。保留も不通過として保持。',dynamic='窓中央の解析位相導関数Hzへ全件誤差以内。中央値や推定lag中心truthで救済しない。',boundary='窓全体の周期truthがないので推定保留を要求。部分有声のHzをtruthにしない。',unvoiced='全件推定保留を要求。',scope='部分通過は事前group別の限定資格。全域/瞬時/知覚truthには移さない。'),
        costs=dict(render=861,dsp=867,ai=0,maximum_seconds=6000,external_peak=30000000,temporary_peak=8000000,temporary_write=16000000,RAM_gb=8,closeout_Git_included=True),limits=limits,
        source=dict(links=['https://pubmed.ncbi.nlm.nih.gov/12002874/','https://librosa.org/doc/0.11.0/generated/librosa.yin.html','https://raw.githubusercontent.com/aubio/aubio/master/src/pitch/pitchyin.c'],paper_DOI='10.1121/1.1458024',paper_fulltext_status='著者PDFと大学hostは取得不能、出版社リンクも取得不能。要旨と公式実装資料の範囲で限定YIN型を独立実装し、原論文全手順再現とは呼ばない。',source_code_copied=False),
        previous_review=previous,module_sha256=hashlib.sha256(MODULE.encode()).hexdigest(),worker_sha256=hashlib.sha256(WORKER.encode()).hexdigest(),controller_sha256=digest(Path(__file__)),
        old_measurement_sources_and_249_missing_and_judgments_unchanged=True,same_old_corpus_not_used_for_rescue=True,perceptual_qualification=False,protected_confirmation_opened=False,quality_goal_completed=False,
        next='通過した人工範囲と未確認HTS音響を区別して次の共有制御へ進む。不通過域を同じfixtureの閾値変更で救済しない。')
    b.start_campaign(NAME,str(HERE.relative_to(ROOT)),limits,hashlib.sha256(encode(reg)).hexdigest())
    with b.job(NAME,'setup','人工音響周期と限定YIN型範囲の出力前登録',reserve_bytes=2000000) as j:
        b.save(HERE/'registration.json',reg,j);b.write(HERE/'yin_style.py',MODULE.encode(),j);b.write(HERE/'worker.py',WORKER.encode(),j)
        b.save(HERE/'execution-contract.json',dict(files={str(p.relative_to(HERE)):digest(p) for p in HERE.rglob('*') if p.is_file()},controller_sha256=digest(Path(__file__)),no_scientific_output_yet=True),j)
    b.save(ROOT/'progress-0079.json',dict(active_campaign=NAME,next=reg['next'],new_scientific_outputs=0,quality_goal_completed=False,budget=b.reconcile()))
    print(dict(registered=True,render=861,dsp=867,new_scientific_outputs=0),flush=True)

def run():
    b=Budget();b.recover();assert not b.snapshot()['jobs'];contract=read(HERE/'execution-contract.json');assert digest(Path(__file__))==contract['controller_sha256']
    for n,h in contract['files'].items():assert digest(HERE/n)==h,n
    r=b.reserve(NAME,'render','新人工周期・変動・境界・無周期の全生成',861,20000000,expected_seconds=1200)
    try:
        d=b.reserve(NAME,'dsp','限定YIN型全855条件と独立差分/正規化照合',867,10000000,expected_seconds=1200)
        try:
            with b.workspace(r,'限定YIN型fixtureの科学ライブラリ初期化') as (_,env):
                env.update(OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',VECLIB_MAXIMUM_THREADS='1')
                out=subprocess.run([str(PYTHON),'-B',str(HERE/'worker.py')],env=env,check=True,capture_output=True,text=True,timeout=1100)
            result=json.loads(out.stdout);b.write_data(HERE/'fixture-records.json',encode(result),d)
        except BaseException as exc:
            if isinstance(exc,subprocess.CalledProcessError):b.save(HERE/'child-failure.json',dict(returncode=exc.returncode,stdout=exc.stdout,stderr=exc.stderr),d)
            b.finish(d,repr(exc));raise
        else:b.finish(d)
    except BaseException as exc:b.finish(r,repr(exc));raise
    else:b.finish(r)
    with b.job(NAME,'audit','限定資格・全不通過分母・旧保護・費用・一時回収の終了照合',reserve_bytes=4000000) as j:
        rows=result['rows'];assert len(rows)==855 and len(result['mechanism'])==6
        groups={}
        for x in rows:
            # 出力前規定groupにのみ分け、成功条件をあとから追加しない。
            key='/'.join(map(str,[x['group'],x['window_ms'],x['form']]+([x['truth_hz']] if x['group']=='static' else [x['truth_hz'],x['slope_semitones_per_second']] if x['group']=='dynamic' else [x['segment_frequency_hz'],x['edge'],x['voiced_fraction']] if x['group']=='boundary' else [])))
            groups.setdefault(key,[]).append(x)
        group_summary={k:dict(expected=len(v),passed=sum(x['passed'] for x in v),all_required_pass=all(x['passed'] for x in v),missing=sum(x['output']['hz'] is None for x in v),failures=[x['id'] for x in v if not x['passed']]) for k,v in groups.items()}
        domains={}
        for group in ('static','dynamic','boundary','unvoiced'):
            domains[group]={}
            for window in (20,40,80):
                chosen=[x for x in rows if x['group']==group and x['window_ms']==window]
                domains[group][str(window)]=dict(expected=len(chosen),passed=sum(x['passed'] for x in chosen),all_required_pass=all(x['passed'] for x in chosen),missing=sum(x['output']['hz'] is None for x in chosen))
        summary=dict(total_conditions=855,mechanical_formula_passed=True,mechanism=result['mechanism'],domains=domains,registered_groups=group_summary,
            qualified_scope='事前group別の全件通過した人工音響周期だけ。HTS/人間/知覚/旧欠測救済へは拡張しない。',
            all_declared_domains_passed=all(v['all_required_pass'] for d in domains.values() for v in d.values()),old_measurement_and_249_missing_and_judgments_unchanged=True,
            perceptual_qualification=False,protected_confirmation_opened=False,quality_goal_completed=False,fixture_path=str((HERE/'fixture-records.json').relative_to(REPO)),fixture_sha256=digest(HERE/'fixture-records.json'),
            next='不通過範囲と限定人工資格を保持し、同じfixtureの閾値調整を封印する。生成経路の次の独立した共有制御または新入力での測定範囲へ進む。')
        b.save(HERE/'aggregate-summary.json',summary,j)
        lines=['# 限定YIN型測定の人工範囲検証','','6機構信号で独立スカラー差分/累積正規化を照合し、855人工条件の全分母・保留・不通過を保存した。完全YINの全手順再現とは呼ばない。静的/動的は音響周期の式をtruthとし、知覚truthにはしない。','','|範囲|窓ms|通過|保留|全件通過|','|---|---:|---:|---:|---|']
        for group,windows in domains.items():
            for window,v in windows.items():lines.append(f'|{group}|{window}|{v["passed"]}/{v["expected"]}|{v["missing"]}|{v["all_required_pass"]}|')
        lines+=['','差分幅N-floor(fs/70)は全lagで固定し、差分幅が選択周期未満なら保留する。動的truthは窓中央の位相導関数で、推定lagに合わせた時刻変更で救済しない。境界窓は全体周期truthがなく、推定保留を要求した。','','旧DIO/ACF、旧支持/249欠測、旧判定は変更しない。成功した事前groupだけが人工限定資格であり、HTS音響・短窓の一般資格・知覚自然さを主張しない。同fixtureの閾値救済は封印する。P5未開封・品質未達。','',
            '一次資料: [YIN書誌/要旨](https://pubmed.ncbi.nlm.nih.gov/12002874/)、[librosa公式YIN](https://librosa.org/doc/0.11.0/generated/librosa.yin.html)、[aubio公式実装](https://github.com/aubio/aubio/blob/master/src/pitch/pitchyin.c)。著者原論文PDF/出版社本文は取得できず、公式実装の説明と式の範囲で独立実装した。','']
        b.write(HERE/'report.md','\n'.join(lines).encode(),j)
        for n,h in contract['files'].items():assert digest(HERE/n)==h,n
        s=b.snapshot();c=s['campaigns'][NAME];temporary=[v for v in s['temporary_work'].values() if v['campaign']==NAME];assert all(v['status']=='removed' and not os.path.lexists(v['path']) for v in temporary)
        b.save(HERE/'cost-audit.json',dict(counts=c['counts'],seconds=s['seconds']-c['start_seconds'],write_bytes=s['write_bytes']-c['start_write_bytes'],temporary_owned=len(temporary),all_temporary_absent=True,no_speech_or_model_download=True),j)
        b.save(HERE/'artifact-seal.json',dict(files={str(p.relative_to(REPO)):digest(p) for p in HERE.rglob('*') if p.is_file()},path_base='repository',experiment_completed=True,quality_goal_completed=False,protected_confirmation_opened=False),j)
    b.close_campaign(NAME)
    with b.locked():
        s=b._load();s['continuation_checkpoint'].update(id='yin-scope-qualification-completed',active_campaign=None,next=summary['next'],git_save_pending=True);b._write_state(s)
    b.save(ROOT/'progress-0080.json',dict(latest_completed=NAME,quality_goal_completed=False,next=summary['next'],review=b.review_due(),budget=b.reconcile()))
    print(dict(domains=domains,quality_goal_completed=False),flush=True)

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['register','fixture']);a=p.parse_args();register() if a.stage=='register' else run()
