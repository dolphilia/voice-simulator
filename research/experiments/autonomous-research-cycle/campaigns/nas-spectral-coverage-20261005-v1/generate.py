"""旧2教師のraw byte再現を確認してから、新79教師を生成する。"""
from paths import *
from teacher_common import canonical,wavbytes
from kokoro_loader import load_teacher
import numpy as np,time,hashlib
def main():
 b=Budget();p=read(HERE/'protocol.json')
 with b.job(NAME,'setup','同一Kokoro/声/G2Pを読込、取得0',reserve_bytes=100000) as j:
  model,voice,g2p=load_teacher()
  import torch
  assert torch.get_num_threads()==4
  b.save(HERE/'teacher-contract.json',dict(weight_checks=model.load_audit,loader_sha256=digest(HERE/'kokoro_loader.py'),seed=20261002,CPU_threads=4,pronunciation_repair=False,model_sha256=digest(PILOT/'.cache/teacher/kokoro-v1_0.pth'),voice_sha256=digest(PILOT/'.cache/teacher/voices/jf_alpha.pt'),config_sha256=digest(PILOT/'.cache/teacher/config.json'),G2P_source_sha256=digest(PILOT/'.cache/packages/misaki/cutlet.py'),offline=True),j)
 checks=[]
 oldrows=[r for r in p['training_rows'] if r['id'] in p['original_training_ids']]
 for row in oldrows[:2]:
  with b.job(NAME,'teacher','旧教師raw再現gate '+row['id'],reserve_bytes=5000000) as j:
   meta=read(REPO/row['teacher_metadata']);assert digest(REPO/row['teacher_metadata'])==row['teacher_metadata_sha256'];phones,tokens=g2p(row['text']);assert phones==meta['phonemes'];torch.manual_seed(20261002);out=model(phones,voice[len(phones)-1],speed=1.,return_output=True);raw=out.audio.numpy().astype(np.float32);data=wavbytes(raw);expected=row['teacher_wav_sha256'];actual=hashlib.sha256(data).hexdigest();path=HERE/'reproducibility'/(row['id']+'.wav');b.write(path,data,j)
   result=dict(id=row['id'],expected_sha256=expected,actual_sha256=actual,raw_wave_bitmatch=expected==actual,duration_prediction_equal=out.pred_dur.tolist()==meta['predicted_duration_frames']);b.save(path.with_suffix('.json'),result,j);checks.append(result)
  assert all(q['raw_wave_bitmatch'] and q['duration_prediction_equal'] for q in checks),'旧教師の再現gate不通過：新教師前停止'
 b.save(HERE/'teacher-reproducibility-gate.json',dict(checks=checks,passed=True,new_teacher_not_yet_generated=True))
 for row in [r for r in p['training_rows'] if r['id'] not in p['original_training_ids']]:
  target=HERE/'teacher/kokoro'/row['id']
  if target.with_suffix('.json').exists():continue
  with b.job(NAME,'teacher','新訓練Kokoro '+row['id'],reserve_bytes=8000000) as j:
   phones,tokens=g2p(row['text']);assert not (set(phones)-set(model.vocab));assert 1<=len(phones)<=510;torch.manual_seed(20261002);start=time.monotonic();out=model(phones,voice[len(phones)-1],speed=1.,return_output=True);raw=out.audio.numpy();assert np.isfinite(raw).all() and np.max(abs(raw))<1;x,n=canonical(raw,24000)
   original=target.with_suffix('.original.wav');b.write(original,wavbytes(raw.astype(np.float32)),j);b.write(target.with_suffix('.wav'),wavbytes(x),j)
   b.save(target.with_suffix('.json'),dict(row,id=row['id']+'/neutral/kokoro',variant='kokoro',mode='teacher',factor=0,condition='neutral',status='generated',wav=str(target.with_suffix('.wav').relative_to(REPO)),wav_sha256=digest(target.with_suffix('.wav')),original_wav=str(original.relative_to(REPO)),original_wav_sha256=digest(original),normalization=n,phonemes=phones,predicted_duration_frames=out.pred_dur.tolist(),internal_prediction_not_acoustic_ground_truth=True,new_teacher_calls=1,seed=20261002,seconds=time.monotonic()-start,research_only=True,quality_certified=False),j)
  print('teacher',row['id'],len(x)/24000,flush=True)
 print(b.reconcile(),flush=True)
if __name__=='__main__':main()
