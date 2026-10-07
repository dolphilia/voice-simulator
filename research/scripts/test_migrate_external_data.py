"""外部移動の失敗時に元データと既存移動先が保護されることを確認する。"""
from contextlib import contextmanager
import os
from pathlib import Path
import stat
import tempfile
import unittest

import migrate_external_data as migration


class TemporaryGuard:
    def __init__(self, root):
        self.root = root

    def check(self):
        pass

    @contextmanager
    def parent_fd(self, relative):
        target = self.root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            yield fd, target.name
        finally:
            os.close(fd)


class MigrationSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.guard = TemporaryGuard(self.root / 'external')
        self.source = self.root / 'source.wav'
        self.content = bytes(range(256)) * 4096
        self.source.write_bytes(self.content)
        source_stat = self.source.stat()
        self.row = dict(size=source_stat.st_size, mtime=source_stat.st_mtime_ns,
                        device=source_stat.st_dev, inode=source_stat.st_ino,
                        mode=stat.S_IMODE(source_stat.st_mode), physical='data/source.wav')
        self.target = self.guard.root / self.row['physical']

    def test_verified_copy_keeps_content_and_original_path(self):
        sha, _ = migration.copy_verified(self.source, self.row, self.guard)
        self.assertFalse(self.source.is_symlink())
        migration.replace_with_link(self.source, self.target, self.row, sha)
        self.assertTrue(self.source.is_symlink())
        self.assertEqual(self.source.read_bytes(), self.content)

    def test_existing_destination_is_not_overwritten(self):
        self.target.parent.mkdir(parents=True)
        self.target.write_bytes(b'existing')
        with self.assertRaises(FileExistsError):
            migration.copy_verified(self.source, self.row, self.guard)
        self.assertEqual(self.target.read_bytes(), b'existing')
        self.assertEqual(self.source.read_bytes(), self.content)

    def test_corrupt_destination_keeps_original(self):
        sha, _ = migration.copy_verified(self.source, self.row, self.guard)
        self.target.write_bytes(b'corrupted')
        with self.assertRaises(RuntimeError):
            migration.replace_with_link(self.source, self.target, self.row, sha)
        self.assertFalse(self.source.is_symlink())
        self.assertEqual(self.source.read_bytes(), self.content)

    def test_changed_source_is_rejected(self):
        self.source.write_bytes(b'changed')
        with self.assertRaises(RuntimeError):
            migration.copy_verified(self.source, self.row, self.guard)
        self.assertEqual(self.source.read_bytes(), b'changed')
        self.assertFalse(self.target.exists())

    def test_existing_symlink_is_rejected(self):
        alias = self.root / 'alias.wav'
        alias.symlink_to(self.source)
        with self.assertRaises(RuntimeError):
            migration.copy_verified(alias, self.row, self.guard)
        self.assertEqual(self.source.read_bytes(), self.content)

    def test_readonly_owned_directory_permissions_are_restored(self):
        sha, _ = migration.copy_verified(self.source, self.row, self.guard)
        self.root.chmod(0o555)
        self.addCleanup(self.root.chmod, 0o755)
        migration.replace_with_link(self.source, self.target, self.row, sha)
        self.assertEqual(stat.S_IMODE(self.root.stat().st_mode), 0o555)
        self.assertEqual(self.source.read_bytes(), self.content)

    def test_permissions_are_restored_after_replacement_error(self):
        sha, _ = migration.copy_verified(self.source, self.row, self.guard)
        temporary = self.source.with_name('.' + self.source.name + '.external-migration-link')
        temporary.write_bytes(b'existing')
        self.root.chmod(0o555)
        self.addCleanup(self.root.chmod, 0o755)
        with self.assertRaises(FileExistsError):
            migration.replace_with_link(self.source, self.target, self.row, sha)
        self.assertEqual(stat.S_IMODE(self.root.stat().st_mode), 0o555)
        self.assertEqual(self.source.read_bytes(), self.content)
        self.assertEqual(temporary.read_bytes(), b'existing')


if __name__ == '__main__':
    unittest.main()
