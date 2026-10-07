"""認識器・系列別の内容保護と軸別の実音響を集計する。"""
import math
import subprocess
import sys
from campaign import FactorialBudget, ROOT, RESULT, read, save, digest


def paired(rows):
    complete = [r for r in rows if r['status'] == 'completed']
    errors = sum(r['errors'] for r in complete)
    native = sum(r['native_errors'] for r in complete)
    chars = sum(r['characters'] for r in complete)
    return {'expected_wavs': len(rows), 'completed_wavs': len(complete), 'missing': len(rows)-len(complete),
        'independent_texts': len({r['text_id'] for r in rows}), 'errors': errors, 'native_errors': native,
        'characters': chars, 'cer': errors/chars if chars else None, 'native_cer': native/chars if chars else None,
        'error_delta': errors-native, 'observed_non_worsening': bool(rows) and len(complete) == len(rows) and errors <= native,
        'worse_wavs': sum(r['errors'] > r['native_errors'] for r in complete),
        'better_wavs': sum(r['errors'] < r['native_errors'] for r in complete)}


def main():
    budget = FactorialBudget()
    protocol = read(RESULT/'protocol.json')
    manifest = read(RESULT/'render-manifest.json')
    generated = {r['id']: r for r in manifest['rows']}
    with budget.job('audit', '比較集計と辞書診断', 10_000_000):
        subprocess.run([sys.executable, str(ROOT/'dictionary_diagnostic.py')], check=True)
        readings = read(RESULT/'reading-diagnostic.json')
        ambiguous = {(r['engine'], r['id']): bool(r['ambiguities']) for r in readings['rows']}
        engines, raw = {}, {}
        for engine in ('whisper', 'reazon'):
            records = {}
            for row in manifest['rows']:
                p = RESULT/'asr'/engine/(row['id']+'.json')
                record = read(p) if p.exists() else {**row, 'status': 'missing'}
                if record['status'] == 'completed':
                    assert digest(ROOT/row['wav']) == record['wav_sha256'] == row['wav_sha256']
                    assert record['protocol_sha256'] == digest(RESULT/'protocol.json')
                records[row['id']] = record
            raw[engine] = records
            comparisons = {}
            for variant in protocol['variants']:
                if variant == 'native':
                    continue
                pairs = []
                for record in records.values():
                    if record['variant'] != variant:
                        continue
                    text_id = record['id'].split('/')[0]
                    native = records[text_id+'/'+record['condition']+'/native']
                    pair = {'id': record['id'], 'text_id': text_id, 'text': record['text'], 'condition': record['condition'],
                        'length': record['length'], 'challenge_group': record['challenge_group'], 'status': 'missing',
                        'reading_ambiguity': ambiguous.get((engine, record['id']), False),
                        'native_reading_ambiguity': ambiguous.get((engine, native['id']), False)}
                    if record['status'] == native['status'] == 'completed':
                        assert record['reference_kana'] == native['reference_kana']
                        pair.update(status='completed', errors=record['errors'], native_errors=native['errors'],
                            characters=record['characters'], hypothesis=record['hypothesis'], native_hypothesis=native['hypothesis'])
                    pairs.append(pair)
                assert len(pairs) == 24
                groups = {}
                for group in ('all', 'short', 'long', 'g0', 'g1', 'g2', 'g3'):
                    selected = [p for p in pairs if group == 'all' or p['length'] == group or group == 'g'+str(p['challenge_group'])]
                    for condition in ('neutral', 'challenge', 'combined'):
                        groups[group+'/'+condition] = paired([p for p in selected if condition == 'combined' or p['condition'] == condition])
                comparisons[variant] = {'pairs': pairs, 'groups': groups,
                    'all_groups_non_worsening': all(g['observed_non_worsening'] for g in groups.values()),
                    'worsening_groups': [k for k, g in groups.items() if not g['observed_non_worsening']]}
            interactions = []
            for row in protocol['rows']:
                for condition in ('neutral', 'challenge'):
                    ids = {v: row['id']+'/'+condition+'/'+v for v in ('native', 'direct_f0_only', 'direct_duration_only', 'direct_joint')}
                    cases = {v: records[id] for v, id in ids.items()}
                    if all(r['status'] == 'completed' for r in cases.values()):
                        interactions.append({'text_id': row['id'], 'condition': condition,
                            'errors': {v: r['errors'] for v, r in cases.items()},
                            'interaction_error_delta': cases['direct_joint']['errors']-cases['direct_f0_only']['errors']-
                                                      cases['direct_duration_only']['errors']+cases['native']['errors'],
                            'contains_reading_ambiguity': any(ambiguous.get((engine, id), False) for id in ids.values())})
            engines[engine] = {'comparisons': comparisons, 'interactions': interactions,
                'status_counts': {s: sum(r['status'] == s for r in records.values()) for s in ('completed', 'failed', 'missing')}}
        engineering = {}
        for variant in protocol['variants']:
            rows = [r for r in generated.values() if r['variant'] == variant]
            complete = [r for r in rows if r['status'] == 'completed']
            responses, targets, held = [], [], []
            for row in protocol['rows']:
                neutral = generated[row['id']+'/neutral/'+variant]
                challenge = generated[row['id']+'/challenge/'+variant]
                if neutral['status'] == challenge['status'] == 'completed':
                    f0_ratio_error = abs((challenge['measurement']['f0_hz']/neutral['measurement']['f0_hz'])/
                                          (row['requests']['challenge']['requested_f0']/220)-1)
                    duration_ratio_error = abs((challenge['measurement']['active_seconds']/neutral['measurement']['active_seconds'])*
                                              row['requests']['challenge']['speed']-1)
                    responses.append({'text_id': row['id'], 'f0_ratio_error': f0_ratio_error,
                        'duration_ratio_error': duration_ratio_error,
                        'f0_response_pass': f0_ratio_error <= .05, 'duration_response_pass': duration_ratio_error <= .10})
            for record in complete:
                if record['target']:
                    errors = {k: abs(record['measurement'][k]/record['target'][k]-1) for k in ('f0_hz', 'active_seconds')}
                    targets.append({'id': record['id'], 'errors': errors,
                        'targeted_axes': record['settings']['active_axes']})
                if variant in ('direct_f0_only', 'direct_duration_only'):
                    native = generated[record['id'].rsplit('/', 1)[0]+'/native']
                    if native['status'] == 'completed':
                        key = 'active_seconds' if variant == 'direct_f0_only' else 'f0_hz'
                        command = 'speed' if variant == 'direct_f0_only' else 'half_tone'
                        assert record['settings'][command] == native['settings'][command]
                        held.append({'id': record['id'], 'held_command': command, 'command_equal': True,
                            'measured_quantity': key, 'relative_acoustic_difference': record['measurement'][key]/native['measurement'][key]-1})
            engineering[variant] = {'completed': len(complete), 'missing': len(rows)-len(complete),
                'E0_pass': sum(r['evaluation']['E0_pass'] for r in complete),
                'saturated': sum(r['settings']['saturated'] for r in complete),
                'responses': responses, 'f0_response_pass': sum(r['f0_response_pass'] for r in responses),
                'duration_response_pass': sum(r['duration_response_pass'] for r in responses),
                'targets': targets, 'held_axes': held,
                'dio_acf_disagreement_over_10pct': sum(r['measurement'].get('dio_f0_hz') is not None and
                    abs(r['measurement']['f0_hz']/r['measurement']['dio_f0_hz']-1) > .10 for r in complete)}
        disagreements = [{'id': id, 'whisper': raw['whisper'][id]['hypothesis'], 'reazon': raw['reazon'][id]['hypothesis']}
            for id in raw['whisper'] if raw['whisper'][id]['status'] == raw['reazon'][id]['status'] == 'completed'
            and raw['whisper'][id]['predicted_kana'] != raw['reazon'][id]['predicted_kana']]
        save(RESULT/'summary.json', {'by_engine': engines, 'engineering': engineering,
            'decisions': {v: {'content_diagnostic_supported': all(engines[e]['comparisons'][v]['all_groups_non_worsening'] for e in engines),
                'quality_certified': False, 'independent_final_confirmation': False} for v in protocol['variants'] if v != 'native'},
            'disagreements': disagreements, 'all_requirements_met': False, 'no_training_after_asr': True,
            'scope': protocol['scope'], 'content_rule': protocol['content_rule'],
            'unresolved': ['局所イベントと声質', '日本語非ニューラル知覚資格', '未使用集合での最終品質確認']})
    print('系列・認識器別の内容保護と軸間干渉を集計しました')


if __name__ == '__main__':
    main()
