"""共有制御比較を終了して全成果を封印する。"""
import time
from campaign import LocalBudget, ROOT, RESULT, REPO, read, save, digest, check_seal


def main():
    b=LocalBudget();audit=read(RESULT/'completion-audit.json');cost=read(RESULT/'cost-audit.json');summary=read(RESULT/'summary.json')
    assert audit['authorized_comparison_completed']
    seals=read(RESULT/'input-preservation.json')['seals'];assert [check_seal(REPO/s['seal']) for s in seals]==seals
    events=b.events();assert {e['id'] for e in events if e['event']=='start'}=={e['id'] for e in events if e['event']=='finish'}
    save(RESULT/'closeout.json',{'campaign_closed':True,'quality_goal_completed':False,'counts':cost['counts'],'pending_processes':[],
        'qualifications':summary['qualifications'],'runtime_independence_passed':summary['runtime_independence_passed'],
        'no_automatic_extension':True,'next_campaign_started':False,'next_comparison_authorized':False,
        'current_turn_classification':'progress','fresh_resumed_turn':1})
    docs=[REPO/'docs/note/saved-waveform-shared-control-result-2026-10-03.md']
    if (RESULT/'next-proposal.json').exists():docs.append(REPO/read(RESULT/'next-proposal.json')['path'])
    files=[path for path in ROOT.rglob('*') if path.is_file() and not path.is_symlink() and path.name!='.lock' and '__pycache__' not in path.parts]
    inv=b.inventory();elapsed=time.time()-read(RESULT/'contract.json')['started_epoch'];assert elapsed<3600 and inv['bytes']+65536<350000000
    save(RESULT/'artifact-seal.json',{'path_base':str(REPO),'campaign':RESULT.name,'files':{str(path.relative_to(REPO)):digest(path) for path in sorted(files+docs)},
        'counts':cost['counts'],'wall_seconds_at_seal':elapsed,'inventory_before_seal':inv,'quality_certified':False,'all_requirements_met':False})
    result=check_seal(RESULT/'artifact-seal.json')
    try:b.reserve('audit','封印後の処理拒否検査')
    except RuntimeError as exc:assert str(exc)=='終了封印後の処理を認めません'
    else:raise AssertionError('封印後の追加処理を拒否しません')
    print({'sealed_files':result['verified_files'],'seconds':elapsed,'bytes':b.inventory()['bytes'],'closed_budget_rejected':True})

if __name__=='__main__':main()
