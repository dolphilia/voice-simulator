"""保存全MCP frameの全極近似を一度監査する。波形再生成・係数探索は行わない。"""
import ast,hashlib,json,os,subprocess
from pathlib import Path
from budget import ROOT,read,digest,encode
from long_horizon_budget import LongHorizonBudget as Budget
REPO=ROOT.parents[2]
HERE=ROOT/'campaigns/nas-hts-lattice-projection-20261008-v1'
NAME='hts-lattice-projection-v1'
MECHANISM=ROOT/'campaigns/nas-hts-lattice-mechanism-20261008-v1'
CORPUS=ROOT/'campaigns/nas-hts-output-bound-comparison-20261008-v1'
PYTHON=REPO/'research/experiments/autonomous-speech-synthesis/.venv-eval/bin/python'

WORKER=r'''"""有限gridの近似損失と数値安定域を全frameで記録する。"""
import sys,json,os,tempfile
from pathlib import Path
here=Path(__file__).resolve().parent;reg=json.loads((here/'registration.json').read_text());corpus=json.loads((here/'corpus-contract.json').read_text())
assert Path(tempfile.gettempdir()).resolve()==Path(os.environ['TMPDIR']).resolve()
sys.path.insert(0,reg['mechanism_bundle'])
import numpy as np
from scipy import linalg
from lattice import levinson,project,ORDER,FFT_LENGTH
assert ORDER==34 and FFT_LENGTH==16384
q={n:np.exp(-2j*np.pi*np.arange(n//2+1)/n) for n in (16384,32768)}
w={n:(v-.55)/(1.-.55*v) for n,v in q.items()}
def batch_response(mc,n):
    result=np.broadcast_to(mc[:,-1,None],(len(mc),len(w[n]))).astype(np.complex128).copy()
    for i in range(33,-1,-1):result=result*w[n][None,:]+mc[:,i,None]
    return np.exp(result)
def normalized_error(a,z):return float(np.max(np.abs(a-z))/max(1.,np.max(np.abs(a))))
records=[];waves=[];frames_expected=0
for ci,item in enumerate(corpus['rows']):
    with np.load(item['npz'],allow_pickle=False) as z:mc=z['mcp'].copy()
    assert mc.ndim==2 and mc.shape[1]==35 and np.isfinite(mc).all();frames_expected+=len(mc)
    current=[];batch_check=None
    for start in range(0,len(mc),32):
        part=mc[start:start+32];h=batch_response(part,16384);hr=batch_response(part,32768)
        power=np.abs(h)**2;refpower=np.abs(hr)**2
        r=np.fft.irfft(power,n=16384,axis=1)[:,:35];rr=np.fft.irfft(refpower,n=32768,axis=1)[:,:35]
        for offset,c in enumerate(part):
            frame=start+offset;row=dict(id=item['id'],frame=frame,passed=False,failures=[],normalized_dense_coefficient_error=None,log_magnitude_RMSE_dB=None,refinement_relative_coefficient_error=None,refinement_relative_gain_error=None,reflection_max_abs=None,root_radius_diagnostic=None)
            try:
                a,k,g=levinson(r[offset]);ar,kr,gr=levinson(rr[offset]);row['reflection_max_abs']=float(np.max(np.abs(k)))
                dense=np.r_[1.,np.linalg.solve(linalg.toeplitz(r[offset,:-1]/r[offset,0]),-r[offset,1:]/r[offset,0])]
                de=normalized_error(a,dense);ce=normalized_error(a,ar);ge=float(abs(g-gr)/max(abs(g),1e-12))
                approx=g/np.polynomial.polynomial.polyval(q[16384],a)
                rmse=float(np.sqrt(np.mean((20*np.log10(np.abs(approx)/np.abs(h[offset])))**2)))
                radius=float(np.max(np.abs(np.roots(a))))
                row.update(normalized_dense_coefficient_error=de,log_magnitude_RMSE_dB=rmse,refinement_relative_coefficient_error=ce,refinement_relative_gain_error=ge,root_radius_diagnostic=radius)
                if de>1e-10:row['failures'].append('独立密Toeplitz係数誤差')
                if rmse>2.:row['failures'].append('有限grid振幅RMSE')
                if ce>1e-8 or ge>1e-8:row['failures'].append('grid観測refinement')
                if not np.isfinite([de,rmse,ce,ge,radius]).all():row['failures'].append('非有限診断')
                if frame==0:
                    aa,kk,gg,r0=project(c);be=max(normalized_error(a,aa),float(np.max(np.abs(k-kk))),float(abs(g-gg)/max(abs(g),1e-12)),float(np.max(np.abs(r[offset]-r0))/max(float(r0[0]),1e-12)))
                    batch_check=be
                    if be>1e-12:row['failures'].append('batchと原projectの数値差')
                row['passed']=not row['failures']
            except (ValueError,np.linalg.LinAlgError,FloatingPointError) as exc:
                row['failures'].append('射影/独立解/安定域の定義不能');row['error']=repr(exc)
            for key,value in list(row.items()):
                if isinstance(value,float) and not np.isfinite(value):row[key]=None
            current.append(row);records.append(row)
    assert len(current)==len(mc)
    def maximum(key):
        vals=[v[key] for v in current if v[key] is not None];return max(vals) if vals else None
    causes={}
    for v in current:
        for reason in v['failures']:causes[reason]=causes.get(reason,0)+1
    waves.append(dict(id=item['id'],frames_expected=len(mc),frames_recorded=len(current),passed_frames=sum(v['passed'] for v in current),excluded_frames=0,failed_frames=sum(not v['passed'] for v in current),causes=causes,
        maximum_log_magnitude_RMSE_dB=maximum('log_magnitude_RMSE_dB'),maximum_normalized_dense_coefficient_error=maximum('normalized_dense_coefficient_error'),
        maximum_refinement_relative_coefficient_error=maximum('refinement_relative_coefficient_error'),maximum_refinement_relative_gain_error=maximum('refinement_relative_gain_error'),
        maximum_reflection_abs=maximum('reflection_max_abs'),maximum_root_radius_diagnostic=maximum('root_radius_diagnostic'),batch_original_project_maximum_error=batch_check,all_required_pass=all(v['passed'] for v in current)))
    Path(os.environ['TMPDIR'],'progress.json').write_text(json.dumps(dict(completed_native_cases=ci+1,total_native_cases=32,frames_recorded=len(records),failed_frames=sum(not v['passed'] for v in records))))
assert len(waves)==32 and len(records)==frames_expected==20276
print(json.dumps(dict(rows=waves,frames=records,total_frames=frames_expected,excluded_frames=0,all_frames_attempted=True,all_required_pass=all(v['passed'] for v in records),render=0,dsp=160,
    diagnostics_only=True,no_waveform_read_or_generated=True,order=34,base_FFT=16384,observation_refinement_FFT=32768,coefficient_adjustment_after_output=False,quality_certified=False),allow_nan=False))
'''

