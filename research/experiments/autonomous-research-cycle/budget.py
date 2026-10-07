"""包括予算を全campaignで共有する。予約は処理開始前に永続化する。"""
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import time
import uuid

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[2]
CONTROL = ROOT / 'control'
LIMITS = {'seconds': 172800, 'bytes': 20_000_000_000, 'experiment_bytes': 18_000_000_000,
          'write_bytes': 60_000_000_000, 'download': 5_000_000_000,
          'render': 20000, 'teacher': 1000, 'ai': 50000, 'dsp': 100000,
          'train': 60, 'inverse': 300, 'campaigns': 24}
MARGIN = 262144


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024*1024), b''): h.update(block)
    return h.hexdigest()


def encode(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n').encode('utf8')


def read(path): return json.loads(Path(path).read_text())


class Budget:
    def __init__(self, root=ROOT, limits=None):
        self.root = Path(root).resolve()
        self.control = self.root/'control'
        self.state_path = self.control/'state.json'
        self.lock_path = self.control/'lock'
        self.initial_limits = dict(LIMITS if limits is None else limits)

    @contextmanager
    def locked(self):
        self.control.mkdir(parents=True, exist_ok=True)
        with self.lock_path.open('a+b') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try: yield
            finally: fcntl.flock(lock, fcntl.LOCK_UN)

    def inventory(self):
        return {str(p.relative_to(self.root)): [p.stat().st_size, p.stat().st_mtime_ns]
                for p in self.root.rglob('*') if p.is_file() and self.control not in p.parents}

    def index(self):
        con=sqlite3.connect(self.control/'files.sqlite')
        con.execute('CREATE TABLE IF NOT EXISTS files (name TEXT PRIMARY KEY, size INTEGER, mtime INTEGER)')
        return con

    def registered(self):
        with self.index() as con:
            return {n:[s,t] for n,s,t in con.execute('SELECT name,size,mtime FROM files')}

    def set_file(self,state,name,value):
        if len(name)>1000: raise ValueError('保存先名が長すぎます')
        with self.index() as con:
            if value is None:con.execute('DELETE FROM files WHERE name=?',(name,))
            else:con.execute('INSERT OR REPLACE INTO files VALUES (?,?,?)',(name,*value))
        # SQLiteのページ・journal更新費は、行更新ごとに64KiBを保守的に計数。
        state['write_bytes']+=65536

    def event(self,state,value):
        data=(json.dumps(value,ensure_ascii=False,allow_nan=False)+'\n').encode('utf8')
        with (self.control/'jobs.jsonl').open('ab') as f:f.write(data);f.flush();os.fsync(f.fileno())
        state['write_bytes']+=len(data)

    def _write_state(self, state):
        # 台帳更新そのものも累積書込へ計数する。数桁の自己参照分は反復で確定。
        base = state['write_bytes']
        n = 0
        for _ in range(8):
            state['write_bytes'] = base+n
            data = encode(state)
            if len(data) == n: break
            n = len(data)
        else: raise RuntimeError('台帳容量が安定しません')
        if state['write_bytes'] > state['limits']['write_bytes']: raise RuntimeError('累積書込上限')
        path = self.state_path.with_suffix('.tmp')
        with path.open('xb') as f: f.write(data); f.flush(); os.fsync(f.fileno())
        os.replace(path, self.state_path)

    def initialize(self, authorization, initial_seconds=0):
        with self.locked():
            if self.state_path.exists(): raise FileExistsError('包括台帳は既に存在します。リセット禁止')
            files = self.inventory()
            state = {'version': 1, 'cycle': 'arc-20261004-v1', 'authorization': authorization,
                     'limits': self.initial_limits, 'counts': {}, 'campaigns': {}, 'jobs': {},
                     'payload_bytes':sum(v[0] for v in files.values()), 'seconds': initial_seconds,
                     'write_bytes': sum(v[0] for v in files.values()), 'session': None,
                     'created_epoch': time.time(), 'closed': False}
            for n,v in files.items():self.set_file(state,n,v)
            self._write_state(state)

    def _tick(self, state):
        now = time.time()
        if state['session'] is not None:
            delta = max(0, now-state['session']['checkpoint'])
            state['seconds'] += delta
            state['session']['checkpoint'] = now
        return now

    def _load(self, active=True):
        state = read(self.state_path)
        if state['closed']: raise RuntimeError('終了したサイクルです')
        if active and state['session'] is None: raise RuntimeError('実稼働セッションを開始してください')
        self._tick(state)
        return state

    def resume(self):
        with self.locked():
            state = self._load(False)
            if state['session'] is None:
                state['session'] = {'id': uuid.uuid4().hex, 'checkpoint': time.time()}
            self._check(state)
            self._write_state(state)
        return state['session']['id']

    def suspend(self):
        with self.locked():
            state = self._load()
            if any(j['status']=='running' for j in state['jobs'].values()):
                raise RuntimeError('実処理中のジョブが残っています')
            state['session'] = None
            self._write_state(state)
        return state['seconds']

    def _check(self, state, extra=0, campaign=None):
        if state['seconds'] >= state['limits']['seconds']-14400:
            raise RuntimeError('研究時間枠終了。残り4時間は終了処理用')
        if shutil.disk_usage(self.root).free < 20_000_000_000:
            raise RuntimeError('空き容量20GB未満')
        payload = state['payload_bytes']
        reserved = sum(j['reserve_bytes'] for j in state['jobs'].values() if j['status']=='running')
        overhead = sum(p.stat().st_size for p in self.control.glob('*') if p.is_file())
        if payload+reserved+extra+overhead+MARGIN > state['limits']['experiment_bytes']:
            raise RuntimeError('包括実験容量の上限')
        if state['write_bytes']+extra+MARGIN > state['limits']['write_bytes']:
            raise RuntimeError('累積書込予約の上限')
        if campaign:
            c = state['campaigns'][campaign]
            size = c['payload_bytes']
            pending = sum(j['reserve_bytes'] for j in state['jobs'].values()
                          if j['status']=='running' and j['campaign']==campaign)
            if size+pending+extra+MARGIN > c['limits']['bytes']: raise RuntimeError('campaign容量上限')
            if state['seconds']-c['start_seconds'] >= c['limits']['seconds']: raise RuntimeError('campaign時間上限')

    def start_campaign(self, name, prefix, limits, protocol_sha256):
        with self.locked():
            state = self._load()
            if name in state['campaigns']: raise FileExistsError('campaign再初期化禁止')
            if len(state['campaigns']) >= state['limits']['campaigns']: raise RuntimeError('campaign数上限')
            if not prefix.startswith('campaigns/') or '..' in Path(prefix).parts: raise ValueError('保存先が不正')
            self._check(state)
            state['campaigns'][name] = {'prefix': prefix, 'limits': limits, 'counts': {},
                'start_seconds': state['seconds'], 'protocol_sha256': protocol_sha256,
                'payload_bytes':0,'closed': False}
            self._write_state(state)

    def reserve(self, campaign, kind, label, count=1, reserve_bytes=0):
        with self.locked():
            state = self._load()
            c = state['campaigns'][campaign]
            if c['closed']: raise RuntimeError('終了campaignへの処理禁止')
            if kind not in c['limits'] or count < 1 or reserve_bytes < 0: raise ValueError('未登録処理/予約')
            if state['counts'].get(kind,0)+count > state['limits'].get(kind,10**9): raise RuntimeError('包括回数上限')
            if c['counts'].get(kind,0)+count > c['limits'][kind]: raise RuntimeError('campaign回数上限')
            running = [j for j in state['jobs'].values() if j['status']=='running']
            if len(running)>=2 or (kind in ('teacher','train') and any(j['kind'] in ('teacher','train') for j in running)):
                raise RuntimeError('同時ジョブ上限')
            self._check(state, reserve_bytes, campaign)
            job = uuid.uuid4().hex
            state['counts'][kind] = state['counts'].get(kind,0)+count
            c['counts'][kind] = c['counts'].get(kind,0)+count
            state['jobs'][job] = {'campaign': campaign, 'kind': kind, 'label': label,
                'count': count, 'reserve_bytes': reserve_bytes, 'status': 'running',
                'pid': os.getpid(), 'started_epoch': time.time()}
            self.event(state,{'event':'start','id':job,**state['jobs'][job]})
            self._write_state(state)
        return job

    def finish(self, job, error=None):
        with self.locked():
            state = self._load()
            j = state['jobs'][job]
            if j['status']!='running': raise RuntimeError('ジョブ二重終了')
            j.update(status='failed' if error else 'completed', error=error,
                     finished_epoch=time.time(), reserve_bytes=0)
            self.event(state,{'event':'finish','id':job,**j})
            del state['jobs'][job]
            self._write_state(state)

    @contextmanager
    def job(self, campaign, kind, label, count=1, reserve_bytes=0):
        token = self.reserve(campaign,kind,label,count,reserve_bytes)
        try: yield token
        except BaseException as exc:
            self.finish(token,repr(exc)); raise
        else: self.finish(token)

    def write(self, path, data, job=None):
        path = Path(path).resolve()
        if self.root not in path.parents or self.control in path.parents: raise ValueError('保存領域外')
        name = str(path.relative_to(self.root))
        with self.locked():
            state = self._load()
            if path.exists(): raise FileExistsError('成果の上書き禁止')
            campaign = next((n for n,c in state['campaigns'].items() if name.startswith(c['prefix']+'/')),None)
            if campaign and state['campaigns'][campaign]['closed']:raise RuntimeError('終了campaignの保存禁止')
            if job:
                j = state['jobs'][job]
                if j['status']!='running': raise RuntimeError('終了ジョブの書込')
                campaign = j['campaign']
                if not name.startswith(state['campaigns'][campaign]['prefix']+'/'): raise ValueError('別campaignの書込')
                if len(data)>j['reserve_bytes']: raise RuntimeError('予約を超える符号化済み出力')
                j['reserve_bytes'] -= len(data)
            self._check(state,len(data),campaign)
            if state['write_bytes']+len(data)+MARGIN > state['limits']['write_bytes']: raise RuntimeError('累積書込上限')
            # 保存前に容量を永続予約。障害時の未整合はreconcileで検出して停止する。
            self.set_file(state,name,[len(data),None])
            state['payload_bytes']+=len(data)
            if campaign:state['campaigns'][campaign]['payload_bytes']+=len(data)
            state['write_bytes'] += len(data)
            self._write_state(state)
            path.parent.mkdir(parents=True,exist_ok=True)
            with path.open('xb') as f: f.write(data); f.flush(); os.fsync(f.fileno())
            self.set_file(state,name,[path.stat().st_size,path.stat().st_mtime_ns])
            self._write_state(state)

    def save(self,path,value,job=None): self.write(path,encode(value),job)

    @contextmanager
    def external_output(self,path,maximum_bytes,job):
        path=Path(path).resolve()
        if self.root not in path.parents or self.control in path.parents: raise ValueError('保存領域外')
        name=str(path.relative_to(self.root))
        with self.locked():
            state=self._load();j=state['jobs'][job];campaign=j['campaign']
            if path.exists() or j['status']!='running': raise RuntimeError('外部出力の開始状態が不正')
            if not name.startswith(state['campaigns'][campaign]['prefix']+'/'): raise ValueError('別campaign')
            if maximum_bytes>j['reserve_bytes']: raise RuntimeError('外部出力予約不足')
            self._check(state,campaign=campaign)
            before=self.inventory()
            if before != self.registered(): raise RuntimeError('外部処理前の予約外変更')
            self.set_file(state,name,[maximum_bytes,None])
            state['payload_bytes']+=maximum_bytes;state['campaigns'][campaign]['payload_bytes']+=maximum_bytes
            j['reserve_bytes']-=maximum_bytes
            # 書込上限は最大量を先取りし、失敗途中の出力も計数する。
            state['write_bytes']+=maximum_bytes
            self._write_state(state)
        path.parent.mkdir(parents=True,exist_ok=True)
        try: yield
        finally:
            with self.locked():
                state=self._load();after=self.inventory()
                actual=after.pop(name,None)
                if after != before: raise RuntimeError('外部処理が別ファイルを変更')
                if actual:
                    self.set_file(state,name,actual)
                    state['payload_bytes']+=actual[0]-maximum_bytes
                    state['campaigns'][campaign]['payload_bytes']+=actual[0]-maximum_bytes
                    if actual[0]>maximum_bytes:
                        self._write_state(state)
                        raise RuntimeError('外部出力が予約量を超過')
                else:
                    self.set_file(state,name,None)
                    state['payload_bytes']-=maximum_bytes;state['campaigns'][campaign]['payload_bytes']-=maximum_bytes
                self._write_state(state)

    def close_campaign(self,name):
        with self.locked():
            state=self._load();c=state['campaigns'][name]
            if any(j['status']=='running' and j['campaign']==name for j in state['jobs'].values()):
                raise RuntimeError('未終了処理が残っています')
            c['closed']=True;c['end_seconds']=state['seconds']
            self._write_state(state)

    def reconcile(self):
        with self.locked():
            state=self._load()
            actual=self.inventory()
            if actual != self.registered(): raise RuntimeError('予約外の新規/変更/削除、または未完了保存を検出')
            if sum(v[0] for v in actual.values())!=state['payload_bytes']:raise RuntimeError('台帳容量の不整合')
            self._check(state)
            self._write_state(state)
        return {'files':len(actual),'bytes':sum(v[0] for v in actual.values()),
                'seconds':state['seconds'],'counts':state['counts'],'write_bytes':state['write_bytes']}

    def snapshot(self):
        with self.locked():
            state=self._load(False);self._write_state(state)
        return state
