"""研究資産を拒否する子プロセスで固定4係数の未知文生成を検証する。"""
import json,sys,subprocess
from paths import *
def main():
 b=Budget();p=read(HERE/'protocol.json');bundle=HERE/'runtime-bundle'
 with b.job(NAME,'setup','韻律4係数の固定bundleとOS隔離を準備',reserve_bytes=2_500_000) as j:
  mapping={n:HERE/n for n in ['local_renderer.py','local_hts-v2.dylib','prosody_model.py','source_renderer.py','counter.dylib','counter.c','world_renderer2.py']}
  mapping.update({n:SHARED/n for n in ['local_control.py','centered_projection.py']});mapping.update({n:BUNDLE/n for n in ['japanese_frontend.py','mei_normal.htsvoice','acoustics.py']});mapping['runtime.py']=HERE/'runtime-core.py'
  mapping.update({n+'.json':CONTROL/'models'/(n+'.json') for n in ['direct_prosody','distilled_prosody']})
  mapping.update({n+'.json':SRES/'models'/(n+'.json') for n in ['direct_non_neural','distilled_non_neural']})
  mapping['LICENSE-HTSVOICE']=BUNDLE/'LICENSE-HTSVOICE'
  mapping['HTS_engine.h']=HERE/'vendor/HTS_engine.h';mapping['HTS_hidden.h']=HERE/'vendor/HTS_hidden.h'
  mapping['LICENSE-WORLD.txt']=HERE/'upstream/LICENSE-WORLD.txt'
  for q in (HERE/'packages-v2').rglob('*'):
   if q.is_file():mapping['packages-v2/'+str(q.relative_to(HERE/'packages-v2'))]=q
  for n,path in mapping.items():b.write(bundle/n,path.read_bytes(),j)
  b.save(bundle/'manifest.json',{'files':{n:digest(bundle/n) for n in mapping},'final_non_neural':True,'utterance_tables':0,'teacher_audio':0},j)
  size=sum(q.stat().st_size for q in bundle.rglob('*') if q.is_file());assert size<=2_000_000
  forbidden=[SHARED,PILOT,COUNTER,REPO/'research/data',OLD/'.cache',HERE/'render',PREP,CURRENT,CONTROL,PREVIOUS,ROOT/'campaigns/nas-prosody-only-20261004-v1']
  site=OLD/'.venv-eval/lib/python3.11/site-packages';forbidden += [site/n for n in ['torch','tensorflow','transformers','faster_whisper','ctranslate2','onnxruntime','sherpa_onnx'] if (site/n).exists()]
  profile='(version 1)\n(allow default)\n(deny network*)\n(deny file-read* '+''.join('(subpath '+json.dumps(str(x))+') ' for x in forbidden)+')\n';b.write(HERE/'isolation.sb',profile.encode(),j)
 pairs=[]
 for row in [p['rows'][8],p['rows'][12]]:
  for condition,request in row['requests'].items():
   for method in ['native','direct_non_neural','distilled_non_neural','direct_prosody','distilled_prosody']:
    ident=row['id']+'/'+condition+'/'+method;expected=read(HERE/'render/world'/(ident+'.json'));values=[]
    for mode in ['normal','isolated']:
     target=HERE/'runtime-check'/mode/(ident+'.wav')
     with b.job(NAME,'render','runtime '+mode+'/'+ident,count=2,reserve_bytes=3_000_000) as j:
      with b.job(NAME,'dsp','runtime E0 '+mode+'/'+ident,reserve_bytes=10000):
       cmd=['/usr/bin/sandbox-exec','-f',str(HERE/('isolation.sb' if mode=='isolated' else 'offline.sb')),sys.executable,'-I','-B',str(bundle/'runtime.py'),'--text',row['text'],'--method',method,'--speed',str(request['speed']),'--pitch',str(request['requested_f0']),'--output',str(target)]
       with b.external_output(target,2_000_000,j):
        result=subprocess.run(cmd,capture_output=True,text=True)
        assert result.returncode==0,result.stderr
      value=json.loads(result.stdout);assert digest(target)==value['sha256']==expected['wav_sha256'];assert value['E0_pass'] and value['synthesis_calls']==2 and not value['forbidden_imports']
      b.save(target.with_suffix('.json'),value,j);values.append(value)
    pairs.append({'id':ident,'bit_match':values[0]['sha256']==values[1]['sha256']==expected['wav_sha256']});print('isolated',ident,flush=True)
 b.save(HERE/'runtime-audit.json',{'passed':len(pairs)==20 and all(r['bit_match'] for r in pairs),'pairs':pairs,'new_render_calls':80,'new_E0_calls':40,'bundle_bytes':size,'quality_certified':False,'final_non_neural':True,'network_teacher_NN_trajectory_reads_denied':True})
 print(b.reconcile(),flush=True)
if __name__=='__main__':main()
