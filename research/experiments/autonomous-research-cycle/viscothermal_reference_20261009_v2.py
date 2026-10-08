"""一次の粘性/熱/壁モデルをCGSとSIで独立確認し、周波数参照を固定する。"""
import argparse,ast,hashlib,json,os,subprocess
from pathlib import Path
from contextlib import contextmanager
from budget import ROOT,read,digest,encode
from research_plan_budget_20261009 import ResearchPlanBudget as Budget
from observed_process_20261009 import run_observed
REPO=ROOT.parents[2];HERE=ROOT/'campaigns/nas-viscothermal-reference-20261009-v2';NAME='viscothermal-reference-v2'
PREV=ROOT/'campaigns/nas-viscothermal-primary-source-20261009-v1'
TUBE=ROOT/'campaigns/nas-waveguide-sequence-runtime-20261008-v1'
PYTHON=REPO/'research/experiments/autonomous-speech-synthesis/.venv-eval/bin/python'
PARAM=dict(primary_CGS=dict(rho_g_cm3=1.14e-3,viscosity_dyn_s_cm2=1.86e-4,thermal_cal_cm_s_deg=5.5e-5,cp_cal_g_deg=.24,c_cm_s=35800.,wall_R_dyn_s_cm3=1400.,wall_M_dyn_s2_cm3=1.6),primary_SI=dict(rho_kg_m3=1.14,viscosity_Pa_s=1.86e-5,thermal_W_m_K=.023012,cp_J_kg_K=1004.16,c_m_s=358.,wall_R_Pa_s_m=14000.,wall_M_kg_m2=16.),main_SI=dict(rho_kg_m3=1.2,viscosity_Pa_s=1.86e-5,thermal_W_m_K=.023012,cp_J_kg_K=1004.16,c_m_s=343.,wall_R_Pa_s_m=14000.,wall_M_kg_m2=16.))
WORKER=r'''"""原CGS式とSI式、円管二port散逸、共有径の周波数参照を別計算する。"""
import sys,json,math,hashlib,os,tempfile
from pathlib import Path
import numpy as np
here=Path(sys.argv[1]);work=Path(sys.argv[2]);assert work.resolve()==Path(os.environ['TMPDIR']).resolve()==Path(tempfile.gettempdir()).resolve()
param=json.loads((here/'parameters.json').read_text());omega=2*np.pi*np.arange(70,4001,dtype=float);areas=np.linspace(.75,12.,65);modes=['lossless','air','air-wall-Suzuki']
def cgs(area_cm2,w,mode):
 p=param['primary_CGS'];A=np.asarray(area_cm2);S=2*np.sqrt(np.pi*A);L=p['rho_g_cm3']/A;C=A/(p['rho_g_cm3']*p['c_cm_s']**2)
 R=0. if mode=='lossless' else S/A**2*np.sqrt(w*p['rho_g_cm3']*p['viscosity_dyn_s_cm2']/2)
 G=0. if mode=='lossless' else .4*S/(p['rho_g_cm3']*p['c_cm_s']**2)*np.sqrt(w*p['thermal_cal_cm_s_deg']/(2*p['cp_cal_g_deg']*p['rho_g_cm3']))
 Y=0. if mode!='air-wall-Suzuki' else S/(p['wall_R_dyn_s_cm3']+1j*w*p['wall_M_dyn_s2_cm3'])
 z=R+1j*w*L;y=G+1j*w*C+Y;return np.sqrt(z*y),np.sqrt(z/y)
def si(area_cm2,w,mode,p):
 A=np.asarray(area_cm2)*1e-4;S=2*np.sqrt(np.pi*A);mass=p['rho_kg_m3']/A;compliance=A/(p['rho_kg_m3']*p['c_m_s']**2)
 r=0. if mode=='lossless' else S/(A*A)*np.sqrt(.5*w*p['rho_kg_m3']*p['viscosity_Pa_s'])
 g=0. if mode=='lossless' else S*.4/(p['rho_kg_m3']*p['c_m_s']**2)*np.sqrt(.5*w*p['thermal_W_m_K']/(p['cp_J_kg_K']*p['rho_kg_m3']))
 wall=0. if mode!='air-wall-Suzuki' else S/(p['wall_R_Pa_s_m']+1j*w*p['wall_M_kg_m2'])
 z=r+1j*w*mass;y=g+1j*w*compliance+wall;product=z*y
 gamma=np.sqrt(abs(product))*np.exp(.5j*np.angle(product));Z=z/gamma;return gamma,Z,r,g,wall
def scattering(gamma,Z,length,Zref):
 a=np.cosh(gamma*length);b=Z*np.sinh(gamma*length);c=np.sinh(gamma*length)/Z;den=2*a+b/Zref+c*Zref
 return (b/Zref-c*Zref)/den,2/den,a*a-b*c
rows=[];gammas=[];impedances=[];max_gamma_error=0.;max_Z_error=0.;max_excess=0.;points=65*len(omega)*3
for mode in modes:
 gc,zc=cgs(areas[:,None],omega[None,:],mode);gs,zs,*_=si(areas[:,None],omega[None,:],mode,param['primary_SI'])
 ge=float(np.max(abs(gs/(gc*100)-1)));ze=float(np.max(abs(zs/(zc*1e5)-1)));assert ge<=3e-13 and ze<=3e-13;max_gamma_error=max(max_gamma_error,ge);max_Z_error=max(max_Z_error,ze)
 gamma,Z,R,G,Y=si(areas[:,None],omega[None,:],mode,param['main_SI']);Zref=param['main_SI']['rho_kg_m3']*param['main_SI']['c_m_s']/(areas[:,None]*1e-4)
 reflected,transmitted,det=scattering(gamma,Z,.01,Zref);excess=float(np.max(np.maximum(abs(reflected+transmitted),abs(reflected-transmitted))**2-1.));max_excess=max(max_excess,excess)
 assert np.all(np.isfinite(gamma)) and np.all(np.isfinite(Z)) and np.min(gamma.real)>=-1e-13 and np.all(np.asarray(R)>=0.) and np.all(np.asarray(G)>=0.) and np.all(np.asarray(Y).real>=0.) and excess<=3e-12 and np.max(abs(det-1))<=3e-12
 if mode=='lossless':assert np.max(abs(gamma-1j*omega[None,:]/343))<=3e-12 and np.max(abs(reflected))<=3e-12 and np.max(abs(transmitted-np.exp(-1j*omega[None,:]*.01/343)))<=3e-12
 rows.append(dict(mode=mode,area_points=65,frequency_points=len(omega),primary_CGS_SI_gamma_relative_error=ge,primary_CGS_SI_impedance_relative_error=ze,max_two_port_power_excess=excess,max_chain_determinant_error=float(np.max(abs(det-1))),minimum_propagation_magnitude=float(np.min(np.exp(-gamma.real*.01))),maximum_propagation_magnitude=float(np.max(np.exp(-gamma.real*.01))),passed=True));gammas.append(gamma);impedances.append(Z)
# 全geometryは旧共有表。原語句や波形を読み出す計算ではない。
diam=json.loads((here/'diameters.json').read_text());curves=[];profiles=[];Rcoef=json.loads((here/'radiation-coefficients.json').read_text())['flanged'];rho=1.2;c0=343.
for vowel in 'aiueo':
 area=np.pi*(np.asarray(diam[vowel][::-1],dtype=float)/20.)**2;assert area.min()>=.75 and area.max()<=12
 radius=np.sqrt(area[-1]*1e-4/np.pi);n,d,e=Rcoef;s=1j*omega*radius/c0;Rlip=-(1+n*s)/(1+d*s+e*s*s);Zlip=rho*c0/(area[-1]*1e-4)*(1+Rlip)/(1-Rlip)
 for mode in modes:
  M=np.tile(np.eye(2,dtype=complex),(len(omega),1,1))
  for A in area:
   gamma,Z,*_=si(A,omega,mode,param['main_SI']);cell=np.empty_like(M);cell[:,0,0]=cell[:,1,1]=np.cosh(gamma*.01);cell[:,0,1]=Z*np.sinh(gamma*.01);cell[:,1,0]=np.sinh(gamma*.01)/Z;M=np.einsum('nij,njk->nik',M,cell)
  transfer=1/(M[:,1,0]*Zlip+M[:,1,1]);assert np.all(np.isfinite(transfer));curves.append(transfer);profiles.append(dict(vowel=vowel,mode=mode,sections=16,total_length_cm=16.,input='ideal prescribed Us',output='mouth U',maximum_volume_transfer_gain=float(np.max(abs(transfer))),maximum_gain_frequency_Hz=float(omega[np.argmax(abs(transfer))]/(2*np.pi)),curve_sha256=hashlib.sha256(np.asarray(transfer,dtype='<c16').tobytes()).hexdigest()))
np.savez_compressed(work/'reference-grid.npz',areas_cm2=areas,frequency_Hz=omega/(2*np.pi),modes=np.asarray(modes),gamma_m_inverse=np.stack(gammas),characteristic_impedance_Pa_s_m3=np.stack(impedances))
np.savez_compressed(work/'vowel-frequency-reference.npz',frequency_Hz=omega/(2*np.pi),profiles=np.asarray([p['vowel']+'-'+p['mode'] for p in profiles]),mouth_volume_transfer=np.stack(curves))
assert len(profiles)==15 and points==766545
# 連続Suzuki壁の最小因果一portだけ。空気損失/複素接合/声道時間音声は未実装。
from scipy import signal
fs_wall=48000.;dt=1/fs_wall;Rwall=14000.;Mwall=16.;frames=4800
rng=np.random.default_rng(17);pressure=rng.normal(size=frames);pressure[:100]=0
wall_rows=[]
for A in areas:
 circumference=2*np.sqrt(np.pi*A*1e-4);alpha=(2*Mwall-Rwall*dt)/(2*Mwall+Rwall*dt);beta=2*circumference*dt/(2*Mwall+Rwall*dt)
 def solve(values,initial):
  u=initial;mid=[]
  for p in values:
   nxt=alpha*u+beta*p;mid.append((nxt+u)/2);u=nxt
  return np.asarray(mid),u
 flow,end=solve(pressure,0.);first,state=solve(pressure[:1379],0.);last,other=solve(pressure[1379:],state)
 independent=signal.lfilter([beta/2,beta/2],[1.,-alpha],pressure)
 analytic_work=.5*Mwall/circumference*end**2+Rwall/circumference*np.sum(flow**2)*dt;actual_work=np.sum(pressure*flow)*dt
 balance=abs(actual_work-analytic_work)/max(1e-30,abs(actual_work));numeric=float(np.max(abs(flow-independent)))
 z=np.exp(-1j*omega/fs_wall);digital=beta/2*(1+z)/(1-alpha*z);warped=circumference/(Rwall+1j*2*fs_wall*Mwall*np.tan(omega/(2*fs_wall)));continuous=circumference/(Rwall+1j*omega*Mwall)
 frequency=float(np.max(abs(digital/warped-1)));deviation=float(np.max(abs(digital/continuous-1)))
 assert abs(alpha)<1 and numeric<3e-14 and balance<3e-12 and np.array_equal(flow,np.concatenate([first,last])) and end==other and np.all(flow[:100]==0.) and np.min(digital.real)>=-1e-13 and frequency<3e-12 and deviation<=.025
 wall_rows.append(dict(area_cm2=float(A),midpoint_energy_relative_error=float(balance),independent_filter_max_error=numeric,warped_frequency_relative_error=frequency,original_analog_relative_error=deviation))
causal_wall=dict(passed=True,conditions=65,rows=wall_rows,fs_Hz=fs_wall,pressure_samples=frames,maximum_original_analog_relative_error=max(x['original_analog_relative_error'] for x in wall_rows),max_energy_balance_relative_error=max(x['midpoint_energy_relative_error'] for x in wall_rows),all_zeros_prefix_and_state_chunks_exact=True,scope='Suzuki式1の壁一portだけ。Tustinの周波数ずれを明記。空気粘熱R/Gの因果近似・全複素接合・声道接続と音声は未資格。')

print(json.dumps(dict(causal_wall_only=causal_wall,frequency_reference_passed=True,rows=rows,primary_CGS_SI_units_passed=True,all_grid_points=points,max_gamma_CGS_SI_relative_error=max_gamma_error,max_impedance_CGS_SI_relative_error=max_Z_error,max_two_port_power_excess=max_excess,vowel_frequency_profiles=profiles,source_and_output_WAVs_generated=0,fit_or_inverse_runs=0,causal_time_realization_qualified=False,frequency_independent_junction_equal_to_full_loss_model=False,first_mode_cutoff_min_Hz=float(1.841*343/(2*np.pi*np.sqrt(12e-4/np.pi))),source_steady_frequency_model_not_total_human_voice=True)))
'''
@contextmanager
def job(b,kind,label,count=1,size=0,seconds=600):
    j=b.reserve(NAME,kind,label,count,size,expected_seconds=seconds)
    try:yield j
    except BaseException as e:b.finish(j,repr(e));raise
    else:b.finish(j)
