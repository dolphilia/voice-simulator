"""局所比較・失敗回復・上限・旧保存を監査して終了判断を保存する。"""
from collections import Counter
import time
from campaign import LocalBudget, ROOT, RESULT, REPO, read, save, digest, check_seal
from summarize import paired
from centered_projection import tests


def main():
    b = LocalBudget()
    with b.job('audit', '局所比較の完了範囲・上限・旧封印と負例を監査', 2_000_000):
        preserve = read(RESULT/'input-preservation.json')
        assert [check_seal(REPO/p['seal']) for p in preserve['seals']] == preserve['seals']
        for path in ('protocol.json', 'evaluation-contract.json'):
            for name, sha in read(RESULT/path)['source_hashes'].items():
                assert digest(ROOT/name) == sha
        for name, sha in read(RESULT/'training-contract.json')['input_files'].items():
            assert digest(ROOT/name) == sha
        for name, sha in read(RESULT/'model-comparison.json')['model_hashes'].items():
            assert digest(RESULT/'models'/name) == sha
        for name, sha in read(RESULT/'engine-contract.json')['asr_model_hashes'].items():
            assert digest(REPO/name) == sha
        manifest = read(RESULT/'render-manifest.json')
        assert len(manifest['rows']) == manifest['completed'] == 64 and len(manifest['development_rows']) == 64
        for row in manifest['rows']+manifest['development_rows']:
            assert row['status'] == 'completed' and digest(ROOT/row['wav']) == row['wav_sha256']
            assert row['evaluation']['E0_pass'] and row['maximum_abs_half_tone'] <= 3
            assert len(row['internal_unchanged']) == 5
        for row in manifest['rows']:
            for engine in ('whisper', 'reazon'):
                result = read(RESULT/'asr'/engine/(row['id']+'.json'))
                assert result['status'] == 'completed' and result['wav_sha256'] == row['wav_sha256']
        assert read(RESULT/'entry-audit.json')['passed'] and read(RESULT/'runtime-audit.json')['passed']
        bundle = RESULT/'bundle'
        for name, sha in read(bundle/'manifest.json')['files'].items():
            assert digest(bundle/name) == sha
        for name in ('direct_non_neural', 'distilled_non_neural'):
            assert len(read(bundle/(name+'.json'))['coefficients']) == 16
        fixture = {'text_id': 'fixture', 'status': 'completed', 'errors': 1, 'native_errors': 1, 'characters': 8}
        assert paired([fixture])['observed_non_worsening']
        assert not paired([])['observed_non_worsening']
        assert not paired([fixture, {'text_id': 'fixture', 'status': 'missing'}])['observed_non_worsening']
        assert not paired([{**fixture, 'errors': 2}])['observed_non_worsening']
        save(RESULT/'projection-preparation-tests.json', tests())
        save(RESULT/'completion-audit.json', {'authorized_comparison_completed': True, 'diagnostic_wavs': 64,
            'development_wavs': 64, 'completed_ai_results': 128, 'failed_or_missing_asr': 0,
            'entry_exact_match': True, 'runtime_exact_match_pairs': 4, 'previous_seals_verified': 9,
            'previous_sealed_files_verified': sum(p['verified_files'] for p in preserve['seals']),
            'models_and_frozen_source_hashes_match': True, 'negative_missing_empty_worsening_tests': True,
            'all_requirements_met': False, 'pending_processes': [], 'fresh_resumed_turn': 1,
            'current_turn_classification': 'progress', 'next_projection_only_prepared': True,
            'unresolved': read(RESULT/'summary.json')['unresolved'], 'quality_certified': False})
    # 未終了の自分自身の監査ジョブがなくなってから上限を検査する。
    events = b.events()
    starts = {e['id']: e for e in events if e['event'] == 'start'}
    finishes = [e for e in events if e['event'] == 'finish']
    assert len(starts) == len(finishes)
    try:
        b.reserve('ai', '129回目の拒否検査')
    except RuntimeError as exc:
        assert str(exc) == '試行数の上限です'
    else:
        raise AssertionError('AI上限を超えました')
    assert events == b.events()
    counts = Counter()
    for e in starts.values():
        counts[e['kind']] += e['count']
    failed = [e for e in finishes if e['status'] != 'completed']
    assert counts['render'] == 181 and counts['ai'] == 128 and counts['train'] == 3 and counts['teacher'] == 0
    assert len(failed) == 3 and [starts[e['id']]['kind'] for e in failed] == ['setup', 'setup', 'render']
    contract = read(RESULT/'contract.json')
    elapsed = time.time()-contract['started_epoch']
    inventory = b.inventory()
    assert elapsed < contract['limits']['seconds'] and inventory['bytes']+65536 < contract['limits']['bytes']
    download = read(RESULT/'source-provenance.json')['download_bytes']+read(RESULT/'source-supplement.json')['bytes']
    assert download <= contract['source_download_limit_bytes']
    save(RESULT/'cost-audit.json', {'counts': dict(counts), 'seconds_before_report': elapsed,
        'inventory_before_cost_audit': inventory, 'limits': contract['limits'], 'source_download_bytes': download,
        'failed_jobs': failed, 'all_jobs_finished': True, 'all_jobs_succeeded': False,
        'failures_resolved': ['ソース取得のネットワーク拒否→承認範囲の権限付き取得',
            '既定clangのSDK不足→既存Apple clangで構築', '無声状態のゼロ残差拒否→範囲を緩和せず別版で厳密一致再検査'],
        'no_further_generation_evaluation_training': True, 'unused_render_calls': 11, 'unused_ai_calls': 0,
        'unused_train_calls': 1, 'no_automatic_extension': True})
    print({'counts': dict(counts), 'seconds': elapsed, 'bytes': inventory['bytes']})


if __name__ == '__main__':
    main()
