"""既存教師の予測音素時計を、総時間固定の状態長目標へ移す。"""
from paths import *
from timing_control import descriptions,integer_sum,LOWER,UPPER,FEATURES
import numpy as np
def main():
 b=Budget();p=read(HERE/'protocol.json');old=read(COVERAGE/'alignment-manifest.json');alignments={r['row']['id']:r for r in old['rows']};prior={r['id']:r for r in read(COVERAGE/'target-manifest.json')['rows']};rows=[]
 with b.job(NAME,'setup','教師時計・音素長制約・80文の時間目標を固定',reserve_bytes=100000) as j:
  b.save(HERE/'target-contract.json',dict(protocol_sha256=digest(HERE/'protocol.json'),source_sha256=digest(HERE/'targets.py'),features=FEATURES,minimum_utterances=80,teacher_prediction_not_acoustic_GT=True,original96_denominator_preserved=True,phone_bounds=[LOWER,UPPER],minimum_phone_frames=5,global_frame_count_fixed=True,sil_pau_fixed=True,fit_not_started=True),j)
 for row in p['training_rows']:
  entry=alignments[row['id']];assert entry['result']['passed'] and entry['row']['text']==row['text'] and entry['row']['full_context_labels']==row['full_context_labels']
  with b.job(NAME,'dsp','教師予測時計→固定長音素・状態目標 '+row['id'],reserve_bytes=500000) as j:
   q=prior[row['id']];native=read(REPO/q['native_record']);assert digest(REPO/q['native_record'])==q['native_snapshot_sha256'];snapshot=native['snapshot'];duration=np.array(snapshot['duration'],int).reshape(-1,5);length=duration.sum(1);desc=descriptions(row);indices=[r['label_index'] for r in desc];phones={r['label_index']:r for r in entry['result']['matched']};teacher=np.array([(phones[i]['end_frame']-phones[i]['start_frame'])*5 for i in indices],float);assert np.all(teacher>=5)
   l=length[indices];lower=np.maximum(5,np.ceil(LOWER*l).astype(int));upper=np.maximum(lower,np.floor(UPPER*l).astype(int));target=integer_sum(teacher,int(l.sum()),lower,upper);ratio=np.log(target/l);assert np.isfinite(ratio).all() and np.max(abs(ratio))<=np.log(UPPER)+1e-12
   values=[dict(label_index=r['label_index'],phone=r['phone'],x=r['x'],target_log_ratio=float(y),native_frames=int(a),teacher_raw_predicted_frames=float(t),bounded_target_frames=int(o)) for r,y,a,t,o in zip(desc,ratio,l,teacher,target)]
   record=dict(id=row['id'],text=row['text'],length=row['length'],status='accepted',targets=values,native_snapshot_sha256=q['native_snapshot_sha256'],native_record=q['native_record'],native_total_frames=int(length.sum()),raw_teacher_spoken_frames=int(teacher.sum()),output_spoken_frames=int(target.sum()),native_spoken_frames=int(l.sum()),all_targets_preserved=True,teacher_prediction_not_acoustic_GT=True)
   b.save(HERE/'targets'/(row['id']+'.json'),record,j);rows.append(record)
  print('timing target',row['id'],len(values),flush=True)
 with b.job(NAME,'audit','全96履歴分母と全80整列目標を保持',reserve_bytes=4000000) as j:
  b.save(HERE/'target-manifest.json',dict(rows=rows,training_candidates_original=96,accepted_utterances=len(rows),excluded_prior_alignment_failures=p['excluded_prior_training'],accepted_targets=sum(len(r['targets']) for r in rows),fit_supported=len(rows)==80,all96_denominator_preserved=True,fit_performed=False,unknown_generated=False,quality_certified=False),j)
 print(b.reconcile(),flush=True)
if __name__=='__main__':main()
