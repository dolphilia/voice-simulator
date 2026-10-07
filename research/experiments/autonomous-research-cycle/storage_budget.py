"""内蔵に資料・台帳、外部に今後の大容量データを保存する包括予算。"""
from contextlib import contextmanager
import hashlib
import os
from pathlib import Path
import shutil
from budget import Budget, ROOT, MARGIN, read
from storage_guard import VolumeGuard

DATA_SUFFIXES = {'.wav', '.flac', '.mp3', '.ogg', '.npz', '.npy',
                 '.zip', '.gz', '.tar', '.xz', '.zst'}
MODEL_SUFFIXES = {'.pt', '.pth', '.onnx', '.bin', '.safetensors'}

class StorageBudget(Budget):
    def __init__(self, root=ROOT):
        super().__init__(root)
        self.storage = read(self.control / 'storage-config.json')
        state = read(self.state_path)
        if state.get('storage_amendment') != self.storage['amendment_id']:
            raise RuntimeError('外部保存の予算追補が未適用')
        self.guard = VolumeGuard(self.storage)
        self.external = self.guard.root / self.storage['cycle_directory']
        with self.index() as con:
            con.execute('CREATE TABLE IF NOT EXISTS locations '
                        '(name TEXT PRIMARY KEY, physical TEXT UNIQUE, size INTEGER, '
                        'alias_size INTEGER, sha256 TEXT)')

    def locations(self):
        with self.index() as con:
            return {n: dict(physical=p, size=s, alias_size=a, sha256=h)
                    for n,p,s,a,h in con.execute('SELECT * FROM locations')}

    def locate(self, state, name, physical, size, alias_size, sha256=None):
        with self.index() as con:
            con.execute('INSERT OR REPLACE INTO locations VALUES (?,?,?,?,?)',
                        (name, physical, size, alias_size, sha256))
        state['write_bytes'] += 65536

    def inventory(self):
        self.guard.check()
        locations = self.locations()
        for name, row in locations.items():
            logical = self.root / name
            physical = self.guard.root / row['physical']
            if not logical.is_symlink() or os.readlink(logical) != str(physical):
                raise RuntimeError('外部データ参照の差替えまたは削除: '+name)
        actual = super().inventory()
        expected = {row['physical'] for row in locations.values()}
        if self.external.exists():
            for path in self.external.rglob('*'):
                if path.is_symlink():
                    raise RuntimeError('外部領域の未許可リンク')
                if path.is_file() and str(path.relative_to(self.guard.root)) not in expected:
                    raise RuntimeError('外部領域の予約外ファイル: '+str(path))
        return actual

    def _check(self, state, extra=0, campaign=None, tier='internal'):
        self.guard.check()
        super()._check(state, extra, campaign)
        rows = self.locations().values()
        external = sum(r['size'] for r in rows)
        aliases = sum(r['alias_size'] for r in rows)
        reserved = sum(j['reserve_bytes'] for j in state['jobs'].values()
                       if j['status']=='running')
        overhead = sum(p.stat().st_size for p in self.control.glob('*') if p.is_file())
        internal = state['payload_bytes'] - external + aliases + overhead
        if internal+reserved+(extra if tier=='internal' else 0)+MARGIN > self.storage['internal_experiment_bytes']:
            raise RuntimeError('内蔵保存容量の上限')
        pending = reserved+(extra if tier=='external' else 0)
        if external+pending+MARGIN > self.storage['external_experiment_bytes']:
            raise RuntimeError('外部保存容量の上限')
        if shutil.disk_usage(self.guard.mount).free < pending+self.storage['external_closing_bytes']+MARGIN:
            raise RuntimeError('外部メディアの空き容量不足')

    def logical(self, path):
        # resolveは既存のファイルリンクを追うため、論理パスの検査には使わない。
        path = Path(os.path.abspath(path))
        if self.root not in path.parents or self.control in path.parents:
            raise ValueError('保存領域外')
        if any(parent.is_symlink() for parent in path.parents if self.root in parent.parents):
            raise ValueError('保存先の親ディレクトリにリンクがあります')
        return path, str(path.relative_to(self.root))

    def routed(self, path, size):
        return path.suffix.lower() in DATA_SUFFIXES or (
            path.suffix.lower() in MODEL_SUFFIXES and size >= 1_000_000)

    def write(self, path, data, job=None):
        logical, name = self.logical(path)
        if not self.routed(logical, len(data)):
            self.guard.check()
            return super().write(logical, data, job)
        return self.write_data(logical, data, job)

    def prepare(self, state, path, name, maximum, job):
        if os.path.lexists(path): raise FileExistsError('成果の上書き禁止')
        campaign = next((n for n,c in state['campaigns'].items()
                         if name.startswith(c['prefix']+'/')), None)
        if campaign and state['campaigns'][campaign]['closed']:
            raise RuntimeError('終了campaignの保存禁止')
        if job:
            j = state['jobs'][job]
            if j['status']!='running': raise RuntimeError('終了ジョブの書込')
            campaign = j['campaign']
            if not name.startswith(state['campaigns'][campaign]['prefix']+'/'):
                raise ValueError('別campaignの書込')
            if maximum > j['reserve_bytes']: raise RuntimeError('予約を超える符号化済み出力')
            j['reserve_bytes'] -= maximum
        self._check(state, maximum, campaign, tier='external')
        physical = str(Path(self.storage['cycle_directory']) / name)
        target = self.guard.root / physical
        if os.path.lexists(target): raise FileExistsError('外部成果の上書き禁止')
        self.locate(state, name, physical, maximum, len(os.fsencode(str(target))))
        self.set_file(state, name, [maximum, None])
        state['payload_bytes'] += maximum
        if campaign: state['campaigns'][campaign]['payload_bytes'] += maximum
        state['write_bytes'] += maximum
        self._write_state(state)
        return campaign, physical, target

    def write_data(self, path, data, job=None):
        path, name = self.logical(path)
        with self.locked():
            state = self._load()
            campaign, physical, target = self.prepare(state, path, name, len(data), job)
            h = self.guard.write(physical, data)
            self.guard.check()
            path.parent.mkdir(parents=True, exist_ok=True)
            os.symlink(str(target), path)
            self.locate(state, name, physical, len(data), len(os.fsencode(str(target))), h)
            self.set_file(state, name, [path.stat().st_size, path.stat().st_mtime_ns])
            self._write_state(state)

    @contextmanager
    def external_output(self, path, maximum_bytes, job):
        path, name = self.logical(path)
        if not self.routed(path, maximum_bytes):
            with super().external_output(path, maximum_bytes, job):
                yield
            return
        if maximum_bytes <= 0: raise ValueError('外部出力の予約量が不正')
        with self.locked():
            state = self._load()
            before = self.inventory()
            if before != self.registered(): raise RuntimeError('外部処理前の予約外変更')
            campaign, physical, target = self.prepare(state, path, name, maximum_bytes, job)
            with self.guard.parent_fd(physical): pass
            path.parent.mkdir(parents=True, exist_ok=True)
            os.symlink(str(target), path)
        try:
            yield
        finally:
            with self.locked():
                state = self._load()
                after = self.inventory()
                actual = after.pop(name, None)
                if after != before: raise RuntimeError('外部処理が別ファイルを変更')
                size = actual[0] if actual else 0
                self.set_file(state, name, actual)
                state['payload_bytes'] += size-maximum_bytes
                state['campaigns'][campaign]['payload_bytes'] += size-maximum_bytes
                if actual:
                    h = hashlib.sha256(target.read_bytes()).hexdigest()
                    self.locate(state, name, physical, size, len(os.fsencode(str(target))), h)
                else:
                    path.unlink()
                    with self.index() as con:
                        con.execute('DELETE FROM locations WHERE name=?', (name,))
                    state['write_bytes'] += 65536
                if size > maximum_bytes:
                    state['write_bytes'] += size-maximum_bytes
                    self._write_state(state)
                    raise RuntimeError('外部出力が予約量を超過')
                self._write_state(state)

    def audit_data_hashes(self):
        self.guard.check()
        count = 0
        for name, row in self.locations().items():
            path = self.guard.root / row['physical']
            if row['sha256'] is None or hashlib.sha256(path.read_bytes()).hexdigest() != row['sha256']:
                raise RuntimeError('外部データのhash不一致: '+name)
            count += 1
        return count
