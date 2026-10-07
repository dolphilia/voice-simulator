"""既存native/calibrated基準とのwave hashを確認する工学fixture。"""
import sys,json,hashlib,base64,os,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent
assert Path(tempfile.gettempdir()).resolve()==Path(os.environ['TMPDIR']).resolve()
sys.path.insert(0,str(ROOT/'runtime-bundle-v2'))
from runtime import generate,verify
verify()
old=ROOT.parent/'nas-absolute-f0-20261008-v1'
row=json.loads((old/'protocol.json').read_text())['rows'][0]
records=[]
for method in ['native','calibrated']:
    data,meta=generate(row['text'],method,1.,220.)
    expected=hashlib.sha256((old/'render'/row['id']/'neutral'/(method+'.wav')).read_bytes()).hexdigest()
    assert meta['sha256']==expected==hashlib.sha256(data).hexdigest()
    records.append(dict(method=method,wav_base64=base64.b64encode(data).decode(),meta=meta,old_hash=expected))
print(json.dumps(dict(records=records,render_calls=2,DSP_calls=2,all_baseline_bit_match=True,quality_evidence=False),allow_nan=False))
