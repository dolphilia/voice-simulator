#!/usr/bin/env python3
"""追加campaignのASR呼び出しを失敗・中断も含めて予約する。"""
import fcntl
import sys
import time
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'src'))
from autonomous_speech_synthesis.io import read,write_once,append,rows,file_hash,now
from cycle_campaign_v1 import CYCLE_ID,LIMITS,inventory
from diagnostics import asr


def main():
    name=sys.argv[1]
    if Path(name).name!=name:raise ValueError('campaign IDのみ指定してください')
    path=ROOT/'results'/name
    identity=read(path/'identity.json')
    if identity['config'].get('cycle_id')!=CYCLE_ID:raise ValueError('追加サイクル外です')
    with (path/'.ai.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (path/'asr-evaluation.json').exists():
            print('保存済みASR結果を使用します');return
        approval=read(ROOT/'results/cycles'/CYCLE_ID/'approval.json')
        if time.time()-approval['unix']>LIMITS['max_cycle_seconds']:raise RuntimeError('サイクル時間上限です')
        if time.time()-read(path/'started.json')['unix']>LIMITS['max_campaign_seconds']:raise RuntimeError('campaign時間上限です')
        current=inventory(ROOT);baseline=approval['baseline_inventory']
        if sum(max(0,n-baseline.get(p,0)) for p,n in current.items())+10_000_000>=LIMITS['max_additional_bytes']:raise RuntimeError('追加保存量上限です')
        generated=sum(r['kind']=='sentence' and bool(r.get('wav')) for r in read(path/'p34-speech.json')['rows'])
        natural=min(3,len({r['speaker'] for r in read(path/'splits.json')['groups']['development']['records']}))
        count=generated+natural;ledger=path/'ai-ledger.jsonl'
        used=sum(r['count'] for r in rows(ledger) if r['event']=='reserved')
        if count+used>identity['config']['budget']['max_ai_evaluations']:raise RuntimeError('AI評価上限です')
        append(ledger,{'event':'reserved','count':count,'utc':now(),'script_sha256':file_hash(Path(__file__)),'engine_sha256':file_hash(ROOT/'diagnostics.py')})
        result=asr(path)
        append(ledger,{'event':'finished','count':count,'utc':now(),'result_sha256':file_hash(path/'asr-evaluation.json')})
        print(result)

if __name__=='__main__':main()
