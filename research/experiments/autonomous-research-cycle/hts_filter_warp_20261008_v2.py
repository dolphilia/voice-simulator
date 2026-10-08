"""初回fixtureを保持し、独立libm fma対照の完全一致で再開する。"""
import json,subprocess,argparse
from hts_filter_warp_20261008 import *
from hts_filter_warp_20261008 import run as original_run

def run(stage,engine=None):
    if stage!='fixture':return original_run(stage,engine)
    b=Budget();b.recover();assert not b.snapshot()['jobs']
    amendment=read(HERE/'fixture-amendment-v2.json')
    for path,h in amendment['hashes'].items():assert digest(REPO/path)==h,path
    for path,h in read(HERE/'execution-contract.json')['source_hashes'].items():assert digest(HERE/path)==h,path
    with job(b,'render','フィルタ周波数軸の原波形対照fixture',40,20000000,180) as r:
        with job(b,'dsp','全励振一致・MLSA係数/伝達関数恒等式fixture',600,1000000,180) as d:
            with b.workspace(r,'fixtureの科学ライブラリ初期化') as (_,env):
                result=subprocess.run([str(PYTHON),'-B',str(HERE/'fixture_v2.py')],env=env,check=True,timeout=120,stdout=subprocess.PIPE,text=True)
            value=json.loads(result.stdout);value['fixture_source_sha256']=digest(HERE/'fixture_v2.py');value['original_failed_attempt_preserved']=True
            b.save(HERE/'fixture-audit.json',value,d)
    print(b.reconcile(),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['fixture','comparison','isolate','asr']);p.add_argument('--engine');a=p.parse_args();run(a.stage,a.engine)
