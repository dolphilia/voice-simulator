"""同じ放射近似を共通エネルギー状態へ実現し、半径変更時の受動性を検証する。"""
import argparse,ast,hashlib,json,os,subprocess
from pathlib import Path
from contextlib import contextmanager
from budget import ROOT,read,digest,encode
from long_horizon_budget import LongHorizonBudget as Budget
REPO=ROOT.parents[2];HERE=ROOT/'campaigns/nas-radiation-passive-state-20261008-v1';NAME='radiation-passive-state-v1'
PREV=ROOT/'campaigns/nas-radiation-boundary-mechanism-20261008-v1'
PYTHON=REPO/'research/experiments/autonomous-speech-synthesis/.venv-eval/bin/python'

C_SOURCE='''/* 一次反射係数の独自エネルギー状態実現。人体の移動壁の仕事ではない。 */
#include <math.h>
#include <stddef.h>
static void mul(const double a[2][2],const double b[2][2],double c[2][2]){
 for(int i=0;i<2;i++)for(int j=0;j<2;j++)c[i][j]=a[i][0]*b[0][j]+a[i][1]*b[1][j];
}
int port_matrix(double fs,double radius,int flanged,double*out){
 if(!out||!isfinite(fs)||fs<16000||fs>96000||!isfinite(radius)||radius<.003||radius>.03||(flanged!=0&&flanged!=1))return 0;
 double n1=flanged?.182:.167,d1=flanged?1.825:1.393,d2=flanged?.649:.457;
 double delta=d1*d1-2.*d2-n1*n1,sd=sqrt(delta);
 double p00=d1-n1,p01=d2,p11=d2*(d1-sd);
 double u00=sqrt(p00),u01=p01/u00,u11=sqrt(p11-u01*u01);
 double U[2][2]={{u00,u01},{0.,u11}},V[2][2]={{1./u00,-u01/(u00*u11)},{0.,1./u11}};
 double A[2][2]={{0.,1.},{-1./d2,-d1/d2}},temp[2][2],AA[2][2];mul(U,A,temp);mul(temp,V,AA);
 double B[2]={u01/d2,u11/d2},CC[2][2];
 double C[2][2]={{-1.,-n1},{-1.,sd-d1}};mul(C,V,CC);
 double h=343./(2.*fs*radius),root=sqrt(2.*h);
 double M[2][2]={{1.-h*AA[0][0],-h*AA[0][1]},{-h*AA[1][0],1.-h*AA[1][1]}};
 double det=M[0][0]*M[1][1]-M[0][1]*M[1][0];
 double inv[2][2]={{M[1][1]/det,-M[0][1]/det},{-M[1][0]/det,M[0][0]/det}};
 double plus[2][2]={{1.+h*AA[0][0],h*AA[0][1]},{h*AA[1][0],1.+h*AA[1][1]}},Ad[2][2],Cd[2][2];mul(inv,plus,Ad);mul(CC,inv,Cd);
 double ib[2]={inv[0][0]*B[0]+inv[0][1]*B[1],inv[1][0]*B[0]+inv[1][1]*B[1]};
 for(int i=0;i<2;i++){out[i*3]=Ad[i][0];out[i*3+1]=Ad[i][1];out[i*3+2]=root*ib[i];}
 for(int i=0;i<2;i++){out[(i+2)*3]=root*Cd[i][0];out[(i+2)*3+1]=root*Cd[i][1];out[(i+2)*3+2]=(i==1?1.:0.)+h*(CC[i][0]*ib[0]+CC[i][1]*ib[1]);}
 for(int i=0;i<12;i++)if(!isfinite(out[i]))return 0;return 1;
}
int radiation_port(const double*x,const double*radius,size_t n,double fs,int flanged,const double*initial,double*last,double*reflected,double*loss,double*energy){
 if(!x||!radius||!initial||!last||!reflected||!loss||!energy||n<1||n>96000||!isfinite(fs)||fs<16000||fs>96000||(flanged!=0&&flanged!=1))return 0;
 if(!isfinite(initial[0])||!isfinite(initial[1]))return 0;
 for(size_t i=0;i<n;i++)if(!isfinite(x[i])||!isfinite(radius[i])||radius[i]<.003||radius[i]>.03)return 0;
 double z0=initial[0],z1=initial[1],K[12];
 for(size_t i=0;i<n;i++){
  if(!port_matrix(fs,radius[i],flanged,K))return 0;
  double v0=K[0]*z0+K[1]*z1+K[2]*x[i],v1=K[3]*z0+K[4]*z1+K[5]*x[i];
  reflected[i]=K[6]*z0+K[7]*z1+K[8]*x[i];loss[i]=K[9]*z0+K[10]*z1+K[11]*x[i];
  z0=v0;z1=v1;energy[i]=z0*z0+z1*z1;
 }
 last[0]=z0;last[1]=z1;return 1;
}
'''

