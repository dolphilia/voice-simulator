#!/usr/bin/env python3
"""実行中でも再確認6件が完了したセルだけを、探索に戻さず選別話者で点検する。"""
import argparse
import json
from pathlib import Path
import sys
import numpy as np
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'src'))
from autonomous_speech_synthesis.io import read,write_once,now,file_hash
from spectral_fit_v1 import features

class Results:
    def __init__(self,path):self.path=path


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--checkpoint',required=True);args=parser.parse_args()
    if not args.checkpoint.isdigit():raise ValueError('checkpointには整数を指定してください')
    p=ROOT/'results/ans-spectral-multistart-v1'
    raw=(p/'ledger.jsonl').read_text();events=[json.loads(line) for line in raw[:raw.rfind('\n')].splitlines()]
    grouped={}
    for e in events:
        if e['event']!='finished':continue
        row=read(p/e['result'])
        if row['stage']=='P2-recheck':grouped.setdefault(row['task']['id'],[]).append(row)
    ref=read(p/'reference-spectral-selection.json');summary=[]
    for name,group in sorted(grouped.items()):
        expected={(kind,seed) for kind in ('shared','free') for seed in (101,103,107)}
        actual={(r['candidate_id'],r['seed']) for r in group}
        if actual!=expected or len(group)!=6:continue
        task=group[0]['task'];speakers={}
        for r in ref['rows']:
            if r['vowel']==task['phonemes'][0] and abs(np.log(r['f0_hz']/task['f0_hz']))<np.log(1.3):
                speakers.setdefault(r['speaker'],[]).append(r['features'])
        measures={kind:[features(Results(p),r) for r in group if r['candidate_id']==kind] for kind in ('shared','free')}
        paired=[]
        for speaker,values in speakers.items():
            target=np.mean(values,axis=0)
            shared=float(np.mean([(x-target)**2 for x in measures['shared']]))
            free=float(np.mean([(x-target)**2 for x in measures['free']]))
            paired.append({'speaker':speaker,'shared':shared,'free':free,'difference':free-shared})
        summary.append({'task':name,'speakers':paired,'speaker_mean_difference':float(np.mean([r['difference'] for r in paired]))})
    result={'utc':now(),'completed_cells':len(summary),'rows':summary,'selection_improved_cells':sum(r['speaker_mean_difference']<0 for r in summary),
            'scope':'進行中の事前指定比較の監視。完了6再確認/セルのみ。選別結果を実行中の探索・停止基準へ戻さない。全体の品質・全セルの成功を主張しない。',
            'source_sha256':file_hash(Path(__file__)),'source_reference_sha256':file_hash(p/'reference-spectral-selection.json')}
    write_once(ROOT/f'results/cycles/ans-extension-20261002-v1/selection-checkpoint-{args.checkpoint}.json',result)
    print({k:v for k,v in result.items() if k!='rows'})
    for row in summary:print(row['task'],row['speaker_mean_difference'])

if __name__=='__main__':main()
