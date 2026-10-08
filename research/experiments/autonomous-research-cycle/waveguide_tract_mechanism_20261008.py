"""断面積からの正規化二方向伝搬を、圧力波の独立実装とエネルギーで検証する。"""
import argparse,ast,hashlib,json,os,subprocess,urllib.request
from pathlib import Path
from budget import ROOT,read,digest,encode
from long_horizon_budget import LongHorizonBudget as Budget
REPO=ROOT.parents[2]
HERE=ROOT/'campaigns/nas-waveguide-tract-mechanism-20261008-v1'
NAME='waveguide-tract-mechanism-v1'
PYTHON=REPO/'research/experiments/autonomous-speech-synthesis/.venv-eval/bin/python'
SOURCES=[('normalized-scattering','https://www.dsprelated.com/freebooks/pasp/Normalized_Scattering_Junctions.html'),
         ('pressure-scattering','https://www.dsprelated.com/freebooks/pasp/Plane_Wave_Scattering.html'),
         ('ideal-acoustic-tube','https://www.dsprelated.com/freebooks/pasp/Digital_Waveguide_Models.html')]

C_SOURCE=r'''/* 独自の正規化波伝搬。媒体形状の生理正解や移動壁の仕事は主張しない。 */
#include <math.h>
#include <stddef.h>
int tube_render(const double *drive,const double *area,size_t samples,size_t sections,
                double rg,double rl,double *out,double *energy) {
 if(!drive||!area||!out||!energy||samples<1||samples>96000||sections<2||sections>44)return 0;
 if(!isfinite(rg)||!isfinite(rl)||fabs(rg)>=1.||fabs(rl)>=1.)return 0;
 for(size_t n=0;n<samples;n++) {
  if(!isfinite(drive[n]))return 0;
  for(size_t j=0;j<sections;j++) {
   double a=area[n*sections+j];if(!isfinite(a)||a<.05||a>12.)return 0;
  }
 }
 double right[44]={0},left[44]={0},nr[44],nl[44];
 for(size_t n=0;n<samples;n++) {
  out[n]=(1.+rl)*right[sections-1];
  nr[0]=drive[n]+rg*left[0];nl[sections-1]=rl*right[sections-1];
  for(size_t j=0;j+1<sections;j++) {
   double a=area[n*sections+j],b=area[n*sections+j+1];
   double k=(a-b)/(a+b),t=sqrt(1.-k*k);
   nr[j+1]=t*right[j]-k*left[j+1];nl[j]=k*right[j]+t*left[j+1];
  }
  double e=0.;for(size_t j=0;j<sections;j++) {
   right[j]=nr[j];left[j]=nl[j];e+=nr[j]*nr[j]+nl[j]*nl[j];
  }
  if(!isfinite(out[n])||!isfinite(e))return 0;energy[n]=e;
 }
 return 1;
}
'''

MODULE=r'''"""断面積を直接入力する正規化波の共有声道primitive。保存音声・HMM・学習なし。"""
import ctypes as C,hashlib
from pathlib import Path
import numpy as np
P=C.POINTER(C.c_double);S=C.c_size_t
_lib=C.CDLL(str(Path(__file__).resolve().parent/'waveguide_tract.dylib'))
_fn=_lib.tube_render;_fn.restype=C.c_int;_fn.argtypes=[P,P,S,S,C.c_double,C.c_double,P,P]
def ah(x):return hashlib.sha256(np.asarray(x,dtype='<f8').tobytes()).hexdigest()
def render(drive,area,rg=.75,rl=-.85):
 x=np.ascontiguousarray(drive,dtype=np.float64);a=np.ascontiguousarray(area,dtype=np.float64)
 if x.ndim!=1 or not len(x) or a.ndim!=2 or len(x)!=len(a):raise ValueError('駆動列と同標本数の2D断面積が必要')
 before=(ah(x),ah(a));out=np.empty_like(x);energy=np.empty_like(x)
 if not _fn(x.ctypes.data_as(P),a.ctypes.data_as(P),len(x),a.shape[1],rg,rl,out.ctypes.data_as(P),energy.ctypes.data_as(P)):
  raise ValueError('断面積/終端反射/駆動/有限出力の内部検査に不通過')
 assert before==(ah(x),ah(a));return out,energy
def tests():
 assert not _fn(None,None,0,0,0.,0.,None,None)
 invalid=0
 for value in (np.nan,np.inf,0.,.049,12.001):
  a=np.ones((8,24));a[3,4]=value
  try:render(np.zeros(8),a)
  except ValueError:invalid+=1
  else:raise AssertionError('登録外の断面積を拒否しない')
 for value in (np.nan,np.inf,1.,-1.):
  try:render(np.zeros(8),np.ones((8,24)),rg=value)
  except ValueError:invalid+=1
  else:raise AssertionError('登録外の終端反射を拒否しない')
 for x,a in ((np.zeros(8),np.ones((8,1))),(np.zeros(8),np.ones((8,45))),(np.full(8,np.nan),np.ones((8,24)))):
  try:render(x,a)
  except ValueError:invalid+=1
  else:raise AssertionError('登録外の駆動/sectionを拒否しない')
 return dict(null_rejected=True,invalid_arrays_or_reflections_rejected=invalid)
'''

