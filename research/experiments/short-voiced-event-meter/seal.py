"""終了資料を含めて封印し、追加処理の拒否を確認する。"""
from campaign import *

def main():
    b=LocalBudget();assert read(RESULT/'closeout.json')['campaign_closed'];Storage().check()
    docs=[REPO/'docs/note/short-voiced-event-meter-result-2026-10-03.md']
    if (RESULT/'next-proposal.json').exists():docs.append(REPO/read(RESULT/'next-proposal.json')['path'])
    files=[p for p in ROOT.rglob('*') if p.is_file() and p.name not in ('.lock','.storage-state.json')]
    seconds=time.time()-read(RESULT/'contract.json')['started_epoch'];inv=b.inventory();assert seconds<1800 and inv['bytes']+65536<50_000_000
    save(RESULT/'artifact-seal.json',{'path_base':str(REPO),'campaign':RESULT.name,
        'files':{str(p.relative_to(REPO)):digest(p) for p in sorted(files+docs)},'counts':read(RESULT/'cost-audit.json')['counts'],
        'wall_seconds_at_seal':seconds,'inventory_before_seal':inv,'quality_certified':False,'all_requirements_met':False})
    verified=check_seal(RESULT/'artifact-seal.json')
    try:b.reserve('render','封印後の拒否検査')
    except RuntimeError:pass
    else:raise AssertionError('封印後の生成を拒否しません')
    print({'sealed_files':verified['verified_files'],'seconds':seconds,'bytes':b.inventory()['bytes'],'closed_budget_rejected':True})
if __name__=='__main__':main()
