"""1音声ごとの予約を維持し、160通常/隔離waveを単一archiveずつで照合する。"""
from paths import *
from storage_budget import StorageBudget
Budget=StorageBudget
import sys,json,subprocess,zipfile,hashlib,time
SRC=ROOT/'campaigns/nas-source-identity-20261004-v1'
def put(b,path,data,j):
 if path.exists():assert path.read_bytes()==data,'凍結準備の不一致 '+str(path)
 else:b.write(path,data,j)
def main():
 b=Budget();p=read(HERE/'protocol.json');bundle=HERE/'runtime-storage-bundle'
 with b.job(NAME,'setup','同固定係数と時計policyの最終bundle/隔離を準備',reserve_bytes=5000000) as j:
  mapping={n:SRC/n for n in ['local_renderer.py','local_hts-v2.dylib','source_renderer.py','counter.dylib','counter.c']}
  mapping.update({n:HERE/n for n in ['timing_control.py','timing_engine.py','timing.c','timing.dylib','state_event_control.py','post_mlpg_warp.py','local_control.py','centered_projection.py']})
  mapping.update({n:BUNDLE/n for n in ['japanese_frontend.py','mei_normal.htsvoice','acoustics.py','LICENSE-HTSVOICE']})
  mapping['world_renderer2.py']=WORLD/'world_renderer2.py';mapping['runtime.py']=HERE/'runtime-storage.py';mapping['runtime-batch.py']=HERE/'runtime-storage-batch.py'
  mapping.update({n:HERE/n for n in ['storage_output.py','storage-output-config.json']});mapping['storage_guard.py']=ROOT/'storage_guard.py'
  mapping.update({n+'.json':HERE/'models'/(n+'.json') for n in ['direct','student']})
  for n in ['HTS_engine.h','HTS_hidden.h']:mapping[n]=HERE/'vendor'/n
  mapping['LICENSE-WORLD.txt']=WORLD/'upstream/LICENSE-WORLD.txt';mapping['KOKORO-model-README.md']=PILOT/'.cache/teacher/README.md';mapping['KOKORO-VOICES.md']=PILOT/'.cache/teacher/VOICES.md'
  for q in (WORLD/'packages-v2').rglob('*'):
   if q.is_file():mapping['packages-v2/'+str(q.relative_to(WORLD/'packages-v2'))]=q
  for n,path in mapping.items():put(b,bundle/n,path.read_bytes(),j)
  put(b,bundle/'manifest.json',encode(dict(files={n:digest(bundle/n) for n in mapping},final_non_neural=True,utterance_tables=0,teacher_audio=0,shared_timing_regression_coefficients_each=58,normalization_values_each=116,neural_control_network_present=False,quality_certified=False)),j)
  size=sum(q.stat().st_size for q in bundle.rglob('*') if q.is_file());assert size<=2000000
  forbidden=[q for q in (ROOT/'campaigns').iterdir() if q!=HERE]+[SHARED,PILOT,COUNTER,REPO/'research/data',OLD/'.cache',HERE/'render',HERE/'models',HERE/'targets',HERE/'protocol.json',HERE/'registration.json',HERE/'registration2.json',HERE/'model-comparison.json',HERE/'model-reuse-audit.json',HERE/'training-render-reuse-audit.json',HERE/'novelty-audit.json',HERE/'self-test',HERE/'self-test.json',ROOT/'control']
  site=OLD/'.venv-eval/lib/python3.11/site-packages';forbidden += [site/n for n in ['torch','tensorflow','transformers','faster_whisper','ctranslate2','onnxruntime','sherpa_onnx'] if (site/n).exists()]
  profile='(version 1)\n(allow default)\n(deny network*)\n(deny file-read* '+''.join('(subpath '+json.dumps(str(x))+') ' for x in forbidden)+')\n'+'(deny file-read-data '+''.join('(subpath '+json.dumps(str(HERE/n))+') ' for n in ['runtime-check','runtime-archives','runtime-cli'])+')\n';profile+='(deny file-read-data (subpath '+json.dumps(str(b.guard.root))+'))\n(allow file-read-data (literal '+json.dumps(str(b.guard.root/'identity.json'))+'))\n';output_base=b.guard.root/b.storage['cycle_directory']/str(HERE.relative_to(ROOT));allowed={b.guard.root}
  targets=[output_base/'runtime-archives']
  for row in p['rows']:
   if row['cohort']=='prospective_once':
    for condition in row['requests']:
     for mode in ['normal','isolated']:targets.append(output_base/'runtime-cli'/mode/row['id']/condition)
  for target in targets:
   allowed.update(parent for parent in [target,*target.parents] if parent==b.guard.root or b.guard.root in parent.parents)
  profile+='(allow file-read-data '+''.join('(literal '+json.dumps(str(q))+') ' for q in sorted(allowed))+')\n';put(b,HERE/'isolation-storage-02.sb',profile.encode(),j)
  requests=[]
  for row in [r for r in p['rows'] if r['cohort']=='prospective_once']:
   for condition,q in row['requests'].items():
    for method in ['native','direct_pre','student_pre','direct_post','student_post']:
     requests.append(dict(id=row['id']+'/'+condition+'/'+method,text=row['text'],method=method,speed=q['speed'],pitch=q['requested_f0']))
  assert len(requests)==160;put(b,HERE/'runtime-requests.json',encode(requests),j)
 if '--prepare-only' in sys.argv:print('bundle/profile/requestsを初比較前に固定',flush=True);return
 outputs={};timings={}
 for mode in ['normal','isolated']:
  path=HERE/'runtime-archives'/(mode+'.zip');started=time.monotonic()
  with b.job(NAME,'render','batch160 '+mode,count=160,reserve_bytes=180000000) as j:
   with b.job(NAME,'dsp','batch160 E0 '+mode,count=160,reserve_bytes=10000):
    with b.external_output(path,100000000,j):
     cmd=['/usr/bin/sandbox-exec','-f',str(HERE/('isolation-storage-02.sb' if mode=='isolated' else 'offline.sb')),sys.executable,'-I','-B',str(bundle/'runtime-batch.py'),'--requests',str(HERE/'runtime-requests.json'),'--output',str(path)]
     result=subprocess.run(cmd,text=True);assert result.returncode==0,'batch子プロセスが失敗'
   timings[mode]=time.monotonic()-started;records={}
   with zipfile.ZipFile(path) as z:
    expected_names={'manifest.json'}|{r['id']+suffix for r in requests for suffix in ['.wav','.json']};assert set(z.namelist())==expected_names and len(z.namelist())==321
    manifest=json.loads(z.read('manifest.json'));assert manifest['synthesis_calls']==manifest['E0_calls']==160 and manifest['no_generation_deduplication'] and len(manifest['records'])==160
    for request,r in zip(requests,manifest['records']):
     assert r['id']==request['id'];ident=r['id'];meta=json.loads(z.read(ident+'.json'));assert {k:v for k,v in r.items() if k!='id'}==meta
     data=z.read(ident+'.wav');expected=read(HERE/'render/diagnostic'/(ident+'.json'));assert hashlib.sha256(data).hexdigest()==r['sha256']==expected['wav_sha256']
     assert r['E0_pass'] and r['synthesis_calls']==r['E0_calls']==1 and not r['forbidden_imports']
     assert r['mixed_state_duration_fixed']
     if request['method'].endswith('_post'):assert r['mixed_parameter_blocks_exact'] and not r['engine_state_clock_changed']
     target=HERE/'runtime-check'/mode/(ident+'.wav');b.write(target,data,j);b.save(target.with_suffix('.json'),meta,j);records[ident]=meta
   b.save(HERE/('runtime-batch-'+mode+'.json'),dict(archive_sha256=digest(path),records=records,synthesis_calls=160,E0_calls=160,seconds_including_inventory=timings[mode],all_match=True),j);outputs[mode]=records
 pairs=[dict(id=r['id'],bit_match=outputs['normal'][r['id']]['sha256']==outputs['isolated'][r['id']]['sha256']) for r in requests];assert len(pairs)==160 and all(r['bit_match'] for r in pairs)
 # 単独CLIとbatchの同値を新短/長の二つ・両環境で検査する。
 cli=[]
 for request in [requests[0],requests[-1]]:
  for mode in ['normal','isolated']:
   target=HERE/'runtime-cli'/mode/(request['id']+'.wav')
   with b.job(NAME,'render','単独/batch同値 '+mode+'/'+request['id'],reserve_bytes=3000000) as j:
    with b.job(NAME,'dsp','単独CLI E0 '+mode+'/'+request['id'],reserve_bytes=10000):
     with b.external_output(target,2000000,j):
      cmd=['/usr/bin/sandbox-exec','-f',str(HERE/('isolation-storage-02.sb' if mode=='isolated' else 'offline.sb')),sys.executable,'-I','-B',str(bundle/'runtime.py'),'--text',request['text'],'--method',request['method'],'--speed',str(request['speed']),'--pitch',str(request['pitch']),'--output',str(target)]
      result=subprocess.run(cmd,text=True,capture_output=True);assert result.returncode==0,result.stderr
    meta=json.loads(result.stdout);assert digest(target)==meta['sha256']==outputs[mode][request['id']]['sha256'] and meta['E0_pass'] and not meta['forbidden_imports'];b.save(target.with_suffix('.json'),meta,j);cli.append(dict(id=request['id'],mode=mode,sha256=meta['sha256'],bit_match=True))
 blocked=[COVERAGE/'teacher/kokoro/coverage-train-00.wav',COVERAGE/'native/coverage-train-00.parameters.npz',COVERAGE/'alignment-manifest.json',HERE/'models/neural.pt',HERE/'models/direct.json',HERE/'render/diagnostic/mlpg-fresh-00/neutral/native.wav',HERE/'protocol.json',HERE/'runtime-archives/normal.zip',TIME/'render/diagnostic/timing-fresh-00/neutral/student.wav']
 blocked.append(Path(next(v['physical'] for n,v in b.locations().items() if n.endswith('.wav'))));blocked[-1]=b.guard.root/blocked[-1]
 assert all(q.exists() for q in blocked)
 probe="import socket,json;paths="+repr([str(x) for x in blocked])+";a=[]\nfor p in paths:\n try:open(p,'rb');a.append(False)\n except PermissionError:a.append(True)\ns=socket.socket()\ntry:s.bind(('127.0.0.1',0));net=False\nexcept PermissionError:net=True\nprint(json.dumps({'read_denied':a,'network_denied':net}))"
 with b.job(NAME,'audit','禁止資料/既存archiveと通信の実拒否を確認',reserve_bytes=10000) as j:
  result=subprocess.run(['/usr/bin/sandbox-exec','-f',str(HERE/'isolation-storage-02.sb'),sys.executable,'-I','-B','-c',probe],capture_output=True,text=True);assert result.returncode==0,result.stderr;proof=json.loads(result.stdout);assert all(proof['read_denied']) and proof['network_denied'];b.save(HERE/'denial-probe.json',dict(proof,paths=[str(q.relative_to(REPO)) if REPO in q.parents else str(q) for q in blocked]),j)
 b.save(HERE/'runtime-audit.json',dict(passed=True,pairs=pairs,single_CLI_checks=cli,actual_isolation_controller_sha256=digest(Path(__file__)),actual_isolation_controller_relative_path=str(Path(__file__).relative_to(REPO)),profile_sha256=digest(HERE/'isolation-storage-02.sb'),new_render_calls=324,new_E0_calls=324,bundle_bytes=size,denial_probe=proof,batch_archives_retained=True,management_seconds=timings,render_count_not_reduced_by_batching=True,final_non_neural=True,quality_certified=False));print(b.reconcile(),flush=True)
if __name__=='__main__':main()
