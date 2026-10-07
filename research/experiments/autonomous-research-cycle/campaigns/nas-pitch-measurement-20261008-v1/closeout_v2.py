"""測定の限定資格・全費用・独立性・一時削除を封印する。"""
from paths import *
from controller import verify
def main():
    verify();b=Budget();b.recover();assert not b.snapshot()['jobs']
    summary=read(HERE/'aggregate-summary.json')
    assert summary['known_period_conditions']==272 and summary['normal_isolated_pairs']==272
    with b.job(NAME,'audit','測定検証の全実体hash・費用・終了封印',reserve_bytes=4000000) as job:
        count=b.audit_data_hashes();state=b.snapshot();campaign=state['campaigns'][NAME]
        assert all(v['status']=='removed' and v['absence_verified'] for v in state.get('temporary_work',{}).values())
        assert all(campaign['counts'].get(k,0)<=v for k,v in campaign['limits'].items() if k not in ['seconds','bytes'])
        assert state['seconds']-campaign['start_seconds']<campaign['limits']['seconds'] and campaign['payload_bytes']<campaign['limits']['bytes']
        assert campaign['counts']['render']==820 and campaign['counts']['dsp']==2292
        b.save(HERE/'summary-source-audit.json',dict(original_summarizer_sha256=digest(HERE/'summarize.py'),aggregate_sha256=digest(HERE/'aggregate-summary.json'),closeout_source_sha256=digest(HERE/'closeout_v2.py'),scientific_gates_unchanged=True,legacy_decisions_unchanged=True),job)
        b.save(HERE/'decision-audit.json',dict(aggregate_sha256=digest(HERE/'aggregate-summary.json'),known_period_qualified=['centered_acf'],Japanese_non_neural_qualified=[],perceptual_qualified=[],historical_decisions_changed=False,diagnostic_missing_unit='固定支持音素区間の合計数。発話件数ではない。',correlated_methods='DIO/Harvestは同WORLD系、global/centered ACFは同推定式。4つの独立票として扱わない。',finding='人工条件では基本波欠損への応答と無声誤受理に測定差がある。実音声では中心ACFの欠測が増えるため、人工資格を拡張しない。',next_campaign='mcp-postfilter-v1',next='HTS一次実装にあるエネルギー保存MCP後処理を独立要因として、新契約・新未知入力で内容と制御への影響を比較する。LF0係数探索は反復しない。',quality_goal_completed=False,protected_confirmation_opened=False),job)
        b.save(HERE/'cost-audit.json',dict(campaign=campaign,whole_cycle_counts=state['counts'],whole_cycle_seconds=state['seconds'],whole_cycle_write_bytes=state['write_bytes'],all_temporary_work_removed=True,new_AI_teacher_train_inverse_download_money=0,actual_expected_render=820,actual_expected_DSP=2292,closing_reserves_preserved=True),job)
        lines=['# 周期既知の短区間・雑音源に対する測定検証','', '272人工条件、全272通常／隔離組、CLI4件、封印済み192音声への追加診断を完了。全生成はE0通過。','', '|測定|主96条件の通過|全条件の無声誤受理|人工域の資格|','|---|---:|---:|---|']
        for method in ['dio','harvest','centered_acf']:
            q=summary['qualifications'][method]
            lines.append(f"|{method}|{q['primary_pass_count']}/96|{q['false_voiced_frames']}/{q['unvoiced_frames']}|{q['qualified_known_period_primary']}|")
        lines+=['', '旧全体ACFは88/96条件通過、否定16条件の誤受理は0。事前の全条件通過を満たさず、支持位置の資格も持たない。','', '|旧方式|DIOの欠測区間|Harvestの欠測区間|中心ACFの欠測区間|','|---|---:|---:|---:|']
        for method,q in summary['diagnostic'].items():
            lines.append(f"|{method}|{q['legacy_missing']}|{q['harvest_missing']}|{q['centered_acf_missing']}|")
        lines+=['', '欠測は32発話ごとの固定支持音素区間を合計した値であり、欠測発話件数ではない。', 'DIO/Harvestは同WORLD系、2つのACFは同推定式で、4つの独立票とは扱わない。', '中心ACFは既知周期域の資格を満たしたが、実音声で欠測が増える。合成波形の真の周期はこの診断では既知でなく、日本語HTS/WORLDや自然さへの評価資格は未確立。既存の音声と判定は変更しない。', '全生成820回、DSP2292回。AI・教師・学習・逆推定・取得・金銭支出は0。自分の一時領域は削除・不存在確認済み。', '次は一次HTS実装のエネルギー保存MCP後処理を独立要因として登録する。LF0係数探索の反復は避ける。', '保護最終確認は未開封、全体品質は未達。','']
        b.write(HERE/'report.md','\n'.join(lines).encode(),job)
        hashes={str(p.relative_to(REPO)):digest(p) for p in HERE.rglob('*') if p.is_file()}
        b.save(HERE/'artifact-seal.json',dict(files=hashes,path_base='repository',external_hash_verified=count,quality_certified=False,quality_goal_completed=False,budget_before_seal=b.snapshot()),job)
        b.save(HERE/'completion-audit.json',dict(files_verified=len(hashes),seal_sha256=digest(HERE/'artifact-seal.json'),all_temporary_work_removed=True,quality_goal_completed=False,protected_confirmation_opened=False),job)
    b.close_campaign(NAME)
    b.save(ROOT/'progress-0020.json',dict(latest_completed=str(HERE.relative_to(ROOT)),active_campaign=None,known_period_conditions=272,normal_isolated_pairs=272,CLI=4,existing_speech_diagnostics=192,qualifications=summary['qualifications'],quality_goal_completed=False,protected_confirmation_opened=False,all_temporary_work_removed=True,git_save_pending=True,next='人工信号と実音声の適用範囲を分け、測定診断と内容保護から次の独立音響要因を選ぶ。',budget=b.reconcile()))
    print(b.reconcile(),flush=True)
if __name__=='__main__':main()
