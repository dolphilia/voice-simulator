"""大容量計測の実体を作業用ディスクに置き、元の実験パスで公開する。"""

import os
from hashlib import file_digest
from pathlib import Path
import plistlib
import re
import shutil
import struct
import subprocess
import sys
from tempfile import NamedTemporaryFile
from uuid import UUID


WORK_DISK = Path('/Volumes/RTL9210B-CG')
WORK_UUID = '3D26C0E2-12EF-4613-A693-E21C0D51D2E7'
WORK_RUNS = WORK_DISK / 'voice-simulator/scratch/chimera-runs'
ARCHIVE_DISK = Path('/Volumes/CT2000X8')
ARCHIVE_UUID = '9B51F3F1-8509-4272-B72B-ABA311912659'


def _darwin_mount_matches(mount, expected_uuid):
    from ctypes import CDLL, byref, c_size_t, c_ulong, create_string_buffer

    # macOS の sys/attr.h にある ATTR_VOL_INFO と ATTR_VOL_UUID を指定する。
    attrs = create_string_buffer(struct.pack('=HHIIIII', 5, 0, 0, 0x80040000, 0, 0, 0))
    reply = create_string_buffer(20)
    if CDLL(None).getattrlist(os.fsencode(mount), byref(attrs), byref(reply), c_size_t(len(reply)), c_ulong(0)):
        return False
    size, uuid_bytes = struct.unpack('=I16s', reply.raw)
    return (size == len(reply) and str(UUID(bytes=uuid_bytes)).upper() == expected_uuid
            and mount.resolve() == mount and not os.statvfs(mount).f_flag & os.ST_RDONLY)


def mounted_volume(mount, expected_uuid):
    try:
        try:
            info = plistlib.loads(subprocess.check_output(
                ['/usr/sbin/diskutil', 'info', '-plist', str(mount)], stderr=subprocess.DEVNULL, timeout=10))
            matches = (info.get('MountPoint') == str(mount) and info.get('VolumeUUID', '').upper() == expected_uuid
                       and info.get('WritableVolume'))
        except subprocess.TimeoutExpired:
            matches = sys.platform == 'darwin' and _darwin_mount_matches(mount, expected_uuid)
    except (OSError, subprocess.CalledProcessError, plistlib.InvalidFileException) as error:
        raise ValueError(f'指定した外部ディスクを確認できません ({mount})') from error
    if not matches or not os.path.ismount(mount):
        raise ValueError(f'外部ディスクのマウント先、UUID、書き込み可否を確認してください ({mount})')
    return mount.stat().st_dev


class RunStorage:
    def __init__(self, runs, run_id):
        if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]*', run_id):
            raise ValueError(f'実行 ID の形式が不正です ({run_id})')
        self.run = runs / run_id
        self.logical = self.run / 'artifacts'
        self.artifacts = self.logical
        self.device = None
        self.metadata = None
        mode = os.environ.get('CHIMERA_RUN_STORAGE', '')
        if mode not in ('', 'rtl9210b'):
            raise ValueError('CHIMERA_RUN_STORAGE は未設定または rtl9210b を指定してください')
        if mode:
            self.device = mounted_volume(WORK_DISK, WORK_UUID)
            if (not WORK_RUNS.is_dir() or WORK_RUNS.resolve() != WORK_RUNS
                    or WORK_RUNS.stat().st_dev != self.device):
                raise ValueError(f'外部ディスクの計測領域を利用できません ({WORK_RUNS})')
            expected = os.environ.get('CHIMERA_RUN_BYTES', '')
            if not re.fullmatch(r'[1-9][0-9]*', expected):
                raise ValueError('CHIMERA_RUN_BYTES に一時出力を含む最大見積もり（バイト）を指定してください')
            if shutil.disk_usage(WORK_RUNS).free < int(expected):
                raise ValueError(f'外部ディスクの空き容量が計測の見積もりを下回っています ({WORK_RUNS})')
            external_run = WORK_RUNS / run_id
            self.artifacts = external_run / 'artifacts'
            self.metadata = {'volume_uuid': WORK_UUID, 'artifacts_root': str(self.artifacts),
                             'estimated_peak_bytes': int(expected)}

    def create(self):
        self.run.mkdir(parents=True, exist_ok=False)
        if self.device is not None:
            self.assert_connected(WORK_RUNS)
            self.artifacts.parent.mkdir(exist_ok=False)
            self.artifacts.mkdir()
            (self.artifacts.parent / 'tmp').mkdir()
        self.logical.mkdir()

    def assert_connected(self, directory):
        if self.device is not None and (not directory.is_dir() or directory.stat().st_dev != self.device):
            raise OSError(f'外部ディスクの計測領域を利用できなくなりました ({directory})')

    def subprocess_env(self):
        self.assert_connected(self.artifacts)
        if self.device is not None:
            return {**os.environ, 'TMPDIR': str(self.artifacts.parent / 'tmp')}
        return None

    def snapshot_source(self, source, destination, digest):
        # 作業中の入力とは別の実体を作り、同じ内容の保存済み入力だけを共有する。
        objects = self.run.parent / '.source-objects' / digest[:2]
        objects.mkdir(parents=True, exist_ok=True)
        stored = objects / digest
        if not stored.exists():
            with NamedTemporaryFile(dir=objects, prefix='.snapshot-') as staged:
                with source.open('rb') as original:
                    shutil.copyfileobj(original, staged)
                staged.flush()
                staged.seek(0)
                if file_digest(staged, 'sha256').hexdigest() != digest:
                    raise ValueError(f'実行元の保存中に変更されました ({destination})')
                os.fchmod(staged.fileno(), 0o444)
                os.fsync(staged.fileno())
                try:
                    os.link(staged.name, stored)
                except FileExistsError:
                    pass
        if stored.is_symlink():
            raise ValueError(f'共有するソースの保存先がリンクです ({stored})')
        with stored.open('rb') as saved:
            if file_digest(saved, 'sha256').hexdigest() != digest:
                raise ValueError(f'共有するソースのSHA-256が一致しません ({stored})')
        destination.parent.mkdir(parents=True, exist_ok=True)
        os.link(stored, destination, follow_symlinks=False)

    def publish(self):
        if self.device is None:
            return
        self.assert_connected(self.artifacts)
        for physical in sorted(self.artifacts.rglob('*')):
            if physical.is_file():
                logical = self.logical / physical.relative_to(self.artifacts)
                logical.parent.mkdir(parents=True, exist_ok=True)
                logical.symlink_to(physical)
        self.assert_connected(self.artifacts)
