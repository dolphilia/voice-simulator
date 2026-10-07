"""既存の凍結コアを保ち、課題数上限と初期化失敗時の解放を追加する。"""
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'src'))
from autonomous_speech_synthesis.runner import Campaign,BudgetExhausted
from autonomous_speech_synthesis.io import append,rows


class BoundedCampaign(Campaign):
    def __init__(self,campaign_id,config=None):
        try:super().__init__(campaign_id,config)
        except BaseException:
            if hasattr(self,'lock') and not self.lock.closed:self.lock.close()
            raise

    def preflight_tasks(self,tasks):
        ids={t['id'] for t in tasks if t['stage'] in ('P3','P4')}
        if len(ids)>self.config['max_p34_tasks']:
            raise BudgetExhausted('P3/P4の異なる課題数の上限です')

    def trial(self,candidate_id,backend,stage,task,seed,parameters,renderer,save=False):
        if stage in ('P3','P4'):
            reservations=self.path/'task-reservations.jsonl'
            used={r['task_id'] for r in rows(reservations)}
            if task['id'] not in used:
                if len(used)>=self.config['max_p34_tasks']:
                    raise BudgetExhausted('P3/P4の異なる課題数の上限です')
                # 中断や失敗でも予約を消さない。再開後も異なる課題数を保持する。
                append(reservations,{'task_id':task['id'],'stage':stage})
        return super().trial(candidate_id,backend,stage,task,seed,parameters,renderer,save)
