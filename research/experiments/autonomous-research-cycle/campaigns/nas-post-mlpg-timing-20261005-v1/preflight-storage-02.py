"""外部出力の既知fixtureを検証し、成功済み通常出力は再使用する。"""
from paths import *
from storage_budget import StorageBudget
import sys, subprocess, zipfile, json, hashlib
def main():
    b=StorageBudget();bundle=HERE/'runtime-storage-bundle'
    previous=read(TIME/'protocol.json')
    row=next(r for r in previous['rows'] if r['id']=='timing-fresh-00')
    requests=read(HERE/'runtime-preflight-storage-requests.json')
    expected={ 'fixture/'+c+'/native':read(TIME/'render/diagnostic'/row['id']/c/'native.json')['wav_sha256']
              for c in row['requests'] }
    assert len(requests)==2 and set(r['id'] for r in requests)==set(expected)
    results={}
    for mode in ['normal','isolated']:
        path=HERE/'runtime-archives'/('preflight-storage-normal.zip' if mode=='normal' else 'preflight-storage02-isolated.zip')
        if mode=='isolated':
            with b.job(NAME,'render','外部保存の既知2 隔離ディレクトリ権限修正',count=2,reserve_bytes=10000000) as j:
                with b.job(NAME,'dsp','既知2 E0 隔離',count=2,reserve_bytes=10000):
                    with b.external_output(path,5000000,j):
                        result=subprocess.run(['/usr/bin/sandbox-exec','-f',str(HERE/'isolation-storage-02.sb'),
                            sys.executable,'-I','-B',str(bundle/'runtime-batch.py'),
                            '--requests',str(HERE/'runtime-preflight-storage-requests.json'),
                            '--output',str(path)],text=True,capture_output=True)
                        assert result.returncode==0,result.stderr
        with zipfile.ZipFile(path) as z:
            assert len(z.namelist())==5
            meta=json.loads(z.read('manifest.json'))
            assert meta['synthesis_calls']==meta['E0_calls']==2
            for r in meta['records']:
                assert hashlib.sha256(z.read(r['id']+'.wav')).hexdigest()==r['sha256']==expected[r['id']]
                assert r['E0_pass'] and not r['forbidden_imports']
        results[mode]=dict(archive_sha256=digest(path),records=meta['records'],
                           known_fixture_bit_match=True,reused_successful_normal=(mode=='normal'))
    physical=next(b.guard.root/r['physical'] for n,r in b.locations().items() if n.endswith('.wav'))
    probe="import json,socket;paths="+repr([str(physical),str(HERE/'models/neural.pt')])+";a=[]\nfor p in paths:\n try:open(p,'rb');a.append(False)\n except PermissionError:a.append(True)\ns=socket.socket()\ntry:s.bind(('127.0.0.1',0));net=False\nexcept PermissionError:net=True\nprint(json.dumps({'read_denied':a,'network_denied':net}))"
    with b.job(NAME,'audit','外部実体データ/NN重み/通信の実拒否',reserve_bytes=30000) as j:
        result=subprocess.run(['/usr/bin/sandbox-exec','-f',str(HERE/'isolation-storage-02.sb'),
            sys.executable,'-I','-B','-c',probe],capture_output=True,text=True)
        assert result.returncode==0,result.stderr
        proof=json.loads(result.stdout)
        assert all(proof['read_denied']) and proof['network_denied']
        b.save(HERE/'runtime-preflight-storage-02.json',
               dict(passed=True,results=results,new_renders_this_attempt=2,reused_normal_renders=2,
                    previous_failed_isolated_render_reservations=2,
                    output_only_data_read_denied=True,denial_probe=proof,
                    external_physical_wave=str(physical),profile_sha256=digest(HERE/'isolation-storage-02.sb'),
                    fixture_not_quality_evidence=True,quality_certified=False),j)
    print(dict(passed=True,external_hashes=b.audit_data_hashes(),reconcile=b.reconcile()),flush=True)
if __name__=='__main__':main()
