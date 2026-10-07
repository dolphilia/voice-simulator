"""同じ文・条件の既定HMMと比較し、認識器別の悪化を残す。"""
from collections import Counter
from campaign import ContentBudget, ROOT, RESULT, EXT, REPO, read, save, digest, verify_seal


def aggregate(pairs):
    complete = [p for p in pairs if p['status'] == 'completed']
    chars = sum(p['characters'] for p in complete)
    errors = sum(p['errors'] for p in complete)
    native = sum(p['native_errors'] for p in complete)
    missing = len(pairs)-len(complete)
    return {'expected_wavs': len(pairs), 'complete_wavs': len(complete), 'missing': missing,
            'independent_texts': len({p['text_id'] for p in pairs}),
            'characters': chars, 'errors': errors, 'native_errors': native,
            'cer': errors/chars if chars else None,
            'native_cer': native/chars if chars else None,
            'error_delta': errors-native,
            'worse_wavs': sum(p['errors'] > p['native_errors'] for p in complete),
            'better_wavs': sum(p['errors'] < p['native_errors'] for p in complete),
            'observed_non_worsening': bool(pairs) and not missing and errors <= native}


def main():
    budget = ContentBudget()
    protocol = read(RESULT/'protocol.json')
    with budget.job('audit', '認識器別集計と内容保持判定', 2_000_000):
        by_engine = {}
        raw = {}
        for engine in ('whisper', 'reazon'):
            records = {}
            for row in protocol['rows']:
                path = RESULT/'asr'/engine/(row['id']+'.json')
                if path.exists():
                    record = read(path)
                    assert record['wav_sha256'] == row['wav_sha256']
                    assert record['protocol_sha256'] == digest(RESULT/'protocol.json')
                    assert digest(EXT/row['wav']) == row['wav_sha256']
                else:
                    record = {**row, 'status': 'missing'}
                records[row['id']] = record
            raw[engine] = records
            comparisons = {}
            for source, variants in [('render', ['direct_non_neural', 'neural_control', 'distilled_non_neural']),
                                     ('refined', ['direct_non_neural', 'distilled_non_neural'])]:
                for variant in variants:
                    pairs = []
                    for record in records.values():
                        if record['source'] != source or record['variant'] != variant:
                            continue
                        text_id = record['id'].split('/')[1]
                        group = protocol['groups'][text_id]
                        native = records[f'render/{text_id}/{record["condition"]}/native']
                        pair = {'id': record['id'], 'text_id': text_id, 'text': record['text'],
                            'condition': record['condition'], 'length': group['length'],
                            'challenge_group': group['challenge_group'], 'status': 'missing',
                            'candidate_status': record['status'], 'native_status': native['status'],
                            'wav_sha256': record['wav_sha256'], 'native_wav_sha256': native['wav_sha256']}
                        if record['status'] == native['status'] == 'completed':
                            assert record['reference_kana'] == native['reference_kana']
                            pair.update(status='completed', characters=record['characters'],
                                errors=record['errors'], native_errors=native['errors'],
                                hypothesis=record['hypothesis'], native_hypothesis=native['hypothesis'],
                                error_delta=record['errors']-native['errors'])
                        pairs.append(pair)
                    assert len(pairs) == 16
                    groups = {}
                    selectors = {'all': lambda p: True,
                        'short': lambda p: p['length'] == 'short',
                        'long': lambda p: p['length'] == 'long'}
                    for i in range(4):
                        selectors[f'challenge_group_{i}'] = lambda p, i=i: p['challenge_group'] == i
                    for name, select in selectors.items():
                        for condition in ('neutral', 'challenge', 'combined'):
                            subset = [p for p in pairs if select(p) and
                                      (condition == 'combined' or p['condition'] == condition)]
                            groups[name+'/'+condition] = aggregate(subset)
                    comparisons[source+'/'+variant] = {'pairs': pairs, 'groups': groups,
                        'all_groups_non_worsening': all(g['observed_non_worsening'] for g in groups.values()),
                        'worsening_groups': [k for k, g in groups.items() if not g['observed_non_worsening']]}
            by_engine[engine] = {'status_counts': dict(Counter(r['status'] for r in records.values())),
                                'comparisons': comparisons,
                                'runtime_diagnostic': [r for r in records.values() if r['source'] == 'runtime']}
        disagreements = []
        for row in protocol['rows']:
            a, b = (raw[e][row['id']] for e in ('whisper', 'reazon'))
            if a['status'] == b['status'] == 'completed' and a['predicted_kana'] != b['predicted_kana']:
                disagreements.append({'id': row['id'], 'text': row['text'],
                    'whisper_hypothesis': a['hypothesis'], 'reazon_hypothesis': b['hypothesis'],
                    'whisper_errors': a['errors'], 'reazon_errors': b['errors'], 'characters': a['characters']})
        decisions = {key: {'content_diagnostic_supported': all(
            by_engine[e]['comparisons'][key]['all_groups_non_worsening'] for e in by_engine),
            'perceptual_quality_certified': False, 'final_independent_confirmation': False}
            for key in by_engine['whisper']['comparisons']}
        save(RESULT/'summary.json', {'by_engine': by_engine, 'decisions': decisions,
            'disagreements': disagreements, 'failed_or_missing': [
                {'engine': e, 'id': r['id'], 'status': r['status'], 'error': r.get('error')}
                for e in raw for r in raw[e].values() if r['status'] != 'completed'],
            'rule': protocol['comparison_rule'], 'rule_scope': protocol['rule_scope'],
            'no_training_or_selection_after_asr': True, 'all_requirements_met': False,
            'unresolved': ['知覚評価器の日本語・非ニューラル方式への資格',
                '未使用集合での最終独立品質確認', '局所イベント・声質の実装と評価',
                '全条件での絶対F0・制御応答の保護']})
    with budget.job('audit', '終了時の旧成果物保全と費用監査', 2_000_000):
        old = read(RESULT/'input-preservation-audit.json')
        checks = [verify_seal(REPO/r['seal']) for r in old['seals']]
        for path, sha in protocol['model_hashes'].items():
            assert digest(REPO/path) == sha
        starts = [r for r in budget.events() if r['event'] == 'start']
        finishes = [r for r in budget.events() if r['event'] == 'finish']
        save(RESULT/'cost-audit.json', {'counts': dict(Counter(r['kind'] for r in starts)),
            'ai_calls': sum(r['count'] for r in starts if r['kind'] == 'ai'),
            'ai_seconds': sum(r['seconds'] for r in finishes if r['id'] in
                {s['id'] for s in starts if s['kind'] == 'ai'}),
            'inventory': budget.inventory(), 'limits': read(RESULT/'contract.json')['limits'],
            'old_preservation': checks, 'models_unchanged': True,
            'current_audit_finishes_after_this_snapshot': True})
    print('認識結果の比較・旧成果物の保全・費用監査が完了しました')


if __name__ == '__main__':
    main()
