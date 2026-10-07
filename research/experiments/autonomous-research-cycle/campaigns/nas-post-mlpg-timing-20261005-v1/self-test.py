"""ゼロ時計の自己回復と、状態内補間によるLF0・混在列保持を検証する。"""
from paths import *
import sys,math,hashlib,numpy as np
SRC=ROOT/'campaigns/nas-source-identity-20261004-v1'
sys.path[:0]=[str(HERE),str(SRC),str(WORLD),str(SHARED),str(BUNDLE)]
from timing_engine import Engine
from state_event_control import durations
from timing_control import LOGBOUND
from post_mlpg_warp import warp
from world_renderer2 import synthesize
from teacher_common import wavbytes
from acoustics import evaluate
def ah(x):return hashlib.sha256(np.asarray(x,dtype='<f8').tobytes()).hexdigest()
def main():
 b=Budget();row=next(r for r in read(TIME/'protocol.json')['rows'] if r['id']=='timing-fresh-00');pairs=[]
 for condition,request in row['requests'].items():
  expected=read(TIME/'render/diagnostic'/row['id']/condition/'native.json');values=[]
  for mode in ['native','pre_zero','post_zero']:
   with b.job(NAME,'render','MLPG前後ゼロ自己回復 '+condition+'/'+mode,reserve_bytes=4000000) as j:
    with Engine(row,BUNDLE/'mei_normal.htsvoice',speed=request['speed'],half_tone=12*math.log2(request['requested_f0']/220)) as e:
     before=e.snapshot();variance=e.variance();settings=e.get_settings()
     d,notes=durations(row,before,lambda x:np.zeros(len(x)));assert d==before['duration']
     if mode=='pre_zero':_,after=e.modify_duration(d);assert after==before
     params=e.parameters()
     if mode=='post_zero':params,info=warp(params,before['duration'],d,before['msd']);assert info['changed_states']==0
     raw,_=synthesize(params,settings);assert e.snapshot()==before and np.array_equal(variance,e.variance())
    audio=(raw*.25).astype(np.float32)
    with b.job(NAME,'dsp','ゼロfixture E0 '+condition+'/'+mode,reserve_bytes=1000):assert evaluate(audio,{},24000)['E0_pass']
    path=HERE/'self-test'/condition/(mode+'.wav');b.write(path,wavbytes(audio),j)
    v=dict(wav_sha256=digest(path),parameter_hashes=[ah(q) for q in params],duration=before['duration'])
    assert v['wav_sha256']==expected['wav_sha256'] and v['parameter_hashes']==expected['parameter_hashes']
    b.save(path.with_suffix('.json'),v,j);values.append(v)
  assert values[0]==values[1]==values[2];pairs.append(dict(condition=condition,pre_post_zero_bit_match=True))
 with b.job(NAME,'setup','状態内補間の非ゼロ・負例・混在列の完全保持検査',reserve_bytes=20000) as j:
  with Engine(row,BUNDLE/'mei_normal.htsvoice',speed=1.,half_tone=0.) as e:
   before=e.snapshot();variance=e.variance();settings=e.get_settings();params=e.parameters()
   d,notes=durations(row,before,lambda x:np.linspace(-LOGBOUND,LOGBOUND,len(x)))
   assert d!=before['duration'],'既知fixtureの非ゼロ差を要求'
   out,info=warp(params,before['duration'],d,before['msd'])
   assert info['changed_states']>0 and info['mixed_phone_count']>0 and info['mixed_parameter_blocks_exact']
   assert e.snapshot()==before and np.array_equal(variance,e.variance()) and e.get_settings()==settings
  old=np.full(10,2);new=old.copy();new[5:]=[1,3,2,2,2];msd=np.array([1,1,1,0,0,1,1,1,1,1.])
  p=[np.arange(20*d,dtype=float).reshape(20,d) for d in [35,1,31]];p[1][:,0]=np.where(np.repeat(msd>.5,old),5+np.arange(20)/100,-1e10)
  result,fixture=warp(p,old,new,msd)
  assert result[0][:10].tobytes()==p[0][:10].tobytes() and result[1][:10].tobytes()==p[1][:10].tobytes() and result[2][:10].tobytes()==p[2][:10].tobytes()
  assert result[1][10,0]==p[1][10:12,0].mean()
  bad=[]
  invalid=new.copy();invalid[0]-=1;invalid[1]+=1;bad.append((p,old,invalid,msd))
  invalid=new.copy();invalid[5]=0;invalid[6]+=1;bad.append((p,old,invalid,msd))
  invalid=new.copy();invalid[5]+=1;bad.append((p,old,invalid,msd))
  q=[x.copy() for x in p];q[1][6,0]=5;bad.append((q,old,new,msd))
  q=[x.copy() for x in p];q[0][0,0]=np.nan;bad.append((q,old,new,msd))
  q=[x.copy() for x in p];q[2]=q[2][:,:3];bad.append((q,old,new,msd))
  for args in bad:
   try:warp(*args)
   except ValueError:pass
   else:raise AssertionError('不正な補間入力を拒否できない')
  b.save(HERE/'self-test.json',dict(passed=True,pairs=pairs,render_calls=6,E0_calls=6,native_parameter_dimensions=[35,1,31],native_engine_clock_preserved_post=True,mixed_parameter_blocks_exact=True,LF0_mask_matches_state_MSD=True,negative_cases_passed=len(bad),real_nonzero_warp=info,fixture_not_quality_evidence=True,source_sha256=digest(HERE/'post_mlpg_warp.py'),inherited_C_validation_sha256=digest(TIME/'self-test.json')),j)
 print('MLPG前後ゼロ回復・実非ゼロ補間・負例を確認',flush=True);print(b.reconcile(),flush=True)
if __name__=='__main__':main()
