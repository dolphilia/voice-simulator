"""局所制御の内容保護・蒸留損失・実音響干渉を認識器ごとに記録する。"""
import subprocess
import sys
from campaign import LocalBudget, ROOT, RESULT, read, save, digest


def paired(rows):
    complete = [r for r in rows if r['status'] == 'completed']
    errors = sum(r['errors'] for r in complete)
    native = sum(r['native_errors'] for r in complete)
    chars = sum(r['characters'] for r in complete)
    return {'expected_wavs': len(rows), 'missing': len(rows)-len(complete),
        'independent_texts': len({r['text_id'] for r in rows}), 'errors': errors, 'native_errors': native,
        'characters': chars, 'cer': errors/chars if chars else None, 'native_cer': native/chars if chars else None,
        'error_delta': errors-native, 'observed_non_worsening': bool(rows) and len(complete) == len(rows) and errors <= native,
        'worse_wavs': sum(r['errors'] > r['native_errors'] for r in complete),
        'better_wavs': sum(r['errors'] < r['native_errors'] for r in complete)}


def main():
    with LocalBudget().job('audit', '局所内容保護・蒸留差・実音響を集計', 5_000_000):
        p = read(RESULT/'protocol.json')
        subprocess.run([sys.executable, str(ROOT/'dictionary_diagnostic.py')], check=True)
        readings = read(RESULT/'reading-diagnostic.json')
        ambiguous = {(r['engine'], r['id']): bool(r['ambiguities']) for r in readings['rows']}
        manifest = read(RESULT/'render-manifest.json')
        by_engine = {}
        for engine in ('whisper', 'reazon'):
            records = {}
            for row in manifest['rows']:
                path = RESULT/'asr'/engine/(row['id']+'.json')
                r = read(path) if path.exists() else {**row, 'status': 'missing'}
                if r['status'] == 'completed':
                    assert digest(ROOT/row['wav']) == r['wav_sha256'] == row['wav_sha256']
                    assert r['protocol_sha256'] == digest(RESULT/'protocol.json')
                records[row['id']] = r
            comparisons = {}
            for variant in p['variants'][1:]:
                pairs = []
                for record in records.values():
                    if record['variant'] != variant:
                        continue
                    text_id = record['id'].split('/')[0]
                    native = records[text_id+'/'+record['condition']+'/native']
                    pair = {k: record[k] for k in ('id', 'text', 'condition', 'length', 'challenge_group')}
                    pair.update(text_id=text_id, status='missing',
                        reading_ambiguity=ambiguous.get((engine, record['id']), False),
                        native_reading_ambiguity=ambiguous.get((engine, native['id']), False))
                    if record['status'] == native['status'] == 'completed':
                        assert record['reference_kana'] == native['reference_kana']
                        pair.update(status='completed', errors=record['errors'], native_errors=native['errors'],
                            characters=record['characters'], hypothesis=record['hypothesis'], native_hypothesis=native['hypothesis'])
                    pairs.append(pair)
                groups = {}
                for group in ('all', 'short', 'long', 'g0', 'g1', 'g2', 'g3'):
                    selected = [r for r in pairs if group == 'all' or r['length'] == group or group == 'g'+str(r['challenge_group'])]
                    for condition in ('neutral', 'challenge', 'combined'):
                        groups[group+'/'+condition] = paired([r for r in selected if condition == 'combined' or r['condition'] == condition])
                comparisons[variant] = {'pairs': pairs, 'groups': groups,
                    'all_groups_non_worsening': all(g['observed_non_worsening'] for g in groups.values()),
                    'worsening_groups': [k for k, g in groups.items() if not g['observed_non_worsening']]}
            transfer = []
            for row in p['rows']:
                for condition in ('neutral', 'challenge'):
                    case = {v: records[row['id']+'/'+condition+'/'+v] for v in p['variants']}
                    transfer.append({'text_id': row['id'], 'condition': condition,
                        'errors': {v: r.get('errors') for v, r in case.items()},
                        'student_minus_neural_errors': case['distilled_non_neural'].get('errors', 0)-case['neural'].get('errors', 0),
                        'student_minus_direct_errors': case['distilled_non_neural'].get('errors', 0)-case['direct_non_neural'].get('errors', 0),
                        'missing': any(r['status'] != 'completed' for r in case.values())})
            by_engine[engine] = {'comparisons': comparisons, 'transfer': transfer,
                'status_counts': {s: sum(r['status'] == s for r in records.values()) for s in ('completed', 'failed', 'missing')}}
        allrows = {r['id']: r for r in manifest['rows']+manifest['development_rows']}
        engineering = {}
        for variant in p['variants']:
            complete = [r for r in manifest['rows'] if r['variant'] == variant and r['status'] == 'completed']
            held, responses = [], []
            for record in complete:
                native = allrows[record['id'].rsplit('/', 1)[0]+'/native']
                assert record['settings'] == native['settings']
                held.append({'id': record['id'], 'global_commands_equal': True,
                    'duration_relative_difference': record['measurement']['active_seconds']/native['measurement']['active_seconds']-1,
                    'acf_f0_relative_difference': record['measurement']['f0_hz']/native['measurement']['f0_hz']-1,
                    'dio_f0_relative_difference': record['measurement']['dio_f0_hz']/native['measurement']['dio_f0_hz']-1,
                    'dio_voiced_fraction_difference': record['measurement']['dio_voiced_fraction']-native['measurement']['dio_voiced_fraction']})
            for row in p['rows']:
                neutral, challenge = [allrows[row['id']+'/'+c+'/'+variant] for c in ('neutral', 'challenge')]
                response = {'text_id': row['id']}
                for estimator, field in [('acf', 'f0_hz'), ('dio', 'dio_f0_hz')]:
                    error = abs((challenge['measurement'][field]/neutral['measurement'][field])/(row['requests']['challenge']['requested_f0']/220)-1)
                    response[estimator+'_relative_response_error'] = error
                response['duration_relative_response_error'] = abs((challenge['measurement']['active_seconds']/neutral['measurement']['active_seconds'])*row['requests']['challenge']['speed']-1)
                responses.append(response)
            engineering[variant] = {'completed': len(complete), 'E0_pass': sum(r['evaluation']['E0_pass'] for r in complete),
                'internal_unchanged_records': sum(len(r['internal_unchanged']) == 5 for r in complete),
                'max_local_half_tone': max(r['maximum_abs_half_tone'] for r in complete), 'held': held, 'responses': responses,
                'acf_response_pass': sum(r['acf_relative_response_error'] <= .05 for r in responses),
                'dio_response_pass': sum(r['dio_relative_response_error'] <= .05 for r in responses),
                'duration_response_pass': sum(r['duration_relative_response_error'] <= .10 for r in responses)}
        save(RESULT/'summary.json', {'by_engine': by_engine, 'engineering': engineering,
            'decisions': {v: {'content_diagnostic_supported': all(by_engine[e]['comparisons'][v]['all_groups_non_worsening'] for e in by_engine),
                             'quality_certified': False} for v in p['variants'][1:]},
            'model_comparison': read(RESULT/'model-comparison.json'), 'all_requirements_met': False,
            'no_optimization_after_asr': True, 'independent_final_confirmation': False,
            'unresolved': ['局所タイミング・閉鎖・開放・摩擦・声質', '日本語非ニューラル知覚資格', '独立最終品質確認'],
            'limitations': ['教師区間は内部予測で手動境界ではない', 'HMM状態平均と教師波形DIOの測定量差',
                '教師F0採用区間と実行時対象区間の支持域差', '中心化前のクリップがニューラル出力の共通オフセットにも依存',
                '小標本の21群保護は統計的非劣性・ASRの発音転記資格ではない']})
        print({e: {v: c['worsening_groups'] for v, c in r['comparisons'].items()} for e, r in by_engine.items()})


if __name__ == '__main__':
    main()