def verify(contract):
    assert digest(Path(__file__))==contract['controller_sha256']
    for n,h in contract['files'].items():assert digest(HERE/n)==h,n
    for n,h in read(HERE/'corpus-contract.json')['files'].items():assert digest(Path(n))==h,n
    for n,h in read(HERE/'mechanism-contract.json')['files'].items():assert digest(REPO/n)==h,n
def register():
    b=Budget();b.recover();assert not b.snapshot()['jobs'] and not b.review_due()['due']
    m=read(MECHANISM/'aggregate-summary.json');assert not m['mechanical_fixture_passed'] and m['implementation_mechanical_fixture_passed']
    assert b.snapshot()['long_horizon']['last_review']['scientific_completed']==24
    ast.parse(WORKER)
    limits=dict(seconds=7200,bytes=300000000,write_bytes=800000000,setup=10,audit=10,render=0,dsp=480,ai=0,teacher=0,train=0,inverse=0,download=0)
    reg=dict(campaign=NAME,question='実native全MCP frameの固定order34全極射影が、有限grid振幅損失・独立密Toeplitz・反射係数安定域・gridrefinementの操作的条件を全件保持できるか。',
        input='直前の未使用16文×2条件のnative保存32列、全20,276 frame。選別/除外なし。波形本体は読みも生成もしない。',
        factor='alpha.55/order34/FFT16384/自己相関/元Levinson-Durbinを固定。32768は観測refinementのみで候補を変更しない。loading/clip/新係数/gain探索なし。',
        thresholds=dict(log_magnitude_RMSE_dB_at_most=2.,normalized_dense_coefficient_error_at_most=1e-10,reflection_abs_below=.99999999,
            relative_refinement_coefficient_and_gain_error_at_most=1e-8,batch_original_project_relative_error_at_most=1e-12,all_frames_required=True,undefined_measures_fail=True),
        root_radius_scope='有限精度polynomial根は診断値として保存。瞬時反射係数域と有限gridを、任意時間変動の一様安定へ拡張しない。',
        approximation_scope='2dB等は事前設計の工学的近似幅。既知AR2不通過を救済せず、日本語自然さ/動的pitch/内容を保証しない。',
        estimates=dict(render=0,dsp=160,dsp_unit='32保存列×全frame射影、独立解、grid損失、refinement、安定域/batch照合の5監査。各監査は全frameを検査。',maximum_seconds=6500,temporary_peak=8000000,temporary_write=16000000,RAM_gb=8),limits=limits,
        mechanism_bundle=str(MECHANISM/'runtime-bundle'),worker_sha256=hashlib.sha256(WORKER.encode()).hexdigest(),controller_sha256=digest(Path(__file__)),
        source=dict(mechanism_seal_sha256=digest(MECHANISM/'artifact-seal.json'),corpus_seal_sha256=digest(CORPUS/'artifact-seal.json'),review_sha256=digest(ROOT/'campaigns/nas-long-horizon-review-20261008-v4/decision.json')),
        next_if_pass='一回のみ新16文native/latticeの日本語比較を生成前登録し、全工学/二ASR/隔離を確認。',
        next_if_fail='同order/warp/loadingの係数救済を封印し、別の共有音響モデル/文脈表現または調音制御へ移る。旧17→96同8残差/同learnerの救済は継承しない。',
        original_known_AR_qualification=False,perceptual_qualification=False,protected_confirmation_opened=False,quality_goal_completed=False)
    b.start_campaign(NAME,str(HERE.relative_to(ROOT)),limits,hashlib.sha256(encode(reg)).hexdigest())
    with b.job(NAME,'setup','全実MCP有限射影の分母・近似幅・全費用を観測前登録',reserve_bytes=2000000) as j:
        rows=[];files={}
        for item in read(CORPUS/'render-manifest.json')['rows']:
            r=read(REPO/item['record'])
            if r['variant']!='native':continue
            p=(REPO/r['wav']).with_suffix('.npz');rows.append(dict(id=r['id'],npz=str(p)));files[str(p)]=digest(p)
        assert len(rows)==32
        b.save(HERE/'registration.json',reg,j);b.write(HERE/'worker.py',WORKER.encode(),j)
        b.save(HERE/'corpus-contract.json',dict(rows=rows,files=files,corpus_seal_sha256=digest(CORPUS/'artifact-seal.json'),waveform_body_not_read=True),j)
        b.save(HERE/'mechanism-contract.json',dict(files=read(MECHANISM/'artifact-seal.json')['files'],implementation_scope_only=True,original_AR_qualification=False),j)
        b.save(HERE/'execution-contract.json',dict(files={str(p.relative_to(HERE)):digest(p) for p in HERE.rglob('*') if p.is_file()},controller_sha256=digest(Path(__file__)),no_scientific_output_yet=True),j)
    b.save(ROOT/'progress-0092.json',dict(active_campaign=NAME,new_scientific_outputs=0,next='登録push→全32保存列の20,276 frame観測→近似/安定域の全件封印',quality_goal_completed=False,budget=b.reconcile()))
    print(dict(registered=True,saved_native_arrays=32,expected_frames=20276,new_scientific_outputs=0),flush=True)
