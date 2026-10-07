"""外部の専用一時領域を共有予約・所有記録・不要時削除につなぐ。"""
from contextlib import contextmanager
import os
from pathlib import Path
import uuid
from storage_budget import StorageBudget


class ManagedStorageBudget(StorageBudget):
    def _check(self, state, extra=0, campaign=None, tier='internal'):
        pending = sum(w['maximum_bytes'] for w in state.get('temporary_work', {}).values()
                      if w['status'] != 'removed')
        super()._check(state, extra + pending, campaign, tier)

    def _owned(self, value):
        self.guard.check()
        base = self.guard.root / 'work' / self.storage['cycle_directory']
        path = Path(value['path'])
        if path.parent != base or path.name != value['owner'] or path.is_symlink():
            raise RuntimeError('一時領域の所有・実パスが不一致')
        if path.exists() and path.stat().st_dev != self.guard.device:
            raise RuntimeError('一時領域が別媒体')
        return path

    def cleanup(self, owner):
        with self.locked():
            state = self._load()
            value = state['temporary_work'][owner]
            if value['status'] == 'removed':
                return
            value['status'] = 'cleanup_pending'
            self.event(state, dict(kind='temporary-cleanup-start', owner=owner))
            self._write_state(state)
        path = self._owned(value)
        files, directories = [], []
        if path.exists():
            for current, dirs, names in os.walk(path, followlinks=False):
                for name in dirs:
                    item = Path(current) / name
                    if item.is_symlink():
                        raise RuntimeError('未許可の一時ディレクトリリンク。削除を保留')
                    directories.append(item)
                for name in names:
                    item = Path(current) / name
                    if item.is_symlink() or not item.is_file():
                        raise RuntimeError('未許可の一時ファイル種別。削除を保留')
                    stat = item.stat()
                    files.append(dict(relative=str(item.relative_to(path)), bytes=stat.st_size,
                                      inode=stat.st_ino, device=stat.st_dev))
        actual = sum(v['bytes'] for v in files)
        over = actual > value['maximum_bytes']
        # 自分の排他的領域で作られた実ファイルだけを、削除前にmanifestへ登録する。
        with self.locked():
            state = self._load()
            state['temporary_work'][owner].update(files=files, observed_bytes=actual,
                                                 peak_violation=over)
            state['write_bytes'] += max(0, actual - value['maximum_write_bytes'])
            self.event(state, dict(kind='temporary-owned-files', owner=owner, files=files,
                                  observed_bytes=actual, peak_violation=over))
            self._write_state(state)
        for item in files:
            self.guard.check()
            target = path / item['relative']
            stat = target.lstat()
            if target.is_symlink() or (stat.st_ino, stat.st_dev, stat.st_size) != (
                    item['inode'], item['device'], item['bytes']):
                raise RuntimeError('一時ファイルが削除前に変化。削除を保留')
            target.unlink()
        for directory in sorted(directories, key=lambda p: len(p.parts), reverse=True):
            directory.rmdir()
        if path.exists():
            path.rmdir()
        assert not os.path.lexists(path)
        with self.locked():
            state = self._load()
            state['temporary_work'][owner].update(status='removed', removed_files=len(files),
                                                 remaining_bytes=0, absence_verified=True)
            self.event(state, dict(kind='temporary-cleanup-complete', owner=owner,
                                  files=len(files), bytes=actual, absence_verified=True,
                                  consumed_write_bytes_not_refunded=True))
            self._write_state(state)
        if over:
            raise RuntimeError('一時領域の予約超過。違反を保持し自分の不要物は削除済み')

    def recover(self):
        state = self.snapshot()
        for owner, value in state.get('temporary_work', {}).items():
            if value['status'] != 'removed':
                if value['job'] in state['jobs']:
                    raise RuntimeError('一時領域を使用するジョブが未終了。新規作業を停止')
                self.cleanup(owner)

    @contextmanager
    def workspace(self, job, purpose, maximum_bytes=8_000_000,
                  maximum_write_bytes=16_000_000):
        if maximum_bytes <= 0 or maximum_write_bytes < maximum_bytes:
            raise ValueError('一時容量と累積書込予約が不正')
        self.guard.check()
        owner = 'voicing-ap-' + uuid.uuid4().hex
        path = self.guard.root / 'work' / self.storage['cycle_directory'] / owner
        with self.locked():
            state = self._load()
            if any(v['status'] != 'removed' for v in state.get('temporary_work', {}).values()):
                raise RuntimeError('先行一時領域を照合・回収してから新規作業を開始')
            record = state['jobs'][job]
            if maximum_bytes > record['reserve_bytes']:
                raise RuntimeError('一時領域の事前予約不足')
            record['reserve_bytes'] -= maximum_bytes
            self._check(state, maximum_bytes, record['campaign'], tier='external')
            state['write_bytes'] += maximum_write_bytes
            state.setdefault('temporary_work', {})[owner] = dict(
                owner=owner, job=job, campaign=record['campaign'], path=str(path), purpose=purpose,
                maximum_bytes=maximum_bytes, maximum_write_bytes=maximum_write_bytes,
                status='reserved', creation_scope='排他的な所有ディレクトリ以下の通常ファイル',
                delete_when='子の終了・wait、全ハンドルclose後。成功・失敗とも不要時に削除。')
            self.event(state, dict(kind='temporary-reserved', **state['temporary_work'][owner]))
            self._write_state(state)
        try:
            with self.guard.parent_fd(str((path / 'owner-placeholder').relative_to(self.guard.root))):
                pass
            self._owned(dict(path=str(path), owner=owner))
            env = dict(os.environ)
            env.update({key: str(path) for key in (
                'TMPDIR', 'TMP', 'TEMP', 'XDG_CACHE_HOME', 'HF_HOME', 'MPLCONFIGDIR',
                'NUMBA_CACHE_DIR', 'TORCH_HOME')})
            env.update(PYTHONDONTWRITEBYTECODE='1', HF_HUB_OFFLINE='1',
                       TRANSFORMERS_OFFLINE='1', TOKENIZERS_PARALLELISM='false')
            yield path, env
        finally:
            self.cleanup(owner)

    def reconcile(self):
        state = self.snapshot()
        for value in state.get('temporary_work', {}).values():
            if value['status'] != 'removed':
                raise RuntimeError('一時領域が未回収。照合を完了できない')
            if os.path.lexists(value['path']):
                raise RuntimeError('削除済み一時領域が再出現')
        return super().reconcile()
