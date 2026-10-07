"""新1campaignを終了し旧成果を再検証して封印する。"""
import time
from campaign import LocalBudget, ROOT, RESULT, REPO, read, save, digest, check_seal


def main():
    b=LocalBudget();costs=read(RESULT/'cost-audit.json');summary=read(RESULT/'summary.json')
    assert read(RESULT/'completion-audit.json')['authorized_comparison_completed']
    seals=read(RESULT/'input-preservation.json')['seals'];assert [check_seal(REPO/p['seal']) for p in seals]==seals
    events=b.events();assert {e['id'] for e in events if e['event']=='start'}=={e['id'] for e in events if e['event']=='finish'}
    save(RESULT/'closeout.json',{'campaign_closed':True,'quality_goal_completed':False,'counts':costs['counts'],'pending_processes':[],
        'reason':'承認済み4文の片側差分・縮小更新比較と監査を完了。共有制御・独立最終品質確認は未達。',
        'next_shared_control_research_supported':summary['next_shared_control_research_supported'],
        'no_automatic_extension':True,'next_campaign_started':False,'next_comparison_authorized':False,
        'current_turn_classification':'progress','fresh_resumed_turn':1})
    docs=[REPO/'docs/note/guarded-waveform-reachability-result-2026-10-03.md']
    if (RESULT/'next-proposal.json').exists():docs.append(REPO/read(RESULT/'next-proposal.json')['path'])
    files=[p for p in ROOT.rglob('*') if p.is_file() and not p.is_symlink() and p.name!='.lock' and '__pycache__' not in p.parts]
    inv=b.inventory();elapsed=time.time()-read(RESULT/'contract.json')['started_epoch']
    assert elapsed<3600 and inv['bytes']+65536<150000000
    save(RESULT/'artifact-seal.json',{'path_base':str(REPO),'campaign':RESULT.name,'files':{str(p.relative_to(REPO)):digest(p) for p in sorted(files+docs)},
        'counts':costs['counts'],'wall_seconds_at_seal':elapsed,'inventory_before_seal':inv,'quality_certified':False,'all_requirements_met':False})
    seal=check_seal(RESULT/'artifact-seal.json')
    try:b.reserve('audit','封印後の拒否検査')
    except RuntimeError as e:assert str(e)=='終了封印後の処理を認めません'
    else:raise AssertionError('封印後の追加処理を拒否しません')
    print({'sealed_files':seal['verified_files'],'seconds':elapsed,'bytes':b.inventory()['bytes'],'closed_budget_rejected':True})

if __name__=='__main__':main()
