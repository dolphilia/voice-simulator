"""音声payloadを保持する無音境界と、固定端点taperを別に比較する。"""
from paths import *
from teacher_common import wavbytes
from signal_measurement import measure_record,np
from scipy.io import wavfile
POLICIES=['raw','pad_900ms','taper12ms_pad900ms']
def transform(x,policy):
 x=np.asarray(x,dtype=np.float32);speech=x.copy();pad=0;fade=0
 if policy=='taper12ms_pad900ms':
  fade=288;assert len(speech)>2*fade;w=np.linspace(0.,1.,fade,dtype=np.float32);speech[:fade]*=w;speech[-fade:]*=w[::-1]
  assert np.array_equal(speech[fade:-fade],x[fade:-fade]) and speech[0]==speech[-1]==0
 if policy!='raw':pad=21600
 out=np.pad(speech,(pad,pad));assert len(out)==len(x)+2*pad and np.array_equal(out[pad:pad+len(x)],speech)
 if not fade:assert np.array_equal(speech,x)
 return out,dict(pad_samples_each_side=pad,speech_offset_seconds=pad/24000,source_samples=len(x),fade_samples_each_side=fade,source_payload_exact=not fade,interior_payload_exact=True,embedded_speech_endpoint_amplitude=float(max(abs(speech[0]),abs(speech[-1]))),internal_join_continuity=float(max(abs(speech[0]),abs(speech[-1])))<=1e-6)
def tests():
 x=np.linspace(.1,.2,2000,dtype=np.float32)
 for q in POLICIES:
  y,a=transform(x,q);assert a['internal_join_continuity']==(q=='taper12ms_pad900ms')
 return dict(clock_and_middle_payload_preserved=True,padding_only_discontinuity_rejected=True,taper_endpoints_exact_zero=True,fixture_not_quality_evidence=True)
def main():
 b=Budget();p=read(HERE/'protocol.json');rows=[]
 with b.job(NAME,'audit','音声境界のclock/payload/内部step検査fixture',reserve_bytes=10000) as j:b.save(HERE/'boundary-self-test.json',tests(),j)
 for row in p['rows']:
  base=HERE if row['cohort']=='prospective_once' else JP
  for mode in ['teacher','world']:
   for teacher in p['teachers']:
    source=base/mode/teacher/(row['id']+'.measured.json');r=read(source);assert digest(REPO/r['wav'])==r['wav_sha256'];fs,x=wavfile.read(REPO/r['wav']);assert fs==24000 and x.dtype==np.float32
    for policy in POLICIES:
     target=HERE/'render'/mode/row['id']/policy/teacher
     with b.job(NAME,'render','固定境界 '+mode+'/'+row['id']+'/'+policy+'/'+teacher,reserve_bytes=5000000) as j:
      out,details=transform(x,policy);assert np.isfinite(out).all() and np.max(abs(out))<1 and len(out)/24000<=30
      b.write(target.with_suffix('.wav'),wavbytes(out),j)
      if policy=='raw':assert digest(target.with_suffix('.wav'))==r['wav_sha256']
      payload_checks=r['measurement']['E0']['checks'];payload_safe=all(v for k,v in payload_checks.items() if k!='endpoint_continuity')
      v=dict(row,id=row['id']+'/'+policy+'/'+teacher,condition=policy,variant=teacher,mode=mode,factor=POLICIES.index(policy),status='generated',wav=str(target.with_suffix('.wav').relative_to(REPO)),wav_sha256=digest(target.with_suffix('.wav')),source_record=str(source.relative_to(REPO)),source_wav_sha256=r['wav_sha256'],boundary=details,source_payload_checks_except_endpoint_pass=payload_safe,research_only=True,quality_certified=False,final_text_synthesis=False)
      b.save(target.with_suffix('.json'),v,j)
     measured=measure_record(b,row,target.with_suffix('.json'));rows.append({'id':mode+'/'+v['id'],'record':str(target.with_suffix('.measured.json').relative_to(REPO)),'wav':v['wav'],'wav_sha256':v['wav_sha256']})
  print('boundary',row['id'],flush=True)
 assert len(rows)==240
 b.save(HERE/'render-manifest.json',{'rows':rows,'search_completed_before_ASR':True,'audio_and_analysis_completed_before_ASR':True,'final_text_synthesis':False,'planned_ASR_records':480,'old_raw_reuse_requires_exact_wave_text_engine_hash':True,'quality_certified':False});print(b.reconcile(),flush=True)
if __name__=='__main__':main()
