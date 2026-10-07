"""全160音声・固定33群・二ASRを集計し、欠測と悪化を保持する。"""
from paths import *


def grouped(pairs):
    groups = {}
    for condition in ['both', 'neutral', 'higher']:
        for group in ['all', 'short', 'long'] + ['group' + str(i) for i in range(8)]:
            chosen = [r for r in pairs if (condition == 'both' or r['condition'] == condition)
                and (group == 'all' or r['length'] == group or (
                    group.startswith('group') and r['challenge_group'] == int(group[5:])))]
            valid = [r for r in chosen if r['status'] == 'completed']
            errors = sum(r['errors'] for r in valid)
            native = sum(r['native_errors'] for r in valid)
            chars = sum(r['characters'] for r in valid)
            groups[condition + '/' + group] = dict(expected=len(chosen), missing=len(chosen)-len(valid),
                errors=errors, native_errors=native, characters=chars,
                non_worsening=bool(chosen) and len(valid) == len(chosen) and chars > 0 and errors <= native)
    assert len(groups) == 33
    return groups


def negative_tests():
    assert not all(v['non_worsening'] for v in grouped([]).values())
    pairs = [dict(condition=c, length=l, challenge_group=g, status='completed',
        errors=0, native_errors=0, characters=10)
        for c in ['neutral', 'higher'] for l in ['short', 'long'] for g in range(8)]
    assert all(v['non_worsening'] for v in grouped(pairs).values())
    pairs[0]['status'] = 'missing'
    assert not all(v['non_worsening'] for v in grouped(pairs).values())
    pairs[0].update(status='completed', errors=1)
    assert not all(v['non_worsening'] for v in grouped(pairs).values())
    return dict(empty_missing_worse_rejected=True, fixture_not_quality_evidence=True)


