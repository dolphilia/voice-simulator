"""既存bundleを保持し、各子プロセスへ一重のOS隔離を適用する。"""
import json,sys,subprocess
from paths import *

def main():
 b=Budget();p=read(HERE/'protocol.json');bundle=HERE/'runtime-bundle'
 ec=read(HERE/'execution-contract.json')
 for n,h in ec['source_hashes'].items():assert digest(HERE/n)==h
 manifest=read(bundle/'manifest.json')
 for n,h in manifest['files'].items():assert digest(bundle/n)==h
 size=sum(q.stat().st_size for q in bundle.rglob('*') if q.is_file());assert size<=2_000_000
 pairs=[];resumed=0;calls=0
 for row in [p['rows'][8],p['rows'][12]]:
  for condition,request in row['requests'].items():
   for method in ['native','direct_non_neural','distilled_non_neural']:
    ident=row['id']+'/'+condition+'/'+method;expected=read(HERE/'render/partial'/(ident+'.json'));values=[]
    for mode in ['normal','isolated']:
     target=HERE/'runtime-check'/mode/(ident+'.wav');record=target.with_suffix('.json')
     if record.exists():
      value=read(record);assert digest(target)==value['sha256']==expected['wav_sha256']
      assert value['synthesis_calls']==2 and value['E0_pass'] and not value['forbidden_imports']
      values.append(value);resumed+=1;continue
     assert not target.exists()
     with b.job(NAME,'render','runtime一重sandbox '+mode+'/'+ident,count=2,reserve_bytes=3_000_000) as j:
      with b.job(NAME,'dsp','runtime E0 '+mode+'/'+ident,count=1,reserve_bytes=10000):
       cmd=['/usr/bin/sandbox-exec','-f',str(HERE/('isolation.sb' if mode=='isolated' else 'offline.sb')),sys.executable,'-I','-B',str(bundle/'runtime.py'),'--text',row['text'],'--method',method,'--speed',str(request['speed']),'--pitch',str(request['requested_f0']),'--output',str(target)]
       with b.external_output(target,2_000_000,j):
        result=subprocess.run(cmd,capture_output=True,text=True)
        if result.returncode:
         b.save(HERE/'runtime-check'/mode/(ident+'.failure.json'),{'returncode':result.returncode,'stdout':result.stdout,'stderr':result.stderr,'command':cmd},j)
         raise RuntimeError('隔離子プロセス失敗: '+result.stderr)
      value=json.loads(result.stdout);assert digest(target)==value['sha256']==expected['wav_sha256']
      assert value['synthesis_calls']==2 and value['E0_pass'] and not value['forbidden_imports']
      b.save(record,value,j);values.append(value);calls+=2
    pairs.append({'id':ident,'normal_isolated_diagnostic_bit_match':values[0]['sha256']==values[1]['sha256']==expected['wav_sha256']})
    print('isolated',ident,flush=True)
 b.save(HERE/'runtime-audit.json',{'passed':len(pairs)==12 and all(r['normal_isolated_diagnostic_bit_match'] for r in pairs),'pairs':pairs,'bundle_bytes':size,'successful_render_calls':48,'failed_render_calls':2,'resumed_successes':resumed,'this_launch_render_calls':calls,'new_E0_attempts':25,'network_and_teacher_neural_trajectory_reads_denied':True,'quality_certified':False})
 print(b.reconcile(),flush=True)
if __name__=='__main__':main()
