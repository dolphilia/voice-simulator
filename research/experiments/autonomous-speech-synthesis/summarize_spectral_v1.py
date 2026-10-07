#!/usr/bin/env python3
"""自由適合の選別残差を話者単位で集計し、少数話者の推論限界を残す。"""
import itertools
import sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'src'))
from autonomous_speech_synthesis.io import read,write_once,rows,file_hash
from spectral_fit_v1 import features


class Results:
    def __init__(self,path):self.path=path


def main():
    path=ROOT/'results/ans-spectral-multistart-v1'
    comparison=read(path/'comparison.json');reference=read(path/'reference-spectral-selection.json')
    trials={e['trial_id']:read(path/e['result']) for e in rows(path/'ledger.jsonl') if e['event']=='finished'}
    tasks={t['id']:t for t in read(path/'task-suite.json')['tasks']};report=[]
    tested=sum(r['status']=='diagnostic-only' for r in comparison['rows'])
    for row in comparison['rows']:
        if row['status']!='diagnostic-only':report.append(row);continue
        task=tasks[row['task']];grouped={}
        for r in reference['rows']:
            if r['vowel']==task['phonemes'][0] and abs(np.log(r['f0_hz']/task['f0_hz']))<np.log(1.3):
                grouped.setdefault(r['speaker'],[]).append(r['features'])
        generated={kind:[features(Results(path),trials[r['trial']]) for r in row['selection'] if r['kind']==kind] for kind in ('shared','free')}
        speakers=[]
        for speaker,values in grouped.items():
            target=np.mean(values,axis=0)
            losses={kind:float(np.mean([(x-target)**2 for x in xs])) for kind,xs in generated.items()}
            speakers.append({'speaker':speaker,**losses,'free_minus_shared':losses['free']-losses['shared']})
        deltas=np.array([r['free_minus_shared'] for r in speakers]);observed=float(deltas.mean())
        # 小標本で達成可能なp値の粒度を明示するため、全符号反転を列挙する。
        permutation=[float(np.mean(deltas*np.array(signs))) for signs in itertools.product((-1,1),repeat=len(deltas))]
        p=sum(x<=observed+1e-14 for x in permutation)/len(permutation)
        report.append({'task':row['task'],'development_shared':row['shared_development_loss'],'development_free':row['free_development_loss'],
                       'selection_speaker_rows':speakers,'selection_mean_delta':observed,'exact_sign_flip_p':p,
                       'diagnostic_bonferroni_alpha':.05/tested,'diagnostic_threshold_met':p<=.05/tested,'best_point':row['best_point'],
                       'limits':'探索開始後に追加した探索的集計であり、事前登録済みの昇格検定ではない。符号反転は対称性の仮定を含む。選別2〜3話者ではp値の粒度が粗い。'})
    valid=[r for r in report if 'selection_mean_delta' in r]
    result={'cells_tested':len(valid),'cells_excluded':len(report)-len(valid),'selection_improved_cells':sum(r['selection_mean_delta']<0 for r in valid),
            'diagnostic_threshold_met_cells':sum(r['diagnostic_threshold_met'] for r in valid),'rows':report,'export_allowed':False,
            'promotion_allowed':False,
            'analysis_registration':'話者単位の符号反転とセル数によるBonferroni補正は探索開始後に追加した診断。事前登録済みの品質判定・昇格条件を置換しない。',
            'quality_goal_achieved':False,'scope':'条件別静的スペクトルの能力診断。自由適合係数は共有生成規則へ移出しない。',
            'source_sha256':file_hash(Path(__file__))}
    write_once(path/'speaker-comparison.json',result);print({k:v for k,v in result.items() if k!='rows'})

if __name__=='__main__':main()