def register():
    b=Budget();b.recover();assert not b.snapshot()['jobs'] and not b.review_due()['due'] and read(PREV/'aggregate-summary.json')['source_available'];ast.parse(WORKER)
    limits=dict(seconds=7200,bytes=500000000,write_bytes=1000000000,setup=20,audit=20,render=0,dsp=4000,ai=0,teacher=0,train=0,inverse=0,download=0)
    reg=dict(campaign=NAME,question='一次の粘性/熱/壁の周波数式をCGSとSIで独立再現し、正の散逸と円管二portの受動性、共有母音の周波数参照を因果実現に先立って固定できるか。',
      primary=dict(previous_seal=digest(PREV/'artifact-seal.json'),PDF=digest(PREV/'source/hayashi-miki-2008.pdf'),equation_page_image=digest(PREV/'source/page-2.png'),propagation_page_image=digest(PREV/'source/page-3.png'),DOI='10.1250/ast.29.130',PDF_page2_printed131_visually_checked=True,PDF_page3_printed132_visually_checked=True,equations=['L=rho/A','C=A/(rho*c^2)','R=(S/A^2)*sqrt(omega*rho*mu/2)','G=.4*S/(rho*c^2)*sqrt(omega*lambda/(2*cp*rho))','Ywall=S/(1400+1.6*j*omega) in CGS (Suzuki eq1)','Zc=sqrt((R+jwL)/(G+jwC+Ywall))','gamma=sqrt((R+jwL)*(G+jwC+Ywall))']),
      constants=PARAM,unit_conversions=dict(cm2_to_m2=1e-4,rho_g_cm3_to_kg_m3=1000.,dyn_s_cm2_to_Pa_s=.1,cal_cm_s_deg_to_W_m_K=418.4,cal_g_deg_to_J_kg_K=4184.,cm_s_to_m_s=.01,wall_specific_impedance_CGS_to_SI=10.,gamma_CGS_to_SI=100.,tube_characteristic_impedance_CGS_to_SI=1e5),
      choices='原論文のCGS定数をそのままSIへ変換して同一性を検証。主参照は旧SI源のrho1.2/c343を固定し、残りは一次値。wallは連続なSuzuki式1を事前選択。原論文が用いた周波数325Hzで分かれる式2や掲載MRI/fit係数/語句を再現したとは主張しない。円形S=2sqrt(pi*A)、長さ1cm。',
      fixtures=dict(areas_cm2=dict(first=.75,last=12.,points=65),frequency_Hz=dict(first=70,last=4000,step=1,points=3931),modes=['lossless','air','air-wall-Suzuki'],grid_points=766545,shared_vowels=['a','i','u','e','o'],diameters=digest(TUBE/'runtime-bundle/diameters.json'),flanged_radiation=digest(ROOT/'campaigns/nas-radiation-passive-state-20261008-v1/coefficients.json'),vowel_reference='continuous frequency-domain full lossy chain; ideal Us to mouth U; same geometry and source boundary, no WAV or fit'),
      gates=dict(causal_wall_midpoint_energy_error=3e-12,causal_wall_filter_error=3e-14,causal_wall_warped_complex_error=3e-12,causal_wall_original_analog_error=.025,causal_wall_all_65_zero_prefix_and_chunk_exact=True,CGS_SI_gamma_and_impedance_relative_error=3e-13,positive_R_G_real_wall_and_gamma=True,finite_reference_arrays=True,two_port_power_excess=3e-12,chain_determinant_error=3e-12,lossless_analytic_phase_and_no_reflection=3e-12),
      scope='周波数ごとの線形散逸/単位/連鎖参照。R,Gのsqrt(omega)を勝手にsqrt(s)と置換せず、因果時間実現は別資格。複素特性インピーダンスで接合が周波数依存となることを保持。伝搬の減衰だけを旧瞬時junctionへ足すモデルは全一次モデルと同一ではない。70..4kHz/.75..12cm²のplane-wave参照で、人の壁物性/流れ/共振の正解/声門渦/総流量/日本語品質は未資格。6kHz旧源や観測を救済しない。',
      estimates=dict(maximum_array_RAM_bytes=2000000000,causal_wall_fixture='65円管×4800pressure samples、48kHz、seed17、Suzuki式1の一portだけ。反射接合/空気粘熱/声道未接続。',process_observation_source_sha256=digest(ROOT/'observed_process_20261009.py'),render=0,DSP=1600,AI=0,train=0,inverse=0,temporary_peak=64000000,temporary_write=128000000,closeout_Git_included=True),limits=limits,controller_sha256=digest(Path(__file__)),protected_confirmation_opened=False,perceptual_qualification=False,quality_goal_completed=False,next='科学48件終了の第8回レビューを先に実施する。因果wall一portを全粘熱損失や声道時間生成の資格へ移さない。工程Bの残時間内に全複素接合を含む音声比較への見通しを判断し、見通し不足なら分布損失を副線へ移して既定VTLの共有母音標的を直接学習する。')
    b.start_campaign(NAME,str(HERE.relative_to(ROOT)),limits,hashlib.sha256(encode(reg)).hexdigest())
    with job(b,'setup','一次損失式/全CGSとSI定数/独立分母/適用帯域を出力前固定',size=3000000) as j:
        b.save(HERE/'registration.json',reg,j);b.save(HERE/'parameters.json',PARAM,j);b.write(HERE/'worker.py',WORKER.encode(),j);b.write(HERE/'diameters.json',(TUBE/'runtime-bundle/diameters.json').read_bytes(),j);b.write(HERE/'radiation-coefficients.json',(ROOT/'campaigns/nas-radiation-passive-state-20261008-v1/coefficients.json').read_bytes(),j);b.save(HERE/'source-contract.json',dict(controller_sha256=digest(Path(__file__)),files={str(p.relative_to(HERE)):digest(p) for p in HERE.rglob('*') if p.is_file()},no_scientific_outputs_yet=True),j)
    b.save(ROOT/'progress-0142.json',dict(active_campaign=NAME,next='登録push→CGS/SI/全766545周波数点/共有径15参照/因果wall65条件→全未資格/費用/回収封印→第8回レビュー',quality_goal_completed=False,budget=b.reconcile()));print('一次損失の単位と周波数参照を事前登録',flush=True)
