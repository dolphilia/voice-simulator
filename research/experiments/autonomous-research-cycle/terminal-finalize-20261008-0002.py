"""終了結果のpushを記録し、無稼働台帳を一度だけ終端commitとして同期する。"""
from pathlib import Path
import sys,subprocess,json,re,time,argparse,shutil,os
ROOT=Path(__file__).resolve().parent
HERE=ROOT/'campaigns/nas-additional-closeout-20261008-v1'
sys.path[:0]=[str(HERE),str(ROOT)]
from budget import read,digest,encode
from temporary_storage import ManagedStorageBudget as Budget
REPO=ROOT.parents[2]
def git(*args):
    return subprocess.check_output(['git',*args],cwd=REPO,text=True,stderr=subprocess.STDOUT,timeout=60).strip()
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--expected-result-commit',required=True);args=parser.parse_args()
    head=git('rev-parse','HEAD');remote=git('ls-remote','origin','refs/heads/main').split()[0]
    assert head==remote==args.expected_result_commit
    assert git('symbolic-ref','--short','HEAD')=='main'
    assert git('remote','get-url','origin')=='https://github.com/dolphilia/voice-simulator.git'
    assert git('rev-parse','--abbrev-ref','--symbolic-full-name','@{upstream}')=='origin/main'
    assert not git('status','--porcelain') and not git('diff','--cached','--name-only')
    b=Budget();b.recover();v=b.snapshot();assert not v['jobs'] and len(v['campaigns'])==28
    assert all(c['closed'] for c in v['campaigns'].values())
    assert all(w['status']=='removed' and w['absence_verified'] and not os.path.lexists(w['path']) for w in v['temporary_work'].values())
    result=read(ROOT/'cycle-closeout-result-20261008-0002.json')
    assert not result['quality_goal_completed'] and not result['protected_confirmation_opened']
    b.reconcile()
    fees=[json.loads(l) for l in (ROOT/'control/jobs.jsonl').read_text().splitlines()]
    previous=[e for e in fees if e.get('kind')=='git-write-reservation' and e.get('scope')=='additional-closeout-result'][-1]
    terminal_seconds=180
    # 終端Git・検証・報告を最大180秒で保守的に先取りする。停止後に無稼働時間を加算しない。
    estimated_blob=(ROOT/'control/state.json').stat().st_size+(ROOT/'control/jobs.jsonl').stat().st_size+16000
    terminal_fee=2*estimated_blob+262144
    with b.locked():
        s=b._load();assert s['seconds']+terminal_seconds<s['limits']['seconds']-14400
        s['seconds']+=terminal_seconds;s['write_bytes']+=terminal_fee
        b.event(s,dict(kind='terminal-management-reservation',scope='terminal-state-once-v2',
            conservative_seconds=terminal_seconds,conservative_git_write_bytes=terminal_fee,
            consumed_budget_not_refunded=True,reason='終端台帳commit/push・先端照合・最終報告。自己参照記録のcommit連鎖を避ける。'))
        b._write_state(s)
    b.save(ROOT/'git-save-20261008-0027.json',dict(commit=head,branch='main',
        origin='https://github.com/dolphilia/voice-simulator.git',remote_head=remote,
        push_origin_verified=True,scope='additional-closeout-result',files=previous['files'],
        blob_bytes=previous['blob_bytes'],conservative_git_write_bytes=previous['conservative_bytes'],
        raw_data_not_in_Git=True,quality_goal_completed=False))
    v=b.snapshot()
    b.save(ROOT/'terminal-state-20261008-0002.json',dict(
        cycle=v['cycle'],stop_reason='campaigns_limit_reached',quality_goal_completed=False,
        campaigns_used=28,campaigns_limit=28,all_campaigns_closed=True,jobs={},
        session_required_at_rest=None,all_temporary_removed=True,temporary_workspaces=len(v['temporary_work']),
        protected_confirmation_opened=False,perceptual_qualification=False,
        result_commit=head,result_push_origin_verified=True,result_remote_head=remote,
        terminal_commit_sha_self_reference_omitted=True,
        terminal_commit_sync_rule='この終端ファイルを含むcommitのHEADとorigin refs/heads/mainが一致することを実照合。最終SHAとpush結果はGitおよび実行記録に保存する。',
        terminal_commit_push_expected_after_save=True,no_chain_of_receipt_only_commits=True,
        conservative_post_suspend_management_seconds=terminal_seconds,
        conservative_terminal_git_write_bytes=terminal_fee,
        additional_campaign_authorization_required=True,
        proposed_campaign_limit=32,other_limits_and_prior_consumption_unchanged=True,
        new_scientific_work_prohibited_until_amendment=True,
        allocation_request='next-campaign-allocation-request-20261008-0002.md',
        result='cycle-closeout-result-20261008-0002.json',report='cycle-closeout-report-20261008-0002.md',
        canonical_final_budget='control/state.json',
        real_free_internal=shutil.disk_usage(ROOT).free,real_free_external=shutil.disk_usage(b.guard.mount).free,
        budget_observation=dict(seconds=v['seconds'],counts=v['counts'],write_bytes=v['write_bytes'],limits=v['limits']),
        goal_blocked_audit=dict(consecutive_goal_turns_with_this_stop=1,
            note='このターンで初めて28回上限に達した。品質達成とはしない。blockedの3連続ターン条件も未成立。')))
    with b.locked():
        s=b._load();s['continuation_checkpoint'].update(
            id='campaign-limit-terminal-20261008-0002',
            git_save_pending=False,scientific_result_commit=head,scientific_result_push_verified=True,
            terminal_state='terminal-state-20261008-0002.json',
            terminal_commit_sync='保存後にHEAD/origin先端一致を検証。自己SHAはGit実体を正本とする。',
            next='追加campaign上限の明示承認まで新規科学処理を開始しない。再開時は同じ台帳・媒体・封印・Git先端から確認する。')
        b._write_state(s)
    b.reconcile()
    b.suspend()
    frozen=read(ROOT/'control/state.json');assert frozen['session'] is None and not frozen['jobs']
    phase_started=time.monotonic()
    files=[str((ROOT/n).relative_to(REPO)) for n in ['git-save-20261008-0027.json','terminal-state-20261008-0002.json','control/state.json','control/jobs.jsonl']]
    for n in files:
        p=REPO/n;assert not p.is_symlink()
        if p.suffix=='.json':json.loads(p.read_text())
        if p.suffix=='.jsonl':
            for line in p.read_text().splitlines():json.loads(line)
        assert not re.search(r'(?:sk-[A-Za-z0-9]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|-----BEGIN (?:RSA |OPENSSH )?PRIVATE KEY-----)',p.read_text()),n
    git('diff','--check');git('add','--',*files)
    assert set(git('diff','--cached','--name-only').splitlines())==set(files)
    git('diff','--cached','--check')
    print(git('commit','-m','research: 追加4枠の終端台帳とGit先端を同期して休止')[:450],flush=True)
    final_head=git('rev-parse','HEAD')
    print(git('push','origin','main'),flush=True)
    final_remote=git('ls-remote','origin','refs/heads/main').split()[0]
    assert final_head==final_remote and not git('status','--porcelain')
    elapsed=time.monotonic()-phase_started
    assert elapsed<=terminal_seconds,'終端管理時間の予約超過。新しい管理追記で実超過を計上する必要がある。'
    final=read(ROOT/'control/state.json');assert final==frozen
    print(json.dumps(dict(final_commit=final_head,origin_head=final_remote,clean_worktree=True,
        session=final['session'],jobs=final['jobs'],all_campaigns_closed=True,
        campaigns=len(final['campaigns']),quality_goal_completed=False,
        seconds=final['seconds'],remaining_seconds=final['limits']['seconds']-final['seconds'],
        counts=final['counts'],write_bytes=final['write_bytes'],
        terminal_elapsed_seconds=elapsed,conservative_terminal_seconds=terminal_seconds,
        state_sha256=digest(ROOT/'control/state.json'),
        local_files_index_sha256=digest(ROOT/'control/files.sqlite')),ensure_ascii=False),flush=True)
if __name__=='__main__':main()