WORKER=r'''"""静的な圧力波と周波数行列、動的な正規化波、因果性、無入力エネルギーを照合。"""
import sys,json,math,os,tempfile
from pathlib import Path
here=Path(__file__).resolve().parent;sys.path.insert(0,str(here/'runtime-bundle'))
assert Path(tempfile.gettempdir()).resolve()==Path(os.environ['TMPDIR']).resolve()
import numpy as np
from waveguide_tract import render,tests,ah
RG=.75;RL=-.85;FS=48000.;SPEED=343.;N=24;T=8192
rng=np.random.default_rng(1067081)
def pressure_reference(x,A):
 # R=rho*c/A。rho*cは単位定数1として圧力↔正規化波を変換する。
 size=len(A);r=np.zeros(size);l=np.zeros(size);out=[];energy=[]
 for drive in x:
  out.append((1.+RL)*r[-1]*math.sqrt(A[-1]));nr=np.empty(size);nl=np.empty(size)
  nr[0]=drive/math.sqrt(A[0])+RG*l[0];nl[-1]=RL*r[-1]
  for j in range(size-1):
   # 独立に圧力連続/流量連続の式から求めた非正規化係数。
   R1=1./A[j];R2=1./A[j+1];k=(R2-R1)/(R1+R2)
   nr[j+1]=(1.+k)*r[j]-k*l[j+1];nl[j]=k*r[j]+(1.-k)*l[j+1]
  r=nr;l=nl;energy.append(float(np.sum(A*(r*r+l*l))))
 return np.array(out),np.array(energy)
def normalized_reference(x,areas):
 size=areas.shape[1];r=[0.]*size;l=[0.]*size;out=[];energy=[]
 for n,drive in enumerate(x):
  out.append((1.+RL)*r[-1]);nr=[0.]*size;nl=[0.]*size;nr[0]=drive+RG*l[0];nl[-1]=RL*r[-1]
  for j in range(size-1):
   k=(float(areas[n,j])-float(areas[n,j+1]))/(float(areas[n,j])+float(areas[n,j+1]));theta=math.asin(k)
   # sqrt演算と異なる回転表現で独立に計算。
   nr[j+1]=math.cos(theta)*r[j]-math.sin(theta)*l[j+1];nl[j]=math.sin(theta)*r[j]+math.cos(theta)*l[j+1]
  r=nr;l=nl;energy.append(sum(v*v for v in r)+sum(v*v for v in l))
 return np.array(out),np.array(energy)
def pressure_matrix(A):
 size=len(A);M=np.zeros((size*2,size*2));B=np.zeros(size*2);C=np.zeros(size*2)
 M[0,size]=RG;M[-1,size-1]=RL;B[0]=1./math.sqrt(A[0]);C[size-1]=(1.+RL)*math.sqrt(A[-1])
 for j in range(size-1):
  R1=1./A[j];R2=1./A[j+1];k=(R2-R1)/(R1+R2)
  M[j+1,j]=1.+k;M[j+1,size+j+1]=-k;M[size+j,j]=k;M[size+j,size+j+1]=1.-k
 return M,B,C
positions=(np.arange(N)+.5)/N
geometries=[np.ones(N),2.-1.8*np.exp(-.5*((positions-.25)/.09)**2),2.-1.8*np.exp(-.5*((positions-.75)/.09)**2),np.r_[np.full(N//2,.1),np.full(N//2,4.)]]
static=[];impulses={};wave_calls=0
for g,A in enumerate(geometries):
 for mode in ('impulse','noise'):
  x=np.zeros(T)
  if mode=='impulse':x[0]=1.
  else:x[:2048]=rng.normal(0.,.01,2048)
  area=np.tile(A,(T,1));before=(ah(x),ah(area));y,e=render(x,area);ref,er=pressure_reference(x,A);wave_calls+=2
  error=float(np.max(np.abs(y-ref)));energy_error=float(np.max(np.abs(e-er)));assert error<=1e-10 and energy_error<=1e-10
  assert before==(ah(x),ah(area));start=1 if mode=='impulse' else 2048
  assert np.max(np.diff(e[start:]))<=1e-10 and e[-1]<=e[start]+1e-10
  changed=x.copy();changed[4096:]+=.01;future=render(changed,area)[0];wave_calls+=1;assert np.array_equal(y[:4096],future[:4096])
  altered=area.copy();altered[4096:]=geometries[(g+1)%len(geometries)];future_shape=render(x,altered)[0];wave_calls+=1;assert np.array_equal(y[:4096],future_shape[:4096])
  if mode=='impulse':impulses[g]=y
  static.append(dict(geometry=g,driver=mode,output_max_error=error,energy_max_error=energy_error,unforced_energy_nonincreasing=True,input_and_future_area_prefix_exact=True,input_bytes_unchanged=True,output_sha256=ah(y)))
analytic=[]
for size in (8,16,24):
 x=np.zeros(T);x[0]=1.;expected=np.zeros(T);roundtrip=2*size
 for n in range(size,T,roundtrip):expected[n]=(1.+RL)*(RG*RL)**((n-size)//roundtrip)
 if size==24:y=impulses[0]
 else:y=render(x,np.ones((T,size)))[0];wave_calls+=1
 wave_calls+=1 # 解析応答列自体を保守的に生成として計上する。
 error=float(np.max(np.abs(y-expected)));assert error<=1e-12
 analytic.append(dict(sections=size,one_way_samples=size,roundtrip_samples=roundtrip,max_abs_error=error,first_three_resonances_Hz=[FS*(2*k+1)/(4*size) for k in range(3)],length_cm=SPEED*size/FS*100.))
frequency=[]
for g,A in enumerate(geometries):
 M,B,C=pressure_matrix(A);bins=np.arange(1,1025,2);omega=2*np.pi*bins/T;actual=np.fft.rfft(impulses[g])[bins]
 independent=np.array([C@np.linalg.solve(np.exp(1j*w)*np.eye(len(B))-M,B) for w in omega])
 error=float(np.max(np.abs(actual-independent)));assert error<=1e-9
 frequency.append(dict(geometry=g,bins=len(bins),maximum_complex_error=error,pressure_matrix_derived_from_continuity=True))
dynamic=[]
for mode in ('ramp','sine','step'):
 if mode=='ramp':weight=np.linspace(0.,1.,T)
 elif mode=='sine':weight=.5+.5*np.sin(2*np.pi*np.arange(T)/2048.)
 else:weight=(np.arange(T)>=2048).astype(float)
 area=(1.-weight[:,None])*geometries[1]+weight[:,None]*geometries[2]
 for source in ('impulse','noise'):
  x=np.zeros(T)
  if source=='impulse':x[0]=1.
  else:x[:2048]=rng.normal(0.,.01,2048)
  y,e=render(x,area);ref,er=normalized_reference(x,area);wave_calls+=2
  error=float(np.max(np.abs(y-ref)));energy_error=float(np.max(np.abs(e-er)));assert error<=1e-10 and energy_error<=1e-10
  start=1 if source=='impulse' else 2048;assert np.max(np.diff(e[start:]))<=1e-10
  future_area=area.copy();future_area[4096:]=1.;future=render(x,future_area)[0];wave_calls+=1;assert np.array_equal(y[:4096],future[:4096])
  dynamic.append(dict(mode=mode,driver=source,output_max_error=error,energy_max_error=energy_error,unforced_normalized_energy_nonincreasing=True,future_area_prefix_exact=True,
                      moving_wall_mechanical_work_modeled=False,normalized_state_not_physical_pressure_energy_under_geometry_changes=True,output_sha256=ah(y)))
bad=tests()
assert len(static)==8 and len(dynamic)==6 and len(frequency)==4 and wave_calls<=80
print(json.dumps(dict(passed=True,static_rows=static,analytic_uniform_rows=analytic,frequency_rows=frequency,dynamic_rows=dynamic,invalid_inputs=bad,
                     actual_valid_output_or_reference_calls=wave_calls,charged_render=80,charged_DSP=256,conservative_counts_not_returned=True,
                     geometry_fixtures_are_not_vowel_labels=True,phoneme_generation_qualified=False,real_Japanese_quality_qualified=False,perceptual_qualification=False)))
'''

