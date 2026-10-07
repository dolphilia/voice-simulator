"""固定係数の時計をMLPG前後で適用する、文章入力だけの最終入口。"""
from pathlib import Path
import sys,argparse,json,hashlib,math,io
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
import numpy as np
from scipy.io import wavfile
from japanese_frontend import analyze
from timing_engine import Engine
from world_renderer2 import synthesize
from timing_control import predict
from state_event_control import durations
from post_mlpg_warp import warp
from acoustics import evaluate
METHODS=['native','direct_pre','student_pre','direct_post','student_post']
def verify():
 for n,h in json.loads((ROOT/'manifest.json').read_text())['files'].items():
  assert hashlib.sha256((ROOT/n).read_bytes()).hexdigest()==h
def generate(text,method,speed,pitch):
 assert method in METHODS
 row=analyze(text);m=json.loads((ROOT/(method.split('_')[0]+'.json')).read_text()) if method!='native' else None
 with Engine(row,ROOT/'mei_normal.htsvoice',speed=speed,half_tone=12*math.log2(pitch/220)) as e:
  before=e.snapshot();variance=e.variance();settings=e.get_settings();d=before['duration'];after=before;w=None
  if m is not None:
   d,notes=durations(row,before,lambda x:predict(m,x))
   if method.endswith('_pre'):_,after=e.modify_duration(d)
  params=e.parameters()
  if method.endswith('_post'):params,w=warp(params,before['duration'],d,before['msd'])
  assert sum(d)==sum(before['duration']) and all(before[k]==after[k] for k in ['means','msd','layout']) and np.array_equal(variance,e.variance())
  mask=np.asarray(before['msd']).reshape(-1,5)>.5;mix=np.any(mask,axis=1)&~np.all(mask,axis=1)
  protected=np.array_equal(np.asarray(before['duration']).reshape(-1,5)[mix],np.asarray(d).reshape(-1,5)[mix]);assert protected
  raw,_=synthesize(params,settings);assert e.snapshot()==after and np.array_equal(variance,e.variance())
 audio=(raw*.25).astype(np.float32);assert np.isfinite(audio).all() and np.max(abs(audio))<1 and evaluate(audio,{},24000)['E0_pass']
 forbidden=[n for n in sys.modules if n.split('.')[0] in ['torch','tensorflow','transformers','faster_whisper','ctranslate2','onnxruntime','sherpa_onnx']];assert not forbidden
 f=io.BytesIO();wavfile.write(f,24000,audio);data=f.getvalue()
 meta=dict(sha256=hashlib.sha256(data).hexdigest(),synthesis_calls=1,E0_calls=1,E0_pass=True,forbidden_imports=forbidden,runtime_neural=False,utterance_tables=0,teacher_audio=0,total_frame_count_fixed=True,mixed_state_duration_fixed=bool(protected),clock_application='post_MLPG' if method.endswith('_post') else 'pre_MLPG',engine_state_clock_changed=before['duration']!=after['duration'],output_state_clock_changed=before['duration']!=d,mixed_parameter_blocks_exact=w['mixed_parameter_blocks_exact'] if w else None)
 return data,meta
def main():
 p=argparse.ArgumentParser();p.add_argument('--text',required=True);p.add_argument('--method',choices=METHODS,required=True);p.add_argument('--speed',type=float,required=True);p.add_argument('--pitch',type=float,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists()
 verify();data,meta=generate(a.text,a.method,a.speed,a.pitch);a.output.write_bytes(data);print(json.dumps(meta))
if __name__=='__main__':main()
