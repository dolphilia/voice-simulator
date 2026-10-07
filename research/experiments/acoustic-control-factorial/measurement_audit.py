"""保存済みACF/DIO測定を対照し、制御指令と実音響を区別する。"""
from campaign import FactorialBudget, RESULT, read, save


def main():
    with FactorialBudget().job('audit', 'ACF・DIOの応答と固定軸の感度を再集計', 2_000_000):
        protocol = read(RESULT/'protocol.json')
        rows = {r['id']: r for r in read(RESULT/'render-manifest.json')['rows']}
        result = {}
        for variant in protocol['variants']:
            responses, held, differences = [], [], []
            for row in protocol['rows']:
                neutral = rows[row['id']+'/neutral/'+variant]
                challenge = rows[row['id']+'/challenge/'+variant]
                measures = {}
                for estimator, field in [('acf', 'f0_hz'), ('dio', 'dio_f0_hz')]:
                    a, b = neutral['measurement'][field], challenge['measurement'][field]
                    error = abs((b/a)/(row['requests']['challenge']['requested_f0']/220)-1) if a and b else None
                    measures[estimator] = {'relative_response_error': error, 'pass_5pct': error is not None and error <= .05}
                responses.append({'text_id': row['id'], **measures})
                for record in (neutral, challenge):
                    m = record['measurement']
                    delta = m['f0_hz']/m['dio_f0_hz']-1 if m['dio_f0_hz'] else None
                    if delta is None or abs(delta) > .10:
                        differences.append({'id': record['id'], 'text': row['text'], 'measurement': m,
                                            'acf_vs_dio_relative_difference': delta})
                    if variant == 'direct_duration_only':
                        native = rows[record['id'].rsplit('/', 1)[0]+'/native']
                        assert record['settings']['half_tone'] == native['settings']['half_tone']
                        held.append({'id': record['id'], 'half_tone_unchanged': True,
                            **{estimator: record['measurement'][field]/native['measurement'][field]-1
                               for estimator, field in [('acf', 'f0_hz'), ('dio', 'dio_f0_hz')]}})
            result[variant] = {'responses': responses,
                'acf_response_pass': sum(r['acf']['pass_5pct'] for r in responses),
                'dio_response_pass': sum(r['dio']['pass_5pct'] for r in responses),
                'disagreements_over_10pct': differences, 'duration_only_held_f0': held}
        save(RESULT/'measurement-audit.json', {'variants': result, 'source': '保存済み120最終波形の測定値',
            'new_ai_calls': 0, 'new_render_calls': 0, 'quality_certified': False,
            'primary_summary_estimator': '70〜800Hzの自己相関中央値',
            'previous_revision_estimator': '70〜800HzのDIO/stonemask中央値',
            'interpretation': '指令が固定でも速度変更は観測F0中央値を変える。測定器間の不一致はどちらの正しさも証明しない。旧版との合格件数を同一測定法として直接比較しない。'})
        print({v: {'acf': r['acf_response_pass'], 'dio': r['dio_response_pass'],
                   'disagreement': len(r['disagreements_over_10pct'])} for v, r in result.items()})


if __name__ == '__main__':
    main()
