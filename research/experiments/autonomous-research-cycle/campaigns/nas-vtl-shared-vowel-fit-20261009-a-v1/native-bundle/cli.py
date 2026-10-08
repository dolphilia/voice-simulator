"""現文章/速度/F0を標準入力から一件だけ受け付ける。"""
import sys,json,base64
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from runtime import generate,verify
verify();r=json.loads(sys.stdin.read());data,meta=generate(r['text'],r['speed'],r['pitch']) if r['method']=='native' else generate(r['text'],r['speed'],r['pitch'],source=r['method'])
print(json.dumps(dict(id=r['id'],wav_base64=base64.b64encode(data).decode(),meta=meta),allow_nan=False))
