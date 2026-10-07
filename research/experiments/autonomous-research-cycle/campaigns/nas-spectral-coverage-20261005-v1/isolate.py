"""固定スペクトル回帰の未知文生成をNN/教師/旧軌跡拒否環境で照合する。"""
from paths import *
import json,sys,subprocess
SRC=ROOT/'campaigns/nas-source-identity-20261004-v1'
def main():
 b=Budget();p=read(HERE/'protocol.json');bundle=HERE/'runtime-bundle'
 with b.job(NAME,'setup','固定共有128係数bundleとOS隔離を準備',reserve_bytes=3000000) as j:
  mapping={n:SRC/n for n in ['local_renderer.py','local_hts-v2.dylib','source_renderer.py','counter.dylib','counter.c']};mapping.update({n:HERE/n for n in ['spectral_model.py','local_control.py','centered_projection.py']});mapping.update({n:BUNDLE/n for n in ['japanese_frontend.py','mei_normal.htsvoice','acoustics.py','LICENSE-HTSVOICE']});mapping['world_renderer2.py']=WORLD/'world_renderer2.py';mapping['runtime.py']=HERE/'runtime-core.py'
  mapping.update({n+'.json':HERE/'models'/(n+'.json') for n in ['direct17','student17','direct96','student96']})
  for n in ['HTS_engine.h','HTS_hidden.h']:mapping[n]=WORLD/'vendor'/n
  mapping['LICENSE-WORLD.txt']=WORLD/'upstream/LICENSE-WORLD.txt';mapping['KOKORO-model-README.md']=PILOT/'.cache/teacher/README.md';mapping['KOKORO-VOICES.md']=PILOT/'.cache/teacher/VOICES.md'
  for q in (WORLD/'packages-v2').rglob('*'):
   if q.is_file():mapping['packages-v2/'+str(q.relative_to(WORLD/'packages-v2'))]=q
  for n,path in mapping.items():b.write(bundle/n,path.read_bytes(),j)
  b.save(bundle/'manifest.json',dict(files={n:digest(bundle/n) for n in mapping},final_non_neural=True,utterance_tables=0,teacher_audio=0,shared_spectral_regression_coefficients=128,neural_control_network_present=False,quality_certified=False),j)
  size=sum(q.stat().st_size for q in bundle.rglob('*') if q.is_file());assert size<=2000000
  forbidden=[q for q in (ROOT/'campaigns').iterdir() if q!=HERE]+[SHARED,PILOT,COUNTER,REPO/'research/data',OLD/'.cache',HERE/'render',HERE/'models',HERE/'targets',HERE/'protocol.json',HERE/'training-contract.json',ROOT/'control'];site=OLD/'.venv-eval/lib/python3.11/site-packages';forbidden += [site/n for n in ['torch','tensorflow','transformers','faster_whisper','ctranslate2','onnxruntime','sherpa_onnx'] if (site/n).exists()]
  profile='(version 1)\n(allow default)\n(deny network*)\n(deny file-read* '+''.join('(subpath '+json.dumps(str(x))+') ' for x in forbidden)+')\n';b.write(HERE/'isolation.sb',profile.encode(),j)
 pairs=[]
 for row in [r for r in p['rows'] if r['cohort']=='prospective_once']:
  for condition,request in row['requests'].items():
   for method in ['native','direct17','student17','direct96','student96']:
    ident=row['id']+'/'+condition+'/'+method;expected=read(HERE/'render/diagnostic'/(ident+'.json'));values=[]
    for mode in ['normal','isolated']:
     target=HERE/'runtime-check'/mode/(ident+'.wav')
     with b.job(NAME,'render','runtime '+mode+'/'+ident,reserve_bytes=3000000) as j:
      with b.job(NAME,'dsp','runtime E0 '+mode+'/'+ident,reserve_bytes=10000):
       cmd=['/usr/bin/sandbox-exec','-f',str(HERE/('isolation.sb' if mode=='isolated' else 'offline.sb')),sys.executable,'-I','-B',str(bundle/'runtime.py'),'--text',row['text'],'--method',method,'--speed',str(request['speed']),'--pitch',str(request['requested_f0']),'--output',str(target)]
       with b.external_output(target,2000000,j):
        process=subprocess.run(cmd,capture_output=True,text=True);assert process.returncode==0,process.stderr
      value=json.loads(process.stdout);assert digest(target)==value['sha256']==expected['wav_sha256'];assert value['synthesis_calls']==1 and value['E0_pass'] and not value['forbidden_imports'];b.save(target.with_suffix('.json'),value,j);values.append(value)
    pairs.append(dict(id=ident,bit_match=values[0]['sha256']==values[1]['sha256']==expected['wav_sha256']));print('isolated',ident,flush=True)
 blocked=[HERE/'models/neural96.pt',HERE/'models/direct96.json',HERE/'render/diagnostic/coverage-fresh-00/neutral/native.wav',SPECTRAL1/'native/development-00.parameters.npz',JP/'models/teacher/jvnv-F1-jp/jvnv-F1-jp_e160_s14000.safetensors']
 probe="import socket,json;paths="+repr([str(x) for x in blocked])+";a=[]\nfor p in paths:\n try:open(p,'rb');a.append(False)\n except PermissionError:a.append(True)\ns=socket.socket()\ntry:s.bind(('127.0.0.1',0));net=False\nexcept PermissionError:net=True\nprint(json.dumps({'read_denied':a,'network_denied':net}))"
 with b.job(NAME,'audit','OS拒否probeでNN/教師/係数旧保存/波形/軌跡/通信を検査',reserve_bytes=10000) as j:
  result=subprocess.run(['/usr/bin/sandbox-exec','-f',str(HERE/'isolation.sb'),sys.executable,'-I','-B','-c',probe],capture_output=True,text=True);assert result.returncode==0,result.stderr;proof=json.loads(result.stdout);assert all(proof['read_denied']) and proof['network_denied'];b.save(HERE/'denial-probe.json',proof,j)
 b.save(HERE/'runtime-audit.json',dict(passed=len(pairs)==160 and all(r['bit_match'] for r in pairs),pairs=pairs,new_render_calls=320,new_E0_calls=320,bundle_bytes=size,denial_probe=proof,final_non_neural=True,quality_certified=False));print(b.reconcile(),flush=True)
if __name__=='__main__':main()
