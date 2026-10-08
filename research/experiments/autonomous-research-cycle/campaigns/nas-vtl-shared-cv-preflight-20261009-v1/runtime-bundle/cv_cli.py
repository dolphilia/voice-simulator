"""共有CV生成器のCLI。close後に所有出力を書き、過去音声を読まない。"""
import argparse,json,os,tempfile
from pathlib import Path
from cv_runtime import CV
p=argparse.ArgumentParser();p.add_argument('--text',required=True);p.add_argument('--F0',type=float,default=140.);p.add_argument('--speed',type=float,default=1.);p.add_argument('--mode',choices=['baseline','learned'],required=True);p.add_argument('--seed',type=int,default=41);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
if a.output.exists() or a.output.parent.resolve()!=Path(os.environ['TMPDIR']).resolve():raise ValueError('不存在の所有一時出力を要求')
v=CV()
try:data,meta=v.render_text(a.text,a.F0,a.speed,a.mode=='learned',a.seed)
finally:v.close()
a.output.write_bytes(data);print(json.dumps(meta,ensure_ascii=False,allow_nan=False))
