"""外部メディアの同一性確認と、ディレクトリFDを使う保存。"""
import json
import os
from pathlib import Path
import plistlib
import subprocess
from contextlib import contextmanager
import hashlib

class VolumeGuard:
    def __init__(self, config):
        self.config = config
        self.mount = Path(config['mount'])
        self.root = Path(config['data_root'])
        if self.root.parent != self.mount or self.root.name != 'voice-simulator-data':
            raise ValueError('専用の保存領域ではありません')
        info = plistlib.loads(subprocess.check_output(
            ['/usr/sbin/diskutil', 'info', '-plist', str(self.mount)]))
        if info.get('VolumeUUID') != config['volume_uuid'] or not info.get('WritableVolume'):
            raise RuntimeError('外部メディアの識別子または書込属性が不一致')
        self.device = self.mount.stat().st_dev
        self.check()

    def check(self):
        if not os.path.ismount(self.mount) or self.mount.stat().st_dev != self.device:
            raise RuntimeError('外部メディアが未接続または別メディアです')
        if os.statvfs(self.mount).f_flag & os.ST_RDONLY:
            raise RuntimeError('外部メディアが読取専用です')
        marker = self.root / 'identity.json'
        if self.root.is_symlink() or marker.is_symlink():
            raise RuntimeError('外部保存領域のリンク差替え')
        if hashlib.sha256(marker.read_bytes()).hexdigest() != self.config['marker_sha256']:
            raise RuntimeError('外部保存領域の識別情報が不一致')
        if self.root.stat().st_dev != self.device:
            raise RuntimeError('保存領域が別のデバイスです')

    @contextmanager
    def parent_fd(self, relative):
        self.check()
        parts = Path(relative).parts
        if not parts or any(p in ('..', '.', '/') for p in parts) or Path(relative).is_absolute():
            raise ValueError('外部保存先が不正')
        fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            for part in parts[:-1]:
                try: os.mkdir(part, dir_fd=fd)
                except FileExistsError: pass
                next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                os.close(fd)
                fd = next_fd
                if os.fstat(fd).st_dev != self.device:
                    raise RuntimeError('保存途中のデバイス変更')
            self.check()
            yield fd, parts[-1]
        finally:
            os.close(fd)

    def write(self, relative, data):
        with self.parent_fd(relative) as (fd, name):
            out = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                          0o600, dir_fd=fd)
            with os.fdopen(out, 'wb') as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            os.fsync(fd)
        self.check()
        path = self.root / relative
        expected = hashlib.sha256(data).hexdigest()
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise RuntimeError('外部保存後のhash不一致')
        return expected
