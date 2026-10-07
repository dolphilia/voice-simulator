"""外部の自分のテスト領域で、成功・失敗・超過・回収を検査する。"""
import hashlib
import os
from pathlib import Path
import plistlib
from unittest.mock import patch
from paths import ROOT
from budget import Budget as BaseBudget, LIMITS, encode
from temporary_storage import ManagedStorageBudget


def tests(directory):
    root = directory / 'fixture-cycle'
    root.mkdir()
    mount = directory / 'fixture-volume'
    media = mount / 'voice-simulator-data'
    media.mkdir(parents=True)
    marker = encode(dict(test_only=True))
    (media / 'identity.json').write_bytes(marker)
    original = BaseBudget(root, {**LIMITS, 'bytes': 40_000_000, 'experiment_bytes': 30_000_000})
    original.initialize({'test': True})
    config = dict(mount=str(mount), data_root=str(media), volume_uuid='fixture',
        marker_sha256=hashlib.sha256(marker).hexdigest(), cycle_directory='fixture',
        amendment_id='fixture', internal_experiment_bytes=20_000_000,
        external_experiment_bytes=20_000_000, external_closing_bytes=1000)
    (original.control / 'storage-config.json').write_bytes(encode(config))
    with original.locked():
        state = original._load(False)
        state['storage_amendment'] = 'fixture'
        original._write_state(state)
    info = plistlib.dumps(dict(VolumeUUID='fixture', WritableVolume=True))
    with patch('storage_guard.subprocess.check_output', return_value=info), \
            patch('storage_guard.os.path.ismount', return_value=True):
        b = ManagedStorageBudget(root)
        b.resume()
        b.start_campaign('test', 'campaigns/test', dict(seconds=3600, bytes=10_000_000, audit=20), 'fixture')
        charged = b.snapshot()['write_bytes']
        with b.job('test', 'audit', '正常', reserve_bytes=1000) as job:
            with b.workspace(job, '正常', 64, 128) as (work, env):
                assert env['TMPDIR'] == env['TMP'] == env['TEMP'] == str(work)
                (work / 'own.txt').write_bytes(b'123')
            assert not work.exists()
        assert b.snapshot()['write_bytes'] > charged + 128
        try:
            with b.job('test', 'audit', '途中失敗', reserve_bytes=1000) as job:
                with b.workspace(job, '失敗', 64, 128) as (work, _):
                    (work / 'own.txt').write_bytes(b'123')
                    raise ValueError('人工途中失敗')
        except ValueError:
            assert not work.exists()
        try:
            with b.job('test', 'audit', '予約超過', reserve_bytes=1000) as job:
                with b.workspace(job, '超過', 64, 128) as (work, _):
                    (work / 'own.txt').write_bytes(b'x' * 65)
        except RuntimeError:
            assert not work.exists()
        else:
            raise AssertionError('超過を拒否する')
        # 媒体の一時的な不通で削除を保留し、同じ媒体の復旧後に再開回収する。
        try:
            with b.job('test', 'audit', '媒体不通', reserve_bytes=1000) as job:
                with b.workspace(job, '回収', 64, 128) as (work, _):
                    (work / 'own.txt').write_bytes(b'123')
                    check = b.guard.check
                    b.guard.check = lambda: (_ for _ in ()).throw(RuntimeError('人工媒体不通'))
        except RuntimeError:
            assert work.exists()
        b.guard.check = check
        before = b.snapshot()['write_bytes']
        b.recover()
        assert not work.exists() and b.snapshot()['write_bytes'] > before
        assert all(v['status'] == 'removed' for v in b.snapshot()['temporary_work'].values())
        b.reconcile()
        b.close_campaign('test')
        b.suspend()
    return dict(success_and_failure_cleaned=True, oversize_rejected_and_cleaned=True,
                detached_cleanup_pending_recovered=True, write_cost_not_refunded=True,
                env_realpath_checked=True, fixture_not_quality_evidence=True)


if __name__ == '__main__':
    import json
    import tempfile
    directory = Path(os.environ['TMPDIR']).resolve()
    assert Path(tempfile.gettempdir()).resolve() == directory
    print(json.dumps(tests(directory)))