MODULE='''"""二状態/二出力の等長行列。lossは正規化損失portで、遠方micではない。"""
import ctypes as C,math,json,hashlib
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parent;COEF=json.loads((HERE/'coefficients.json').read_text());P=C.POINTER(C.c_double)
_lib=C.CDLL(str(HERE/'radiation_port.dylib'));_matrix=_lib.port_matrix;_matrix.restype=C.c_int;_matrix.argtypes=[C.c_double,C.c_double,C.c_int,P]
_fn=_lib.radiation_port;_fn.restype=C.c_int;_fn.argtypes=[P,P,C.c_size_t,C.c_double,C.c_int,P,P,P,P,P]
def ah(x):return hashlib.sha256(np.asarray(x,dtype='<f8').tobytes()).hexdigest()
def matrix(fs,radius,flanged):
 if type(flanged) is not bool:raise ValueError('終端はboolのみ')
 out=np.empty((4,3))
 if not _matrix(fs,radius,int(flanged),out.ctypes.data_as(P)):raise ValueError('有限Fs/半径が登録範囲外')
 return out
def block(x,radius,fs,flanged,state=None):
 if type(flanged) is not bool:raise ValueError('終端はboolのみ')
 x=np.ascontiguousarray(x,dtype=float);radius=np.ascontiguousarray(radius,dtype=float);state=np.zeros(2) if state is None else np.ascontiguousarray(state,dtype=float)
 if x.ndim!=1 or radius.shape!=x.shape or state.shape!=(2,) or not 1<=len(x)<=96000:raise ValueError('列/状態寸法が不整合')
 before=(ah(x),ah(radius),ah(state));r=np.empty_like(x);l=np.empty_like(x);energy=np.empty_like(x);last=np.empty_like(state)
 if not _fn(x.ctypes.data_as(P),radius.ctypes.data_as(P),len(x),fs,int(flanged),state.ctypes.data_as(P),last.ctypes.data_as(P),r.ctypes.data_as(P),l.ctypes.data_as(P),energy.ctypes.data_as(P)):raise ValueError('有限入力/状態/半径を拒否')
 assert before==(ah(x),ah(radius),ah(state));return r,l,energy,last
'''