def main():
    from controller import verify
    verify()
    b = Budget()
    p = read(HERE / 'protocol.json')
    content, engineering, qualifications = {}, {}, {}
    runtime = read(HERE / 'runtime-audit.json')
    assert runtime['passed'] and len(runtime['pairs']) == 192 and len(runtime['CLI']) == 4
    with b.job(NAME, 'audit', '全音声・全群・欠測を固定分母で集計', reserve_bytes=6_000_000) as job:
        for method in p['variants']:
            measures = []
            for row in p['rows']:
                for condition in p['conditions']:
                    path = HERE / 'render' / row['id'] / condition / (method + '.json')
                    value = dict(id=row['id'] + '/' + condition + '/' + method,
                                 status='missing', required_pass=False)
                    if path.exists():
                        record = read(path)
                        assert digest(REPO / record['wav']) == record['wav_sha256']
                        value.update(status=record['status'], E0_pass=record['E0_pass'],
                            invariants_pass=record['invariants_pass'],
                            pitch_gate=record['pitch_gate'], measurement=record['measurement'],
                            generated_lf0_median_hz=record['meta']['generated_lf0_median_hz'],
                            required_pass=record['status'] == 'completed' and record['E0_pass']
                            and record['invariants_pass'] and record['pitch_gate']['passed'])
                    measures.append(value)
            engineering[method] = dict(pairs=measures, expected=32,
                missing=sum(r['status'] != 'completed' for r in measures),
                E0_pass_count=sum(r.get('E0_pass', False) for r in measures),
                pitch_pass_count=sum(r.get('pitch_gate', {}).get('passed', False) for r in measures),
                all_required_pass=len(measures) == 32 and all(r['required_pass'] for r in measures))
            content[method] = {}
            for engine in ['whisper', 'reazon']:
                pairs = []
                for row in p['rows']:
                    for condition in p['conditions']:
                        pair = dict(text_id=row['id'], condition=condition, length=row['length'],
                                    challenge_group=row['challenge_group'], status='missing')
                        a = HERE / 'asr' / engine / row['id'] / condition / (method + '.json')
                        n = a.with_name('native.json')
                        if a.exists() and n.exists():
                            x, y = read(a), read(n)
                            if x['status'] == y['status'] == 'completed':
                                assert x['reference_kana'] == y['reference_kana']
                                assert x['characters'] == y['characters']
                                for r in [x, y]:
                                    assert r['protocol_sha256'] == digest(HERE / 'protocol.json')
                                    assert digest(REPO / r['wav']) == r['wav_sha256']
                                pair.update(status='completed', errors=x['errors'], native_errors=y['errors'],
                                    characters=x['characters'], candidate_hypothesis=x['hypothesis'],
                                    native_hypothesis=y['hypothesis'])
                        pairs.append(pair)
                groups = grouped(pairs)
                content[method][engine] = dict(pairs=pairs, groups=groups,
                    worsening_groups=[n for n, r in groups.items() if not r['non_worsening']],
                    all_groups_non_worsening=len(pairs) == 32 and all(r['non_worsening'] for r in groups.values()))
            qualifications[method] = engineering[method]['all_required_pass'] and all(
                v['all_groups_non_worsening'] for v in content[method].values()) and runtime['passed']
        factorial={}
        for metric in ['missing_support','DIO_error','ACF_error','whisper_errors','reazon_errors']:
            values={}
            for method in p['variants']:
                if metric.endswith('_errors'):
                    pairs=content[method][metric.split('_')[0]]['pairs']
                    values[method]=sum(r['errors'] for r in pairs) if all(r['status']=='completed' for r in pairs) else None
                else:
                    pairs=engineering[method]['pairs']
                    if metric=='missing_support':
                        values[method]=sum(len(r['measurement']['missing_support']) for r in pairs) if all('measurement' in r for r in pairs) else None
                    else:
                        key='dio_error_semitones' if metric=='DIO_error' else 'acf_error_semitones'
                        points=[r.get('pitch_gate',{}).get(key) for r in pairs]
                        values[method]=sum(points)/len(points) if all(x is not None for x in points) else None
            complete=all(x is not None for x in values.values())
            delta={m:values['hts_'+m]-values[m] for m in ['native','calibrated','voicing']} if complete else {}
            factorial[metric]=dict(values=values,complete=complete,lower_is_better=True,renderer_delta_at_each_LF0=delta,
                renderer_main=sum(delta.values())/3 if complete else None,
                calibration_main=((values['calibrated']-values['native'])+(values['hts_calibrated']-values['hts_native']))/2 if complete else None,
                voicing_addition_main=((values['voicing']-values['calibrated'])+(values['hts_voicing']-values['hts_calibrated']))/2 if complete else None,
                renderer_calibration_interaction=delta['calibrated']-delta['native'] if complete else None,
                renderer_voicing_interaction=delta['voicing']-delta['calibrated'] if complete else None)
        summary=dict(content=content, engineering=engineering,
            factorial_analysis=factorial, factorial_analysis_descriptive_only=True,
            qualifications=qualifications, negative_tests=negative_tests(),
            final_non_neural_runtime_verified=True, vocoder_LF0_research_only=True,
            perceptual_qualification=False, protected_confirmation_opened=False,
            quality_goal_completed=False)
        b.write_data(HERE/'summary.json',encode(summary),job)
        compact=dict(summary)
        compact['engineering']={m:{k:v for k,v in e.items() if k!='pairs'} for m,e in engineering.items()}
        compact['content']={m:{n:{k:v for k,v in result.items() if k!='pairs'} for n,result in engines.items()} for m,engines in content.items()}
        compact['detailed_summary_path']=str((HERE/'summary.json').relative_to(REPO))
        compact['detailed_summary_sha256']=digest(HERE/'summary.json')
        compact['individual_records_external']=True
        b.save(HERE/'aggregate-summary.json',compact,job)
    print(qualifications, flush=True)
    print(b.reconcile(), flush=True)


if __name__ == '__main__':
    main()
