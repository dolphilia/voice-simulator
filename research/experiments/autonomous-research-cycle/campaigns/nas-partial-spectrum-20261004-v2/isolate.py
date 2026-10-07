"""固定サイズbundleからtextのみで同じ候補を生成し、OSでも依存を拒否する。"""
import json,sys,subprocess
from paths import *

def main():
 b=Budget();p=read(HERE/'protocol.json');bundle=HERE/'runtime-bundle'
 with b.job(NAME,'setup','非ニューラルbundleと隔離profileを準備',reserve_bytes=2_000_000) as j:
  mapping={n:HERE/n for n in ['local_renderer.py','local_hts-v2.dylib','spectrum_renderer.py','counter.dylib']}
  mapping.update({n:SHARED/n for n in ['local_control.py','centered_projection.py']})
  mapping.update({n:BUNDLE/n for n in ['japanese_frontend.py','acoustics.py','mei_normal.htsvoice']})
  mapping['runtime.py']=HERE/'runtime-core.py'
  mapping.update({v+'.json':SRES/'models'/(v+'.json') for v in ['direct_non_neural','distilled_non_neural']})
  for n,path in mapping.items():b.write(bundle/n,path.read_bytes(),j)
  b.save(bundle/'manifest.json',{'files':{n:digest(bundle/n) for n in mapping},'final_non_neural':True,'utterance_tables':0,'teacher_audio':0},j)
  size=sum(q.stat().st_size for q in bundle.rglob('*') if q.is_file());assert size<=2_000_000
  forbidden=[SHARED,PILOT,COUNTER,REPO/'research/data',OLD/'.cache',HERE/'render',PREP]
  site=OLD/'.venv-eval/lib/python3.11/site-packages'
  forbidden += [site/n for n in ['torch','tensorflow','transformers','faster_whisper','ctranslate2','onnxruntime','sherpa_onnx'] if (site/n).exists()]
  profile='(version 1)\n(allow default)\n(deny network*)\n(deny file-read* '+''.join('(subpath '+json.dumps(str(x))+') ' for x in forbidden)+')\n'
  b.write(HERE/'isolation.sb',profile.encode(),j)
 pairs=[]
 for row in [p['rows'][8],p['rows'][12]]:
  for condition,request in row['requests'].items():
   for method in ['native','direct_non_neural','distilled_non_neural']:
    ident=row['id']+'/'+condition+'/'+method;expected=read(HERE/'render/partial'/(ident+'.json'))
    values=[]
    for mode in ['normal','isolated']:
     target=HERE/'runtime-check'/mode/(ident+'.wav')
     with b.job(NAME,'render','runtime '+mode+'/'+ident,count=2,reserve_bytes=3_000_000) as j:
      with b.job(NAME,'dsp','runtime E0 '+mode+'/'+ident,count=1,reserve_bytes=10000):
       cmd=[sys.executable,'-I','-B',str(bundle/'runtime.py'),'--text',row['text'],'--method',method,'--speed',str(request['speed']),'--pitch',str(request['requested_f0']),'--output',str(target)]
       if mode=='isolated':cmd=['/usr/bin/sandbox-exec','-f',str(HERE/'isolation.sb')]+cmd
       with b.external_output(target,2_000_000,j):result=subprocess.run(cmd,capture_output=True,text=True,check=True)
      value=json.loads(result.stdout);assert digest(target)==value['sha256']==expected['wav_sha256']
      assert value['synthesis_calls']==2 and value['E0_pass'] and not value['forbidden_imports']
      b.save(target.with_suffix('.json'),value,j);values.append(value)
    pairs.append({'id':ident,'normal_isolated_diagnostic_bit_match':values[0]['sha256']==values[1]['sha256']==expected['wav_sha256']})
    print('isolated',ident,flush=True)
 b.save(HERE/'runtime-audit.json',{'passed':len(pairs)==12 and all(r['normal_isolated_diagnostic_bit_match'] for r in pairs),
  'pairs':pairs,'bundle_bytes':size,'new_render_calls':48,'new_E0_calls':24,'network_and_teacher_neural_trajectory_reads_denied':True,'quality_certified':False})
 print(b.reconcile(),flush=True)
if __name__=='__main__':main()
