"""JVNV固定先生を生成し、内部attentionは研究用の予測として保存する。"""
from paths import *
from jvnv_loader2 import load,Languages,torch,np
from teacher_common import canonical,wavbytes
from style_bert_vits2.nlp.symbols import SYMBOLS
import time,hashlib

def main():
 b=Budget();p=read(HERE/'protocol.json');cfg=read(HERE/'registration.json')['teacher_settings']
 with b.job(NAME,'setup','JVNV教師再読込と固定推論重み再照合',reserve_bytes=10000):
  model,audit=load();prior=read(HERE/'teacher-load-audit.json')
  # 重み照合で得た未保存の学習専用キー集合だけを順序非依存にする。
  for value in (audit,prior):
   for weight in value['weights'].values():weight['training_only_unstored']=sorted(weight['training_only_unstored'])
  assert audit==prior
 original=model.net_g.infer;captured={}
 def infer(*args,**kw):
  out=original(*args,**kw);attn=out[1].detach().cpu();assert attn.ndim==4 and attn.shape[:2]==(1,1)
  captured.clear();captured.update(phone_ids=args[0][0].detach().cpu().tolist(),tone_ids=args[3][0].detach().cpu().tolist(),predicted_phone_duration_frames=attn[0,0].sum(dim=0).tolist(),predicted_total_frames=attn.shape[2],raw_peak_before_TTSModel_PCM_normalization=float(out[0].abs().max()))
  assert len(captured['phone_ids'])==len(captured['predicted_phone_duration_frames']);captured['symbols']=[SYMBOLS[k] for k in captured['phone_ids']];return out
 model.net_g.infer=infer
 for row in p['rows']:
  target=HERE/'teacher/jvnv'/row['id']
  if target.with_suffix('.json').exists():continue
  with b.job(NAME,'teacher','JVNV先生 '+row['id'],reserve_bytes=8000000) as j:
   torch.manual_seed(cfg['seed']);start=time.monotonic();fs,raw=model.infer(text=row['text'],language=Languages.JP,speaker_id=0,reference_audio_path=None,sdp_ratio=cfg['sdp_ratio'],noise=cfg['noise'],noise_w=cfg['noise_w'],length=cfg['length'],line_split=False,assist_text=None,style=cfg['style'],style_weight=cfg['style_weight'],pitch_scale=1.,intonation_scale=1.)
   assert fs==44100;assert len(raw)==captured['predicted_total_frames']*512
   x,n=canonical(raw,fs);b.write(target.with_suffix('.original.wav'),wavbytes(raw,fs),j);b.write(target.with_suffix('.wav'),wavbytes(x),j)
   b.save(target.with_suffix('.json'),dict(row,id=row['id']+'/neutral/jvnv',variant='jvnv',mode='teacher',factor=0,condition='neutral',status='generated',wav=str(target.with_suffix('.wav').relative_to(REPO)),wav_sha256=digest(target.with_suffix('.wav')),normalization=n,internal_prediction=captured.copy(),internal_prediction_not_acoustic_ground_truth=True,prediction_hop_samples=512,prediction_fs=44100,original_teacher_PCM_normalization='公式TTSModel.inferのpeak divide×32767→int16。別教師とは内部正規化が異なる',new_teacher_calls=1,seed=cfg['seed'],seconds=time.monotonic()-start,research_only=True,quality_certified=False),j)
  print('teacher jvnv',row['id'],flush=True)
 print(b.reconcile(),flush=True)
if __name__=='__main__':main()
