"""結果・失敗・実装・次案を封印し、以後の自動実行を拒否する。"""
import time
from campaign import LocalBudget, ROOT, RESULT, REPO, read, save, digest, check_seal


def main():
    b = LocalBudget()
    if (RESULT/'artifact-seal.json').exists():
        raise FileExistsError('封印済みです')
    costs = read(RESULT/'cost-audit.json')
    assert costs['counts']['render'] == 181 and costs['counts']['ai'] == 128
    assert read(RESULT/'completion-audit.json')['authorized_comparison_completed']
    assert read(RESULT/'runtime-audit.json')['passed']
    assert not any(d['content_diagnostic_supported'] for d in read(RESULT/'summary.json')['decisions'].values())
    preserved = read(RESULT/'input-preservation.json')['seals']
    assert [check_seal(REPO/s['seal']) for s in preserved] == preserved
    save(RESULT/'closeout.json', {'campaign_closed': True, 'quality_goal_completed': False,
        'counts': costs['counts'], 'pending_processes': [], 'no_automatic_extension': True,
        'reason': '固定比較・単独実行・失敗監査を完了。全候補が内容保護不通過。',
        'next_projection_math_prepared': True, 'next_comparison_authorized': False,
        'next_proposal': 'docs/plans/local-f0-projection-revision-proposal-2026-10-03.md',
        'fresh_resumed_turn': 1, 'current_turn_classification': 'progress'})
    docs = [REPO/'docs/note/local-f0-transfer-result-2026-10-03.md',
            REPO/'docs/plans/local-f0-projection-revision-proposal-2026-10-03.md']
    files = [p for p in ROOT.rglob('*') if p.is_file() and not p.is_symlink() and p.name != '.lock' and '__pycache__' not in p.parts]
    inventory = b.inventory()
    elapsed = time.time()-read(RESULT/'contract.json')['started_epoch']
    assert elapsed < 7200 and inventory['bytes']+65536 < 200_000_000
    save(RESULT/'artifact-seal.json', {'path_base': str(REPO), 'campaign': RESULT.name,
        'files': {str(p.relative_to(REPO)): digest(p) for p in sorted(files+docs)},
        'counts': costs['counts'], 'wall_seconds_at_seal': elapsed, 'inventory_before_seal': inventory,
        'quality_certified': False, 'all_requirements_met': False})
    checked = check_seal(RESULT/'artifact-seal.json')
    try:
        b.reserve('audit', '終了後実行の拒否検査')
    except RuntimeError as exc:
        assert str(exc) == '終了封印後の処理を認めません'
    else:
        raise AssertionError('封印後に再予約できました')
    print({'sealed_files': checked['verified_files'], 'seconds': elapsed, 'bytes': b.inventory()['bytes'],
           'closed_budget_rejected': True})


if __name__ == '__main__':
    main()
