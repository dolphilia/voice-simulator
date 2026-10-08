"""全保存32組の二駆動・源/状態/時計・原native中央値を再生成なしに確認する。"""
import sys,json,re,math
from pathlib import Path
import numpy as np
here=Path(sys.argv[1]);p=json.loads((here/'protocol.json').read_text());rows=[]
for row in p['rows']:
 for c,q in p['conditions'].items():
  base=here/'render'/row['id']/c;n=json.loads((base/'native.json').read_text())
  for source in ('derivative','flow'):
   w=json.loads((base/(source+'.json')).read_text());m=w['meta'];ctl=m['control'];phones=[re.search(r'\-([^+]+)\+',x).group(1) for x in row['full_context_labels']][1:-1];ms=250 if q['speed']==1. else 215
   assert m['request']==dict(segments=[dict(vowel=v,duration_ms=ms) for v in phones],f0=q['requested_f0']) and m['source_kind']==ctl['source_kind']==source
   bounds=np.rint(np.arange(len(phones)+1)*ms*34300/1000.).astype(np.int64).tolist();assert bounds==ctl['bounds_samples'];frames=ms//5;part=[frames//5+(k<frames%5) for k in range(5)];assert m['duration']==[0]*5+part*len(phones)+[0]*5
   assert ctl['source_f0']==q['requested_f0'] and ctl['phase_start']==.125 and ctl['harmonics']==math.floor(8000/q['requested_f0'])
   assert m['output_gain']==ctl['shared_gain']==.10 and not m['HMM_called'] and not m['between_method_clock_identity_claimed']
   assert ctl['state_reset_only_at_utterance_start'] and not ctl['source_phase_reset_at_block_boundaries'];assert n['measurement']['support']==w['measurement']['support']
  assert n['meta']['output_gain']==.25 and n['meta']['conversion']['source_method']=='native-pulse-noise'
  with np.load(base/'native.npz',allow_pickle=False) as z:
   assert z['duration'].tolist()==n['meta']['duration'];mask=z['lf0'][:,0]>0;assert abs(np.median(z['lf0'][mask,0])-math.log(q['requested_f0']))<=3e-15
  rows.append(dict(id=row['id']+'/'+c,passed=True,variants=2,source_state_duration_gain_intentionally_different=True,phone_index_support_exact=True,clock_identity_claimed=False))
assert len(rows)==32
print(json.dumps(dict(passed=True,triplets_checked=32,candidate_pairs_checked=64,rows=rows,no_wave_resynthesis=True,render=0,dsp=192)))
