#!/usr/bin/env python3
"""追加campaignの条件別比較と移出・評価器診断をまとめる。"""
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'src'))
from autonomous_speech_synthesis.io import read,write_once,file_hash,rows


def main():
    path=ROOT/'results/ans-vtl-japanese-v2'
    identity=read(path/'identity.json');sources=identity['config']['branch_sources']
    source_errors=[p for p,h in sources.items() if file_hash(ROOT/p)!=h]
    tasks={t['id']:t for t in read(path/'task-suite.json')['tasks']}
    attempts=rows(path/'ledger.jsonl');used={r['task_id'] for r in rows(path/'task-reservations.jsonl')}
    assert not source_errors and len(used)<=identity['config']['max_p34_tasks'] and used==set(tasks)
    asr=read(path/'asr-evaluation.json');groups={}
    for variant in ('baseline','mora','accent','accent-tap'):
        groups[variant]={}
        for split in ('all','development','novel'):
            data=[r for r in asr['rows'] if r.get('variant')==variant and (split=='all' or tasks[r['id']]['frontend_split']==split)]
            valid=[r for r in data if r.get('kana_CER') is not None]
            groups[variant][split]={'attempts':len(data),'available':len(valid),'kana_CER':sum(r['kana_errors'] for r in valid)/sum(r['kana_characters'] for r in valid) if valid else None}
    seeded=read(ROOT/'results/evaluator-seeded-v1/evaluation.json')
    checks=read(ROOT/'results/vtl-isolation-v2/denial-probes.json')
    assert all(v is True for v in checks.values())
    result={'quality_goal_achieved':False,'state':'inconclusive','render_count':sum(e['event']=='started' for e in attempts),'asr':groups,
      'source_hashes_verified':not source_errors,'unique_tasks':len(used),'task_limit':identity['config']['max_p34_tasks'],
      'utmos_fixed_seed_repeat_error':seeded['repeat_max_absolute_error'],'vtl_export_isolation_passed':read(ROOT/'results/vtl-isolation-v2/verification.json')['passed'],
      'adoption':'新規3条件は採用しない。moraは全体のみ改善し開発群で悪化。accent/tapは全体でも悪化。',
      'next_action':'短い舌尖閉鎖の応答を音声探索前に幾何で校正し、P2の自由適合と独立E1/E2評価の不足を解消する。最終確認群は維持。',
      'completion_audit':{'unknown_generation':'verified within limited inputs','reference_AI_network_independence':'verified for DSP and VTL','E0':'passed on rendered tasks','E1_required_content':'not achieved','E2_qualification':'not achieved; deterministic inference only','P2_free_fit':'sampled oracle only, incomplete','Japanese_dictionary_frontend':'12 texts, no general quality claim','final_heldout_quality_confirmation':'unopened','reproducible_evidence':'saved'},
      'source_sha256':file_hash(Path(__file__))}
    write_once(path/'followup-summary.json',result)
    manifest={str(p.relative_to(ROOT)):file_hash(p) for p in sorted(list(ROOT.glob('*.py'))+list((ROOT/'tests').glob('*.py')))}
    write_once(ROOT/'results/execution-tools-manifest-v2.json',{'files':manifest})
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