def verify(contract):
    assert digest(Path(__file__))==contract['controller_sha256']
    for n,h in contract['files'].items():assert digest(HERE/n)==h,n

def register():
    b=Budget();b.recover();assert not b.snapshot()['jobs'] and not b.review_due()['due']
    prev=ROOT/'campaigns/nas-fujisaki-context-comparison-20261008-v1';assert not read(prev/'aggregate-summary.json')['research_protection_gates']['fujisaki']
    ast.parse(MODULE);ast.parse(WORKER)
    limits=dict(seconds=7200,bytes=300000000,write_bytes=800000000,setup=16,audit=16,render=240,dsp=768,download=3000000,ai=0,teacher=0,train=0,inverse=0)
    reg=dict(campaign=NAME,question='正の断面積から独立した二方向伝搬を実装し、静的圧力波の連続条件/解析応答/動的正規化エネルギー/因果性を検証できるか。',
             factor='波インピーダンスR=rho*c/A、k=(A_left-A_right)/(A_left+A_right)。正規化波の透過sqrt(1-k^2)と反射±k、各sectionの一標本遅延。',
             boundary=dict(glottal_reflection=.75,lip_reflection=-.85,observed_lip_pressure_factor='1+lip_reflection',fs=48000.,sound_speed=343.,main_sections=24,main_length_cm=17.15),
             controls='固定設計の終端反射、駆動はunit impulse/固定seed noise。波形別利得/係数探索/HTS/HMM/録音/教師/lookupなし。',
             fixture=dict(static_geometries=['uniform1','2-1.8*Gaussian(center.25,width.09)','2-1.8*Gaussian(center.75,width.09)','前半.1/後半4'],static_drivers=['impulse','noise'],samples=8192,
                          dynamic=['ramp','sine(period2048)','step(at2048)'],causal_cut=4096,uniform_sections=[8,16,24],frequency_bins=512,area_range_cm2=[.05,12.]),
             thresholds=dict(independent_output_and_energy_error=1e-10,uniform_analytic_error=1e-12,complex_pressure_matrix_response_error=1e-9,unforced_energy_increase_at_most=1e-10,future_input_and_geometry_prefix_exact=True,input_bytes_exact=True),
             scope='正の固定/動的断面積の正規化波primitiveだけ。正規化状態は形状変更時にもpassiveだが、移動壁の機械仕事を含む物理圧力エネルギーとは同一視しない。閉鎖/鼻腔/粘性/熱/放射/生理声門/音素制御/日本語自然さは未資格。',
             costs=dict(charged_render=80,charged_DSP=256,download_conservative=3000000,maximum_seconds=6000,temporary_peak=16000000,temporary_write=32000000,RAM_gb=8),limits=limits,
             sources=dict(primary_book='Julius O. Smith III, Physical Audio Signal Processing, 著者書籍の公開Web版',public_pages=SOURCES,formula_implementation_independently_authored=True,third_party_source_code_downloaded=False,previous_comparison_seal_sha256=digest(prev/'artifact-seal.json')),
             c_sha256=hashlib.sha256(C_SOURCE.encode()).hexdigest(),module_sha256=hashlib.sha256(MODULE.encode()).hexdigest(),worker_sha256=hashlib.sha256(WORKER.encode()).hexdigest(),controller_sha256=digest(Path(__file__)),
             prior_Fujisaki_same_cohort_coefficients_command_times_median_gain_frozen=True,all_inherited_frozen_routes_kept=True,perceptual_qualification=False,protected_confirmation_opened=False,quality_goal_completed=False,
             next='科学36件の第6回レビュー。通過時は一次測定に基づく共有声道形状/音素指令を別登録し、人工断面を母音正解と扱わず生成制御へ進む。')
    b.start_campaign(NAME,str(HERE.relative_to(ROOT)),limits,hashlib.sha256(encode(reg)).hexdigest())
    with b.job(NAME,'setup','独立断面積伝搬の因子・全数値条件・全機構費を出力前登録',reserve_bytes=2000000) as j:
        b.save(HERE/'registration.json',reg,j);b.write(HERE/'waveguide_tract.c',C_SOURCE.encode(),j);b.write(HERE/'waveguide_tract.py',MODULE.encode(),j);b.write(HERE/'worker.py',WORKER.encode(),j)
        b.save(HERE/'source-contract.json',dict(files={str(p.relative_to(HERE)):digest(p) for p in HERE.rglob('*') if p.is_file()},controller_sha256=digest(Path(__file__)),no_scientific_output_yet=True),j)
    b.save(ROOT/'progress-0115.json',dict(active_campaign=NAME,next='登録push→公開一次式hash→独自primitive build→全静的/動的数値fixture',new_scientific_outputs=0,quality_goal_completed=False,budget=b.reconcile()))
    print(dict(registered=True,new_scientific_outputs=0),flush=True)

