"""限定比較を旧成果と照合して封印し、以後の実行を拒否する。"""
import time
from campaign import LocalBudget, ROOT, RESULT, REPO, read, save, digest, check_seal

def main():
    b=LocalBudget(); costs=read(RESULT/'cost-audit.json')
    assert costs['counts']['render']==80 and costs['counts']['ai']==128
    assert read(RESULT/'completion-audit.json')['authorized_comparison_completed']
    assert read(RESULT/'runtime-audit.json')['passed']
    assert not any(d['content_diagnostic_supported'] for d in read(RESULT/'summary.json')['decisions'].values())
    seals=read(RESULT/'input-preservation.json')['seals']
    assert [check_seal(REPO/p['seal']) for p in seals]==seals
    events=b.events(); starts={e['id'] for e in events if e['event']=='start'}; ends={e['id'] for e in events if e['event']=='finish'}
    assert starts==ends and all(e['status']=='completed' for e in events if e['event']=='finish')
    save(RESULT/'closeout.json',{'campaign_closed':True,'quality_goal_completed':False,'counts':costs['counts'],
        'pending_processes':[],'no_automatic_extension':True,'current_turn_classification':'progress','fresh_resumed_turn':1,
        'reason':'投影不変性と比較・隔離を完了。全候補内容保護不通過。',
        'next_campaign_started':False,'next_comparison_authorized':False,
        'next_proposal':'docs/plans/waveform-local-f0-reachability-proposal-2026-10-03.md'})
    docs=[REPO/'docs/note/local-f0-projection-revision-result-2026-10-03.md',
          REPO/'docs/plans/waveform-local-f0-reachability-proposal-2026-10-03.md']
    files=[p for p in ROOT.rglob('*') if p.is_file() and not p.is_symlink() and p.name!='.lock' and '__pycache__' not in p.parts]
    inv=b.inventory(); elapsed=time.time()-read(RESULT/'contract.json')['started_epoch']
    assert elapsed<3600 and inv['bytes']+65536<100000000
    save(RESULT/'artifact-seal.json',{'path_base':str(REPO),'campaign':RESULT.name,
        'files':{str(p.relative_to(REPO)):digest(p) for p in sorted(files+docs)},'counts':costs['counts'],
        'wall_seconds_at_seal':elapsed,'inventory_before_seal':inv,'quality_certified':False,'all_requirements_met':False})
    checked=check_seal(RESULT/'artifact-seal.json')
    try: b.reserve('audit','封印後の拒否検査')
    except RuntimeError as e: assert str(e)=='終了封印後の処理を認めません'
    else: raise AssertionError('封印後に処理を予約できました')
    print({'sealed_files':checked['verified_files'],'seconds':elapsed,'bytes':b.inventory()['bytes'],'closed_budget_rejected':True})

if __name__=='__main__': main()
