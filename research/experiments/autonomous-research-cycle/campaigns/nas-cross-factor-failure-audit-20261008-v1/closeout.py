"""既存全6コホートの診断整理を封印し、最終包括監査へ渡す。"""
from paths import *
from audit import verify
def main():
    verify();b=Budget();b.recover();assert not b.snapshot()['jobs']
    s=read(HERE/'aggregate-summary.json')
    assert s['old_group_counts_exact_match'] and s['old_qualifications_unchanged'] and not s['quality_goal_completed']
    with b.job(NAME,'audit','旧結果整理の費用・外部hash・全分母を封印',reserve_bytes=4_000_000) as j:
        n=b.audit_data_hashes();v=b.snapshot();c=v['campaigns'][NAME]
        assert all(w['status']=='removed' and w['absence_verified'] for w in v['temporary_work'].values())
        assert c['counts'].get('render',0)==c['counts'].get('dsp',0)==c['counts'].get('ai',0)==0
        assert v['seconds']-c['start_seconds']<c['limits']['seconds'] and c['payload_bytes']<c['limits']['bytes']
        b.save(HERE/'cost-audit.json',dict(actual_render=0,actual_DSP=0,actual_AI=0,
            new_teacher_train_inverse_download_money=0,technical_retries=0,campaign=c,
            all_temporary_removed=True,no_new_temporary_files=True,whole_cycle_counts=v['counts']),j)
        files={str(p.relative_to(REPO)):digest(p) for p in HERE.rglob('*') if p.is_file()}
        b.save(HERE/'artifact-seal.json',dict(files=files,path_base='repository',external_hash_verified=n,
            experiment_completed=True,posthoc_diagnostic_only=True,old_qualification_unchanged=True,quality_goal_completed=False),j)
        b.save(HERE/'completion-audit.json',dict(files_verified=len(files),seal_sha256=digest(HERE/'artifact-seal.json'),
            all_temporary_removed=True,quality_goal_completed=False,protected_confirmation_opened=False),j)
    b.close_campaign(NAME)
    b.save(ROOT/'progress-0030.json',dict(latest_completed=str(HERE.relative_to(ROOT)),active_campaign=None,
        existing_wave_records=992,existing_ASR_records=1984,new_render_DSP_AI=0,quality_goal_completed=False,
        protected_confirmation_opened=False,next='第24回包括終了監査。全予算・旧封印・媒体・一時・Git・未達条件を照合。',git_save_pending=True,budget=b.reconcile()))
    print(b.reconcile(),flush=True)
if __name__=='__main__':main()
