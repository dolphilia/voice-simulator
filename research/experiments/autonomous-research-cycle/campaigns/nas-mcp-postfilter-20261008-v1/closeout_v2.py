"""全256比較・二ASR・独立性・費用を保持して封印する。"""
from paths import *
from controller_v2 import verify
def main():
    verify();b=Budget();b.recover();assert not b.snapshot()['jobs']
    summary=read(HERE/'aggregate-summary.json')
    assert all(not v for v in [summary['perceptual_qualification'],summary['quality_goal_completed'],summary['protected_confirmation_opened']])
    with b.job(NAME,'audit','MCP後処理の全実体hash・費用・終了封印',reserve_bytes=4000000) as job:
        count=b.audit_data_hashes();state=b.snapshot();campaign=state['campaigns'][NAME]
        assert all(v['status']=='removed' and v['absence_verified'] for v in state.get('temporary_work',{}).values())
        assert all(campaign['counts'].get(k,0)<=v for k,v in campaign['limits'].items() if k not in ['seconds','bytes'])
        assert state['seconds']-campaign['start_seconds']<campaign['limits']['seconds'] and campaign['payload_bytes']<campaign['limits']['bytes']
        b.save(HERE/'cost-audit.json',dict(campaign=campaign,whole_cycle_counts=state['counts'],whole_cycle_seconds=state['seconds'],whole_cycle_write_bytes=state['write_bytes'],all_temporary_work_removed=True,planned_render=780,planned_DSP=1804,planned_AI=512,new_teacher_train_inverse_download_money=0),job)
        b.save(HERE/'summary-source-audit.json',dict(summary_sha256=digest(HERE/'summary.json'),aggregate_sha256=digest(HERE/'aggregate-summary.json'),source_sha256=digest(HERE/'summarize_v2.py'),all_scientific_conditions_unchanged=True),job)
        b.save(HERE/'decision-audit.json',dict(qualifications=summary['qualifications'],selected=[k for k,v in summary['qualifications'].items() if v],scope='内容/指定制御の研究資格だけ。日本語非ニューラル知覚資格と独立P5は未達。',postfilter_contrasts=summary['factorial_analysis'],secondary_diagnostics=summary['secondary_diagnostics'],no_post_output_tuning=True,quality_goal_completed=False,protected_confirmation_opened=False,next='全256比較の欠測・悪化群・要因差を読み、70%見直しに従って残り枠の処理を選ぶ。'),job)
        lines=['# エネルギー補正付きMCP後処理の比較','', '新16文×2条件×8方式の256比較。全256通常／隔離組、CLI4件、二ASR各256件。','', '|方式|ピッチ/支持通過|E0通過|Whisper誤り|Reazon誤り|資格|','|---|---:|---:|---:|---:|---|']
        for method,q in summary['qualifications'].items():
            e=summary['engineering'][method];w=summary['content'][method]['whisper']['groups']['both/all'];r=summary['content'][method]['reazon']['groups']['both/all']
            lines.append(f"|{method}|{e['pitch_pass_count']}/32|{e['E0_pass_count']}/32|{w['errors']}/{w['characters']}|{r['errors']}/{r['characters']}|{q}|")
        lines+=['', '全33群の悪化・欠測はaggregate-summary.jsonに保持。βは出力前に0/0.2へ固定し、途中の係数探索なし。','MCPエネルギーは一次HTS内部式による補正で、波形の等ラウドネスや知覚品質の保証ではない。','追加Harvest/中心ACFは限定診断で、主判定と旧判定を変更しない。測定器4つを独立票とは扱わない。','保護最終確認は未開封、全体品質は未達。一時領域は全件削除・不存在確認済み。','']
        b.write(HERE/'report.md','\n'.join(lines).encode(),job)
        hashes={str(p.relative_to(REPO)):digest(p) for p in HERE.rglob('*') if p.is_file()}
        b.save(HERE/'artifact-seal.json',dict(files=hashes,path_base='repository',external_hash_verified=count,experiment_completed=True,quality_certified=False,quality_goal_completed=False,budget_before_seal=b.snapshot()),job)
        b.save(HERE/'completion-audit.json',dict(files_verified=len(hashes),seal_sha256=digest(HERE/'artifact-seal.json'),all_temporary_work_removed=True,quality_goal_completed=False,protected_confirmation_opened=False),job)
    b.close_campaign(NAME)
    b.save(ROOT/'progress-0022.json',dict(latest_completed=str(HERE.relative_to(ROOT)),active_campaign=None,comparison_records=256,normal_isolated_pairs=256,CLI=4,ASR_records=512,qualifications=summary['qualifications'],quality_goal_completed=False,protected_confirmation_opened=False,all_temporary_work_removed=True,git_save_pending=True,next='要因差と残予算を確認し、有効な次処理へ継続。',budget=b.reconcile()))
    print(b.reconcile(),flush=True)
if __name__=='__main__':main()
