"""LF声門流微分の独自実装を、面積・連続性・独立積分で検証する。LF0列変更ではない。"""
import ast,hashlib,json,os,subprocess,urllib.request
from pathlib import Path
from budget import ROOT,read,digest,encode
from long_horizon_budget import LongHorizonBudget as Budget
REPO=ROOT.parents[2]
HERE=ROOT/'campaigns/nas-lf-source-mechanism-20261008-v1'
NAME='lf-source-mechanism-v1'
PYTHON=REPO/'research/experiments/autonomous-speech-synthesis/.venv-eval/bin/python'
PAPER='https://www.speech.kth.se/qpsr/1985/1985_26_4_001-013.pdf'

C_SOURCE=r'''/* 独自LF周期関数。係数は固定時間比とゼロ面積の式から求め、波形からfitしない。 */
#include <math.h>
#include <stddef.h>
int lf_evaluate(const double *phase,double *out,size_t n,const double *c,size_t cols) {
 if(!phase||!out||!c||!n||cols!=7)return 0;
 for(size_t j=0;j<7;j++)if(!isfinite(c[j]))return 0;
 const double tp=c[0],te=c[1],ta=c[2],ep=c[3],a=c[4],e0=c[5],scale=c[6];
 if(!(0.<tp&&tp<te&&te<1.&&ta>0.&&ta<1.-te&&ep>0.&&a>0.&&e0>0.&&scale>0.))return 0;
 for(size_t i=0;i<n;i++)if(!isfinite(phase[i])||phase[i]<0.||phase[i]>1.)return 0;
 const double w=3.14159265358979323846264338327950288/tp,end=exp(-ep*(1.-te));
 for(size_t i=0;i<n;i++){
  double t=phase[i];
  double g=t<=te?e0*exp(a*t)*sin(w*t):-(exp(-ep*(t-te))-end)/(ep*ta);
  out[i]=g*scale;if(!isfinite(out[i]))return 0;
 }
 return 1;
}
'''

MODULE=r'''"""固定Tp=.4/Te=.6/Ta=.05/Ee=1のLF。連続時間の二乗積分で源の尺度を固定する。"""
import math,ctypes as C
from pathlib import Path
import numpy as np
TP=.4;TE=.6;TA=.05;EE=1.
def bisect(fn,lo,hi):
 f=fn(lo);h=fn(hi)
 if not math.isfinite(f+h) or f*h>=0:raise ValueError('正根の事前区間が成立しない')
 for _ in range(160):
  mid=(lo+hi)/2.;v=fn(mid)
  if v==0:return mid
  if f*v>0:lo=mid;f=v
  else:hi=mid
 return (lo+hi)/2.
def coefficients():
 length=1.-TE;w=math.pi/TP
 ep=bisect(lambda e:-math.expm1(-e*length)-e*TA,1e-8,1./TA)
 end=math.exp(-ep*length)
 returning=-((-math.expm1(-ep*length))/ep-length*end)/(ep*TA)
 def opened(a):
  e0=-EE/(math.exp(a*TE)*math.sin(w*TE))
  return e0*(math.exp(a*TE)*(a*math.sin(w*TE)-w*math.cos(w*TE))+w)/(a*a+w*w)
 alpha=bisect(lambda a:opened(a)+returning,0.,10.)
 e0=-EE/(math.exp(alpha*TE)*math.sin(w*TE))
 z=complex(2.*alpha,2.*w)
 first=(math.expm1(2.*alpha*TE)/(2.*alpha)-((__import__('cmath').exp(z*TE)-1.)/z).real)*e0*e0/2.
 second=((-math.expm1(-2.*ep*length))/(2.*ep)-2.*end*(-math.expm1(-ep*length))/ep+end*end*length)/(ep*TA)**2
 power=first+second
 if not power>0 or not math.isfinite(power):raise ValueError('LF周期powerが正の有限値でない')
 return np.array([TP,TE,TA,ep,alpha,e0,1./math.sqrt(power)]),dict(return_equation_residual=-math.expm1(-ep*length)-ep*TA,
  open_integral=opened(alpha),return_integral=returning,net_integral=opened(alpha)+returning,continuous_power=power,source_RMS_normalization='連続周期の解析二乗積分、全入力で固定。波形別gainではない。')
def scalar(t,c):
 tp,te,ta,ep,a,e0,scale=map(float,c)
 if not math.isfinite(t) or not 0.<=t<=1.:raise ValueError('phaseが有限0..1でない')
 return scale*(e0*math.exp(a*t)*math.sin(math.pi*t/tp) if t<=te else -(math.exp(-ep*(t-te))-math.exp(-ep*(1.-te)))/(ep*ta))
_lib=C.CDLL(str(Path(__file__).resolve().parent/'lf_source.dylib'));_fn=_lib.lf_evaluate
P=C.POINTER(C.c_double);_fn.restype=C.c_int;_fn.argtypes=[P,P,C.c_size_t,P,C.c_size_t]
def evaluate(phase,c):
 p=np.ascontiguousarray(phase,dtype=np.float64);v=np.ascontiguousarray(c,dtype=np.float64)
 if p.ndim!=1 or not len(p) or v.shape!=(7,):raise ValueError('phase列と7係数が必要')
 before=(p.tobytes(),v.tobytes());out=np.empty_like(p)
 if not _fn(p.ctypes.data_as(P),out.ctypes.data_as(P),len(p),v.ctypes.data_as(P),len(v)):raise ValueError('LF入力または有限出力を内部検査が拒否')
 assert before==(p.tobytes(),v.tobytes());return out
def tests(c):
 assert not _fn(None,None,0,None,0)
 for p in (np.array([np.nan]),np.array([np.inf]),np.array([-.01]),np.array([1.01])):
  try:evaluate(p,c)
  except ValueError:pass
  else:raise AssertionError('不正phaseを拒否しない')
 return dict(null_and_four_invalid_phases_rejected=True)
'''

