"""固定結果の事後診断。採否の規則や認識出力は書き換えない。"""
import sys
from collections import Counter
from campaign import ContentBudget, OLD, EXT, RESULT, read, save, digest
from summarize import aggregate
sys.path.insert(0, str(OLD))
from diagnostics import normalize_text, edit_distance


def main():
    budget = ContentBudget()
    with budget.job('audit', '補正の内容差・かな変換の曖昧性・停止条件の診断', 1_000_000):
        summary = read(RESULT/'summary.json')
        comparisons = {}
        for engine in ('whisper', 'reazon'):
            for variant in ('direct_non_neural', 'distilled_non_neural'):
                pairs = []
                for row in read(RESULT/'protocol.json')['rows']:
                    if row['source'] != 'refined' or row['variant'] != variant:
                        continue
                    before_id = row['id'].replace('refined/', 'render/', 1)
                    before = read(RESULT/'asr'/engine/(before_id+'.json'))
                    after = read(RESULT/'asr'/engine/(row['id']+'.json'))
                    before_wav = EXT/before['wav']
                    after_wav = EXT/after['wav']
                    a, b = read(before_wav.with_suffix('.json')), read(after_wav.with_suffix('.json'))
                    assert digest(before_wav) == before['wav_sha256']
                    assert digest(after_wav) == after['wav_sha256']
                    pair = {'id': row['id'], 'before_errors': before.get('errors'),
                        'after_errors': after.get('errors'), 'status': 'missing',
                        'before_settings': a['settings'], 'after_settings': b['settings'],
                        'target': b['target'], 'before_measurement': a['measurement'],
                        'after_measurement': b['measurement']}
                    if before['status'] == after['status'] == 'completed':
                        pair.update(status='completed', characters=after['characters'],
                            cer_error_delta=after['errors']-before['errors'],
                            before_hypothesis=before['hypothesis'], after_hypothesis=after['hypothesis'])
                    for name, field in [('duration', 'active_seconds'), ('f0', 'f0_hz')]:
                        target = b['target'][field]
                        pair[name+'_before_relative_error'] = abs(a['measurement'][field]/target-1)
                        pair[name+'_after_relative_error'] = abs(b['measurement'][field]/target-1)
                    pair['duration_target_improved'] = pair['duration_after_relative_error'] < pair['duration_before_relative_error']
                    pair['f0_target_improved'] = pair['f0_after_relative_error'] < pair['f0_before_relative_error']
                    pairs.append(pair)
                complete = [p for p in pairs if p['status'] == 'completed']
                comparisons[engine+'/'+variant] = {'pairs': pairs,
                    'before_errors': sum(p['before_errors'] for p in complete),
                    'after_errors': sum(p['after_errors'] for p in complete),
                    'characters': sum(p['characters'] for p in complete),
                    'better_wavs': sum(p['cer_error_delta'] < 0 for p in complete),
                    'worse_wavs': sum(p['cer_error_delta'] > 0 for p in complete),
                    'duration_improved_but_cer_worse': [p['id'] for p in complete
                        if p['duration_target_improved'] and p['cer_error_delta'] > 0],
                    'scope': '同じ8既知文の事後照合。音響目標損失と内容は同じ目的ではない。因果分離・独立確認ではない'}
        import pyopenjtalk
        transformations = []
        reference = normalize_text(pyopenjtalk.g2p('鐘が響く。', kana=True))
        for text in ('鐘が響く。', 'カネの響く', '金の響く'):
            kana = normalize_text(pyopenjtalk.g2p(text, kana=True))
            transformations.append({'text': text, 'kana': kana, 'errors_against_reference': edit_distance(reference, kana),
                'frontend': pyopenjtalk.run_frontend(text)})
        save(RESULT/'interpretation.json', {'refinement_pairs': comparisons,
            'normalization_diagnostic': {'transformations': transformations,
                'frozen_worsening_case': 'refined/acoustic-03/neutral/distilled_non_neural',
                'native_hypothesis': 'カネの響く', 'candidate_hypothesis': '金の響く',
                'whisper_frozen_error_delta': 2, 'reazon_same_pair_errors': [0, 0],
                'interpretation': '追加2誤りはかな変換のカネ/キン差。ASRの表記選択と実際の発音を、この結果だけでは分離できない。変換器の曖昧性の疑いを残し、実音の悪化と断定しない',
                'alternative_reading_not_verified_from_audio': True,
                'posthoc_score_correction': False, 'gate_unchanged': True},
            'engine_disagreement_count': len(summary['disagreements']),
            'next_mechanism': '全体F0と速度を単独に変更する対照で、共同補正の影響を分離する。評価の読み曖昧性は別の事前契約で点検する',
            'no_new_audio_or_learning': True})
        fixture = {'status': 'completed', 'text_id': 'fixture', 'characters': 6, 'errors': 1, 'native_errors': 1}
        assert aggregate([fixture])['observed_non_worsening']
        assert not aggregate([{**fixture, 'errors': 2}])['observed_non_worsening']
        assert not aggregate([fixture, {'status': 'missing', 'text_id': 'fixture'}])['observed_non_worsening']
        assert not aggregate([])['observed_non_worsening']
        blocked = []
        for kind in ('teacher', 'render', 'train', 'ai'):
            try:
                budget.reserve(kind, '禁止操作の非実行検査')
            except RuntimeError as exc:
                blocked.append({'kind': kind, 'reason': str(exc)})
            else:
                raise AssertionError('禁止操作の予約が成功しました')
        save(RESULT/'negative-path-tests.json', {'empty_missing_worsening_rejected': True,
            'equal_observation_accepted': True, 'generation_training_and_exhausted_ai_rejected': blocked,
            'actual_ai_calls': sum(r['count'] for r in budget.events() if r['event'] == 'start' and r['kind'] == 'ai'),
            'scope': '判定器と上限の人工検査。実音声の品質証拠ではない'})
    print('事後診断と禁止操作・欠損・悪化の拒否検査が完了しました')


if __name__ == '__main__':
    main()
