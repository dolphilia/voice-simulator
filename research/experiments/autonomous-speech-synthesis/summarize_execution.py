#!/usr/bin/env python3
"""完了した各campaignを再探索せず集計し、補助処理と証拠の版を保存する。"""
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'src'))
from autonomous_speech_synthesis.io import read,rows,file_hash,write_once


def cer_summary(data):
    valid=[r for r in data if 'kana_CER' in r]
    return {'attempts':len(data),'available':len(valid),'kana_errors':sum(r['kana_errors'] for r in valid),
            'kana_characters':sum(r['kana_characters'] for r in valid),
            'kana_CER':sum(r['kana_errors'] for r in valid)/sum(r['kana_characters'] for r in valid) if valid else None}


def main():
    campaigns={}
    for cid in ('ans-pilot-v1','ans-vtl-speech-v1','ans-vtl-control-v1'):
        path=ROOT/'results'/cid
        ledger=rows(path/'ledger.jsonl')
        finished=[r for r in ledger if r['event']=='finished']
        trials=[read(path/r['result']) for r in finished]
        asr=read(path/'asr-evaluation.json')
        variants=sorted({r.get('variant','natural') for r in asr['rows']})
        campaigns[cid]={'started':sum(r['event']=='started' for r in ledger),'finished':len(finished),
            'failed':sum(r['status']!='signal-qualified' for r in trials),
            'asr':{v:cer_summary([r for r in asr['rows'] if r.get('variant','natural')==v]) for v in variants},
            'quality_goal_achieved':False,'confirmation_consumed':(path/'confirmation-consumed.json').exists()}
        if (path/'ai-qualification.json').exists():campaigns[cid]['utmos']=read(path/'ai-qualification.json')['groups']
    base=read(ROOT/'results/ans-vtl-speech-v1/asr-evaluation.json')['rows']
    common=cer_summary([r for r in base if r.get('variant')=='gesture-prosody' and int(r['id'].split('-')[1])<8])
    summary={'status':'inconclusive','quality_goal_achieved':False,'campaigns':campaigns,
        'renders':sum(r['started'] for r in campaigns.values()),'vtl_parent_same_first8':common,
        'script_sha256':file_hash(Path(__file__)),
        'scope':'開発・選別での診断。最終確認群の品質評価ではない。',
        'protocol_deviations':['主campaignのP3/P4は116課題でmax_p34_tasks=40を超過。レンダー総数は上限内。',
            '旧B9/G40の最初の帯域測定の窓時間が新方式と異なる。24kHz・280msの保存波形監査を別保存。'],
        'remaining':['日本語物理合成の独立したE1/E2資格','明瞭性・自然さの条件別品質','最終未使用条件で一度だけの品質確認']}
    write_once(ROOT/'results/execution-summary.json',summary)
    scripts=list(ROOT.glob('*.py'))+list((ROOT/'tests').glob('*.py'))+[ROOT/'config/evaluation-requirements.lock.txt']
    write_once(ROOT/'results/execution-tools-manifest.json',{'files':{str(p.relative_to(ROOT)):file_hash(p) for p in sorted(scripts)}})
    log=ROOT/'.cache/test-results-17.log'
    target=ROOT/'results/test-results-17.log'
    with target.open('x') as f:f.write(log.read_text())
    print(json.dumps({'renders':summary['renders'],'campaigns':{k:{a:b for a,b in v.items() if a in ('started','finished','failed')} for k,v in campaigns.items()}},indent=2))


if __name__=='__main__':main()
