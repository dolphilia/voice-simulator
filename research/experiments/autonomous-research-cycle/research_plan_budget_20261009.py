"""改訂工程時計を検証済み長期入口へ追加。旧管理ソースと封印を保持する。"""
from budget import read,digest
from long_horizon_budget import LongHorizonBudget

def account_plan(s):
    p=s['research_execution_plan']
    if p['status']!='active':raise RuntimeError('工程は未再開')
    delta=s['seconds']-p['last_accounted_seconds']
    if delta < -1e-9:raise RuntimeError('工程時計の減算禁止')
    if delta:
        segment=p['segment'];stage=next(x for x in p['first_stage']['stages'] if x['id']==segment['stage'])
        stage['used_seconds']+=delta;p['first_stage']['used_seconds']+=delta
        if segment['foundation_only']:p['foundation_only']['used_seconds']+=delta
        p['last_accounted_seconds']=s['seconds']
    return p

def check_plan(s,expected_seconds=0):
    p=account_plan(s)
    if expected_seconds<0:raise ValueError('負の予約')
    stage=next(x for x in p['first_stage']['stages'] if x['id']==p['segment']['stage'])
    pending=sum(j.get('expected_seconds',0) for j in s['jobs'].values() if j['status']=='running')
    need=expected_seconds+pending
    if stage['used_seconds']+need>stage['maximum_seconds']:raise RuntimeError('工程の予約上限')
    if p['first_stage']['used_seconds']+need>p['first_stage']['maximum_seconds']:raise RuntimeError('24時間工程の予約上限')
    if p['segment']['foundation_only'] and p['foundation_only']['used_seconds']+need>p['foundation_only']['maximum_seconds']:raise RuntimeError('基盤12時間の切替境界')
    if s['continuation_checkpoint'].get('user_pause_requested'):raise RuntimeError('ユーザーの停止が有効')
    return p

class ResearchPlanBudget(LongHorizonBudget):
    def _load(self,active=True):
        s=super()._load(active);account_plan(s);return s
    def _check(self,s,extra=0,campaign=None,tier='internal'):
        check_plan(s);return super()._check(s,extra,campaign,tier)
    def _science_ready(self,s):
        super()._science_ready(s);v=s['research_execution_plan'].get('guard_validation')
        if not v or digest(self.root/v['path'])!=v['sha256']:raise RuntimeError('工程時計の検証記録なし')
        audit=read(self.root/v['path'])
        if not audit['passed']:raise RuntimeError('工程時計の検証不通過')
        for n,h in audit['validated_sources'].items():
            if digest(self.root/n)!=h:raise RuntimeError('工程入口hash不一致')
        check_plan(s)
    def reserve(self,campaign,kind,label,count=1,reserve_bytes=0,*,expected_seconds=0):
        with self.locked():
            s=self._load();check_plan(s,expected_seconds);self._write_state(s)
        return super().reserve(campaign,kind,label,count,reserve_bytes,expected_seconds=expected_seconds)
    def transition_stage(self,target,reason,previous_status='completed',foundation_only=False):
        with self.locked():
            s=self._load();p=check_plan(s)
            if s['jobs'] or any(not c['closed'] for c in s['campaigns'].values()):raise RuntimeError('工程切替前に全ジョブと契約を閉じる')
            old=p['segment']['stage'];ids=[x['id'] for x in p['first_stage']['stages']]
            if target not in ids or ids.index(target)!=ids.index(old)+1:raise RuntimeError('工程巻戻し/飛越し禁止')
            if previous_status not in ('completed','partial_switched'):raise ValueError('終了状態不足')
            for x in p['first_stage']['stages']:
                if x['id']==old:x.update(status=previous_status,exit_reason=reason)
                if x['id']==target:x['status']='running'
            p['first_stage']['current']=target;p['segment']=dict(stage=target,foundation_only=foundation_only,reason=reason)
            p['foundation_only']['status']='running' if foundation_only else 'secondary_or_audio_work'
            self.event(s,dict(event='research_stage_transition',previous=old,target=target,previous_status=previous_status,reason=reason,stage_used_seconds=p['first_stage']['used_seconds'],foundation_used_seconds=p['foundation_only']['used_seconds']));self._write_state(s)
