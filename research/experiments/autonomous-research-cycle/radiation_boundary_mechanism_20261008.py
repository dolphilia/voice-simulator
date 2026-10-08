"""一次の因果的円管放射反射を独自Cで離散化し、独立数値計算と照合する。"""
import argparse,ast,hashlib,json,os,subprocess,sys,urllib.request
from pathlib import Path
from contextlib import contextmanager
from budget import ROOT,read,digest,encode
from long_horizon_budget import LongHorizonBudget as Budget
REPO=ROOT.parents[2]
HERE=ROOT/'campaigns/nas-radiation-boundary-mechanism-20261008-v1'
NAME='radiation-boundary-mechanism-v1'
PREV=ROOT/'campaigns/nas-waveguide-vowel-comparison-20261008-v1'
PYTHON=REPO/'research/experiments/autonomous-speech-synthesis/.venv-eval/bin/python'
PDFPY='/Users/dolphilia/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3'
POPPLER='/Users/dolphilia/.cache/codex-runtimes/codex-primary-runtime/dependencies/bin/override/pdftoppm'
COEFFICIENTS={'unflanged':[.167,1.393,.457],'flanged':[.182,1.825,.649]}
URLS={'silva-2008.pdf':'https://arxiv.org/pdf/0811.3625','silva-2008.html':'https://arxiv.org/html/0811.3625v1'}

C_SOURCE='''/* 論文の式から独自に実装。コード転載なし。固定半径の因果的反射だけ。 */
#include <math.h>
#include <stddef.h>
int radiation(const double*x,size_t n,double fs,double radius,int flanged,const double*initial,double*last,double*y,double*p,double*u){
 if(!x||!initial||!last||!y||!p||!u||n<1||n>96000||!isfinite(fs)||!isfinite(radius)||fs<16000||fs>96000||radius<.003||radius>.03||(flanged!=0&&flanged!=1))return 0;
 for(size_t i=0;i<n;i++)if(!isfinite(x[i]))return 0;
 for(size_t i=0;i<4;i++)if(!isfinite(initial[i]))return 0;
 double n1=flanged?.182:.167,d1=flanged?1.825:1.393,d2=flanged?.649:.457;
 double q=2.*fs*radius/343.,den=1.+d1*q+d2*q*q;
 double b0=-(1.+n1*q)/den,b1=-2./den,b2=-(1.-n1*q)/den;
 double a1=(2.-2.*d2*q*q)/den,a2=(1.-d1*q+d2*q*q)/den;
 double x1=initial[0],x2=initial[1],y1=initial[2],y2=initial[3];
 for(size_t i=0;i<n;i++){
  double z=b0*x[i]+b1*x1+b2*x2-a1*y1-a2*y2;
  y[i]=z;p[i]=x[i]+z;u[i]=x[i]-z;
  x2=x1;x1=x[i];y2=y1;y1=z;
 }
 last[0]=x1;last[1]=x2;last[2]=y1;last[3]=y2;return 1;
}
'''