WORKER=r'''"""解析積分を独立quadで確認し、固定phaseのC/Python二波形を全件照合する。"""
import sys,json,os,tempfile,hashlib,math
from pathlib import Path
here=Path(__file__).resolve().parent;sys.path.insert(0,str(here/'runtime-bundle'))
assert Path(tempfile.gettempdir()).resolve()==Path(os.environ['TMPDIR']).resolve()
import numpy as np
from scipy import integrate
from lf_source import coefficients,scalar,evaluate,tests,TP,TE,TA,EE
c,proof=coefficients();tests(c);tp,te,ta,ep,alpha,e0,scale=c
assert max(abs(proof['return_equation_residual']),abs(proof['net_integral']))<=1e-12
mean=sum(integrate.quad(lambda t:scalar(t,c),a,b,epsabs=1e-13,epsrel=1e-13)[0] for a,b in ((0.,te),(te,1.)))
power=sum(integrate.quad(lambda t:scalar(t,c)**2,a,b,epsabs=1e-13,epsrel=1e-13)[0] for a,b in ((0.,te),(te,1.)))
assert abs(mean)<=1e-12 and abs(power-1.)<=1e-12
left=scale*e0*math.exp(alpha*te)*math.sin(math.pi*te/tp)
right=-scale*(1.-math.exp(-ep*(1.-te)))/(ep*ta)
assert abs(left-right)<=1e-12 and abs(left+scale*EE)<=1e-12
assert abs(scalar(0.,c))<=1e-12 and abs(scalar(1.,c))<=1e-12
grid=np.unique(np.r_[np.linspace(0.,1.,4097),tp,te]);x=evaluate(grid,c);ref=np.array([scalar(float(t),c) for t in grid])
grid_error=float(np.max(np.abs(x-ref)));assert grid_error<=1e-12
flow=[]
for t in np.linspace(0.,1.,17):
 v=sum(integrate.quad(lambda q:scalar(q,c),a,b,epsabs=1e-13,epsrel=1e-13)[0] for a,b in ((0.,min(t,te)),(te,max(te,t))))
 flow.append(dict(phase=float(t),normalized_flow=v));assert v>=-1e-12
rows=[]
for fs in (24000,48000):
 for frequency in (80.,110.,220.,280.,400.):
  for initial in (.125,.731):
   phase=np.mod(initial+np.arange(fs//2)*frequency/fs,1.);a=evaluate(phase,c);b=np.array([scalar(float(t),c) for t in phase])
   error=float(np.max(np.abs(a-b)));assert error<=1e-12
   # 同じ入力phaseの前半を別評価して完全一致を確認する。時間変動の声道安定ではない。
   prefix=evaluate(phase[:len(phase)//2],c);assert np.array_equal(a[:len(prefix)],prefix)
   rows.append(dict(fs=fs,frequency=frequency,initial_phase=initial,samples=len(a),C_Python_max_abs_error=error,C_prefix_exact=True,finite_wave=bool(np.isfinite(a).all()),
    wave_sha256=hashlib.sha256(a.astype('<f8').tobytes()).hexdigest(),passed=True))
fundamental=complex(*[sum(integrate.quad(lambda t:scalar(t,c)*fn(2*math.pi*t),a,b,epsabs=1e-13,epsrel=1e-13)[0] for a,b in ((0.,te),(te,1.))) for fn in (math.cos,lambda x:-math.sin(x))])
assert abs(fundamental)>1e-6
assert len(rows)==20
print(json.dumps(dict(passed=True,coefficients=c.tolist(),proof=proof,independent_quad_mean=mean,independent_quad_power=power,closing_continuity_error=abs(left-right),dense_grid_error=grid_error,
 flow_grid=flow,fundamental_coefficient=[fundamental.real,fundamental.imag],rows=rows,render=42,dsp=128,
 spectrum_and_root_definition_only=True,antialiasing_claimed=False,biological_voice_or_perceived_pitch_truth=False,HTS_coupling_qualified=False,quality_certified=False),allow_nan=False))
'''