WORKER='''"""等長行列と固定伝達を別計算し、時間変化下の正規化エネルギーを検証する。"""
import sys,json,math
from pathlib import Path
import numpy as np
from scipy import signal
here=Path(sys.argv[1]);sys.path.insert(0,str(here/'runtime-bundle'))
from radiation_port import matrix,block,COEF,_fn,P
def independent_matrix(fs,radius,flanged):
 n,d,e=COEF['flanged' if flanged else 'unflanged'];delta=d*d-2*e-n*n;root=np.sqrt(delta)
 metric=np.array([[d-n,e],[e,e*(d-root)]]);U=np.linalg.cholesky(metric).T;V=np.linalg.inv(U)
 A=U@np.array([[0.,1.],[-1/e,-d/e]])@V;B=U@np.array([0.,1/e]);C=np.array([[-1.,-n],[-1.,root-d]])@V
 h=343/(2*fs*radius);inv=np.linalg.inv(np.eye(2)-h*A)
 return np.vstack([np.column_stack([inv@(np.eye(2)+h*A),np.sqrt(2*h)*inv@B]),np.column_stack([np.sqrt(2*h)*C@inv,np.array([0.,1.])+h*C@inv@B])])
grid=[];max_matrix=0.;max_isometry=0.
for fs in (34300.,48000.):
 for flanged in (False,True):
  for radius in np.linspace(.003,.03,129):
   K=matrix(fs,float(radius),flanged);ref=independent_matrix(fs,float(radius),flanged);err=float(np.max(abs(K-ref)));iso=float(np.max(abs(K.T@K-np.eye(3))));assert err<=3e-12 and iso<=3e-12
   max_matrix=max(max_matrix,err);max_isometry=max(max_isometry,iso)
  grid.append(dict(fs=fs,flanged=flanged,points=129))
T=8192;rng=np.random.default_rng(720810);rows=[];calls=0
for fs in (34300.,48000.):
 for flanged in (False,True):
  n,d,e=COEF['flanged' if flanged else 'unflanged'];tau=None;delta=d*d-2*e-n*n
  for radius in (.007,.008,.012,.016):
   tau=radius/343.;den=[e*tau*tau,d*tau,1.];br,ar=signal.bilinear([-n*tau,-1.],den,fs);bl,al=signal.bilinear([e*tau*tau,np.sqrt(delta)*tau,0.],den,fs)
   for name in ('impulse','noise'):
    x=np.zeros(T) if name=='impulse' else rng.normal(0,.1,T)
    if name=='impulse':x[0]=1.
    radius_values=np.full(T,radius);r,l,E,last=block(x,radius_values,fs,flanged);calls+=1
    rr=signal.lfilter(br,ar,x);ll=signal.lfilter(bl,al,x);calls+=2
    error=max(float(np.max(abs(r-rr))),float(np.max(abs(l-ll))));assert error<=3e-13
    balance=float(np.max(abs(E+np.cumsum(r*r+l*l)-np.cumsum(x*x))));assert balance<=2e-11
    state=np.zeros(2);pieces=[];start=0;k=0
    while start<T:
     stop=min(T,start+(2048,4096,8192)[k%3]);z,w,_,state=block(x[start:stop],radius_values[start:stop],fs,flanged,state);pieces.append(np.column_stack([z,w]));calls+=1;start=stop;k+=1
    assert np.concatenate(pieces).tobytes()==np.column_stack([r,l]).tobytes() and state.tobytes()==last.tobytes()
    rows.append(dict(kind='fixed',fs=fs,radius_m=radius,flanged=flanged,signal=name,independent_transfer_error=error,cumulative_energy_error=balance,passed=True))
  t=np.arange(T)/fs
  curves=[('ramp',np.linspace(.007,.016,T)),('sine',.0115+.0045*np.sin(2*np.pi*7*t)),('step',np.where(np.arange(T)<T//2,.016,.007))]
  for name,radius_values in curves:
   matrices=np.stack([independent_matrix(fs,float(v),flanged) for v in radius_values])
   for forced in (False,True):
    x=rng.normal(0,.1,T) if forced else np.zeros(T);initial=np.array([.7,-.4]);r,l,E,last=block(x,radius_values,fs,flanged,initial);calls+=1
    refstate=initial.copy();ref=np.empty((T,2))
    for i,K in enumerate(matrices):
     out=K@np.r_[refstate,x[i]];refstate=out[:2];ref[i]=out[2:]
    calls+=1;error=float(np.max(abs(np.column_stack([r,l])-ref)));assert error<=3e-13 and float(np.max(abs(refstate-last)))<=3e-13
    balance=float(np.max(abs(E+np.cumsum(r*r+l*l)-np.cumsum(x*x)-initial@initial)));assert balance<=2e-11
    if not forced:assert np.max(np.diff(np.r_[initial@initial,E]))<=3e-12
    future_r=radius_values.copy();future_r[T//2:]=.003;future_x=x.copy();future_x[T//2:]=.3;future=block(future_x,future_r,fs,flanged,initial);calls+=1
    assert future[0][:T//2].tobytes()==r[:T//2].tobytes() and future[1][:T//2].tobytes()==l[:T//2].tobytes()
    state=initial.copy();pieces=[];start=0;k=0
    while start<T:
     stop=min(T,start+(2048,4096,8192)[k%3]);z,w,_,state=block(x[start:stop],radius_values[start:stop],fs,flanged,state);pieces.append(np.column_stack([z,w]));calls+=1;start=stop;k+=1
    assert np.concatenate(pieces).tobytes()==np.column_stack([r,l]).tobytes() and state.tobytes()==last.tobytes()
    rows.append(dict(kind='dynamic',fs=fs,flanged=flanged,radius_curve=name,forced=forced,independent_state_error=error,cumulative_energy_error=balance,unforced_monotone=not forced,passed=True))
invalid=0
cases=[(np.zeros(0),np.zeros(0),34300.,False,None),(np.zeros(3),np.zeros(2),34300.,False,None),(np.array([np.nan]),np.array([.007]),34300.,False,None),(np.zeros(1),np.array([np.inf]),34300.,False,None),(np.zeros(1),np.array([.002]),34300.,False,None),(np.zeros(1),np.array([.031]),34300.,False,None),(np.zeros(1),np.array([.007]),np.nan,False,None),(np.zeros(1),np.array([.007]),1000.,False,None),(np.zeros(1),np.array([.007]),34300.,2,None),(np.zeros(1),np.array([.007]),34300.,False,np.zeros(3)),(np.zeros(1),np.array([.007]),34300.,False,np.array([np.nan,0.]))]
for args in cases:
 try:block(*args)
 except ValueError:invalid+=1
 else:raise AssertionError('不正入力を受理')
assert invalid==11
initial=np.zeros(2);last=np.full(2,321.);out=np.full(4,123.);radii=np.full(4,.007)
assert not _fn(None,radii.ctypes.data_as(P),4,34300.,0,initial.ctypes.data_as(P),last.ctypes.data_as(P),out.ctypes.data_as(P),out.ctypes.data_as(P),out.ctypes.data_as(P)) and np.all(out==123.) and np.all(last==321.)
assert len(rows)==56 and calls<=450
print(json.dumps(dict(passed=True,rows=rows,matrix_grid=grid,grid_points=516,max_independent_matrix_error=max_matrix,max_isometry_error=max_isometry,actual_render_calls=calls,invalid_cases=invalid+1,fixed_transfer_matches_previous_Pade=True,dynamic_normalized_energy_passive=True,partition_and_future_prefix_exact=True,loss_port_is_not_far_field_microphone=True,moving_wall_physical_work_qualified=False)))
'''

