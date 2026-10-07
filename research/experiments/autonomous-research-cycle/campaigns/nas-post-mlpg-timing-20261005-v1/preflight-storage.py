"""既知の二指定で、まとめ生成・-I読込・出力read拒否を初比較前に実検査する。"""
from paths import *
from storage_budget import StorageBudget
Budget=StorageBudget
import sys,subprocess,zipfile,json,hashlib
def main():
 b=Budget();bundle=HERE/'runtime-storage-bundle';previous=read(TIME/'protocol.json');row=next(r for r in previous['rows'] if r['id']=='timing-fresh-00');requests=[];expected={}
 with b.job(NAME,'setup','既知fixtureのbatch起動入力を固定',reserve_bytes=10000) as j:
  for condition,q in row['requests'].items():
   ident='fixture/'+condition+'/native';requests.append(dict(id=ident,text=row['text'],method='native',speed=q['speed'],pitch=q['requested_f0']));expected[ident]=read(TIME/'render/diagnostic'/row['id']/condition/'native.json')['wav_sha256']
  b.save(HERE/'runtime-preflight-storage-requests.json',requests,j)
 results={}
 for mode in ['normal','isolated']:
  path=HERE/'runtime-archives'/('preflight-storage-'+mode+'.zip')
  with b.job(NAME,'render','batch既知2 '+mode,count=2,reserve_bytes=10000000) as j:
   with b.job(NAME,'dsp','batch既知2 E0 '+mode,count=2,reserve_bytes=10000):
    with b.external_output(path,5000000,j):
     result=subprocess.run(['/usr/bin/sandbox-exec','-f',str(HERE/('isolation-storage.sb' if mode=='isolated' else 'offline.sb')),sys.executable,'-I','-B',str(bundle/'runtime-batch.py'),'--requests',str(HERE/'runtime-preflight-storage-requests.json'),'--output',str(path)],text=True,capture_output=True);assert result.returncode==0,result.stderr
   with zipfile.ZipFile(path) as z:
    assert len(z.namelist())==5;meta=json.loads(z.read('manifest.json'));assert meta['synthesis_calls']==meta['E0_calls']==2
    for r in meta['records']:
     assert hashlib.sha256(z.read(r['id']+'.wav')).hexdigest()==r['sha256']==expected[r['id']] and r['E0_pass'] and not r['forbidden_imports']
   results[mode]=dict(archive_sha256=digest(path),records=meta['records'],known_fixture_bit_match=True)
 b.save(HERE/'runtime-preflight-storage.json',dict(passed=True,results=results,new_renders=4,new_E0=4,batch_and_isolated_startup_verified=True,archive_output_opened_write_only=True,output_read_data_denied_metadata_allowed=True,fixture_not_quality_evidence=True));print('batch既知fixture通常/隔離と単独基準のbit一致を確認',flush=True);print(b.reconcile(),flush=True)
if __name__=='__main__':main()
