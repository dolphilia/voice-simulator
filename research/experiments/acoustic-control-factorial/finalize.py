"""承認された比較の結果・費用・旧封印を監査する。"""
from collections import Counter
import time
from campaign import FactorialBudget, ROOT, RESULT, REPO, read, save, digest, check_seal
from summarize import paired


def main():
    budget = FactorialBudget()
    if (RESULT/'artifact-seal.json').exists():
        raise RuntimeError('封印済みの実験です')
    events = budget.events()
    starts = [e for e in events if e['event'] == 'start']
    ends = {e['id'] for e in events if e['event'] == 'finish'}
    assert all(e['id'] in ends for e in starts)
    # 未終了ジョブがない状態で、AI上限そのものを検査する。
    try:
        budget.reserve('ai', '241回目の拒否検査')
    except RuntimeError as exc:
        assert str(exc) == '試行数の上限です'
    else:
        raise AssertionError('AI上限を超えて予約できました')
    assert len(events) == len(budget.events())
    with budget.job('audit', '完了範囲・負例・旧封印の監査', 2_000_000):
        protocol = read(RESULT/'protocol.json')
        for name, sha in protocol['source_hashes'].items():
            assert digest(ROOT/name) == sha
        previous = read(RESULT/'input-preservation.json')
        preservation = [check_seal(REPO/x['seal']) for x in previous['seals']]
        assert previous['seals'] == preservation
        for name, sha in protocol['asr_model_hashes'].items():
            assert digest(REPO/name) == sha
        manifest = read(RESULT/'render-manifest.json')
        assert len(manifest['rows']) == manifest['completed'] == 120
        for row in manifest['rows']:
            assert digest(ROOT/row['wav']) == row['wav_sha256']
            for engine in ('whisper', 'reazon'):
                result = read(RESULT/'asr'/engine/(row['id']+'.json'))
                assert result['status'] == 'completed' and result['wav_sha256'] == row['wav_sha256']
        fixture = {'text_id': 'fixture', 'status': 'completed', 'errors': 1, 'native_errors': 1, 'characters': 6}
        assert paired([fixture])['observed_non_worsening']
        assert not paired([{**fixture, 'errors': 2}])['observed_non_worsening']
        assert not paired([fixture, {'text_id': 'fixture', 'status': 'missing'}])['observed_non_worsening']
        assert not paired([])['observed_non_worsening']
        save(RESULT/'completion-audit.json', {'authorized_factorial_comparison_completed': True,
            'final_wavs': 120, 'completed_ai_results': 240, 'failed_or_missing': 0,
            'all_requirements_met': False, 'old_preservation': preservation,
            'source_and_model_hashes_match': True, 'negative_tests': {
                'missing_empty_worsening_rejected': True, 'equal_observation_accepted': True,
                'exhausted_ai_cap_rejected_without_outstanding_jobs': True},
            'teacher_and_training_calls': 0, 'no_optimization_after_asr': True,
            'solo_runtime_pairs': 4, 'solo_runtime_passed': read(RESULT/'solo-runtime-audit.json')['passed'],
            'previous_turn_classification': 'progress', 'current_turn_classification': 'progress',
            'fresh_resumed_turn': 1, 'pending_processes': [],
            'unresolved': read(RESULT/'summary.json')['unresolved'],
            'scope': '新12文の比較を完了。自然さ・独立最終品質の資格へ置換しない'})
    events = budget.events()
    starts = [e for e in events if e['event'] == 'start']
    finishes = [e for e in events if e['event'] == 'finish']
    assert len(starts) == len(finishes)
    failed = [e for e in finishes if e['status'] != 'completed']
    by_ticket = {e['id']: e for e in starts}
    assert len(failed) == 1 and by_ticket[failed[0]['id']]['kind'] == 'audit'
    probe = read(RESULT/'solo-runtime-audit/probe-result.json')
    assert probe['returncode'] == 71 and 'sandbox_apply: Operation not permitted' in probe['stderr']
    assert read(RESULT/'solo-runtime-audit.json')['passed']
    counts = Counter()
    for e in starts:
        counts[e['kind']] += e['count']
    assert counts['render'] <= 256 and counts['ai'] == 240 and counts['teacher'] == counts['train'] == 0
    contract = read(RESULT/'contract.json')
    wall = time.time()-contract['started_epoch']
    inv = budget.inventory()
    assert wall < contract['limits']['seconds'] and inv['bytes']+65536 < contract['limits']['bytes']
    by_id = {e['id']: e['kind'] for e in starts}
    save(RESULT/'cost-audit.json', {'counts': dict(counts), 'wall_seconds_before_seal': wall,
        'seconds_by_kind': {k: sum(e['seconds'] for e in finishes if by_id[e['id']] == k) for k in counts},
        'inventory_before_cost_audit': inv, 'limits': contract['limits'], 'all_jobs_finished': True,
        'all_jobs_succeeded': False, 'failed_jobs': failed,
        'failure_resolution': '入れ子sandbox起動拒否を保存。権限付き再実行で同じ隔離profileの遮断検査と4組の生成一致を確認。音声生成とAI評価の失敗は0。',
        'no_automatic_extension': True})
    print({'counts': dict(counts), 'seconds': wall, 'bytes': budget.inventory()['bytes']})


if __name__ == '__main__':
    main()