MODULE='''"""固定半径の反射、唇位置pressure/flow。遠方放射音の資格ではない。"""
import ctypes as C,json,hashlib,math
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parent
COEFFICIENTS=json.loads((HERE/'coefficients.json').read_text());P=C.POINTER(C.c_double)
_lib=C.CDLL(str(HERE/'radiation.dylib'));_fn=_lib.radiation
_fn.restype=C.c_int;_fn.argtypes=[P,C.c_size_t,C.c_double,C.c_double,C.c_int,P,P,P,P,P]
def ah(x):return hashlib.sha256(np.asarray(x,dtype='<f8').tobytes()).hexdigest()
def coefficients(fs,radius,flanged):
 if type(flanged) is not bool or not math.isfinite(fs) or not 16000<=fs<=96000 or not math.isfinite(radius) or not .003<=radius<=.03:raise ValueError('登録した有限Fs/半径/終端が必要')
 n1,d1,d2=COEFFICIENTS['flanged' if flanged else 'unflanged'];q=2.*fs*radius/343.;d=1+d1*q+d2*q*q
 return np.array([-(1+n1*q),-2.,-(1-n1*q)])/d,np.array([1.,(2-2*d2*q*q)/d,(1-d1*q+d2*q*q)/d])
def block(x,fs,radius,flanged,state=None):
 coefficients(fs,radius,flanged);x=np.ascontiguousarray(x,dtype=np.float64);state=np.zeros(4) if state is None else np.ascontiguousarray(state,dtype=np.float64)
 if x.ndim!=1 or not 1<=len(x)<=96000 or state.shape!=(4,):raise ValueError('標本/状態寸法が登録範囲外')
 before=(ah(x),ah(state));y=np.empty_like(x);p=np.empty_like(x);u=np.empty_like(x);last=np.empty_like(state)
 if not _fn(x.ctypes.data_as(P),len(x),fs,radius,int(flanged),state.ctypes.data_as(P),last.ctypes.data_as(P),y.ctypes.data_as(P),p.ctypes.data_as(P),u.ctypes.data_as(P)):raise ValueError('非有限入力を拒否')
 assert before==(ah(x),ah(state));return y,p,u,last
'''

WORKER='''"""SciPyの別式/状態空間と反射の独自Cを全条件で照合する。"""
import sys,json,math
from pathlib import Path
import numpy as np
from scipy import signal
here=Path(sys.argv[1]);sys.path.insert(0,str(here/'runtime-bundle'))
from radiation import block,coefficients,COEFFICIENTS,ah,_fn,P
import ctypes as C
rows=[];calls=0;T=8192;rng=np.random.default_rng(710810)
for fs in (34300.,48000.):
 for radius in (.007,.008,.012,.016):
  for flanged in (False,True):
   n1,d1,d2=COEFFICIENTS['flanged' if flanged else 'unflanged'];tau=radius/343.
   b,a=coefficients(fs,radius,flanged);sb,sa=signal.bilinear([-n1*tau,-1.],[d2*tau*tau,d1*tau,1.],fs)
   coefficient_error=max(float(np.max(abs(sb-b))),float(np.max(abs(sa-a))));assert coefficient_error<=1e-14
   poles=np.roots(a);assert max(abs(poles))<1.
   delta=d1*d1-2*d2-n1*n1;assert delta>0 and d1>0 and d2>0
   impulse=np.zeros(T);impulse[0]=1.;noise=rng.normal(0,.1,T)
   for name,x in [('impulse',impulse),('noise',noise)]:
    y,p,u,last=block(x,fs,radius,flanged);calls+=1
    ref=signal.lfilter(sb,sa,x);calls+=1;error=float(np.max(abs(y-ref)));assert error<=3e-14
    assert np.array_equal(p,x+y) and np.array_equal(u,x-y)
    passive=float(np.max(np.cumsum(y*y)-np.cumsum(x*x)));assert passive<=1e-10
    prefix=x.copy();prefix[T//2:]=rng.normal(0,.1,T//2);future=block(prefix,fs,radius,flanged)[0];calls+=1;assert future[:T//2].tobytes()==y[:T//2].tobytes()
    state=np.zeros(4);pieces=[];start=0;k=0
    while start<T:
     stop=min(T,start+(2048,4096,8192)[k%3]);z,_,_,state=block(x[start:stop],fs,radius,flanged,state);pieces.append(z);start=stop;k+=1;calls+=1
    assert np.concatenate(pieces).tobytes()==y.tobytes() and state.tobytes()==last.tobytes()
    if name=='impulse':
     spectrum=np.fft.rfft(y);omega=2*np.pi*np.arange(1,T//2)/T;s=2j*fs*tau*np.tan(omega/2)
     expected=-(1+n1*s)/(1+d1*s+d2*s*s);frequency_error=float(np.max(abs(spectrum[1:-1]-expected)));assert frequency_error<=3e-12
     assert abs(spectrum[0]+1.)<=1e-12 and abs(spectrum[-1])<=1e-12 and max(abs(expected))<=1+1e-12
     low=1e-4;R=-(1+n1*1j*low)/(1+d1*1j*low+d2*(1j*low)**2)
     eta=(d1-n1)/2.;beta=delta/2.;assert abs(-np.angle(-R)/(2*low)-eta)<=1e-7
     rows.append(dict(fs=fs,radius_m=radius,flanged=flanged,coefficient_error=coefficient_error,max_pole_radius=float(max(abs(poles))),independent_wave_error=error,frequency_error=frequency_error,passivity_margin=passive,eta_from_rounded_table=eta,beta_from_rounded_table=beta,
         ka_paper_8percent_claim_at_most=2.,maximum_warped_ka_8khz=float(2*fs*tau*np.tan(np.pi*8000/fs)),physical_frequency_warp_qualified_as_exact=False,passed=True))
invalid=0
for x,fs,radius,flanged,state in [(np.zeros(0),34300.,.007,False,None),(np.zeros((2,2)),34300.,.007,False,None),(np.array([np.nan]),34300.,.007,False,None),(np.array([np.inf]),34300.,.007,False,None),(np.zeros(4),np.nan,.007,False,None),(np.zeros(4),1000.,.007,False,None),(np.zeros(4),34300.,0.,False,None),(np.zeros(4),34300.,.1,False,None),(np.zeros(4),34300.,.007,2,None),(np.zeros(4),34300.,.007,False,np.zeros(3)),(np.zeros(4),34300.,.007,False,np.array([0.,0.,np.nan,0.]))]:
 try:block(x,fs,radius,flanged,state)
 except ValueError:invalid+=1
 else:raise AssertionError('不正入力を受理')
assert invalid==11
zero=np.zeros(4);out=np.full(4,123.);state=np.zeros(4);last=np.full(4,321.)
assert not _fn(None,4,34300.,.007,0,state.ctypes.data_as(P),last.ctypes.data_as(P),out.ctypes.data_as(P),out.ctypes.data_as(P),out.ctypes.data_as(P)) and np.all(out==123.) and np.all(last==321.)
assert len(rows)==16 and calls<=224
print(json.dumps(dict(rows=rows,passed=True,actual_render_calls=calls,invalid_cases=invalid+1,reflection_state_partition_and_future_prefix_exact=True,pressure_and_normalized_flow_identity_exact=True,fixed_radius_only=True,far_field_or_dynamic_lip_or_speech_qualified=False)))
'''

