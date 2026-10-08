"""API定数・形状・出力close後の再読取と独立拒否の小検査。"""
import argparse,hashlib,json,os,socket,sys,tempfile
from pathlib import Path
from scipy.io import wavfile
from vtl_runtime import VTL
from acoustics import evaluate
p=argparse.ArgumentParser();p.add_argument('work');p.add_argument('--vowels',default='ai');p.add_argument('--blocked',default='[]');a=p.parse_args();work=Path(a.work);assert work.resolve()==Path(os.environ['TMPDIR']).resolve()==Path(tempfile.gettempdir()).resolve()
vtl=VTL();rows=[]
try:
 for vowel in a.vowels:
  data,meta=vtl.render(vowel,120.,.32,41);path=work/(vowel+'.wav');path.write_bytes(data);reread=path.read_bytes();assert reread==data and hashlib.sha256(reread).hexdigest()==meta['wav_sha256'];fs,audio=wavfile.read(path);assert fs==24000 and len(audio)==7680
  rows.append(dict(**meta,E0=evaluate(audio,dict(expected_duration_seconds=.32),24000),close_then_read_exact=True))
finally:vtl.close()
probes=[]
for n in json.loads(a.blocked):
 try:
  with Path(n).open('rb') as f:f.read(1)
 except PermissionError:probes.append(dict(path=n,denied=True))
 else:probes.append(dict(path=n,denied=False))
network=socket.socket();rc=network.connect_ex(('127.0.0.1',9));network.close()
print(json.dumps(dict(rows=rows,denial_probes=probes,network_error=rc,network_permission_denied=rc in (1,13),forbidden_imports=[n for n in sys.modules if n.split('.')[0] in ['torch','tensorflow','transformers','onnxruntime','faster_whisper','sherpa_onnx']])))
