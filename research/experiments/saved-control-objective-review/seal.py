"""終了報告と次の一実験の具体案を含めて封印する。"""
from campaign import *

def main():
    b=LocalBudget();assert read(RESULT/'closeout.json')['campaign_closed'];Storage().check()
    docs=[REPO/'docs/note/saved-control-objective-review-result-2026-10-04.md',REPO/read(RESULT/'next-proposal.json')['path']]
    files=[p for p in ROOT.rglob('*') if p.is_file() and p.name not in ('.lock','.storage-state.json')]
    seconds=time.time()-read(RESULT/'contract.json')['started_epoch'];inv=b.inventory();extra=sum(p.stat().st_size for p in docs)
    assert seconds<1200 and inv['bytes']+extra+65536<10_000_000
    save(RESULT/'artifact-seal.json',{'path_base':str(REPO),'campaign':RESULT.name,'files':{str(p.relative_to(REPO)):digest(p) for p in sorted(files+docs)},
        'wall_seconds_at_seal':seconds,'inventory_before_seal':inv,'external_docs_bytes':extra,'quality_certified':False,'all_requirements_met':False})
    print(check_seal(RESULT/'artifact-seal.json'))
    try:b.reserve('audit','封印後の拒否')
    except RuntimeError:pass
    else:raise AssertionError('封印後処理を拒否しません')
if __name__=='__main__':main()