def prepare():
    b=Budget();b.recover();assert not b.snapshot()['jobs'];verify(read(HERE/'source-contract.json'))
    with b.job(NAME,'download','正規化波・圧力連続・理想tubeの一次解説を固定保存',3000000,5000000) as j:
        rows=[]
        for name,url in SOURCES:
            with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'VoiceSimulatorResearch/1.0'}),timeout=45) as response:data=response.read(1000001);resolved=str(response.url)
            assert len(data)<=1000000
            b.write_data(HERE/'upstream'/f'{name}.html',data,j);rows.append(dict(id=name,url=url,resolved_url=resolved,bytes=len(data),sha256=hashlib.sha256(data).hexdigest()))
        b.save(HERE/'primary-source-audit.json',dict(rows=rows,conservative_charge=3000000,unused_reservation_not_returned=True,no_third_party_code_copied=True),j)
    with b.job(NAME,'setup','独自断面積伝搬Cの外部cache buildと共有入口を固定',reserve_bytes=30000000) as j:
        bundle=HERE/'runtime-bundle';b.write(bundle/'waveguide_tract.py',MODULE.encode(),j)
        with b.workspace(j,'断面積伝搬primitive build専用',16000000,32000000) as (work,env):
            env['CLANG_MODULE_CACHE_PATH']=str(work/'clang-modules');tool='/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/clang';sdk='/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk'
            cmd=[tool,'-dynamiclib','-O2','-fno-modules','-isysroot',sdk,str(HERE/'waveguide_tract.c'),'-o',str(bundle/'waveguide_tract.dylib')]
            with b.external_output(bundle/'waveguide_tract.dylib',100000,j):out=subprocess.run(cmd,env=env,check=True,capture_output=True,text=True,timeout=120)
        b.save(HERE/'build-audit.json',dict(command=cmd,stderr=out.stderr,source_sha256=digest(HERE/'waveguide_tract.c'),binary_sha256=digest(bundle/'waveguide_tract.dylib'),temporary_removed=True),j)
        b.save(bundle/'manifest.json',dict(files={str(p.relative_to(bundle)):digest(p) for p in bundle.rglob('*') if p.is_file()},neural_inference=False,recorded_audio_used=False),j)
        b.save(HERE/'execution-contract.json',dict(files={str(p.relative_to(HERE)):digest(p) for p in HERE.rglob('*') if p.is_file()},controller_sha256=digest(Path(__file__)),no_scientific_output_yet=True),j)
    print('独自二方向声道primitiveと一次式を出力前固定',flush=True)

