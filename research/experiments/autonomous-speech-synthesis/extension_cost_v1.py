#!/usr/bin/env python3
"""保存台帳から、生成処理と管理処理を含む実時間の差を測定する。"""
from datetime import datetime
from pathlib import Path
import sys
import numpy as np
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'src'))
from autonomous_speech_synthesis.io import read,rows,write_once,file_hash


def main():
    result=[]
    for name in ('ans-spectral-fit-v1','ans-vtl-tap-timing-v1'):
        path=ROOT/'results'/name
        if not (path/'decision.json').exists():raise RuntimeError('未完了campaignは費用集計しません')
        events=rows(path/'ledger.jsonl');finished=[r for r in events if r['event']=='finished']
        trials=[read(path/r['result']) for r in finished]
        wall=datetime.fromisoformat(finished[-1]['utc']).timestamp()-read(path/'started.json')['unix']
        render=sum(r['elapsed_seconds'] for r in trials);audio=sum(r.get('samples',0)/r.get('sample_rate',1) for r in trials)
        result.append({'campaign':name,'renders':len(trials),'wall_seconds_to_last_finish':wall,'sum_trial_elapsed_seconds':render,
                       'audio_seconds':audio,'trial_elapsed_RTF':render/audio,'wall_RTF':wall/audio,
                       'wall_seconds_per_render':wall/len(trials),'trial_seconds_median':float(np.median([r['elapsed_seconds'] for r in trials])),
                       'time_outside_trial_seconds':wall-render,'ledger_sha256':file_hash(path/'ledger.jsonl')})
    output={'rows':result,'source_sha256':file_hash(Path(__file__)),
            'scope':'開始登録から最終試行完了まで。trial.elapsedは生成・信号評価・代表WAV保存を含む。予算走査・台帳更新・探索器・待機等は別であり、差分の全てを特定関数へ帰属しない。',
            'conclusion':'無人探索の計画にはwall_seconds_per_renderを使う。単体生成RTFだけをcampaignの実行費として扱わない。'}
    write_once(ROOT/'results/cycles/ans-extension-20261002-v1/cost-diagnostic.json',output)
    print(output)

if __name__=='__main__':main()
