"""終了資料と新実験を封印する。"""
from campaign import *

def main():
    b=LocalBudget();assert read(RESULT/'closeout.json')['campaign_closed']
    Storage().check()
    documents=[REPO/'docs/note/saved-shared-control-evaluation-result-2026-10-03.md']
    if (RESULT/'next-proposal.json').exists():documents.append(REPO/read(RESULT/'next-proposal.json')['path'])
    files=[p for p in ROOT.rglob('*') if p.is_file() and p.name not in ('.lock','.storage-state.json')]
    seconds=time.time()-read(RESULT/'contract.json')['started_epoch'];inv=b.inventory()
    assert seconds<3600 and inv['bytes']+65536<100_000_000
    save(RESULT/'artifact-seal.json',{'path_base':str(REPO),'campaign':RESULT.name,
        'files':{str(p.relative_to(REPO)):digest(p) for p in sorted(files+documents)},
        'counts':read(RESULT/'cost-audit.json')['counts'],'wall_seconds_at_seal':seconds,
        'inventory_before_seal':inv,'quality_certified':False,'all_requirements_met':False})
    verified=check_seal(RESULT/'artifact-seal.json')
    try:b.reserve('audit','封印後拒否確認')
    except RuntimeError:pass
    else:raise AssertionError('封印後の処理が開始されました')
    print({'sealed_files':verified['verified_files'],'seconds':seconds,'bytes':b.inventory()['bytes'],'closed_budget_rejected':True})

if __name__=='__main__':main()
