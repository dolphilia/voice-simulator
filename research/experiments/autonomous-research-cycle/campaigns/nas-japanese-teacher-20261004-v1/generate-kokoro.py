"""Kokoroは旧4先生を再利用し、固定新8先生だけ生成する。"""
from paths import *
from teacher_common import canonical,wavbytes
import numpy as np,torch,time
from scipy.io import wavfile
from kokoro_loader import load_teacher

def main():
 b=Budget();p=read(HERE/'protocol.json')
 for row in p['rows'][:4]:
  target=HERE/'teacher/kokoro'/row['id']
  if target.with_suffix('.json').exists():continue
  with b.job(NAME,'dsp','旧Kokoroキャッシュ単位/共通利得 '+row['id'],reserve_bytes=4000000) as j:
   source=REPO/row['old_teacher_wav'];assert digest(source)==row['old_teacher_wav_sha256'];fs,raw=wavfile.read(source);x,n=canonical(raw,fs);b.write(target.with_suffix('.wav'),wavbytes(x),j)
   b.save(target.with_suffix('.json'),dict(row,id=row['id']+'/neutral/kokoro',variant='kokoro',mode='teacher',factor=0,condition='neutral',status='generated',wav=str(target.with_suffix('.wav').relative_to(REPO)),wav_sha256=digest(target.with_suffix('.wav')),normalization=n,old_teacher_cache_reused=True,new_teacher_calls=0,original_teacher_metadata=row['old_teacher_metadata'],original_teacher_seed=read(REPO/row['old_teacher_metadata'])['seed'],source_sha256=digest(source),research_only=True,quality_certified=False),j)
 with b.job(NAME,'setup','固定Kokoro/voice/G2P読込、追加取得なし',reserve_bytes=20000) as j:
  model,voice,g2p=load_teacher();torch.set_num_threads(2);b.save(HERE/'kokoro-load-audit.json',{'weight_checks':model.load_audit,'old_loader_source_sha256':digest(PILOT/'teacher.py'),'extracted_loader_sha256':digest(HERE/'kokoro_loader.py'),'new_teacher_seed':42,'CPU_threads':2,'no_pronunciation_repair':True},j)
 for row in p['rows'][4:]:
  target=HERE/'teacher/kokoro'/row['id']
  if target.with_suffix('.json').exists():continue
  with b.job(NAME,'teacher','Kokoro先生 '+row['id'],reserve_bytes=8000000) as j:
   phones,tokens=g2p(row['text']);assert not (set(phones)-set(model.vocab));torch.manual_seed(42);start=time.monotonic();output=model(phones,voice[len(phones)-1],speed=1.,return_output=True);raw=output.audio.numpy();x,n=canonical(raw,24000)
   b.write(target.with_suffix('.original.wav'),wavbytes(raw.astype(np.float32)),j);b.write(target.with_suffix('.wav'),wavbytes(x),j)
   b.save(target.with_suffix('.json'),dict(row,id=row['id']+'/neutral/kokoro',variant='kokoro',mode='teacher',factor=0,condition='neutral',status='generated',wav=str(target.with_suffix('.wav').relative_to(REPO)),wav_sha256=digest(target.with_suffix('.wav')),normalization=n,phonemes=phones,predicted_duration_frames=output.pred_dur.tolist(),internal_prediction_not_acoustic_ground_truth=True,old_teacher_cache_reused=False,new_teacher_calls=1,seed=42,seconds=time.monotonic()-start,research_only=True,quality_certified=False),j)
  print('teacher kokoro',row['id'],flush=True)
 print(b.reconcile(),flush=True)
if __name__=='__main__':main()
