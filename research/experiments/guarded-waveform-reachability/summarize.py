"""到達性・内容・干渉を別々に判定する。最適化済み既知4文の診断。"""
import subprocess
import sys
import numpy as np
from campaign import LocalBudget, ROOT, RESULT, WRES, read, save, digest


def paired(rows):
    ok=[r for r in rows if r['status']=='completed']
    errors=sum(r['errors'] for r in ok);native=sum(r['native_errors'] for r in ok);chars=sum(r['characters'] for r in ok)
    return {'expected':len(rows),'missing':len(rows)-len(ok),'independent_texts':len({r['text_id'] for r in rows}),
        'errors':errors,'native_errors':native,'characters':chars,'cer':errors/chars if chars else None,
        'native_cer':native/chars if chars else None,'non_worsening':bool(rows) and len(ok)==len(rows) and errors<=native}


def main():
    with LocalBudget().job('audit','4文の到達性・固定支持域・内容・干渉を集計',2000000):
        p=read(RESULT/'protocol.json');manifest=read(RESULT/'render-manifest.json')
        records={r['id']:r for r in manifest['rows']};engineering=[]
        for row in p['rows']:
            case={v:records[row['id']+'/neutral/'+v] for v in p['variants']}
            search=read(RESULT/'searches'/(row['id']+'.json'))
            record={'text_id':row['id'],'text':row['text'],'length':row['length'],'complete':all(c['status']=='completed' for c in case.values()),
                'attempts':search.get('new_attempts',1),'failed_attempts':search.get('failed_attempts',1),
                'accepted_updates':sum(i['accepted'] for i in search['iterations']),
                'stopping_reasons':[i['stop_reason'] for i in search['iterations'] if 'stop_reason' in i],
                'diagnostic_supported':False,'extra_shrink_renders':search['extra_shrink_renders'],
                'derivative_method_counts':{m:sum(i['derivative_methods'].count(m) for i in search['iterations']) for m in ('central','forward','backward','unavailable')},
                'shrink_attempts':[r for i in search['iterations'] for r in i.get('recoveries',[])]}
            if record['complete']:
                n,s,w=[case[v] for v in p['variants']]
                differences={v:{f:r['measurement'][f]/n['measurement'][f]-1 for f in ('f0_hz','dio_f0_hz','active_seconds')} for v,r in case.items()}
                record.update(wave_mse={v:r['wave_mse'] for v,r in case.items()},state_mse={v:r['state_mse'] for v,r in case.items()},
                    final_coefficients={v:r['coefficients'] for v,r in case.items()},relative_to_native=differences,
                    global_f0_protected=all(abs(differences['wavefit'][f])<=.05 for f in ('f0_hz','dio_f0_hz')),
                    duration_protected=abs(differences['wavefit']['active_seconds'])<=.03,
                    wave_error_below_native=w['wave_mse']<n['wave_mse'],wave_error_at_most_statefit=w['wave_mse']<=s['wave_mse'],
                    final_support_complete=all(r['support_complete'] for r in case.values()),
                    final_E0_pass=all(r['E0_pass'] for r in case.values()),
                    final_internal_unchanged=all(r['internal_unchanged'] for r in case.values()))
                record['diagnostic_supported']=all(record[k] for k in ('global_f0_protected','duration_protected','wave_error_below_native','wave_error_at_most_statefit','final_support_complete','final_E0_pass','final_internal_unchanged'))
                support=read(RESULT/'render'/row['id']/'support-contract.json')
                record.update(common_support_phones=len(support['indices']),excluded_native_support=support['excluded_from_baseline_intersection'])
            old=read(WRES/'searches'/(row['id']+'.json'))
            record['old_strict_comparison']={'wave_mse':{v:old[v].get('wave_mse') for v in p['variants']},
                'attempts':old['new_attempts'],'old_wavefit_sha256':old['wavefit']['wav_sha256'],
                'same_final_wave':case['wavefit'].get('wav_sha256')==old['wavefit']['wav_sha256'],
                'old_stop_reasons':[i['stop_reason'] for i in old['iterations'] if 'stop_reason' in i]}
            engineering.append(record)
        by_engine={}
        for engine in ('whisper','reazon'):
            output={}
            for variant in p['variants'][1:]:
                pairs=[]
                for row in p['rows']:
                    target=RESULT/'asr'/engine/(row['id']+'/neutral/'+variant+'.json')
                    native_path=RESULT/'asr'/engine/(row['id']+'/neutral/native.json')
                    a=read(target) if target.exists() else {'status':'missing'}
                    n=read(native_path) if native_path.exists() else {'status':'missing'}
                    pair={'text_id':row['id'],'text':row['text'],'length':row['length'],'status':'missing'}
                    if a['status']==n['status']=='completed':
                        for r in (a,n):
                            assert r['protocol_sha256']==digest(RESULT/'protocol.json')
                            wav=ROOT/r['wav'];assert digest(wav)==r['wav_sha256']
                        assert a['reference_kana']==n['reference_kana']
                        pair.update(status='completed',errors=a['errors'],native_errors=n['errors'],characters=a['characters'],hypothesis=a['hypothesis'],native_hypothesis=n['hypothesis'])
                    pairs.append(pair)
                groups={g:paired([r for r in pairs if g=='all' or r['length']==g]) for g in ('all','short','long')}
                output[variant]={'pairs':pairs,'groups':groups,'all_groups_non_worsening':all(g['non_worsening'] for g in groups.values())}
            by_engine[engine]=output
        subprocess.run([sys.executable,str(ROOT/'dictionary_diagnostic.py')],check=True)
        content=all(by_engine[e]['wavefit']['all_groups_non_worsening'] for e in by_engine)
        acoustic=all(r['diagnostic_supported'] for r in engineering)
        save(RESULT/'summary.json',{'engineering':engineering,'by_engine':by_engine,
            'wavefit_content_supported':content,'wavefit_acoustic_supported':acoustic,'next_shared_control_research_supported':content and acoustic,
            'new_shared_models_trained':False,'research_inverse_only':True,'generalization_evaluated':False,
            'independent_final_confirmation':False,'quality_certified':False,'all_requirements_met':False,
            'no_optimization_after_asr':True,'limitations':['旧development4文の参照依存逆推定。未知文生成ではない。',
                '教師境界・HMM境界・DIOは日本語の人手正解に対して未資格。','小標本の内容保護は統計的非劣性ではない。',
                '発話ごとの係数は最終bundleへ配布しない。'],
            'unresolved':['未知文共有制御','局所タイミング・閉鎖・開放・摩擦・声質','日本語非ニューラル知覚資格','独立最終品質確認']})
        print({'acoustic':acoustic,'content':content,'next_shared_control_research_supported':content and acoustic},flush=True)

if __name__=='__main__':main()
