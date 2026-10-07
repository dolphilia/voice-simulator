"""固定全区間表現で新79教師を解析し、旧17目標をhash再利用する。"""
from paths import *
import sys,numpy as np
SRC=ROOT/'campaigns/nas-source-identity-20261004-v1'
sys.path[:0]=[str(HERE),str(SRC),str(WORLD)]
from source_renderer import Engine
from world_renderer2 import log_amplitude
from local_control import describe,ELIGIBLE,FEATURES
from signal_measurement import measure_record,packed,pw
from alignment import align,tests
from scipy.io import wavfile
def projection(y):
 y=np.asarray(y,float);return y*np.minimum(1.,.5/np.maximum(np.sum(abs(y),axis=-1,keepdims=True),1e-12))
def main():
 b=Budget();p=read(HERE/'protocol.json');assert read(HERE/'teacher-reproducibility-gate.json')['passed']
 seal=read(SPECTRAL2/'artifact-seal.json');assert digest(SPECTRAL2/'artifact-seal.json')==p['dependencies'][str((SPECTRAL2/'artifact-seal.json').relative_to(REPO))]
 eye=np.zeros((8,35));eye[np.arange(8),np.arange(1,9)]=1.;basis=log_amplitude(eye)[:,:1025].T;basis-=basis.mean(0);assert np.linalg.matrix_rank(basis)==8
 with b.job(NAME,'setup','全区間targetと資料拡張gateを初解析前固定',reserve_bytes=200000) as j:
  b.save(HERE/'target-contract.json',dict(previous_target_contract=read(SPECTRAL2/'target-contract.json'),registration_sha256=digest(HERE/'registration.json'),source_sha256=digest(HERE/'targets.py'),protocol_sha256=digest(HERE/'protocol.json'),minimum_utterances=80,minimum_short=32,minimum_long=32,training_total=96,old17_reused=True,teacher_clock_central_fraction=1.,inverse_lambda=.001,L1_bound=.5,min_teacher_frames=3,alignment_tests=tests()),j)
 results=[];alignments=[]
 oldalignment={x['row']['id']:x for x in read(SPECTRAL1/'alignment-manifest.json')['rows']}
 for row in p['training_rows']:
  if row['id'] in p['original_training_ids']:
   path=SPECTRAL2/'targets'/(row['id']+'.json');assert digest(path)==seal['files'][str(path.relative_to(REPO))]
   item=read(path);assert item['status']=='accepted'
   with b.job(NAME,'setup','旧target byte再利用 '+row['id'],reserve_bytes=300000) as j:b.write(HERE/'targets'/(row['id']+'.json'),path.read_bytes(),j)
   results.append(item);alignments.append(oldalignment[row['id']]);continue
  target=HERE/'teacher/kokoro'/row['id'];meta=read(target.with_suffix('.json'));assert digest(REPO/meta['original_wav'])==meta['original_wav_sha256'];fs,x=wavfile.read(REPO/meta['wav']);assert fs==24000 and digest(REPO/meta['wav'])==meta['wav_sha256']
  with b.job(NAME,'dsp','固定教師clock/IPA全列照合 '+row['id'],reserve_bytes=300000) as j:
   try:aligned=align(row,meta,len(x))
   except (ValueError,AssertionError) as exc:aligned=dict(passed=False,reason=repr(exc),clock_exact=False)
   aligned.update(id=row['id'],text=row['text'],length=row['length'],teacher_metadata_sha256=digest(target.with_suffix('.json')),teacher_wav_sha256=meta['wav_sha256']);b.save(HERE/'alignment'/(row['id']+'.json'),aligned,j)
  alignments.append(dict(row=row,result=aligned));item=dict(id=row['id'],text=row['text'],length=row['length'],status='failed',alignment_pass=aligned['passed'],reason=aligned.get('reason'))
  if aligned['passed']:
   record=measure_record(b,row,target.with_suffix('.json'));dio=np.load(REPO/record['DIO_file']);f0,t=dio['f0'],dio['times']
   with b.job(NAME,'dsp','教師CheapTrick/native MCP '+row['id'],count=2,reserve_bytes=40000000) as j:
    sp=pw.cheaptrick(x.astype(float),f0,t,24000,fft_size=2048);assert sp.shape==(len(t),1025) and np.isfinite(sp).all() and np.min(sp)>0
    with Engine(row,BUNDLE/'mei_normal.htsvoice',speed=1.,half_tone=0.) as e:snapshot=e.snapshot();params=e.parameters();settings=e.get_settings();assert e.snapshot()==snapshot
    lengths=np.array(snapshot['duration'],int).reshape(-1,5).sum(1);edges=np.r_[0,np.cumsum(lengths)];assert edges[-1]==len(params[0])
    native_path=HERE/'native'/(row['id']+'.parameters.npz');b.write(native_path,packed(mcp=params[0],lf0=params[1],lpf=params[2],phone_frames=lengths),j);b.write(target.with_suffix('.power.npz'),packed(power=sp,times=t,f0=f0),j)
    native_record=HERE/'native'/(row['id']+'.json');b.save(native_record,dict(row,snapshot=snapshot,settings=settings,parameters=str(native_path.relative_to(REPO)),parameters_sha256=digest(native_path)),j)
   with b.job(NAME,'inverse','固定8基底の全対象phone投影 '+row['id'],reserve_bytes=500000) as j:
    phone_map={r['label_index']:r for r in aligned['matched']};targets=[];missing=[]
    for r in describe(row):
     i=r['label_index']
     if r['phone'] not in ELIGIBLE or not any(snapshot['msd'][s]>.5 for s in range(i*5,(i+1)*5)):continue
     q=phone_map[i];lo=q['start_seconds'];hi=q['end_seconds'];mask=(t>=lo)&(t<hi)
     if sum(mask)<3:missing.append(dict(label_index=i,phone=r['phone'],available_frames=int(sum(mask))));continue
     teacher=.5*np.log(np.median(sp[mask],axis=0));teacher-=teacher.mean();baseline=log_amplitude(np.mean(params[0][edges[i]:edges[i+1]],axis=0,keepdims=True))[0,:1025];baseline-=baseline.mean();residual=teacher-baseline
     coef=np.linalg.solve(basis.T@basis/1025+.001*np.eye(8),basis.T@residual/1025);bounded=projection(coef[None,:])[0]
     targets.append(dict(label_index=i,phone=r['phone'],x=r['x'],target_coefficients=bounded.tolist(),inverse_raw_coefficients=coef.tolist(),L1_projection_active=bool(np.sum(abs(coef))>.5),teacher_window=[lo,hi],teacher_frames=int(sum(mask)),baseline_centered_logamp_RMSE=float(np.sqrt(np.mean(residual**2))),target_centered_logamp_RMSE=float(np.sqrt(np.mean((residual-basis@bounded)**2))),source_prediction_not_acoustic_GT=True))
    item.update(status='accepted' if targets and not missing else 'failed',targets=targets,missing=missing,reason='全対象予測区間スペクトル窓成立' if targets and not missing else '対象区間不足',native_record=str(native_record.relative_to(REPO)),native_snapshot_sha256=digest(native_record),teacher_record=str(target.with_suffix('.measured.json').relative_to(REPO)),teacher_record_sha256=digest(target.with_suffix('.measured.json')),target_frame_clock_verified=True)
  with b.job(NAME,'setup','target結果・失敗を保存 '+row['id'],reserve_bytes=500000) as j:b.save(HERE/'targets'/(row['id']+'.json'),item,j)
  results.append(item);print('target',row['id'],item['status'],len(item.get('targets',[])),flush=True)
 accepted=[r for r in results if r['status']=='accepted'];vowels={q['phone'] for r in accepted for q in r['targets']};gate=len(accepted)>=80 and sum(r['length']=='short' for r in accepted)>=32 and sum(r['length']=='long' for r in accepted)>=32 and set('aiueo')<=vowels
 with b.job(NAME,'audit','全96分母・固定gate集計',reserve_bytes=15000000) as j:
  b.save(HERE/'alignment-manifest.json',dict(rows=alignments,training_total=96,aligned=sum(r['result']['passed'] for r in alignments),alignment_not_acoustic_ground_truth=True),j)
  b.save(HERE/'target-manifest.json',dict(rows=results,all_96_denominator_preserved=True,accepted_utterances=len(accepted),accepted_targets=sum(len(r['targets']) for r in accepted),accepted_short=sum(r['length']=='short' for r in accepted),accepted_long=sum(r['length']=='long' for r in accepted),vowels=sorted(vowels),fit_supported=gate,old17_targets_reused=True,internal_prediction_alignment_not_acoustic_GT=True,inverse_control_is_not_waveform_quality_evidence=True,fit_performed=False,unknown_generated=False),j)
 print('target gate',gate,len(accepted),flush=True);print(b.reconcile(),flush=True)
if __name__=='__main__':main()
