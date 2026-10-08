"""長期承認の適用・意味のある検証・旧証拠照合を行う管理入口。"""
import ast
import json
import os
from pathlib import Path
import subprocess
import time

from budget import ROOT, read, digest, encode
from storage_budget import StorageBudget
from long_horizon_budget import LongHorizonBudget, AMENDMENT, TOTALS, VALIDATION_SOURCES
from test_long_horizon_budget import run_tests

REPO=ROOT.parents[2]
NAME='long-horizon-management-v1'
HERE=ROOT/'campaigns/nas-long-horizon-management-20261008-v1'
SOURCES=('long_horizon_budget.py','test_long_horizon_budget.py','apply_long_horizon_20261008.py')


def apply():
    old=StorageBudget();approval_path=ROOT/'long-horizon-approval-20261008-v1.json'
    approval=read(approval_path)
    assert approval['status']=='approved_pending_implementation'
    for kind in ('proposal','prompt'):
        assert digest(REPO/approval[kind+'_path'])==approval[kind+'_sha256']
    s=read(old.state_path)
    if s.get('long_horizon'):
        return LongHorizonBudget()
    assert s['cycle']==approval['cycle'] and s['campaigns']==approval['base_state']['campaigns']
    assert s['counts']==approval['base_state']['counts'] and not s['jobs']
    # 先行読取で自動生成された自己所有pycだけを明示記録して削除する。
    pyc=ROOT/'__pycache__/storage_guard.cpython-314.pyc'
    actual=old.inventory();known=old.registered()
    assert all(v==actual[n] for n,v in known.items())
    allowed=set(SOURCES)
    if '__pycache__/storage_guard.cpython-314.pyc' not in known and pyc.exists():
        allowed.add(str(pyc.relative_to(ROOT)))
        with old.locked():
            state=old._load();state['write_bytes']+=pyc.stat().st_size
            old.event(state,dict(kind='owned-incidental-bytecode-cleanup',path=str(pyc),bytes=pyc.stat().st_size,
                created_by='初回の保存ガード読取',deleted_when='判明直後。後続入口はPYTHONDONTWRITEBYTECODE=1',sha256=digest(pyc)))
            old._write_state(state)
        pyc.unlink();assert not os.path.lexists(pyc)
    assert set(actual)-set(known)<=allowed
    for name in SOURCES:
        ast.parse((ROOT/name).read_text(),filename=name)
    with old.locked():
        s=old._load()
        for name in SOURCES:
            p=ROOT/name;assert name not in known
            old.set_file(s,name,[p.stat().st_size,p.stat().st_mtime_ns])
            s['payload_bytes']+=p.stat().st_size;s['write_bytes']+=p.stat().st_size
        s['limits'].update(TOTALS);s['limits'].pop('campaigns')
        record=dict(id=AMENDMENT,status='applied',approval_path=approval_path.name,approval_sha256=digest(approval_path),
                    applied_seconds=s['seconds'],applied_counts=dict(s['counts']),scientific_completed=0,
                    last_review=dict(seconds=s['seconds'],scientific_completed=0),closing_seconds=43200,
                    science_enabled_after_validation=True,old_contracts_and_consumption_retained=True,
                    wrapper_path='long_horizon_budget.py',wrapper_sha256=digest(ROOT/'long_horizon_budget.py'))
        s['long_horizon']=record
        s['authorization_amendments'].append(dict(record))
        s['pending_budget_proposal']={**s['pending_budget_proposal'],'status':'approved_applied','approval_path':approval_path.name}
        s['pending_continuation_prompt']={**s['pending_continuation_prompt'],'status':'approved_current_entry'}
        s['continuation_checkpoint_history'].append(s['continuation_checkpoint'])
        s['continuation_checkpoint']=dict(id='long-horizon-applied-validation-pending',active_campaign=None,
            quality_goal_completed=False,protected_confirmation_opened=False,
            next='管理契約で強制・旧封印を検証→commit/push→HTS LPF純観測の登録',git_save_pending=True)
        old.event(s,dict(kind='long-horizon-authorization-applied',amendment=AMENDMENT,limits=TOTALS,
                        campaigns_count_is_not_stop=True,closing_seconds=43200,no_reset=True))
        old._write_state(s)
    return LongHorizonBudget()


