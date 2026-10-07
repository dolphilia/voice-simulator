"""固定4係数とHTSのみで文章から韻律制御を生成する。"""
from pathlib import Path
import argparse,sys,json,math,hashlib
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
import numpy as np
from scipy.io import wavfile
from japanese_frontend import analyze
from local_renderer import StateEngine
from local_control import deltas
from prosody_model import predict
from acoustics import evaluate

def main():
 p=argparse.ArgumentParser();p.add_argument('--text',required=True);p.add_argument('--method',choices=['direct_prosody','distilled_prosody'],required=True);p.add_argument('--speed',type=float,required=True);p.add_argument('--pitch',type=float,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 assert not a.output.exists()
 for n,h in json.loads((ROOT/'manifest.json').read_text())['files'].items():assert hashlib.sha256((ROOT/n).read_bytes()).hexdigest()==h
 row=analyze(a.text);model=json.loads((ROOT/(a.method+'.json')).read_text())
 with StateEngine(row,ROOT/'mei_normal.htsvoice',speed=a.speed,half_tone=12*math.log2(a.pitch/220)) as e:
  delta,phones=deltas(row,e.snapshot(),lambda x:predict(model,x));e.modify(delta);raw,lf0=e.generate()
 peak=float(np.max(abs(raw)));gain=min(1.,.95/peak) if peak else 1.;audio=(raw*gain).astype(np.float32);assert np.isfinite(audio).all() and np.max(abs(audio))<1
 assert evaluate(audio,{},24000)['E0_pass']
 forbidden=[n for n in sys.modules if n.split('.')[0] in ['torch','tensorflow','transformers','faster_whisper','ctranslate2','onnxruntime','sherpa_onnx']];assert not forbidden
 wavfile.write(a.output,24000,audio)
 print(json.dumps({'sha256':hashlib.sha256(a.output.read_bytes()).hexdigest(),'synthesis_calls':1,'E0_calls':1,'E0_pass':True,'forbidden_imports':forbidden,'runtime_neural':False,'utterance_tables':0,'coefficients':4,'quality_certified':False}))
if __name__=='__main__':main()
