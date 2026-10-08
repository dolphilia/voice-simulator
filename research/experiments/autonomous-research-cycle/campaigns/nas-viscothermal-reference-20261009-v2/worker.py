"""原CGS式とSI式、円管二port散逸、共有径の周波数参照を別計算する。"""
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
