"""全音素対応した教師スペクトルを、固定8係数残差へ解析投影する。"""
from paths import *
import sys
SRC=ROOT/'campaigns/nas-source-identity-20261004-v1'
sys.path[:0]=[str(HERE),str(SRC),str(WORLD)]
from source_renderer import Engine
from world_renderer2 import log_amplitude
from local_control import describe,ELIGIBLE,FEATURES
from signal_measurement import measure_record,packed,pw,np
from teacher_common import canonical,wavbytes
from scipy.io import wavfile

def projection(y):
 y=np.asarray(y,float);scale=np.minimum(1.,.5/np.maximum(np.sum(abs(y),axis=-1,keepdims=True),1e-12));return y*scale

def main():
 b=Budget();a=read(HERE/'alignment-manifest.json');results=[]
 eye=np.zeros((8,35));eye[np.arange(8),np.arange(1,9)]=1.;basis=log_amplitude(eye)[:,:1025].T;basis-=basis.mean(0);rank=int(np.linalg.matrix_rank(basis));assert rank==8
 with b.job(NAME,'setup','スペクトル投影基底・解析・gateを入力前固定',reserve_bytes=100000) as j:
  b.save(HERE/'target-contract.json',dict(registration_sha256=digest(HERE/'registration.json'),alignment_manifest_sha256=digest(HERE/'alignment-manifest.json'),source_sha256=digest(HERE/'targets.py'),source_renderer_sha256=digest(SRC/'source_renderer.py'),world_conversion_source_sha256=digest(WORLD/'world_renderer2.py'),source_library_sha256=digest(SRC/'counter.dylib'),local_engine_source_sha256=digest(SRC/'local_renderer.py'),local_engine_library_sha256=digest(SRC/'local_hts-v2.dylib'),voice_sha256=digest(BUNDLE/'mei_normal.htsvoice'),features=FEATURES,coefficients=list(range(1,9)),alpha=.55,FFT48k=4096,FFT24k=2048,frequency_bins=1025,basis_rank=rank,centered_frequency_power=True,inverse_lambda=.001,coefficient_L1_bound=.5,teacher_clock_central_fraction=.5,min_teacher_frames=3,minimum_utterances=12,minimum_short=5,minimum_long=3,target_is_internal_prediction_aligned_diagnostic=True,fit_not_started=True),j)
 for entry in a['rows']:
  row,aligned=entry['row'],entry['result'];target=HERE/'teacher/kokoro'/row['id'];item=dict(id=row['id'],text=row['text'],length=row['length'],status='failed',alignment_pass=aligned['passed'],reason=aligned.get('reason'))
  if aligned['passed']:
   with b.job(NAME,'dsp','教師canonical入口 '+row['id'],reserve_bytes=3000000) as j:
    assert digest(REPO/row['teacher_wav'])==row['teacher_wav_sha256'];fs,raw=wavfile.read(REPO/row['teacher_wav']);assert fs==24000;x,n=canonical(raw,fs);b.write(target.with_suffix('.wav'),wavbytes(x),j)
    b.save(target.with_suffix('.json'),dict(row,id=row['id']+'/neutral/kokoro',condition='neutral',variant='kokoro',mode='teacher',factor=0,status='generated',wav=str(target.with_suffix('.wav').relative_to(REPO)),wav_sha256=digest(target.with_suffix('.wav')),normalization=n,original_teacher_wave_sha256=row['teacher_wav_sha256'],new_teacher_calls=0,research_only=True,quality_certified=False),j)
   record=measure_record(b,row,target.with_suffix('.json'));dio=np.load(REPO/record['DIO_file']);f0,t=dio['f0'],dio['times']
   with b.job(NAME,'dsp','教師CheapTrickとnative MCP '+row['id'],count=2,reserve_bytes=40000000) as j:
    sp=pw.cheaptrick(x.astype(float),f0,t,24000,fft_size=2048);assert sp.shape==(len(t),1025) and np.isfinite(sp).all() and np.min(sp)>0
    with Engine(row,BUNDLE/'mei_normal.htsvoice',speed=1.,half_tone=0.) as e:
     snapshot=e.snapshot();params=e.parameters();settings=e.get_settings();assert e.snapshot()==snapshot
    lengths=np.array(snapshot['duration'],int).reshape(-1,5).sum(1);edges=np.r_[0,np.cumsum(lengths)];assert edges[-1]==len(params[0])
    b.write(HERE/'native'/(row['id']+'.parameters.npz'),packed(mcp=params[0],lf0=params[1],lpf=params[2],phone_frames=lengths),j);b.write(target.with_suffix('.power.npz'),packed(power=sp,times=t,f0=f0),j)
    b.save(HERE/'native'/(row['id']+'.json'),dict(row,snapshot=snapshot,settings=settings,parameters=str((HERE/'native'/(row['id']+'.parameters.npz')).relative_to(REPO)),parameters_sha256=digest(HERE/'native'/(row['id']+'.parameters.npz'))),j)
   with b.job(NAME,'inverse','固定8基底への全対象phone投影 '+row['id'],reserve_bytes=300000) as j:
    descriptions=describe(row);phone_map={r['label_index']:r for r in aligned['matched']};targets=[];missing=[]
    for r in descriptions:
     i=r['label_index']
     if r['phone'] not in ELIGIBLE or not any(snapshot['msd'][s]>.5 for s in range(i*5,(i+1)*5)):continue
     q=phone_map[i];start=q['start_seconds'];end=q['end_seconds'];lo=start+.25*(end-start);hi=end-.25*(end-start);mask=(t>=lo)&(t<hi)
     if sum(mask)<3:missing.append(dict(label_index=i,phone=r['phone'],available_frames=int(sum(mask))));continue
     teacher=.5*np.log(np.median(sp[mask],axis=0));teacher-=teacher.mean();native=log_amplitude(np.mean(params[0][edges[i]:edges[i+1]],axis=0,keepdims=True))[0,:1025];native-=native.mean();residual=teacher-native
     coef=np.linalg.solve(basis.T@basis/1025+.001*np.eye(8),basis.T@residual/1025);bounded=projection(coef[None,:])[0];assert np.sum(abs(bounded))<=.5+1e-12
     targets.append(dict(label_index=i,phone=r['phone'],x=r['x'],target_coefficients=bounded.tolist(),inverse_raw_coefficients=coef.tolist(),L1_projection_active=bool(np.sum(abs(coef))>.5),teacher_window=[lo,hi],teacher_frames=int(sum(mask)),baseline_centered_logamp_RMSE=float(np.sqrt(np.mean(residual**2))),target_centered_logamp_RMSE=float(np.sqrt(np.mean((residual-basis@bounded)**2))),source_prediction_not_acoustic_GT=True))
    item.update(status='accepted' if targets and not missing else 'failed',targets=targets,missing=missing,reason='全対象中央スペクトル窓成立' if targets and not missing else '対象区間不足',native_snapshot_sha256=digest(HERE/'native'/(row['id']+'.json')),teacher_record_sha256=digest(target.with_suffix('.measured.json')),target_frame_clock_verified=True)
    b.save(HERE/'targets'/(row['id']+'.json'),item,j)
  results.append(item);print('target',row['id'],item['status'],len(item.get('targets',[])),flush=True)
 accepted=[r for r in results if r['status']=='accepted'];vowels={q['phone'] for r in accepted for q in r['targets']};gate=len(accepted)>=12 and sum(r['length']=='short' for r in accepted)>=5 and sum(r['length']=='long' for r in accepted)>=3 and set('aiueo')<=vowels
 b.save(HERE/'target-manifest.json',dict(rows=results,all_17_denominator_preserved=True,accepted_utterances=len(accepted),accepted_targets=sum(len(r['targets']) for r in accepted),vowels=sorted(vowels),fit_supported=gate,internal_prediction_alignment_not_acoustic_GT=True,inverse_control_is_not_waveform_quality_evidence=True,fit_performed=False,unknown_generated=False));print('target gate',gate,flush=True);print(b.reconcile(),flush=True)
if __name__=='__main__':main()
