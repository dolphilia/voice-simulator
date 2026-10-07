"""再開時に検出したOSメタデータを削除せず、個別hash付きで台帳へ取り込む。"""
import sys, os, hashlib, json
from pathlib import Path
sys.path.insert(0, '/Users/dolphilia/github/voice-simulator/research/experiments/autonomous-research-cycle')
from storage_budget import StorageBudget
from budget import Budget, digest
b = StorageBudget()
here = b.root/'campaigns/nas-post-mlpg-timing-20261005-v1'
expected = {
'arc-20261004-v1/.DS_Store':'3ee32c29f8dd660b582ca4136c300f8938c8c7680d76b5d8bcb848ef7868defd',
'arc-20261004-v1/campaigns/.DS_Store':'a6128b62a5086df64284173d21feeb052f8d8f17928e00175ee32404076bd88c',
'arc-20261004-v1/campaigns/nas-post-mlpg-timing-20261005-v1/.DS_Store':'7a5d9750de2e5582796aafea57d9a78849a51ca44104049fe95e779a049a28c7',
'arc-20261004-v1/campaigns/nas-post-mlpg-timing-20261005-v1/render/.DS_Store':'b713e67fba16648b9114f139967e73e0f32ae8ecdfd782721522236cfaa34d0b'}
assert Budget.inventory(b) == b.registered(), '内蔵成果の予約外変更'
assert b.audit_data_hashes() == 149
known = {r['physical'] for r in b.locations().values()}
actual = {str(p.relative_to(b.guard.root)) for p in b.external.rglob('*') if p.is_file() and str(p.relative_to(b.guard.root)) not in known}
assert actual == set(expected), '未知の予約外成果'
observations = []
for physical, sha in expected.items():
 p = b.guard.root/physical
 assert not p.is_symlink() and p.stat().st_size == 6148 and digest(p) == sha
 assert p.read_bytes()[:8] == b'\x00\x00\x00\x01Bud1', 'OSメタデータの形式不一致'
 observations.append(dict(physical=physical, bytes=p.stat().st_size, mtime_ns=p.stat().st_mtime_ns, sha256=sha))
with b.job('post-mlpg-timing-v1','audit','再開照合で検出したOSメタデータ4件の保存・容量計上', reserve_bytes=100000) as j:
 b.write(b.root/'resume-storage-metadata-0001.py', Path(__file__).read_bytes(), j if False else None)
 for i, row in enumerate(observations):
  target=b.guard.root/row['physical']; logical=here/'storage-os-metadata-0001'/('%02d.dsstore'%i)
  with b.locked():
   state=b._load();job=state['jobs'][j]; name=str(logical.relative_to(b.root))
   assert not os.path.lexists(logical) and digest(target)==row['sha256']
   b._check(state,row['bytes'],'post-mlpg-timing-v1',tier='external')
   job['reserve_bytes']-=row['bytes']; assert job['reserve_bytes']>=0
   b.locate(state,name,row['physical'],row['bytes'],len(os.fsencode(str(target))),row['sha256'])
   b.set_file(state,name,[row['bytes'],None]);state['payload_bytes']+=row['bytes']
   state['campaigns']['post-mlpg-timing-v1']['payload_bytes']+=row['bytes']
   state['write_bytes']+=row['bytes']+len(os.fsencode(str(target)))
   b._write_state(state)
   logical.parent.mkdir(parents=True,exist_ok=True);os.symlink(str(target),logical)
   b.set_file(state,name,[logical.stat().st_size,logical.stat().st_mtime_ns]);b._write_state(state)
 b.save(here/'storage-os-metadata-observation-0001.json',dict(reason='前セッション終了後の予約外OSメタデータを再開監査で発見。削除・移動・書換えせず個別hashとサイズを登録。一般的な除外規則は追加しない。',observations=observations,original_external_files_unchanged=True,previous_reservation_absent=True,unreserved_write_bytes_conservatively_accounted=24592,scientific_sources_unchanged=True,quality_evidence=False,source_sha256=digest(Path(__file__))),j)
print(b.reconcile(),flush=True);print({'external_hashes':b.audit_data_hashes()},flush=True)