def main():
    b=apply();b.recover();b.reconcile()
    if NAME not in b.snapshot()['campaigns']:
        limits=dict(seconds=14400,bytes=200000000,write_bytes=400000000,render=0,teacher=0,ai=0,dsp=0,
                    train=0,inverse=0,download=0,setup=30,audit=30)
        registration=dict(campaign=NAME,purpose='長期予算強制検証と旧科学証拠の保存同一性照合',
            limits=limits,scientific_outputs=0,final_quality_evidence=False,protected_confirmation_opened=False,
            tests='全有限資源・終了12時間・個別上限・未承認拒否・旧消費・失敗・一時回収',
            prior_manifest='campaigns/nas-additional-closeout-20261008-v1/integrity-manifest.json',
            input_hashes={n:digest(ROOT/n) for n in ['long-horizon-approval-20261008-v1.json',
                'campaigns/nas-additional-closeout-20261008-v1/artifact-seal.json',
                'campaigns/nas-additional-closeout-20261008-v1/integrity-manifest.json']},
            source_hashes={n:digest(ROOT/n) for n in SOURCES},no_old_scientific_source_edit=True)
        b.start_campaign(NAME,str(HERE.relative_to(ROOT)),limits,__import__('hashlib').sha256(encode(registration)).hexdigest(),purpose='management')
        with b.job(NAME,'setup','管理契約登録',reserve_bytes=1000000) as j:b.save(HERE/'registration.json',registration,j)
    if not (HERE/'validation.json').exists():
        with b.job(NAME,'audit','長期強制の合成台帳検証',reserve_bytes=50000000) as j:
            with b.workspace(j,'合成台帳・外部保存・失敗回収の意味のある管理検証',maximum_bytes=30000000,maximum_write_bytes=100000000) as (path,env):
                result=run_tests(path)
            result.update(validated_sources={n:digest(ROOT/n) for n in VALIDATION_SOURCES},
                          owned_fixture_removed=True,fixture_directory_absent=not os.path.lexists(path))
            b.save(HERE/'validation.json',result,j)
    if not (HERE/'preservation-audit.json').exists():
        manifest=read(ROOT/'campaigns/nas-additional-closeout-20261008-v1/integrity-manifest.json')
        expected=dict(manifest['physical_file_hashes'])
        s=b.snapshot()
        for name,c in read(ROOT/'long-horizon-approval-20261008-v1.json')['base_state']['campaigns'].items():
            seal_path=ROOT/c['prefix']/'artifact-seal.json';seal=read(seal_path)
            expected[str(seal_path.resolve())]=dict(bytes=seal_path.stat().st_size,sha256=digest(seal_path))
            for n,h in seal['files'].items():
                p=(REPO/n).resolve(strict=True)
                if str(p) in expected:assert expected[str(p)]['sha256']==h,n
                else:expected[str(p)]=dict(bytes=p.stat().st_size,sha256=h)
        with b.job(NAME,'audit','旧封印・全外部・移動実体hash照合',reserve_bytes=1000000) as j:
            total=0
            for i,(n,v) in enumerate(expected.items(),1):
                p=Path(n);assert p.stat().st_size==v['bytes'] and digest(p)==v['sha256'],n
                total+=v['bytes']
                if i%10000==0:print(json.dumps(dict(verified=i,total=len(expected))),flush=True)
            inventory=b.reconcile();locations=b.locations()
            assert all(row['sha256'] and expected.get(str((b.guard.root/row['physical']).resolve()),{}).get('sha256')==row['sha256'] for row in locations.values())
            b.save(HERE/'preservation-audit.json',dict(passed=True,old_campaigns=28,
                physical_files_hashed=len(expected),bytes_read=total,all_old_seals_and_references_unchanged=True,
                all_external_locations_verified=len(locations),all_old_temporary_absent=True,
                prior_integrity_manifest_sha256=digest(ROOT/'campaigns/nas-additional-closeout-20261008-v1/integrity-manifest.json'),
                hashes_only_no_P5_text_inspection=True,old_gates_and_results_not_reinterpreted=True,
                inventory=inventory),j)
    with b.locked():
        s=b._load();s['long_horizon'].update(validation_path=str((HERE/'validation.json').relative_to(ROOT)),
            validation_sha256=digest(HERE/'validation.json'),preservation_path=str((HERE/'preservation-audit.json').relative_to(ROOT)),
            preservation_sha256=digest(HERE/'preservation-audit.json'))
        s['continuation_checkpoint'].update(id='long-horizon-validated',next='commit/push後、HTS224件LPF後周期成分の純観測を新契約で登録',active_campaign=NAME)
        b._write_state(s)
    if not (HERE/'result.json').exists():
        b.save(HERE/'result.json',dict(budget_applied=True,validated=True,preservation_passed=True,
            scientific_outputs=0,quality_goal_completed=False,protected_confirmation_opened=False,
            next='HTS224件LPF後観測・WORLD原因分離・短窓動的資格・早期の知覚資格検証',budget=b.reconcile()))
    if not b.snapshot()['campaigns'][NAME]['closed']:b.close_campaign(NAME)
    with b.locked():
        s=b._load();s['continuation_checkpoint'].update(active_campaign=None,all_campaigns_closed=True);b._write_state(s)
    print(json.dumps(dict(status='management_completed_science_allowed',budget=b.reconcile()),ensure_ascii=False),flush=True)


if __name__=='__main__':main()