def verify(contract):
    assert digest(Path(__file__))==contract['controller_sha256']
    for n,h in contract['files'].items():assert digest(HERE/n)==h,n

def register():
    b=Budget();b.recover();assert not b.snapshot()['jobs'] and not b.review_due()['due']
    previous=ROOT/'campaigns/nas-hts-tohoku-comparison-20261008-v1';assert not read(previous/'aggregate-summary.json')['research_protection_gates']['tohoku']
    ast.parse(MODULE);ast.parse(WORKER)
    limits=dict(seconds=7200,bytes=200000000,write_bytes=600000000,setup=12,audit=12,render=126,dsp=384,ai=0,teacher=0,train=0,inverse=0,download=3000000)
    reg=dict(campaign=NAME,question='LF声門流微分の固定周期関数を、ゼロ面積/有限帰還/連続性/周期powerの定義と独立積分で非ニューラル実装できるか。',
        factor='正規化T0=1、Tp=.4/Te=.6/Ta=.05/Ee=1固定。epsilon*Ta=1-exp(-epsilon*(1-Te))の正根、開相と帰還相の面積和0からalphaを求める。RMSは連続解析二乗積分で固定。',
        meaning='LFは声門流微分モデルで、LF0基本周波数列の縮小/平坦化とは別。Rosenberg/有限差分の同係数救済ではない。生物測定による最適パラメータや日本語自然声と主張しない。',
        formulas='開相E0*exp(alpha*t)*sin(pi*t/Tp)、帰還相-[exp(-epsilon*(t-Te))-exp(-epsilon*(1-Te))]/(epsilon*Ta)。閉相peak=-Ee、周期端0、面積和0。',
        controls='同一固定phaseでC/独立Pythonを比較。各20人工条件+密phase gridの2実装42波形。声道/HTS/録音/教師/保存波形を使わない。入力で係数を選別しない。',
        fixture=dict(fs=[24000,48000],F0=[80.,110.,220.,280.,400.],phase=[.125,.731],seconds=.5,dense_phase_points=4097,all_20_required=True),
        thresholds=dict(root_area_continuity_and_endpoints_at_most=1e-12,independent_quad_mean_and_power_at_most=1e-12,C_Python_absolute_error_at_most=1e-12,C_prefix_exact=True,
            nonnegative_flow_grid_tolerance=1e-12,nonzero_fundamental_coefficient_above=1e-6,invalid_phase_rejected=True),
        scope='固定一形状、固定phase入力の周期関数だけ。時間変動の源/声道、HTS混合励振/LPFへの結合、aliasing、自然さ、知覚pitchを資格付けしない。',
        estimates=dict(render=42,dsp=128,dsp_breakdown='全20条件×5のphase/数値/有限/入力保持/前半照合と根/積分/連続/flow/Fourier等28監査',
            download_conservatively=1000000,maximum_seconds=6000,temporary_peak=16000000,temporary_write=32000000,RAM_gb=8),limits=limits,
        sources=dict(paper=PAPER,reference='Fant, Liljencrants & Lin (1985), STL-QPSR 26(4), 1–13。一次式を読んだ独自C/Python実装。Pink TromboneやGPL派生コードを取得/コピーしない。',
            previous_seal_sha256=digest(previous/'artifact-seal.json')),
        c_sha256=hashlib.sha256(C_SOURCE.encode()).hexdigest(),module_sha256=hashlib.sha256(MODULE.encode()).hexdigest(),worker_sha256=hashlib.sha256(WORKER.encode()).hexdigest(),controller_sha256=digest(Path(__file__)),
        next='科学30件の定期レビュー後、通過した限定LFを原HTS励振へ結合する独立機構を別登録。未通過を同係数/閾値で救済しない。',
        old_missing_and_all_frozen_routes_retained=True,perceptual_qualification=False,protected_confirmation_opened=False,quality_goal_completed=False)
    b.start_campaign(NAME,str(HERE.relative_to(ROOT)),limits,hashlib.sha256(encode(reg)).hexdigest())
    with b.job(NAME,'setup','LF声門流微分の固定形状・一次式・全機構費用を出力前登録',reserve_bytes=2000000) as j:
        b.save(HERE/'registration.json',reg,j);b.write(HERE/'lf_source.c',C_SOURCE.encode(),j);b.write(HERE/'lf_source.py',MODULE.encode(),j);b.write(HERE/'worker.py',WORKER.encode(),j)
        b.save(HERE/'source-contract.json',dict(files={str(p.relative_to(HERE)):digest(p) for p in HERE.rglob('*') if p.is_file()},controller_sha256=digest(Path(__file__)),no_scientific_output_yet=True),j)
    b.save(ROOT/'progress-0102.json',dict(active_campaign=NAME,new_waveforms=0,next='登録push→一次論文hash取得→LF primitive build→独立積分と全20人工条件',quality_goal_completed=False,budget=b.reconcile()))
    print(dict(registered=True,new_waveforms=0),flush=True)

