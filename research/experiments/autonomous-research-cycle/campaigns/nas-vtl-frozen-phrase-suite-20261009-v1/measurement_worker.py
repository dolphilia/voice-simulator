"""同コホートnativeで固定した有声phone-indexを、各方式自身の時計へ適用する。"""
import sys,json,re,io,os,tempfile
from pathlib import Path
import numpy as np
from scipy.io import wavfile
work=Path(sys.argv[1]);old=Path(sys.argv[2]);bundle=Path(sys.argv[3])
assert work.resolve()==Path(os.environ['TMPDIR']).resolve()==Path(tempfile.gettempdir()).resolve()
sys.path[:0]=[str(bundle),str(old)]
from measurement import measure,pitch_pass
spec=json.loads((work/'measurement-input.json').read_text());result=[];dsp=0
def duration(row,phones):
 if row['request']['method']=='native':return row['meta']['duration']
 bounds=[0.,.05]
 for mora in row['meta']['phone_intervals']:
  start,end=mora['source_schedule_vowel_interval']
  if mora['phone']:bounds.append(start)
  bounds.append(end)
 bounds.append(row['meta']['duration_seconds'])
 assert len(bounds)==len(phones)+1
 widths=np.diff(bounds);assert np.all(widths>0)
 return (np.repeat(widths/5/.005,5)).tolist()
for ident,rows in spec['cases'].items():
 native=rows['native'];phones=spec['phones'][ident]
 eligible=[i for i,p in enumerate(phones) if p in ['a','i','u','e','o','N','m','n','my','ny']]
 fixed=[];native_measure=None
 for method in ['native','baseline','learned']:
  r=rows[method]
  if r['status']!='generated':
   result.append(dict(id=r['request']['id'],method=method,status=r['status'],E0_pass=False,pitch_gate=dict(passed=False),measurement=None,support_missing_due_to_native=r['request']['method']!='native'));continue
  fs,audio=wavfile.read(work/r['file']);assert fs==24000
  clock=duration(r,phones)
  if method=='native':
   labels=[re.search(r'\-([^+]+)\+',z).group(1) for z in r['meta']['full_context_labels']]
   assert labels==phones
   measurement,f0,times=measure(audio,clock,eligible);fixed=measurement['support']
  else:measurement,f0,times=measure(audio,clock,eligible,fixed)
  # 旧measure内部のDIO/stonemask/全体ACFを3 macroとして予約。支持の時計は実観測境界ではない。
  dsp+=3;gate=pitch_pass(measurement,r['request']['F0_Hz'])
  result.append(dict(id=r['request']['id'],method=method,status='measured',E0_pass=bool(r['E0']['E0_pass']),pitch_gate=gate,measurement=measurement,source_state_or_rule_clock_not_observed_boundary=True,native_fixed_support=fixed,duration_state_frames=clock))
  (work/'measurement-partial.json').write_text(json.dumps(dict(rows=result,DSP=dsp),ensure_ascii=False,allow_nan=False))
print(json.dumps(dict(rows=result,DSP=dsp),ensure_ascii=False,allow_nan=False))
