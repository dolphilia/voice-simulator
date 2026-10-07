#!/usr/bin/env python3
"""追加枠の台帳・ソース・結果・E0を完了後に監査し、成果物を封印する。"""
import argparse
from collections import Counter
import fcntl
import json
import sys
from pathlib import Path
import numpy as np
from scipy.io import wavfile
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'src'))
from autonomous_speech_synthesis.io import read,rows,write_once,file_hash,digest,code_manifest
from cycle_campaign_v1 import CYCLE_ID,LIMITS,inventory


def audit(name):
    if Path(name).name!=name:raise ValueError('campaign IDのみ指定してください')
    path=ROOT/'results'/name
    with (path/'.run.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if not (path/'decision.json').exists():raise RuntimeError('未完了campaignは封印しません')
        identity=read(path/'identity.json');expected=digest(identity);errors=[]
        if identity['config'].get('cycle_id')!=CYCLE_ID:errors.append('cycle ID不一致')
        if identity['config'].get('approved_cycle_limits')!=LIMITS:errors.append('承認上限不一致')
        if identity['code']!=code_manifest():errors.append('凍結コアの変更')
        for file,sha in identity['config'].get('branch_sources',{}).items():
            if file_hash(ROOT/file)!=sha:errors.append('分岐ソースの変更: '+file)
        events=rows(path/'ledger.jsonl');started={};finished={};counts=Counter();wave_count=0;e0_failed=[]
        for event in events:
            key=(event['trial_id'],event['attempt'])
            if event['event']=='started':
                if key in started:errors.append('開始の重複: '+str(key))
                started[key]=event;counts[(event['budget_key'],event['backend'] if event['budget_key']=='max_p2_per_backend' else 'all')]+=1
            elif event['event']=='finished':
                if key in finished:errors.append('完了の重複: '+str(key))
                if key not in started:errors.append('開始のない完了: '+str(key))
                trial=read(path/event['result']);finished[key]=trial
                request={k:trial[k] for k in ('candidate_id','backend','stage','task','seed','parameters','identity')}
                if trial['identity']!=expected or digest(request)[:24]!=trial['trial_id']:errors.append('試行の版・ID不一致: '+str(key))
                if not trial['evaluation']['E0_pass']:e0_failed.append(trial['trial_id'])
                if trial['status']=='signal-qualified' and not trial['evaluation']['E0_pass']:errors.append('E0誤昇格: '+str(key))
                if trial.get('wav'):
                    wav=path/trial['wav'];fs,audio=wavfile.read(wav);wave_count+=1
                    if fs!=trial['sample_rate'] or len(audio)!=trial['samples'] or not np.all(np.isfinite(audio)):errors.append('保存WAVの契約違反: '+str(key))
                    # 保存はfloat32、生成時hashはfloat64。この監査では両hashの同一性を主張しない。
                    if not wav.with_suffix('.controls.json').exists():errors.append('制御記録の欠落: '+str(key))
        if set(started)!=set(finished):errors.append('未完了試行または対応のない完了')
        for (budget,backend),count in counts.items():
            if count>identity['config']['budget'][budget]:errors.append('レンダー上限超過: '+budget+'/'+backend)
        p34={r['task']['id'] for r in finished.values() if r['stage'] in ('P3','P4')}
        if len(p34)>identity['config']['max_p34_tasks']:errors.append('P3/P4課題数超過')
        ai=rows(path/'ai-ledger.jsonl');reserved=sum(r['count'] for r in ai if r['event']=='reserved')
        if reserved>identity['config']['budget']['max_ai_evaluations']:errors.append('AI評価上限超過')
        # 同じ実験を再開しても最終参照の特徴を扱うファイルは作らない。
        forbidden=list(path.glob('*reference*confirmation*'))+list(path.glob('*confirmation-consumed*'))
        if forbidden:errors.append('最終参照消費を示すファイルが存在')
        split_path=path/'splits.json'
        if not split_path.exists():split_path=ROOT/'results/ans-pilot-v1/splits.json'
        split=read(split_path)['groups'];names=list(split)
        for i,a in enumerate(names):
            for b in names[i+1:]:
                for field in ('speakers','sentence_ids'):
                    if set(split[a][field])&set(split[b][field]):errors.append('参照分割の重複: '+field)
        approval=read(ROOT/'results/cycles'/CYCLE_ID/'approval.json')
        current=inventory(ROOT);additional=sum(max(0,n-approval['baseline_inventory'].get(p,0)) for p,n in current.items())
        if additional>LIMITS['max_additional_bytes']:errors.append('追加保存量の上限超過')
        members=list((ROOT/'results/cycles'/CYCLE_ID/'members').glob('*.json'))
        if len(members)>LIMITS['max_campaigns']:errors.append('追加campaign数超過')
        result={'passed':not errors,'errors':errors,'campaign':name,'started':len(started),'finished':len(finished),
            'counts':{key+'/'+backend:n for (key,backend),n in counts.items()},'saved_waves':wave_count,'E0_failed':e0_failed,
            'AI_reserved':reserved,'p34_task_count':len(p34),'additional_bytes_at_audit':additional,
            'confirmation_evidence':'専用消費ファイルなし。分岐コードの自然参照読込はdevelopment/selectionに限定。ファイル不在だけで全OSアクセスを証明するものではない。',
            'scope':'完了試行の構造・版・分割・予算・保存形式の監査。知覚資格とは別。','script_sha256':file_hash(Path(__file__))}
        write_once(path/'extension-audit.json',result)
        files={str(p.relative_to(path)):file_hash(p) for p in sorted(path.rglob('*')) if p.is_file() and not p.name.startswith('.') and p.name!='extension-artifact-seal.json'}
        write_once(path/'extension-artifact-seal.json',{'files':files,'count':len(files)})
        print(json.dumps(result,ensure_ascii=False,indent=2))
        if errors:raise SystemExit(1)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--campaign',required=True);audit(parser.parse_args().campaign)
