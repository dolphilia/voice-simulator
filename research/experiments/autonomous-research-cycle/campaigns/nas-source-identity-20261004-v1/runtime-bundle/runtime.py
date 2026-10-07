"""固定共有係数とHTSで単位LPF音源を文章から生成する。"""
from pathlib import Path
import argparse,sys,json,math,hashlib
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
import numpy as np
from scipy.io import wavfile
from japanese_frontend import analyze
from source_renderer import Engine
from local_control import deltas,linear_predict
from prosody_model import predict
from acoustics import evaluate

def main():
 p=argparse.ArgumentParser();p.add_argument('--text',required=True);p.add_argument('--method',choices=['native','direct_non_neural','distilled_non_neural','direct_prosody','distilled_prosody'],required=True);p.add_argument('--speed',type=float,required=True);p.add_argument('--pitch',type=float,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists()
 for n,h in json.loads((ROOT/'manifest.json').read_text())['files'].items():assert hashlib.sha256((ROOT/n).read_bytes()).hexdigest()==h
 row=analyze(a.text);model=json.loads((ROOT/(a.method+'.json')).read_text()) if a.method!='native' else None;audio=[]
 for mode in [0,1]:
  with Engine(row,ROOT/'mei_normal.htsvoice',speed=a.speed,half_tone=12*math.log2(a.pitch/220)) as e:
   delta=np.zeros(e.count) if model is None else deltas(row,e.snapshot(),lambda x:predict(model,x) if a.method.endswith('prosody') else linear_predict(model,x))[0]
   e.modify(delta);params=e.parameters();raw,_=e.synthesize(params,mode);audio.append(raw)
 peak=float(np.max(abs(audio[0])));gain=(min(1.,.95/peak) if peak else 1.)*.25;out=(audio[1]*gain).astype(np.float32)
 assert np.isfinite(out).all() and np.max(abs(out))<1 and evaluate(out,{},24000)['E0_pass']
 forbidden=[n for n in sys.modules if n.split('.')[0] in ['torch','tensorflow','transformers','faster_whisper','ctranslate2','onnxruntime','sherpa_onnx']];assert not forbidden
 wavfile.write(a.output,24000,out)
 print(json.dumps({'sha256':hashlib.sha256(a.output.read_bytes()).hexdigest(),'synthesis_calls':2,'E0_calls':1,'E0_pass':True,'forbidden_imports':forbidden,'runtime_neural':False,'utterance_tables':0,'quality_certified':False}))
if __name__=='__main__':main()
