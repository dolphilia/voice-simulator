"""隔離v2の保存済み全出力を再利用し、予約時間0だった拒否probeだけ再開する。"""
import json,hashlib,sys,importlib.util,subprocess
from pathlib import Path
from budget import ROOT,read,digest
from long_horizon_budget import LongHorizonBudget as Budget
REPO=ROOT.parents[2];HERE=ROOT/'campaigns/nas-hts-lf-comparison-20261008-v1';NAME='hts-lf-comparison-v1'

def main():
    b=Budget();b.recover();assert not b.snapshot()['jobs'];assert b.snapshot()['campaigns'][NAME]['counts']['render']==393
    sys.path.insert(0,str(HERE));spec=importlib.util.spec_from_file_location('_lf_finish_v2',HERE/'controller-isolation-v2.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);m.verify()
    with b.job(NAME,'setup','隔離v2の予約時間0だった終了probeだけ再開する別ソースを固定',reserve_bytes=2000000) as j:
        b.save(HERE/'technical-resume-v3.json',dict(source_sha256=digest(Path(__file__)),reason='b.jobのaudit expected_seconds既定0をm.executeが不正timeoutとして拒否。追加生成せずsubprocessに独立45秒を明示。',
            isolation_controller_v2_sha256=digest(HERE/'controller-isolation-v2.py'),amendment_v2_sha256=digest(HERE/'isolation-amendment-v2.json'),original_repair_source_sha256=digest(ROOT/'lf_isolation_repair_20261008.py'),
            factors_and_gates_and_profile_unchanged=True,render=0,DSP=0,failed_consumption_retained=True,quality_certified=False),j)
    reqs=m.requests();normal=read(HERE/'runtime-batch-normal.json')['records'];isolated=read(HERE/'runtime-batch-isolated-v2.json')['records']
    expected={v['id']:read(REPO/v['record'])['wav_sha256'] for v in read(HERE/'render-manifest.json')['rows']};assert len(normal)==len(isolated)==len(expected)==64
    assert all(normal[k]['sha256']==isolated[k]['sha256']==v for k,v in expected.items())
    cli=[]
    for request in [reqs[0],reqs[-1]]:
        for mode in ('normal','isolated-v2'):
            p=HERE/'runtime-cli'/mode/(request['id']+'.wav');assert digest(p)==expected[request['id']]
            cli.append(dict(id=request['id'],mode=mode,sha256=digest(p),bit_match=True,reused_after_exact_hash=True))
    logical=HERE/'render/lf-fresh-00/neutral/native.wav';blocked=[logical,logical.resolve(),HERE/'protocol.json',HERE/'registration.json',m.PREVIOUS/'protocol.json',HERE/'runtime-archives/normal.zip',(HERE/'runtime-archives/normal.zip').resolve(),HERE/'isolation-amendment-v2.json',HERE/'controller-isolation-v2.py']
    code='import json,socket;paths='+repr([str(p) for p in blocked])+';a=[]\nfor p in paths:\n try:\n  f=open(p,"rb");f.read(1);f.close();a.append(False)\n except PermissionError:a.append(True)\ns=socket.socket()\ntry:s.bind(("127.0.0.1",0));net=False\nexcept PermissionError:net=True\nprint(json.dumps(dict(read_denied=a,network_denied=net)))'
    with b.job(NAME,'audit','修正版隔離v2の九資料と通信の実拒否',reserve_bytes=20000000) as j:
        with b.workspace(j,'隔離v2の拒否probe再開、生成なし',8000000,16000000) as (work,env):
            p=m.profile(b,work,True);assert '(allow file-read-data )' not in p and '(allow file-read-metadata )' not in p
            out=subprocess.run(['/usr/bin/sandbox-exec','-p',p,str(m.PYTHON),'-I','-B','-c',code],env=env,check=True,capture_output=True,text=True,timeout=45)
        proof=json.loads(out.stdout);b.save(HERE/'denial-probe-v2.json',dict(proof,paths=[str(p) for p in blocked],amendment_sha256=digest(HERE/'isolation-amendment-v2.json'),technical_resume_sha256=digest(HERE/'technical-resume-v3.json')),j)
        assert all(proof['read_denied']) and proof['network_denied']
        pairs=[dict(id=r['id'],bit_match=normal[r['id']]['sha256']==isolated[r['id']]['sha256']) for r in reqs]
        b.save(HERE/'runtime-audit.json',dict(passed=True,pairs=pairs,CLI=cli,new_render_calls=297,new_DSP_calls=198,internal_MLSA_helpers=99,original_isolate_render=198,repair_render=99,repair_DSP=66,
            original_denial_failure_retained=True,original_repair_timeout_failure_retained=True,amendment_sha256=digest(HERE/'isolation-amendment-v2.json'),technical_resume_sha256=digest(HERE/'technical-resume-v3.json'),denial_probe=proof,final_non_neural=True,quality_certified=False),j)
    print('全64通常/隔離v2・CLI4・九資料/通信拒否を確認。追加生成なし。',flush=True)
if __name__=='__main__':main()
