"""中断・継続時に、実ファイルから進捗を再点検する。"""
import argparse
import json
import time
from budget import Budget, ROOT, RESULT, save


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    budget=Budget()
    events=budget.events()
    starts=[r for r in events if r['event']=='start']
    finishes={r['id']:r for r in events if r['event']=='finish'}
    contract=json.loads((RESULT/'contract.json').read_text())
    state={
        'created_epoch':time.time(),
        'goal_status':'pilot比較・監査・移出済み。最終品質目標は未達',
        'elapsed_seconds':time.time()-contract['started_epoch'],
        'counts':{kind:sum(r.get('count',1) for r in starts if r['kind']==kind) for kind in ('teacher','render','ai','train','setup','audit')},
        'failed':[{'id':r['id'],'kind':r['kind'],'label':r['label'],'error':finishes[r['id']]['details']}
                  for r in starts if r['id'] in finishes and finishes[r['id']]['status']=='failed'],
        'pending':[r for r in starts if r['id'] not in finishes],
        'pending_note':'台帳だけでプロセス生存を断定しない。ツールのsessionまたはOSプロセスを別途確認する',
        'inventory':budget.inventory(),
        'evidence':{name:(RESULT/name).exists() for name in (
            'teacher-provenance.json','teacher-load-verification.json','splits.json','control-schema.json',
            'protocol.json','teacher-controls-v2.json','renderer-qualification.json','fit-qualification.json',
            'acoustic-repair-audit.json','model-selection.json','runtime-audit.json','main-comparison-summary.json',
            'hts-runtime-audit-v2.json','extended-comparison-summary-v2.json','completion-audit.json')},
        'fitted_utterances':len(list((RESULT/'fitted').glob('*/summary.json'))),
        'completed_comparison_renders':len([p for p in (RESULT/'comparisons').glob('*/*.json') if not p.name.endswith('.control.json')]),
        'completed_content_evaluations':len(list((RESULT/'content').glob('*/*.json'))),
        'next':['日本語HMM/VTLへの知覚評価の適用資格を調べる',
                'VOT/局所遷移を実波形から測る独立な整列方法を設計する',
                '次の比較は新しい文・文脈・教師/自然参照と費用契約を固定し、同じ監査資料で再調整しない',
                '現campaignはAI評価299/300。上限・campaign数を自動延長しない'],
    }
    save(RESULT/args.output,state)
    print(json.dumps({k:state[k] for k in ('counts','fitted_utterances','inventory','elapsed_seconds')},ensure_ascii=False))


if __name__=='__main__':
    main()
