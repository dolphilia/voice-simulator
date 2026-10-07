"""文章と固定係数から波形bytesを作る単独・batch共通非ニューラル入口。"""
from pathlib import Path
import sys,argparse,json,hashlib,math,io
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
import numpy as np
from scipy.io import wavfile
from japanese_frontend import analyze
from timing_engine import Engine
from world_renderer2 import synthesize
from timing_control import durations as original,predict
from state_event_control import durations as mixed_fixed
from acoustics import evaluate
METHODS=['native','direct_original','student_original','direct_mixed_fixed','student_mixed_fixed']
def verify():
 for n,h in json.loads((ROOT/'manifest.json').read_text())['files'].items():
  assert hashlib.sha256((ROOT/n).read_bytes()).hexdigest()==h
def generate(text,method,speed,pitch):
 assert method in METHODS
 row=analyze(text);m=json.loads((ROOT/(method.split('_')[0]+'.json')).read_text()) if method!='native' else None
 with Engine(row,ROOT/'mei_normal.htsvoice',speed=speed,half_tone=12*math.log2(pitch/220)) as e:
  before=e.snapshot();variance=e.variance();settings=e.get_settings()
  if m is not None:
   clock=mixed_fixed if method.endswith('mixed_fixed') else original
   d,notes=clock(row,before,lambda x:predict(m,x));_,after=e.modify_duration(d)
  else:after=before
  assert sum(after['duration'])==sum(before['duration']) and all(before[k]==after[k] for k in ['means','msd','layout']) and np.array_equal(variance,e.variance())
  mask=np.asarray(before['msd']).reshape(-1,5)>.5;mix=np.any(mask,axis=1)&~np.all(mask,axis=1)
  protected=np.array_equal(np.asarray(before['duration']).reshape(-1,5)[mix],np.asarray(after['duration']).reshape(-1,5)[mix])
  if method.endswith('mixed_fixed'):assert protected
  params=e.parameters();raw,_=synthesize(params,settings);assert e.snapshot()==after and np.array_equal(variance,e.variance())
 audio=(raw*.25).astype(np.float32);assert np.isfinite(audio).all() and np.max(abs(audio))<1 and evaluate(audio,{},24000)['E0_pass']
 forbidden=[n for n in sys.modules if n.split('.')[0] in ['torch','tensorflow','transformers','faster_whisper','ctranslate2','onnxruntime','sherpa_onnx']];assert not forbidden
 f=io.BytesIO();wavfile.write(f,24000,audio);data=f.getvalue()
 meta=dict(sha256=hashlib.sha256(data).hexdigest(),synthesis_calls=1,E0_calls=1,E0_pass=True,forbidden_imports=forbidden,runtime_neural=False,utterance_tables=0,teacher_audio=0,total_frame_count_fixed=True,duration_only_state_change=True,mixed_state_duration_fixed=bool(protected))
 return data,meta
def main():
 p=argparse.ArgumentParser();p.add_argument('--text',required=True);p.add_argument('--method',choices=METHODS,required=True);p.add_argument('--speed',type=float,required=True);p.add_argument('--pitch',type=float,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists()
 verify();data,meta=generate(a.text,a.method,a.speed,a.pitch);a.output.write_bytes(data);print(json.dumps(meta))
if __name__=='__main__':main()
