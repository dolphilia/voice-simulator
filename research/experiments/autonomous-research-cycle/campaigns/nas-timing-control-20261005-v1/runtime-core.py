"""文章と固定回帰から状態時計を生成する非ニューラル入口。"""
from pathlib import Path
import sys,argparse,json,hashlib,math
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
import numpy as np
from scipy.io import wavfile
from japanese_frontend import analyze
from timing_engine import Engine
from world_renderer2 import synthesize
from timing_control import durations,predict
from acoustics import evaluate
def main():
 p=argparse.ArgumentParser();p.add_argument('--text',required=True);p.add_argument('--method',choices=['native','direct','student'],required=True);p.add_argument('--speed',type=float,required=True);p.add_argument('--pitch',type=float,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists()
 for n,h in json.loads((ROOT/'manifest.json').read_text())['files'].items():assert hashlib.sha256((ROOT/n).read_bytes()).hexdigest()==h
 row=analyze(a.text);m=json.loads((ROOT/(a.method+'.json')).read_text()) if a.method!='native' else None
 with Engine(row,ROOT/'mei_normal.htsvoice',speed=a.speed,half_tone=12*math.log2(a.pitch/220)) as e:
  before=e.snapshot();variance=e.variance();settings=e.get_settings()
  if m is not None:
   d,notes=durations(row,before,lambda x:predict(m,x));_,after=e.modify_duration(d)
  else:after=before
  assert sum(after['duration'])==sum(before['duration']) and all(before[k]==after[k] for k in ['means','msd','layout']) and np.array_equal(variance,e.variance())
  params=e.parameters();raw,_=synthesize(params,settings);assert e.snapshot()==after and np.array_equal(variance,e.variance())
 audio=(raw*.25).astype(np.float32);assert np.isfinite(audio).all() and np.max(abs(audio))<1 and evaluate(audio,{},24000)['E0_pass']
 forbidden=[n for n in sys.modules if n.split('.')[0] in ['torch','tensorflow','transformers','faster_whisper','ctranslate2','onnxruntime','sherpa_onnx']];assert not forbidden
 wavfile.write(a.output,24000,audio);print(json.dumps(dict(sha256=hashlib.sha256(a.output.read_bytes()).hexdigest(),synthesis_calls=1,E0_calls=1,E0_pass=True,forbidden_imports=forbidden,runtime_neural=False,utterance_tables=0,teacher_audio=0,total_frame_count_fixed=True,duration_only_state_change=True,quality_certified=False)))
if __name__=='__main__':main()
