"""固定二ASRを、生成と隔離監査が終わった波形へ適用する。"""
import argparse,os,sys,time
from math import gcd
from paths import *
os.environ['HF_HUB_OFFLINE']='1'
sys.path[:0]=[str(OLD),str(PILOT/'.cache/packages')]
from diagnostics import normalize_text,edit_distance
import pyopenjtalk,numpy as np
from scipy import signal
from scipy.io import wavfile

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--engine',choices=['whisper','reazon'],required=True);name=parser.parse_args().engine
 b=Budget();engine=read(HERE/'engine-contract.json');p=read(HERE/'protocol.json')
 ec=read(HERE/'execution-contract.json')
 for n,h in ec['source_hashes'].items():assert digest(HERE/n)==h
 for n,h in engine['asr_model_hashes'].items():assert digest(REPO/n)==h
 assert digest(OLD/'diagnostics.py')==engine['normalizer_source_sha256']
 assert engine==read(ERES/'engine-contract.json')
 cfg=engine['reading_diagnostic']['contract']
 for n,h in cfg['dictionary_files'].items():assert digest(Path(cfg['dictionary_path'])/n)==h
 assert digest(cfg['library'])==cfg['library_sha256']
 with b.job(NAME,'setup','固定ASR読込 '+name,reserve_bytes=10000):
  if name=='whisper':
   from faster_whisper import WhisperModel
   recognizer=WhisperModel(engine['whisper_path'],device='cpu',compute_type='int8',cpu_threads=4,local_files_only=True)
  else:
   import sherpa_onnx
   cache=PILOT/'.cache/reazonspeech'
   recognizer=sherpa_onnx.OfflineRecognizer.from_transducer(encoder=str(cache/'encoder-epoch-99-avg-1.int8.onnx'),
    decoder=str(cache/'decoder-epoch-99-avg-1.int8.onnx'),joiner=str(cache/'joiner-epoch-99-avg-1.int8.onnx'),tokens=str(cache/'tokens.txt'),
    num_threads=2,sample_rate=16000,feature_dim=80,decoding_method='greedy_search',provider='cpu')
 cache={};reused=0;new=0;records=[]
 assert read(HERE/'runtime-audit.json')['passed']
 manifest=read(HERE/'render-manifest.json');assert manifest['search_completed_before_ASR']
 with b.job(NAME,'audit','保存認識再利用と全転記 '+name,reserve_bytes=8_000_000) as copyjob:
  for item in manifest['rows']:
   target=HERE/'asr'/name/(item['id']+'.json')
   if target.exists():records.append({'path':str(target.relative_to(REPO)),'sha256':digest(target)});continue
   r=read(REPO/item['record']);assert digest(REPO/r['wav'])==r['wav_sha256']
   result={k:r[k] for k in ('id','text','cohort','length','challenge_group','condition','variant','mode','factor','wav','wav_sha256')}
   result.update(engine=name,status='failed',quality_certified=False,used_in_optimization=False,protocol_sha256=digest(HERE/'protocol.json'),engine_contract_sha256=digest(HERE/'engine-contract.json'))
   key=(r['wav_sha256'],r['text'])
   oldpath=ERES/'asr'/name/(r['id']+'.json')
   previous=None
   if key in cache:previous,path=cache[key]
   elif False: # 共通利得変更後のwaveへ旧ASRを転記しない
    value=read(oldpath)
    if value['status']=='completed' and value['wav_sha256']==r['wav_sha256'] and value['text']==r['text']:
     assert value['protocol_sha256']==digest(ERES/'protocol.json');assert digest(REPO/value['wav'])==value['wav_sha256']
     previous,path=value,oldpath
   if previous:
    assert previous['reference_kana']==normalize_text(pyopenjtalk.g2p(r['text'],kana=True))
    result.update({k:previous[k] for k in ('duration_seconds','hypothesis','reference_kana','predicted_kana','errors','characters','kana_cer')})
    result.update(status='completed',ai_calls=0,reused_from=str(path.relative_to(REPO)),reused_sha256=digest(path))
    b.save(target,result,copyjob);reused+=1
   else:
    with b.job(NAME,'ai',name+'/'+item['id'],reserve_bytes=30000) as j:
     fs,raw=wavfile.read(REPO/r['wav']);assert raw.ndim==1 and len(raw)/fs<=30
     started=time.monotonic()
     if name=='whisper':
      segments,_=recognizer.transcribe(str(REPO/r['wav']),language='ja',beam_size=5,initial_prompt=None,condition_on_previous_text=False,vad_filter=False)
      hypothesis=''.join(s.text for s in segments)
     else:
      audio=raw.astype(np.float32)/(32768. if raw.dtype==np.int16 else 1.)
      g=gcd(fs,16000);audio=signal.resample_poly(audio,16000//g,fs//g).astype(np.float32)
      stream=recognizer.create_stream();stream.accept_waveform(16000,audio);recognizer.decode_stream(stream);hypothesis=stream.result.text
     ref=normalize_text(pyopenjtalk.g2p(r['text'],kana=True));pred=normalize_text(pyopenjtalk.g2p(hypothesis,kana=True)) if hypothesis else ''
     errors=edit_distance(ref,pred)
     result.update(status='completed',ai_calls=1,hypothesis=hypothesis,reference_kana=ref,predicted_kana=pred,
      errors=errors,characters=len(ref),kana_cer=errors/max(1,len(ref)),duration_seconds=len(raw)/fs,seconds=time.monotonic()-started)
     b.save(target,result,j);new+=1
   cache[key]=(result,target);records.append({'path':str(target.relative_to(REPO)),'sha256':digest(target)})
   if len(records)%32==0:print(name,len(records),'/1008',flush=True)
  b.save(HERE/('asr-manifest-'+name+'.json'),{'rows':records,'new_ai':new,'reused':reused,'optimization_after_asr':False},copyjob)
 print({'engine':name,'new_ai':new,'reused':reused,'records':len(records)},flush=True)
 b.reconcile()
if __name__=='__main__':main()