def fixture():
    b=Budget();b.recover();assert not b.snapshot()['jobs'];c=read(HERE/'source-contract.json');assert digest(Path(__file__))==c['controller_sha256']
    for n,h in c['files'].items():assert digest(HERE/n)==h,n
    with job(b,'dsp','全CGS/SI/766545点の散逸と15母音周波数参照と因果wallを独立計算',1600,160000000,1800) as j:
        with b.workspace(j,'分布損失の純周波数参照と解析配列の科学一時領域',64000000,128000000) as (work,env):
            env.update(OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',VECLIB_MAXIMUM_THREADS='1')
            stdout,stderr,observed=run_observed([str(PYTHON),'-B',str(HERE/'worker.py'),str(HERE),str(work)],env,work,label='loss-reference',timeout=1500)
            b.save(HERE/'child-process-observation.json',observed,j)
            if observed['returncode']!=0:
                b.save(HERE/'child-failure.json',dict(observation=observed,stdout=stdout,stderr=stderr),j)
                raise RuntimeError('周波数/因果wallの子検査不通過')
            v=json.loads(stdout);assert v['frequency_reference_passed'] and v['causal_wall_only']['passed']
            for n in ('reference-grid.npz','vowel-frequency-reference.npz'):b.write_data(HERE/'reference'/n,(work/n).read_bytes(),j)
            b.save(HERE/'frequency-reference-audit.json',v,j)
    with job(b,'audit','一次周波数参照の全分母/限定受動/因果未資格/費用/回収を封印',size=2000000) as j:
        for n,h in read(PREV/'artifact-seal.json')['files'].items():assert digest(REPO/n)==h,n
        result=dict(v,protected_confirmation_opened=False,perceptual_qualification=False,quality_goal_completed=False,next=read(HERE/'registration.json')['next']);b.save(HERE/'aggregate-summary.json',result,j)
        lines=['# 一次粘性・熱・壁モデルの単位と周波数参照','','[Hayashi・Miki 2008](https://doi.org/10.1250/ast.29.130)の原131–132頁を目視し、平面波円管のL/C/R/Gと壁アドミタンス、伝搬/特性インピーダンス式を出力前に固定した。Suzuki式1の連続な壁resistance/massを選び、原論文の325Hzで分かれる式2の再現は主張しない。原CGSとSIの定数を独立に計算し、主参照では旧SI源のrho1.2/c343を保持した。','',
          f'面積65×周波数3931×3損失条件の全{v["all_grid_points"]}点。CGS/SIのgamma相対差最大{v["max_gamma_CGS_SI_relative_error"]:.3g}、特性インピーダンス差最大{v["max_impedance_CGS_SI_relative_error"]:.3g}。正のR/G/壁散逸、有限性、二port最大電力超過{v["max_two_port_power_excess"]:.3g}、連鎖determinantとlossless解析が通過。共有五母音×3条件の完全な複素lossy chain参照を保存した。','',
          '70〜4000Hz/面積.75〜12cm²の周波数参照。Suzuki壁一portだけの65条件は因果/受動/区切りを検査したが、全空気粘熱と複素接合の因果性や声道時間stateは未資格。R/Gのsqrt(omega)をsqrt(s)に置換せず、複素特性インピーダンスの接合も含めた参照と、伝搬損失だけの近似を区別する。壁定数がこの話者の実測真値とは主張しない。生成音声・fit・inverse・AIは0。','',result['next'],'','1600DSPの全費用、指定外部の解析配列と原一次資料、全自分一時回収を保持。旧全不採択/凍結・P5未開封・知覚資格なし・品質未達。',''];b.write(HERE/'report.md','\n'.join(lines).encode(),j)
        s=b.snapshot();camp=s['campaigns'][NAME];tmp=[x for x in s['temporary_work'].values() if x['campaign']==NAME];assert all(x['status']=='removed' and not os.path.lexists(x['path']) for x in tmp);b.save(HERE/'cost-audit.json',dict(counts=camp['counts'],seconds=s['seconds']-camp['start_seconds'],write_bytes=s['write_bytes']-camp['start_write_bytes'],temporary_owned=len(tmp),all_owned_temporary_absent=True),j);b.save(HERE/'artifact-seal.json',dict(files={str(p.relative_to(REPO)):digest(p) for p in HERE.rglob('*') if p.is_file()},path_base='repository',experiment_completed=True,quality_goal_completed=False,protected_confirmation_opened=False),j)
    b.close_campaign(NAME)
    with b.locked():
        s=b._load();s['continuation_checkpoint'].update(id='viscothermal-reference-completed',active_campaign=None,next=result['next'],git_save_pending=True);b._write_state(s)
    b.save(ROOT/'progress-0143.json',dict(latest_completed=NAME,next=result['next'],review=b.review_due(),quality_goal_completed=False,budget=b.reconcile()));print(dict(frequency_reference_passed=True,quality_goal_completed=False,next=result['next']),flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['register','fixture']);a=p.parse_args();globals()[a.stage]()
