"""空の実体一覧による無条件読取許可を別版で修正し、隔離だけ再検証する。"""
import ast,hashlib,json,subprocess,sys,importlib.util,base64,io,zipfile
from pathlib import Path
from budget import ROOT,read,digest,encode
from long_horizon_budget import LongHorizonBudget as Budget
REPO=ROOT.parents[2]
HERE=ROOT/'campaigns/nas-hts-lf-comparison-20261008-v1'
NAME='hts-lf-comparison-v1'
AMENDMENT=HERE/'isolation-amendment-v2.json'

def register():
    b=Budget();b.recover();assert not b.snapshot()['jobs'];s=b.snapshot();assert s['campaigns'][NAME]['counts']['render']==294
    d=read(HERE/'denial-probe-diagnostic-v2.json');assert [v['denied'] for v in d['rows']]==[True,True,False,False,False,True,True] and d['network_denied']
    controller=(HERE/'controller.py').read_text()
    old="        text += '(allow file-read-data ' + ''.join('(literal '+json.dumps(str(p))+') ' for p in physical) + ')\\n'\n        text += '(allow file-read-metadata ' + ''.join('(literal '+json.dumps(str(p))+') ' for p in physical) + ')\\n'"
    assert controller.count(old)==1
    new="        if physical:\n"+'\n'.join('    '+v for v in old.splitlines())
    controller=controller.replace(old,new)
    controller=controller.replace('    return contract\n', "    amendment=read(HERE/'isolation-amendment-v2.json')\n    assert digest(Path(__file__))==amendment['controller_v2_sha256']\n    assert digest(HERE/'controller.py')==amendment['original_controller_sha256']\n    return contract\n",1)
    ast.parse(controller)
    close=(ROOT/'hts_lf_closeout_20261008.py').read_text()
    needle="registration=read(HERE/'registration.json');assert digest(Path(__file__))==registration['closeout_source_sha256']"
    assert close.count(needle)==1
    close=close.replace(needle,"registration=read(HERE/'registration.json');assert digest(ROOT/'hts_lf_closeout_20261008.py')==registration['closeout_source_sha256']\n    amendment=read(HERE/'isolation-amendment-v2.json');assert digest(Path(__file__))==amendment['closeout_v2_sha256'] and digest(HERE/'controller-isolation-v2.py')==amendment['controller_v2_sha256']")
    close=close.replace("HERE/'controller.py'","HERE/'controller-isolation-v2.py'").replace("runtime['new_render_calls']==198","runtime['new_render_calls']==297")
    close=close.replace('inherited_mechanism_fixture_passed=True,','isolation_repair_amendment_sha256=digest(HERE/\'isolation-amendment-v2.json\'),original_denial_failure_retained=True,inherited_mechanism_fixture_passed=True,')
    close=close.replace("'全件研究保護: '+str(research_gates)","'元隔離は内部登録資料の読取拒否に不通過。空の実体一覧を無条件許可にしないv2を出力前固定し、隔離64+CLI2を追加99生成/66DSPで再検証した。元波形/失敗/消費を保持し、元normal64+CLI2はhash照合で再利用。','全件研究保護: '+str(research_gates)")
    ast.parse(close);cp=ROOT/'hts_lf_closeout_20261008_v2.py';b.write(cp,close.encode())
    amendment=dict(reason='外部bundle実体一覧が空でも条件なしallow file-read-data/file-read-metadataが出ていた。空なら両許可を省く。',
        original_controller_sha256=digest(HERE/'controller.py'),original_registration_sha256=digest(HERE/'registration.json'),original_closeout_sha256=digest(ROOT/'hts_lf_closeout_20261008.py'),
        original_execution_contract_sha256=digest(HERE/'execution-contract.json'),original_diagnostic_sha256=digest(HERE/'denial-probe-diagnostic-v2.json'),
        controller_v2_sha256=hashlib.sha256(controller.encode()).hexdigest(),closeout_v2_sha256=digest(cp),repair_source_sha256=digest(Path(__file__)),
        factor_parameters_measurement_gates_normalization_and_inputs_unchanged=True,no_original_source_overwritten=True,original_failure_and_all_consumption_retained=True,
        repair_estimates=dict(render=99,dsp=66,ai=0,teacher=0,train=0,inverse=0,download=0),total_without_other_retries=dict(render=393,dsp=486,ai=128),
        normal_64_and_two_CLI_reused_only_after_exact_hash=True,isolated_64_and_two_CLI_require_new_wave_hash_match=True,existing_campaign_limits_unchanged=True,quality_certified=False)
    with b.job(NAME,'setup','空のbundle実体一覧を拒否する隔離v2と終了監査を別登録',reserve_bytes=2000000) as j:
        b.write(HERE/'controller-isolation-v2.py',controller.encode(),j);b.save(AMENDMENT,amendment,j)
    print('空一覧の許可を省くv2を、因子/閾値を変えず固定',flush=True)

