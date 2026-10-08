"""元契約を保持し、予約入口の別名だけを接続したcontrollerで未実施段階を実行する。"""
import ast
import os
import subprocess
from pathlib import Path
import hts_allpass_comparison_20261008 as original
from budget import read,digest

ROOT=original.ROOT;HERE=original.HERE;NAME=original.NAME;REPO=original.REPO

def verify_amendment():
    a=read(HERE/'execution-amendment-v2.json');assert digest(Path(__file__))==a['driver_sha256']
    assert digest(HERE/'execution-contract.json')==a['original_execution_contract_sha256']
    assert digest(ROOT/'hts_allpass_closeout_20261008_v2.py')==a['closeout_wrapper_sha256']
    assert digest(HERE/'controller_v2.py')==a['patched_controller_sha256']
    for n,h in a['original_source_hashes'].items():assert digest(HERE/n)==h,n
    return a

def amend():
    b=original.Budget();b.recover();assert not b.snapshot()['jobs'] and not (HERE/'render-manifest.json').exists()
    old=HERE/'controller.py';text=old.read_text();assert text.count('from paths import *')==1
    text=text.replace('from paths import *','from paths import *\nfrom paths import job as managed_job',1)
    text=text.replace("str(HERE / 'controller.py')","str(HERE / 'controller_v2.py')")
    needle="def verify():\n    contract=read(HERE/'execution-contract.json')"
    added="def verify():\n    amendment=read(HERE/'execution-amendment-v2.json')\n    assert digest(Path(__file__))==amendment['patched_controller_sha256']\n    assert digest(HERE/'execution-contract.json')==amendment['original_execution_contract_sha256']\n    contract=read(HERE/'execution-contract.json')"
    assert text.count(needle)==1;text=text.replace(needle,added);ast.parse(text)
    with original.job(b,'setup','予約入口別名の別版接続と生成前停止の保持',size=2000000) as j:
        b.write(HERE/'controller_v2.py',text.encode(),j)
        b.save(HERE/'execution-amendment-v2.json',dict(reason='機構fixture継承後、比較controllerのmanaged_job呼出しがpaths.jobの別名定義なしでNameErrorになった。予約・科学生成前に停止。',
            original_controller_sha256=digest(old),original_execution_contract_sha256=digest(HERE/'execution-contract.json'),original_source_hashes=read(HERE/'execution-contract.json')['source_hashes'],
            patched_controller_sha256=digest(HERE/'controller_v2.py'),driver_sha256=digest(Path(__file__)),closeout_wrapper_sha256=digest(ROOT/'hts_allpass_closeout_20261008_v2.py'),
            failed_child=dict(returncode=1,error="NameError: name 'managed_job' is not defined",stage='comparison',before_render_reservation=True,render_records_saved=0),
            old_source_and_contract_unchanged=True,C_binary_and_variants_inputs_gates_costs_unchanged=True,no_waveform_reexecuted=True),j)
    verify_amendment()
    import importlib.util,sys
    sys.path.insert(0,str(HERE));spec=importlib.util.spec_from_file_location('_allpass_alias_verified',HERE/'controller_v2.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);m.verify();assert callable(m.managed_job)
    b.save(ROOT/'allpass-comparison-alias-verification-v2.json',dict(passed=True,controller_amendment_sha256=digest(HERE/'execution-amendment-v2.json'),reservation_alias_bound=True,worker_child_uses_v2_source=True,new_scientific_outputs=0,budget=b.reconcile()))
    print('予約入口の別名と子ソースを確認。元契約と0生成停止を保存。',flush=True)

def run(stage,engine=None):
    b=original.Budget();b.recover();assert not b.snapshot()['jobs'];verify_amendment();assert read(HERE/'fixture-audit.json')['passed']
    env=os.environ.copy();env['PYTHONDONTWRITEBYTECODE']='1';env['PYTHONPATH']=str(original.BASE/'runtime-bundle/packages-v2')
    args=[str(original.PYTHON),'-B',str(HERE/'controller_v2.py'),stage]
    if engine:args+=['--engine',engine]
    try:
        result=subprocess.run(args,env=env,check=True,capture_output=True,text=True,timeout=4000)
    except subprocess.CalledProcessError as exc:
        with original.job(b,'audit','別版controller子の失敗出力保持 '+stage+(engine or ''),size=2000000) as j:b.save(HERE/('child-failure-v2-'+stage+(engine or '')+'.json'),dict(returncode=exc.returncode,stdout=exc.stdout,stderr=exc.stderr),j)
        raise
    print(result.stdout,flush=True)
    if result.stderr:print(result.stderr,flush=True)
    print(b.reconcile(),flush=True)

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['amend','comparison','isolate','asr']);p.add_argument('--engine');a=p.parse_args()
    amend() if a.stage=='amend' else run(a.stage,a.engine)
