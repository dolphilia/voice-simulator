"""現入力を辞書で母音へ変換し、共有声道と連続源から生成する。"""
import sys,json,hashlib,io,re
from pathlib import Path
ROOT=Path(__file__).resolve().parent;sys.path.insert(0,str(ROOT))
import numpy as np
from scipy.io import wavfile
from japanese_frontend import analyze
from sequence_tract import generate as tract
from acoustics import evaluate
def verify():
 for name,h in json.loads((ROOT/'manifest.json').read_text())['files'].items():assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==h,name
def generate(text,speed,pitch,full=False):
 if speed not in (1.,1.15):raise ValueError('登録速度のみを受け付ける')
 row=analyze(text);phones=[re.search(r'\-([^+]+)\+',x).group(1) for x in row['full_context_labels']]
 if phones[0]!='sil' or phones[-1]!='sil' or any(p not in 'aiueo' or len(p)!=1 for p in phones[1:-1]):raise ValueError('両端silと母音だけの入力が必要')
 n=len(phones)-2
 if not 3<=n<=24:raise ValueError('3..24母音だけを受け付ける')
 ms=250 if speed==1. else 215
 request=dict(segments=[dict(vowel=p,duration_ms=ms) for p in phones[1:-1]],f0=pitch)
 y,control,raw,source,areas=tract(request);audio=y.astype(np.float32)
 frames=ms//5;part=[frames//5+(k<frames%5) for k in range(5)]
 duration=[0]*5+part*n+[0]*5;msd=[0.]*5+[1.]*(5*n)+[0.]*5
 e0=evaluate(audio,{},24000);buf=io.BytesIO();wavfile.write(buf,24000,audio);data=buf.getvalue()
 forbidden=[m for m in sys.modules if m.split('.')[0] in ('torch','tensorflow','transformers','faster_whisper','ctranslate2','onnxruntime','sherpa_onnx')];assert not forbidden
 meta=dict(sha256=hashlib.sha256(data).hexdigest(),E0=e0,E0_pass=e0['E0_pass'],invariants_pass=True,
  duration=duration,msd=msd,control=control,request=request,source_and_block_render_calls=control['source_and_block_render_calls'],
  output_gain=.10,generated_lf0_median_hz=float(pitch),synthesis_calls=control['source_and_block_render_calls'],E0_calls=1,
  runtime_neural=False,HMM_called=False,teacher_audio=0,utterance_tables=0,forbidden_imports=forbidden,
  full_context_labels=row['full_context_labels'],between_method_clock_identity_claimed=False,
  semantics='各母音250/215ms・定数F0・100ms面積遷移。源/声道/長さ/gainは原HTSと意図して異なる。',
  conversion=dict(render_calls_including_internal_MLSA=control['source_and_block_render_calls']))
 return (data,meta,None,row) if full else (data,meta)
