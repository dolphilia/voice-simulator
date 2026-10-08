"""共有生成器の通常/隔離バッチと単独CLI。入力以外の発話資産を読まない。"""
import sys,json,os,io,hashlib,tempfile,argparse,subprocess
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--bundle',type=Path,required=True);p.add_argument('--input',type=Path,required=True);p.add_argument('--single',action='store_true');a=p.parse_args()
work=Path(os.environ['TMPDIR']).resolve();assert work==Path(tempfile.gettempdir()).resolve() and a.input.parent.resolve()==work
requests=json.loads(a.input.read_text());assert len(requests)==1 if a.single else len(requests)>0
sys.path.insert(0,str(a.bundle))
method=requests[0]['method'];assert all(q['method']==method for q in requests)
if method=='native':
 from runtime import generate,verify
 verify()
elif not a.single:
 from cv_runtime import CV
from acoustics import evaluate
import numpy as np
from scipy.io import wavfile
rows=[];calls=0;dsp=0
for q in requests:
 assert q['method'] in ['native','baseline','learned']
 out=work/(q['file_id']+'.wav');assert not out.exists()
 data=None;meta={}
 try:
  if method=='native':
   data,meta=generate(q['text'],q['speed'],q['F0_Hz']);calls+=meta['conversion']['render_calls_including_internal_MLSA'];dsp+=3
  elif a.single:
   # 既存の公開引数形式のCV CLIを実際に別子processで呼ぶ。
   qout=subprocess.run([sys.executable,'-B',str(a.bundle/'cv_cli.py'),'--text',q['kana'],'--F0',str(q['F0_Hz']),'--speed',str(q['speed']),'--mode',method,'--seed','41','--output',str(out)],env=os.environ,check=True,capture_output=True,text=True,timeout=600)
   meta=json.loads(qout.stdout);data=out.read_bytes();calls+=meta['render_calls']
  else:
   v=CV()
   try:data,meta=v.render_text(q['kana'],q['F0_Hz'],q['speed'],method=='learned',41);calls+=meta['render_calls']
   finally:v.close()
 except ValueError as e:
  if method!='native' or str(e)!='LF0 sentinelまたは有声F0範囲が不正':raise
  meta=dict(error=str(e),status='native_parameter_domain_failed')
 if data is not None:
  if not out.exists():out.write_bytes(data)
  # ファイルclose後、所有WAVを再読取りしてhash/型/全E0を確認する。
  reread=out.read_bytes();assert reread==data
  fs,audio=wavfile.read(io.BytesIO(reread));assert fs==24000 and audio.dtype==np.float32 and audio.ndim==1
  e0=evaluate(audio,{},fs);dsp+=3;h=hashlib.sha256(reread).hexdigest()
  assert h==meta.get('sha256',meta.get('wav_sha256'))
  row=dict(request=q,status='generated',meta=meta,E0=e0,wav_sha256=h,file=out.name)
 else:row=dict(request=q,status='native_parameter_domain_failed',meta=meta,E0=None,wav_sha256=None,file=None)
 rows.append(row)
 (work/('partial-'+method+'.json')).write_text(json.dumps(dict(rows=rows,calls=calls,DSP=dsp),ensure_ascii=False,allow_nan=False))
forbidden=[n for n in sys.modules if n.split('.')[0] in ['torch','tensorflow','transformers','faster_whisper','ctranslate2','onnxruntime','sherpa_onnx']]
assert not forbidden
print(json.dumps(dict(rows=rows,calls=calls,DSP=dsp,forbidden_imports=forbidden,close_then_self_read=True),ensure_ascii=False,allow_nan=False))
