"""同一Cの終了済み機構資格を照合する。新波形は生成しない。"""
import hashlib,json
from pathlib import Path
here=Path(__file__).resolve().parent
parent=here.parent/'nas-hts-minphase-mechanism-20261008-v1'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(here/'shape.c')==sha(parent/'shape.c')
assert sha(here/'shape.dylib')==sha(parent/'shape.dylib')
fixture=json.loads((parent/'fixture-audit.json').read_text())
assert fixture['passed']
print(json.dumps(dict(passed=True,inherited=True,new_render=0,new_dsp=0,source_sha256=sha(parent/'fixture-audit.json'))))