def prepare():
    b=Budget();b.recover();assert not b.snapshot()['jobs'];verify(read(HERE/'source-contract.json'))
    with b.job(NAME,'download','公開KTH原論文の固定保存とhash記録',1000000,3000000) as j:
        with urllib.request.urlopen(urllib.request.Request(PAPER,headers={'User-Agent':'VoiceSimulatorResearch'}),timeout=45) as response:data=response.read(1000001);url=str(response.url)
        assert len(data)<=1000000 and data.startswith(b'%PDF')
        b.write_data(HERE/'upstream/lf-paper-1985.pdf',data,j);b.save(HERE/'primary-source-audit.json',dict(url=PAPER,resolved_url=url,bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),conservative_charged_bytes=1000000,
            unused_reservations_not_returned=True,source_code_downloaded_or_copied=False,formula_implementation_authored_independently=True),j)
    with b.job(NAME,'setup','独自LF C primitiveを外部専用cacheでbuild',reserve_bytes=30000000) as j:
        bundle=HERE/'runtime-bundle';b.write(bundle/'lf_source.py',MODULE.encode(),j)
        with b.workspace(j,'LF primitive build中間物とcache',16000000,32000000) as (work,env):
            env['CLANG_MODULE_CACHE_PATH']=str(work/'clang-modules');tool='/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/clang';sdk='/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk'
            cmd=[tool,'-dynamiclib','-O2','-fno-modules','-isysroot',sdk,str(HERE/'lf_source.c'),'-o',str(bundle/'lf_source.dylib')]
            with b.external_output(bundle/'lf_source.dylib',100000,j):out=subprocess.run(cmd,env=env,check=True,capture_output=True,text=True,timeout=120)
        b.save(HERE/'build-audit.json',dict(command=cmd,stderr=out.stderr,source_sha256=digest(HERE/'lf_source.c'),binary_sha256=digest(bundle/'lf_source.dylib'),temporary_removed=True),j)
        b.save(bundle/'manifest.json',dict(files={str(p.relative_to(bundle)):digest(p) for p in bundle.rglob('*') if p.is_file()},no_neural_inference=True),j)
        b.save(HERE/'execution-contract.json',dict(files={str(p.relative_to(HERE)):digest(p) for p in HERE.rglob('*') if p.is_file()},controller_sha256=digest(Path(__file__)),no_waveform_generated_yet=True),j)
    print('一次論文hashとLF primitiveを人工出力前に固定',flush=True)