def run():
    b=Budget();b.recover();assert not b.snapshot()['jobs'];contract=read(HERE/'execution-contract.json');verify(contract)
    d=b.reserve(NAME,'dsp','全32nativeの全frame射影・独立解・近似損失・refinement・安定域監査',160,20000000,expected_seconds=6500)
    try:
        with b.workspace(d,'全実MCP観測の科学ライブラリ初期化',8000000,16000000) as (work,env):
            env.update(OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',VECLIB_MAXIMUM_THREADS='1')
            try:out=subprocess.run([str(PYTHON),'-B',str(HERE/'worker.py')],env=env,check=True,capture_output=True,text=True,timeout=6400)
            except subprocess.CalledProcessError as exc:
                progress=read(work/'progress.json') if (work/'progress.json').exists() else None
                b.save(HERE/'child-failure.json',dict(returncode=exc.returncode,stdout=exc.stdout,stderr=exc.stderr,progress=progress),d);raise
        data=json.loads(out.stdout);assert data['total_frames']==20276 and data['excluded_frames']==0
        frames=data.pop('frames');b.write_data(HERE/'frame-records.json',encode(frames),d);data['frame_records_sha256']=digest(HERE/'frame-records.json')
        b.save(HERE/'aggregate-summary.json',dict(data,original_known_AR_qualification=False,perceptual_qualification=False,protected_confirmation_opened=False,quality_goal_completed=False),d)
    except BaseException as exc:b.finish(d,repr(exc));raise
    else:b.finish(d)
    with b.job(NAME,'audit','全分母・近似幅・不通過・hash・費用・一時回収の終了照合',reserve_bytes=2000000) as j:
        verify(contract);reg=read(HERE/'registration.json')
        nxt=reg['next_if_pass'] if data['all_required_pass'] else reg['next_if_fail']
        lines=['# 実MCPの全極近似と安定域の監査','','保存新native32列の全20,276 frameを観測した。波形の読取/再生成0、係数調整0。原order34/alpha.55/FFT16384を固定し、32768は観測refinementだけに使った。','',
            '|native条件|全frame|通過frame|不通過frame|最大振幅RMSE dB|','|---|---:|---:|---:|---:|']
        for r in data['rows']:lines.append(f'|{r["id"]}|{r["frames_expected"]}|{r["passed_frames"]}|{r["failed_frames"]}|{r["maximum_log_magnitude_RMSE_dB"]}|')
        lines+=['','全件近似資格: '+str(data['all_required_pass'])+'。2dB/独立解1e-10/refinement1e-8等は事前の操作的閾値で、自然さ・内容・動的安定や連続全周波数を保証しない。定義不能・不通過を分母から除外していない。既知ARの元14/16不通過も保持する。','',nxt,'','旧欠測249/各ASR33群・全凍結は保持。知覚資格なし・P5未開封・品質未達。','']
        b.write(HERE/'report.md','\n'.join(lines).encode(),j)
        s=b.snapshot();c=s['campaigns'][NAME];temporary=[v for v in s['temporary_work'].values() if v['campaign']==NAME];assert all(v['status']=='removed' and not os.path.lexists(v['path']) for v in temporary)
        b.save(HERE/'cost-audit.json',dict(counts=c['counts'],seconds=s['seconds']-c['start_seconds'],write_bytes=s['write_bytes']-c['start_write_bytes'],temporary_owned=len(temporary),all_temporary_absent=True),j)
        b.save(HERE/'artifact-seal.json',dict(files={str(p.relative_to(REPO)):digest(p) for p in HERE.rglob('*') if p.is_file()},path_base='repository',experiment_completed=True,all_frame_approximation_qualification=data['all_required_pass'],quality_goal_completed=False,protected_confirmation_opened=False),j)
    b.close_campaign(NAME)
    with b.locked():
        s=b._load();s['continuation_checkpoint'].update(id='lattice-projection-completed',active_campaign=None,next=nxt,git_save_pending=True);b._write_state(s)
    b.save(ROOT/'progress-0093.json',dict(latest_completed=NAME,all_frame_approximation_qualification=data['all_required_pass'],quality_goal_completed=False,next=nxt,review=b.review_due(),budget=b.reconcile()))
    print(dict(all_frames=data['total_frames'],failed_frames=sum(v['failed_frames'] for v in data['rows']),all_required_pass=data['all_required_pass'],next=nxt,quality_goal_completed=False),flush=True)
if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['register','observe']);a=p.parse_args();register() if a.stage=='register' else run()
