"""承認済み長期予算を同じ台帳へ強制する別版。旧科学ソースは変更しない。"""
import importlib.util
import os
from pathlib import Path
import shutil
import time
import uuid

from budget import ROOT, MARGIN, digest, read

_source = ROOT / 'campaigns/nas-additional-closeout-20261008-v1/temporary_storage.py'
_spec = importlib.util.spec_from_file_location('_arc_frozen_temporary', _source)
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)
ManagedStorageBudget = _module.ManagedStorageBudget

AMENDMENT = 'long-horizon-20261008-v1'
TOTALS = dict(seconds=691200, render=120000, teacher=2000, ai=200000,
              dsp=400000, train=120, inverse=600, download=10000000000,
              write_bytes=600000000000)
CLOSING_SECONDS = 43200
NORMAL = dict(seconds=14400, bytes=2000000000, render=3000, teacher=128,
              ai=6000, dsp=15000, train=8, inverse=40)
VALIDATION_SOURCES = ('long_horizon_budget.py', 'test_long_horizon_budget.py',
                      'budget.py', 'storage_budget.py', 'storage_guard.py',
                      'campaigns/nas-additional-closeout-20261008-v1/temporary_storage.py')


class LongHorizonBudget(ManagedStorageBudget):
    def __init__(self, root=ROOT):
        super().__init__(root)
        self._authorization(read(self.state_path))

    def _authorization(self, state):
        a = state.get('long_horizon')
        if not a or a['id'] != AMENDMENT or a['status'] != 'applied':
            raise RuntimeError('長期包括承認・適用がありません')
        p = self.root / a['approval_path']
        if digest(p) != a['approval_sha256']:
            raise RuntimeError('承認記録hash不一致')
        approval = read(p)
        if approval['status'] != 'approved_pending_implementation' or not approval['explicit_user_approval']:
            raise RuntimeError('明示承認記録がありません')
        if state['cycle'] != approval['cycle']:
            raise RuntimeError('サイクル変更による消費初期化禁止')
        if any(state['limits'].get(k) != v for k, v in TOTALS.items()) or 'campaigns' in state['limits']:
            raise RuntimeError('承認済み累計上限と台帳が不一致')
        base = approval['base_state']
        if state['seconds'] < base['seconds'] or state['write_bytes'] < base['write_bytes']:
            raise RuntimeError('既消費の減算禁止')
        if any(state['counts'].get(k, 0) < v for k, v in base['counts'].items()):
            raise RuntimeError('既消費回数の減算禁止')
        if any(state['campaigns'].get(k) != v for k, v in base['campaigns'].items()):
            raise RuntimeError('旧campaign契約・終了状態の変更禁止')
        return a

    def _load(self, active=True):
        state = super()._load(active)
        self._authorization(state)
        return state

    def _remaining(self, state, key, exclude=None):
        result = 0
        for name, c in state['campaigns'].items():
            if c['closed'] or name == exclude or not c.get('long_horizon_contract'):
                continue
            if key == 'seconds':
                used = state['seconds'] - c['start_seconds']
            elif key == 'write_bytes':
                # 並行時もグローバル差分を保守的に各契約へ課す。返金しない。
                used = state['write_bytes'] - c['start_write_bytes']
            else:
                used = c['counts'].get(key, 0)
            result += max(0, c['limits'][key] - used)
        return result

    def _science_ready(self, state):
        a = self._authorization(state)
        path = a.get('validation_path')
        if not path or digest(self.root / path) != a.get('validation_sha256'):
            raise RuntimeError('長期ラッパーの有効な検証が未完了')
        if not read(self.root / path).get('passed'):
            raise RuntimeError('長期ラッパー検証不通過')
        validated = read(self.root / path)['validated_sources']
        if not set(VALIDATION_SOURCES).issubset(validated):
            raise RuntimeError('検証済み管理ソースの登録不足')
        for name, expected in validated.items():
            if digest(self.root / name) != expected:
                raise RuntimeError('検証済み管理ソースhash不一致')

    def _check(self, state, extra=0, campaign=None, tier='internal'):
        self._authorization(state)
        self.guard.check()
        if state['seconds'] >= TOTALS['seconds']:
            raise RuntimeError('累計実稼働時間上限')
        if shutil.disk_usage(self.root).free < 20000000000:
            raise RuntimeError('内蔵実空き20GB未満')
        temporary = sum(w['maximum_bytes'] for w in state.get('temporary_work', {}).values()
                        if w['status'] != 'removed')
        reserved = sum(j['reserve_bytes'] for j in state['jobs'].values() if j['status'] == 'running')
        overhead = sum(p.stat().st_size for p in self.control.glob('*') if p.is_file())
        allocation = extra + temporary + reserved + MARGIN
        if state['payload_bytes'] + overhead + allocation > state['limits']['experiment_bytes']:
            raise RuntimeError('包括保存予約上限')
        if state['write_bytes'] + extra + MARGIN > TOTALS['write_bytes']:
            raise RuntimeError('累積書込予約上限')
        if campaign:
            c = state['campaigns'][campaign]
            pending = sum(j['reserve_bytes'] for j in state['jobs'].values()
                          if j['campaign'] == campaign and j['status'] == 'running')
            if c['payload_bytes'] + pending + extra + temporary + MARGIN > c['limits']['bytes']:
                raise RuntimeError('campaign保存予約上限')
            if state['seconds'] - c['start_seconds'] >= c['limits']['seconds']:
                raise RuntimeError('campaign時間上限')
            if state['write_bytes'] - c['start_write_bytes'] + extra + MARGIN > c['limits']['write_bytes']:
                raise RuntimeError('campaign累積書込予約上限')
        rows = self.locations().values()
        external = sum(r['size'] for r in rows)
        aliases = sum(r['alias_size'] for r in rows)
        internal = state['payload_bytes'] - external + aliases + overhead
        if internal + reserved + temporary + (extra if tier == 'internal' else 0) + MARGIN > self.storage['internal_experiment_bytes']:
            raise RuntimeError('内蔵保存予約上限')
        pending = reserved + temporary + (extra if tier == 'external' else 0)
        if external + pending + MARGIN > self.storage['external_experiment_bytes']:
            raise RuntimeError('外部保存予約上限')
        if shutil.disk_usage(self.guard.mount).free < pending + self.storage['external_closing_bytes'] + MARGIN:
            raise RuntimeError('外部実空き・終了容量不足')

    def start_campaign(self, name, prefix, limits, protocol_sha256, *, purpose='science', expansion_reason=None):
        if purpose not in ('science', 'management', 'closeout'):
            raise ValueError('未登録のcampaign用途')
        if not prefix.startswith('campaigns/') or '..' in Path(prefix).parts:
            raise ValueError('保存先が不正')
        for k in ('seconds', 'bytes', 'write_bytes', 'setup', 'audit', *TOTALS.keys()):
            if k not in limits or not isinstance(limits[k], int) or limits[k] < 0:
                raise ValueError('比較一式の上限が未登録: ' + k)
        for k, cap in NORMAL.items():
            if limits[k] > cap * (2 if expansion_reason else 1):
                raise RuntimeError('個別上限超過または拡張理由なし: ' + k)
        if limits['seconds'] <= 0 or limits['bytes'] <= MARGIN:
            raise ValueError('終了まで実行できる予約が必要')
        if purpose != 'science' and any(limits[k] for k in ('render','teacher','ai','dsp','train','inverse','download')):
            raise ValueError('管理・終了契約へ科学費を転嫁しない')
        with self.locked():
            s = self._load()
            if name in s['campaigns']:
                raise FileExistsError('campaign再初期化禁止')
            if purpose == 'science':
                self._science_ready(s)
            end = TOTALS['seconds'] - (0 if purpose == 'closeout' else CLOSING_SECONDS)
            if s['seconds'] + self._remaining(s, 'seconds') + limits['seconds'] > end:
                raise RuntimeError('全時間予約超過。最後12時間は終了専用')
            for k, total in TOTALS.items():
                if k == 'seconds': continue
                used = s['write_bytes'] if k == 'write_bytes' else s['counts'].get(k, 0)
                if used + self._remaining(s, k) + limits[k] + (MARGIN if k == 'write_bytes' else 0) > total:
                    raise RuntimeError('比較一式の包括予約超過: ' + k)
            unspent_capacity = sum(max(0, c['limits']['bytes'] - c['payload_bytes'])
                                   for c in s['campaigns'].values() if not c['closed'])
            self._check(s, limits['bytes'] + unspent_capacity)
            s['campaigns'][name] = dict(prefix=prefix, limits=dict(limits), counts={},
                start_seconds=s['seconds'], start_write_bytes=s['write_bytes'],
                protocol_sha256=protocol_sha256, payload_bytes=0, closed=False,
                long_horizon_contract=True, purpose=purpose, expansion_reason=expansion_reason,
                attempts={}, technical_retries=0)
            self._write_state(s)

    def reserve(self, campaign, kind, label, count=1, reserve_bytes=0, *, expected_seconds=0):
        with self.locked():
            s = self._load(); c = s['campaigns'][campaign]
            if c['closed'] or not c.get('long_horizon_contract'):
                raise RuntimeError('旧契約・終了契約への新規処理禁止')
            if kind not in ('render','teacher','ai','dsp','train','inverse','download','setup','audit') or kind not in c['limits'] or count < 1 or reserve_bytes < 0 or expected_seconds < 0:
                raise ValueError('未登録の処理予約')
            if c['purpose'] == 'science':
                self._science_ready(s)
            end = TOTALS['seconds'] - (0 if c['purpose'] == 'closeout' else CLOSING_SECONDS)
            if s['seconds'] + expected_seconds >= end:
                raise RuntimeError('最後12時間の新規研究・管理処理禁止')
            if s['seconds'] - c['start_seconds'] + expected_seconds >= c['limits']['seconds']:
                raise RuntimeError('ジョブ時間予約超過')
            if kind == 'train' and expected_seconds > 1800:
                raise RuntimeError('学習30分上限')
            if c['counts'].get(kind, 0) + count > c['limits'][kind]:
                raise RuntimeError('campaign回数予約超過')
            if kind in TOTALS and s['counts'].get(kind, 0) + count + self._remaining(s, kind, campaign) > TOTALS[kind]:
                raise RuntimeError('包括回数予約超過')
            running = list(s['jobs'].values())
            if len(running) >= 2 or (kind in ('teacher','train') and any(j['kind'] in ('teacher','train') for j in running)):
                raise RuntimeError('同時ジョブ上限')
            attempt_key = kind + ':' + label
            previous = c['attempts'].get(attempt_key, [])
            if previous and (previous[-1]['status'] != 'failed' or len(previous) >= 3 or c['technical_retries'] >= 10):
                raise RuntimeError('再試行資格または上限不通過')
            self._check(s, reserve_bytes, campaign)
            token = uuid.uuid4().hex
            s['counts'][kind] = s['counts'].get(kind, 0) + count
            c['counts'][kind] = c['counts'].get(kind, 0) + count
            if previous: c['technical_retries'] += 1
            c['attempts'].setdefault(attempt_key, []).append(dict(id=token, status='running'))
            s['jobs'][token] = dict(campaign=campaign, kind=kind, label=label, count=count,
                reserve_bytes=reserve_bytes, status='running', pid=os.getpid(),
                started_epoch=time.time(), expected_seconds=expected_seconds)
            self.event(s, dict(event='start', id=token, **s['jobs'][token]))
            self._write_state(s)
        return token

    def finish(self, job, error=None):
        with self.locked():
            s = self._load(); j = s['jobs'][job]
            c = s['campaigns'][j['campaign']]
            attempt = c['attempts'][j['kind'] + ':' + j['label']][-1]
            if attempt['id'] != job or attempt['status'] != 'running':
                raise RuntimeError('ジョブ二重終了またはID不一致')
            attempt['status'] = 'failed' if error else 'completed'
            attempt['error'] = error
            j.update(status=attempt['status'], error=error, finished_epoch=time.time(), reserve_bytes=0)
            self.event(s, dict(event='finish', id=job, **j))
            del s['jobs'][job]
            self._write_state(s)

    def close_campaign(self, name):
        state = self.snapshot()
        if state['campaigns'][name]['closed']:
            raise RuntimeError('campaign二重終了禁止')
        super().close_campaign(name)
        with self.locked():
            s = self._load(); c = s['campaigns'][name]
            if c['purpose'] == 'science':
                s['long_horizon']['scientific_completed'] += 1
            self._write_state(s)

    def review_due(self, state=None):
        s = self.snapshot() if state is None else state
        a = s['long_horizon']; last = a['last_review']
        resources = {k: (s['seconds'] if k == 'seconds' else s['write_bytes'] if k == 'write_bytes'
                         else s['counts'].get(k, 0)) / total for k, total in TOTALS.items()}
        return dict(due=s['seconds'] - last['seconds'] >= 86400 or
                    a['scientific_completed'] - last['scientific_completed'] >= 6,
                    resources=resources, new_routes_avoid=[k for k,v in resources.items() if v >= .85],
                    allocation_review=[k for k,v in resources.items() if v >= .70])
