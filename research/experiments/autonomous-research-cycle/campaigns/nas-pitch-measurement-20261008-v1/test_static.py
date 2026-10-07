"""波形なしの入力境界・人工archive・欠測判定fixture。"""
from paths import *
import io,json,sys,zipfile,hashlib,base64,contextlib
sys.path[:0]=[str(HERE/'runtime-bundle'),str(HERE/'runtime-bundle/packages-v2')]
import numpy as np
from runtime import validated
import runtime_batch as rb
from measurement import score_track,global_score
spec=read(HERE/'protocol.json')['specifications'][0]
assert validated(spec)==spec
cases=[]
for key,value in [('f0',69),('voiced_ms',0),('harmonic','all-even'),('vowel','x'),('seed',-1),('SNR',5),('ramp_ms',0)]:
    bad=dict(spec);bad[key]=value;cases.append(bad)
for bad in cases:
    try:validated(bad)
    except ValueError:pass
    else:raise AssertionError('不正仕様を受理')
truth=dict(voiced=True,f0=220.,core_start=.09,core_end=.12,voiced_start=.08,voiced_end=.13)
times=np.arange(50)*.005;values=np.zeros(50);values[(times>=.09)&(times<.12)]=220.
assert score_track(values,times,truth)['core_pass']
assert not score_track(np.zeros(50),times,truth)['core_pass']
wrong=values.copy();wrong[wrong>0]=440.
assert not score_track(wrong,times,truth)['core_pass']
assert not global_score(dict(hz=None,confidence=0.,accepted=False),truth)['core_pass']
requests=read(HERE/'protocol.json')['specifications'];assert len(requests)==272
def fake(s):
    data=b'artificial-no-wave'
    return data,dict(sha256=hashlib.sha256(data).hexdigest(),synthesis_calls=1,E0_calls=1,forbidden_imports=[],nested={'integer':1,'boolean':True})
original=(rb.generate,rb.verify,sys.stdin)
rb.generate=fake;rb.verify=lambda:None;sys.stdin=io.StringIO(json.dumps(requests))
try:
    out=io.StringIO()
    with contextlib.redirect_stdout(out):rb.main()
finally:rb.generate,rb.verify,sys.stdin=original
data=base64.b64decode(out.getvalue().strip(),validate=True)
with zipfile.ZipFile(io.BytesIO(data)) as archive:
    manifest=json.loads(archive.read('manifest.json'));assert len(archive.namelist())==545 and len(manifest['records'])==272
    assert manifest['synthesis_calls']==manifest['E0_calls']==272
    for row in manifest['records']:
        assert hashlib.sha256(archive.read(row['id']+'.wav')).hexdigest()==row['sha256']
        assert json.loads(archive.read(row['id']+'.json'))['nested']['boolean'] is True
print(json.dumps(dict(invalid_cases_rejected=len(cases),missing_octave_unreliable_rejected=True,valid_known_period_fixture_accepted=True,archive272_roundtrip=True,base64_valid=True,actual_render_calls=0,actual_signal_measurement_calls=0,fixture_not_quality_evidence=True)))
