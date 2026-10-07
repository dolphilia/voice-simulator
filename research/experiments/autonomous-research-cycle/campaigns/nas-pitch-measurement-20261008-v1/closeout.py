"""測定の限定資格・全費用・独立性・一時削除を封印する。"""
from paths import *
from controller import verify
def main():
    verify();b=Budget();b.recover();assert not b.snapshot()['jobs']
    summary=read(HERE/'aggregate-summary.json')
    assert summary['known_period_conditions']==272 and summary['normal_isolated_pairs']==272
    with b.job(NAME,'audit','測定検証の全実体hash・費用・終了封印',reserve_bytes=3000000) as job:
        count=b.audit_data_hashes();state=b.snapshot();campaign=state['campaigns'][NAME]
        assert all(v['status']=='removed' and v['absence_verified'] for v in state.get('temporary_work',{}).values())
        assert all(campaign['counts'].get(k,0)<=v for k,v in campaign['limits'].items() if k not in ['seconds','bytes'])
        assert state['seconds']-campaign['start_seconds']<campaign['limits']['seconds'] and campaign['payload_bytes']<campaign['limits']['bytes']
        b.save(HERE/'cost-audit.json',dict(campaign=campaign,whole_cycle_counts=state['counts'],whole_cycle_seconds=state['seconds'],whole_cycle_write_bytes=state['write_bytes'],all_temporary_work_removed=True,new_AI_teacher_train_inverse_download_money=0,actual_expected_render=820,actual_expected_DSP=2292,closing_reserves_preserved=True),job)
        lines=['# 周期既知の短区間・雑音源に対する測定検証','', '272人工条件と全272通常/隔離組・CLI4件、封印済み192音声への追加診断を完了。','']
        for name,value in summary['qualifications'].items():lines.append('- '+name+': '+str(value))
        lines+=['','人工域の資格を日本語HTS/WORLDや自然さへ拡張しない。既存の音声と判定は変更しない。','保護最終確認は未開封、全体品質は未達。','自分の一時領域は削除・不存在確認済み。','']
        b.write(HERE/'report.md','\n'.join(lines).encode(),job)
        hashes={str(p.relative_to(REPO)):digest(p) for p in HERE.rglob('*') if p.is_file()}
        b.save(HERE/'artifact-seal.json',dict(files=hashes,path_base='repository',external_hash_verified=count,quality_certified=False,quality_goal_completed=False,budget_before_seal=b.snapshot()),job)
        b.save(HERE/'completion-audit.json',dict(files_verified=len(hashes),seal_sha256=digest(HERE/'artifact-seal.json'),all_temporary_work_removed=True,quality_goal_completed=False,protected_confirmation_opened=False),job)
    b.close_campaign(NAME)
    b.save(ROOT/'progress-0020.json',dict(latest_completed=str(HERE.relative_to(ROOT)),active_campaign=None,known_period_conditions=272,normal_isolated_pairs=272,CLI=4,existing_speech_diagnostics=192,qualifications=summary['qualifications'],quality_goal_completed=False,protected_confirmation_opened=False,all_temporary_work_removed=True,git_save_pending=True,next='人工信号と実音声の適用範囲を分け、測定診断と内容保護から次の独立音響要因を選ぶ。',budget=b.reconcile()))
    print(b.reconcile(),flush=True)
if __name__=='__main__':main()