def run():
    b=Budget();b.recover();assert not b.snapshot()['jobs'];a=read(AMENDMENT);assert digest(Path(__file__))==a['repair_source_sha256']
    sys.path.insert(0,str(HERE));spec=importlib.util.spec_from_file_location('_lf_isolation_v2',HERE/'controller-isolation-v2.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);m.verify()
    reqs=m.requests();normal=read(HERE/'runtime-batch-normal.json')['records'];expected={v['id']:read(REPO/v['record'])['wav_sha256'] for v in read(HERE/'render-manifest.json')['rows']}
    assert len(normal)==len(expected)==64 and all(normal[k]['sha256']==v for k,v in expected.items())
    with m.managed_job(b,NAME,'render','修正版隔離batch64 v2',count=96,reserve_bytes=200000000) as j:
        with m.managed_job(b,NAME,'dsp','修正版隔離batch64 E0 v2',count=64,reserve_bytes=100000):
            with b.workspace(j,'空一覧を省く隔離v2の実生成') as (work,env):
                profile=m.profile(b,work,True);output=m.execute([str(m.PYTHON),'-I','-B',str(HERE/'runtime-bundle/runtime_batch.py')],env,profile,json.dumps(reqs,ensure_ascii=False))
            archive_data=base64.b64decode(output,validate=False);b.write(HERE/'runtime-archives/isolated-v2.zip',archive_data,j)
            with zipfile.ZipFile(io.BytesIO(archive_data)) as z:
                v=json.loads(z.read('manifest.json'));assert len(v['records'])==64 and len(z.namelist())==129
                assert v['synthesis_calls']==v['E0_calls']==64 and sum(r['conversion']['render_calls_including_internal_MLSA'] for r in v['records'])==96
                records={}
                for r in v['records']:
                    assert hashlib.sha256(z.read(r['id']+'.wav')).hexdigest()==r['sha256']==expected[r['id']]==normal[r['id']]['sha256']
                    assert r['synthesis_calls']==r['E0_calls']==1 and not r['forbidden_imports'];records[r['id']]=r
            b.write_data(HERE/'runtime-batch-isolated-v2.json',encode(dict(records=records,all_hash_match=True,profile=dict(source=profile,sha256=hashlib.sha256(profile.encode()).hexdigest()),amendment_sha256=digest(AMENDMENT))),j)
    print('隔離v2全64件のhash一致',flush=True)
    cli=[]
    for request in [reqs[0],reqs[-1]]:
        old=HERE/'runtime-cli/normal'/(request['id']+'.wav');assert digest(old)==expected[request['id']]
        cli.append(dict(id=request['id'],mode='normal',sha256=digest(old),bit_match=True,reused_after_exact_hash=True))
        with m.managed_job(b,NAME,'render','修正版隔離CLI v2 '+request['id'],count=1 if request['method']=='native' else 2,reserve_bytes=10000000) as j:
            with m.managed_job(b,NAME,'dsp','修正版隔離CLI E0 v2 '+request['id'],reserve_bytes=100000):
                with b.workspace(j,'隔離CLI v2') as (work,env):
                    value=json.loads(m.execute([str(m.PYTHON),'-I','-B',str(HERE/'runtime-bundle/runtime.py'),'--text',request['text'],'--method',request['method'],'--speed',str(request['speed']),'--pitch',str(request['pitch'])],env,m.profile(b,work,True)))
                data=base64.b64decode(value['wav_base64']);assert hashlib.sha256(data).hexdigest()==value['meta']['sha256']==expected[request['id']]
                b.write(HERE/'runtime-cli/isolated-v2'/(request['id']+'.wav'),data,j);cli.append(dict(id=request['id'],mode='isolated-v2',sha256=value['meta']['sha256'],bit_match=True))
    logical=HERE/'render/lf-fresh-00/neutral/native.wav'
    blocked=[logical,logical.resolve(),HERE/'protocol.json',HERE/'registration.json',m.PREVIOUS/'protocol.json',HERE/'runtime-archives/normal.zip',(HERE/'runtime-archives/normal.zip').resolve(),AMENDMENT,HERE/'controller-isolation-v2.py']
    code='import json,socket;paths='+repr([str(p) for p in blocked])+';a=[]\nfor p in paths:\n try:\n  f=open(p,"rb");f.read(1);f.close();a.append(False)\n except PermissionError:a.append(True)\ns=socket.socket()\ntry:s.bind(("127.0.0.1",0));net=False\nexcept PermissionError:net=True\nprint(json.dumps(dict(read_denied=a,network_denied=net)))'
    with b.job(NAME,'audit','修正版隔離v2の九資料と通信の実拒否',reserve_bytes=20000000) as j:
        with b.workspace(j,'隔離v2の追加生成なし拒否probe',8000000,16000000) as (work,env):proof=json.loads(m.execute([str(m.PYTHON),'-I','-B','-c',code],env,m.profile(b,work,True)))
        b.save(HERE/'denial-probe-v2.json',dict(proof,paths=[str(p) for p in blocked],amendment_sha256=digest(AMENDMENT)),j)
        assert all(proof['read_denied']) and proof['network_denied']
        pairs=[dict(id=r['id'],bit_match=normal[r['id']]['sha256']==records[r['id']]['sha256']) for r in reqs];assert len(pairs)==64 and all(v['bit_match'] for v in pairs)
        b.save(HERE/'runtime-audit.json',dict(passed=True,pairs=pairs,CLI=cli,new_render_calls=297,new_DSP_calls=198,internal_MLSA_helpers=99,
            original_isolate_render=198,repair_render=99,repair_DSP=66,original_denial_failure_retained=True,amendment_sha256=digest(AMENDMENT),denial_probe=proof,final_non_neural=True,quality_certified=False),j)
    print('隔離v2、normal全64組・CLI4・九資料/通信拒否を確認。旧失敗を保持。',flush=True)

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['register','isolate']);v=p.parse_args();register() if v.stage=='register' else run()