@contextmanager
def job(b,kind,label,count=1,size=0,seconds=600):
    j=b.reserve(NAME,kind,label,count,size,expected_seconds=seconds)
    try:yield j
    except BaseException as e:b.finish(j,repr(e));raise
    else:b.finish(j)
def execute(cmd,env,timeout=600):
    env=dict(env);env.update(OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',VECLIB_MAXIMUM_THREADS='1')
    return subprocess.run(cmd,env=env,check=True,capture_output=True,text=True,timeout=timeout)
def verify(name):
    c=read(HERE/name);assert digest(Path(__file__))==c['controller_sha256']
    for p,h in c['files'].items():assert digest(HERE/p)==h,p
def register():
    b=Budget();b.recover();assert not b.snapshot()['jobs'] and not b.review_due()['due'] and read(PREV/'aggregate-summary.json')['quality_goal_completed']==False
    for src in (MODULE,WORKER):ast.parse(src)
    limits=dict(seconds=7200,bytes=300000000,write_bytes=800000000,setup=20,audit=20,render=600,dsp=2000,ai=0,teacher=0,train=0,inverse=0,download=2000000)
    reg=dict(campaign=NAME,question='円管放射の因果的Padé反射を、固定半径の離散時間境界として独立に再現し安定/受動/因果/状態継承を満たせるか。',
      primary=dict(title='Approximation formulae for the acoustic radiation impedance of a cylindrical pipe',authors=['F. Silva','Ph. Guillemain','J. Kergomard','B. Mallaroni','A. N. Norris'],arxiv='0811.3625v1',journal='J. Sound Vib. 322(1-2),255-263(2009)',DOI='10.1016/j.jsv.2008.11.008',URLs=URLS,license='arXiv perpetual non-exclusive。原PDF/図/本文のGit再配布なし。式/数値の引用から独自C/Pythonを実装、原コード転載なし。'),
      factor='一次式16/Table1の丸め値を固定。exp(+jwt)へ共役変換しR(s)=-(1+n1*tau*s)/(1+d1*tau*s+d2*tau^2*s^2),tau=a/c。s=2Fs(1-z^-1)/(1+z^-1)のbilinearを明示展開。',
      coefficients=COEFFICIENTS,rounding='eta=(d1-n1)/2、beta=(d1^2-n1^2-2d2)/2の実値を記録し、論文の低周波値との完全一致を主張しない。出力後の係数補正なし。',
      fixtures=dict(fs=[34300,48000],radii_m=[.007,.008,.012,.016],terminations=['unflanged','flanged'],signals=['impulse','fixed-seed Gaussian noise'],samples=8192,seed=710810),
      gates=dict(coefficients_vs_SciPy_bilinear=1e-14,wave_vs_independent_lfilter=3e-14,complex_response_vs_analytic_warped_s=3e-12,stable_poles_abs_less_than=1.,analytic_bounded_real_delta_positive=True,cumulative_reflected_energy_excess_at_most=1e-10,partition_and_future_input_prefix_bytes_exact=True,pressure_equals_incident_plus_reflected=True,normalized_flow_equals_incident_minus_reflected=True,invalid_rejected=12),
      scope='固定半径/円管の近似反射のみ。Ka≤2で論文の近似誤差8%記述があり、bilinear周波数warpingとそれを超える帯域を区別。動く唇/全声道/人体頭部/遠方観測/日本語知覚/内容は未資格。',
      estimates=dict(render=224,dsp=512,source_and_block_calls_included=True,download=2000000,temporary_peak=24000000,temporary_write=48000000,closeout_Git_included=True,RAM_gb=8),
      limits=limits,controller_sha256=digest(Path(__file__)),all_prior_frozen_routes_kept=True,perceptual_qualification=False,protected_confirmation_opened=False,quality_goal_completed=False,
      next='固定放射機構を通過した範囲で体積流量/唇flow観測と声道への結合を別契約で検証。動的半径や遠方音を無検証で資格移転しない。同じ語句のgain/径/終端/源/時刻で救済しない。')
    b.start_campaign(NAME,str(HERE.relative_to(ROOT)),limits,hashlib.sha256(encode(reg)).hexdigest())
    with job(b,'setup','因果的放射反射の一次式/丸め値/独立全条件と費用を出力前固定',size=3000000) as j:
        b.save(HERE/'registration.json',reg,j);b.save(HERE/'coefficients.json',COEFFICIENTS,j)
        for n,s in [('radiation.c',C_SOURCE),('radiation.py',MODULE),('worker.py',WORKER)]:b.write(HERE/n,s.encode(),j)
        b.save(HERE/'source-contract.json',dict(files={str(p.relative_to(HERE)):digest(p) for p in HERE.rglob('*') if p.is_file()},controller_sha256=digest(Path(__file__)),no_scientific_output_yet=True),j)
    b.save(ROOT/'progress-0125.json',dict(active_campaign=NAME,next='登録push→一次PDF/表の目視・独自C固定→独立数値/状態/全分母封印',new_waveforms=0,quality_goal_completed=False,budget=b.reconcile()));print('固定放射境界を出力前登録',flush=True)
def prepare():
    b=Budget();b.recover();assert not b.snapshot()['jobs'];verify('source-contract.json')
    with job(b,'download','一次arXiv PDF/HTMLの有限取得',2000000,4000000,120) as j:
        for name,url in URLS.items():
            with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'VoiceSimulatorResearch/1.0'}),timeout=45) as f:data=f.read(1000001)
            assert len(data)<=1000000 and (name.endswith('.html') or data.startswith(b'%PDF'));b.write_data(HERE/'upstream'/name,data,j)
        b.save(HERE/'upstream-receipt.json',dict(rows=[dict(name=n,url=u,sha256=digest(HERE/'upstream'/n),bytes=(HERE/'upstream'/n).stat().st_size) for n,u in URLS.items()],charged_download=2000000,no_audio_models_or_reference_data=True),j)
    with job(b,'setup','一次表抽出/原頁目視準備と独自放射C build',size=110000000,seconds=600) as j:
        bundle=HERE/'runtime-bundle';b.write(bundle/'radiation.py',MODULE.encode(),j);b.save(bundle/'coefficients.json',COEFFICIENTS,j)
        with b.workspace(j,'一次PDF表の抽出と目視頁生成',24000000,48000000) as (work,env):
            code="from pypdf import PdfReader;import sys,json; r=PdfReader(sys.argv[1]);t=r.pages[11].extract_text();values=['0.167','1.393','0.457','0.182','1.825','0.649'];assert all(v in t for v in values);print(json.dumps(dict(page=12,all_six_coefficients_found=True,pages=len(r.pages))))"
            value=json.loads(execute([PDFPY,'-B','-c',code,str(HERE/'upstream/silva-2008.pdf')],env,120).stdout);execute([POPPLER,'-f','12','-singlefile','-r','120','-png',str(HERE/'upstream/silva-2008.pdf'),str(work/'table')],env,120);b.write_data(HERE/'source-table-page.png',(work/'table.png').read_bytes(),j)
            b.save(HERE/'table-extraction-audit.json',value,j)
        with b.workspace(j,'独自放射C build cache',16000000,32000000) as (work,env):
            env['CLANG_MODULE_CACHE_PATH']=str(work/'clang-modules');tool='/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/clang';sdk='/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk';cmd=[tool,'-dynamiclib','-O2','-fno-modules','-isysroot',sdk,str(HERE/'radiation.c'),'-o',str(bundle/'radiation.dylib')]
            with b.external_output(bundle/'radiation.dylib',100000,j):out=execute(cmd,env,120)
        b.save(HERE/'build-audit.json',dict(command=cmd,stderr=out.stderr,source_sha256=digest(HERE/'radiation.c'),binary_sha256=digest(bundle/'radiation.dylib'),temporary_removed=True),j)
        b.save(bundle/'manifest.json',dict(files={str(p.relative_to(bundle)):digest(p) for p in bundle.rglob('*') if p.is_file()},HMM=False,neural=False,recording=False,utterance_lookup=False),j)
        b.save(HERE/'execution-contract-before-visual.json',dict(files={str(p.relative_to(HERE)):digest(p) for p in HERE.rglob('*') if p.is_file()},controller_sha256=digest(Path(__file__)),fixed_before_science=True),j)
    print('原12頁のTable1を目視確認してからvisualを実行',flush=True)
