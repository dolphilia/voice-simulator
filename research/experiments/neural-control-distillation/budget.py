"""単一campaignの上限と失敗を含む追記台帳。旧実験全体は走査しない。"""
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import time
import uuid

ROOT = Path(__file__).resolve().parent
RESULT = ROOT / 'results/nas-pilot-20261002-v1'
LIMITS = {'seconds': 14400, 'bytes': 3_000_000_000,
          'teacher': 48, 'render': 2000, 'ai': 300}


def digest(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as f:
        json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write('\n')


class Budget:
    def __init__(self, root=ROOT, result=RESULT):
        self.root, self.result = Path(root), Path(result)
        self.result.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def locked(self):
        with (self.result / '.lock').open('a') as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            yield

    def events(self):
        p = self.result / 'ledger.jsonl'
        return [json.loads(x) for x in p.read_text().splitlines()] if p.exists() else []

    def append(self, row):
        with (self.result / 'ledger.jsonl').open('a') as f:
            f.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + '\n')
            f.flush()
            os.fsync(f.fileno())

    def initialize(self):
        with self.locked():
            p = self.result / 'contract.json'
            if not p.exists():
                save(p, {'campaign': self.result.name, 'started_epoch': time.time(),
                         'limits': LIMITS, 'authorization': 'ユーザーによる新計画の実施指示',
                         'scope': '新実験ディレクトリの依存・重み・出力を全て容量に含む',
                         'old_campaign_reused': False})
            return json.loads(p.read_text())

    def inventory(self):
        t = time.monotonic()
        # シンボリックリンクから外部の既存資産を二重計数しない。新規依存はここへ実体保存する。
        files = [p for p in self.root.rglob('*') if p.is_file() and not p.is_symlink()]
        return {'bytes': sum(p.stat().st_size for p in files), 'files': len(files),
                'seconds': time.monotonic() - t}

    def reserve(self, kind, label, reserve_bytes=0, count=1):
        if kind not in ('teacher', 'render', 'ai', 'setup', 'train', 'audit'):
            raise ValueError('未登録の処理種別です')
        if reserve_bytes < 0:
            raise ValueError('容量予約は非負にします')
        if type(count) is not int or count < 1:
            raise ValueError('試行数は正の整数にします')
        with self.locked():
            contract = json.loads((self.result / 'contract.json').read_text())
            events = self.events()
            starts = [r for r in events if r['event'] == 'start']
            ends = {r['id'] for r in events if r['event'] == 'finish'}
            if any(r['id'] not in ends for r in starts):
                raise RuntimeError('未終了の処理があります。実プロセスを点検してから復旧してください')
            limits = contract['limits']
            if time.time() - contract['started_epoch'] >= limits['seconds']:
                raise RuntimeError('実行時間の上限です')
            if kind in limits and sum(r.get('count', 1) for r in starts if r['kind'] == kind) + count > limits[kind]:
                raise RuntimeError('試行数の上限です')
            inv = self.inventory()
            if inv['bytes'] + reserve_bytes + 65536 > limits['bytes']:
                raise RuntimeError('容量の上限です')
            row = {'event': 'start', 'id': uuid.uuid4().hex, 'kind': kind,
                   'label': label, 'epoch': time.time(), 'reserved_bytes': reserve_bytes, 'count': count,
                   'inventory': inv, 'pid': os.getpid(),
                   'source_hashes': {p.name: digest(p) for p in sorted(self.root.glob('*.py'))}}
            self.append(row)
            return row

    def finish(self, ticket, status, details=None):
        with self.locked():
            if any(r['event'] == 'finish' and r['id'] == ticket['id'] for r in self.events()):
                raise RuntimeError('終了記録が重複しています')
            self.append({'event': 'finish', 'id': ticket['id'], 'status': status,
                         'seconds': time.time() - ticket['epoch'], 'details': details or {}})

    @contextmanager
    def job(self, kind, label, reserve_bytes=0, count=1):
        ticket = self.reserve(kind, label, reserve_bytes, count)
        try:
            yield ticket
        except BaseException as exc:
            self.finish(ticket, 'failed', {'error': repr(exc)})
            raise
        else:
            self.finish(ticket, 'completed')