def run():
    b=Budget();b.recover();assert not b.snapshot()['jobs'];contract=read(HERE/'execution-contract.json');verify(contract)
    r=b.reserve(NAME,'render','全静的/動的声道のCと独立圧力波/回転表現の生成',80,20000000,expected_seconds=900)
    try:
        d=b.reserve(NAME,'dsp','独立圧力波・解析delay・周波数行列・エネルギー・因果性',256,2000000,expected_seconds=900)
        try:
            with b.workspace(r,'断面積伝搬fixtureの科学ライブラリ初期化',8000000,16000000) as (_,env):
                env.update(OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',VECLIB_MAXIMUM_THREADS='1')
                out=subprocess.run([str(PYTHON),'-B',str(HERE/'worker.py')],env=env,check=True,capture_output=True,text=True,timeout=840)
            fixture=json.loads(out.stdout);b.save(HERE/'fixture-audit.json',fixture,d)
        except BaseException as exc:
            if isinstance(exc,subprocess.CalledProcessError):b.save(HERE/'child-failure.json',dict(returncode=exc.returncode,stdout=exc.stdout,stderr=exc.stderr),d)
            b.finish(d,repr(exc));raise
        else:b.finish(d)
    except BaseException as exc:b.finish(r,repr(exc));raise
    else:b.finish(r)
    with b.job(NAME,'audit','独立声道primitiveの限定範囲・全条件・費用・一時回収を封印',reserve_bytes=2000000) as j:
        verify(contract);assert fixture['passed'] and len(fixture['static_rows'])==8 and len(fixture['dynamic_rows'])==6
        result=dict(mechanical_fixture_passed=True,positive_area_control=True,independent_static_pressure_wave_verified=True,uniform_delay_and_response_verified=True,
                    independent_frequency_matrix_verified=True,normalized_dynamic_energy_passive=True,future_drive_and_area_prefix_exact=True,moving_wall_mechanical_work_modeled=False,
                    phoneme_generation_qualified=False,real_Japanese_quality_qualified=False,perceptual_qualification=False,protected_confirmation_opened=False,quality_goal_completed=False,next=read(HERE/'registration.json')['next'])
        b.save(HERE/'aggregate-summary.json',result,j)
        lines=['# 正の断面積による独立二方向声道伝搬','','原HTS/MLSA/共有HMMから独立した正規化波primitiveを独自Cで実装した。R=rho*c/Aから反射kと透過sqrt(1-k²)を作り、sectionごとに一標本伝搬する。終端反射.75/-.85と人工geometryを出力前に固定し、結果から利得/係数を選ばない。','',
               '静的4形状×2駆動の独立圧力波とエネルギー、8/16/24section一様管の解析delay応答、4形状の独立圧力行列の複素応答、3動的形状×2駆動の独立回転表現・無入力正規化エネルギー・将来入力/形状の前半不変を照合した。不正断面・駆動・終端反射を拒否する。80render/256DSPを保守的に課し返金しない。','',
               '48kHz/音速343m/s/24sectionで一様管長17.15cm。人工断面は母音正解ではない。正規化波のpassivityを、移動壁の仕事を含む実圧力エネルギーや生理的調音の資格へ拡張しない。閉鎖/鼻腔/粘性/熱/放射/生理声門/音素指令/日本語は別検証。','',
               '一次式: '+', '.join('[Julius O. Smith, '+name+']('+url+')' for name,url in SOURCES),'',result['next'],'','P5未開封・日本語知覚資格なし・品質未達。旧係数救済と全凍結を保持。','']
        b.write(HERE/'report.md','\n'.join(lines).encode(),j)
        s=b.snapshot();c=s['campaigns'][NAME];tmp=[x for x in s['temporary_work'].values() if x['campaign']==NAME];assert all(x['status']=='removed' and not os.path.lexists(x['path']) for x in tmp)
        b.save(HERE/'cost-audit.json',dict(counts=c['counts'],seconds=s['seconds']-c['start_seconds'],write_bytes=s['write_bytes']-c['start_write_bytes'],temporary_owned=len(tmp),all_owned_temporary_absent=True),j)
        b.save(HERE/'artifact-seal.json',dict(files={str(p.relative_to(REPO)):digest(p) for p in HERE.rglob('*') if p.is_file()},path_base='repository',experiment_completed=True,quality_goal_completed=False,protected_confirmation_opened=False),j)
    b.close_campaign(NAME)
    with b.locked():
        s=b._load();s['continuation_checkpoint'].update(id='waveguide-tract-mechanism-completed',active_campaign=None,next=result['next'],git_save_pending=True);b._write_state(s)
    b.save(ROOT/'progress-0116.json',dict(latest_completed=NAME,next=result['next'],quality_goal_completed=False,review=b.review_due(),budget=b.reconcile()))
    print(dict(mechanical_fixture_passed=True,phoneme_generation_qualified=False,quality_goal_completed=False),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['register','prepare','fixture']);a=p.parse_args();{'register':register,'prepare':prepare,'fixture':run}[a.stage]()
