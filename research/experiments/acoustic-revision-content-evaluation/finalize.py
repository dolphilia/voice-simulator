"""上限・完了範囲・旧成果物の保全を確認して、追加枠を封印する。"""
from collections import Counter
import time
from campaign import ContentBudget, ROOT, RESULT, REPO, EXT, read, save, digest, verify_seal


def main():
    budget = ContentBudget()
    if (RESULT/'artifact-seal.json').exists():
        raise RuntimeError('既に封印したcampaignです')
    # 未終了ジョブがない状態で、200回の上限そのものによる拒否を検査する。
    events = budget.events()
    starts = [r for r in events if r['event'] == 'start']
    ends = {r['id'] for r in events if r['event'] == 'finish'}
    assert all(r['id'] in ends for r in starts)
    before_events = len(events)
    try:
        budget.reserve('ai', '200回の上限拒否検査')
    except RuntimeError as exc:
        assert str(exc) == '試行数の上限です', str(exc)
        rejection = str(exc)
    else:
        raise AssertionError('201回目の予約が成功しました')
    assert len(budget.events()) == before_events
    with budget.job('audit', '承認範囲の完了と封印前監査', 2_000_000):
        save(RESULT/'negative-path-tests-v2.json', {
            'no_outstanding_jobs_at_test': True, 'ai_cap_rejection': rejection,
            'no_extra_ai_ticket_created': True,
            'clarification': '旧negative-path-tests.jsonのAI拒否は監査ジョブ中の未終了ジョブ保護によるもの。本検査で未終了ジョブなしの状態の200回上限拒否を確認した',
            'generation_training_tests': 'negative-path-tests.json',
            'missing_empty_worsening_tests': 'negative-path-tests.json',
            'perceptual_evidence': False})
        protocol = read(RESULT/'protocol.json')
        for name, sha in protocol['source_hashes'].items():
            assert digest(ROOT/name) == sha
        old = read(RESULT/'input-preservation-audit.json')
        seals = [verify_seal(REPO/r['seal']) for r in old['seals']]
        for path, sha in protocol['model_hashes'].items():
            assert digest(REPO/path) == sha
        for row in protocol['rows']:
            assert digest(EXT/row['wav']) == row['wav_sha256']
            for engine in ('whisper', 'reazon'):
                result = read(RESULT/'asr'/engine/(row['id']+'.json'))
                assert result['status'] == 'completed'
                assert result['wav_sha256'] == row['wav_sha256']
        save(RESULT/'completion-checkpoint.json', {
            'authorized_evaluation_completed': True, 'planned_ai_calls': 200,
            'completed_ai_results': 200, 'unique_wavs': 100, 'failed_or_missing': 0,
            'original_goal_completed': False, 'goal_objective_unchanged': True,
            'old_seals': seals, 'old_files_verified': sum(s['verified_files'] for s in seals),
            'frozen_models_and_evaluation_sources_unchanged': True,
            'content_gate': '全体の改善は観測したが、Whisperの条件群別保護が不通過。読み変換の疑義は診断として保持し、採否を変更していない',
            'next_proposal': 'docs/plans/acoustic-control-factorial-proposal-2026-10-02.md',
            'next_proposal_executed': False,
            'unresolved': read(RESULT/'summary.json')['unresolved'],
            'fresh_resumed_turn': 1, 'current_turn_classification': 'meaningful_progress',
            'same_blocking_condition_for_three_resumed_turns': False,
            'pending_processes': [], 'no_automatic_budget_extension': True})
    events = budget.events()
    starts = [r for r in events if r['event'] == 'start']
    finishes = [r for r in events if r['event'] == 'finish']
    by_id = {r['id']: r for r in starts}
    assert len(starts) == len(finishes)
    assert all(r['status'] == 'completed' for r in finishes)
    counts = Counter()
    for row in starts:
        counts[row['kind']] += row['count']
    assert counts['ai'] == 200 and not any(counts[k] for k in ('teacher', 'render', 'train'))
    contract = read(RESULT/'contract.json')
    notes = [REPO/'docs/note/acoustic-revision-content-evaluation-result-2026-10-02.md',
             REPO/'docs/plans/acoustic-control-factorial-proposal-2026-10-02.md']
    wall = time.time()-contract['started_epoch']
    inventory = budget.inventory()
    external_bytes = sum(p.stat().st_size for p in notes)
    assert wall < contract['limits']['seconds']
    assert inventory['bytes']+external_bytes+65536 < contract['limits']['bytes']
    save(RESULT/'final-cost-audit.json', {'counts': dict(counts), 'wall_seconds_before_seal': wall,
        'seconds_by_kind': {k: sum(r['seconds'] for r in finishes if by_id[r['id']]['kind'] == k)
                            for k in counts},
        'inventory_before_final_audit_and_seal': inventory, 'external_report_and_proposal_bytes': external_bytes,
        'limits': contract['limits'], 'all_jobs_completed': True, 'outstanding_jobs': [],
        'previous_campaigns_unmodified': True,
        'later_seal_and_audit_capacity_reserve': 65536})
    paths = [p for p in ROOT.rglob('*') if p.is_file() and not p.is_symlink()
             and '__pycache__' not in p.parts and p.name != '.lock'] + notes
    files = {str(p.relative_to(REPO)): digest(p) for p in sorted(paths)}
    save(RESULT/'artifact-seal.json', {'epoch': time.time(), 'path_base': str(REPO), 'files': files,
        'scope': '追加の内容評価・診断・提案を封印。旧封印へ上書きしない',
        'authorized_evaluation_completed': True, 'all_requirements_met': False,
        'inventory_before_seal': budget.inventory()})
    actual_bytes = budget.inventory()['bytes']+external_bytes
    assert actual_bytes <= contract['limits']['bytes']
    print({'ai_calls': counts['ai'], 'teacher': counts['teacher'], 'render': counts['render'],
           'train': counts['train'], 'wall_seconds': wall, 'additional_bytes': actual_bytes,
           'sealed_files': len(files)})


if __name__ == '__main__':
    main()
