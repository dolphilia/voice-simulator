"""外部保存の容量・同一性・監査拒否経路を一時領域で検査する。"""
import hashlib
import json
import os
from pathlib import Path
import plistlib
import tempfile
from unittest.mock import patch
from budget import Budget, LIMITS, encode, read
from storage_budget import StorageBudget

def refused(action, error=RuntimeError):
    try: action()
    except error: return
    raise AssertionError('拒否すべき操作が通りました')

def tests():
    with tempfile.TemporaryDirectory(prefix='arc-storage-', dir='/private/tmp') as directory:
        root = Path(directory)/'cycle'
        root.mkdir()
        mount = Path(directory)/'volume'
        media = mount/'voice-simulator-data'
        media.mkdir(parents=True)
        marker = encode(dict(project='voice-simulator', volume_uuid='fixture'))
        (media/'identity.json').write_bytes(marker)
        limits = {**LIMITS, 'bytes': 6_000_000, 'experiment_bytes': 5_000_000}
        original = Budget(root, limits)
        original.initialize({'fixture': True})
        original.resume()
        config = dict(mount=str(mount), data_root=str(media), volume_uuid='fixture',
                      marker_sha256=hashlib.sha256(marker).hexdigest(),
                      cycle_directory='fixture-cycle', amendment_id='fixture',
                      internal_experiment_bytes=2_000_000,
                      external_experiment_bytes=3_000_000, external_closing_bytes=1000)
        (original.control/'storage-config.json').write_bytes(encode(config))
        with original.locked():
            state=original._load()
            state['storage_amendment']='fixture'
            original._write_state(state)
        info = plistlib.dumps(dict(VolumeUUID='fixture', WritableVolume=True))
        with patch('storage_guard.subprocess.check_output', return_value=info), \
             patch('storage_guard.os.path.ismount', return_value=True) as mounted:
            b=StorageBudget(root)
            b.start_campaign('a','campaigns/a',
                             {'seconds':3600,'bytes':3_000_000,'render':30,'audit':30}, 'fixture')
            wav=root/'campaigns/a/audio.wav'
            with b.job('a','render','外部保存',reserve_bytes=1000) as job:
                b.write(wav,b'abcdef',job)
                b.save(root/'campaigns/a/meta.json',{'kept_internal':True},job)
            assert wav.is_symlink() and wav.read_bytes()==b'abcdef'
            assert not (root/'campaigns/a/meta.json').is_symlink()
            assert b.reconcile()['bytes']==6+len(encode({'kept_internal':True}))
            assert b.audit_data_hashes()==1
            assert StorageBudget(root).snapshot()['counts']['render']==1
            refused(lambda:b.write(wav,b'replace'),FileExistsError)
            before=b.snapshot()['counts']['render']
            try:
                with b.job('a','render','失敗を含む',reserve_bytes=2) as job:
                    b.write(root/'campaigns/a/oversize.wav',b'abc',job)
            except RuntimeError:pass
            else:raise AssertionError('符号化済み出力超過')
            assert b.snapshot()['counts']['render']==before+1
            assert not os.path.lexists(root/'campaigns/a/oversize.wav')
            mounted.return_value=False
            refused(lambda:b.write(root/'campaigns/a/detached.wav',b'x'))
            assert not os.path.lexists(root/'campaigns/a/detached.wav')
            mounted.return_value=True
            with patch('storage_guard.subprocess.check_output',
                       return_value=plistlib.dumps(dict(VolumeUUID='other',WritableVolume=True))):
                refused(lambda:StorageBudget(root))
            with patch('storage_guard.os.statvfs',return_value=type('Flags',(),{'f_flag':os.ST_RDONLY})()):
                refused(lambda:b.write(root/'campaigns/a/readonly.wav',b'x'))
            marker_path=media/'identity.json'
            marker_path.write_bytes(b'wrong')
            refused(lambda:b.reconcile())
            marker_path.write_bytes(marker)
            unknown=b.external/'unknown.wav'
            unknown.write_bytes(b'x')
            refused(lambda:b.reconcile())
            unknown.unlink()
            physical=Path(os.readlink(wav))
            stat=physical.stat()
            physical.write_bytes(b'ghijkl')
            os.utime(physical,ns=(stat.st_atime_ns,stat.st_mtime_ns))
            refused(lambda:b.audit_data_hashes())
            physical.write_bytes(b'abcdef')
            os.utime(physical,ns=(stat.st_atime_ns,stat.st_mtime_ns))
            wave_target=os.readlink(wav)
            wav.unlink();wav.symlink_to(physical.parent/'other')
            refused(lambda:b.reconcile())
            wav.unlink();wav.symlink_to(wave_target)
            with b.job('a','audit','外部子処理',reserve_bytes=20) as job:
                with b.external_output(root/'campaigns/a/batch.zip',10,job):
                    (root/'campaigns/a/batch.zip').write_bytes(b'123')
            b.reconcile()
            with b.job('a','audit','出力なし',reserve_bytes=20) as job:
                with b.external_output(root/'campaigns/a/empty.zip',10,job):pass
            assert not os.path.lexists(root/'campaigns/a/empty.zip')
            before=b.snapshot()['write_bytes']
            try:
                with b.job('a','audit','子処理の容量超過',reserve_bytes=20) as job:
                    with b.external_output(root/'campaigns/a/large.zip',2,job):
                        (root/'campaigns/a/large.zip').write_bytes(b'123')
            except RuntimeError:pass
            else:raise AssertionError('子処理の超過')
            assert b.snapshot()['write_bytes']>before and not b.snapshot()['jobs']
            b.reconcile()
            refused(lambda:b.reserve('a','audit','個別容量超過',reserve_bytes=3_000_000))
            # 並行した管理インスタンスでも同じ台帳の予約を読む。
            second=StorageBudget(root)
            with b.job('a','audit','共有予約',reserve_bytes=1_500_000):
                refused(lambda:second.reserve('a','audit','重複容量',reserve_bytes=1_500_000))
            # 予約なしの大容量直接保存も内部容量へ転嫁しない。
            b.write_data(root/'campaigns/a/direct.npy',b'x'*1_800_000)
            b.reconcile()
            b.close_campaign('a')
            refused(lambda:b.write(root/'campaigns/a/closed.wav',b'x'))
            b.suspend()
    return dict(external_data_internal_metadata=True, counters_preserved=True,
                detached_wrong_uuid_readonly_marker_rejected=True,
                external_unknown_files_and_hash_tampering_rejected=True,
                alias_replacement_rejected=True, encoded_and_child_output_caps=True,
                shared_reservations=True, failed_attempts_charged=True,
                large_external_write_not_charged_to_internal_payload=True,
                closed_campaign_and_overwrite_rejected=True, quality_evidence=False)

if __name__=='__main__':print(json.dumps(tests(),ensure_ascii=False))
