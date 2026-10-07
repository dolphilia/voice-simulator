"""文章から基準利得も求め、固定包絡の非ニューラル出力を作る。"""
from pathlib import Path
import argparse,hashlib,json,sys,math
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
import numpy as np
from scipy.io import wavfile
from japanese_frontend import analyze
from local_control import deltas,linear_predict
from spectrum_renderer import Engine
from acoustics import evaluate

def main():
 p=argparse.ArgumentParser();p.add_argument('--text',required=True);p.add_argument('--method',choices=['native','direct_non_neural','distilled_non_neural'],required=True)
 p.add_argument('--speed',type=float,required=True);p.add_argument('--pitch',type=float,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 if a.output.exists():raise FileExistsError('既存出力を上書きしません')
 manifest=json.loads((ROOT/'manifest.json').read_text())
 for n,h in manifest['files'].items():assert hashlib.sha256((ROOT/n).read_bytes()).hexdigest()==h
 row=analyze(a.text);settings={'speed':a.speed,'half_tone':12*math.log2(a.pitch/220)}
 model=json.loads((ROOT/(a.method+'.json')).read_text()) if a.method!='native' else None
 audio=[]
 for factor in (1.,.75):
  with Engine(row,ROOT/'mei_normal.htsvoice',**settings) as e:
   before=e.snapshot();delta=np.zeros(e.count) if model is None else deltas(row,before,lambda x:linear_predict(model,x))[0]
   e.modify(delta);params=e.parameters();raw,_=e.synthesize(params,factor);audio.append(raw)
 gain=min(1.,.95/float(np.max(abs(audio[0])))) if np.max(abs(audio[0])) else 1.
 out=(audio[1]*gain).astype(np.float32);assert np.isfinite(out).all() and np.max(abs(out))<1
 e0=evaluate(out,{},24000);assert e0['E0_pass']
 forbidden=[n for n in sys.modules if n.split('.')[0] in ('torch','tensorflow','transformers','onnxruntime','faster_whisper','ctranslate2','sherpa_onnx')]
 assert not forbidden
 wavfile.write(a.output,24000,out)
 print(json.dumps({'method':a.method,'text':a.text,'factor':.75,'synthesis_calls':2,'E0_calls':1,
  'output_gain':gain,'E0_pass':True,'forbidden_imports':forbidden,'runtime_neural':False,
  'sha256':hashlib.sha256(a.output.read_bytes()).hexdigest(),'quality_certified':False},ensure_ascii=False))
if __name__=='__main__':main()
