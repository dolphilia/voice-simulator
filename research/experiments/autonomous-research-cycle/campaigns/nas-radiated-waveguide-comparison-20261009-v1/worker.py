"""全96音声の固定時計支持を測定し、方式間の時間差を保持する。"""
from paths import *
import sys,json,io,re,importlib.util,hashlib
import numpy as np
from scipy.io import wavfile
sys.path.insert(0,str(HERE/'runtime-bundle'))
from measurement import measure,pitch_pass,ELIGIBLE
def module(name,path):
 sys.path.insert(0,str(path));s=importlib.util.spec_from_file_location(name,path/'runtime.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m);m.verify();return m
native=module('_native',HERE/'native-bundle');candidate=module('_candidate',HERE/'runtime-bundle')
b=Budget();rjob,djob=sys.argv[1:3];protocol=read(HERE/'protocol.json');records=[];calls=0
for row in protocol['rows']:
 for condition,q in protocol['conditions'].items():
  support=None
  for method,m in [('native',native),('derivative',candidate),('flow',candidate)]:
   path=HERE/'render'/row['id']/condition/method;assert not path.with_suffix('.json').exists()
   data,meta,params,analyzed=m.generate(row['text'],q['speed'],q['requested_f0'],full=True) if method=='native' else m.generate(row['text'],q['speed'],q['requested_f0'],full=True,source=method)
   assert analyzed['full_context_labels']==row['full_context_labels'];calls+=meta['synthesis_calls']
   b.write_data(path.with_suffix('.wav'),data,rjob)
   if params is not None:
    buf=io.BytesIO();np.savez_compressed(buf,mcp=params[0],lf0=params[1],lpf=params[2],duration=meta['duration']);b.write_data(path.with_suffix('.npz'),buf.getvalue(),rjob)
   _,audio=wavfile.read(io.BytesIO(data));eligible=[i for i,x in enumerate(row['full_context_labels']) if re.search(r'\-([^+]+)\+',x).group(1) in ELIGIBLE and any(v>.5 for v in meta['msd'][i*5:(i+1)*5])]
   measured,f0,times=measure(audio,meta['duration'],eligible,support)
   if support is None:
    support=measured['support'];b.save(HERE/'support'/row['id']/(condition+'.json'),dict(indices=support,excluded=[x['index'] for x in measured['eligible_native_intervals'] if not x['support_complete']],native_wave_sha256=meta['sha256'],fixed_from_native=True,not_candidate_selected=True,phone_index_identity_not_clock_identity=True),djob)
   buf=io.BytesIO();np.savez_compressed(buf,f0=f0,times=times);b.write_data(path.with_suffix('.dio.npz'),buf.getvalue(),djob)
   record={k:row[k] for k in ['text','length','challenge_group','cohort']};record.update(id=row['id']+'/'+condition+'/'+method,condition=condition,variant=method,wav=str(path.with_suffix('.wav').relative_to(REPO)),wav_sha256=meta['sha256'],status='completed',meta=meta,measurement=measured,pitch_gate=pitch_pass(measured,q['requested_f0']),E0_pass=meta['E0_pass'],invariants_pass=meta['invariants_pass'],protocol_sha256=digest(HERE/'protocol.json'),quality_certified=False)
   b.write_data(path.with_suffix('.json'),encode(record),djob);records.append(dict(id=record['id'],record=str(path.with_suffix('.json').relative_to(REPO)),sha256=digest(path.with_suffix('.json'))))
  print('比較 '+str(len(records))+'/96',file=sys.stderr,flush=True)
assert len(records)==96
b.save(HERE/'render-manifest.json',dict(rows=records,new_render_calls=calls,source_and_all_block_calls_counted=True,output_waves=96,new_DSP_calls=288,no_optimization_after_output=True,quality_certified=False),djob)
print(json.dumps(dict(records=96,calls=calls)))
