"""明示承認された外部保存予算を一度だけ追加し、既存消費を保持する。"""
import hashlib
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import time
import uuid
from budget import Budget, ROOT, REPO, encode, read, digest
from storage_guard import VolumeGuard

MOUNT=Path('/Volumes/CCCOMA_X64FRE_JA-JP_DV9')
VOLUME='B7863180-5738-36A9-BAEF-7CB3008381B3'
APPROVED=246776643584
AMENDMENT='external-storage-20261006-v1'

def main():
    b=Budget()
    info=plistlib.loads(subprocess.check_output(['/usr/sbin/diskutil','info','-plist',str(MOUNT)]))
    assert info['VolumeUUID']==VOLUME and info['WritableVolume'] and os.path.ismount(MOUNT)
    free=shutil.disk_usage(MOUNT).free
    if free!=APPROVED:raise RuntimeError('初期容量が追補の実測値と違います。自動拡張しません')
    media=MOUNT/'voice-simulator-data'
    if media.exists():raise FileExistsError('既存の外部専用領域を上書きしません')
    marker=encode(dict(project='voice-simulator',volume_uuid=VOLUME,
                       namespace_token=uuid.uuid4().hex,created_epoch=time.time()))
    config=dict(version=1,amendment_id=AMENDMENT,mount=str(MOUNT),data_root=str(media),
                volume_uuid=VOLUME,marker_sha256=hashlib.sha256(marker).hexdigest(),
                cycle_directory='arc-20261004-v1',approved_external_bytes=APPROVED,
                internal_bytes=20000000000,internal_experiment_bytes=18000000000,
                external_closing_bytes=2000000000,external_experiment_bytes=APPROVED-2000000000)
    with b.locked():
        state=b._load()
        if state.get('storage_amendment'):raise FileExistsError('外部予算の重複加算禁止')
        if state['jobs']:raise RuntimeError('処理中の予算切替は禁止')
        b._check(state)
        before=dict(counts=dict(state['counts']),seconds=state['seconds'],
                    write_bytes=state['write_bytes'],payload_bytes=state['payload_bytes'],
                    limits=dict(state['limits']))
        # 専用領域の識別情報と一時検査の書込を処理前に計数する。
        state['write_bytes']+=32*1024*1024+len(marker)
        b.event(state,dict(event='storage_activation_preflight',amendment_id=AMENDMENT,
                          transient_probe_bytes=16*1024*1024,charged_write_bytes=32*1024*1024,
                          user_authorization='外部メディアの空き容量はすべて予算として使って構いません。'))
        b._write_state(state)
    media.mkdir()
    with (media/'identity.json').open('xb') as f:f.write(marker);f.flush();os.fsync(f.fileno())
    guard=VolumeGuard(config)
    data=os.urandom(16*1024*1024)
    started=time.monotonic()
    h=guard.write('.storage-probe.bin',data)
    write_verify_seconds=time.monotonic()-started
    started=time.monotonic()
    assert hashlib.sha256((media/'.storage-probe.bin').read_bytes()).hexdigest()==h
    read_seconds=time.monotonic()-started
    guard.check()
    (media/'.storage-probe.bin').unlink()
    probe=dict(bytes=len(data),sha256=h,write_fsync_and_first_readback_seconds=write_verify_seconds,
               second_read_seconds=read_seconds,read_may_be_OS_cached=True,removed_transient_probe=True)
    plans=[REPO/'docs/plans'/n for n in
           ['autonomous-research-external-storage-amendment-2026-10-06.md',
            'autonomous-research-execution-prompt-2026-10-06.md']]
    source_names=['budget.py','storage_guard.py','storage_budget.py','activate_external_storage.py',
                  'test_storage_budget.py']
    report=dict(amendment_id=AMENDMENT,observed_epoch=time.time(),volume_uuid=VOLUME,
                filesystem=info['FilesystemName'],bus=info['BusProtocol'],initial_free_bytes=free,
                data_root=str(media),old_budget_before=before,
                plans={str(p.relative_to(REPO)):digest(p) for p in plans},
                sources={n:digest(ROOT/n) for n in source_names},probe=probe,
                time_count_campaign_limits_preserved=True,old_sealed_data_not_moved=True,
                quality_certified=False)
    b.save(ROOT/'external-storage-activation-0001.json',report)
    with b.locked():
        state=b._load()
        assert state['counts']==before['counts']
        assert state['limits']==before['limits']
        assert not state['jobs'] and not state.get('storage_amendment')
        config_data=encode(config)
        with (b.control/'storage-config.json').open('xb') as f:
            f.write(config_data);f.flush();os.fsync(f.fileno())
        state['write_bytes']+=len(config_data)
        state['limits']['bytes']+=APPROVED
        state['limits']['experiment_bytes']+=APPROVED-2000000000
        state['limits']['write_bytes']+=APPROVED
        state['storage_amendment']=AMENDMENT
        state['authorization_amendments']=[dict(id=AMENDMENT,plans=report['plans'],
             explicit_user_approval='今後は推奨の分担で進める。外部メディアの空き容量はすべて予算として使って構いません。計画書も適切に調整してください。',
             volume_uuid=VOLUME,external_bytes=APPROVED,original_limits=before['limits'])]
        b.event(state,dict(event='storage_budget_amended',id=AMENDMENT,
                          limits=state['limits'],counts_unchanged=state['counts']))
        b._write_state(state)
    from storage_budget import StorageBudget
    external=StorageBudget()
    print(json.dumps(dict(reconcile=external.reconcile(),probe=probe,config=config),ensure_ascii=False))

if __name__=='__main__':main()
