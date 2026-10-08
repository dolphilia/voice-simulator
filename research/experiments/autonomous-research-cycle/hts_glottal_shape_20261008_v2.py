"""波形前の静的検査で見つけた予約helper名の衝突を別版で修正する。"""
import hts_glottal_shape_20261008 as original
from hts_glottal_shape_20261008 import HERE,ROOT,NAME,PYTHON,BASE,Budget,read,digest,job
import json
import os
from pathlib import Path
import subprocess

def prepare():
    b=Budget();b.recover();assert not (HERE/'fixture-audit.json').exists()
    text=(HERE/'controller.py').read_text()
    text=text.replace('from paths import *','from paths import *\nfrom paths import job as managed_job')
    text=text.replace('with job(b,','with managed_job(b,')
    text=original.replace_once(text,'    return contract\n',"    amendment=read(HERE/'execution-control-amendment.json')\n    for n,h in amendment['source_hashes'].items():assert digest(ROOT/n)==h,n\n    return contract\n")
    with job(b,'setup','生成前静的検査のhelper名衝突修正',size=2000000) as j:
        b.write(HERE/'controller_v2.py',text.encode(),j)
        b.save(HERE/'execution-control-amendment.json',dict(reason='旧controllerのas job局所変数と新job helperが同名。実行前の静的検査で検出。helper別名のみ変更。',
            old_controller_sha256=digest(HERE/'controller.py'),source_hashes={str(p.relative_to(ROOT)):digest(p) for p in (HERE/'controller_v2.py',Path(__file__))},
            waveform_outputs_before_amendment=0,scientific_factors_or_inputs_changed=False,limits_unchanged=True),j)
    print(b.reconcile(),flush=True)

def run(stage,engine=None):
    if stage=='fixture':return original.run(stage)
    b=Budget();b.recover();assert not b.snapshot()['jobs']
    assert read(HERE/'fixture-audit.json')['passed']
    env=os.environ.copy();env['PYTHONDONTWRITEBYTECODE']='1';env['PYTHONPATH']=str(BASE/'runtime-bundle/packages-v2')
    command=[str(PYTHON),'-B',str(HERE/'controller_v2.py'),stage]
    if engine:command+=['--engine',engine]
    subprocess.run(command,env=env,check=True,timeout=4000)
    print(b.reconcile(),flush=True)

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['prepare','fixture','comparison','isolate','asr']);p.add_argument('--engine')
    args=p.parse_args()
    prepare() if args.stage=='prepare' else run(args.stage,args.engine)