@contextmanager
def job(b,kind,label,count=1,size=0,seconds=600):
    j=b.reserve(NAME,kind,label,count,size,expected_seconds=seconds)
    try:yield j
    except BaseException as e:b.finish(j,repr(e));raise
    else:b.finish(j)
def execute(cmd,env,timeout=600):
    env=dict(env);env.update(OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',VECLIB_MAXIMUM_THREADS='1');return subprocess.run(cmd,env=env,check=True,capture_output=True,text=True,timeout=timeout)
def verify(name):
    c=read(HERE/name);assert digest(Path(__file__))==c['controller_sha256']
    for p,h in c['files'].items():assert digest(HERE/p)==h,p
def register():
    b=Budget();b.recover();assert not b.snapshot()['jobs'] and not b.review_due()['due'] and read(PREV/'aggregate-summary.json')['passed']
    for src in (MODULE,WORKER):ast.parse(src)
    limits=dict(seconds=7200,bytes=300000000,write_bytes=800000000,setup=20,audit=20,render=900,dsp=4000,ai=0,teacher=0,train=0,inverse=0,download=0)
    reg=dict(campaign=NAME,question='固定Padé反射を共通正規化エネルギー状態へ実現し、半径が変わる時も受動性と状態/因果/区切りを保持できるか。',
      primary=dict(previous_seal=digest(PREV/'artifact-seal.json'),coefficients=digest(PREV/'coefficients.json'),URL='https://arxiv.org/abs/0811.3625',previous_causal_approximation_unchanged=True),
      derivation='独自導出。delta=d1^2-2d2-n1^2>0、反射R=-(1+n1*s)/(1+d1*s+d2*s^2)、補完loss T=s(sqrt(delta)+d2*s)/(1+d1*s+d2*s^2)。全実周波数で|R|^2+|T|^2=1。A=[[0,1],[-1/d2,-d1/d2]],B=[0,1/d2],C=[[-1,-n1],[-1,sqrt(delta)-d1]],D=[0,1]。P=[[d1-n1,d2],[d2,d2(d1-sqrt(delta))]]、U^TU=P、A0=UAU^-1,B0=UB,C0=CU^-1。h=c/(2Fs*a),M=(I-hA0)^-1。Ad=M(I+hA0),Bd=sqrt(2h)MB0,Cd=sqrt(2h)C0M,Dd=D+hC0MB0。K=[[Ad,Bd],[Cd,Dd]]がK^TK=I。',
      factor='半径ごとのDF1履歴から、共通Euclidean二状態と反射/loss二portへ変更。現在半径の等長4x3行列を使い、stateを変更/リセットせず継承する。係数のfit/補正/clipなし。',
      fixtures=dict(fs=[34300,48000],matrix_radii_m=dict(min=.003,max=.03,points=129),fixed_radii_m=[.007,.008,.012,.016],terminations=['unflanged','flanged'],samples=8192,signals=['impulse','Gaussian noise'],dynamic_radii=['linear .007→.016','7Hz sine .0115±.0045','half .016→.007 step'],dynamic_initial_state=[.7,-.4],dynamic_forced_and_unforced=True,seed=720810),
      gates=dict(matrix_vs_independent_Cholesky_and_inverse=3e-12,isometry_K_transpose_K_identity=3e-12,fixed_R_and_loss_vs_SciPy_bilinear_lfilter=3e-13,dynamic_vs_independent_matrix_state=3e-13,cumulative_energy_error=2e-11,unforced_state_energy_increase_at_most=3e-12,partition_and_future_input_radius_prefix_bytes_exact=True,invalid_rejected=12),
      scope='数学的正規化状態の受動性。変化する実人体の壁の仕事/圧力連続/頭部指向性/遠方mic/日本語音声の資格を主張しない。loss portは正規化放射損失の一つの因果的スペクトル因子で、物理micの位相や位置ではない。',
      estimates=dict(render=450,dsp=1400,source_and_internal_blocks_included=True,temporary_peak=16000000,temporary_write=32000000,RAM_gb=8,closeout_Git_included=True),
      limits=limits,controller_sha256=digest(Path(__file__)),all_old_failed_routes_kept=True,perceptual_qualification=False,protected_confirmation_opened=False,quality_goal_completed=False,
      next='全機構通過時だけ声道stateとこの二状態を結合し、同じ入力/固定形状の独立反射と動的無強制エネルギーを検証する。loss出力/唇flow/源の積分表現は別の因果因子として明記し、工学資格と新語句内容比較を順に行う。')
    b.start_campaign(NAME,str(HERE.relative_to(ROOT)),limits,hashlib.sha256(encode(reg)).hexdigest())
    with job(b,'setup','可変半径の正規化等長状態/独自導出/全条件を実出力前固定',size=3000000) as j:
        b.save(HERE/'registration.json',reg,j);b.save(HERE/'coefficients.json',read(PREV/'coefficients.json'),j)
        for n,s in [('radiation_port.c',C_SOURCE),('radiation_port.py',MODULE),('worker.py',WORKER)]:b.write(HERE/n,s.encode(),j)
        b.save(HERE/'source-contract.json',dict(files={str(p.relative_to(HERE)):digest(p) for p in HERE.rglob('*') if p.is_file()},controller_sha256=digest(Path(__file__)),fixed_before_science=True),j)
    b.save(ROOT/'progress-0127.json',dict(active_campaign=NAME,next='登録push→独自等長state C build→全516行列/56信号の独立/状態/受動を封印',new_waveforms=0,quality_goal_completed=False,budget=b.reconcile()));print('可変半径の正規化受動状態を実出力前登録',flush=True)
def prepare():
    b=Budget();b.recover();assert not b.snapshot()['jobs'];verify('source-contract.json')
    with job(b,'setup','独自の二状態/二出力Cと共有係数を固定',size=50000000) as j:
        bundle=HERE/'runtime-bundle';b.write(bundle/'radiation_port.py',MODULE.encode(),j);b.save(bundle/'coefficients.json',read(PREV/'coefficients.json'),j)
        with b.workspace(j,'等長状態C build専用cache',16000000,32000000) as (work,env):
            env['CLANG_MODULE_CACHE_PATH']=str(work/'clang-modules');tool='/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/clang';sdk='/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk';cmd=[tool,'-dynamiclib','-O2','-fno-modules','-isysroot',sdk,str(HERE/'radiation_port.c'),'-o',str(bundle/'radiation_port.dylib')]
            with b.external_output(bundle/'radiation_port.dylib',100000,j):out=execute(cmd,env,120)
        b.save(HERE/'build-audit.json',dict(command=cmd,stderr=out.stderr,source_sha256=digest(HERE/'radiation_port.c'),binary_sha256=digest(bundle/'radiation_port.dylib'),temporary_removed=True),j)
        b.save(bundle/'manifest.json',dict(files={str(p.relative_to(bundle)):digest(p) for p in bundle.rglob('*') if p.is_file()},HMM=False,neural=False,recording=False,utterance_lookup=False),j)
        b.save(HERE/'execution-contract.json',dict(files={str(p.relative_to(HERE)):digest(p) for p in HERE.rglob('*') if p.is_file()},controller_sha256=digest(Path(__file__)),fixed_before_science=True),j)
    print('独自等長stateと一次係数の共有bundle固定',flush=True)
def fixture():
    b=Budget();b.recover();assert not b.snapshot()['jobs'];verify('execution-contract.json')
    with job(b,'render','固定/動的反射lossの全源/参照/区切り/前半呼出し',450,90000000,1800) as r:
        with job(b,'dsp','全516行列と56信号の独立/等長/エネルギー監査',1400,3000000,1800) as d:
            with b.workspace(r,'正規化受動stateの科学依存初期化',16000000,32000000) as (_,env):
                try:out=execute([str(PYTHON),'-B',str(HERE/'worker.py'),str(HERE)],env,1500)
                except subprocess.CalledProcessError as e:b.save(HERE/'child-failure.json',dict(returncode=e.returncode,stdout=e.stdout,stderr=e.stderr),d);raise
            v=json.loads(out.stdout);assert v['passed'];b.save(HERE/'fixture-audit.json',v,d)
    with job(b,'audit','可変半径の数学的限定資格/全分母/費用/回収を封印',size=2000000) as j:
        verify('execution-contract.json')
        for n,h in read(PREV/'artifact-seal.json')['files'].items():assert digest(REPO/n)==h,n
        result=dict(v,perceptual_qualification=False,protected_confirmation_opened=False,quality_goal_completed=False,next=read(HERE/'registration.json')['next']);b.save(HERE/'aggregate-summary.json',result,j)
        lines=['# 半径変更でも受動性を保持する正規化放射状態','','[Silva et al. の因果的近似](https://arxiv.org/abs/0811.3625)の係数を保持し、独自導出の補完loss portと共通二状態を用いた。半径ごとのDF1履歴ではなく、現半径の等長4×3行列がstateを継承する。原一次反射の固定伝達を保つ。','',f'全516行列、固定32信号と動的24信号。独立行列誤差最大 {v["max_independent_matrix_error"]:.3g}、K転置Kの単位行列との差最大 {v["max_isometry_error"]:.3g}。固定反射/lossは独立bilinear/lfilterと一致。強制/無強制の累積正規化エネルギー、無強制の単調性、区切り/未来入力と半径の因果前半byte一致、不正12件拒否が通過。','',
            'Rと補完Tは全実周波数で|R|²+|T|²=1。一次の反射に一つの因果的スペクトル因子Tを付けた数学的損失portであり、実micの位置/位相/指向性を表さない。共通正規化stateの受動性を動く人体壁の物理仕事や圧力の正解へ移さない。','',
            '450render/1400DSPは独立参照と全内部呼出しを含む保守的費用。返金なし。全自分一時領域を指定外部から回収した。全旧契約・封印・不採択を保持し、日本語知覚資格なし・P5未開封・品質未達。','',result['next'],'']
        b.write(HERE/'report.md','\n'.join(lines).encode(),j);s=b.snapshot();c=s['campaigns'][NAME];tmp=[x for x in s['temporary_work'].values() if x['campaign']==NAME];assert all(x['status']=='removed' and not os.path.lexists(x['path']) for x in tmp)
        b.save(HERE/'cost-audit.json',dict(counts=c['counts'],seconds=s['seconds']-c['start_seconds'],write_bytes=s['write_bytes']-c['start_write_bytes'],temporary_owned=len(tmp),all_owned_temporary_absent=True),j)
        b.save(HERE/'artifact-seal.json',dict(files={str(p.relative_to(REPO)):digest(p) for p in HERE.rglob('*') if p.is_file()},path_base='repository',experiment_completed=True,quality_goal_completed=False,protected_confirmation_opened=False),j)
    b.close_campaign(NAME)
    with b.locked():
        s=b._load();s['continuation_checkpoint'].update(id='radiation-passive-state-completed',active_campaign=None,next=result['next'],git_save_pending=True);b._write_state(s)
    b.save(ROOT/'progress-0128.json',dict(latest_completed=NAME,next=result['next'],review=b.review_due(),quality_goal_completed=False,budget=b.reconcile()));print(dict(passed=True,conditions=56,quality_goal_completed=False),flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['register','prepare','fixture']);a=p.parse_args();globals()[a.stage]()
