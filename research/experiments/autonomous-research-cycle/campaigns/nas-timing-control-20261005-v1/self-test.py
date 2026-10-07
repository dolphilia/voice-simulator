"""時間制御のゼロ自己回復・状態保存・不正入力拒否を実C/波形で確認する。"""
from paths import *
import sys,hashlib
SRC=ROOT/'campaigns/nas-source-identity-20261004-v1'
sys.path[:0]=[str(HERE),str(SRC),str(WORLD),str(BUNDLE)]
from timing_engine import Engine,set_duration
from timing_control import descriptions,durations,tests,FEATURES
from source_renderer import Engine as NativeEngine
from world_renderer2 import synthesize
from teacher_common import wavbytes
from acoustics import evaluate
import ctypes as C,numpy as np
def main():
 b=Budget();p=read(HERE/'protocol.json');row=p['training_rows'][0];results=[]
 with b.job(NAME,'audit','時間配分の負例とC更新前検査',reserve_bytes=100000) as j:
  check=tests()
  with Engine(row,BUNDLE/'mei_normal.htsvoice') as e:
   before=e.snapshot();v=np.array(before['duration'],dtype=np.uintp);bad=v.copy();bad[0]=0
   assert not set_duration(None,None,0) and not set_duration(e.pointer,None,len(v)) and not set_duration(e.pointer,bad.ctypes.data_as(C.POINTER(C.c_size_t)),len(bad)) and e.snapshot()==before
   bad=v.copy();bad[0]+=1;assert not set_duration(e.pointer,bad.ctypes.data_as(C.POINTER(C.c_size_t)),len(bad)) and e.snapshot()==before
   bad=v.copy();assert not set_duration(e.pointer,bad.ctypes.data_as(C.POINTER(C.c_size_t)),len(bad)-1) and e.snapshot()==before
   d,notes=durations(row,before,lambda x:np.zeros(len(x)));assert d==before['duration'];a,z=e.modify_duration(d);params=e.parameters();assert e.snapshot()==z
   assert not set_duration(e.pointer,v.ctypes.data_as(C.POINTER(C.c_size_t)),len(v)) and e.snapshot()==z
  b.save(HERE/'negative-tests.json',dict(check,zero_assignment_exact=True,C_null_zero_wrong_total_wrong_length_after_MLPG_rejected=True,invalid_update_left_state_unchanged=True,fixture_not_quality_evidence=True),j)
 for label,request in [('neutral',{'speed':1.,'half_tone':0.}),('higher',{'speed':1.15,'half_tone':12*np.log2(280/220)})]:
  records=[]
  for method,cls in [('native',NativeEngine),('zero_timing',Engine)]:
   with b.job(NAME,'render','ゼロ時計自己回復 '+label+'/'+method,reserve_bytes=3000000) as j:
    with cls(row,BUNDLE/'mei_normal.htsvoice',**request) as e:
     before=e.snapshot();var0=e.variance() if method=='zero_timing' else None
     if method=='zero_timing':
      d,notes=durations(row,before,lambda x:np.zeros(len(x)));e.modify_duration(d)
     after=e.snapshot();assert before==after;params=e.parameters();settings=e.get_settings();raw,conversion=synthesize(params,settings);assert e.snapshot()==after
     if var0 is not None:assert np.array_equal(var0,e.variance())
    audio=(raw*.25).astype(np.float32);path=HERE/'self-test'/label/(method+'.wav');b.write(path,wavbytes(audio),j);records.append(dict(wav_sha256=digest(path),parameter_hashes=[hashlib.sha256(q.astype('<f8').tobytes()).hexdigest() for q in params],state_hash=hashlib.sha256(encode(before)).hexdigest(),settings=settings))
    with b.job(NAME,'dsp','ゼロ時計E0 '+label+'/'+method,reserve_bytes=10000):
     assert evaluate(audio,{},24000)['E0_pass']
   print('ゼロ時計',label,method,flush=True)
  assert records[0]==records[1];results.append(dict(condition=label,all_parameters_states_wave_bitmatch=True,wav_sha256=records[0]['wav_sha256']))
 with b.job(NAME,'audit','非ゼロ時間の状態平均/分散/MSD保存と制約検査',reserve_bytes=200000) as j:
  with Engine(row,BUNDLE/'mei_normal.htsvoice') as e:
   before=e.snapshot();variance=e.variance();d,notes=durations(row,before,lambda x:np.linspace(-np.log(1.25),np.log(1.25),len(x)));a,z=e.modify_duration(d);assert a==before and np.array_equal(variance,e.variance())
   assert sum(d)==sum(before['duration']) and all(a[k]==z[k] for k in ['means','msd','layout']);params=e.parameters();assert all(np.isfinite(q).all() for q in params) and e.snapshot()==z
   changed=bool(d!=before['duration']);assert changed
  b.save(HERE/'self-test.json',dict(zero_bit_matches=results,nonzero_duration_changed=changed,total_time_fixed=True,means_variance_MSD_layout_preserved=True,after_MLPG_state_preserved=True,source_hashes={n:digest(HERE/n) for n in ['timing.c','timing.dylib','timing_engine.py','timing_control.py','self-test.py']},real_renders=4,new_DSP=4,training_or_unknown_not_yet_generated=True,passed=True,fixture_not_quality_evidence=True),j)
 print(b.reconcile(),flush=True)
if __name__=='__main__':main()
