"""費用・一時削除・全hashを照合して実験を封印し、次の再開点を残す。"""
from paths import *


def main():
    from controller import verify
    verify()
    b = Budget()
    b.recover()
    assert not b.snapshot()['jobs']
    summary = read(HERE / 'summary.json')
    manifest = read(HERE / 'render-manifest.json')
    assert len(manifest['rows']) == 160
    assert all(digest(REPO / r['record']) == r['sha256'] for r in manifest['rows'])
    assert all(len(read(HERE / ('asr-manifest-' + engine + '.json'))['rows']) == 160
               for engine in ['whisper', 'reazon'])
    with b.job(NAME, 'audit', '費用・証拠・一時領域・外部hashの終了監査', reserve_bytes=4_000_000) as job:
        state = b.snapshot()
        campaign = state['campaigns'][NAME]
        assert all(value['status'] == 'removed' and value['absence_verified']
                   for value in state.get('temporary_work', {}).values())
        for key, count in campaign['counts'].items():
            assert count <= campaign['limits'][key]
        assert state['seconds'] - campaign['start_seconds'] <= campaign['limits']['seconds']
        assert campaign['payload_bytes'] < campaign['limits']['bytes']
        b.save(HERE / 'cost-audit.json', dict(campaign=campaign,
            whole_cycle_counts=state['counts'], whole_cycle_seconds=state['seconds'],
            whole_cycle_write_bytes=state['write_bytes'], all_temporary_work_removed=True,
            temporary_reservations=[v for v in state.get('temporary_work', {}).values() if v['campaign'] == NAME],
            render_attempt_reservation_counts_preserved=True, money_yen=0,
            new_teacher_train_inverse_download=0, budget_violation=False), job)
        report = ['# 有声補完・非周期成分2×2の比較結果', '', '新16文×2条件×5方式の160比較を完了。',
                  '全160通常/隔離組とCLI4件の波形hashが一致。二ASRは各160件。',
                  '最終音源は文章から計算する非ニューラルHTS/WORLD。', '']
        for method in summary['qualifications']:
            e = summary['engineering'][method]
            report.append(f"- {method}: 指定F0・支持通過 {e['pitch_pass_count']}/32、E0 {e['E0_pass_count']}/32、研究資格 {summary['qualifications'][method]}。")
            for engine in ['whisper', 'reazon']:
                c = summary['content'][method][engine]
                g = c['groups']['both/all']
                report.append(f"  {engine}: 誤り{g['errors']}/{g['characters']}、native誤り{g['native_errors']}。悪化/欠測群: {', '.join(c['worsening_groups']) or 'なし'}。")
        report += ['', '未達: 日本語非ニューラル知覚資格、独立P5確認。保護最終確認は未開封。',
                   '一時領域は自分の所有manifestだけを削除し、不存在を確認。時間・回数・累積書込は返却しない。',
                   '個別実験の終了を全体品質達成へ読み替えない。', '']
        b.write(HERE / 'report.md', '\n'.join(report).encode(), job)
        hashes = {str(p.relative_to(REPO)): digest(p) for p in HERE.rglob('*') if p.is_file()}
        b.save(HERE / 'artifact-seal.json', dict(path_base='repository', files=hashes,
            budget_before_seal=b.snapshot(), experiment_completed=True,
            quality_certified=False, quality_goal_completed=False), job)
        b.save(HERE / 'completion-audit.json', dict(files_verified=len(hashes),
            seal_sha256=digest(HERE / 'artifact-seal.json'),
            qualifications=summary['qualifications'], all_temporary_work_removed=True,
            final_non_neural_verified=True, protected_confirmation_opened=False,
            quality_goal_completed=False), job)
    b.close_campaign(NAME)
    next_action = ('共有校正を研究版として保持し、声質・励振の独立要因を事前登録。'
        if summary['qualifications']['calibrated'] else
        '駆動値・実波形F0・内容悪化群を分けて診断し、励振/APとフィルタの独立要因を新入力・新契約で比較。絶対F0実験を再実行しない。')
    b.save(ROOT / 'progress-0016.json', dict(latest_completed=str(HERE.relative_to(ROOT)),
        active_campaign=None, qualifications=summary['qualifications'], quality_goal_completed=False,
        comparison_records=160, normal_isolated_pairs=160, CLI=4, ASR_records=320,
        temporary_work_removed=True, next=next_action, budget_snapshot=b.snapshot(),
        protected_confirmation_opened=False, git_save_pending=True))
    print(b.reconcile(), flush=True)
    print(next_action, flush=True)


if __name__ == '__main__':
    main()
