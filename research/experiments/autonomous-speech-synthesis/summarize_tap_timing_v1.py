#!/usr/bin/env python3
"""事前の系列保護条件に沿って接触時刻の比較を報告する。"""
import sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'src'))
from autonomous_speech_synthesis.io import read,write_once,file_hash


def main():
    p=ROOT/'results/ans-vtl-tap-timing-v1'
    tasks={t['id']:t for t in read(p/'task-suite.json')['tasks']}
    sources=[(p,'early'),(p,'late'),(ROOT/'results/ans-vtl-calibrated-v3','mora-tap-calibrated'),(ROOT/'results/ans-vtl-japanese-v2','mora')]
    groups={};sentences={}
    for path,variant in sources:
        data=[r for r in read(path/'asr-evaluation.json')['rows'] if r.get('variant')==variant and r['group']=='generated']
        sentences[variant]={r['id']:r for r in data}
        groups[variant]={}
        for group in ('all','development','novel'):
            selected=[r for r in data if group=='all' or tasks[r['id']]['frontend_split']==group]
            groups[variant][group]={'count':len(selected),'kana_CER':sum(r['kana_errors'] for r in selected)/sum(r['kana_characters'] for r in selected)}
    decisions=[]
    for variant in ('early','late'):
        protections=[{'comparator':base,'group':group,'delta_CER':groups[variant][group]['kana_CER']-groups[base][group]['kana_CER']} for base in ('mora-tap-calibrated','mora') for group in ('all','development','novel')]
        decisions.append({'variant':variant,'protected_diagnostic_pass':all(r['delta_CER']<=0 for r in protections),'protections':protections,'quality_promotion':False})
    geometry=read(p/'timing-audit.json')['geometry'];mechanism={}
    for variant in ('early','center','late'):
        data=[r for r in geometry if r['variant']==variant]
        mechanism[variant]={'interval_count':len(data),'near_closure_count':sum(r['near_closure'] for r in data),
                            'duration_seconds':[r['near_closure_seconds'] for r in data],
                            'min_area_cm2':[r['minimum_area_cm2'] for r in data]}
    result={'groups':groups,'decisions':decisions,'mechanism':mechanism,'state':'inconclusive','quality_goal_achieved':False,
            'scope':'同じ12文への診断。既使用のnovel群は最終未使用群ではない。ASRは補助尺度で、自然さや正しい日本語弾音の証拠にしない。',
            'source_sha256':file_hash(Path(__file__))}
    write_once(p/'timing-comparison.json',result)
    print(groups);print(decisions)

if __name__=='__main__':main()
