"""既存解析を再利用し、予測音素全区間の表現を別登録で検査する。"""
from paths import *
import sys,numpy as np
sys.path.insert(0,str(WORLD))
from world_renderer2 import log_amplitude
from local_control import describe,ELIGIBLE,FEATURES

def projection(y):
 y=np.asarray(y,float);return y*np.minimum(1.,.5/np.maximum(np.sum(abs(y),axis=-1,keepdims=True),1e-12))
def main():
 b=Budget();ref=read(HERE/'alignment-manifest-reference.json');assert digest(REPO/ref['path'])==ref['sha256'] and digest(SPECTRAL1/'artifact-seal.json')==ref['previous_seal_sha256'];seal=read(SPECTRAL1/'artifact-seal.json');a=read(REPO/ref['path']);results=[]
 def verified(path):assert digest(path)==seal['files'][str(path.relative_to(REPO))];return path
 eye=np.zeros((8,35));eye[np.arange(8),np.arange(1,9)]=1.;basis=log_amplitude(eye)[:,:1025].T;basis-=basis.mean(0);assert np.linalg.matrix_rank(basis)==8
 with b.job(NAME,'setup','全区間目標の基底・旧解析参照・gateを凍結',reserve_bytes=100000) as j:
  old=read(SPECTRAL1/'target-contract.json');b.save(HERE/'target-contract.json',dict(old,registration_sha256=digest(HERE/'registration.json'),source_sha256=digest(HERE/'targets.py'),teacher_clock_central_fraction=1.,reused_analysis_seal_sha256=ref['previous_seal_sha256'],reused_alignment_manifest_sha256=ref['sha256'],no_fit_or_generation_before_gate=True),j)
 for entry in a['rows']:
  row,aligned=entry['row'],entry['result'];item=dict(id=row['id'],text=row['text'],length=row['length'],status='failed',alignment_pass=aligned['passed'],reason=aligned.get('reason'))
  with b.job(NAME,'inverse','全予測区間の固定8係数投影 '+row['id'],reserve_bytes=300000) as j:
   native=read(verified(SPECTRAL1/'native'/(row['id']+'.json')));snapshot=native['snapshot'];p=np.load(verified(REPO/native['parameters']));mcp=p['mcp'];lengths=p['phone_frames'];edges=np.r_[0,np.cumsum(lengths)];assert edges[-1]==len(mcp)
   power=np.load(verified(SPECTRAL1/'teacher/kokoro'/(row['id']+'.power.npz')));sp,t=power['power'],power['times'];assert np.isfinite(sp).all() and np.min(sp)>0
   descriptions=describe(row);phone_map={r['label_index']:r for r in aligned['matched']};targets=[];missing=[]
   for r in descriptions:
    i=r['label_index']
    if r['phone'] not in ELIGIBLE or not any(snapshot['msd'][s]>.5 for s in range(i*5,(i+1)*5)):continue
    q=phone_map[i];lo=q['start_seconds'];hi=q['end_seconds'];mask=(t>=lo)&(t<hi)
    if sum(mask)<3:missing.append(dict(label_index=i,phone=r['phone'],available_frames=int(sum(mask))));continue
    teacher=.5*np.log(np.median(sp[mask],axis=0));teacher-=teacher.mean();baseline=log_amplitude(np.mean(mcp[edges[i]:edges[i+1]],axis=0,keepdims=True))[0,:1025];baseline-=baseline.mean();residual=teacher-baseline
    coef=np.linalg.solve(basis.T@basis/1025+.001*np.eye(8),basis.T@residual/1025);bounded=projection(coef[None,:])[0];assert np.sum(abs(bounded))<=.5+1e-12
    targets.append(dict(label_index=i,phone=r['phone'],x=r['x'],target_coefficients=bounded.tolist(),inverse_raw_coefficients=coef.tolist(),L1_projection_active=bool(np.sum(abs(coef))>.5),teacher_window=[lo,hi],teacher_frames=int(sum(mask)),baseline_centered_logamp_RMSE=float(np.sqrt(np.mean(residual**2))),target_centered_logamp_RMSE=float(np.sqrt(np.mean((residual-basis@bounded)**2))),source_prediction_not_acoustic_GT=True))
   item.update(status='accepted' if targets and not missing else 'failed',targets=targets,missing=missing,reason='全対象予測区間スペクトル窓成立' if targets and not missing else '対象区間不足',native_record=str((SPECTRAL1/'native'/(row['id']+'.json')).relative_to(REPO)),native_snapshot_sha256=digest(SPECTRAL1/'native'/(row['id']+'.json')),teacher_record=str((SPECTRAL1/'teacher/kokoro'/(row['id']+'.measured.json')).relative_to(REPO)),teacher_record_sha256=digest(verified(SPECTRAL1/'teacher/kokoro'/(row['id']+'.measured.json'))),target_frame_clock_verified=True,analysis_reused_not_independent=True)
   b.save(HERE/'targets'/(row['id']+'.json'),item,j)
  results.append(item);print('whole target',row['id'],item['status'],len(targets),flush=True)
 accepted=[r for r in results if r['status']=='accepted'];vowels={q['phone'] for r in accepted for q in r['targets']};gate=len(accepted)>=12 and sum(r['length']=='short' for r in accepted)>=5 and sum(r['length']=='long' for r in accepted)>=3 and set('aiueo')<=vowels
 b.save(HERE/'target-manifest.json',dict(rows=results,all_17_denominator_preserved=True,accepted_utterances=len(accepted),accepted_targets=sum(len(r['targets']) for r in accepted),vowels=sorted(vowels),fit_supported=gate,internal_prediction_alignment_not_acoustic_GT=True,inverse_control_is_not_waveform_quality_evidence=True,fit_performed=False,unknown_generated=False,previous_central_50_gate_failed=True));print('target gate',gate,flush=True);print(b.reconcile(),flush=True)
if __name__=='__main__':main()
