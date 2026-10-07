"""実音声を生成せず、batch全入出力とarchive符号化を人工fixtureで検査。"""
import ast,base64,contextlib,hashlib,io,json,os,runpy,sys,tempfile,zipfile
from pathlib import Path
HERE=Path(__file__).resolve().parent
assert Path(tempfile.gettempdir()).resolve()==Path(os.environ['TMPDIR']).resolve()
entry=HERE/'runtime-bundle-v2/runtime_batch_v4.py'
for node in ast.walk(ast.parse(entry.read_text())):
    if isinstance(node,ast.Attribute) and isinstance(node.value,ast.Name) and node.value.id=='base64':
        assert hasattr(base64,node.attr),node.attr
ns=runpy.run_path(str(entry),run_name='fixture_import')
calls=[]
def fake_generate(text,method,speed,pitch):
    calls.append((text,method,speed,pitch))
    data=b'artificial-archive-payload'
    return data,dict(sha256=hashlib.sha256(data).hexdigest(),synthesis_calls=1,E0_calls=1)
ns['main'].__globals__['generate']=fake_generate
sys.stdin=io.StringIO(json.dumps([dict(id=str(i),text='fixture',method='native',speed=1,pitch=220) for i in range(160)]))
output=io.StringIO()
with contextlib.redirect_stdout(output): ns['main']()
archive=base64.b64decode(output.getvalue(),validate=False)
with zipfile.ZipFile(io.BytesIO(archive)) as z:
    manifest=json.loads(z.read('manifest.json'))
    assert len(z.namelist())==321 and len(manifest['records'])==160 and len(calls)==160
    assert manifest['synthesis_calls']==manifest['E0_calls']==160
    assert all(hashlib.sha256(z.read(r['id']+'.wav')).hexdigest()==r['sha256'] for r in manifest['records'])
print(json.dumps(dict(input_archive_base64_roundtrip=True,fixture_calls=160,actual_render=0,actual_DSP=0,quality_evidence=False)))