def run():
    b=Budget();b.recover();assert not b.snapshot()['jobs'];contract=read(HERE/'execution-contract.json');verify(contract)
    r=b.reserve(NAME,'render','LF固定形状のC/独立Python20条件と密phase grid',42,20000000,expected_seconds=600)
    try:
        d=b.reserve(NAME,'dsp','LF根・面積・power・連続・flow・phase・数値・前半の限定監査',128,2000000,expected_seconds=600)
        try:
            with b.workspace(r,'LF数式と独立積分の科学ライブラリ初期化',8000000,16000000) as (_,env):
                env.update(OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',VECLIB_MAXIMUM_THREADS='1')
                out=subprocess.run([str(PYTHON),'-B',str(HERE/'worker.py')],env=env,check=True,capture_output=True,text=True,timeout=540)
            fixture=json.loads(out.stdout);b.save(HERE/'fixture-audit.json',fixture,d)
        except BaseException as exc:
            if isinstance(exc,subprocess.CalledProcessError):b.save(HERE/'child-failure.json',dict(returncode=exc.returncode,stdout=exc.stdout,stderr=exc.stderr),d)
            b.finish(d,repr(exc));raise
        else:b.finish(d)
    except BaseException as exc:b.finish(r,repr(exc));raise
    else:b.finish(r)
    with b.job(NAME,'audit','LF固定周期関数の限定資格・費用・一時回収を封印',reserve_bytes=2000000) as j:
        verify(contract);assert fixture['passed'] and len(fixture['rows'])==20
        b.save(HERE/'aggregate-summary.json',dict(mechanical_fixture_passed=True,fixed_LF_shape=True,net_flow_derivative_area_zero=True,independent_quad_power_one=True,closing_and_period_end_continuous=True,
            C_independent_Python_verified=True,HTS_coupling_qualified=False,antialiasing_qualified=False,real_Japanese_speech_qualified=False,perceptual_qualification=False,protected_confirmation_opened=False,quality_goal_completed=False),j)
        b.write(HERE/'report.md',('# LF声門流微分の固定周期関数\n\nTp=.4/Te=.6/Ta=.05/Ee=1を出力前固定し、有限帰還のepsilonとゼロ面積のalphaを数式から解いた。連続解析二乗積分で源のRMS尺度を一つに固定し、波形からgain/係数をfitしない。LF0列の縮小/平坦化やRosenberg有限差分の救済ではない。\n\n独立quadによる面積0・power1、閉相/周期端の連続、flow非負の17点、基本波Fourier係数非ゼロ、密phase gridと20人工条件のC/Python数値一致・前半一致・不正入力拒否を確認した。42生成/128DSP。周期関数の固定入力に限り、時間変動の源・声道、HTS/LPFへの結合、aliasing、日本語自然さ/知覚pitchを資格付けしない。\n\n一次資料: [Fant, Liljencrants & Lin (1985), A four-parameter model of glottal flow](https://www.speech.kth.se/qpsr/1985/1985_26_4_001-013.pdf)。式に基づく独自C/Python実装。Pink TromboneやGPL派生コードは取得/コピーしていない。\n\n次は科学30件のレビュー後、限定LFを原HTS励振へ結合する機構を別登録する。旧欠測と全凍結を保持。日本語知覚資格なし・P5未開封・品質未達。\n').encode(),j)
        s=b.snapshot();c=s['campaigns'][NAME];temporary=[v for v in s['temporary_work'].values() if v['campaign']==NAME];assert all(v['status']=='removed' and not os.path.lexists(v['path']) for v in temporary)
        b.save(HERE/'cost-audit.json',dict(counts=c['counts'],seconds=s['seconds']-c['start_seconds'],write_bytes=s['write_bytes']-c['start_write_bytes'],temporary_owned=len(temporary),all_temporary_absent=True,unused_download_reservation_not_returned=True),j)
        b.save(HERE/'artifact-seal.json',dict(files={str(p.relative_to(REPO)):digest(p) for p in HERE.rglob('*') if p.is_file()},path_base='repository',experiment_completed=True,quality_goal_completed=False,protected_confirmation_opened=False),j)
    b.close_campaign(NAME)
    with b.locked():
        s=b._load();s['continuation_checkpoint'].update(id='lf-source-mechanism-completed',active_campaign=None,next='科学30件レビュー後、LF/原HTS結合を別登録',git_save_pending=True);b._write_state(s)
    b.save(ROOT/'progress-0103.json',dict(latest_completed=NAME,quality_goal_completed=False,next='科学30件の定期レビュー',review=b.review_due(),budget=b.reconcile()))
    print(dict(passed=True,primitive_only=True,quality_goal_completed=False),flush=True)

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['register','prepare','fixture']);a=p.parse_args();{'register':register,'prepare':prepare,'fixture':run}[a.stage]()
