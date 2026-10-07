"""上限超過の事実と未実施を保持して部分成果を封印する。"""
import time
from campaign import LocalBudget, ROOT, RESULT, REPO, read, save, digest, check_seal


def main():
    b=LocalBudget();audit=read(RESULT/'completion-audit-v2.json');cost=read(RESULT/'cost-audit-v2.json')
    assert audit['authorized_campaign_closed_at_limit'] and not audit['authorized_comparison_completed']
    seals=read(RESULT/'input-preservation.json')['seals'];assert [check_seal(REPO/s['seal']) for s in seals]==seals
    events=b.events();assert {e['id'] for e in events if e['event']=='start'}=={e['id'] for e in events if e['event']=='finish'}
    save(RESULT/'closeout.json',{'campaign_closed':True,'quality_goal_completed':False,'comparison_complete':False,
        'reason':'保存実装が容量350MBを超過。証拠を可逆圧縮して生成・fit・AIの追加を止めた。',
        'counts':cost['counts'],'resource_limit_violation':True,'peak_observed_bytes':cost['peak_observed_bytes'],
        'isolated_waves':0,'asr_records':0,'pending_processes':[],'no_automatic_extension':True,
        'next_campaign_started':False,'next_comparison_authorized':False,'current_turn_classification':'progress','fresh_resumed_turn':1})
    docs=[REPO/'docs/note/saved-waveform-shared-control-result-2026-10-03.md',REPO/read(RESULT/'next-proposal.json')['path']]
    files=[p for p in ROOT.rglob('*') if p.is_file() and not p.is_symlink() and p.name!='.lock' and '__pycache__' not in p.parts]
    inv=b.inventory();elapsed=time.time()-read(RESULT/'contract.json')['started_epoch'];assert elapsed<3600 and inv['bytes']+65536<350000000
    save(RESULT/'artifact-seal.json',{'path_base':str(REPO),'campaign':RESULT.name,'files':{str(p.relative_to(REPO)):digest(p) for p in sorted(files+docs)},
        'counts':cost['counts'],'resource_limit_violation':True,'peak_observed_bytes':cost['peak_observed_bytes'],
        'inventory_before_seal':inv,'wall_seconds_at_seal':elapsed,'quality_certified':False,'all_requirements_met':False})
    verified=check_seal(RESULT/'artifact-seal.json')
    try:b.reserve('audit','封印後の処理拒否検査')
    except RuntimeError as exc:assert str(exc)=='終了封印後の処理を認めません'
    else:raise AssertionError('封印後の処理を拒否しません')
    print({'sealed_files':verified['verified_files'],'seconds':elapsed,'bytes_after_recovery':b.inventory()['bytes'],'resource_limit_violation':True,'closed_budget_rejected':True})

if __name__=='__main__':main()
