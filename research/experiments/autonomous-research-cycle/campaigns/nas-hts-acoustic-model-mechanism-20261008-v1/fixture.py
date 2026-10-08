"""元モデル恒等交換と別モデル交換の保護を全件確認する限定機構試験。"""
import sys,json,os,tempfile,hashlib
from pathlib import Path
here=Path(__file__).resolve().parent;bundle=here/'runtime-bundle';sys.path.insert(0,str(bundle))
assert Path(tempfile.gettempdir()).resolve()==Path(os.environ['TMPDIR']).resolve()
import numpy as np
from japanese_frontend import analyze
from acoustic_model import Engine,tests
from controls_v2 import transform
from shape_arrays import raw
from hts_arrays import ah
texts=['紫の船がゆっくり進む。','雨が降る。','切手を買った。','新しい地図を机に広げた。']
rows=[];tests()
for index,text in enumerate(texts):
 for speed,pitch in ((1.,220.),(1.15,280.)):
  row=analyze(text);tone=12*np.log2(pitch/220.);saved={};transfers={}
  for method in ('original','identity','happy_mcp'):
   with Engine(row,bundle/'mei_normal.htsvoice',speed=speed,half_tone=tone) as engine:
    original=engine.snapshot();settings=engine.get_settings()
    if method!='original':
     voice='mei_normal.htsvoice' if method=='identity' else 'mei_happy.htsvoice'
     with Engine(row,bundle/voice,speed=speed,half_tone=tone) as donor:transfers[method]=engine.transfer_mcp(donor)
    after=engine.snapshot();params=engine.parameters();converted,control,error,invariants=transform('calibrated',params,row['full_context_labels'],original['duration'],pitch)
    audio,source=raw(converted,settings,'native');assert np.isfinite(audio).all() and invariants
    assert engine.snapshot()==after
    saved[method]=dict(params=converted,audio=audio,source=source,duration=original['duration'])
  a=saved['original'];i=saved['identity'];z=saved['happy_mcp']
  assert all(np.array_equal(x,y) for x,y in zip(a['params'],i['params'])) and np.array_equal(a['audio'],i['audio'])
  assert all(np.array_equal(a['params'][k],z['params'][k]) for k in (1,2)) and a['duration']==z['duration']
  assert not np.array_equal(a['params'][0],z['params'][0]) and not np.array_equal(a['audio'],z['audio'])
  keys=('period','counter','event','original_excitation','processed_excitation')
  assert all(np.array_equal(a['source'][k],i['source'][k]) and np.array_equal(a['source'][k],z['source'][k]) for k in keys)
  assert transfers['identity']['before_MCP_mean_sha256']==transfers['identity']['after_MCP_mean_sha256']
  rows.append(dict(text=text,speed=speed,pitch=pitch,frames=len(a['params'][0]),original_wave_sha256=ah(a['audio']),identity_wave_sha256=ah(i['audio']),candidate_wave_sha256=ah(z['audio']),
   native_identity_byte_exact=True,LF0_LPF_duration_exact=True,all_source_clock_and_excitation_exact=True,MCP_and_wave_intentionally_changed=True,
   source_hashes={k:ah(a['source'][k]) for k in keys},transfers=transfers,passed=True))
assert len(rows)==8
print(json.dumps(dict(rows=rows,passed=True,render=24,dsp=72,limited_mechanism_only=True,real_Japanese_comparison_qualified=False,quality_certified=False),allow_nan=False))