def visual():
    b=Budget();assert not b.snapshot()['jobs'];verify('execution-contract-before-visual.json')
    with job(b,'audit','一次Table1の全6丸め係数を原頁で目視照合',size=1000000) as j:
        b.save(HERE/'table-visual-audit.json',dict(source_page=12,source_table=1,all_six_values_visually_checked=True,coefficients=COEFFICIENTS,source_image_sha256=digest(HERE/'source-table-page.png'),source_PDF_sha256=digest(HERE/'upstream/silva-2008.pdf'),no_choice_after_output=True),j)
        b.save(HERE/'execution-contract.json',dict(files={str(p.relative_to(HERE)):digest(p) for p in HERE.rglob('*') if p.is_file()},controller_sha256=digest(Path(__file__)),fixed_before_science=True),j)
def fixture():
    b=Budget();b.recover();assert not b.snapshot()['jobs'];verify('execution-contract.json')
    with job(b,'render','放射反射の全入力/独立参照/前半/状態block呼出し',224,90000000,1200) as r:
        with job(b,'dsp','反射/安定/受動/複素応答/不正入力の全独立照合',512,2000000,1200) as d:
            with b.workspace(r,'放射機構の科学依存初期化',16000000,32000000) as (_,env):
                try:out=execute([str(PYTHON),'-B',str(HERE/'worker.py'),str(HERE)],env,1000)
                except subprocess.CalledProcessError as e:b.save(HERE/'child-failure.json',dict(returncode=e.returncode,stdout=e.stdout,stderr=e.stderr),d);raise
            value=json.loads(out.stdout);assert value['passed'];b.save(HERE/'fixture-audit.json',value,d)
    with job(b,'audit','固定放射境界の限定資格/全分母/費用/一時回収を封印',size=2000000) as j:
        verify('execution-contract.json');result=dict(read(HERE/'fixture-audit.json'),perceptual_qualification=False,protected_confirmation_opened=False,quality_goal_completed=False,next=read(HERE/'registration.json')['next']);b.save(HERE/'aggregate-summary.json',result,j)
        lines=['# 固定半径の因果的円管放射境界','','[Silva et al. (2008/2009)](https://arxiv.org/abs/0811.3625)の式16/Table1の6丸め値を出力前固定。独自Cでbilinear離散化した反射を、SciPy別展開・lfilter・解析複素式と照合した。原PDF/本文/原頁画像は指定外部へ保持し、Git再配布しない。','',f'2Fs×4半径×2終端の全16条件。独立wave誤差最大 {max(x["independent_wave_error"] for x in value["rows"]):.3g}、解析warped複素応答誤差最大 {max(x["frequency_error"] for x in value["rows"]):.3g}。全poleは単位円内。解析delta>0と累積反射エネルギー、区切り/因果前半のbyte一致、pressure/正規化flowの恒等式、不正12件拒否を通過。','',
          'Tableの丸めで低周波eta/betaは原小数の理想値とわずかに異なる。値を出力後補正しない。物理周波数のbilinear warpingを記録し、Ka≤2という原近似範囲を全8kHzや実人体の資格へ拡張しない。','',
          '固定半径の反射だけの資格。遠方放射音/動く唇/全声道/日本語音声の工学・内容・知覚を合格にしていない。224render/512DSPは内部呼出し・独立参照を含む。失敗/再試行があれば台帳に追加保持。','',result['next'],'','全旧契約・封印・不採択を保持。日本語知覚資格なし・P5未開封・品質未達。','']
        b.write(HERE/'report.md','\n'.join(lines).encode(),j);s=b.snapshot();c=s['campaigns'][NAME];tmp=[x for x in s['temporary_work'].values() if x['campaign']==NAME];assert all(x['status']=='removed' and not os.path.lexists(x['path']) for x in tmp)
        b.save(HERE/'cost-audit.json',dict(counts=c['counts'],seconds=s['seconds']-c['start_seconds'],write_bytes=s['write_bytes']-c['start_write_bytes'],temporary_owned=len(tmp),all_owned_temporary_absent=True),j)
        b.save(HERE/'artifact-seal.json',dict(files={str(p.relative_to(REPO)):digest(p) for p in HERE.rglob('*') if p.is_file()},path_base='repository',experiment_completed=True,quality_goal_completed=False,protected_confirmation_opened=False),j)
    b.close_campaign(NAME)
    with b.locked():
        s=b._load();s['continuation_checkpoint'].update(id='radiation-boundary-mechanism-completed',active_campaign=None,next=result['next'],git_save_pending=True);b._write_state(s)
    b.save(ROOT/'progress-0126.json',dict(latest_completed=NAME,next=result['next'],review=b.review_due(),quality_goal_completed=False,budget=b.reconcile()));print(dict(passed=True,conditions=16,quality_goal_completed=False),flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['register','prepare','visual','fixture']);a=p.parse_args();globals()[a.stage]()
