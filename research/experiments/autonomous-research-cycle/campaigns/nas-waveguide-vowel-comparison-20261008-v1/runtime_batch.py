"""渡された現入力だけを共有入口で生成し、結果をpipeへ返す。"""
import sys,json,base64
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from runtime import generate,verify
verify();requests=json.loads(sys.stdin.read());rows=[]
for r in requests:
 data,meta=generate(r['text'],r['speed'],r['pitch']);rows.append(dict(id=r['id'],wav_base64=base64.b64encode(data).decode(),meta=meta))
print(json.dumps(dict(rows=rows,calls=sum(r['meta']['synthesis_calls'] for r in rows)),allow_nan=False))
