"""承認済み追加サイクルの独立計数。旧campaignの台帳・制限は変更しない。"""
import copy
import fcntl
import re
import time
from pathlib import Path
from campaign_v2 import BoundedCampaign
from autonomous_speech_synthesis.io import ROOT, read, write_once, rows, digest, code_manifest, environment, now
from autonomous_speech_synthesis.runner import BudgetExhausted

CYCLE_ID = 'ans-extension-20261002-v1'
LIMITS = {'max_campaigns': 3, 'max_cycle_seconds': 86400, 'max_additional_bytes': 10_000_000_000,
          'max_campaign_seconds': 28800}


def inventory(root):
    return {str(p.relative_to(root)): p.stat().st_size for p in root.rglob('*') if p.is_file() and not p.is_symlink()}


class CycleCampaign(BoundedCampaign):
    def __init__(self, campaign_id, config, root=None):
        self.root = Path(root) if root is not None else ROOT
        if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_.-]{0,80}', campaign_id):
            raise ValueError('campaign IDの書式が不正です')
        self.config = copy.deepcopy(config)
        self.config['cycle_id'] = CYCLE_ID
        self.config['approved_cycle_limits'] = LIMITS.copy()
        self.cycle = self.root/'results/cycles'/CYCLE_ID
        self.cycle.mkdir(parents=True, exist_ok=True)
        self.path = self.root/'results'/campaign_id
        self.lock = None
        # 登録を直列化し、失敗・中断した登録も枠へ含める。
        with (self.cycle/'.registration.lock').open('a+') as registration:
            fcntl.flock(registration, fcntl.LOCK_EX)
            approval = self.cycle/'approval.json'
            if not approval.exists():
                write_once(approval, {'cycle_id': CYCLE_ID, 'approved_date': '2026-10-02',
                    'authorization': 'ユーザー: 提案を承認します。作業を続行してください。',
                    'limits': LIMITS, 'unix': time.time(), 'utc': now(),
                    'prior_campaigns': sorted(p.parent.name for p in (self.root/'results').glob('*/started.json')),
                    'baseline_inventory': inventory(self.root), 'quality_conditions_unchanged': True})
            self.approval = read(approval)
            if self.approval['limits'] != LIMITS:
                raise ValueError('承認された上限が現在の実装と一致しません')
            members = self.cycle/'members'
            members.mkdir(exist_ok=True)
            member = members/(campaign_id+'.json')
            if not member.exists():
                if (self.path/'started.json').exists():
                    raise ValueError('既存campaignを追加サイクルへ付け替えることはできません')
                if len(list(members.glob('*.json'))) >= LIMITS['max_campaigns']:
                    raise BudgetExhausted('追加サイクルのcampaign数上限です')
                self.check_cycle()
                write_once(member, {'campaign_id': campaign_id, 'unix': time.time(), 'utc': now()})
            self.path.mkdir(parents=True, exist_ok=True)
            try:
                self.lock = (self.path/'.run.lock').open('a+')
                fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                identity = {'code': code_manifest(), 'config': self.config, 'environment': environment()}
                write_once(self.path/'identity.json', identity)
                self.identity_hash = digest(identity)
                if not (self.path/'started.json').exists():
                    write_once(self.path/'started.json', read(member))
                self.events = rows(self.path/'ledger.jsonl')
            except BaseException:
                if self.lock is not None: self.lock.close()
                raise

    def check_cycle(self):
        if time.time()-self.approval['unix'] > LIMITS['max_cycle_seconds']:
            raise BudgetExhausted('追加サイクルの実時間上限です')
        # 削除した旧資産で追加容量を相殺しない。既存ファイルの増分も含める。
        baseline = self.approval['baseline_inventory']
        current = inventory(self.root)
        added = sum(max(0, size-baseline.get(name, 0)) for name, size in current.items())
        if added+10_000_000 >= LIMITS['max_additional_bytes']:
            raise BudgetExhausted('追加サイクルの保存量上限です')
        return added

    def budget_check(self, stage, backend):
        self.check_cycle()
        limits = self.config['budget']
        if time.time()-read(self.path/'started.json')['unix'] > min(limits['max_campaign_seconds'], LIMITS['max_campaign_seconds']):
            raise BudgetExhausted('campaign実時間上限です')
        if sum(inventory(self.path).values())+10_000_000 >= limits['max_campaign_bytes']:
            raise BudgetExhausted('campaign保存量上限です')
        key = ('max_p1_renders' if stage == 'P1' else 'max_legacy_renders' if backend in ('B9','G40')
               else 'max_recheck_renders' if stage == 'P2-recheck' else 'max_p2_per_backend' if stage == 'P2'
               else 'max_confirm_renders' if stage == 'P5' else 'max_p34_renders')
        count = sum(e['event']=='started' and e['budget_key']==key and
                    (key!='max_p2_per_backend' or e['backend']==backend) for e in self.events)
        if count >= limits[key]: raise BudgetExhausted('レンダー上限です: '+key)
        return key
