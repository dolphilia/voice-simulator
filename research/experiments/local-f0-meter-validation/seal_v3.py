"""限定計測検証を封印し、残余枠の使用を拒否する。"""
import time
from campaign import LocalBudget, ROOT, RESULT, REPO, read, save, digest, check_seal


def main():
    for n,sha in read(RESULT/'supplemental-contract-v2.json')['source_hashes'].items():assert digest(ROOT/n)==sha
    b=LocalBudget();costs=read(RESULT/'cost-audit.json')
    assert read(RESULT/'completion-audit-v2.json')['authorized_comparison_completed']
    preserve=read(RESULT/'input-preservation.json')['seals'];assert [check_seal(REPO/p['seal']) for p in preserve]==preserve
    events=b.events();assert {e['id'] for e in events if e['event']=='start'}=={e['id'] for e in events if e['event']=='finish'}
    save(RESULT/'closeout.json',{'campaign_closed':True,'quality_goal_completed':False,'counts':costs['counts'],'pending_processes':[],
        'reason':'24信号の自己回復と93波形の局所感度比較・監査を完了。日本語品質資格は未達。',
        'qualified_procedural_signal_method':read(RESULT/'summary.json')['qualified_procedural_signal_method'],
        'no_automatic_extension':True,'next_campaign_started':False,'next_comparison_authorized':False,
        'current_turn_classification':'progress','fresh_resumed_turn':1})
    docs=[REPO/'docs/note/local-f0-meter-validation-result-2026-10-03.md']
    for filename in ('guarded-waveform-reachability-proposal-2026-10-03.md',):
        p=REPO/'docs/plans'/filename
        if p.exists():docs.append(p)
    files=[p for p in ROOT.rglob('*') if p.is_file() and not p.is_symlink() and p.name!='.lock' and '__pycache__' not in p.parts]
    inv=b.inventory();elapsed=time.time()-read(RESULT/'contract.json')['started_epoch']
    assert elapsed<1800 and inv['bytes']+65536<50000000
    save(RESULT/'artifact-seal.json',{'path_base':str(REPO),'campaign':RESULT.name,'files':{str(p.relative_to(REPO)):digest(p) for p in sorted(files+docs)},
        'counts':costs['counts'],'wall_seconds_at_seal':elapsed,'inventory_before_seal':inv,'quality_certified':False,'all_requirements_met':False})
    seal=check_seal(RESULT/'artifact-seal.json')
    try:b.reserve('audit','終了後の実行拒否検査')
    except RuntimeError as e:assert str(e)=='終了封印後の処理を認めません'
    else:raise AssertionError('封印後の処理を拒否しません')
    print({'sealed_files':seal['verified_files'],'seconds':elapsed,'bytes':b.inventory()['bytes'],'closed_budget_rejected':True})

if __name__=='__main__':main()
