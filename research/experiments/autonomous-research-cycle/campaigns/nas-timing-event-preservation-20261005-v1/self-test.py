"""旧ゼロ制御と混在state長固定を、実HMMと波形で検査する。"""
from paths import *
import sys,math,hashlib,numpy as np
SRC=ROOT/'campaigns/nas-source-identity-20261004-v1'
sys.path[:0]=[str(HERE),str(SRC),str(WORLD),str(SHARED),str(BUNDLE)]
from timing_engine import Engine
from timing_control import durations as original,FEATURES,LOGBOUND
from state_event_control import durations as mixed_fixed
from world_renderer2 import synthesize
from teacher_common import wavbytes
from acoustics import evaluate
def ah(x):return hashlib.sha256(np.asarray(x,dtype='<f8').tobytes()).hexdigest()
def main():
 b=Budget();old=read(TIME/'protocol.json');row=next(r for r in old['rows'] if r['id']=='timing-fresh-00');pairs=[]
 for condition,request in row['requests'].items():
  expected=read(TIME/'render/diagnostic'/row['id']/condition/'native.json')
  values=[]
  for mode in ['native','original_zero','mixed_zero']:
   with b.job(NAME,'render','新policyゼロ自己回復 '+condition+'/'+mode,reserve_bytes=4000000) as j:
    with Engine(row,BUNDLE/'mei_normal.htsvoice',speed=request['speed'],half_tone=12*math.log2(request['requested_f0']/220)) as e:
     before=e.snapshot();v=e.variance();settings=e.get_settings()
     if mode!='native':
      fun=original if mode=='original_zero' else mixed_fixed
      d,n=fun(row,before,lambda x:np.zeros(len(x)));assert d==before['duration'];_,after=e.modify_duration(d);assert before==after
     params=e.parameters();raw,_=synthesize(params,settings);assert e.snapshot()==before and np.array_equal(v,e.variance())
    audio=(raw*.25).astype(np.float32)
    with b.job(NAME,'dsp','ゼロfixture E0 '+condition+'/'+mode,reserve_bytes=1000):
     assert evaluate(audio,{},24000)['E0_pass']
    path=HERE/'self-test'/condition/(mode+'.wav');b.write(path,wavbytes(audio),j)
    value=dict(wav_sha256=digest(path),parameter_hashes=[ah(q) for q in params],duration=before['duration'])
    assert value['wav_sha256']==expected['wav_sha256'] and value['parameter_hashes']==expected['parameter_hashes'] and value['duration']==expected['duration']
    b.save(path.with_suffix('.json'),value,j);values.append(value)
  assert values[0]==values[1]==values[2];pairs.append(dict(condition=condition,original_mixed_zero_bit_match=True))
 with b.job(NAME,'setup','MSD混在の状態長固定と、元policyへの同値/差分を検査',reserve_bytes=20000) as j:
  with Engine(row,BUNDLE/'mei_normal.htsvoice',speed=1.,half_tone=0.) as e:
   before=e.snapshot();v=e.variance();base=np.array(before['duration']).reshape(-1,5);mask=np.array(before['msd']).reshape(-1,5)>.5;mix=np.any(mask,axis=1)&~np.all(mask,axis=1);assert mix.any()
   f=lambda x:np.linspace(-LOGBOUND,LOGBOUND,len(x))
   d,n=mixed_fixed(row,before,f);arr=np.array(d).reshape(-1,5)
   assert np.array_equal(arr[mix],base[mix]) and sum(d)==sum(before['duration']) and np.all(arr>=1)
   _,after=e.modify_duration(d);assert np.array_equal(v,e.variance()) and all(before[k]==after[k] for k in ['means','msd','layout'])
   e.parameters();assert e.snapshot()==after and np.array_equal(v,e.variance())
  bad=dict(before,msd=[float('nan')]*len(before['msd']))
  try:mixed_fixed(row,bad,f)
  except ValueError:pass
  else:raise AssertionError('非有限MSDを拒否')
  uniform=dict(before,msd=[1.]*len(before['msd']));assert original(row,uniform,f)[0]==mixed_fixed(row,uniform,f)[0]
  uniform=dict(before,msd=[0.]*len(before['msd']));assert original(row,uniform,f)[0]==mixed_fixed(row,uniform,f)[0]
  b.save(HERE/'self-test.json',dict(passed=True,pairs=pairs,render_calls=6,E0_calls=6,mixed_state_durations_exactly_native=True,total_frame_count_preserved=True,means_variance_MSD_layout_preserved=True,uniform_voicing_matches_original_projection=True,nonfinite_MSD_rejected=True,current_source_sha256=digest(HERE/'state_event_control.py'),inherited_C_validation_sha256=digest(TIME/'self-test.json'),fixture_not_quality_evidence=True),j)
 print('mixed-state policy自己回復・構造不変を通過',flush=True);print(b.reconcile(),flush=True)
if __name__=='__main__':main()
