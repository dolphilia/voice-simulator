#!/usr/bin/env python3
"""6campaignの実績と未達条件を集約し、品質達成と区別して研究サイクルを閉じる。"""
import json
from pathlib import Path
import sys
import time
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'src'))
from autonomous_speech_synthesis.io import read,rows,write_once,file_hash,now


def metric(data):
    valid=[r for r in data if 'kana_CER' in r]
    return {'attempts':len(data),'available':len(valid),'kana_CER':sum(r['kana_errors'] for r in valid)/sum(r['kana_characters'] for r in valid) if valid else None}


def main():
    directories=sorted(p.parent for p in (ROOT/'results').glob('*/started.json'))
    campaigns=[];errors=[]
    for path in directories:
        identity=read(path/'identity.json');events=rows(path/'ledger.jsonl')
        started=[e for e in events if e['event']=='started'];finished=[e for e in events if e['event']=='finished']
        if len(started)!=len(finished):errors.append(path.name+': 未完了試行')
        decision=read(path/'decision.json')
        for source,expected in identity['config'].get('branch_sources',{}).items():
            if file_hash(ROOT/source)!=expected:errors.append(path.name+': 分岐ソース版の不一致 '+source)
        campaigns.append({'id':path.name,'renders':len(started),'completed':len(finished),'state':decision['state'],'quality_goal_achieved':decision['quality_goal_achieved'],'confirmation_consumed':(path/'confirmation-consumed.json').exists()})
    path=ROOT/'results/ans-vtl-calibrated-v3';parent=ROOT/'results/ans-vtl-japanese-v2'
    suite={t['id']:t for t in read(path/'task-suite.json')['tasks']};asr=read(path/'asr-evaluation.json')['rows'];prior=read(parent/'asr-evaluation.json')['rows'];comparisons={}
    for variant,source,data in [('mora','parent',prior),('accent','parent',prior),('accent-tap','parent',prior),('mora-tap-calibrated','current',asr),('accent-tap-calibrated','current',asr)]:
        comparisons[variant]={split:metric([r for r in data if r.get('variant')==variant and (split=='all' or suite[r['id']]['frontend_split']==split)]) for split in ('all','development','novel')}
    assert len(directories)==6 and not errors
    summary={'utc':now(),'cycle_state':'ended-inconclusive','quality_goal_achieved':False,'campaign_limit':6,'campaign_count':len(directories),'total_ledger_renders':sum(c['renders'] for c in campaigns),'campaigns':campaigns,'calibrated_comparisons':comparisons,
      'adoption':'校正した2条件も採用しない。mora比で明瞭性悪化、accent-tap比の改善も新規4文で悪化し保護条件未達。',
      'mechanism':'42ms・時定数7msで8/8文脈の幾何閉鎖が成立。日本語弾音の品質達成とは別。',
      'free_fit':'86レンダーの自己回復で近傍は通過、遠方は不通過。自然参照への適合は未実施。v1係数境界の交差も検出し、次版の範囲写像だけを修正・単体検査。',
      'elapsed_seconds_from_first_campaign':time.time()-min(read(p/'started.json')['unix'] for p in directories),
      'experiment_bytes':sum(p.stat().st_size for p in ROOT.rglob('*') if p.is_file() and not p.is_symlink()),
      'mandatory_quality_gate':'日本語内容・知覚代理の独立資格が不足。診断の高得点で代替しない。',
      'confirmation_policy':'最終確認用の人間参照群を未使用のまま維持',
      'continuation_requires':'計画のcampaign上限の見直し。さらに品質完了には対象領域での独立E1/E2検証が必要。',
      'goal_status_recommendation':'blocked。品質目標を達成したとは扱わない。',
      'source_sha256':file_hash(Path(__file__))}
    write_once(ROOT/'results/cycle-decision.json',summary)
    write_once(ROOT/'results/execution-tools-manifest-v3.json',{'files':{str(p.relative_to(ROOT)):file_hash(p) for p in sorted(list(ROOT.glob('*.py'))+list((ROOT/'tests').glob('*.py')))}})
    print(json.dumps({k:v for k,v in summary.items() if k not in ('campaigns','calibrated_comparisons')},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
