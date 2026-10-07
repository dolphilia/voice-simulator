"""二教師24波形のWORLD解析再合成を、最終文章合成と分離して検査する。"""
from paths import *
from signal_measurement import measure_record,pw,packed,np
from teacher_common import wavbytes
from scipy.io import wavfile

def main():
 b=Budget();p=read(HERE/'protocol.json');records=[]
 for teacher in p['teachers']:
  for row in p['fresh_rows']:
   source=HERE/'teacher'/teacher/(row['id']+'.json');r=measure_record(b,row,source);records.append(r)
   target=HERE/'world'/teacher/row['id']
   if not target.with_suffix('.json').exists():
    with b.job(NAME,'render','WORLD研究用再合成 '+teacher+'/'+row['id'],reserve_bytes=100000000) as j:
     fs,x=wavfile.read(REPO/r['wav']);assert fs==24000 and digest(REPO/r['DIO_file'])==r['DIO_sha256'];dio=np.load(REPO/r['DIO_file']);f0,t=dio['f0'],dio['times']
     with b.job(NAME,'dsp','CheapTrick/D4C '+teacher+'/'+row['id'],count=2):
      sp=pw.cheaptrick(x.astype(float),f0,t,24000,fft_size=2048);ap=pw.d4c(x.astype(float),f0,t,24000,threshold=.85,fft_size=2048)
     raw=pw.synthesize(f0,sp,ap,24000,frame_period=5.);assert len(raw)>=len(x);out=raw[:len(x)].astype(np.float32)
     assert np.isfinite(out).all() and np.max(abs(out))<1,'再合成clip/nonfinite：事後gain変更しない'
     b.write(target.with_suffix('.wav'),wavbytes(out),j);b.write(target.with_suffix('.parameters.npz'),packed(f0=f0,times=t,power=sp,AP=ap),j)
     value=dict(row,id=row['id']+'/neutral/'+teacher,variant=teacher,mode='world',factor=1,condition='neutral',status='generated',wav=str(target.with_suffix('.wav').relative_to(REPO)),wav_sha256=digest(target.with_suffix('.wav')),teacher_wave_sha256=r['wav_sha256'],parameters=str(target.with_suffix('.parameters.npz').relative_to(REPO)),parameters_sha256=digest(target.with_suffix('.parameters.npz')),normalization={'candidate_gain':1.,'teacher_common_factor_already_in_power':.25,'candidate_peak_normalization':False,'crop_to_teacher_samples':len(x)},requires_teacher_audio_at_runtime=True,final_text_synthesis=False,research_only=True,quality_certified=False)
     b.save(target.with_suffix('.json'),value,j)
   records.append(measure_record(b,row,target.with_suffix('.json')));print('resynth',teacher,row['id'],flush=True)
  b.reconcile()
 assert len(records)==32
 b.save(HERE/'fresh-source-manifest.json',{'rows':[{'id':r['mode']+'/'+r['id'],'record':str((HERE/('teacher' if r['mode']=='teacher' else 'world')/r['variant']/(r['id'].split('/')[0]+'.measured.json')).relative_to(REPO)),'wav':r['wav'],'wav_sha256':r['wav_sha256']} for r in records],'search_completed_before_ASR':True,'audio_and_analysis_completed_before_ASR':True,'final_text_synthesis':False,'all_E0_pass':all(r['E0_pass'] for r in records),'planned_ASR_calls':64,'quality_certified':False})
 print(b.reconcile(),flush=True)
if __name__=='__main__':main()
