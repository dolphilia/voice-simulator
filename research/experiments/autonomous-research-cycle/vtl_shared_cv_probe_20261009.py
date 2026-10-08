"""三CVの通常/隔離/CLIと静的係数再現、close後自己WAV再読取を検査。"""
import argparse,hashlib,json,os,socket,subprocess,sys,tempfile
from pathlib import Path
from scipy.io import wavfile
from cv_runtime import CV
from acoustics import evaluate
p=argparse.ArgumentParser();p.add_argument('work');p.add_argument('--mode',choices=['normal','isolated','cli'],required=True);p.add_argument('--blocked',default='[]');a=p.parse_args();work=Path(a.work);assert work.resolve()==Path(os.environ['TMPDIR']).resolve()==Path(tempfile.gettempdir()).resolve()
rows=[];v=None
try:
 if a.mode!='cli':v=CV()
 for token,text in [('ka','カ'),('chi','チ'),('su','ス')]:
  for learned in [False,True]:
   ident=token+'-'+('learned' if learned else 'baseline');path=work/(ident+'.wav')
   if a.mode=='cli':
    out=subprocess.run([sys.executable,'-B',str(Path(__file__).parent/'cv_cli.py'),'--text',text,'--F0','140','--mode','learned' if learned else 'baseline','--output',str(path)],check=True,capture_output=True,text=True,timeout=90);meta=json.loads(out.stdout)
   else:data,meta=v.render_text(text,140.,1.,learned,41);path.write_bytes(data)
   rows.append(dict(id=ident,kind='CV',meta=meta))
 if a.mode=='normal':
  for vowel in 'aiu':
   data,meta=v.render_vowel(vowel,280.,True);ident='static-'+vowel;path=work/(ident+'.wav');path.write_bytes(data);rows.append(dict(id=ident,kind='static-training-reproduction',meta=meta))
finally:
 if v:v.close()
for row in rows:
 path=work/(row['id']+'.wav');data=path.read_bytes();assert hashlib.sha256(data).hexdigest()==row['meta']['wav_sha256'];fs,audio=wavfile.read(path);assert fs==24000
 row.update(E0=evaluate(audio,{},fs),close_then_self_read=True,bytes=len(data))
probes=[]
for name in json.loads(a.blocked):
 try:
  with Path(name).open('rb') as f:f.read(1)
 except PermissionError:probes.append(dict(path=name,denied=True))
 else:probes.append(dict(path=name,denied=False))
sock=socket.socket();rc=sock.connect_ex(('127.0.0.1',9));sock.close()
print(json.dumps(dict(rows=rows,denial_probes=probes,network_error=rc,network_permission_denied=rc in (1,13),forbidden_imports=[x for x in sys.modules if x.split('.')[0] in ['torch','tensorflow','transformers','onnxruntime','faster_whisper','sherpa_onnx']]),allow_nan=False))
